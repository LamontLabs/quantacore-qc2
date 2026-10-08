"""Inactive QC2-019 research rewrites over registered daily features."""

from __future__ import annotations

from decimal import Decimal

from .models import ContractRef
from .runner_protocol_models import (
    ProtocolInputRequirement,
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


def research_wave1_protocols(feature_snapshot_ref: ContractRef) -> tuple[RunnerProtocolSpec, ...]:
    """Build inactive research hypotheses bound only to registered daily feature snapshots.

    These are component-level rewrites, not behavior-equivalent ports of the legacy
    protocols. Their synthetic evidence class and research namespace are intentional.
    """
    if feature_snapshot_ref.target_schema_name != _FEATURE_SNAPSHOT_SCHEMA:
        raise RunnerProtocolError("research protocols require a FeatureSnapshot reference")

    relative_volume = input_value("relative_volume")
    accumulation = input_value("accumulation")
    return_10 = input_value("return_10")
    return_20 = input_value("return_20")

    zero = parameter_value("zero_boundary")
    positive_trend = protocol_operation(
        "and",
        protocol_operation("gt", return_10, zero),
        protocol_operation("gt", return_20, zero),
    )
    negative_trend = protocol_operation(
        "and",
        protocol_operation("lt", return_10, zero),
        protocol_operation("lt", return_20, zero),
    )
    flat_trend = protocol_operation(
        "and",
        protocol_operation("eq", return_10, zero),
        protocol_operation("eq", return_20, zero),
    )

    specs = (
        RunnerProtocolSpec(
            protocol_namespace="research",
            protocol_id="t41-volume-expansion",
            version=1,
            hypothesis=(
                "Research-only: current daily volume exceeds the preceding 20-session "
                "arithmetic mean."
            ),
            direction="POSITIVE",
            regime="research_daily",
            input_requirements=(
                ProtocolInputRequirement("relative_volume", "ratio", feature_snapshot_ref),
            ),
            parameter_refs=(),
            parameters=(("expansion_boundary", Decimal("1.000000000000")),),
            expression=protocol_operation(
                "gt", relative_volume, parameter_value("expansion_boundary")
            ),
            on_match=RunnerProtocolState.PASS,
            on_non_match=RunnerProtocolState.OBSERVE,
            evidence_class=_RESEARCH_EVIDENCE_CLASS,
            environment_namespace=_RESEARCH_ENVIRONMENT,
            max_steps=16,
        ),
        RunnerProtocolSpec(
            protocol_namespace="research",
            protocol_id="t44-positive-money-flow",
            version=1,
            hypothesis=(
                "Research-only: registered 20-session volume-weighted close-location "
                "pressure is positive."
            ),
            direction="POSITIVE",
            regime="research_daily",
            input_requirements=(
                ProtocolInputRequirement("accumulation", "signed_fraction", feature_snapshot_ref),
            ),
            parameter_refs=(),
            parameters=(("zero_boundary", Decimal("0")),),
            expression=protocol_operation(
                "gt", accumulation, parameter_value("zero_boundary")
            ),
            on_match=RunnerProtocolState.PASS,
            on_non_match=RunnerProtocolState.OBSERVE,
            evidence_class=_RESEARCH_EVIDENCE_CLASS,
            environment_namespace=_RESEARCH_ENVIRONMENT,
            max_steps=16,
        ),
        RunnerProtocolSpec(
            protocol_namespace="research",
            protocol_id="t78-return-sign-alignment",
            version=1,
            hypothesis=(
                "Research-only: registered 10- and 20-session returns have the same sign."
            ),
            direction="UNKNOWN",
            regime="research_daily",
            input_requirements=(
                ProtocolInputRequirement("return_10", "fraction", feature_snapshot_ref),
                ProtocolInputRequirement("return_20", "fraction", feature_snapshot_ref),
            ),
            parameter_refs=(),
            parameters=(("zero_boundary", Decimal("0")),),
            expression=protocol_operation(
                "or", positive_trend, negative_trend, flat_trend
            ),
            on_match=RunnerProtocolState.PASS,
            on_non_match=RunnerProtocolState.OBSERVE,
            evidence_class=_RESEARCH_EVIDENCE_CLASS,
            environment_namespace=_RESEARCH_ENVIRONMENT,
            max_steps=64,
        ),
    )
    return tuple(sorted(specs, key=lambda item: item.protocol_key))
