-- QC2-006: transactional evidence chains, checkpoints, and mutation capture.
-- This migration extends the immutable QC2-005 authority foundation.
SET ROLE qc2_migrator;

DO $pgcrypto_setup$
DECLARE
  extension_schema text;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_extension WHERE extname = 'pgcrypto'
  ) THEN
    EXECUTE 'CREATE EXTENSION pgcrypto WITH SCHEMA qc2_integrity_build';
  END IF;

  SELECT namespace.nspname
    INTO extension_schema
    FROM pg_catalog.pg_extension AS extension
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = extension.extnamespace
    WHERE extension.extname = 'pgcrypto';

  IF extension_schema <> 'qc2_integrity_build' THEN
    RAISE EXCEPTION
      'pgcrypto must be installed in qc2_integrity_build before QC2-006';
  END IF;
END
$pgcrypto_setup$;

ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE TABLE qc2_integrity_build.evidence_stream_head (
  stream_id text PRIMARY KEY CHECK (stream_id ~ '^[a-z][a-z0-9_-]{0,95}$'),
  installation_id text NOT NULL CHECK (installation_id ~ '^[a-z][a-z0-9_-]{0,95}$'),
  environment_namespace text NOT NULL
    CHECK (environment_namespace IN ('development','test','research','production')),
  evidence_class text NOT NULL
    CHECK (evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )),
  head_sequence bigint NOT NULL DEFAULT 0
    CHECK (head_sequence BETWEEN 0 AND 9007199254740991),
  head_event_hash text,
  event_count bigint NOT NULL DEFAULT 0
    CHECK (event_count BETWEEN 0 AND 9007199254740991),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CHECK (event_count = head_sequence),
  CHECK (
    (head_sequence = 0 AND head_event_hash IS NULL)
    OR (head_sequence > 0 AND head_event_hash ~ '^[0-9a-f]{64}$')
  )
);

CREATE UNIQUE INDEX evidence_stream_one_active_per_environment
  ON qc2_integrity_build.evidence_stream_head(environment_namespace)
  WHERE active;

CREATE TABLE qc2_integrity_build.evidence_event (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  stream_id text NOT NULL REFERENCES qc2_integrity_build.evidence_stream_head(stream_id)
    ON DELETE RESTRICT,
  sequence bigint NOT NULL CHECK (sequence BETWEEN 1 AND 9007199254740991),
  event_hash text NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  payload_bytes bytea NOT NULL,
  event_contract jsonb NOT NULL CHECK (
    event_contract->>'schema_name' = 'qc2.integrity_build.EvidenceEvent.v1'
    AND event_contract->>'schema_version' = '1.0'
    AND event_contract->>'owning_authority' = 'evidence'
    AND event_contract->>'id' = id::text
    AND event_contract->>'stream_id' = stream_id
    AND (event_contract->>'sequence')::bigint = sequence
    AND event_contract->>'event_hash' = event_hash
    AND event_contract->>'content_hash' = content_hash
    AND event_contract->>'payload_hash' = payload_hash
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (stream_id, sequence)
);

CREATE TABLE qc2_integrity_build.evidence_checkpoint (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  stream_id text NOT NULL REFERENCES qc2_integrity_build.evidence_stream_head(stream_id)
    ON DELETE RESTRICT,
  checkpoint_hash text NOT NULL UNIQUE CHECK (checkpoint_hash ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  previous_checkpoint_hash text
    CHECK (previous_checkpoint_hash IS NULL OR previous_checkpoint_hash ~ '^[0-9a-f]{64}$'),
  artifact_refs jsonb NOT NULL CHECK (jsonb_typeof(artifact_refs) = 'array'),
  checkpoint_contract jsonb NOT NULL CHECK (
    checkpoint_contract->>'schema_name' = 'qc2.integrity_build.Checkpoint.v1'
    AND checkpoint_contract->>'schema_version' = '1.0'
    AND checkpoint_contract->>'owning_authority' = 'evidence'
    AND checkpoint_contract->>'id' = id::text
    AND checkpoint_contract->>'stream_id' = stream_id
    AND checkpoint_contract->>'checkpoint_hash' = checkpoint_hash
    AND checkpoint_contract->>'content_hash' = content_hash
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (stream_id, checkpoint_hash)
);

ALTER TABLE qc2_integrity_build.evidence_stream_head ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.evidence_stream_head FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.evidence_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.evidence_event FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.evidence_checkpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.evidence_checkpoint FORCE ROW LEVEL SECURITY;

CREATE POLICY evidence_stream_migrator_all ON qc2_integrity_build.evidence_stream_head
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY evidence_event_migrator_all ON qc2_integrity_build.evidence_event
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY evidence_checkpoint_migrator_all ON qc2_integrity_build.evidence_checkpoint
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

CREATE POLICY evidence_stream_runtime_read ON qc2_integrity_build.evidence_stream_head
  FOR SELECT TO
    qc2_runtime_evidence, qc2_runtime_model_registry, qc2_runtime_core,
    qc2_runtime_apexlab, qc2_runtime_validation, qc2_runtime_owner_api,
    qc2_runtime_configuration, qc2_runtime_governance, qc2_runtime_build_governance
  USING (true);
CREATE POLICY evidence_event_runtime_read ON qc2_integrity_build.evidence_event
  FOR SELECT TO
    qc2_runtime_evidence, qc2_runtime_model_registry, qc2_runtime_core,
    qc2_runtime_apexlab, qc2_runtime_validation, qc2_runtime_owner_api,
    qc2_runtime_configuration, qc2_runtime_governance, qc2_runtime_build_governance
  USING (true);
CREATE POLICY evidence_checkpoint_runtime_read ON qc2_integrity_build.evidence_checkpoint
  FOR SELECT TO
    qc2_runtime_evidence, qc2_runtime_model_registry, qc2_runtime_core,
    qc2_runtime_apexlab, qc2_runtime_validation, qc2_runtime_owner_api,
    qc2_runtime_configuration, qc2_runtime_governance, qc2_runtime_build_governance
  USING (true);

CREATE FUNCTION qc2_integrity_build.canonical_jsonb_text(p_value jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog, qc2_integrity_build
AS $function$
DECLARE
  value_kind text := pg_catalog.jsonb_typeof(p_value);
  item record;
  result_text text;
  separator text := '';
  scalar_text text;
  key_count bigint;
  normalized_key_count bigint;
BEGIN
  IF value_kind = 'null' THEN
    RETURN 'null';
  ELSIF value_kind = 'boolean' THEN
    RETURN p_value::text;
  ELSIF value_kind = 'string' THEN
    RETURN pg_catalog.to_json(normalize(p_value #>> '{}', NFC))::text;
  ELSIF value_kind = 'number' THEN
    scalar_text := p_value #>> '{}';
    IF scalar_text !~ '^-?(0|[1-9][0-9]*)$'
      OR pg_catalog.abs(scalar_text::numeric) > 9007199254740991 THEN
      RAISE EXCEPTION 'QC2 canonical JSON permits only safe integers'
        USING ERRCODE = '22023';
    END IF;
    IF scalar_text::numeric = 0 THEN
      RETURN '0';
    END IF;
    RETURN scalar_text;
  ELSIF value_kind = 'array' THEN
    result_text := '[';
    FOR item IN
      SELECT element, ordinal
      FROM pg_catalog.jsonb_array_elements(p_value) WITH ORDINALITY AS rows(element, ordinal)
      ORDER BY ordinal
    LOOP
      result_text := result_text || separator
        || qc2_integrity_build.canonical_jsonb_text(item.element);
      separator := ',';
    END LOOP;
    RETURN result_text || ']';
  ELSIF value_kind = 'object' THEN
    SELECT count(*), count(DISTINCT normalize(key, NFC))
      INTO key_count, normalized_key_count
      FROM pg_catalog.jsonb_object_keys(p_value) AS keys(key);
    IF key_count <> normalized_key_count THEN
      RAISE EXCEPTION 'NFC normalization creates duplicate JSON object keys'
        USING ERRCODE = '22023';
    END IF;

    result_text := '{';
    FOR item IN
      SELECT normalize(key, NFC) AS normalized_key, value
      FROM pg_catalog.jsonb_each(p_value) AS pairs(key, value)
      ORDER BY pg_catalog.convert_to(normalize(key, NFC), 'UTF8')
    LOOP
      result_text := result_text || separator
        || pg_catalog.to_json(item.normalized_key)::text || ':'
        || qc2_integrity_build.canonical_jsonb_text(item.value);
      separator := ',';
    END LOOP;
    RETURN result_text || '}';
  END IF;

  RAISE EXCEPTION 'Unsupported JSON value for QC2 canonicalization'
    USING ERRCODE = '22023';
END
$function$;

CREATE FUNCTION qc2_integrity_build.hash_json(p_domain text, p_value jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog, qc2_integrity_build
AS $function$
  SELECT pg_catalog.encode(
    qc2_integrity_build.digest(
      pg_catalog.decode('5143322d484153482d563100', 'hex')
      || pg_catalog.convert_to(p_domain, 'UTF8')
      || pg_catalog.decode('00', 'hex')
      || pg_catalog.convert_to(
        qc2_integrity_build.canonical_jsonb_text(p_value),
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  )
$function$;

CREATE FUNCTION qc2_integrity_build.new_uuid_v7()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_integrity_build
AS $function$
DECLARE
  timestamp_ms bigint;
  uuid_hex text;
  variant_value integer;
BEGIN
  timestamp_ms := pg_catalog.floor(
    extract(epoch FROM pg_catalog.clock_timestamp()) * 1000
  )::bigint;
  uuid_hex := pg_catalog.lpad(pg_catalog.to_hex(timestamp_ms), 12, '0')
    || pg_catalog.encode(qc2_integrity_build.gen_random_bytes(10), 'hex');
  uuid_hex := pg_catalog.substr(uuid_hex, 1, 12)
    || '7' || pg_catalog.substr(uuid_hex, 14, 3)
    || pg_catalog.substr(uuid_hex, 17);
  variant_value := (('x' || pg_catalog.substr(uuid_hex, 17, 1))::bit(4)::integer & 3) | 8;
  uuid_hex := pg_catalog.substr(uuid_hex, 1, 16)
    || pg_catalog.to_hex(variant_value)
    || pg_catalog.substr(uuid_hex, 18);
  RETURN (
    pg_catalog.substr(uuid_hex, 1, 8) || '-'
    || pg_catalog.substr(uuid_hex, 9, 4) || '-'
    || pg_catalog.substr(uuid_hex, 13, 4) || '-'
    || pg_catalog.substr(uuid_hex, 17, 4) || '-'
    || pg_catalog.substr(uuid_hex, 21, 12)
  )::uuid;
END
$function$;

CREATE FUNCTION qc2_integrity_build.prevent_integrity_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'QC2 evidence and checkpoint records are append-only'
    USING ERRCODE = '42501';
END
$function$;

CREATE TRIGGER evidence_event_no_update_delete
BEFORE UPDATE OR DELETE ON qc2_integrity_build.evidence_event
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_integrity_rewrite();
CREATE TRIGGER evidence_event_no_truncate
BEFORE TRUNCATE ON qc2_integrity_build.evidence_event
FOR EACH STATEMENT EXECUTE FUNCTION qc2_integrity_build.prevent_integrity_rewrite();
CREATE TRIGGER evidence_checkpoint_no_update_delete
BEFORE UPDATE OR DELETE ON qc2_integrity_build.evidence_checkpoint
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_integrity_rewrite();
CREATE TRIGGER evidence_checkpoint_no_truncate
BEFORE TRUNCATE ON qc2_integrity_build.evidence_checkpoint
FOR EACH STATEMENT EXECUTE FUNCTION qc2_integrity_build.prevent_integrity_rewrite();

CREATE FUNCTION qc2_integrity_build.append_event_internal(
  p_event_type text,
  p_payload jsonb,
  p_monotonic_generation bigint DEFAULT 0,
  p_source_refs jsonb DEFAULT '[]'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  stream_row qc2_integrity_build.evidence_stream_head%ROWTYPE;
  event_id uuid;
  event_time timestamptz;
  event_time_text text;
  payload_bytes bytea;
  payload_hash text;
  event_body jsonb;
  event_hash text;
  content_hash text;
  event_contract jsonb;
  actor text;
  next_sequence bigint;
BEGIN
  actor := qc2_control.current_runtime_authority();
  IF p_event_type !~ '^[a-z][a-z0-9_-]{0,95}$'
    OR p_monotonic_generation < 0
    OR p_monotonic_generation > 9007199254740991
    OR pg_catalog.jsonb_typeof(p_payload) <> 'object'
    OR pg_catalog.jsonb_typeof(p_source_refs) <> 'array' THEN
    RAISE EXCEPTION 'Evidence event input is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT * INTO stream_row
    FROM qc2_integrity_build.evidence_stream_head
    WHERE active
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'No active evidence stream is configured'
      USING ERRCODE = '23514';
  END IF;
  IF stream_row.evidence_class = 'FORWARD_SEALED' THEN
    RAISE EXCEPTION 'FORWARD_SEALED writes require an approved independent anchor'
      USING ERRCODE = '55000';
  END IF;
  IF stream_row.head_sequence >= 9007199254740991 THEN
    RAISE EXCEPTION 'Evidence stream sequence exhausted the safe-integer range'
      USING ERRCODE = '22003';
  END IF;

  next_sequence := stream_row.head_sequence + 1;
  event_id := qc2_integrity_build.new_uuid_v7();
  event_time := pg_catalog.clock_timestamp();
  event_time_text := pg_catalog.to_char(
    event_time AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  payload_bytes := pg_catalog.convert_to(
    qc2_integrity_build.canonical_jsonb_text(p_payload),
    'UTF8'
  );
  payload_hash := qc2_integrity_build.hash_json(
    'qc2.evidence-payload.v1',
    p_payload
  );

  event_body := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.integrity_build.EvidenceEvent.v1',
    'schema_version', '1.0',
    'id', event_id::text,
    'created_at', event_time_text,
    'owning_authority', 'evidence',
    'evidence_class', stream_row.evidence_class,
    'environment_namespace', stream_row.environment_namespace,
    'source_refs', p_source_refs,
    'installation_id', stream_row.installation_id,
    'stream_id', stream_row.stream_id,
    'sequence', next_sequence,
    'event_type', p_event_type,
    'actor_identity', actor,
    'authorized_command_ref', NULL,
    'correlation_id', p_event_type || '-' || pg_catalog.replace(event_id::text, '-', ''),
    'payload_hash', payload_hash,
    'dependency_refs', '[]'::jsonb,
    'previous_event_hash', stream_row.head_event_hash,
    'wall_clock_at', event_time_text,
    'monotonic_generation', p_monotonic_generation
  );
  event_hash := qc2_integrity_build.hash_json(
    'qc2.evidence-event.v1',
    event_body
  );
  event_contract := event_body || pg_catalog.jsonb_build_object(
    'event_hash', event_hash
  );
  content_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.integrity_build.evidenceevent.v1/1.0',
    event_contract - ARRAY[
      'schema_name', 'schema_version', 'id', 'created_at', 'content_hash'
    ]::text[]
  );
  event_contract := event_contract || pg_catalog.jsonb_build_object(
    'content_hash', content_hash
  );

  INSERT INTO qc2_integrity_build.evidence_event(
    id, stream_id, sequence, event_hash, content_hash, payload_hash,
    payload_bytes, event_contract, created_at
  )
  VALUES (
    event_id, stream_row.stream_id, next_sequence, event_hash, content_hash,
    payload_hash, payload_bytes, event_contract, event_time
  );

  UPDATE qc2_integrity_build.evidence_stream_head
    SET head_sequence = next_sequence,
        event_count = next_sequence,
        head_event_hash = event_hash
    WHERE stream_id = stream_row.stream_id;

  RETURN event_id;
END
$function$;

CREATE FUNCTION qc2_integrity_build.record_domain_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  row_value jsonb;
  event_payload jsonb;
  row_id text;
  event_generation bigint := 0;
  event_type text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    row_value := pg_catalog.to_jsonb(OLD);
  ELSE
    row_value := pg_catalog.to_jsonb(NEW);
  END IF;
  event_type := pg_catalog.lower(TG_TABLE_NAME || '_' || TG_OP);

  IF TG_TABLE_NAME IN ('job_definition', 'outbox_message', 'resource_reservation') THEN
    row_id := row_value->>'id';
  ELSIF TG_TABLE_NAME = 'job_lease' THEN
    row_id := row_value->>'job_id';
  ELSIF TG_TABLE_NAME = 'reservation_resource' THEN
    row_id := qc2_integrity_build.hash_json(
      'qc2.evidence.redacted-key.v1',
      pg_catalog.jsonb_build_object('key', row_value->>'resource_key')
    );
  ELSE
    RAISE EXCEPTION 'No evidence policy for mutated relation %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME
      USING ERRCODE = '55000';
  END IF;

  event_payload := pg_catalog.jsonb_build_object(
    'relation', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
    'operation', pg_catalog.lower(TG_OP),
    'row_id', row_id
  );

  IF TG_TABLE_NAME = 'job_definition' THEN
    event_payload := event_payload || pg_catalog.jsonb_build_object(
      'logical_key', row_value->>'logical_key',
      'state', row_value->>'state',
      'deadline', row_value->>'deadline'
    );
  ELSIF TG_TABLE_NAME = 'job_lease' THEN
    event_generation := (row_value->>'fencing_generation')::bigint;
    event_payload := event_payload || pg_catalog.jsonb_build_object(
      'job_id', row_value->>'job_id',
      'lease_owner', row_value->>'lease_owner',
      'fencing_generation', event_generation,
      'lease_expires_at', row_value->>'lease_expires_at'
    );
  ELSIF TG_TABLE_NAME = 'outbox_message' THEN
    event_generation := (row_value->>'fencing_generation')::bigint;
    event_payload := event_payload || pg_catalog.jsonb_build_object(
      'logical_operation_id', row_value->>'logical_operation_id',
      'message_type', row_value->>'message_type',
      'payload_hash', row_value->>'payload_hash',
      'status', row_value->>'status',
      'attempt_count', (row_value->>'attempt_count')::bigint,
      'fencing_generation', event_generation
    );
  ELSIF TG_TABLE_NAME = 'reservation_resource' THEN
    event_generation := (row_value->>'generation')::bigint;
    event_payload := event_payload || pg_catalog.jsonb_build_object(
      'capacity', pg_catalog.trim_scale((row_value->>'capacity')::numeric)::text,
      'reserved', pg_catalog.trim_scale((row_value->>'reserved')::numeric)::text,
      'generation', event_generation
    );
  ELSIF TG_TABLE_NAME = 'resource_reservation' THEN
    event_payload := event_payload || pg_catalog.jsonb_build_object(
      'resource_key_hash', qc2_integrity_build.hash_json(
        'qc2.evidence.redacted-key.v1',
        pg_catalog.jsonb_build_object('key', row_value->>'resource_key')
      ),
      'reservation_key_hash', qc2_integrity_build.hash_json(
        'qc2.evidence.redacted-key.v1',
        pg_catalog.jsonb_build_object('key', row_value->>'reservation_key')
      ),
      'quantity', pg_catalog.trim_scale((row_value->>'quantity')::numeric)::text,
      'state', row_value->>'state'
    );
  END IF;

  PERFORM qc2_integrity_build.append_event_internal(
    event_type,
    event_payload,
    event_generation
  );
  RETURN NULL;
END
$function$;

CREATE TRIGGER evidence_job_definition_mutations
AFTER INSERT OR UPDATE OR DELETE ON qc2_control.job_definition
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.record_domain_mutation();
CREATE TRIGGER evidence_job_lease_mutations
AFTER INSERT OR UPDATE OR DELETE ON qc2_control.job_lease
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.record_domain_mutation();
CREATE TRIGGER evidence_outbox_mutations
AFTER INSERT OR UPDATE OR DELETE ON qc2_control.outbox_message
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.record_domain_mutation();
CREATE TRIGGER evidence_reservation_resource_mutations
AFTER INSERT OR UPDATE OR DELETE ON qc2_execution.reservation_resource
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.record_domain_mutation();
CREATE TRIGGER evidence_resource_reservation_mutations
AFTER INSERT OR UPDATE OR DELETE ON qc2_execution.resource_reservation
FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.record_domain_mutation();

CREATE FUNCTION qc2_integrity_build.create_checkpoint(p_artifact_refs jsonb DEFAULT '[]'::jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  stream_row qc2_integrity_build.evidence_stream_head%ROWTYPE;
  checkpoint_id uuid;
  checkpoint_time timestamptz;
  checkpoint_time_text text;
  previous_hash text;
  ordered_refs jsonb;
  artifact_root_hash text;
  checkpoint_hash text;
  content_hash text;
  checkpoint_body jsonb;
  checkpoint_contract jsonb;
  invalid_count bigint;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('evidence');
  IF pg_catalog.jsonb_typeof(p_artifact_refs) <> 'array' THEN
    RAISE EXCEPTION 'Checkpoint artifact refs must be an array'
      USING ERRCODE = '22023';
  END IF;

  SELECT count(*)
    INTO invalid_count
    FROM pg_catalog.jsonb_array_elements(p_artifact_refs) AS refs(ref)
    WHERE pg_catalog.jsonb_typeof(ref) <> 'object'
      OR CASE
        WHEN pg_catalog.jsonb_typeof(ref) = 'object' THEN (
          SELECT count(*) FROM pg_catalog.jsonb_object_keys(ref)
        ) NOT BETWEEN 2 AND 3
        ELSE false
      END
      OR ref->>'target_schema_name' <> 'qc2.integrity_build.ArtifactManifest.v1'
      OR coalesce(ref->>'target_id', '') !~
        '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      OR (
        ref ? 'content_hash'
        AND coalesce(ref->>'content_hash', '') !~ '^[0-9a-f]{64}$'
      );
  IF invalid_count > 0 THEN
    RAISE EXCEPTION 'Checkpoint contains an invalid artifact reference'
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.jsonb_array_elements(p_artifact_refs) AS refs(ref)
    GROUP BY ref->>'target_id'
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'Checkpoint artifact refs contain duplicate IDs'
      USING ERRCODE = '23505';
  END IF;

  SELECT coalesce(
    pg_catalog.jsonb_agg(ref ORDER BY pg_catalog.convert_to(ref->>'target_id', 'UTF8')),
    '[]'::jsonb
  )
    INTO ordered_refs
    FROM pg_catalog.jsonb_array_elements(p_artifact_refs) AS refs(ref);

  SELECT * INTO stream_row
    FROM qc2_integrity_build.evidence_stream_head
    WHERE active
    FOR UPDATE;
  IF NOT FOUND OR stream_row.head_sequence < 1 THEN
    RAISE EXCEPTION 'An active evidence stream with a genesis event is required'
      USING ERRCODE = '23514';
  END IF;
  IF stream_row.evidence_class = 'FORWARD_SEALED' THEN
    RAISE EXCEPTION 'FORWARD_SEALED checkpoints require an approved independent anchor'
      USING ERRCODE = '55000';
  END IF;

  SELECT checkpoint.checkpoint_hash
    INTO previous_hash
    FROM qc2_integrity_build.evidence_checkpoint AS checkpoint
    WHERE checkpoint.stream_id = stream_row.stream_id
    ORDER BY checkpoint.created_at DESC, checkpoint.id DESC
    LIMIT 1;

  checkpoint_id := qc2_integrity_build.new_uuid_v7();
  checkpoint_time := pg_catalog.clock_timestamp();
  checkpoint_time_text := pg_catalog.to_char(
    checkpoint_time AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  artifact_root_hash := qc2_integrity_build.hash_json(
    'qc2.checkpoint-artifact-roots.v1',
    ordered_refs
  );
  checkpoint_body := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.integrity_build.Checkpoint.v1',
    'schema_version', '1.0',
    'id', checkpoint_id::text,
    'created_at', checkpoint_time_text,
    'owning_authority', 'evidence',
    'evidence_class', stream_row.evidence_class,
    'environment_namespace', stream_row.environment_namespace,
    'source_refs', ordered_refs,
    'stream_id', stream_row.stream_id,
    'head_sequence', stream_row.head_sequence,
    'head_hash', stream_row.head_event_hash,
    'event_count', stream_row.event_count,
    'artifact_root_hash', artifact_root_hash
  );
  checkpoint_hash := qc2_integrity_build.hash_json(
    'qc2.checkpoint-root.v1',
    checkpoint_body
  );
  checkpoint_contract := checkpoint_body || pg_catalog.jsonb_build_object(
    'checkpoint_hash', checkpoint_hash
  );
  content_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.integrity_build.checkpoint.v1/1.0',
    checkpoint_contract - ARRAY[
      'schema_name', 'schema_version', 'id', 'created_at', 'content_hash'
    ]::text[]
  );
  checkpoint_contract := checkpoint_contract || pg_catalog.jsonb_build_object(
    'content_hash', content_hash
  );

  INSERT INTO qc2_integrity_build.evidence_checkpoint(
    id, stream_id, checkpoint_hash, content_hash,
    previous_checkpoint_hash, artifact_refs, checkpoint_contract, created_at
  )
  VALUES (
    checkpoint_id, stream_row.stream_id, checkpoint_hash, content_hash,
    previous_hash, ordered_refs, checkpoint_contract, checkpoint_time
  );
  RETURN checkpoint_id;
END
$function$;

CREATE FUNCTION qc2_integrity_build.create_evidence_stream(
  p_installation_id text,
  p_environment_namespace text,
  p_stream_id text,
  p_evidence_class text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  genesis_event_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('evidence');
  IF p_installation_id !~ '^[a-z][a-z0-9_-]{0,95}$'
    OR p_stream_id !~ '^[a-z][a-z0-9_-]{0,95}$'
    OR p_environment_namespace NOT IN ('development','test','research','production')
    OR p_evidence_class NOT IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    ) THEN
    RAISE EXCEPTION 'Evidence stream identity is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF p_evidence_class = 'FORWARD_SEALED' THEN
    RAISE EXCEPTION 'FORWARD_SEALED requires an approved independent anchor'
      USING ERRCODE = '55000';
  END IF;
  IF p_environment_namespace = 'production'
    AND p_evidence_class <> 'FORWARD_OPERATIONAL' THEN
    RAISE EXCEPTION 'Production evidence streams must be FORWARD_OPERATIONAL'
      USING ERRCODE = '55000';
  END IF;

  INSERT INTO qc2_integrity_build.evidence_stream_head(
    stream_id, installation_id, environment_namespace, evidence_class
  )
  VALUES (
    p_stream_id, p_installation_id, p_environment_namespace, p_evidence_class
  );

  genesis_event_id := qc2_integrity_build.append_event_internal(
    'stream_genesis',
    pg_catalog.jsonb_build_object(
      'installation_id', p_installation_id,
      'environment_namespace', p_environment_namespace,
      'stream_id', p_stream_id,
      'evidence_class', p_evidence_class,
      'previous_checkpoint_hash', NULL
    )
  );
  PERFORM qc2_integrity_build.create_checkpoint();
  RETURN genesis_event_id;
END
$function$;

CREATE FUNCTION qc2_integrity_build.rotate_evidence_stream(p_new_stream_id text)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  old_stream qc2_integrity_build.evidence_stream_head%ROWTYPE;
  prior_checkpoint_id uuid;
  prior_checkpoint_hash text;
  prior_checkpoint_content_hash text;
  genesis_event_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('evidence');
  IF p_new_stream_id !~ '^[a-z][a-z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'New stream ID is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT * INTO old_stream
    FROM qc2_integrity_build.evidence_stream_head
    WHERE active
    FOR UPDATE;
  IF NOT FOUND OR old_stream.head_sequence < 1 THEN
    RAISE EXCEPTION 'An active evidence stream with a genesis event is required'
      USING ERRCODE = '23514';
  END IF;
  PERFORM qc2_integrity_build.create_checkpoint();
  SELECT id, checkpoint_hash, content_hash
    INTO prior_checkpoint_id, prior_checkpoint_hash, prior_checkpoint_content_hash
    FROM qc2_integrity_build.evidence_checkpoint
    WHERE stream_id = old_stream.stream_id
    ORDER BY created_at DESC, id DESC
    LIMIT 1;
  IF prior_checkpoint_id IS NULL THEN
    RAISE EXCEPTION 'Stream rotation requires a committed checkpoint'
      USING ERRCODE = '23514';
  END IF;

  UPDATE qc2_integrity_build.evidence_stream_head
    SET active = false
    WHERE stream_id = old_stream.stream_id;
  INSERT INTO qc2_integrity_build.evidence_stream_head(
    stream_id, installation_id, environment_namespace, evidence_class
  )
  VALUES (
    p_new_stream_id, old_stream.installation_id,
    old_stream.environment_namespace, old_stream.evidence_class
  );

  genesis_event_id := qc2_integrity_build.append_event_internal(
    'stream_genesis',
    pg_catalog.jsonb_build_object(
      'installation_id', old_stream.installation_id,
      'environment_namespace', old_stream.environment_namespace,
      'stream_id', p_new_stream_id,
      'evidence_class', old_stream.evidence_class,
      'previous_stream_id', old_stream.stream_id,
      'previous_checkpoint_hash', prior_checkpoint_hash
    ),
    0,
    pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.integrity_build.Checkpoint.v1',
      'target_id', prior_checkpoint_id::text,
      'content_hash', prior_checkpoint_content_hash
    ))
  );
  PERFORM qc2_integrity_build.create_checkpoint();
  RETURN genesis_event_id;
END
$function$;

CREATE FUNCTION qc2_control.register_job_and_enqueue_outbox(
  p_job_id uuid,
  p_logical_key text,
  p_deadline timestamptz,
  p_outbox_id uuid,
  p_logical_operation_id uuid,
  p_message_type text,
  p_payload_hash text
)
RETURNS TABLE(job_id uuid, outbox_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  job_id := qc2_control.register_job(p_job_id, p_logical_key, p_deadline);
  outbox_id := qc2_control.enqueue_outbox(
    p_outbox_id,
    p_logical_operation_id,
    p_message_type,
    p_payload_hash
  );
  RETURN NEXT;
END
$function$;

REVOKE ALL ON ALL TABLES IN SCHEMA qc2_integrity_build FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qc2_integrity_build FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qc2_control FROM PUBLIC;

GRANT SELECT ON
  qc2_integrity_build.evidence_stream_head,
  qc2_integrity_build.evidence_event,
  qc2_integrity_build.evidence_checkpoint
TO
  qc2_runtime_evidence, qc2_runtime_model_registry, qc2_runtime_core,
  qc2_runtime_apexlab, qc2_runtime_validation, qc2_runtime_owner_api,
  qc2_runtime_configuration, qc2_runtime_governance, qc2_runtime_build_governance;

GRANT EXECUTE ON FUNCTION qc2_integrity_build.create_evidence_stream(text, text, text, text),
  qc2_integrity_build.rotate_evidence_stream(text),
  qc2_integrity_build.create_checkpoint(jsonb)
TO qc2_runtime_evidence;

GRANT EXECUTE ON FUNCTION qc2_control.register_job_and_enqueue_outbox(
  uuid, text, timestamptz, uuid, uuid, text, text
)
TO qc2_runtime_durable_job_service;

RESET ROLE;
