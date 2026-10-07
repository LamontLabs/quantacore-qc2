-- QC2-005 PostgreSQL authority foundation.
-- Bootstrap must be reviewed and applied to one development/test database at a
-- time. The migration creates the offline migration identity, then owns all
-- product schemas and SECURITY DEFINER interfaces through that identity.

DO $bootstrap_migration_role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'qc2_migrator') THEN
    EXECUTE 'CREATE ROLE qc2_migrator LOGIN CREATEROLE NOCREATEDB NOSUPERUSER NOINHERIT NOREPLICATION NOBYPASSRLS';
  ELSE
    IF EXISTS (
      SELECT 1
      FROM pg_catalog.pg_roles
      WHERE rolname = 'qc2_migrator'
        AND (
          NOT rolcanlogin OR NOT rolcreaterole OR rolsuper OR rolcreatedb
          OR rolreplication OR rolbypassrls OR rolinherit
        )
    ) THEN
      RAISE EXCEPTION 'existing qc2_migrator role has unsafe attributes';
    END IF;
  END IF;
END
$bootstrap_migration_role$;

DO $grant_migration_schema_privilege$
BEGIN
  IF NOT pg_catalog.has_database_privilege(
    'qc2_migrator', pg_catalog.current_database(), 'CREATE'
  ) THEN
    EXECUTE pg_catalog.format(
      'GRANT CREATE ON DATABASE %I TO qc2_migrator',
      pg_catalog.current_database()
    );
  END IF;
END
$grant_migration_schema_privilege$;

DO $runtime_roles$
DECLARE
  authority text;
  role_name text;
  role_attributes record;
  authorities constant text[] := ARRAY[
    'alert',
    'apexlab',
    'build_governance',
    'calendar',
    'configuration',
    'core',
    'durable_job_service',
    'evidence',
    'execution',
    'feature',
    'governance',
    'ground_truth',
    'identity',
    'inference',
    'instrument_universe',
    'label',
    'market_data',
    'model_registry',
    'owner_api',
    'prediction',
    'promotion',
    'quantscore',
    'runner_protocol',
    'safety',
    'strategy',
    'universe',
    'validation'
  ];
BEGIN
  FOREACH authority IN ARRAY authorities LOOP
    role_name := 'qc2_runtime_' || authority;
    SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit, rolcanlogin
      INTO role_attributes
      FROM pg_catalog.pg_roles
      WHERE rolname = role_name;

    IF NOT FOUND THEN
      EXECUTE pg_catalog.format(
        'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',
        role_name
      );
    ELSIF role_attributes.rolsuper
      OR role_attributes.rolcreatedb
      OR role_attributes.rolcreaterole
      OR role_attributes.rolreplication
      OR role_attributes.rolbypassrls
      OR role_attributes.rolinherit
      OR NOT role_attributes.rolcanlogin THEN
      RAISE EXCEPTION 'existing runtime role % has unsafe attributes', role_name;
    END IF;

  END LOOP;
END
$runtime_roles$;

DO $qc2_role_membership_guard$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_auth_members AS membership
    JOIN pg_catalog.pg_roles AS granted_role
      ON granted_role.oid = membership.roleid
    JOIN pg_catalog.pg_roles AS member_role
      ON member_role.oid = membership.member
    WHERE granted_role.rolname = 'qc2_migrator'
       OR granted_role.rolname ~ '^qc2_runtime_'
       OR member_role.rolname = 'qc2_migrator'
       OR member_role.rolname ~ '^qc2_runtime_'
  ) THEN
    RAISE EXCEPTION 'QC2 roles must not participate in PostgreSQL role memberships';
  END IF;
END
$qc2_role_membership_guard$;

ALTER ROLE qc2_migrator NOCREATEROLE;
SET ROLE qc2_migrator;

CREATE SCHEMA qc2_control AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_time_operation AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_identity_market AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_scientific_definitions AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_models_prediction AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_outcomes_research AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_validation AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_execution AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_governance_owner AUTHORIZATION qc2_migrator;
CREATE SCHEMA qc2_integrity_build AUTHORIZATION qc2_migrator;

REVOKE ALL ON SCHEMA qc2_control FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_time_operation FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_identity_market FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_scientific_definitions FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_models_prediction FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_outcomes_research FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_validation FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_execution FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_governance_owner FROM PUBLIC;
REVOKE ALL ON SCHEMA qc2_integrity_build FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_control
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_control
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_control
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_execution
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_execution
  REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE qc2_migrator IN SCHEMA qc2_execution
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

GRANT USAGE ON SCHEMA qc2_time_operation TO
  qc2_runtime_calendar, qc2_runtime_durable_job_service, qc2_runtime_safety,
  qc2_runtime_core, qc2_runtime_prediction, qc2_runtime_validation,
  qc2_runtime_owner_api, qc2_runtime_evidence, qc2_runtime_configuration;
GRANT USAGE ON SCHEMA qc2_identity_market TO
  qc2_runtime_instrument_universe, qc2_runtime_market_data, qc2_runtime_universe,
  qc2_runtime_feature, qc2_runtime_prediction, qc2_runtime_ground_truth,
  qc2_runtime_validation, qc2_runtime_apexlab, qc2_runtime_evidence,
  qc2_runtime_core;
GRANT USAGE ON SCHEMA qc2_scientific_definitions TO
  qc2_runtime_feature, qc2_runtime_runner_protocol, qc2_runtime_safety,
  qc2_runtime_label, qc2_runtime_quantscore, qc2_runtime_inference,
  qc2_runtime_prediction, qc2_runtime_validation, qc2_runtime_model_registry,
  qc2_runtime_apexlab, qc2_runtime_owner_api;
GRANT USAGE ON SCHEMA qc2_models_prediction TO
  qc2_runtime_model_registry, qc2_runtime_inference, qc2_runtime_prediction,
  qc2_runtime_validation, qc2_runtime_promotion, qc2_runtime_execution,
  qc2_runtime_owner_api, qc2_runtime_apexlab, qc2_runtime_evidence;
GRANT USAGE ON SCHEMA qc2_outcomes_research TO
  qc2_runtime_ground_truth, qc2_runtime_apexlab, qc2_runtime_validation,
  qc2_runtime_prediction, qc2_runtime_model_registry, qc2_runtime_evidence,
  qc2_runtime_owner_api;
GRANT USAGE ON SCHEMA qc2_validation TO
  qc2_runtime_validation, qc2_runtime_prediction, qc2_runtime_ground_truth,
  qc2_runtime_model_registry, qc2_runtime_promotion, qc2_runtime_owner_api,
  qc2_runtime_evidence, qc2_runtime_apexlab;
GRANT USAGE ON SCHEMA qc2_execution TO
  qc2_runtime_execution, qc2_runtime_strategy, qc2_runtime_configuration,
  qc2_runtime_safety, qc2_runtime_prediction, qc2_runtime_instrument_universe,
  qc2_runtime_market_data, qc2_runtime_owner_api, qc2_runtime_evidence,
  qc2_runtime_alert;
GRANT USAGE ON SCHEMA qc2_governance_owner TO
  qc2_runtime_promotion, qc2_runtime_validation, qc2_runtime_identity,
  qc2_runtime_owner_api, qc2_runtime_model_registry, qc2_runtime_execution,
  qc2_runtime_alert, qc2_runtime_evidence;
GRANT USAGE ON SCHEMA qc2_integrity_build TO
  qc2_runtime_evidence, qc2_runtime_model_registry, qc2_runtime_core,
  qc2_runtime_apexlab, qc2_runtime_validation, qc2_runtime_owner_api,
  qc2_runtime_configuration, qc2_runtime_governance,
  qc2_runtime_build_governance;

CREATE TABLE qc2_control.schema_migrations (
  version text PRIMARY KEY CHECK (version ~ '^[0-9]{4}_[a-z0-9_]+\.sql$'),
  sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  applied_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  applied_by name NOT NULL DEFAULT session_user
);

CREATE TABLE qc2_control.job_definition (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  logical_key text NOT NULL UNIQUE CHECK (logical_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  owner_authority text NOT NULL DEFAULT 'durable_job_service'
    CHECK (owner_authority = 'durable_job_service'),
  deadline timestamptz,
  state text NOT NULL DEFAULT 'QUEUED'
    CHECK (state IN ('QUEUED','CLAIMED','RUNNING','SUCCEEDED','FAILED_RETRYABLE','TERMINAL_FAILURE','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_control.job_lease (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  job_id uuid NOT NULL UNIQUE REFERENCES qc2_control.job_definition(id) ON DELETE RESTRICT,
  owner_authority text NOT NULL DEFAULT 'durable_job_service'
    CHECK (owner_authority = 'durable_job_service'),
  lease_owner uuid NOT NULL,
  lease_expires_at timestamptz NOT NULL,
  fencing_generation bigint NOT NULL CHECK (fencing_generation > 0),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_control.outbox_message (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  logical_operation_id uuid NOT NULL UNIQUE CHECK (
    logical_operation_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  owner_authority text NOT NULL DEFAULT 'durable_job_service'
    CHECK (owner_authority = 'durable_job_service'),
  message_type text NOT NULL CHECK (message_type ~ '^[a-z][a-z0-9_-]{0,95}$'),
  payload_hash char(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  status text NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','PUBLISHING','DELIVERED','UNKNOWN','FAILED')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at timestamptz,
  lease_owner uuid,
  fencing_generation bigint NOT NULL DEFAULT 0 CHECK (fencing_generation >= 0),
  lease_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  delivered_at timestamptz,
  CHECK ((status = 'DELIVERED') = (delivered_at IS NOT NULL))
);

CREATE TABLE qc2_execution.reservation_resource (
  resource_key text PRIMARY KEY CHECK (length(resource_key) BETWEEN 1 AND 160),
  owner_authority text NOT NULL DEFAULT 'execution'
    CHECK (owner_authority = 'execution'),
  capacity numeric(38, 12) NOT NULL CHECK (capacity > 0),
  reserved numeric(38, 12) NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= capacity),
  generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.resource_reservation (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  resource_key text NOT NULL REFERENCES qc2_execution.reservation_resource(resource_key) ON DELETE RESTRICT,
  reservation_key text NOT NULL CHECK (length(reservation_key) BETWEEN 1 AND 160),
  owner_authority text NOT NULL DEFAULT 'execution'
    CHECK (owner_authority = 'execution'),
  quantity numeric(38, 12) NOT NULL CHECK (quantity > 0),
  state text NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','RELEASED')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  released_at timestamptz,
  UNIQUE (resource_key, reservation_key),
  CHECK ((state = 'RELEASED') = (released_at IS NOT NULL))
);

ALTER TABLE qc2_control.schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.schema_migrations FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.job_definition ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.job_definition FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.job_lease ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.job_lease FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.outbox_message ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_control.outbox_message FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.reservation_resource ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.reservation_resource FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.resource_reservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_execution.resource_reservation FORCE ROW LEVEL SECURITY;

CREATE POLICY schema_migrations_migrator_all ON qc2_control.schema_migrations
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY job_definition_migrator_all ON qc2_control.job_definition
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY job_lease_migrator_all ON qc2_control.job_lease
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY outbox_migrator_all ON qc2_control.outbox_message
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY reservation_resource_migrator_all ON qc2_execution.reservation_resource
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY resource_reservation_migrator_all ON qc2_execution.resource_reservation
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

CREATE FUNCTION qc2_control.current_runtime_authority()
RETURNS text
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  authenticated_role text;
BEGIN
  authenticated_role := session_user::text;
  IF authenticated_role !~ '^qc2_runtime_[a-z][a-z0-9_]*$' THEN
    RAISE EXCEPTION 'authenticated runtime role is required'
      USING ERRCODE = '42501';
  END IF;
  RETURN pg_catalog.substr(
    authenticated_role,
    pg_catalog.length('qc2_runtime_') + 1
  );
END
$function$;

CREATE FUNCTION qc2_control.assert_runtime_authority(expected_authority text)
RETURNS void
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  IF qc2_control.current_runtime_authority() <> expected_authority THEN
    RAISE EXCEPTION 'runtime authority is not authorized for this mutation'
      USING ERRCODE = '42501';
  END IF;
END
$function$;

CREATE FUNCTION qc2_control.register_job(
  p_id uuid,
  p_logical_key text,
  p_deadline timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  INSERT INTO qc2_control.job_definition(id, logical_key, deadline)
  VALUES (p_id, p_logical_key, p_deadline);
  RETURN p_id;
END
$function$;

CREATE FUNCTION qc2_control.claim_job(
  p_job_id uuid,
  p_lease_id uuid,
  p_worker_id uuid,
  p_lease_seconds integer
)
RETURNS TABLE(fencing_generation bigint, lease_expires_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  job_state text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  IF p_lease_seconds NOT BETWEEN 1 AND 3600 THEN
    RAISE EXCEPTION 'lease duration must be between 1 and 3600 seconds'
      USING ERRCODE = '22023';
  END IF;
  SELECT definition.state
    INTO job_state
    FROM qc2_control.job_definition AS definition
    WHERE definition.id = p_job_id
    FOR UPDATE;
  IF NOT FOUND OR job_state NOT IN ('QUEUED','CLAIMED','RUNNING') THEN
    RAISE EXCEPTION 'job is missing or not claimable'
      USING ERRCODE = '23514';
  END IF;

  INSERT INTO qc2_control.job_lease AS current_lease (
    id, job_id, lease_owner, lease_expires_at, fencing_generation
  )
  VALUES (
    p_lease_id, p_job_id, p_worker_id,
    pg_catalog.clock_timestamp() + pg_catalog.make_interval(secs => p_lease_seconds),
    1
  )
  ON CONFLICT (job_id) DO UPDATE
    SET id = EXCLUDED.id,
        lease_owner = EXCLUDED.lease_owner,
        lease_expires_at = EXCLUDED.lease_expires_at,
        fencing_generation = current_lease.fencing_generation + 1,
        updated_at = pg_catalog.clock_timestamp()
    WHERE current_lease.lease_expires_at <= pg_catalog.clock_timestamp()
  RETURNING current_lease.fencing_generation, current_lease.lease_expires_at
    INTO fencing_generation, lease_expires_at;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'job already has a live lease'
      USING ERRCODE = '55P03';
  END IF;
  UPDATE qc2_control.job_definition
    SET state = 'CLAIMED'
    WHERE id = p_job_id;
  RETURN NEXT;
END
$function$;

CREATE FUNCTION qc2_control.complete_job(
  p_job_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  completed boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  UPDATE qc2_control.job_lease
    SET lease_expires_at = pg_catalog.clock_timestamp(),
        updated_at = pg_catalog.clock_timestamp()
    WHERE job_id = p_job_id
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp();
  completed := FOUND;
  IF completed THEN
    UPDATE qc2_control.job_definition
      SET state = 'SUCCEEDED'
      WHERE id = p_job_id;
  END IF;
  RETURN completed;
END
$function$;

CREATE FUNCTION qc2_control.enqueue_outbox(
  p_id uuid,
  p_logical_operation_id uuid,
  p_message_type text,
  p_payload_hash text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  existing_message qc2_control.outbox_message%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  INSERT INTO qc2_control.outbox_message(
    id, logical_operation_id, message_type, payload_hash
  )
  VALUES (p_id, p_logical_operation_id, p_message_type, p_payload_hash)
  ON CONFLICT (logical_operation_id) DO NOTHING;

  SELECT * INTO existing_message
    FROM qc2_control.outbox_message
    WHERE logical_operation_id = p_logical_operation_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'outbox operation could not be recorded'
      USING ERRCODE = '23514';
  END IF;
  IF existing_message.id <> p_id
    OR existing_message.message_type <> p_message_type
    OR existing_message.payload_hash <> p_payload_hash THEN
    RAISE EXCEPTION 'logical operation ID was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  RETURN existing_message.id;
END
$function$;

CREATE FUNCTION qc2_control.claim_outbox(
  p_worker_id uuid,
  p_lease_seconds integer
)
RETURNS TABLE(message_id uuid, fencing_generation bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  selected_id uuid;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  IF p_lease_seconds NOT BETWEEN 1 AND 3600 THEN
    RAISE EXCEPTION 'lease duration must be between 1 and 3600 seconds'
      USING ERRCODE = '22023';
  END IF;
  SELECT message.id
    INTO selected_id
    FROM qc2_control.outbox_message AS message
    WHERE message.status IN ('PENDING','UNKNOWN','PUBLISHING')
      AND (message.next_attempt_at IS NULL OR message.next_attempt_at <= pg_catalog.clock_timestamp())
      AND (message.lease_expires_at IS NULL OR message.lease_expires_at <= pg_catalog.clock_timestamp())
    ORDER BY message.created_at, message.id
    FOR UPDATE SKIP LOCKED
    LIMIT 1;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  UPDATE qc2_control.outbox_message AS message
    SET status = 'PUBLISHING',
        attempt_count = message.attempt_count + 1,
        lease_owner = p_worker_id,
        fencing_generation = message.fencing_generation + 1,
        lease_expires_at = pg_catalog.clock_timestamp() + pg_catalog.make_interval(secs => p_lease_seconds)
    WHERE message.id = selected_id
    RETURNING message.id, message.fencing_generation
      INTO message_id, fencing_generation;
  RETURN NEXT;
END
$function$;

CREATE FUNCTION qc2_control.complete_outbox(
  p_message_id uuid,
  p_worker_id uuid,
  p_fencing_generation bigint,
  p_delivered boolean
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control
AS $function$
DECLARE
  completed boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  UPDATE qc2_control.outbox_message
    SET status = CASE WHEN p_delivered THEN 'DELIVERED' ELSE 'UNKNOWN' END,
        next_attempt_at = CASE
          WHEN p_delivered THEN NULL
          ELSE pg_catalog.clock_timestamp() + interval '1 second'
        END,
        delivered_at = CASE
          WHEN p_delivered THEN pg_catalog.clock_timestamp()
          ELSE NULL
        END,
        lease_expires_at = NULL,
        lease_owner = NULL
    WHERE id = p_message_id
      AND lease_owner = p_worker_id
      AND fencing_generation = p_fencing_generation
      AND lease_expires_at > pg_catalog.clock_timestamp()
      AND status = 'PUBLISHING';
  completed := FOUND;
  RETURN completed;
END
$function$;

CREATE FUNCTION qc2_control.set_reservation_capacity(
  p_resource_key text,
  p_capacity numeric
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_capacity <= 0 THEN
    RAISE EXCEPTION 'reservation capacity must be positive'
      USING ERRCODE = '22023';
  END IF;
  INSERT INTO qc2_execution.reservation_resource(resource_key, capacity)
  VALUES (p_resource_key, p_capacity)
  ON CONFLICT (resource_key) DO UPDATE
    SET capacity = EXCLUDED.capacity,
        generation = qc2_execution.reservation_resource.generation + 1,
        updated_at = pg_catalog.clock_timestamp()
    WHERE EXCLUDED.capacity >= qc2_execution.reservation_resource.reserved;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'capacity cannot be reduced below active reservations'
      USING ERRCODE = '23514';
  END IF;
END
$function$;

CREATE FUNCTION qc2_control.reserve_resource(
  p_id uuid,
  p_resource_key text,
  p_reservation_key text,
  p_quantity numeric
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
DECLARE
  resource_capacity numeric(38,12);
  resource_reserved numeric(38,12);
  existing_reservation qc2_execution.resource_reservation%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_quantity <= 0 THEN
    RAISE EXCEPTION 'reservation quantity must be positive'
      USING ERRCODE = '22023';
  END IF;
  SELECT capacity, reserved
    INTO resource_capacity, resource_reserved
    FROM qc2_execution.reservation_resource
    WHERE resource_key = p_resource_key
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reservation resource is not registered'
      USING ERRCODE = '23503';
  END IF;

  SELECT * INTO existing_reservation
    FROM qc2_execution.resource_reservation
    WHERE resource_key = p_resource_key
      AND reservation_key = p_reservation_key
    FOR UPDATE;
  IF FOUND THEN
    IF existing_reservation.id = p_id
      AND existing_reservation.quantity = p_quantity
      AND existing_reservation.state = 'ACTIVE' THEN
      RETURN existing_reservation.id;
    END IF;
    RAISE EXCEPTION 'reservation key was reused with conflicting content'
      USING ERRCODE = '23505';
  END IF;

  IF resource_reserved + p_quantity > resource_capacity THEN
    RAISE EXCEPTION 'conflicting reservation exceeds available capacity'
      USING ERRCODE = '23514';
  END IF;
  UPDATE qc2_execution.reservation_resource
    SET reserved = reserved + p_quantity,
        generation = generation + 1,
        updated_at = pg_catalog.clock_timestamp()
    WHERE resource_key = p_resource_key;
  INSERT INTO qc2_execution.resource_reservation(
    id, resource_key, reservation_key, quantity
  )
  VALUES (p_id, p_resource_key, p_reservation_key, p_quantity);
  RETURN p_id;
END
$function$;

CREATE FUNCTION qc2_control.release_resource_reservation(
  p_resource_key text,
  p_reservation_key text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
DECLARE
  reservation_row qc2_execution.resource_reservation%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO reservation_row
    FROM qc2_execution.resource_reservation
    WHERE resource_key = p_resource_key
      AND reservation_key = p_reservation_key
      AND state = 'ACTIVE'
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  UPDATE qc2_execution.resource_reservation
    SET state = 'RELEASED',
        released_at = pg_catalog.clock_timestamp()
    WHERE id = reservation_row.id;
  UPDATE qc2_execution.reservation_resource
    SET reserved = reserved - reservation_row.quantity,
        generation = generation + 1,
        updated_at = pg_catalog.clock_timestamp()
    WHERE resource_key = p_resource_key;
  RETURN true;
END
$function$;

CREATE FUNCTION qc2_control.prevent_outbox_identity_change()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, qc2_control
AS $function$
BEGIN
  IF ROW(
    NEW.id,
    NEW.logical_operation_id,
    NEW.owner_authority,
    NEW.message_type,
    NEW.payload_hash,
    NEW.created_at
  ) IS DISTINCT FROM ROW(
    OLD.id,
    OLD.logical_operation_id,
    OLD.owner_authority,
    OLD.message_type,
    OLD.payload_hash,
    OLD.created_at
  ) THEN
    RAISE EXCEPTION 'outbox identity and payload fields are immutable'
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END
$function$;

CREATE TRIGGER outbox_identity_is_immutable
BEFORE UPDATE ON qc2_control.outbox_message
FOR EACH ROW EXECUTE FUNCTION qc2_control.prevent_outbox_identity_change();

CREATE POLICY job_definition_runtime_read ON qc2_control.job_definition
  FOR SELECT TO
    qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
    qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
    qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
    qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
    qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
    qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
    qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
    qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
    qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation
  USING (owner_authority = qc2_control.current_runtime_authority());

CREATE POLICY job_lease_runtime_read ON qc2_control.job_lease
  FOR SELECT TO
    qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
    qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
    qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
    qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
    qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
    qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
    qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
    qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
    qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation
  USING (owner_authority = qc2_control.current_runtime_authority());

CREATE POLICY outbox_runtime_read ON qc2_control.outbox_message
  FOR SELECT TO
    qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
    qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
    qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
    qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
    qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
    qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
    qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
    qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
    qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation
  USING (owner_authority = qc2_control.current_runtime_authority());

CREATE POLICY reservation_resource_runtime_read ON qc2_execution.reservation_resource
  FOR SELECT TO
    qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
    qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
    qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
    qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
    qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
    qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
    qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
    qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
    qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation
  USING (owner_authority = qc2_control.current_runtime_authority());

CREATE POLICY resource_reservation_runtime_read ON qc2_execution.resource_reservation
  FOR SELECT TO
    qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
    qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
    qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
    qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
    qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
    qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
    qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
    qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
    qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation
  USING (owner_authority = qc2_control.current_runtime_authority());

GRANT USAGE ON SCHEMA qc2_control TO
  qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
  qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
  qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
  qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
  qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
  qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
  qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
  qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
  qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation;

GRANT SELECT ON qc2_control.job_definition, qc2_control.job_lease, qc2_control.outbox_message,
  qc2_execution.reservation_resource, qc2_execution.resource_reservation
TO
  qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
  qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
  qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
  qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
  qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
  qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
  qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
  qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
  qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation;

REVOKE ALL ON ALL TABLES IN SCHEMA qc2_control FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA qc2_execution FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qc2_control FROM PUBLIC;

GRANT EXECUTE ON FUNCTION qc2_control.current_runtime_authority() TO
  qc2_runtime_alert, qc2_runtime_apexlab, qc2_runtime_build_governance,
  qc2_runtime_calendar, qc2_runtime_configuration, qc2_runtime_core,
  qc2_runtime_durable_job_service, qc2_runtime_evidence, qc2_runtime_execution,
  qc2_runtime_feature, qc2_runtime_governance, qc2_runtime_ground_truth,
  qc2_runtime_identity, qc2_runtime_inference, qc2_runtime_instrument_universe,
  qc2_runtime_label, qc2_runtime_market_data, qc2_runtime_model_registry,
  qc2_runtime_owner_api, qc2_runtime_prediction, qc2_runtime_promotion,
  qc2_runtime_quantscore, qc2_runtime_runner_protocol, qc2_runtime_safety,
  qc2_runtime_strategy, qc2_runtime_universe, qc2_runtime_validation;

GRANT EXECUTE ON FUNCTION qc2_control.register_job(uuid, text, timestamptz),
  qc2_control.claim_job(uuid, uuid, uuid, integer),
  qc2_control.complete_job(uuid, uuid, bigint),
  qc2_control.enqueue_outbox(uuid, uuid, text, text),
  qc2_control.claim_outbox(uuid, integer),
  qc2_control.complete_outbox(uuid, uuid, bigint, boolean)
TO qc2_runtime_durable_job_service;

GRANT EXECUTE ON FUNCTION qc2_control.set_reservation_capacity(text, numeric),
  qc2_control.reserve_resource(uuid, text, text, numeric),
  qc2_control.release_resource_reservation(text, text)
TO qc2_runtime_execution;

RESET ROLE;
