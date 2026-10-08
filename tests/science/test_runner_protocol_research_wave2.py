from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from qc2_science import (
    ContractRef,
    ProtocolEvidenceValue,
    ProtocolInputBundle,
    RunnerProtocolError,
    RunnerProtocolState,
    evaluate_runner_protocol,
    materialize_runner_protocol_definition,
    materialize_runner_protocol_registry,
    research_wave2_dependency_graphs,
    research_wave2_protocols,
)

FIXED_CUTOFF = "2026-01-03T20:00:00Z"
FIXED_CREATED = "2026-01-03T20:01:00Z"
KNOWN_AT = "2026-01-03T19:59:00Z"
FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"


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
    return ContractRef(schema_name, _uuid7(f"{schema_name}:{key}"), _hash(key))


def _specs():
    return research_wave2_protocols(_ref(FEATURE_SNAPSHOT_SCHEMA, "wave2-snapshot"))


def _spec(protocol_id: str):
    return next(item for item in _specs() if item.protocol_id == protocol_id)


def _definition(spec, key: str):
    return materialize_runner_protocol_definition(
        spec,
        record_id=_uuid7(f"definition:{key}"),
        created_at=FIXED_CREATED,
    )


def _bundle(
    spec,
    values: dict[str, Decimal | int | str],
    *,
    missingness: dict[str, str] | None = None,
    known_at: dict[str, str] | None = None,
) -> ProtocolInputBundle:
    missingness = missingness or {}
    known_at = known_at or {}
    evidence = []
    for requirement in spec.input_requirements:
        state = missingness.get(requirement.key, "PRESENT")
        evidence.append(
            ProtocolEvidenceValue(
                key=requirement.key,
                value=values.get(requirement.key) if state == "PRESENT" else None,
                unit=requirement.unit,
                uncertainty=Decimal("0"),
                missingness=state,
                source_ref=requirement.source_ref,
                known_at=(
                    known_at.get(requirement.key, KNOWN_AT) if state == "PRESENT" else None
                ),
            )
        )
    return ProtocolInputBundle(
        session_id=date(2026, 1, 3),
        instrument_ref=_ref(INSTRUMENT_SCHEMA, "wave2-instrument"),
        cutoff=FIXED_CUTOFF,
        values=tuple(evidence),
    )


def _evaluate(
    spec,
    key: str,
    values: dict[str, Decimal | int | str],
    *,
    missingness: dict[str, str] | None = None,
    known_at: dict[str, str] | None = None,
):
    return evaluate_runner_protocol(
        spec,
        _definition(spec, key),
        _bundle(spec, values, missingness=missingness, known_at=known_at),
        result_id=_uuid7(f"result:{key}"),
        created_at=FIXED_CREATED,
    )


def _registry(specs):
    definitions = tuple(
        _definition(spec, f"registry:{index}:{spec.protocol_id}")
        for index, spec in enumerate(specs)
    )
    return materialize_runner_protocol_registry(
        specs,
        definitions,
        registry_version=1,
        active_protocol_keys=(),
        effective_from=date(2026, 1, 3),
        record_id=_uuid7("wave2-registry"),
        created_at=FIXED_CREATED,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="research",
    )


def test_research_wave2_catalog_is_inactive_and_has_transitive_feature_graphs() -> None:
    specs = _specs()
    ids = [spec.protocol_id for spec in specs]
    assert len(ids) == len(set(ids)) == 6
    assert all(spec.protocol_namespace == "research" for spec in specs)
    assert all(spec.evidence_class == "SYNTHETIC_FIXTURE" for spec in specs)
    assert all(spec.environment_namespace == "research" for spec in specs)
    assert all(not spec.source_refs for spec in specs)

    graph = {
        protocol_id: dict(adjacency)
        for protocol_id, adjacency in research_wave2_dependency_graphs()
    }
    assert set(graph) == set(ids)
    assert graph["daily-breakout-confluence"]["breakout_proximity"] == (
        "rolling_high_distance",
    )
    assert graph["daily-reversal-location"]["reversal_score"] == ()
    assert graph["daily-price-volume-divergence-observation"][
        "price_volume_divergence"
    ] == ("accumulation", "return_20")
    assert "close_location_value" in graph[
        "daily-price-volume-divergence-observation"
    ]
    assert graph["daily-exhaustion-pressure-observation"]["exhaustion_pressure"] == (
        "atr",
        "close_location_value",
        "trend_slope",
        "true_range",
    )
    similarity_nodes = graph["historical-similarity-interface-observation"]
    assert set(similarity_nodes["runner_similarity"]) == {
        "return_1",
        "return_3",
        "return_5",
        "return_20",
        "momentum_slope",
        "volatility_expansion",
        "relative_volume",
        "trend_slope",
        "exhaustion_pressure",
    }
    assert set(similarity_nodes["failure_similarity"]) == set(
        similarity_nodes["runner_similarity"]
    )

    registry = _registry(specs)
    assert registry.registry_record.to_payload()["active_protocol_ids"] == []


def test_duplicate_protocol_ids_cannot_be_used_to_double_count_a_composite() -> None:
    spec = _specs()[0]
    with pytest.raises(RunnerProtocolError, match="protocol keys must be unique"):
        _registry((spec, spec))


def test_breakout_confluence_requires_all_daily_legs_and_respects_cutoff() -> None:
    spec = _spec("daily-breakout-confluence")
    values = {
        "breakout_proximity": Decimal("0"),
        "relative_volume": Decimal("1.2"),
        "return_1": Decimal("0.02"),
    }
    at_cutoff = {key: FIXED_CUTOFF for key in values}
    matched = _evaluate(spec, "breakout-match", values, known_at=at_cutoff)
    assert matched.state is RunnerProtocolState.PASS

    assert (
        _evaluate(
            spec,
            "breakout-no-high",
            {**values, "breakout_proximity": Decimal("0.001")},
        ).state
        is RunnerProtocolState.OBSERVE
    )
    assert (
        _evaluate(
            spec,
            "breakout-no-volume",
            {**values, "relative_volume": Decimal("1")},
        ).state
        is RunnerProtocolState.OBSERVE
    )
    assert (
        _evaluate(
            spec,
            "breakout-no-positive-return",
            {**values, "return_1": Decimal("0")},
        ).state
        is RunnerProtocolState.OBSERVE
    )

    unavailable = _evaluate(
        spec,
        "breakout-missing-volume",
        values,
        missingness={"relative_volume": "NOT_APPLICABLE"},
    )
    assert unavailable.state is RunnerProtocolState.UNAVAILABLE
    assert unavailable.reason_code == "INPUT_UNAVAILABLE"

    with pytest.raises(RunnerProtocolError, match="not known at the decision cutoff"):
        _evaluate(
            spec,
            "breakout-late-return",
            values,
            known_at={"return_1": "2026-01-03T20:00:01Z"},
        )


@pytest.mark.parametrize(
    ("key", "values"),
    [
        (
            "bullish-reversal",
            {
                "reversal_score": Decimal("-1"),
                "return_1": Decimal("0.03"),
                "close_location_value": Decimal("0.2"),
            },
        ),
        (
            "bearish-reversal",
            {
                "reversal_score": Decimal("1"),
                "return_1": Decimal("-0.03"),
                "close_location_value": Decimal("-0.2"),
            },
        ),
    ],
)
def test_reversal_observation_requires_direction_and_close_location_agreement(
    key: str,
    values: dict[str, Decimal],
) -> None:
    result = _evaluate(_spec("daily-reversal-location"), key, values)
    assert result.state is RunnerProtocolState.PASS


def test_unavailable_similarity_stays_unavailable_and_present_values_only_observe() -> None:
    spec = _spec("historical-similarity-interface-observation")
    values = {
        "runner_similarity": Decimal("-1"),
        "failure_similarity": Decimal("1"),
    }
    available = _evaluate(spec, "similarity-available", values)
    assert available.state is RunnerProtocolState.OBSERVE

    missing_failure = _evaluate(
        spec,
        "similarity-no-failure-memory",
        values,
        missingness={"failure_similarity": "NOT_APPLICABLE"},
    )
    assert missing_failure.state is RunnerProtocolState.UNAVAILABLE
    assert missing_failure.reason_code == "INPUT_UNAVAILABLE"

    unknown_failure = _evaluate(
        spec,
        "similarity-unknown-failure-memory",
        values,
        missingness={"failure_similarity": "UNKNOWN"},
    )
    assert unknown_failure.state is RunnerProtocolState.UNKNOWN
    assert unknown_failure.reason_code == "INPUT_UNKNOWN"
