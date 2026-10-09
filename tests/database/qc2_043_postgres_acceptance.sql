DO $qc2_043_privilege_boundary$
BEGIN
  IF NOT pg_catalog.has_function_privilege(
       'qc2_runtime_promotion',
       'qc2_governance_owner.ensure_no_champion_slot(uuid)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'qc2_runtime_promotion',
       'qc2_governance_owner.commit_champion_transition(jsonb,jsonb,jsonb,jsonb,text,text)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'qc2_runtime_inference',
       'qc2_governance_owner.get_champion_load_request(uuid)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'qc2_runtime_inference',
       'qc2_governance_owner.record_champion_load_confirmation(uuid,uuid,integer,text,uuid,text,uuid,text,text,text)',
       'EXECUTE'
     )
     OR NOT pg_catalog.has_function_privilege(
       'qc2_runtime_prediction',
       'qc2_governance_owner.assert_champion_load_ready(uuid,integer,text)',
       'EXECUTE'
     )
     OR pg_catalog.has_function_privilege(
       'qc2_runtime_prediction',
       'qc2_governance_owner.commit_champion_transition(jsonb,jsonb,jsonb,jsonb,text,text)',
       'EXECUTE'
     )
     OR pg_catalog.has_function_privilege(
       'qc2_runtime_promotion',
       'qc2_governance_owner.get_champion_load_request(uuid)',
       'EXECUTE'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_promotion',
       'qc2_governance_owner.promotion_approval_nonce',
       'INSERT'
     )
     OR pg_catalog.has_table_privilege(
       'qc2_runtime_inference',
       'qc2_governance_owner.champion_load_confirmation',
       'INSERT'
     ) THEN
    RAISE EXCEPTION 'QC2-043 runtime function or table privilege boundary is invalid';
  END IF;
END
$qc2_043_privilege_boundary$;

CREATE TEMP TABLE qc2_043_temp_schema_init (marker boolean) ON COMMIT DROP;

CREATE FUNCTION pg_temp.qc2_043_build_inputs(
  p_candidate_ref jsonb,
  p_epoch_ref jsonb,
  p_prior_ref jsonb,
  p_transition_kind text,
  p_expected_generation integer,
  p_expected_pointer_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_integrity_build
AS $function$
DECLARE
  v_created text := pg_catalog.to_char(
    pg_catalog.clock_timestamp() AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  v_expires text := '2099-12-31T23:59:59Z';
  v_bundle jsonb;
  v_request jsonb;
  v_decision jsonb;
  v_ticket jsonb;
  v_challenge_ref jsonb;
  v_bundle_ref jsonb;
  v_request_hash text;
  v_bundle_hash text;
  v_decision_hash text;
BEGIN
  v_bundle := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.PromotionBundleManifest.v1',
    'schema_version', '1.0',
    'id', qc2_integrity_build.new_uuid_v7()::text,
    'created_at', v_created,
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', pg_catalog.jsonb_build_array(p_candidate_ref),
    'candidate_model_ref', p_candidate_ref,
    'prior_champion_ref', COALESCE(p_prior_ref, 'null'::jsonb),
    'epoch_ref', p_epoch_ref,
    'mode', 'OPERATING',
    'registry_refs', '[]'::jsonb,
    'dataset_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.DatasetManifest.v1',
      'target_id', qc2_integrity_build.new_uuid_v7()::text,
      'content_hash', pg_catalog.repeat('a', 64)
    ),
    'split_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.outcomes_research.SplitManifest.v1',
      'target_id', qc2_integrity_build.new_uuid_v7()::text,
      'content_hash', pg_catalog.repeat('b', 64)
    ),
    'holdout_receipt_refs', '[]'::jsonb,
    'replay_report_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.ReplayReceipt.v1',
      'target_id', qc2_integrity_build.new_uuid_v7()::text,
      'content_hash', pg_catalog.repeat('c', 64)
    ),
    'evaluation_refs', '[]'::jsonb,
    'shadow_seal_refs', '[]'::jsonb,
    'policy_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionPolicy.v1',
      'target_id', qc2_integrity_build.new_uuid_v7()::text,
      'content_hash', pg_catalog.repeat('d', 64)
    ),
    'gate_results', pg_catalog.jsonb_build_object('fixture_status', 'PASS'),
    'environment_fingerprint', pg_catalog.repeat('e', 64),
    'expires_at', v_expires,
    'transition_intent', p_transition_kind,
    'inventory_hash', pg_catalog.repeat('f', 64)
  );
  v_bundle_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.governance_owner.promotionbundlemanifest.v1/1.0',
    v_bundle - ARRAY[
      'schema_name', 'schema_version', 'id', 'created_at'
    ]::text[]
  );
  v_bundle := v_bundle || pg_catalog.jsonb_build_object(
    'content_hash', v_bundle_hash
  );
  v_bundle_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.governance_owner.PromotionBundleManifest.v1',
    'target_id', v_bundle->>'id',
    'content_hash', v_bundle_hash
  );

  v_request := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.PromotionRequest.v1',
    'schema_version', '1.0',
    'id', qc2_integrity_build.new_uuid_v7()::text,
    'created_at', v_created,
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'bundle_ref', v_bundle_ref,
    'candidate_model_ref', p_candidate_ref,
    'expected_champion_ref', COALESCE(p_prior_ref, 'null'::jsonb),
    'epoch_ref', p_epoch_ref,
    'requested_at', v_created,
    'expires_at', v_expires
  );
  v_request_hash := qc2_integrity_build.hash_json(
    'qc2.qc2_043_fixture_request.v1', v_request
  );
  v_request := v_request || pg_catalog.jsonb_build_object(
    'request_hash', v_request_hash
  );

  v_challenge_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.governance_owner.PromotionChallenge.v1',
    'target_id', qc2_integrity_build.new_uuid_v7()::text,
    'content_hash', qc2_integrity_build.hash_json(
      'qc2.qc2_043_fixture_challenge.v1',
      pg_catalog.jsonb_build_object('request_hash', v_request_hash)
    )
  );
  v_decision := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.PromotionDecision.v1',
    'schema_version', '1.0',
    'id', qc2_integrity_build.new_uuid_v7()::text,
    'created_at', v_created,
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', '[]'::jsonb,
    'challenge_ref', v_challenge_ref,
    'decision', 'APPROVE',
    'signed_by_device_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.OwnerDevice.v1',
      'target_id', qc2_integrity_build.new_uuid_v7()::text
    ),
    'key_id', 'qc2-043-fixture-key',
    'signature', pg_catalog.repeat('0', 128),
    'signed_at', v_created,
    'request_hash', v_request_hash
  );
  v_decision_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.governance_owner.promotiondecision.v1/1.0',
    v_decision - ARRAY[
      'schema_name', 'schema_version', 'id', 'created_at'
    ]::text[]
  );
  v_decision := v_decision || pg_catalog.jsonb_build_object(
    'content_hash', v_decision_hash
  );
  v_ticket := pg_catalog.jsonb_build_object(
    'nonce', qc2_integrity_build.new_uuid_v7()::text,
    'request_hash', v_request_hash,
    'expected_generation', p_expected_generation::text,
    'expected_champion_hash', p_expected_pointer_hash,
    'idempotency_key', qc2_integrity_build.new_uuid_v7()::text,
    'envelope_hash', qc2_integrity_build.hash_json(
      'qc2.qc2_043_fixture_envelope.v1',
      pg_catalog.jsonb_build_object('decision_id', v_decision->>'id')
    ),
    'decision_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionDecision.v1',
      'target_id', v_decision->>'id',
      'content_hash', v_decision_hash
    ),
    'promotion_challenge_ref', v_challenge_ref
  );
  RETURN pg_catalog.jsonb_build_object(
    'request', v_request,
    'bundle', v_bundle,
    'decision', v_decision,
    'ticket', v_ticket
  );
END
$function$;

CREATE FUNCTION pg_temp.qc2_043_assert_failed_attempt(
  p_epoch_id uuid,
  p_model_id uuid,
  p_model_hash text,
  p_decision_id uuid,
  p_outbox_count bigint,
  p_test_event_count bigint,
  p_lifecycle_event_count bigint
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
BEGIN
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = p_epoch_id;
  IF v_slot.slot_state <> 'NO_CHAMPION'
     OR v_slot.generation <> 0
     OR v_slot.pointer_id IS NOT NULL
     OR NOT EXISTS (
       SELECT 1 FROM qc2_models_prediction.model_registry_model
       WHERE id = p_model_id
         AND content_hash = p_model_hash
         AND lifecycle_state = 'PROMOTION_ELIGIBLE'
     )
     OR EXISTS (
       SELECT 1 FROM qc2_governance_owner.champion_pointer
       WHERE epoch_id = p_epoch_id AND role = 'OPERATING'
     )
     OR EXISTS (
       SELECT 1 FROM qc2_governance_owner.promotion_transition_receipt
       WHERE decision_id = p_decision_id
     )
     OR EXISTS (
       SELECT 1 FROM qc2_governance_owner.promotion_approval_nonce
       WHERE decision_id = p_decision_id
     )
     OR (
       SELECT pg_catalog.count(*)
       FROM qc2_control.outbox_message
       WHERE message_type = 'champion_model_load'
     ) <> p_outbox_count
     OR COALESCE((
       SELECT pg_catalog.sum(head.event_count)
       FROM qc2_integrity_build.evidence_stream_head AS head
       WHERE head.environment_namespace = 'test' AND head.active
     ), 0) <> p_test_event_count
     OR (
       SELECT pg_catalog.count(*)
       FROM qc2_models_prediction.model_lifecycle_event
       WHERE model_id = p_model_id AND model_hash = p_model_hash
     ) <> p_lifecycle_event_count
     OR EXISTS (
       SELECT 1 FROM qc2_governance_owner.promotion_rollback_retention
       WHERE model_id = p_model_id AND model_hash = p_model_hash
     ) THEN
    RAISE EXCEPTION 'failed transition changed authoritative or durable state';
  END IF;
END
$function$;

GRANT EXECUTE ON FUNCTION pg_temp.qc2_043_assert_failed_attempt(
  uuid, uuid, text, uuid, bigint, bigint, bigint
) TO qc2_runtime_promotion;

DO $qc2_043_fixture_ids$
BEGIN
  PERFORM pg_catalog.set_config(
    'qc2_test.model2_id',
    qc2_integrity_build.new_uuid_v7()::text,
    true
  );
  PERFORM pg_catalog.set_config(
    'qc2_test.artifact2_id',
    qc2_integrity_build.new_uuid_v7()::text,
    true
  );
  PERFORM pg_catalog.set_config(
    'qc2_test.worker1_id',
    qc2_integrity_build.new_uuid_v7()::text,
    true
  );
  PERFORM pg_catalog.set_config(
    'qc2_test.worker3_id',
    qc2_integrity_build.new_uuid_v7()::text,
    true
  );
END
$qc2_043_fixture_ids$;

CREATE FUNCTION pg_temp.qc2_043_register_second_fixture_model()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_integrity_build, qc2_models_prediction
AS $function$
DECLARE
  v_model_id uuid := current_setting('qc2_test.model_id')::uuid;
  v_model_hash text := current_setting('qc2_test.model_hash');
  v_artifact_id uuid := current_setting('qc2_test.artifact_id')::uuid;
  v_model2_id uuid := current_setting('qc2_test.model2_id')::uuid;
  v_artifact2_id uuid := current_setting('qc2_test.artifact2_id')::uuid;
  v_model jsonb;
  v_artifact jsonb;
  v_artifact_ref jsonb;
  v_ordered_files jsonb;
  v_blob_receipts jsonb;
  v_storage_receipts jsonb;
  v_ack_rows jsonb;
  v_storage_backend text;
  v_durability_receipt text;
  v_ack_hash text;
  v_verification_hash text;
  v_created timestamptz := pg_catalog.clock_timestamp();
  v_created_text text;
  v_model_hash2 text;
  v_registered_id uuid;
BEGIN
  v_created_text := pg_catalog.to_char(
    v_created AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  SELECT model_contract INTO STRICT v_model
  FROM qc2_models_prediction.model_registry_model
  WHERE id = v_model_id AND content_hash = v_model_hash;
  SELECT manifest_contract, storage_backend, durability_receipt
  INTO STRICT v_artifact, v_storage_backend, v_durability_receipt
  FROM qc2_integrity_build.model_artifact_manifest
  WHERE id = v_artifact_id;

  v_artifact := pg_catalog.jsonb_set(
    pg_catalog.jsonb_set(v_artifact, '{id}', pg_catalog.to_jsonb(v_artifact2_id::text), true),
    '{created_at}', pg_catalog.to_jsonb(v_created_text), true
  );
  SELECT pg_catalog.jsonb_agg(file_row ORDER BY file_row->>'relative_path' COLLATE "C")
  INTO v_ordered_files
  FROM pg_catalog.jsonb_array_elements(v_artifact->'files') AS files(file_row);
  v_artifact := pg_catalog.jsonb_set(v_artifact, '{files}', v_ordered_files, true);
  v_artifact := pg_catalog.jsonb_set(
    v_artifact,
    '{inventory_hash}',
    pg_catalog.to_jsonb(
      qc2_integrity_build.hash_json('qc2.artifact-inventory.v1', v_ordered_files)
    ),
    true
  );
  v_artifact := pg_catalog.jsonb_set(
    v_artifact,
    '{content_hash}',
    pg_catalog.to_jsonb(
      qc2_integrity_build.hash_json(
        'qc2.contract-content.v1/qc2.integrity_build.artifactmanifest.v1/1.0',
        v_artifact - ARRAY[
          'content_hash', 'created_at', 'id', 'schema_name', 'schema_version',
          'detached_signature', 'transport_hash'
        ]::text[]
      )
    ),
    true
  );
  IF v_artifact->>'content_hash' IS DISTINCT FROM
       (SELECT content_hash
        FROM qc2_integrity_build.model_artifact_manifest
        WHERE id = v_artifact_id) THEN
    RAISE EXCEPTION 'cloned fixture ArtifactManifest content did not remain stable';
  END IF;
  v_artifact_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.integrity_build.ArtifactManifest.v1',
    'target_id', v_artifact2_id::text,
    'content_hash', v_artifact->>'content_hash'
  );
  v_model := pg_catalog.jsonb_set(
    pg_catalog.jsonb_set(
      pg_catalog.jsonb_set(v_model, '{id}', pg_catalog.to_jsonb(v_model2_id::text), true),
      '{created_at}', pg_catalog.to_jsonb(v_created_text), true
    ),
    '{artifact_manifest_ref}', v_artifact_ref, true
  );
  v_model := pg_catalog.jsonb_set(
    v_model, '{source_refs}', pg_catalog.jsonb_build_array(v_artifact_ref), true
  );
  v_model_hash2 := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.models_prediction.modelmanifest.v1/1.0',
    v_model - ARRAY[
      'content_hash', 'created_at', 'id', 'schema_name', 'schema_version',
      'lifecycle_state'
    ]::text[]
  );
  v_model := pg_catalog.jsonb_set(
    v_model, '{content_hash}', pg_catalog.to_jsonb(v_model_hash2), true
  );

  SELECT pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_object(
      'manifest_id', v_artifact2_id::text,
      'manifest_hash', v_artifact->>'content_hash',
      'sha256', file_row->>'sha256',
      'byte_count', (file_row->>'length_bytes')::bigint,
      'storage_backend', v_storage_backend,
      'object_key', blob.object_key,
      'durability_receipt', COALESCE(blob.durability_receipt, ''),
      'staged_at', v_created_text
    )
    ORDER BY file_row->>'sha256' COLLATE "C", blob.object_key COLLATE "C"
  )
  INTO v_blob_receipts
  FROM pg_catalog.jsonb_array_elements(v_ordered_files) AS files(file_row)
  JOIN qc2_integrity_build.model_artifact_blob AS blob
    ON blob.sha256 = file_row->>'sha256'
   AND blob.storage_backend = v_storage_backend;

  SELECT pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_object(
      'sha256', receipt->>'sha256',
      'object_key', receipt->>'object_key',
      'durability_receipt', receipt->>'durability_receipt'
    )
    ORDER BY receipt->>'sha256' COLLATE "C", receipt->>'object_key' COLLATE "C"
  )
  INTO v_ack_rows
  FROM pg_catalog.jsonb_array_elements(v_blob_receipts) AS blobs(receipt);
  v_ack_hash := CASE WHEN v_storage_backend = 'external_object_store'
    THEN qc2_integrity_build.hash_json('qc2.model-artifact-storage-ack.v1', v_ack_rows)
    ELSE NULL
  END;
  IF v_storage_backend = 'external_object_store'
     AND v_ack_hash IS DISTINCT FROM v_durability_receipt THEN
    RAISE EXCEPTION 'cloned fixture storage acknowledgement is inconsistent';
  END IF;
  v_verification_hash := qc2_integrity_build.hash_json(
    'qc2.model-artifact-verification.v1',
    pg_catalog.jsonb_build_object(
      'manifest_id', v_artifact2_id::text,
      'manifest_content_hash', v_artifact->>'content_hash',
      'files', v_ordered_files,
      'storage_backend', v_storage_backend,
      'durability_receipt', COALESCE(v_durability_receipt, '')
    )
  );
  v_storage_receipts := pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object(
      'manifest_id', v_artifact2_id::text,
      'manifest_hash', v_artifact->>'content_hash',
      'storage_backend', v_storage_backend,
      'durability_receipt', v_durability_receipt,
      'verification_state', 'FULL_VERIFIED',
      'verification_hash', v_verification_hash
    )
  );
  v_registered_id := qc2_models_prediction.register_verified_model(
    v_model,
    pg_catalog.jsonb_build_array(v_artifact),
    v_blob_receipts,
    v_storage_receipts,
    '[]'::jsonb
  );
  IF v_registered_id <> v_model2_id THEN
    RAISE EXCEPTION 'QC2-043 second fixture model registered with the wrong ID';
  END IF;
  PERFORM pg_catalog.set_config('qc2_test.model2_hash', v_model_hash2, true);
END
$function$;

GRANT EXECUTE ON FUNCTION pg_temp.qc2_043_register_second_fixture_model()
TO qc2_runtime_model_registry;

SET SESSION AUTHORIZATION qc2_runtime_model_registry;

SELECT pg_temp.qc2_043_register_second_fixture_model();

RESET SESSION AUTHORIZATION;

DO $qc2_043_prepare_test_inputs$
DECLARE
  v_epoch_id uuid := current_setting('qc2_test.epoch_id')::uuid;
  v_epoch_ref jsonb;
  v_model_ref jsonb;
  v_inputs jsonb;
  v_outbox_count bigint;
  v_event_count bigint;
  v_lifecycle_count bigint;
BEGIN
  v_epoch_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.validation.ValidationEpoch.v1',
    'target_id', v_epoch_id::text,
    'content_hash', pg_catalog.repeat('e', 64)
  );
  v_model_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
    'target_id', current_setting('qc2_test.model_id'),
    'content_hash', current_setting('qc2_test.model_hash')
  );
  v_inputs := pg_temp.qc2_043_build_inputs(
    v_model_ref, v_epoch_ref, NULL, 'initial_bootstrap', 0, NULL
  );
  PERFORM pg_catalog.set_config('qc2_test.transition_inputs', v_inputs::text, true);
  PERFORM pg_catalog.set_config('qc2_test.epoch_ref', v_epoch_ref::text, true);
  SELECT pg_catalog.count(*) INTO v_outbox_count
  FROM qc2_control.outbox_message
  WHERE message_type = 'champion_model_load';
  SELECT COALESCE(pg_catalog.sum(event_count), 0) INTO v_event_count
  FROM qc2_integrity_build.evidence_stream_head
  WHERE environment_namespace = 'test' AND active;
  SELECT pg_catalog.count(*) INTO v_lifecycle_count
  FROM qc2_models_prediction.model_lifecycle_event
  WHERE model_id = (current_setting('qc2_test.model_id'))::uuid
    AND model_hash = current_setting('qc2_test.model_hash');
  PERFORM pg_catalog.set_config('qc2_test.baseline_outbox', v_outbox_count::text, true);
  PERFORM pg_catalog.set_config('qc2_test.baseline_test_events', v_event_count::text, true);
  PERFORM pg_catalog.set_config('qc2_test.baseline_lifecycle', v_lifecycle_count::text, true);
END
$qc2_043_prepare_test_inputs$;

SET SESSION AUTHORIZATION qc2_runtime_promotion;

DO $qc2_043_seed_no_champion$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
BEGIN
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.ensure_no_champion_slot(
    current_setting('qc2_test.epoch_id')::uuid
  );
  IF v_slot.slot_state <> 'NO_CHAMPION'
     OR v_slot.generation <> 0
     OR v_slot.pointer_id IS NOT NULL THEN
    RAISE EXCEPTION 'QC2-043 bootstrap did not begin from explicit NO_CHAMPION';
  END IF;
END
$qc2_043_seed_no_champion$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_validation;

DO $qc2_043_validation_lifecycle$
DECLARE
  v_model_id uuid;
  v_model_hash text;
  v_model_ref jsonb;
  v_evidence jsonb;
  v_model_row record;
BEGIN
  FOR v_model_id, v_model_hash IN
    SELECT current_setting('qc2_test.model_id')::uuid,
           current_setting('qc2_test.model_hash')
    UNION ALL
    SELECT current_setting('qc2_test.model2_id')::uuid,
           current_setting('qc2_test.model2_hash')
  LOOP
    v_model_ref := pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
      'target_id', v_model_id::text,
      'content_hash', v_model_hash
    );
    v_evidence := pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.outcomes_research.CandidateEvaluation.v1',
      'id', CASE WHEN v_model_id = current_setting('qc2_test.model_id')::uuid
        THEN '018f0000-0000-7000-8000-000000000051'
        ELSE '018f0000-0000-7000-8000-000000000054' END,
      'content_hash', pg_catalog.repeat('1', 64),
      'owning_authority', 'validation',
      'verdict', 'PASS',
      'candidate_ref', v_model_ref
    );
    PERFORM qc2_models_prediction.record_model_lifecycle_transition(
      v_model_id, 'RESEARCH', 'CANDIDATE', v_evidence, pg_catalog.clock_timestamp()
    );
    v_evidence := pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.outcomes_research.ChallengerEvaluation.v1',
      'id', CASE WHEN v_model_id = current_setting('qc2_test.model_id')::uuid
        THEN '018f0000-0000-7000-8000-000000000052'
        ELSE '018f0000-0000-7000-8000-000000000055' END,
      'content_hash', pg_catalog.repeat('2', 64),
      'owning_authority', 'validation',
      'verdict', 'PASS',
      'challenger_ref', v_model_ref
    );
    PERFORM qc2_models_prediction.record_model_lifecycle_transition(
      v_model_id, 'CANDIDATE', 'CHALLENGER', v_evidence, pg_catalog.clock_timestamp()
    );
  END LOOP;
END
$qc2_043_validation_lifecycle$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_prediction;

DO $qc2_043_shadow_lifecycle$
DECLARE
  v_model_id uuid;
  v_model_hash text;
  v_model_ref jsonb;
  v_evidence jsonb;
BEGIN
  FOR v_model_id, v_model_hash IN
    SELECT current_setting('qc2_test.model_id')::uuid,
           current_setting('qc2_test.model_hash')
    UNION ALL
    SELECT current_setting('qc2_test.model2_id')::uuid,
           current_setting('qc2_test.model2_hash')
  LOOP
    v_model_ref := pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
      'target_id', v_model_id::text,
      'content_hash', v_model_hash
    );
    v_evidence := pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.models_prediction.ShadowPredictionSet.v1',
      'id', CASE WHEN v_model_id = current_setting('qc2_test.model_id')::uuid
        THEN '018f0000-0000-7000-8000-000000000053'
        ELSE '018f0000-0000-7000-8000-000000000056' END,
      'content_hash', pg_catalog.repeat('3', 64),
      'owning_authority', 'prediction',
      'model_ref', v_model_ref
    );
    PERFORM qc2_models_prediction.record_model_lifecycle_transition(
      v_model_id, 'CHALLENGER', 'SHADOW', v_evidence, pg_catalog.clock_timestamp()
    );
  END LOOP;
END
$qc2_043_shadow_lifecycle$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_validation;

DO $qc2_043_promotion_eligibility$
DECLARE
  v_model_id uuid;
  v_model_hash text;
  v_model_ref jsonb;
  v_evidence jsonb;
BEGIN
  FOR v_model_id, v_model_hash IN
    SELECT current_setting('qc2_test.model_id')::uuid,
           current_setting('qc2_test.model_hash')
    UNION ALL
    SELECT current_setting('qc2_test.model2_id')::uuid,
           current_setting('qc2_test.model2_hash')
  LOOP
    v_model_ref := pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
      'target_id', v_model_id::text,
      'content_hash', v_model_hash
    );
    v_evidence := pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.validation.ValidationReport.v1',
      'id', CASE WHEN v_model_id = current_setting('qc2_test.model_id')::uuid
        THEN '018f0000-0000-7000-8000-000000000057'
        ELSE '018f0000-0000-7000-8000-000000000058' END,
      'content_hash', pg_catalog.repeat('4', 64),
      'owning_authority', 'validation',
      'verdict', 'PASS',
      'source_refs', pg_catalog.jsonb_build_array(v_model_ref)
    );
    PERFORM qc2_models_prediction.record_model_lifecycle_transition(
      v_model_id, 'SHADOW', 'PROMOTION_ELIGIBLE', v_evidence,
      pg_catalog.clock_timestamp()
    );
  END LOOP;
END
$qc2_043_promotion_eligibility$;

RESET SESSION AUTHORIZATION;

DO $qc2_043_refresh_transition_baselines$
DECLARE
  v_outbox_count bigint;
  v_event_count bigint;
  v_lifecycle_count bigint;
BEGIN
  SELECT pg_catalog.count(*) INTO v_outbox_count
  FROM qc2_control.outbox_message
  WHERE message_type = 'champion_model_load';
  SELECT COALESCE(pg_catalog.sum(event_count), 0) INTO v_event_count
  FROM qc2_integrity_build.evidence_stream_head
  WHERE environment_namespace = 'test' AND active;
  SELECT pg_catalog.count(*) INTO v_lifecycle_count
  FROM qc2_models_prediction.model_lifecycle_event
  WHERE model_id = current_setting('qc2_test.model_id')::uuid
    AND model_hash = current_setting('qc2_test.model_hash');
  PERFORM pg_catalog.set_config('qc2_test.baseline_outbox', v_outbox_count::text, true);
  PERFORM pg_catalog.set_config('qc2_test.baseline_test_events', v_event_count::text, true);
  PERFORM pg_catalog.set_config('qc2_test.baseline_lifecycle', v_lifecycle_count::text, true);
END
$qc2_043_refresh_transition_baselines$;

SET SESSION AUTHORIZATION qc2_runtime_promotion;

DO $qc2_043_atomic_faults_and_bootstrap$
DECLARE
  v_inputs jsonb := current_setting('qc2_test.transition_inputs')::jsonb;
  v_fault text;
  v_receipt jsonb;
  v_replay jsonb;
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_faults text[] := ARRAY[
    'before_nonce_consumption', 'after_nonce_consumption',
    'before_evidence', 'after_evidence',
    'before_receipt', 'after_receipt',
    'before_lifecycle', 'after_lifecycle',
    'before_pointer_insert', 'after_pointer_insert',
    'before_slot_cas', 'after_slot_cas',
    'before_outbox', 'after_outbox'
  ];
BEGIN
  FOREACH v_fault IN ARRAY v_faults LOOP
    BEGIN
      PERFORM qc2_governance_owner.commit_champion_transition(
        v_inputs->'request', v_inputs->'bundle', v_inputs->'decision',
        v_inputs->'ticket', 'initial_bootstrap', v_fault
      );
      RAISE EXCEPTION 'fault injection % did not abort', v_fault
        USING ERRCODE = 'P0002';
    EXCEPTION
      WHEN SQLSTATE 'P0001' THEN NULL;
    END;
    PERFORM pg_temp.qc2_043_assert_failed_attempt(
      current_setting('qc2_test.epoch_id')::uuid,
      current_setting('qc2_test.model_id')::uuid,
      current_setting('qc2_test.model_hash'),
      (v_inputs->'decision'->>'id')::uuid,
      current_setting('qc2_test.baseline_outbox')::bigint,
      current_setting('qc2_test.baseline_test_events')::bigint,
      current_setting('qc2_test.baseline_lifecycle')::bigint
    );
  END LOOP;
  v_receipt := qc2_governance_owner.commit_champion_transition(
    v_inputs->'request', v_inputs->'bundle', v_inputs->'decision',
    v_inputs->'ticket', 'initial_bootstrap', NULL
  );
  v_replay := qc2_governance_owner.commit_champion_transition(
    v_inputs->'request', v_inputs->'bundle', v_inputs->'decision',
    v_inputs->'ticket', 'initial_bootstrap', NULL
  );
  IF v_receipt IS DISTINCT FROM v_replay
     OR v_receipt->>'transition_state' IS DISTINCT FROM 'COMMITTED'
     OR v_receipt->>'prior_generation' IS DISTINCT FROM '0'
     OR v_receipt->>'new_generation' IS DISTINCT FROM '1' THEN
    RAISE EXCEPTION 'QC2-043 receipt was not committed or replayed idempotently';
  END IF;
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.ensure_no_champion_slot(
    current_setting('qc2_test.epoch_id')::uuid
  );
  IF v_slot.slot_state <> 'CHAMPION_SET'
     OR v_slot.generation <> 1
     OR v_slot.pointer_id IS NULL
     OR v_slot.model_id <> current_setting('qc2_test.model_id')::uuid THEN
    RAISE EXCEPTION 'QC2-043 bootstrap did not atomically advance the operating slot';
  END IF;
  PERFORM pg_catalog.set_config('qc2_test.receipt1_id', v_receipt->>'id', true);
  PERFORM pg_catalog.set_config('qc2_test.pointer1_id', v_slot.pointer_id::text, true);
  PERFORM pg_catalog.set_config('qc2_test.pointer1_hash', v_receipt->>'pointer_hash', true);
END
$qc2_043_atomic_faults_and_bootstrap$;

RESET SESSION AUTHORIZATION;

DO $qc2_043_bootstrap_records$
BEGIN
  IF (SELECT count(*) FROM qc2_governance_owner.promotion_transition_receipt
      WHERE id = current_setting('qc2_test.receipt1_id')::uuid) <> 1
     OR (SELECT count(*) FROM qc2_governance_owner.promotion_approval_nonce
         WHERE decision_id = (current_setting('qc2_test.transition_inputs')::jsonb
           ->'decision'->>'id')::uuid) <> 1
     OR (SELECT count(*) FROM qc2_governance_owner.champion_pointer
         WHERE id = current_setting('qc2_test.pointer1_id')::uuid
           AND pointer_hash = current_setting('qc2_test.pointer1_hash')
           AND generation = 1 AND role = 'OPERATING') <> 1
     OR (SELECT count(*) FROM qc2_control.outbox_message
         WHERE logical_operation_id = current_setting('qc2_test.receipt1_id')::uuid
           AND message_type = 'champion_model_load') <> 1 THEN
    RAISE EXCEPTION 'QC2-043 receipt, nonce, pointer, or load outbox is missing';
  END IF;
END
$qc2_043_bootstrap_records$;

SET SESSION AUTHORIZATION qc2_runtime_promotion;

DO $qc2_043_production_denial$
DECLARE
  v_inputs jsonb := current_setting('qc2_test.transition_inputs')::jsonb;
BEGIN
  BEGIN
    PERFORM qc2_governance_owner.commit_champion_transition(
      pg_catalog.jsonb_set(v_inputs->'request', '{environment_namespace}', '"production"'::jsonb),
      pg_catalog.jsonb_set(v_inputs->'bundle', '{environment_namespace}', '"production"'::jsonb),
      pg_catalog.jsonb_set(v_inputs->'decision', '{environment_namespace}', '"production"'::jsonb),
      v_inputs->'ticket', 'initial_bootstrap', NULL
    );
    RAISE EXCEPTION 'QC2-043 accepted a production fixture approval'
      USING ERRCODE = 'P0002';
  EXCEPTION
    WHEN SQLSTATE '42501' THEN NULL;
  END;
END
$qc2_043_production_denial$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_inference;

DO $qc2_043_first_worker_load$
DECLARE
  v_receipt_id uuid := current_setting('qc2_test.receipt1_id')::uuid;
  v_load jsonb;
  v_epoch_id uuid := current_setting('qc2_test.epoch_id')::uuid;
  v_pointer_id uuid := current_setting('qc2_test.pointer1_id')::uuid;
  v_pointer_hash text := current_setting('qc2_test.pointer1_hash');
  v_model_id uuid := current_setting('qc2_test.model_id')::uuid;
  v_model_hash text := current_setting('qc2_test.model_hash');
BEGIN
  v_load := qc2_governance_owner.get_champion_load_request(v_receipt_id);
  IF v_load->'message'->>'message_type' IS DISTINCT FROM 'champion_model_load'
     OR v_load->'load_request'->>'pointer_id' IS DISTINCT FROM v_pointer_id::text
     OR v_load->'load_request'->>'generation' IS DISTINCT FROM '1' THEN
    RAISE EXCEPTION 'QC2-043 durable worker load request is not receipt-bound';
  END IF;
  PERFORM qc2_governance_owner.record_champion_load_confirmation(
    v_epoch_id, v_pointer_id, 1, v_pointer_hash,
    v_model_id, v_model_hash, current_setting('qc2_test.worker1_id')::uuid,
    'FAILED', pg_catalog.repeat('5', 64), 'model_load_failed'
  );
END
$qc2_043_first_worker_load$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_prediction;

DO $qc2_043_failed_worker_blocks$
BEGIN
  BEGIN
    PERFORM qc2_governance_owner.assert_champion_load_ready(
      current_setting('qc2_test.epoch_id')::uuid,
      1,
      current_setting('qc2_test.pointer1_hash')
    );
    RAISE EXCEPTION 'failed worker load unexpectedly unlocked the generation'
      USING ERRCODE = 'P0002';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN NULL;
  END;
END
$qc2_043_failed_worker_blocks$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_inference;

DO $qc2_043_first_worker_load_success$
BEGIN
  PERFORM qc2_governance_owner.record_champion_load_confirmation(
    current_setting('qc2_test.epoch_id')::uuid,
    current_setting('qc2_test.pointer1_id')::uuid,
    1,
    current_setting('qc2_test.pointer1_hash'),
    current_setting('qc2_test.model_id')::uuid,
    current_setting('qc2_test.model_hash'),
    current_setting('qc2_test.worker1_id')::uuid,
    'LOADED',
    pg_catalog.repeat('6', 64),
    NULL
  );
END
$qc2_043_first_worker_load_success$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_prediction;

DO $qc2_043_first_generation_ready$
BEGIN
  IF qc2_governance_owner.assert_champion_load_ready(
    current_setting('qc2_test.epoch_id')::uuid,
    1,
    current_setting('qc2_test.pointer1_hash')
  ) <> current_setting('qc2_test.pointer1_id')::uuid THEN
    RAISE EXCEPTION 'QC2-043 loaded generation did not pass readiness';
  END IF;
END
$qc2_043_first_generation_ready$;

RESET SESSION AUTHORIZATION;

DO $qc2_043_build_promotion_inputs$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_pointer qc2_governance_owner.champion_pointer%ROWTYPE;
  v_prior_ref jsonb;
  v_model_ref jsonb;
  v_inputs jsonb;
BEGIN
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = current_setting('qc2_test.epoch_id')::uuid;
  SELECT * INTO STRICT v_pointer
  FROM qc2_governance_owner.champion_pointer
  WHERE id = v_slot.pointer_id;
  v_prior_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.governance_owner.ChampionPointer.v1',
    'target_id', v_pointer.id::text,
    'content_hash', v_pointer.pointer_hash
  );
  v_model_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
    'target_id', current_setting('qc2_test.model2_id'),
    'content_hash', current_setting('qc2_test.model2_hash')
  );
  v_inputs := pg_temp.qc2_043_build_inputs(
    v_model_ref,
    current_setting('qc2_test.epoch_ref')::jsonb,
    v_prior_ref,
    'promotion',
    v_slot.generation,
    v_pointer.pointer_hash
  );
  PERFORM pg_catalog.set_config('qc2_test.promotion_inputs', v_inputs::text, true);
END
$qc2_043_build_promotion_inputs$;

SET SESSION AUTHORIZATION qc2_runtime_promotion;

DO $qc2_043_promotion_commit$
DECLARE
  v_inputs jsonb := current_setting('qc2_test.promotion_inputs')::jsonb;
  v_receipt jsonb;
BEGIN
  v_receipt := qc2_governance_owner.commit_champion_transition(
    v_inputs->'request', v_inputs->'bundle', v_inputs->'decision',
    v_inputs->'ticket', 'promotion', NULL
  );
  IF v_receipt->>'prior_generation' IS DISTINCT FROM '1'
     OR v_receipt->>'new_generation' IS DISTINCT FROM '2' THEN
    RAISE EXCEPTION 'QC2-043 promotion did not advance generation 1 to 2';
  END IF;
  PERFORM pg_catalog.set_config('qc2_test.receipt2_id', v_receipt->>'id', true);
END
$qc2_043_promotion_commit$;

RESET SESSION AUTHORIZATION;

DO $qc2_043_promotion_retention$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_governance_owner.promotion_rollback_retention
    WHERE model_id = current_setting('qc2_test.model_id')::uuid
      AND model_hash = current_setting('qc2_test.model_hash')
      AND source_receipt_id = current_setting('qc2_test.receipt2_id')::uuid
  )
     OR NOT EXISTS (
       SELECT 1
       FROM qc2_models_prediction.model_registry_model
       WHERE id = current_setting('qc2_test.model_id')::uuid
         AND lifecycle_state = 'RETIRED'
     ) THEN
    RAISE EXCEPTION 'QC2-043 did not retain the retired Champion for forward rollback';
  END IF;
END
$qc2_043_promotion_retention$;

DO $qc2_043_build_rollback_inputs$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_pointer qc2_governance_owner.champion_pointer%ROWTYPE;
  v_prior_ref jsonb;
  v_model_ref jsonb;
  v_inputs jsonb;
BEGIN
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = current_setting('qc2_test.epoch_id')::uuid;
  SELECT * INTO STRICT v_pointer
  FROM qc2_governance_owner.champion_pointer
  WHERE id = v_slot.pointer_id;
  v_prior_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.governance_owner.ChampionPointer.v1',
    'target_id', v_pointer.id::text,
    'content_hash', v_pointer.pointer_hash
  );
  v_model_ref := pg_catalog.jsonb_build_object(
    'target_schema_name', 'qc2.models_prediction.ModelManifest.v1',
    'target_id', current_setting('qc2_test.model_id'),
    'content_hash', current_setting('qc2_test.model_hash')
  );
  v_inputs := pg_temp.qc2_043_build_inputs(
    v_model_ref,
    current_setting('qc2_test.epoch_ref')::jsonb,
    v_prior_ref,
    'forward_rollback',
    v_slot.generation,
    v_pointer.pointer_hash
  );
  PERFORM pg_catalog.set_config('qc2_test.rollback_inputs', v_inputs::text, true);
END
$qc2_043_build_rollback_inputs$;

SET SESSION AUTHORIZATION qc2_runtime_promotion;

DO $qc2_043_forward_rollback$
DECLARE
  v_inputs jsonb := current_setting('qc2_test.rollback_inputs')::jsonb;
  v_receipt jsonb;
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
BEGIN
  v_receipt := qc2_governance_owner.commit_champion_transition(
    v_inputs->'request', v_inputs->'bundle', v_inputs->'decision',
    v_inputs->'ticket', 'forward_rollback', NULL
  );
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.ensure_no_champion_slot(
    current_setting('qc2_test.epoch_id')::uuid
  );
  IF v_receipt->>'prior_generation' IS DISTINCT FROM '2'
     OR v_receipt->>'new_generation' IS DISTINCT FROM '3'
     OR v_slot.generation <> 3
     OR v_slot.model_id <> current_setting('qc2_test.model_id')::uuid THEN
    RAISE EXCEPTION 'QC2-043 forward rollback did not commit as generation 3';
  END IF;
  PERFORM pg_catalog.set_config('qc2_test.receipt3_id', v_receipt->>'id', true);
  PERFORM pg_catalog.set_config('qc2_test.pointer3_id', v_slot.pointer_id::text, true);
  PERFORM pg_catalog.set_config('qc2_test.pointer3_hash', v_receipt->>'pointer_hash', true);
END
$qc2_043_forward_rollback$;

RESET SESSION AUTHORIZATION;

DO $qc2_043_rollback_records$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM qc2_governance_owner.promotion_rollback_retention
    WHERE model_id = current_setting('qc2_test.model2_id')::uuid
      AND model_hash = current_setting('qc2_test.model2_hash')
      AND source_receipt_id = current_setting('qc2_test.receipt3_id')::uuid
  )
     OR NOT EXISTS (
       SELECT 1
       FROM qc2_models_prediction.model_registry_model
       WHERE id = current_setting('qc2_test.model_id')::uuid
         AND lifecycle_state = 'CHAMPION'
     )
     OR NOT EXISTS (
       SELECT 1
       FROM qc2_models_prediction.model_registry_model
       WHERE id = current_setting('qc2_test.model2_id')::uuid
         AND lifecycle_state = 'RETIRED'
     ) THEN
    RAISE EXCEPTION 'QC2-043 forward rollback did not preserve both generations';
  END IF;
END
$qc2_043_rollback_records$;

SET SESSION AUTHORIZATION qc2_runtime_prediction;

DO $qc2_043_new_generation_blocks$
BEGIN
  BEGIN
    PERFORM qc2_governance_owner.assert_champion_load_ready(
      current_setting('qc2_test.epoch_id')::uuid,
      3,
      current_setting('qc2_test.pointer3_hash')
    );
    RAISE EXCEPTION 'unconfirmed rollback generation unexpectedly passed readiness'
      USING ERRCODE = 'P0002';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN NULL;
  END;
END
$qc2_043_new_generation_blocks$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_inference;

DO $qc2_043_rollback_generation_load$
DECLARE
  v_load jsonb;
BEGIN
  v_load := qc2_governance_owner.get_champion_load_request(
    current_setting('qc2_test.receipt3_id')::uuid
  );
  IF v_load->'load_request'->>'generation' IS DISTINCT FROM '3'
     OR v_load->'load_request'->>'pointer_id'
       IS DISTINCT FROM current_setting('qc2_test.pointer3_id') THEN
    RAISE EXCEPTION 'forward rollback load request does not identify generation 3';
  END IF;
  PERFORM qc2_governance_owner.record_champion_load_confirmation(
    current_setting('qc2_test.epoch_id')::uuid,
    current_setting('qc2_test.pointer3_id')::uuid,
    3,
    current_setting('qc2_test.pointer3_hash'),
    current_setting('qc2_test.model_id')::uuid,
    current_setting('qc2_test.model_hash'),
    current_setting('qc2_test.worker3_id')::uuid,
    'LOADED',
    pg_catalog.repeat('7', 64),
    NULL
  );
END
$qc2_043_rollback_generation_load$;

RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION qc2_runtime_prediction;

DO $qc2_043_rollback_generation_ready$
BEGIN
  IF qc2_governance_owner.assert_champion_load_ready(
    current_setting('qc2_test.epoch_id')::uuid,
    3,
    current_setting('qc2_test.pointer3_hash')
  ) <> current_setting('qc2_test.pointer3_id')::uuid THEN
    RAISE EXCEPTION 'confirmed rollback generation did not pass readiness';
  END IF;
END
$qc2_043_rollback_generation_ready$;

RESET SESSION AUTHORIZATION;
