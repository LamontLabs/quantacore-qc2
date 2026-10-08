\set ON_ERROR_STOP on

DO $check_environment$
BEGIN
  IF current_setting('server_encoding') <> 'UTF8' THEN
    RAISE EXCEPTION 'QC2-034 acceptance requires a UTF8 database';
  END IF;
END
$check_environment$;

CREATE SCHEMA qc2_034_fixture AUTHORIZATION postgres;
CREATE TABLE qc2_034_fixture.contract_fixture (
  fixture_key text PRIMARY KEY,
  id uuid NOT NULL,
  content_hash text NOT NULL,
  contract jsonb NOT NULL
);
GRANT USAGE ON SCHEMA qc2_034_fixture
  TO qc2_runtime_configuration, qc2_runtime_apexlab, qc2_runtime_validation;
GRANT SELECT ON qc2_034_fixture.contract_fixture
  TO qc2_runtime_configuration, qc2_runtime_apexlab, qc2_runtime_validation;

WITH raw AS (
  SELECT
    'budget'::text AS fixture_key,
    '018f0000-0000-7000-8000-000000000001'::uuid AS id,
    jsonb_build_object(
      'schema_name', 'qc2.integrity_build.ResourceBudget.v1',
      'schema_version', '1.0',
      'id', '018f0000-0000-7000-8000-000000000001',
      'created_at', '2026-10-08T12:00:00Z',
      'owning_authority', 'configuration',
      'evidence_class', 'SYNTHETIC_FIXTURE',
      'environment_namespace', 'test',
      'source_refs', '[]'::jsonb,
      'budget_key', 'qc2-034-acceptance',
      'configuration_domain', 'RESEARCH',
      'version', 1,
      'max_experiments', 3,
      'max_concurrent_jobs', 1,
      'max_elapsed_seconds', 120,
      'max_cpu_seconds', 120,
      'max_memory_bytes', 4096,
      'max_artifact_bytes', 2048,
      'authorized_cost_minor_units', 0,
      'currency', 'USD',
      'owner_approval_ref', 'null'::jsonb,
      'effective_from', '2026-10-08',
      'fixture_only', true,
      'content_hash', pg_catalog.repeat('0', 64)
    ) AS contract
),
sealed AS (
  SELECT
    fixture_key,
    id,
    qc2_integrity_build.hash_json(
      'qc2.contract-content.v1/qc2.integrity_build.resourcebudget.v1/1.0',
      contract - ARRAY[
        'content_hash','created_at','id','schema_name','schema_version'
      ]::text[]
    ) AS digest,
    contract
  FROM raw
)
INSERT INTO qc2_034_fixture.contract_fixture(fixture_key, id, content_hash, contract)
SELECT
  fixture_key,
  id,
  digest,
  pg_catalog.jsonb_set(contract, '{content_hash}', pg_catalog.to_jsonb(digest), true)
FROM sealed;

WITH budget AS (
  SELECT id, content_hash
  FROM qc2_034_fixture.contract_fixture
  WHERE fixture_key = 'budget'
),
experiment_input(fixture_key, experiment_id, candidate_id, created_at) AS (
  VALUES
    (
      'experiment-rejected',
      '018f0000-0000-7000-8000-000000000011'::uuid,
      '018f0000-0000-7000-8000-000000000031'::uuid,
      '2026-10-08T12:01:00Z'
    ),
    (
      'experiment-interrupted',
      '018f0000-0000-7000-8000-000000000012'::uuid,
      '018f0000-0000-7000-8000-000000000032'::uuid,
      '2026-10-08T12:01:01Z'
    ),
    (
      'experiment-registered',
      '018f0000-0000-7000-8000-000000000013'::uuid,
      '018f0000-0000-7000-8000-000000000033'::uuid,
      '2026-10-08T12:01:02Z'
    ),
    (
      'experiment-over-limit',
      '018f0000-0000-7000-8000-000000000014'::uuid,
      '018f0000-0000-7000-8000-000000000034'::uuid,
      '2026-10-08T12:01:03Z'
    )
),
raw AS (
  SELECT
    input.fixture_key,
    input.experiment_id AS id,
    jsonb_build_object(
      'schema_name', 'qc2.outcomes_research.Experiment.v1',
      'schema_version', '1.0',
      'id', input.experiment_id::text,
      'created_at', input.created_at,
      'owning_authority', 'apexlab',
      'evidence_class', 'SYNTHETIC_FIXTURE',
      'environment_namespace', 'test',
      'source_refs', '[]'::jsonb,
      'hypothesis', 'QC2-034 isolated acceptance fixture',
      'search_space_hash', pg_catalog.repeat('a', 64),
      'code_hash', pg_catalog.repeat('b', 64),
      'environment_fingerprint', pg_catalog.repeat('c', 64),
      'dataset_ref', jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.DatasetManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000010',
        'content_hash', pg_catalog.repeat('d', 64)
      ),
      'split_ref', jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.SplitManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000020',
        'content_hash', pg_catalog.repeat('e', 64)
      ),
      'candidate_refs', jsonb_build_array(jsonb_build_object(
        'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
        'target_id', input.candidate_id::text,
        'content_hash', pg_catalog.repeat('f', 64)
      )),
      'algorithm', 'fixture_model',
      'seed', 17,
      'configuration_ref', jsonb_build_object(
        'target_schema_name', 'qc2.integrity_build.ConfigurationManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000040',
        'content_hash', pg_catalog.repeat('1', 64)
      ),
      'budget_ref', jsonb_build_object(
        'target_schema_name', 'qc2.integrity_build.ResourceBudget.v1',
        'target_id', budget.id::text,
        'content_hash', budget.content_hash
      ),
      'compute_cost', '0',
      'evaluation_access', '[]'::jsonb,
      'result_ref', 'null'::jsonb,
      'rejection_reason', 'null'::jsonb,
      'artifact_refs', '[]'::jsonb,
      'content_hash', pg_catalog.repeat('0', 64)
    ) AS contract
  FROM experiment_input AS input
  CROSS JOIN budget
),
sealed AS (
  SELECT
    fixture_key,
    id,
    qc2_integrity_build.hash_json(
      'qc2.contract-content.v1/qc2.outcomes_research.experiment.v1/1.0',
      contract - ARRAY[
        'content_hash','created_at','id','schema_name','schema_version'
      ]::text[]
    ) AS digest,
    contract
  FROM raw
)
INSERT INTO qc2_034_fixture.contract_fixture(fixture_key, id, content_hash, contract)
SELECT
  fixture_key,
  id,
  digest,
  pg_catalog.jsonb_set(contract, '{content_hash}', pg_catalog.to_jsonb(digest), true)
FROM sealed;

WITH members AS (
  SELECT
    pg_catalog.array_agg(fixture.id ORDER BY fixture.id) AS experiment_ids,
    pg_catalog.jsonb_agg(
      jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.Experiment.v1',
        'target_id', fixture.id::text,
        'content_hash', fixture.content_hash
      ) ORDER BY fixture.id
    ) AS experiment_refs,
    pg_catalog.jsonb_agg(candidate.candidate_ref
      ORDER BY candidate.candidate_ref->>'target_id'
    ) AS candidate_refs
  FROM qc2_034_fixture.contract_fixture AS fixture
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
    fixture.contract->'candidate_refs'
  ) AS candidate(candidate_ref)
  WHERE fixture.fixture_key IN ('experiment-rejected', 'experiment-interrupted')
),
comparison_base AS (
  SELECT
    '018f0000-0000-7000-8000-000000000100'::uuid AS id,
    '2026-10-08T12:02:00Z'::text AS registered_at,
    jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.DatasetManifest.v1',
      'target_id', '018f0000-0000-7000-8000-000000000010',
      'content_hash', pg_catalog.repeat('d', 64)
    ) AS dataset_ref,
    jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.SplitManifest.v1',
      'target_id', '018f0000-0000-7000-8000-000000000020',
      'content_hash', pg_catalog.repeat('e', 64)
    ) AS split_ref
),
comparison_payload AS (
  SELECT
    base.id,
    members.experiment_ids,
    base.registered_at::timestamptz AS registered_at,
    jsonb_build_object(
      'id', base.id::text,
      'registered_at', base.registered_at,
      'experiment_refs', members.experiment_refs,
      'dataset_ref', base.dataset_ref,
      'split_ref', base.split_ref,
      'candidate_refs', members.candidate_refs
    ) AS body
  FROM comparison_base AS base
  CROSS JOIN members
),
sealed AS (
  SELECT
    id,
    experiment_ids,
    registered_at,
    qc2_integrity_build.hash_json(
      'qc2.apexlab.experiment-comparison.v1',
      body
    ) AS digest,
    body
  FROM comparison_payload
)
INSERT INTO qc2_034_fixture.contract_fixture(fixture_key, id, content_hash, contract)
SELECT
  'comparison',
  id,
  digest,
  body || jsonb_build_object('registration_hash', digest)
FROM sealed;

CREATE FUNCTION qc2_034_fixture.insert_trial_event(
  p_experiment_id uuid,
  p_event_id uuid,
  p_sequence integer,
  p_event_type text,
  p_attempt_number integer,
  p_recorded_at timestamptz,
  p_previous_event_id uuid,
  p_usage jsonb,
  p_budget_overruns jsonb,
  p_extra jsonb
)
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
  experiment_hash text;
  previous_hash text;
  body jsonb;
  digest text;
BEGIN
  SELECT experiment.content_hash
    INTO experiment_hash
    FROM qc2_outcomes_research.experiment AS experiment
    WHERE experiment.id = p_experiment_id;
  IF p_previous_event_id IS NOT NULL THEN
    SELECT event.event_hash
      INTO previous_hash
      FROM qc2_outcomes_research.experiment_trial_event AS event
      WHERE event.id = p_previous_event_id;
  END IF;
  body := jsonb_build_object(
    'id', p_event_id::text,
    'experiment_ref', jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.Experiment.v1',
      'target_id', p_experiment_id::text,
      'content_hash', experiment_hash
    ),
    'sequence', p_sequence,
    'event_type', p_event_type,
    'attempt_number', p_attempt_number,
    'recorded_at', p_recorded_at,
    'previous_event_hash', previous_hash,
    'usage', p_usage,
    'budget_overruns', p_budget_overruns
  ) || p_extra;
  digest := qc2_integrity_build.hash_json(
    'qc2.apexlab.experiment-trial-event.v1', body
  );
  INSERT INTO qc2_outcomes_research.experiment_trial_event(
    id, experiment_id, sequence_no, event_type, attempt_number, recorded_at,
    previous_event_hash, event_hash, event_record
  )
  VALUES (
    p_event_id,
    p_experiment_id,
    p_sequence,
    p_event_type,
    p_attempt_number,
    p_recorded_at,
    previous_hash,
    digest,
    body || jsonb_build_object('event_hash', digest)
  );
END
$function$;
GRANT EXECUTE ON FUNCTION qc2_034_fixture.insert_trial_event(
  uuid, uuid, integer, text, integer, timestamptz, uuid, jsonb, jsonb, jsonb
) TO qc2_runtime_apexlab;

SET SESSION AUTHORIZATION qc2_runtime_configuration;
INSERT INTO qc2_integrity_build.research_resource_budget(
  id, budget_key, version, environment_namespace, evidence_class, currency,
  max_experiments, max_concurrent_jobs, max_elapsed_seconds, max_cpu_seconds,
  max_memory_bytes, max_artifact_bytes, authorized_cost_minor_units,
  effective_from, content_hash, budget_contract
)
SELECT
  (contract->>'id')::uuid,
  contract->>'budget_key',
  (contract->>'version')::integer,
  contract->>'environment_namespace',
  contract->>'evidence_class',
  contract->>'currency',
  (contract->>'max_experiments')::integer,
  (contract->>'max_concurrent_jobs')::integer,
  (contract->>'max_elapsed_seconds')::bigint,
  (contract->>'max_cpu_seconds')::bigint,
  (contract->>'max_memory_bytes')::bigint,
  (contract->>'max_artifact_bytes')::bigint,
  (contract->>'authorized_cost_minor_units')::bigint,
  (contract->>'effective_from')::date,
  content_hash,
  contract
FROM qc2_034_fixture.contract_fixture
WHERE fixture_key = 'budget';
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_apexlab;
DO $register_experiments$
DECLARE
  experiment_fixture record;
  budget_id uuid := '018f0000-0000-7000-8000-000000000001';
  blocked boolean := false;
BEGIN
  IF qc2_control.current_runtime_authority() <> 'apexlab' THEN
    RAISE EXCEPTION 'test is not running as the authenticated ApexLab role';
  END IF;
  FOR experiment_fixture IN
    SELECT * FROM qc2_034_fixture.contract_fixture
    WHERE fixture_key IN (
      'experiment-rejected','experiment-interrupted','experiment-registered'
    )
    ORDER BY id
  LOOP
    INSERT INTO qc2_outcomes_research.experiment(
      id, budget_id, content_hash, environment_namespace,
      evidence_class, created_at, experiment_contract
    )
    VALUES (
      experiment_fixture.id,
      budget_id,
      experiment_fixture.content_hash,
      experiment_fixture.contract->>'environment_namespace',
      experiment_fixture.contract->>'evidence_class',
      (experiment_fixture.contract->>'created_at')::timestamptz,
      experiment_fixture.contract
    );
  END LOOP;

  BEGIN
    SELECT * INTO experiment_fixture
    FROM qc2_034_fixture.contract_fixture
    WHERE fixture_key = 'experiment-over-limit';
    INSERT INTO qc2_outcomes_research.experiment(
      id, budget_id, content_hash, environment_namespace,
      evidence_class, created_at, experiment_contract
    )
    VALUES (
      experiment_fixture.id,
      budget_id,
      experiment_fixture.content_hash,
      experiment_fixture.contract->>'environment_namespace',
      experiment_fixture.contract->>'evidence_class',
      (experiment_fixture.contract->>'created_at')::timestamptz,
      experiment_fixture.contract
    );
  EXCEPTION WHEN check_violation THEN
    blocked := true;
  END;
  IF NOT blocked THEN
    RAISE EXCEPTION 'experiment registration exceeded max_experiments';
  END IF;

  INSERT INTO qc2_outcomes_research.experiment_comparison_registration(
    id, experiment_ids, registered_at, registration_hash, comparison_record
  )
  SELECT
    fixture.id,
    ARRAY[
      '018f0000-0000-7000-8000-000000000011'::uuid,
      '018f0000-0000-7000-8000-000000000012'::uuid
    ],
    (fixture.contract->>'registered_at')::timestamptz,
    fixture.content_hash,
    fixture.contract
  FROM qc2_034_fixture.contract_fixture AS fixture
  WHERE fixture.fixture_key = 'comparison';

  PERFORM qc2_034_fixture.insert_trial_event(
    '018f0000-0000-7000-8000-000000000011',
    '018f0000-0000-7000-8000-000000000201',
    1,
    'TRIAL_REJECTED',
    0,
    '2026-10-08T12:03:00Z',
    NULL,
    jsonb_build_object(
      'elapsed_seconds', 3, 'cpu_seconds', 2, 'peak_memory_bytes', 0,
      'artifact_bytes', 0, 'cost_minor_units', 0, 'currency', 'USD'
    ),
    '[]'::jsonb,
    jsonb_build_object(
      'reason', 'fixture candidate failed compatibility checks',
      'reason_code', 'COMPATIBILITY_REJECTED'
    )
  );

  PERFORM qc2_034_fixture.insert_trial_event(
    '018f0000-0000-7000-8000-000000000012',
    '018f0000-0000-7000-8000-000000000202',
    1,
    'TRIAL_STARTED',
    1,
    '2026-10-08T12:03:01Z',
    NULL,
    jsonb_build_object(
      'elapsed_seconds', 0, 'cpu_seconds', 0, 'peak_memory_bytes', 0,
      'artifact_bytes', 0, 'cost_minor_units', 0, 'currency', 'USD'
    ),
    '[]'::jsonb,
    '{}'::jsonb
  );

  PERFORM qc2_034_fixture.insert_trial_event(
    '018f0000-0000-7000-8000-000000000012',
    '018f0000-0000-7000-8000-000000000203',
    2,
    'TRIAL_INTERRUPTED',
    1,
    '2026-10-08T12:03:10Z',
    '018f0000-0000-7000-8000-000000000202',
    jsonb_build_object(
      'elapsed_seconds', 9, 'cpu_seconds', 6, 'peak_memory_bytes', 512,
      'artifact_bytes', 64, 'cost_minor_units', 0, 'currency', 'USD'
    ),
    '[]'::jsonb,
    jsonb_build_object(
      'reason', 'fixture worker interruption',
      'reason_code', 'WORKER_INTERRUPTED',
      'checkpoint_ref', jsonb_build_object(
        'target_schema_name', 'qc2.integrity_build.ArtifactManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000050',
        'content_hash', pg_catalog.repeat('9', 64)
      )
    )
  );

  PERFORM qc2_034_fixture.insert_trial_event(
    '018f0000-0000-7000-8000-000000000012',
    '018f0000-0000-7000-8000-000000000204',
    3,
    'TRIAL_RESUMED',
    2,
    '2026-10-08T12:04:00Z',
    '018f0000-0000-7000-8000-000000000203',
    jsonb_build_object(
      'elapsed_seconds', 0, 'cpu_seconds', 0, 'peak_memory_bytes', 0,
      'artifact_bytes', 0, 'cost_minor_units', 0, 'currency', 'USD'
    ),
    '[]'::jsonb,
    jsonb_build_object(
      'resume_from_event_id', '018f0000-0000-7000-8000-000000000203',
      'checkpoint_ref', jsonb_build_object(
        'target_schema_name', 'qc2.integrity_build.ArtifactManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000050',
        'content_hash', pg_catalog.repeat('9', 64)
      )
    )
  );
END
$register_experiments$;
SET SESSION AUTHORIZATION qc2_runtime_validation;
DO $record_denied_access$
DECLARE
  experiment_hash text;
  previous_hash text;
  body jsonb;
  digest text;
  attempt_no integer;
  attempt_id uuid;
BEGIN
  IF qc2_control.current_runtime_authority() <> 'validation' THEN
    RAISE EXCEPTION 'test is not running as the authenticated validation role';
  END IF;
  SELECT content_hash INTO experiment_hash
  FROM qc2_034_fixture.contract_fixture
  WHERE fixture_key = 'experiment-rejected';
  FOR attempt_no IN 1..2 LOOP
    attempt_id := CASE attempt_no
      WHEN 1 THEN '018f0000-0000-7000-8000-000000000301'::uuid
      ELSE '018f0000-0000-7000-8000-000000000302'::uuid
    END;
    body := jsonb_build_object(
      'id', attempt_id::text,
      'experiment_ref', jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.Experiment.v1',
        'target_id', '018f0000-0000-7000-8000-000000000011',
        'content_hash', experiment_hash
      ),
      'dataset_ref', jsonb_build_object(
        'target_schema_name', 'qc2.outcomes_research.DatasetManifest.v1',
        'target_id', '018f0000-0000-7000-8000-000000000010',
        'content_hash', pg_catalog.repeat('d', 64)
      ),
      'sequence', attempt_no,
      'disposition', 'DENIED',
      'requested_at', CASE attempt_no
        WHEN 1 THEN '2026-10-08T12:04:00Z'
        ELSE '2026-10-08T12:05:00Z'
      END,
      'reason_code', 'ACCESS_REFUSED',
      'denial_reason', 'fixture has no qualifying validation receipt',
      'receipt_ref', 'null'::jsonb,
      'presented_receipt_id', 'null'::jsonb,
      'previous_event_hash', previous_hash
    );
    digest := qc2_integrity_build.hash_json(
      'qc2.validation.experiment-access-attempt.v1', body
    );
    INSERT INTO qc2_outcomes_research.experiment_evaluation_access_attempt(
      id, experiment_id, dataset_id, dataset_content_hash, sequence_no,
      disposition, requested_at, reason_code, receipt_id,
      previous_event_hash, event_hash, access_record
    )
    VALUES (
      attempt_id,
      '018f0000-0000-7000-8000-000000000011',
      '018f0000-0000-7000-8000-000000000010',
      pg_catalog.repeat('d', 64),
      attempt_no,
      'DENIED',
      (body->>'requested_at')::timestamptz,
      'ACCESS_REFUSED',
      NULL,
      previous_hash,
      digest,
      body || jsonb_build_object('event_hash', digest)
    );
    previous_hash := digest;
  END LOOP;
END
$record_denied_access$;
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_apexlab;
DO $hostile_trainer_checks$
DECLARE
  blocked boolean;
BEGIN
  IF qc2_control.current_runtime_authority() <> 'apexlab' THEN
    RAISE EXCEPTION 'trainer mutation checks lack authenticated ApexLab authority';
  END IF;
  blocked := false;
  BEGIN
    DELETE FROM qc2_outcomes_research.experiment_trial_event
    WHERE id = '018f0000-0000-7000-8000-000000000201';
  EXCEPTION WHEN insufficient_privilege THEN
    blocked := true;
  END;
  IF NOT blocked THEN
    RAISE EXCEPTION 'trainer role deleted an unfavorable trial event';
  END IF;

  blocked := false;
  BEGIN
    UPDATE qc2_outcomes_research.holdout_access_receipt
    SET receipt_hash = receipt_hash
    WHERE id = '018f0000-0000-7000-8000-000000000399';
  EXCEPTION WHEN insufficient_privilege THEN
    blocked := true;
  END;
  IF NOT blocked THEN
    RAISE EXCEPTION 'trainer role altered a validation-owned receipt';
  END IF;

  blocked := false;
  BEGIN
    DELETE FROM qc2_outcomes_research.holdout_access_receipt
    WHERE id = '018f0000-0000-7000-8000-000000000399';
  EXCEPTION WHEN insufficient_privilege THEN
    blocked := true;
  END;
  IF NOT blocked THEN
    RAISE EXCEPTION 'trainer role deleted a validation-owned receipt';
  END IF;

  IF (SELECT pg_catalog.count(*)
      FROM qc2_outcomes_research.experiment_trial_event
      WHERE experiment_id = '018f0000-0000-7000-8000-000000000011') <> 1 THEN
    RAISE EXCEPTION 'unfavorable trial event did not remain persisted';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.holdout_consumption_state
    WHERE dataset_id = '018f0000-0000-7000-8000-000000000010'
      AND dataset_content_hash = pg_catalog.repeat('d', 64)
      AND consumption_state = 'NOT_CONSUMED'
      AND access_attempt_count = 2
  ) THEN
    RAISE EXCEPTION 'denied access attempts changed holdout consumption state';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.experiment_budget_report
    WHERE budget_id = '018f0000-0000-7000-8000-000000000001'
      AND registered_experiments = 3
      AND rejected_trials = 1
      AND interrupted_trials = 0
      AND running_trials = 1
      AND registered_trials = 1
      AND elapsed_seconds = 12
      AND cpu_seconds = 8
  ) THEN
    RAISE EXCEPTION 'budget report omitted retained trial usage or resume state';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.experiment_trial_event
    WHERE id = '018f0000-0000-7000-8000-000000000203'
      AND event_type = 'TRIAL_INTERRUPTED'
  ) OR NOT EXISTS (
    SELECT 1
    FROM qc2_outcomes_research.experiment_trial_event
    WHERE id = '018f0000-0000-7000-8000-000000000204'
      AND event_type = 'TRIAL_RESUMED'
      AND attempt_number = 2
  ) THEN
    RAISE EXCEPTION 'interruption checkpoint or resumed event was not retained';
  END IF;
END
$hostile_trainer_checks$;
RESET SESSION AUTHORIZATION;

SELECT 'QC2-034 PostgreSQL acceptance passed' AS result;
