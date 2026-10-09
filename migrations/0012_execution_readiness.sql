-- QC2-051: generation-bound action readiness and durable entry-pause control.
SET ROLE qc2_migrator;

CREATE TABLE qc2_execution.entry_pause_state (
  singleton_id boolean PRIMARY KEY CHECK (singleton_id),
  entry_paused boolean NOT NULL,
  generation bigint NOT NULL CHECK (generation >= 1),
  reason_code text CHECK (
    reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

INSERT INTO qc2_execution.entry_pause_state(
  singleton_id, entry_paused, generation, reason_code
)
VALUES (true, true, 1, 'initial_fail_closed');

CREATE TABLE qc2_execution.entry_pause_request (
  request_id uuid PRIMARY KEY CHECK (
    request_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  generation bigint NOT NULL CHECK (generation >= 1),
  reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_-]{0,95}$'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.entry_pause_cancel_work (
  pause_generation bigint NOT NULL CHECK (pause_generation >= 1),
  target_intent_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  cancel_intent_id uuid CHECK (
    cancel_intent_id IS NULL OR cancel_intent_id::text ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  work_state text NOT NULL DEFAULT 'PENDING'
    CHECK (work_state IN ('PENDING','ENQUEUED','RESOLVED')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (pause_generation, target_intent_id),
  CHECK (work_state <> 'ENQUEUED' OR cancel_intent_id IS NOT NULL)
);

CREATE TRIGGER entry_pause_request_append_only
BEFORE UPDATE OR DELETE ON qc2_execution.entry_pause_request
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_execution_record_rewrite();

ALTER TABLE qc2_execution.entry_pause_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.entry_pause_state FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.entry_pause_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.entry_pause_request FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.entry_pause_cancel_work ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.entry_pause_cancel_work FORCE ROW LEVEL SECURITY;

CREATE POLICY entry_pause_state_migrator_all
  ON qc2_execution.entry_pause_state
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY entry_pause_request_migrator_all
  ON qc2_execution.entry_pause_request
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY entry_pause_cancel_work_migrator_all
  ON qc2_execution.entry_pause_cancel_work
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY entry_pause_state_execution_read
  ON qc2_execution.entry_pause_state
  FOR SELECT TO qc2_runtime_execution USING (true);
CREATE POLICY entry_pause_request_execution_read
  ON qc2_execution.entry_pause_request
  FOR SELECT TO qc2_runtime_execution USING (true);
CREATE POLICY entry_pause_cancel_work_execution_read
  ON qc2_execution.entry_pause_cancel_work
  FOR SELECT TO qc2_runtime_execution USING (true);

REVOKE ALL ON qc2_execution.entry_pause_state,
  qc2_execution.entry_pause_request,
  qc2_execution.entry_pause_cancel_work
FROM PUBLIC, qc2_runtime_execution;
GRANT SELECT ON qc2_execution.entry_pause_state,
  qc2_execution.entry_pause_request,
  qc2_execution.entry_pause_cancel_work
TO qc2_runtime_execution;

CREATE FUNCTION qc2_control.get_entry_pause_state()
RETURNS TABLE(entry_paused boolean, generation bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  RETURN QUERY
    SELECT state.entry_paused, state.generation
    FROM qc2_execution.entry_pause_state AS state
    WHERE state.singleton_id;
END
$function$;

CREATE FUNCTION qc2_control.pause_new_entries(
  p_request_id uuid,
  p_reason_code text
)
RETURNS TABLE(entry_paused boolean, generation bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  state_row qc2_execution.entry_pause_state%ROWTYPE;
  prior_request qc2_execution.entry_pause_request%ROWTYPE;
  target_row qc2_execution.paper_order_intent%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_request_id IS NULL
     OR p_request_id::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_reason_code IS NULL
     OR p_reason_code !~ '^[a-z][a-z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'entry-pause request envelope is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT * INTO prior_request
    FROM qc2_execution.entry_pause_request AS request
    WHERE request.request_id = p_request_id;
  IF FOUND THEN
    IF prior_request.reason_code <> p_reason_code THEN
      RAISE EXCEPTION 'entry-pause request ID was reused with different content'
        USING ERRCODE = '23505';
    END IF;
    RETURN QUERY
      SELECT state.entry_paused, state.generation
      FROM qc2_execution.entry_pause_state AS state
      WHERE state.singleton_id;
    RETURN;
  END IF;

  SELECT * INTO state_row
    FROM qc2_execution.entry_pause_state AS state
    WHERE state.singleton_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'entry-pause state is missing'
      USING ERRCODE = '23514';
  END IF;
  IF NOT state_row.entry_paused THEN
    UPDATE qc2_execution.entry_pause_state AS state
      SET entry_paused = true,
          generation = state.generation + 1,
          reason_code = p_reason_code,
          updated_at = pg_catalog.clock_timestamp()
      WHERE state.singleton_id
      RETURNING * INTO state_row;
  ELSE
    UPDATE qc2_execution.entry_pause_state AS state
      SET reason_code = p_reason_code,
          updated_at = pg_catalog.clock_timestamp()
      WHERE state.singleton_id
      RETURNING * INTO state_row;
  END IF;

  INSERT INTO qc2_execution.entry_pause_request(
    request_id, generation, reason_code
  )
  VALUES (p_request_id, state_row.generation, p_reason_code);

  FOR target_row IN
    SELECT intent.*
    FROM qc2_execution.paper_order_intent AS intent
    WHERE intent.intent_contract->>'action_kind' = 'OPEN_LONG'
      AND intent.intent_contract->>'side' = 'BUY'
      AND intent.intent_state IN (
        'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED'
      )
    ORDER BY intent.created_at, intent.id
    FOR UPDATE
  LOOP
    INSERT INTO qc2_execution.entry_pause_cancel_work(
      pause_generation, target_intent_id
    )
    VALUES (state_row.generation, target_row.id)
    ON CONFLICT (pause_generation, target_intent_id) DO NOTHING;
  END LOOP;

  FOR target_row IN
    SELECT intent.*
    FROM qc2_execution.paper_order_intent AS intent
    WHERE intent.intent_contract->>'action_kind' = 'OPEN_LONG'
      AND intent.intent_contract->>'side' = 'BUY'
      AND intent.intent_state IN ('CREATED','VERIFIED','RESERVED')
    ORDER BY intent.created_at, intent.id
    FOR UPDATE
  LOOP
    IF target_row.intent_state = 'RESERVED' THEN
      PERFORM qc2_control.transition_paper_order_intent(target_row.id, 'CANCELLED');
    ELSE
      PERFORM qc2_control.transition_paper_order_intent(target_row.id, 'REJECTED');
    END IF;
  END LOOP;

  PERFORM qc2_integrity_build.append_event_internal(
    'new_entry_pause_requested',
    pg_catalog.jsonb_build_object(
      'request_id', p_request_id::text,
      'pause_generation', state_row.generation,
      'reason_code', p_reason_code,
      'entry_paused', true
    ),
    0,
    '[]'::jsonb
  );
  RETURN QUERY SELECT state_row.entry_paused, state_row.generation;
END
$function$;

CREATE FUNCTION qc2_control.pending_entry_pause_cancellations()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');

  UPDATE qc2_execution.entry_pause_cancel_work AS work
    SET work_state = 'RESOLVED',
        updated_at = pg_catalog.clock_timestamp()
    FROM qc2_execution.paper_order_intent AS target
    WHERE target.id = work.target_intent_id
      AND work.work_state = 'PENDING'
      AND target.intent_state NOT IN (
        'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED'
      );

  RETURN coalesce(
    (
      SELECT pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'pause_generation', work.pause_generation,
          'target_intent_id', target.id::text,
          'target_intent',
            target.intent_contract || pg_catalog.jsonb_build_object(
              'content_hash', target.content_hash,
              'intent_state', target.intent_state
            ),
          'cancel_intent_id', work.cancel_intent_id
        )
        ORDER BY target.created_at, target.id
      )
      FROM qc2_execution.entry_pause_cancel_work AS work
      JOIN qc2_execution.paper_order_intent AS target
        ON target.id = work.target_intent_id
      WHERE work.work_state = 'PENDING'
        AND target.intent_state IN (
          'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED'
        )
    ),
    '[]'::jsonb
  );
END
$function$;

CREATE FUNCTION qc2_control.reserve_pause_cancel_intent_id(
  p_pause_generation bigint,
  p_target_intent_id uuid,
  p_cancel_intent_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
DECLARE
  existing_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_pause_generation IS NULL OR p_pause_generation < 1
     OR p_cancel_intent_id IS NULL
     OR p_cancel_intent_id::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'pause cancellation ID request is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT work.cancel_intent_id INTO existing_id
    FROM qc2_execution.entry_pause_cancel_work AS work
    WHERE work.pause_generation = p_pause_generation
      AND work.target_intent_id = p_target_intent_id
      AND work.work_state = 'PENDING'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF existing_id IS NULL THEN
    UPDATE qc2_execution.entry_pause_cancel_work AS work
      SET cancel_intent_id = p_cancel_intent_id,
          updated_at = pg_catalog.clock_timestamp()
      WHERE work.pause_generation = p_pause_generation
        AND work.target_intent_id = p_target_intent_id
      RETURNING work.cancel_intent_id INTO existing_id;
  END IF;
  RETURN existing_id;
END
$function$;

CREATE FUNCTION qc2_control.mark_pause_cancel_enqueued(
  p_pause_generation bigint,
  p_target_intent_id uuid,
  p_cancel_intent_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
DECLARE
  work_row qc2_execution.entry_pause_cancel_work%ROWTYPE;
  cancel_row qc2_execution.paper_order_intent%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO work_row
    FROM qc2_execution.entry_pause_cancel_work AS work
    WHERE work.pause_generation = p_pause_generation
      AND work.target_intent_id = p_target_intent_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  IF work_row.work_state = 'ENQUEUED' THEN
    RETURN work_row.cancel_intent_id = p_cancel_intent_id;
  END IF;
  IF work_row.work_state <> 'PENDING'
     OR work_row.cancel_intent_id IS DISTINCT FROM p_cancel_intent_id THEN
    RETURN false;
  END IF;
  SELECT * INTO cancel_row
    FROM qc2_execution.paper_order_intent AS intent
    WHERE intent.id = p_cancel_intent_id;
  IF NOT FOUND
     OR cancel_row.intent_contract->>'action_kind' <> 'CANCEL_PENDING_ENTRY'
     OR cancel_row.intent_contract->'source_ref'->>'target_id'
          <> p_target_intent_id::text
     OR cancel_row.intent_state NOT IN (
       'QUEUED_FOR_SUBMISSION','SUBMISSION_STARTED','SUBMISSION_UNKNOWN',
       'ACKNOWLEDGED','PARTIALLY_FILLED','CANCEL_REQUESTED','CANCELLED',
       'REJECTED','EXPIRED'
     ) THEN
    RETURN false;
  END IF;
  UPDATE qc2_execution.entry_pause_cancel_work AS work
    SET work_state = 'ENQUEUED',
        updated_at = pg_catalog.clock_timestamp()
    WHERE work.pause_generation = p_pause_generation
      AND work.target_intent_id = p_target_intent_id;
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.resume_new_entries(
  p_expected_pause_generation bigint,
  p_assessment jsonb
)
RETURNS TABLE(entry_paused boolean, generation bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  state_row qc2_execution.entry_pause_state%ROWTYPE;
  pause_gate_count integer;
  other_gate_count integer;
  invalid_gate_count integer;
  readiness_generation bigint;
  assessment_deadline timestamptz;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_expected_pause_generation IS NULL
     OR p_expected_pause_generation < 1
     OR pg_catalog.jsonb_typeof(p_assessment) IS DISTINCT FROM 'object'
     OR p_assessment->>'assessment_id' IS NULL
     OR p_assessment->>'assessment_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_assessment->>'action' IS DISTINCT FROM 'NEW_ENTRY'
     OR p_assessment->>'status' IS DISTINCT FROM 'READY_TO_RESUME'
     OR p_assessment->>'pause_generation' IS NULL
     OR p_assessment->>'pause_generation' IS DISTINCT FROM p_expected_pause_generation::text
     OR p_assessment->>'input_generation' IS NULL
     OR p_assessment->>'input_generation' !~ '^[1-9][0-9]*$'
     OR p_assessment->>'pending_entry_orders_clear' IS DISTINCT FROM 'true'
     OR p_assessment->>'evaluated_at' IS NULL
     OR p_assessment->>'evaluated_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$'
     OR p_assessment->>'freshness_deadline' IS NULL
     OR p_assessment->>'freshness_deadline' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$'
     OR pg_catalog.jsonb_typeof(p_assessment->'gate_results') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_assessment->'allowed_warning_gate_ids') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'resume assessment envelope is invalid'
      USING ERRCODE = '22023';
  END IF;
  readiness_generation := (p_assessment->>'input_generation')::bigint;
  assessment_deadline := (p_assessment->>'freshness_deadline')::timestamptz;
  IF (p_assessment->>'evaluated_at')::timestamptz
       > pg_catalog.clock_timestamp()
     OR assessment_deadline <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'resume assessment is not current'
      USING ERRCODE = '23514';
  END IF;

  SELECT count(*) INTO pause_gate_count
    FROM pg_catalog.jsonb_array_elements(p_assessment->'gate_results') AS gate(value)
    WHERE gate.value->>'gate_id' = 'entry_pause_authority'
      AND gate.value->>'status' = 'BLOCK'
      AND gate.value->'reason_codes' @> '["ENTRY_PAUSED"]'::jsonb;
  SELECT count(*) INTO other_gate_count
    FROM pg_catalog.jsonb_array_elements(p_assessment->'gate_results') AS gate(value)
    WHERE gate.value->>'gate_id' <> 'entry_pause_authority';
  SELECT count(*) INTO invalid_gate_count
    FROM pg_catalog.jsonb_array_elements(p_assessment->'gate_results') AS gate(value)
    WHERE gate.value->>'gate_id' IS NULL
       OR (
         gate.value->>'gate_id' = 'entry_pause_authority'
         AND NOT (
           gate.value->>'status' = 'BLOCK'
           AND gate.value->'reason_codes' @> '["ENTRY_PAUSED"]'::jsonb
         )
       )
       OR (
         gate.value->>'gate_id' <> 'entry_pause_authority'
         AND NOT (
           gate.value->>'status' = 'PASS'
           OR (
             gate.value->>'status' = 'WARN'
             AND p_assessment->'allowed_warning_gate_ids'
               @> pg_catalog.jsonb_build_array(gate.value->>'gate_id')
           )
         )
       );
  IF pause_gate_count <> 1
     OR other_gate_count < 1
     OR invalid_gate_count <> 0
     OR (
       SELECT count(*) <> count(DISTINCT gate.value->>'gate_id')
       FROM pg_catalog.jsonb_array_elements(p_assessment->'gate_results') AS gate(value)
     )
     OR (
       SELECT count(*) <> count(DISTINCT warning.value)
       FROM pg_catalog.jsonb_array_elements_text(
         p_assessment->'allowed_warning_gate_ids'
       ) AS warning(value)
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements_text(
         p_assessment->'allowed_warning_gate_ids'
       ) AS warning(value)
       WHERE NOT EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements(p_assessment->'gate_results')
           AS gate(value)
         WHERE gate.value->>'gate_id' = warning.value
           AND gate.value->>'status' = 'WARN'
       )
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(p_assessment->'allowed_warning_gate_ids')
         AS warning(value)
       WHERE pg_catalog.jsonb_typeof(warning.value) IS DISTINCT FROM 'string'
     ) THEN
    RAISE EXCEPTION 'resume requires every non-pause entry prerequisite to pass'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO state_row
    FROM qc2_execution.entry_pause_state AS state
    WHERE state.singleton_id
    FOR UPDATE;
  IF NOT FOUND
     OR NOT state_row.entry_paused
     OR state_row.generation <> p_expected_pause_generation THEN
    RETURN;
  END IF;

  UPDATE qc2_execution.entry_pause_cancel_work AS work
    SET work_state = 'RESOLVED',
        updated_at = pg_catalog.clock_timestamp()
    FROM qc2_execution.paper_order_intent AS target
    WHERE target.id = work.target_intent_id
      AND work.work_state IN ('PENDING','ENQUEUED')
      AND target.intent_state NOT IN (
        'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED','PARTIALLY_FILLED',
        'CANCEL_REQUESTED'
      );
  IF EXISTS (
    SELECT 1
    FROM qc2_execution.paper_order_intent AS intent
    WHERE intent.intent_contract->>'action_kind' = 'OPEN_LONG'
      AND intent.intent_contract->>'side' = 'BUY'
      AND intent.intent_state IN (
        'CREATED','VERIFIED','RESERVED','QUEUED_FOR_SUBMISSION',
        'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED',
        'PARTIALLY_FILLED','CANCEL_REQUESTED'
      )
  ) OR EXISTS (
    SELECT 1
    FROM qc2_execution.entry_pause_cancel_work AS work
    JOIN qc2_execution.paper_order_intent AS target
      ON target.id = work.target_intent_id
    WHERE work.work_state IN ('PENDING','ENQUEUED')
      AND target.intent_state IN (
        'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED',
        'PARTIALLY_FILLED','CANCEL_REQUESTED'
      )
  ) THEN
    RAISE EXCEPTION 'pending entry orders must settle before resume'
      USING ERRCODE = '23514';
  END IF;

  UPDATE qc2_execution.entry_pause_state AS state
    SET entry_paused = false,
        generation = state.generation + 1,
        reason_code = NULL,
        updated_at = pg_catalog.clock_timestamp()
    WHERE state.singleton_id
    RETURNING * INTO state_row;
  PERFORM qc2_integrity_build.append_event_internal(
    'new_entry_pause_resumed',
    pg_catalog.jsonb_build_object(
      'assessment_id', p_assessment->>'assessment_id',
      'pause_generation', p_expected_pause_generation,
      'input_generation', readiness_generation,
      'freshness_deadline', assessment_deadline,
      'new_generation', state_row.generation
    ),
    0,
    '[]'::jsonb
  );
  RETURN QUERY SELECT state_row.entry_paused, state_row.generation;
END
$function$;

CREATE FUNCTION qc2_execution.assert_submit_time_readiness(
  p_intent jsonb,
  p_gate_snapshot jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
DECLARE
  expected_action text;
  matching_assessments integer;
  input_generation bigint;
  scopes text[];
  pause_state qc2_execution.entry_pause_state%ROWTYPE;
BEGIN
  IF pg_catalog.jsonb_typeof(p_gate_snapshot) IS DISTINCT FROM 'object'
     OR p_gate_snapshot->>'input_generation' IS NULL
     OR p_gate_snapshot->>'input_generation' !~ '^[1-9][0-9]*$'
     OR p_gate_snapshot->>'entry_pause_generation' IS NULL
     OR p_gate_snapshot->>'entry_pause_generation' !~ '^[1-9][0-9]*$'
     OR p_gate_snapshot->>'account_identity_status' IS DISTINCT FROM 'VERIFIED'
     OR p_gate_snapshot->>'reconciliation_status' IS DISTINCT FROM 'FRESH'
     OR pg_catalog.jsonb_typeof(p_gate_snapshot->'readiness') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_typeof(p_gate_snapshot->'emergency_scopes') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'submit-time readiness snapshot is incomplete'
      USING ERRCODE = '23514';
  END IF;
  input_generation := (p_gate_snapshot->>'input_generation')::bigint;
  expected_action := qc2_execution.expected_readiness_action(p_intent);
  IF expected_action IS NULL THEN
    RAISE EXCEPTION 'paper-order action has no readiness scope'
      USING ERRCODE = '23514';
  END IF;

  SELECT count(*) INTO matching_assessments
    FROM pg_catalog.jsonb_array_elements(p_gate_snapshot->'readiness') AS assessment(value)
    WHERE assessment.value->>'action' = expected_action
      AND assessment.value->>'status' = 'READY'
      AND assessment.value->>'input_generation' = input_generation::text
      AND assessment.value->>'assessment_id' ~
        '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      AND assessment.value->>'freshness_deadline' ~
        '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$'
      AND (assessment.value->>'freshness_deadline')::timestamptz
        > pg_catalog.clock_timestamp();
  IF matching_assessments <> 1 THEN
    RAISE EXCEPTION 'submit-time action readiness is stale or generation-mismatched'
      USING ERRCODE = '23514';
  END IF;

  SELECT coalesce(pg_catalog.array_agg(scope.value), ARRAY[]::text[])
    INTO scopes
    FROM pg_catalog.jsonb_array_elements_text(
      p_gate_snapshot->'emergency_scopes'
    ) AS scope(value);
  IF cardinality(scopes) <> (
       SELECT count(DISTINCT scope.value)
       FROM pg_catalog.jsonb_array_elements_text(
         p_gate_snapshot->'emergency_scopes'
       ) AS scope(value)
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
         p_gate_snapshot->'emergency_scopes'
       ) AS scope(value)
       WHERE pg_catalog.jsonb_typeof(scope.value) IS DISTINCT FROM 'string'
     )
     OR EXISTS (
       SELECT 1
       FROM unnest(scopes) AS scope(value)
       WHERE scope.value NOT IN (
         'NEW_EXPOSURE_HALT','SCIENTIFIC_HOLD','EXECUTION_UNCERTAIN',
         'IDENTITY_HALT','INTEGRITY_HALT'
       )
     ) THEN
    RAISE EXCEPTION 'submit-time emergency scope set is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF scopes && ARRAY['IDENTITY_HALT','INTEGRITY_HALT']::text[]
     OR (
       expected_action = 'NEW_ENTRY'
       AND scopes && ARRAY[
         'NEW_EXPOSURE_HALT','SCIENTIFIC_HOLD','EXECUTION_UNCERTAIN'
       ]::text[]
     ) THEN
    RAISE EXCEPTION 'emergency scope blocks this broker mutation'
      USING ERRCODE = '23514';
  END IF;

  IF expected_action = 'NEW_ENTRY' THEN
    IF p_gate_snapshot->>'entry_paused' IS DISTINCT FROM 'false' THEN
      RAISE EXCEPTION 'new entries are paused'
        USING ERRCODE = '23514';
    END IF;
    SELECT * INTO pause_state
      FROM qc2_execution.entry_pause_state AS state
      WHERE state.singleton_id
      FOR SHARE;
    IF NOT FOUND
       OR pause_state.entry_paused
       OR pause_state.generation <>
         (p_gate_snapshot->>'entry_pause_generation')::bigint THEN
      RAISE EXCEPTION 'entry-pause state changed before broker authorization'
        USING ERRCODE = '40001';
    END IF;
  END IF;
END
$function$;

CREATE OR REPLACE FUNCTION qc2_control.authorize_paper_order_attempt(
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
    PERFORM qc2_execution.assert_submit_time_readiness(
      intent_row.intent_contract, p_gate_snapshot
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
      'input_generation', p_gate_snapshot->>'input_generation'
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION
  qc2_control.get_entry_pause_state(),
  qc2_control.pause_new_entries(uuid, text),
  qc2_control.pending_entry_pause_cancellations(),
  qc2_control.reserve_pause_cancel_intent_id(bigint, uuid, uuid),
  qc2_control.mark_pause_cancel_enqueued(bigint, uuid, uuid),
  qc2_control.resume_new_entries(bigint, jsonb),
  qc2_execution.assert_submit_time_readiness(jsonb, jsonb)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  qc2_control.get_entry_pause_state(),
  qc2_control.pause_new_entries(uuid, text),
  qc2_control.pending_entry_pause_cancellations(),
  qc2_control.reserve_pause_cancel_intent_id(bigint, uuid, uuid),
  qc2_control.mark_pause_cancel_enqueued(bigint, uuid, uuid),
  qc2_control.resume_new_entries(bigint, jsonb)
TO qc2_runtime_execution;

RESET ROLE;
