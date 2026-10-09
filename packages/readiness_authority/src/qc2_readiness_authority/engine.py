"""Scientific readiness stages with explicit, non-broker prerequisites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import (
    DeadlineAssessment,
    EvidenceFact,
    GateAssessment,
    GateState,
    ReadinessStatus,
    ReadinessContext,
    ReadinessInputError,
    ReadinessStage,
    SourceReference,
    StageAssessment,
    parse_utc_instant,
)

_OPERATING_POINTER_STATE = "CHAMPION_SET"
_REFERENCE_SCHEMA = "qc2.governance_owner.ChampionPointer.v1"
_MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
_RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
_EPOCH_SCHEMA = "qc2.validation.ValidationEpoch.v1"


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _references(*groups: Iterable[SourceReference]) -> tuple[SourceReference, ...]:
    by_identity = {ref.identity: ref for group in groups for ref in group if ref is not None}
    return tuple(by_identity[key] for key in sorted(by_identity))


def _versions(*groups: Iterable[str]) -> tuple[str, ...]:
    return _dedupe(value for group in groups for value in group)


def _fallback_time(fact: EvidenceFact | None, context: ReadinessContext) -> tuple[str, str]:
    if fact is not None and fact.observed_at and fact.freshness_deadline:
        return fact.observed_at, fact.freshness_deadline
    return context.evaluated_at, context.evaluated_at


def _gate(
    context: ReadinessContext,
    gate_id: str,
    status: GateState,
    reason_codes: Iterable[str] = (),
    *,
    fact: EvidenceFact | None = None,
    source_refs: Iterable[SourceReference] = (),
    observed_versions: Iterable[str] = (),
    deadlines: Iterable[DeadlineAssessment] = (),
    evaluated_at: str | None = None,
    freshness_deadline: str | None = None,
) -> GateAssessment:
    fact_evaluated_at, fact_freshness_deadline = _fallback_time(fact, context)
    versions = list(observed_versions)
    if fact is not None and fact.version is not None:
        versions.insert(0, fact.version)
    if fact is not None:
        source_refs = (*fact.source_refs, *source_refs)
    return GateAssessment(
        gate_id=gate_id,
        status=status,
        reason_codes=_dedupe(reason_codes),
        evaluated_at=evaluated_at or fact_evaluated_at,
        freshness_deadline=freshness_deadline or fact_freshness_deadline,
        source_refs=_references(source_refs),
        observed_versions=_versions(versions),
        deadline_assessments=tuple(deadlines),
    )


def _fact_gate(
    context: ReadinessContext,
    gate_id: str,
    fact: EvidenceFact | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if fact is None:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("EVIDENCE_MISSING",),
        )

    if fact.input_generation is not None and fact.input_generation != context.input_generation:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            (*fact.reason_codes, "INPUT_GENERATION_MISMATCH"),
            fact=fact,
        )

    if fact.status is not GateState.PASS:
        defaults = {
            GateState.BLOCK: "EVIDENCE_BLOCKED",
            GateState.UNKNOWN: "EVIDENCE_UNKNOWN",
            GateState.UNAVAILABLE: "CAPABILITY_UNAVAILABLE",
        }
        return _gate(
            context,
            gate_id,
            fact.status,
            fact.reason_codes or (defaults[fact.status],),
            fact=fact,
        )

    if not clock_trusted:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("CLOCK_UNTRUSTED",),
            fact=fact,
        )
    if (
        fact.observed_at is None
        or fact.freshness_deadline is None
        or fact.version is None
        or not fact.source_refs
    ):
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("EVIDENCE_BINDING_MISSING",),
            fact=fact,
        )

    evaluated = parse_utc_instant(context.evaluated_at, "evaluated_at")
    observed = parse_utc_instant(fact.observed_at, "observed_at")
    deadline = parse_utc_instant(fact.freshness_deadline, "freshness_deadline")
    if observed > evaluated:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("EVIDENCE_FROM_FUTURE",),
            fact=fact,
        )
    if evaluated > deadline:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("EVIDENCE_STALE",),
            fact=fact,
        )
    return _gate(context, gate_id, GateState.PASS, fact=fact)


def _upstream_gate(
    context: ReadinessContext,
    gate_id: str,
    assessment: StageAssessment | None,
    *,
    expected_stage: ReadinessStage,
) -> GateAssessment:
    if assessment is None:
        return _gate(context, gate_id, GateState.UNKNOWN, ("UPSTREAM_ASSESSMENT_MISSING",))

    refs = _references(ref for result in assessment.gate_results for ref in result.source_refs)
    versions = (f"{assessment.stage.value}:{assessment.context.input_generation}",)
    evaluated = parse_utc_instant(context.evaluated_at, "evaluated_at")
    oldest_gate = min(
        assessment.gate_results,
        key=lambda gate: parse_utc_instant(
            gate.freshness_deadline, "upstream gate freshness_deadline"
        ),
    )
    upstream_observed_at = oldest_gate.evaluated_at
    deadline = parse_utc_instant(assessment.freshness_deadline, "upstream freshness_deadline")
    reasons: list[str] = []

    if assessment.stage is not expected_stage:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("UPSTREAM_STAGE_MISMATCH",),
            source_refs=refs,
            observed_versions=versions,
            evaluated_at=upstream_observed_at,
            freshness_deadline=assessment.freshness_deadline,
        )
    if assessment.context.input_generation != context.input_generation:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("INPUT_GENERATION_MISMATCH",),
            source_refs=refs,
            observed_versions=versions,
            evaluated_at=upstream_observed_at,
            freshness_deadline=assessment.freshness_deadline,
        )
    upstream_times = (
        assessment.context.evaluated_at,
        *(gate.evaluated_at for gate in assessment.gate_results),
    )
    if any(
        evaluated < parse_utc_instant(value, "upstream evaluated_at") for value in upstream_times
    ):
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("UPSTREAM_ASSESSMENT_FROM_FUTURE",),
            source_refs=refs,
            observed_versions=versions,
        )
    if evaluated > deadline:
        return _gate(
            context,
            gate_id,
            GateState.UNKNOWN,
            ("UPSTREAM_ASSESSMENT_STALE",),
            source_refs=refs,
            observed_versions=versions,
            evaluated_at=upstream_observed_at,
            freshness_deadline=assessment.freshness_deadline,
        )
    if assessment.status is not ReadinessStatus.READY:
        for result in assessment.gate_results:
            if result.status is not GateState.PASS:
                reasons.extend(result.reason_codes)
        reasons.append(
            "UPSTREAM_ASSESSMENT_BLOCKED"
            if assessment.status.value == "BLOCKED"
            else "UPSTREAM_ASSESSMENT_UNKNOWN"
        )
        status = GateState.BLOCK if assessment.status.value == "BLOCKED" else GateState.UNKNOWN
        return _gate(
            context,
            gate_id,
            status,
            reasons,
            source_refs=refs,
            observed_versions=versions,
            evaluated_at=upstream_observed_at,
            freshness_deadline=assessment.freshness_deadline,
        )
    return _gate(
        context,
        gate_id,
        GateState.PASS,
        source_refs=refs,
        observed_versions=versions,
        evaluated_at=upstream_observed_at,
        freshness_deadline=assessment.freshness_deadline,
    )


def _clock_is_trusted(context: ReadinessContext, assessment: StageAssessment | None) -> bool:
    if (
        assessment is None
        or assessment.stage is not ReadinessStage.INGESTION_PREFLIGHT
        or assessment.context.input_generation != context.input_generation
    ):
        return False
    clock_gate = next(
        (gate for gate in assessment.gate_results if gate.gate_id == "clock_calendar"),
        None,
    )
    if clock_gate is None or clock_gate.status is not GateState.PASS:
        return False
    return parse_utc_instant(context.evaluated_at, "evaluated_at") <= parse_utc_instant(
        clock_gate.freshness_deadline, "clock freshness_deadline"
    )


def assess_ingestion_preflight(
    context: ReadinessContext,
    *,
    installation: EvidenceFact | None,
    clock_calendar: EvidenceFact | None,
    data_capability: EvidenceFact | None,
    storage_evidence_write: EvidenceFact | None,
    bounded_resources: EvidenceFact | None,
) -> StageAssessment:
    """Assess required installation, time, data, evidence-write and resource gates."""
    clock = _fact_gate(context, "clock_calendar", clock_calendar, clock_trusted=True)
    clock_trusted = clock.status is GateState.PASS
    gates = (
        _fact_gate(context, "installation_capability", installation, clock_trusted=clock_trusted),
        clock,
        _fact_gate(context, "data_capability", data_capability, clock_trusted=clock_trusted),
        _fact_gate(
            context,
            "storage_evidence_write",
            storage_evidence_write,
            clock_trusted=clock_trusted,
        ),
        _fact_gate(context, "bounded_resources", bounded_resources, clock_trusted=clock_trusted),
    )
    return StageAssessment(ReadinessStage.INGESTION_PREFLIGHT, context, gates)


def assess_snapshot_ready(
    context: ReadinessContext,
    *,
    ingestion_preflight: StageAssessment | None,
    declared_acquisition: EvidenceFact | None,
    semantic_provenance: EvidenceFact | None,
    universe_coverage: EvidenceFact | None,
    durable_snapshot_dependencies: EvidenceFact | None,
) -> StageAssessment:
    """Assess complete, semantically validated and durably bound market snapshots."""
    gates = [
        _upstream_gate(
            context,
            "ingestion_preflight",
            ingestion_preflight,
            expected_stage=ReadinessStage.INGESTION_PREFLIGHT,
        )
    ]
    clock_trusted = _clock_is_trusted(context, ingestion_preflight)
    gates.extend(
        (
            _fact_gate(
                context,
                "declared_acquisition",
                declared_acquisition,
                clock_trusted=clock_trusted,
            ),
            _fact_gate(
                context,
                "semantic_provenance",
                semantic_provenance,
                clock_trusted=clock_trusted,
            ),
            _fact_gate(
                context,
                "universe_coverage",
                universe_coverage,
                clock_trusted=clock_trusted,
            ),
            _fact_gate(
                context,
                "durable_snapshot_dependencies",
                durable_snapshot_dependencies,
                clock_trusted=clock_trusted,
            ),
        )
    )
    return StageAssessment(ReadinessStage.SNAPSHOT_READY, context, tuple(gates))


@dataclass(frozen=True, slots=True)
class ModelLoadBinding:
    pointer_state: str
    pointer_ref: SourceReference | None
    pointer_model_ref: SourceReference | None
    pointer_epoch_ref: SourceReference | None
    pointer_generation: int | None
    pointer_role: str | None
    loaded_model_ref: SourceReference | None
    loaded_epoch_ref: SourceReference | None
    loaded_generation: int | None
    load_confirmed: bool | None
    pointer_evidence_class: str | None
    pointer_environment_namespace: str | None
    loaded_evidence_class: str | None
    loaded_environment_namespace: str | None
    fact: EvidenceFact | None

    def __post_init__(self) -> None:
        if self.pointer_state not in {"CHAMPION_SET", "NO_CHAMPION", "UNKNOWN"}:
            raise ReadinessInputError("unsupported operating pointer state")
        for name, generation in (
            ("pointer_generation", self.pointer_generation),
            ("loaded_generation", self.loaded_generation),
        ):
            if generation is not None and (
                isinstance(generation, bool) or not isinstance(generation, int) or generation < 1
            ):
                raise ReadinessInputError(f"{name} must be positive when supplied")


@dataclass(frozen=True, slots=True)
class ModelQualification:
    qualified_model_ref: SourceReference | None
    fact: EvidenceFact | None


@dataclass(frozen=True, slots=True)
class RegistryCompatibility:
    model_ref: SourceReference | None
    model_registry_refs: tuple[SourceReference, ...]
    active_registry_refs: tuple[SourceReference, ...]
    fact: EvidenceFact | None

    def __post_init__(self) -> None:
        model_refs = tuple(self.model_registry_refs)
        active_refs = tuple(self.active_registry_refs)
        if any(not isinstance(ref, SourceReference) for ref in model_refs + active_refs):
            raise ReadinessInputError("registry refs must be SourceReference values")
        if len(model_refs) != len(set(model_refs)) or len(active_refs) != len(set(active_refs)):
            raise ReadinessInputError("registry refs must not contain duplicates")
        object.__setattr__(self, "model_registry_refs", model_refs)
        object.__setattr__(self, "active_registry_refs", active_refs)


@dataclass(frozen=True, slots=True)
class DependencyAvailability:
    dependency_id: str
    available_at: str
    source_ref: SourceReference
    version: str

    def __post_init__(self) -> None:
        if not self.dependency_id.strip() or not self.version.strip():
            raise ReadinessInputError("dependency ID and version are required")
        parse_utc_instant(self.available_at, "dependency available_at")


@dataclass(frozen=True, slots=True)
class TemporalDependencyAssessment:
    decision_cutoff: str | None
    dependencies: tuple[DependencyAvailability, ...]
    fact: EvidenceFact | None

    def __post_init__(self) -> None:
        if self.decision_cutoff is not None:
            parse_utc_instant(self.decision_cutoff, "decision_cutoff")
        dependencies = tuple(self.dependencies)
        if any(not isinstance(item, DependencyAvailability) for item in dependencies):
            raise ReadinessInputError("dependencies must contain DependencyAvailability values")
        if len({item.dependency_id for item in dependencies}) != len(dependencies):
            raise ReadinessInputError("dependency IDs must be unique")
        object.__setattr__(self, "dependencies", dependencies)


@dataclass(frozen=True, slots=True)
class SealCapability:
    fact: EvidenceFact | None
    estimated_prediction_complete_at: str | None
    decision_deadline: str | None
    estimated_sealed_at: str | None
    seal_deadline: str | None
    estimated_anchor_at: str | None
    evidence_anchor_deadline: str | None
    next_session_open: str | None

    def __post_init__(self) -> None:
        pairs = (
            ("estimated_prediction_complete_at", "decision_deadline"),
            ("estimated_sealed_at", "seal_deadline"),
            ("estimated_anchor_at", "evidence_anchor_deadline"),
        )
        for estimate_name, deadline_name in pairs:
            estimate = getattr(self, estimate_name)
            deadline = getattr(self, deadline_name)
            if (estimate is None) != (deadline is None):
                raise ReadinessInputError(
                    f"{estimate_name} and {deadline_name} must be supplied together"
                )
            if estimate is not None:
                parse_utc_instant(estimate, estimate_name)
                parse_utc_instant(deadline, deadline_name)
        if self.next_session_open is not None:
            parse_utc_instant(self.next_session_open, "next_session_open")


@dataclass(frozen=True, slots=True)
class PredictionReadinessInputs:
    context: ReadinessContext
    ingestion_preflight: StageAssessment | None
    snapshot_ready: StageAssessment | None
    run_ref: SourceReference | None
    run_binding_fact: EvidenceFact | None
    expected_epoch_ref: SourceReference | None
    model_binding: ModelLoadBinding | None
    model_qualification: ModelQualification | None
    registry_compatibility: RegistryCompatibility | None
    temporal_dependencies: TemporalDependencyAssessment | None
    numerical_environment: EvidenceFact | None
    seal_capability: SealCapability | None

    def __post_init__(self) -> None:
        if self.run_ref is not None and self.run_ref.target_schema_name != _RUN_SCHEMA:
            raise ReadinessInputError("run_ref must reference PredictionRun")
        if (
            self.expected_epoch_ref is not None
            and self.expected_epoch_ref.target_schema_name != _EPOCH_SCHEMA
        ):
            raise ReadinessInputError("expected_epoch_ref must reference ValidationEpoch")


def _same_reference(left: SourceReference | None, right: SourceReference | None) -> bool:
    return left is not None and right is not None and left.identity == right.identity


def _model_binding_gate(
    context: ReadinessContext,
    binding: ModelLoadBinding | None,
    expected_epoch_ref: SourceReference | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if binding is None:
        return _gate(
            context,
            "model_pointer_consistency",
            GateState.UNKNOWN,
            ("MODEL_BINDING_MISSING",),
        )

    refs = _references(
        tuple(
            ref
            for ref in (
                binding.pointer_ref,
                binding.pointer_model_ref,
                binding.pointer_epoch_ref,
                binding.loaded_model_ref,
                binding.loaded_epoch_ref,
                expected_epoch_ref,
            )
            if ref is not None
        )
    )
    versions = list(
        filter(
            None,
            (
                f"pointer-generation:{binding.pointer_generation}"
                if binding.pointer_generation is not None
                else None,
                f"loaded-generation:{binding.loaded_generation}"
                if binding.loaded_generation is not None
                else None,
            ),
        )
    )
    base = _fact_gate(
        context,
        "model_pointer_consistency",
        binding.fact,
        clock_trusted=clock_trusted,
    )
    if binding.fact is not None and binding.fact.version:
        versions.insert(0, binding.fact.version)

    failures: list[str] = []
    unknowns: list[str] = []
    if binding.pointer_state == "NO_CHAMPION":
        failures.append("CHAMPION_POINTER_MISSING")
    elif binding.pointer_state != _OPERATING_POINTER_STATE:
        unknowns.append("CHAMPION_POINTER_UNKNOWN")
    else:
        if binding.pointer_role is None:
            unknowns.append("CHAMPION_POINTER_ROLE_MISSING")
        elif binding.pointer_role != "OPERATING":
            failures.append("OPERATING_CHAMPION_REQUIRED")
        if binding.pointer_ref is None:
            unknowns.append("CHAMPION_POINTER_REFERENCE_MISSING")
        elif binding.pointer_ref.target_schema_name != _REFERENCE_SCHEMA:
            failures.append("CHAMPION_POINTER_REFERENCE_TYPE_INVALID")
        if binding.pointer_model_ref is None:
            unknowns.append("CHAMPION_MODEL_REFERENCE_MISSING")
        elif binding.pointer_model_ref.target_schema_name != _MODEL_SCHEMA:
            failures.append("CHAMPION_MODEL_REFERENCE_TYPE_INVALID")
        if binding.pointer_epoch_ref is None:
            unknowns.append("CHAMPION_EPOCH_BINDING_MISSING")
        elif binding.pointer_epoch_ref.target_schema_name != _EPOCH_SCHEMA:
            failures.append("CHAMPION_EPOCH_REFERENCE_TYPE_INVALID")
        if binding.pointer_generation is None:
            unknowns.append("CHAMPION_GENERATION_MISSING")

    if binding.pointer_state == _OPERATING_POINTER_STATE:
        if binding.load_confirmed is False:
            failures.append("MODEL_LOAD_UNCONFIRMED")
        elif binding.load_confirmed is None:
            unknowns.append("MODEL_LOAD_CONFIRMATION_MISSING")
        if binding.loaded_model_ref is None:
            unknowns.append("LOADED_MODEL_REFERENCE_MISSING")
        elif binding.pointer_model_ref is not None and not _same_reference(
            binding.pointer_model_ref, binding.loaded_model_ref
        ):
            failures.append("MODEL_LOAD_MISMATCH")
        if binding.pointer_generation is not None:
            if binding.loaded_generation is None:
                unknowns.append("MODEL_LOAD_GENERATION_MISSING")
            elif binding.pointer_generation != binding.loaded_generation:
                failures.append("MODEL_GENERATION_MISMATCH")
        if expected_epoch_ref is None:
            unknowns.append("VALIDATION_EPOCH_BINDING_MISSING")
        if (
            binding.pointer_epoch_ref is not None
            and expected_epoch_ref is not None
            and not _same_reference(binding.pointer_epoch_ref, expected_epoch_ref)
        ):
            failures.append("CHAMPION_EPOCH_MISMATCH")
        if binding.loaded_epoch_ref is not None and expected_epoch_ref is not None:
            if not _same_reference(binding.loaded_epoch_ref, expected_epoch_ref):
                failures.append("LOADED_MODEL_EPOCH_MISMATCH")
        elif binding.loaded_epoch_ref is None:
            unknowns.append("LOADED_MODEL_EPOCH_BINDING_MISSING")
        if not binding.pointer_evidence_class or not binding.loaded_evidence_class:
            unknowns.append("MODEL_EVIDENCE_CONTEXT_MISSING")
        elif binding.pointer_evidence_class != binding.loaded_evidence_class:
            failures.append("MODEL_EVIDENCE_CONTEXT_MISMATCH")
        if not binding.pointer_environment_namespace or not binding.loaded_environment_namespace:
            unknowns.append("MODEL_ENVIRONMENT_BINDING_MISSING")
        elif binding.pointer_environment_namespace != binding.loaded_environment_namespace:
            failures.append("MODEL_ENVIRONMENT_MISMATCH")

    if failures or base.status is GateState.BLOCK:
        return _gate(
            context,
            "model_pointer_consistency",
            GateState.BLOCK,
            (*failures, *base.reason_codes),
            fact=binding.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if unknowns or base.status is not GateState.PASS:
        return _gate(
            context,
            "model_pointer_consistency",
            GateState.UNKNOWN,
            (*unknowns, *base.reason_codes),
            fact=binding.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    return _gate(
        context,
        "model_pointer_consistency",
        base.status,
        base.reason_codes,
        fact=binding.fact,
        source_refs=refs,
        observed_versions=versions,
    )


def _model_qualification_gate(
    context: ReadinessContext,
    qualification: ModelQualification | None,
    binding: ModelLoadBinding | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if qualification is None:
        return _gate(
            context,
            "model_qualification",
            GateState.UNKNOWN,
            ("MODEL_QUALIFICATION_MISSING",),
        )
    base = _fact_gate(
        context,
        "model_qualification",
        qualification.fact,
        clock_trusted=clock_trusted,
    )
    refs = _references(
        (qualification.qualified_model_ref,)
        if qualification.qualified_model_ref is not None
        else (),
        (binding.pointer_model_ref,)
        if binding is not None and binding.pointer_model_ref is not None
        else (),
    )
    if (
        binding is not None
        and binding.pointer_model_ref is not None
        and qualification.qualified_model_ref is not None
        and not _same_reference(binding.pointer_model_ref, qualification.qualified_model_ref)
    ):
        return _gate(
            context,
            "model_qualification",
            GateState.BLOCK,
            ("MODEL_QUALIFICATION_MODEL_MISMATCH", *base.reason_codes),
            fact=qualification.fact,
            source_refs=refs,
        )
    if base.status is GateState.BLOCK:
        return _gate(
            context,
            "model_qualification",
            GateState.BLOCK,
            base.reason_codes,
            fact=qualification.fact,
            source_refs=refs,
        )
    if qualification.qualified_model_ref is None:
        return _gate(
            context,
            "model_qualification",
            GateState.UNKNOWN,
            ("MODEL_QUALIFICATION_BINDING_MISSING", *base.reason_codes),
            fact=qualification.fact,
            source_refs=refs,
        )
    return _gate(
        context,
        "model_qualification",
        base.status,
        base.reason_codes,
        fact=qualification.fact,
        source_refs=refs,
    )


def _registry_gate(
    context: ReadinessContext,
    compatibility: RegistryCompatibility | None,
    binding: ModelLoadBinding | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if compatibility is None:
        return _gate(
            context,
            "registry_compatibility",
            GateState.UNKNOWN,
            ("REGISTRY_COMPATIBILITY_MISSING",),
        )
    base = _fact_gate(
        context,
        "registry_compatibility",
        compatibility.fact,
        clock_trusted=clock_trusted,
    )
    expected_model = binding.pointer_model_ref if binding is not None else None
    refs = _references(
        (compatibility.model_ref,) if compatibility.model_ref is not None else (),
        (expected_model,) if expected_model is not None else (),
        compatibility.model_registry_refs,
        compatibility.active_registry_refs,
    )
    versions = tuple(
        f"{ref.target_schema_name}:{ref.target_id}:{ref.content_hash or 'unversioned'}"
        for ref in (
            *compatibility.model_registry_refs,
            *compatibility.active_registry_refs,
        )
    )
    if (
        compatibility.model_ref is not None
        and expected_model is not None
        and not _same_reference(compatibility.model_ref, expected_model)
    ):
        return _gate(
            context,
            "registry_compatibility",
            GateState.BLOCK,
            ("REGISTRY_MODEL_MISMATCH", *base.reason_codes),
            fact=compatibility.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if base.status is GateState.BLOCK:
        return _gate(
            context,
            "registry_compatibility",
            GateState.BLOCK,
            base.reason_codes,
            fact=compatibility.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if compatibility.model_ref is None or expected_model is None:
        return _gate(
            context,
            "registry_compatibility",
            GateState.UNKNOWN,
            ("REGISTRY_MODEL_BINDING_MISSING", *base.reason_codes),
            fact=compatibility.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if not compatibility.model_registry_refs or not compatibility.active_registry_refs:
        return _gate(
            context,
            "registry_compatibility",
            GateState.UNKNOWN,
            ("REGISTRY_SET_MISSING", *base.reason_codes),
            fact=compatibility.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    declared = tuple(sorted(ref.identity for ref in compatibility.model_registry_refs))
    active = tuple(sorted(ref.identity for ref in compatibility.active_registry_refs))
    if declared != active:
        return _gate(
            context,
            "registry_compatibility",
            GateState.BLOCK,
            ("REGISTRY_VERSION_MISMATCH", *base.reason_codes),
            fact=compatibility.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    return _gate(
        context,
        "registry_compatibility",
        base.status,
        base.reason_codes,
        fact=compatibility.fact,
        source_refs=refs,
        observed_versions=versions,
    )


def _temporal_gate(
    context: ReadinessContext,
    temporal: TemporalDependencyAssessment | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if temporal is None:
        return _gate(
            context,
            "temporal_dependencies",
            GateState.UNKNOWN,
            ("TEMPORAL_DEPENDENCIES_MISSING",),
        )
    base = _fact_gate(
        context,
        "temporal_dependencies",
        temporal.fact,
        clock_trusted=clock_trusted,
    )
    refs = _references(tuple(item.source_ref for item in temporal.dependencies))
    versions = tuple(
        f"{item.dependency_id}:{item.version}@{item.available_at}" for item in temporal.dependencies
    )
    if base.status is GateState.BLOCK:
        return _gate(
            context,
            "temporal_dependencies",
            GateState.BLOCK,
            base.reason_codes,
            fact=temporal.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if temporal.decision_cutoff is None:
        return _gate(
            context,
            "temporal_dependencies",
            GateState.UNKNOWN,
            ("DECISION_CUTOFF_MISSING", *base.reason_codes),
            fact=temporal.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    if not temporal.dependencies:
        return _gate(
            context,
            "temporal_dependencies",
            GateState.UNKNOWN,
            ("TEMPORAL_DEPENDENCIES_MISSING", *base.reason_codes),
            fact=temporal.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    cutoff = parse_utc_instant(temporal.decision_cutoff, "decision_cutoff")
    illegal = [
        item
        for item in temporal.dependencies
        if parse_utc_instant(item.available_at, "dependency available_at") > cutoff
    ]
    if illegal:
        return _gate(
            context,
            "temporal_dependencies",
            GateState.BLOCK,
            ("ILLEGAL_TEMPORAL_DEPENDENCY", *base.reason_codes),
            fact=temporal.fact,
            source_refs=refs,
            observed_versions=versions,
        )
    return _gate(
        context,
        "temporal_dependencies",
        base.status,
        base.reason_codes,
        fact=temporal.fact,
        source_refs=refs,
        observed_versions=versions,
    )


def _deadline_assessment(
    context: ReadinessContext,
    deadline_id: str,
    deadline_at: str | None,
    estimated_at: str | None,
    *,
    clock_trusted: bool,
) -> DeadlineAssessment:
    if deadline_at is None or estimated_at is None:
        return DeadlineAssessment(
            deadline_id,
            None,
            None,
            GateState.UNKNOWN,
            ("DEADLINE_UNKNOWN",),
        )
    deadline = parse_utc_instant(deadline_at, deadline_id)
    estimate = parse_utc_instant(estimated_at, f"{deadline_id} estimate")
    now = parse_utc_instant(context.evaluated_at, "evaluated_at")
    if clock_trusted and now > deadline:
        return DeadlineAssessment(
            deadline_id,
            deadline_at,
            estimated_at,
            GateState.BLOCK,
            ("DEADLINE_EXPIRED",),
        )
    if estimate > deadline:
        return DeadlineAssessment(
            deadline_id,
            deadline_at,
            estimated_at,
            GateState.BLOCK,
            ("SEAL_DEADLINE_UNREACHABLE",),
        )
    return DeadlineAssessment(
        deadline_id,
        deadline_at,
        estimated_at,
        GateState.PASS,
    )


def _seal_gate(
    context: ReadinessContext,
    capability: SealCapability | None,
    *,
    clock_trusted: bool,
) -> GateAssessment:
    if capability is None:
        return _gate(
            context,
            "seal_capability",
            GateState.UNKNOWN,
            ("SEAL_CAPABILITY_MISSING",),
        )
    base = _fact_gate(
        context,
        "seal_capability",
        capability.fact,
        clock_trusted=clock_trusted,
    )
    checks = (
        _deadline_assessment(
            context,
            "prediction_completion",
            capability.decision_deadline,
            capability.estimated_prediction_complete_at,
            clock_trusted=clock_trusted,
        ),
        _deadline_assessment(
            context,
            "prediction_seal",
            capability.seal_deadline,
            capability.estimated_sealed_at,
            clock_trusted=clock_trusted,
        ),
        _deadline_assessment(
            context,
            "evidence_anchor",
            capability.evidence_anchor_deadline,
            capability.estimated_anchor_at,
            clock_trusted=clock_trusted,
        ),
    )
    reasons = [reason for check in checks for reason in check.reason_codes]
    if base.status is not GateState.PASS:
        reasons.extend(base.reason_codes)
    required_times = (
        capability.decision_deadline,
        capability.seal_deadline,
        capability.evidence_anchor_deadline,
        capability.next_session_open,
    )
    if any(value is None for value in required_times):
        status = GateState.UNKNOWN
        reasons.append("SEAL_DEADLINE_UNKNOWN")
    else:
        decision, seal, anchor, next_open = (
            parse_utc_instant(value, "seal deadline") for value in required_times
        )
        if not decision <= seal <= anchor < next_open:
            status = GateState.BLOCK
            reasons.append("SEAL_DEADLINE_ORDER_INVALID")
        else:
            status = GateState.PASS

    if (
        status is GateState.BLOCK
        or base.status is GateState.BLOCK
        or any(check.status is GateState.BLOCK for check in checks)
    ):
        status = GateState.BLOCK
    elif not clock_trusted:
        status = GateState.UNKNOWN
        reasons.append("CLOCK_UNTRUSTED")
    elif any(check.status is GateState.UNKNOWN for check in checks):
        status = GateState.UNKNOWN
    elif base.status is not GateState.PASS:
        status = GateState.UNKNOWN
        reasons.extend(base.reason_codes)

    return _gate(
        context,
        "seal_capability",
        status,
        reasons,
        fact=capability.fact,
        deadlines=checks,
    )


def assess_prediction_ready(inputs: PredictionReadinessInputs) -> StageAssessment:
    """Compose scientific prerequisites before inference; no completed prediction is an input."""
    context = inputs.context
    clock_trusted = _clock_is_trusted(context, inputs.ingestion_preflight)
    run_gate = _fact_gate(
        context,
        "prediction_run_binding",
        inputs.run_binding_fact,
        clock_trusted=clock_trusted,
    )
    if inputs.run_ref is None:
        run_gate = _gate(
            context,
            "prediction_run_binding",
            GateState.UNKNOWN,
            ("PREDICTION_RUN_BINDING_MISSING",),
            fact=inputs.run_binding_fact,
        )
    elif (
        inputs.run_binding_fact is not None
        and inputs.run_ref not in inputs.run_binding_fact.source_refs
    ):
        run_gate = _gate(
            context,
            "prediction_run_binding",
            GateState.UNKNOWN,
            ("PREDICTION_RUN_REFERENCE_MISMATCH",),
            fact=inputs.run_binding_fact,
            source_refs=(inputs.run_ref,),
        )
    gates = (
        _upstream_gate(
            context,
            "ingestion_preflight",
            inputs.ingestion_preflight,
            expected_stage=ReadinessStage.INGESTION_PREFLIGHT,
        ),
        _upstream_gate(
            context,
            "snapshot_ready",
            inputs.snapshot_ready,
            expected_stage=ReadinessStage.SNAPSHOT_READY,
        ),
        run_gate,
        _model_binding_gate(
            context,
            inputs.model_binding,
            inputs.expected_epoch_ref,
            clock_trusted=clock_trusted,
        ),
        _model_qualification_gate(
            context,
            inputs.model_qualification,
            inputs.model_binding,
            clock_trusted=clock_trusted,
        ),
        _registry_gate(
            context,
            inputs.registry_compatibility,
            inputs.model_binding,
            clock_trusted=clock_trusted,
        ),
        _temporal_gate(context, inputs.temporal_dependencies, clock_trusted=clock_trusted),
        _fact_gate(
            context,
            "numerical_environment",
            inputs.numerical_environment,
            clock_trusted=clock_trusted,
        ),
        _seal_gate(context, inputs.seal_capability, clock_trusted=clock_trusted),
    )
    return StageAssessment(ReadinessStage.PREDICTION_READY, context, gates)
