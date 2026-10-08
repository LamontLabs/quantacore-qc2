-- QC2-026 prospective qualification, aggregate metrics, and immutable closure artifacts.
-- This policy/framework migration is restricted to nonproduction namespaces.

SET ROLE qc2_migrator;

GRANT USAGE ON SCHEMA qc2_outcomes_research TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_control.assert_runtime_authority(text)
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_integrity_build.hash_json(text, jsonb)
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_integrity_build.canonical_jsonb_text(jsonb),
  qc2_integrity_build.digest(bytea, text)
  TO qc2_runtime_validation;

ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_validation
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_outcomes_research
  REVOKE ALL ON TABLES FROM PUBLIC;

CREATE TABLE qc2_validation.metric_definition (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  metric_key text NOT NULL CHECK (metric_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  version integer NOT NULL CHECK (version > 0),
  definition_contract jsonb NOT NULL CHECK (
    definition_contract->>'schema_name' = 'qc2.validation.MetricDefinition.v1'
    AND definition_contract->>'schema_version' = '1.0'
    AND definition_contract->>'owning_authority' = 'validation'
    AND definition_contract->>'id' = id::text
    AND definition_contract->>'metric_key' = metric_key
    AND definition_contract->>'version' = version::text
    AND definition_contract->>'environment_namespace' IN ('development','test','research')
  ),
  UNIQUE (metric_key, version)
);

INSERT INTO qc2_validation.metric_definition (
  id, metric_key, version, definition_contract
)
SELECT
  definition.id,
  definition.metric_key,
  1,
  pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.validation.MetricDefinition.v1',
    'schema_version', '1.0',
    'id', definition.id::text,
    'created_at', '2026-10-08T00:00:00Z',
    'owning_authority', 'validation',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'metric_key', definition.metric_key,
    'version', 1,
    'estimand', definition.estimand,
    'unit', definition.unit,
    'direction', definition.direction,
    'missingness_policy', 'EXPLICIT_REASON',
    'tie_handling', definition.tie_handling
  )
FROM (
  VALUES
    (
      '018f0000-0000-7000-8000-000000002001'::uuid,
      'operating_expansion_runner_precision_at_10',
      'Per exchange session, expansion-runner outcomes among the first ten eligible operating predictions, divided by ten.',
      'fraction',
      'HIGHER_IS_BETTER',
      'Use the sealed prediction rank; tied scores must already use the pinned tie rule.'
    ),
    (
      '018f0000-0000-7000-8000-000000002002'::uuid,
      'comparator_expansion_runner_precision_at_10',
      'Per exchange session, expansion-runner outcomes among the first ten transparent-composite predictions, divided by ten.',
      'fraction',
      'HIGHER_IS_BETTER',
      'Use the sealed prediction rank; tied scores must already use the pinned tie rule.'
    ),
    (
      '018f0000-0000-7000-8000-000000002003'::uuid,
      'operating_expansion_runner_recall_at_10',
      'Per exchange session, known expansion-runner events among the first ten eligible predictions divided by all expansion-runner events in the eligible universe.',
      'fraction',
      'HIGHER_IS_BETTER',
      'Use the sealed prediction rank; tied scores must already use the pinned tie rule.'
    ),
    (
      '018f0000-0000-7000-8000-000000002004'::uuid,
      'comparator_expansion_runner_recall_at_10',
      'Per exchange session, known expansion-runner events among the first ten transparent-composite predictions divided by all expansion-runner events in the eligible universe.',
      'fraction',
      'HIGHER_IS_BETTER',
      'Use the sealed prediction rank; tied scores must already use the pinned tie rule.'
    ),
    (
      '018f0000-0000-7000-8000-000000002005'::uuid,
      'operating_eligible_prediction_coverage',
      'Scored eligible instruments divided by all census-eligible instruments in the session.',
      'fraction',
      'DESCRIPTIVE',
      'Not applicable; coverage uses the complete eligible instrument denominator.'
    ),
    (
      '018f0000-0000-7000-8000-000000002006'::uuid,
      'comparator_eligible_prediction_coverage',
      'Transparent-composite scored eligible instruments divided by all census-eligible instruments in the session.',
      'fraction',
      'DESCRIPTIVE',
      'Not applicable; coverage uses the complete eligible instrument denominator.'
    ),
    (
      '018f0000-0000-7000-8000-000000002007'::uuid,
      'paired_precision_difference_at_10',
      'Operating expansion-runner Precision@10 minus transparent-composite Precision@10, paired by the same exchange session and instrument labels.',
      'fraction',
      'HIGHER_IS_BETTER',
      'Use each sealed role''s pinned rank; shared instrument outcomes cancel in the paired bound.'
    ),
    (
      '018f0000-0000-7000-8000-000000002008'::uuid,
      'expansion_runner_precision_lift_at_10',
      'Operating expansion-runner Precision@10 divided by transparent-composite Precision@10; undefined when the comparator precision can be zero.',
      'ratio',
      'HIGHER_IS_BETTER',
      'Use the sealed prediction rank; tied scores must already use the pinned tie rule.'
    )
) AS definition(id, metric_key, estimand, unit, direction, tie_handling);

CREATE TABLE qc2_validation.qualification_receipt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  prediction_seal_id uuid NOT NULL,
  checkpoint_id uuid NOT NULL
    REFERENCES qc2_integrity_build.evidence_checkpoint(id) ON DELETE RESTRICT,
  prediction_integrity text NOT NULL CHECK (
    prediction_integrity IN ('FULL_VERIFIED','PARTIAL_SCAN','FAILED','UNAVAILABLE','VALID','INVALID')
  ),
  denominator_status text NOT NULL CHECK (
    denominator_status IN ('VALID','INSUFFICIENT','MISSING','UNKNOWN')
  ),
  on_time_seal boolean NOT NULL,
  on_time_anchor boolean NOT NULL,
  comparator_available boolean NOT NULL,
  protocol_conformity boolean NOT NULL,
  sealed_at timestamptz NOT NULL,
  on_time_receipt boolean NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  qualification_state text GENERATED ALWAYS AS (
    CASE
      WHEN prediction_integrity IN ('FAILED','INVALID')
        OR denominator_status IN ('INSUFFICIENT','MISSING')
        OR NOT on_time_seal
        OR NOT on_time_anchor
        OR NOT on_time_receipt
        OR NOT comparator_available
        OR NOT protocol_conformity
        THEN 'NONQUALIFYING'
      WHEN prediction_integrity IN ('FULL_VERIFIED','VALID')
        AND denominator_status = 'VALID'
        AND on_time_seal
        AND on_time_anchor
        AND on_time_receipt
        AND comparator_available
        AND protocol_conformity
        THEN 'QUALIFYING'
      ELSE 'INDETERMINATE'
    END
  ) STORED,
  receipt_contract jsonb NOT NULL CHECK (
    receipt_contract->>'schema_name' = 'qc2.validation.QualificationReceipt.v1'
    AND receipt_contract->>'schema_version' = '1.0'
    AND receipt_contract->>'owning_authority' = 'validation'
    AND receipt_contract->>'id' = id::text
    AND receipt_contract->'epoch_ref'->>'target_schema_name'
      = 'qc2.validation.ValidationEpoch.v1'
    AND receipt_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND receipt_contract->>'session_id' = session_id
    AND receipt_contract->'prediction_seal_ref'->>'target_schema_name'
      = 'qc2.models_prediction.PredictionSeal.v1'
    AND receipt_contract->'prediction_seal_ref'->>'target_id' = prediction_seal_id::text
    AND receipt_contract->'checkpoint_ref'->>'target_schema_name'
      = 'qc2.integrity_build.Checkpoint.v1'
    AND receipt_contract->'checkpoint_ref'->>'target_id' = checkpoint_id::text
    AND receipt_contract->>'prediction_integrity' = prediction_integrity
    AND receipt_contract->>'denominator_status' = denominator_status
    AND (receipt_contract->>'on_time_seal')::boolean = on_time_seal
    AND (receipt_contract->>'on_time_anchor')::boolean = on_time_anchor
    AND (receipt_contract->>'comparator_available')::boolean = comparator_available
    AND (receipt_contract->>'protocol_conformity')::boolean = protocol_conformity
    AND (receipt_contract->>'sealed_at')::timestamptz = sealed_at
    AND receipt_contract->>'content_hash' = content_hash
    AND receipt_contract->>'environment_namespace' IN ('development','test','research')
  ),
  UNIQUE (epoch_id, session_id),
  UNIQUE (id, epoch_id, session_id),
  FOREIGN KEY (epoch_id, session_id)
    REFERENCES qc2_models_prediction.scheduled_attempt(epoch_id, session_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (epoch_id, session_id, prediction_seal_id)
    REFERENCES qc2_models_prediction.prediction_seal(epoch_id, session_id, id)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_outcomes_research.holdout_access_receipt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  dataset_id uuid NOT NULL,
  epoch_id uuid NOT NULL,
  dataset_content_hash text NOT NULL CHECK (dataset_content_hash ~ '^[0-9a-f]{64}$'),
  evaluator_identity text NOT NULL CHECK (pg_catalog.length(evaluator_identity) > 0),
  access_scope text NOT NULL CHECK (access_scope IN ('METRICS_ONLY','AGGREGATES_ONLY')),
  receipt_hash text NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
  receipt_contract jsonb NOT NULL CHECK (
    receipt_contract->>'schema_name' = 'qc2.outcomes_research.HoldoutAccessReceipt.v1'
    AND receipt_contract->>'schema_version' = '1.0'
    AND receipt_contract->>'owning_authority' = 'validation'
    AND receipt_contract->>'id' = id::text
    AND pg_catalog.jsonb_array_length(receipt_contract->'source_refs') = 1
    AND receipt_contract->'source_refs'->0->>'target_schema_name'
      = 'qc2.validation.ValidationEpoch.v1'
    AND receipt_contract->'source_refs'->0->>'target_id' = epoch_id::text
    AND receipt_contract->'dataset_ref'->>'target_schema_name'
      = 'qc2.outcomes_research.DatasetManifest.v1'
    AND receipt_contract->'dataset_ref'->>'target_id' = dataset_id::text
    AND receipt_contract->'dataset_ref'->>'content_hash' = dataset_content_hash
    AND receipt_contract->>'evaluator_identity' = evaluator_identity
    AND receipt_contract->>'access_scope' = access_scope
    AND receipt_contract->'consumed_fields'
      = '["eligible_instrument_ids","sealed_rank","matured_binary_event","feed_snapshot_hash","label_registry_hash","session_id"]'::jsonb
    AND receipt_contract->'released_metrics'
      = '["operating_expansion_runner_precision_at_10","comparator_expansion_runner_precision_at_10","operating_expansion_runner_recall_at_10","comparator_expansion_runner_recall_at_10","operating_eligible_prediction_coverage","comparator_eligible_prediction_coverage","paired_precision_difference_at_10","expansion_runner_precision_lift_at_10"]'::jsonb
    AND receipt_contract->>'receipt_hash' = receipt_hash
    AND receipt_contract->>'environment_namespace' IN ('development','test','research')
  ),
  UNIQUE (dataset_id, dataset_content_hash)
);

CREATE TABLE qc2_validation.metric_result (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  holdout_receipt_id uuid NOT NULL
    REFERENCES qc2_outcomes_research.holdout_access_receipt(id) ON DELETE RESTRICT,
  qualification_receipt_id uuid NOT NULL,
  metric_definition_id uuid NOT NULL
    REFERENCES qc2_validation.metric_definition(id) ON DELETE RESTRICT,
  epoch_id uuid NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  value text CHECK (value IS NULL OR value ~ '^-?(0|[1-9][0-9]*)\.[0-9]{12}$'),
  lower_bound text CHECK (
    lower_bound IS NULL OR lower_bound ~ '^-?(0|[1-9][0-9]*)\.[0-9]{12}$'
  ),
  upper_bound text CHECK (
    upper_bound IS NULL OR upper_bound ~ '^-?(0|[1-9][0-9]*)\.[0-9]{12}$'
  ),
  denominator integer NOT NULL CHECK (denominator >= 0),
  missing_count integer NOT NULL CHECK (missing_count >= 0 AND missing_count <= denominator),
  computed_at timestamptz NOT NULL,
  result_contract jsonb NOT NULL CHECK (
    result_contract->>'schema_name' = 'qc2.validation.MetricResult.v1'
    AND result_contract->>'schema_version' = '1.0'
    AND result_contract->>'owning_authority' = 'validation'
    AND result_contract->>'id' = id::text
    AND result_contract->'definition_ref'->>'target_schema_name'
      = 'qc2.validation.MetricDefinition.v1'
    AND result_contract->'definition_ref'->>'target_id' = metric_definition_id::text
    AND result_contract->'epoch_ref'->>'target_schema_name'
      = 'qc2.validation.ValidationEpoch.v1'
    AND result_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND result_contract->>'session_id' = session_id
    AND result_contract->>'value' IS NOT DISTINCT FROM value
    AND result_contract->>'lower_bound' IS NOT DISTINCT FROM lower_bound
    AND result_contract->>'upper_bound' IS NOT DISTINCT FROM upper_bound
    AND result_contract->>'denominator' = denominator::text
    AND result_contract->>'missing_count' = missing_count::text
    AND (result_contract->>'computed_at')::timestamptz = computed_at
    AND result_contract->>'environment_namespace' IN ('development','test','research')
  ),
  FOREIGN KEY (qualification_receipt_id, epoch_id, session_id)
    REFERENCES qc2_validation.qualification_receipt(id, epoch_id, session_id)
    ON DELETE RESTRICT,
  UNIQUE (holdout_receipt_id, qualification_receipt_id, metric_definition_id)
);

CREATE TABLE qc2_validation.statistical_analysis_plan (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL UNIQUE,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  plan_contract jsonb NOT NULL CHECK (
    plan_contract->>'schema_name' = 'qc2.validation.StatisticalAnalysisPlan.v1'
    AND plan_contract->>'schema_version' = '1.0'
    AND plan_contract->>'owning_authority' = 'validation'
    AND plan_contract->>'id' = id::text
    AND plan_contract->'epoch_ref'->>'target_schema_name'
      = 'qc2.validation.ValidationEpoch.v1'
    AND plan_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND plan_contract->'primary_metric_ref'->>'target_schema_name'
      = 'qc2.validation.MetricDefinition.v1'
    AND plan_contract->'comparator_ref'->>'target_schema_name'
      = 'qc2.scientific_definitions.BaselineManifest.v1'
    AND plan_contract->>'content_hash' = content_hash
    AND plan_contract->>'interval_method' IN (
      'contiguous_block_bootstrap_v1',
      'moving_block_bootstrap_v1',
      'stationary_block_bootstrap_v1',
      'event_cluster_bootstrap_v1'
    )
    AND plan_contract->'primary_metric_ref'->>'target_id'
      = '018f0000-0000-7000-8000-000000002007'
    AND (plan_contract->>'resample_count')::bigint >= 10000
    AND plan_contract->>'environment_namespace' IN ('development','test','research')
  )
);

CREATE TABLE qc2_validation.validation_report (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL UNIQUE,
  verdict text NOT NULL CHECK (verdict IN ('PASS','FAIL','INSUFFICIENT_EVIDENCE')),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  report_hash text NOT NULL CHECK (report_hash ~ '^[0-9a-f]{64}$'),
  report_contract jsonb NOT NULL CHECK (
    report_contract->>'schema_name' = 'qc2.validation.ValidationReport.v1'
    AND report_contract->>'schema_version' = '1.0'
    AND report_contract->>'owning_authority' = 'validation'
    AND report_contract->>'id' = id::text
    AND report_contract->'epoch_ref'->>'target_schema_name'
      = 'qc2.validation.ValidationEpoch.v1'
    AND report_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND report_contract->>'verdict' = verdict
    AND report_contract->>'content_hash' = content_hash
    AND report_contract->>'report_hash' = report_hash
    AND report_contract->>'environment_namespace' IN ('development','test','research')
  )
);

CREATE FUNCTION qc2_validation.guard_content_addressed_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build, qc2_validation
AS $function$
DECLARE
  contract_payload jsonb;
  schema_name text;
  schema_version text;
  expected_hash text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  contract_payload := pg_catalog.to_jsonb(NEW) -> TG_ARGV[0];
  schema_name := contract_payload->>'schema_name';
  schema_version := contract_payload->>'schema_version';
  IF schema_name IS NULL OR schema_version IS NULL THEN
    RAISE EXCEPTION 'content-addressed contract envelope is incomplete'
      USING ERRCODE = '23514';
  END IF;
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/' || pg_catalog.lower(schema_name) || '/'
      || pg_catalog.lower(schema_version),
    contract_payload - ARRAY[
      'content_hash','created_at','id','schema_name','schema_version'
    ]::text[]
  );
  IF contract_payload->>'content_hash' IS DISTINCT FROM expected_hash THEN
    RAISE EXCEPTION 'contract content hash does not match canonical content'
      USING ERRCODE = '23514';
  END IF;

  IF TG_TABLE_NAME = 'validation_report' THEN
    expected_hash := qc2_integrity_build.hash_json(
      'qc2.validation-report.v1',
      contract_payload - ARRAY['content_hash','report_hash']::text[]
    );
    IF contract_payload->>'report_hash' IS DISTINCT FROM expected_hash THEN
      RAISE EXCEPTION 'validation report hash does not match report payload'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_validation.guard_qualification_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_models_prediction, qc2_validation
AS $function$
DECLARE
  scheduled qc2_models_prediction.scheduled_attempt%ROWTYPE;
  seal_run_id uuid;
  seal_role text;
  seal_deadline timestamptz;
  seal_sealed_at timestamptz;
  seal_content_hash text;
  anchor_created_at timestamptz;
  anchor_content_hash text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  SELECT * INTO STRICT scheduled
    FROM qc2_models_prediction.scheduled_attempt
    WHERE epoch_id = NEW.epoch_id AND session_id = NEW.session_id;
  SELECT run_id, role, deadline, sealed_at, seal_contract->>'content_hash'
    INTO STRICT seal_run_id, seal_role, seal_deadline, seal_sealed_at, seal_content_hash
    FROM qc2_models_prediction.prediction_seal
    WHERE id = NEW.prediction_seal_id
      AND epoch_id = NEW.epoch_id
      AND session_id = NEW.session_id;
  SELECT created_at, content_hash INTO STRICT anchor_created_at, anchor_content_hash
    FROM qc2_integrity_build.evidence_checkpoint
    WHERE id = NEW.checkpoint_id;
  IF scheduled.attempt_state <> 'SEALED'
    OR scheduled.run_id IS DISTINCT FROM seal_run_id
    OR seal_role <> 'OPERATING'
    OR NEW.receipt_contract->'prediction_seal_ref'->>'content_hash'
      IS DISTINCT FROM seal_content_hash
    OR NEW.receipt_contract->'checkpoint_ref'->>'content_hash'
      IS DISTINCT FROM anchor_content_hash
    OR seal_deadline > scheduled.expected_deadline
    OR seal_sealed_at > anchor_created_at
    OR anchor_created_at > NEW.sealed_at
    OR NEW.on_time_seal IS DISTINCT FROM (
      seal_sealed_at <= LEAST(seal_deadline, scheduled.expected_deadline)
    )
    OR NEW.on_time_anchor IS DISTINCT FROM (
      anchor_created_at <= scheduled.expected_deadline
    ) THEN
    RAISE EXCEPTION 'qualification requires the sealed operating run for its scheduled session'
      USING ERRCODE = '23514';
  END IF;
  NEW.on_time_receipt := NEW.sealed_at <= scheduled.expected_deadline;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_validation.guard_metric_result_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_outcomes_research, qc2_validation
AS $function$
DECLARE
  qualification_state text;
  access_scope text;
  access_epoch_id uuid;
  metric_key text;
  released_metrics jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  SELECT qualification.qualification_state INTO STRICT qualification_state
    FROM qc2_validation.qualification_receipt AS qualification
    WHERE qualification.id = NEW.qualification_receipt_id
      AND qualification.epoch_id = NEW.epoch_id
      AND qualification.session_id = NEW.session_id;
  SELECT receipt.epoch_id, receipt.access_scope, receipt.receipt_contract->'released_metrics'
    INTO STRICT access_epoch_id, access_scope, released_metrics
    FROM qc2_outcomes_research.holdout_access_receipt AS receipt
    WHERE receipt.id = NEW.holdout_receipt_id;
  SELECT definition.metric_key INTO STRICT metric_key
    FROM qc2_validation.metric_definition AS definition
    WHERE definition.id = NEW.metric_definition_id;
  IF qualification_state <> 'QUALIFYING' THEN
    RAISE EXCEPTION 'metric results require a qualifying receipt'
      USING ERRCODE = '23514';
  END IF;
  IF access_scope NOT IN ('METRICS_ONLY','AGGREGATES_ONLY') THEN
    RAISE EXCEPTION 'metric results require narrow aggregate holdout access'
      USING ERRCODE = '23514';
  END IF;
  IF access_epoch_id IS DISTINCT FROM NEW.epoch_id
    OR NOT (released_metrics ? metric_key) THEN
    RAISE EXCEPTION 'metric result is outside the authorized epoch or metric set'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_outcomes_research.guard_holdout_access_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control, qc2_integrity_build,
  qc2_models_prediction, qc2_outcomes_research, qc2_validation
AS $function$
DECLARE
  expected_hash text;
  latest_deadline timestamptz;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  expected_hash := qc2_integrity_build.hash_json(
    'qc2.validation.holdout-access.v1',
    NEW.receipt_contract - 'receipt_hash'
  );
  IF NEW.receipt_hash IS DISTINCT FROM expected_hash THEN
    RAISE EXCEPTION 'holdout access receipt hash does not match its payload'
      USING ERRCODE = '23514';
  END IF;
  SELECT pg_catalog.max(scheduled.expected_deadline)
    INTO latest_deadline
    FROM qc2_models_prediction.scheduled_attempt AS scheduled
    WHERE scheduled.epoch_id = NEW.epoch_id;
  IF latest_deadline IS NULL
    OR EXISTS (
      SELECT 1
      FROM qc2_models_prediction.scheduled_attempt AS scheduled
      WHERE scheduled.epoch_id = NEW.epoch_id
        AND scheduled.attempt_state NOT IN (
          'SEALED','MISSED_START','FAILED','NONQUALIFYING'
        )
    )
    OR EXISTS (
      SELECT 1
      FROM qc2_models_prediction.scheduled_attempt AS scheduled
      WHERE scheduled.epoch_id = NEW.epoch_id
        AND scheduled.attempt_state = 'SEALED'
        AND NOT EXISTS (
          SELECT 1
          FROM qc2_validation.qualification_receipt AS qualification
          WHERE qualification.epoch_id = scheduled.epoch_id
            AND qualification.session_id = scheduled.session_id
        )
    )
    OR (NEW.receipt_contract->>'granted_at')::timestamptz < latest_deadline THEN
    RAISE EXCEPTION 'holdout access requires a closed, prospectively qualified schedule'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_validation.prevent_immutable_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('validation');
  RAISE EXCEPTION 'validation evidence is append-only'
    USING ERRCODE = '42501';
END
$function$;

CREATE TRIGGER qualification_receipt_content_hash
BEFORE INSERT ON qc2_validation.qualification_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_validation.guard_content_addressed_insert('receipt_contract');
CREATE TRIGGER qualification_receipt_run_binding
BEFORE INSERT ON qc2_validation.qualification_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_validation.guard_qualification_insert();
CREATE TRIGGER metric_result_qualification_guard
BEFORE INSERT ON qc2_validation.metric_result
FOR EACH ROW EXECUTE FUNCTION qc2_validation.guard_metric_result_insert();
CREATE TRIGGER analysis_plan_content_hash
BEFORE INSERT ON qc2_validation.statistical_analysis_plan
FOR EACH ROW EXECUTE FUNCTION qc2_validation.guard_content_addressed_insert('plan_contract');
CREATE TRIGGER validation_report_content_hash
BEFORE INSERT ON qc2_validation.validation_report
FOR EACH ROW EXECUTE FUNCTION qc2_validation.guard_content_addressed_insert('report_contract');
CREATE TRIGGER holdout_access_receipt_hash
BEFORE INSERT ON qc2_outcomes_research.holdout_access_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_outcomes_research.guard_holdout_access_insert();

CREATE TRIGGER metric_definition_append_only
BEFORE UPDATE OR DELETE ON qc2_validation.metric_definition
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();
CREATE TRIGGER qualification_receipt_append_only
BEFORE UPDATE OR DELETE ON qc2_validation.qualification_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();
CREATE TRIGGER metric_result_append_only
BEFORE UPDATE OR DELETE ON qc2_validation.metric_result
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();
CREATE TRIGGER statistical_analysis_plan_append_only
BEFORE UPDATE OR DELETE ON qc2_validation.statistical_analysis_plan
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();
CREATE TRIGGER validation_report_append_only
BEFORE UPDATE OR DELETE ON qc2_validation.validation_report
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();
CREATE TRIGGER holdout_access_receipt_append_only
BEFORE UPDATE OR DELETE ON qc2_outcomes_research.holdout_access_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_validation.prevent_immutable_record_mutation();

ALTER TABLE qc2_validation.metric_definition ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.metric_definition FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.qualification_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.qualification_receipt FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.metric_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.metric_result FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.statistical_analysis_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.statistical_analysis_plan FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.validation_report ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_validation.validation_report FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.holdout_access_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_outcomes_research.holdout_access_receipt FORCE ROW LEVEL SECURITY;

CREATE POLICY validation_metric_definition_migrator_all
  ON qc2_validation.metric_definition FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY validation_qualification_receipt_migrator_all
  ON qc2_validation.qualification_receipt FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY validation_metric_result_migrator_all
  ON qc2_validation.metric_result FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY validation_analysis_plan_migrator_all
  ON qc2_validation.statistical_analysis_plan FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY validation_report_migrator_all
  ON qc2_validation.validation_report FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);
CREATE POLICY holdout_access_receipt_migrator_all
  ON qc2_outcomes_research.holdout_access_receipt FOR ALL TO qc2_migrator
  USING (true) WITH CHECK (true);

CREATE POLICY validation_metric_definition_read
  ON qc2_validation.metric_definition FOR SELECT TO qc2_runtime_validation
  USING (true);
CREATE POLICY validation_qualification_receipt_read
  ON qc2_validation.qualification_receipt FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_qualification_receipt_insert
  ON qc2_validation.qualification_receipt FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_metric_result_read
  ON qc2_validation.metric_result FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_metric_result_insert
  ON qc2_validation.metric_result FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_analysis_plan_read
  ON qc2_validation.statistical_analysis_plan FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_analysis_plan_insert
  ON qc2_validation.statistical_analysis_plan FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_report_validation_read
  ON qc2_validation.validation_report FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_report_validation_insert
  ON qc2_validation.validation_report FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY validation_report_owner_read
  ON qc2_validation.validation_report FOR SELECT TO qc2_runtime_owner_api
  USING (true);
CREATE POLICY holdout_access_receipt_validation_read
  ON qc2_outcomes_research.holdout_access_receipt FOR SELECT TO qc2_runtime_validation
  USING (qc2_control.current_runtime_authority() = 'validation');
CREATE POLICY holdout_access_receipt_validation_insert
  ON qc2_outcomes_research.holdout_access_receipt FOR INSERT TO qc2_runtime_validation
  WITH CHECK (qc2_control.current_runtime_authority() = 'validation');

GRANT SELECT ON qc2_validation.metric_definition TO qc2_runtime_validation;
GRANT SELECT, INSERT ON
  qc2_validation.qualification_receipt,
  qc2_validation.metric_result,
  qc2_validation.statistical_analysis_plan,
  qc2_validation.validation_report,
  qc2_outcomes_research.holdout_access_receipt
TO qc2_runtime_validation;
GRANT SELECT ON qc2_validation.validation_report TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_validation.guard_content_addressed_insert()
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_validation.guard_qualification_insert()
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_validation.guard_metric_result_insert()
  TO qc2_runtime_validation;
GRANT EXECUTE ON FUNCTION qc2_outcomes_research.guard_holdout_access_insert()
  TO qc2_runtime_validation;

RESET ROLE;
