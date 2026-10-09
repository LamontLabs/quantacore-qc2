-- QC2-046: execution-only outbox dispatch, fenced broker mutation attempts,
-- and explicit recovery for outcomes that cannot be determined at send time.
SET ROLE qc2_migrator;

ALTER TABLE qc2_control.outbox_message
  DROP CONSTRAINT outbox_message_owner_authority_check,
  ADD CONSTRAINT outbox_message_owner_authority_check
    CHECK (owner_authority IN ('durable_job_service', 'execution'));

CREATE TABLE qc2_execution.paper_execution_attempt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  intent_id uuid NOT NULL UNIQUE
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  outbox_message_id uuid NOT NULL UNIQUE
    REFERENCES qc2_control.outbox_message(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number = 1),
  client_order_key text NOT NULL CHECK (client_order_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  normalized_request_hash text NOT NULL CHECK (normalized_request_hash ~ '^[0-9a-f]{64}$'),
  normalized_request jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(normalized_request) = 'object'),
  initial_gate_snapshot jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(initial_gate_snapshot) = 'object'),
  send_gate_snapshot jsonb CHECK (
    send_gate_snapshot IS NULL OR pg_catalog.jsonb_typeof(send_gate_snapshot) = 'object'
  ),
  attempt_state text NOT NULL CHECK (attempt_state IN (
    'SUBMISSION_STARTED','ACKNOWLEDGED','SUBMISSION_UNKNOWN','REJECTED','BLOCKED'
  )),
  started_at timestamptz NOT NULL,
  send_authorized_at timestamptz,
  completed_at timestamptz,
  broker_order_id text,
  order_state text,
  uncertainty_code text CHECK (
    uncertainty_code IS NULL OR uncertainty_code ~ '^[A-Z][A-Z0-9_-]{0,95}$'
  ),
  result_event_id uuid CHECK (
    result_event_id IS NULL OR result_event_id::text ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CHECK ((attempt_state IN ('ACKNOWLEDGED','SUBMISSION_UNKNOWN','REJECTED','BLOCKED'))
         = (completed_at IS NOT NULL))
);

CREATE TABLE qc2_execution.submission_attempt_contract (
  id uuid PRIMARY KEY
    REFERENCES qc2_execution.paper_execution_attempt(id) ON DELETE RESTRICT,
  intent_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number = 1),
  outcome text NOT NULL CHECK (
    outcome IN ('ACKNOWLEDGED','SUBMISSION_UNKNOWN','REJECTED')
  ),
  contract jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(contract) = 'object'
    AND contract->>'schema_name' = 'qc2.execution.SubmissionAttempt.v1'
    AND contract->>'schema_version' = '1.0'
    AND contract->>'owning_authority' = 'execution'
    AND contract->>'id' = id::text
    AND contract->>'outcome' = outcome
    AND contract->'intent_ref'->>'target_id' = intent_id::text
    AND contract->>'attempt_number' = attempt_number::text
    AND contract->>'normalized_request_hash' ~ '^[0-9a-f]{64}$'
    AND contract->'broker_order_ref' = 'null'::jsonb
    AND contract->'evidence_ref'->>'target_schema_name'
      = 'qc2.integrity_build.EvidenceEvent.v1'
    AND contract->'evidence_ref'->>'target_id' ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    AND contract->'evidence_ref'->>'content_hash' ~ '^[0-9a-f]{64}$'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (intent_id, attempt_number)
);

CREATE TABLE qc2_execution.paper_execution_gate_decision (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  intent_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  outbox_message_id uuid NOT NULL UNIQUE
    REFERENCES qc2_control.outbox_message(id) ON DELETE RESTRICT,
  attempt_id uuid REFERENCES qc2_execution.paper_execution_attempt(id) ON DELETE RESTRICT,
  reason_code text NOT NULL CHECK (reason_code ~ '^[A-Z][A-Z0-9_-]{0,95}$'),
  gate_snapshot jsonb CHECK (
    gate_snapshot IS NULL OR pg_catalog.jsonb_typeof(gate_snapshot) = 'object'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.paper_submission_resolution (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  attempt_id uuid NOT NULL UNIQUE
    REFERENCES qc2_execution.paper_execution_attempt(id) ON DELETE RESTRICT,
  disposition text NOT NULL CHECK (disposition IN ('FOUND','ABSENCE_PROVEN')),
  evidence jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(evidence) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE FUNCTION qc2_execution.prevent_execution_record_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'execution evidence records are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER submission_attempt_contract_append_only
BEFORE UPDATE OR DELETE ON qc2_execution.submission_attempt_contract
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_execution_record_rewrite();
CREATE TRIGGER paper_execution_gate_decision_append_only
BEFORE UPDATE OR DELETE ON qc2_execution.paper_execution_gate_decision
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_execution_record_rewrite();
CREATE TRIGGER paper_submission_resolution_append_only
BEFORE UPDATE OR DELETE ON qc2_execution.paper_submission_resolution
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_execution_record_rewrite();

ALTER TABLE qc2_execution.paper_execution_attempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_execution_attempt FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.submission_attempt_contract ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.submission_attempt_contract FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_execution_gate_decision ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_execution_gate_decision FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_submission_resolution ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_submission_resolution FORCE ROW LEVEL SECURITY;

CREATE POLICY paper_execution_attempt_migrator_all
  ON qc2_execution.paper_execution_attempt
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY submission_attempt_contract_migrator_all
  ON qc2_execution.submission_attempt_contract
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY paper_execution_gate_decision_migrator_all
  ON qc2_execution.paper_execution_gate_decision
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY paper_submission_resolution_migrator_all
  ON qc2_execution.paper_submission_resolution
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

CREATE POLICY paper_execution_attempt_runtime_read
  ON qc2_execution.paper_execution_attempt
  FOR SELECT TO qc2_runtime_execution USING (true);
CREATE POLICY submission_attempt_contract_runtime_read
  ON qc2_execution.submission_attempt_contract
  FOR SELECT TO qc2_runtime_execution USING (true);
CREATE POLICY paper_execution_gate_decision_runtime_read
  ON qc2_execution.paper_execution_gate_decision
  FOR SELECT TO qc2_runtime_execution USING (true);
CREATE POLICY paper_submission_resolution_runtime_read
  ON qc2_execution.paper_submission_resolution
  FOR SELECT TO qc2_runtime_execution USING (true);

REVOKE ALL ON qc2_execution.paper_execution_attempt,
  qc2_execution.submission_attempt_contract,
  qc2_execution.paper_execution_gate_decision,
  qc2_execution.paper_submission_resolution
FROM PUBLIC, qc2_runtime_execution;
GRANT SELECT ON qc2_execution.paper_execution_attempt,
  qc2_execution.submission_attempt_contract,
  qc2_execution.paper_execution_gate_decision,
  qc2_execution.paper_submission_resolution
TO qc2_runtime_execution;

CREATE FUNCTION qc2_execution.expected_readiness_action(p_intent jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $function$
BEGIN
  RETURN CASE
    WHEN p_intent->>'action_kind' = 'OPEN_LONG' THEN 'NEW_ENTRY'
    WHEN p_intent->>'action_kind' = 'CANCEL_PENDING_ENTRY' THEN 'CANCEL_ENTRY'
    WHEN p_intent->>'action_kind' IN ('REDUCE_LONG','CLOSE_LONG') THEN 'EXIT_POSITION'
    WHEN p_intent->>'action_kind' = 'REPLACE_ORDER'
      AND p_intent->>'side' = 'BUY' THEN 'NEW_ENTRY'
    WHEN p_intent->>'action_kind' = 'REPLACE_ORDER'
      AND p_intent->>'side' = 'SELL' THEN 'EXIT_POSITION'
    ELSE NULL
  END;
END
$function$;

CREATE FUNCTION qc2_execution.assert_paper_execution_gate(
  p_intent jsonb,
  p_request jsonb,
  p_gate jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  required_action text;
  target_session text;
  matching_assessments integer;
  ready_assessments integer;
BEGIN
  IF pg_catalog.jsonb_typeof(p_intent) <> 'object'
     OR pg_catalog.jsonb_typeof(p_request) <> 'object'
     OR pg_catalog.jsonb_typeof(p_gate) <> 'object'
     OR pg_catalog.jsonb_typeof(p_gate->'readiness') <> 'array' THEN
    RAISE EXCEPTION 'execution gate envelope is invalid'
      USING ERRCODE = '22023';
  END IF;

  required_action := qc2_execution.expected_readiness_action(p_intent);
  IF required_action IS NULL THEN
    RAISE EXCEPTION 'unsupported paper action'
      USING ERRCODE = '23514';
  END IF;
  IF p_intent->>'intent_state' <> 'QUEUED_FOR_SUBMISSION'
     OR (p_intent->>'expires_at')::timestamptz <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'paper intent is not current and queued'
      USING ERRCODE = '23514';
  END IF;
  IF p_intent->>'account_mode' IS DISTINCT FROM 'PAPER'
     OR p_gate->>'account_mode' IS DISTINCT FROM 'PAPER'
     OR p_gate->>'paper_endpoint_verified' IS DISTINCT FROM 'true'
     OR p_gate->>'paper_account_fingerprint'
       IS DISTINCT FROM p_intent->>'paper_account_fingerprint' THEN
    RAISE EXCEPTION 'paper account or endpoint changed'
      USING ERRCODE = '42501';
  END IF;
  IF required_action = 'NEW_ENTRY'
     AND p_gate->>'entry_paused' IS DISTINCT FROM 'false' THEN
    RAISE EXCEPTION 'new entries are paused'
      USING ERRCODE = '42501';
  END IF;
  SELECT pg_catalog.count(*)::integer,
    pg_catalog.count(*) FILTER (
      WHERE assessment.value->>'status' = 'READY'
        AND assessment.value->>'input_generation' ~ '^[1-9][0-9]*$'
        AND assessment.value->>'assessment_id' ~
          '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        AND (assessment.value->>'freshness_deadline')::timestamptz
          > pg_catalog.clock_timestamp()
    )::integer
    INTO matching_assessments, ready_assessments
    FROM pg_catalog.jsonb_array_elements(p_gate->'readiness')
      AS assessment(value)
    WHERE assessment.value->>'action' = required_action;
  IF matching_assessments <> 1 OR ready_assessments <> 1 THEN
    RAISE EXCEPTION 'action-scoped readiness is absent, stale, or ambiguous'
      USING ERRCODE = '42501';
  END IF;
  IF p_request->>'schema_name' IS DISTINCT FROM
       'qc2.execution.normalized_mutation_request.v1'
     OR p_request->>'intent_id' IS DISTINCT FROM p_intent->>'id'
     OR p_request->>'client_order_key' IS DISTINCT FROM p_intent->>'idempotency_key'
     OR p_request->>'account_fingerprint'
       IS DISTINCT FROM p_intent->>'paper_account_fingerprint' THEN
    RAISE EXCEPTION 'normalized request identity does not match the intent'
      USING ERRCODE = '23514';
  END IF;

  IF p_intent->>'action_kind' = 'CANCEL_PENDING_ENTRY' THEN
    IF p_request->>'action' IS DISTINCT FROM 'CANCEL'
       OR p_gate->>'prior_reservation_active' IS DISTINCT FROM 'true' THEN
      RAISE EXCEPTION 'cancellation does not bind an active prior order'
        USING ERRCODE = '23514';
    END IF;
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM qc2_execution.paper_order_intent_reservation AS intent_reservation
    JOIN qc2_execution.resource_reservation AS resource
      ON resource.resource_key = intent_reservation.resource_key
     AND resource.reservation_key = p_intent->>'id'
     AND resource.state = 'ACTIVE'
    WHERE intent_reservation.intent_id = (p_intent->>'id')::uuid
  ) THEN
    RAISE EXCEPTION 'paper order has no active exposure reservation'
      USING ERRCODE = '23514';
  END IF;

  target_session := p_intent->>'target_execution_session';
  IF p_request->>'action' IS DISTINCT FROM 'SUBMIT'
     OR p_gate->>'session_open' IS DISTINCT FROM 'true'
     OR p_gate->>'current_session' IS DISTINCT FROM target_session
     OR p_gate->>'reservation_active' IS DISTINCT FROM 'true'
     OR p_gate->>'symbol_assignment_id'
       IS DISTINCT FROM p_intent->'symbol_assignment_ref'->>'target_id'
     OR p_gate->>'broker_symbol' IS NULL
     OR pg_catalog.btrim(p_gate->>'broker_symbol') = ''
     OR p_request->>'symbol' IS DISTINCT FROM p_gate->>'broker_symbol'
     OR p_request->>'symbol_assignment_id'
       IS DISTINCT FROM p_gate->>'symbol_assignment_id'
     OR p_request->>'instrument_id'
       IS DISTINCT FROM p_intent->'instrument_ref'->>'target_id'
     OR p_request->>'side' IS DISTINCT FROM p_intent->>'side'
     OR p_request->>'quantity_whole_shares'
       IS DISTINCT FROM p_intent->>'quantity_whole_shares'
     OR p_request->>'order_type' IS DISTINCT FROM p_intent->>'order_type'
     OR p_request->>'time_in_force' IS DISTINCT FROM p_intent->>'time_in_force'
     OR p_request->>'session_restriction'
       IS DISTINCT FROM p_intent->>'session_restriction'
     OR p_request->'limit_price' IS DISTINCT FROM p_intent->'limit_price'
     OR p_request->'stop_price' IS DISTINCT FROM p_intent->'stop_price'
     OR p_request->>'extended_hours' IS DISTINCT FROM 'false' THEN
    RAISE EXCEPTION 'normalized order request or current gate does not match intent'
      USING ERRCODE = '23514';
  END IF;

  IF p_intent->>'action_kind' = 'REPLACE_ORDER'
     AND (
       p_gate->>'prior_intent_state' IS DISTINCT FROM 'CANCELLED'
       AND p_gate->>'prior_intent_state' IS DISTINCT FROM 'REJECTED'
       OR p_gate->>'prior_reservation_active' IS DISTINCT FROM 'false'
     ) THEN
    RAISE EXCEPTION 'replacement is blocked until the prior order is terminal'
      USING ERRCODE = '23514';
  END IF;
END
$function$;

CREATE FUNCTION qc2_execution.assert_paper_order_context(
  p_intent jsonb,
  p_gate jsonb,
  p_request jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_execution
AS $function$
DECLARE
  prior_row qc2_execution.paper_order_intent%ROWTYPE;
  prior_id uuid;
  active_reservation boolean;
  prior_action text;
BEGIN
  IF p_intent->>'action_kind' NOT IN ('CANCEL_PENDING_ENTRY','REPLACE_ORDER') THEN
    RETURN;
  END IF;
  IF p_intent->'source_ref'->>'target_schema_name'
       <> 'qc2.execution.PaperOrderIntent.v1'
     OR p_intent->'source_ref'->>'target_id' IS NULL
     OR p_intent->'source_ref'->>'content_hash' !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'prior intent reference is invalid'
      USING ERRCODE = '23514';
  END IF;

  prior_id := (p_intent->'source_ref'->>'target_id')::uuid;
  SELECT * INTO prior_row
    FROM qc2_execution.paper_order_intent
    WHERE id = prior_id
    FOR UPDATE;
  IF NOT FOUND
     OR prior_row.content_hash <> p_intent->'source_ref'->>'content_hash'
     OR prior_row.paper_account_fingerprint
       <> p_intent->>'paper_account_fingerprint'
     OR prior_row.intent_contract->'instrument_ref'->>'target_id'
       <> p_intent->'instrument_ref'->>'target_id' THEN
    RAISE EXCEPTION 'prior intent identity, account, or instrument changed'
      USING ERRCODE = '23514';
  END IF;
  SELECT EXISTS (
    SELECT 1
    FROM qc2_execution.paper_order_intent_reservation AS intent_reservation
    JOIN qc2_execution.resource_reservation AS resource
      ON resource.resource_key = intent_reservation.resource_key
     AND resource.reservation_key = prior_id::text
     AND resource.state = 'ACTIVE'
    WHERE intent_reservation.intent_id = prior_id
  ) INTO active_reservation;

  IF p_gate->>'prior_intent_state' IS DISTINCT FROM prior_row.intent_state
     OR (p_gate->>'prior_reservation_active')::boolean
       IS DISTINCT FROM active_reservation THEN
    RAISE EXCEPTION 'prior intent changed after the readiness snapshot'
      USING ERRCODE = '40001';
  END IF;

  prior_action := prior_row.intent_contract->>'action_kind';
  IF p_intent->>'action_kind' = 'CANCEL_PENDING_ENTRY' THEN
    IF prior_action <> 'OPEN_LONG'
       OR prior_row.intent_contract->>'side' <> 'BUY'
       OR prior_row.intent_state NOT IN (
         'SUBMISSION_UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED'
       )
       OR NOT active_reservation
       OR p_request->>'action' IS DISTINCT FROM 'CANCEL'
       OR p_request->>'target_intent_id' IS DISTINCT FROM prior_id::text
       OR p_request->>'target_client_order_key'
         IS DISTINCT FROM prior_row.idempotency_key
       OR p_request->>'broker_order_id'
         IS DISTINCT FROM p_gate->>'prior_broker_order_id' THEN
      RAISE EXCEPTION 'prior entry is not cancellable or has no active reservation'
        USING ERRCODE = '23514';
    END IF;
  ELSIF prior_row.intent_state NOT IN ('CANCELLED','REJECTED')
        OR active_reservation THEN
    RAISE EXCEPTION 'replacement is blocked while prior exposure remains unresolved'
      USING ERRCODE = '23514';
  END IF;
END
$function$;

CREATE FUNCTION qc2_control.enqueue_paper_order_submission(p_intent_id uuid)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  existing_message qc2_control.outbox_message%ROWTYPE;
  new_message_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = p_intent_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper-order intent does not exist'
      USING ERRCODE = '23503';
  END IF;

  SELECT * INTO existing_message
    FROM qc2_control.outbox_message
    WHERE logical_operation_id = p_intent_id;
  IF FOUND THEN
    IF existing_message.owner_authority <> 'execution'
       OR existing_message.message_type <> 'paper_order_submission'
       OR existing_message.payload_hash <> intent_row.content_hash THEN
      RAISE EXCEPTION 'logical operation ID was reused with conflicting outbox content'
        USING ERRCODE = '23505';
    END IF;
    RETURN existing_message.id;
  END IF;

  IF intent_row.intent_state <> 'RESERVED' THEN
    RAISE EXCEPTION 'only a reserved intent can enter the execution outbox'
      USING ERRCODE = '23514';
  END IF;
  IF NOT qc2_control.transition_paper_order_intent(
       p_intent_id, 'QUEUED_FOR_SUBMISSION'
     ) THEN
    RAISE EXCEPTION 'reserved intent could not be queued'
      USING ERRCODE = '23514';
  END IF;
  new_message_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_control.outbox_message(
    id, logical_operation_id, owner_authority, message_type, payload_hash
  )
  VALUES (
    new_message_id, p_intent_id, 'execution',
    'paper_order_submission', intent_row.content_hash
  );
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_enqueued',
    pg_catalog.jsonb_build_object(
      'intent_id', p_intent_id::text,
      'outbox_message_id', new_message_id::text,
      'content_hash', intent_row.content_hash
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  RETURN new_message_id;
END
$function$;

CREATE FUNCTION qc2_control.claim_paper_order_submission(
  p_worker_id uuid,
  p_lease_seconds integer
)
RETURNS TABLE(
  message_id uuid,
  logical_operation_id uuid,
  message_type text,
  payload_hash text,
  worker_id uuid,
  fencing_generation bigint,
  lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  selected_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_worker_id IS NULL OR p_lease_seconds NOT BETWEEN 1 AND 3600 THEN
    RAISE EXCEPTION 'execution lease input is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT message.id INTO selected_id
    FROM qc2_control.outbox_message AS message
    WHERE message.owner_authority = 'execution'
      AND message.message_type = 'paper_order_submission'
      AND message.status IN ('PENDING','PUBLISHING')
      AND (message.next_attempt_at IS NULL
           OR message.next_attempt_at <= pg_catalog.clock_timestamp())
      AND (message.lease_expires_at IS NULL
           OR message.lease_expires_at <= pg_catalog.clock_timestamp())
    ORDER BY message.created_at, message.id
    FOR UPDATE SKIP LOCKED
    LIMIT 1;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  UPDATE qc2_control.outbox_message AS message
    SET status = 'PUBLISHING',
        attempt_count = message.attempt_count + 1,
        lease_owner = p_worker_id,
        fencing_generation = message.fencing_generation + 1,
        lease_expires_at = pg_catalog.clock_timestamp()
          + pg_catalog.make_interval(secs => p_lease_seconds)
    WHERE message.id = selected_id
    RETURNING message.id, message.logical_operation_id, message.message_type,
      message.payload_hash, message.lease_owner, message.fencing_generation,
      message.lease_expires_at
    INTO message_id, logical_operation_id, message_type, payload_hash,
      worker_id, fencing_generation, lease_expires_at;
  RETURN NEXT;
END
$function$;

CREATE FUNCTION qc2_control.begin_paper_order_attempt(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_request jsonb,
  p_request_hash text,
  p_gate_snapshot jsonb
)
RETURNS TABLE(
  attempt_id uuid,
  intent_id uuid,
  attempt_number integer,
  attempt_state text,
  created boolean,
  client_order_key text,
  normalized_request_hash text,
  started_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  message_row qc2_control.outbox_message%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  attempt_row qc2_execution.paper_execution_attempt%ROWTYPE;
  next_attempt_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO message_row
    FROM qc2_control.outbox_message
    WHERE id = p_message_id
      AND owner_authority = 'execution'
      AND message_type = 'paper_order_submission'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'outbox lease is stale'
      USING ERRCODE = '40001';
  END IF;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = message_row.logical_operation_id
    FOR UPDATE;
  IF NOT FOUND
     OR intent_row.content_hash <> message_row.payload_hash
     OR intent_row.intent_state <> 'QUEUED_FOR_SUBMISSION'
     OR (intent_row.intent_contract->>'expires_at')::timestamptz
       <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'queued intent is missing, changed, or expired'
      USING ERRCODE = '23514';
  END IF;
  IF p_request_hash !~ '^[0-9a-f]{64}$'
     OR qc2_integrity_build.hash_json(
       'qc2.execution.normalized-request.v1', p_request
     ) <> p_request_hash THEN
    RAISE EXCEPTION 'normalized request hash does not match request bytes'
      USING ERRCODE = '23514';
  END IF;
  PERFORM qc2_execution.assert_paper_execution_gate(
    intent_row.intent_contract, p_request, p_gate_snapshot
  );
  PERFORM qc2_execution.assert_paper_order_context(
    intent_row.intent_contract, p_gate_snapshot, p_request
  );
  IF p_request->>'action' = 'SUBMIT'
     AND (
       p_request->>'order_type' IS DISTINCT FROM intent_row.intent_contract->>'order_type'
       OR p_request->>'time_in_force'
         IS DISTINCT FROM intent_row.intent_contract->>'time_in_force'
     ) THEN
    RAISE EXCEPTION 'order terms changed while normalizing request'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO attempt_row
    FROM qc2_execution.paper_execution_attempt AS persisted_attempt
    WHERE persisted_attempt.intent_id = intent_row.id
    FOR UPDATE;
  IF FOUND THEN
    IF attempt_row.normalized_request_hash <> p_request_hash
       OR attempt_row.normalized_request IS DISTINCT FROM p_request THEN
      RAISE EXCEPTION 'intent already has a conflicting broker attempt'
        USING ERRCODE = '23505';
    END IF;
    attempt_id := attempt_row.id;
    intent_id := attempt_row.intent_id;
    attempt_number := attempt_row.attempt_number;
    attempt_state := attempt_row.attempt_state;
    created := false;
    client_order_key := attempt_row.client_order_key;
    normalized_request_hash := attempt_row.normalized_request_hash;
    started_at := attempt_row.started_at;
    RETURN NEXT;
    RETURN;
  END IF;

  next_attempt_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_execution.paper_execution_attempt(
    id, intent_id, outbox_message_id, attempt_number, client_order_key,
    normalized_request_hash, normalized_request, initial_gate_snapshot,
    attempt_state, started_at
  )
  VALUES (
    next_attempt_id, intent_row.id, message_row.id, 1,
    intent_row.idempotency_key, p_request_hash, p_request, p_gate_snapshot,
    'SUBMISSION_STARTED', pg_catalog.clock_timestamp()
  )
  RETURNING paper_execution_attempt.id, paper_execution_attempt.intent_id,
    paper_execution_attempt.attempt_number, paper_execution_attempt.attempt_state,
    paper_execution_attempt.client_order_key,
    paper_execution_attempt.normalized_request_hash,
    paper_execution_attempt.started_at
  INTO attempt_id, intent_id, attempt_number, attempt_state, client_order_key,
    normalized_request_hash, started_at;
  IF NOT qc2_control.transition_paper_order_intent(
       intent_row.id, 'SUBMISSION_STARTED'
     ) THEN
    RAISE EXCEPTION 'intent could not enter submission-started state'
      USING ERRCODE = '23514';
  END IF;
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_attempt_started',
    pg_catalog.jsonb_build_object(
      'attempt_id', attempt_id::text,
      'intent_id', intent_row.id::text,
      'normalized_request_hash', p_request_hash
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  created := true;
  RETURN NEXT;
END
$function$;

CREATE FUNCTION qc2_control.authorize_paper_order_attempt(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_attempt_id uuid,
  p_gate_snapshot jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  message_row qc2_control.outbox_message%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  attempt_row qc2_execution.paper_execution_attempt%ROWTYPE;
  gate_intent jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO message_row
    FROM qc2_control.outbox_message
    WHERE id = p_message_id
      AND owner_authority = 'execution'
      AND message_type = 'paper_order_submission'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO attempt_row
    FROM qc2_execution.paper_execution_attempt
    WHERE id = p_attempt_id
      AND outbox_message_id = message_row.id
      AND attempt_state = 'SUBMISSION_STARTED'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = attempt_row.intent_id
    FOR UPDATE;
  IF NOT FOUND OR intent_row.intent_state <> 'SUBMISSION_STARTED' THEN
    RETURN false;
  END IF;
  gate_intent := pg_catalog.jsonb_set(
    intent_row.intent_contract,
    '{intent_state}',
    pg_catalog.to_jsonb('QUEUED_FOR_SUBMISSION'::text)
  );
  BEGIN
    PERFORM qc2_execution.assert_paper_execution_gate(
      gate_intent, attempt_row.normalized_request, p_gate_snapshot
    );
    PERFORM qc2_execution.assert_paper_order_context(
      intent_row.intent_contract, p_gate_snapshot, attempt_row.normalized_request
    );
  EXCEPTION
    WHEN SQLSTATE '23514' OR SQLSTATE '42501' OR SQLSTATE '40001' THEN
      RETURN false;
  END;
  UPDATE qc2_execution.paper_execution_attempt
    SET send_gate_snapshot = p_gate_snapshot,
        send_authorized_at = pg_catalog.clock_timestamp()
    WHERE id = attempt_row.id;
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_send_authorized',
    pg_catalog.jsonb_build_object(
      'attempt_id', attempt_row.id::text,
      'intent_id', intent_row.id::text,
      'input_generation',
        (SELECT assessment.value->>'input_generation'
         FROM pg_catalog.jsonb_array_elements(p_gate_snapshot->'readiness')
           AS assessment(value)
         WHERE assessment.value->>'action'
           = qc2_execution.expected_readiness_action(intent_row.intent_contract)
           AND assessment.value->>'status' = 'READY'
         LIMIT 1)
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.block_paper_order_attempt(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_intent_id uuid,
  p_attempt_id uuid,
  p_reason_code text,
  p_gate_snapshot jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  message_row qc2_control.outbox_message%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  attempt_row qc2_execution.paper_execution_attempt%ROWTYPE;
  reservation_row qc2_execution.paper_order_intent_reservation%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_reason_code IS NULL OR p_reason_code !~ '^[A-Z][A-Z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'execution block reason code is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT * INTO message_row
    FROM qc2_control.outbox_message
    WHERE id = p_message_id
      AND logical_operation_id = p_intent_id
      AND owner_authority = 'execution'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = p_intent_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;

  IF p_attempt_id IS NOT NULL THEN
    SELECT * INTO attempt_row
      FROM qc2_execution.paper_execution_attempt
      WHERE id = p_attempt_id
        AND intent_id = p_intent_id
        AND attempt_state = 'SUBMISSION_STARTED'
      FOR UPDATE;
    IF NOT FOUND OR intent_row.intent_state <> 'SUBMISSION_STARTED' THEN
      RETURN false;
    END IF;
    UPDATE qc2_execution.paper_execution_attempt
      SET attempt_state = 'BLOCKED',
          completed_at = pg_catalog.clock_timestamp(),
          uncertainty_code = p_reason_code
      WHERE id = attempt_row.id;
    IF NOT qc2_control.transition_paper_order_intent(p_intent_id, 'REJECTED') THEN
      RAISE EXCEPTION 'blocked intent could not be rejected'
        USING ERRCODE = '23514';
    END IF;
    SELECT * INTO reservation_row
      FROM qc2_execution.paper_order_intent_reservation
      WHERE intent_id = p_intent_id;
    IF FOUND THEN
      PERFORM qc2_control.release_resource_reservation(
        reservation_row.resource_key, p_intent_id::text
      );
    END IF;
  ELSE
    IF intent_row.intent_state <> 'QUEUED_FOR_SUBMISSION' THEN
      RETURN false;
    END IF;
    IF NOT qc2_control.transition_paper_order_intent(p_intent_id, 'CANCELLED') THEN
      RAISE EXCEPTION 'blocked queued intent could not be cancelled'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  INSERT INTO qc2_execution.paper_execution_gate_decision(
    id, intent_id, outbox_message_id, attempt_id, reason_code, gate_snapshot
  )
  VALUES (
    qc2_integrity_build.new_uuid_v7(), p_intent_id, p_message_id, p_attempt_id,
    p_reason_code, p_gate_snapshot
  );
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_blocked',
    pg_catalog.jsonb_build_object(
      'intent_id', p_intent_id::text,
      'outbox_message_id', p_message_id::text,
      'attempt_id', p_attempt_id::text,
      'reason_code', p_reason_code
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.finish_paper_order_attempt(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_attempt_id uuid,
  p_outcome text,
  p_broker_order_id text,
  p_order_state text,
  p_uncertainty_code text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  message_row qc2_control.outbox_message%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  attempt_row qc2_execution.paper_execution_attempt%ROWTYPE;
  prior_row qc2_execution.paper_order_intent%ROWTYPE;
  reservation_row qc2_execution.paper_order_intent_reservation%ROWTYPE;
  new_state text;
  event_id uuid;
  event_hash text;
  event_time timestamptz;
  event_time_text text;
  started_time_text text;
  outcome_contract jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_outcome NOT IN ('ACKNOWLEDGED','SUBMISSION_UNKNOWN','REJECTED')
     OR p_order_state IS NOT NULL
       AND p_order_state !~ '^[A-Z][A-Z0-9_-]{0,63}$'
     OR p_uncertainty_code IS NOT NULL
       AND p_uncertainty_code !~ '^[A-Z][A-Z0-9_-]{0,95}$'
     OR p_broker_order_id IS NOT NULL
       AND pg_catalog.btrim(p_broker_order_id) = '' THEN
    RAISE EXCEPTION 'paper submission result is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT * INTO message_row
    FROM qc2_control.outbox_message
    WHERE id = p_message_id
      AND owner_authority = 'execution'
      AND message_type = 'paper_order_submission'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO attempt_row
    FROM qc2_execution.paper_execution_attempt
    WHERE id = p_attempt_id
      AND outbox_message_id = message_row.id
      AND attempt_state = 'SUBMISSION_STARTED'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = attempt_row.intent_id
    FOR UPDATE;
  IF NOT FOUND OR intent_row.intent_state <> 'SUBMISSION_STARTED' THEN
    RETURN false;
  END IF;
  IF intent_row.intent_contract->>'action_kind' = 'CANCEL_PENDING_ENTRY'
     AND p_order_state IS NOT NULL
     AND p_order_state NOT IN ('CANCEL_REQUESTED','CANCELLED') THEN
    RAISE EXCEPTION 'cancel outcome contains a non-cancellation order state'
      USING ERRCODE = '23514';
  END IF;
  IF p_order_state = 'CANCELLED'
     AND (
       p_outcome <> 'ACKNOWLEDGED'
       OR intent_row.intent_contract->>'action_kind' <> 'CANCEL_PENDING_ENTRY'
     ) THEN
    RAISE EXCEPTION 'cancelled order state lacks a definitive cancel acknowledgement'
      USING ERRCODE = '23514';
  END IF;
  IF p_outcome = 'SUBMISSION_UNKNOWN' THEN
    new_state := 'SUBMISSION_UNKNOWN';
  ELSE
    new_state := p_outcome;
  END IF;
  UPDATE qc2_execution.paper_execution_attempt
    SET attempt_state = new_state,
        completed_at = pg_catalog.clock_timestamp(),
        broker_order_id = p_broker_order_id,
        order_state = p_order_state,
        uncertainty_code = p_uncertainty_code
    WHERE id = attempt_row.id;

  event_id := qc2_integrity_build.append_event_internal(
    'paper_submission_outcome_recorded',
    pg_catalog.jsonb_build_object(
      'attempt_id', attempt_row.id::text,
      'intent_id', intent_row.id::text,
      'outcome', p_outcome,
      'broker_order_id', p_broker_order_id,
      'order_state', p_order_state,
      'uncertainty_code', p_uncertainty_code,
      'normalized_request_hash', attempt_row.normalized_request_hash
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  SELECT event.content_hash INTO event_hash
    FROM qc2_integrity_build.evidence_event AS event
    WHERE event.id = event_id;
  IF event_hash IS NULL THEN
    RAISE EXCEPTION 'submission outcome evidence event is missing'
      USING ERRCODE = '23514';
  END IF;
  event_time := pg_catalog.clock_timestamp();
  event_time_text := pg_catalog.to_char(
    event_time AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  started_time_text := pg_catalog.to_char(
    attempt_row.started_at AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  outcome_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.execution.SubmissionAttempt.v1',
    'schema_version', '1.0',
    'id', attempt_row.id::text,
    'created_at', event_time_text,
    'owning_authority', 'execution',
    'evidence_class', intent_row.intent_contract->>'evidence_class',
    'environment_namespace', intent_row.intent_contract->>'environment_namespace',
    'source_refs', '[]'::jsonb,
    'intent_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.execution.PaperOrderIntent.v1',
      'target_id', intent_row.id::text,
      'content_hash', intent_row.content_hash
    ),
    'client_order_key', attempt_row.client_order_key,
    'normalized_request_hash', attempt_row.normalized_request_hash,
    'attempt_number', attempt_row.attempt_number,
    'started_at', started_time_text,
    'outcome', p_outcome,
    'broker_order_ref', NULL,
    'evidence_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.integrity_build.EvidenceEvent.v1',
      'target_id', event_id::text,
      'content_hash', event_hash
    )
  );
  INSERT INTO qc2_execution.submission_attempt_contract(
    id, intent_id, attempt_number, outcome, contract
  )
  VALUES (
    attempt_row.id, intent_row.id, attempt_row.attempt_number,
    p_outcome, outcome_contract
  );

  IF NOT qc2_control.transition_paper_order_intent(intent_row.id, new_state) THEN
    RAISE EXCEPTION 'submission outcome could not advance the intent'
      USING ERRCODE = '23514';
  END IF;
  IF p_outcome = 'REJECTED'
     AND intent_row.intent_contract->>'action_kind' <> 'CANCEL_PENDING_ENTRY' THEN
    SELECT * INTO reservation_row
      FROM qc2_execution.paper_order_intent_reservation
      WHERE intent_id = intent_row.id;
    IF FOUND THEN
      PERFORM qc2_control.release_resource_reservation(
        reservation_row.resource_key, intent_row.id::text
      );
    END IF;
  END IF;

  IF intent_row.intent_contract->>'action_kind' = 'CANCEL_PENDING_ENTRY'
     AND p_outcome IN ('ACKNOWLEDGED','SUBMISSION_UNKNOWN') THEN
    SELECT * INTO prior_row
      FROM qc2_execution.paper_order_intent
      WHERE id = (intent_row.intent_contract->'source_ref'->>'target_id')::uuid
      FOR UPDATE;
    IF FOUND THEN
      IF p_order_state = 'CANCELLED' THEN
        IF prior_row.intent_state = 'ACKNOWLEDGED'
           OR prior_row.intent_state = 'SUBMISSION_UNKNOWN' THEN
          PERFORM qc2_control.transition_paper_order_intent(
            prior_row.id, 'CANCEL_REQUESTED'
          );
        END IF;
        IF prior_row.intent_state IN (
          'ACKNOWLEDGED','SUBMISSION_UNKNOWN','PARTIALLY_FILLED','CANCEL_REQUESTED'
        ) THEN
          PERFORM qc2_control.transition_paper_order_intent(prior_row.id, 'CANCELLED');
        END IF;
        SELECT * INTO reservation_row
          FROM qc2_execution.paper_order_intent_reservation
          WHERE intent_id = prior_row.id;
        IF FOUND AND prior_row.intent_state <> 'PARTIALLY_FILLED' THEN
          PERFORM qc2_control.release_resource_reservation(
            reservation_row.resource_key, prior_row.id::text
          );
        END IF;
      ELSIF prior_row.intent_state IN (
        'ACKNOWLEDGED','SUBMISSION_UNKNOWN','PARTIALLY_FILLED'
      ) THEN
        PERFORM qc2_control.transition_paper_order_intent(
          prior_row.id, 'CANCEL_REQUESTED'
        );
      END IF;
    END IF;
  END IF;
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.mark_paper_order_attempt_unknown(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_attempt_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  RETURN qc2_control.finish_paper_order_attempt(
    p_message_id,
    p_worker_id,
    p_fencing_generation,
    p_attempt_id,
    'SUBMISSION_UNKNOWN',
    NULL,
    NULL,
    'PROCESS_LOST_AFTER_START'
  );
END
$function$;

CREATE FUNCTION qc2_control.complete_paper_order_submission(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  UPDATE qc2_control.outbox_message
    SET status = 'DELIVERED',
        next_attempt_at = NULL,
        delivered_at = pg_catalog.clock_timestamp(),
        lease_expires_at = NULL,
        lease_owner = NULL
    WHERE id = p_message_id
      AND owner_authority = 'execution'
      AND message_type = 'paper_order_submission'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp();
  RETURN FOUND;
END
$function$;

CREATE FUNCTION qc2_control.defer_paper_order_submission(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_reason_code text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  operation_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_reason_code IS NULL OR p_reason_code !~ '^[A-Z][A-Z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'execution deferral reason code is invalid'
      USING ERRCODE = '22023';
  END IF;
  UPDATE qc2_control.outbox_message
    SET status = 'PENDING',
        next_attempt_at = pg_catalog.clock_timestamp() + interval '30 seconds',
        lease_expires_at = NULL,
        lease_owner = NULL
    WHERE id = p_message_id
      AND owner_authority = 'execution'
      AND message_type = 'paper_order_submission'
      AND status = 'PUBLISHING'
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
    RETURNING logical_operation_id INTO operation_id;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_deferred',
    pg_catalog.jsonb_build_object(
      'intent_id', operation_id::text,
      'outbox_message_id', p_message_id::text,
      'reason_code', p_reason_code
    ),
    0,
    '[]'::jsonb
  );
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.resolve_paper_order_attempt_unknown(
  p_attempt_id uuid,
  p_evidence jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution,
  qc2_integrity_build
AS $function$
DECLARE
  attempt_row qc2_execution.paper_execution_attempt%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  disposition text;
  checked_source_count integer;
  evidence_id uuid;
  evidence_hash text;
  reservation_row qc2_execution.paper_order_intent_reservation%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_evidence) <> 'object' THEN
    RAISE EXCEPTION 'reconciliation evidence must be an object'
      USING ERRCODE = '22023';
  END IF;
  SELECT * INTO attempt_row
    FROM qc2_execution.paper_execution_attempt
    WHERE id = p_attempt_id
      AND attempt_state = 'SUBMISSION_UNKNOWN'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = attempt_row.intent_id
    FOR UPDATE;
  disposition := p_evidence->>'disposition';
  IF intent_row.intent_state <> 'SUBMISSION_UNKNOWN'
     OR p_evidence->>'intent_id' IS DISTINCT FROM intent_row.id::text
     OR p_evidence->>'account_fingerprint'
       IS DISTINCT FROM intent_row.paper_account_fingerprint
     OR p_evidence->>'client_order_key'
       IS DISTINCT FROM attempt_row.client_order_key
     OR p_evidence->>'normalized_request_hash'
       IS DISTINCT FROM attempt_row.normalized_request_hash THEN
    RAISE EXCEPTION 'reconciliation evidence binding does not match unknown attempt'
      USING ERRCODE = '23514';
  END IF;
  IF disposition = 'UNRESOLVED' THEN
    RETURN false;
  END IF;
  IF disposition NOT IN ('FOUND','ABSENCE_PROVEN')
     OR pg_catalog.jsonb_typeof(p_evidence->'checked_sources') <> 'array' THEN
    RAISE EXCEPTION 'reconciliation disposition or source coverage is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT pg_catalog.count(DISTINCT item.value #>> '{}')::integer
    INTO checked_source_count
    FROM pg_catalog.jsonb_array_elements(p_evidence->'checked_sources') AS item(value)
    WHERE pg_catalog.jsonb_typeof(item.value) = 'string'
      AND pg_catalog.btrim(item.value #>> '{}') <> '';
  IF checked_source_count <> pg_catalog.jsonb_array_length(p_evidence->'checked_sources') THEN
    RAISE EXCEPTION 'reconciliation source set is empty or duplicated'
      USING ERRCODE = '23514';
  END IF;
  IF disposition = 'ABSENCE_PROVEN'
     AND (
       checked_source_count < 2
       OR p_evidence->>'consistency_window_closed' IS DISTINCT FROM 'true'
       OR p_evidence->'broker_order_id' IS DISTINCT FROM 'null'::jsonb
     ) THEN
    RAISE EXCEPTION 'absence is not proven beyond a single not-found query'
      USING ERRCODE = '23514';
  END IF;
  IF disposition = 'FOUND'
     AND (
       pg_catalog.jsonb_typeof(p_evidence->'broker_order_id')
         IS DISTINCT FROM 'string'
       OR pg_catalog.btrim(p_evidence->>'broker_order_id') = ''
     ) THEN
    RAISE EXCEPTION 'found reconciliation requires a broker order ID'
      USING ERRCODE = '23514';
  END IF;
  IF p_evidence->'evidence_ref'->>'target_schema_name'
       IS DISTINCT FROM 'qc2.integrity_build.EvidenceEvent.v1'
     OR coalesce(p_evidence->'evidence_ref'->>'target_id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR coalesce(p_evidence->'evidence_ref'->>'content_hash', '') !~
       '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'reconciliation evidence reference is invalid'
      USING ERRCODE = '23514';
  END IF;
  evidence_id := (p_evidence->'evidence_ref'->>'target_id')::uuid;
  SELECT event.content_hash INTO evidence_hash
    FROM qc2_integrity_build.evidence_event AS event
    WHERE event.id = evidence_id;
  IF evidence_hash IS NULL
     OR evidence_hash <> p_evidence->'evidence_ref'->>'content_hash' THEN
    RAISE EXCEPTION 'reconciliation evidence event is missing or mismatched'
      USING ERRCODE = '23514';
  END IF;

  INSERT INTO qc2_execution.paper_submission_resolution(
    id, attempt_id, disposition, evidence
  )
  VALUES (
    qc2_integrity_build.new_uuid_v7(), p_attempt_id, disposition, p_evidence
  );
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_submission_reconciled',
    pg_catalog.jsonb_build_object(
      'attempt_id', p_attempt_id::text,
      'intent_id', intent_row.id::text,
      'disposition', disposition,
      'evidence_ref', p_evidence->'evidence_ref'
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  IF disposition = 'FOUND' THEN
    UPDATE qc2_execution.paper_execution_attempt
      SET broker_order_id = p_evidence->>'broker_order_id'
      WHERE id = p_attempt_id;
    RETURN qc2_control.transition_paper_order_intent(intent_row.id, 'ACKNOWLEDGED');
  END IF;

  IF NOT qc2_control.transition_paper_order_intent(intent_row.id, 'REJECTED') THEN
    RETURN false;
  END IF;
  SELECT * INTO reservation_row
    FROM qc2_execution.paper_order_intent_reservation
    WHERE intent_id = intent_row.id;
  IF FOUND THEN
    PERFORM qc2_control.release_resource_reservation(
      reservation_row.resource_key, intent_row.id::text
    );
  END IF;
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.get_paper_order_attempt(p_intent_id uuid)
RETURNS TABLE(
  attempt_id uuid,
  intent_id uuid,
  attempt_number integer,
  attempt_state text,
  created boolean,
  client_order_key text,
  normalized_request_hash text,
  started_at timestamptz,
  broker_order_id text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
  SELECT attempt.id, attempt.intent_id, attempt.attempt_number,
    attempt.attempt_state, false, attempt.client_order_key,
    attempt.normalized_request_hash, attempt.started_at, attempt.broker_order_id
  FROM qc2_execution.paper_execution_attempt AS attempt
  WHERE attempt.intent_id = p_intent_id
$function$;

CREATE FUNCTION qc2_control.get_paper_order_attempt_by_id(p_attempt_id uuid)
RETURNS TABLE(
  attempt_id uuid,
  intent_id uuid,
  attempt_number integer,
  attempt_state text,
  created boolean,
  client_order_key text,
  normalized_request_hash text,
  started_at timestamptz,
  broker_order_id text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
  SELECT attempt.id, attempt.intent_id, attempt.attempt_number,
    attempt.attempt_state, false, attempt.client_order_key,
    attempt.normalized_request_hash, attempt.started_at, attempt.broker_order_id
  FROM qc2_execution.paper_execution_attempt AS attempt
  WHERE attempt.id = p_attempt_id
$function$;

REVOKE ALL ON FUNCTION qc2_execution.expected_readiness_action(jsonb),
  qc2_execution.assert_paper_execution_gate(jsonb, jsonb, jsonb),
  qc2_execution.assert_paper_order_context(jsonb, jsonb, jsonb),
  qc2_execution.prevent_execution_record_rewrite()
FROM PUBLIC;
REVOKE ALL ON FUNCTION
  qc2_control.enqueue_paper_order_submission(uuid),
  qc2_control.claim_paper_order_submission(uuid, integer),
  qc2_control.begin_paper_order_attempt(uuid, uuid, bigint, jsonb, text, jsonb),
  qc2_control.authorize_paper_order_attempt(uuid, uuid, bigint, uuid, jsonb),
  qc2_control.block_paper_order_attempt(uuid, uuid, bigint, uuid, uuid, text, jsonb),
  qc2_control.finish_paper_order_attempt(uuid, uuid, bigint, uuid, text, text, text, text),
  qc2_control.mark_paper_order_attempt_unknown(uuid, uuid, bigint, uuid),
  qc2_control.complete_paper_order_submission(uuid, uuid, bigint),
  qc2_control.defer_paper_order_submission(uuid, uuid, bigint, text),
  qc2_control.resolve_paper_order_attempt_unknown(uuid, jsonb),
  qc2_control.get_paper_order_attempt(uuid),
  qc2_control.get_paper_order_attempt_by_id(uuid)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  qc2_control.enqueue_paper_order_submission(uuid),
  qc2_control.claim_paper_order_submission(uuid, integer),
  qc2_control.begin_paper_order_attempt(uuid, uuid, bigint, jsonb, text, jsonb),
  qc2_control.authorize_paper_order_attempt(uuid, uuid, bigint, uuid, jsonb),
  qc2_control.block_paper_order_attempt(uuid, uuid, bigint, uuid, uuid, text, jsonb),
  qc2_control.finish_paper_order_attempt(uuid, uuid, bigint, uuid, text, text, text, text),
  qc2_control.mark_paper_order_attempt_unknown(uuid, uuid, bigint, uuid),
  qc2_control.complete_paper_order_submission(uuid, uuid, bigint),
  qc2_control.defer_paper_order_submission(uuid, uuid, bigint, text),
  qc2_control.resolve_paper_order_attempt_unknown(uuid, jsonb),
  qc2_control.get_paper_order_attempt(uuid),
  qc2_control.get_paper_order_attempt_by_id(uuid)
TO qc2_runtime_execution;

RESET ROLE;
