-- QC2-054: bounded, rebuildable owner projections isolated from source authority tables.
SET ROLE qc2_migrator;

CREATE SCHEMA qc2_owner_api AUTHORIZATION qc2_migrator;
REVOKE ALL ON SCHEMA qc2_owner_api FROM PUBLIC;
GRANT USAGE ON SCHEMA qc2_owner_api TO qc2_runtime_owner_api;

GRANT EXECUTE ON FUNCTION
  qc2_governance_owner.identity_resolve_access(text, text, timestamptz)
TO qc2_runtime_owner_api;

CREATE TABLE qc2_owner_api.owner_projection_snapshot (
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  view_name text NOT NULL CHECK (view_name IN (
    'today','predictions','validation','models','system',
    'positions','alerts','reports','evidence'
  )),
  projection_sequence bigint NOT NULL CHECK (
    projection_sequence BETWEEN 1 AND 9007199254740991
  ),
  source_sequence bigint NOT NULL CHECK (
    source_sequence BETWEEN 0 AND 9007199254740991
  ),
  built_at timestamptz NOT NULL,
  freshness_deadline timestamptz NOT NULL CHECK (freshness_deadline > built_at),
  source_refs jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(source_refs) = 'array'
    AND pg_catalog.jsonb_array_length(source_refs) <= 100000
  ),
  snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (environment_namespace, view_name, projection_sequence)
);

CREATE TABLE qc2_owner_api.owner_projection_item (
  environment_namespace text NOT NULL,
  view_name text NOT NULL,
  projection_sequence bigint NOT NULL,
  item_id text NOT NULL CHECK (
    item_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
  ),
  sort_key text NOT NULL CHECK (
    pg_catalog.octet_length(sort_key) <= 256
    AND sort_key ~ '^[ -~]*$'
  ),
  source_sequence bigint NOT NULL CHECK (
    source_sequence BETWEEN 1 AND 9007199254740991
  ),
  source_ref jsonb NOT NULL CHECK (
    pg_catalog.jsonb_typeof(source_ref) = 'object'
    AND source_ref->>'target_schema_name' ~ '^qc2\.[A-Za-z0-9_.-]+\.v[1-9][0-9]*$'
    AND pg_catalog.char_length(source_ref->>'target_id') BETWEEN 1 AND 128
    AND (
      source_ref->>'content_hash' IS NULL
      OR source_ref->>'content_hash' ~ '^[0-9a-f]{64}$'
    )
  ),
  payload jsonb NOT NULL CHECK (pg_catalog.jsonb_typeof(payload) = 'object'),
  receipt_hash text NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (environment_namespace, view_name, projection_sequence, item_id),
  FOREIGN KEY (environment_namespace, view_name, projection_sequence)
    REFERENCES qc2_owner_api.owner_projection_snapshot(
      environment_namespace, view_name, projection_sequence
    ) ON DELETE CASCADE
);

CREATE INDEX owner_projection_item_page_order
  ON qc2_owner_api.owner_projection_item(
    environment_namespace, view_name, projection_sequence,
    sort_key COLLATE "C", item_id COLLATE "C"
  );

CREATE UNIQUE INDEX owner_projection_item_source_sequence_unique
  ON qc2_owner_api.owner_projection_item(
    environment_namespace, view_name, projection_sequence, source_sequence
  );

CREATE TABLE qc2_owner_api.owner_projection_head (
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  view_name text NOT NULL CHECK (view_name IN (
    'today','predictions','validation','models','system',
    'positions','alerts','reports','evidence'
  )),
  projection_sequence bigint NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (environment_namespace, view_name),
  FOREIGN KEY (environment_namespace, view_name, projection_sequence)
    REFERENCES qc2_owner_api.owner_projection_snapshot(
      environment_namespace, view_name, projection_sequence
    ) ON DELETE RESTRICT
);

CREATE TABLE qc2_owner_api.owner_projection_watermark (
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  view_name text NOT NULL CHECK (view_name IN (
    'today','predictions','validation','models','system',
    'positions','alerts','reports','evidence'
  )),
  source_highwater_sequence bigint NOT NULL CHECK (
    source_highwater_sequence BETWEEN 0 AND 9007199254740991
  ),
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (environment_namespace, view_name)
);

CREATE TABLE qc2_owner_api.owner_projection_access_audit (
  audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  environment_namespace text NOT NULL CHECK (
    environment_namespace IN ('development','test','research','production')
  ),
  session_record_id uuid NOT NULL,
  view_name text NOT NULL CHECK (view_name IN (
    'today','predictions','validation','models','system',
    'positions','alerts','reports','evidence'
  )),
  projection_sequence bigint NOT NULL CHECK (
    projection_sequence BETWEEN 1 AND 9007199254740991
  ),
  item_count integer NOT NULL CHECK (item_count BETWEEN 0 AND 1000),
  response_bytes integer NOT NULL CHECK (response_bytes BETWEEN 0 AND 1048576),
  requested_at timestamptz NOT NULL,
  FOREIGN KEY (environment_namespace, session_record_id)
    REFERENCES qc2_governance_owner.identity_session(environment_namespace, id)
    ON DELETE RESTRICT
);

ALTER TABLE qc2_owner_api.owner_projection_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_snapshot FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_item FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_head ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_head FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_watermark ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_watermark FORCE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_access_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE qc2_owner_api.owner_projection_access_audit FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_projection_snapshot_migrator
  ON qc2_owner_api.owner_projection_snapshot
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY owner_projection_item_migrator
  ON qc2_owner_api.owner_projection_item
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY owner_projection_head_migrator
  ON qc2_owner_api.owner_projection_head
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY owner_projection_watermark_migrator
  ON qc2_owner_api.owner_projection_watermark
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);
CREATE POLICY owner_projection_access_audit_migrator
  ON qc2_owner_api.owner_projection_access_audit
  FOR ALL TO qc2_migrator USING (true) WITH CHECK (true);

REVOKE ALL ON ALL TABLES IN SCHEMA qc2_owner_api
FROM PUBLIC, qc2_runtime_owner_api;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA qc2_owner_api
FROM PUBLIC, qc2_runtime_owner_api;

CREATE FUNCTION qc2_owner_api.owner_projection_source_allowed(
  p_view_name text,
  p_target_schema_name text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $function$
  SELECT CASE p_view_name
    WHEN 'today' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.models_prediction.PredictionSeal.v1',
      'qc2.time_operation.MarketSession.v1',
      'qc2.time_operation.ReadinessAssessment.v1'
    ]::text[])
    WHEN 'predictions' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.models_prediction.Prediction.v1'
    ]::text[])
    WHEN 'validation' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.validation.QualificationReceipt.v1',
      'qc2.validation.ValidationReport.v1'
    ]::text[])
    WHEN 'models' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.models_prediction.ModelManifest.v1',
      'qc2.governance_owner.ChampionPointer.v1'
    ]::text[])
    WHEN 'system' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.time_operation.ReadinessAssessment.v1'
    ]::text[])
    WHEN 'positions' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.execution.Position.v1'
    ]::text[])
    WHEN 'alerts' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.governance_owner.Alert.v1',
      'qc2.execution.ReconciliationReport.v1'
    ]::text[])
    WHEN 'reports' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.validation.ValidationReport.v1',
      'qc2.execution.ReconciliationReport.v1'
    ]::text[])
    WHEN 'evidence' THEN p_target_schema_name = ANY (ARRAY[
      'qc2.integrity_build.EvidenceEvent.v1',
      'qc2.integrity_build.Checkpoint.v1'
    ]::text[])
    ELSE false
  END
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_advance_source(
  p_environment_namespace text,
  p_view_name text,
  p_source_highwater_sequence bigint
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api
AS $function$
DECLARE
  v_current bigint;
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production')
     OR p_view_name NOT IN (
       'today','predictions','validation','models','system',
       'positions','alerts','reports','evidence'
     )
     OR p_source_highwater_sequence NOT BETWEEN 0 AND 9007199254740991 THEN
    RAISE EXCEPTION 'invalid owner projection watermark' USING ERRCODE = '22023';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      p_environment_namespace || ':' || p_view_name,
      0
    )
  );
  SELECT watermark.source_highwater_sequence
    INTO v_current
    FROM qc2_owner_api.owner_projection_watermark AS watermark
   WHERE watermark.environment_namespace = p_environment_namespace
     AND watermark.view_name = p_view_name
   FOR UPDATE;

  IF FOUND AND p_source_highwater_sequence < v_current THEN
    RAISE EXCEPTION 'owner projection watermark cannot move backwards'
      USING ERRCODE = '23514';
  END IF;

  INSERT INTO qc2_owner_api.owner_projection_watermark(
    environment_namespace, view_name, source_highwater_sequence, updated_at
  )
  VALUES (
    p_environment_namespace, p_view_name, p_source_highwater_sequence,
    pg_catalog.clock_timestamp()
  )
  ON CONFLICT (environment_namespace, view_name)
  DO UPDATE SET
    source_highwater_sequence = EXCLUDED.source_highwater_sequence,
    updated_at = EXCLUDED.updated_at;

  RETURN pg_catalog.jsonb_build_object(
    'status', 'ADVANCED',
    'source_highwater_sequence', p_source_highwater_sequence
  );
END
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_rebuild(
  p_environment_namespace text,
  p_view_name text,
  p_projection_sequence bigint,
  p_source_sequence bigint,
  p_source_highwater_sequence bigint,
  p_built_at timestamptz,
  p_freshness_deadline timestamptz,
  p_source_refs jsonb,
  p_items jsonb,
  p_snapshot_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api, qc2_integrity_build
AS $function$
DECLARE
  v_current bigint;
  v_item jsonb;
  v_item_id text;
  v_sort_key text;
  v_item_sequence bigint;
  v_source_ref jsonb;
  v_payload jsonb;
  v_receipt_hash text;
  v_expected_hash text;
  v_receipt_body jsonb;
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production')
     OR p_view_name NOT IN (
       'today','predictions','validation','models','system',
       'positions','alerts','reports','evidence'
     )
     OR p_projection_sequence NOT BETWEEN 1 AND 9007199254740991
     OR p_source_sequence NOT BETWEEN 0 AND 9007199254740991
     OR p_source_highwater_sequence NOT BETWEEN p_source_sequence AND 9007199254740991
     OR p_built_at IS NULL
     OR p_freshness_deadline <= p_built_at
     OR pg_catalog.jsonb_typeof(p_source_refs) <> 'array'
     OR pg_catalog.jsonb_array_length(p_source_refs) > 100000
     OR pg_catalog.jsonb_typeof(p_items) <> 'array'
     OR pg_catalog.jsonb_array_length(p_items) > 100000
     OR p_snapshot_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid owner projection rebuild request' USING ERRCODE = '22023';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      p_environment_namespace || ':' || p_view_name,
      0
    )
  );
  SELECT head.projection_sequence
    INTO v_current
    FROM qc2_owner_api.owner_projection_head AS head
   WHERE head.environment_namespace = p_environment_namespace
     AND head.view_name = p_view_name
   FOR UPDATE;
  IF NOT FOUND THEN
    v_current := 0;
  END IF;
  IF p_projection_sequence <> v_current + 1 THEN
    RAISE EXCEPTION 'owner projection sequence is not the next generation'
      USING ERRCODE = '23514';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM pg_catalog.jsonb_array_elements(p_source_refs) AS ref(value)
     WHERE pg_catalog.jsonb_typeof(ref.value) <> 'object'
        OR ref.value->>'target_schema_name'
           !~ '^qc2\.[A-Za-z0-9_.-]+\.v[1-9][0-9]*$'
        OR NOT qc2_owner_api.owner_projection_source_allowed(
          p_view_name,
          ref.value->>'target_schema_name'
        )
        OR ref.value->>'target_id' IS NULL
         OR pg_catalog.char_length(ref.value->>'target_id') NOT BETWEEN 1 AND 128
        OR (
          ref.value->>'content_hash' IS NOT NULL
          AND ref.value->>'content_hash' !~ '^[0-9a-f]{64}$'
        )
  ) THEN
    RAISE EXCEPTION 'invalid owner projection source reference'
      USING ERRCODE = '23514';
  END IF;
  IF (
    SELECT pg_catalog.count(*) <> pg_catalog.count(DISTINCT ref.value)
      FROM pg_catalog.jsonb_array_elements(p_source_refs) AS ref(value)
  ) THEN
    RAISE EXCEPTION 'duplicate owner projection source reference'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM pg_catalog.jsonb_array_elements(p_source_refs) AS ref(value)
     WHERE NOT EXISTS (
       SELECT 1
         FROM pg_catalog.jsonb_array_elements(p_items) AS item(value)
        WHERE item.value->'source_ref' = ref.value
     )
  ) THEN
    RAISE EXCEPTION 'owner projection source reference is unused'
      USING ERRCODE = '23514';
  END IF;

  INSERT INTO qc2_owner_api.owner_projection_snapshot(
    environment_namespace, view_name, projection_sequence, source_sequence,
    built_at, freshness_deadline, source_refs, snapshot_hash
  )
  VALUES (
    p_environment_namespace, p_view_name, p_projection_sequence,
    p_source_sequence, p_built_at, p_freshness_deadline, p_source_refs,
    p_snapshot_hash
  );

  FOR v_item IN
    SELECT item.value
      FROM pg_catalog.jsonb_array_elements(p_items) AS item(value)
  LOOP
    v_item_id := v_item->>'item_id';
    v_sort_key := v_item->>'sort_key';
    v_item_sequence := (v_item->>'source_sequence')::bigint;
    v_source_ref := v_item->'source_ref';
    v_payload := v_item->'payload';
    v_receipt_hash := v_item->>'receipt_hash';

    IF pg_catalog.jsonb_typeof(v_item) <> 'object'
       OR v_item_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR pg_catalog.octet_length(v_sort_key) > 256
       OR v_sort_key !~ '^[ -~]*$'
       OR v_item_sequence NOT BETWEEN 1 AND p_source_sequence
       OR pg_catalog.jsonb_typeof(v_source_ref) <> 'object'
       OR v_source_ref->>'target_schema_name' IS NULL
       OR NOT qc2_owner_api.owner_projection_source_allowed(
         p_view_name,
         v_source_ref->>'target_schema_name'
       )
       OR pg_catalog.jsonb_typeof(v_payload) <> 'object'
       OR v_receipt_hash !~ '^[0-9a-f]{64}$'
       OR NOT (p_source_refs @> pg_catalog.jsonb_build_array(v_source_ref)) THEN
      RAISE EXCEPTION 'invalid owner projection item' USING ERRCODE = '23514';
    END IF;

    v_receipt_body := pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.owner_api.OwnerReadSourceReceipt.v1',
      'schema_version', '1.0',
      'environment_namespace', p_environment_namespace,
      'view_name', p_view_name,
      'source_sequence', v_item_sequence,
      'item_id', v_item_id,
      'sort_key', v_sort_key,
      'source_ref', v_source_ref,
      'payload', v_payload
    );
    v_expected_hash := qc2_integrity_build.hash_json(
      'qc2.owner_api.read_source_receipt.v1',
      v_receipt_body
    );
    IF v_receipt_hash <> v_expected_hash THEN
      RAISE EXCEPTION 'owner projection source receipt hash mismatch'
        USING ERRCODE = '23514';
    END IF;

    INSERT INTO qc2_owner_api.owner_projection_item(
      environment_namespace, view_name, projection_sequence, item_id,
      sort_key, source_sequence, source_ref, payload, receipt_hash
    )
    VALUES (
      p_environment_namespace, p_view_name, p_projection_sequence,
      v_item_id, v_sort_key, v_item_sequence, v_source_ref, v_payload,
      v_receipt_hash
    );
  END LOOP;

  INSERT INTO qc2_owner_api.owner_projection_watermark(
    environment_namespace, view_name, source_highwater_sequence, updated_at
  )
  VALUES (
    p_environment_namespace, p_view_name, p_source_highwater_sequence,
    pg_catalog.clock_timestamp()
  )
  ON CONFLICT (environment_namespace, view_name)
  DO UPDATE SET
    source_highwater_sequence = GREATEST(
      qc2_owner_api.owner_projection_watermark.source_highwater_sequence,
      EXCLUDED.source_highwater_sequence
    ),
    updated_at = EXCLUDED.updated_at;

  INSERT INTO qc2_owner_api.owner_projection_head(
    environment_namespace, view_name, projection_sequence, updated_at
  )
  VALUES (
    p_environment_namespace, p_view_name, p_projection_sequence,
    pg_catalog.clock_timestamp()
  )
  ON CONFLICT (environment_namespace, view_name)
  DO UPDATE SET
    projection_sequence = EXCLUDED.projection_sequence,
    updated_at = EXCLUDED.updated_at;

  DELETE FROM qc2_owner_api.owner_projection_snapshot AS old_snapshot
   WHERE old_snapshot.environment_namespace = p_environment_namespace
     AND old_snapshot.view_name = p_view_name
     AND old_snapshot.projection_sequence IN (
       SELECT prior.projection_sequence
         FROM qc2_owner_api.owner_projection_snapshot AS prior
        WHERE prior.environment_namespace = p_environment_namespace
          AND prior.view_name = p_view_name
        ORDER BY prior.projection_sequence DESC
        OFFSET 5
     );

  RETURN pg_catalog.jsonb_build_object(
    'status', 'BUILT',
    'projection_sequence', p_projection_sequence,
    'source_sequence', p_source_sequence,
    'source_highwater_sequence', p_source_highwater_sequence
  );
END
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_page(
  p_environment_namespace text,
  p_view_name text,
  p_limit integer,
  p_after_sort_key text,
  p_after_item_id text,
  p_projection_sequence bigint
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api
AS $function$
DECLARE
  v_snapshot qc2_owner_api.owner_projection_snapshot%ROWTYPE;
  v_page_items jsonb;
  v_page_source_refs jsonb;
  v_has_more boolean;
  v_total_count bigint;
  v_highwater bigint;
  v_lag bigint;
  v_stale boolean;
  v_data_state text;
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production')
     OR p_view_name NOT IN (
       'today','predictions','validation','models','system',
       'positions','alerts','reports','evidence'
     )
     OR p_limit NOT BETWEEN 1 AND 1000
     OR ((p_after_sort_key IS NULL) <> (p_after_item_id IS NULL))
     OR (p_after_sort_key IS NOT NULL AND (
       pg_catalog.octet_length(p_after_sort_key) > 256
       OR p_after_sort_key !~ '^[ -~]*$'
       OR p_after_item_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
     ))
     OR (p_projection_sequence IS NOT NULL AND
         p_projection_sequence NOT BETWEEN 1 AND 9007199254740991) THEN
    RAISE EXCEPTION 'invalid owner projection page request' USING ERRCODE = '22023';
  END IF;

  SELECT snapshot.*
    INTO v_snapshot
    FROM qc2_owner_api.owner_projection_head AS head
    JOIN qc2_owner_api.owner_projection_snapshot AS snapshot
      ON snapshot.environment_namespace = head.environment_namespace
     AND snapshot.view_name = head.view_name
     AND snapshot.projection_sequence = COALESCE(
       p_projection_sequence, head.projection_sequence
     )
   WHERE head.environment_namespace = p_environment_namespace
     AND head.view_name = p_view_name;
  IF NOT FOUND THEN
    IF EXISTS (
      SELECT 1 FROM qc2_owner_api.owner_projection_head AS head
       WHERE head.environment_namespace = p_environment_namespace
         AND head.view_name = p_view_name
    ) THEN
      RETURN pg_catalog.jsonb_build_object('status', 'CURSOR_EXPIRED');
    END IF;
    RETURN pg_catalog.jsonb_build_object('status', 'UNAVAILABLE');
  END IF;

  SELECT COALESCE(watermark.source_highwater_sequence, 0)
    INTO v_highwater
    FROM (SELECT 1) AS singleton
    LEFT JOIN qc2_owner_api.owner_projection_watermark AS watermark
      ON watermark.environment_namespace = p_environment_namespace
     AND watermark.view_name = p_view_name;
  v_lag := GREATEST(0, v_highwater - v_snapshot.source_sequence);
  v_stale := v_lag > 0
    OR v_snapshot.freshness_deadline <= pg_catalog.clock_timestamp();
  SELECT pg_catalog.count(*)
    INTO v_total_count
    FROM qc2_owner_api.owner_projection_item AS item
   WHERE item.environment_namespace = p_environment_namespace
     AND item.view_name = p_view_name
     AND item.projection_sequence = v_snapshot.projection_sequence;
  v_data_state := CASE
    WHEN v_stale THEN 'STALE'
    WHEN v_total_count = 0 THEN 'EMPTY'
    ELSE 'CURRENT'
  END;

  WITH selected AS (
    SELECT
      item.item_id,
      item.sort_key,
      item.source_sequence,
      item.source_ref,
      item.payload,
      item.receipt_hash,
      pg_catalog.row_number() OVER (
        ORDER BY item.sort_key COLLATE "C", item.item_id COLLATE "C"
      ) AS row_number
    FROM qc2_owner_api.owner_projection_item AS item
    WHERE item.environment_namespace = p_environment_namespace
      AND item.view_name = p_view_name
      AND item.projection_sequence = v_snapshot.projection_sequence
      AND (
        p_after_sort_key IS NULL
        OR (item.sort_key COLLATE "C", item.item_id COLLATE "C")
           > (p_after_sort_key COLLATE "C", p_after_item_id COLLATE "C")
      )
    ORDER BY item.sort_key COLLATE "C", item.item_id COLLATE "C"
    LIMIT p_limit + 1
  )
  SELECT
    COALESCE(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'item_id', selected.item_id,
          'sort_key', selected.sort_key,
          'source_sequence', selected.source_sequence,
          'source_ref', selected.source_ref,
          'payload', selected.payload,
          'receipt_hash', selected.receipt_hash
        ) ORDER BY selected.row_number
      ) FILTER (WHERE selected.row_number <= p_limit),
      '[]'::jsonb
    ),
    COALESCE(pg_catalog.max(selected.row_number) > p_limit, false)
    INTO v_page_items, v_has_more
    FROM selected;

  SELECT COALESCE(
      pg_catalog.jsonb_agg(
        refs.source_ref
        ORDER BY refs.source_ref::text COLLATE "C"
      ),
      '[]'::jsonb
    )
    INTO v_page_source_refs
    FROM (
      SELECT DISTINCT selected_item.value->'source_ref' AS source_ref
        FROM pg_catalog.jsonb_array_elements(v_page_items)
          AS selected_item(value)
    ) AS refs;

  RETURN pg_catalog.jsonb_build_object(
    'status', 'OK',
    'page', pg_catalog.jsonb_build_object(
      'projection_sequence', v_snapshot.projection_sequence,
      'source_sequence', v_snapshot.source_sequence,
      'source_highwater_sequence', v_highwater,
      'lag', v_lag,
      'stale', v_stale,
      'data_state', v_data_state,
      'built_at', v_snapshot.built_at,
      'freshness_deadline', v_snapshot.freshness_deadline,
      'source_refs', v_page_source_refs,
      'items', v_page_items
    ),
    'has_more', v_has_more
  );
END
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_evidence_detail(
  p_environment_namespace text,
  p_item_id text
)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api
AS $function$
  SELECT CASE
    WHEN head.projection_sequence IS NULL THEN
      pg_catalog.jsonb_build_object('status', 'UNAVAILABLE')
    WHEN item.item_id IS NULL THEN
      pg_catalog.jsonb_build_object('status', 'NOT_FOUND')
    ELSE
      pg_catalog.jsonb_build_object(
        'status', 'FOUND',
        'projection_sequence', head.projection_sequence,
        'item', pg_catalog.jsonb_build_object(
          'item_id', item.item_id,
          'sort_key', item.sort_key,
          'source_sequence', item.source_sequence,
          'source_ref', item.source_ref,
          'payload', item.payload,
          'receipt_hash', item.receipt_hash
        )
      )
  END
  FROM (SELECT 1) AS singleton
  LEFT JOIN qc2_owner_api.owner_projection_head AS head
    ON head.environment_namespace = p_environment_namespace
   AND head.view_name = 'evidence'
  LEFT JOIN qc2_owner_api.owner_projection_item AS item
    ON item.environment_namespace = p_environment_namespace
   AND item.view_name = 'evidence'
   AND item.projection_sequence = head.projection_sequence
   AND item.item_id = p_item_id
  WHERE p_environment_namespace IN ('development','test','research','production')
    AND p_item_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_diagnostics(
  p_environment_namespace text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api
AS $function$
DECLARE
  v_views jsonb;
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production') THEN
    RAISE EXCEPTION 'invalid owner projection environment' USING ERRCODE = '22023';
  END IF;

  WITH view_names(view_name) AS (
    VALUES
      ('today'), ('predictions'), ('validation'), ('models'), ('system'),
      ('positions'), ('alerts'), ('reports'), ('evidence')
  ),
  status_rows AS (
    SELECT
      view_names.view_name,
      COALESCE(head.projection_sequence, 0) AS projection_sequence,
      COALESCE(snapshot.source_sequence, 0) AS source_sequence,
      COALESCE(watermark.source_highwater_sequence, 0)
        AS source_highwater_sequence,
      snapshot.built_at,
      (
        head.projection_sequence IS NULL
        OR COALESCE(watermark.source_highwater_sequence, 0)
           > COALESCE(snapshot.source_sequence, 0)
        OR snapshot.freshness_deadline <= pg_catalog.clock_timestamp()
      ) AS stale
    FROM view_names
    LEFT JOIN qc2_owner_api.owner_projection_head AS head
      ON head.environment_namespace = p_environment_namespace
     AND head.view_name = view_names.view_name
    LEFT JOIN qc2_owner_api.owner_projection_snapshot AS snapshot
      ON snapshot.environment_namespace = head.environment_namespace
     AND snapshot.view_name = head.view_name
     AND snapshot.projection_sequence = head.projection_sequence
    LEFT JOIN qc2_owner_api.owner_projection_watermark AS watermark
      ON watermark.environment_namespace = p_environment_namespace
     AND watermark.view_name = view_names.view_name
  )
  SELECT pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_object(
      'view_name', status_rows.view_name,
      'projection_sequence', status_rows.projection_sequence,
      'source_sequence', status_rows.source_sequence,
      'source_highwater_sequence', status_rows.source_highwater_sequence,
      'lag', GREATEST(
        0, status_rows.source_highwater_sequence - status_rows.source_sequence
      ),
      'stale', status_rows.stale,
      'built_at', status_rows.built_at
    ) ORDER BY status_rows.view_name COLLATE "C"
  )
  INTO v_views
  FROM status_rows;

  RETURN pg_catalog.jsonb_build_object(
    'status', 'OK',
    'diagnostics', pg_catalog.jsonb_build_object(
      'schema_name', 'qc2.owner_api.OwnerReadDiagnostics.v1',
      'environment_namespace', p_environment_namespace,
      'views', COALESCE(v_views, '[]'::jsonb)
    )
  );
END
$function$;

CREATE FUNCTION qc2_owner_api.owner_projection_record_export(
  p_environment_namespace text,
  p_session_record_id uuid,
  p_view_name text,
  p_projection_sequence bigint,
  p_item_count integer,
  p_response_bytes integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, qc2_owner_api, qc2_governance_owner
AS $function$
DECLARE
  v_session qc2_governance_owner.identity_session%ROWTYPE;
  v_device qc2_governance_owner.identity_device%ROWTYPE;
BEGIN
  IF p_environment_namespace NOT IN ('development','test','research','production')
     OR p_view_name NOT IN (
       'today','predictions','validation','models','system',
       'positions','alerts','reports','evidence'
     )
     OR p_projection_sequence NOT BETWEEN 1 AND 9007199254740991
     OR p_item_count NOT BETWEEN 0 AND 1000
     OR p_response_bytes NOT BETWEEN 0 AND 1048576 THEN
    RAISE EXCEPTION 'invalid owner export audit request' USING ERRCODE = '22023';
  END IF;

  SELECT session.*
    INTO v_session
    FROM qc2_governance_owner.identity_session AS session
   WHERE session.environment_namespace = p_environment_namespace
     AND session.id = p_session_record_id;
  IF NOT FOUND
     OR v_session.revoked_at IS NOT NULL
     OR (v_session.record->>'expires_at')::timestamptz <= pg_catalog.clock_timestamp()
     OR NOT (v_session.record->'scope_refs' @> '["OWNER_READ"]'::jsonb) THEN
    RAISE EXCEPTION 'owner export session is not active' USING ERRCODE = '42501';
  END IF;

  SELECT device.*
    INTO v_device
    FROM qc2_governance_owner.identity_device AS device
   WHERE device.environment_namespace = p_environment_namespace
     AND device.id = v_session.device_id;
  IF NOT FOUND OR v_device.revoked_at IS NOT NULL THEN
    RAISE EXCEPTION 'owner export device is not active' USING ERRCODE = '42501';
  END IF;

  INSERT INTO qc2_owner_api.owner_projection_access_audit(
    environment_namespace, session_record_id, view_name,
    projection_sequence, item_count, response_bytes, requested_at
  )
  VALUES (
    p_environment_namespace, p_session_record_id, p_view_name,
    p_projection_sequence, p_item_count, p_response_bytes,
    pg_catalog.clock_timestamp()
  );
  RETURN pg_catalog.jsonb_build_object('status', 'RECORDED');
END
$function$;

REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_source_allowed(
  text, text
) FROM PUBLIC, qc2_runtime_owner_api;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_advance_source(
  text, text, bigint
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_rebuild(
  text, text, bigint, bigint, bigint, timestamptz, timestamptz,
  jsonb, jsonb, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_page(
  text, text, integer, text, text, bigint
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_evidence_detail(
  text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_diagnostics(text)
FROM PUBLIC;
REVOKE ALL ON FUNCTION qc2_owner_api.owner_projection_record_export(
  text, uuid, text, bigint, integer, integer
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_advance_source(
  text, text, bigint
) TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_rebuild(
  text, text, bigint, bigint, bigint, timestamptz, timestamptz,
  jsonb, jsonb, text
) TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_page(
  text, text, integer, text, text, bigint
) TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_evidence_detail(
  text, text
) TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_diagnostics(text)
TO qc2_runtime_owner_api;
GRANT EXECUTE ON FUNCTION qc2_owner_api.owner_projection_record_export(
  text, uuid, text, bigint, integer, integer
) TO qc2_runtime_owner_api;

RESET ROLE;
