-- QC2-045: immutable paper-order intents and transactional exposure reservations.
-- Runtime writes remain behind execution-owned SECURITY DEFINER functions.
SET ROLE qc2_migrator;

CREATE TABLE qc2_execution.paper_order_intent (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  idempotency_key text NOT NULL UNIQUE CHECK (
    idempotency_key ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  paper_account_fingerprint text NOT NULL CHECK (
    paper_account_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  intent_state text NOT NULL CHECK (intent_state IN (
    'CREATED','VERIFIED','RESERVED','QUEUED_FOR_SUBMISSION',
    'SUBMISSION_STARTED','ACKNOWLEDGED','SUBMISSION_UNKNOWN','REJECTED',
    'PARTIALLY_FILLED','FILLED','CANCEL_REQUESTED','CANCELLED','EXPIRED','REPLACED'
  )),
  intent_contract jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(intent_contract) = 'object'
    AND intent_contract->>'schema_name' = 'qc2.execution.PaperOrderIntent.v1'
    AND intent_contract->>'schema_version' = '1.0'
    AND intent_contract->>'id' = id::text
    AND intent_contract->>'idempotency_key' = idempotency_key
    AND intent_contract->>'paper_account_fingerprint' = paper_account_fingerprint
    AND intent_contract->>'content_hash' = content_hash
    AND intent_contract->>'intent_state' = intent_state
    AND intent_contract->>'account_mode' = 'PAPER'
    AND intent_contract->>'extended_hours' = 'false'
  ),
  created_at timestamptz NOT NULL,
  UNIQUE (id, idempotency_key, content_hash)
);

CREATE TABLE qc2_execution.paper_order_intent_reservation (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  intent_id uuid NOT NULL UNIQUE
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  resource_key text NOT NULL REFERENCES qc2_execution.reservation_resource(resource_key)
    ON DELETE RESTRICT,
  reserved_amount numeric(38, 12) NOT NULL CHECK (reserved_amount > 0),
  reservation_contract jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(reservation_contract) = 'object'
    AND reservation_contract->>'schema_name' = 'qc2.execution.Reservation.v1'
    AND reservation_contract->>'schema_version' = '1.0'
    AND reservation_contract->>'id' = id::text
    AND reservation_contract->'intent_ref'->>'target_id' = intent_id::text
    AND reservation_contract->>'state' = 'ACTIVE'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

ALTER TABLE qc2_execution.paper_order_intent ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_order_intent FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_order_intent_reservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.paper_order_intent_reservation FORCE ROW LEVEL SECURITY;

CREATE POLICY paper_order_intent_migrator_all
  ON qc2_execution.paper_order_intent
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY paper_order_reservation_migrator_all
  ON qc2_execution.paper_order_intent_reservation
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY paper_order_intent_execution_read
  ON qc2_execution.paper_order_intent
  FOR SELECT TO qc2_runtime_execution
  USING (true);
CREATE POLICY paper_order_reservation_execution_read
  ON qc2_execution.paper_order_intent_reservation
  FOR SELECT TO qc2_runtime_execution
  USING (true);

REVOKE ALL ON qc2_execution.paper_order_intent,
  qc2_execution.paper_order_intent_reservation
FROM PUBLIC, qc2_runtime_execution;
GRANT SELECT ON qc2_execution.paper_order_intent,
  qc2_execution.paper_order_intent_reservation
TO qc2_runtime_execution;

CREATE FUNCTION qc2_execution.prevent_paper_intent_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_execution
AS $function$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'paper-order intents are append-only'
      USING ERRCODE = '55000';
  END IF;
  IF ROW(
       NEW.id, NEW.idempotency_key, NEW.paper_account_fingerprint,
       NEW.content_hash, NEW.created_at,
       NEW.intent_contract - 'intent_state'
     ) IS DISTINCT FROM ROW(
       OLD.id, OLD.idempotency_key, OLD.paper_account_fingerprint,
       OLD.content_hash, OLD.created_at,
       OLD.intent_contract - 'intent_state'
     ) THEN
    RAISE EXCEPTION 'paper-order intent terms are immutable'
      USING ERRCODE = '42501';
  END IF;
  IF NOT (NEW.intent_state = ANY(pg_catalog.string_to_array(
       CASE OLD.intent_state
         WHEN 'CREATED' THEN 'VERIFIED,REJECTED'
         WHEN 'VERIFIED' THEN 'RESERVED,REJECTED,EXPIRED'
         WHEN 'RESERVED' THEN 'QUEUED_FOR_SUBMISSION,CANCELLED,EXPIRED'
         WHEN 'QUEUED_FOR_SUBMISSION' THEN 'SUBMISSION_STARTED,CANCELLED,EXPIRED'
         WHEN 'SUBMISSION_STARTED' THEN 'ACKNOWLEDGED,SUBMISSION_UNKNOWN,REJECTED'
         WHEN 'ACKNOWLEDGED' THEN 'PARTIALLY_FILLED,FILLED,CANCEL_REQUESTED,EXPIRED,REPLACED'
         WHEN 'SUBMISSION_UNKNOWN' THEN 'ACKNOWLEDGED,REJECTED,CANCEL_REQUESTED'
         WHEN 'PARTIALLY_FILLED' THEN 'FILLED,CANCEL_REQUESTED,CANCELLED,EXPIRED,REPLACED'
         WHEN 'CANCEL_REQUESTED' THEN 'CANCELLED,PARTIALLY_FILLED,FILLED,SUBMISSION_UNKNOWN'
         ELSE ''
       END,
       ','
     ))) THEN
    RAISE EXCEPTION 'invalid paper-order intent state transition: % -> %',
      OLD.intent_state, NEW.intent_state
      USING ERRCODE = '23514';
  END IF;
  IF NEW.intent_contract->>'intent_state' <> NEW.intent_state THEN
    RAISE EXCEPTION 'intent state column and contract state must match'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$function$;

CREATE TRIGGER paper_order_intent_immutable_terms
BEFORE UPDATE OR DELETE ON qc2_execution.paper_order_intent
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_paper_intent_rewrite();

CREATE FUNCTION qc2_execution.prevent_paper_reservation_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'paper-order reservation contracts are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER paper_order_reservation_append_only
BEFORE UPDATE OR DELETE ON qc2_execution.paper_order_intent_reservation
FOR EACH ROW EXECUTE FUNCTION qc2_execution.prevent_paper_reservation_rewrite();

CREATE FUNCTION qc2_control.persist_paper_order_intent(
  p_intent jsonb,
  p_expected_account_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  existing_intent qc2_execution.paper_order_intent%ROWTYPE;
  intent_id uuid;
  intent_key text;
  account_fingerprint text;
  expected_hash text;
  action_kind text;
  expected_source_schema text;
  expires_at timestamptz;
  limit_price numeric;
  quantity numeric;
  reservation_ref jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_intent IS NULL
     OR pg_catalog.jsonb_typeof(p_intent) <> 'object'
     OR NOT (p_intent ?& ARRAY[
       'schema_name','schema_version','owning_authority','intent_state',
       'account_mode','extended_hours','id','idempotency_key','content_hash',
       'paper_account_fingerprint','quantity_whole_shares','created_at',
       'expires_at','source_refs','episode_ref','action_kind','source_ref',
       'instrument_ref','side','order_type','time_in_force',
       'session_restriction','reservation_ref'
     ]::text[])
     OR p_intent->>'schema_name' IS DISTINCT FROM 'qc2.execution.PaperOrderIntent.v1'
     OR p_intent->>'schema_version' IS DISTINCT FROM '1.0'
     OR p_intent->>'owning_authority' IS DISTINCT FROM 'execution'
     OR p_intent->>'intent_state' IS DISTINCT FROM 'CREATED'
     OR p_intent->>'account_mode' IS DISTINCT FROM 'PAPER'
     OR p_intent->>'extended_hours' IS DISTINCT FROM 'false'
     OR p_intent->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_intent->>'idempotency_key' !~ '^[a-z][a-z0-9_-]{0,95}$'
     OR p_intent->>'content_hash' !~ '^[0-9a-f]{64}$'
     OR p_intent->>'paper_account_fingerprint' !~ '^[0-9a-f]{64}$'
     OR p_intent->>'action_kind' IS NULL
     OR p_intent->>'side' IS NULL
     OR p_intent->>'created_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$'
     OR p_intent->>'expires_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$'
     OR p_intent->>'id' IS NULL
     OR p_intent->>'idempotency_key' IS NULL
     OR p_intent->>'content_hash' IS NULL
     OR p_intent->>'paper_account_fingerprint' IS NULL
     OR p_expected_account_fingerprint IS NULL
     OR p_expected_account_fingerprint !~ '^[0-9a-f]{64}$'
     OR p_intent->>'quantity_whole_shares' IS NULL
     OR p_intent->>'quantity_whole_shares' !~ '^[1-9][0-9]*$'
     OR (p_intent->>'quantity_whole_shares')::numeric > 9007199254740991
     OR p_intent->>'created_at' IS NULL
     OR p_intent->>'expires_at' IS NULL
     OR pg_catalog.jsonb_typeof(p_intent->'source_refs') <> 'array'
     OR pg_catalog.jsonb_typeof(p_intent->'source_ref') <> 'object'
     OR pg_catalog.jsonb_typeof(p_intent->'instrument_ref') <> 'object'
     OR pg_catalog.jsonb_typeof(p_intent->'episode_ref') <> 'object'
     OR p_intent->'source_ref' IS NULL
     OR p_intent->'source_ref'->>'target_id' IS NULL
     OR p_intent->'source_ref'->>'target_schema_name' IS NULL
     OR p_intent->'instrument_ref'->>'target_id' IS NULL
     OR p_intent->'instrument_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.identity_market.Instrument.v1'
     OR p_intent->'episode_ref'->>'target_id' IS NULL
     OR p_intent->'episode_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.ExecutionEpisode.v1'
     OR p_intent->'episode_ref'->>'content_hash' !~ '^[0-9a-f]{64}$'
     OR pg_catalog.jsonb_typeof(p_intent->'reservation_ref') IS NULL THEN
    RAISE EXCEPTION 'paper-order intent envelope is invalid'
      USING ERRCODE = '22023';
  END IF;

  intent_id := (p_intent->>'id')::uuid;
  intent_key := p_intent->>'idempotency_key';
  account_fingerprint := p_intent->>'paper_account_fingerprint';
  IF account_fingerprint <> p_expected_account_fingerprint THEN
    RAISE EXCEPTION 'paper-order intent account does not match configured paper account'
      USING ERRCODE = '42501';
  END IF;

  expected_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.execution.paperorderintent.v1/1.0',
    p_intent - ARRAY[
      'schema_name','schema_version','id','created_at',
      'content_hash','intent_state'
    ]::text[]
  );
  IF expected_hash <> p_intent->>'content_hash' THEN
    RAISE EXCEPTION 'paper-order intent content hash is invalid'
      USING ERRCODE = '23514';
  END IF;

  action_kind := p_intent->>'action_kind';
  expected_source_schema := CASE action_kind
    WHEN 'OPEN_LONG' THEN 'qc2.models_prediction.Prediction.v1'
    WHEN 'REDUCE_LONG' THEN 'qc2.execution.Position.v1'
    WHEN 'CLOSE_LONG' THEN 'qc2.execution.Position.v1'
    WHEN 'CANCEL_PENDING_ENTRY' THEN 'qc2.execution.PaperOrderIntent.v1'
    WHEN 'REPLACE_ORDER' THEN 'qc2.execution.PaperOrderIntent.v1'
    ELSE NULL
  END;
  IF expected_source_schema IS NULL
     OR p_intent->'source_ref'->>'target_schema_name' IS DISTINCT FROM expected_source_schema
     OR p_intent->'source_ref'->>'target_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR (
       expected_source_schema IN (
         'qc2.models_prediction.Prediction.v1',
         'qc2.execution.PaperOrderIntent.v1'
       )
       AND p_intent->'source_ref'->>'content_hash' !~ '^[0-9a-f]{64}$'
     )
     OR (
       action_kind = 'OPEN_LONG'
       AND (
         p_intent->>'side' IS DISTINCT FROM 'BUY'
         OR p_intent->>'order_type' IS DISTINCT FROM 'LIMIT'
         OR p_intent->>'time_in_force' IS DISTINCT FROM 'DAY'
         OR p_intent->>'session_restriction' IS DISTINCT FROM 'REGULAR_SESSION_ONLY'
         OR p_intent->>'limit_price' IS NULL
         OR p_intent->>'limit_price' !~ '^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$'
         OR (p_intent->>'limit_price')::numeric <= 0
       )
     )
     OR (
       action_kind IN ('REDUCE_LONG','CLOSE_LONG')
       AND p_intent->>'side' IS DISTINCT FROM 'SELL'
     )
     OR (
       action_kind IN ('CANCEL_PENDING_ENTRY','REPLACE_ORDER')
       AND p_intent->>'side' NOT IN ('BUY','SELL')
     ) THEN
    RAISE EXCEPTION 'paper-order intent action, source reference, or side is invalid'
      USING ERRCODE = '23514';
  END IF;

  reservation_ref := p_intent->'reservation_ref';
  IF action_kind = 'CANCEL_PENDING_ENTRY' THEN
    IF reservation_ref IS DISTINCT FROM 'null'::jsonb THEN
      RAISE EXCEPTION 'cancel intents cannot create a second reservation'
        USING ERRCODE = '23514';
    END IF;
  ELSIF reservation_ref IS NULL
     OR pg_catalog.jsonb_typeof(reservation_ref) <> 'object'
     OR reservation_ref->>'target_schema_name' IS DISTINCT FROM 'qc2.execution.Reservation.v1'
     OR reservation_ref->>'target_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'order intent must bind its planned reservation identity'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO existing_intent
    FROM qc2_execution.paper_order_intent
    WHERE idempotency_key = intent_key
    FOR UPDATE;
  IF FOUND THEN
    IF existing_intent.id <> intent_id
       OR existing_intent.paper_account_fingerprint <> account_fingerprint
       OR existing_intent.content_hash <> p_intent->>'content_hash' THEN
      RAISE EXCEPTION 'idempotency key was reused with different immutable intent bytes'
        USING ERRCODE = '23505';
    END IF;
    RETURN existing_intent.id;
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(intent_key, 0)
  );
  SELECT * INTO existing_intent
    FROM qc2_execution.paper_order_intent
    WHERE idempotency_key = intent_key
    FOR UPDATE;
  IF FOUND THEN
    IF existing_intent.id <> intent_id
       OR existing_intent.paper_account_fingerprint <> account_fingerprint
       OR existing_intent.content_hash <> p_intent->>'content_hash' THEN
      RAISE EXCEPTION 'idempotency key was reused with different immutable intent bytes'
        USING ERRCODE = '23505';
    END IF;
    RETURN existing_intent.id;
  END IF;

  expires_at := (p_intent->>'expires_at')::timestamptz;
  IF expires_at <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'expired paper-order intent cannot be persisted'
      USING ERRCODE = '23514';
  END IF;
  IF action_kind = 'OPEN_LONG' THEN
    quantity := (p_intent->>'quantity_whole_shares')::numeric;
    limit_price := (p_intent->>'limit_price')::numeric;
    IF quantity * limit_price > 99999999999999999999999999.999999999999 THEN
      RAISE EXCEPTION 'paper-order notional exceeds reservation precision'
        USING ERRCODE = '22003';
    END IF;
  END IF;

  INSERT INTO qc2_execution.paper_order_intent(
    id, idempotency_key, paper_account_fingerprint, content_hash,
    intent_state, intent_contract, created_at
  )
  VALUES (
    intent_id, intent_key, account_fingerprint, p_intent->>'content_hash',
    'CREATED', p_intent, (p_intent->>'created_at')::timestamptz
  );

  PERFORM qc2_integrity_build.append_event_internal(
    'paper_order_intent_created',
    pg_catalog.jsonb_build_object(
      'intent_id', intent_id::text,
      'content_hash', p_intent->>'content_hash',
      'idempotency_key_hash', qc2_integrity_build.hash_json(
        'qc2.evidence.redacted-key.v1',
        pg_catalog.jsonb_build_object('key', intent_key)
      ),
      'action_kind', action_kind,
      'intent_state', 'CREATED'
    ),
    0,
    p_intent->'source_refs'
  );
  RETURN intent_id;
END
$function$;

CREATE FUNCTION qc2_control.reserve_paper_order_intent(
  p_intent_id uuid,
  p_reservation jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  prior_row qc2_execution.paper_order_intent%ROWTYPE;
  existing_reservation qc2_execution.paper_order_intent_reservation%ROWTYPE;
  reservation_id uuid;
  action_kind text;
  side text;
  v_resource_key text;
  reservation_key text;
  reservation_kind text;
  reserved_quantity numeric;
  reserved_cash numeric;
  order_quantity numeric;
  limit_price numeric;
  resource_capacity numeric;
  resource_reserved numeric;
  expected_amount numeric;
  prior_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = p_intent_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'paper-order intent does not exist'
      USING ERRCODE = '23503';
  END IF;

  SELECT * INTO existing_reservation
    FROM qc2_execution.paper_order_intent_reservation
    WHERE intent_id = p_intent_id
    FOR UPDATE;
  IF FOUND THEN
    IF existing_reservation.reservation_contract IS DISTINCT FROM p_reservation
       OR intent_row.intent_state <> 'RESERVED' THEN
      RAISE EXCEPTION 'intent reservation was retried with conflicting content'
        USING ERRCODE = '23505';
    END IF;
    RETURN existing_reservation.id;
  END IF;
  IF intent_row.intent_state = 'RESERVED'
     AND intent_row.intent_contract->>'action_kind' = 'CANCEL_PENDING_ENTRY'
     AND p_reservation IS NULL THEN
    RETURN NULL;
  END IF;

  IF intent_row.intent_state <> 'VERIFIED' THEN
    RAISE EXCEPTION 'only a verified paper-order intent can be reserved'
      USING ERRCODE = '23514';
  END IF;
  IF (intent_row.intent_contract->>'expires_at')::timestamptz
       <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'expired paper-order intent cannot be reserved'
      USING ERRCODE = '23514';
  END IF;

  action_kind := intent_row.intent_contract->>'action_kind';
  side := intent_row.intent_contract->>'side';
  order_quantity := (intent_row.intent_contract->>'quantity_whole_shares')::numeric;
  reservation_key := p_intent_id::text;

  IF action_kind IN ('CANCEL_PENDING_ENTRY','REPLACE_ORDER') THEN
    prior_id := (intent_row.intent_contract->'source_ref'->>'target_id')::uuid;
    SELECT * INTO prior_row
      FROM qc2_execution.paper_order_intent
      WHERE id = prior_id
      FOR UPDATE;
    IF NOT FOUND
       OR prior_row.paper_account_fingerprint <> intent_row.paper_account_fingerprint
       OR prior_row.intent_contract->'instrument_ref'->>'target_id'
            <> intent_row.intent_contract->'instrument_ref'->>'target_id'
       OR prior_row.intent_contract->>'content_hash'
            <> intent_row.intent_contract->'source_ref'->>'content_hash'
       OR prior_row.intent_state NOT IN (
         'CREATED','VERIFIED','RESERVED','QUEUED_FOR_SUBMISSION',
         'SUBMISSION_STARTED','SUBMISSION_UNKNOWN','ACKNOWLEDGED',
         'PARTIALLY_FILLED','CANCEL_REQUESTED'
       ) THEN
      RAISE EXCEPTION 'prior intent is missing, mismatched, or no longer pending'
        USING ERRCODE = '23514';
    END IF;
    IF action_kind = 'CANCEL_PENDING_ENTRY' THEN
      IF prior_row.intent_contract->>'action_kind' <> 'OPEN_LONG'
         OR prior_row.intent_contract->>'side' <> 'BUY'
         OR NOT EXISTS (
           SELECT 1
           FROM qc2_execution.paper_order_intent_reservation AS reservation
           JOIN qc2_execution.resource_reservation AS resource
             ON resource.resource_key = reservation.resource_key
            AND resource.reservation_key = prior_id::text
            AND resource.state = 'ACTIVE'
           WHERE reservation.intent_id = prior_id
         ) THEN
        RAISE EXCEPTION 'cancel intent must refer to a pending long entry'
          USING ERRCODE = '23514';
      END IF;
      UPDATE qc2_execution.paper_order_intent
        SET intent_state = 'RESERVED',
            intent_contract = pg_catalog.jsonb_set(
              intent_row.intent_contract, '{intent_state}', '"RESERVED"'::jsonb
            )
        WHERE id = p_intent_id;
      PERFORM qc2_integrity_build.append_event_internal(
        'paper_order_intent_reserved',
        pg_catalog.jsonb_build_object(
          'intent_id', p_intent_id::text,
          'intent_state', 'RESERVED',
          'effect', 'HOLD_PRIOR_UNTIL_DEFINITIVE_CANCEL',
          'prior_intent_id', prior_id::text
        ),
        0,
        intent_row.intent_contract->'source_refs'
      );
      RETURN NULL;
    END IF;
    IF prior_row.intent_contract->>'side' <> side
       OR prior_row.intent_contract->'instrument_ref'->>'target_id'
            <> intent_row.intent_contract->'instrument_ref'->>'target_id'
       OR NOT EXISTS (
         SELECT 1
         FROM qc2_execution.paper_order_intent_reservation AS reservation
         JOIN qc2_execution.resource_reservation AS resource
           ON resource.resource_key = reservation.resource_key
          AND resource.reservation_key = prior_id::text
          AND resource.state = 'ACTIVE'
         WHERE reservation.intent_id = prior_id
       ) THEN
      RAISE EXCEPTION 'replacement must preserve an active reservation for the same order'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF p_reservation IS NULL
     OR pg_catalog.jsonb_typeof(p_reservation) <> 'object'
     OR p_reservation->>'schema_name' <> 'qc2.execution.Reservation.v1'
     OR p_reservation->>'schema_version' <> '1.0'
     OR p_reservation->>'owning_authority' <> 'execution'
     OR p_reservation->>'state' <> 'ACTIVE'
     OR p_reservation->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_reservation->>'id' IS NULL
     OR p_reservation->'intent_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.PaperOrderIntent.v1'
     OR p_reservation->'intent_ref'->>'target_id' <> p_intent_id::text
     OR p_reservation->'intent_ref'->>'content_hash'
          <> intent_row.content_hash
     OR p_reservation->'episode_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.ExecutionEpisode.v1'
     OR p_reservation->'episode_ref'->>'target_id'
          <> intent_row.intent_contract->'episode_ref'->>'target_id'
     OR p_reservation->'episode_ref'->>'content_hash'
          <> intent_row.intent_contract->'episode_ref'->>'content_hash'
     OR p_reservation->'instrument_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.identity_market.Instrument.v1'
     OR p_reservation->'instrument_ref'->>'target_id'
          <> intent_row.intent_contract->'instrument_ref'->>'target_id'
     OR intent_row.intent_contract->'reservation_ref'->>'target_id'
          <> p_reservation->>'id'
     OR p_reservation->>'reserved_quantity' IS NULL
     OR p_reservation->>'reserved_quantity' !~ '^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$'
     OR p_reservation->>'reserved_cash' IS NULL
     OR p_reservation->>'reserved_cash' !~ '^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$' THEN
    RAISE EXCEPTION 'paper-order reservation contract is invalid or mismatched'
      USING ERRCODE = '23514';
  END IF;

  reservation_id := (p_reservation->>'id')::uuid;
  reservation_kind := p_reservation->>'reservation_kind';
  reserved_quantity := (p_reservation->>'reserved_quantity')::numeric;
  reserved_cash := (p_reservation->>'reserved_cash')::numeric;
  IF side = 'BUY' THEN
    IF action_kind NOT IN ('OPEN_LONG','REPLACE_ORDER')
       OR reservation_kind <> 'CASH'
       OR reserved_quantity <> 0 THEN
      RAISE EXCEPTION 'BUY order requires an exact cash reservation'
        USING ERRCODE = '23514';
    END IF;
    IF intent_row.intent_contract->>'limit_price' IS NULL
       OR intent_row.intent_contract->>'limit_price'
         !~ '^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$' THEN
      RAISE EXCEPTION 'BUY order requires a canonical positive limit price'
        USING ERRCODE = '23514';
    END IF;
    limit_price := (intent_row.intent_contract->>'limit_price')::numeric;
    IF limit_price <= 0 OR reserved_cash < order_quantity * limit_price THEN
      RAISE EXCEPTION 'BUY cash reservation is below limit notional'
        USING ERRCODE = '23514';
    END IF;
    expected_amount := reserved_cash;
    v_resource_key := 'paper_cash:' || intent_row.paper_account_fingerprint;
  ELSIF side = 'SELL' THEN
    IF action_kind NOT IN ('REDUCE_LONG','CLOSE_LONG','REPLACE_ORDER')
       OR reservation_kind <> 'SHARES'
       OR reserved_quantity <> order_quantity
       OR reserved_cash <> 0 THEN
      RAISE EXCEPTION 'SELL order requires an exact whole-share reservation'
        USING ERRCODE = '23514';
    END IF;
    expected_amount := reserved_quantity;
    v_resource_key := 'paper_shares:' || intent_row.paper_account_fingerprint
      || ':' || (intent_row.intent_contract->'instrument_ref'->>'target_id');
    IF action_kind = 'CLOSE_LONG' THEN
      SELECT capacity, reserved
        INTO resource_capacity, resource_reserved
        FROM qc2_execution.reservation_resource
        WHERE reservation_resource.resource_key = v_resource_key
        FOR UPDATE;
      IF NOT FOUND OR resource_capacity <> order_quantity OR resource_reserved <> 0 THEN
        RAISE EXCEPTION 'CLOSE_LONG must reserve the exact unreserved whole-share position'
          USING ERRCODE = '23514';
      END IF;
    END IF;
  ELSE
    RAISE EXCEPTION 'unsupported paper order side'
      USING ERRCODE = '23514';
  END IF;
  IF expected_amount <= 0
     OR expected_amount > 99999999999999999999999999.999999999999
     OR pg_catalog.scale(expected_amount) > 12 THEN
    RAISE EXCEPTION 'reservation amount is outside exact reservation precision'
      USING ERRCODE = '22003';
  END IF;

  PERFORM qc2_control.reserve_resource(
    reservation_id, v_resource_key, reservation_key, expected_amount
  );
  INSERT INTO qc2_execution.paper_order_intent_reservation(
    id, intent_id, resource_key, reserved_amount, reservation_contract
  )
  VALUES (
    reservation_id, p_intent_id, v_resource_key,
    expected_amount, p_reservation
  );

  UPDATE qc2_execution.paper_order_intent
    SET intent_state = 'RESERVED',
        intent_contract = pg_catalog.jsonb_set(
          intent_row.intent_contract, '{intent_state}', '"RESERVED"'::jsonb
        )
    WHERE id = p_intent_id;
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_order_reservation_created',
    pg_catalog.jsonb_build_object(
      'intent_id', p_intent_id::text,
      'reservation_id', reservation_id::text,
      'reservation_kind', reservation_kind,
      'reserved_amount', pg_catalog.trim_scale(expected_amount)::text,
      'resource_key_hash', qc2_integrity_build.hash_json(
        'qc2.evidence.redacted-key.v1',
        pg_catalog.jsonb_build_object('key', v_resource_key)
      )
    ),
    0,
    intent_row.intent_contract->'source_refs'
  );
  RETURN reservation_id;
END
$function$;

CREATE FUNCTION qc2_control.transition_paper_order_intent(
  p_intent_id uuid,
  p_new_state text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  allowed_states text;
  reservation_row qc2_execution.paper_order_intent_reservation%ROWTYPE;
  changed boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = p_intent_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  IF p_new_state = 'RESERVED' THEN
    RAISE EXCEPTION 'RESERVED state can only be reached through the reservation transaction'
      USING ERRCODE = '42501';
  END IF;
  allowed_states := CASE intent_row.intent_state
    WHEN 'CREATED' THEN 'VERIFIED,REJECTED'
    WHEN 'VERIFIED' THEN 'REJECTED,EXPIRED'
    WHEN 'RESERVED' THEN 'QUEUED_FOR_SUBMISSION,CANCELLED,EXPIRED'
    WHEN 'QUEUED_FOR_SUBMISSION' THEN 'SUBMISSION_STARTED,CANCELLED,EXPIRED'
    WHEN 'SUBMISSION_STARTED' THEN 'ACKNOWLEDGED,SUBMISSION_UNKNOWN,REJECTED'
    WHEN 'ACKNOWLEDGED' THEN 'PARTIALLY_FILLED,FILLED,CANCEL_REQUESTED,EXPIRED,REPLACED'
    WHEN 'SUBMISSION_UNKNOWN' THEN 'ACKNOWLEDGED,REJECTED,CANCEL_REQUESTED'
    WHEN 'PARTIALLY_FILLED' THEN 'FILLED,CANCEL_REQUESTED,CANCELLED,EXPIRED,REPLACED'
    WHEN 'CANCEL_REQUESTED' THEN 'CANCELLED,PARTIALLY_FILLED,FILLED,SUBMISSION_UNKNOWN'
    ELSE ''
  END;
  IF p_new_state IS NULL
     OR NOT (
       p_new_state = ANY(pg_catalog.string_to_array(allowed_states, ','))
     ) THEN
    RAISE EXCEPTION 'invalid paper-order intent state transition: % -> %',
      intent_row.intent_state, p_new_state
      USING ERRCODE = '23514';
  END IF;
  IF p_new_state IN ('VERIFIED','RESERVED','QUEUED_FOR_SUBMISSION')
     AND (intent_row.intent_contract->>'expires_at')::timestamptz
       <= pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'expired paper-order intent cannot advance toward submission'
      USING ERRCODE = '23514';
  END IF;
  IF p_new_state = 'EXPIRED'
     AND (intent_row.intent_contract->>'expires_at')::timestamptz
       > pg_catalog.clock_timestamp() THEN
    RAISE EXCEPTION 'intent cannot be marked EXPIRED before its deadline'
      USING ERRCODE = '23514';
  END IF;
  IF p_new_state = 'QUEUED_FOR_SUBMISSION'
     AND intent_row.intent_contract->>'action_kind' <> 'CANCEL_PENDING_ENTRY'
     AND NOT EXISTS (
       SELECT 1
       FROM qc2_execution.paper_order_intent_reservation AS reservation
       JOIN qc2_execution.resource_reservation AS resource
         ON resource.resource_key = reservation.resource_key
        AND resource.reservation_key = p_intent_id::text
        AND resource.state = 'ACTIVE'
       WHERE reservation.intent_id = p_intent_id
     ) THEN
    RAISE EXCEPTION 'intent cannot queue without an active exposure reservation'
      USING ERRCODE = '23514';
  END IF;

  IF p_new_state IN ('CANCELLED','EXPIRED','REJECTED')
     AND intent_row.intent_state IN ('RESERVED','QUEUED_FOR_SUBMISSION') THEN
    SELECT * INTO reservation_row
      FROM qc2_execution.paper_order_intent_reservation
      WHERE intent_id = p_intent_id;
    IF FOUND THEN
      PERFORM qc2_control.release_resource_reservation(
        reservation_row.resource_key, p_intent_id::text
      );
    END IF;
  END IF;

  UPDATE qc2_execution.paper_order_intent
    SET intent_state = p_new_state,
        intent_contract = pg_catalog.jsonb_set(
          intent_row.intent_contract, '{intent_state}', pg_catalog.to_jsonb(p_new_state)
        )
    WHERE id = p_intent_id;
  changed := FOUND;
  IF changed THEN
    PERFORM qc2_integrity_build.append_event_internal(
      'paper_order_intent_state_changed',
      pg_catalog.jsonb_build_object(
        'intent_id', p_intent_id::text,
        'prior_state', intent_row.intent_state,
        'new_state', p_new_state,
        'content_hash', intent_row.content_hash
      ),
      0,
      intent_row.intent_contract->'source_refs'
    );
  END IF;
  RETURN changed;
END
$function$;

REVOKE ALL ON FUNCTION qc2_execution.prevent_paper_intent_rewrite(),
  qc2_execution.prevent_paper_reservation_rewrite()
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_control.persist_paper_order_intent(jsonb, text),
  qc2_control.reserve_paper_order_intent(uuid, jsonb),
  qc2_control.transition_paper_order_intent(uuid, text)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qc2_control.persist_paper_order_intent(jsonb, text),
  qc2_control.reserve_paper_order_intent(uuid, jsonb),
  qc2_control.transition_paper_order_intent(uuid, text)
TO qc2_runtime_execution;

RESET ROLE;
