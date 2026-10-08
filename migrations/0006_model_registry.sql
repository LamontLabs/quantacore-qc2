-- QC2-037 immutable model artifacts, lifecycle facts, retention links, and pointer slots.
-- PostgreSQL references are committed only after the caller presents full-verification
-- and storage-acknowledgment receipts. No operating-pointer transition is introduced here.

SET ROLE qc2_migrator;

GRANT USAGE ON SCHEMA qc2_integrity_build TO
  qc2_runtime_inference, qc2_runtime_prediction, qc2_runtime_promotion;
GRANT USAGE ON SCHEMA qc2_governance_owner TO
  qc2_runtime_inference, qc2_runtime_prediction;
GRANT EXECUTE ON FUNCTION qc2_control.assert_runtime_authority(text),
  qc2_control.current_runtime_authority(),
  qc2_integrity_build.canonical_jsonb_text(jsonb),
  qc2_integrity_build.hash_json(text, jsonb)
TO qc2_runtime_model_registry, qc2_runtime_validation,
  qc2_runtime_prediction, qc2_runtime_promotion;

ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_integrity_build
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_models_prediction
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_models_prediction
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_models_prediction
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_governance_owner
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_governance_owner
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_governance_owner
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE TABLE qc2_integrity_build.model_artifact_blob (
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  storage_backend text NOT NULL CHECK (
    storage_backend IN ('fixture_memory', 'local_cache', 'external_object_store')
  ),
  object_key text NOT NULL CHECK (object_key <> ''),
  byte_count bigint NOT NULL CHECK (byte_count > 0),
  durability_receipt text,
  staged_at timestamptz NOT NULL,
  PRIMARY KEY (sha256, storage_backend),
  UNIQUE (storage_backend, object_key),
  CHECK (
    (storage_backend = 'external_object_store' AND durability_receipt IS NOT NULL)
    OR
    (storage_backend <> 'external_object_store' AND durability_receipt IS NULL)
  )
);

CREATE TABLE qc2_integrity_build.model_artifact_manifest (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  inventory_hash text NOT NULL CHECK (inventory_hash ~ '^[0-9a-f]{64}$'),
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )
  ),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development', 'test', 'research', 'production')
  ),
  storage_backend text NOT NULL CHECK (
    storage_backend IN ('fixture_memory', 'local_cache', 'external_object_store')
  ),
  durability_receipt text,
  verification_hash text NOT NULL CHECK (verification_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL,
  manifest_contract jsonb NOT NULL CHECK (
    manifest_contract->>'schema_name' = 'qc2.integrity_build.ArtifactManifest.v1'
    AND manifest_contract->>'schema_version' = '1.0'
    AND manifest_contract->>'owning_authority' = 'model_registry'
    AND manifest_contract->>'id' = id::text
    AND manifest_contract->>'content_hash' = content_hash
    AND manifest_contract->>'inventory_hash' = inventory_hash
    AND manifest_contract->>'evidence_class' = evidence_class
    AND manifest_contract->>'environment_namespace' = environment_namespace
    AND (manifest_contract->>'created_at')::timestamptz = created_at
  ),
  UNIQUE (id, content_hash),
  CHECK (
    (storage_backend = 'external_object_store' AND durability_receipt IS NOT NULL)
    OR
    (storage_backend <> 'external_object_store' AND durability_receipt IS NULL)
  ),
  CHECK (
    environment_namespace <> 'production'
    OR (
      evidence_class = 'FORWARD_SEALED'
      AND storage_backend = 'external_object_store'
      AND durability_receipt IS NOT NULL
    )
  )
);

CREATE TABLE qc2_integrity_build.model_artifact_manifest_file (
  manifest_id uuid NOT NULL,
  manifest_hash text NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
  relative_path text NOT NULL CHECK (
    relative_path ~ '^[A-Za-z0-9._/-]+[.]json$'
    AND relative_path !~ '(^/|(^|/)[.][.]?(/|$)|//|:)'
  ),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  byte_count bigint NOT NULL CHECK (byte_count > 0),
  media_type text NOT NULL CHECK (media_type = 'application/json'),
  schema_name text NOT NULL CHECK (
    schema_name IN (
      'qc2.apexlab.SafeModelArtifact.v1',
      'qc2.apexlab.TrainingEnvironment.v1',
      'qc2.apexlab.FrozenHyperparameterSpace.v1'
    )
  ),
  schema_version text NOT NULL CHECK (schema_version = '1.0'),
  PRIMARY KEY (manifest_id, relative_path),
  FOREIGN KEY (manifest_id, manifest_hash)
    REFERENCES qc2_integrity_build.model_artifact_manifest(id, content_hash)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_models_prediction.model_registry_model (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  artifact_manifest_id uuid NOT NULL,
  artifact_manifest_hash text NOT NULL CHECK (artifact_manifest_hash ~ '^[0-9a-f]{64}$'),
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )
  ),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development', 'test', 'research', 'production')
  ),
  lifecycle_state text NOT NULL CHECK (
    lifecycle_state IN (
      'RESEARCH',
      'CANDIDATE',
      'CHALLENGER',
      'SHADOW',
      'PROMOTION_ELIGIBLE',
      'CHAMPION',
      'REJECTED',
      'RETIRED'
    )
  ),
  created_at timestamptz NOT NULL,
  model_contract jsonb NOT NULL CHECK (
    model_contract->>'schema_name' = 'qc2.models_prediction.ModelManifest.v1'
    AND model_contract->>'schema_version' = '1.0'
    AND model_contract->>'owning_authority' = 'model_registry'
    AND model_contract->>'id' = id::text
    AND model_contract->>'content_hash' = content_hash
    AND model_contract->'artifact_manifest_ref'->>'target_id' = artifact_manifest_id::text
    AND model_contract->'artifact_manifest_ref'->>'content_hash' = artifact_manifest_hash
    AND model_contract->>'evidence_class' = evidence_class
    AND model_contract->>'environment_namespace' = environment_namespace
    AND model_contract->>'lifecycle_state' = 'RESEARCH'
    AND model_contract->>'safe_format' = 'json'
    AND (model_contract->>'created_at')::timestamptz = created_at
  ),
  UNIQUE (id, content_hash),
  FOREIGN KEY (artifact_manifest_id, artifact_manifest_hash)
    REFERENCES qc2_integrity_build.model_artifact_manifest(id, content_hash)
    ON DELETE RESTRICT,
  CHECK (
    environment_namespace <> 'production'
    OR evidence_class = 'FORWARD_SEALED'
  )
);

CREATE TABLE qc2_integrity_build.model_artifact_dependency (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  parent_manifest_id uuid NOT NULL,
  parent_manifest_hash text NOT NULL CHECK (parent_manifest_hash ~ '^[0-9a-f]{64}$'),
  dependency_manifest_id uuid NOT NULL,
  dependency_manifest_hash text NOT NULL CHECK (dependency_manifest_hash ~ '^[0-9a-f]{64}$'),
  dependency_role text NOT NULL CHECK (dependency_role ~ '^[a-z][a-z0-9_-]{0,63}$'),
  required_for_retention boolean NOT NULL,
  discovered_at timestamptz NOT NULL,
  dependency_contract jsonb NOT NULL CHECK (
    dependency_contract->>'schema_name' = 'qc2.integrity_build.ArtifactDependency.v1'
    AND dependency_contract->>'schema_version' = '1.0'
    AND dependency_contract->>'owning_authority' = 'model_registry'
    AND dependency_contract->>'id' = id::text
    AND dependency_contract->>'dependency_role' = dependency_role
    AND dependency_contract->>'required_for_retention' = required_for_retention::text
    AND dependency_contract->'parent_ref'->>'target_id' = parent_manifest_id::text
    AND dependency_contract->'parent_ref'->>'content_hash' = parent_manifest_hash
    AND dependency_contract->'dependency_ref'->>'target_id' = dependency_manifest_id::text
    AND dependency_contract->'dependency_ref'->>'content_hash' = dependency_manifest_hash
    AND (dependency_contract->>'discovered_at')::timestamptz = discovered_at
  ),
  FOREIGN KEY (parent_manifest_id, parent_manifest_hash)
    REFERENCES qc2_integrity_build.model_artifact_manifest(id, content_hash)
    ON DELETE RESTRICT,
  FOREIGN KEY (dependency_manifest_id, dependency_manifest_hash)
    REFERENCES qc2_integrity_build.model_artifact_manifest(id, content_hash)
    ON DELETE RESTRICT,
  CHECK (
    (parent_manifest_id, parent_manifest_hash)
    <> (dependency_manifest_id, dependency_manifest_hash)
  ),
  UNIQUE (
    parent_manifest_id,
    parent_manifest_hash,
    dependency_manifest_id,
    dependency_manifest_hash,
    dependency_role
  )
);

CREATE TABLE qc2_models_prediction.model_lifecycle_event (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  prior_state text CHECK (
    prior_state IS NULL OR prior_state IN (
      'RESEARCH', 'CANDIDATE', 'CHALLENGER', 'SHADOW',
      'PROMOTION_ELIGIBLE', 'CHAMPION', 'REJECTED', 'RETIRED'
    )
  ),
  next_state text NOT NULL CHECK (
    next_state IN (
      'RESEARCH', 'CANDIDATE', 'CHALLENGER', 'SHADOW',
      'PROMOTION_ELIGIBLE', 'CHAMPION', 'REJECTED', 'RETIRED'
    )
  ),
  evidence_ref jsonb NOT NULL,
  runtime_authority text NOT NULL CHECK (runtime_authority ~ '^[a-z][a-z0-9_]*$'),
  transitioned_at timestamptz NOT NULL,
  FOREIGN KEY (model_id, model_hash)
    REFERENCES qc2_models_prediction.model_registry_model(id, content_hash)
    ON DELETE RESTRICT,
  UNIQUE (model_id, model_hash, sequence_no),
  CHECK (
    jsonb_typeof(evidence_ref) = 'object'
    AND evidence_ref->>'target_schema_name' LIKE 'qc2.%'
    AND evidence_ref->>'target_id' ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    AND evidence_ref->>'content_hash' ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE qc2_models_prediction.model_retention_reference (
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  retaining_ref jsonb NOT NULL,
  purpose text NOT NULL CHECK (purpose ~ '^[a-z][a-z0-9_-]{0,95}$'),
  linked_at timestamptz NOT NULL,
  FOREIGN KEY (model_id, model_hash)
    REFERENCES qc2_models_prediction.model_registry_model(id, content_hash)
    ON DELETE RESTRICT,
  CHECK (
    jsonb_typeof(retaining_ref) = 'object'
    AND retaining_ref->>'target_schema_name' IN (
      'qc2.models_prediction.Prediction.v1',
      'qc2.models_prediction.PredictionSeal.v1'
    )
    AND retaining_ref->>'target_id' ~
      '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    AND retaining_ref->>'content_hash' ~ '^[0-9a-f]{64}$'
  ),
  UNIQUE (model_id, model_hash, retaining_ref)
);

CREATE TABLE qc2_governance_owner.champion_pointer (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL CHECK (
    epoch_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  role text NOT NULL CHECK (role IN ('OPERATING', 'REFERENCE')),
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  generation integer NOT NULL CHECK (generation > 0),
  pointer_hash text NOT NULL CHECK (pointer_hash ~ '^[0-9a-f]{64}$'),
  evidence_class text NOT NULL CHECK (
    evidence_class IN (
      'SYNTHETIC_FIXTURE',
      'HISTORICAL_RECONSTRUCTED',
      'FORWARD_OPERATIONAL',
      'FORWARD_SEALED'
    )
  ),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development', 'test', 'research', 'production')
  ),
  created_at timestamptz NOT NULL,
  pointer_contract jsonb NOT NULL CHECK (
    pointer_contract->>'schema_name' = 'qc2.governance_owner.ChampionPointer.v1'
    AND pointer_contract->>'schema_version' = '1.0'
    AND pointer_contract->>'owning_authority' = 'promotion'
    AND pointer_contract->>'id' = id::text
    AND pointer_contract->>'role' = role
    AND pointer_contract->'model_ref'->>'target_id' = model_id::text
    AND pointer_contract->'model_ref'->>'content_hash' = model_hash
    AND pointer_contract->'epoch_ref'->>'target_id' = epoch_id::text
    AND pointer_contract->>'generation' = generation::text
    AND pointer_contract->>'pointer_hash' = pointer_hash
    AND pointer_contract->>'evidence_class' = evidence_class
    AND pointer_contract->>'environment_namespace' = environment_namespace
    AND (pointer_contract->>'created_at')::timestamptz = created_at
  ),
  FOREIGN KEY (model_id, model_hash)
    REFERENCES qc2_models_prediction.model_registry_model(id, content_hash)
    ON DELETE RESTRICT,
  UNIQUE (epoch_id, role, generation)
);

CREATE UNIQUE INDEX champion_pointer_single_reference_per_epoch
  ON qc2_governance_owner.champion_pointer(epoch_id)
  WHERE role = 'REFERENCE';

CREATE TABLE qc2_governance_owner.operating_pointer_slot (
  epoch_id uuid PRIMARY KEY CHECK (
    epoch_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  slot_state text NOT NULL CHECK (slot_state IN ('NO_CHAMPION', 'CHAMPION_SET')),
  pointer_id uuid UNIQUE
    REFERENCES qc2_governance_owner.champion_pointer(id) ON DELETE RESTRICT,
  model_id uuid,
  model_hash text CHECK (model_hash IS NULL OR model_hash ~ '^[0-9a-f]{64}$'),
  generation integer NOT NULL CHECK (generation >= 0),
  FOREIGN KEY (model_id, model_hash)
    REFERENCES qc2_models_prediction.model_registry_model(id, content_hash)
    ON DELETE RESTRICT,
  CHECK (
    (
      slot_state = 'NO_CHAMPION'
      AND pointer_id IS NULL
      AND model_id IS NULL
      AND model_hash IS NULL
      AND generation = 0
    )
    OR
    (
      slot_state = 'CHAMPION_SET'
      AND pointer_id IS NOT NULL
      AND model_id IS NOT NULL
      AND model_hash IS NOT NULL
      AND generation > 0
    )
  )
);

CREATE FUNCTION qc2_integrity_build.prevent_registry_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_integrity_build
AS $function$
BEGIN
  RAISE EXCEPTION 'model artifact and dependency records are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE FUNCTION qc2_models_prediction.guard_model_registry_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_models_prediction
AS $function$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
     OR NEW.artifact_manifest_id IS DISTINCT FROM OLD.artifact_manifest_id
     OR NEW.artifact_manifest_hash IS DISTINCT FROM OLD.artifact_manifest_hash
     OR NEW.evidence_class IS DISTINCT FROM OLD.evidence_class
     OR NEW.environment_namespace IS DISTINCT FROM OLD.environment_namespace
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.model_contract IS DISTINCT FROM OLD.model_contract THEN
    RAISE EXCEPTION 'registered model contract and artifact references are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NEW.lifecycle_state IS DISTINCT FROM OLD.lifecycle_state
     AND pg_catalog.current_setting('qc2.model_lifecycle_transition', true)
       IS DISTINCT FROM 'authorized' THEN
    RAISE EXCEPTION 'lifecycle projection changes require the typed transition function'
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_governance_owner.guard_operating_pointer_slot()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
DECLARE
  pointer_row qc2_governance_owner.champion_pointer%ROWTYPE;
BEGIN
  IF NEW.slot_state = 'CHAMPION_SET' THEN
    SELECT * INTO STRICT pointer_row
    FROM qc2_governance_owner.champion_pointer
    WHERE id = NEW.pointer_id;
    IF pointer_row.role <> 'OPERATING'
       OR pointer_row.epoch_id <> NEW.epoch_id
       OR pointer_row.model_id <> NEW.model_id
       OR pointer_row.model_hash <> NEW.model_hash
       OR pointer_row.generation <> NEW.generation THEN
      RAISE EXCEPTION 'operating pointer slot must match one OPERATING ChampionPointer'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_models_prediction.register_verified_model(
  p_model jsonb,
  p_artifacts jsonb,
  p_blob_receipts jsonb,
  p_storage_receipts jsonb,
  p_dependencies jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_models_prediction, qc2_integrity_build, qc2_control
AS $function$
DECLARE
  v_model_id uuid;
  v_artifact jsonb;
  v_file jsonb;
  v_receipt jsonb;
  v_storage jsonb;
  v_dependency jsonb;
  v_ordered_files jsonb;
  v_basis jsonb;
  v_actual_hash text;
  v_expected_hash text;
  v_verify_hash text;
  v_blob_ack_rows jsonb;
  v_backend text;
  v_ref jsonb;
  v_primary_id uuid;
  v_primary_hash text;
  v_row_count integer;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('model_registry');
  IF jsonb_typeof(p_model) <> 'object'
     OR jsonb_typeof(p_artifacts) <> 'array'
     OR jsonb_typeof(p_blob_receipts) <> 'array'
     OR jsonb_typeof(p_storage_receipts) <> 'array'
     OR jsonb_typeof(p_dependencies) <> 'array' THEN
    RAISE EXCEPTION 'verified model registration inputs must be JSON objects and arrays'
      USING ERRCODE = '22023';
  END IF;
  IF p_model->>'schema_name' <> 'qc2.models_prediction.ModelManifest.v1'
     OR p_model->>'schema_version' <> '1.0'
     OR p_model->>'owning_authority' <> 'model_registry'
     OR p_model->>'safe_format' <> 'json'
     OR p_model->>'lifecycle_state' <> 'RESEARCH' THEN
    RAISE EXCEPTION 'only a model_registry-owned RESEARCH JSON manifest may be registered'
      USING ERRCODE = '22023';
  END IF;
  v_model_id := (p_model->>'id')::uuid;
  IF v_model_id::text !~
    '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'ModelManifest id must be UUIDv7' USING ERRCODE = '22023';
  END IF;
  v_basis := p_model - ARRAY[
    'content_hash', 'created_at', 'id', 'schema_name', 'schema_version', 'lifecycle_state'
  ]::text[];
  v_expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.models_prediction.modelmanifest.v1/1.0',
    v_basis
  );
  IF p_model->>'content_hash' IS DISTINCT FROM v_expected_hash THEN
    RAISE EXCEPTION 'ModelManifest content hash is invalid' USING ERRCODE = '22023';
  END IF;
  IF (p_model->>'environment_namespace') = 'production'
     AND p_model->>'evidence_class' <> 'FORWARD_SEALED' THEN
    RAISE EXCEPTION 'production ModelManifest requires FORWARD_SEALED evidence'
      USING ERRCODE = '42501';
  END IF;
  IF pg_catalog.jsonb_array_length(p_artifacts) = 0
     OR pg_catalog.jsonb_array_length(p_storage_receipts)
       <> pg_catalog.jsonb_array_length(p_artifacts) THEN
    RAISE EXCEPTION 'each staged artifact manifest requires exactly one storage receipt'
      USING ERRCODE = '22023';
  END IF;

  FOR v_receipt IN
    SELECT value FROM pg_catalog.jsonb_array_elements(p_blob_receipts)
  LOOP
    IF v_receipt->>'sha256' !~ '^[0-9a-f]{64}$'
       OR (v_receipt->>'byte_count')::bigint <= 0
       OR v_receipt->>'object_key' IS NULL
       OR v_receipt->>'storage_backend' NOT IN (
         'fixture_memory', 'local_cache', 'external_object_store'
       ) THEN
      RAISE EXCEPTION 'staged blob receipt is malformed' USING ERRCODE = '22023';
    END IF;
    IF v_receipt->>'storage_backend' = 'external_object_store'
       AND COALESCE(v_receipt->>'durability_receipt', '') = '' THEN
      RAISE EXCEPTION 'external object storage must acknowledge durable blob writes'
        USING ERRCODE = '22023';
    END IF;
    INSERT INTO qc2_integrity_build.model_artifact_blob (
      sha256, storage_backend, object_key, byte_count, durability_receipt, staged_at
    )
    VALUES (
      v_receipt->>'sha256',
      v_receipt->>'storage_backend',
      v_receipt->>'object_key',
      (v_receipt->>'byte_count')::bigint,
      NULLIF(v_receipt->>'durability_receipt', ''),
      (v_receipt->>'staged_at')::timestamptz
    )
    ON CONFLICT (sha256, storage_backend) DO NOTHING;

    IF NOT EXISTS (
      SELECT 1
      FROM qc2_integrity_build.model_artifact_blob AS blob
      WHERE blob.sha256 = v_receipt->>'sha256'
        AND blob.storage_backend = v_receipt->>'storage_backend'
        AND blob.object_key = v_receipt->>'object_key'
        AND blob.byte_count = (v_receipt->>'byte_count')::bigint
        AND blob.durability_receipt IS NOT DISTINCT FROM
          NULLIF(v_receipt->>'durability_receipt', '')
    ) THEN
      RAISE EXCEPTION 'content-addressed blob metadata conflicts with an existing object'
        USING ERRCODE = '23505';
    END IF;
  END LOOP;

  FOR v_artifact IN
    SELECT value FROM pg_catalog.jsonb_array_elements(p_artifacts)
  LOOP
    IF v_artifact->>'schema_name' <> 'qc2.integrity_build.ArtifactManifest.v1'
       OR v_artifact->>'schema_version' <> '1.0'
       OR v_artifact->>'owning_authority' <> 'model_registry'
       OR v_artifact->>'evidence_class' IS DISTINCT FROM p_model->>'evidence_class'
       OR v_artifact->>'environment_namespace'
         IS DISTINCT FROM p_model->>'environment_namespace'
       OR jsonb_typeof(v_artifact->'files') <> 'array'
       OR pg_catalog.jsonb_array_length(v_artifact->'files') = 0 THEN
      RAISE EXCEPTION 'ArtifactManifest is malformed or has a different evidence context'
        USING ERRCODE = '22023';
    END IF;
    SELECT pg_catalog.jsonb_agg(file_row ORDER BY file_row->>'relative_path' COLLATE "C")
    INTO v_ordered_files
    FROM pg_catalog.jsonb_array_elements(v_artifact->'files') AS files(file_row);
    v_actual_hash := qc2_integrity_build.hash_json(
      'qc2.artifact-inventory.v1',
      v_ordered_files
    );
    IF v_artifact->>'inventory_hash' IS DISTINCT FROM v_actual_hash THEN
      RAISE EXCEPTION 'ArtifactManifest inventory hash is invalid' USING ERRCODE = '22023';
    END IF;
    v_basis := (
      v_artifact - ARRAY[
        'content_hash', 'created_at', 'id', 'schema_name', 'schema_version',
        'detached_signature', 'transport_hash'
      ]::text[]
    ) || pg_catalog.jsonb_build_object('files', v_ordered_files);
    v_expected_hash := qc2_integrity_build.hash_json(
      'qc2.contract-content.v1/qc2.integrity_build.artifactmanifest.v1/1.0',
      v_basis
    );
    IF v_artifact->>'content_hash' IS DISTINCT FROM v_expected_hash THEN
      RAISE EXCEPTION 'ArtifactManifest content hash is invalid' USING ERRCODE = '22023';
    END IF;
    SELECT receipt INTO v_storage
    FROM (
      SELECT value AS receipt
      FROM pg_catalog.jsonb_array_elements(p_storage_receipts)
    ) AS receipts
    WHERE receipt->>'manifest_id' = v_artifact->>'id'
      AND receipt->>'manifest_hash' = v_artifact->>'content_hash';
    IF v_storage IS NULL
       OR v_storage->>'verification_state' <> 'FULL_VERIFIED'
       OR v_storage->>'verification_hash' !~ '^[0-9a-f]{64}$'
       OR v_storage->>'storage_backend' NOT IN (
         'fixture_memory', 'local_cache', 'external_object_store'
       ) THEN
      RAISE EXCEPTION 'artifact is not fully verified or lacks a storage receipt'
        USING ERRCODE = '22023';
    END IF;
    v_backend := v_storage->>'storage_backend';
    IF (p_model->>'environment_namespace') = 'production'
       AND (
         v_backend <> 'external_object_store'
         OR COALESCE(v_storage->>'durability_receipt', '') = ''
       ) THEN
      RAISE EXCEPTION 'production artifacts require acknowledged durable object storage'
        USING ERRCODE = '42501';
    END IF;
    IF v_backend = 'external_object_store' THEN
      SELECT pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'sha256', receipt->>'sha256',
          'object_key', receipt->>'object_key',
          'durability_receipt', receipt->>'durability_receipt'
        )
        ORDER BY receipt->>'sha256' COLLATE "C", receipt->>'object_key' COLLATE "C"
      )
      INTO v_blob_ack_rows
      FROM pg_catalog.jsonb_array_elements(p_blob_receipts) AS receipts(receipt)
      WHERE receipt->>'manifest_id' = v_artifact->>'id'
        AND receipt->>'manifest_hash' = v_artifact->>'content_hash'
        AND receipt->>'storage_backend' = v_backend;
      IF v_blob_ack_rows IS NULL
         OR pg_catalog.jsonb_array_length(v_blob_ack_rows)
           <> pg_catalog.jsonb_array_length(v_artifact->'files')
         OR v_storage->>'durability_receipt' IS DISTINCT FROM
           qc2_integrity_build.hash_json(
             'qc2.model-artifact-storage-ack.v1',
             v_blob_ack_rows
           ) THEN
        RAISE EXCEPTION 'durability receipt does not bind every artifact object'
          USING ERRCODE = '22023';
      END IF;
    END IF;
    v_verify_hash := qc2_integrity_build.hash_json(
      'qc2.model-artifact-verification.v1',
      pg_catalog.jsonb_build_object(
        'manifest_id', v_artifact->>'id',
        'manifest_content_hash', v_artifact->>'content_hash',
        'files', v_ordered_files,
        'storage_backend', v_backend,
        'durability_receipt', COALESCE(v_storage->>'durability_receipt', '')
      )
    );
    IF v_storage->>'verification_hash' IS DISTINCT FROM v_verify_hash THEN
      RAISE EXCEPTION 'artifact full-verification receipt does not match its contents'
        USING ERRCODE = '22023';
    END IF;
    IF v_artifact->>'environment_namespace' = 'production'
       AND (
         v_artifact->>'evidence_class' <> 'FORWARD_SEALED'
         OR v_backend <> 'external_object_store'
       ) THEN
      RAISE EXCEPTION 'production ArtifactManifest requires durable FORWARD_SEALED storage'
        USING ERRCODE = '42501';
    END IF;
    INSERT INTO qc2_integrity_build.model_artifact_manifest (
      id, content_hash, inventory_hash, evidence_class, environment_namespace,
      storage_backend, durability_receipt, verification_hash, created_at, manifest_contract
    )
    VALUES (
      (v_artifact->>'id')::uuid,
      v_artifact->>'content_hash',
      v_artifact->>'inventory_hash',
      v_artifact->>'evidence_class',
      v_artifact->>'environment_namespace',
      v_backend,
      NULLIF(v_storage->>'durability_receipt', ''),
      v_verify_hash,
      (v_artifact->>'created_at')::timestamptz,
      v_artifact
    );
    FOR v_file IN
      SELECT value FROM pg_catalog.jsonb_array_elements(v_artifact->'files')
    LOOP
      IF v_file->>'media_type' <> 'application/json'
         OR v_file->>'schema_version' <> '1.0'
         OR v_file->>'schema_name' NOT IN (
           'qc2.apexlab.SafeModelArtifact.v1',
           'qc2.apexlab.TrainingEnvironment.v1',
           'qc2.apexlab.FrozenHyperparameterSpace.v1'
         )
         OR v_file->>'relative_path' !~ '^[A-Za-z0-9._/-]+[.]json$'
         OR v_file->>'relative_path' ~ '(^/|(^|/)[.][.]?(/|$)|//|:)'
         OR NOT EXISTS (
           SELECT 1
           FROM qc2_integrity_build.model_artifact_blob AS blob
           WHERE blob.sha256 = v_file->>'sha256'
             AND blob.byte_count = (v_file->>'length_bytes')::bigint
             AND blob.storage_backend = v_backend
         ) THEN
        RAISE EXCEPTION 'artifact file is unsafe or lacks a matching staged blob'
          USING ERRCODE = '22023';
      END IF;
      INSERT INTO qc2_integrity_build.model_artifact_manifest_file (
        manifest_id, manifest_hash, relative_path, sha256, byte_count,
        media_type, schema_name, schema_version
      )
      VALUES (
        (v_artifact->>'id')::uuid,
        v_artifact->>'content_hash',
        v_file->>'relative_path',
        v_file->>'sha256',
        (v_file->>'length_bytes')::bigint,
        v_file->>'media_type',
        v_file->>'schema_name',
        v_file->>'schema_version'
      );
    END LOOP;
  END LOOP;

  v_primary_id := (p_model->'artifact_manifest_ref'->>'target_id')::uuid;
  v_primary_hash := p_model->'artifact_manifest_ref'->>'content_hash';
  IF p_model->'artifact_manifest_ref'->>'target_schema_name'
       <> 'qc2.integrity_build.ArtifactManifest.v1'
     OR NOT EXISTS (
       SELECT 1
       FROM qc2_integrity_build.model_artifact_manifest AS artifact
       WHERE artifact.id = v_primary_id
         AND artifact.content_hash = v_primary_hash
         AND artifact.evidence_class = p_model->>'evidence_class'
         AND artifact.environment_namespace = p_model->>'environment_namespace'
     ) THEN
    RAISE EXCEPTION 'ModelManifest primary ArtifactManifest reference is unregistered'
      USING ERRCODE = '23503';
  END IF;
  FOR v_ref IN
    SELECT value
    FROM pg_catalog.jsonb_array_elements(COALESCE(p_model->'source_refs', '[]'::jsonb))
    WHERE value->>'target_schema_name' = 'qc2.integrity_build.ArtifactManifest.v1'
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM qc2_integrity_build.model_artifact_manifest AS artifact
      WHERE artifact.id = (v_ref->>'target_id')::uuid
        AND artifact.content_hash = v_ref->>'content_hash'
    ) THEN
      RAISE EXCEPTION 'ModelManifest source references an unstaged ArtifactManifest'
        USING ERRCODE = '23503';
    END IF;
  END LOOP;

  FOR v_dependency IN
    SELECT value FROM pg_catalog.jsonb_array_elements(p_dependencies)
  LOOP
    IF v_dependency->>'schema_name' <> 'qc2.integrity_build.ArtifactDependency.v1'
       OR v_dependency->>'owning_authority' <> 'model_registry'
       OR v_dependency->>'evidence_class' IS DISTINCT FROM p_model->>'evidence_class'
       OR v_dependency->>'environment_namespace'
         IS DISTINCT FROM p_model->>'environment_namespace' THEN
      RAISE EXCEPTION 'ArtifactDependency authority or evidence context is invalid'
        USING ERRCODE = '22023';
    END IF;
    IF EXISTS (
      WITH RECURSIVE reachable(manifest_id, manifest_hash) AS (
        SELECT
          (v_dependency->'dependency_ref'->>'target_id')::uuid,
          v_dependency->'dependency_ref'->>'content_hash'
        UNION
        SELECT edge.dependency_manifest_id, edge.dependency_manifest_hash
        FROM qc2_integrity_build.model_artifact_dependency AS edge
        JOIN reachable
          ON edge.parent_manifest_id = reachable.manifest_id
         AND edge.parent_manifest_hash = reachable.manifest_hash
      )
      SELECT 1
      FROM reachable
      WHERE manifest_id = (v_dependency->'parent_ref'->>'target_id')::uuid
        AND manifest_hash = v_dependency->'parent_ref'->>'content_hash'
    ) THEN
      RAISE EXCEPTION 'ArtifactDependency would create a retention cycle'
        USING ERRCODE = '23514';
    END IF;
    INSERT INTO qc2_integrity_build.model_artifact_dependency (
      id, parent_manifest_id, parent_manifest_hash,
      dependency_manifest_id, dependency_manifest_hash,
      dependency_role, required_for_retention, discovered_at, dependency_contract
    )
    VALUES (
      (v_dependency->>'id')::uuid,
      (v_dependency->'parent_ref'->>'target_id')::uuid,
      v_dependency->'parent_ref'->>'content_hash',
      (v_dependency->'dependency_ref'->>'target_id')::uuid,
      v_dependency->'dependency_ref'->>'content_hash',
      v_dependency->>'dependency_role',
      (v_dependency->>'required_for_retention')::boolean,
      (v_dependency->>'discovered_at')::timestamptz,
      v_dependency
    );
  END LOOP;

  INSERT INTO qc2_models_prediction.model_registry_model (
    id, content_hash, artifact_manifest_id, artifact_manifest_hash,
    evidence_class, environment_namespace, lifecycle_state, created_at, model_contract
  )
  VALUES (
    v_model_id,
    p_model->>'content_hash',
    v_primary_id,
    v_primary_hash,
    p_model->>'evidence_class',
    p_model->>'environment_namespace',
    'RESEARCH',
    (p_model->>'created_at')::timestamptz,
    p_model
  );
  INSERT INTO qc2_models_prediction.model_lifecycle_event (
    model_id, model_hash, sequence_no, prior_state, next_state,
    evidence_ref, runtime_authority, transitioned_at
  )
  VALUES (
    v_model_id,
    p_model->>'content_hash',
    1,
    NULL,
    'RESEARCH',
    p_model->'artifact_manifest_ref',
    'model_registry',
    (p_model->>'created_at')::timestamptz
  );
  RETURN v_model_id;
END
$function$;

CREATE FUNCTION qc2_models_prediction.record_model_lifecycle_transition(
  p_model_id uuid,
  p_expected_state text,
  p_next_state text,
  p_evidence jsonb,
  p_transitioned_at timestamptz
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_models_prediction, qc2_control
AS $function$
DECLARE
  v_authority text;
  v_model qc2_models_prediction.model_registry_model%ROWTYPE;
  v_evidence_ref jsonb;
  v_expected_ref jsonb;
  v_sequence integer;
BEGIN
  v_authority := qc2_control.current_runtime_authority();
  IF p_evidence IS NULL OR jsonb_typeof(p_evidence) <> 'object' THEN
    RAISE EXCEPTION 'typed lifecycle evidence is required' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO STRICT v_model
  FROM qc2_models_prediction.model_registry_model
  WHERE id = p_model_id
  FOR UPDATE;
  IF v_model.lifecycle_state <> p_expected_state THEN
    RAISE EXCEPTION 'model lifecycle state changed concurrently'
      USING ERRCODE = '40001';
  END IF;
  IF (
    CASE p_expected_state
    WHEN 'RESEARCH' THEN p_next_state IN ('CANDIDATE', 'REJECTED')
    WHEN 'CANDIDATE' THEN p_next_state IN ('CHALLENGER', 'REJECTED')
    WHEN 'CHALLENGER' THEN p_next_state IN ('SHADOW', 'REJECTED')
    WHEN 'SHADOW' THEN p_next_state IN ('PROMOTION_ELIGIBLE', 'REJECTED', 'RETIRED')
    WHEN 'PROMOTION_ELIGIBLE' THEN p_next_state IN ('CHAMPION', 'REJECTED', 'RETIRED')
    WHEN 'CHAMPION' THEN p_next_state = 'RETIRED'
    ELSE false
    END
  ) IS NOT TRUE THEN
    RAISE EXCEPTION 'illegal model lifecycle transition'
      USING ERRCODE = '23514';
  END IF;

  IF p_next_state = 'CHAMPION' THEN
    RAISE EXCEPTION 'Champion lifecycle and pointer changes require Promotion atomic commit'
      USING ERRCODE = '42501';
  ELSIF p_next_state = 'CANDIDATE' THEN
    IF v_authority IS DISTINCT FROM 'validation'
       OR p_evidence->>'schema_name' IS DISTINCT FROM
         'qc2.outcomes_research.CandidateEvaluation.v1'
       OR p_evidence->>'owning_authority' IS DISTINCT FROM 'validation'
       OR p_evidence->>'verdict' IS DISTINCT FROM 'PASS'
       OR p_evidence->'candidate_ref'->>'target_id' <> v_model.id::text
       OR p_evidence->'candidate_ref'->>'content_hash' <> v_model.content_hash THEN
      RAISE EXCEPTION 'CANDIDATE requires a passing independent CandidateEvaluation'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_next_state = 'CHALLENGER' THEN
    IF v_authority IS DISTINCT FROM 'validation'
       OR p_evidence->>'schema_name' IS DISTINCT FROM
         'qc2.outcomes_research.ChallengerEvaluation.v1'
       OR p_evidence->>'owning_authority' IS DISTINCT FROM 'validation'
       OR p_evidence->>'verdict' IS DISTINCT FROM 'PASS'
       OR p_evidence->'challenger_ref'->>'target_id' <> v_model.id::text
       OR p_evidence->'challenger_ref'->>'content_hash' <> v_model.content_hash THEN
      RAISE EXCEPTION 'CHALLENGER requires a passing independent comparison'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_next_state = 'SHADOW' THEN
    IF v_authority IS DISTINCT FROM 'prediction'
       OR p_evidence->>'schema_name' IS DISTINCT FROM
         'qc2.models_prediction.ShadowPredictionSet.v1'
       OR p_evidence->>'owning_authority' IS DISTINCT FROM 'prediction'
       OR p_evidence->'model_ref'->>'target_id' <> v_model.id::text
       OR p_evidence->'model_ref'->>'content_hash' <> v_model.content_hash THEN
      RAISE EXCEPTION 'SHADOW requires a model-bound ShadowPredictionSet'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_next_state = 'PROMOTION_ELIGIBLE' THEN
    IF v_authority IS DISTINCT FROM 'validation'
       OR p_evidence->>'schema_name' IS DISTINCT FROM 'qc2.validation.ValidationReport.v1'
       OR p_evidence->>'owning_authority' IS DISTINCT FROM 'validation'
       OR p_evidence->>'verdict' IS DISTINCT FROM 'PASS'
       OR NOT (COALESCE(p_evidence->'source_refs', '[]'::jsonb) @>
         pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
           'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
           'target_id', v_model.id::text,
           'content_hash', v_model.content_hash
         ))) THEN
      RAISE EXCEPTION 'PROMOTION_ELIGIBLE requires a passing bound ValidationReport'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_next_state = 'REJECTED' THEN
    IF v_authority IS DISTINCT FROM 'validation'
       OR p_evidence->>'owning_authority' IS DISTINCT FROM 'validation'
       OR p_evidence->>'verdict' IS NULL
       OR p_evidence->>'verdict' NOT IN (
         'FAIL', 'INSUFFICIENT_EVIDENCE', 'BLOCKED', 'NOT_INTERPRETABLE'
       ) THEN
      RAISE EXCEPTION 'REJECTED requires non-passing validation evidence'
        USING ERRCODE = '42501';
    END IF;
    IF COALESCE(
         p_evidence->'candidate_ref'->>'target_id',
         p_evidence->'challenger_ref'->>'target_id',
         p_evidence->'model_ref'->>'target_id'
       ) IS DISTINCT FROM v_model.id::text
       OR COALESCE(
         p_evidence->'candidate_ref'->>'content_hash',
         p_evidence->'challenger_ref'->>'content_hash',
         p_evidence->'model_ref'->>'content_hash'
       ) IS DISTINCT FROM v_model.content_hash THEN
      RAISE EXCEPTION 'rejection evidence refers to a different model'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_next_state = 'RETIRED' THEN
    IF v_authority NOT IN ('model_registry', 'promotion')
       OR (v_model.lifecycle_state = 'CHAMPION' AND v_authority <> 'promotion')
       OR (v_authority = 'promotion'
           AND p_evidence->>'schema_name' <> 'qc2.governance_owner.PromotionReceipt.v1') THEN
      RAISE EXCEPTION 'retirement authority or receipt is invalid'
        USING ERRCODE = '42501';
    END IF;
  END IF;

  v_evidence_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', p_evidence->>'schema_name',
    'target_id', p_evidence->>'id',
    'content_hash', COALESCE(p_evidence->>'content_hash', p_evidence->>'report_hash')
  );
  IF v_evidence_ref->>'target_schema_name' IS NULL
     OR v_evidence_ref->>'target_id' !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR v_evidence_ref->>'content_hash' !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'lifecycle evidence reference is not content-bound'
      USING ERRCODE = '22023';
  END IF;
  SELECT COALESCE(pg_catalog.max(sequence_no), 0) + 1
  INTO v_sequence
  FROM qc2_models_prediction.model_lifecycle_event
  WHERE model_id = v_model.id AND model_hash = v_model.content_hash;
  PERFORM pg_catalog.set_config('qc2.model_lifecycle_transition', 'authorized', true);
  UPDATE qc2_models_prediction.model_registry_model
  SET lifecycle_state = p_next_state
  WHERE id = v_model.id;
  INSERT INTO qc2_models_prediction.model_lifecycle_event (
    model_id, model_hash, sequence_no, prior_state, next_state,
    evidence_ref, runtime_authority, transitioned_at
  )
  VALUES (
    v_model.id, v_model.content_hash, v_sequence, v_model.lifecycle_state, p_next_state,
    v_evidence_ref, v_authority, p_transitioned_at
  );
  RETURN v_sequence;
END
$function$;

CREATE FUNCTION qc2_models_prediction.record_model_retention_reference(
  p_model_id uuid,
  p_model_hash text,
  p_retaining_ref jsonb,
  p_purpose text,
  p_linked_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_models_prediction, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('model_registry');
  IF jsonb_typeof(p_retaining_ref) <> 'object'
     OR p_retaining_ref->>'target_schema_name' NOT IN (
       'qc2.models_prediction.Prediction.v1',
       'qc2.models_prediction.PredictionSeal.v1'
     )
     OR p_retaining_ref->>'target_id' !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_retaining_ref->>'content_hash' !~ '^[0-9a-f]{64}$'
     OR p_purpose !~ '^[a-z][a-z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'retention target or purpose is invalid' USING ERRCODE = '22023';
  END IF;
  INSERT INTO qc2_models_prediction.model_retention_reference (
    model_id, model_hash, retaining_ref, purpose, linked_at
  )
  VALUES (p_model_id, p_model_hash, p_retaining_ref, p_purpose, p_linked_at);
END
$function$;

CREATE TRIGGER model_artifact_blob_append_only
  BEFORE UPDATE OR DELETE ON qc2_integrity_build.model_artifact_blob
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_artifact_manifest_append_only
  BEFORE UPDATE OR DELETE ON qc2_integrity_build.model_artifact_manifest
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_artifact_manifest_file_append_only
  BEFORE UPDATE OR DELETE ON qc2_integrity_build.model_artifact_manifest_file
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_artifact_dependency_append_only
  BEFORE UPDATE OR DELETE ON qc2_integrity_build.model_artifact_dependency
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_registry_model_update_guard
  BEFORE UPDATE ON qc2_models_prediction.model_registry_model
  FOR EACH ROW EXECUTE FUNCTION qc2_models_prediction.guard_model_registry_update();
CREATE TRIGGER model_registry_model_no_delete
  BEFORE DELETE ON qc2_models_prediction.model_registry_model
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_lifecycle_event_append_only
  BEFORE UPDATE OR DELETE ON qc2_models_prediction.model_lifecycle_event
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER model_retention_reference_append_only
  BEFORE UPDATE OR DELETE ON qc2_models_prediction.model_retention_reference
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER champion_pointer_append_only
  BEFORE UPDATE OR DELETE ON qc2_governance_owner.champion_pointer
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();
CREATE TRIGGER operating_pointer_slot_guard
  BEFORE INSERT OR UPDATE ON qc2_governance_owner.operating_pointer_slot
  FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.guard_operating_pointer_slot();
CREATE TRIGGER operating_pointer_slot_no_delete
  BEFORE DELETE ON qc2_governance_owner.operating_pointer_slot
  FOR EACH ROW EXECUTE FUNCTION qc2_integrity_build.prevent_registry_record_mutation();

ALTER TABLE qc2_integrity_build.model_artifact_blob ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_blob FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_manifest FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_manifest_file ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_manifest_file FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_dependency ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_integrity_build.model_artifact_dependency FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_registry_model ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_registry_model FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_lifecycle_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_lifecycle_event FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_retention_reference ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_models_prediction.model_retention_reference FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.champion_pointer ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.champion_pointer FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.operating_pointer_slot ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.operating_pointer_slot FORCE ROW LEVEL SECURITY;

CREATE POLICY model_artifact_blob_migrator_all
  ON qc2_integrity_build.model_artifact_blob
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_artifact_manifest_migrator_all
  ON qc2_integrity_build.model_artifact_manifest
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_artifact_manifest_file_migrator_all
  ON qc2_integrity_build.model_artifact_manifest_file
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_artifact_dependency_migrator_all
  ON qc2_integrity_build.model_artifact_dependency
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_registry_model_migrator_all
  ON qc2_models_prediction.model_registry_model
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_lifecycle_event_migrator_all
  ON qc2_models_prediction.model_lifecycle_event
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY model_retention_reference_migrator_all
  ON qc2_models_prediction.model_retention_reference
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY champion_pointer_migrator_all
  ON qc2_governance_owner.champion_pointer
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY operating_pointer_slot_migrator_all
  ON qc2_governance_owner.operating_pointer_slot
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

CREATE POLICY model_artifact_blob_read
  ON qc2_integrity_build.model_artifact_blob
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference
  USING (true);
CREATE POLICY model_artifact_manifest_read
  ON qc2_integrity_build.model_artifact_manifest
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY model_artifact_manifest_file_read
  ON qc2_integrity_build.model_artifact_manifest_file
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY model_artifact_dependency_read
  ON qc2_integrity_build.model_artifact_dependency
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY model_registry_model_read
  ON qc2_models_prediction.model_registry_model
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY model_lifecycle_event_read
  ON qc2_models_prediction.model_lifecycle_event
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence
  USING (true);
CREATE POLICY model_retention_reference_read
  ON qc2_models_prediction.model_retention_reference
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_prediction,
    qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_owner_api,
    qc2_runtime_evidence
  USING (true);
CREATE POLICY champion_pointer_read
  ON qc2_governance_owner.champion_pointer
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_execution, qc2_runtime_evidence
  USING (true);
CREATE POLICY operating_pointer_slot_read
  ON qc2_governance_owner.operating_pointer_slot
  FOR SELECT TO qc2_runtime_model_registry, qc2_runtime_inference,
    qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_promotion,
    qc2_runtime_owner_api, qc2_runtime_execution, qc2_runtime_evidence
  USING (true);

REVOKE ALL ON
  qc2_integrity_build.model_artifact_blob,
  qc2_integrity_build.model_artifact_manifest,
  qc2_integrity_build.model_artifact_manifest_file,
  qc2_integrity_build.model_artifact_dependency,
  qc2_models_prediction.model_registry_model,
  qc2_models_prediction.model_lifecycle_event,
  qc2_models_prediction.model_retention_reference,
  qc2_governance_owner.champion_pointer,
  qc2_governance_owner.operating_pointer_slot
FROM PUBLIC;
REVOKE ALL ON
  qc2_models_prediction.model_lifecycle_event_id_seq
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_models_prediction.register_verified_model(
  jsonb, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_models_prediction.record_model_lifecycle_transition(
  uuid, text, text, jsonb, timestamptz
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_models_prediction.record_model_retention_reference(
  uuid, text, jsonb, text, timestamptz
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_integrity_build.prevent_registry_record_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_models_prediction.guard_model_registry_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.guard_operating_pointer_slot() FROM PUBLIC;

GRANT SELECT ON
  qc2_integrity_build.model_artifact_blob
TO qc2_runtime_model_registry, qc2_runtime_inference;
GRANT SELECT ON
  qc2_integrity_build.model_artifact_manifest,
  qc2_integrity_build.model_artifact_manifest_file,
  qc2_integrity_build.model_artifact_dependency
TO qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
   qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_owner_api,
   qc2_runtime_apexlab, qc2_runtime_evidence;
GRANT SELECT ON
  qc2_models_prediction.model_registry_model,
  qc2_models_prediction.model_lifecycle_event
TO qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
   qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_owner_api,
   qc2_runtime_apexlab, qc2_runtime_evidence;
GRANT SELECT ON qc2_models_prediction.model_retention_reference
TO qc2_runtime_model_registry, qc2_runtime_prediction, qc2_runtime_validation,
   qc2_runtime_promotion, qc2_runtime_owner_api, qc2_runtime_evidence;
GRANT SELECT ON
  qc2_governance_owner.champion_pointer,
  qc2_governance_owner.operating_pointer_slot
TO qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
   qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_owner_api,
   qc2_runtime_execution, qc2_runtime_evidence;

GRANT EXECUTE ON FUNCTION qc2_models_prediction.register_verified_model(
  jsonb, jsonb, jsonb, jsonb, jsonb
) TO qc2_runtime_model_registry;
GRANT EXECUTE ON FUNCTION qc2_models_prediction.record_model_lifecycle_transition(
  uuid, text, text, jsonb, timestamptz
) TO qc2_runtime_model_registry, qc2_runtime_validation,
   qc2_runtime_prediction, qc2_runtime_promotion;
GRANT EXECUTE ON FUNCTION qc2_models_prediction.record_model_retention_reference(
  uuid, text, jsonb, text, timestamptz
) TO qc2_runtime_model_registry;

RESET ROLE;
