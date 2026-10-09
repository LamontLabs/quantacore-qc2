-- QC2-055: durable owner-command payloads and immutable acceptance receipts.
SET ROLE qc2_migrator;

CREATE SEQUENCE qc2_governance_owner.owner_command_receipt_sequence
  AS bigint
  START WITH 1
  INCREMENT BY 1
  NO CYCLE;

CREATE TABLE qc2_governance_owner.owner_command_receipt_projection (
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development', 'test', 'research', 'production')
  ),
  source_sequence bigint NOT NULL CHECK (source_sequence > 0),
  receipt_id uuid NOT NULL CHECK (
    receipt_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  command_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_body_hash text NOT NULL CHECK (request_body_hash ~ '^[0-9a-f]{64}$'),
  request_body jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(request_body) = 'object'
  ),
  owner_command jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(owner_command) = 'object'
  ),
  receipt jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(receipt) = 'object'
    AND receipt->>'schema_name' = 'qc2.governance_owner.OwnerCommandReceipt.v1'
    AND receipt->>'id' = receipt_id::text
    AND receipt->>'environment_namespace' = environment_namespace
    AND receipt->'command_ref'->>'target_id' = owner_command->>'id'
    AND receipt->>'source_sequence' = source_sequence::text
    AND receipt->>'state' = 'ACCEPTED'
    AND receipt->'resulting_evidence_ref' = 'null'::jsonb
  ),
  received_at timestamptz NOT NULL,
  PRIMARY KEY (environment_namespace, idempotency_key),
  UNIQUE (environment_namespace, receipt_id),
  UNIQUE (environment_namespace, command_id),
  UNIQUE (environment_namespace, source_sequence),
  FOREIGN KEY (environment_namespace, idempotency_key)
    REFERENCES qc2_governance_owner.identity_owner_command(
      environment_namespace, idempotency_key
    )
    ON DELETE RESTRICT,
  FOREIGN KEY (environment_namespace, command_id)
    REFERENCES qc2_governance_owner.identity_owner_command(
      environment_namespace, command_id
    )
    ON DELETE RESTRICT
);

REVOKE ALL ON TABLE
  qc2_governance_owner.owner_command_receipt_projection
FROM PUBLIC;
REVOKE ALL ON SEQUENCE
  qc2_governance_owner.owner_command_receipt_sequence
FROM PUBLIC;

CREATE FUNCTION qc2_governance_owner.owner_api_commit_signed_command(
  p_environment_namespace text,
  p_challenge_id uuid,
  p_owner_command jsonb,
  p_request_body jsonb,
  p_target_device_id uuid,
  p_receipt_id uuid,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner, qc2_integrity_build
AS $function$
DECLARE
  environment_name text := p_environment_namespace;
  command_document jsonb := p_owner_command;
  request_body_document jsonb := p_request_body;
  request_hash text;
  expected_command_hash text;
  expected_scope text;
  challenge_row qc2_governance_owner.identity_challenge%ROWTYPE;
  session_row qc2_governance_owner.identity_session%ROWTYPE;
  device_row qc2_governance_owner.identity_device%ROWTYPE;
  existing_command qc2_governance_owner.identity_owner_command%ROWTYPE;
  existing_receipt qc2_governance_owner.owner_command_receipt_projection%ROWTYPE;
  identity_result jsonb;
  receipt_document jsonb;
  source_sequence_value bigint;
  command_status text;
BEGIN
  IF environment_name IS NULL
     OR environment_name NOT IN ('development', 'test', 'research', 'production')
     OR p_now IS NULL
     OR p_challenge_id IS NULL
     OR p_receipt_id IS NULL
     OR pg_catalog.jsonb_typeof(command_document) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(request_body_document) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'owner command input is invalid' USING ERRCODE = '23514';
  END IF;

  request_hash := qc2_integrity_build.hash_json(
    'qc2.owner.command-body.v1', request_body_document
  );
  IF command_document->>'schema_name'
       <> 'qc2.governance_owner.OwnerCommand.v1'
     OR command_document->>'schema_version' <> '1.0'
     OR command_document->>'environment_namespace' <> environment_name
     OR command_document->>'owning_authority' <> 'owner_api'
     OR command_document->>'request_body_hash' <> request_hash
     OR command_document->>'signature' IS NULL
     OR command_document->>'idempotency_key' IS NULL
     OR command_document->>'command_id' IS NULL THEN
    RAISE EXCEPTION 'owner command content does not match its request'
      USING ERRCODE = '23514';
  END IF;

  expected_command_hash := qc2_integrity_build.hash_json(
    'qc2.contract-content.v1/qc2.governance_owner.ownercommand.v1/1.0',
    pg_catalog.jsonb_build_object(
      'owning_authority', command_document->'owning_authority',
      'evidence_class', command_document->'evidence_class',
      'environment_namespace', command_document->'environment_namespace',
      'source_refs', command_document->'source_refs',
      'command_id', command_document->'command_id',
      'command_type', command_document->'command_type',
      'idempotency_key', command_document->'idempotency_key',
      'request_body_hash', command_document->'request_body_hash',
      'issued_at', command_document->'issued_at',
      'device_ref', command_document->'device_ref',
      'signature', command_document->'signature',
      'scope', command_document->'scope'
    )
  );
  IF command_document->>'content_hash' <> expected_command_hash THEN
    RAISE EXCEPTION 'owner command content hash is invalid'
      USING ERRCODE = '23514';
  END IF;

  expected_scope := CASE command_document->>'command_type'
    WHEN 'PROMOTION' THEN 'PROMOTION'
    WHEN 'EPOCH_ACTIVATION' THEN 'EPOCH_ACTIVATION'
    WHEN 'PAUSE_NEW_ENTRIES' THEN 'PAUSE'
    WHEN 'RESUME_REQUEST' THEN 'RESUME'
    WHEN 'ACKNOWLEDGE_ALERT' THEN 'ALERT'
    WHEN 'DEVICE_ACTION' THEN 'DEVICE_ADMIN'
    ELSE NULL
  END;
  IF expected_scope IS NULL OR command_document->>'scope' <> expected_scope THEN
    RAISE EXCEPTION 'owner command type is not authorized'
      USING ERRCODE = '42501';
  END IF;

  IF command_document->>'command_type' = 'DEVICE_ACTION' THEN
    IF request_body_document->>'schema_name'
         <> 'qc2.owner_api.OwnerCommandRequest.v1'
       OR request_body_document->>'schema_version' <> '1.0'
       OR request_body_document->>'command_type' <> 'DEVICE_ACTION'
       OR request_body_document->'payload'->>'action' <> 'REVOKE_DEVICE'
       OR p_target_device_id IS NULL
       OR request_body_document->'payload'->>'device_id'
          <> p_target_device_id::text THEN
      RAISE EXCEPTION 'unsupported device action'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_target_device_id IS NOT NULL THEN
    RAISE EXCEPTION 'device revocation requires a device-admin command'
      USING ERRCODE = '42501';
  END IF;

  SELECT * INTO challenge_row
  FROM qc2_governance_owner.identity_challenge AS challenge
  WHERE challenge.environment_namespace = environment_name
    AND challenge.challenge_type = 'COMMAND'
    AND challenge.id = p_challenge_id
  FOR UPDATE;
  IF NOT FOUND
     OR (challenge_row.challenge_document->>'expires_at')::timestamptz <= p_now THEN
    RAISE EXCEPTION 'owner command challenge is unknown or expired'
      USING ERRCODE = '55000';
  END IF;

  IF command_document->>'issued_at'
       <> challenge_row.challenge_document->>'issued_at'
     OR command_document->>'command_id'
       <> challenge_row.challenge_document->>'command_id'
     OR command_document->>'command_type'
       <> challenge_row.challenge_document->>'command_type'
     OR command_document->>'idempotency_key'
       <> challenge_row.challenge_document->>'idempotency_key'
     OR command_document->>'request_body_hash'
       <> challenge_row.challenge_document->>'request_body_hash'
     OR command_document->>'scope'
       <> challenge_row.challenge_document->>'scope'
     OR command_document->'device_ref'->>'target_id'
       <> challenge_row.challenge_document->'device_ref'->>'target_id'
     OR challenge_row.binding_document->>'request_body_hash' <> request_hash THEN
    RAISE EXCEPTION 'owner command does not match its signed challenge'
      USING ERRCODE = '23514';
  END IF;

  SELECT * INTO session_row
  FROM qc2_governance_owner.identity_session AS session
  WHERE session.environment_namespace = environment_name
    AND session.id = (challenge_row.binding_document->>'session_record_id')::uuid
  FOR UPDATE;
  IF NOT FOUND
     OR session_row.revoked_at IS NOT NULL
     OR (session_row.record->>'expires_at')::timestamptz <= p_now
     OR session_row.session_id <> challenge_row.binding_document->>'session_id'
     OR session_row.device_id
       <> (challenge_row.binding_document->>'device_id')::uuid
     OR session_row.record->>'environment_namespace' <> environment_name
     OR (
       environment_name <> 'test'
       AND session_row.record->>'evidence_class' = 'SYNTHETIC_FIXTURE'
     )
     OR NOT (
       session_row.record->'scope_refs' @>
       pg_catalog.jsonb_build_array(expected_scope)
     )
     OR command_document->'device_ref'->>'target_id'
       <> session_row.device_id::text
     OR challenge_row.challenge_document->'session_ref'->>'target_id'
       <> session_row.id::text
     OR challenge_row.challenge_document->'device_ref'->>'target_id'
       <> session_row.device_id::text THEN
    RAISE EXCEPTION 'owner command identity was revoked or changed before commit'
      USING ERRCODE = '42501';
  END IF;

  SELECT * INTO device_row
  FROM qc2_governance_owner.identity_device AS device
  WHERE device.environment_namespace = environment_name
    AND device.id = session_row.device_id
  FOR UPDATE;
  IF NOT FOUND
     OR device_row.revoked_at IS NOT NULL
     OR device_row.public_key_fingerprint
       <> challenge_row.challenge_document->>'public_key_fingerprint'
     OR device_row.record->>'owner_key_id'
       <> challenge_row.challenge_document->>'owner_key_id' THEN
    RAISE EXCEPTION 'owner command device was revoked or changed before commit'
      USING ERRCODE = '42501';
  END IF;

  SELECT * INTO existing_command
  FROM qc2_governance_owner.identity_owner_command AS command
  WHERE command.environment_namespace = environment_name
    AND command.idempotency_key = command_document->>'idempotency_key'
  FOR UPDATE;
  IF FOUND THEN
    IF existing_command.request_body_hash <> request_hash
       OR existing_command.device_id <> device_row.id
       OR existing_command.command_type <> command_document->>'command_type'
       OR existing_command.scope <> expected_scope THEN
      RAISE EXCEPTION 'owner command idempotency key conflicts with prior content'
        USING ERRCODE = '23505';
    END IF;
    SELECT * INTO existing_receipt
    FROM qc2_governance_owner.owner_command_receipt_projection AS projection
    WHERE projection.environment_namespace = environment_name
      AND projection.idempotency_key = command_document->>'idempotency_key'
    FOR UPDATE;
    IF NOT FOUND
       OR existing_receipt.request_body_hash <> request_hash
       OR existing_receipt.request_body <> request_body_document THEN
      RAISE EXCEPTION 'owner command receipt is unavailable for the prior command'
        USING ERRCODE = '23514';
    END IF;
    UPDATE qc2_governance_owner.identity_challenge AS challenge
      SET consumed_at = COALESCE(challenge.consumed_at, p_now)
      WHERE challenge.environment_namespace = environment_name
        AND challenge.challenge_type = 'COMMAND'
        AND challenge.id = p_challenge_id;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'DUPLICATE',
      'owner_command', existing_command.record,
      'receipt', existing_receipt.receipt
    );
  END IF;

  identity_result := qc2_governance_owner.identity_commit_owner_command(
    environment_name,
    p_challenge_id,
    command_document,
    command_document->>'idempotency_key',
    p_target_device_id,
    p_now
  );
  command_status := identity_result->>'status';
  IF command_status = 'DUPLICATE' THEN
    SELECT * INTO existing_receipt
    FROM qc2_governance_owner.owner_command_receipt_projection AS projection
    WHERE projection.environment_namespace = environment_name
      AND projection.idempotency_key = command_document->>'idempotency_key'
    FOR UPDATE;
    IF NOT FOUND
       OR existing_receipt.request_body_hash <> request_hash
       OR existing_receipt.request_body <> request_body_document THEN
      RAISE EXCEPTION 'owner command receipt is unavailable for the prior command'
        USING ERRCODE = '23514';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'status', 'DUPLICATE',
      'owner_command', identity_result->'owner_command',
      'receipt', existing_receipt.receipt
    );
  END IF;
  IF command_status <> 'COMMITTED' THEN
    RAISE EXCEPTION 'owner command was not committed'
      USING ERRCODE = '23514';
  END IF;

  source_sequence_value := pg_catalog.nextval(
    'qc2_governance_owner.owner_command_receipt_sequence'::regclass
  );
  receipt_document := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.OwnerCommandReceipt.v1',
    'schema_version', '1.0',
    'id', p_receipt_id::text,
    'created_at', pg_catalog.to_char(
      p_now AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
    ),
    'owning_authority', 'owner_api',
    'evidence_class', command_document->'evidence_class',
    'environment_namespace', environment_name,
    'source_refs', '[]'::jsonb,
    'command_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.governance_owner.OwnerCommand.v1',
      'target_id', command_document->>'id',
      'content_hash', command_document->>'content_hash'
    ),
    'state', 'ACCEPTED',
    'resulting_evidence_ref', NULL,
    'source_sequence', source_sequence_value,
    'projection_lag_ms', GREATEST(
      0,
      FLOOR(EXTRACT(EPOCH FROM (
        p_now - (command_document->>'created_at')::timestamptz
      )) * 1000)::bigint
    ),
    'received_at', pg_catalog.to_char(
      p_now AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
    )
  );

  INSERT INTO qc2_governance_owner.owner_command_receipt_projection(
    environment_namespace,
    source_sequence,
    receipt_id,
    command_id,
    idempotency_key,
    request_body_hash,
    request_body,
    owner_command,
    receipt,
    received_at
  )
  VALUES (
    environment_name,
    source_sequence_value,
    (receipt_document->>'id')::uuid,
    command_document->>'command_id',
    command_document->>'idempotency_key',
    request_hash,
    request_body_document,
    command_document,
    receipt_document,
    p_now
  );

  RETURN pg_catalog.jsonb_build_object(
    'status', 'COMMITTED',
    'owner_command', identity_result->'owner_command',
    'receipt', receipt_document
  );
END
$function$;

CREATE FUNCTION qc2_governance_owner.owner_command_payload_by_command(
  p_environment_namespace text,
  p_command_id text
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_governance_owner
AS $function$
  SELECT COALESCE(
    (
      SELECT pg_catalog.jsonb_build_object(
        'status', 'FOUND',
        'source_sequence', projection.source_sequence,
        'request_body', projection.request_body,
        'owner_command', projection.owner_command,
        'receipt', projection.receipt
      )
      FROM qc2_governance_owner.owner_command_receipt_projection AS projection
      WHERE projection.environment_namespace = p_environment_namespace
        AND projection.command_id = p_command_id
    ),
    pg_catalog.jsonb_build_object('status', 'NOT_FOUND')
  )
$function$;

REVOKE ALL ON FUNCTION
  qc2_governance_owner.owner_api_commit_signed_command(
    text, uuid, jsonb, jsonb, uuid, uuid, timestamptz
  ),
  qc2_governance_owner.owner_command_payload_by_command(text, text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
  qc2_governance_owner.owner_api_commit_signed_command(
    text, uuid, jsonb, jsonb, uuid, uuid, timestamptz
  )
TO qc2_runtime_identity;

GRANT EXECUTE ON FUNCTION qc2_governance_owner.owner_command_payload_by_command(
  text, text
)
TO qc2_runtime_alert, qc2_runtime_execution, qc2_runtime_identity,
   qc2_runtime_promotion, qc2_runtime_validation;

RESET ROLE;
