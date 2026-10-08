-- QC2-034 append-only experiment search, resource accounting, and holdout-use ledger.
-- This migration adds forward-only tables; it does not alter QC2-026 receipts.

SET ROLE qc2_migrator;

GRANT USAGE ON SCHEMA qc2_config, qc2_outcomes_research TO
  qc2_runtime_configuration, qc2_runtime_apexlab, qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_control.assert_runtime_authority(text),
  qc2_control.current_runtime_authority(),
  qc2_integrity_build.hash_json(text, jsonb)
TO qc2_runtime_configuration, qc2_runtime_apexlab, qc2_runtime_validation;

ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_config
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_outcomes_research
  REVOKE ALL ON TABLES FROM PUBLIC;

CREATE TABLE qc2_config.research_resource_budget (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  budget_key text NOT NULL CHECK (budget_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  version integer NOT NULL CHECK (version > 0),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research')
  ),
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )
  ),
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  max_experiments integer NOT NULL CHECK (max_experiments >= 0),
  max_concurrent_jobs integer NOT NULL CHECK (max_concurrent_jobs > 0),
  max_elapsed_seconds bigint NOT NULL CHECK (max_elapsed_seconds >= 0),
  max_cpu_seconds bigint NOT NULL CHECK (max_cpu_seconds >= 0),
  max_memory_bytes bigint NOT NULL CHECK (max_memory_bytes >= 0),
  max_artifact_bytes bigint NOT NULL CHECK (max_artifact_bytes >= 0),
  authorized_cost_minor_units bigint NOT NULL CHECK (authorized_cost_minor_units >= 0),
  effective_from date NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  budget_contract jsonb NOT NULL CHECK (
    budget_contract->>'schema_name' = 'qc2.integrity_build.ResourceBudget.v1'
    AND budget_contract->>'schema_version' = '1.0'
    AND budget_contract->>'owning_authority' = 'configuration'
    AND budget_contract->>'id' = id::text
    AND budget_contract->>'budget_key' = budget_key
    AND budget_contract->>'version' = version::text
    AND budget_contract->>'environment_namespace' = environment_namespace
    AND budget_contract->>'evidence_class' = evidence_class
    AND budget_contract->>'currency' = currency
    AND budget_contract->>'max_experiments' = max_experiments::text
    AND budget_contract->>'max_concurrent_jobs' = max_concurrent_jobs::text
    AND budget_contract->>'max_elapsed_seconds' = max_elapsed_seconds::text
    AND budget_contract->>'max_cpu_seconds' = max_cpu_seconds::text
    AND budget_contract->>'max_memory_bytes' = max_memory_bytes::text
    AND budget_contract->>'max_artifact_bytes' = max_artifact_bytes::text
    AND budget_contract->>'authorized_cost_minor_units'
      = authorized_cost_minor_units::text
    AND budget_contract->>'effective_from' = effective_from::text
    AND budget_contract->>'configuration_domain' = 'RESEARCH'
    AND budget_contract->>'fixture_only' IN ('true','false')
    AND budget_contract->>'content_hash' = content_hash
  ),
  UNIQUE (environment_namespace, budget_key, version)
);

CREATE TABLE qc2_outcomes_research.experiment (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  budget_id uuid NOT NULL
    REFERENCES qc2_config.research_resource_budget(id) ON DELETE RESTRICT,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research')
  ),
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )
  ),
  created_at timestamptz NOT NULL,
  experiment_contract jsonb NOT NULL CHECK (
    experiment_contract->>'schema_name' = 'qc2.outcomes_research.Experiment.v1'
    AND experiment_contract->>'schema_version' = '1.0'
    AND experiment_contract->>'owning_authority' = 'apexlab'
    AND experiment_contract->>'id' = id::text
    AND experiment_contract->>'content_hash' = content_hash
    AND experiment_contract->>'environment_namespace' = environment_namespace
    AND experiment_contract->>'evidence_class' = evidence_class
    AND (experiment_contract->>'created_at')::timestamptz = created_at
    AND experiment_contract->'budget_ref'->>'target_schema_name'
      = 'qc2.integrity_build.ResourceBudget.v1'
    AND experiment_contract->'budget_ref'->>'target_id' = budget_id::text
  )
);

CREATE TABLE qc2_outcomes_research.experiment_trial_event (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  experiment_id uuid NOT NULL
    REFERENCES qc2_outcomes_research.experiment(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  event_type text NOT NULL CHECK (event_type IN (
    'TRIAL_STARTED',
    'TRIAL_RESUMED',
    'TRIAL_INTERRUPTED',
    'TRIAL_REJECTED',
    'TRIAL_FAILED',
    'TRIAL_COMPLETED',
    'ARTIFACT_REGISTERED'
  )),
  attempt_number integer NOT NULL CHECK (attempt_number >= 0),
  recorded_at timestamptz NOT NULL,
  previous_event_hash text CHECK (
    previous_event_hash IS NULL OR previous_event_hash ~ '^[0-9a-f]{64}$'
  ),
  event_hash text NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
  event_record jsonb NOT NULL CHECK (
    event_record->>'id' = id::text
    AND event_record->>'sequence' = sequence_no::text
    AND event_record->>'event_type' = event_type
    AND event_record->>'attempt_number' = attempt_number::text
    AND (event_record->>'recorded_at')::timestamptz = recorded_at
    AND event_record->>'event_hash' = event_hash
    AND event_record->>'previous_event_hash' IS NOT DISTINCT FROM previous_event_hash
    AND jsonb_typeof(event_record->'experiment_ref') = 'object'
    AND event_record->'experiment_ref'->>'target_schema_name'
      = 'qc2.outcomes_research.Experiment.v1'
    AND event_record->'experiment_ref'->>'target_id' = experiment_id::text
    AND jsonb_typeof(event_record->'usage') = 'object'
    AND jsonb_typeof(event_record->'budget_overruns') = 'array'
  ),
  UNIQUE (experiment_id, sequence_no)
);

CREATE TABLE qc2_outcomes_research.experiment_comparison_registration (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  experiment_ids uuid[] NOT NULL CHECK (
    pg_catalog.cardinality(experiment_ids) >= 2
  ),
  registered_at timestamptz NOT NULL,
  registration_hash text NOT NULL CHECK (registration_hash ~ '^[0-9a-f]{64}$'),
  comparison_record jsonb NOT NULL CHECK (
    comparison_record->>'id' = id::text
    AND (comparison_record->>'registered_at')::timestamptz = registered_at
    AND comparison_record->>'registration_hash' = registration_hash
    AND jsonb_typeof(comparison_record->'experiment_refs') = 'array'
    AND jsonb_typeof(comparison_record->'candidate_refs') = 'array'
  )
);

CREATE TABLE qc2_outcomes_research.experiment_evaluation_access_attempt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  experiment_id uuid NOT NULL
    REFERENCES qc2_outcomes_research.experiment(id) ON DELETE RESTRICT,
  dataset_id uuid NOT NULL CHECK (
    dataset_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  dataset_content_hash text NOT NULL CHECK (dataset_content_hash ~ '^[0-9a-f]{64}$'),
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  disposition text NOT NULL CHECK (
    disposition IN ('GRANTED','DENIED','REPEAT_BLOCKED')
  ),
  requested_at timestamptz NOT NULL,
  reason_code text,
  receipt_id uuid
    REFERENCES qc2_outcomes_research.holdout_access_receipt(id) ON DELETE RESTRICT,
  previous_event_hash text CHECK (
    previous_event_hash IS NULL OR previous_event_hash ~ '^[0-9a-f]{64}$'
  ),
  event_hash text NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
  access_record jsonb NOT NULL CHECK (
    access_record->>'id' = id::text
    AND access_record->>'sequence' = sequence_no::text
    AND access_record->>'disposition' = disposition
    AND (access_record->>'requested_at')::timestamptz = requested_at
    AND access_record->>'event_hash' = event_hash
    AND access_record->>'previous_event_hash' IS NOT DISTINCT FROM previous_event_hash
    AND access_record->'experiment_ref'->>'target_id' = experiment_id::text
    AND access_record->'dataset_ref'->>'target_id' = dataset_id::text
    AND access_record->'dataset_ref'->>'content_hash' = dataset_content_hash
    AND access_record->>'reason_code' IS NOT DISTINCT FROM reason_code
    AND access_record->'receipt_ref'->>'target_id'
      IS NOT DISTINCT FROM receipt_id::text
  ),
  UNIQUE (dataset_id, dataset_content_hash, sequence_no)
);

CREATE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority(TG_ARGV[0]);
  RAISE EXCEPTION 'QC2-034 experiment and evaluation records are append-only'
    USING ERRCODE = '42501';
END
$function$;

CREATE FUNCTION qc2_config.guard_research_budget_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_config
AS $function$
DECLARE
  expected_hash text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('configuration');
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.integrity_build.resourcebudget.v1/1.0',
    NEW.budget_contract - ARRAY[
      'content_hash','created_at','id','schema_name','schema_version'
    ]::text[]
  );
  IF NEW.content_hash IS DISTINCT FROM expected_hash
     OR NEW.budget_contract->>'content_hash' IS DISTINCT FROM expected_hash THEN
    RAISE EXCEPTION 'resource budget content hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.authorized_cost_minor_units <> 0 THEN
    RAISE EXCEPTION 'paid experiment budgets require verifiable owner approval'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.budget_contract->>'fixture_only' = 'true'
     AND NEW.evidence_class <> 'SYNTHETIC_FIXTURE' THEN
    RAISE EXCEPTION 'fixture-only resource budgets require synthetic evidence'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_outcomes_research.guard_experiment_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_config,
  qc2_outcomes_research
AS $function$
DECLARE
  budget_contract jsonb;
  expected_hash text;
  experiment_count integer;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('apexlab');
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.outcomes_research.experiment.v1/1.0',
    NEW.experiment_contract - ARRAY[
      'content_hash','created_at','id','schema_name','schema_version'
    ]::text[]
  );
  IF NEW.content_hash IS DISTINCT FROM expected_hash
     OR NEW.experiment_contract->>'content_hash' IS DISTINCT FROM expected_hash THEN
    RAISE EXCEPTION 'experiment content hash is invalid'
      USING ERRCODE = '23514';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(NEW.budget_id::text, 0)
  );
  SELECT budget.budget_contract
    INTO budget_contract
    FROM qc2_config.research_resource_budget AS budget
    WHERE budget.id = NEW.budget_id
      AND budget.content_hash = NEW.experiment_contract->'budget_ref'->>'content_hash'
    FOR SHARE;
  IF budget_contract IS NULL THEN
    RAISE EXCEPTION 'experiment resource budget reference is missing or stale'
      USING ERRCODE = '23503';
  END IF;
  IF (budget_contract->>'environment_namespace')
       IS DISTINCT FROM NEW.environment_namespace
     OR NEW.created_at::date < (budget_contract->>'effective_from')::date
     OR NEW.experiment_contract->'result_ref' IS DISTINCT FROM 'null'::jsonb
     OR NEW.experiment_contract->'rejection_reason' IS DISTINCT FROM 'null'::jsonb
     OR NEW.experiment_contract->'evaluation_access' <> '[]'::jsonb THEN
    RAISE EXCEPTION 'experiment preregistration does not match its budget or is already evaluated'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.environment_namespace = 'production'
     OR NEW.evidence_class = 'SYNTHETIC_FIXTURE' AND NEW.environment_namespace = 'production' THEN
    RAISE EXCEPTION 'QC2-034 experiment registration is disabled in production'
      USING ERRCODE = '23514';
  END IF;
  SELECT pg_catalog.count(*)::integer
    INTO experiment_count
    FROM qc2_outcomes_research.experiment AS experiment
    WHERE experiment.budget_id = NEW.budget_id;
  IF experiment_count >= (budget_contract->>'max_experiments')::integer THEN
    RAISE EXCEPTION 'experiment count budget is exhausted'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_outcomes_research.guard_trial_event_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_config,
  qc2_outcomes_research
AS $function$
DECLARE
  experiment_row qc2_outcomes_research.experiment%ROWTYPE;
  experiment_budget_id uuid;
  budget_contract jsonb;
  expected_hash text;
  prior_hash text;
  prior_record jsonb;
  prior_recorded_at timestamptz;
  prior_lifecycle_type text;
  prior_lifecycle_id uuid;
  expected_attempt integer;
  prior_elapsed bigint;
  prior_cpu bigint;
  prior_memory bigint;
  prior_artifacts bigint;
  prior_cost bigint;
  budget_cost bigint;
  active_jobs integer;
  actual_overruns jsonb;
  expected_overruns text[] := ARRAY[]::text[];
  supplied_overruns jsonb;
  usage_record jsonb;
  allowed_keys text[] := ARRAY[
    'id','experiment_ref','sequence','event_type','attempt_number',
    'recorded_at','previous_event_hash','usage','budget_overruns',
    'reason','reason_code','checkpoint_ref','resume_from_event_id',
    'result_ref','artifact_refs','artifact_ref','event_hash'
  ];
BEGIN
  PERFORM qc2_control.assert_runtime_authority('apexlab');
  SELECT experiment.budget_id
    INTO experiment_budget_id
    FROM qc2_outcomes_research.experiment AS experiment
    WHERE experiment.id = NEW.experiment_id;
  IF experiment_budget_id IS NULL THEN
    RAISE EXCEPTION 'trial event experiment does not exist'
      USING ERRCODE = '23503';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('budget:' || experiment_budget_id::text, 0)
  );
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('experiment:' || NEW.experiment_id::text, 0)
  );
  SELECT experiment.*
    INTO experiment_row
    FROM qc2_outcomes_research.experiment AS experiment
    WHERE experiment.id = NEW.experiment_id
    FOR UPDATE;
  IF experiment_row.id IS NULL THEN
    RAISE EXCEPTION 'trial event experiment does not exist'
      USING ERRCODE = '23503';
  END IF;
  SELECT budget.budget_contract
    INTO budget_contract
    FROM qc2_config.research_resource_budget AS budget
    WHERE budget.id = experiment_row.budget_id;
  IF budget_contract IS NULL THEN
    RAISE EXCEPTION 'trial event budget no longer resolves'
      USING ERRCODE = '23503';
  END IF;
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.apexlab.experiment-trial-event.v1',
    NEW.event_record - 'event_hash'
  );
  IF NEW.event_hash IS DISTINCT FROM expected_hash
     OR NEW.event_record->>'event_hash' IS DISTINCT FROM expected_hash
     OR NEW.event_record->'experiment_ref'->>'content_hash'
       IS DISTINCT FROM experiment_row.content_hash
     OR (NEW.event_record - allowed_keys) <> '{}'::jsonb THEN
    RAISE EXCEPTION 'trial event hash, reference, or field set is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.sequence_no <> COALESCE((
      SELECT pg_catalog.max(event.sequence_no)
      FROM qc2_outcomes_research.experiment_trial_event AS event
      WHERE event.experiment_id = NEW.experiment_id
    ), 0) + 1 THEN
    RAISE EXCEPTION 'trial event sequence is not contiguous'
      USING ERRCODE = '23514';
  END IF;
  SELECT event.event_hash, event.event_record, event.recorded_at
    INTO prior_hash, prior_record, prior_recorded_at
    FROM qc2_outcomes_research.experiment_trial_event AS event
    WHERE event.experiment_id = NEW.experiment_id
    ORDER BY event.sequence_no DESC
    LIMIT 1;
  IF NEW.previous_event_hash IS DISTINCT FROM prior_hash
     OR NEW.event_record->>'previous_event_hash'
       IS DISTINCT FROM prior_hash THEN
    RAISE EXCEPTION 'trial event hash chain does not continue the prior event'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.experiment_trial_event AS event
    WHERE event.experiment_id = NEW.experiment_id
      AND event.event_type <> 'ARTIFACT_REGISTERED'
  ) THEN
    SELECT event.event_type, event.id
      INTO prior_lifecycle_type, prior_lifecycle_id
      FROM qc2_outcomes_research.experiment_trial_event AS event
      WHERE event.experiment_id = NEW.experiment_id
        AND event.event_type <> 'ARTIFACT_REGISTERED'
      ORDER BY event.sequence_no DESC
      LIMIT 1;
  END IF;
  SELECT (1 + pg_catalog.count(*) FILTER (
      WHERE event.event_type IN ('TRIAL_STARTED','TRIAL_RESUMED')
    ))::integer
    INTO expected_attempt
    FROM qc2_outcomes_research.experiment_trial_event AS event
    WHERE event.experiment_id = NEW.experiment_id;
  IF NEW.event_type = 'TRIAL_STARTED' THEN
    IF prior_lifecycle_type IS NOT NULL OR NEW.attempt_number <> 1 THEN
      RAISE EXCEPTION 'trial start is not a first attempt'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.event_type = 'TRIAL_RESUMED' THEN
    IF prior_lifecycle_type <> 'TRIAL_INTERRUPTED'
       OR NEW.attempt_number <> expected_attempt
       OR NEW.event_record->>'resume_from_event_id'
         IS DISTINCT FROM prior_lifecycle_id::text
       OR NEW.event_record->'checkpoint_ref'
         IS DISTINCT FROM prior_record->'checkpoint_ref' THEN
      RAISE EXCEPTION 'trial resume must continue its latest interruption checkpoint'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.event_type = 'TRIAL_INTERRUPTED' THEN
    IF prior_lifecycle_type NOT IN ('TRIAL_STARTED','TRIAL_RESUMED')
       OR NEW.attempt_number <> expected_attempt
       OR NEW.event_record->'checkpoint_ref'->>'target_schema_name'
         <> 'qc2.integrity_build.ArtifactManifest.v1' THEN
      RAISE EXCEPTION 'interruption requires an active attempt and checkpoint artifact'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.event_type IN ('TRIAL_FAILED','TRIAL_COMPLETED') THEN
    IF prior_lifecycle_type NOT IN ('TRIAL_STARTED','TRIAL_RESUMED')
       OR NEW.attempt_number <> expected_attempt THEN
      RAISE EXCEPTION 'trial terminal event requires an active attempt'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.event_type = 'TRIAL_REJECTED' THEN
    IF prior_lifecycle_type IS NOT NULL
       AND prior_lifecycle_type NOT IN ('TRIAL_STARTED','TRIAL_RESUMED') THEN
      RAISE EXCEPTION 'trial rejection is not valid after a terminal attempt'
        USING ERRCODE = '23514';
    END IF;
    IF NEW.attempt_number <> COALESCE(expected_attempt - 1, 0) THEN
      RAISE EXCEPTION 'trial rejection attempt number is invalid'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.event_type = 'ARTIFACT_REGISTERED' THEN
    IF NEW.attempt_number <> expected_attempt - 1
       OR NEW.event_record->'artifact_ref'->>'target_schema_name'
         <> 'qc2.integrity_build.ArtifactManifest.v1' THEN
      RAISE EXCEPTION 'artifact registration is missing its manifest reference'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  IF NEW.event_type = 'TRIAL_INTERRUPTED'
     AND (
       NEW.event_record->>'reason_code' <> 'WORKER_INTERRUPTED'
       OR pg_catalog.length(pg_catalog.btrim(NEW.event_record->>'reason')) = 0
     ) THEN
    RAISE EXCEPTION 'interruption reason is required'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.event_type IN ('TRIAL_REJECTED','TRIAL_FAILED')
     AND (
       pg_catalog.length(pg_catalog.btrim(NEW.event_record->>'reason')) = 0
       OR pg_catalog.length(pg_catalog.btrim(NEW.event_record->>'reason_code')) = 0
     ) THEN
    RAISE EXCEPTION 'rejection and failure events require a reason and reason code'
      USING ERRCODE = '23514';
  END IF;

  usage_record := NEW.event_record->'usage';
  IF pg_catalog.jsonb_object_length(usage_record) <> 6
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.unnest(ARRAY[
         'elapsed_seconds','cpu_seconds','peak_memory_bytes',
         'artifact_bytes','cost_minor_units'
       ]) AS field_name
       WHERE pg_catalog.jsonb_typeof(usage_record->field_name) <> 'number'
          OR (usage_record->>field_name)::bigint < 0
     )
     OR usage_record->>'currency' <> budget_contract->>'currency' THEN
    RAISE EXCEPTION 'trial resource usage is malformed or uses the wrong currency'
      USING ERRCODE = '23514';
  END IF;
  IF prior_recorded_at > NEW.recorded_at THEN
    RAISE EXCEPTION 'trial event time cannot move backward'
      USING ERRCODE = '23514';
  END IF;

  SELECT
      COALESCE(pg_catalog.sum((event.event_record->'usage'->>'elapsed_seconds')::bigint), 0),
      COALESCE(pg_catalog.sum((event.event_record->'usage'->>'cpu_seconds')::bigint), 0),
      COALESCE(pg_catalog.max((event.event_record->'usage'->>'peak_memory_bytes')::bigint), 0),
      COALESCE(pg_catalog.sum((event.event_record->'usage'->>'artifact_bytes')::bigint), 0),
      COALESCE(pg_catalog.sum((event.event_record->'usage'->>'cost_minor_units')::bigint), 0)
    INTO prior_elapsed, prior_cpu, prior_memory, prior_artifacts, prior_cost
    FROM qc2_outcomes_research.experiment_trial_event AS event
    WHERE event.experiment_id = NEW.experiment_id;
  SELECT COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'cost_minor_units')::bigint
    ), 0)
    INTO budget_cost
    FROM qc2_outcomes_research.experiment AS experiment
    JOIN qc2_outcomes_research.experiment_trial_event AS event
      ON event.experiment_id = experiment.id
    WHERE experiment.budget_id = experiment_row.budget_id;
  IF prior_elapsed + (usage_record->>'elapsed_seconds')::bigint
       > (budget_contract->>'max_elapsed_seconds')::bigint THEN
    expected_overruns := expected_overruns || 'MAX_ELAPSED_SECONDS';
  END IF;
  IF prior_cpu + (usage_record->>'cpu_seconds')::bigint
       > (budget_contract->>'max_cpu_seconds')::bigint THEN
    expected_overruns := expected_overruns || 'MAX_CPU_SECONDS';
  END IF;
  IF pg_catalog.greatest(
       prior_memory,
       (usage_record->>'peak_memory_bytes')::bigint
     ) > (budget_contract->>'max_memory_bytes')::bigint THEN
    expected_overruns := expected_overruns || 'MAX_MEMORY_BYTES';
  END IF;
  IF prior_artifacts + (usage_record->>'artifact_bytes')::bigint
       > (budget_contract->>'max_artifact_bytes')::bigint THEN
    expected_overruns := expected_overruns || 'MAX_ARTIFACT_BYTES';
  END IF;
  IF budget_cost + (usage_record->>'cost_minor_units')::bigint
       > (budget_contract->>'authorized_cost_minor_units')::bigint THEN
    expected_overruns := expected_overruns || 'AUTHORIZED_COST_MINOR_UNITS';
  END IF;
  supplied_overruns := pg_catalog.to_jsonb(expected_overruns);
  IF NEW.event_record->'budget_overruns' IS DISTINCT FROM supplied_overruns THEN
    RAISE EXCEPTION 'trial resource overrun list does not match the budget'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.event_type IN ('TRIAL_STARTED','TRIAL_RESUMED') THEN
    IF prior_elapsed >= (budget_contract->>'max_elapsed_seconds')::bigint
       OR prior_cpu >= (budget_contract->>'max_cpu_seconds')::bigint
       OR prior_artifacts >= (budget_contract->>'max_artifact_bytes')::bigint
       OR prior_memory > (budget_contract->>'max_memory_bytes')::bigint
       OR budget_cost >= (budget_contract->>'authorized_cost_minor_units')::bigint
          AND (budget_contract->>'authorized_cost_minor_units')::bigint > 0 THEN
      RAISE EXCEPTION 'resource budget has no remaining capacity for a trial attempt'
        USING ERRCODE = '23514';
    END IF;
    SELECT pg_catalog.count(*)::integer
      INTO active_jobs
      FROM (
        SELECT DISTINCT ON (event.experiment_id)
          event.experiment_id,
          event.event_type
        FROM qc2_outcomes_research.experiment_trial_event AS event
        JOIN qc2_outcomes_research.experiment AS active_experiment
          ON active_experiment.id = event.experiment_id
        WHERE active_experiment.budget_id = experiment_row.budget_id
          AND event.event_type <> 'ARTIFACT_REGISTERED'
          AND event.experiment_id <> NEW.experiment_id
        ORDER BY event.experiment_id, event.sequence_no DESC
      ) AS latest
      WHERE latest.event_type IN ('TRIAL_STARTED','TRIAL_RESUMED');
    IF active_jobs >= (budget_contract->>'max_concurrent_jobs')::integer THEN
      RAISE EXCEPTION 'concurrent-job budget is exhausted'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_outcomes_research.guard_comparison_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build,
  qc2_outcomes_research
AS $function$
DECLARE
  expected_hash text;
  expected_refs jsonb;
  expected_candidates jsonb;
  expected_dataset jsonb;
  expected_split jsonb;
  experiment_item qc2_outcomes_research.experiment%ROWTYPE;
  member_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('apexlab');
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.apexlab.experiment-comparison.v1',
    NEW.comparison_record - 'registration_hash'
  );
  IF NEW.registration_hash IS DISTINCT FROM expected_hash
     OR NEW.comparison_record->>'registration_hash' IS DISTINCT FROM expected_hash
     OR pg_catalog.cardinality(NEW.experiment_ids) <> (
       SELECT pg_catalog.count(DISTINCT member)::integer
       FROM pg_catalog.unnest(NEW.experiment_ids) AS member
     ) THEN
    RAISE EXCEPTION 'comparison registration hash or members are invalid'
      USING ERRCODE = '23514';
  END IF;
  FOR member_id IN
    SELECT member FROM pg_catalog.unnest(NEW.experiment_ids) AS member
  LOOP
    SELECT experiment.*
      INTO experiment_item
      FROM qc2_outcomes_research.experiment AS experiment
      WHERE experiment.id = member_id
      FOR UPDATE;
    IF experiment_item.id IS NULL THEN
      RAISE EXCEPTION 'comparison references an unregistered experiment'
        USING ERRCODE = '23503';
    END IF;
    IF EXISTS (
      SELECT 1
      FROM qc2_outcomes_research.experiment_trial_event AS event
      WHERE event.experiment_id = member_id
    ) THEN
      RAISE EXCEPTION 'comparison must be registered before trial execution'
        USING ERRCODE = '23514';
    END IF;
    IF expected_dataset IS NULL THEN
      expected_dataset := experiment_item.experiment_contract->'dataset_ref';
      expected_split := experiment_item.experiment_contract->'split_ref';
    ELSIF expected_dataset IS DISTINCT FROM
            experiment_item.experiment_contract->'dataset_ref'
       OR expected_split IS DISTINCT FROM
            experiment_item.experiment_contract->'split_ref' THEN
      RAISE EXCEPTION 'comparison experiments must use the same dataset and split'
        USING ERRCODE = '23514';
    END IF;
  END LOOP;
  SELECT pg_catalog.jsonb_agg(
      pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.Experiment.v1',
        'target_id', experiment.id::text,
        'content_hash', experiment.content_hash
      ) ORDER BY experiment.id
    )
    INTO expected_refs
    FROM qc2_outcomes_research.experiment AS experiment
    WHERE experiment.id = ANY(NEW.experiment_ids);
  SELECT pg_catalog.jsonb_agg(candidate.candidate_ref ORDER BY candidate.target_id)
    INTO expected_candidates
    FROM (
      SELECT DISTINCT ON (candidate_ref->>'target_id')
        candidate_ref,
        candidate_ref->>'target_id' AS target_id
      FROM qc2_outcomes_research.experiment AS experiment
      CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
        experiment.experiment_contract->'candidate_refs'
      ) AS candidate(candidate_ref)
      WHERE experiment.id = ANY(NEW.experiment_ids)
      ORDER BY candidate_ref->>'target_id', candidate_ref->>'content_hash'
    ) AS candidate;
  IF pg_catalog.jsonb_array_length(COALESCE(expected_candidates, '[]'::jsonb)) < 2
     OR NEW.comparison_record->'experiment_refs' IS DISTINCT FROM expected_refs
     OR NEW.comparison_record->'candidate_refs' IS DISTINCT FROM expected_candidates
     OR NEW.comparison_record->'dataset_ref' IS DISTINCT FROM expected_dataset
     OR NEW.comparison_record->'split_ref' IS DISTINCT FROM expected_split THEN
    RAISE EXCEPTION 'comparison record does not match its experiments or candidates'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_outcomes_research.guard_evaluation_access_attempt_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build,
  qc2_outcomes_research
AS $function$
DECLARE
  expected_hash text;
  prior_hash text;
  prior_receipt_id uuid;
  comparison_exists boolean;
  receipt_contract jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      NEW.dataset_id::text || ':' || NEW.dataset_content_hash, 0
    )
  );
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.validation.experiment-access-attempt.v1',
    NEW.access_record - 'event_hash'
  );
  IF NEW.event_hash IS DISTINCT FROM expected_hash
     OR NEW.access_record->>'event_hash' IS DISTINCT FROM expected_hash
     OR NEW.access_record->'experiment_ref'->>'content_hash'
       IS DISTINCT FROM (
         SELECT experiment.content_hash
         FROM qc2_outcomes_research.experiment AS experiment
         WHERE experiment.id = NEW.experiment_id
       ) THEN
    RAISE EXCEPTION 'evaluation access event hash or experiment reference is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.experiment_comparison_registration AS comparison
    WHERE NEW.experiment_id = ANY(comparison.experiment_ids)
  ) THEN
    RAISE EXCEPTION 'evaluation access requires a preregistered comparison'
      USING ERRCODE = '23514';
  END IF;
  SELECT attempt.event_hash, attempt.receipt_id
    INTO prior_hash, prior_receipt_id
    FROM qc2_outcomes_research.experiment_evaluation_access_attempt AS attempt
    WHERE attempt.dataset_id = NEW.dataset_id
      AND attempt.dataset_content_hash = NEW.dataset_content_hash
    ORDER BY attempt.sequence_no DESC
    LIMIT 1;
  IF NEW.sequence_no <> COALESCE((
      SELECT pg_catalog.max(attempt.sequence_no)
      FROM qc2_outcomes_research.experiment_evaluation_access_attempt AS attempt
      WHERE attempt.dataset_id = NEW.dataset_id
        AND attempt.dataset_content_hash = NEW.dataset_content_hash
    ), 0) + 1
     OR NEW.previous_event_hash IS DISTINCT FROM prior_hash
     OR NEW.access_record->>'previous_event_hash' IS DISTINCT FROM prior_hash THEN
    RAISE EXCEPTION 'evaluation access sequence or hash chain is invalid'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.disposition = 'GRANTED' THEN
    IF NEW.receipt_id IS NULL
       OR EXISTS (
         SELECT 1
         FROM qc2_outcomes_research.experiment_evaluation_access_attempt AS attempt
         WHERE attempt.dataset_id = NEW.dataset_id
           AND attempt.dataset_content_hash = NEW.dataset_content_hash
           AND attempt.disposition = 'GRANTED'
       ) THEN
      RAISE EXCEPTION 'holdout dataset can receive only one successful access'
        USING ERRCODE = '23514';
    END IF;
    SELECT receipt.receipt_contract
      INTO receipt_contract
      FROM qc2_outcomes_research.holdout_access_receipt AS receipt
      WHERE receipt.id = NEW.receipt_id
        AND receipt.dataset_id = NEW.dataset_id
        AND receipt.dataset_content_hash = NEW.dataset_content_hash;
    IF receipt_contract IS NULL
       OR (receipt_contract->>'requested_at')::timestamptz
         IS DISTINCT FROM NEW.requested_at THEN
      RAISE EXCEPTION 'evaluation access grant does not match its validation receipt'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.disposition = 'REPEAT_BLOCKED' THEN
    IF prior_receipt_id IS NULL
       OR NEW.receipt_id IS DISTINCT FROM prior_receipt_id
       OR NEW.reason_code IS DISTINCT FROM 'HOLDOUT_ALREADY_CONSUMED' THEN
      RAISE EXCEPTION 'repeat access must retain the consumed receipt and be blocked'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.disposition = 'DENIED' THEN
    IF NEW.receipt_id IS NOT NULL
       OR pg_catalog.length(pg_catalog.btrim(NEW.access_record->>'denial_reason')) = 0 THEN
      RAISE EXCEPTION 'denied evaluation access requires a reason and no receipt'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

CREATE TRIGGER research_budget_content_hash
BEFORE INSERT ON qc2_config.research_resource_budget
FOR EACH ROW EXECUTE FUNCTION qc2_config.guard_research_budget_insert();
CREATE TRIGGER experiment_content_hash_and_budget
BEFORE INSERT ON qc2_outcomes_research.experiment
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.guard_experiment_insert();
CREATE TRIGGER experiment_trial_event_chain_and_budget
BEFORE INSERT ON qc2_outcomes_research.experiment_trial_event
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.guard_trial_event_insert();
CREATE TRIGGER experiment_comparison_preregistration
BEFORE INSERT ON qc2_outcomes_research.experiment_comparison_registration
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.guard_comparison_insert();
CREATE TRIGGER experiment_evaluation_access_authority
BEFORE INSERT ON qc2_outcomes_research.experiment_evaluation_access_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.guard_evaluation_access_attempt_insert();

CREATE TRIGGER research_budget_append_only
BEFORE UPDATE OR DELETE ON qc2_config.research_resource_budget
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation(
  'configuration'
);
CREATE TRIGGER experiment_append_only
BEFORE UPDATE OR DELETE ON qc2_outcomes_research.experiment
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation(
  'apexlab'
);
CREATE TRIGGER experiment_trial_event_append_only
BEFORE UPDATE OR DELETE ON qc2_outcomes_research.experiment_trial_event
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation(
  'apexlab'
);
CREATE TRIGGER experiment_comparison_append_only
BEFORE UPDATE OR DELETE ON qc2_outcomes_research.experiment_comparison_registration
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation(
  'apexlab'
);
CREATE TRIGGER experiment_evaluation_access_append_only
BEFORE UPDATE OR DELETE ON qc2_outcomes_research.experiment_evaluation_access_attempt
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation(
  'validation'
);

ALTER TABLE qc2_config.research_resource_budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_config.research_resource_budget FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_trial_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_trial_event FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_comparison_registration
  ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_comparison_registration
  FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_evaluation_access_attempt
  ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.experiment_evaluation_access_attempt
  FORCE ROW LEVEL SECURITY;

CREATE POLICY research_budget_migrator_all
  ON qc2_config.research_resource_budget FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY research_budget_configuration_read
  ON qc2_config.research_resource_budget FOR SELECT TO qc2_runtime_configuration
  USING (qc2_control.current_runtime_authority() = 'configuration');
CREATE POLICY research_budget_configuration_insert
  ON qc2_config.research_resource_budget FOR INSERT TO qc2_runtime_configuration
  WITH CHECK (qc2_control.current_runtime_authority() = 'configuration');
CREATE POLICY research_budget_apexlab_read
  ON qc2_config.research_resource_budget FOR SELECT TO qc2_runtime_apexlab
  USING (qc2_control.current_runtime_authority() = 'apexlab');

CREATE POLICY experiment_migrator_all
  ON qc2_outcomes_research.experiment FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY experiment_apexlab_read
  ON qc2_outcomes_research.experiment FOR SELECT TO qc2_runtime_apexlab
  USING (qc2_control.current_runtime_authority() = 'apexlab');
CREATE POLICY experiment_apexlab_insert
  ON qc2_outcomes_research.experiment FOR INSERT TO qc2_runtime_apexlab
  WITH CHECK (qc2_control.current_runtime_authority() = 'apexlab');

CREATE POLICY experiment_trial_event_migrator_all
  ON qc2_outcomes_research.experiment_trial_event FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY experiment_trial_event_apexlab_read
  ON qc2_outcomes_research.experiment_trial_event FOR SELECT TO qc2_runtime_apexlab
  USING (qc2_control.current_runtime_authority() = 'apexlab');
CREATE POLICY experiment_trial_event_apexlab_insert
  ON qc2_outcomes_research.experiment_trial_event FOR INSERT TO qc2_runtime_apexlab
  WITH CHECK (qc2_control.current_runtime_authority() = 'apexlab');

CREATE POLICY experiment_comparison_migrator_all
  ON qc2_outcomes_research.experiment_comparison_registration
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY experiment_comparison_apexlab_read
  ON qc2_outcomes_research.experiment_comparison_registration
  FOR SELECT TO qc2_runtime_apexlab
  USING (qc2_control.current_runtime_authority() = 'apexlab');
CREATE POLICY experiment_comparison_apexlab_insert
  ON qc2_outcomes_research.experiment_comparison_registration
  FOR INSERT TO qc2_runtime_apexlab
  WITH CHECK (qc2_control.current_runtime_authority() = 'apexlab');

CREATE POLICY evaluation_access_migrator_all
  ON qc2_outcomes_research.experiment_evaluation_access_attempt
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY evaluation_access_validation_read
  ON qc2_outcomes_research.experiment_evaluation_access_attempt
  FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY evaluation_access_validation_insert
  ON qc2_outcomes_research.experiment_evaluation_access_attempt
  FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');

CREATE VIEW qc2_outcomes_research.experiment_resource_report
WITH (security_barrier = true)
AS
SELECT
  experiment.budget_id,
  experiment.id AS experiment_id,
  budget.currency,
  budget.max_elapsed_seconds,
  budget.max_cpu_seconds,
  budget.max_memory_bytes,
  budget.max_artifact_bytes,
  budget.authorized_cost_minor_units,
  COALESCE(pg_catalog.sum(
    (event.event_record->'usage'->>'elapsed_seconds')::bigint
  ), 0)::bigint AS elapsed_seconds,
  COALESCE(pg_catalog.sum(
    (event.event_record->'usage'->>'cpu_seconds')::bigint
  ), 0)::bigint AS cpu_seconds,
  COALESCE(pg_catalog.max(
    (event.event_record->'usage'->>'peak_memory_bytes')::bigint
  ), 0)::bigint AS peak_memory_bytes,
  COALESCE(pg_catalog.sum(
    (event.event_record->'usage'->>'artifact_bytes')::bigint
  ), 0)::bigint AS artifact_bytes,
  COALESCE(pg_catalog.sum(
    (event.event_record->'usage'->>'cost_minor_units')::bigint
  ), 0)::bigint AS spent_minor_units,
  GREATEST(
    0,
    budget.authorized_cost_minor_units - COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'cost_minor_units')::bigint
    ), 0)
  )::bigint AS remaining_cost_minor_units
FROM qc2_outcomes_research.experiment AS experiment
JOIN qc2_config.research_resource_budget AS budget
  ON budget.id = experiment.budget_id
LEFT JOIN qc2_outcomes_research.experiment_trial_event AS event
  ON event.experiment_id = experiment.id
GROUP BY experiment.budget_id, experiment.id, budget.currency,
  budget.max_elapsed_seconds, budget.max_cpu_seconds, budget.max_memory_bytes,
  budget.max_artifact_bytes, budget.authorized_cost_minor_units;

CREATE VIEW qc2_outcomes_research.experiment_budget_report
WITH (security_barrier = true)
AS
WITH lifecycle AS (
  SELECT DISTINCT ON (experiment.id)
    experiment.id AS experiment_id,
    experiment.budget_id,
    CASE
      WHEN event.event_type IS NULL THEN 'REGISTERED'
      WHEN event.event_type = 'TRIAL_STARTED' OR event.event_type = 'TRIAL_RESUMED'
        THEN 'RUNNING'
      WHEN event.event_type = 'TRIAL_INTERRUPTED' THEN 'INTERRUPTED'
      WHEN event.event_type = 'TRIAL_REJECTED' THEN 'REJECTED'
      WHEN event.event_type = 'TRIAL_FAILED' THEN 'FAILED'
      WHEN event.event_type = 'TRIAL_COMPLETED' THEN 'COMPLETED'
      ELSE 'REGISTERED'
    END AS state
  FROM qc2_outcomes_research.experiment AS experiment
  LEFT JOIN qc2_outcomes_research.experiment_trial_event AS event
    ON event.experiment_id = experiment.id
   AND event.event_type <> 'ARTIFACT_REGISTERED'
  ORDER BY experiment.id, event.sequence_no DESC NULLS LAST
),
usage AS (
  SELECT
    experiment.budget_id,
    COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'elapsed_seconds')::bigint
    ), 0)::bigint AS elapsed_seconds,
    COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'cpu_seconds')::bigint
    ), 0)::bigint AS cpu_seconds,
    COALESCE(pg_catalog.max(
      (event.event_record->'usage'->>'peak_memory_bytes')::bigint
    ), 0)::bigint AS peak_memory_bytes,
    COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'artifact_bytes')::bigint
    ), 0)::bigint AS artifact_bytes,
    COALESCE(pg_catalog.sum(
      (event.event_record->'usage'->>'cost_minor_units')::bigint
    ), 0)::bigint AS spent_minor_units
  FROM qc2_outcomes_research.experiment AS experiment
  LEFT JOIN qc2_outcomes_research.experiment_trial_event AS event
    ON event.experiment_id = experiment.id
  GROUP BY experiment.budget_id
)
SELECT
  budget.id AS budget_id,
  budget.currency,
  budget.max_experiments,
  budget.max_concurrent_jobs,
  budget.max_elapsed_seconds,
  budget.max_cpu_seconds,
  budget.max_memory_bytes,
  budget.max_artifact_bytes,
  budget.authorized_cost_minor_units,
  pg_catalog.count(lifecycle.experiment_id)::integer AS registered_experiments,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'REGISTERED')::integer
    AS registered_trials,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'RUNNING')::integer
    AS running_trials,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'INTERRUPTED')::integer
    AS interrupted_trials,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'REJECTED')::integer
    AS rejected_trials,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'FAILED')::integer
    AS failed_trials,
  pg_catalog.count(*) FILTER (WHERE lifecycle.state = 'COMPLETED')::integer
    AS completed_trials,
  COALESCE(usage.elapsed_seconds, 0)::bigint AS elapsed_seconds,
  COALESCE(usage.cpu_seconds, 0)::bigint AS cpu_seconds,
  COALESCE(usage.peak_memory_bytes, 0)::bigint AS peak_memory_bytes,
  COALESCE(usage.artifact_bytes, 0)::bigint AS artifact_bytes,
  COALESCE(usage.spent_minor_units, 0)::bigint AS spent_minor_units,
  GREATEST(
    0,
    budget.authorized_cost_minor_units - COALESCE(usage.spent_minor_units, 0)
  )::bigint AS remaining_cost_minor_units
FROM qc2_config.research_resource_budget AS budget
LEFT JOIN lifecycle ON lifecycle.budget_id = budget.id
LEFT JOIN usage ON usage.budget_id = budget.id
GROUP BY budget.id, budget.currency, budget.max_experiments,
  budget.max_concurrent_jobs, budget.max_elapsed_seconds,
  budget.max_cpu_seconds, budget.max_memory_bytes, budget.max_artifact_bytes,
  budget.authorized_cost_minor_units, usage.elapsed_seconds, usage.cpu_seconds,
  usage.peak_memory_bytes, usage.artifact_bytes, usage.spent_minor_units;

CREATE VIEW qc2_outcomes_research.holdout_consumption_state
WITH (security_barrier = true)
AS
SELECT
  attempt.dataset_id,
  attempt.dataset_content_hash,
  CASE
    WHEN pg_catalog.bool_or(attempt.disposition = 'REPEAT_BLOCKED')
      THEN 'REPEATED_ACCESS'
    WHEN pg_catalog.bool_or(attempt.disposition = 'GRANTED')
      THEN 'CONSUMED'
    ELSE 'NOT_CONSUMED'
  END AS consumption_state,
  pg_catalog.count(*)::integer AS access_attempt_count,
  (pg_catalog.array_agg(attempt.receipt_id ORDER BY attempt.sequence_no)
    FILTER (WHERE attempt.disposition = 'GRANTED'))[1] AS successful_receipt_id
FROM qc2_outcomes_research.experiment_evaluation_access_attempt AS attempt
GROUP BY attempt.dataset_id, attempt.dataset_content_hash;

ALTER TABLE qc2_config.research_resource_budget OWNER TO qc2_migrator;
ALTER TABLE qc2_outcomes_research.experiment OWNER TO qc2_migrator;
ALTER TABLE qc2_outcomes_research.experiment_trial_event OWNER TO qc2_migrator;
ALTER TABLE qc2_outcomes_research.experiment_comparison_registration
  OWNER TO qc2_migrator;
ALTER TABLE qc2_outcomes_research.experiment_evaluation_access_attempt
  OWNER TO qc2_migrator;

REVOKE ALL ON
  qc2_config.research_resource_budget,
  qc2_outcomes_research.experiment,
  qc2_outcomes_research.experiment_trial_event,
  qc2_outcomes_research.experiment_comparison_registration,
  qc2_outcomes_research.experiment_evaluation_access_attempt
FROM PUBLIC;
REVOKE ALL ON
  qc2_outcomes_research.experiment_resource_report,
  qc2_outcomes_research.experiment_budget_report,
  qc2_outcomes_research.holdout_consumption_state
FROM PUBLIC;

GRANT SELECT, INSERT ON qc2_config.research_resource_budget
  TO qc2_runtime_configuration;
GRANT SELECT ON qc2_config.research_resource_budget TO qc2_runtime_apexlab;
GRANT SELECT, INSERT ON
  qc2_outcomes_research.experiment,
  qc2_outcomes_research.experiment_trial_event,
  qc2_outcomes_research.experiment_comparison_registration
TO qc2_runtime_apexlab;
GRANT SELECT ON
  qc2_outcomes_research.experiment_resource_report,
  qc2_outcomes_research.experiment_budget_report,
  qc2_outcomes_research.holdout_consumption_state
TO qc2_runtime_apexlab;
GRANT SELECT, INSERT ON
  qc2_outcomes_research.experiment_evaluation_access_attempt
TO qc2_runtime_validation;

GRANT EXECUTE ON FUNCTION qc2_config.guard_research_budget_insert()
  TO qc2_runtime_configuration;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.guard_experiment_insert()
  TO qc2_runtime_apexlab;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.guard_trial_event_insert()
  TO qc2_runtime_apexlab;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.guard_comparison_insert()
  TO qc2_runtime_apexlab;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.guard_evaluation_access_attempt_insert()
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.prevent_experiment_ledger_mutation()
  TO qc2_runtime_configuration, qc2_runtime_apexlab, qc2_runtime_validation;

RESET ROLE;
