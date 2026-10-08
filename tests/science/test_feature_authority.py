from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from qc2_contracts.runtime import canonical_json_bytes, validate_contract, verify_content_hash
from qc2_science import (
    ContractRef,
    DailyFeatureBar,
    FeatureInput,
    FeatureInputError,
    ProductionActivationDenied,
    SimilarityPrototype,
    TemporalAccessEvidence,
    TemporalLeakageError,
    build_feature_specs,
    compute_feature_snapshot,
    fixture_daily_profile,
    materialize_feature_registry,
)
from qc2_science.engine import _format_value

ROOT = Path(__file__).resolve().parents[2]
CODE_HASH = "c" * 64
ENVIRONMENT_HASH = "b" * 64
FIXED_CREATED = "2026-01-01T00:00:00Z"
RETURN_FEATURES = {f"return_{period}" for period in (1, 2, 3, 5, 10, 20)}
SIMILARITY_FEATURES = (
    "return_1",
    "return_3",
    "return_5",
    "return_20",
    "momentum_slope",
    "volatility_expansion",
    "relative_volume",
    "trend_slope",
    "exhaustion_pressure",
)


def _uuid7(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    timestamp_ms = 1_767_225_600_000
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (rand_a << 64)
        | (2 << 62)
        | rand_b
    )
    return str(UUID(int=value))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ref(schema_name: str, key: str) -> ContractRef:
    return ContractRef(schema_name, _uuid7(f"{schema_name}:{key}"), _hash(f"{schema_name}:{key}"))


@pytest.fixture(scope="module")
def registry():
    profile = fixture_daily_profile()
    specs = build_feature_specs(profile)
    return materialize_feature_registry(
        profile,
        definition_ids={spec.stable_key: _uuid7(f"definition:{spec.stable_key}") for spec in specs},
        registry_id=_uuid7("feature-registry"),
        created_at=FIXED_CREATED,
        effective_from="2026-01-01",
        implementation_hash=CODE_HASH,
        environment_namespace="test",
    )


def make_inputs(
    *,
    bar_count: int = 80,
    start: date = date(2026, 1, 1),
    missing_indices: tuple[int, ...] = (),
    flat: bool = False,
    absent_volume: bool = False,
    volume_scale: Decimal = Decimal(1),
    price_scale: Decimal = Decimal(1),
    adjustment_key: str = "adjustment-v1",
    symbol_change: bool = False,
) -> FeatureInput:
    sessions = tuple(start + timedelta(days=index) for index in range(bar_count))
    target = sessions[-1]
    cutoff = datetime.combine(target + timedelta(days=1), time(1), tzinfo=timezone.utc)
    instrument = _ref("qc2.identity_market.Instrument.v1", "instrument-main")
    calendar = _ref("qc2.time_operation.CalendarManifest.v1", "calendar-fixture")
    adjustment = _ref("qc2.identity_market.AdjustmentManifest.v1", adjustment_key)
    assignment_a = _ref("qc2.identity_market.SymbolAssignment.v1", "symbol-assignment-a")
    assignment_b = _ref("qc2.identity_market.SymbolAssignment.v1", "symbol-assignment-b")
    bars: list[DailyFeatureBar] = []
    excluded = set(missing_indices)
    switch_index = bar_count // 2

    for index, session in enumerate(sessions):
        if index in excluded:
            continue
        if flat:
            open_value = close_value = high_value = low_value = Decimal(100) * price_scale
            volume_value: Decimal | None = Decimal(0)
        else:
            base_close = Decimal(100) + Decimal(index) / 2 + Decimal(index % 7) / 10
            close_value = base_close * price_scale
            open_value = (
                base_close - Decimal("0.15")
                if index % 2
                else base_close + Decimal("0.12")
            ) * price_scale
            high_value = (max(base_close, open_value / price_scale) + Decimal("0.50")) * price_scale
            low_value = (min(base_close, open_value / price_scale) - Decimal("0.40")) * price_scale
            volume_value = Decimal(1_000 + index * 17 + (index % 5) * 11) * volume_scale
        if absent_volume:
            volume_value = None

        assignment_ref = assignment_a
        effective_from = sessions[0]
        effective_to = None
        if symbol_change and index >= switch_index:
            assignment_ref = assignment_b
            effective_from = sessions[switch_index]
        elif symbol_change:
            effective_to = sessions[switch_index] - timedelta(days=1)

        known_at = datetime.combine(session + timedelta(days=1), time(0), tzinfo=timezone.utc)
        source_ref = _ref(
            "qc2.identity_market.DailyBar.v1",
            f"bar:{session.isoformat()}:{open_value}:{high_value}:{low_value}:{close_value}:{volume_value}",
        )
        bars.append(
            DailyFeatureBar(
                session_id=session,
                open_price=open_value,
                high_price=high_value,
                low_price=low_value,
                close_price=close_value,
                volume=volume_value,
                known_at=known_at,
                source_ref=source_ref,
                instrument_ref=instrument,
                symbol_assignment_ref=assignment_ref,
                symbol_assignment_instrument_ref=instrument,
                symbol_assignment_known_at=datetime.combine(
                    start - timedelta(days=20), time(0), tzinfo=timezone.utc
                ),
                symbol_assignment_effective_from=effective_from,
                symbol_assignment_effective_to=effective_to,
                adjustment_ref=adjustment,
                share_basis_key=f"common-basis:{adjustment_key}",
            )
        )
    return FeatureInput(
        target_session=target,
        decision_cutoff=cutoff,
        calendar_sessions=sessions,
        bars=tuple(bars),
        instrument_ref=instrument,
        calendar_ref=calendar,
        adjustment_ref=adjustment,
        instrument_known_at=datetime.combine(start - timedelta(days=100), time(0), tzinfo=timezone.utc),
        calendar_known_at=datetime.combine(start - timedelta(days=20), time(0), tzinfo=timezone.utc),
        adjustment_known_at=datetime.combine(start - timedelta(days=10), time(0), tzinfo=timezone.utc),
    )


def _snapshot(inputs: FeatureInput, registry, key: str = "snapshot"):
    created = inputs.decision_cutoff + timedelta(seconds=1)
    return compute_feature_snapshot(
        inputs,
        registry,
        snapshot_id=_uuid7(key),
        created_at=created,
        code_hash=CODE_HASH,
        environment_fingerprint=ENVIRONMENT_HASH,
    )


def _features(snapshot: dict) -> dict[str, dict[str, str]]:
    return {item["feature_id"]: item for item in snapshot["feature_values"]}


def _numeric(snapshot: dict, key: str) -> Decimal:
    record = _features(snapshot)[key]
    assert "value" in record
    return Decimal(record["value"])


def test_registry_contracts_cover_required_families_and_topological_column_order(registry):
    assert RETURN_FEATURES.issubset(registry.ordered_feature_ids)
    expected_families = {
        "returns",
        "momentum",
        "directional_persistence",
        "range",
        "volatility",
        "volume",
        "price_volume",
        "gaps",
        "candle_geometry",
        "rolling_structure",
        "breakout",
        "trend",
        "reversal",
        "exhaustion",
        "historical_similarity",
    }
    assert {spec.research_family for spec in registry.definitions} == expected_families
    positions = {key: index for index, key in enumerate(registry.ordered_feature_ids)}
    for spec in registry.definitions:
        for dependency in spec.dependencies:
            assert positions[dependency] < positions[spec.stable_key]
    assert list(registry.registry_contract["ordered_feature_ids"]) == list(registry.ordered_feature_ids)
    validate_contract("FeatureRegistry", registry.registry_contract)
    verify_content_hash("FeatureRegistry", registry.registry_contract)
    for record in registry.definition_contracts.values():
        validate_contract("FeatureDefinition", record)
        verify_content_hash("FeatureDefinition", record)
        assert record["precision"] == 12 or record["research_family"] == "breakout"
        if record["stable_key"] in {"breakout_attempt_count", "breakout_failure_count"}:
            assert record["output_dtype"] == "INTEGER"
            assert record["precision"] == 0
        else:
            assert record["output_dtype"] == "DECIMAL"
        assert record["parameter_profile"] == "fixture_daily_v1"


def test_snapshot_is_canonical_and_reordered_inputs_produce_identical_payload(registry):
    inputs = make_inputs()
    original = _snapshot(inputs, registry, "ordered-snapshot")
    reordered = _snapshot(
        replace(inputs, bars=tuple(reversed(inputs.bars))),
        registry,
        "ordered-snapshot",
    )
    assert canonical_json_bytes(original) == canonical_json_bytes(reordered)
    assert len(original["feature_values"]) == len(registry.ordered_feature_ids)
    assert [item["feature_id"] for item in original["feature_values"]] == list(
        registry.ordered_feature_ids
    )
    assert all(
        item["output_dtype"]
        == registry.definition_contracts[item["feature_id"]]["output_dtype"]
        for item in original["feature_values"]
    )
    assert all(("value" in item) != ("missing_reason" in item) for item in original["feature_values"])
    verify_content_hash("FeatureSnapshot", original)


def test_flat_zero_range_zero_volume_and_absent_volume_are_reason_coded(registry):
    flat = _features(_snapshot(make_inputs(bar_count=40, flat=True), registry))
    assert Decimal(flat["true_range"]["value"]) == 0
    assert Decimal(flat["normalized_range"]["value"]) == 0
    assert flat["close_location_value"]["missing_reason"] == "DIVISION_BY_ZERO"
    assert flat["body_proportion"]["missing_reason"] == "DIVISION_BY_ZERO"
    assert flat["relative_volume"]["missing_reason"] == "DIVISION_BY_ZERO"
    assert flat["volatility_expansion"]["missing_reason"] == "DIVISION_BY_ZERO"
    assert flat["exhaustion_pressure"]["missing_reason"] == "DIVISION_BY_ZERO"

    no_volume = _features(_snapshot(make_inputs(bar_count=40, absent_volume=True), registry))
    for key in ("relative_volume", "volume_acceleration", "volume_slope", "accumulation"):
        assert no_volume[key]["missing_reason"] == "SOURCE_FIELD_MISSING"
    assert no_volume["price_volume_divergence"]["missing_reason"] == "SOURCE_FIELD_MISSING"


def test_ipo_warmup_and_sparse_calendar_history_are_distinguished(registry):
    ipo = _features(_snapshot(make_inputs(bar_count=6), registry))
    assert ipo["return_5"].get("value") is not None
    assert ipo["return_20"]["missing_reason"] == "WARMUP_REQUIRED"

    sparse = _features(_snapshot(make_inputs(missing_indices=(75,)), registry))
    assert sparse["return_20"]["missing_reason"] == "SOURCE_FIELD_MISSING"
    assert sparse["body_proportion"].get("value") is not None


def test_future_bars_future_metadata_and_duplicate_sessions_fail_closed(registry):
    inputs = make_inputs()
    target_bar = inputs.bars[-1]
    future_bar = replace(
        target_bar,
        session_id=inputs.target_session + timedelta(days=1),
        known_at=inputs.decision_cutoff,
    )
    with pytest.raises(TemporalLeakageError):
        _snapshot(replace(inputs, bars=inputs.bars + (future_bar,)), registry)

    future_known_bar = replace(target_bar, known_at=inputs.decision_cutoff + timedelta(seconds=1))
    with pytest.raises(TemporalLeakageError):
        _snapshot(replace(inputs, bars=inputs.bars[:-1] + (future_known_bar,)), registry)

    future_metadata = replace(
        inputs,
        instrument_known_at=inputs.decision_cutoff + timedelta(seconds=1),
    )
    with pytest.raises(TemporalLeakageError):
        _snapshot(future_metadata, registry)

    late_assignment_bar = replace(
        target_bar,
        symbol_assignment_known_at=inputs.decision_cutoff + timedelta(seconds=1),
    )
    with pytest.raises(TemporalLeakageError):
        _snapshot(replace(inputs, bars=inputs.bars[:-1] + (late_assignment_bar,)), registry)

    with pytest.raises(FeatureInputError, match="duplicate daily bar"):
        _snapshot(replace(inputs, bars=inputs.bars + (target_bar,)), registry)


def test_symbol_reassignment_preserves_instrument_identity_and_cross_instrument_mix_is_rejected(registry):
    inputs = make_inputs(symbol_change=True)
    snapshot = _snapshot(inputs, registry)
    assignment_refs = {
        item["target_id"]
        for item in snapshot["source_refs"]
        if item["target_schema_name"] == "qc2.identity_market.SymbolAssignment.v1"
    }
    assert len(assignment_refs) == 2

    other_instrument = _ref("qc2.identity_market.Instrument.v1", "other-instrument")
    wrong_assignment_bar = replace(
        inputs.bars[-1],
        symbol_assignment_instrument_ref=other_instrument,
    )
    with pytest.raises(FeatureInputError, match="different canonical instrument"):
        _snapshot(replace(inputs, bars=inputs.bars[:-1] + (wrong_assignment_bar,)), registry)

    wrong_bar = replace(inputs.bars[-1], instrument_ref=other_instrument)
    with pytest.raises(FeatureInputError, match="crosses canonical instrument"):
        _snapshot(replace(inputs, bars=inputs.bars[:-1] + (wrong_bar,)), registry)


def test_split_basis_and_scale_metamorphisms(registry):
    base_inputs = make_inputs()
    split_inputs = make_inputs(
        price_scale=Decimal("0.5"),
        volume_scale=Decimal(2),
        adjustment_key="post-split-common-basis",
    )
    base = _features(_snapshot(base_inputs, registry))
    split = _features(_snapshot(split_inputs, registry))
    invariant_keys = (
        "return_1",
        "return_2",
        "return_3",
        "return_5",
        "return_10",
        "return_20",
        "momentum_slope",
        "momentum_acceleration",
        "directional_persistence",
        "normalized_range",
        "volatility_expansion",
        "volatility_compression",
        "volatility_of_volatility",
        "relative_volume",
        "volume_acceleration",
        "volume_slope",
        "accumulation",
        "price_volume_divergence",
        "gap_return",
        "close_location_value",
        "body_proportion",
        "upper_wick_proportion",
        "lower_wick_proportion",
        "rolling_high_distance",
        "breakout_proximity",
        "breakout_attempt_count",
        "breakout_failure_count",
        "trend_slope",
        "reversal_score",
        "exhaustion_pressure",
    )
    for key in invariant_keys:
        assert base[key] == split[key], key
    assert Decimal(split["true_range"]["value"]) == Decimal(base["true_range"]["value"]) / 2
    assert abs(
        Decimal(split["atr"]["value"]) - Decimal(base["atr"]["value"]) / 2
    ) <= Decimal("0.000000000001")

    scaled_inputs = make_inputs(price_scale=Decimal(3), volume_scale=Decimal(5))
    scaled = _features(_snapshot(scaled_inputs, registry))
    for key in invariant_keys:
        assert base[key] == scaled[key], key
    assert Decimal(scaled["true_range"]["value"]) == Decimal(base["true_range"]["value"]) * 3
    assert Decimal(scaled["atr"]["value"]) == Decimal(base["atr"]["value"]) * 3

    mixed_basis_bar = replace(base_inputs.bars[-10], share_basis_key="unadjusted-after-split")
    with pytest.raises(FeatureInputError, match="mixes share bases"):
        _snapshot(replace(base_inputs, bars=base_inputs.bars[:-10] + (mixed_basis_bar,) + base_inputs.bars[-9:]), registry)


def test_large_volumes_and_decimal_output_precision(registry):
    snapshot = _snapshot(make_inputs(volume_scale=Decimal("1e50")), registry)
    values = _features(snapshot)
    for item in snapshot["feature_values"]:
        if "value" in item:
            number = Decimal(item["value"])
            assert number.is_finite()
            if item["output_dtype"] == "INTEGER":
                assert number == number.to_integral_value()
                assert "." not in item["value"]
            else:
                assert len(item["value"].split(".")[-1]) == 12
    assert Decimal(values["relative_volume"]["value"]) > 0


def test_decimal_output_rounding_is_half_even():
    assert _format_value(Decimal("1.2345678901235"), 12, "DECIMAL") == "1.234567890124"
    assert _format_value(Decimal("1.2345678901245"), 12, "DECIMAL") == "1.234567890124"


def test_similarity_uses_only_historical_registry_matched_receipted_prototypes(registry):
    inputs = make_inputs()
    base_snapshot = _snapshot(inputs, registry, "historical-source")
    base_values = _features(base_snapshot)
    vector = {key: Decimal(base_values[key]["value"]) for key in SIMILARITY_FEATURES}
    event_session = inputs.target_session - timedelta(days=2)
    available_at = inputs.decision_cutoff - timedelta(hours=2)
    access_at = inputs.decision_cutoff - timedelta(hours=1)
    past_snapshot_ref = _ref("qc2.scientific_definitions.FeatureSnapshot.v1", "prior-feature-snapshot")
    runner_source_ref = _ref("qc2.outcomes_research.RunnerGenome.v1", "runner-genome")
    runner_access = TemporalAccessEvidence(
        receipt_hash=_hash("runner-access-receipt"),
        artifact_hashes=(runner_source_ref.content_hash, past_snapshot_ref.content_hash),
        decision_cutoff=inputs.decision_cutoff,
        artifact_available_at=available_at,
        authorized_at=access_at,
    )
    runner = SimilarityPrototype(
        kind="RUNNER",
        source_ref=runner_source_ref,
        feature_snapshot_ref=past_snapshot_ref,
        feature_snapshot_session=event_session,
        event_session=event_session,
        available_at=available_at,
        registry_content_hash=registry.registry_contract["content_hash"],
        temporal_access_evidence=runner_access,
        feature_values=vector,
    )
    failure_source_ref = _ref("qc2.outcomes_research.FailureGenome.v1", "failure-genome")
    failure_snapshot_ref = _ref(
        "qc2.scientific_definitions.FeatureSnapshot.v1",
        "failure-snapshot",
    )
    failure = SimilarityPrototype(
        kind="FAILURE",
        source_ref=failure_source_ref,
        feature_snapshot_ref=failure_snapshot_ref,
        feature_snapshot_session=event_session,
        event_session=event_session,
        available_at=available_at,
        registry_content_hash=registry.registry_contract["content_hash"],
        temporal_access_evidence=TemporalAccessEvidence(
            receipt_hash=_hash("failure-access-receipt"),
            artifact_hashes=(failure_source_ref.content_hash, failure_snapshot_ref.content_hash),
            decision_cutoff=inputs.decision_cutoff,
            artifact_available_at=available_at,
            authorized_at=access_at,
        ),
        feature_values={key: -value for key, value in vector.items()},
    )
    result = _features(_snapshot(replace(inputs, prototypes=(failure, runner)), registry))
    assert Decimal(result["runner_similarity"]["value"]) == 1
    assert Decimal(result["failure_similarity"]["value"]) < 1

    future_event = replace(
        runner,
        event_session=inputs.target_session,
        feature_snapshot_session=inputs.target_session,
    )
    with pytest.raises(TemporalLeakageError, match="not strictly historical"):
        _snapshot(replace(inputs, prototypes=(future_event,)), registry)

    late_access = replace(
        runner,
        temporal_access_evidence=replace(
            runner.temporal_access_evidence,
            authorized_at=inputs.decision_cutoff + timedelta(seconds=1),
        ),
    )
    with pytest.raises(TemporalLeakageError, match="access receipt"):
        _snapshot(replace(inputs, prototypes=(late_access,)), registry)

    wrong_cutoff = replace(
        runner,
        temporal_access_evidence=replace(
            runner.temporal_access_evidence,
            decision_cutoff=inputs.decision_cutoff - timedelta(seconds=1),
        ),
    )
    with pytest.raises(TemporalLeakageError, match="different decision cutoff"):
        _snapshot(replace(inputs, prototypes=(wrong_cutoff,)), registry)

    wrong_availability = replace(runner, available_at=available_at - timedelta(minutes=1))
    with pytest.raises(TemporalLeakageError, match="availability differs"):
        _snapshot(replace(inputs, prototypes=(wrong_availability,)), registry)

    wrong_registry = replace(runner, registry_content_hash=_hash("other-registry"))
    with pytest.raises(FeatureInputError, match="different feature registry"):
        _snapshot(replace(inputs, prototypes=(wrong_registry,)), registry)


def test_fixture_profile_has_no_production_activation_path(registry):
    assert registry.profile.fixture_only is True
    profile = fixture_daily_profile()
    specs = build_feature_specs(profile)
    definition_ids = {
        spec.stable_key: _uuid7(f"production-definition:{spec.stable_key}")
        for spec in specs
    }
    with pytest.raises(ProductionActivationDenied):
        materialize_feature_registry(
            profile,
            definition_ids=definition_ids,
            registry_id=_uuid7("production-registry"),
            created_at=FIXED_CREATED,
            effective_from="2026-01-01",
            implementation_hash=CODE_HASH,
            environment_namespace="production",
        )


def test_feature_engine_has_no_outcome_import_or_external_side_effect_path():
    source_path = ROOT / "packages" / "science" / "src" / "qc2_science" / "engine.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_names.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not any("Outcome" in name or "outcome" in name for name in imported_names)
    assert "requests." not in source
    assert "httpx." not in source
    assert "fetch(" not in source
    assert "open(" not in source
