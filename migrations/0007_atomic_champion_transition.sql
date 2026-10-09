-- QC2-043: one durable, compare-and-swap Champion transition boundary.
-- Live owner approval is deliberately disabled; this commit path accepts only
-- synthetic test transitions until the production identity/approval gate is authorized.

SET ROLE qc2_migrator;

GRANT USAGE ON SCHEMA qc2_governance_owner TO
  qc2_runtime_promotion, qc2_runtime_inference, qc2_runtime_prediction;

ALTER TABLE qc2_governance_owner.champion_pointer
  ADD CONSTRAINT champion_pointer_transition_lookup_unique
  UNIQUE (id, epoch_id, generation, pointer_hash, model_id, model_hash);

CREATE TABLE qc2_governance_owner.promotion_transition_receipt (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL,
  request_id uuid NOT NULL,
  decision_id uuid NOT NULL UNIQUE,
  transition_kind text NOT NULL CHECK (
    transition_kind IN ('initial_bootstrap', 'promotion', 'forward_rollback')
  ),
  prior_generation integer NOT NULL CHECK (prior_generation >= 0),
  new_generation integer NOT NULL CHECK (new_generation > prior_generation),
  pointer_id uuid NOT NULL,
  pointer_hash text NOT NULL CHECK (pointer_hash ~ '^[0-9a-f]{64}$'),
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  receipt_hash text NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
  nonce_hash text NOT NULL UNIQUE CHECK (nonce_hash ~ '^[0-9a-f]{64}$'),
  committed_at timestamptz NOT NULL,
  receipt_contract jsonb NOT NULL CHECK (
    receipt_contract->>'schema_name' = 'qc2.governance_owner.PromotionReceipt.v1'
    AND receipt_contract->>'schema_version' = '1.0'
    AND receipt_contract->>'id' = id::text
    AND receipt_contract->>'transition_state' = 'COMMITTED'
    AND receipt_contract->>'prior_generation' = prior_generation::text
    AND receipt_contract->>'new_generation' = new_generation::text
    AND receipt_contract->>'pointer_hash' = pointer_hash
    AND (receipt_contract->>'committed_at')::timestamptz = committed_at
    AND receipt_contract->'request_ref'->>'target_id' = request_id::text
    AND receipt_contract->'decision_ref'->>'target_id' = decision_id::text
  ),
  UNIQUE (epoch_id, new_generation),
  UNIQUE (id, decision_id),
  UNIQUE (id, receipt_hash),
  FOREIGN KEY (
    pointer_id, epoch_id, new_generation, pointer_hash, model_id, model_hash
  )
    REFERENCES qc2_governance_owner.champion_pointer(
      id, epoch_id, generation, pointer_hash, model_id, model_hash
    )
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE qc2_governance_owner.promotion_approval_nonce (
  nonce_hash text PRIMARY KEY CHECK (nonce_hash ~ '^[0-9a-f]{64}$'),
  decision_id uuid NOT NULL UNIQUE,
  request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  expected_generation integer NOT NULL CHECK (expected_generation >= 0),
  expected_pointer_hash text CHECK (
    expected_pointer_hash IS NULL OR expected_pointer_hash ~ '^[0-9a-f]{64}$'
  ),
  consumed_at timestamptz NOT NULL,
  FOREIGN KEY (decision_id)
    REFERENCES qc2_governance_owner.promotion_transition_receipt(decision_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE qc2_governance_owner.promotion_rollback_retention (
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  source_receipt_id uuid NOT NULL,
  source_receipt_hash text NOT NULL CHECK (source_receipt_hash ~ '^[0-9a-f]{64}$'),
  retained_at timestamptz NOT NULL,
  PRIMARY KEY (model_id, model_hash, source_receipt_id),
  FOREIGN KEY (model_id, model_hash)
    REFERENCES qc2_models_prediction.model_registry_model(id, content_hash)
    ON DELETE RESTRICT,
  FOREIGN KEY (source_receipt_id, source_receipt_hash)
    REFERENCES qc2_governance_owner.promotion_transition_receipt(id, receipt_hash)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_governance_owner.champion_load_confirmation (
  sequence_no bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id uuid NOT NULL UNIQUE CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  epoch_id uuid NOT NULL,
  pointer_id uuid NOT NULL,
  generation integer NOT NULL CHECK (generation > 0),
  pointer_hash text NOT NULL CHECK (pointer_hash ~ '^[0-9a-f]{64}$'),
  model_id uuid NOT NULL,
  model_hash text NOT NULL CHECK (model_hash ~ '^[0-9a-f]{64}$'),
  worker_id uuid NOT NULL CHECK (
    worker_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  status text NOT NULL CHECK (status IN ('LOADED', 'FAILED')),
  receipt_hash text NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
  failure_code text CHECK (
    failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  checked_at timestamptz NOT NULL,
  FOREIGN KEY (pointer_id, epoch_id, generation, pointer_hash, model_id, model_hash)
    REFERENCES qc2_governance_owner.champion_pointer(
      id, epoch_id, generation, pointer_hash, model_id, model_hash
    )
    ON DELETE RESTRICT,
  CHECK ((status = 'FAILED') OR failure_code IS NULL)
);

CREATE INDEX champion_load_confirmation_latest
  ON qc2_governance_owner.champion_load_confirmation
    (epoch_id, pointer_id, generation, sequence_no DESC);

CREATE FUNCTION qc2_governance_owner.prevent_transition_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'promotion transition records are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER promotion_transition_receipt_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.promotion_transition_receipt
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_transition_record_mutation();

CREATE TRIGGER promotion_approval_nonce_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.promotion_approval_nonce
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_transition_record_mutation();

CREATE TRIGGER promotion_rollback_retention_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.promotion_rollback_retention
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_transition_record_mutation();

CREATE TRIGGER champion_load_confirmation_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.champion_load_confirmation
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_transition_record_mutation();

ALTER TABLE qc2_governance_owner.promotion_transition_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.promotion_approval_nonce ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.promotion_rollback_retention ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_governance_owner.champion_load_confirmation ENABLE ROW LEVEL SECURITY;

CREATE POLICY promotion_transition_receipt_migrator_all
  ON qc2_governance_owner.promotion_transition_receipt
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY promotion_approval_nonce_migrator_all
  ON qc2_governance_owner.promotion_approval_nonce
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY promotion_rollback_retention_migrator_all
  ON qc2_governance_owner.promotion_rollback_retention
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY champion_load_confirmation_migrator_all
  ON qc2_governance_owner.champion_load_confirmation
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

REVOKE ALL ON qc2_governance_owner.promotion_transition_receipt,
  qc2_governance_owner.promotion_approval_nonce,
  qc2_governance_owner.promotion_rollback_retention,
  qc2_governance_owner.champion_load_confirmation
FROM PUBLIC, qc2_runtime_promotion, qc2_runtime_inference, qc2_runtime_prediction;
REVOKE ALL ON FUNCTION qc2_governance_owner.prevent_transition_record_mutation()
FROM PUBLIC;

CREATE FUNCTION qc2_governance_owner.ensure_no_champion_slot(p_epoch_id uuid)
RETURNS qc2_governance_owner.operating_pointer_slot
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_control
AS $function$
DECLARE
  slot_row qc2_governance_owner.operating_pointer_slot%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('promotion');
  IF p_epoch_id::text !~
    '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'epoch identity must be UUIDv7' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
       SELECT 1
       FROM qc2_governance_owner.operating_pointer_slot
       WHERE epoch_id = p_epoch_id
     )
     AND EXISTS (
       SELECT 1
       FROM qc2_governance_owner.champion_pointer
       WHERE epoch_id = p_epoch_id AND role = 'OPERATING'
     ) THEN
    RAISE EXCEPTION 'untracked operating pointer requires reconciliation, not bootstrap'
      USING ERRCODE = '55000';
  END IF;
  INSERT INTO qc2_governance_owner.operating_pointer_slot(
    epoch_id, slot_state, pointer_id, model_id, model_hash, generation
  )
  VALUES (p_epoch_id, 'NO_CHAMPION', NULL, NULL, NULL, 0)
  ON CONFLICT (epoch_id) DO NOTHING;
  SELECT * INTO STRICT slot_row
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = p_epoch_id;
  IF slot_row.slot_state = 'NO_CHAMPION'
     AND EXISTS (
       SELECT 1
       FROM qc2_governance_owner.champion_pointer
       WHERE epoch_id = p_epoch_id AND role = 'OPERATING'
     ) THEN
    RAISE EXCEPTION 'NO_CHAMPION conflicts with a retained operating pointer'
      USING ERRCODE = '55000';
  END IF;
  RETURN slot_row;
END
$function$;

CREATE FUNCTION qc2_governance_owner.commit_champion_transition(
  p_request jsonb,
  p_bundle jsonb,
  p_decision jsonb,
  p_ticket jsonb,
  p_transition_kind text,
  p_fault_at text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_models_prediction,
  qc2_integrity_build, qc2_control
AS $function$
DECLARE
  v_epoch_id uuid;
  v_request_id uuid;
  v_decision_id uuid;
  v_candidate_id uuid;
  v_candidate_hash text;
  v_candidate qc2_models_prediction.model_registry_model%ROWTYPE;
  v_old qc2_models_prediction.model_registry_model%ROWTYPE;
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_current_pointer qc2_governance_owner.champion_pointer%ROWTYPE;
  v_existing qc2_governance_owner.promotion_transition_receipt%ROWTYPE;
  v_receipt_id uuid;
  v_pointer_id uuid;
  v_event_id uuid;
  v_nonce_hash text;
  v_pointer_hash text;
  v_evidence_hash text;
  v_receipt_hash text;
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_now_text text;
  v_new_generation integer;
  v_event_payload jsonb;
  v_event_source_refs jsonb;
  v_pointer_base jsonb;
  v_pointer_contract jsonb;
  v_receipt_contract jsonb;
  v_load_payload jsonb;
  v_source_refs jsonb;
  v_lifecycle_sequence integer;
  v_changed integer;
  v_ticket_generation text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('promotion');

  IF pg_catalog.jsonb_typeof(p_request) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_bundle) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_decision) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_ticket) IS DISTINCT FROM 'object'
     OR p_transition_kind IS NULL
     OR p_transition_kind NOT IN (
       'initial_bootstrap', 'promotion', 'forward_rollback'
     ) THEN
    RAISE EXCEPTION 'promotion transition input is invalid' USING ERRCODE = '22023';
  END IF;
  IF p_request->>'schema_name' IS DISTINCT FROM
       'qc2.governance_owner.PromotionRequest.v1'
     OR p_request->>'schema_version' IS DISTINCT FROM '1.0'
     OR p_bundle->>'schema_name' IS DISTINCT FROM
       'qc2.governance_owner.PromotionBundleManifest.v1'
     OR p_bundle->>'schema_version' IS DISTINCT FROM '1.0'
     OR p_decision->>'schema_name' IS DISTINCT FROM
       'qc2.governance_owner.PromotionDecision.v1'
     OR p_decision->>'schema_version' IS DISTINCT FROM '1.0'
     OR p_bundle->>'transition_intent' IS DISTINCT FROM p_transition_kind
     OR p_decision->>'decision' IS DISTINCT FROM 'APPROVE' THEN
    RAISE EXCEPTION 'transition contracts or explicit intent do not match'
      USING ERRCODE = '22023';
  END IF;
  IF p_bundle->>'environment_namespace' IS DISTINCT FROM 'test'
     OR p_request->>'environment_namespace' IS DISTINCT FROM 'test'
     OR p_decision->>'environment_namespace' IS DISTINCT FROM 'test'
     OR p_bundle->>'evidence_class' IS DISTINCT FROM 'SYNTHETIC_FIXTURE'
     OR p_request->>'evidence_class' IS DISTINCT FROM 'SYNTHETIC_FIXTURE'
     OR p_decision->>'evidence_class' IS DISTINCT FROM 'SYNTHETIC_FIXTURE' THEN
    RAISE EXCEPTION
      'real owner approval and non-test Champion transitions remain disabled'
      USING ERRCODE = '42501';
  END IF;
  IF p_fault_at IS NOT NULL AND p_fault_at NOT IN (
    'before_nonce_consumption', 'after_nonce_consumption',
    'before_evidence', 'after_evidence',
    'before_receipt', 'after_receipt',
    'before_lifecycle', 'after_lifecycle',
    'before_pointer_insert', 'after_pointer_insert',
    'before_slot_cas', 'after_slot_cas',
    'before_outbox', 'after_outbox'
  ) THEN
    RAISE EXCEPTION 'unknown transition fault point' USING ERRCODE = '22023';
  END IF;

  IF COALESCE(p_request->>'id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR COALESCE(p_decision->>'id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR COALESCE(p_bundle->>'id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR COALESCE(p_request->>'request_hash', '') !~ '^[0-9a-f]{64}$'
     OR COALESCE(p_bundle->>'content_hash', '') !~ '^[0-9a-f]{64}$'
     OR COALESCE(p_decision->>'content_hash', '') !~ '^[0-9a-f]{64}$'
     OR p_ticket->>'nonce' IS NULL
     OR p_ticket->>'nonce' = ''
     OR p_request->>'expires_at' IS NULL
     OR p_bundle->>'expires_at' IS NULL
     OR p_ticket->>'request_hash' IS DISTINCT FROM p_request->>'request_hash'
     OR (p_decision->>'request_hash') IS DISTINCT FROM p_request->>'request_hash'
     OR (p_ticket->'decision_ref'->>'target_schema_name')
       IS DISTINCT FROM 'qc2.governance_owner.PromotionDecision.v1'
     OR (p_ticket->'decision_ref'->>'target_id') IS DISTINCT FROM p_decision->>'id'
     OR (p_ticket->'decision_ref'->>'content_hash')
       IS DISTINCT FROM p_decision->>'content_hash'
     OR (p_decision->'challenge_ref'->>'target_schema_name')
       IS DISTINCT FROM 'qc2.governance_owner.PromotionChallenge.v1'
     OR (p_decision->'challenge_ref'->>'target_id')
       IS DISTINCT FROM (p_ticket->'promotion_challenge_ref'->>'target_id')
     OR (p_ticket->'promotion_challenge_ref'->>'target_schema_name')
       IS DISTINCT FROM 'qc2.governance_owner.PromotionChallenge.v1'
     OR (p_decision->'challenge_ref'->>'content_hash')
       IS DISTINCT FROM (p_ticket->'promotion_challenge_ref'->>'content_hash')
     OR COALESCE(p_decision->'challenge_ref'->>'target_id', '') !~
       '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR COALESCE(p_decision->'challenge_ref'->>'content_hash', '') !~
       '^[0-9a-f]{64}$'
     OR (p_request->'bundle_ref'->>'target_id') IS DISTINCT FROM p_bundle->>'id'
     OR (p_request->'bundle_ref'->>'target_schema_name')
       IS DISTINCT FROM 'qc2.governance_owner.PromotionBundleManifest.v1'
     OR (p_request->'bundle_ref'->>'content_hash')
       IS DISTINCT FROM p_bundle->>'content_hash'
     OR (p_request->'candidate_model_ref') IS DISTINCT FROM
       (p_bundle->'candidate_model_ref')
     OR (p_request->'epoch_ref') IS DISTINCT FROM (p_bundle->'epoch_ref')
     OR (p_bundle->>'content_hash') IS DISTINCT FROM
       qc2_integrity_build.hash_json(
         'qc2.contract-content.v1/qc2.governance_owner.promotionbundlemanifest.v1/1.0',
         p_bundle - ARRAY[
           'schema_name', 'schema_version', 'id', 'created_at', 'content_hash'
         ]::text[]
       )
     OR (p_decision->>'content_hash') IS DISTINCT FROM
       qc2_integrity_build.hash_json(
         'qc2.contract-content.v1/qc2.governance_owner.promotiondecision.v1/1.0',
         p_decision - ARRAY[
           'schema_name', 'schema_version', 'id', 'created_at', 'content_hash'
         ]::text[]
       ) THEN
    RAISE EXCEPTION 'request, decision, bundle, or ticket binding is invalid'
      USING ERRCODE = '22023';
  END IF;
  v_ticket_generation := p_ticket->>'expected_generation';
  IF COALESCE(v_ticket_generation, '') !~ '^(0|[1-9][0-9]{0,9})$' THEN
    RAISE EXCEPTION 'approval expected generation is invalid' USING ERRCODE = '22023';
  END IF;

  v_epoch_id := (p_request->'epoch_ref'->>'target_id')::uuid;
  v_request_id := (p_request->>'id')::uuid;
  v_decision_id := (p_decision->>'id')::uuid;
  v_candidate_id := (p_request->'candidate_model_ref'->>'target_id')::uuid;
  v_candidate_hash := p_request->'candidate_model_ref'->>'content_hash';
  IF p_request->'candidate_model_ref'->>'target_schema_name' IS DISTINCT FROM
       'qc2.models_prediction.ModelManifest.v1'
     OR p_bundle->'candidate_model_ref'->>'target_schema_name' IS DISTINCT FROM
       'qc2.models_prediction.ModelManifest.v1'
     OR p_request->'epoch_ref'->>'target_schema_name' IS DISTINCT FROM
       'qc2.validation.ValidationEpoch.v1'
     OR p_bundle->'epoch_ref'->>'target_schema_name' IS DISTINCT FROM
       'qc2.validation.ValidationEpoch.v1'
     OR COALESCE(v_candidate_hash, '') !~ '^[0-9a-f]{64}$'
     OR (p_bundle->'candidate_model_ref'->>'content_hash')
       IS DISTINCT FROM v_candidate_hash
     OR (p_bundle->'epoch_ref'->>'target_id') IS DISTINCT FROM v_epoch_id::text THEN
    RAISE EXCEPTION 'candidate or epoch binding is invalid' USING ERRCODE = '22023';
  END IF;

  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = v_epoch_id
  FOR UPDATE;
  SELECT receipt_row.* INTO v_existing
  FROM qc2_governance_owner.promotion_transition_receipt AS receipt_row
  JOIN qc2_governance_owner.promotion_approval_nonce AS nonce_row
    ON nonce_row.decision_id = receipt_row.decision_id
  WHERE receipt_row.decision_id = v_decision_id
    AND receipt_row.request_id = v_request_id
     AND nonce_row.request_hash = p_request->>'request_hash'
     AND nonce_row.expected_generation::text = v_ticket_generation
     AND nonce_row.expected_pointer_hash IS NOT DISTINCT FROM
       p_ticket->>'expected_champion_hash'
    AND nonce_row.nonce_hash = qc2_integrity_build.hash_json(
      'qc2.owner-approval-nonce.v1',
      pg_catalog.jsonb_build_object('nonce', p_ticket->>'nonce')
    );
  -- The stored nonce makes exact retries idempotent after the approval expires.
  IF FOUND THEN
    RETURN v_existing.receipt_contract;
  END IF;

  IF (p_request->>'expires_at')::timestamptz <= v_now
     OR (p_bundle->>'expires_at')::timestamptz <= v_now THEN
    RAISE EXCEPTION 'promotion request or bundle has expired'
      USING ERRCODE = '40001';
  END IF;
  IF v_slot.slot_state = 'NO_CHAMPION' THEN
    IF p_transition_kind <> 'initial_bootstrap'
       OR v_slot.generation <> 0
       OR v_slot.pointer_id IS NOT NULL
       OR p_bundle->'prior_champion_ref' IS DISTINCT FROM 'null'::jsonb
       OR p_request->'expected_champion_ref' IS DISTINCT FROM 'null'::jsonb THEN
      RAISE EXCEPTION 'initial bootstrap requires the explicit NO_CHAMPION state'
        USING ERRCODE = '40001';
    END IF;
  ELSE
    SELECT * INTO STRICT v_current_pointer
    FROM qc2_governance_owner.champion_pointer
    WHERE id = v_slot.pointer_id
      AND epoch_id = v_epoch_id
      AND role = 'OPERATING'
      AND generation = v_slot.generation
      AND model_id = v_slot.model_id
      AND model_hash = v_slot.model_hash;
  END IF;
  IF v_ticket_generation IS DISTINCT FROM v_slot.generation::text
     OR p_ticket->>'expected_champion_hash' IS DISTINCT FROM
       (
         CASE
           WHEN v_slot.pointer_id IS NULL THEN NULL
           ELSE v_current_pointer.pointer_hash
         END
       ) THEN
    RAISE EXCEPTION 'approval is stale for the current Champion generation'
      USING ERRCODE = '40001';
  END IF;
  IF v_slot.slot_state = 'CHAMPION_SET' THEN
    IF p_transition_kind = 'initial_bootstrap'
       OR p_bundle->'prior_champion_ref'->>'target_schema_name' IS DISTINCT FROM
         'qc2.governance_owner.ChampionPointer.v1'
       OR p_bundle->'prior_champion_ref'->>'target_id'
         IS DISTINCT FROM v_current_pointer.id::text
       OR (
         p_bundle->'prior_champion_ref' ? 'content_hash'
         AND p_bundle->'prior_champion_ref'->>'content_hash'
           IS DISTINCT FROM v_current_pointer.pointer_hash
       )
       OR p_request->'expected_champion_ref'->>'target_schema_name'
         IS DISTINCT FROM 'qc2.governance_owner.ChampionPointer.v1'
       OR p_request->'expected_champion_ref'->>'target_id'
         IS DISTINCT FROM v_current_pointer.id::text
       OR (
         p_request->'expected_champion_ref' ? 'content_hash'
         AND p_request->'expected_champion_ref'->>'content_hash'
           IS DISTINCT FROM v_current_pointer.pointer_hash
       ) THEN
      RAISE EXCEPTION 'bundle prior Champion does not match the locked operating pointer'
        USING ERRCODE = '40001';
    END IF;
  END IF;

  PERFORM 1
  FROM qc2_models_prediction.model_registry_model AS model_row
  WHERE model_row.id = v_candidate_id
     OR model_row.id = v_slot.model_id
  ORDER BY model_row.id
  FOR UPDATE;
  SELECT * INTO STRICT v_candidate
  FROM qc2_models_prediction.model_registry_model
  WHERE id = v_candidate_id;
  IF v_candidate.content_hash <> v_candidate_hash
     OR v_candidate.environment_namespace <> 'test'
     OR v_candidate.evidence_class <> 'SYNTHETIC_FIXTURE'
     OR (p_transition_kind IN ('initial_bootstrap', 'promotion')
         AND v_candidate.lifecycle_state <> 'PROMOTION_ELIGIBLE')
     OR (p_transition_kind = 'forward_rollback'
         AND (
           v_slot.slot_state <> 'CHAMPION_SET'
           OR v_candidate.lifecycle_state <> 'RETIRED'
           OR NOT EXISTS (
             SELECT 1
              FROM qc2_governance_owner.promotion_rollback_retention AS retained
             WHERE retained.model_id = v_candidate.id
               AND retained.model_hash = v_candidate.content_hash
           )
         ))
     OR (v_slot.slot_state = 'CHAMPION_SET'
         AND v_candidate.id = v_slot.model_id) THEN
    RAISE EXCEPTION 'candidate lifecycle or rollback-retention requirement failed'
      USING ERRCODE = '42501';
  END IF;
  IF v_slot.slot_state = 'CHAMPION_SET' THEN
    SELECT * INTO STRICT v_old
    FROM qc2_models_prediction.model_registry_model
    WHERE id = v_slot.model_id
      AND content_hash = v_slot.model_hash;
    IF v_old.lifecycle_state <> 'CHAMPION' THEN
      RAISE EXCEPTION 'operating pointer and model lifecycle disagree'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  v_nonce_hash := qc2_integrity_build.hash_json(
    'qc2.owner-approval-nonce.v1',
    pg_catalog.jsonb_build_object('nonce', p_ticket->>'nonce')
  );
  IF p_fault_at = 'before_nonce_consumption' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO qc2_governance_owner.promotion_approval_nonce(
    nonce_hash, decision_id, request_hash, expected_generation,
    expected_pointer_hash, consumed_at
  )
  VALUES (
    v_nonce_hash,
    v_decision_id,
    p_request->>'request_hash',
    v_slot.generation,
    CASE WHEN v_slot.pointer_id IS NULL THEN NULL ELSE v_current_pointer.pointer_hash END,
    v_now
  );
  IF p_fault_at = 'after_nonce_consumption' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  v_now_text := pg_catalog.to_char(
    v_now AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
  );
  v_receipt_id := qc2_integrity_build.new_uuid_v7();
  v_pointer_id := qc2_integrity_build.new_uuid_v7();
  v_new_generation := v_slot.generation + 1;
  v_source_refs := pg_catalog.jsonb_build_array(
    p_request->'bundle_ref',
    pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionRequest.v1',
      'target_id', v_request_id::text
    ),
    pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionDecision.v1',
      'target_id', v_decision_id::text,
      'content_hash', p_decision->>'content_hash'
    )
  );
  v_event_source_refs := v_source_refs;
  v_event_payload := pg_catalog.jsonb_build_object(
    'transition_kind', p_transition_kind,
    'request_id', v_request_id::text,
    'decision_id', v_decision_id::text,
    'epoch_id', v_epoch_id::text,
    'prior_generation', v_slot.generation,
    'new_generation', v_new_generation,
    'pointer_id', v_pointer_id::text,
    'approval_nonce_hash', v_nonce_hash
  );
  IF p_fault_at = 'before_evidence' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  v_event_id := qc2_integrity_build.append_event_internal(
    'champion_transition_committed',
    v_event_payload,
    v_new_generation,
    v_event_source_refs
  );
  SELECT content_hash INTO STRICT v_evidence_hash
  FROM qc2_integrity_build.evidence_event
  WHERE id = v_event_id;
  IF p_fault_at = 'after_evidence' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  v_pointer_base := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.ChampionPointer.v1',
    'schema_version', '1.0',
    'id', v_pointer_id::text,
    'created_at', v_now_text,
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', v_source_refs,
    'epoch_ref', p_request->'epoch_ref',
    'role', 'OPERATING',
    'model_ref', p_request->'candidate_model_ref',
    'generation', v_new_generation,
    'transitioned_at', v_now_text,
    'transition_receipt_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionReceipt.v1',
      'target_id', v_receipt_id::text
    )
  );
  v_pointer_hash := qc2_integrity_build.hash_json(
    'qc2.governance_owner.champion_pointer.v1', v_pointer_base
  );
  v_pointer_contract := v_pointer_base || pg_catalog.jsonb_build_object(
    'pointer_hash', v_pointer_hash
  );
  v_receipt_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.PromotionReceipt.v1',
    'schema_version', '1.0',
    'id', v_receipt_id::text,
    'created_at', v_now_text,
    'owning_authority', 'promotion',
    'evidence_class', 'SYNTHETIC_FIXTURE',
    'environment_namespace', 'test',
    'source_refs', v_source_refs,
    'request_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionRequest.v1',
      'target_id', v_request_id::text
    ),
    'decision_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionDecision.v1',
      'target_id', v_decision_id::text,
      'content_hash', p_decision->>'content_hash'
    ),
    'transition_state', 'COMMITTED',
    'prior_generation', v_slot.generation,
    'new_generation', v_new_generation,
    'committed_at', v_now_text,
    'evidence_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.integrity_build.EvidenceEvent.v1',
      'target_id', v_event_id::text,
      'content_hash', v_evidence_hash
    ),
    'pointer_hash', v_pointer_hash
  );
  v_receipt_hash := qc2_integrity_build.hash_json(
    'qc2.promotion.transition_receipt-record.v1',
    v_receipt_contract
  );
  IF p_fault_at = 'before_receipt' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO qc2_governance_owner.promotion_transition_receipt(
    id, epoch_id, request_id, decision_id, transition_kind,
    prior_generation, new_generation, pointer_id, pointer_hash, model_id,
    model_hash, receipt_hash, nonce_hash, committed_at, receipt_contract
  )
  VALUES (
    v_receipt_id, v_epoch_id, v_request_id, v_decision_id, p_transition_kind,
    v_slot.generation, v_new_generation, v_pointer_id, v_pointer_hash,
    v_candidate.id, v_candidate.content_hash, v_receipt_hash, v_nonce_hash,
    v_now, v_receipt_contract
  );
  IF p_fault_at = 'after_receipt' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  IF p_fault_at = 'before_lifecycle' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  PERFORM pg_catalog.set_config('qc2.model_lifecycle_transition', 'authorized', true);
  IF v_slot.slot_state = 'CHAMPION_SET' THEN
    PERFORM qc2_models_prediction.record_model_lifecycle_transition(
      v_old.id,
      'CHAMPION',
      'RETIRED',
      v_receipt_contract || pg_catalog.jsonb_build_object(
        'content_hash', v_receipt_hash
      ),
      v_now
    );
    INSERT INTO qc2_governance_owner.promotion_rollback_retention(
      model_id, model_hash, source_receipt_id, source_receipt_hash, retained_at
    )
    VALUES (
      v_old.id, v_old.content_hash, v_receipt_id, v_receipt_hash, v_now
    );
  END IF;
  UPDATE qc2_models_prediction.model_registry_model
  SET lifecycle_state = 'CHAMPION'
  WHERE id = v_candidate.id
    AND content_hash = v_candidate.content_hash
    AND lifecycle_state = v_candidate.lifecycle_state;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'candidate lifecycle changed concurrently'
      USING ERRCODE = '40001';
  END IF;
  SELECT COALESCE(pg_catalog.max(sequence_no), 0) + 1 INTO v_lifecycle_sequence
  FROM qc2_models_prediction.model_lifecycle_event
  WHERE model_id = v_candidate.id AND model_hash = v_candidate.content_hash;
  INSERT INTO qc2_models_prediction.model_lifecycle_event(
    model_id, model_hash, sequence_no, prior_state, next_state,
    evidence_ref, runtime_authority, transitioned_at
  )
  VALUES (
    v_candidate.id, v_candidate.content_hash, v_lifecycle_sequence,
    v_candidate.lifecycle_state, 'CHAMPION',
    pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.PromotionReceipt.v1',
      'target_id', v_receipt_id::text,
      'content_hash', v_receipt_hash
    ),
    'promotion', v_now
  );
  IF p_fault_at = 'after_lifecycle' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  IF p_fault_at = 'before_pointer_insert' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO qc2_governance_owner.champion_pointer(
    id, epoch_id, role, model_id, model_hash, generation, pointer_hash,
    evidence_class, environment_namespace, created_at, pointer_contract
  )
  VALUES (
    v_pointer_id, v_epoch_id, 'OPERATING', v_candidate.id, v_candidate.content_hash,
    v_new_generation, v_pointer_hash, 'SYNTHETIC_FIXTURE', 'test', v_now,
    v_pointer_contract
  );
  IF p_fault_at = 'after_pointer_insert' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  IF p_fault_at = 'before_slot_cas' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  UPDATE qc2_governance_owner.operating_pointer_slot
  SET slot_state = 'CHAMPION_SET',
      pointer_id = v_pointer_id,
      model_id = v_candidate.id,
      model_hash = v_candidate.content_hash,
      generation = v_new_generation
  WHERE epoch_id = v_epoch_id
    AND slot_state = v_slot.slot_state
    AND generation = v_slot.generation
    AND pointer_id IS NOT DISTINCT FROM v_slot.pointer_id
    AND model_id IS NOT DISTINCT FROM v_slot.model_id
    AND model_hash IS NOT DISTINCT FROM v_slot.model_hash;
  GET DIAGNOSTICS v_changed = ROW_COUNT;
  IF v_changed <> 1 THEN
    RAISE EXCEPTION 'Champion slot compare-and-swap failed'
      USING ERRCODE = '40001';
  END IF;
  IF p_fault_at = 'after_slot_cas' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;

  v_load_payload := pg_catalog.jsonb_build_object(
    'epoch_id', v_epoch_id::text,
    'pointer_id', v_pointer_id::text,
    'pointer_hash', v_pointer_hash,
    'generation', v_new_generation,
    'model_id', v_candidate.id::text,
    'model_hash', v_candidate.content_hash
  );
  IF p_fault_at = 'before_outbox' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO qc2_control.outbox_message(
    id, logical_operation_id, owner_authority, message_type, payload_hash
  )
  VALUES (
    qc2_integrity_build.new_uuid_v7(),
    v_receipt_id,
    'durable_job_service',
    'champion_model_load',
    qc2_integrity_build.hash_json(
      'qc2.promotion.champion_load_request.v1', v_load_payload
    )
  );
  IF p_fault_at = 'after_outbox' THEN
    RAISE EXCEPTION 'injected transition fault' USING ERRCODE = 'P0001';
  END IF;
  RETURN v_receipt_contract;
END
$function$;

CREATE FUNCTION qc2_governance_owner.get_champion_load_request(p_receipt_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  v_receipt qc2_governance_owner.promotion_transition_receipt%ROWTYPE;
  v_pointer qc2_governance_owner.champion_pointer%ROWTYPE;
  v_message qc2_control.outbox_message%ROWTYPE;
  v_payload jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('inference');
  SELECT * INTO STRICT v_receipt
  FROM qc2_governance_owner.promotion_transition_receipt
  WHERE id = p_receipt_id;
  SELECT * INTO STRICT v_pointer
  FROM qc2_governance_owner.champion_pointer
  WHERE id = v_receipt.pointer_id;
  SELECT * INTO STRICT v_message
  FROM qc2_control.outbox_message
  WHERE logical_operation_id = p_receipt_id
    AND message_type = 'champion_model_load';
  v_payload := pg_catalog.jsonb_build_object(
    'epoch_id', v_receipt.epoch_id::text,
    'pointer_id', v_receipt.pointer_id::text,
    'pointer_hash', v_receipt.pointer_hash,
    'generation', v_receipt.new_generation,
    'model_id', v_pointer.model_id::text,
    'model_hash', v_pointer.model_hash
  );
  IF pg_catalog.btrim(v_message.payload_hash) IS DISTINCT FROM
     qc2_integrity_build.hash_json(
       'qc2.promotion.champion_load_request.v1', v_payload
     ) THEN
    RAISE EXCEPTION 'durable load request payload hash does not match its receipt'
      USING ERRCODE = '23514';
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'message', pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.time_operation.OutboxMessage.v1',
      'schema_version', '1.0',
      'id', v_message.id::text,
      'created_at', pg_catalog.to_char(
        v_message.created_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
      ),
      'owning_authority', v_message.owner_authority,
      'evidence_class', v_receipt.receipt_contract->>'evidence_class',
      'environment_namespace', v_receipt.receipt_contract->>'environment_namespace',
      'source_refs', '[]'::jsonb,
      'logical_operation_id', v_message.logical_operation_id::text,
      'message_type', v_message.message_type,
      'payload_hash', pg_catalog.btrim(v_message.payload_hash),
      'status', v_message.status,
      'attempt_count', v_message.attempt_count,
      'next_attempt_at', v_message.next_attempt_at
    ),
    'load_request', v_payload,
    'pointer_contract', v_pointer.pointer_contract,
    'receipt_contract', v_receipt.receipt_contract,
    'receipt_hash', v_receipt.receipt_hash
  );
END
$function$;

CREATE FUNCTION qc2_governance_owner.record_champion_load_confirmation(
  p_epoch_id uuid,
  p_pointer_id uuid,
  p_generation integer,
  p_pointer_hash text,
  p_model_id uuid,
  p_model_hash text,
  p_worker_id uuid,
  p_status text,
  p_receipt_hash text,
  p_failure_code text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_integrity_build, qc2_control
AS $function$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_confirmation_id uuid;
  v_event_payload jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('inference');
  IF p_status NOT IN ('LOADED', 'FAILED')
     OR p_generation <= 0
     OR p_pointer_hash !~ '^[0-9a-f]{64}$'
     OR p_model_hash !~ '^[0-9a-f]{64}$'
     OR p_receipt_hash !~ '^[0-9a-f]{64}$'
     OR (p_status = 'FAILED' AND COALESCE(p_failure_code, '') !~
       '^[a-z][a-z0-9_-]{0,95}$')
     OR (p_status = 'LOADED' AND p_failure_code IS NOT NULL) THEN
    RAISE EXCEPTION 'worker load confirmation is invalid' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = p_epoch_id
  FOR SHARE;
  IF v_slot.slot_state <> 'CHAMPION_SET'
     OR v_slot.pointer_id <> p_pointer_id
     OR v_slot.generation <> p_generation
     OR v_slot.model_id <> p_model_id
     OR v_slot.model_hash <> p_model_hash
     OR NOT EXISTS (
       SELECT 1 FROM qc2_governance_owner.champion_pointer AS pointer_row
       WHERE pointer_row.id = p_pointer_id
         AND pointer_row.epoch_id = p_epoch_id
         AND pointer_row.generation = p_generation
         AND pointer_row.pointer_hash = p_pointer_hash
         AND pointer_row.model_id = p_model_id
         AND pointer_row.model_hash = p_model_hash
         AND pointer_row.role = 'OPERATING'
     ) THEN
    RAISE EXCEPTION 'worker confirmation is stale for the current pointer'
      USING ERRCODE = '40001';
  END IF;
  v_confirmation_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_governance_owner.champion_load_confirmation(
    id, epoch_id, pointer_id, generation, pointer_hash, model_id,
    model_hash, worker_id, status, receipt_hash, failure_code, checked_at
  )
  VALUES (
    v_confirmation_id, p_epoch_id, p_pointer_id, p_generation, p_pointer_hash,
    p_model_id, p_model_hash, p_worker_id, p_status, p_receipt_hash,
    p_failure_code, pg_catalog.clock_timestamp()
  );
  v_event_payload := pg_catalog.jsonb_build_object(
    'confirmation_id', v_confirmation_id::text,
    'epoch_id', p_epoch_id::text,
    'pointer_id', p_pointer_id::text,
    'generation', p_generation,
    'pointer_hash', p_pointer_hash,
    'model_id', p_model_id::text,
    'model_hash', p_model_hash,
    'status', p_status,
    'receipt_hash', p_receipt_hash,
    'failure_code', p_failure_code
  );
  PERFORM qc2_integrity_build.append_event_internal(
    'champion_model_load_confirmation', v_event_payload, p_generation
  );
  RETURN v_confirmation_id;
END
$function$;

CREATE FUNCTION qc2_governance_owner.assert_champion_load_ready(
  p_epoch_id uuid,
  p_generation integer,
  p_pointer_hash text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_control
AS $function$
DECLARE
  v_slot qc2_governance_owner.operating_pointer_slot%ROWTYPE;
  v_confirmation qc2_governance_owner.champion_load_confirmation%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('prediction');
  SELECT * INTO STRICT v_slot
  FROM qc2_governance_owner.operating_pointer_slot
  WHERE epoch_id = p_epoch_id
  FOR SHARE;
  IF v_slot.slot_state <> 'CHAMPION_SET'
     OR v_slot.generation <> p_generation
     OR NOT EXISTS (
       SELECT 1
       FROM qc2_governance_owner.champion_pointer AS pointer_row
       WHERE pointer_row.id = v_slot.pointer_id
         AND pointer_row.epoch_id = p_epoch_id
         AND pointer_row.generation = p_generation
         AND pointer_row.pointer_hash = p_pointer_hash
         AND pointer_row.role = 'OPERATING'
     ) THEN
    RAISE EXCEPTION 'requested generation is not the current committed Champion'
      USING ERRCODE = '55000';
  END IF;
  SELECT * INTO v_confirmation
  FROM qc2_governance_owner.champion_load_confirmation AS confirmation
  WHERE confirmation.epoch_id = p_epoch_id
    AND confirmation.pointer_id = v_slot.pointer_id
    AND confirmation.generation = p_generation
    AND confirmation.pointer_hash = p_pointer_hash
  ORDER BY confirmation.sequence_no DESC
  LIMIT 1;
  IF NOT FOUND OR v_confirmation.status <> 'LOADED'
     OR v_confirmation.model_id <> v_slot.model_id
     OR v_confirmation.model_hash <> v_slot.model_hash THEN
    RAISE EXCEPTION 'current Champion generation is not confirmed loaded'
      USING ERRCODE = '55000';
  END IF;
  RETURN v_slot.pointer_id;
END
$function$;

REVOKE ALL ON FUNCTION qc2_governance_owner.ensure_no_champion_slot(uuid),
  qc2_governance_owner.commit_champion_transition(jsonb, jsonb, jsonb, jsonb, text, text),
  qc2_governance_owner.record_champion_load_confirmation(
    uuid, uuid, integer, text, uuid, text, uuid, text, text, text
  ),
  qc2_governance_owner.get_champion_load_request(uuid),
  qc2_governance_owner.assert_champion_load_ready(uuid, integer, text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION qc2_governance_owner.ensure_no_champion_slot(uuid),
  qc2_governance_owner.commit_champion_transition(jsonb, jsonb, jsonb, jsonb, text, text)
TO qc2_runtime_promotion;
GRANT EXECUTE ON FUNCTION qc2_governance_owner.record_champion_load_confirmation(
  uuid, uuid, integer, text, uuid, text, uuid, text, text, text
) TO qc2_runtime_inference;
GRANT EXECUTE ON FUNCTION qc2_governance_owner.get_champion_load_request(uuid)
TO qc2_runtime_inference;
GRANT EXECUTE ON FUNCTION qc2_governance_owner.assert_champion_load_ready(uuid, integer, text)
TO qc2_runtime_prediction;
