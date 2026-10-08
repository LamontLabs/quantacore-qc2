SET LOCAL row_security = on;

DO $isolation_check$
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'serializable' THEN
    RAISE EXCEPTION 'QC2-025 PostgreSQL acceptance must run at SERIALIZABLE isolation';
  END IF;
END
$isolation_check$;

DO $prediction_table_guards$
DECLARE
  guarded_count integer;
BEGIN
  SELECT pg_catalog.count(*)::integer
    INTO guarded_count
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'qc2_models_prediction'
      AND relation.relname IN (
        'scheduled_attempt',
        'prediction_run',
        'prediction_attempt',
        'prediction_row',
        'prediction_seal'
      )
      AND relation.relrowsecurity
      AND relation.relforcerowsecurity;
  IF guarded_count <> 5 THEN
    RAISE EXCEPTION 'QC2-025 prediction tables must all force row-level security';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_indexes
    WHERE schemaname = 'qc2_models_prediction'
      AND indexname = 'prediction_one_official_operating_seal'
      AND indexdef ILIKE '%UNIQUE%'
      AND indexdef ILIKE '%role = ''OPERATING''%'
  ) THEN
    RAISE EXCEPTION 'QC2-025 must enforce one official operating seal per epoch/session';
  END IF;

  IF NOT pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_models_prediction.scheduled_attempt',
       'INSERT'
     )
     OR NOT pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_models_prediction.scheduled_attempt',
       'UPDATE'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_prediction',
       'qc2_models_prediction.scheduled_attempt',
       'INSERT'
     ) THEN
    RAISE EXCEPTION 'Scheduled-attempt writes must stay in validation authority';
  END IF;
END
$prediction_table_guards$;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_validation;
INSERT INTO qc2_models_prediction.scheduled_attempt (
  id,
  epoch_id,
  session_id,
  schedule_created_at,
  expected_deadline,
  attempt_state,
  attempt_contract
)
VALUES (
  '018f0000-0000-7000-8000-000000000101',
  '018f0000-0000-7000-8000-000000000001',
  '2026-10-08',
  '2026-10-08T18:59:00Z',
  '2026-10-08T19:00:00Z',
  'SCHEDULED',
  pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.validation.ScheduledAttempt.v1',
    'schema_version', '1.0',
    'id', '018f0000-0000-7000-8000-000000000101',
    'created_at', '2026-10-08T18:59:00Z',
    'owning_authority', 'validation',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'epoch_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
      'target_id', '018f0000-0000-7000-8000-000000000001',
      'content_hash', pg_catalog.repeat('a', 64)
    ),
    'session_id', '2026-10-08',
    'schedule_created_at', '2026-10-08T18:59:00Z',
    'expected_deadline', '2026-10-08T19:00:00Z',
    'attempt_state', 'SCHEDULED',
    'run_ref', NULL,
    'missed_reason', NULL
  )
);
UPDATE qc2_models_prediction.scheduled_attempt
  SET attempt_state = 'MISSED_START',
      missed_reason = 'scheduled_start_not_observed',
      attempt_contract = pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
          attempt_contract,
          '{attempt_state}',
          '"MISSED_START"'::jsonb
        ),
        '{missed_reason}',
        '"scheduled_start_not_observed"'::jsonb
      )
  WHERE id = '018f0000-0000-7000-8000-000000000101';
RESET SESSION AUTHORIZATION;

DO $missed_start_check$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_models_prediction.scheduled_attempt
    WHERE id = '018f0000-0000-7000-8000-000000000101'
      AND attempt_state = 'MISSED_START'
      AND missed_reason = 'scheduled_start_not_observed'
      AND run_id IS NULL
  ) THEN
    RAISE EXCEPTION 'Validation authority could not reconcile a missed scheduled start';
  END IF;
END
$missed_start_check$;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_validation;
INSERT INTO qc2_models_prediction.scheduled_attempt (
  id,
  epoch_id,
  session_id,
  schedule_created_at,
  expected_deadline,
  attempt_state,
  attempt_contract
)
VALUES (
  '018f0000-0000-7000-8000-000000000102',
  '018f0000-0000-7000-8000-000000000001',
  '2026-10-09',
  '2026-10-08T18:59:00Z',
  '2026-10-08T19:00:00Z',
  'SCHEDULED',
  pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.validation.ScheduledAttempt.v1',
    'schema_version', '1.0',
    'id', '018f0000-0000-7000-8000-000000000102',
    'created_at', '2026-10-08T18:59:00Z',
    'owning_authority', 'validation',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'epoch_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
      'target_id', '018f0000-0000-7000-8000-000000000001',
      'content_hash', pg_catalog.repeat('a', 64)
    ),
    'session_id', '2026-10-09',
    'schedule_created_at', '2026-10-08T18:59:00Z',
    'expected_deadline', '2026-10-08T19:00:00Z',
    'attempt_state', 'SCHEDULED',
    'run_ref', NULL,
    'missed_reason', NULL
  )
);
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_prediction;
DO $validation_role_boundary$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    UPDATE qc2_models_prediction.scheduled_attempt
      SET attempt_state = 'MISSED_START',
          missed_reason = 'prediction_must_not_reconcile',
          attempt_contract = pg_catalog.jsonb_set(
            pg_catalog.jsonb_set(
              attempt_contract,
              '{attempt_state}',
              '"MISSED_START"'::jsonb
            ),
            '{missed_reason}',
            '"prediction_must_not_reconcile"'::jsonb
          )
      WHERE id = '018f0000-0000-7000-8000-000000000102';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Prediction authority reconciled a validation-owned missed start';
  END IF;

  denied := false;
  BEGIN
    INSERT INTO qc2_models_prediction.scheduled_attempt (
      id, epoch_id, session_id, schedule_created_at, expected_deadline,
      attempt_state, attempt_contract
    )
    SELECT
      '018f0000-0000-7000-8000-000000000103',
      epoch_id,
      '2026-10-10',
      schedule_created_at,
      expected_deadline,
      'SCHEDULED',
      pg_catalog.jsonb_set(
        attempt_contract,
        '{id}',
        '"018f0000-0000-7000-8000-000000000103"'::jsonb
      )
    FROM qc2_models_prediction.scheduled_attempt
    WHERE id = '018f0000-0000-7000-8000-000000000102';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'Prediction authority inserted a validation-owned schedule';
  END IF;
END
$validation_role_boundary$;
RESET SESSION AUTHORIZATION;

DO $fixture_production_denial$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint AS constraint_row
    WHERE constraint_row.conrelid = 'qc2_models_prediction.prediction_run'::regclass
      AND constraint_row.contype = 'c'
      AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
        ILIKE '%environment_namespace <> ''production''%'
        AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
        ILIKE '%evidence_class = ''FORWARD_SEALED''%'
  ) THEN
    RETURN;
  END IF;
  RAISE EXCEPTION 'Production evidence-class restriction is not installed';
END
$fixture_production_denial$;
