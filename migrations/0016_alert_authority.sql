-- QC2-056: deterministic alert state, lifecycle events, and safe delivery outbox.
-- This migration adds alert as a scoped producer to the shared outbox. The
-- generic durable-job-service remains the only role that leases/completes work.
SET ROLE qc2_migrator;

ALTER TABLE qc2_control.outbox_message
  DROP CONSTRAINT outbox_message_owner_authority_check,
  ADD CONSTRAINT outbox_message_owner_authority_check
    CHECK (owner_authority IN ('durable_job_service', 'execution', 'alert'));

CREATE SCHEMA qc2_alerts AUTHORIZATION qc2_migrator;
REVOKE ALL ON SCHEMA qc2_alerts FROM PUBLIC;
GRANT USAGE ON SCHEMA qc2_alerts
TO qc2_runtime_alert, qc2_runtime_durable_job_service;

CREATE FUNCTION qc2_alerts.severity_rank(p_severity text)
RETURNS integer
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $function$
  SELECT CASE p_severity
    WHEN 'INFO' THEN 0
    WHEN 'NOTICE' THEN 1
    WHEN 'WARNING' THEN 2
    WHEN 'CRITICAL' THEN 3
    WHEN 'EMERGENCY' THEN 4
    ELSE NULL
  END
$function$;

CREATE TABLE qc2_alerts.alert_rule (
  rule_key text PRIMARY KEY CHECK (rule_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  alert_type text NOT NULL CHECK (alert_type ~ '^[a-z][a-z0-9_-]{0,95}$'),
  base_severity text NOT NULL CHECK (
    base_severity IN ('INFO','NOTICE','WARNING','CRITICAL','EMERGENCY')
  ),
  escalation_policy text NOT NULL CHECK (
    escalation_policy IN ('monotonic_source_severity','manual_only')
  ),
  action_owner text NOT NULL CHECK (action_owner ~ '^[a-z][a-z0-9_-]{0,95}$'),
  auto_resolution_condition text NOT NULL CHECK (
    pg_catalog.char_length(auto_resolution_condition) BETWEEN 1 AND 256
  ),
  readiness_effect boolean NOT NULL,
  enabled boolean NOT NULL DEFAULT true
);

INSERT INTO qc2_alerts.alert_rule(
  rule_key, alert_type, base_severity, escalation_policy,
  action_owner, auto_resolution_condition, readiness_effect
)
VALUES
  ('operational_info', 'operational_info', 'INFO',
   'monotonic_source_severity', 'operator', 'source_condition_cleared', false),
  ('operational_notice', 'operational_notice', 'NOTICE',
   'monotonic_source_severity', 'operator', 'source_condition_cleared', false),
  ('operational_warning', 'operational_warning', 'WARNING',
   'monotonic_source_severity', 'operator', 'source_condition_cleared', false),
  ('readiness_failed', 'readiness_failed', 'CRITICAL',
   'monotonic_source_severity', 'operator', 'readiness_restored', true),
  ('safety_emergency', 'safety_emergency', 'EMERGENCY',
   'manual_only', 'operator', 'manual_resolution_required', true);

CREATE TABLE qc2_alerts.alert_instance (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  rule_key text NOT NULL REFERENCES qc2_alerts.alert_rule(rule_key)
    ON DELETE RESTRICT,
  dedupe_key text NOT NULL CHECK (dedupe_key ~ '^[a-z][a-z0-9_-]{0,95}$'),
  current_severity text NOT NULL CHECK (
    current_severity IN ('INFO','NOTICE','WARNING','CRITICAL','EMERGENCY')
  ),
  alert_contract jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(alert_contract) = 'object'
    AND alert_contract->>'schema_name' = 'qc2.governance_owner.Alert.v1'
    AND alert_contract->>'schema_version' = '1.0'
    AND alert_contract->>'owning_authority' = 'alert'
    AND alert_contract->>'id' = id::text
    AND alert_contract->>'environment_namespace' = environment_namespace
    AND alert_contract->>'alert_type' IS NOT NULL
    AND alert_contract->>'trigger_rule' = rule_key
    AND alert_contract->>'dedupe_key' = dedupe_key
    AND alert_contract->>'severity' IN (
      'INFO','NOTICE','WARNING','CRITICAL','EMERGENCY'
    )
    AND pg_catalog.jsonb_typeof(alert_contract->'source_refs') = 'array'
    AND pg_catalog.jsonb_typeof(alert_contract->'evidence_refs') = 'array'
  ),
  state text NOT NULL DEFAULT 'OPEN' CHECK (state IN ('OPEN','RESOLVED')),
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  resolution_kind text CHECK (resolution_kind IN ('AUTO','MANUAL')),
  resolution_code text CHECK (
    resolution_code IS NULL OR resolution_code ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  trigger_count bigint NOT NULL DEFAULT 1 CHECK (trigger_count >= 1),
  created_at timestamptz NOT NULL,
  last_triggered_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK (last_triggered_at >= created_at),
  CHECK (updated_at >= created_at),
  CHECK ((state = 'RESOLVED') = (resolved_at IS NOT NULL)),
  CHECK ((state = 'RESOLVED') = (resolution_kind IS NOT NULL)),
  CHECK ((state = 'RESOLVED') = (resolution_code IS NOT NULL))
);

CREATE UNIQUE INDEX alert_one_open_per_dedupe_key
  ON qc2_alerts.alert_instance(environment_namespace, rule_key, dedupe_key)
  WHERE state = 'OPEN';

CREATE INDEX alert_instance_timeline
  ON qc2_alerts.alert_instance(
    environment_namespace, created_at DESC, id DESC
  );

CREATE TABLE qc2_alerts.alert_event (
  id uuid PRIMARY KEY CHECK (
    id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  alert_id uuid NOT NULL
    REFERENCES qc2_alerts.alert_instance(id) ON DELETE RESTRICT,
  event_type text NOT NULL CHECK (
    event_type IN (
      'TRIGGERED','ESCALATED','ACKNOWLEDGED','AUTO_RESOLVED','MANUAL_RESOLVED'
    )
  ),
  from_severity text CHECK (
    from_severity IS NULL OR
      from_severity IN ('INFO','NOTICE','WARNING','CRITICAL','EMERGENCY')
  ),
  to_severity text NOT NULL CHECK (
    to_severity IN ('INFO','NOTICE','WARNING','CRITICAL','EMERGENCY')
  ),
  source_refs jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(source_refs) = 'array'
  ),
  evidence_refs jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(evidence_refs) = 'array'
  ),
  resolution_code text CHECK (
    resolution_code IS NULL OR resolution_code ~ '^[a-z][a-z0-9_-]{0,95}$'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CHECK (
    (event_type = 'TRIGGERED' AND from_severity IS NULL)
    OR (event_type <> 'TRIGGERED' AND from_severity IS NOT NULL)
  ),
  CHECK (
    (event_type IN ('AUTO_RESOLVED','MANUAL_RESOLVED'))
    = (resolution_code IS NOT NULL)
  )
);

CREATE INDEX alert_event_timeline
  ON qc2_alerts.alert_event(alert_id, created_at, id);

CREATE TABLE qc2_alerts.delivery_payload (
  outbox_message_id uuid PRIMARY KEY
    REFERENCES qc2_control.outbox_message(id) ON DELETE RESTRICT,
  alert_id uuid NOT NULL
    REFERENCES qc2_alerts.alert_instance(id) ON DELETE RESTRICT,
  event_id uuid NOT NULL UNIQUE
    REFERENCES qc2_alerts.alert_event(id) ON DELETE RESTRICT,
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  payload jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(payload) = 'object'
    AND payload->>'payload_type' = 'alert_notification'
    AND payload->>'alert_id' = alert_id::text
    AND pg_catalog.jsonb_typeof(payload->'source_refs') = 'array'
    AND pg_catalog.jsonb_typeof(payload->'evidence_refs') = 'array'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

ALTER TABLE qc2_alerts.alert_rule ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.alert_rule FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.alert_instance ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.alert_instance FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.alert_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.alert_event FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.delivery_payload ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_alerts.delivery_payload FORCE ROW LEVEL SECURITY;

CREATE POLICY alert_rule_migrator_all ON qc2_alerts.alert_rule
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY alert_instance_migrator_all ON qc2_alerts.alert_instance
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY alert_event_migrator_all ON qc2_alerts.alert_event
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY alert_delivery_migrator_all ON qc2_alerts.delivery_payload
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY alert_rule_runtime_read ON qc2_alerts.alert_rule
  FOR SELECT TO qc2_runtime_alert USING (true);
CREATE POLICY alert_instance_runtime_read ON qc2_alerts.alert_instance
  FOR SELECT TO qc2_runtime_alert USING (true);
CREATE POLICY alert_event_runtime_read ON qc2_alerts.alert_event
  FOR SELECT TO qc2_runtime_alert USING (true);
CREATE POLICY alert_delivery_runtime_read ON qc2_alerts.delivery_payload
  FOR SELECT TO qc2_runtime_alert USING (true);
CREATE POLICY alert_delivery_worker_read ON qc2_alerts.delivery_payload
  FOR SELECT TO qc2_runtime_durable_job_service USING (true);

REVOKE ALL ON ALL TABLES IN SCHEMA qc2_alerts
FROM PUBLIC, qc2_runtime_alert, qc2_runtime_durable_job_service;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA qc2_alerts
FROM PUBLIC, qc2_runtime_alert, qc2_runtime_durable_job_service;
GRANT SELECT ON qc2_alerts.alert_rule, qc2_alerts.alert_instance,
  qc2_alerts.alert_event, qc2_alerts.delivery_payload
TO qc2_runtime_alert;
GRANT SELECT ON qc2_alerts.delivery_payload
TO qc2_runtime_durable_job_service;

CREATE FUNCTION qc2_alerts.assert_references(
  p_source_refs jsonb,
  p_evidence_refs jsonb,
  p_require_source boolean
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts
AS $function$
DECLARE
  ref jsonb;
BEGIN
  IF pg_catalog.jsonb_typeof(p_source_refs) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_typeof(p_evidence_refs) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_array_length(p_source_refs) > 64
    OR pg_catalog.jsonb_array_length(p_evidence_refs) > 64
    OR (p_require_source AND pg_catalog.jsonb_array_length(p_source_refs) = 0) THEN
    RAISE EXCEPTION 'alert source references are invalid'
      USING ERRCODE = '22023';
  END IF;

  FOR ref IN SELECT value FROM pg_catalog.jsonb_array_elements(p_source_refs)
  LOOP
    IF pg_catalog.jsonb_typeof(ref) IS DISTINCT FROM 'object'
      OR ref->>'target_schema_name' IS NULL
      OR ref->>'target_schema_name' !~ '^qc2\.[A-Za-z0-9_.-]+\.v[1-9][0-9]*$'
      OR ref->>'target_id' !~
        '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(ref) AS keys(key)
        WHERE keys.key NOT IN ('target_schema_name','target_id','content_hash')
      )
      OR (
        ref ? 'content_hash'
        AND ref->>'content_hash' !~ '^[0-9a-f]{64}$'
      ) THEN
      RAISE EXCEPTION 'alert source reference is invalid'
        USING ERRCODE = '22023';
    END IF;
  END LOOP;

  FOR ref IN SELECT value FROM pg_catalog.jsonb_array_elements(p_evidence_refs)
  LOOP
    IF pg_catalog.jsonb_typeof(ref) IS DISTINCT FROM 'object'
      OR ref->>'target_schema_name' IS DISTINCT FROM 'qc2.integrity_build.EvidenceEvent.v1'
      OR ref->>'target_id' !~
        '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
      OR ref->>'content_hash' !~ '^[0-9a-f]{64}$'
      OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(ref) AS keys(key)
        WHERE keys.key NOT IN ('target_schema_name','target_id','content_hash')
      ) THEN
      RAISE EXCEPTION 'alert evidence reference is invalid'
        USING ERRCODE = '22023';
    END IF;
  END LOOP;
END
$function$;

CREATE FUNCTION qc2_alerts.prevent_alert_contract_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  IF ROW(
    NEW.id, NEW.environment_namespace, NEW.rule_key, NEW.dedupe_key,
    NEW.alert_contract, NEW.created_at
  ) IS DISTINCT FROM ROW(
    OLD.id, OLD.environment_namespace, OLD.rule_key, OLD.dedupe_key,
    OLD.alert_contract, OLD.created_at
  ) THEN
    RAISE EXCEPTION 'alert identity and source contract are immutable'
      USING ERRCODE = '42501';
  END IF;
  IF NEW.state = 'RESOLVED' AND OLD.state <> 'OPEN' THEN
    RAISE EXCEPTION 'resolved alerts cannot transition again'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END
$function$;

CREATE FUNCTION qc2_alerts.prevent_alert_event_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'alert lifecycle events are append-only'
    USING ERRCODE = '42501';
END
$function$;

CREATE TRIGGER alert_contract_identity_is_immutable
BEFORE UPDATE ON qc2_alerts.alert_instance
FOR EACH ROW EXECUTE FUNCTION qc2_alerts.prevent_alert_contract_rewrite();
CREATE TRIGGER alert_event_append_only
BEFORE UPDATE OR DELETE ON qc2_alerts.alert_event
FOR EACH ROW EXECUTE FUNCTION qc2_alerts.prevent_alert_event_rewrite();
CREATE TRIGGER alert_event_no_truncate
BEFORE TRUNCATE ON qc2_alerts.alert_event
FOR EACH STATEMENT EXECUTE FUNCTION qc2_alerts.prevent_alert_event_rewrite();
CREATE TRIGGER alert_delivery_append_only
BEFORE UPDATE OR DELETE ON qc2_alerts.delivery_payload
FOR EACH ROW EXECUTE FUNCTION qc2_alerts.prevent_alert_event_rewrite();
CREATE TRIGGER alert_delivery_no_truncate
BEFORE TRUNCATE ON qc2_alerts.delivery_payload
FOR EACH STATEMENT EXECUTE FUNCTION qc2_alerts.prevent_alert_event_rewrite();

CREATE FUNCTION qc2_alerts.enqueue_alert_event(
  p_alert_id uuid,
  p_event_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  alert_row qc2_alerts.alert_instance%ROWTYPE;
  rule_row qc2_alerts.alert_rule%ROWTYPE;
  event_row qc2_alerts.alert_event%ROWTYPE;
  message_id uuid;
  notification_payload jsonb;
  local_payload_hash text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  SELECT * INTO alert_row
    FROM qc2_alerts.alert_instance
    WHERE id = p_alert_id;
  SELECT * INTO rule_row
    FROM qc2_alerts.alert_rule
    WHERE rule_key = alert_row.rule_key;
  SELECT * INTO event_row
    FROM qc2_alerts.alert_event
    WHERE id = p_event_id AND alert_id = p_alert_id;
  IF NOT FOUND OR alert_row.id IS NULL OR rule_row.rule_key IS NULL THEN
    RAISE EXCEPTION 'alert event cannot be queued'
      USING ERRCODE = '23503';
  END IF;

  notification_payload := pg_catalog.jsonb_build_object(
    'payload_type', 'alert_notification',
    'event_id', event_row.id::text,
    'event_type', event_row.event_type,
    'alert_id', alert_row.id::text,
    'alert_type', rule_row.alert_type,
    'severity', event_row.to_severity,
    'trigger_rule', rule_row.rule_key,
    'dedupe_key', alert_row.dedupe_key,
    'escalation_policy', rule_row.escalation_policy,
    'action_owner', rule_row.action_owner,
    'readiness_effect', rule_row.readiness_effect,
    'source_refs', event_row.source_refs,
    'evidence_refs', event_row.evidence_refs,
    'created_at', event_row.created_at
  );
  local_payload_hash := qc2_integrity_build.hash_json(
    'qc2.alert.notification.v1', notification_payload
  );
  message_id := qc2_integrity_build.new_uuid_v7();

  INSERT INTO qc2_control.outbox_message(
    id, logical_operation_id, owner_authority, message_type, payload_hash
  )
  VALUES (
    message_id, event_row.id, 'alert', 'alert_notification', local_payload_hash
  )
  ON CONFLICT (logical_operation_id) DO NOTHING;

  IF NOT EXISTS (
    SELECT 1 FROM qc2_control.outbox_message AS message
    WHERE message.logical_operation_id = event_row.id
      AND message.owner_authority = 'alert'
      AND message.message_type = 'alert_notification'
      AND message.payload_hash = local_payload_hash
  ) THEN
    RAISE EXCEPTION 'alert notification operation conflicts with existing content'
      USING ERRCODE = '23505';
  END IF;

  SELECT message.id INTO message_id
    FROM qc2_control.outbox_message AS message
    WHERE message.logical_operation_id = event_row.id;
  INSERT INTO qc2_alerts.delivery_payload(
    outbox_message_id, alert_id, event_id, environment_namespace, payload
  )
  VALUES (
    message_id, alert_row.id, event_row.id,
    alert_row.environment_namespace, notification_payload
  );
  RETURN message_id;
END
$function$;

CREATE FUNCTION qc2_alerts.raise_alert(
  p_environment_namespace text,
  p_rule_key text,
  p_dedupe_key text,
  p_source_severity text,
  p_source_refs jsonb,
  p_evidence_refs jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  rule_row qc2_alerts.alert_rule%ROWTYPE;
  alert_row qc2_alerts.alert_instance%ROWTYPE;
  alert_id uuid;
  event_id uuid;
  delivery_id uuid;
  event_time timestamptz;
  alert_document jsonb;
  inserted boolean;
  previous_severity text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  IF p_environment_namespace IS NULL
    OR p_environment_namespace NOT IN ('development','test','research','production')
    OR p_rule_key IS NULL
    OR p_rule_key !~ '^[a-z][a-z0-9_-]{0,95}$'
    OR p_dedupe_key IS NULL
    OR p_dedupe_key !~ '^[a-z][a-z0-9_-]{0,95}$'
    OR qc2_alerts.severity_rank(p_source_severity) IS NULL THEN
    RAISE EXCEPTION 'alert trigger input is invalid'
      USING ERRCODE = '22023';
  END IF;
  PERFORM qc2_alerts.assert_references(
    p_source_refs, p_evidence_refs, true
  );

  SELECT * INTO rule_row
    FROM qc2_alerts.alert_rule
    WHERE rule_key = p_rule_key AND enabled;
  IF NOT FOUND
    OR qc2_alerts.severity_rank(p_source_severity)
       < qc2_alerts.severity_rank(rule_row.base_severity)
    OR (
      rule_row.escalation_policy = 'manual_only'
      AND p_source_severity <> rule_row.base_severity
    ) THEN
    RAISE EXCEPTION 'alert trigger does not match the registered rule'
      USING ERRCODE = '42501';
  END IF;

  event_time := pg_catalog.clock_timestamp();
  alert_id := qc2_integrity_build.new_uuid_v7();
  alert_document := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.governance_owner.Alert.v1',
    'schema_version', '1.0',
    'id', alert_id::text,
    'created_at', event_time,
    'owning_authority', 'alert',
    'evidence_class', CASE p_environment_namespace
      WHEN 'production' THEN 'FORWARD_OPERATIONAL'
      ELSE 'SYNTHETIC_FIXTURE'
    END,
    'environment_namespace', p_environment_namespace,
    'source_refs', p_source_refs,
    'alert_type', rule_row.alert_type,
    'severity', p_source_severity,
    'trigger_rule', rule_row.rule_key,
    'dedupe_key', p_dedupe_key,
    'escalation_policy', rule_row.escalation_policy,
    'action_owner', rule_row.action_owner,
    'auto_resolution_condition', rule_row.auto_resolution_condition,
    'readiness_effect', rule_row.readiness_effect,
    'acknowledged_at', NULL,
    'resolved_at', NULL,
    'evidence_refs', p_evidence_refs
  );

  INSERT INTO qc2_alerts.alert_instance(
    id, environment_namespace, rule_key, dedupe_key, current_severity,
    alert_contract, created_at, last_triggered_at, updated_at
  )
  VALUES (
    alert_id, p_environment_namespace, p_rule_key, p_dedupe_key,
    p_source_severity, alert_document, event_time, event_time, event_time
  )
  ON CONFLICT (environment_namespace, rule_key, dedupe_key)
    WHERE state = 'OPEN'
    DO NOTHING
  RETURNING * INTO alert_row;
  inserted := FOUND;

  IF inserted THEN
    event_id := qc2_integrity_build.new_uuid_v7();
    INSERT INTO qc2_alerts.alert_event(
      id, alert_id, event_type, from_severity, to_severity,
      source_refs, evidence_refs, created_at
    )
    VALUES (
      event_id, alert_row.id, 'TRIGGERED', NULL, p_source_severity,
      p_source_refs, p_evidence_refs, event_time
    );
    delivery_id := qc2_alerts.enqueue_alert_event(alert_row.id, event_id);
    RETURN pg_catalog.jsonb_build_object(
      'status', 'CREATED',
      'alert_id', alert_row.id,
      'severity', alert_row.current_severity,
      'event_id', event_id,
      'delivery_id', delivery_id
    );
  END IF;

  SELECT * INTO alert_row
    FROM qc2_alerts.alert_instance
    WHERE environment_namespace = p_environment_namespace
      AND rule_key = p_rule_key
      AND dedupe_key = p_dedupe_key
      AND state = 'OPEN'
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'active alert disappeared during deduplication'
      USING ERRCODE = '40001';
  END IF;
  previous_severity := alert_row.current_severity;

  IF qc2_alerts.severity_rank(p_source_severity)
       > qc2_alerts.severity_rank(previous_severity)
    AND rule_row.escalation_policy = 'monotonic_source_severity' THEN
    UPDATE qc2_alerts.alert_instance
      SET current_severity = p_source_severity,
          trigger_count = trigger_count + 1,
          last_triggered_at = event_time,
          updated_at = event_time
      WHERE id = alert_row.id
      RETURNING * INTO alert_row;
    event_id := qc2_integrity_build.new_uuid_v7();
    INSERT INTO qc2_alerts.alert_event(
      id, alert_id, event_type, from_severity, to_severity,
      source_refs, evidence_refs, created_at
    )
    VALUES (
      event_id, alert_row.id, 'ESCALATED', previous_severity,
      p_source_severity, p_source_refs, p_evidence_refs, event_time
    );
    delivery_id := qc2_alerts.enqueue_alert_event(alert_row.id, event_id);
    RETURN pg_catalog.jsonb_build_object(
      'status', 'ESCALATED',
      'alert_id', alert_row.id,
      'severity', alert_row.current_severity,
      'event_id', event_id,
      'delivery_id', delivery_id
    );
  END IF;

  UPDATE qc2_alerts.alert_instance
    SET trigger_count = trigger_count + 1,
        last_triggered_at = event_time,
        updated_at = event_time
    WHERE id = alert_row.id
    RETURNING * INTO alert_row;
  RETURN pg_catalog.jsonb_build_object(
    'status', 'DEDUPLICATED',
    'alert_id', alert_row.id,
    'severity', alert_row.current_severity,
    'trigger_count', alert_row.trigger_count
  );
END
$function$;

CREATE FUNCTION qc2_alerts.acknowledge_alert(p_alert_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  alert_row qc2_alerts.alert_instance%ROWTYPE;
  event_id uuid;
  delivery_id uuid;
  event_time timestamptz;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  SELECT * INTO alert_row
    FROM qc2_alerts.alert_instance
    WHERE id = p_alert_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'alert does not exist'
      USING ERRCODE = '23503';
  END IF;
  IF alert_row.state = 'RESOLVED' THEN
    RETURN pg_catalog.jsonb_build_object(
      'status', 'ALREADY_RESOLVED', 'alert_id', alert_row.id
    );
  END IF;
  IF alert_row.acknowledged_at IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'status', 'ALREADY_ACKNOWLEDGED', 'alert_id', alert_row.id
    );
  END IF;

  event_time := pg_catalog.clock_timestamp();
  UPDATE qc2_alerts.alert_instance
    SET acknowledged_at = event_time, updated_at = event_time
    WHERE id = alert_row.id
    RETURNING * INTO alert_row;
  event_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_alerts.alert_event(
    id, alert_id, event_type, from_severity, to_severity,
    source_refs, evidence_refs, created_at
  )
  VALUES (
    event_id, alert_row.id, 'ACKNOWLEDGED', alert_row.current_severity,
    alert_row.current_severity, '[]'::jsonb, '[]'::jsonb, event_time
  );
  delivery_id := qc2_alerts.enqueue_alert_event(alert_row.id, event_id);
  RETURN pg_catalog.jsonb_build_object(
    'status', 'ACKNOWLEDGED',
    'alert_id', alert_row.id,
    'acknowledged_at', alert_row.acknowledged_at,
    'resolved_at', alert_row.resolved_at,
    'delivery_id', delivery_id
  );
END
$function$;

CREATE FUNCTION qc2_alerts.resolve_alert_auto(
  p_alert_id uuid,
  p_condition text,
  p_source_refs jsonb,
  p_evidence_refs jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  alert_row qc2_alerts.alert_instance%ROWTYPE;
  rule_row qc2_alerts.alert_rule%ROWTYPE;
  event_id uuid;
  delivery_id uuid;
  event_time timestamptz;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  PERFORM qc2_alerts.assert_references(
    p_source_refs, p_evidence_refs, true
  );
  SELECT * INTO alert_row
    FROM qc2_alerts.alert_instance
    WHERE id = p_alert_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'alert does not exist'
      USING ERRCODE = '23503';
  END IF;
  IF alert_row.state = 'RESOLVED' THEN
    RETURN pg_catalog.jsonb_build_object(
      'status', 'ALREADY_RESOLVED', 'alert_id', alert_row.id
    );
  END IF;
  SELECT * INTO rule_row
    FROM qc2_alerts.alert_rule
    WHERE rule_key = alert_row.rule_key;
  IF rule_row.escalation_policy = 'manual_only'
    OR p_condition IS DISTINCT FROM rule_row.auto_resolution_condition THEN
    RAISE EXCEPTION 'automatic resolution condition is not authorized'
      USING ERRCODE = '42501';
  END IF;

  event_time := pg_catalog.clock_timestamp();
  UPDATE qc2_alerts.alert_instance
    SET state = 'RESOLVED',
        resolved_at = event_time,
        resolution_kind = 'AUTO',
        resolution_code = 'condition_met',
        updated_at = event_time
    WHERE id = alert_row.id
    RETURNING * INTO alert_row;
  event_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_alerts.alert_event(
    id, alert_id, event_type, from_severity, to_severity,
    source_refs, evidence_refs, resolution_code, created_at
  )
  VALUES (
    event_id, alert_row.id, 'AUTO_RESOLVED', alert_row.current_severity,
    alert_row.current_severity, p_source_refs, p_evidence_refs,
    'condition_met', event_time
  );
  delivery_id := qc2_alerts.enqueue_alert_event(alert_row.id, event_id);
  RETURN pg_catalog.jsonb_build_object(
    'status', 'RESOLVED',
    'resolution_kind', 'AUTO',
    'alert_id', alert_row.id,
    'acknowledged_at', alert_row.acknowledged_at,
    'resolved_at', alert_row.resolved_at,
    'delivery_id', delivery_id
  );
END
$function$;

CREATE FUNCTION qc2_alerts.resolve_alert_manual(
  p_alert_id uuid,
  p_reason_code text,
  p_source_refs jsonb,
  p_evidence_refs jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control, qc2_integrity_build
AS $function$
DECLARE
  alert_row qc2_alerts.alert_instance%ROWTYPE;
  event_id uuid;
  delivery_id uuid;
  event_time timestamptz;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  PERFORM qc2_alerts.assert_references(
    p_source_refs, p_evidence_refs, true
  );
  IF p_reason_code IS NULL
    OR p_reason_code !~ '^[a-z][a-z0-9_-]{0,95}$' THEN
    RAISE EXCEPTION 'manual resolution reason is invalid'
      USING ERRCODE = '22023';
  END IF;
  SELECT * INTO alert_row
    FROM qc2_alerts.alert_instance
    WHERE id = p_alert_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'alert does not exist'
      USING ERRCODE = '23503';
  END IF;
  IF alert_row.state = 'RESOLVED' THEN
    RETURN pg_catalog.jsonb_build_object(
      'status', 'ALREADY_RESOLVED', 'alert_id', alert_row.id
    );
  END IF;

  event_time := pg_catalog.clock_timestamp();
  UPDATE qc2_alerts.alert_instance
    SET state = 'RESOLVED',
        resolved_at = event_time,
        resolution_kind = 'MANUAL',
        resolution_code = p_reason_code,
        updated_at = event_time
    WHERE id = alert_row.id
    RETURNING * INTO alert_row;
  event_id := qc2_integrity_build.new_uuid_v7();
  INSERT INTO qc2_alerts.alert_event(
    id, alert_id, event_type, from_severity, to_severity,
    source_refs, evidence_refs, resolution_code, created_at
  )
  VALUES (
    event_id, alert_row.id, 'MANUAL_RESOLVED', alert_row.current_severity,
    alert_row.current_severity, p_source_refs, p_evidence_refs,
    p_reason_code, event_time
  );
  delivery_id := qc2_alerts.enqueue_alert_event(alert_row.id, event_id);
  RETURN pg_catalog.jsonb_build_object(
    'status', 'RESOLVED',
    'resolution_kind', 'MANUAL',
    'alert_id', alert_row.id,
    'acknowledged_at', alert_row.acknowledged_at,
    'resolved_at', alert_row.resolved_at,
    'delivery_id', delivery_id
  );
END
$function$;

CREATE FUNCTION qc2_alerts.list_alerts(p_environment_namespace text)
RETURNS TABLE(
  alert jsonb,
  lifecycle_state text,
  current_severity text,
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  trigger_count bigint,
  last_triggered_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  IF p_environment_namespace NOT IN ('development','test','research','production') THEN
    RAISE EXCEPTION 'alert environment is invalid'
      USING ERRCODE = '22023';
  END IF;
  RETURN QUERY
  SELECT
    instance.alert_contract,
    instance.state,
    instance.current_severity,
    instance.acknowledged_at,
    instance.resolved_at,
    instance.trigger_count,
    instance.last_triggered_at
  FROM qc2_alerts.alert_instance AS instance
  WHERE instance.environment_namespace = p_environment_namespace
  ORDER BY instance.created_at, instance.id;
END
$function$;

CREATE FUNCTION qc2_alerts.get_notification_payload(p_outbox_message_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('durable_job_service');
  RETURN (
    SELECT payload.payload
    FROM qc2_alerts.delivery_payload AS payload
    WHERE payload.outbox_message_id = p_outbox_message_id
  );
END
$function$;

CREATE FUNCTION qc2_alerts.delivery_status(p_environment_namespace text)
RETURNS TABLE(
  alert_id uuid,
  event_id uuid,
  outbox_message_id uuid,
  event_type text,
  outbox_status text,
  attempt_count integer,
  next_attempt_at timestamptz,
  lease_expires_at timestamptz,
  is_stale boolean,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, qc2_alerts, qc2_control
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('alert');
  IF p_environment_namespace NOT IN ('development','test','research','production') THEN
    RAISE EXCEPTION 'alert environment is invalid'
      USING ERRCODE = '22023';
  END IF;
  RETURN QUERY
  SELECT
    payload.alert_id,
    payload.event_id,
    message.id,
    event.event_type,
    message.status,
    message.attempt_count,
    message.next_attempt_at,
    message.lease_expires_at,
    (
      message.status = 'FAILED'
      OR (
        message.status = 'UNKNOWN'
        AND (
          message.next_attempt_at IS NULL
          OR message.next_attempt_at <= pg_catalog.clock_timestamp()
        )
      )
      OR (
        message.status = 'PUBLISHING'
        AND message.lease_expires_at <= pg_catalog.clock_timestamp()
      )
    ),
    payload.created_at
  FROM qc2_alerts.delivery_payload AS payload
  JOIN qc2_control.outbox_message AS message
    ON message.id = payload.outbox_message_id
  JOIN qc2_alerts.alert_event AS event
    ON event.id = payload.event_id
  WHERE payload.environment_namespace = p_environment_namespace
  ORDER BY payload.created_at, payload.outbox_message_id;
END
$function$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qc2_alerts FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qc2_alerts.raise_alert(
  text, text, text, text, jsonb, jsonb
),
qc2_alerts.acknowledge_alert(uuid),
qc2_alerts.resolve_alert_auto(uuid, text, jsonb, jsonb),
qc2_alerts.resolve_alert_manual(uuid, text, jsonb, jsonb),
qc2_alerts.list_alerts(text),
qc2_alerts.delivery_status(text)
TO qc2_runtime_alert;
GRANT EXECUTE ON FUNCTION qc2_alerts.get_notification_payload(uuid)
TO qc2_runtime_durable_job_service;

RESET ROLE;
