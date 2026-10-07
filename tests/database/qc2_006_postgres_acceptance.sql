SET LOCAL row_security = on;

DO $isolation_check$
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'serializable' THEN
    RAISE EXCEPTION 'QC2-006 PostgreSQL acceptance must run at SERIALIZABLE isolation';
  END IF;
END
$isolation_check$;

DO $canonical_hash_parity$
BEGIN
  IF qc2_integrity_build.canonical_jsonb_text('{"z":"é","a":1}'::jsonb)
       <> '{"a":1,"z":"é"}'
    OR qc2_integrity_build.hash_json(
      'qc2.cross-language-fixture.v1',
      '{"z":"é","a":1}'::jsonb
    ) <> 'e36fa0a3f70037fb1708b319479be031bc0dcd5c553877c49e826273b5e00109' THEN
    RAISE EXCEPTION 'PostgreSQL canonical JSON/hash differs from the Python fixture';
  END IF;
END
$canonical_hash_parity$;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_evidence;
SELECT qc2_integrity_build.create_evidence_stream(
  'qc2-006-test-installation',
  'test',
  'qc2-006-evidence',
  'SYNTHETIC_FIXTURE'
);
RESET SESSION AUTHORIZATION;

DO $genesis_verification$
DECLARE
  event_row qc2_integrity_build.evidence_event%ROWTYPE;
  payload jsonb;
  stream_row qc2_integrity_build.evidence_stream_head%ROWTYPE;
BEGIN
  SELECT * INTO STRICT stream_row
    FROM qc2_integrity_build.evidence_stream_head
    WHERE stream_id = 'qc2-006-evidence';
  IF stream_row.head_sequence <> 1
    OR stream_row.event_count <> 1
    OR stream_row.evidence_class <> 'SYNTHETIC_FIXTURE' THEN
    RAISE EXCEPTION 'Evidence stream genesis state is invalid';
  END IF;

  SELECT * INTO STRICT event_row
    FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-evidence' AND sequence = 1;
  payload := pg_catalog.convert_from(event_row.payload_bytes, 'UTF8')::jsonb;
  IF event_row.event_contract->>'event_type' <> 'stream_genesis'
    OR qc2_integrity_build.canonical_jsonb_text(payload)
       <> pg_catalog.convert_from(event_row.payload_bytes, 'UTF8')
    OR qc2_integrity_build.hash_json('qc2.evidence-payload.v1', payload)
       <> event_row.payload_hash
    OR qc2_integrity_build.hash_json(
       'qc2.evidence-event.v1',
       event_row.event_contract - ARRAY['event_hash','content_hash']::text[]
    ) <> event_row.event_hash
    OR qc2_integrity_build.hash_json(
       'qc2.contract-content.v1/qc2.integrity_build.evidenceevent.v1/1.0',
       event_row.event_contract
         - ARRAY['schema_name','schema_version','id','created_at','content_hash']::text[]
    ) <> event_row.content_hash
    OR event_row.event_contract->>'event_hash' <> stream_row.head_event_hash THEN
    RAISE EXCEPTION 'Evidence event contract, payload, or chain hash is invalid';
  END IF;
END
$genesis_verification$;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_execution;
SELECT qc2_control.reserve_resource(
  '018f0000-0000-7000-8000-00000000000a',
  'paper:account-1:AAPL',
  'qc2-006-reservation',
  1
);
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
SELECT * FROM qc2_control.register_job_and_enqueue_outbox(
  '018f0000-0000-7000-8000-00000000000b',
  'qc2-006-atomic-job',
  pg_catalog.clock_timestamp() + interval '5 minutes',
  '018f0000-0000-7000-8000-00000000000c',
  '018f0000-0000-7000-8000-00000000000d',
  'qc2_006_dispatch',
  repeat('a', 64)
);
SELECT qc2_control.enqueue_outbox(
  '018f0000-0000-7000-8000-00000000000e',
  '018f0000-0000-7000-8000-00000000000f',
  'qc2_006_dispatch',
  repeat('b', 64)
);
RESET SESSION AUTHORIZATION;

DO $mutation_capture_check$
DECLARE
  captured_types text[];
BEGIN
  SELECT pg_catalog.array_agg(event_contract->>'event_type' ORDER BY sequence)
    INTO captured_types
    FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-evidence';
  IF NOT captured_types @> ARRAY[
    'reservation_resource_update',
    'resource_reservation_insert',
    'job_definition_insert',
    'outbox_message_insert'
  ]::text[] THEN
    RAISE EXCEPTION 'Protected domain mutations did not append evidence';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-evidence'
      AND event_contract->>'actor_identity' = 'execution'
      AND event_contract->>'event_type' = 'resource_reservation_insert'
  ) OR NOT EXISTS (
    SELECT 1 FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-evidence'
      AND event_contract->>'actor_identity' = 'durable_job_service'
      AND event_contract->>'event_type' = 'job_definition_insert'
  ) THEN
    RAISE EXCEPTION 'Evidence did not retain the authorized mutation identities';
  END IF;
END
$mutation_capture_check$;

CREATE TEMP TABLE qc2_006_rollback_head AS
SELECT stream_id, head_sequence, head_event_hash
FROM qc2_integrity_build.evidence_stream_head
WHERE stream_id = 'qc2-006-evidence';
SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
SAVEPOINT qc2_006_rollback_probe;
SELECT qc2_control.register_job(
  '018f0000-0000-7000-8000-000000000010',
  'qc2-006-rolled-back-job',
  pg_catalog.clock_timestamp() + interval '5 minutes'
);
ROLLBACK TO SAVEPOINT qc2_006_rollback_probe;
RESET SESSION AUTHORIZATION;
DO $rollback_atomicity_check$
BEGIN
  IF EXISTS (
    SELECT 1 FROM qc2_control.job_definition
    WHERE logical_key = 'qc2-006-rolled-back-job'
  ) OR EXISTS (
    SELECT 1
    FROM qc2_integrity_build.evidence_stream_head AS current_head
    JOIN qc2_006_rollback_head AS old_head USING (stream_id)
    WHERE current_head.head_sequence <> old_head.head_sequence
       OR current_head.head_event_hash <> old_head.head_event_hash
  ) THEN
    RAISE EXCEPTION 'Savepoint rollback left either a domain row or evidence head';
  END IF;
END
$rollback_atomicity_check$;
RELEASE SAVEPOINT qc2_006_rollback_probe;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
SELECT qc2_control.enqueue_outbox(
  '018f0000-0000-7000-8000-000000000011',
  '018f0000-0000-7000-8000-000000000012',
  'qc2_006_conflict',
  repeat('c', 64)
);
RESET SESSION AUTHORIZATION;
CREATE TEMP TABLE qc2_006_outbox_head AS
SELECT stream_id, head_sequence, head_event_hash
FROM qc2_integrity_build.evidence_stream_head
WHERE stream_id = 'qc2-006-evidence';
SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
DO $cross_domain_atomicity_check$
DECLARE
  conflict_seen boolean := false;
BEGIN
  BEGIN
    PERFORM qc2_control.register_job_and_enqueue_outbox(
      '018f0000-0000-7000-8000-000000000013',
      'qc2-006-must-rollback',
      pg_catalog.clock_timestamp() + interval '5 minutes',
      '018f0000-0000-7000-8000-000000000014',
      '018f0000-0000-7000-8000-000000000012',
      'qc2_006_conflict',
      repeat('d', 64)
    );
    RAISE EXCEPTION 'expected conflicting outbox operation to abort';
  EXCEPTION WHEN unique_violation THEN
    conflict_seen := true;
  END;
  IF NOT conflict_seen THEN
    RAISE EXCEPTION 'conflicting outbox operation was not rejected';
  END IF;
END
$cross_domain_atomicity_check$;
RESET SESSION AUTHORIZATION;
DO $cross_domain_rollback_check$
BEGIN
  IF EXISTS (
    SELECT 1 FROM qc2_control.job_definition
    WHERE logical_key = 'qc2-006-must-rollback'
  ) OR EXISTS (
    SELECT 1
    FROM qc2_integrity_build.evidence_stream_head AS current_head
    JOIN qc2_006_outbox_head AS old_head USING (stream_id)
    WHERE current_head.head_sequence <> old_head.head_sequence
       OR current_head.head_event_hash <> old_head.head_event_hash
  ) THEN
    RAISE EXCEPTION 'Outbox conflict did not roll back the domain row and evidence';
  END IF;
END
$cross_domain_rollback_check$;

CREATE TEMP TABLE qc2_006_no_stream_head AS
SELECT stream_id, head_sequence, head_event_hash
FROM qc2_integrity_build.evidence_stream_head
WHERE stream_id = 'qc2-006-evidence';
SET LOCAL SESSION AUTHORIZATION qc2_migrator;
UPDATE qc2_integrity_build.evidence_stream_head
  SET active = false
  WHERE stream_id = 'qc2-006-evidence';
RESET SESSION AUTHORIZATION;
SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
DO $append_failure_check$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    PERFORM qc2_control.register_job(
      '018f0000-0000-7000-8000-000000000015',
      'qc2-006-no-stream-job',
      pg_catalog.clock_timestamp() + interval '5 minutes'
    );
  EXCEPTION WHEN check_violation THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Protected mutation succeeded without an active evidence stream';
  END IF;
END
$append_failure_check$;
RESET SESSION AUTHORIZATION;
SET LOCAL SESSION AUTHORIZATION qc2_migrator;
UPDATE qc2_integrity_build.evidence_stream_head
  SET active = true
  WHERE stream_id = 'qc2-006-evidence';
RESET SESSION AUTHORIZATION;
DO $append_failure_rollback_check$
BEGIN
  IF EXISTS (
    SELECT 1 FROM qc2_control.job_definition
    WHERE logical_key = 'qc2-006-no-stream-job'
  ) OR EXISTS (
    SELECT 1
    FROM qc2_integrity_build.evidence_stream_head AS current_head
    JOIN qc2_006_no_stream_head AS old_head USING (stream_id)
    WHERE current_head.head_sequence <> old_head.head_sequence
       OR current_head.head_event_hash <> old_head.head_event_hash
  ) THEN
    RAISE EXCEPTION 'Failed evidence append did not abort its protected mutation';
  END IF;
END
$append_failure_rollback_check$;

SET LOCAL SESSION AUTHORIZATION qc2_migrator;
DO $immutable_evidence_check$
DECLARE
  event_id uuid;
  checkpoint_id uuid;
  denied boolean;
BEGIN
  SELECT id INTO STRICT event_id
    FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-evidence' AND sequence = 1;
  SELECT id INTO STRICT checkpoint_id
    FROM qc2_integrity_build.evidence_checkpoint
    WHERE stream_id = 'qc2-006-evidence';

  denied := false;
  BEGIN
    UPDATE qc2_integrity_build.evidence_event
      SET event_hash = repeat('f', 64)
      WHERE id = event_id;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Evidence event update was accepted';
  END IF;

  denied := false;
  BEGIN
    DELETE FROM qc2_integrity_build.evidence_event WHERE id = event_id;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Evidence event deletion was accepted';
  END IF;

  denied := false;
  BEGIN
    EXECUTE 'TRUNCATE qc2_integrity_build.evidence_event';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Evidence event truncation was accepted';
  END IF;

  denied := false;
  BEGIN
    UPDATE qc2_integrity_build.evidence_checkpoint
      SET checkpoint_hash = repeat('e', 64)
      WHERE id = checkpoint_id;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Checkpoint update was accepted';
  END IF;
END
$immutable_evidence_check$;
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_evidence;
SELECT qc2_integrity_build.rotate_evidence_stream('qc2-006-rotated');
RESET SESSION AUTHORIZATION;
DO $rotation_check$
DECLARE
  new_genesis jsonb;
  new_genesis_payload jsonb;
  prior_checkpoint record;
BEGIN
  SELECT id, checkpoint_hash, content_hash
    INTO STRICT prior_checkpoint
    FROM qc2_integrity_build.evidence_checkpoint
    WHERE stream_id = 'qc2-006-evidence'
    ORDER BY created_at DESC, id DESC
    LIMIT 1;
  SELECT event_contract, pg_catalog.convert_from(payload_bytes, 'UTF8')::jsonb
    INTO STRICT new_genesis, new_genesis_payload
    FROM qc2_integrity_build.evidence_event
    WHERE stream_id = 'qc2-006-rotated' AND sequence = 1;
  IF new_genesis->>'event_type' <> 'stream_genesis'
    OR new_genesis->'source_refs'->0->>'target_id' <> prior_checkpoint.id::text
    OR new_genesis->'source_refs'->0->>'content_hash' <> prior_checkpoint.content_hash
    OR new_genesis_payload->>'previous_checkpoint_hash' <> prior_checkpoint.checkpoint_hash
    OR new_genesis_payload->>'previous_stream_id' <> 'qc2-006-evidence'
    OR new_genesis->'dependency_refs' <> '[]'::jsonb
    OR new_genesis->>'previous_event_hash' IS NOT NULL
    OR NOT EXISTS (
      SELECT 1 FROM qc2_integrity_build.evidence_stream_head
      WHERE stream_id = 'qc2-006-evidence' AND NOT active
    )
    OR NOT EXISTS (
      SELECT 1 FROM qc2_integrity_build.evidence_stream_head
      WHERE stream_id = 'qc2-006-rotated' AND active
    ) THEN
    RAISE EXCEPTION 'Evidence rotation did not anchor the prior checkpoint';
  END IF;
END
$rotation_check$;

RESET SESSION AUTHORIZATION;
