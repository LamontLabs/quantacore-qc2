-- QC2-053: single-owner enrollment, revocable devices, sessions, and recovery.
SET ROLE qc2_migrator;

CREATE TABLE qc2_governance_owner.identity_owner (
  environment_namespace text PRIMARY KEY CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  owner_binding text NOT NULL CHECK (
    owner_binding ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  bootstrap_verifier_hash text NOT NULL CHECK (
    bootstrap_verifier_hash ~ '^[0-9a-f]{64}$'
  ),
  bootstrap_consumed_at timestamptz,
  recovery_verifier_hash text CHECK (
    recovery_verifier_hash IS NULL OR recovery_verifier_hash ~ '^[0-9a-f]{64}$'
  ),
  recovery_generation bigint NOT NULL DEFAULT 0 CHECK (recovery_generation >= 0),
  promotion_hold boolean NOT NULL DEFAULT false,
  entry_hold boolean NOT NULL DEFAULT false,
  reconciliation_required boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (environment_namespace, owner_binding)
);

CREATE TABLE qc2_governance_owner.identity_device (
  environment_namespace text NOT NULL
    REFERENCES qc2_governance_owner.identity_owner(environment_namespace)
    ON DELETE RESTRICT,
  id uuid NOT NULL CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  owner_binding text NOT NULL CHECK (owner_binding ~ '^[a-z][a-z0-9_-]{0,95}$'),
  public_key_fingerprint text NOT NULL CHECK (public_key_fingerprint ~ '^[0-9a-f]{64}$'),
  record jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(record) = 'object'
    AND record->>'schema_name' = 'qc2.governance_owner.OwnerDevice.v1'
    AND record->>'id' = id::text
    AND record->>'environment_namespace' = environment_namespace
    AND record->>'owner_binding' = owner_binding
  ),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (environment_namespace, id),
  FOREIGN KEY (environment_namespace, owner_binding)
    REFERENCES qc2_governance_owner.identity_owner(environment_namespace, owner_binding)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX identity_device_active_fingerprint_unique
  ON qc2_governance_owner.identity_device(environment_namespace, public_key_fingerprint)
  WHERE revoked_at IS NULL;

CREATE TABLE qc2_governance_owner.identity_session (
  environment_namespace text NOT NULL,
  id uuid NOT NULL CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  session_id text NOT NULL CHECK (session_id ~ '^session-[a-f0-9]{32}$'),
  device_id uuid NOT NULL,
  generation integer NOT NULL CHECK (generation >= 1),
  record jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(record) = 'object'
    AND record->>'schema_name' = 'qc2.governance_owner.OwnerSession.v1'
    AND record->>'id' = id::text
    AND record->>'environment_namespace' = environment_namespace
    AND record->>'session_id' = session_id
    AND (record->>'refresh_generation')::integer = generation
    AND record->'device_ref'->>'target_id' = device_id::text
  ),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (environment_namespace, id),
  UNIQUE (environment_namespace, session_id, generation),
  FOREIGN KEY (environment_namespace, device_id)
    REFERENCES qc2_governance_owner.identity_device(environment_namespace, id)
    ON DELETE RESTRICT
);

CREATE UNIQUE INDEX identity_session_one_active_generation
  ON qc2_governance_owner.identity_session(environment_namespace, session_id)
  WHERE revoked_at IS NULL;

CREATE TABLE qc2_governance_owner.identity_access_credential (
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  environment_namespace text NOT NULL,
  session_record_id uuid NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  FOREIGN KEY (environment_namespace, session_record_id)
    REFERENCES qc2_governance_owner.identity_session(environment_namespace, id)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_governance_owner.identity_refresh_credential (
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  environment_namespace text NOT NULL,
  session_id text NOT NULL CHECK (session_id ~ '^session-[a-f0-9]{32}$'),
  session_record_id uuid NOT NULL,
  generation integer NOT NULL CHECK (generation >= 1),
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  FOREIGN KEY (environment_namespace, session_record_id)
    REFERENCES qc2_governance_owner.identity_session(environment_namespace, id)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_governance_owner.identity_challenge (
  environment_namespace text NOT NULL
    REFERENCES qc2_governance_owner.identity_owner(environment_namespace)
    ON DELETE RESTRICT,
  challenge_type text NOT NULL CHECK (
    challenge_type IN ('BOOTSTRAP','ADDITIONAL_ENROLLMENT','RECOVERY','COMMAND')
  ),
  id uuid NOT NULL CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  challenge_document jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(challenge_document) = 'object'),
  pending_document jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(pending_document) = 'object'),
  binding_document jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (pg_catalog.jsonb_typeof(binding_document) = 'object'),
  consumed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (environment_namespace, challenge_type, id)
);

CREATE TABLE qc2_governance_owner.identity_owner_command (
  environment_namespace text NOT NULL
    REFERENCES qc2_governance_owner.identity_owner(environment_namespace)
    ON DELETE RESTRICT,
  id uuid NOT NULL CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  command_id text NOT NULL CHECK (command_id ~ '^[a-z][a-z0-9_-]{0,95}$'),
  idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  request_body_hash text NOT NULL CHECK (request_body_hash ~ '^[0-9a-f]{64}$'),
  device_id uuid NOT NULL,
  command_type text NOT NULL CHECK (
    command_type IN ('PROMOTION','EPOCH_ACTIVATION','PAUSE_NEW_ENTRIES',
                     'RESUME_REQUEST','ACKNOWLEDGE_ALERT','DEVICE_ACTION')
  ),
  scope text NOT NULL CHECK (
    scope IN ('PROMOTION','EPOCH_ACTIVATION','PAUSE','RESUME','ALERT','DEVICE_ADMIN')
  ),
  record jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(record) = 'object'
    AND record->>'schema_name' = 'qc2.governance_owner.OwnerCommand.v1'
    AND record->>'id' = id::text
    AND record->>'environment_namespace' = environment_namespace
    AND record->>'command_id' = command_id
    AND record->>'idempotency_key' = idempotency_key
    AND record->>'request_body_hash' = request_body_hash
    AND record->>'command_type' = command_type
    AND record->>'scope' = scope
    AND record->'device_ref'->>'target_id' = device_id::text
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (environment_namespace, id),
  UNIQUE (environment_namespace, command_id),
  UNIQUE (environment_namespace, idempotency_key),
  FOREIGN KEY (environment_namespace, device_id)
    REFERENCES qc2_governance_owner.identity_device(environment_namespace, id)
    ON DELETE RESTRICT
);

CREATE TABLE qc2_governance_owner.identity_recovery_event (
  environment_namespace text NOT NULL
    REFERENCES qc2_governance_owner.identity_owner(environment_namespace)
    ON DELETE RESTRICT,
  id uuid NOT NULL CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  record jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(record) = 'object'
    AND record->>'schema_name' = 'qc2.governance_owner.RecoveryEvent.v1'
    AND record->>'id' = id::text
    AND record->>'environment_namespace' = environment_namespace
    AND record->>'promotion_hold' = 'true'
    AND record->>'entry_hold' = 'true'
    AND record->>'reconciliation_required' = 'true'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (environment_namespace, id)
);

CREATE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
DECLARE
  immutable_field text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'identity authority records are forward-only'
      USING ERRCODE = '55000';
  END IF;
  FOREACH immutable_field IN ARRAY TG_ARGV LOOP
    IF pg_catalog.to_jsonb(NEW)->immutable_field
       IS DISTINCT FROM pg_catalog.to_jsonb(OLD)->immutable_field THEN
      RAISE EXCEPTION 'identity contract documents are immutable'
        USING ERRCODE = '55000';
    END IF;
  END LOOP;
  RETURN NEW;
END
$function$;

CREATE TRIGGER identity_device_document_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.identity_device
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite('record');
CREATE TRIGGER identity_session_document_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.identity_session
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite('record');
CREATE TRIGGER identity_challenge_documents_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.identity_challenge
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite(
  'challenge_document', 'pending_document', 'binding_document'
);
CREATE TRIGGER identity_owner_command_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.identity_owner_command
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite('record');
CREATE TRIGGER identity_recovery_event_immutable
BEFORE UPDATE OR DELETE ON qc2_governance_owner.identity_recovery_event
FOR EACH ROW EXECUTE FUNCTION qc2_governance_owner.prevent_identity_document_rewrite('record');

DO $block$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'identity_owner',
    'identity_device',
    'identity_session',
    'identity_access_credential',
    'identity_refresh_credential',
    'identity_challenge',
    'identity_owner_command',
    'identity_recovery_event'
  ] LOOP
    EXECUTE pg_catalog.format(
      'ALTER TABLE qc2_governance_owner.%I ENABLE ROW LEVEL SECURITY', table_name
    );
    EXECUTE pg_catalog.format(
      'ALTER TABLE qc2_governance_owner.%I FORCE ROW LEVEL SECURITY', table_name
    );
    EXECUTE pg_catalog.format(
      'CREATE POLICY %I ON qc2_governance_owner.%I FOR ALL TO qc2_migrator USING (true) WITH CHECK (true)',
      table_name || '_migrator_all', table_name
    );
    EXECUTE pg_catalog.format(
      'REVOKE ALL ON qc2_governance_owner.%I FROM PUBLIC, qc2_runtime_identity',
      table_name
    );
  END LOOP;
END
$block$;

CREATE FUNCTION qc2_governance_owner.identity_provision_owner(
  p_environment_namespace text,
  p_owner_binding text,
  p_bootstrap_verifier_hash text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production')
     OR p_owner_binding !~ '^[a-z][a-z0-9_-]{0,95}$'
     OR p_bootstrap_verifier_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'initial owner provisioning envelope is invalid'
      USING ERRCODE = '22023';
  END IF;
  INSERT INTO qc2_governance_owner.identity_owner(
    environment_namespace, owner_binding, bootstrap_verifier_hash
  )
  VALUES (p_environment_namespace, p_owner_binding, p_bootstrap_verifier_hash);
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_read(
  p_operation text,
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_governance_owner
AS $function$
DECLARE
  environment_name text;
  challenge_id uuid;
  session_id uuid;
  token_verifier text;
  request_time timestamptz;
  owner_row qc2_governance_owner.identity_owner%ROWTYPE;
  challenge_row qc2_governance_owner.identity_challenge%ROWTYPE;
  access_row qc2_governance_owner.identity_access_credential%ROWTYPE;
  device_row qc2_governance_owner.identity_device%ROWTYPE;
  session_row qc2_governance_owner.identity_session%ROWTYPE;
  device_document jsonb;
  session_document jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('identity');
  IF pg_catalog.jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'identity read payload must be an object'
      USING ERRCODE = '22023';
  END IF;
  environment_name := p_payload->>'environment_namespace';
  IF environment_name NOT IN ('development','test','research','production') THEN
    RAISE EXCEPTION 'identity environment is invalid' USING ERRCODE = '22023';
  END IF;

  IF p_operation = 'bootstrap_state' OR p_operation = 'status' THEN
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'NOT_PROVISIONED');
    END IF;
    IF p_operation = 'bootstrap_state' THEN
      RETURN pg_catalog.jsonb_build_object(
        'status', 'FOUND',
        'owner_binding', owner_row.owner_binding,
        'bootstrap_verifier_hash', owner_row.bootstrap_verifier_hash,
        'bootstrap_consumed', owner_row.bootstrap_consumed_at IS NOT NULL
      );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'FOUND',
      'owner_binding', owner_row.owner_binding,
      'enrolled_devices', COALESCE((
        SELECT pg_catalog.jsonb_agg(device.record ORDER BY device.created_at, device.id)
        FROM qc2_governance_owner.identity_device AS device
        WHERE device.environment_namespace = environment_name
          AND device.revoked_at IS NULL
      ), '[]'::jsonb),
      'promotion_hold', owner_row.promotion_hold,
      'entry_hold', owner_row.entry_hold,
      'reconciliation_required', owner_row.reconciliation_required
    );
  END IF;

  challenge_id := NULLIF(p_payload->>'challenge_id', '')::uuid;
  IF p_operation IN (
    'bootstrap_challenge', 'additional_challenge',
    'recovery_challenge', 'command_challenge'
  ) THEN
    SELECT * INTO challenge_row
    FROM qc2_governance_owner.identity_challenge AS challenge
    WHERE challenge.environment_namespace = environment_name
      AND challenge.id = challenge_id
      AND challenge.challenge_type = CASE p_operation
        WHEN 'bootstrap_challenge' THEN 'BOOTSTRAP'
        WHEN 'additional_challenge' THEN 'ADDITIONAL_ENROLLMENT'
        WHEN 'recovery_challenge' THEN 'RECOVERY'
        ELSE 'COMMAND'
      END;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'UNKNOWN_CHALLENGE');
    END IF;
    IF p_operation = 'bootstrap_challenge' THEN
      RETURN pg_catalog.jsonb_build_object(
        'status', 'FOUND',
        'contract', challenge_row.challenge_document,
        'pending', challenge_row.pending_document,
        'consumed', challenge_row.consumed_at IS NOT NULL
      );
    ELSIF p_operation = 'additional_challenge' OR p_operation = 'recovery_challenge' THEN
      RETURN pg_catalog.jsonb_build_object(
        'status', 'FOUND',
        'challenge', challenge_row.challenge_document,
        'pending', challenge_row.pending_document,
        'consumed', challenge_row.consumed_at IS NOT NULL
      );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'FOUND',
      'challenge', challenge_row.challenge_document,
      'binding', challenge_row.binding_document
    );
  END IF;

  IF p_operation = 'resolve_access' THEN
    token_verifier := p_payload->>'token_hash';
    request_time := (p_payload->>'now')::timestamptz;
    SELECT * INTO access_row
    FROM qc2_governance_owner.identity_access_credential AS credential
    WHERE credential.environment_namespace = environment_name
      AND credential.token_hash = token_verifier;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_IDENTITY');
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = access_row.session_record_id;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_IDENTITY');
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_IDENTITY');
    END IF;
    IF access_row.revoked_at IS NOT NULL
       OR access_row.expires_at <= request_time
       OR session_row.revoked_at IS NOT NULL
       OR (session_row.record->>'expires_at')::timestamptz <= request_time
       OR device_row.revoked_at IS NOT NULL THEN
      RETURN pg_catalog.jsonb_build_object('status', 'IDENTITY_REVOKED');
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'VALID',
      'device_record', device_row.record,
      'session_record', session_row.record
    );
  END IF;

  IF p_operation = 'resolve_session' THEN
    session_id := NULLIF(p_payload->>'session_record_id', '')::uuid;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = session_id;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_IDENTITY');
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_IDENTITY');
    END IF;
    device_document := device_row.record;
    session_document := session_row.record;
    IF device_row.revoked_at IS NOT NULL THEN
      device_document := device_document || pg_catalog.jsonb_build_object(
        'revocation_state', 'REVOKED', 'revoked_at', device_row.revoked_at
      );
    END IF;
    IF session_row.revoked_at IS NOT NULL THEN
      session_document := session_document || pg_catalog.jsonb_build_object(
        'revoked_at', session_row.revoked_at
      );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'FOUND',
      'device_record', device_document,
      'session_record', session_document,
      'session_revoked_at', session_row.revoked_at,
      'device_revoked_at', device_row.revoked_at
    );
  END IF;

  RAISE EXCEPTION 'unsupported identity read operation: %', p_operation
    USING ERRCODE = '22023';
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_insert_device(
  p_environment_namespace text,
  p_record jsonb,
  p_public_key_fingerprint text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
DECLARE
  owner_row qc2_governance_owner.identity_owner%ROWTYPE;
BEGIN
  SELECT * INTO owner_row
  FROM qc2_governance_owner.identity_owner AS owner
  WHERE owner.environment_namespace = p_environment_namespace
  FOR UPDATE;
  IF NOT FOUND
     OR owner_row.owner_binding <> p_record->>'owner_binding'
     OR p_record->>'environment_namespace' <> p_environment_namespace
     OR p_record->>'revocation_state' <> 'ENROLLED'
     OR p_record->>'revoked_at' IS NOT NULL
     OR p_public_key_fingerprint !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'owner device enrollment record is invalid'
      USING ERRCODE = '23514';
  END IF;
  INSERT INTO qc2_governance_owner.identity_device(
    environment_namespace, id, owner_binding, public_key_fingerprint, record
  )
  VALUES (
    p_environment_namespace,
    (p_record->>'id')::uuid,
    p_record->>'owner_binding',
    p_public_key_fingerprint,
    p_record
  );
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_insert_session(
  p_environment_namespace text,
  p_record jsonb,
  p_access_token_hash text,
  p_refresh_token_hash text,
  p_refresh_expires_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
DECLARE
  device_id uuid;
  record_id uuid;
  generation integer;
  family_id text;
BEGIN
  device_id := (p_record->'device_ref'->>'target_id')::uuid;
  record_id := (p_record->>'id')::uuid;
  generation := (p_record->>'refresh_generation')::integer;
  family_id := p_record->>'session_id';
  IF p_record->>'environment_namespace' <> p_environment_namespace
     OR family_id !~ '^session-[a-f0-9]{32}$'
     OR p_record->>'revoked_at' IS NOT NULL
     OR generation < 1
     OR p_access_token_hash !~ '^[0-9a-f]{64}$'
     OR p_refresh_token_hash !~ '^[0-9a-f]{64}$'
     OR p_refresh_expires_at IS NULL
     OR p_refresh_expires_at <= (p_record->>'issued_at')::timestamptz
     OR (p_record->>'expires_at')::timestamptz
        <= (p_record->>'issued_at')::timestamptz THEN
    RAISE EXCEPTION 'owner session or credential envelope is invalid'
      USING ERRCODE = '23514';
  END IF;
  INSERT INTO qc2_governance_owner.identity_session(
    environment_namespace, id, session_id, device_id, generation, record
  )
  VALUES (
    p_environment_namespace, record_id, family_id, device_id, generation, p_record
  );
  INSERT INTO qc2_governance_owner.identity_access_credential(
    token_hash, environment_namespace, session_record_id, expires_at
  )
  VALUES (
    p_access_token_hash, p_environment_namespace, record_id,
    (p_record->>'expires_at')::timestamptz
  );
  INSERT INTO qc2_governance_owner.identity_refresh_credential(
    token_hash, environment_namespace, session_id, session_record_id,
    generation, expires_at
  )
  VALUES (
    p_refresh_token_hash, p_environment_namespace, family_id, record_id,
    generation, p_refresh_expires_at
  );
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_revoke_session_family(
  p_environment_namespace text,
  p_session_id text,
  p_revoked_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
BEGIN
  UPDATE qc2_governance_owner.identity_session AS session
    SET revoked_at = COALESCE(session.revoked_at, p_revoked_at)
    WHERE session.environment_namespace = p_environment_namespace
      AND session.session_id = p_session_id;
  UPDATE qc2_governance_owner.identity_access_credential AS credential
    SET revoked_at = COALESCE(credential.revoked_at, p_revoked_at)
    WHERE credential.environment_namespace = p_environment_namespace
      AND credential.session_record_id IN (
        SELECT session.id
        FROM qc2_governance_owner.identity_session AS session
        WHERE session.environment_namespace = p_environment_namespace
          AND session.session_id = p_session_id
      );
  UPDATE qc2_governance_owner.identity_refresh_credential AS credential
    SET consumed_at = COALESCE(credential.consumed_at, p_revoked_at)
    WHERE credential.environment_namespace = p_environment_namespace
      AND credential.session_id = p_session_id;
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_revoke_device(
  p_environment_namespace text,
  p_device_id uuid,
  p_revoked_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
DECLARE
  session_family text;
BEGIN
  UPDATE qc2_governance_owner.identity_device AS device
    SET revoked_at = COALESCE(device.revoked_at, p_revoked_at)
    WHERE device.environment_namespace = p_environment_namespace
      AND device.id = p_device_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'target device is not enrolled in this environment'
      USING ERRCODE = '23503';
  END IF;
  FOR session_family IN
    SELECT DISTINCT session.session_id
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = p_environment_namespace
      AND session.device_id = p_device_id
  LOOP
    PERFORM qc2_governance_owner.identity_revoke_session_family(
      p_environment_namespace, session_family, p_revoked_at
    );
  END LOOP;
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_transition(
  p_operation text,
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution,
  qc2_governance_owner, qc2_integrity_build
AS $function$
DECLARE
  environment_name text;
  challenge_id uuid;
  device_id uuid;
  request_time timestamptz;
  public_key_fingerprint text;
  owner_row qc2_governance_owner.identity_owner%ROWTYPE;
  challenge_row qc2_governance_owner.identity_challenge%ROWTYPE;
  device_row qc2_governance_owner.identity_device%ROWTYPE;
  session_row qc2_governance_owner.identity_session%ROWTYPE;
  refresh_row qc2_governance_owner.identity_refresh_credential%ROWTYPE;
  command_row qc2_governance_owner.identity_owner_command%ROWTYPE;
  target_device_row qc2_governance_owner.identity_device%ROWTYPE;
  device_document jsonb;
  session_document jsonb;
  command_document jsonb;
  recovery_document jsonb;
  prior_device_refs jsonb;
  event_source_refs jsonb;
  evidence_event_id uuid;
  event_content_hash text;
  evidence_environment text;
  evidence_class text;
  required_scope text;
  next_generation bigint;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('identity');
  IF pg_catalog.jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'identity transition payload must be an object'
      USING ERRCODE = '22023';
  END IF;
  environment_name := p_payload->>'environment_namespace';
  IF environment_name NOT IN ('development','test','research','production') THEN
    RAISE EXCEPTION 'identity environment is invalid' USING ERRCODE = '22023';
  END IF;
  request_time := COALESCE(
    NULLIF(p_payload->>'now', '')::timestamptz,
    pg_catalog.clock_timestamp()
  );

  IF p_operation = 'store_bootstrap_challenge' THEN
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    IF owner_row.bootstrap_consumed_at IS NOT NULL
       OR EXISTS (
         SELECT 1 FROM qc2_governance_owner.identity_device AS device
         WHERE device.environment_namespace = environment_name
       ) THEN
      RAISE EXCEPTION 'owner bootstrap was already consumed' USING ERRCODE = '55000';
    END IF;
    IF p_payload->'contract'->>'environment_namespace' <> environment_name
       OR p_payload->'pending'->>'environment_namespace' <> environment_name
       OR p_payload->'pending'->>'challenge_id' <> p_payload->'contract'->>'id'
       OR p_payload->'pending'->>'bootstrap_verifier_hash'
          <> owner_row.bootstrap_verifier_hash
       OR p_payload->'contract'->>'bootstrap_verifier_hash'
          <> owner_row.bootstrap_verifier_hash
       OR (p_payload->'contract'->>'expires_at')::timestamptz <= request_time
       OR p_payload->'pending'->>'owner_binding' <> owner_row.owner_binding
       OR p_payload->'pending'->>'public_key_fingerprint' !~ '^[0-9a-f]{64}$'
       OR p_payload->'pending'->>'public_key_der' IS NULL THEN
      RAISE EXCEPTION 'bootstrap challenge is not bound to provisioned owner'
        USING ERRCODE = '23514';
    END IF;
    UPDATE qc2_governance_owner.identity_challenge AS prior
      SET consumed_at = request_time
      WHERE prior.environment_namespace = environment_name
        AND prior.challenge_type = 'BOOTSTRAP'
        AND prior.consumed_at IS NULL;
    INSERT INTO qc2_governance_owner.identity_challenge(
      environment_namespace, challenge_type, id,
      challenge_document, pending_document
    )
    VALUES (
      environment_name, 'BOOTSTRAP',
      (p_payload->'contract'->>'id')::uuid,
      p_payload->'contract', p_payload->'pending'
    );
    RETURN pg_catalog.jsonb_build_object('status', 'STORED');
  END IF;

  IF p_operation = 'complete_bootstrap' THEN
    challenge_id := (p_payload->>'challenge_id')::uuid;
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO challenge_row
    FROM qc2_governance_owner.identity_challenge AS challenge
    WHERE challenge.environment_namespace = environment_name
      AND challenge.challenge_type = 'BOOTSTRAP'
      AND challenge.id = challenge_id
    FOR UPDATE;
    IF NOT FOUND OR challenge_row.consumed_at IS NOT NULL
       OR owner_row.bootstrap_consumed_at IS NOT NULL THEN
      RAISE EXCEPTION 'bootstrap challenge is unknown or consumed'
        USING ERRCODE = '55000';
    END IF;
    device_document := p_payload->'device_record';
    session_document := p_payload->'session_record';
    public_key_fingerprint := challenge_row.pending_document->>'public_key_fingerprint';
    IF (challenge_row.challenge_document->>'expires_at')::timestamptz <= request_time
       OR p_payload->>'bootstrap_verifier_hash' <> owner_row.bootstrap_verifier_hash
       OR challenge_row.pending_document->>'bootstrap_verifier_hash'
          <> owner_row.bootstrap_verifier_hash
       OR challenge_row.challenge_document->>'bootstrap_verifier_hash'
          <> owner_row.bootstrap_verifier_hash
       OR challenge_row.pending_document->>'public_key_der'
          <> device_document->>'public_key'
       OR device_document->>'owner_binding' <> owner_row.owner_binding
       OR device_document->>'environment_namespace' <> environment_name
       OR device_document->>'revocation_state' <> 'ENROLLED'
       OR public_key_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_payload->>'recovery_verifier_hash' !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'bootstrap proof or owner record is invalid'
        USING ERRCODE = '23514';
    END IF;
    PERFORM qc2_governance_owner.identity_insert_device(
      environment_name, device_document, public_key_fingerprint
    );
    PERFORM qc2_governance_owner.identity_insert_session(
      environment_name, session_document, p_payload->>'access_token_hash',
      p_payload->>'refresh_token_hash',
      (p_payload->>'refresh_expires_at')::timestamptz
    );
    UPDATE qc2_governance_owner.identity_challenge AS challenge
      SET consumed_at = request_time
      WHERE challenge.environment_namespace = environment_name
        AND challenge.challenge_type = 'BOOTSTRAP'
        AND challenge.id = challenge_id;
    UPDATE qc2_governance_owner.identity_owner AS owner
      SET bootstrap_consumed_at = request_time,
          recovery_verifier_hash = p_payload->>'recovery_verifier_hash',
          recovery_generation = 1
      WHERE owner.environment_namespace = environment_name;
    RETURN pg_catalog.jsonb_build_object('status', 'COMPLETED');
  END IF;

  IF p_operation = 'store_additional_challenge' THEN
    challenge_id := (p_payload->'challenge'->>'id')::uuid;
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = (p_payload->'pending'->>'authorized_session_record_id')::uuid
    FOR UPDATE;
    IF NOT FOUND OR session_row.revoked_at IS NOT NULL
       OR (session_row.record->>'expires_at')::timestamptz <= request_time
       OR session_row.device_id
          <> (p_payload->'pending'->>'authorized_device_id')::uuid
       OR NOT (session_row.record->'scope_refs' @> '["DEVICE_ADMIN"]'::jsonb) THEN
      RAISE EXCEPTION 'additional enrollment requires a live device-admin session'
        USING ERRCODE = '42501';
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL
       OR device_row.owner_binding <> owner_row.owner_binding
       OR p_payload->'challenge'->>'owner_binding' <> owner_row.owner_binding
       OR p_payload->'pending'->>'owner_binding' <> owner_row.owner_binding
       OR p_payload->'pending'->>'environment_namespace' <> environment_name
       OR p_payload->'challenge'->>'environment_namespace' <> environment_name
       OR p_payload->'pending'->>'public_key_fingerprint'
          <> p_payload->'challenge'->>'public_key_fingerprint'
       OR p_payload->'pending'->>'public_key_der' IS NULL
       OR pg_catalog.jsonb_array_length(
         p_payload->'challenge'->'scope_refs'
       ) = 0
       OR (p_payload->'challenge'->>'expires_at')::timestamptz <= request_time
       OR EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements_text(
           p_payload->'challenge'->'scope_refs'
         ) AS requested(scope_ref)
         WHERE NOT (
           session_row.record->'scope_refs' @> pg_catalog.jsonb_build_array(
             requested.scope_ref
           )
         )
       ) THEN
      RAISE EXCEPTION 'additional enrollment challenge does not match active owner authority'
        USING ERRCODE = '23514';
    END IF;
    INSERT INTO qc2_governance_owner.identity_challenge(
      environment_namespace, challenge_type, id,
      challenge_document, pending_document
    )
    VALUES (
      environment_name, 'ADDITIONAL_ENROLLMENT', challenge_id,
      p_payload->'challenge', p_payload->'pending'
    );
    RETURN pg_catalog.jsonb_build_object('status', 'STORED');
  END IF;

  IF p_operation = 'complete_additional_enrollment' THEN
    challenge_id := (p_payload->>'challenge_id')::uuid;
    device_document := p_payload->'device_record';
    session_document := p_payload->'session_record';
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO challenge_row
    FROM qc2_governance_owner.identity_challenge AS challenge
    WHERE challenge.environment_namespace = environment_name
      AND challenge.challenge_type = 'ADDITIONAL_ENROLLMENT'
      AND challenge.id = challenge_id
    FOR UPDATE;
    IF NOT FOUND OR challenge_row.consumed_at IS NOT NULL
       OR (challenge_row.challenge_document->>'expires_at')::timestamptz <= request_time THEN
      RAISE EXCEPTION 'additional enrollment challenge is unknown, consumed, or expired'
        USING ERRCODE = '55000';
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = (p_payload->>'authorized_session_record_id')::uuid
    FOR UPDATE;
    IF NOT FOUND OR session_row.revoked_at IS NOT NULL
       OR session_row.device_id <> (p_payload->>'authorized_device_id')::uuid
       OR (session_row.record->>'expires_at')::timestamptz <= request_time
       OR NOT (session_row.record->'scope_refs' @> '["DEVICE_ADMIN"]'::jsonb)
       OR challenge_row.pending_document->>'authorized_session_record_id'
          <> session_row.id::text
       OR challenge_row.pending_document->>'authorized_device_id'
          <> session_row.device_id::text
       OR challenge_row.pending_document->>'owner_binding' <> owner_row.owner_binding
       OR challenge_row.pending_document->>'environment_namespace' <> environment_name
       OR challenge_row.pending_document->>'public_key_der'
          <> device_document->>'public_key'
       OR challenge_row.pending_document->>'public_key_fingerprint'
          <> challenge_row.challenge_document->>'public_key_fingerprint' THEN
      RAISE EXCEPTION 'additional enrollment does not match live owner authorization'
        USING ERRCODE = '42501';
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL THEN
      RAISE EXCEPTION 'authorizing device was revoked before enrollment commit'
        USING ERRCODE = '42501';
    END IF;
    IF session_document->'scope_refs' IS DISTINCT FROM
       challenge_row.pending_document->'scope_refs' THEN
      RAISE EXCEPTION 'new device scopes differ from the signed enrollment request'
        USING ERRCODE = '23514';
    END IF;
    public_key_fingerprint :=
      challenge_row.pending_document->>'public_key_fingerprint';
    PERFORM qc2_governance_owner.identity_insert_device(
      environment_name, device_document, public_key_fingerprint
    );
    PERFORM qc2_governance_owner.identity_insert_session(
      environment_name, session_document, p_payload->>'access_token_hash',
      p_payload->>'refresh_token_hash',
      (p_payload->>'refresh_expires_at')::timestamptz
    );
    UPDATE qc2_governance_owner.identity_challenge AS challenge
      SET consumed_at = request_time
      WHERE challenge.environment_namespace = environment_name
        AND challenge.challenge_type = 'ADDITIONAL_ENROLLMENT'
        AND challenge.id = challenge_id;
    RETURN pg_catalog.jsonb_build_object('status', 'COMPLETED');
  END IF;

  IF p_operation = 'refresh_context' THEN
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    SELECT * INTO refresh_row
    FROM qc2_governance_owner.identity_refresh_credential AS credential
    WHERE credential.environment_namespace = environment_name
      AND credential.token_hash = p_payload->>'token_hash'
    FOR UPDATE;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    IF refresh_row.consumed_at IS NOT NULL THEN
      PERFORM qc2_governance_owner.identity_revoke_session_family(
        environment_name, refresh_row.session_id, request_time
      );
      RETURN pg_catalog.jsonb_build_object('status', 'REFRESH_REPLAY');
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = refresh_row.session_record_id
    FOR UPDATE;
    IF NOT FOUND OR session_row.session_id <> refresh_row.session_id
       OR session_row.generation <> refresh_row.generation
       OR session_row.revoked_at IS NOT NULL THEN
      PERFORM qc2_governance_owner.identity_revoke_session_family(
        environment_name, refresh_row.session_id, request_time
      );
      RETURN pg_catalog.jsonb_build_object('status', 'REFRESH_REPLAY');
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL
       OR refresh_row.expires_at <= request_time THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'VALID',
      'device_record', device_row.record,
      'session_record', session_row.record
    );
  END IF;

  IF p_operation = 'rotate_refresh' THEN
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    SELECT * INTO refresh_row
    FROM qc2_governance_owner.identity_refresh_credential AS credential
    WHERE credential.environment_namespace = environment_name
      AND credential.token_hash = p_payload->>'token_hash'
    FOR UPDATE;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    IF refresh_row.consumed_at IS NOT NULL THEN
      PERFORM qc2_governance_owner.identity_revoke_session_family(
        environment_name, refresh_row.session_id, request_time
      );
      RETURN pg_catalog.jsonb_build_object('status', 'REFRESH_REPLAY');
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = refresh_row.session_record_id
    FOR UPDATE;
    IF NOT FOUND OR session_row.session_id <> refresh_row.session_id
       OR session_row.generation <> refresh_row.generation
       OR session_row.revoked_at IS NOT NULL THEN
      PERFORM qc2_governance_owner.identity_revoke_session_family(
        environment_name, refresh_row.session_id, request_time
      );
      RETURN pg_catalog.jsonb_build_object('status', 'REFRESH_REPLAY');
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    session_document := p_payload->'session_record';
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL
       OR refresh_row.expires_at <= request_time THEN
      RETURN pg_catalog.jsonb_build_object('status', 'INVALID_REFRESH');
    END IF;
    IF session_document->>'environment_namespace' <> environment_name
       OR session_document->>'session_id' <> refresh_row.session_id
       OR session_document->'device_ref'->>'target_id' <> session_row.device_id::text
       OR (session_document->>'refresh_generation')::integer
          <> refresh_row.generation + 1
       OR session_document->'scope_refs' IS DISTINCT FROM
          session_row.record->'scope_refs'
       OR (session_document->>'issued_at')::timestamptz <> request_time THEN
      RAISE EXCEPTION 'refresh rotation changed session identity or scope'
        USING ERRCODE = '23514';
    END IF;
    UPDATE qc2_governance_owner.identity_session AS session
      SET revoked_at = request_time
      WHERE session.environment_namespace = environment_name
        AND session.id = session_row.id;
    UPDATE qc2_governance_owner.identity_access_credential AS credential
      SET revoked_at = request_time
      WHERE credential.environment_namespace = environment_name
        AND credential.session_record_id = session_row.id;
    UPDATE qc2_governance_owner.identity_refresh_credential AS credential
      SET consumed_at = request_time
      WHERE credential.environment_namespace = environment_name
        AND credential.token_hash = refresh_row.token_hash;
    PERFORM qc2_governance_owner.identity_insert_session(
      environment_name, session_document, p_payload->>'access_token_hash',
      p_payload->>'new_refresh_token_hash',
      (p_payload->>'refresh_expires_at')::timestamptz
    );
    RETURN pg_catalog.jsonb_build_object('status', 'ROTATED');
  END IF;

  IF p_operation = 'store_command_challenge' THEN
    challenge_id := (p_payload->'challenge'->>'id')::uuid;
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = (p_payload->'binding'->>'session_record_id')::uuid
    FOR UPDATE;
    required_scope := CASE p_payload->'challenge'->>'command_type'
      WHEN 'PROMOTION' THEN 'PROMOTION'
      WHEN 'EPOCH_ACTIVATION' THEN 'EPOCH_ACTIVATION'
      WHEN 'PAUSE_NEW_ENTRIES' THEN 'PAUSE'
      WHEN 'RESUME_REQUEST' THEN 'RESUME'
      WHEN 'ACKNOWLEDGE_ALERT' THEN 'ALERT'
      WHEN 'DEVICE_ACTION' THEN 'DEVICE_ADMIN'
      ELSE NULL
    END;
    IF NOT FOUND OR session_row.revoked_at IS NOT NULL
       OR (session_row.record->>'expires_at')::timestamptz <= request_time
       OR session_row.session_id <> p_payload->'binding'->>'session_id'
       OR session_row.device_id <> (p_payload->'binding'->>'device_id')::uuid
       OR required_scope IS NULL
       OR p_payload->'challenge'->>'scope' <> required_scope
       OR NOT (
         session_row.record->'scope_refs' @> pg_catalog.jsonb_build_array(required_scope)
       )
       OR p_payload->'challenge'->>'environment_namespace' <> environment_name
       OR p_payload->'challenge'->'session_ref'->>'target_id'
          <> session_row.id::text
       OR p_payload->'challenge'->'device_ref'->>'target_id'
          <> session_row.device_id::text
       OR p_payload->'binding'->>'request_body_hash'
          <> p_payload->'challenge'->>'request_body_hash'
       OR (p_payload->'challenge'->>'expires_at')::timestamptz <= request_time THEN
      RAISE EXCEPTION 'signed-command challenge is not bound to a live session'
        USING ERRCODE = '42501';
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL THEN
      RAISE EXCEPTION 'signed-command device is revoked'
        USING ERRCODE = '42501';
    END IF;
    INSERT INTO qc2_governance_owner.identity_challenge(
      environment_namespace, challenge_type, id,
      challenge_document, pending_document, binding_document
    )
    VALUES (
      environment_name, 'COMMAND', challenge_id,
      p_payload->'challenge', '{}'::jsonb, p_payload->'binding'
    );
    RETURN pg_catalog.jsonb_build_object('status', 'STORED');
  END IF;

  IF p_operation = 'commit_command' THEN
    challenge_id := (p_payload->>'challenge_id')::uuid;
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO challenge_row
    FROM qc2_governance_owner.identity_challenge AS challenge
    WHERE challenge.environment_namespace = environment_name
      AND challenge.challenge_type = 'COMMAND'
      AND challenge.id = challenge_id
    FOR UPDATE;
    IF NOT FOUND OR challenge_row.consumed_at IS NOT NULL
       OR (challenge_row.challenge_document->>'expires_at')::timestamptz <= request_time THEN
      RAISE EXCEPTION 'owner command challenge is unknown, consumed, or expired'
        USING ERRCODE = '55000';
    END IF;
    SELECT * INTO session_row
    FROM qc2_governance_owner.identity_session AS session
    WHERE session.environment_namespace = environment_name
      AND session.id = (challenge_row.binding_document->>'session_record_id')::uuid
    FOR UPDATE;
    required_scope := CASE challenge_row.challenge_document->>'command_type'
      WHEN 'PROMOTION' THEN 'PROMOTION'
      WHEN 'EPOCH_ACTIVATION' THEN 'EPOCH_ACTIVATION'
      WHEN 'PAUSE_NEW_ENTRIES' THEN 'PAUSE'
      WHEN 'RESUME_REQUEST' THEN 'RESUME'
      WHEN 'ACKNOWLEDGE_ALERT' THEN 'ALERT'
      WHEN 'DEVICE_ACTION' THEN 'DEVICE_ADMIN'
      ELSE NULL
    END;
    IF NOT FOUND OR session_row.revoked_at IS NOT NULL
       OR (session_row.record->>'expires_at')::timestamptz <= request_time
       OR session_row.device_id
          <> (challenge_row.binding_document->>'device_id')::uuid
       OR session_row.session_id
          <> challenge_row.binding_document->>'session_id'
       OR required_scope IS NULL
       OR challenge_row.challenge_document->>'scope' <> required_scope
       OR NOT (
         session_row.record->'scope_refs' @> pg_catalog.jsonb_build_array(required_scope)
       ) THEN
      RAISE EXCEPTION 'owner command session was revoked before commit'
        USING ERRCODE = '42501';
    END IF;
    SELECT * INTO device_row
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name
      AND device.id = session_row.device_id
    FOR UPDATE;
    IF NOT FOUND OR device_row.revoked_at IS NOT NULL THEN
      RAISE EXCEPTION 'owner command device was revoked before commit'
        USING ERRCODE = '42501';
    END IF;
    command_document := p_payload->'owner_command';
    IF command_document->>'environment_namespace' <> environment_name
       OR command_document->>'issued_at'
          <> challenge_row.challenge_document->>'issued_at'
       OR command_document->>'command_id'
          <> challenge_row.challenge_document->>'command_id'
       OR command_document->>'command_type'
          <> challenge_row.challenge_document->>'command_type'
       OR command_document->>'idempotency_key'
          <> p_payload->>'idempotency_key'
       OR command_document->>'idempotency_key'
          <> challenge_row.challenge_document->>'idempotency_key'
       OR command_document->>'request_body_hash'
          <> challenge_row.challenge_document->>'request_body_hash'
       OR command_document->>'request_body_hash'
          <> challenge_row.binding_document->>'request_body_hash'
       OR command_document->>'scope'
          <> challenge_row.challenge_document->>'scope'
       OR command_document->'device_ref'->>'target_id'
          <> device_row.id::text
       OR challenge_row.challenge_document->>'public_key_fingerprint'
          <> device_row.public_key_fingerprint
       OR command_document->>'signature' IS NULL THEN
      RAISE EXCEPTION 'owner command does not match its signed challenge'
        USING ERRCODE = '23514';
    END IF;
    SELECT * INTO command_row
    FROM qc2_governance_owner.identity_owner_command AS command
    WHERE command.environment_namespace = environment_name
      AND command.idempotency_key = p_payload->>'idempotency_key'
    FOR UPDATE;
    IF FOUND THEN
      IF command_row.request_body_hash
           <> command_document->>'request_body_hash'
         OR command_row.device_id <> device_row.id
         OR command_row.command_type <> command_document->>'command_type'
         OR command_row.scope <> command_document->>'scope' THEN
        RAISE EXCEPTION 'owner command idempotency key conflicts with prior content'
          USING ERRCODE = '23505';
      END IF;
      UPDATE qc2_governance_owner.identity_challenge AS challenge
        SET consumed_at = request_time
        WHERE challenge.environment_namespace = environment_name
          AND challenge.challenge_type = 'COMMAND'
          AND challenge.id = challenge_id;
      RETURN pg_catalog.jsonb_build_object(
        'status', 'DUPLICATE', 'owner_command', command_row.record
      );
    END IF;
    INSERT INTO qc2_governance_owner.identity_owner_command(
      environment_namespace, id, command_id, idempotency_key,
      request_body_hash, device_id, command_type, scope, record
    )
    VALUES (
      environment_name,
      (command_document->>'id')::uuid,
      command_document->>'command_id',
      command_document->>'idempotency_key',
      command_document->>'request_body_hash',
      device_row.id,
      command_document->>'command_type',
      command_document->>'scope',
      command_document
    )
    RETURNING * INTO command_row;
    UPDATE qc2_governance_owner.identity_challenge AS challenge
      SET consumed_at = request_time
      WHERE challenge.environment_namespace = environment_name
        AND challenge.challenge_type = 'COMMAND'
        AND challenge.id = challenge_id;
    IF NULLIF(p_payload->>'target_device_id', '') IS NOT NULL THEN
      IF command_document->>'command_type' <> 'DEVICE_ACTION'
         OR command_document->>'scope' <> 'DEVICE_ADMIN' THEN
        RAISE EXCEPTION 'device revocation requires a signed device-admin command'
          USING ERRCODE = '42501';
      END IF;
      PERFORM qc2_governance_owner.identity_revoke_device(
        environment_name, (p_payload->>'target_device_id')::uuid, request_time
      );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'COMMITTED', 'owner_command', command_row.record
    );
  END IF;

  IF p_operation = 'verify_recovery_material' THEN
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name;
    IF NOT FOUND OR owner_row.recovery_verifier_hash IS NULL
       OR owner_row.recovery_verifier_hash <> p_payload->>'recovery_verifier_hash' THEN
      RETURN pg_catalog.jsonb_build_object('status', 'RECOVERY_DENIED');
    END IF;
    RETURN pg_catalog.jsonb_build_object('status', 'VALID');
  END IF;

  IF p_operation = 'store_recovery_challenge' THEN
    challenge_id := (p_payload->'challenge'->>'id')::uuid;
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND OR owner_row.recovery_verifier_hash IS NULL
       OR owner_row.recovery_verifier_hash
          <> p_payload->'pending'->>'recovery_verifier_hash' THEN
      RAISE EXCEPTION 'recovery material is not current for this owner'
        USING ERRCODE = '42501';
    END IF;
    IF p_payload->'challenge'->>'environment_namespace' <> environment_name
       OR p_payload->'pending'->>'environment_namespace' <> environment_name
       OR p_payload->'challenge'->>'owner_binding' <> owner_row.owner_binding
       OR p_payload->'pending'->>'owner_binding' <> owner_row.owner_binding
       OR p_payload->'challenge'->>'public_key_fingerprint'
          <> p_payload->'pending'->>'public_key_fingerprint'
       OR p_payload->'pending'->>'public_key_fingerprint' !~ '^[0-9a-f]{64}$'
       OR p_payload->'pending'->>'public_key_der' IS NULL
       OR (p_payload->'challenge'->>'expires_at')::timestamptz <= request_time THEN
      RAISE EXCEPTION 'recovery challenge is malformed or expired'
        USING ERRCODE = '23514';
    END IF;
    INSERT INTO qc2_governance_owner.identity_challenge(
      environment_namespace, challenge_type, id,
      challenge_document, pending_document
    )
    VALUES (
      environment_name, 'RECOVERY', challenge_id,
      p_payload->'challenge', p_payload->'pending'
    );
    RETURN pg_catalog.jsonb_build_object('status', 'STORED');
  END IF;

  IF p_operation = 'complete_recovery' THEN
    challenge_id := (p_payload->>'challenge_id')::uuid;
    device_document := p_payload->'replacement_device';
    session_document := p_payload->'replacement_session';
    recovery_document := p_payload->'recovery_event';
    SELECT * INTO owner_row
    FROM qc2_governance_owner.identity_owner AS owner
    WHERE owner.environment_namespace = environment_name
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'owner identity is not provisioned' USING ERRCODE = '23503';
    END IF;
    SELECT * INTO challenge_row
    FROM qc2_governance_owner.identity_challenge AS challenge
    WHERE challenge.environment_namespace = environment_name
      AND challenge.challenge_type = 'RECOVERY'
      AND challenge.id = challenge_id
    FOR UPDATE;
    IF NOT FOUND OR challenge_row.consumed_at IS NOT NULL
       OR (challenge_row.challenge_document->>'expires_at')::timestamptz <= request_time THEN
      RAISE EXCEPTION 'recovery challenge is unknown, consumed, or expired'
        USING ERRCODE = '55000';
    END IF;
    public_key_fingerprint :=
      challenge_row.pending_document->>'public_key_fingerprint';
    IF owner_row.recovery_verifier_hash IS NULL
       OR owner_row.recovery_verifier_hash <> p_payload->>'recovery_verifier_hash'
       OR owner_row.recovery_verifier_hash
          <> challenge_row.pending_document->>'recovery_verifier_hash'
       OR challenge_row.challenge_document->>'owner_binding' <> owner_row.owner_binding
       OR challenge_row.pending_document->>'owner_binding' <> owner_row.owner_binding
       OR challenge_row.pending_document->>'environment_namespace' <> environment_name
       OR challenge_row.pending_document->>'public_key_der'
          <> device_document->>'public_key'
       OR public_key_fingerprint
          <> challenge_row.challenge_document->>'public_key_fingerprint'
       OR device_document->>'owner_binding' <> owner_row.owner_binding
       OR device_document->>'environment_namespace' <> environment_name
       OR device_document->>'revocation_state' <> 'ENROLLED'
       OR recovery_document->>'environment_namespace' <> environment_name
       OR p_payload->>'next_recovery_verifier_hash' !~ '^[0-9a-f]{64}$'
       OR p_payload->>'next_recovery_verifier_hash' = owner_row.recovery_verifier_hash
       OR EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements_text(
           session_document->'scope_refs'
         ) AS requested(scope_ref)
         WHERE requested.scope_ref NOT IN ('OWNER_READ','DEVICE_ADMIN')
       )
       OR session_document->'scope_refs' = '[]'::jsonb THEN
      RAISE EXCEPTION 'recovery evidence or replacement identity is invalid'
        USING ERRCODE = '23514';
    END IF;

    SELECT COALESCE(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'target_schema_name', 'qc2.governance_owner.OwnerDevice.v1',
          'target_id', device.id::text
        ) ORDER BY device.created_at, device.id
      ),
      '[]'::jsonb
    )
    INTO prior_device_refs
    FROM qc2_governance_owner.identity_device AS device
    WHERE device.environment_namespace = environment_name;
    event_source_refs := prior_device_refs || pg_catalog.jsonb_build_array(
      pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.governance_owner.OwnerDevice.v1',
        'target_id', (device_document->>'id')
      )
    );

    UPDATE qc2_governance_owner.identity_device AS device
      SET revoked_at = COALESCE(device.revoked_at, request_time)
      WHERE device.environment_namespace = environment_name;
    UPDATE qc2_governance_owner.identity_session AS session
      SET revoked_at = COALESCE(session.revoked_at, request_time)
      WHERE session.environment_namespace = environment_name;
    UPDATE qc2_governance_owner.identity_access_credential AS credential
      SET revoked_at = COALESCE(credential.revoked_at, request_time)
      WHERE credential.environment_namespace = environment_name;
    UPDATE qc2_governance_owner.identity_refresh_credential AS credential
      SET consumed_at = COALESCE(credential.consumed_at, request_time)
      WHERE credential.environment_namespace = environment_name;

    UPDATE qc2_execution.entry_pause_state AS state
      SET entry_paused = true,
          generation = CASE
            WHEN state.entry_paused THEN state.generation
            ELSE state.generation + 1
          END,
          reason_code = 'owner_identity_recovery',
          updated_at = request_time
      WHERE state.singleton_id
      RETURNING state.generation INTO next_generation;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'entry-pause state is missing during owner recovery'
        USING ERRCODE = '23514';
    END IF;
    INSERT INTO qc2_execution.entry_pause_request(
      request_id, generation, reason_code, created_at
    )
    VALUES (
      (recovery_document->>'id')::uuid,
      next_generation,
      'owner_identity_recovery',
      request_time
    );
    PERFORM qc2_integrity_build.append_event_internal(
      'new_entry_pause_requested',
      pg_catalog.jsonb_build_object(
        'request_id', recovery_document->>'id',
        'pause_generation', next_generation,
        'reason_code', 'owner_identity_recovery',
        'entry_paused', true
      )
    );
    evidence_event_id := qc2_integrity_build.append_event_internal(
      'owner_identity_recovery',
      pg_catalog.jsonb_build_object(
        'owner_binding', owner_row.owner_binding,
        'recovery_event_id', recovery_document->>'id',
        'prior_device_ids', prior_device_refs,
        'replacement_device_id', device_document->>'id',
        'recovery_generation', owner_row.recovery_generation + 1,
        'promotion_hold', true,
        'entry_hold', true,
        'reconciliation_required', true
      ),
      0,
      event_source_refs
    );
    SELECT event.event_contract->>'content_hash',
           event.event_contract->>'environment_namespace',
           event.event_contract->>'evidence_class'
      INTO event_content_hash, evidence_environment, evidence_class
      FROM qc2_integrity_build.evidence_event AS event
      WHERE event.id = evidence_event_id;
    IF NOT FOUND OR evidence_environment <> environment_name
       OR evidence_class <> recovery_document->>'evidence_class' THEN
      RAISE EXCEPTION 'active evidence stream does not match the recovery environment'
        USING ERRCODE = '23514';
    END IF;

    recovery_document := recovery_document || pg_catalog.jsonb_build_object(
      'prior_device_refs', prior_device_refs,
      'replacement_device_ref', pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.governance_owner.OwnerDevice.v1',
        'target_id', device_document->>'id'
      ),
      'evidence_ref', pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.integrity_build.EvidenceEvent.v1',
        'target_id', evidence_event_id::text,
        'content_hash', event_content_hash
      )
    );
    UPDATE qc2_governance_owner.identity_owner AS owner
      SET recovery_verifier_hash = p_payload->>'next_recovery_verifier_hash',
          recovery_generation = owner.recovery_generation + 1,
          promotion_hold = true,
          entry_hold = true,
          reconciliation_required = true
      WHERE owner.environment_namespace = environment_name;
    UPDATE qc2_governance_owner.identity_challenge AS challenge
      SET consumed_at = request_time
      WHERE challenge.environment_namespace = environment_name
        AND challenge.challenge_type = 'RECOVERY'
        AND challenge.id = challenge_id;
    PERFORM qc2_governance_owner.identity_insert_device(
      environment_name, device_document, public_key_fingerprint
    );
    PERFORM qc2_governance_owner.identity_insert_session(
      environment_name, session_document, p_payload->>'access_token_hash',
      p_payload->>'refresh_token_hash',
      (p_payload->>'refresh_expires_at')::timestamptz
    );
    INSERT INTO qc2_governance_owner.identity_recovery_event(
      environment_namespace, id, record
    )
    VALUES (
      environment_name, (recovery_document->>'id')::uuid, recovery_document
    );
    RETURN pg_catalog.jsonb_build_object(
      'status', 'RECOVERED',
      'recovery_event', recovery_document,
      'entry_pause_generation', next_generation
    );
  END IF;

  RAISE EXCEPTION 'unsupported identity transition operation: %', p_operation
    USING ERRCODE = '22023';
END
$function$;

CREATE FUNCTION qc2_governance_owner.identity_bootstrap_state(p_environment_namespace text)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'bootstrap_state',
    pg_catalog.jsonb_build_object('environment_namespace', p_environment_namespace)
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_store_bootstrap_challenge(
  p_environment_namespace text, p_contract jsonb, p_pending jsonb
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'store_bootstrap_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'contract', p_contract,
      'pending', p_pending,
      'now', p_contract->>'issued_at'
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_get_bootstrap_challenge(
  p_environment_namespace text, p_challenge_id uuid
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'bootstrap_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_complete_bootstrap(
  p_environment_namespace text,
  p_challenge_id uuid,
  p_bootstrap_verifier_hash text,
  p_device_record jsonb,
  p_session_record jsonb,
  p_access_token_hash text,
  p_refresh_token_hash text,
  p_refresh_expires_at timestamptz,
  p_recovery_verifier_hash text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'complete_bootstrap',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text,
      'bootstrap_verifier_hash', p_bootstrap_verifier_hash,
      'device_record', p_device_record,
      'session_record', p_session_record,
      'access_token_hash', p_access_token_hash,
      'refresh_token_hash', p_refresh_token_hash,
      'refresh_expires_at', p_refresh_expires_at,
      'recovery_verifier_hash', p_recovery_verifier_hash,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_resolve_access(
  p_environment_namespace text, p_access_token_hash text, p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'resolve_access',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'token_hash', p_access_token_hash,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_refresh_context(
  p_environment_namespace text, p_refresh_token_hash text, p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'refresh_context',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'token_hash', p_refresh_token_hash,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_rotate_refresh(
  p_environment_namespace text,
  p_refresh_token_hash text,
  p_session_record jsonb,
  p_access_token_hash text,
  p_new_refresh_token_hash text,
  p_refresh_expires_at timestamptz,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'rotate_refresh',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'token_hash', p_refresh_token_hash,
      'session_record', p_session_record,
      'access_token_hash', p_access_token_hash,
      'new_refresh_token_hash', p_new_refresh_token_hash,
      'refresh_expires_at', p_refresh_expires_at,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_store_command_challenge(
  p_environment_namespace text, p_challenge jsonb, p_binding jsonb
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'store_command_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge', p_challenge,
      'binding', p_binding,
      'now', p_challenge->>'issued_at'
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_get_command_challenge(
  p_environment_namespace text, p_challenge_id uuid
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'command_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_commit_owner_command(
  p_environment_namespace text,
  p_challenge_id uuid,
  p_owner_command jsonb,
  p_idempotency_key text,
  p_target_device_id uuid,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'commit_command',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text,
      'owner_command', p_owner_command,
      'idempotency_key', p_idempotency_key,
      'target_device_id', p_target_device_id,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_verify_recovery_material(
  p_environment_namespace text, p_recovery_verifier_hash text
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'verify_recovery_material',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'recovery_verifier_hash', p_recovery_verifier_hash
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_store_recovery_challenge(
  p_environment_namespace text, p_challenge jsonb, p_pending jsonb
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'store_recovery_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge', p_challenge,
      'pending', p_pending,
      'now', p_challenge->>'issued_at'
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_get_recovery_challenge(
  p_environment_namespace text, p_challenge_id uuid
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'recovery_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_complete_recovery(
  p_environment_namespace text,
  p_challenge_id uuid,
  p_recovery_verifier_hash text,
  p_replacement_device jsonb,
  p_replacement_session jsonb,
  p_access_token_hash text,
  p_refresh_token_hash text,
  p_refresh_expires_at timestamptz,
  p_next_recovery_verifier_hash text,
  p_recovery_event jsonb,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'complete_recovery',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text,
      'recovery_verifier_hash', p_recovery_verifier_hash,
      'replacement_device', p_replacement_device,
      'replacement_session', p_replacement_session,
      'access_token_hash', p_access_token_hash,
      'refresh_token_hash', p_refresh_token_hash,
      'refresh_expires_at', p_refresh_expires_at,
      'next_recovery_verifier_hash', p_next_recovery_verifier_hash,
      'recovery_event', p_recovery_event,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_store_additional_enrollment_challenge(
  p_environment_namespace text, p_challenge jsonb, p_pending jsonb
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'store_additional_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge', p_challenge,
      'pending', p_pending,
      'now', p_challenge->>'issued_at'
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_get_additional_enrollment_challenge(
  p_environment_namespace text, p_challenge_id uuid
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'additional_challenge',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_complete_additional_enrollment(
  p_environment_namespace text,
  p_challenge_id uuid,
  p_authorized_session_record_id uuid,
  p_authorized_device_id uuid,
  p_device_record jsonb,
  p_session_record jsonb,
  p_access_token_hash text,
  p_refresh_token_hash text,
  p_refresh_expires_at timestamptz,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_transition(
    'complete_additional_enrollment',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'challenge_id', p_challenge_id::text,
      'authorized_session_record_id', p_authorized_session_record_id::text,
      'authorized_device_id', p_authorized_device_id::text,
      'device_record', p_device_record,
      'session_record', p_session_record,
      'access_token_hash', p_access_token_hash,
      'refresh_token_hash', p_refresh_token_hash,
      'refresh_expires_at', p_refresh_expires_at,
      'now', p_now
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_resolve_session(
  p_environment_namespace text, p_session_record_id uuid
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'resolve_session',
    pg_catalog.jsonb_build_object(
      'environment_namespace', p_environment_namespace,
      'session_record_id', p_session_record_id::text
    )
  )
$function$;

CREATE FUNCTION qc2_governance_owner.identity_status(p_environment_namespace text)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT qc2_governance_owner.identity_read(
    'status',
    pg_catalog.jsonb_build_object('environment_namespace', p_environment_namespace)
  )
$function$;

REVOKE ALL ON FUNCTION qc2_governance_owner.prevent_identity_document_rewrite()
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_provision_owner(text, text, text)
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_read(text, jsonb)
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_transition(text, jsonb)
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_insert_device(text, jsonb, text)
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_insert_session(
  text, jsonb, text, text, timestamptz
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_revoke_session_family(
  text, text, timestamptz
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_governance_owner.identity_revoke_device(
  text, uuid, timestamptz
) FROM PUBLIC;
REVOKE ALL ON FUNCTION
  qc2_governance_owner.identity_bootstrap_state(text),
  qc2_governance_owner.identity_store_bootstrap_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_bootstrap_challenge(text, uuid),
  qc2_governance_owner.identity_complete_bootstrap(
    text, uuid, text, jsonb, jsonb, text, text, timestamptz, text, timestamptz
  ),
  qc2_governance_owner.identity_resolve_access(text, text, timestamptz),
  qc2_governance_owner.identity_refresh_context(text, text, timestamptz),
  qc2_governance_owner.identity_rotate_refresh(
    text, text, jsonb, text, text, timestamptz, timestamptz
  ),
  qc2_governance_owner.identity_store_command_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_command_challenge(text, uuid),
  qc2_governance_owner.identity_commit_owner_command(
    text, uuid, jsonb, text, uuid, timestamptz
  ),
  qc2_governance_owner.identity_verify_recovery_material(text, text),
  qc2_governance_owner.identity_store_recovery_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_recovery_challenge(text, uuid),
  qc2_governance_owner.identity_complete_recovery(
    text, uuid, text, jsonb, jsonb, text, text, timestamptz, text, jsonb, timestamptz
  ),
  qc2_governance_owner.identity_store_additional_enrollment_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_additional_enrollment_challenge(text, uuid),
  qc2_governance_owner.identity_complete_additional_enrollment(
    text, uuid, uuid, uuid, jsonb, jsonb, text, text, timestamptz, timestamptz
  ),
  qc2_governance_owner.identity_resolve_session(text, uuid),
  qc2_governance_owner.identity_status(text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  qc2_governance_owner.identity_bootstrap_state(text),
  qc2_governance_owner.identity_store_bootstrap_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_bootstrap_challenge(text, uuid),
  qc2_governance_owner.identity_complete_bootstrap(
    text, uuid, text, jsonb, jsonb, text, text, timestamptz, text, timestamptz
  ),
  qc2_governance_owner.identity_resolve_access(text, text, timestamptz),
  qc2_governance_owner.identity_refresh_context(text, text, timestamptz),
  qc2_governance_owner.identity_rotate_refresh(
    text, text, jsonb, text, text, timestamptz, timestamptz
  ),
  qc2_governance_owner.identity_store_command_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_command_challenge(text, uuid),
  qc2_governance_owner.identity_commit_owner_command(
    text, uuid, jsonb, text, uuid, timestamptz
  ),
  qc2_governance_owner.identity_verify_recovery_material(text, text),
  qc2_governance_owner.identity_store_recovery_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_recovery_challenge(text, uuid),
  qc2_governance_owner.identity_complete_recovery(
    text, uuid, text, jsonb, jsonb, text, text, timestamptz, text, jsonb, timestamptz
  ),
  qc2_governance_owner.identity_store_additional_enrollment_challenge(text, jsonb, jsonb),
  qc2_governance_owner.identity_get_additional_enrollment_challenge(text, uuid),
  qc2_governance_owner.identity_complete_additional_enrollment(
    text, uuid, uuid, uuid, jsonb, jsonb, text, text, timestamptz, timestamptz
  ),
  qc2_governance_owner.identity_resolve_session(text, uuid),
  qc2_governance_owner.identity_status(text)
TO qc2_runtime_identity;

GRANT EXECUTE ON FUNCTION
  qc2_governance_owner.identity_provision_owner(text, text, text)
TO qc2_migrator;

RESET ROLE;
