"""Outcome-blind risk-set matching and post-match sampling accounting."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    SCHEMA_TO_CONTRACT,
    canonical_content_hash,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall import (
    TemporalArtifact,
    TemporalFirewall,
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
    TemporalViolation,
)
from qc2_temporal_firewall.models import canonical_json_bytes

from .decoy_models import (
    CaliperRule,
    DecoyReuse,
    FinalizedMatch,
    MatchAssignment,
    MatchPlan,
    MatchedDecoyError,
    MatchedDecoyRecord,
    MatchedDecoyResult,
    MatchedDecoyRiskSet,
    MatchingPolicy,
    OriginalPopulationEvidence,
    PositiveCase,
    RiskSetMember,
    StratumCandidateCount,
    TrainingSampleWeight,
    UnmatchedCase,
    VariableDistance,
)
from .models import (
    FEATURE_SNAPSHOT_SCHEMA,
    OUTCOME_SCHEMA,
    RUNNER_EVENT_SCHEMA,
    GenomeError,
    _artifact_ref,
    _contract_dict,
    _date,
    _ordered_refs,
    _utc,
    contract_artifact,
)

INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
UNIVERSE_MANIFEST_SCHEMA = "qc2.identity_market.UniverseManifest.v1"
DATASET_MANIFEST_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
_POSITIVE_EVENT_TYPES = frozenset({"EXPANSION_RUNNER", "SESSION_MONSTER"})
_OUTCOME_DEPENDENCY_SCHEMAS = frozenset(
    {
        OUTCOME_SCHEMA,
        "qc2.outcomes_research.OutcomeRevision.v1",
        RUNNER_EVENT_SCHEMA,
    }
)
_REGIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MatchedDecoyError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise MatchedDecoyError(f"{field} must be a finite decimal")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _strict_contract(
    artifact: TemporalArtifact, expected_schema: str, label: str
) -> dict[str, Any]:
    if not isinstance(artifact, TemporalArtifact):
        raise MatchedDecoyError(f"{label} must be a TemporalArtifact")
    payload = _contract_dict(artifact.payload)
    if (
        not payload
        or payload.get("schema_name") != expected_schema
        or payload.get("id") != artifact.artifact_id
        or artifact.artifact_kind != expected_schema
    ):
        raise MatchedDecoyError(f"{label} is not backed by a {expected_schema} contract")
    try:
        contract_name = SCHEMA_TO_CONTRACT[expected_schema]
        validate_contract(contract_name, payload)
        if contract_name in CONTENT_ADDRESSED:
            verify_content_hash(contract_name, payload)
        expected = contract_artifact(
            payload,
            known_at=artifact.known_at,
            historical_assumed_available_at=artifact.historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                artifact.historical_assumed_available_for_learning_at
            ),
        )
    except (KeyError, ValueError) as exc:
        raise MatchedDecoyError(f"{label} contract or temporal metadata is invalid: {exc}") from exc
    if expected != artifact:
        raise MatchedDecoyError(f"{label} temporal metadata differs from its persisted contract")
    return payload


def _validate_any_source(artifact: TemporalArtifact) -> None:
    if not isinstance(artifact, TemporalArtifact):
        raise MatchedDecoyError("source catalog entries must be TemporalArtifacts")
    if not artifact.payload:
        return
    payload = _contract_dict(artifact.payload)
    schema_name = payload.get("schema_name")
    if not isinstance(schema_name, str):
        raise MatchedDecoyError("contract-backed source is missing schema_name")
    _strict_contract(artifact, schema_name, "source artifact")


def _catalog(
    artifacts: Sequence[TemporalArtifact],
) -> tuple[TemporalArtifact, ...]:
    by_id: dict[str, TemporalArtifact] = {}
    for artifact in artifacts:
        _validate_any_source(artifact)
        previous = by_id.get(artifact.artifact_id)
        if previous is not None and previous != artifact:
            raise MatchedDecoyError("one temporal source ID resolves to conflicting records")
        by_id[artifact.artifact_id] = artifact
    return tuple(sorted(by_id.values(), key=lambda item: item.artifact_id))


def _catalog_revision(artifacts: Sequence[TemporalArtifact]) -> str:
    rows = [
        {
            "id": item.artifact_id,
            "kind": item.artifact_kind,
            "revision": item.revision_id,
            "hash": item.content_hash,
            "created_at": item.created_at,
            "known_at": item.known_at,
            "available_for_learning_at": item.available_for_learning_at,
            "dependency_refs": list(item.dependency_refs),
        }
        for item in sorted(artifacts, key=lambda value: value.artifact_id)
    ]
    return domain_separated_sha256(
        "qc2.apexlab.matched-decoy-input-catalog.v1", canonical_json_bytes(rows)
    )


def _ref_identity(ref: Mapping[str, Any]) -> tuple[str, str]:
    return (str(ref.get("target_schema_name", "")), str(ref.get("target_id", "")))


def _ref_text(ref: Mapping[str, Any]) -> str:
    return f"{ref['target_schema_name']}:{ref['target_id']}"


def _member_id(member: RiskSetMember) -> str:
    return member.instrument.artifact_id


def _feature_vector(
    member: RiskSetMember, rules: Sequence[CaliperRule]
) -> tuple[dict[str, Decimal] | None, str | None]:
    snapshot = member.feature_snapshot
    if snapshot is None:
        return None, member.missing_feature_reason or "FEATURE_SNAPSHOT_UNAVAILABLE"
    payload = _strict_contract(snapshot, FEATURE_SNAPSHOT_SCHEMA, "FeatureSnapshot")
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for record in payload["feature_values"]:
        by_id.setdefault(record["feature_id"], []).append(record)
    vector: dict[str, Decimal] = {}
    for rule in rules:
        records = by_id.get(rule.feature_id, [])
        if len(records) != 1:
            return None, f"MISSING_OR_DUPLICATE_FEATURE:{rule.feature_id}"
        record = records[0]
        if record["unit"] != rule.unit or record["output_dtype"] != "DECIMAL":
            raise MatchedDecoyError(
                f"feature {rule.feature_id} unit or dtype differs from the frozen policy"
            )
        if record.get("missing_reason") is not None or record.get("value") is None:
            return None, f"MISSING_FEATURE:{rule.feature_id}"
        vector[rule.feature_id] = _decimal(record["value"], rule.feature_id)
    return vector, None


def _unmatched(
    case: TemporalArtifact,
    instrument_ref: Mapping[str, str],
    *,
    session_id: str,
    regime_id: str,
    reason: str,
    required: int,
    pre_matches: int = 0,
    confirmed_matches: int = 0,
) -> UnmatchedCase:
    return UnmatchedCase(
        event_ref=_artifact_ref(case),
        positive_instrument_ref=dict(instrument_ref),
        session_id=session_id,
        regime_id=regime_id,
        reason=reason,
        required_decoys=required,
        pre_outcome_matches=pre_matches,
        confirmed_negative_matches=confirmed_matches,
    )


def match_pre_outcome(
    risk_set: MatchedDecoyRiskSet,
    cases: Sequence[PositiveCase],
    policy: MatchingPolicy,
) -> MatchPlan:
    """Select nearest same-session/regime candidates without access to outcome rows."""
    if not isinstance(risk_set, MatchedDecoyRiskSet):
        raise MatchedDecoyError("risk_set must be a MatchedDecoyRiskSet")
    if not isinstance(policy, MatchingPolicy):
        raise MatchedDecoyError("policy must be a frozen MatchingPolicy")
    if not cases or any(not isinstance(case, PositiveCase) for case in cases):
        raise MatchedDecoyError("at least one PositiveCase is required")

    universe = _strict_contract(
        risk_set.universe_manifest, UNIVERSE_MANIFEST_SCHEMA, "UniverseManifest"
    )
    session_id = _date(universe["session_id"], "UniverseManifest.session_id").isoformat()
    cutoff = universe["cutoff"]
    _utc(cutoff, "UniverseManifest.cutoff")
    if not _REGIME_ID.fullmatch(risk_set.regime_id):
        raise MatchedDecoyError("regime_id must be a stable slug")

    member_by_id: dict[str, RiskSetMember] = {}
    member_refs: dict[str, dict[str, str]] = {}
    for member in risk_set.members:
        if not isinstance(member, RiskSetMember):
            raise MatchedDecoyError("risk-set members must be RiskSetMember values")
        _strict_contract(member.instrument, INSTRUMENT_SCHEMA, "Instrument")
        instrument_ref = _artifact_ref(member.instrument)
        if instrument_ref["target_schema_name"] != INSTRUMENT_SCHEMA:
            raise MatchedDecoyError("risk-set member is not an Instrument")
        instrument_id = member.instrument.artifact_id
        if instrument_id in member_by_id:
            raise MatchedDecoyError("risk set repeats an eligible instrument")
        member_by_id[instrument_id] = member
        member_refs[instrument_id] = instrument_ref
        if member.feature_snapshot is not None:
            feature = _strict_contract(
                member.feature_snapshot, FEATURE_SNAPSHOT_SCHEMA, "FeatureSnapshot"
            )
            if feature["instrument_ref"] != instrument_ref:
                raise MatchedDecoyError("FeatureSnapshot instrument differs from its risk-set member")
            if feature["session_id"] != session_id:
                raise MatchedDecoyError("FeatureSnapshot session differs from the risk set")
            if _utc(feature["decision_cutoff"], "FeatureSnapshot.decision_cutoff") > _utc(
                cutoff, "UniverseManifest.cutoff"
            ):
                raise MatchedDecoyError("FeatureSnapshot decision cutoff follows the risk-set cutoff")

    universe_eligible = {
        (ref["target_schema_name"], ref["target_id"])
        for ref in universe["eligible_instrument_refs"]
    }
    observed_eligible = {
        (ref["target_schema_name"], ref["target_id"]) for ref in member_refs.values()
    }
    if len(universe_eligible) != len(universe["eligible_instrument_refs"]):
        raise MatchedDecoyError("UniverseManifest repeats an eligible instrument")
    if observed_eligible != universe_eligible:
        raise MatchedDecoyError(
            "risk-set members must cover the UniverseManifest eligible population exactly"
        )
    unscorable_ids = {
        ref["target_id"]
        for ref in universe["unscorable_instrument_refs"]
        if ref["target_schema_name"] == INSTRUMENT_SCHEMA
    }

    normalized_cases: list[PositiveCase] = []
    case_by_instrument: dict[str, TemporalArtifact] = {}
    case_refs: set[str] = set()
    label_identity: tuple[str, str] | None = None
    for case in cases:
        event = _strict_contract(case.event, RUNNER_EVENT_SCHEMA, "RunnerEvent")
        if event["event_type"] not in _POSITIVE_EVENT_TYPES:
            raise MatchedDecoyError("only declared positive RunnerEvent types can be matched")
        if event["start_session"] != session_id:
            raise MatchedDecoyError("positive event and risk set must have the same session")
        instrument_ref = event["instrument_ref"]
        if instrument_ref["target_schema_name"] != INSTRUMENT_SCHEMA:
            raise MatchedDecoyError("RunnerEvent instrument_ref is not an Instrument")
        instrument_id = instrument_ref["target_id"]
        if instrument_id not in member_by_id and instrument_id not in unscorable_ids:
            raise MatchedDecoyError("positive event is outside the UniverseManifest census")
        if instrument_id in case_by_instrument:
            raise MatchedDecoyError("risk set contains multiple positive events for one instrument")
        event_ref = _artifact_ref(case.event)
        if event_ref["target_id"] in case_refs:
            raise MatchedDecoyError("positive case list repeats a RunnerEvent")
        current_label = _ref_identity(event["label_ref"])
        if label_identity is None:
            label_identity = current_label
        elif current_label != label_identity:
            raise MatchedDecoyError("one matched-decoy set cannot mix label definitions")
        case_by_instrument[instrument_id] = case.event
        case_refs.add(event_ref["target_id"])
        normalized_cases.append(case)
    normalized_cases.sort(key=lambda item: item.event.artifact_id)

    artifacts: list[TemporalArtifact] = [
        risk_set.universe_manifest,
        *risk_set.source_artifacts,
    ]
    for member in risk_set.members:
        artifacts.append(member.instrument)
        if member.feature_snapshot is not None:
            artifacts.append(member.feature_snapshot)
    catalog = _catalog(artifacts)
    for artifact in catalog:
        schema = _contract_dict(artifact.payload).get("schema_name")
        if schema in {OUTCOME_SCHEMA, "qc2.outcomes_research.OutcomeRevision.v1"}:
            raise MatchedDecoyError(
                "outcome artifacts cannot be inputs to pre-outcome risk-set selection"
            )
    catalog_by_id = {artifact.artifact_id: artifact for artifact in catalog}
    roots = [risk_set.universe_manifest.artifact_id]
    roots.extend(
        sorted(
            member.feature_snapshot.artifact_id
            for member in risk_set.members
            if member.feature_snapshot is not None
        )
    )
    revision = _catalog_revision(catalog)
    try:
        view = TemporalFirewall(catalog, catalog_revision=revision).query(
            TemporalQuery(
                cutoff=cutoff,
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.QUERY,
                artifact_ids=tuple(dict.fromkeys(roots)),
            ),
            TemporalPermission(
                operations=frozenset({TemporalOperation.QUERY}),
                artifact_kinds=frozenset(
                    {UNIVERSE_MANIFEST_SCHEMA, FEATURE_SNAPSHOT_SCHEMA}
                ),
                allow_historical_reconstructed=False,
            ),
        )
    except TemporalViolation as exc:
        raise MatchedDecoyError(f"cutoff-safe feature proof failed: {exc}") from exc

    proof_hash_by_id: dict[str, str] = {}
    for root_id in roots:
        closure = view.dependency_closure.get(root_id, ())
        if any(
            catalog_by_id[dependency_id].artifact_kind in _OUTCOME_DEPENDENCY_SCHEMAS
            for dependency_id in closure
            if dependency_id in catalog_by_id
        ):
            raise MatchedDecoyError(
                "outcome-derived dependencies are forbidden in matching feature lineage"
            )
        proof_hash_by_id[root_id] = domain_separated_sha256(
            "qc2.apexlab.matched-decoy-feature-proof.v1",
            canonical_json_bytes(
                {
                    "root_id": root_id,
                    "cutoff": cutoff,
                    "catalog_revision": revision,
                    "dependency_closure": list(closure),
                }
            ),
        )

    vector_by_instrument: dict[str, dict[str, Decimal] | None] = {}
    unusable_reason: dict[str, str] = {}
    for instrument_id, member in member_by_id.items():
        vector, reason = _feature_vector(member, policy.rules)
        vector_by_instrument[instrument_id] = vector
        if reason is not None:
            unusable_reason[instrument_id] = reason

    assignments: list[MatchAssignment] = []
    unmatched: list[UnmatchedCase] = []
    candidate_counts: list[StratumCandidateCount] = []
    for case in normalized_cases:
        event = _contract_dict(case.event.payload)
        event_ref = _artifact_ref(case.event)
        positive_ref = dict(event["instrument_ref"])
        positive_id = positive_ref["target_id"]
        member = member_by_id.get(positive_id)
        same_stratum_count = max(0, len(member_by_id) - (1 if member else 0))
        feature_usable = sum(
            1
            for candidate_id, candidate_vector in vector_by_instrument.items()
            if candidate_id != positive_id and candidate_vector is not None
        )
        within_caliper: list[
            tuple[Decimal, str, dict[str, Decimal], tuple[VariableDistance, ...]]
        ] = []
        case_vector: dict[str, Decimal] | None = None
        case_reason: str | None = None

        if member is None:
            case_reason = "POSITIVE_CASE_OUTSIDE_ELIGIBLE_RISK_SET"
        else:
            case_vector, case_reason = _feature_vector(member, policy.rules)
            if case_vector is not None:
                for candidate_id in sorted(member_by_id):
                    if candidate_id == positive_id:
                        continue
                    candidate = member_by_id[candidate_id]
                    candidate_vector = vector_by_instrument[candidate_id]
                    if candidate_vector is None:
                        continue
                    distances: list[VariableDistance] = []
                    total = Decimal(0)
                    within = True
                    for rule in policy.rules:
                        delta = abs(case_vector[rule.feature_id] - candidate_vector[rule.feature_id])
                        if delta > rule.maximum_difference:
                            within = False
                        scaled = delta / rule.scale
                        distances.append(
                            VariableDistance(
                                feature_id=rule.feature_id,
                                absolute_difference=delta,
                                scaled_difference=scaled,
                                maximum_difference=rule.maximum_difference,
                            )
                        )
                        total += scaled
                    if within:
                        within_caliper.append(
                            (total, candidate_id, candidate_vector, tuple(distances))
                        )
        within_caliper.sort(key=lambda item: (item[0], item[1]))
        selected = within_caliper[: policy.decoys_per_case]

        if member is None or case_vector is None:
            reason = case_reason or "POSITIVE_MATCHING_FEATURES_UNAVAILABLE"
        elif not selected:
            reason = "NO_SAME_STRATUM_CANDIDATE_WITHIN_CALIPERS"
        elif len(selected) < policy.decoys_per_case:
            reason = "INSUFFICIENT_PRE_OUTCOME_MATCHES"
        else:
            reason = ""

        candidate_counts.append(
            StratumCandidateCount(
                event_ref=event_ref,
                same_stratum_candidates=same_stratum_count,
                feature_usable_candidates=feature_usable,
                within_caliper_candidates=len(within_caliper),
                selected_candidates=len(selected),
            )
        )
        if reason:
            unmatched.append(
                _unmatched(
                    case.event,
                    positive_ref,
                    session_id=session_id,
                    regime_id=risk_set.regime_id,
                    reason=reason,
                    required=policy.decoys_per_case,
                    pre_matches=len(selected),
                )
            )
        if member is not None and case_vector is not None:
            case_snapshot = member.feature_snapshot
            if case_snapshot is None:
                raise MatchedDecoyError("usable positive feature vector lacks its snapshot")
            for rank, (total, candidate_id, _, distances) in enumerate(selected, start=1):
                candidate = member_by_id[candidate_id]
                candidate_snapshot = candidate.feature_snapshot
                if candidate_snapshot is None:
                    raise MatchedDecoyError("usable decoy feature vector lacks its snapshot")
                assignments.append(
                    MatchAssignment(
                        event_ref=event_ref,
                        positive_instrument_ref=positive_ref,
                        decoy_instrument_ref=member_refs[candidate_id],
                        session_id=session_id,
                        regime_id=risk_set.regime_id,
                        positive_feature_snapshot_ref=_artifact_ref(case_snapshot),
                        decoy_feature_snapshot_ref=_artifact_ref(candidate_snapshot),
                        positive_feature_proof_hash=proof_hash_by_id[
                            case_snapshot.artifact_id
                        ],
                        decoy_feature_proof_hash=proof_hash_by_id[
                            candidate_snapshot.artifact_id
                        ],
                        variable_distances=distances,
                        total_distance=total,
                        candidate_rank=rank,
                    )
                )

    return MatchPlan(
        risk_set=risk_set,
        policy=policy,
        cases=tuple(normalized_cases),
        assignments=tuple(assignments),
        unmatched_cases=tuple(unmatched),
        candidate_counts=tuple(candidate_counts),
        catalog_revision=revision,
        universe_ref=_artifact_ref(risk_set.universe_manifest),
        session_id=session_id,
        decision_cutoff=cutoff,
    )


def _unmatched_json(item: UnmatchedCase) -> str:
    return canonical_json_bytes(
        {
            "event_ref": dict(item.event_ref),
            "positive_instrument_ref": dict(item.positive_instrument_ref),
            "session_id": item.session_id,
            "regime_id": item.regime_id,
            "reason": item.reason,
            "required_decoys": item.required_decoys,
            "pre_outcome_matches": item.pre_outcome_matches,
            "confirmed_negative_matches": item.confirmed_negative_matches,
        }
    ).decode("utf-8")


def _assignment_payload(item: MatchAssignment) -> dict[str, Any]:
    return {
        "event_ref": dict(item.event_ref),
        "positive_instrument_ref": dict(item.positive_instrument_ref),
        "decoy_instrument_ref": dict(item.decoy_instrument_ref),
        "session_id": item.session_id,
        "regime_id": item.regime_id,
        "positive_feature_snapshot_ref": dict(item.positive_feature_snapshot_ref),
        "decoy_feature_snapshot_ref": dict(item.decoy_feature_snapshot_ref),
        "positive_feature_proof_hash": item.positive_feature_proof_hash,
        "decoy_feature_proof_hash": item.decoy_feature_proof_hash,
        "variable_distances": [
            {
                "feature_id": value.feature_id,
                "absolute_difference": _decimal_text(value.absolute_difference),
                "scaled_difference": _decimal_text(value.scaled_difference),
                "maximum_difference": _decimal_text(value.maximum_difference),
            }
            for value in item.variable_distances
        ],
        "total_distance": _decimal_text(item.total_distance),
        "candidate_rank": item.candidate_rank,
    }


def finalize_matched_decoy_set(
    plan: MatchPlan,
    population: OriginalPopulationEvidence,
    *,
    created_at: str,
) -> MatchedDecoyResult:
    """Apply resolved outcome membership after selection; never backfill rejected matches."""
    if not isinstance(plan, MatchPlan):
        raise MatchedDecoyError("plan must be a MatchPlan")
    if not isinstance(population, OriginalPopulationEvidence):
        raise MatchedDecoyError("population must be OriginalPopulationEvidence")
    try:
        created_dt = _utc(created_at, "MatchedDecoySet.created_at")
        _strict_contract(
            plan.risk_set.universe_manifest, UNIVERSE_MANIFEST_SCHEMA, "UniverseManifest"
        )
        dataset = _strict_contract(
            population.dataset_manifest, DATASET_MANIFEST_SCHEMA, "DatasetManifest"
        )
    except GenomeError as exc:
        raise MatchedDecoyError(str(exc)) from exc

    sample_policy = dataset["sampling_policy"].lower()
    if any(token in sample_policy for token in ("case-control", "case_control", "matched", "decoy", "balanced")):
        raise MatchedDecoyError(
            "original_population_ref must refer to an unbalanced original-population dataset"
        )
    if dataset["universe_fidelity"] != "PIT_VERIFIED":
        raise MatchedDecoyError("original-population DatasetManifest must be PIT_VERIFIED")
    session_date = _date(plan.session_id, "risk-set session")
    if not (
        _date(dataset["time_start"], "DatasetManifest.time_start")
        <= session_date
        <= _date(dataset["time_end"], "DatasetManifest.time_end")
    ):
        raise MatchedDecoyError("original-population DatasetManifest does not cover the risk-set session")
    universe_ref = _artifact_ref(plan.risk_set.universe_manifest)
    if universe_ref not in dataset["source_refs"]:
        raise MatchedDecoyError(
            "original-population DatasetManifest must reference the exact UniverseManifest"
        )

    members = {
        member.instrument.artifact_id: member for member in plan.risk_set.members
    }
    eligible_ids = set(members)
    event_by_instrument: dict[str, TemporalArtifact] = {}
    label_refs: set[tuple[str, str]] = set()
    for case in plan.cases:
        event = _strict_contract(case.event, RUNNER_EVENT_SCHEMA, "RunnerEvent")
        instrument_id = event["instrument_ref"]["target_id"]
        event_by_instrument[instrument_id] = case.event
        label_refs.add(_ref_identity(event["label_ref"]))
    if len(label_refs) != 1:
        raise MatchedDecoyError("matched-decoy outcome population must use one label definition")
    expected_label = next(iter(label_refs))

    outcomes_by_instrument: dict[str, TemporalArtifact] = {}
    for outcome_artifact in population.outcome_artifacts:
        outcome = _strict_contract(outcome_artifact, OUTCOME_SCHEMA, "Outcome")
        if outcome["session_id"] != plan.session_id:
            raise MatchedDecoyError("Outcome session differs from the matched risk set")
        instrument_id = outcome["instrument_ref"]["target_id"]
        if instrument_id in outcomes_by_instrument:
            raise MatchedDecoyError("original population repeats an Outcome for one instrument")
        if _ref_identity(outcome["label_ref"]) != expected_label:
            raise MatchedDecoyError("original-population outcomes use a different label definition")
        outcomes_by_instrument[instrument_id] = outcome_artifact

    if not eligible_ids.issubset(outcomes_by_instrument):
        raise MatchedDecoyError("original-population evidence must cover every eligible instrument")
    event_ids = set(event_by_instrument)
    allowed_outcome_ids = eligible_ids | event_ids
    if set(outcomes_by_instrument) - allowed_outcome_ids:
        raise MatchedDecoyError("outcome evidence contains instruments outside the original risk set")

    membership: dict[str, str] = {}
    membership_rows: list[dict[str, Any]] = []
    population_available_times: list[str] = [population.dataset_manifest.known_at]
    for instrument_id in sorted(eligible_ids):
        outcome_artifact = outcomes_by_instrument[instrument_id]
        outcome = _contract_dict(outcome_artifact.payload)
        member_ref = _artifact_ref(members[instrument_id].instrument)
        if outcome["instrument_ref"] != member_ref:
            raise MatchedDecoyError("Outcome instrument does not match the eligible member")
        event_artifact = event_by_instrument.get(instrument_id)
        if event_artifact is not None:
            event = _contract_dict(event_artifact.payload)
            if event["outcome_ref"] != _artifact_ref(outcome_artifact):
                raise MatchedDecoyError("positive RunnerEvent does not reference its resolved Outcome")
            if event["label_ref"] != outcome["label_ref"]:
                raise MatchedDecoyError("positive RunnerEvent and Outcome labels differ")
        if outcome["outcome_state"] == "RESOLVED":
            available = outcome.get("available_for_learning_at")
            if not isinstance(available, str):
                raise MatchedDecoyError("resolved Outcome lacks learning availability")
            _utc(available, "Outcome.available_for_learning_at")
            membership[instrument_id] = "POSITIVE" if event_artifact else "NEGATIVE"
            population_available_times.append(available)
        else:
            if event_artifact is not None:
                raise MatchedDecoyError("positive RunnerEvent cannot have an unresolved Outcome")
            membership[instrument_id] = "UNRESOLVED"
        membership_rows.append(
            {
                "instrument_ref": member_ref,
                "outcome_ref": _artifact_ref(outcome_artifact),
                "label_ref": outcome["label_ref"],
                "membership": membership[instrument_id],
            }
        )

    for instrument_id, event_artifact in event_by_instrument.items():
        outcome_artifact = outcomes_by_instrument.get(instrument_id)
        if outcome_artifact is None:
            raise MatchedDecoyError("every positive RunnerEvent requires its source Outcome")
        event = _contract_dict(event_artifact.payload)
        outcome = _contract_dict(outcome_artifact.payload)
        if outcome["instrument_ref"] != event["instrument_ref"]:
            raise MatchedDecoyError("RunnerEvent and Outcome instruments differ")
        if outcome["outcome_state"] != "RESOLVED":
            raise MatchedDecoyError("positive RunnerEvent requires a resolved Outcome")
        if event["outcome_ref"] != _artifact_ref(outcome_artifact):
            raise MatchedDecoyError("RunnerEvent outcome reference differs from the source Outcome")
        if not isinstance(outcome.get("available_for_learning_at"), str):
            raise MatchedDecoyError("positive RunnerEvent Outcome lacks learning availability")
        if instrument_id not in eligible_ids:
            membership_rows.append(
                {
                    "instrument_ref": event["instrument_ref"],
                    "outcome_ref": _artifact_ref(outcome_artifact),
                    "label_ref": event["label_ref"],
                    "membership": "POSITIVE_OUTSIDE_ELIGIBLE_RISK_SET",
                }
            )
        population_available_times.append(outcome["available_for_learning_at"])

    outcome_membership_hash = domain_separated_sha256(
        "qc2.apexlab.matched-decoy-outcome-membership.v1",
        canonical_json_bytes(membership_rows),
    )

    pre_use_counts = Counter(
        item.decoy_instrument_ref["target_id"] for item in plan.assignments
    )
    retained_assignments = [
        item
        for item in plan.assignments
        if membership.get(item.decoy_instrument_ref["target_id"]) == "NEGATIVE"
    ]
    negative_use_counts = Counter(
        item.decoy_instrument_ref["target_id"] for item in retained_assignments
    )
    finalized = tuple(
        FinalizedMatch(
            assignment=item,
            outcome_membership=membership.get(
                item.decoy_instrument_ref["target_id"], "OUTSIDE_ORIGINAL_POPULATION"
            ),
            reuse_count=pre_use_counts[item.decoy_instrument_ref["target_id"]],
            retained_as_decoy=membership.get(
                item.decoy_instrument_ref["target_id"]
            )
            == "NEGATIVE",
        )
        for item in plan.assignments
    )
    reuse_rows = tuple(
        DecoyReuse(
            instrument_ref=_artifact_ref(members[instrument_id].instrument),
            pre_outcome_use_count=pre_use_counts[instrument_id],
            confirmed_negative_use_count=negative_use_counts[instrument_id],
            outcome_membership=membership.get(instrument_id, "OUTSIDE_ORIGINAL_POPULATION"),
        )
        for instrument_id in sorted(pre_use_counts)
    )
    decoy_refs = _ordered_refs(
        [
            _artifact_ref(members[instrument_id].instrument)
            for instrument_id in sorted(negative_use_counts)
        ]
    )

    assignments_by_event: dict[str, list[MatchAssignment]] = {}
    for assignment in plan.assignments:
        assignments_by_event.setdefault(assignment.event_ref["target_id"], []).append(
            assignment
        )
    pre_unmatched_by_event = {
        item.event_ref["target_id"]: item for item in plan.unmatched_cases
    }
    unmatched_final: list[UnmatchedCase] = []
    cases_by_event_id = {
        case.event.artifact_id: case.event for case in plan.cases
    }
    for event_id in sorted(cases_by_event_id):
        event_artifact = cases_by_event_id[event_id]
        event = _contract_dict(event_artifact.payload)
        instrument_ref = event["instrument_ref"]
        attempts = assignments_by_event.get(event_id, [])
        confirmed = sum(
            1
            for assignment in attempts
            if membership.get(assignment.decoy_instrument_ref["target_id"]) == "NEGATIVE"
        )
        if confirmed >= plan.policy.decoys_per_case:
            continue
        if not attempts:
            prior = pre_unmatched_by_event.get(event_id)
            reason = prior.reason if prior else "NO_PRE_OUTCOME_MATCHES"
        elif confirmed < len(attempts):
            reason = "POST_MATCH_OUTCOME_MEMBERSHIP_REJECTED_CANDIDATES"
        else:
            reason = "INSUFFICIENT_PRE_OUTCOME_MATCHES"
        unmatched_final.append(
            _unmatched(
                event_artifact,
                instrument_ref,
                session_id=plan.session_id,
                regime_id=plan.risk_set.regime_id,
                reason=reason,
                required=plan.policy.decoys_per_case,
                pre_matches=len(attempts),
                confirmed_matches=confirmed,
            )
        )

    positive_population_count = sum(
        1 for status in membership.values() if status == "POSITIVE"
    )
    negative_population_count = sum(
        1 for status in membership.values() if status == "NEGATIVE"
    )
    unresolved_population_count = sum(
        1 for status in membership.values() if status == "UNRESOLVED"
    )
    positive_sample_count = sum(
        1 for instrument_id in eligible_ids if membership[instrument_id] == "POSITIVE"
    )
    unique_negative_sample_count = len(negative_use_counts)
    natural_prevalence: Decimal | None = None
    sample_prevalence: Decimal | None = None
    weights: tuple[TrainingSampleWeight, ...] = ()
    if unresolved_population_count:
        weight_status = "NOT_ESTIMABLE_UNRESOLVED_OUTCOMES"
    elif positive_population_count == 0 or negative_population_count == 0:
        weight_status = "NOT_ESTIMABLE_SINGLE_CLASS_POPULATION"
    elif positive_sample_count == 0 or unique_negative_sample_count == 0:
        weight_status = "NOT_ESTIMABLE_EMPTY_TRAINING_CLASS"
    else:
        natural_prevalence = Decimal(positive_population_count) / Decimal(
            positive_population_count + negative_population_count
        )
        sample_prevalence = Decimal(positive_sample_count) / Decimal(
            positive_sample_count + unique_negative_sample_count
        )
        positive_weight = natural_prevalence / sample_prevalence
        negative_weight = (Decimal(1) - natural_prevalence) / (
            Decimal(1) - sample_prevalence
        )
        samples: list[TrainingSampleWeight] = []
        for instrument_id in sorted(eligible_ids):
            if membership[instrument_id] != "POSITIVE":
                continue
            event_artifact = event_by_instrument[instrument_id]
            samples.append(
                TrainingSampleWeight(
                    sample_kind="POSITIVE_CASE",
                    sample_ref=_artifact_ref(event_artifact),
                    weight=positive_weight,
                    reuse_count=1,
                )
            )
        for instrument_id in sorted(negative_use_counts):
            samples.append(
                TrainingSampleWeight(
                    sample_kind="UNIQUE_NEGATIVE_DECOY",
                    sample_ref=_artifact_ref(members[instrument_id].instrument),
                    weight=negative_weight,
                    reuse_count=negative_use_counts[instrument_id],
                )
            )
        weights = tuple(samples)
        weight_status = "CLASS_PRIOR_CORRECTION_ONLY"

    source_artifacts = _catalog(
        [
            plan.risk_set.universe_manifest,
            *plan.risk_set.source_artifacts,
            *(member.instrument for member in plan.risk_set.members),
            *(
                member.feature_snapshot
                for member in plan.risk_set.members
                if member.feature_snapshot is not None
            ),
            *[case.event for case in plan.cases],
            population.dataset_manifest,
            *population.source_artifacts,
            *population.outcome_artifacts,
        ]
    )
    latest_source_times = [item.known_at for item in source_artifacts]
    latest_source_times.extend(
        item.available_for_learning_at
        for item in source_artifacts
        if item.available_for_learning_at is not None
    )
    latest_source_times.extend(population_available_times)
    if any(created_dt < _utc(value, "source availability") for value in latest_source_times):
        raise MatchedDecoyError("MatchedDecoySet creation precedes an input's availability")

    source_refs = _ordered_refs(
        [
            _artifact_ref(item)
            for item in source_artifacts
            if item.payload
        ]
    )
    unmatched_strings = [_unmatched_json(item) for item in unmatched_final]
    calipers = [
        f"{rule.feature_id}|unit={rule.unit}|abs_diff<={_decimal_text(rule.maximum_difference)}"
        for rule in plan.policy.rules
    ]
    calipers.extend(
        [
            "distance_metric=SCALED_L1",
            f"decoys_per_case={plan.policy.decoys_per_case}",
            "reuse=WITH_REPLACEMENT_UNBOUNDED",
            "outcome_filtering=POST_MATCH_ONLY_NO_BACKFILL",
        ]
    )
    contract: dict[str, Any] = {
        "schema_name": "qc2.outcomes_research.MatchedDecoySet.v1",
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": created_at,
        "owning_authority": "apexlab",
        "evidence_class": _contract_dict(plan.risk_set.universe_manifest.payload)[
            "evidence_class"
        ],
        "environment_namespace": _contract_dict(
            plan.risk_set.universe_manifest.payload
        )["environment_namespace"],
        "source_refs": source_refs,
        "content_hash": "0" * 64,
        "positive_event_refs": _ordered_refs(
            [_artifact_ref(case.event) for case in plan.cases]
        ),
        "decoy_instrument_refs": decoy_refs,
        "matching_procedure_hash": domain_separated_sha256(
            "qc2.apexlab.matched-decoy-policy.v1",
            canonical_json_bytes(plan.policy.canonical_payload()),
        ),
        "pre_outcome_variable_ids": list(plan.policy.feature_ids),
        "strata": [
            f"session_id={plan.session_id}",
            f"regime_id={plan.risk_set.regime_id}",
        ],
        "calipers": calipers,
        "unmatched_cases": unmatched_strings,
        "outcome_membership_hash": outcome_membership_hash,
    }
    try:
        contract["content_hash"] = canonical_content_hash("MatchedDecoySet", contract)
        validate_contract("MatchedDecoySet", contract)
        verify_content_hash("MatchedDecoySet", contract)
    except ValueError as exc:
        raise MatchedDecoyError(f"MatchedDecoySet contract is invalid: {exc}") from exc

    available_for_learning_at = max(
        [created_at, *population_available_times],
        key=lambda value: _utc(value, "MatchedDecoySet learning availability"),
    )
    temporal = TemporalArtifact.from_contract(
        contract,
        known_at=created_at,
        available_for_learning_at=available_for_learning_at,
    )
    record = MatchedDecoyRecord(
        canonical_json=canonical_json_bytes(contract).decode("utf-8"),
        temporal_artifact=temporal,
    )
    audit_payload = {
        "policy": plan.policy.canonical_payload(),
        "policy_hash": contract["matching_procedure_hash"],
        "risk_set_ref": dict(plan.universe_ref),
        "original_population_ref": _artifact_ref(population.dataset_manifest),
        "session_id": plan.session_id,
        "regime_id": plan.risk_set.regime_id,
        "decision_cutoff": plan.decision_cutoff,
        "catalog_revision": plan.catalog_revision,
        "candidate_counts": [
            {
                "event_ref": dict(row.event_ref),
                "same_stratum_candidates": row.same_stratum_candidates,
                "feature_usable_candidates": row.feature_usable_candidates,
                "within_caliper_candidates": row.within_caliper_candidates,
                "selected_candidates": row.selected_candidates,
            }
            for row in plan.candidate_counts
        ],
        "assignments": [
            {
                **_assignment_payload(item.assignment),
                "outcome_membership": item.outcome_membership,
                "reuse_count": item.reuse_count,
                "retained_as_decoy": item.retained_as_decoy,
            }
            for item in finalized
        ],
        "reuse": [
            {
                "instrument_ref": dict(row.instrument_ref),
                "pre_outcome_use_count": row.pre_outcome_use_count,
                "confirmed_negative_use_count": row.confirmed_negative_use_count,
                "outcome_membership": row.outcome_membership,
            }
            for row in reuse_rows
        ],
        "unmatched_cases": [_unmatched_json(item) for item in unmatched_final],
        "outcome_membership_hash": outcome_membership_hash,
        "population_counts": {
            "positive": positive_population_count,
            "negative": negative_population_count,
            "unresolved": unresolved_population_count,
        },
        "sample_counts": {
            "positive": positive_sample_count,
            "unique_negative_decoys": unique_negative_sample_count,
        },
        "natural_prevalence": (
            _decimal_text(natural_prevalence) if natural_prevalence is not None else None
        ),
        "sample_prevalence": (
            _decimal_text(sample_prevalence) if sample_prevalence is not None else None
        ),
        "weights": [
            {
                "sample_kind": item.sample_kind,
                "sample_ref": dict(item.sample_ref),
                "weight": _decimal_text(item.weight),
                "reuse_count": item.reuse_count,
            }
            for item in weights
        ],
        "weight_status": weight_status,
        "calibration_eligible": False,
    }
    audit_hash = domain_separated_sha256(
        "qc2.apexlab.matched-decoy-audit.v1", canonical_json_bytes(audit_payload)
    )
    return MatchedDecoyResult(
        record=record,
        plan=plan,
        finalized_matches=finalized,
        reuse=reuse_rows,
        unmatched_cases=tuple(unmatched_final),
        original_population_ref=_artifact_ref(population.dataset_manifest),
        positive_population_count=positive_population_count,
        negative_population_count=negative_population_count,
        unresolved_population_count=unresolved_population_count,
        natural_prevalence=natural_prevalence,
        sample_prevalence=sample_prevalence,
        training_sample_weights=weights,
        weight_status=weight_status,
        audit_hash=audit_hash,
        calibration_eligible=False,
    )


def require_original_distribution_calibration(
    result: MatchedDecoyResult, evaluation_population_ref: Mapping[str, Any]
) -> Mapping[str, str]:
    """Reject calibration on the matched sample; require the referenced source population."""
    if not isinstance(result, MatchedDecoyResult):
        raise MatchedDecoyError("result must be a MatchedDecoyResult")
    ref = dict(evaluation_population_ref)
    if ref != dict(result.original_population_ref):
        raise MatchedDecoyError(
            "probability calibration must use the original population, not the matched case-control sample"
        )
    if result.unresolved_population_count:
        raise MatchedDecoyError(
            "original-population probability calibration is unavailable while outcomes are unresolved"
        )
    return result.original_population_ref
