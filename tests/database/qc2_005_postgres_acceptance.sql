DO $isolation_check$
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'serializable' THEN
    RAISE EXCEPTION 'PostgreSQL acceptance must run at SERIALIZABLE isolation';
  END IF;
END
$isolation_check$;

DO $runtime_role_check$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname LIKE 'qc2_runtime_%'
      AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit)
  ) THEN
    RAISE EXCEPTION 'a runtime role has an elevated PostgreSQL attribute';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname = 'qc2_migrator'
      AND rolcanlogin AND NOT rolcreaterole AND NOT rolsuper
      AND NOT rolcreatedb AND NOT rolbypassrls AND NOT rolinherit
  ) THEN
    RAISE EXCEPTION 'the separate migration role is missing or misconfigured';
  END IF;
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
    RAISE EXCEPTION 'a QC2 role participates in an unexpected membership';
  END IF;
END
$runtime_role_check$;

SET LOCAL SESSION AUTHORIZATION qc2_migrator;
INSERT INTO qc2_control.job_definition(id, logical_key)
VALUES ('018f0000-0000-7000-8000-000000000001', 'acceptance-job');
INSERT INTO qc2_execution.reservation_resource(resource_key, capacity)
VALUES ('paper:account-1:AAPL', 10);
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
SAVEPOINT rollback_probe;
SELECT qc2_control.register_job(
  '018f0000-0000-7000-8000-000000000002',
  'rolled-back-job'
);
ROLLBACK TO SAVEPOINT rollback_probe;
DO $rollback_check$
BEGIN
  IF EXISTS (
    SELECT 1 FROM qc2_control.job_definition
    WHERE logical_key = 'rolled-back-job'
  ) THEN
    RAISE EXCEPTION 'rolled-back job definition remained visible';
  END IF;
END
$rollback_check$;
RELEASE SAVEPOINT rollback_probe;

DO $duplicate_id_check$
BEGIN
  BEGIN
    PERFORM qc2_control.register_job(
      '018f0000-0000-7000-8000-000000000001',
      'duplicate-id-job'
    );
    RAISE EXCEPTION 'duplicate job ID was accepted';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END
$duplicate_id_check$;

DO $first_job_claim$
DECLARE
  first_claim record;
BEGIN
  SELECT * INTO first_claim
    FROM qc2_control.claim_job(
      '018f0000-0000-7000-8000-000000000001',
      '018f0000-0000-7000-8000-000000000003',
      '10000000-0000-4000-8000-000000000001',
      300
    );
  IF first_claim.fencing_generation <> 1 THEN
    RAISE EXCEPTION 'first lease generation should be 1';
  END IF;
END
$first_job_claim$;

SELECT qc2_control.enqueue_outbox(
  '018f0000-0000-7000-8000-000000000004',
  '018f0000-0000-7000-8000-000000000005',
  'job_dispatch',
  repeat('a', 64)
);
DO $outbox_idempotency_check$
BEGIN
  IF qc2_control.enqueue_outbox(
    '018f0000-0000-7000-8000-000000000004',
    '018f0000-0000-7000-8000-000000000005',
    'job_dispatch',
    repeat('a', 64)
  ) <> '018f0000-0000-7000-8000-000000000004'::uuid THEN
    RAISE EXCEPTION 'same outbox operation was not idempotent';
  END IF;
  BEGIN
    PERFORM qc2_control.enqueue_outbox(
      '018f0000-0000-7000-8000-000000000004',
      '018f0000-0000-7000-8000-000000000005',
      'job_dispatch',
      repeat('b', 64)
    );
    RAISE EXCEPTION 'conflicting outbox content was accepted';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END
$outbox_idempotency_check$;

DO $outbox_claim_check$
DECLARE
  claim record;
BEGIN
  SELECT * INTO claim
    FROM qc2_control.claim_outbox(
      '10000000-0000-4000-8000-000000000002',
      300
    );
  IF claim.message_id <> '018f0000-0000-7000-8000-000000000004'::uuid
    OR claim.fencing_generation <> 1 THEN
    RAISE EXCEPTION 'outbox claim did not return the first fencing generation';
  END IF;
END
$outbox_claim_check$;
DO $durable_service_cross_authority_check$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    PERFORM qc2_control.reserve_resource(
      '018f0000-0000-7000-8000-000000000009',
      'paper:account-1:AAPL',
      'cross-authority-reservation',
      1
    );
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'scheduler role invoked an execution-only mutation';
  END IF;
END
$durable_service_cross_authority_check$;
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_migrator;
UPDATE qc2_control.job_lease
  SET lease_expires_at = pg_catalog.clock_timestamp() - interval '1 second'
  WHERE job_id = '018f0000-0000-7000-8000-000000000001';
UPDATE qc2_control.outbox_message
  SET lease_expires_at = pg_catalog.clock_timestamp() - interval '1 second'
  WHERE id = '018f0000-0000-7000-8000-000000000004';
DO $immutable_outbox_trigger_check$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    UPDATE qc2_control.outbox_message
      SET payload_hash = repeat('f', 64)
      WHERE id = '018f0000-0000-7000-8000-000000000004';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'outbox immutability trigger accepted a payload change';
  END IF;
END
$immutable_outbox_trigger_check$;
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_durable_job_service;
DO $stale_generation_check$
DECLARE
  second_claim record;
BEGIN
  SELECT * INTO second_claim
    FROM qc2_control.claim_job(
      '018f0000-0000-7000-8000-000000000001',
      '018f0000-0000-7000-8000-000000000006',
      '10000000-0000-4000-8000-000000000003',
      300
    );
  IF second_claim.fencing_generation <> 2 THEN
    RAISE EXCEPTION 'expired lease did not advance the fencing generation';
  END IF;
  IF qc2_control.complete_job(
    '018f0000-0000-7000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    1
  ) THEN
    RAISE EXCEPTION 'stale worker completed a newer job generation';
  END IF;
  IF NOT qc2_control.complete_job(
    '018f0000-0000-7000-8000-000000000001',
    '10000000-0000-4000-8000-000000000003',
    2
  ) THEN
    RAISE EXCEPTION 'current worker could not complete its job generation';
  END IF;
END
$stale_generation_check$;
DO $stale_outbox_check$
DECLARE
  second_claim record;
BEGIN
  SELECT * INTO second_claim
    FROM qc2_control.claim_outbox(
      '10000000-0000-4000-8000-000000000004',
      300
    );
  IF second_claim.fencing_generation <> 2 THEN
    RAISE EXCEPTION 'expired outbox lease did not advance its generation';
  END IF;
  IF qc2_control.complete_outbox(
    '018f0000-0000-7000-8000-000000000004',
    '10000000-0000-4000-8000-000000000002',
    1,
    true
  ) THEN
    RAISE EXCEPTION 'stale worker completed a newer outbox generation';
  END IF;
  IF NOT qc2_control.complete_outbox(
    '018f0000-0000-7000-8000-000000000004',
    '10000000-0000-4000-8000-000000000004',
    2,
    true
  ) THEN
    RAISE EXCEPTION 'current worker could not complete its outbox generation';
  END IF;
END
$stale_outbox_check$;
RESET SESSION AUTHORIZATION;

SET LOCAL SESSION AUTHORIZATION qc2_runtime_execution;
SELECT qc2_control.reserve_resource(
  '018f0000-0000-7000-8000-000000000007',
  'paper:account-1:AAPL',
  'intent-1',
  6
);
DO $reservation_idempotency_check$
BEGIN
  IF qc2_control.reserve_resource(
    '018f0000-0000-7000-8000-000000000007',
    'paper:account-1:AAPL',
    'intent-1',
    6
  ) <> '018f0000-0000-7000-8000-000000000007'::uuid THEN
    RAISE EXCEPTION 'identical reservation retry was not idempotent';
  END IF;
  BEGIN
    PERFORM qc2_control.reserve_resource(
      '018f0000-0000-7000-8000-000000000008',
      'paper:account-1:AAPL',
      'intent-2',
      5
    );
    RAISE EXCEPTION 'conflicting reservation exceeded resource capacity';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
  IF (
    SELECT reserved FROM qc2_execution.reservation_resource
    WHERE resource_key = 'paper:account-1:AAPL'
  ) <> 6 THEN
    RAISE EXCEPTION 'rejected reservation changed the reserved balance';
  END IF;
END
$reservation_idempotency_check$;

DO $cross_authority_check$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    PERFORM qc2_control.register_job(
      '018f0000-0000-7000-8000-000000000009',
      'cross-authority-job'
    );
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'execution role invoked a scheduler-only mutation';
  END IF;

  BEGIN
    PERFORM pg_catalog.set_config(
      'role',
      'qc2_runtime_durable_job_service',
      true
    );
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
  IF qc2_control.current_runtime_authority() <> 'execution' THEN
    RAISE EXCEPTION 'execution role spoofed another authority identity';
  END IF;

  denied := false;
  BEGIN
    UPDATE qc2_control.outbox_message
      SET payload_hash = repeat('c', 64)
      WHERE logical_operation_id = '018f0000-0000-7000-8000-000000000005';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'runtime role modified an immutable outbox record';
  END IF;
END
$cross_authority_check$;

DO $row_security_check$
DECLARE
  row_visible boolean;
  denied boolean := false;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM qc2_control.outbox_message
    WHERE logical_operation_id = '018f0000-0000-7000-8000-000000000005'
  ) INTO row_visible;
  IF row_visible THEN
    RAISE EXCEPTION 'execution authority observed another authority outbox row';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
  ) THEN
    RAISE EXCEPTION 'runtime role can bypass row-level security';
  END IF;

  PERFORM pg_catalog.set_config('row_security', 'off', true);
  BEGIN
    PERFORM count(*) FROM qc2_control.outbox_message;
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'row_security=off bypassed a runtime row policy';
  END IF;
END
$row_security_check$;

DO $ddl_escalation_check$
DECLARE
  denied boolean := false;
BEGIN
  BEGIN
    EXECUTE 'CREATE TABLE qc2_execution.runtime_ddl_probe(id integer)';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'runtime role created a table';
  END IF;

  denied := false;
  BEGIN
    EXECUTE 'SET LOCAL ROLE qc2_migrator';
  EXCEPTION WHEN insufficient_privilege THEN
    denied := true;
  END;
  IF NOT denied THEN
    RAISE EXCEPTION 'runtime role escalated to the migration role';
  END IF;
END
$ddl_escalation_check$;
RESET SESSION AUTHORIZATION;
