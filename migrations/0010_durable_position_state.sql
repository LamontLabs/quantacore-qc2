-- QC2-048: append-only broker facts with deterministic, episode-scoped state.
SET ROLE qc2_migrator;

CREATE TABLE qc2_execution.execution_episode_state (
  episode_id uuid PRIMARY KEY CHECK (
    episode_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  episode_hash text NOT NULL CHECK (episode_hash ~ '^[0-9a-f]{64}$'),
  paper_account_fingerprint text NOT NULL
    CHECK (paper_account_fingerprint ~ '^[0-9a-f]{64}$'),
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  opening_cash numeric(38, 12) NOT NULL,
  opened_at timestamptz NOT NULL,
  episode_contract jsonb NOT NULL
    CHECK (pg_catalog.jsonb_typeof(episode_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.position_state_broker_order (
  order_id uuid PRIMARY KEY CHECK (
    order_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  intent_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  broker_order_id text NOT NULL CHECK (length(broker_order_id) BETWEEN 1 AND 256),
  instrument_id uuid NOT NULL,
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  order_quantity numeric(38, 12) NOT NULL CHECK (order_quantity > 0),
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  order_contract jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(order_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (episode_id, broker_order_id),
  UNIQUE (intent_id, order_id)
);

CREATE TABLE qc2_execution.position_state_broker_event (
  event_id uuid PRIMARY KEY CHECK (
    event_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  order_id uuid NOT NULL
    REFERENCES qc2_execution.position_state_broker_order(order_id) ON DELETE RESTRICT,
  provider_event_id text NOT NULL CHECK (length(provider_event_id) BETWEEN 1 AND 256),
  event_type text NOT NULL CHECK (event_type IN (
    'ACCEPTED','PARTIAL_FILL','FILL','CANCEL_REQUEST','CANCELLED',
    'REJECTED','EXPIRED','CORRECTION'
  )),
  event_sequence bigint NOT NULL CHECK (event_sequence >= 0),
  event_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL,
  event_payload_hash text NOT NULL CHECK (event_payload_hash ~ '^[0-9a-f]{64}$'),
  event_contract jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(event_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE INDEX position_state_broker_event_sequence_idx
  ON qc2_execution.position_state_broker_event(order_id, event_sequence, event_id);

CREATE TABLE qc2_execution.position_state_fill (
  fill_id uuid PRIMARY KEY CHECK (
    fill_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  order_id uuid NOT NULL
    REFERENCES qc2_execution.position_state_broker_order(order_id) ON DELETE RESTRICT,
  provider_fill_id text NOT NULL CHECK (length(provider_fill_id) BETWEEN 1 AND 256),
  provider_payload_hash text NOT NULL CHECK (provider_payload_hash ~ '^[0-9a-f]{64}$'),
  instrument_id uuid NOT NULL,
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  quantity numeric(38, 12) NOT NULL CHECK (quantity > 0),
  price numeric(38, 12) NOT NULL CHECK (price > 0),
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  filled_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL,
  fill_contract jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(fill_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (order_id, provider_fill_id, provider_payload_hash)
);

CREATE INDEX position_state_fill_episode_idx
  ON qc2_execution.position_state_fill(order_id, filled_at, provider_fill_id);

CREATE TABLE qc2_execution.position_state_fill_correction (
  correction_id uuid PRIMARY KEY CHECK (
    correction_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  fill_id uuid NOT NULL
    REFERENCES qc2_execution.position_state_fill(fill_id) ON DELETE RESTRICT,
  source_event_id uuid NOT NULL
    REFERENCES qc2_execution.position_state_broker_event(event_id) ON DELETE RESTRICT,
  correction_kind text NOT NULL CHECK (correction_kind IN (
    'BUST','QUANTITY_ADJUSTMENT','PRICE_ADJUSTMENT','FEE_ADJUSTMENT'
  )),
  quantity_delta numeric(38, 12) NOT NULL,
  price_delta numeric(38, 12) NOT NULL,
  reason_code text NOT NULL CHECK (reason_code ~ '^[a-z][a-z0-9_-]{0,95}$'),
  corrected_at timestamptz NOT NULL,
  correction_contract jsonb NOT NULL
    CHECK (pg_catalog.jsonb_typeof(correction_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.position_state_cash_ledger (
  cash_entry_id uuid PRIMARY KEY CHECK (
    cash_entry_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  entry_sequence bigint GENERATED ALWAYS AS IDENTITY,
  entry_kind text NOT NULL CHECK (entry_kind IN (
    'FILL','FEE','CORPORATE_ACTION','MANUAL_ADJUSTMENT'
  )),
  amount numeric(38, 12) NOT NULL,
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  effective_at timestamptz NOT NULL,
  source_schema_name text NOT NULL CHECK (length(source_schema_name) BETWEEN 1 AND 160),
  source_id uuid NOT NULL,
  balance_after numeric(38, 12) NOT NULL,
  cash_contract jsonb CHECK (
    cash_contract IS NULL OR pg_catalog.jsonb_typeof(cash_contract) = 'object'
  ),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (episode_id, source_schema_name, source_id, entry_kind),
  UNIQUE (episode_id, entry_sequence)
);

CREATE TABLE qc2_execution.position_state_corporate_action (
  adjustment_id uuid PRIMARY KEY CHECK (
    adjustment_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  corporate_action_id uuid NOT NULL,
  instrument_id uuid NOT NULL,
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  effective_at timestamptz NOT NULL,
  share_ratio numeric(38, 12) NOT NULL CHECK (share_ratio > 0),
  cash_per_share numeric(38, 12) NOT NULL CHECK (cash_per_share >= 0),
  adjustment_contract jsonb NOT NULL
    CHECK (pg_catalog.jsonb_typeof(adjustment_contract) = 'object'),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (episode_id, adjustment_id)
);

CREATE TABLE qc2_execution.position_state_position_projection (
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  instrument_id uuid NOT NULL,
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  quantity numeric(38, 12) NOT NULL CHECK (quantity > 0),
  average_cost numeric(38, 12) NOT NULL CHECK (average_cost > 0),
  as_of timestamptz NOT NULL,
  reconciliation_status text NOT NULL CHECK (reconciliation_status IN (
    'RECONCILED','DISCREPANCY','UNKNOWN','HOLD'
  )),
  source_fill_refs jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(source_fill_refs) = 'array'),
  corporate_action_refs jsonb NOT NULL
    CHECK (pg_catalog.jsonb_typeof(corporate_action_refs) = 'array'),
  position_contract jsonb NOT NULL
    CHECK (pg_catalog.jsonb_typeof(position_contract) = 'object'),
  projection_hash text NOT NULL CHECK (projection_hash ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (episode_id, instrument_id, currency)
);

CREATE TABLE qc2_execution.position_state_cash_projection (
  episode_id uuid NOT NULL
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  balance numeric(38, 12) NOT NULL,
  reconciliation_status text NOT NULL CHECK (reconciliation_status IN (
    'RECONCILED','DISCREPANCY','UNKNOWN','HOLD'
  )),
  projection_hash text NOT NULL CHECK (projection_hash ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  PRIMARY KEY (episode_id, currency)
);

CREATE TABLE qc2_execution.position_state_projection_control (
  episode_id uuid PRIMARY KEY
    REFERENCES qc2_execution.execution_episode_state(episode_id) ON DELETE RESTRICT,
  reconciliation_status text NOT NULL DEFAULT 'UNKNOWN' CHECK (reconciliation_status IN (
    'RECONCILED','DISCREPANCY','UNKNOWN','HOLD'
  )),
  hold_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (pg_catalog.jsonb_typeof(hold_reasons) = 'array'),
  projection_hash text CHECK (
    projection_hash IS NULL OR projection_hash ~ '^[0-9a-f]{64}$'
  ),
  generation bigint NOT NULL DEFAULT 0 CHECK (generation >= 0),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE qc2_execution.position_state_reservation_settlement (
  settlement_id uuid PRIMARY KEY CHECK (
    settlement_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  intent_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent(id) ON DELETE RESTRICT,
  reservation_id uuid NOT NULL
    REFERENCES qc2_execution.paper_order_intent_reservation(id) ON DELETE RESTRICT,
  source_id uuid NOT NULL,
  previous_amount numeric(38, 12) NOT NULL CHECK (previous_amount >= 0),
  remaining_amount numeric(38, 12) NOT NULL CHECK (remaining_amount >= 0),
  settlement_state text NOT NULL CHECK (settlement_state IN (
    'PARTIALLY_CONSUMED','SETTLED','RELEASED','HELD'
  )),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  UNIQUE (intent_id, source_id)
);

CREATE FUNCTION qc2_execution.reject_position_state_ledger_rewrite()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'QC2 position-state ledger rows are append-only'
    USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER execution_episode_state_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.execution_episode_state
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_broker_order_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_broker_order
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_broker_event_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_broker_event
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_fill_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_fill
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_fill_correction_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_fill_correction
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_cash_ledger_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_cash_ledger
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_corporate_action_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_corporate_action
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();
CREATE TRIGGER position_state_reservation_settlement_immutable
  BEFORE UPDATE OR DELETE ON qc2_execution.position_state_reservation_settlement
  FOR EACH ROW EXECUTE FUNCTION qc2_execution.reject_position_state_ledger_rewrite();

DO $rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'execution_episode_state',
    'position_state_broker_order',
    'position_state_broker_event',
    'position_state_fill',
    'position_state_fill_correction',
    'position_state_cash_ledger',
    'position_state_corporate_action',
    'position_state_position_projection',
    'position_state_cash_projection',
    'position_state_projection_control',
    'position_state_reservation_settlement'
  ] LOOP
    EXECUTE pg_catalog.format(
      'ALTER TABLE qc2_execution.%I ENABLE ROW LEVEL SECURITY', table_name
    );
    EXECUTE pg_catalog.format(
      'ALTER TABLE qc2_execution.%I FORCE ROW LEVEL SECURITY', table_name
    );
    EXECUTE pg_catalog.format(
      'CREATE POLICY %I ON qc2_execution.%I FOR ALL TO qc2_migrator USING (true) WITH CHECK (true)',
      table_name || '_migrator_all', table_name
    );
    EXECUTE pg_catalog.format(
      'CREATE POLICY %I ON qc2_execution.%I FOR SELECT TO qc2_runtime_execution USING (qc2_control.current_runtime_authority() = %L)',
      table_name || '_runtime_read', table_name, 'execution'
    );
  END LOOP;
END
$rls$;

REVOKE ALL ON qc2_execution.execution_episode_state,
  qc2_execution.position_state_broker_order,
  qc2_execution.position_state_broker_event,
  qc2_execution.position_state_fill,
  qc2_execution.position_state_fill_correction,
  qc2_execution.position_state_cash_ledger,
  qc2_execution.position_state_corporate_action,
  qc2_execution.position_state_position_projection,
  qc2_execution.position_state_cash_projection,
  qc2_execution.position_state_projection_control,
  qc2_execution.position_state_reservation_settlement
FROM PUBLIC, qc2_runtime_execution;
GRANT SELECT ON qc2_execution.execution_episode_state,
  qc2_execution.position_state_broker_order,
  qc2_execution.position_state_broker_event,
  qc2_execution.position_state_fill,
  qc2_execution.position_state_fill_correction,
  qc2_execution.position_state_cash_ledger,
  qc2_execution.position_state_corporate_action,
  qc2_execution.position_state_position_projection,
  qc2_execution.position_state_cash_projection,
  qc2_execution.position_state_projection_control,
  qc2_execution.position_state_reservation_settlement
TO qc2_runtime_execution;

CREATE FUNCTION qc2_control.hold_execution_position_state(
  p_episode_id uuid,
  p_reason text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution
AS $function$
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF p_reason IS NULL OR p_reason !~ '^[a-z][a-z0-9:_-]{0,159}$' THEN
    RAISE EXCEPTION 'position-state hold reason is invalid'
      USING ERRCODE = '22023';
  END IF;
  INSERT INTO qc2_execution.position_state_projection_control(
    episode_id, reconciliation_status, hold_reasons, generation
  )
  VALUES (p_episode_id, 'HOLD', pg_catalog.jsonb_build_array(p_reason), 1)
  ON CONFLICT (episode_id) DO UPDATE
    SET reconciliation_status = 'HOLD',
        hold_reasons = CASE
          WHEN qc2_execution.position_state_projection_control.hold_reasons
                 @> pg_catalog.jsonb_build_array(p_reason)
            THEN qc2_execution.position_state_projection_control.hold_reasons
          ELSE qc2_execution.position_state_projection_control.hold_reasons
                 || pg_catalog.jsonb_build_array(p_reason)
        END,
        generation = qc2_execution.position_state_projection_control.generation + 1,
        updated_at = pg_catalog.clock_timestamp();
END
$function$;

CREATE FUNCTION qc2_control.register_execution_episode(
  p_contract jsonb,
  p_opening_positions jsonb DEFAULT '[]'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
<<register_execution_episode>>
DECLARE
  episode_id uuid;
  prior qc2_execution.execution_episode_state%ROWTYPE;
  opening_cash numeric(38,12);
  opening_position jsonb;
  position_id uuid;
  instrument_id uuid;
  position_quantity numeric(38,12);
  average_cost numeric(38,12);
  opening_projection_hash text;
  inserted boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_contract) <> 'object'
     OR p_contract->>'schema_name' <> 'qc2.execution.ExecutionEpisode.v1'
     OR p_contract->>'schema_version' <> '1.0'
     OR p_contract->>'owning_authority' <> 'execution'
     OR p_contract->>'account_mode' <> 'PAPER'
     OR p_contract->>'sealed_at' IS NULL
     OR p_contract->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_contract->>'content_hash' !~ '^[0-9a-f]{64}$'
     OR p_contract->>'episode_hash' !~ '^[0-9a-f]{64}$'
     OR p_contract->>'paper_account_fingerprint' !~ '^[0-9a-f]{64}$'
     OR p_contract->>'currency' !~ '^[A-Z]{3}$'
     OR p_contract->>'opening_cash' !~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$'
     OR pg_catalog.jsonb_typeof(p_contract->'opening_position_refs') <> 'array'
     OR pg_catalog.jsonb_typeof(p_contract->'opening_order_refs') <> 'array'
     OR pg_catalog.jsonb_typeof(p_opening_positions) <> 'array'
     OR pg_catalog.jsonb_array_length(p_contract->'opening_position_refs')
          <> pg_catalog.jsonb_array_length(p_opening_positions) THEN
    RAISE EXCEPTION 'execution episode contract is invalid'
      USING ERRCODE = '23514';
  END IF;
  episode_id := (p_contract->>'id')::uuid;
  opening_cash := (p_contract->>'opening_cash')::numeric;
  INSERT INTO qc2_execution.execution_episode_state(
    episode_id, content_hash, episode_hash, paper_account_fingerprint,
    currency, opening_cash, opened_at, episode_contract
  )
  VALUES (
    episode_id, p_contract->>'content_hash', p_contract->>'episode_hash',
    p_contract->>'paper_account_fingerprint', p_contract->>'currency',
    opening_cash, (p_contract->>'opened_at')::timestamptz, p_contract
  )
  ON CONFLICT ON CONSTRAINT execution_episode_state_pkey DO NOTHING;
  inserted := FOUND;
  SELECT state_row.* INTO prior
    FROM qc2_execution.execution_episode_state AS state_row
    WHERE state_row.episode_id = register_execution_episode.episode_id;
  IF prior.episode_contract IS DISTINCT FROM p_contract THEN
    RAISE EXCEPTION 'execution episode identity was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  INSERT INTO qc2_execution.position_state_projection_control(episode_id)
  VALUES (episode_id)
  ON CONFLICT ON CONSTRAINT position_state_projection_control_pkey DO NOTHING;
  IF inserted THEN
    FOR opening_position IN
      SELECT items.value
      FROM pg_catalog.jsonb_array_elements(p_opening_positions) AS items(value)
    LOOP
      IF opening_position->>'schema_name' <> 'qc2.execution.Position.v1'
         OR opening_position->>'schema_version' <> '1.0'
         OR opening_position->>'owning_authority' <> 'execution'
         OR opening_position->'episode_ref'->>'target_id' <> episode_id::text
         OR opening_position->'episode_ref'->>'content_hash'
              <> p_contract->>'content_hash'
         OR opening_position->>'currency' <> p_contract->>'currency'
         OR opening_position->'instrument_ref'->>'target_id' IS NULL
         OR opening_position->>'quantity' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
         OR opening_position->>'average_cost' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
         OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(
             p_contract->'opening_position_refs'
           ) AS refs(value)
           WHERE refs.value->>'target_schema_name' =
               'qc2.execution.Position.v1'
             AND refs.value->>'target_id' = opening_position->>'id'
         ) THEN
        RAISE EXCEPTION 'opening position does not match its execution episode'
          USING ERRCODE = '23514';
      END IF;
      position_id := (opening_position->>'id')::uuid;
      instrument_id :=
        (opening_position->'instrument_ref'->>'target_id')::uuid;
      position_quantity := (opening_position->>'quantity')::numeric;
      average_cost := (opening_position->>'average_cost')::numeric;
      IF position_quantity <= 0 OR average_cost <= 0
         OR pg_catalog.scale(position_quantity) > 12
         OR pg_catalog.scale(average_cost) > 12 THEN
        RAISE EXCEPTION 'opening position is flat, short, or inexact'
          USING ERRCODE = '23514';
      END IF;
      opening_projection_hash := qc2_integrity_build.hash_json(
        'qc2.execution.position-state.opening-projection.v1',
        opening_position
      );
      INSERT INTO qc2_execution.position_state_position_projection(
        episode_id, instrument_id, currency, quantity, average_cost, as_of,
        reconciliation_status, source_fill_refs, corporate_action_refs,
        position_contract, projection_hash
      )
      VALUES (
        episode_id, instrument_id, opening_position->>'currency',
        position_quantity, average_cost,
        (opening_position->>'as_of')::timestamptz,
        opening_position->>'reconciliation_status',
        opening_position->'source_fill_refs',
        opening_position->'corporate_action_refs',
        opening_position, opening_projection_hash
      );
    END LOOP;
    PERFORM qc2_integrity_build.append_event_internal(
      'execution_episode_registered',
      pg_catalog.jsonb_build_object(
        'episode_id', episode_id::text,
        'episode_hash', p_contract->>'episode_hash',
        'account_fingerprint_hash', p_contract->>'paper_account_fingerprint'
      ),
      0,
      '[]'::jsonb
    );
  END IF;
  RETURN episode_id;
END
$function$;

CREATE FUNCTION qc2_control.register_position_state_broker_order(p_contract jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
<<register_position_state_broker_order>>
DECLARE
  order_id uuid;
  intent_id uuid;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  episode_row qc2_execution.execution_episode_state%ROWTYPE;
  prior qc2_execution.position_state_broker_order%ROWTYPE;
  episode_id uuid;
  instrument_id uuid;
  order_quantity numeric(38,12);
  inserted boolean;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_contract) <> 'object'
     OR p_contract->>'schema_name' <> 'qc2.execution.BrokerOrder.v1'
     OR p_contract->>'schema_version' <> '1.0'
     OR p_contract->>'owning_authority' <> 'execution'
     OR p_contract->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_contract->'intent_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.PaperOrderIntent.v1'
     OR p_contract->'intent_ref'->>'target_id' IS NULL
     OR p_contract->'intent_ref'->>'content_hash' !~ '^[0-9a-f]{64}$'
     OR p_contract->>'broker_order_id' IS NULL
     OR p_contract->>'paper_account_fingerprint' !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'broker order contract is invalid'
      USING ERRCODE = '23514';
  END IF;
  order_id := (p_contract->>'id')::uuid;
  intent_id := (p_contract->'intent_ref'->>'target_id')::uuid;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = intent_id
    FOR SHARE;
  IF NOT FOUND
     OR intent_row.content_hash <> p_contract->'intent_ref'->>'content_hash' THEN
    RAISE EXCEPTION 'broker order intent reference is missing or hash-mismatched'
      USING ERRCODE = '23503';
  END IF;
  IF intent_row.intent_contract->>'account_mode' <> 'PAPER'
     OR intent_row.intent_contract->'episode_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.ExecutionEpisode.v1'
     OR intent_row.intent_contract->'episode_ref'->>'content_hash' IS NULL
     OR intent_row.intent_contract->>'paper_account_fingerprint'
          <> p_contract->>'paper_account_fingerprint' THEN
    RAISE EXCEPTION 'broker order does not match the paper execution intent'
      USING ERRCODE = '23514';
  END IF;
  episode_id := (intent_row.intent_contract->'episode_ref'->>'target_id')::uuid;
  SELECT * INTO episode_row
    FROM qc2_execution.execution_episode_state
    WHERE execution_episode_state.episode_id = register_position_state_broker_order.episode_id
    FOR SHARE;
  IF NOT FOUND
     OR episode_row.content_hash
          <> intent_row.intent_contract->'episode_ref'->>'content_hash'
     OR episode_row.paper_account_fingerprint
          <> p_contract->>'paper_account_fingerprint' THEN
    RAISE EXCEPTION 'execution episode is missing or does not match the intent'
      USING ERRCODE = '23503';
  END IF;
  IF intent_row.intent_contract->>'quantity_whole_shares' !~ '^[1-9][0-9]*$'
     OR intent_row.intent_contract->'instrument_ref'->>'target_id' IS NULL
     OR intent_row.intent_contract->>'side' NOT IN ('BUY','SELL') THEN
    RAISE EXCEPTION 'paper order intent lacks a valid side, quantity, or instrument'
      USING ERRCODE = '23514';
  END IF;
  instrument_id := (intent_row.intent_contract->'instrument_ref'->>'target_id')::uuid;
  order_quantity := (intent_row.intent_contract->>'quantity_whole_shares')::numeric;

  INSERT INTO qc2_execution.position_state_broker_order(
    order_id, episode_id, intent_id, broker_order_id, instrument_id,
    side, order_quantity, currency, order_contract
  )
  VALUES (
    order_id, episode_id, intent_id, p_contract->>'broker_order_id',
    instrument_id, intent_row.intent_contract->>'side', order_quantity,
    episode_row.currency, p_contract
  )
  ON CONFLICT ON CONSTRAINT position_state_broker_order_pkey DO NOTHING;
  inserted := FOUND;
  SELECT state_row.* INTO prior
    FROM qc2_execution.position_state_broker_order AS state_row
    WHERE state_row.order_id = register_position_state_broker_order.order_id;
  IF prior.order_contract IS DISTINCT FROM p_contract THEN
    RAISE EXCEPTION 'broker order identity was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  IF inserted THEN
    PERFORM qc2_integrity_build.append_event_internal(
    'broker_order_state_registered',
    pg_catalog.jsonb_build_object(
      'order_id', order_id::text,
      'intent_id', intent_id::text,
      'episode_id', episode_id::text,
      'broker_order_id_hash', qc2_integrity_build.hash_json(
        'qc2.execution.broker-order-id.v1',
        pg_catalog.jsonb_build_object('broker_order_id', p_contract->>'broker_order_id')
      )
    ),
    0,
    p_contract->'source_refs'
    );
  END IF;
  RETURN order_id;
END
$function$;

CREATE FUNCTION qc2_control.append_position_state_broker_event(p_contract jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
<<append_position_state_broker_event>>
DECLARE
  event_id uuid;
  order_id uuid;
  episode_id uuid;
  prior_event qc2_execution.position_state_broker_event%ROWTYPE;
  identity_conflict boolean := false;
  sequence_conflict boolean;
  event_id_conflict boolean := false;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_contract) <> 'object'
     OR p_contract->>'schema_name' <> 'qc2.execution.BrokerOrderEvent.v1'
     OR p_contract->>'schema_version' <> '1.0'
     OR p_contract->>'owning_authority' <> 'execution'
     OR p_contract->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_contract->'broker_order_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.BrokerOrder.v1'
     OR p_contract->'broker_order_ref'->>'target_id' IS NULL
     OR p_contract->>'provider_event_id' IS NULL
     OR p_contract->>'event_payload_hash' !~ '^[0-9a-f]{64}$'
     OR p_contract->>'event_sequence' !~ '^(0|[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'broker event contract is invalid'
      USING ERRCODE = '23514';
  END IF;
  event_id := (p_contract->>'id')::uuid;
  order_id := (p_contract->'broker_order_ref'->>'target_id')::uuid;
  SELECT ord.episode_id INTO episode_id
    FROM qc2_execution.position_state_broker_order AS ord
    WHERE ord.order_id = append_position_state_broker_event.order_id
    FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'broker event order does not exist'
      USING ERRCODE = '23503';
  END IF;
  SELECT * INTO prior_event
    FROM qc2_execution.position_state_broker_event AS prior_provider_event
    WHERE prior_provider_event.order_id =
      append_position_state_broker_event.order_id
      AND prior_provider_event.provider_event_id = p_contract->>'provider_event_id'
    ORDER BY prior_provider_event.created_at, prior_provider_event.event_id
    LIMIT 1;
  IF FOUND THEN
    IF prior_event.event_payload_hash = p_contract->>'event_payload_hash'
       AND prior_event.event_type = p_contract->>'event_type'
       AND prior_event.event_sequence = (p_contract->>'event_sequence')::bigint
       AND prior_event.event_at = (p_contract->>'event_at')::timestamptz THEN
      RETURN prior_event.event_id;
    END IF;
    identity_conflict := true;
  END IF;
  SELECT * INTO prior_event
    FROM qc2_execution.position_state_broker_event AS prior
    WHERE prior.event_id = append_position_state_broker_event.event_id;
  IF FOUND THEN
    IF prior_event.event_contract = p_contract THEN
      RETURN event_id;
    END IF;
    event_id_conflict := true;
  END IF;
  sequence_conflict := EXISTS (
    SELECT 1
    FROM qc2_execution.position_state_broker_event AS prior
    WHERE prior.order_id = append_position_state_broker_event.order_id
      AND prior.event_sequence = (p_contract->>'event_sequence')::bigint
      AND (
        prior.provider_event_id <> p_contract->>'provider_event_id'
        OR prior.event_payload_hash <> p_contract->>'event_payload_hash'
        OR prior.event_type <> p_contract->>'event_type'
      )
  );
  IF event_id_conflict THEN
    PERFORM qc2_control.hold_execution_position_state(
      episode_id, 'broker_event_record_id_conflict'
    );
    RAISE EXCEPTION 'broker event record ID was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  INSERT INTO qc2_execution.position_state_broker_event(
    event_id, order_id, provider_event_id, event_type, event_sequence,
    event_at, received_at, event_payload_hash, event_contract
  )
  VALUES (
    event_id, order_id, p_contract->>'provider_event_id',
    p_contract->>'event_type', (p_contract->>'event_sequence')::bigint,
    (p_contract->>'event_at')::timestamptz,
    (p_contract->>'received_at')::timestamptz,
    p_contract->>'event_payload_hash', p_contract
  );
  IF identity_conflict THEN
    PERFORM qc2_control.hold_execution_position_state(
      episode_id, 'provider_event_identity_conflict'
    );
  END IF;
  IF sequence_conflict THEN
    PERFORM qc2_control.hold_execution_position_state(
      episode_id, 'provider_event_sequence_conflict'
    );
  END IF;
  PERFORM qc2_integrity_build.append_event_internal(
    'broker_order_event_appended',
    pg_catalog.jsonb_build_object(
      'event_id', event_id::text,
      'order_id', order_id::text,
      'provider_event_id_hash', qc2_integrity_build.hash_json(
        'qc2.execution.provider-event-id.v1',
        pg_catalog.jsonb_build_object('provider_event_id', p_contract->>'provider_event_id')
      ),
      'event_payload_hash', p_contract->>'event_payload_hash',
      'event_sequence', (p_contract->>'event_sequence')::bigint
    ),
    (p_contract->>'event_sequence')::bigint,
    p_contract->'source_refs'
  );
  PERFORM qc2_control.refresh_position_state_reservation(order_id, event_id);
  RETURN event_id;
END
$function$;

CREATE FUNCTION qc2_control.append_position_state_cash_entry(
  p_episode_id uuid,
  p_order_id uuid,
  p_entry_kind text,
  p_amount numeric,
  p_effective_at timestamptz,
  p_source_schema_name text,
  p_source_id uuid,
  p_source_refs jsonb,
  p_evidence_class text,
  p_environment_namespace text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  order_row qc2_execution.position_state_broker_order%ROWTYPE;
  episode_row qc2_execution.execution_episode_state%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  cash_entry_id uuid;
  balance_after numeric(38,12);
  cash_contract jsonb;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO order_row
    FROM qc2_execution.position_state_broker_order
    WHERE position_state_broker_order.order_id = p_order_id;
  IF NOT FOUND OR order_row.episode_id <> p_episode_id THEN
    RAISE EXCEPTION 'cash entry order does not belong to the episode'
      USING ERRCODE = '23503';
  END IF;
  SELECT * INTO episode_row
    FROM qc2_execution.execution_episode_state
    WHERE execution_episode_state.episode_id = p_episode_id;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = order_row.intent_id;
  IF p_entry_kind NOT IN ('FILL','FEE','CORPORATE_ACTION','MANUAL_ADJUSTMENT')
     OR p_amount IS NULL
     OR pg_catalog.scale(p_amount) > 12
     OR p_source_schema_name IS NULL
     OR p_source_id IS NULL
     OR pg_catalog.jsonb_typeof(p_source_refs) <> 'array' THEN
    RAISE EXCEPTION 'cash ledger entry is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM qc2_execution.position_state_cash_ledger AS prior
    WHERE prior.episode_id = p_episode_id
      AND prior.source_schema_name = p_source_schema_name
      AND prior.source_id = p_source_id
      AND prior.entry_kind = p_entry_kind
  ) THEN
    SELECT cash_entry_id INTO cash_entry_id
      FROM qc2_execution.position_state_cash_ledger
      WHERE episode_id = p_episode_id
        AND source_schema_name = p_source_schema_name
        AND source_id = p_source_id
        AND entry_kind = p_entry_kind;
    RETURN cash_entry_id;
  END IF;
  SELECT episode_row.opening_cash + COALESCE(pg_catalog.sum(amount), 0)
    INTO balance_after
    FROM qc2_execution.position_state_cash_ledger
    WHERE episode_id = p_episode_id;
  balance_after := balance_after + p_amount;
  cash_entry_id := qc2_integrity_build.new_uuid_v7();
  cash_contract := pg_catalog.jsonb_build_object(
    'schema_name', 'qc2.execution.CashLedgerEntry.v1',
    'schema_version', '1.0',
    'id', cash_entry_id::text,
    'created_at', pg_catalog.to_char(
      pg_catalog.clock_timestamp() AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ),
    'owning_authority', 'execution',
    'evidence_class', p_evidence_class,
    'environment_namespace', p_environment_namespace,
    'source_refs', p_source_refs,
    'episode_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.execution.ExecutionEpisode.v1',
      'target_id', p_episode_id::text,
      'content_hash', episode_row.content_hash
    ),
    'entry_kind', p_entry_kind,
    'amount', pg_catalog.trim_scale(p_amount)::text,
    'currency', episode_row.currency,
    'effective_at', pg_catalog.to_char(
      p_effective_at AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ),
    'source_ref', pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.execution.PaperOrderIntent.v1',
      'target_id', intent_row.id::text,
      'content_hash', intent_row.content_hash
    ),
    'balance_after', pg_catalog.trim_scale(balance_after)::text
  );
  INSERT INTO qc2_execution.position_state_cash_ledger(
    cash_entry_id, episode_id, entry_kind, amount, currency, effective_at,
    source_schema_name, source_id, balance_after, cash_contract
  )
  VALUES (
    cash_entry_id, p_episode_id, p_entry_kind, p_amount, episode_row.currency,
    p_effective_at, p_source_schema_name, p_source_id, balance_after, cash_contract
  );
  RETURN cash_entry_id;
END
$function$;

CREATE FUNCTION qc2_control.refresh_position_state_reservation(
  p_order_id uuid,
  p_source_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  order_row qc2_execution.position_state_broker_order%ROWTYPE;
  intent_reservation qc2_execution.paper_order_intent_reservation%ROWTYPE;
  resource_reservation qc2_execution.resource_reservation%ROWTYPE;
  cumulative_quantity numeric(38,12);
  desired_remaining numeric(38,12);
  previous_amount numeric(38,12);
  terminal boolean;
  latest_event_type text;
  settlement_state text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO order_row
    FROM qc2_execution.position_state_broker_order
    WHERE order_id = p_order_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM qc2_execution.position_state_projection_control AS control
    WHERE control.episode_id = order_row.episode_id
      AND control.reconciliation_status = 'HOLD'
  ) THEN
    RETURN;
  END IF;
  SELECT * INTO intent_reservation
    FROM qc2_execution.paper_order_intent_reservation
    WHERE intent_id = order_row.intent_id;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  SELECT * INTO resource_reservation
    FROM qc2_execution.resource_reservation
    WHERE id = intent_reservation.id
    FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM qc2_control.hold_execution_position_state(
      order_row.episode_id, 'paper_order_reservation_missing'
    );
    RETURN;
  END IF;
  SELECT COALESCE(pg_catalog.sum(fill.quantity + COALESCE(correction.quantity_delta_sum, 0)), 0)
    INTO cumulative_quantity
    FROM qc2_execution.position_state_fill AS fill
    LEFT JOIN LATERAL (
      SELECT pg_catalog.sum(correction.quantity_delta) AS quantity_delta_sum
      FROM qc2_execution.position_state_fill_correction AS correction
      WHERE correction.fill_id = fill.fill_id
        AND correction.correction_kind IN ('BUST','QUANTITY_ADJUSTMENT')
    ) AS correction ON true
    WHERE fill.order_id = p_order_id;
  IF cumulative_quantity < 0 OR cumulative_quantity > order_row.order_quantity THEN
    PERFORM qc2_control.hold_execution_position_state(
      order_row.episode_id, 'cumulative_fill_quantity_out_of_bounds'
    );
    RETURN;
  END IF;
  SELECT event_type INTO latest_event_type
    FROM qc2_execution.position_state_broker_event
    WHERE order_id = p_order_id
    ORDER BY event_sequence DESC, event_id DESC
    LIMIT 1;
  terminal := cumulative_quantity = order_row.order_quantity
    OR latest_event_type IN ('CANCELLED','REJECTED','EXPIRED');
  previous_amount := resource_reservation.quantity;
  IF terminal THEN
    desired_remaining := 0;
  ELSE
    desired_remaining := pg_catalog.round(
      intent_reservation.reserved_amount
        * (order_row.order_quantity - cumulative_quantity)
        / order_row.order_quantity,
      12
    );
  END IF;
  IF resource_reservation.state = 'RELEASED' THEN
    IF desired_remaining > 0 THEN
      PERFORM qc2_control.hold_execution_position_state(
        order_row.episode_id, 'reservation_reopen_requires_review'
      );
    END IF;
    RETURN;
  END IF;
  IF desired_remaining > previous_amount THEN
    PERFORM qc2_control.hold_execution_position_state(
      order_row.episode_id, 'reservation_increase_requires_review'
    );
    RETURN;
  END IF;
  IF desired_remaining = previous_amount THEN
    RETURN;
  END IF;
  IF desired_remaining = 0 THEN
    PERFORM qc2_control.release_resource_reservation(
      resource_reservation.resource_key, resource_reservation.reservation_key
    );
    settlement_state := CASE
      WHEN cumulative_quantity = order_row.order_quantity THEN 'SETTLED'
      ELSE 'RELEASED'
    END;
  ELSE
    UPDATE qc2_execution.reservation_resource
      SET reserved = reserved - (previous_amount - desired_remaining),
          generation = generation + 1,
          updated_at = pg_catalog.clock_timestamp()
      WHERE resource_key = resource_reservation.resource_key
        AND reserved >= previous_amount - desired_remaining;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'reservation capacity projection is inconsistent'
        USING ERRCODE = '23514';
    END IF;
    UPDATE qc2_execution.resource_reservation AS resource_row
      SET quantity = desired_remaining
      WHERE resource_row.id = resource_reservation.id
        AND resource_row.state = 'ACTIVE';
    settlement_state := 'PARTIALLY_CONSUMED';
  END IF;
  INSERT INTO qc2_execution.position_state_reservation_settlement(
    settlement_id, intent_id, reservation_id, source_id, previous_amount,
    remaining_amount, settlement_state
  )
  VALUES (
    qc2_integrity_build.new_uuid_v7(), order_row.intent_id,
    intent_reservation.id, p_source_id, previous_amount,
    desired_remaining, settlement_state
  )
  ON CONFLICT (intent_id, source_id) DO NOTHING;
  PERFORM qc2_integrity_build.append_event_internal(
    'paper_order_reservation_settled',
    pg_catalog.jsonb_build_object(
      'intent_id', order_row.intent_id::text,
      'reservation_id', intent_reservation.id::text,
      'source_id', p_source_id::text,
      'previous_amount', pg_catalog.trim_scale(previous_amount)::text,
      'remaining_amount', pg_catalog.trim_scale(desired_remaining)::text,
      'settlement_state', settlement_state
    ),
    0,
    '[]'::jsonb
  );
END
$function$;

CREATE FUNCTION qc2_control.append_position_state_fill(p_contract jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
<<append_position_state_fill>>
DECLARE
  fill_id uuid;
  order_id uuid;
  episode_id uuid;
  order_row qc2_execution.position_state_broker_order%ROWTYPE;
  fill_payload_hash text;
  prior_hash text;
  prior_fill_id uuid;
  amount numeric(38,12);
  evidence_class text;
  environment_namespace text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_contract) <> 'object'
     OR p_contract->>'schema_name' <> 'qc2.execution.Fill.v1'
     OR p_contract->>'schema_version' <> '1.0'
     OR p_contract->>'owning_authority' <> 'execution'
     OR p_contract->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_contract->'broker_order_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.BrokerOrder.v1'
     OR p_contract->'broker_order_ref'->>'target_id' IS NULL
     OR p_contract->>'provider_fill_id' IS NULL
     OR p_contract->>'side' NOT IN ('BUY','SELL')
     OR p_contract->>'quantity' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
     OR p_contract->>'price' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
     OR p_contract->>'currency' !~ '^[A-Z]{3}$' THEN
    RAISE EXCEPTION 'fill contract is invalid'
      USING ERRCODE = '23514';
  END IF;
  fill_id := (p_contract->>'id')::uuid;
  order_id := (p_contract->'broker_order_ref'->>'target_id')::uuid;
  SELECT * INTO order_row
    FROM qc2_execution.position_state_broker_order
    WHERE position_state_broker_order.order_id =
      append_position_state_fill.order_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'fill broker order does not exist'
      USING ERRCODE = '23503';
  END IF;
  episode_id := order_row.episode_id;
  IF p_contract->'instrument_ref'->>'target_id' <> order_row.instrument_id::text
     OR p_contract->>'side' <> order_row.side
     OR p_contract->>'currency' <> order_row.currency
     OR (p_contract->>'quantity')::numeric <= 0
     OR (p_contract->>'price')::numeric <= 0
     OR pg_catalog.scale((p_contract->>'quantity')::numeric) > 12
     OR pg_catalog.scale((p_contract->>'price')::numeric) > 12 THEN
    RAISE EXCEPTION 'fill does not match its order or exceeds exact decimal precision'
      USING ERRCODE = '23514';
  END IF;
  fill_payload_hash := qc2_integrity_build.hash_json(
    'qc2.execution.provider-fill.v1',
    pg_catalog.jsonb_build_object(
      'order_id', order_id::text,
      'provider_fill_id', p_contract->>'provider_fill_id',
      'instrument_id', order_row.instrument_id::text,
      'side', p_contract->>'side',
      'quantity', p_contract->>'quantity',
      'price', p_contract->>'price',
      'currency', p_contract->>'currency',
      'filled_at', p_contract->>'filled_at'
    )
  );
  SELECT fill_record.provider_payload_hash, fill_record.fill_id
    INTO prior_hash, prior_fill_id
    FROM qc2_execution.position_state_fill AS fill_record
    WHERE fill_record.order_id = append_position_state_fill.order_id
      AND fill_record.provider_fill_id = p_contract->>'provider_fill_id'
    ORDER BY fill_record.created_at, fill_record.fill_id
    LIMIT 1;
  IF FOUND AND prior_hash = fill_payload_hash THEN
    RETURN prior_fill_id;
  END IF;
  IF EXISTS (
    SELECT 1 FROM qc2_execution.position_state_fill
    WHERE position_state_fill.fill_id = append_position_state_fill.fill_id
  ) THEN
    RAISE EXCEPTION 'fill record ID was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  INSERT INTO qc2_execution.position_state_fill(
    fill_id, order_id, provider_fill_id, provider_payload_hash, instrument_id,
    side, quantity, price, currency, filled_at, received_at, fill_contract
  )
  VALUES (
    fill_id, order_id, p_contract->>'provider_fill_id', fill_payload_hash,
    order_row.instrument_id, p_contract->>'side',
    (p_contract->>'quantity')::numeric, (p_contract->>'price')::numeric,
    p_contract->>'currency', (p_contract->>'filled_at')::timestamptz,
    (p_contract->>'received_at')::timestamptz, p_contract
  );
  IF prior_hash IS NOT NULL THEN
    PERFORM qc2_control.hold_execution_position_state(
      episode_id, 'provider_fill_identity_conflict'
    );
  END IF;
  IF prior_hash IS NULL THEN
    amount := CASE WHEN p_contract->>'side' = 'BUY'
      THEN -((p_contract->>'quantity')::numeric * (p_contract->>'price')::numeric)
      ELSE (p_contract->>'quantity')::numeric * (p_contract->>'price')::numeric
    END;
    evidence_class := p_contract->>'evidence_class';
    environment_namespace := p_contract->>'environment_namespace';
    PERFORM qc2_control.append_position_state_cash_entry(
      episode_id, order_id, 'FILL', amount,
      (p_contract->>'filled_at')::timestamptz,
      'qc2.execution.Fill.v1', fill_id,
      pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
        'target_schema_name', 'qc2.execution.Fill.v1', 'target_id', fill_id::text
      )),
      evidence_class, environment_namespace
    );
    PERFORM qc2_control.refresh_position_state_reservation(order_id, fill_id);
  END IF;
  PERFORM qc2_integrity_build.append_event_internal(
    'broker_fill_appended',
    pg_catalog.jsonb_build_object(
      'fill_id', fill_id::text,
      'order_id', order_id::text,
      'provider_fill_id_hash', qc2_integrity_build.hash_json(
        'qc2.execution.provider-fill-id.v1',
        pg_catalog.jsonb_build_object('provider_fill_id', p_contract->>'provider_fill_id')
      ),
      'provider_payload_hash', fill_payload_hash
    ),
    0,
    p_contract->'source_refs'
  );
  RETURN fill_id;
END
$function$;

CREATE FUNCTION qc2_control.append_position_state_fill_correction(p_contract jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
<<append_position_state_fill_correction>>
DECLARE
  correction_id uuid;
  fill_id uuid;
  source_event_id uuid;
  fill_row qc2_execution.position_state_fill%ROWTYPE;
  order_row qc2_execution.position_state_broker_order%ROWTYPE;
  event_row qc2_execution.position_state_broker_event%ROWTYPE;
  episode_row qc2_execution.execution_episode_state%ROWTYPE;
  intent_row qc2_execution.paper_order_intent%ROWTYPE;
  current_quantity numeric(38,12);
  current_price numeric(38,12);
  quantity_delta numeric(38,12);
  price_delta numeric(38,12);
  cash_delta numeric(38,12);
  valid_correction boolean := true;
  source_event_conflict boolean := false;
  cash_kind text;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  IF pg_catalog.jsonb_typeof(p_contract) <> 'object'
     OR p_contract->>'schema_name' <> 'qc2.execution.FillCorrection.v1'
     OR p_contract->>'schema_version' <> '1.0'
     OR p_contract->>'owning_authority' <> 'execution'
     OR p_contract->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
     OR p_contract->'original_fill_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.Fill.v1'
     OR p_contract->'source_event_ref'->>'target_schema_name'
          IS DISTINCT FROM 'qc2.execution.BrokerOrderEvent.v1'
     OR p_contract->>'quantity_delta' !~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$'
     OR p_contract->>'price_delta' !~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$' THEN
    RAISE EXCEPTION 'fill correction contract is invalid'
      USING ERRCODE = '23514';
  END IF;
  correction_id := (p_contract->>'id')::uuid;
  fill_id := (p_contract->'original_fill_ref'->>'target_id')::uuid;
  source_event_id := (p_contract->'source_event_ref'->>'target_id')::uuid;
  SELECT * INTO fill_row
    FROM qc2_execution.position_state_fill
    WHERE position_state_fill.fill_id = append_position_state_fill_correction.fill_id
    FOR UPDATE;
  SELECT * INTO event_row
    FROM qc2_execution.position_state_broker_event
    WHERE position_state_broker_event.event_id =
      append_position_state_fill_correction.source_event_id;
  IF NOT FOUND OR event_row.event_type <> 'CORRECTION' THEN
    RAISE EXCEPTION 'fill correction source event is missing or not a correction'
      USING ERRCODE = '23503';
  END IF;
  IF NOT FOUND OR fill_row.fill_id IS NULL THEN
    RAISE EXCEPTION 'fill correction original fill is missing'
      USING ERRCODE = '23503';
  END IF;
  SELECT * INTO order_row
    FROM qc2_execution.position_state_broker_order
    WHERE order_id = fill_row.order_id
    FOR UPDATE;
  IF event_row.order_id <> order_row.order_id THEN
    RAISE EXCEPTION 'fill correction event belongs to a different order'
      USING ERRCODE = '23514';
  END IF;
  SELECT * INTO episode_row
    FROM qc2_execution.execution_episode_state
    WHERE episode_id = order_row.episode_id;
  SELECT * INTO intent_row
    FROM qc2_execution.paper_order_intent
    WHERE id = order_row.intent_id;

  SELECT fill_row.quantity
           + COALESCE(pg_catalog.sum(correction.quantity_delta)
               FILTER (WHERE correction.correction_kind IN (
                 'BUST','QUANTITY_ADJUSTMENT'
               )), 0),
         fill_row.price
           + COALESCE(pg_catalog.sum(correction.price_delta)
               FILTER (WHERE correction.correction_kind = 'PRICE_ADJUSTMENT'), 0)
    INTO current_quantity, current_price
    FROM qc2_execution.position_state_fill_correction AS correction
    WHERE correction.fill_id = append_position_state_fill_correction.fill_id;
  quantity_delta := (p_contract->>'quantity_delta')::numeric;
  price_delta := (p_contract->>'price_delta')::numeric;
  IF EXISTS (
    SELECT 1
    FROM qc2_execution.position_state_fill_correction AS prior
    WHERE prior.fill_id = append_position_state_fill_correction.fill_id
      AND prior.source_event_id =
        append_position_state_fill_correction.source_event_id
  ) THEN
    source_event_conflict := true;
    valid_correction := false;
  END IF;
  IF p_contract->>'correction_kind' = 'BUST' THEN
    valid_correction := valid_correction
      AND quantity_delta = -current_quantity AND price_delta = 0;
    cash_delta := CASE WHEN order_row.side = 'BUY'
      THEN -quantity_delta * current_price
      ELSE quantity_delta * current_price
    END;
    cash_kind := 'FILL';
  ELSIF p_contract->>'correction_kind' = 'QUANTITY_ADJUSTMENT' THEN
    valid_correction := valid_correction
      AND price_delta = 0 AND current_quantity + quantity_delta >= 0;
    cash_delta := CASE WHEN order_row.side = 'BUY'
      THEN -quantity_delta * current_price
      ELSE quantity_delta * current_price
    END;
    cash_kind := 'FILL';
  ELSIF p_contract->>'correction_kind' = 'PRICE_ADJUSTMENT' THEN
    valid_correction := valid_correction
      AND quantity_delta = 0 AND current_price + price_delta > 0;
    cash_delta := CASE WHEN order_row.side = 'BUY'
      THEN -current_quantity * price_delta
      ELSE current_quantity * price_delta
    END;
    cash_kind := 'FILL';
  ELSIF p_contract->>'correction_kind' = 'FEE_ADJUSTMENT' THEN
    valid_correction := valid_correction AND quantity_delta = 0;
    cash_delta := -current_quantity * price_delta;
    cash_kind := 'FEE';
  ELSE
    valid_correction := false;
    cash_delta := 0;
    cash_kind := 'FILL';
  END IF;

  INSERT INTO qc2_execution.position_state_fill_correction(
    correction_id, fill_id, source_event_id, correction_kind,
    quantity_delta, price_delta, reason_code, corrected_at, correction_contract
  )
  VALUES (
    correction_id, fill_id, source_event_id, p_contract->>'correction_kind',
    quantity_delta, price_delta, p_contract->>'reason_code',
    (p_contract->>'corrected_at')::timestamptz, p_contract
  )
  ON CONFLICT ON CONSTRAINT position_state_fill_correction_pkey DO NOTHING;
  IF NOT FOUND THEN
    IF EXISTS (
      SELECT 1 FROM qc2_execution.position_state_fill_correction
      WHERE position_state_fill_correction.correction_id =
        append_position_state_fill_correction.correction_id
        AND correction_contract = p_contract
    ) THEN
      RETURN correction_id;
    END IF;
    RAISE EXCEPTION 'fill correction ID was reused with different content'
      USING ERRCODE = '23505';
  END IF;
  IF NOT valid_correction THEN
    PERFORM qc2_control.hold_execution_position_state(
      order_row.episode_id, 'fill_correction_requires_review'
    );
  ELSE
    PERFORM qc2_control.append_position_state_cash_entry(
      order_row.episode_id, order_row.order_id, cash_kind, cash_delta,
      (p_contract->>'corrected_at')::timestamptz,
      'qc2.execution.FillCorrection.v1', correction_id,
      pg_catalog.jsonb_build_array(
        pg_catalog.jsonb_build_object(
          'target_schema_name', 'qc2.execution.Fill.v1',
          'target_id', fill_id::text
        ),
        pg_catalog.jsonb_build_object(
          'target_schema_name', 'qc2.execution.FillCorrection.v1',
          'target_id', correction_id::text
        )
      ),
      p_contract->>'evidence_class',
      p_contract->>'environment_namespace'
    );
  END IF;
  PERFORM qc2_control.refresh_position_state_reservation(
    order_row.order_id, correction_id
  );
  PERFORM qc2_integrity_build.append_event_internal(
    'broker_fill_correction_appended',
    pg_catalog.jsonb_build_object(
      'correction_id', correction_id::text,
      'fill_id', fill_id::text,
      'source_event_id', source_event_id::text,
      'correction_kind', p_contract->>'correction_kind',
      'valid_for_projection', valid_correction
    ),
    0,
    p_contract->'source_refs'
  );
  RETURN correction_id;
END
$function$;

CREATE FUNCTION qc2_control.append_position_state_corporate_action(
  p_episode_id uuid,
  p_adjustment_id uuid,
  p_corporate_action_id uuid,
  p_instrument_id uuid,
  p_currency text,
  p_effective_at timestamptz,
  p_share_ratio numeric,
  p_cash_per_share numeric,
  p_terms_hash text,
  p_source_order_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  episode_row qc2_execution.execution_episode_state%ROWTYPE;
  adjustment_contract jsonb;
  prior qc2_execution.position_state_corporate_action%ROWTYPE;
  cash_amount numeric(38,12);
  prior_quantity numeric(38,12);
  source_order qc2_execution.position_state_broker_order%ROWTYPE;
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO episode_row
    FROM qc2_execution.execution_episode_state
    WHERE episode_id = p_episode_id;
  IF NOT FOUND OR p_currency <> episode_row.currency
     OR p_terms_hash !~ '^[0-9a-f]{64}$'
     OR p_share_ratio <= 0
     OR p_cash_per_share < 0
     OR pg_catalog.scale(p_share_ratio) > 12
     OR pg_catalog.scale(p_cash_per_share) > 12 THEN
    RAISE EXCEPTION 'corporate action adjustment is invalid for the episode'
      USING ERRCODE = '23514';
  END IF;
  adjustment_contract := pg_catalog.jsonb_build_object(
    'record_kind', 'EXPLICIT_CORPORATE_ACTION_ADJUSTMENT',
    'adjustment_id', p_adjustment_id::text,
    'episode_id', p_episode_id::text,
    'corporate_action_id', p_corporate_action_id::text,
    'instrument_id', p_instrument_id::text,
    'currency', p_currency,
    'effective_at', p_effective_at,
    'share_ratio', pg_catalog.trim_scale(p_share_ratio)::text,
    'cash_per_share', pg_catalog.trim_scale(p_cash_per_share)::text,
    'terms_hash', p_terms_hash,
    'source_order_id', p_source_order_id::text
  );
  INSERT INTO qc2_execution.position_state_corporate_action(
    adjustment_id, episode_id, corporate_action_id, instrument_id, currency,
    effective_at, share_ratio, cash_per_share, adjustment_contract
  )
  VALUES (
    p_adjustment_id, p_episode_id, p_corporate_action_id, p_instrument_id,
    p_currency, p_effective_at, p_share_ratio, p_cash_per_share, adjustment_contract
  )
  ON CONFLICT (episode_id, adjustment_id) DO NOTHING;
  SELECT * INTO prior
    FROM qc2_execution.position_state_corporate_action
    WHERE episode_id = p_episode_id AND adjustment_id = p_adjustment_id;
  IF prior.adjustment_contract IS DISTINCT FROM adjustment_contract THEN
    RAISE EXCEPTION 'corporate action adjustment ID was reused with different terms'
      USING ERRCODE = '23505';
  END IF;
  IF p_cash_per_share > 0 THEN
    SELECT quantity INTO prior_quantity
      FROM qc2_execution.position_state_position_projection
      WHERE episode_id = p_episode_id
        AND instrument_id = p_instrument_id
        AND currency = p_currency;
    IF NOT FOUND THEN
      PERFORM qc2_control.hold_execution_position_state(
        p_episode_id, 'corporate_action_cash_without_position_projection'
      );
    ELSE
      cash_amount := prior_quantity * p_cash_per_share;
      SELECT source_order_row.* INTO source_order
        FROM qc2_execution.position_state_broker_order AS source_order_row
        WHERE source_order_row.order_id = p_source_order_id
          AND source_order_row.episode_id = p_episode_id
          AND source_order_row.instrument_id = p_instrument_id;
      IF FOUND THEN
        PERFORM qc2_control.append_position_state_cash_entry(
          p_episode_id, source_order.order_id, 'CORPORATE_ACTION', cash_amount,
          p_effective_at, 'qc2.identity_market.CorporateActionRecord.v1',
          p_corporate_action_id,
          pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
            'target_schema_name', 'qc2.identity_market.CorporateActionRecord.v1',
            'target_id', p_corporate_action_id::text
          )),
          episode_row.episode_contract->>'evidence_class',
          episode_row.episode_contract->>'environment_namespace'
        );
      ELSE
        PERFORM qc2_control.hold_execution_position_state(
          p_episode_id, 'corporate_action_cash_requires_intent_anchor'
        );
      END IF;
    END IF;
  END IF;
  PERFORM qc2_integrity_build.append_event_internal(
    'corporate_action_position_adjustment_appended',
    pg_catalog.jsonb_build_object(
      'adjustment_id', p_adjustment_id::text,
      'episode_id', p_episode_id::text,
      'corporate_action_id', p_corporate_action_id::text,
      'instrument_id', p_instrument_id::text,
      'terms_hash', p_terms_hash
    ),
    0,
    pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'target_schema_name', 'qc2.identity_market.CorporateActionRecord.v1',
      'target_id', p_corporate_action_id::text
    ))
  );
  RETURN p_adjustment_id;
END
$function$;

CREATE FUNCTION qc2_control.persist_execution_position_projection(
  p_episode_id uuid,
  p_positions jsonb,
  p_reconciliation_status text,
  p_hold_reasons jsonb,
  p_projection_hash text,
  p_as_of timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_control, qc2_execution, qc2_integrity_build
AS $function$
DECLARE
  episode_row qc2_execution.execution_episode_state%ROWTYPE;
  position_contract jsonb;
  projection_row jsonb;
  instrument_id uuid;
  quantity numeric(38,12);
  average_cost numeric(38,12);
  currency text;
  source_fill_refs jsonb;
  corporate_action_refs jsonb;
  ledger_cash numeric(38,12);
BEGIN
  PERFORM qc2_control.assert_runtime_authority('execution');
  SELECT * INTO episode_row
    FROM qc2_execution.execution_episode_state
    WHERE episode_id = p_episode_id;
  IF NOT FOUND
     OR pg_catalog.jsonb_typeof(p_positions) <> 'array'
     OR pg_catalog.jsonb_typeof(p_hold_reasons) <> 'array'
     OR p_reconciliation_status NOT IN ('RECONCILED','DISCREPANCY','UNKNOWN','HOLD')
     OR p_projection_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'position projection envelope is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.jsonb_array_elements(p_positions) AS items(value)
    GROUP BY items.value->'instrument_ref'->>'target_id',
             items.value->>'currency'
    HAVING pg_catalog.count(*) > 1
  ) THEN
    RAISE EXCEPTION 'position projection contains duplicate instrument/currency rows'
      USING ERRCODE = '23505';
  END IF;
  IF p_reconciliation_status = 'RECONCILED' THEN
    DELETE FROM qc2_execution.position_state_position_projection
    WHERE episode_id = p_episode_id;
    FOR position_contract IN
      SELECT items.value FROM pg_catalog.jsonb_array_elements(p_positions) AS items(value)
    LOOP
      IF position_contract->>'schema_name' <> 'qc2.execution.Position.v1'
         OR position_contract->>'schema_version' <> '1.0'
         OR position_contract->>'owning_authority' <> 'execution'
         OR position_contract->'episode_ref'->>'target_id' <> p_episode_id::text
         OR position_contract->'episode_ref'->>'content_hash'
              <> episode_row.content_hash
         OR position_contract->'instrument_ref'->>'target_id'
              !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
         OR position_contract->>'quantity' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
         OR position_contract->>'average_cost' !~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
         OR position_contract->>'currency' <> episode_row.currency
         OR position_contract->>'reconciliation_status' <> 'RECONCILED'
         OR pg_catalog.jsonb_typeof(position_contract->'source_fill_refs') <> 'array'
         OR pg_catalog.jsonb_typeof(position_contract->'corporate_action_refs') <> 'array' THEN
        RAISE EXCEPTION 'position projection contract is invalid or mismatched'
          USING ERRCODE = '23514';
      END IF;
      instrument_id := (position_contract->'instrument_ref'->>'target_id')::uuid;
      quantity := (position_contract->>'quantity')::numeric;
      average_cost := (position_contract->>'average_cost')::numeric;
      currency := position_contract->>'currency';
      source_fill_refs := position_contract->'source_fill_refs';
      corporate_action_refs := position_contract->'corporate_action_refs';
      IF quantity <= 0 OR average_cost <= 0
         OR pg_catalog.scale(quantity) > 12
         OR pg_catalog.scale(average_cost) > 12 THEN
        RAISE EXCEPTION 'flat, short, or inexact position cannot be projected'
          USING ERRCODE = '23514';
      END IF;
      INSERT INTO qc2_execution.position_state_position_projection(
        episode_id, instrument_id, currency, quantity, average_cost, as_of,
        reconciliation_status, source_fill_refs, corporate_action_refs,
        position_contract, projection_hash
      )
      VALUES (
        p_episode_id, instrument_id, currency, quantity, average_cost, p_as_of,
        'RECONCILED', source_fill_refs, corporate_action_refs,
        position_contract, p_projection_hash
      );
    END LOOP;
  ELSE
    UPDATE qc2_execution.position_state_position_projection
      SET reconciliation_status = p_reconciliation_status,
          projection_hash = p_projection_hash,
          updated_at = pg_catalog.clock_timestamp()
      WHERE episode_id = p_episode_id;
  END IF;
  SELECT episode_row.opening_cash + COALESCE(pg_catalog.sum(amount), 0)
    INTO ledger_cash
    FROM qc2_execution.position_state_cash_ledger
    WHERE episode_id = p_episode_id;
  INSERT INTO qc2_execution.position_state_cash_projection(
    episode_id, currency, balance, reconciliation_status, projection_hash
  )
  VALUES (
    p_episode_id, episode_row.currency, ledger_cash,
    p_reconciliation_status, p_projection_hash
  )
  ON CONFLICT ON CONSTRAINT position_state_cash_projection_pkey DO UPDATE
    SET balance = EXCLUDED.balance,
        reconciliation_status = EXCLUDED.reconciliation_status,
        projection_hash = EXCLUDED.projection_hash,
        updated_at = pg_catalog.clock_timestamp();
  INSERT INTO qc2_execution.position_state_projection_control(
    episode_id, reconciliation_status, hold_reasons, projection_hash, generation
  )
  VALUES (
    p_episode_id, p_reconciliation_status, p_hold_reasons,
    p_projection_hash, 1
  )
  ON CONFLICT (episode_id) DO UPDATE
    SET reconciliation_status = EXCLUDED.reconciliation_status,
        hold_reasons = EXCLUDED.hold_reasons,
        projection_hash = EXCLUDED.projection_hash,
        generation = qc2_execution.position_state_projection_control.generation + 1,
        updated_at = pg_catalog.clock_timestamp();
  PERFORM qc2_integrity_build.append_event_internal(
    'execution_position_projection_rebuilt',
    pg_catalog.jsonb_build_object(
      'episode_id', p_episode_id::text,
      'reconciliation_status', p_reconciliation_status,
      'projection_hash', p_projection_hash,
      'position_count', pg_catalog.jsonb_array_length(p_positions),
      'hold_reason_count', pg_catalog.jsonb_array_length(p_hold_reasons)
    ),
    0,
    '[]'::jsonb
  );
END
$function$;

REVOKE ALL ON FUNCTION
  qc2_execution.reject_position_state_ledger_rewrite(),
  qc2_control.hold_execution_position_state(uuid, text),
  qc2_control.register_execution_episode(jsonb, jsonb),
  qc2_control.register_position_state_broker_order(jsonb),
  qc2_control.append_position_state_broker_event(jsonb),
  qc2_control.append_position_state_cash_entry(
    uuid, uuid, text, numeric, timestamptz, text, uuid, jsonb, text, text
  ),
  qc2_control.refresh_position_state_reservation(uuid, uuid),
  qc2_control.append_position_state_fill(jsonb),
  qc2_control.append_position_state_fill_correction(jsonb),
  qc2_control.append_position_state_corporate_action(
    uuid, uuid, uuid, uuid, text, timestamptz, numeric, numeric, text, uuid
  ),
  qc2_control.persist_execution_position_projection(
    uuid, jsonb, text, jsonb, text, timestamptz
  )
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  qc2_control.register_execution_episode(jsonb, jsonb),
  qc2_control.register_position_state_broker_order(jsonb),
  qc2_control.append_position_state_broker_event(jsonb),
  qc2_control.append_position_state_fill(jsonb),
  qc2_control.append_position_state_fill_correction(jsonb),
  qc2_control.append_position_state_corporate_action(
    uuid, uuid, uuid, uuid, text, timestamptz, numeric, numeric, text, uuid
  ),
  qc2_control.persist_execution_position_projection(
    uuid, jsonb, text, jsonb, text, timestamptz
  )
TO qc2_runtime_execution;

RESET ROLE;
