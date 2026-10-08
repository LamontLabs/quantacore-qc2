"""Inactive QC2-020 research hypotheses over the registered daily feature set."""

from __future__ import annotations

from decimal import Decimal

from .models import ContractRef
from .registry import build_feature_specs
from .runner_protocol_models import (
    ProtocolInputRequirement,
    ProtocolExpression,
    RunnerProtocolError,
    RunnerProtocolSpec,
    RunnerProtocolState,
    input_value,
    parameter_value,
    protocol_operation,
)

_FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
_RESEARCH_EVIDENCE_CLASS = "SYNTHETIC_FIXTURE"
_RESEARCH_ENVIRONMENT = "research"

_DIRECT_FEATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "daily-breakout-confluence",
        ("breakout_proximity", "relative_volume", "return_1"),
    ),
    (
        "daily-reversal-location",
        ("reversal_score", "return_1", "close_location_value"),
    ),
    (
        "daily-failed-breakout-observation",
        ("breakout_attempt_count", "breakout_failure_count"),
    ),
    ("daily-price-volume-divergence-observation", ("price_volume_divergence",)),
    ("daily-exhaustion-pressure-observation", ("exhaustion_pressure",)),
    ("historical-similarity-interface-observation", ("runner_similarity", "failure_similarity")),
)


def _make_spec(
    feature_snapshot_ref: ContractRef,
    *,
    protocol_id: str,
    hypothesis: str,
    direction: str,
    feature_keys: tuple[str, ...],
    parameters: tuple[tuple[str, Decimal | str | int], ...],
    expression: ProtocolExpression,
    on_match: RunnerProtocolState,
    on_non_match: RunnerProtocolState,
    max_steps: int,
) -> RunnerProtocolSpec:
    feature_specs = {item.stable_key: item for item in build_feature_specs()}
    missing = sorted(set(feature_keys) - set(feature_specs))
    if missing:
        raise RunnerProtocolError(f"research hypothesis requires unregistered features: {missing}")
    requirements = tuple(
        ProtocolInputRequirement(key, feature_specs[key].output_unit, feature_snapshot_ref)
        for key in feature_keys
    )
    return RunnerProtocolSpec(
        protocol_namespace="research",
        protocol_id=protocol_id,
        version=1,
        hypothesis=hypothesis,
        direction=direction,
        regime="research_daily",
        input_requirements=requirements,
        parameter_refs=(),
        parameters=parameters,
        expression=expression,
        on_match=on_match,
        on_non_match=on_non_match,
        evidence_class=_RESEARCH_EVIDENCE_CLASS,
        environment_namespace=_RESEARCH_ENVIRONMENT,
        max_steps=max_steps,
    )


def research_wave2_protocols(
    feature_snapshot_ref: ContractRef,
) -> tuple[RunnerProtocolSpec, ...]:
    """Build inactive daily research hypotheses, not behavior-equivalent legacy ports."""
    if feature_snapshot_ref.target_schema_name != _FEATURE_SNAPSHOT_SCHEMA:
        raise RunnerProtocolError("research protocols require a FeatureSnapshot reference")

    inputs = {key: input_value(key) for _, keys in _DIRECT_FEATURES for key in keys}
    zero = parameter_value("zero_boundary")
    one = parameter_value("volume_reference")
    signed_min = parameter_value("signed_unit_min")
    signed_max = parameter_value("signed_unit_max")

    breakout = protocol_operation(
        "and",
        protocol_operation("lte", inputs["breakout_proximity"], zero),
        protocol_operation("gt", inputs["relative_volume"], one),
        protocol_operation("gt", inputs["return_1"], zero),
    )
    bullish_reversal = protocol_operation(
        "and",
        protocol_operation("lt", inputs["reversal_score"], zero),
        protocol_operation("gt", inputs["return_1"], zero),
        protocol_operation("gt", inputs["close_location_value"], zero),
    )
    bearish_reversal = protocol_operation(
        "and",
        protocol_operation("gt", inputs["reversal_score"], zero),
        protocol_operation("lt", inputs["return_1"], zero),
        protocol_operation("lt", inputs["close_location_value"], zero),
    )
    reversal = protocol_operation("or", bullish_reversal, bearish_reversal)

    failed_breakout = protocol_operation(
        "and",
        protocol_operation(
            "gt", inputs["breakout_attempt_count"], parameter_value("zero_count")
        ),
        protocol_operation(
            "gt", inputs["breakout_failure_count"], parameter_value("zero_count")
        ),
    )
    divergence_present = protocol_operation(
        "or",
        protocol_operation(
            "gt", inputs["price_volume_divergence"], parameter_value("zero_boundary")
        ),
        protocol_operation(
            "lt", inputs["price_volume_divergence"], parameter_value("zero_boundary")
        ),
    )
    exhaustion_present = protocol_operation(
        "or",
        protocol_operation(
            "gt", inputs["exhaustion_pressure"], parameter_value("zero_boundary")
        ),
        protocol_operation(
            "lt", inputs["exhaustion_pressure"], parameter_value("zero_boundary")
        ),
    )

    def signed_unit_range(key: str) -> ProtocolExpression:
        return protocol_operation(
            "and",
            protocol_operation("gte", inputs[key], signed_min),
            protocol_operation("lte", inputs[key], signed_max),
        )

    similarity_interface = protocol_operation(
        "and",
        signed_unit_range("runner_similarity"),
        signed_unit_range("failure_similarity"),
    )

    observe = RunnerProtocolState.OBSERVE
    specs = (
        _make_spec(
            feature_snapshot_ref,
            protocol_id="daily-breakout-confluence",
            hypothesis=(
                "Research-only daily confluence: current high reaches/exceeds the preceding "
                "registered high window, relative volume exceeds its prior-window mean, and "
                "the close-to-close return is positive. Not a T24 port."
            ),
            direction="POSITIVE",
            feature_keys=("breakout_proximity", "relative_volume", "return_1"),
            parameters=(
                ("zero_boundary", Decimal("0")),
                ("volume_reference", Decimal("1")),
            ),
            expression=breakout,
            on_match=RunnerProtocolState.PASS,
            on_non_match=observe,
            max_steps=32,
        ),
        _make_spec(
            feature_snapshot_ref,
            protocol_id="daily-reversal-location",
            hypothesis=(
                "Research-only daily reversal observation: the registered prior-direction "
                "reversal score opposes the latest return, and close-location value has the "
                "same sign as that latest return."
            ),
            direction="UNKNOWN",
            feature_keys=("reversal_score", "return_1", "close_location_value"),
            parameters=(("zero_boundary", Decimal("0")),),
            expression=reversal,
            on_match=RunnerProtocolState.PASS,
            on_non_match=observe,
            max_steps=48,
        ),
        _make_spec(
            feature_snapshot_ref,
            protocol_id="daily-failed-breakout-observation",
            hypothesis=(
                "Research-only daily count observation: at least one registered breakout "
                "attempt and one registered failed close-back-under-high occurred in their "
                "configured count window. This is not a trap probability or blocker."
            ),
            direction="UNKNOWN",
            feature_keys=("breakout_attempt_count", "breakout_failure_count"),
            parameters=(("zero_count", Decimal("0")),),
            expression=failed_breakout,
            on_match=observe,
            on_non_match=observe,
            max_steps=32,
        ),
        _make_spec(
            feature_snapshot_ref,
            protocol_id="daily-price-volume-divergence-observation",
            hypothesis=(
                "Research-only observation that the registered daily price-volume divergence "
                "feature is nonzero; it does not assign a trade direction or action."
            ),
            direction="UNKNOWN",
            feature_keys=("price_volume_divergence",),
            parameters=(("zero_boundary", Decimal("0")),),
            expression=divergence_present,
            on_match=observe,
            on_non_match=observe,
            max_steps=32,
        ),
        _make_spec(
            feature_snapshot_ref,
            protocol_id="daily-exhaustion-pressure-observation",
            hypothesis=(
                "Research-only observation that the registered daily exhaustion-pressure "
                "feature is nonzero; this is not an execution blocker."
            ),
            direction="UNKNOWN",
            feature_keys=("exhaustion_pressure",),
            parameters=(("zero_boundary", Decimal("0")),),
            expression=exhaustion_present,
            on_match=observe,
            on_non_match=observe,
            max_steps=32,
        ),
        _make_spec(
            feature_snapshot_ref,
            protocol_id="historical-similarity-interface-observation",
            hypothesis=(
                "Research-only interface check: both receipted historical runner and failure "
                "similarity values are present within their registered signed-unit range. "
                "This does not interpret similarity as a decision."
            ),
            direction="UNKNOWN",
            feature_keys=("runner_similarity", "failure_similarity"),
            parameters=(
                ("signed_unit_min", Decimal("-1")),
                ("signed_unit_max", Decimal("1")),
            ),
            expression=similarity_interface,
            on_match=observe,
            on_non_match=observe,
            max_steps=48,
        ),
    )
    return tuple(sorted(specs, key=lambda item: item.protocol_key))


def research_wave2_dependency_graphs() -> tuple[
    tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...
]:
    """Return each protocol's transitive registered-feature dependency adjacency list."""
    feature_specs = {item.stable_key: item for item in build_feature_specs()}
    graphs: list[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]]] = []
    for protocol_id, direct_features in _DIRECT_FEATURES:
        pending = list(direct_features)
        closure: set[str] = set()
        while pending:
            key = pending.pop()
            if key in closure:
                continue
            feature = feature_specs.get(key)
            if feature is None:
                raise RunnerProtocolError(
                    f"dependency graph references unregistered feature {key!r}"
                )
            closure.add(key)
            pending.extend(feature.dependencies)
        adjacency = tuple(
            (key, tuple(sorted(feature_specs[key].dependencies)))
            for key in sorted(closure)
        )
        graphs.append((protocol_id, adjacency))
    return tuple(sorted(graphs))
