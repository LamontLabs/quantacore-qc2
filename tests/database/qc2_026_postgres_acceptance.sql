SET LOCAL row_security = on;

DO $isolation_check$
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'serializable' THEN
    RAISE EXCEPTION 'QC2-026 PostgreSQL acceptance must run at SERIALIZABLE isolation';
  END IF;
END
$isolation_check$;

DO $validation_authority_boundaries$
DECLARE
  guarded_count integer;
  definition_count integer;
BEGIN
  SELECT pg_catalog.count(*)::integer
    INTO guarded_count
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE (
      (namespace.nspname = 'qc2_validation' AND relation.relname IN (
        'metric_definition',
        'qualification_receipt',
        'metric_result',
        'statistical_analysis_plan',
        'validation_report'
      ))
      OR (
        namespace.nspname = 'qc2_outcomes_research'
        AND relation.relname = 'holdout_access_receipt'
      )
    )
      AND relation.relrowsecurity
      AND relation.relforcerowsecurity;
  IF guarded_count <> 6 THEN
    RAISE EXCEPTION 'QC2-026 validation tables must all force row-level security';
  END IF;

  SELECT pg_catalog.count(*)::integer
    INTO definition_count
    FROM qc2_validation.metric_definition
    WHERE definition_contract->>'owning_authority' = 'validation'
      AND definition_contract->>'environment_namespace' = 'test';
  IF definition_count <> 8 THEN
    RAISE EXCEPTION 'QC2-026 must freeze all eight independent metric definitions';
  END IF;

  IF NOT pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_validation.qualification_receipt',
       'INSERT'
     )
     OR NOT pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_validation.metric_result',
       'INSERT'
     )
     OR NOT pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_outcomes_research.holdout_access_receipt',
       'INSERT'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_validation',
       'qc2_validation.metric_result',
       'UPDATE'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_apexlab',
       'qc2_validation.qualification_receipt',
       'SELECT'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_apexlab',
       'qc2_validation.metric_result',
       'SELECT'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_owner_api',
       'qc2_validation.metric_result',
       'SELECT'
     )
     OR NOT pg_catalog.has_table_privilege(
       'qc2_runtime_owner_api',
       'qc2_validation.validation_report',
       'SELECT'
     ) THEN
    RAISE EXCEPTION 'QC2-026 validation read/write privileges exceed the narrow role boundary';
  END IF;
END
$validation_authority_boundaries$;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_validation;
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
  WHERE id = '018f0000-0000-7000-8000-000000000102'
    AND attempt_state = 'SCHEDULED';
DO $one_time_holdout_access$
DECLARE
  access_contract jsonb;
  access_hash text;
  duplicate_rejected boolean := false;
BEGIN
  access_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.outcomes_research.HoldoutAccessReceipt.v1',
    'schema_version', '1.0',
    'id', '018f0000-0000-7000-8000-000000003001',
    'created_at', '2026-10-08T18:05:00Z',
    'owning_authority', 'validation',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', pg_catalog.jsonb_build_array(
      pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
        'target_id', '018f0000-0000-7000-8000-000000000001',
        'content_hash', pg_catalog.repeat('a', 64)
      )
    ),
    'dataset_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.DatasetManifest.v1',
      'target_id', '018f0000-0000-7000-8000-000000003100',
      'content_hash', pg_catalog.repeat('d', 64)
    ),
    'evaluator_identity', 'qc2-026-acceptance-evaluator',
    'access_scope', 'METRICS_ONLY',
    'requested_at', '2026-10-08T18:00:00Z',
    'granted_at', '2026-10-08T18:05:00Z',
    'consumed_fields', '["eligible_instrument_ids","sealed_rank","matured_binary_event","feed_snapshot_hash","label_registry_hash","session_id"]'::jsonb,
    'released_metrics', '["operating_expansion_runner_precision_at_10","comparator_expansion_runner_precision_at_10","operating_expansion_runner_recall_at_10","comparator_expansion_runner_recall_at_10","operating_eligible_prediction_coverage","comparator_eligible_prediction_coverage","paired_precision_difference_at_10","expansion_runner_precision_lift_at_10"]'::jsonb,
    'receipt_hash', pg_catalog.repeat('0', 64)
  );
  access_hash := qc2_integrity_build.hash_json(
    'qc2.validation.holdout-access.v1',
    access_contract - 'receipt_hash'
  );
  access_contract := pg_catalog.jsonb_set(
    access_contract,
    '{receipt_hash}',
    pg_catalog.to_jsonb(access_hash)
  );
  INSERT INTO qc2_outcomes_research.holdout_access_receipt (
    id,
    dataset_id,
    epoch_id,
    dataset_content_hash,
    evaluator_identity,
    access_scope,
    receipt_hash,
    receipt_contract
  )
  VALUES (
    '018f0000-0000-7000-8000-000000003001',
    '018f0000-0000-7000-8000-000000003100',
    '018f0000-0000-7000-8000-000000000001',
    pg_catalog.repeat('d', 64),
    'qc2-026-acceptance-evaluator',
    'METRICS_ONLY',
    access_hash,
    access_contract
  );

  access_contract := pg_catalog.jsonb_set(
    access_contract,
    '{id}',
    '"018f0000-0000-7000-8000-000000003002"'::jsonb
  );
  access_contract := pg_catalog.jsonb_set(
    access_contract,
    '{receipt_hash}',
    pg_catalog.to_jsonb(pg_catalog.repeat('0', 64))
  );
  access_hash := qc2_integrity_build.hash_json(
    'qc2.validation.holdout-access.v1',
    access_contract - 'receipt_hash'
  );
  access_contract := pg_catalog.jsonb_set(
    access_contract,
    '{receipt_hash}',
    pg_catalog.to_jsonb(access_hash)
  );
  BEGIN
    INSERT INTO qc2_outcomes_research.holdout_access_receipt (
      id,
      dataset_id,
      epoch_id,
      dataset_content_hash,
      evaluator_identity,
      access_scope,
      receipt_hash,
      receipt_contract
    )
    VALUES (
      '018f0000-0000-7000-8000-000000003002',
      '018f0000-0000-7000-8000-000000003100',
      '018f0000-0000-7000-8000-000000000001',
      pg_catalog.repeat('d', 64),
      'qc2-026-acceptance-evaluator',
      'METRICS_ONLY',
      access_hash,
      access_contract
    );
  EXCEPTION WHEN unique_violation THEN
    duplicate_rejected := true;
  END;
  IF NOT duplicate_rejected THEN
    RAISE EXCEPTION 'A content-addressed qualification holdout was granted more than once';
  END IF;
END
$one_time_holdout_access$;

DO $unsealed_attempt_cannot_qualify$
DECLARE
  receipt_contract jsonb;
  receipt_hash text;
  unsealed_rejected boolean := false;
BEGIN
  receipt_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.validation.QualificationReceipt.v1',
    'schema_version', '1.0',
    'id', '018f0000-0000-7000-8000-000000003003',
    'created_at', '2026-10-08T19:00:00Z',
    'owning_authority', 'validation',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'content_hash', pg_catalog.repeat('0', 64),
    'epoch_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
      'target_id', '018f0000-0000-7000-8000-000000000001',
      'content_hash', pg_catalog.repeat('a', 64)
    ),
    'session_id', '2026-10-09',
    'prediction_seal_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.PredictionSeal.v1',
      'target_id', '018f0000-0000-7000-8000-000000003300',
      'content_hash', pg_catalog.repeat('b', 64)
    ),
    'prediction_integrity', 'FULL_VERIFIED',
    'denominator_status', 'VALID',
    'on_time_seal', true,
    'on_time_anchor', true,
    'comparator_available', true,
    'protocol_conformity', true,
    'sealed_at', '2026-10-08T19:00:00Z',
    'checkpoint_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.integrity_build.Checkpoint.v1',
      'target_id', '018f0000-0000-7000-8000-000000003400',
      'content_hash', pg_catalog.repeat('c', 64)
    )
  );
  receipt_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.validation.qualificationreceipt.v1/1.0',
    receipt_contract - ARRAY[
      'content_hash','created_at','id','schema_name','schema_version'
    ]::text[]
  );
  receipt_contract := pg_catalog.jsonb_set(
    receipt_contract,
    '{content_hash}',
    pg_catalog.to_jsonb(receipt_hash)
  );
  BEGIN
    INSERT INTO qc2_validation.qualification_receipt (
      id,
      epoch_id,
      session_id,
      prediction_seal_id,
      checkpoint_id,
      prediction_integrity,
      denominator_status,
      on_time_seal,
      on_time_anchor,
      comparator_available,
      protocol_conformity,
      sealed_at,
      content_hash,
      receipt_contract
    )
    VALUES (
      '018f0000-0000-7000-8000-000000003003',
      '018f0000-0000-7000-8000-000000000001',
      '2026-10-09',
      '018f0000-0000-7000-8000-000000003300',
      '018f0000-0000-7000-8000-000000003400',
      'FULL_VERIFIED',
      'VALID',
      true,
      true,
      true,
      true,
      '2026-10-08T19:00:00Z',
      receipt_hash,
      receipt_contract
    );
  EXCEPTION WHEN no_data_found THEN
    unsealed_rejected := true;
  END;
  IF NOT unsealed_rejected THEN
    RAISE EXCEPTION 'A scheduled but unsealed opportunity received a qualification receipt';
  END IF;
END
$unsealed_attempt_cannot_qualify$;
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_apexlab;
DO $trainer_cannot_read_qualification$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    PERFORM 1 FROM qc2_validation.qualification_receipt;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'A training role read qualification receipts';
  END IF;

  denied := false;
  BEGIN
    PERFORM 1 FROM qc2_validation.metric_result;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'A training role read qualification metrics';
  END IF;
END
$trainer_cannot_read_qualification$;
RESET SESSION AUTHORIZATION;

DO $production_is_not_authorized$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint AS constraint_row
    WHERE constraint_row.conrelid = 'qc2_validation.statistical_analysis_plan'::regclass
      AND constraint_row.contype = 'c'
      AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
        ILIKE '%environment_namespace%development%'
      AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
        ILIKE '%environment_namespace%research%'
  ) THEN
    RAISE EXCEPTION 'QC2-026 statistical plans must remain nonproduction-only';
  END IF;
END
$production_is_not_authorized$;
