DO $check_environment$
BEGIN
  IF current_setting('server_encoding') <> 'UTF8' THEN
    RAISE EXCEPTION 'QC2-037 acceptance requires a UTF8 database';
  END IF;
END
$check_environment$;

DO $check_grants$
BEGIN
  IF NOT has_function_privilege(
       'qc2_runtime_model_registry',
       'qc2_models_prediction.register_verified_model(jsonb,jsonb,jsonb,jsonb,jsonb)',
       'EXECUTE'
     )
     OR NOT has_function_privilege(
       'qc2_runtime_model_registry',
       'qc2_integrity_build.canonical_jsonb_text(jsonb)',
       'EXECUTE'
     )
     OR has_function_privilege(
       'qc2_runtime_apexlab',
       'qc2_models_prediction.register_verified_model(jsonb,jsonb,jsonb,jsonb,jsonb)',
       'EXECUTE'
     )
     OR has_table_privilege(
       'qc2_runtime_apexlab',
       'qc2_governance_owner.champion_pointer',
       'INSERT'
     )
     OR has_table_privilege(
       'qc2_runtime_model_registry',
       'qc2_models_prediction.model_registry_model',
       'UPDATE'
     )
     OR NOT has_table_privilege(
       'qc2_runtime_inference',
       'qc2_governance_owner.champion_pointer',
       'SELECT'
     ) THEN
    RAISE EXCEPTION 'QC2-037 runtime grants violate registry or pointer ownership';
  END IF;
END
$check_grants$;

SET SESSION AUTHORIZATION qc2_runtime_model_registry;

DO $register_fixture$
DECLARE
  model_id uuid := '018f0000-0000-7000-8000-000000000037';
  artifact_id uuid := '018f0000-0000-7000-8000-000000000036';
  created text := '2026-10-08T12:00:00Z';
  object_hash text := pg_catalog.repeat('a', 64);
  file_inventory jsonb;
  artifact jsonb;
  artifact_ref jsonb;
  model jsonb;
  blob_receipts jsonb;
  storage_receipt jsonb;
  storage_receipts jsonb;
  dependencies jsonb := '[]'::jsonb;
  storage_ack text;
  verification_hash text;
  actual_id uuid;
BEGIN
  file_inventory := pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object(
      'relative_path', 'model.json',
      'length_bytes', 64,
      'media_type', 'application/json',
      'schema_name', 'qc2.apexlab.SafeModelArtifact.v1',
      'schema_version', '1.0',
      'sha256', object_hash
    )
  );
  artifact := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.integrity_build.ArtifactManifest.v1',
    'schema_version', '1.0',
    'id', artifact_id::text,
    'created_at', created,
    'owning_authority', 'model_registry',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'content_hash', pg_catalog.repeat('0', 64),
    'manifest_version', 1,
    'files', file_inventory,
    'inventory_hash', pg_catalog.repeat('0', 64),
    'detached_signature', NULL,
    'transport_hash', NULL
  );
  artifact := pg_catalog.jsonb_set(
    artifact,
    '{inventory_hash}',
    pg_catalog.to_jsonb(
      qc2_integrity_build.hash_json('qc2.artifact-inventory.v1', file_inventory)
    ),
    true
  );
  artifact := pg_catalog.jsonb_set(
    artifact,
    '{content_hash}',
    pg_catalog.to_jsonb(
      qc2_integrity_build.hash_json(
        'qc2.contract-content.v1/qc2.integrity_build.artifactmanifest.v1/1.0',
        artifact - ARRAY[
          'content_hash', 'created_at', 'id', 'schema_name', 'schema_version',
          'detached_signature', 'transport_hash'
        ]::text[]
      )
    ),
    true
  );
  artifact_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.integrity_build.ArtifactManifest.v1',
    'target_id', artifact_id::text,
    'content_hash', artifact->>'content_hash'
  );
  model := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.models_prediction.ModelManifest.v1',
    'schema_version', '1.0',
    'id', model_id::text,
    'created_at', created,
    'owning_authority', 'model_registry',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', pg_catalog.jsonb_build_array(artifact_ref),
    'content_hash', pg_catalog.repeat('0', 64),
    'artifact_manifest_ref', artifact_ref,
    'safe_format', 'json',
    'lifecycle_state', 'RESEARCH'
  );
  model := pg_catalog.jsonb_set(
    model,
    '{content_hash}',
    pg_catalog.to_jsonb(
      qc2_integrity_build.hash_json(
        'qc2.contract-content.v1/qc2.models_prediction.modelmanifest.v1/1.0',
        model - ARRAY[
          'content_hash', 'created_at', 'id', 'schema_name', 'schema_version',
          'lifecycle_state'
        ]::text[]
      )
    ),
    true
  );

  storage_ack := qc2_integrity_build.hash_json(
    'qc2.model-artifact-storage-ack.v1',
    pg_catalog.jsonb_build_array(
      pg_catalog.jsonb_build_object(
        'sha256', object_hash,
        'object_key', 'registry-acceptance/' || object_hash,
        'durability_receipt', 'fixture-object-version-00036'
      )
    )
  );
  verification_hash := qc2_integrity_build.hash_json(
    'qc2.model-artifact-verification.v1',
    pg_catalog.jsonb_build_object(
      'manifest_id', artifact_id::text,
      'manifest_content_hash', artifact->>'content_hash',
      'files', file_inventory,
      'storage_backend', 'external_object_store',
      'durability_receipt', storage_ack
    )
  );
  blob_receipts := pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object(
      'manifest_id', artifact_id::text,
      'manifest_hash', artifact->>'content_hash',
      'sha256', object_hash,
      'byte_count', 64,
      'storage_backend', 'external_object_store',
      'object_key', 'registry-acceptance/' || object_hash,
      'durability_receipt', 'fixture-object-version-00036',
      'staged_at', created
    )
  );
  storage_receipt := pg_catalog.jsonb_build_object(
    'manifest_id', artifact_id::text,
    'manifest_hash', artifact->>'content_hash',
    'storage_backend', 'external_object_store',
    'durability_receipt', storage_ack,
    'verification_state', 'FULL_VERIFIED',
    'verification_hash', verification_hash
  );
  storage_receipts := pg_catalog.jsonb_build_array(storage_receipt);

  actual_id := qc2_models_prediction.register_verified_model(
    model,
    pg_catalog.jsonb_build_array(artifact),
    blob_receipts,
    storage_receipts,
    dependencies
  );
  IF actual_id <> model_id THEN
    RAISE EXCEPTION 'QC2-037 registration returned the wrong model identity';
  END IF;

  PERFORM pg_catalog.set_config('qc2_test.model_id', model_id::text, true);
  PERFORM pg_catalog.set_config('qc2_test.model_hash', model->>'content_hash', true);
  PERFORM pg_catalog.set_config('qc2_test.artifact_id', artifact_id::text, true);
  PERFORM pg_catalog.set_config('qc2_test.artifact_hash', artifact->>'content_hash', true);
  PERFORM pg_catalog.set_config('qc2_test.epoch_id', '018f0000-0000-7000-8000-000000000038', true);

  BEGIN
    PERFORM qc2_models_prediction.register_verified_model(
      model,
      pg_catalog.jsonb_build_array(artifact),
      pg_catalog.jsonb_set(
        blob_receipts,
        '{0,object_key}',
        pg_catalog.to_jsonb('registry-acceptance/overwrite-attempt'::text),
        true
      ),
      storage_receipts,
      dependencies
    );
    RAISE EXCEPTION 'content-addressed artifact overwrite unexpectedly succeeded';
  EXCEPTION
    WHEN SQLSTATE '23505' THEN NULL;
  END;
END
$register_fixture$;

RESET SESSION AUTHORIZATION;

DO $check_persisted_model$
DECLARE
  fixture_model_id uuid := current_setting('qc2_test.model_id')::uuid;
  fixture_model_hash text := current_setting('qc2_test.model_hash');
  fixture_artifact_id uuid := current_setting('qc2_test.artifact_id')::uuid;
  fixture_artifact_hash text := current_setting('qc2_test.artifact_hash');
  fixture_epoch_id uuid := current_setting('qc2_test.epoch_id')::uuid;
  pointer_id uuid := '018f0000-0000-7000-8000-000000000039';
  model_ref jsonb;
  pointer_contract jsonb;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_models_prediction.model_registry_model AS model
    WHERE model.id = fixture_model_id
      AND model.content_hash = fixture_model_hash
      AND model.lifecycle_state = 'RESEARCH'
      AND model.artifact_manifest_id = fixture_artifact_id
      AND model.artifact_manifest_hash = fixture_artifact_hash
  ) OR NOT EXISTS (
    SELECT 1
    FROM qc2_models_prediction.model_lifecycle_event AS event
    WHERE event.model_id = fixture_model_id
      AND event.model_hash = fixture_model_hash
      AND event.next_state = 'RESEARCH'
      AND event.sequence_no = 1
  ) OR NOT EXISTS (
    SELECT 1
    FROM qc2_integrity_build.model_artifact_manifest_file AS file
    WHERE file.manifest_id = fixture_artifact_id
      AND file.manifest_hash = fixture_artifact_hash
      AND file.relative_path = 'model.json'
  ) THEN
    RAISE EXCEPTION 'QC2-037 registration did not persist a verified immutable reference';
  END IF;

  INSERT INTO qc2_governance_owner.operating_pointer_slot (
    epoch_id, slot_state, pointer_id, model_id, model_hash, generation
  )
  VALUES (fixture_epoch_id, 'NO_CHAMPION', NULL, NULL, NULL, 0);
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_governance_owner.operating_pointer_slot AS slot
    WHERE slot.epoch_id = fixture_epoch_id AND slot.slot_state = 'NO_CHAMPION'
  ) THEN
    RAISE EXCEPTION 'explicit NO_CHAMPION state was not preserved';
  END IF;

  model_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
    'target_id', fixture_model_id::text,
    'content_hash', fixture_model_hash
  );
  pointer_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.ChampionPointer.v1',
    'schema_version', '1.0',
    'id', pointer_id::text,
    'created_at', '2026-10-08T12:15:00Z',
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'epoch_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
      'target_id', fixture_epoch_id::text,
      'content_hash', pg_catalog.repeat('c', 64)
    ),
    'role', 'REFERENCE',
    'model_ref', model_ref,
    'generation', 1,
    'transitioned_at', '2026-10-08T12:16:00Z',
    'transition_receipt_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionReceipt.v1',
      'target_id', '018f0000-0000-7000-8000-000000000040',
      'content_hash', pg_catalog.repeat('d', 64)
    ),
    'pointer_hash', pg_catalog.repeat('e', 64)
  );
  INSERT INTO qc2_governance_owner.champion_pointer (
    id, epoch_id, role, model_id, model_hash, generation, pointer_hash,
    evidence_class, environment_namespace, created_at, pointer_contract
  )
  VALUES (
    pointer_id, fixture_epoch_id, 'REFERENCE',
    fixture_model_id, fixture_model_hash, 1,
    pg_catalog.repeat('e', 64), 'SYNTHETIC_FIXTURE', 'test',
    '2026-10-08T12:15:00Z', pointer_contract
  );

  BEGIN
    INSERT INTO qc2_governance_owner.champion_pointer (
      id, epoch_id, role, model_id, model_hash, generation, pointer_hash,
      evidence_class, environment_namespace, created_at, pointer_contract
    )
    VALUES (
      '018f0000-0000-7000-8000-000000000041', fixture_epoch_id, 'REFERENCE',
      fixture_model_id, fixture_model_hash, 2, pg_catalog.repeat('f', 64),
      'SYNTHETIC_FIXTURE', 'test', '2026-10-08T12:17:00Z',
      pg_catalog.jsonb_set(
        pg_catalog.jsonb_set(
          pg_catalog.jsonb_set(
            pg_catalog.jsonb_set(
              pointer_contract, '{id}',
              pg_catalog.to_jsonb(
                '018f0000-0000-7000-8000-000000000041'::text
              ), true
            ),
            '{generation}', '2'::jsonb, true
          ),
          '{created_at}',
          pg_catalog.to_jsonb('2026-10-08T12:17:00Z'::text),
          true
        ),
        '{pointer_hash}', pg_catalog.to_jsonb(pg_catalog.repeat('f', 64)), true
      )
    );
    RAISE EXCEPTION 'a second immutable Reference pointer unexpectedly succeeded';
  EXCEPTION
    WHEN SQLSTATE '23505' THEN NULL;
  END;

  BEGIN
    UPDATE qc2_governance_owner.champion_pointer
    SET pointer_hash = pg_catalog.repeat('f', 64)
    WHERE id = pointer_id;
    RAISE EXCEPTION 'immutable ChampionPointer unexpectedly changed';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN NULL;
  END;

  IF EXISTS (
    SELECT 1
    FROM qc2_governance_owner.operating_pointer_slot AS slot
    WHERE slot.epoch_id = fixture_epoch_id AND slot.slot_state <> 'NO_CHAMPION'
  ) THEN
    RAISE EXCEPTION 'fixture Reference pointer changed the explicit operating state';
  END IF;
END
$check_persisted_model$;
