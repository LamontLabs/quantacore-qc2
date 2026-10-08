-- QC2-025 canonical prediction runs, append-only attempts, complete rankings,
-- and irreversible seals. Runtime writes are limited to prediction authority.

SET ROLE qc2_migrator;

GRANT USAGE ON SCHEMA qc2_integrity_build TO qc2_runtime_prediction;
GRANT USAGE ON SCHEMA qc2_models_prediction TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_integrity_build.hash_json(text, jsonb)
  TO qc2_runtime_prediction;
GRANT EXECUTE ON FUNCTION qc2_control.assert_runtime_authority(text)
  TO qc2_runtime_prediction, qc2_runtime_validation;

CREATE TABLE qc2_models_prediction.scheduled_attempt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  schedule_created_at timestamptz NOT NULL,
  expected_deadline timestamptz NOT NULL,
  attempt_state text NOT NULL CHECK (
    attempt_state IN ('SCHEDULED','STARTED','SEALED','MISSED_START','FAILED','NONQUALIFYING')
  ),
  run_id uuid,
  missed_reason text,
  attempt_contract jsonb NOT NULL CHECK (
    attempt_contract->>'schema_name' = 'qc2.validation.ScheduledAttempt.v1'
    AND attempt_contract->>'schema_version' = '1.0'
    AND attempt_contract->>'owning_authority' = 'validation'
    AND attempt_contract->>'id' = id::text
    AND attempt_contract->>'session_id' = session_id
    AND attempt_contract->>'attempt_state' = attempt_state
    AND attempt_contract->'epoch_ref'->>'target_id' = epoch_id::text
  ),
  UNIQUE (epoch_id, session_id),
  CHECK (expected_deadline >= schedule_created_at),
  CHECK (
    (attempt_state = 'MISSED_START' AND missed_reason IS NOT NULL AND run_id IS NULL)
    OR (attempt_state <> 'MISSED_START' AND missed_reason IS NULL)
  ),
  CHECK (
    (attempt_state IN ('SCHEDULED','MISSED_START') AND run_id IS NULL)
    OR (attempt_state IN ('STARTED','SEALED','FAILED','NONQUALIFYING') AND run_id IS NOT NULL)
  )
);

CREATE TABLE qc2_models_prediction.prediction_run (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  scheduled_attempt_id uuid NOT NULL UNIQUE
    REFERENCES qc2_models_prediction.scheduled_attempt(id) ON DELETE RESTRICT,
  epoch_id uuid NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  run_state text NOT NULL CHECK (
    run_state IN (
      'CREATED','INPUTS_BOUND','FEATURES_COMPLETE','SCORED','RANKED',
      'SEALED','ABORTED','FAILED_BEFORE_SEAL'
    )
  ),
  generation integer NOT NULL CHECK (generation > 0),
  decision_deadline timestamptz NOT NULL,
  seal_deadline timestamptz NOT NULL,
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE','HISTORICAL_RECONSTRUCTED','FORWARD_OPERATIONAL','FORWARD_SEALED'
    )
  ),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  binding_snapshot jsonb NOT NULL CHECK (jsonb_typeof(binding_snapshot) = 'object'),
  binding_hash text NOT NULL CHECK (binding_hash ~ '^[0-9a-f]{64}$'),
  run_contract jsonb NOT NULL CHECK (
    run_contract->>'schema_name' = 'qc2.models_prediction.PredictionRun.v1'
    AND run_contract->>'schema_version' = '1.0'
    AND run_contract->>'owning_authority' = 'prediction'
    AND run_contract->>'id' = id::text
    AND run_contract->>'session_id' = session_id
    AND run_contract->>'run_state' = run_state
    AND run_contract->>'generation' = generation::text
    AND run_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND run_contract->>'evidence_class' = evidence_class
    AND run_contract->>'environment_namespace' = environment_namespace
    AND run_contract->>'decision_deadline' IS NOT NULL
    AND run_contract->>'seal_deadline' IS NOT NULL
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (epoch_id, session_id),
  CHECK (decision_deadline <= seal_deadline),
  CHECK (
    binding_snapshot->>'session_id' = session_id
    AND binding_snapshot->'epoch_ref'->>'target_id' = epoch_id::text
    AND binding_snapshot->'operating_champion_pointer'->>'generation' = generation::text
    AND pg_catalog.jsonb_typeof(binding_snapshot->'eligible_instrument_refs') = 'array'
    AND pg_catalog.jsonb_array_length(binding_snapshot->'eligible_instrument_refs') > 0
  ),
  CHECK (
    environment_namespace <> 'production' OR evidence_class = 'FORWARD_SEALED'
  ),
  CHECK (
    (run_contract->>'decision_deadline')::timestamptz = decision_deadline
    AND (run_contract->>'seal_deadline')::timestamptz = seal_deadline
    AND (run_contract->>'created_at')::timestamptz = created_at
  )
);

ALTER TABLE qc2_models_prediction.scheduled_attempt
  ADD CONSTRAINT scheduled_attempt_run_fk
  FOREIGN KEY (run_id) REFERENCES qc2_models_prediction.prediction_run(id)
  ON DELETE RESTRICT;

CREATE TABLE qc2_models_prediction.prediction_attempt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  run_id uuid NOT NULL REFERENCES qc2_models_prediction.prediction_run(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number > 0),
  attempt_event text NOT NULL CHECK (attempt_event IN ('STARTED','COMPLETED')),
  attempt_record jsonb NOT NULL CHECK (jsonb_typeof(attempt_record) = 'object'),
  recorded_at timestamptz NOT NULL,
  UNIQUE (run_id, attempt_number, attempt_event)
);

CREATE TABLE qc2_models_prediction.prediction_row (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  run_id uuid NOT NULL REFERENCES qc2_models_prediction.prediction_run(id) ON DELETE RESTRICT,
  instrument_id uuid NOT NULL,
  disposition text NOT NULL CHECK (disposition IN ('SCORED','UNSCORABLE')),
  score text,
  rank integer CHECK (rank IS NULL OR rank > 0),
  row_contract jsonb NOT NULL CHECK (
    row_contract->>'schema_name' = 'qc2.models_prediction.Prediction.v1'
    AND row_contract->>'schema_version' = '1.0'
    AND row_contract->>'owning_authority' = 'prediction'
    AND row_contract->>'id' = id::text
    AND row_contract->'run_ref'->>'target_id' = run_id::text
    AND row_contract->'instrument_ref'->>'target_id' = instrument_id::text
    AND row_contract->>'disposition' = disposition
    AND row_contract->>'score' IS NOT DISTINCT FROM score
    AND row_contract->>'rank' IS NOT DISTINCT FROM rank::text
    AND row_contract->>'content_hash' ~ '^[0-9a-f]{64}$'
  ),
  scientific_payload jsonb,
  scientific_payload_hash text CHECK (
    scientific_payload_hash IS NULL OR scientific_payload_hash ~ '^[0-9a-f]{64}$'
  ),
  UNIQUE (run_id, instrument_id),
  CHECK (
    (
      disposition = 'SCORED' AND score IS NOT NULL AND rank IS NOT NULL
      AND scientific_payload IS NOT NULL AND scientific_payload_hash IS NOT NULL
    )
    OR
    (
      disposition = 'UNSCORABLE' AND score IS NULL AND rank IS NULL
      AND scientific_payload IS NULL AND scientific_payload_hash IS NULL
      AND row_contract->>'unscorable_reason' IS NOT NULL
    )
  ),
  CHECK (
    scientific_payload IS NULL
    OR (
      scientific_payload->>'schema_name'
        = 'qc2.models_prediction.ScientificPredictionPayload.v1'
      AND scientific_payload->>'content_hash' = scientific_payload_hash
    )
  )
);

CREATE UNIQUE INDEX prediction_row_rank_unique
  ON qc2_models_prediction.prediction_row(run_id, rank)
  WHERE disposition = 'SCORED';

CREATE TABLE qc2_models_prediction.prediction_seal (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  run_id uuid NOT NULL UNIQUE
    REFERENCES qc2_models_prediction.prediction_run(id) ON DELETE RESTRICT,
  epoch_id uuid NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  role text NOT NULL CHECK (
    role IN ('OPERATING','DIAGNOSTIC')
  ),
  payload_inventory_hash text NOT NULL CHECK (payload_inventory_hash ~ '^[0-9a-f]{64}$'),
  deadline timestamptz NOT NULL,
  sealed_at timestamptz NOT NULL,
  seal_contract jsonb NOT NULL CHECK (
    seal_contract->>'schema_name' = 'qc2.models_prediction.PredictionSeal.v1'
    AND seal_contract->>'schema_version' = '1.0'
    AND seal_contract->>'owning_authority' = 'prediction'
    AND seal_contract->>'id' = id::text
    AND seal_contract->'run_ref'->>'target_id' = run_id::text
    AND seal_contract->>'session_id' = session_id
    AND seal_contract->>'role' = role
    AND seal_contract->>'payload_inventory_hash' = payload_inventory_hash
    AND seal_contract->>'content_hash' ~ '^[0-9a-f]{64}$'
  ),
  UNIQUE (epoch_id, session_id, id),
  CHECK (deadline IS NOT NULL AND sealed_at IS NOT NULL)
);

CREATE UNIQUE INDEX prediction_one_official_operating_seal
  ON qc2_models_prediction.prediction_seal(epoch_id, session_id)
  WHERE role = 'OPERATING';

CREATE FUNCTION qc2_models_prediction.guard_scheduled_attempt_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_models_prediction
AS $function$
DECLARE
  expected_run_ref jsonb;
BEGIN
  IF OLD.attempt_state = 'SCHEDULED' AND NEW.attempt_state = 'MISSED_START' THEN
    PERFORM qc2_control.assert_runtime_authority('validation');
  ELSE
    PERFORM qc2_control.assert_runtime_authority('prediction');
  END IF;
  expected_run_ref := CASE WHEN NEW.run_id IS NULL THEN 'null'::jsonb
    ELSE pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.PredictionRun.v1',
      'target_id', NEW.run_id::text
    )
  END;
  IF ROW(
    NEW.id, NEW.epoch_id, NEW.session_id, NEW.schedule_created_at,
    NEW.expected_deadline
  ) IS DISTINCT FROM ROW(
    OLD.id, OLD.epoch_id, OLD.session_id, OLD.schedule_created_at,
    OLD.expected_deadline
  ) THEN
    RAISE EXCEPTION 'scheduled attempt identity and deadline are immutable'
      USING ERRCODE = '42501';
  END IF;
  IF OLD.run_id IS NOT NULL AND NEW.run_id IS DISTINCT FROM OLD.run_id THEN
    RAISE EXCEPTION 'scheduled attempt run binding cannot be replaced'
      USING ERRCODE = '42501';
  END IF;
  IF NOT (
    (OLD.attempt_state = 'SCHEDULED'
      AND NEW.attempt_state IN ('STARTED','MISSED_START'))
    OR (OLD.attempt_state = 'STARTED'
      AND NEW.attempt_state IN ('SEALED','FAILED','NONQUALIFYING'))
  ) THEN
    RAISE EXCEPTION 'invalid scheduled attempt transition: % -> %',
      OLD.attempt_state, NEW.attempt_state
      USING ERRCODE = '23514';
  END IF;
  IF (NEW.attempt_contract - ARRAY['attempt_state','run_ref','missed_reason']::text[])
     IS DISTINCT FROM
     (OLD.attempt_contract - ARRAY['attempt_state','run_ref','missed_reason']::text[])
    OR NEW.attempt_contract->>'attempt_state' <> NEW.attempt_state
     OR NEW.attempt_contract->'run_ref' IS DISTINCT FROM expected_run_ref
    OR NEW.attempt_contract->>'missed_reason' IS DISTINCT FROM NEW.missed_reason THEN
    RAISE EXCEPTION 'scheduled attempt contract does not match its guarded transition'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_scheduled_attempt_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  IF NEW.attempt_state <> 'SCHEDULED'
    OR NEW.run_id IS NOT NULL
    OR NEW.missed_reason IS NOT NULL
    OR NEW.attempt_contract->>'attempt_state' <> 'SCHEDULED'
    OR NEW.attempt_contract->'run_ref' IS DISTINCT FROM 'null'::jsonb
    OR NEW.attempt_contract->>'missed_reason' IS NOT NULL
    OR (NEW.attempt_contract->>'schedule_created_at')::timestamptz
       <> NEW.schedule_created_at
    OR (NEW.attempt_contract->>'expected_deadline')::timestamptz
       <> NEW.expected_deadline THEN
    RAISE EXCEPTION 'scheduled attempt must be inserted as a complete immutable schedule'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_prediction_run_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_models_prediction
AS $function$
DECLARE
  scheduled qc2_models_prediction.scheduled_attempt%ROWTYPE;
  pointer jsonb;
  expected_binding_hash text;
  eligible_ref_count bigint;
  distinct_eligible_count bigint;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  IF NEW.run_state <> 'INPUTS_BOUND' THEN
    RAISE EXCEPTION 'prediction run must be born with frozen INPUTS_BOUND state'
      USING ERRCODE = '23514';
  END IF;
  SELECT * INTO STRICT scheduled
    FROM qc2_models_prediction.scheduled_attempt
    WHERE id = NEW.scheduled_attempt_id
    FOR UPDATE;
  IF scheduled.attempt_state <> 'SCHEDULED'
    OR scheduled.epoch_id <> NEW.epoch_id
    OR scheduled.session_id <> NEW.session_id
    OR NEW.created_at > scheduled.expected_deadline
    OR scheduled.attempt_contract->>'evidence_class' <> NEW.evidence_class
    OR scheduled.attempt_contract->>'environment_namespace' <> NEW.environment_namespace THEN
    RAISE EXCEPTION 'prediction run does not match an available scheduled attempt'
      USING ERRCODE = '23514';
  END IF;
  pointer := NEW.binding_snapshot->'operating_champion_pointer';
  expected_binding_hash := qc2_integrity_build.hash_json(
    'qc2.prediction-run-bindings.v1', NEW.binding_snapshot
  );
  IF expected_binding_hash <> NEW.binding_hash
    OR pointer->>'role' <> 'OPERATING'
    OR pointer->>'generation' <> NEW.generation::text
    OR pointer->>'evidence_class' <> NEW.evidence_class
    OR pointer->>'environment_namespace' <> NEW.environment_namespace
    OR (pointer->>'created_at')::timestamptz > NEW.created_at
    OR (pointer->>'transitioned_at')::timestamptz > NEW.created_at
    OR pointer->'model_ref' IS DISTINCT FROM NEW.binding_snapshot->'operating_model_ref'
    OR pointer->'epoch_ref' IS DISTINCT FROM NEW.binding_snapshot->'epoch_ref'
    OR NEW.run_contract->'epoch_ref' IS DISTINCT FROM NEW.binding_snapshot->'epoch_ref'
    OR NEW.run_contract->'snapshot_ref' IS DISTINCT FROM NEW.binding_snapshot->'snapshot_ref'
    OR NOT (
      NEW.run_contract->'source_refs' @> pg_catalog.jsonb_build_array(
        NEW.binding_snapshot->'census_ref',
        NEW.binding_snapshot->'universe_ref',
        NEW.binding_snapshot->'scientific_code_ref'
      )
    )
    OR NOT (
      NEW.run_contract->'dependency_refs' @> pg_catalog.jsonb_build_array(
        NEW.binding_snapshot->'feature_registry_ref',
        NEW.binding_snapshot->'protocol_registry_ref',
        NEW.binding_snapshot->'label_registry_ref',
        NEW.binding_snapshot->'score_manifest_ref',
        NEW.binding_snapshot->'operating_model_ref',
        NEW.binding_snapshot->'reference_model_ref',
        pg_catalog.jsonb_build_object(
          'target_schema_name', 'qc2.governance_owner.ChampionPointer.v1',
          'target_id', pointer->>'id',
          'content_hash', pointer->>'pointer_hash'
        ),
        NEW.binding_snapshot->'calendar_ref'
      )
    )
    OR NOT (
      NEW.run_contract->'dependency_refs'
        @> NEW.binding_snapshot->'shadow_prediction_set_refs'
      AND NEW.run_contract->'dependency_refs'
        @> NEW.binding_snapshot->'baseline_manifest_refs'
      AND NEW.run_contract->'dependency_refs'
        @> NEW.binding_snapshot->'memory_index_refs'
    )
    OR (NEW.binding_snapshot->'retry_policy'->>'max_attempts')::integer < 1
    OR NEW.binding_snapshot->'retry_policy'->>'row_order'
       <> 'STABLE_INSTRUMENT_ID_ASC'
    OR NEW.binding_snapshot->'retry_policy'->>'replacement_policy'
       <> 'FIRST_SCORED_RESULT_WINS' THEN
    RAISE EXCEPTION 'prediction run bindings do not pin one coherent Champion generation'
      USING ERRCODE = '23514';
  END IF;
  SELECT pg_catalog.count(*), pg_catalog.count(DISTINCT ref->>'target_id')
    INTO eligible_ref_count, distinct_eligible_count
    FROM pg_catalog.jsonb_array_elements(
      NEW.binding_snapshot->'eligible_instrument_refs'
    ) AS eligible(ref);
  IF eligible_ref_count = 0 OR eligible_ref_count <> distinct_eligible_count THEN
    RAISE EXCEPTION 'frozen eligible instrument inventory is empty or duplicated'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.start_scheduled_attempt_after_run()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_models_prediction
AS $function$
BEGIN
  UPDATE qc2_models_prediction.scheduled_attempt
    SET attempt_state = 'STARTED',
        run_id = NEW.id,
        attempt_contract = pg_catalog.jsonb_set(
          pg_catalog.jsonb_set(
            attempt_contract,
            '{attempt_state}',
            '"STARTED"'::jsonb
          ),
          '{run_ref}',
          pg_catalog.jsonb_build_object(
            'target_schema_name', 'qc2.models_prediction.PredictionRun.v1',
            'target_id', NEW.id::text
          )
        )
    WHERE id = NEW.scheduled_attempt_id;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.finalize_prediction_after_seal()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_models_prediction
AS $function$
<<finalize_block>>
DECLARE
  run_row qc2_models_prediction.prediction_run%ROWTYPE;
  scheduled_state text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  SELECT * INTO STRICT run_row
    FROM qc2_models_prediction.prediction_run
    WHERE id = NEW.run_id;
  scheduled_state := CASE WHEN NEW.role = 'OPERATING' THEN 'SEALED' ELSE 'NONQUALIFYING' END;

  UPDATE qc2_models_prediction.prediction_run
    SET run_state = 'SEALED',
        run_contract = pg_catalog.jsonb_set(
          run_contract,
          '{run_state}',
          '"SEALED"'::jsonb
        )
    WHERE id = run_row.id;

  UPDATE qc2_models_prediction.scheduled_attempt
    SET attempt_state = finalize_block.scheduled_state,
        attempt_contract = pg_catalog.jsonb_set(
          attempt_contract,
          '{attempt_state}',
          pg_catalog.to_jsonb(finalize_block.scheduled_state)
        )
    WHERE id = run_row.scheduled_attempt_id;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_prediction_run_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_models_prediction
AS $function$
DECLARE
  expected_hash text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  IF ROW(
    NEW.id, NEW.scheduled_attempt_id, NEW.epoch_id, NEW.session_id,
    NEW.generation, NEW.decision_deadline, NEW.seal_deadline,
    NEW.evidence_class, NEW.environment_namespace, NEW.binding_snapshot,
    NEW.binding_hash, NEW.created_at
  ) IS DISTINCT FROM ROW(
    OLD.id, OLD.scheduled_attempt_id, OLD.epoch_id, OLD.session_id,
    OLD.generation, OLD.decision_deadline, OLD.seal_deadline,
    OLD.evidence_class, OLD.environment_namespace, OLD.binding_snapshot,
    OLD.binding_hash, OLD.created_at
  ) THEN
    RAISE EXCEPTION 'prediction run scientific bindings are immutable'
      USING ERRCODE = '42501';
  END IF;
  IF OLD.run_state = 'SEALED' THEN
    RAISE EXCEPTION 'sealed prediction run is terminal'
      USING ERRCODE = '42501';
  END IF;
  IF NEW.run_state <> OLD.run_state THEN
    IF NOT (
      (OLD.run_state = 'CREATED' AND NEW.run_state IN ('INPUTS_BOUND','ABORTED','FAILED_BEFORE_SEAL'))
      OR (OLD.run_state = 'INPUTS_BOUND'
        AND NEW.run_state IN ('FEATURES_COMPLETE','ABORTED','FAILED_BEFORE_SEAL'))
      OR (OLD.run_state = 'FEATURES_COMPLETE'
        AND NEW.run_state IN ('SCORED','ABORTED','FAILED_BEFORE_SEAL'))
      OR (OLD.run_state = 'SCORED'
        AND NEW.run_state IN ('RANKED','ABORTED','FAILED_BEFORE_SEAL'))
      OR (OLD.run_state = 'RANKED' AND NEW.run_state = 'SEALED')
    ) THEN
      RAISE EXCEPTION 'invalid prediction run transition: % -> %',
        OLD.run_state, NEW.run_state
        USING ERRCODE = '23514';
    END IF;
  END IF;
  IF (NEW.run_contract - 'run_state') IS DISTINCT FROM
     (OLD.run_contract - 'run_state')
    OR NEW.run_contract->>'run_state' <> NEW.run_state THEN
    RAISE EXCEPTION 'prediction run contract may change only its guarded state field'
      USING ERRCODE = '23514';
  END IF;
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.prediction-run-bindings.v1', NEW.binding_snapshot
  );
  IF expected_hash <> NEW.binding_hash THEN
    RAISE EXCEPTION 'prediction run binding hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.run_state = 'SEALED' AND NOT EXISTS (
    SELECT 1
    FROM qc2_models_prediction.prediction_seal AS seal
    WHERE seal.run_id = NEW.id
  ) THEN
    RAISE EXCEPTION 'prediction run cannot become SEALED without its immutable seal'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_prediction_row_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_models_prediction
AS $function$
DECLARE
  run_state text;
  expected_hash text;
  expected_payload_hash text;
  payload_basis jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  SELECT prediction.run_state INTO STRICT run_state
    FROM qc2_models_prediction.prediction_run AS prediction
    WHERE prediction.id = NEW.run_id
    FOR UPDATE;
  IF run_state <> 'SCORED' THEN
    RAISE EXCEPTION 'prediction rows may be added only after scoring and before ranking'
      USING ERRCODE = '23514';
  END IF;
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.models_prediction.prediction.v1/1.0',
    NEW.row_contract
      - ARRAY['schema_name','schema_version','id','created_at','content_hash']::text[]
  );
  IF expected_hash <> NEW.row_contract->>'content_hash' THEN
    RAISE EXCEPTION 'prediction row content hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.disposition = 'SCORED' THEN
    payload_basis := pg_catalog.jsonb_build_object(
      'session_id', NEW.scientific_payload->'session_id',
      'reference_kind', NEW.scientific_payload->'reference_kind',
      'reference_price', NEW.scientific_payload->'reference_price',
      'instrument_ref', NEW.scientific_payload->'instrument_ref',
      'horizon_label_refs', NEW.scientific_payload->'horizon_label_refs',
      'head_output_refs', NEW.scientific_payload->'head_output_refs',
      'dependency_refs', NEW.scientific_payload->'dependency_refs',
      'score', NEW.scientific_payload->'score',
      'rank', NEW.scientific_payload->'rank',
      'disposition', NEW.scientific_payload->'disposition',
      'model_hash', NEW.scientific_payload->'model_hash',
      'epoch_ref', NEW.scientific_payload->'epoch_ref',
      'regime', NEW.scientific_payload->'regime'
    );
    expected_payload_hash := qc2_integrity_build.hash_json(
      'qc2.contract-content.v1/qc2.models_prediction.scientificpredictionpayload.v1/1.0',
      payload_basis
    );
    IF expected_payload_hash <> NEW.scientific_payload_hash
      OR expected_payload_hash <> NEW.scientific_payload->>'content_hash' THEN
      RAISE EXCEPTION 'scientific prediction payload hash is invalid'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_prediction_attempt_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_models_prediction
AS $function$
DECLARE
  run_row qc2_models_prediction.prediction_run%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  SELECT * INTO STRICT run_row
    FROM qc2_models_prediction.prediction_run
    WHERE id = NEW.run_id;
  IF NEW.attempt_record->>'attempt_number' <> NEW.attempt_number::text
    OR NEW.attempt_record->>'attempt_event' <> NEW.attempt_event
    OR NEW.attempt_number >
       (run_row.binding_snapshot->'retry_policy'->>'max_attempts')::integer
    OR run_row.run_state IN ('SEALED','ABORTED','FAILED_BEFORE_SEAL')
    OR (
      NEW.attempt_number = 1
      AND (NEW.attempt_event <> 'COMPLETED' OR run_row.run_state <> 'FEATURES_COMPLETE')
    )
    OR (
      NEW.attempt_number > 1
      AND (
        run_row.run_state <> 'SCORED'
        OR (
          NEW.attempt_event = 'COMPLETED'
          AND NOT EXISTS (
            SELECT 1
            FROM qc2_models_prediction.prediction_attempt AS attempt
            WHERE attempt.run_id = NEW.run_id
              AND attempt.attempt_number = NEW.attempt_number
              AND attempt.attempt_event = 'STARTED'
          )
        )
      )
    ) THEN
    RAISE EXCEPTION 'prediction attempt is outside the frozen retry sequence'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_prediction_seal_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_models_prediction
AS $function$
DECLARE
  run_row qc2_models_prediction.prediction_run%ROWTYPE;
  row_count bigint;
  scored_count bigint;
  max_rank integer;
  expected_inventory jsonb;
  expected_refs jsonb;
  expected_counts jsonb;
  expected_hash text;
  expected_seal_hash text;
  eligible_count bigint;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  SELECT * INTO STRICT run_row
    FROM qc2_models_prediction.prediction_run AS prediction
    WHERE prediction.id = NEW.run_id
    FOR UPDATE;
  IF run_row.run_state <> 'RANKED'
    OR run_row.epoch_id <> NEW.epoch_id
    OR run_row.session_id <> NEW.session_id THEN
    RAISE EXCEPTION 'seal must match a ranked prediction run'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.deadline <> run_row.seal_deadline
    OR (NEW.seal_contract->>'deadline')::timestamptz <> run_row.seal_deadline
    OR (NEW.seal_contract->>'sealed_at')::timestamptz <> NEW.sealed_at THEN
    RAISE EXCEPTION 'seal deadline or actual seal time differs from the frozen contract'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.seal_contract->>'evidence_class' <> run_row.evidence_class
    OR NEW.seal_contract->>'environment_namespace' <> run_row.environment_namespace THEN
    RAISE EXCEPTION 'seal evidence context differs from its prediction run'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.sealed_at >=
     (run_row.binding_snapshot->>'next_regular_session_open_at')::timestamptz THEN
    RAISE EXCEPTION 'prediction seal is outside the pre-outcome time fence'
      USING ERRCODE = '23514';
  END IF;
  IF (
    NEW.sealed_at <= run_row.decision_deadline
    AND NEW.sealed_at <= run_row.seal_deadline
    AND NEW.role <> 'OPERATING'
  ) OR (
    (NEW.sealed_at > run_row.decision_deadline OR NEW.sealed_at > run_row.seal_deadline)
    AND NEW.role <> 'DIAGNOSTIC'
  ) THEN
    RAISE EXCEPTION 'seal role does not match the frozen deadline result'
      USING ERRCODE = '23514';
  END IF;
  IF run_row.environment_namespace = 'production'
    AND run_row.evidence_class <> 'FORWARD_SEALED' THEN
    RAISE EXCEPTION 'fixture or reconstructed evidence cannot seal in production'
      USING ERRCODE = '42501';
  END IF;

  SELECT count(*), count(*) FILTER (WHERE disposition = 'SCORED'),
         max(rank) FILTER (WHERE disposition = 'SCORED')
    INTO row_count, scored_count, max_rank
    FROM qc2_models_prediction.prediction_row
    WHERE run_id = NEW.run_id;
  eligible_count := pg_catalog.jsonb_array_length(
    run_row.binding_snapshot->'eligible_instrument_refs'
  );
  IF row_count = 0 OR row_count <> eligible_count
    OR (scored_count > 0 AND max_rank <> scored_count)
    OR pg_catalog.jsonb_array_length(NEW.seal_contract->'ordered_prediction_refs') <> row_count THEN
    RAISE EXCEPTION 'seal row inventory is incomplete or ranks are not contiguous'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.jsonb_array_elements(run_row.binding_snapshot->'eligible_instrument_refs') AS eligible(ref)
    WHERE NOT EXISTS (
      SELECT 1
      FROM qc2_models_prediction.prediction_row AS prediction
      WHERE prediction.run_id = NEW.run_id
        AND prediction.instrument_id::text = eligible.ref->>'target_id'
    )
  ) OR EXISTS (
    SELECT 1
    FROM qc2_models_prediction.prediction_row AS prediction
    WHERE prediction.run_id = NEW.run_id
      AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(run_row.binding_snapshot->'eligible_instrument_refs') AS eligible(ref)
        WHERE eligible.ref->>'target_id' = prediction.instrument_id::text
      )
  ) THEN
    RAISE EXCEPTION 'seal rows do not match the frozen eligible universe'
      USING ERRCODE = '23514';
  END IF;
  SELECT pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'instrument_id', prediction.instrument_id::text,
        'prediction_ref', pg_catalog.jsonb_build_object(
          'target_schema_name', 'qc2.models_prediction.Prediction.v1',
          'target_id', prediction.id::text,
          'content_hash', prediction.row_contract->>'content_hash'
        ),
        'disposition', prediction.disposition,
        'rank', prediction.rank,
        'unscorable_reason', prediction.row_contract->>'unscorable_reason',
        'scientific_payload_hash', prediction.scientific_payload_hash
      )
      ORDER BY (prediction.rank IS NULL), prediction.rank, prediction.instrument_id::text
    ),
    pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.models_prediction.Prediction.v1',
        'target_id', prediction.id::text,
        'content_hash', prediction.row_contract->>'content_hash'
      )
      ORDER BY (prediction.rank IS NULL), prediction.rank, prediction.instrument_id::text
    )
    INTO expected_inventory, expected_refs
    FROM qc2_models_prediction.prediction_row AS prediction
    WHERE prediction.run_id = NEW.run_id;
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.prediction-inventory.v1', expected_inventory
  );
  IF expected_hash <> NEW.payload_inventory_hash
    OR expected_hash <> NEW.seal_contract->>'payload_inventory_hash' THEN
    RAISE EXCEPTION 'prediction seal inventory hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  SELECT pg_catalog.jsonb_agg(
      pg_catalog.to_jsonb(counts.disposition_count)
      ORDER BY counts.disposition
    )
    INTO expected_counts
    FROM (
      SELECT disposition || '=' || pg_catalog.count(*)::text AS disposition_count,
             disposition
      FROM qc2_models_prediction.prediction_row
      WHERE run_id = NEW.run_id
      GROUP BY disposition
    ) AS counts;
  IF expected_refs IS DISTINCT FROM NEW.seal_contract->'ordered_prediction_refs'
    OR expected_counts IS DISTINCT FROM NEW.seal_contract->'disposition_counts' THEN
    RAISE EXCEPTION 'prediction seal row order or disposition counts are invalid'
      USING ERRCODE = '23514';
  END IF;

  expected_seal_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.models_prediction.predictionseal.v1/1.0',
    NEW.seal_contract
      - ARRAY['schema_name','schema_version','id','created_at','content_hash']::text[]
  );
  IF expected_seal_hash <> NEW.seal_contract->>'content_hash' THEN
    RAISE EXCEPTION 'prediction seal content hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.prevent_prediction_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  RAISE EXCEPTION 'prediction attempts, rows, and seals are append-only'
    USING ERRCODE = '42501';
END
$function$;

CREATE TRIGGER scheduled_attempt_guarded_update
BEFORE UPDATE ON qc2_models_prediction.scheduled_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_scheduled_attempt_update();

CREATE TRIGGER scheduled_attempt_validate_insert
BEFORE INSERT ON qc2_models_prediction.scheduled_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_scheduled_attempt_insert();

CREATE TRIGGER prediction_run_guarded_update
BEFORE UPDATE ON qc2_models_prediction.prediction_run
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_prediction_run_update();

CREATE TRIGGER prediction_run_bindings_validate_insert
BEFORE INSERT ON qc2_models_prediction.prediction_run
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_prediction_run_insert();

CREATE TRIGGER prediction_run_start_scheduled_attempt
AFTER INSERT ON qc2_models_prediction.prediction_run
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.start_scheduled_attempt_after_run();

CREATE TRIGGER prediction_attempt_validate_insert
BEFORE INSERT ON qc2_models_prediction.prediction_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_prediction_attempt_insert();

CREATE TRIGGER prediction_row_validate_insert
BEFORE INSERT ON qc2_models_prediction.prediction_row
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_prediction_row_insert();

CREATE TRIGGER prediction_seal_validate_insert
BEFORE INSERT ON qc2_models_prediction.prediction_seal
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_prediction_seal_insert();

CREATE TRIGGER prediction_seal_finalize_run
AFTER INSERT ON qc2_models_prediction.prediction_seal
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.finalize_prediction_after_seal();

CREATE TRIGGER prediction_attempt_append_only
BEFORE UPDATE OR DELETE ON qc2_models_prediction.prediction_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.prevent_prediction_record_mutation();
CREATE TRIGGER prediction_row_append_only
BEFORE UPDATE OR DELETE ON qc2_models_prediction.prediction_row
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.prevent_prediction_record_mutation();
CREATE TRIGGER prediction_seal_append_only
BEFORE UPDATE OR DELETE ON qc2_models_prediction.prediction_seal
FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.prevent_prediction_record_mutation();

ALTER TABLE qc2_models_prediction.scheduled_attempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.scheduled_attempt FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_run FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_attempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_attempt FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_row ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_row FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_seal ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.prediction_seal FORCE ROW LEVEL SECURITY;

CREATE POLICY scheduled_attempt_migrator_all ON qc2_models_prediction.scheduled_attempt
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY prediction_run_migrator_all ON qc2_models_prediction.prediction_run
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY prediction_attempt_migrator_all ON qc2_models_prediction.prediction_attempt
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY prediction_row_migrator_all ON qc2_models_prediction.prediction_row
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY prediction_seal_migrator_all ON qc2_models_prediction.prediction_seal
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

CREATE POLICY scheduled_attempt_prediction_read ON qc2_models_prediction.scheduled_attempt
  FOR SELECT TO
    qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY prediction_run_prediction_read ON qc2_models_prediction.prediction_run
  FOR SELECT TO
    qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY prediction_attempt_prediction_read ON qc2_models_prediction.prediction_attempt
  FOR SELECT TO
    qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY prediction_row_prediction_read ON qc2_models_prediction.prediction_row
  FOR SELECT TO
    qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY prediction_seal_prediction_read ON qc2_models_prediction.prediction_seal
  FOR SELECT TO
    qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);

CREATE POLICY scheduled_attempt_prediction_update ON qc2_models_prediction.scheduled_attempt
  FOR UPDATE TO qc2_runtime_prediction
  USING (qc2_control.current_runtime_authority() = 'prediction')
  WITH CHECK (qc2_control.current_runtime_authority() = 'prediction');
CREATE POLICY scheduled_attempt_validation_insert ON qc2_models_prediction.scheduled_attempt
  FOR INSERT TO qc2_runtime_validation
  WITH CHECK (
    qc2_control.current_runtime_authority() = 'validation'
    AND attempt_state = 'SCHEDULED'
    AND run_id IS NULL
  );
CREATE POLICY scheduled_attempt_validation_missed_update
  ON qc2_models_prediction.scheduled_attempt
  FOR UPDATE TO qc2_runtime_validation
  USING (
    qc2_control.current_runtime_authority() = 'validation'
    AND attempt_state = 'SCHEDULED'
  )
  WITH CHECK (
    qc2_control.current_runtime_authority() = 'validation'
    AND attempt_state = 'MISSED_START'
    AND run_id IS NULL
  );
CREATE POLICY prediction_run_prediction_write ON qc2_models_prediction.prediction_run
  FOR ALL TO qc2_runtime_prediction
  USING (qc2_control.current_runtime_authority() = 'prediction')
  WITH CHECK (qc2_control.current_runtime_authority() = 'prediction');
CREATE POLICY prediction_attempt_prediction_insert ON qc2_models_prediction.prediction_attempt
  FOR INSERT TO qc2_runtime_prediction
  WITH CHECK (qc2_control.current_runtime_authority() = 'prediction');
CREATE POLICY prediction_row_prediction_insert ON qc2_models_prediction.prediction_row
  FOR INSERT TO qc2_runtime_prediction
  WITH CHECK (qc2_control.current_runtime_authority() = 'prediction');
CREATE POLICY prediction_seal_prediction_insert ON qc2_models_prediction.prediction_seal
  FOR INSERT TO qc2_runtime_prediction
  WITH CHECK (qc2_control.current_runtime_authority() = 'prediction');

GRANT SELECT ON
  qc2_models_prediction.scheduled_attempt,
  qc2_models_prediction.prediction_run,
  qc2_models_prediction.prediction_attempt,
  qc2_models_prediction.prediction_row,
  qc2_models_prediction.prediction_seal
TO
  qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
  qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
  qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence;

GRANT UPDATE ON qc2_models_prediction.scheduled_attempt
TO qc2_runtime_prediction;
GRANT INSERT, UPDATE ON qc2_models_prediction.prediction_run
TO qc2_runtime_prediction;
GRANT INSERT, UPDATE ON qc2_models_prediction.scheduled_attempt
TO qc2_runtime_validation;
GRANT INSERT ON
  qc2_models_prediction.prediction_attempt,
  qc2_models_prediction.prediction_row,
  qc2_models_prediction.prediction_seal
TO qc2_runtime_prediction;

RESET ROLE;
