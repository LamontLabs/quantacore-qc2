-- QC2-049: immutable inventory checkpoints and evidence-gated discrepancy holds.
SET ROLE qc2_migrator;

CREATE TABLE qc2_execution.broker_reconciliation_checkpoint (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  generation bigint NOT NULL CHECK (generation >= 1),
  checkpoint_hash text NOT NULL CHECK (checkpoint_hash ~ '^[0-9a-f]{64}$'),
  local_snapshot_hash text NOT NULL CHECK (local_snapshot_hash ~ '^[0-9a-f]{64}$'),
  broker_snapshot_hash text NOT NULL CHECK (broker_snapshot_hash ~ '^[0-9a-f]{64}$'),
  expected_account_fingerprint text NOT NULL
    CHECK (expected_account_fingerprint ~ '^[0-9a-f]{64}$'),
  observed_account_fingerprint text NOT NULL
    CHECK (observed_account_fingerprint ~ '^[0-9a-f]{64}$'),
  report_status text NOT NULL CHECK (
    report_status IN ('RECONCILED','DISCREPANCY','UNKNOWN','HOLD')
  ),
  evidence_ref jsonb NOT NULL CHECK (
    evidence_ref->>'target_schema_name' = 'qc2.integrity_build.EvidenceEvent.v1'
    AND evidence_ref->>'target_id' ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    AND evidence_ref->>'content_hash' ~ '^[0-9a-f]{64}$'
  ),
  report_contract jsonb NOT NULL CHECK (
    report_contract->>'schema_name' = 'qc2.execution.ReconciliationReport.v1'
    AND report_contract->>'schema_version' = '1.0'
    AND report_contract->>'id' = id::text
    AND report_contract->>'status' = report_status
    AND report_contract->'evidence_ref' = evidence_ref
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (episode_id, checkpoint_hash),
  UNIQUE (episode_id, generation)
);

CREATE TABLE qc2_execution.broker_reconciliation_finding (
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  finding_key text NOT NULL CHECK (finding_key ~ '^[a-z0-9][a-z0-9:_./-]{0,129}$'),
  reason_code text NOT NULL CHECK (reason_code ~ '^[A-Z][A-Z0-9_]{0,95}$'),
  finding_state text NOT NULL CHECK (finding_state IN ('OPEN','RESOLVED')),
  first_checkpoint_id uuid NOT NULL
    REFERENCES qc2_execution.broker_reconciliation_checkpoint(id)
    ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
  last_checkpoint_id uuid NOT NULL
    REFERENCES qc2_execution.broker_reconciliation_checkpoint(id)
    ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
  resolution_event_id uuid
    REFERENCES qc2_integrity_build.evidence_event(id) ON DELETE RESTRICT,
  resolution_evidence_ref jsonb CHECK (
    resolution_evidence_ref IS NULL OR (
      resolution_evidence_ref->>'target_schema_name'
        = 'qc2.integrity_build.EvidenceEvent.v1'
      AND resolution_evidence_ref->>'target_id' ~
        '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      AND resolution_evidence_ref->>'content_hash' ~ '^[0-9a-f]{64}$'
    )
  ),
  resolution_code text CHECK (
    resolution_code IS NULL OR resolution_code ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  resolution_note text CHECK (
    resolution_note IS NULL OR length(resolution_note) BETWEEN 1 AND 512
  ),
  resolved_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (episode_id, finding_key),
  CHECK (
    (finding_state = 'OPEN'
      AND resolution_event_id IS NULL
      AND resolution_evidence_ref IS NULL
      AND resolution_code IS NULL
      AND resolution_note IS NULL
      AND resolved_at IS NULL)
    OR
    (finding_state = 'RESOLVED'
      AND resolution_event_id IS NOT NULL
      AND resolution_evidence_ref IS NOT NULL
      AND resolution_code IS NOT NULL
      AND resolution_note IS NOT NULL
      AND resolved_at IS NOT NULL)
  )
);

CREATE FUNCTION qc2_execution.reject_broker_reconciliation_checkpoint_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'QC2 reconciliation checkpoints are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER broker_reconciliation_checkpoint_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.broker_reconciliation_checkpoint
  FOR EACH ROW
  EXECUTE FUNCTION qc2_execution.reject_broker_reconciliation_checkpoint_rewrite();

ALTER TABLE qc2_execution.broker_reconciliation_checkpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.broker_reconciliation_checkpoint FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.broker_reconciliation_finding ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.broker_reconciliation_finding FORCE ROW LEVEL SECURITY;

CREATE POLICY broker_reconciliation_checkpoint_migrator_all
  ON qc2_execution.broker_reconciliation_checkpoint
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY broker_reconciliation_checkpoint_runtime_read
  ON qc2_execution.broker_reconciliation_checkpoint
  FOR SELECT TO qc2_runtime_execution
  USING (qc2_control.current_runtime_authority() = 'execution');
CREATE POLICY broker_reconciliation_finding_migrator_all
  ON qc2_execution.broker_reconciliation_finding
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY broker_reconciliation_finding_runtime_read
  ON qc2_execution.broker_reconciliation_finding
  FOR SELECT TO qc2_runtime_execution
  USING (qc2_control.current_runtime_authority() = 'execution');

REVOKE ALL ON qc2_execution.broker_reconciliation_checkpoint,
  qc2_execution.broker_reconciliation_finding
FROM PUBLIC, qc2_runtime_execution;
GRANT SELECT ON qc2_execution.broker_reconciliation_checkpoint,
  qc2_execution.broker_reconciliation_finding
TO qc2_runtime_execution;

CREATE FUNCTION qc2_control.record_broker_reconciliation(p_input jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  v_episode_id uuid;
  v_episode_row qc2_execution.execution_episode_state%ROWTYPE;
  v_expected_fingerprint text;
  v_observed_fingerprint text;
  v_local_hash text;
  v_broker_hash text;
  v_checkpoint_hash text;
  v_checkpoint_material jsonb;
  v_checkpoint_row qc2_execution.broker_reconciliation_checkpoint%ROWTYPE;
  v_generation bigint;
  v_checkpoint_id uuid;
  v_event_id uuid;
  v_evidence_ref jsonb;
  v_findings jsonb;
  v_finding jsonb;
  v_finding_key text;
  v_reason_code text;
  v_open_finding_keys jsonb;
  v_discrepancies jsonb;
  v_status text;
  v_now timestamptz;
  v_report jsonb;
  v_result jsonb;
  v_remaining_holds jsonb;
  v_has_unreconciled_position boolean;
  v_has_reconciled_cash boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_input) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_input->'episode_ref') IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_input->'findings') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_input->'discrepancies') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_input->'broker_order_refs') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_input->'position_refs') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_input->'source_refs') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_input->'event_payload') IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'broker reconciliation input is invalid'
      USING ERRCODE = '22023';
  END IF;

  IF coalesce(p_input->'episode_ref'->>'target_schema_name', '')
       <> 'qc2.execution.ExecutionEpisode.v1'
     OR coalesce(p_input->'episode_ref'->>'target_id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR coalesce(p_input->'episode_ref'->>'content_hash', '') !~
       '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'broker reconciliation episode reference is invalid'
      USING ERRCODE = '23514';
  END IF;
  v_episode_id := (p_input->'episode_ref'->>'target_id')::uuid;

  SELECT * INTO v_episode_row
    FROM qc2_execution.execution_episode_state AS episode
    WHERE episode.episode_id = v_episode_id
    FOR UPDATE;
  IF NOT FOUND
     OR v_episode_row.content_hash <> p_input->'episode_ref'->>'content_hash' THEN
    RAISE EXCEPTION 'broker reconciliation episode is missing or mismatched'
      USING ERRCODE = '23514';
  END IF;

  v_expected_fingerprint := v_episode_row.paper_account_fingerprint;
  v_observed_fingerprint := p_input->>'observed_account_fingerprint';
  v_local_hash := p_input->>'local_snapshot_hash';
  v_broker_hash := p_input->>'broker_snapshot_hash';
  IF p_input->>'expected_account_fingerprint' IS DISTINCT FROM v_expected_fingerprint
     OR coalesce(v_observed_fingerprint, '') !~ '^[0-9a-f]{64}$'
     OR coalesce(v_local_hash, '') !~ '^[0-9a-f]{64}$'
     OR coalesce(v_broker_hash, '') !~ '^[0-9a-f]{64}$'
     OR coalesce(p_input->>'status', '')
       NOT IN ('RECONCILED','DISCREPANCY','UNKNOWN','HOLD') THEN
    RAISE EXCEPTION 'broker reconciliation snapshot binding is invalid'
      USING ERRCODE = '23514';
  END IF;

  v_checkpoint_material := pg_catalog.jsonb_build_object(
    'episode_ref', p_input->'episode_ref',
    'expected_account_fingerprint', v_expected_fingerprint,
    'observed_account_fingerprint', v_observed_fingerprint,
    'local_snapshot_hash', v_local_hash,
    'broker_snapshot_hash', v_broker_hash
  );
  v_checkpoint_hash := qc2_integrity_build.hash_json(
    'qc2.execution.broker-reconciliation.checkpoint.v1',
    v_checkpoint_material
  );
  IF p_input->>'checkpoint_hash' IS DISTINCT FROM v_checkpoint_hash THEN
    RAISE EXCEPTION 'broker reconciliation checkpoint hash is invalid'
      USING ERRCODE = '23514';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_episode_id::text, 0)
  );
  SELECT * INTO v_checkpoint_row
    FROM qc2_execution.broker_reconciliation_checkpoint AS checkpoint
    WHERE checkpoint.episode_id = v_episode_id
      AND checkpoint.checkpoint_hash = v_checkpoint_hash;
  IF FOUND THEN
    SELECT coalesce(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(finding.finding_key)
               ORDER BY finding.finding_key
             ),
             '[]'::jsonb
           )
      INTO v_open_finding_keys
      FROM qc2_execution.broker_reconciliation_finding AS finding
      WHERE finding.episode_id = v_episode_id
        AND finding.finding_state = 'OPEN';
    RETURN pg_catalog.jsonb_build_object(
      'checkpoint_id', v_checkpoint_row.id::text,
      'checkpoint_hash', v_checkpoint_row.checkpoint_hash,
      'generation', v_checkpoint_row.generation,
      'report_contract', v_checkpoint_row.report_contract,
      'active_finding_keys', v_open_finding_keys,
      'already_recorded', true
    );
  END IF;

  v_findings := p_input->'findings';
  IF v_observed_fingerprint <> v_expected_fingerprint
     AND NOT EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(v_findings) AS item(value)
       WHERE item.value->>'finding_key' = 'account_reset'
     ) THEN
    v_findings := v_findings || pg_catalog.jsonb_build_array(
      pg_catalog.jsonb_build_object(
        'finding_key', 'account_reset',
        'reason_code', 'ACCOUNT_RESET_DETECTED',
        'detail', 'Broker account identity differs from the execution episode.'
      )
    );
  END IF;

  FOR v_finding IN
    SELECT item.value
    FROM pg_catalog.jsonb_array_elements(v_findings) AS item(value)
  LOOP
    IF pg_catalog.jsonb_typeof(v_finding) IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'broker reconciliation finding must be an object'
        USING ERRCODE = '22023';
    END IF;
    v_finding_key := v_finding->>'finding_key';
    v_reason_code := v_finding->>'reason_code';
    IF coalesce(v_finding_key, '') !~ '^[a-z0-9][a-z0-9:_./-]{0,129}$'
       OR coalesce(v_reason_code, '') !~ '^[A-Z][A-Z0-9_]{0,95}$' THEN
      RAISE EXCEPTION 'broker reconciliation finding identity is invalid'
        USING ERRCODE = '23514';
    END IF;
  END LOOP;
  IF (
    SELECT pg_catalog.count(*) <> pg_catalog.count(DISTINCT item.value->>'finding_key')
    FROM pg_catalog.jsonb_array_elements(v_findings) AS item(value)
  ) THEN
    RAISE EXCEPTION 'broker reconciliation finding keys must be unique'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.jsonb_array_elements(p_input->'discrepancies') AS item(value)
    WHERE pg_catalog.jsonb_typeof(item.value) IS DISTINCT FROM 'string'
       OR pg_catalog.btrim(item.value #>> '{}') = ''
       OR NOT EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements(v_findings) AS finding(value)
         WHERE finding.value->>'finding_key' = item.value #>> '{}'
       )
  ) THEN
    RAISE EXCEPTION 'every discrepancy must have a matching reconciliation finding'
      USING ERRCODE = '23514';
  END IF;
  IF p_input->>'status' = 'RECONCILED'
     AND (
       pg_catalog.jsonb_array_length(v_findings) > 0
       OR pg_catalog.jsonb_array_length(p_input->'discrepancies') > 0
     ) THEN
    RAISE EXCEPTION 'a reconciled checkpoint cannot contain discrepancies'
      USING ERRCODE = '23514';
  END IF;
  IF p_input->>'status' <> 'RECONCILED'
     AND pg_catalog.jsonb_array_length(v_findings) = 0 THEN
    RAISE EXCEPTION 'a blocking reconciliation status requires a finding'
      USING ERRCODE = '23514';
  END IF;

  SELECT coalesce(pg_catalog.max(checkpoint.generation), 0) + 1
    INTO v_generation
    FROM qc2_execution.broker_reconciliation_checkpoint AS checkpoint
    WHERE checkpoint.episode_id = v_episode_id;
  v_checkpoint_id := qc2_integrity_build.new_uuid_v7();
  v_now := pg_catalog.clock_timestamp();
  v_event_id := qc2_integrity_build.append_event_internal(
    'broker_reconciliation_checkpoint',
    p_input->'event_payload'
      || pg_catalog.jsonb_build_object(
        'checkpoint_id', v_checkpoint_id::text,
        'checkpoint_hash', v_checkpoint_hash,
        'generation', v_generation,
        'expected_account_fingerprint', v_expected_fingerprint,
        'observed_account_fingerprint', v_observed_fingerprint,
        'local_snapshot_hash', v_local_hash,
        'broker_snapshot_hash', v_broker_hash,
        'findings', v_findings
      ),
    v_generation,
    p_input->'source_refs'
  );
  SELECT pg_catalog.jsonb_build_object(
           'target_schema_name', 'qc2.integrity_build.EvidenceEvent.v1',
           'target_id', event.id::text,
           'content_hash', event.content_hash
         )
    INTO v_evidence_ref
    FROM qc2_integrity_build.evidence_event AS event
    WHERE event.id = v_event_id;
  IF v_evidence_ref IS NULL THEN
    RAISE EXCEPTION 'broker reconciliation evidence event was not persisted'
      USING ERRCODE = '23514';
  END IF;

  FOR v_finding IN
    SELECT item.value
    FROM pg_catalog.jsonb_array_elements(v_findings) AS item(value)
  LOOP
    v_finding_key := v_finding->>'finding_key';
    v_reason_code := v_finding->>'reason_code';
    INSERT INTO qc2_execution.broker_reconciliation_finding(
      episode_id, finding_key, reason_code, finding_state,
      first_checkpoint_id, last_checkpoint_id
    )
    VALUES (
      v_episode_id, v_finding_key, v_reason_code, 'OPEN',
      v_checkpoint_id, v_checkpoint_id
    )
    ON CONFLICT (episode_id, finding_key) DO UPDATE
      SET reason_code = EXCLUDED.reason_code,
          finding_state = 'OPEN',
          last_checkpoint_id = EXCLUDED.last_checkpoint_id,
          resolution_event_id = NULL,
          resolution_evidence_ref = NULL,
          resolution_code = NULL,
          resolution_note = NULL,
          resolved_at = NULL,
          updated_at = pg_catalog.clock_timestamp();
    PERFORM qc2_control.hold_execution_position_state(
      v_episode_id,
      'broker_reconciliation:' || v_finding_key
    );
  END LOOP;

  SELECT coalesce(
           pg_catalog.jsonb_agg(
             pg_catalog.to_jsonb(finding.finding_key)
             ORDER BY finding.finding_key
           ),
           '[]'::jsonb
         )
    INTO v_open_finding_keys
    FROM qc2_execution.broker_reconciliation_finding AS finding
    WHERE finding.episode_id = v_episode_id
      AND finding.finding_state = 'OPEN';

  SELECT coalesce(
           pg_catalog.jsonb_agg(
             pg_catalog.to_jsonb(discrepancy.value)
             ORDER BY discrepancy.value
           ),
           '[]'::jsonb
         )
    INTO v_discrepancies
    FROM (
      SELECT DISTINCT (item.value #>> '{}') AS value
      FROM pg_catalog.jsonb_array_elements(p_input->'discrepancies') AS item(value)
      WHERE pg_catalog.jsonb_typeof(item.value) = 'string'
        AND pg_catalog.btrim(item.value #>> '{}') <> ''
      UNION
      SELECT finding.finding_key AS value
      FROM qc2_execution.broker_reconciliation_finding AS finding
      WHERE finding.episode_id = v_episode_id
        AND finding.finding_state = 'OPEN'
    ) AS discrepancy;

  v_status := p_input->>'status';
  IF pg_catalog.jsonb_array_length(v_open_finding_keys) > 0
     OR v_observed_fingerprint <> v_expected_fingerprint THEN
    v_status := 'HOLD';
  END IF;
  IF v_status = 'RECONCILED'
     AND v_observed_fingerprint = v_expected_fingerprint THEN
    SELECT coalesce(
             pg_catalog.bool_or(
               projection.reconciliation_status <> 'RECONCILED'
             ),
             false
           )
      INTO v_has_unreconciled_position
      FROM qc2_execution.position_state_position_projection AS projection
      WHERE projection.episode_id = v_episode_id;
    SELECT coalesce(
             pg_catalog.bool_and(cash.reconciliation_status = 'RECONCILED'),
             false
           )
      INTO v_has_reconciled_cash
      FROM qc2_execution.position_state_cash_projection AS cash
      WHERE cash.episode_id = v_episode_id;

    IF NOT v_has_unreconciled_position AND v_has_reconciled_cash THEN
      SELECT control.hold_reasons
        INTO v_remaining_holds
        FROM qc2_execution.position_state_projection_control AS control
        WHERE control.episode_id = v_episode_id
        FOR UPDATE;
      IF FOUND THEN
        SELECT coalesce(
                 pg_catalog.jsonb_agg(item.value ORDER BY item.ordinality),
                 '[]'::jsonb
               )
          INTO v_remaining_holds
          FROM pg_catalog.jsonb_array_elements(v_remaining_holds)
            WITH ORDINALITY AS item(value, ordinality)
          WHERE item.value #>> '{}' NOT LIKE 'broker_reconciliation:%';
        UPDATE qc2_execution.position_state_projection_control AS control
          SET hold_reasons = v_remaining_holds,
              reconciliation_status = CASE
                WHEN pg_catalog.jsonb_array_length(v_remaining_holds) = 0
                  THEN 'RECONCILED'
                ELSE 'HOLD'
              END,
              generation = control.generation + 1,
              updated_at = pg_catalog.clock_timestamp()
          WHERE control.episode_id = v_episode_id;
      END IF;
    END IF;
  END IF;

  v_report := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.execution.ReconciliationReport.v1',
    'schema_version', '1.0',
    'id', v_checkpoint_id::text,
    'created_at', pg_catalog.to_char(
      v_now AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ),
    'owning_authority', 'execution',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', p_input->'source_refs',
    'episode_ref', p_input->'episode_ref',
    'paper_account_fingerprint', v_expected_fingerprint,
    'reconciled_at', pg_catalog.to_char(
      v_now AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ),
    'broker_order_refs', p_input->'broker_order_refs',
    'position_refs', p_input->'position_refs',
    'discrepancies', v_discrepancies,
    'status', v_status,
    'evidence_ref', v_evidence_ref
  );
  INSERT INTO qc2_execution.broker_reconciliation_checkpoint(
    id, episode_id, generation, checkpoint_hash, local_snapshot_hash,
    broker_snapshot_hash, expected_account_fingerprint,
    observed_account_fingerprint, report_status, evidence_ref, report_contract,
    created_at
  )
  VALUES (
    v_checkpoint_id, v_episode_id, v_generation, v_checkpoint_hash,
    v_local_hash, v_broker_hash, v_expected_fingerprint,
    v_observed_fingerprint, v_status, v_evidence_ref, v_report, v_now
  );

  v_result := pg_catalog.jsonb_build_object(
    'checkpoint_id', v_checkpoint_id::text,
    'checkpoint_hash', v_checkpoint_hash,
    'generation', v_generation,
    'report_contract', v_report,
    'active_finding_keys', v_open_finding_keys,
    'already_recorded', false
  );
  RETURN v_result;
END
$function$;

CREATE FUNCTION qc2_control.resolve_broker_reconciliation_finding(
  p_episode_id uuid,
  p_finding_key text,
  p_resolution_code text,
  p_resolution_note text,
  p_evidence_ref jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  v_finding qc2_execution.broker_reconciliation_finding%ROWTYPE;
  v_evidence_id uuid;
  v_evidence_hash text;
  v_resolution_event_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_finding_key IS NULL
     OR p_finding_key !~ '^[a-z0-9][a-z0-9:_./-]{0,129}$'
     OR p_resolution_code IS NULL
     OR p_resolution_code !~ '^[a-z][a-z0-9_-]{0,95}$'
     OR p_resolution_note IS NULL
     OR pg_catalog.btrim(p_resolution_note) = ''
     OR length(p_resolution_note) > 512
     OR pg_catalog.jsonb_typeof(p_evidence_ref) IS DISTINCT FROM 'object'
     OR p_evidence_ref->>'target_schema_name'
       IS DISTINCT FROM 'qc2.integrity_build.EvidenceEvent.v1'
     OR coalesce(p_evidence_ref->>'target_id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR coalesce(p_evidence_ref->>'content_hash', '') !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'broker reconciliation resolution evidence is invalid'
      USING ERRCODE = '22023';
  END IF;
  v_evidence_id := (p_evidence_ref->>'target_id')::uuid;
  SELECT event.content_hash INTO v_evidence_hash
    FROM qc2_integrity_build.evidence_event AS event
    WHERE event.id = v_evidence_id;
  IF v_evidence_hash IS NULL
     OR v_evidence_hash <> p_evidence_ref->>'content_hash' THEN
    RAISE EXCEPTION 'broker reconciliation resolution EvidenceEvent is missing or mismatched'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO v_finding
    FROM qc2_execution.broker_reconciliation_finding AS finding
    WHERE finding.episode_id = p_episode_id
      AND finding.finding_key = p_finding_key
      AND finding.finding_state = 'OPEN'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  v_resolution_event_id := qc2_integrity_build.append_event_internal(
    'broker_reconciliation_finding_resolved',
    pg_catalog.jsonb_build_object(
      'episode_id', p_episode_id::text,
      'finding_key', p_finding_key,
      'resolution_code', p_resolution_code,
      'resolution_note', p_resolution_note,
      'evidence_ref', p_evidence_ref
    ),
    0,
    pg_catalog.jsonb_build_array(p_evidence_ref)
  );
  UPDATE qc2_execution.broker_reconciliation_finding AS finding
    SET finding_state = 'RESOLVED',
        resolution_event_id = v_resolution_event_id,
        resolution_evidence_ref = p_evidence_ref,
        resolution_code = p_resolution_code,
        resolution_note = p_resolution_note,
        resolved_at = pg_catalog.clock_timestamp(),
        updated_at = pg_catalog.clock_timestamp()
    WHERE finding.episode_id = p_episode_id
      AND finding.finding_key = p_finding_key;
  RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION qc2_execution.reject_broker_reconciliation_checkpoint_rewrite(),
  qc2_control.record_broker_reconciliation(jsonb),
  qc2_control.resolve_broker_reconciliation_finding(uuid, text, text, text, jsonb)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  qc2_control.record_broker_reconciliation(jsonb),
  qc2_control.resolve_broker_reconciliation_finding(uuid, text, text, text, jsonb)
TO qc2_runtime_execution;
