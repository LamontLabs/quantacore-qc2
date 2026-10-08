"""Append-only RunnerGenome storage and cutoff-bound memory indexes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    SCHEMA_TO_CONTRACT,
    ContractValidationError,
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

from .models import (
    ARTIFACT_MANIFEST_SCHEMA,
    FEATURE_SNAPSHOT_SCHEMA,
    MARKET_SNAPSHOT_SCHEMA,
    MEMORY_INDEX_SCHEMA,
    OUTCOME_SCHEMA,
    PREDICTION_SCHEMA,
    RUNNER_EVENT_SCHEMA,
    RUNNER_GENOME_SCHEMA,
    GenomeDraft,
    GenomeError,
    GenomeLookup,
    MemoryIndexLookup,
    MemoryIndexRecord,
    RunnerGenomeRecord,
    _artifact_ref,
    _contract_dict,
    _date,
    _max_actual_source_time,
    _max_timestamp,
    _ordered_refs,
    _timestamp_text,
    _utc,
    _assert_historical_sources,
    contract_artifact,
    eligibility_proof_hash,
    member_inventory_hash,
)

_SNAPSHOT_SCHEMAS = frozenset({MARKET_SNAPSHOT_SCHEMA, FEATURE_SNAPSHOT_SCHEMA})
_PROVENANCE_SCHEMAS = frozenset(
    {
        "qc2.integrity_build.EvidenceEvent.v1",
        "qc2.identity_market.DataBundle.v1",
        "qc2.outcomes_research.OutcomeRevision.v1",
    }
)
_TEMPORAL_DEPENDENCY_SCHEMAS = frozenset(
    {
        MARKET_SNAPSHOT_SCHEMA,
        FEATURE_SNAPSHOT_SCHEMA,
        PREDICTION_SCHEMA,
        OUTCOME_SCHEMA,
        "qc2.outcomes_research.OutcomeRevision.v1",
        "qc2.integrity_build.EvidenceEvent.v1",
    }
)


@dataclass(frozen=True, slots=True)
class _StoredRecord:
    canonical_json: str
    temporal_artifact: TemporalArtifact


class RunnerGenomeStore:
    """In-memory append-only research store; no durable adapter is implied.

    Source contracts enter through ``contract_artifact`` and are schema/hash
    checked. Temporal dependency entries can be supplied by an authoritative
    source adapter as ``TemporalArtifact`` values. Every returned genome or
    index is validated through the temporal firewall before it is exposed.
    """

    def __init__(self) -> None:
        self._sources: dict[str, TemporalArtifact] = {}
        self._genomes: dict[str, RunnerGenomeRecord] = {}
        self._indexes: dict[str, MemoryIndexRecord] = {}

    def add_source(self, artifact: TemporalArtifact) -> None:
        """Append a strictly validated contract source."""
        payload = self._validated_payload(artifact, require_contract=True)
        expected = contract_artifact(
            payload,
            known_at=artifact.known_at,
            historical_assumed_available_at=artifact.historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                artifact.historical_assumed_available_for_learning_at
            ),
        )
        if expected != artifact:
            raise GenomeError("source temporal metadata does not match its QC2 contract")
        self._append_temporal_source(artifact)

    def add_temporal_dependency(self, artifact: TemporalArtifact) -> None:
        """Append an adapter-supplied temporal dependency used for closure checks.

        Non-contract leaf metadata may have an empty payload; contract-backed
        entries are schema/hash checked just like direct sources.
        """
        if artifact.payload:
            payload = self._validated_payload(artifact, require_contract=True)
            expected = contract_artifact(
                payload,
                known_at=artifact.known_at,
                historical_assumed_available_at=artifact.historical_assumed_available_at,
                historical_assumed_available_for_learning_at=(
                    artifact.historical_assumed_available_for_learning_at
                ),
            )
            if expected != artifact:
                raise GenomeError("dependency temporal metadata does not match its contract")
        self._append_temporal_source(artifact)

    def create_runner_genome(self, draft: GenomeDraft) -> RunnerGenomeRecord:
        if not isinstance(draft, GenomeDraft):
            raise GenomeError("create_runner_genome requires a GenomeDraft")
        event_artifact = self._source(draft.event_id, RUNNER_EVENT_SCHEMA)
        event = _contract_dict(event_artifact.payload)
        snapshots = [
            self._source(source_id, schema_names=_SNAPSHOT_SCHEMAS)
            for source_id in draft.pre_event_snapshot_ids
        ]
        predictions = [
            self._source(source_id, PREDICTION_SCHEMA)
            for source_id in draft.prediction_ids
        ]
        outcomes = [self._source(source_id, OUTCOME_SCHEMA) for source_id in draft.outcome_ids]
        provenance = [
            self._source(source_id, schema_names=_PROVENANCE_SCHEMAS)
            for source_id in draft.provenance_ids
        ]
        selected_sources = [event_artifact, *snapshots, *predictions, *outcomes, *provenance]
        self._assert_coherent_sources(selected_sources, event_artifact.evidence_class)
        self._assert_event_and_sources(
            event,
            event_artifact,
            snapshots,
            predictions,
            outcomes,
            requested_event_time=draft.event_time,
            historical_reconstructed=(
                event_artifact.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED"
            ),
        )

        actual_created_at = _timestamp_text(draft.created_at, "created_at")
        reviewed_at = _timestamp_text(draft.review_completed_at, "review_completed_at")
        event_time = _timestamp_text(draft.event_time, "event_time")
        latest_actual_source = _max_actual_source_time(selected_sources)
        if _utc(actual_created_at, "created_at") < _utc(latest_actual_source, "source availability"):
            raise GenomeError("genome creation cannot precede actual source availability")
        if _utc(actual_created_at, "created_at") < _utc(reviewed_at, "review_completed_at"):
            raise GenomeError("genome creation cannot precede completed curation review")

        evidence_class = event_artifact.evidence_class
        is_historical = evidence_class.upper() == "HISTORICAL_RECONSTRUCTED"
        if is_historical:
            _assert_historical_sources(selected_sources)
            assumed_available = draft.historical_assumed_available_at
            assumed_learning = draft.historical_assumed_available_for_learning_at
            if assumed_available is None or assumed_learning is None:
                raise GenomeError("reconstructed genomes require explicit historical availability")
            if _utc(assumed_available, "historical_assumed_available_at") < _utc(
                event_time, "event_time"
            ):
                raise GenomeError("historical availability cannot precede the underlying event")
            source_available_times = [
                _utc(source.historical_assumed_available_at, "source historical availability")
                for source in selected_sources
                if source.historical_assumed_available_at is not None
            ]
            if _utc(assumed_available, "historical_assumed_available_at") < max(
                source_available_times
            ):
                raise GenomeError("historical availability precedes a source availability assumption")
            if _utc(assumed_learning, "historical_assumed_available_for_learning_at") < _utc(
                assumed_available, "historical_assumed_available_at"
            ):
                raise GenomeError("historical learning availability precedes historical availability")
            if _utc(assumed_learning, "historical_assumed_available_for_learning_at") < max(
                _utc(source.historical_assumed_available_for_learning_at, "source historical learning")
                for source in selected_sources
                if source.historical_assumed_available_for_learning_at is not None
            ):
                raise GenomeError("historical learning time precedes a source learning assumption")
        else:
            if (
                draft.historical_assumed_available_at is not None
                or draft.historical_assumed_available_for_learning_at is not None
            ):
                raise GenomeError("forward genomes cannot carry retrospective availability claims")

        learning_times = [
            actual_created_at,
            reviewed_at,
            event["detected_at"],
            *(source.known_at for source in selected_sources),
            *(
                source.available_for_learning_at
                for source in selected_sources
                if source.available_for_learning_at is not None
            ),
            *(
                outcome["available_for_learning_at"]
                for outcome in ( _contract_dict(item.payload) for item in outcomes)
                if outcome["available_for_learning_at"] is not None
            ),
        ]
        if draft.learning_embargo_until is not None:
            learning_times.append(
                _timestamp_text(draft.learning_embargo_until, "learning_embargo_until")
            )
        available_for_learning_at = _max_timestamp(
            learning_times, "available_for_learning_at"
        )
        if _utc(available_for_learning_at, "available_for_learning_at") < _utc(
            actual_created_at, "created_at"
        ):
            raise GenomeError("learning availability cannot precede actual genome creation")

        direct_sources = [*selected_sources]
        source_refs = _ordered_refs([_artifact_ref(item) for item in direct_sources])
        snapshot_refs = _ordered_refs([_artifact_ref(item) for item in snapshots])
        prediction_refs = _ordered_refs([_artifact_ref(item) for item in predictions])
        outcome_refs = _ordered_refs([_artifact_ref(item) for item in outcomes])
        provenance_refs = _ordered_refs([_artifact_ref(item) for item in provenance])
        temporal_dependency_refs = _ordered_refs(
            [
                _artifact_ref(item)
                for item in [*snapshots, *predictions, *outcomes, *provenance]
                if item.artifact_kind in _TEMPORAL_DEPENDENCY_SCHEMAS
            ]
        )
        genome: dict[str, Any] = {
            "schema_name": RUNNER_GENOME_SCHEMA,
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": actual_created_at,
            "owning_authority": "apexlab",
            "evidence_class": evidence_class,
            "environment_namespace": event["environment_namespace"],
            "source_refs": source_refs,
            "content_hash": "0" * 64,
            "event_ref": _artifact_ref(event_artifact),
            "pre_event_snapshot_refs": snapshot_refs,
            "prediction_refs": prediction_refs,
            "outcome_refs": outcome_refs,
            "provenance_refs": provenance_refs,
            "curation_version": draft.curation_version,
            "event_time": event_time,
            "available_for_learning_at": available_for_learning_at,
            "temporal_dependency_refs": temporal_dependency_refs,
        }
        try:
            genome["content_hash"] = canonical_content_hash("RunnerGenome", genome)
            validate_contract("RunnerGenome", genome)
            verify_content_hash("RunnerGenome", genome)
        except ContractValidationError as exc:
            raise GenomeError(f"RunnerGenome contract is invalid: {exc}") from exc

        temporal = TemporalArtifact.from_contract(
            genome,
            known_at=actual_created_at,
            historical_assumed_available_at=draft.historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                draft.historical_assumed_available_for_learning_at
            ),
        )
        record = RunnerGenomeRecord(
            canonical_json=canonical_json_bytes(genome).decode("utf-8"),
            temporal_artifact=temporal,
        )
        self._append_genome(record)
        return record

    def build_memory_index(
        self,
        *,
        cutoff: str,
        created_at: str,
        evidence_class: str,
        environment_namespace: str,
        mode: TemporalMode = TemporalMode.FORWARD,
        embedding_artifact_id: str | None = None,
        historical_assumed_available_at: str | None = None,
        historical_assumed_available_for_learning_at: str | None = None,
    ) -> MemoryIndexRecord:
        cutoff = _timestamp_text(cutoff, "cutoff")
        created_at = _timestamp_text(created_at, "created_at")
        mode = TemporalMode(mode)
        cutoff_dt = _utc(cutoff, "cutoff")
        created_dt = _utc(created_at, "created_at")
        is_historical = mode is TemporalMode.HISTORICAL_RECONSTRUCTED
        if is_historical:
            if evidence_class.upper() != "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("historical indexes must be labeled HISTORICAL_RECONSTRUCTED")
            if historical_assumed_available_at is None:
                raise GenomeError("historical index needs an explicit availability assumption")
            if historical_assumed_available_for_learning_at is None:
                raise GenomeError("historical index needs an explicit learning assumption")
            _timestamp_text(historical_assumed_available_at, "historical_assumed_available_at")
            _timestamp_text(
                historical_assumed_available_for_learning_at,
                "historical_assumed_available_for_learning_at",
            )
            if _utc(historical_assumed_available_at, "historical index availability") > cutoff_dt:
                raise GenomeError("historical index assumption exceeds the consumer cutoff")
            if _utc(
                historical_assumed_available_for_learning_at,
                "historical index learning availability",
            ) > cutoff_dt:
                raise GenomeError("historical index learning assumption exceeds the cutoff")
            if _utc(
                historical_assumed_available_for_learning_at,
                "historical index learning availability",
            ) < _utc(
                historical_assumed_available_at,
                "historical index availability",
            ):
                raise GenomeError("historical index learning availability precedes its availability")
        else:
            if evidence_class.upper() == "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("historical evidence requires historical reconstruction mode")
            if historical_assumed_available_at is not None or (
                historical_assumed_available_for_learning_at is not None
            ):
                raise GenomeError("forward indexes cannot carry retrospective assumptions")
            if created_dt > cutoff_dt:
                raise GenomeError("forward index cannot exist before its actual creation time")

        members = self._eligible_genomes(
            cutoff_dt=cutoff_dt,
            evidence_class=evidence_class,
            historical=is_historical,
        )
        member_refs = _ordered_refs([record.replay_dependency_ref for record in members])
        embedding_artifact = (
            self._source(embedding_artifact_id, ARTIFACT_MANIFEST_SCHEMA)
            if embedding_artifact_id is not None
            else None
        )
        if embedding_artifact is not None:
            self._assert_embedding_eligible(
                embedding_artifact,
                cutoff_dt=cutoff_dt,
                historical=is_historical,
            )
        inventory_hash = member_inventory_hash(cutoff, member_refs)
        embedding_ref = (
            _artifact_ref(embedding_artifact) if embedding_artifact is not None else None
        )

        actual_learning_times = [created_at]
        input_learning_times: list[str] = []
        for member in members:
            actual = member.contract["available_for_learning_at"]
            actual_learning_times.append(actual)
            input_learning_times.append(actual)
        if embedding_artifact is not None:
            embedding_actual_learning = (
                embedding_artifact.available_for_learning_at or embedding_artifact.known_at
            )
            actual_learning_times.append(embedding_actual_learning)
            input_learning_times.append(embedding_actual_learning)
        if input_learning_times:
            latest_input_learning = _max_timestamp(
                input_learning_times, "index source learning availability"
            )
            if created_dt < _utc(latest_input_learning, "index source learning availability"):
                raise GenomeError("index creation cannot precede its eligible source artifacts")
        if is_historical:
            member_assumptions = [
                member.temporal_artifact.historical_assumed_available_for_learning_at
                for member in members
            ]
            member_availability_assumptions = [
                member.temporal_artifact.historical_assumed_available_at
                for member in members
            ]
            if any(value is None for value in member_assumptions):
                raise GenomeError("historical member lacks a learning-availability assumption")
            if any(value is None for value in member_availability_assumptions):
                raise GenomeError("historical member lacks an availability assumption")
            assumed_availability_times = [
                _utc(value, "historical member availability")
                for value in member_availability_assumptions
                if value is not None
            ]
            assumed_learning_times = [
                _utc(value, "historical member learning availability")
                for value in member_assumptions
                if value is not None
            ]
            if embedding_artifact is not None:
                embedding_availability = (
                    embedding_artifact.historical_assumed_available_at
                )
                embedding_learning = (
                    embedding_artifact.historical_assumed_available_for_learning_at
                )
                if embedding_availability is None or embedding_learning is None:
                    raise GenomeError("historical embedding lacks temporal assumptions")
                assumed_availability_times.append(
                    _utc(embedding_availability, "historical embedding availability")
                )
                assumed_learning_times.append(
                    _utc(embedding_learning, "historical embedding learning availability")
                )
            if assumed_availability_times and _utc(
                historical_assumed_available_at,
                "historical index availability",
            ) < max(assumed_availability_times):
                raise GenomeError("historical index availability precedes a member or embedding")
            if assumed_learning_times and _utc(
                historical_assumed_available_for_learning_at,
                "historical index learning availability",
            ) < max(assumed_learning_times):
                raise GenomeError("historical index cannot be learnable before its members")
        actual_available_for_learning = _max_timestamp(
            actual_learning_times, "index available_for_learning_at"
        )
        payload: dict[str, Any] = {
            "schema_name": MEMORY_INDEX_SCHEMA,
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": created_at,
            "owning_authority": "apexlab",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": _ordered_refs(
                [*member_refs, *([embedding_ref] if embedding_ref is not None else [])]
            ),
            "content_hash": "0" * 64,
            "index_kind": "RUNNER",
            "member_refs": member_refs,
            "member_inventory_hash": inventory_hash,
            "cutoff": cutoff,
            "available_for_learning_at": actual_available_for_learning,
            "embedding_artifact_ref": embedding_ref,
        }
        try:
            payload["content_hash"] = canonical_content_hash("MemoryIndexManifest", payload)
            validate_contract("MemoryIndexManifest", payload)
            verify_content_hash("MemoryIndexManifest", payload)
        except ContractValidationError as exc:
            raise GenomeError(f"memory-index manifest is invalid: {exc}") from exc

        temporal = TemporalArtifact.from_contract(
            payload,
            known_at=created_at,
            historical_assumed_available_at=historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                historical_assumed_available_for_learning_at
            ),
        )
        record = MemoryIndexRecord(
            canonical_json=canonical_json_bytes(payload).decode("utf-8"),
            temporal_artifact=temporal,
            mode=mode.value,
        )
        self._append_index(record)
        return record

    def lookup_genome(
        self, genome_id: str, *, cutoff: str, mode: TemporalMode = TemporalMode.FORWARD
    ) -> GenomeLookup:
        cutoff = _timestamp_text(cutoff, "cutoff")
        mode = TemporalMode(mode)
        try:
            record = self._genomes[genome_id]
        except KeyError as exc:
            raise GenomeError("RunnerGenome does not exist in this store") from exc
        view = self._firewall().query(
            TemporalQuery(
                cutoff=cutoff,
                mode=mode,
                operation=TemporalOperation.QUERY,
                artifact_ids=(genome_id,),
            ),
            TemporalPermission(
                operations=frozenset({TemporalOperation.QUERY}),
                artifact_kinds=frozenset({RUNNER_GENOME_SCHEMA}),
                allow_historical_reconstructed=(
                    mode is TemporalMode.HISTORICAL_RECONSTRUCTED
                ),
            ),
        )
        dependencies = view.dependency_closure.get(genome_id, ())
        revision = self._revision_for_ids((genome_id, *dependencies))
        proof = eligibility_proof_hash(
            artifact_ref=record.replay_dependency_ref,
            cutoff=cutoff,
            mode=mode.value,
            catalog_revision=revision,
            dependency_closure=dependencies,
        )
        return GenomeLookup(record, cutoff, mode.value, revision, dependencies, proof)

    def lookup_memory_index(
        self,
        index_id: str,
        *,
        cutoff: str,
        mode: TemporalMode | None = None,
    ) -> MemoryIndexLookup:
        cutoff = _timestamp_text(cutoff, "cutoff")
        try:
            record = self._indexes[index_id]
        except KeyError as exc:
            raise GenomeError("memory index does not exist in this store") from exc
        query_mode = TemporalMode(mode or record.mode)
        payload = record.contract
        if query_mode.value != record.mode:
            raise GenomeError("index lookup mode must match the manifest's construction mode")
        if _utc(payload["cutoff"], "index cutoff") != _utc(cutoff, "consumer cutoff"):
            raise GenomeError("memory index must be built for the exact consumer cutoff")
        expected_inventory = member_inventory_hash(cutoff, payload["member_refs"])
        if payload["member_inventory_hash"] != expected_inventory:
            raise GenomeError("index member inventory hash does not match the manifest")

        members: list[RunnerGenomeRecord] = []
        for ref in payload["member_refs"]:
            if ref["target_schema_name"] != RUNNER_GENOME_SCHEMA:
                raise GenomeError("RUNNER index contains a non-RunnerGenome member")
            member = self._genomes.get(ref["target_id"])
            if member is None or member.replay_dependency_ref != ref:
                raise GenomeError("index member is missing or its content hash has changed")
            members.append(member)

        if members:
            view = self._firewall().query(
                TemporalQuery(
                    cutoff=cutoff,
                    mode=query_mode,
                    operation=TemporalOperation.QUERY,
                    artifact_ids=(index_id,),
                ),
                TemporalPermission(
                    operations=frozenset({TemporalOperation.QUERY}),
                    artifact_kinds=frozenset({MEMORY_INDEX_SCHEMA}),
                    allow_historical_reconstructed=(
                        query_mode is TemporalMode.HISTORICAL_RECONSTRUCTED
                    ),
                ),
            )
            dependencies = view.dependency_closure.get(index_id, ())
            revision = self._revision_for_ids((index_id, *dependencies))
        else:
            self._prove_empty_index(record, cutoff=cutoff, mode=query_mode)
            embedding_ref = payload["embedding_artifact_ref"]
            if embedding_ref is not None:
                embedding_view = self._firewall().query(
                    TemporalQuery(
                        cutoff=cutoff,
                        mode=query_mode,
                        operation=TemporalOperation.QUERY,
                        artifact_ids=(embedding_ref["target_id"],),
                    ),
                    TemporalPermission(
                        operations=frozenset({TemporalOperation.QUERY}),
                        artifact_kinds=frozenset({ARTIFACT_MANIFEST_SCHEMA}),
                        allow_historical_reconstructed=(
                            query_mode is TemporalMode.HISTORICAL_RECONSTRUCTED
                        ),
                    ),
                )
                dependencies = embedding_view.dependency_closure.get(
                    embedding_ref["target_id"], ()
                )
                revision = self._revision_for_ids(
                    (index_id, embedding_ref["target_id"], *dependencies)
                )
            else:
                dependencies = ()
                revision = self._revision_for_ids((index_id,))

        proof = eligibility_proof_hash(
            artifact_ref=record.replay_dependency_ref,
            cutoff=cutoff,
            mode=query_mode.value,
            catalog_revision=revision,
            dependency_closure=dependencies,
        )
        return MemoryIndexLookup(
            record,
            tuple(members),
            cutoff,
            query_mode.value,
            revision,
            tuple(dependencies),
            proof,
        )

    def _assert_event_and_sources(
        self,
        event: Mapping[str, Any],
        event_artifact: TemporalArtifact,
        snapshots: Sequence[TemporalArtifact],
        predictions: Sequence[TemporalArtifact],
        outcomes: Sequence[TemporalArtifact],
        *,
        requested_event_time: str,
        historical_reconstructed: bool,
    ) -> None:
        if event.get("event_type") not in {"EXPANSION_RUNNER", "SESSION_MONSTER"}:
            raise GenomeError("only resolved positive RunnerEvent types may create a RunnerGenome")
        event_time = _utc(event.get("detected_at"), "RunnerEvent detected_at")
        requested_event = _utc(requested_event_time, "event_time")
        if requested_event > event_time:
            raise GenomeError("underlying event time cannot follow its RunnerEvent detection")
        for outcome_artifact in outcomes:
            outcome = _contract_dict(outcome_artifact.payload)
            if outcome.get("outcome_state") != "RESOLVED":
                raise GenomeError("RunnerGenome requires fully resolved outcomes")
            available = outcome.get("available_for_learning_at")
            if not isinstance(available, str):
                raise GenomeError("resolved outcome is not yet available for learning")
            if _utc(available, "Outcome available_for_learning_at") > _utc(
                event_artifact.known_at, "RunnerEvent known_at"
            ):
                raise GenomeError("RunnerEvent was known before its resolved outcome")
            if outcome.get("instrument_ref") != event.get("instrument_ref"):
                raise GenomeError("RunnerGenome outcomes must match the RunnerEvent instrument")
            if outcome_artifact.artifact_id == event["outcome_ref"]["target_id"]:
                if outcome.get("label_ref") != event.get("label_ref"):
                    raise GenomeError("RunnerEvent outcome label does not match its event label")
                if _artifact_ref(outcome_artifact) != event["outcome_ref"]:
                    raise GenomeError("RunnerEvent outcome hash does not match the resolved contract")
                try:
                    positive_extremum = Decimal(outcome["max_high_return"])
                except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                    raise GenomeError("positive RunnerEvent requires a resolved positive maximum") from exc
                if positive_extremum <= Decimal(0):
                    raise GenomeError("positive RunnerEvent outcome has no positive maximum return")
        if event["outcome_ref"]["target_id"] not in {
            outcome.artifact_id for outcome in outcomes
        }:
            raise GenomeError("RunnerEvent's resolved Outcome must be included in the genome")

        start_session = _date(event["start_session"], "RunnerEvent.start_session")
        for snapshot_artifact in snapshots:
            snapshot = _contract_dict(snapshot_artifact.payload)
            if _date(snapshot["session_id"], "snapshot.session_id") >= start_session:
                raise GenomeError("pre-event snapshots must precede the RunnerEvent session")
            if historical_reconstructed:
                snapshot_available_at = snapshot_artifact.historical_assumed_available_at
                if snapshot_available_at is None:
                    raise GenomeError("historical pre-event snapshot lacks an availability assumption")
            else:
                snapshot_available_at = snapshot_artifact.known_at
            if _utc(snapshot_available_at, "snapshot availability") > _utc(requested_event_time, "event_time"):
                raise GenomeError("pre-event snapshot was not known by the underlying event time")
            instrument_ref = snapshot.get("instrument_ref")
            if (
                instrument_ref is not None
                and instrument_ref != event.get("instrument_ref")
            ):
                raise GenomeError("pre-event snapshot instrument does not match the RunnerEvent")
            decision_cutoff = snapshot.get("decision_cutoff")
            if decision_cutoff is not None and _utc(
                decision_cutoff, "snapshot decision_cutoff"
            ) > _utc(requested_event_time, "event_time"):
                raise GenomeError("pre-event snapshot decision cutoff is after the underlying event")
        for prediction_artifact in predictions:
            prediction = _contract_dict(prediction_artifact.payload)
            if _date(prediction["session_id"], "Prediction.session_id") >= start_session:
                raise GenomeError("contemporaneous predictions must precede the event session")
            if prediction.get("instrument_ref") != event.get("instrument_ref"):
                raise GenomeError("contemporaneous prediction instrument does not match the event")
            if historical_reconstructed:
                prediction_available_at = (
                    prediction_artifact.historical_assumed_available_at
                )
                if prediction_available_at is None:
                    raise GenomeError("historical prediction lacks an availability assumption")
            else:
                prediction_available_at = prediction_artifact.known_at
            if _utc(prediction_available_at, "prediction availability") > requested_event:
                raise GenomeError("prediction was not known by the underlying event time")

    def _assert_coherent_sources(
        self, sources: Sequence[TemporalArtifact], expected_evidence: str
    ) -> None:
        if not sources:
            raise GenomeError("genome requires an event and source evidence")
        namespaces = set()
        for source in sources:
            payload = _contract_dict(source.payload)
            if source.evidence_class != expected_evidence:
                raise GenomeError("genome sources cannot mix evidence classes")
            if payload.get("environment_namespace") is not None:
                namespaces.add(payload["environment_namespace"])
        if len(namespaces) != 1:
            raise GenomeError("genome sources must share one environment namespace")

    def _assert_embedding_eligible(
        self,
        embedding: TemporalArtifact,
        *,
        cutoff_dt: Any,
        historical: bool,
    ) -> None:
        if historical:
            if embedding.evidence_class.upper() != "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("historical indexes cannot use forward embedding artifacts")
            available = embedding.historical_assumed_available_for_learning_at
            visible_at = embedding.historical_assumed_available_at
            if visible_at is None or _utc(
                visible_at, "embedding historical availability"
            ) > cutoff_dt:
                raise GenomeError("embedding artifact is not available by the historical cutoff")
        else:
            if embedding.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("forward indexes cannot use reconstructed embedding artifacts")
            available = embedding.available_for_learning_at or embedding.known_at
        if available is None or _utc(available, "embedding learning availability") > cutoff_dt:
            raise GenomeError("embedding artifact is not learnable by the index cutoff")

    def _eligible_genomes(
        self, *, cutoff_dt: Any, evidence_class: str, historical: bool
    ) -> list[RunnerGenomeRecord]:
        eligible: list[RunnerGenomeRecord] = []
        for record in self._genomes.values():
            contract = record.contract
            temporal = record.temporal_artifact
            if contract["evidence_class"] != evidence_class:
                continue
            if _utc(contract["event_time"], "RunnerGenome.event_time") > cutoff_dt:
                continue
            if historical:
                if contract["evidence_class"] != "HISTORICAL_RECONSTRUCTED":
                    continue
                learning_at = temporal.historical_assumed_available_for_learning_at
                if learning_at is None or _utc(
                    learning_at, "historical genome learning availability"
                ) > cutoff_dt:
                    continue
            else:
                if contract["evidence_class"] == "HISTORICAL_RECONSTRUCTED":
                    continue
                if _utc(contract["created_at"], "RunnerGenome.created_at") > cutoff_dt:
                    continue
                if _utc(
                    contract["available_for_learning_at"],
                    "RunnerGenome.available_for_learning_at",
                ) > cutoff_dt:
                    continue
            eligible.append(record)
        return sorted(
            eligible,
            key=lambda record: (
                record.contract["event_time"],
                record.contract["id"],
            ),
        )

    def _prove_empty_index(
        self, record: MemoryIndexRecord, *, cutoff: str, mode: TemporalMode
    ) -> None:
        payload = record.contract
        cutoff_dt = _utc(cutoff, "consumer cutoff")
        if mode is TemporalMode.FORWARD:
            if record.temporal_artifact.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("forward lookup cannot read reconstructed index evidence")
            if _utc(record.temporal_artifact.created_at, "index creation") > cutoff_dt:
                raise TemporalViolation(
                    "artifact_unavailable_at_cutoff",
                    "empty index was created after its forward consumer cutoff",
                )
            if _utc(payload["available_for_learning_at"], "index learning availability") > cutoff_dt:
                raise TemporalViolation(
                    "dependency_unavailable_at_cutoff",
                    "empty index is not learnable by its forward consumer cutoff",
                )
            return
        if record.temporal_artifact.evidence_class.upper() != "HISTORICAL_RECONSTRUCTED":
            raise GenomeError("historical lookup requires reconstructed index evidence")
        assumed_available = record.temporal_artifact.historical_assumed_available_at
        assumed_learning = record.temporal_artifact.historical_assumed_available_for_learning_at
        if (
            assumed_available is None
            or assumed_learning is None
            or _utc(assumed_available, "historical index availability") > cutoff_dt
            or _utc(assumed_learning, "historical index learning availability") > cutoff_dt
        ):
            raise TemporalViolation(
                "dependency_unavailable_at_cutoff",
                "empty reconstructed index lacks a cutoff-eligible availability proof",
            )

    def _source(
        self,
        source_id: str,
        expected_schema: str | None = None,
        *,
        schema_names: frozenset[str] | None = None,
    ) -> TemporalArtifact:
        try:
            artifact = self._sources[source_id]
        except KeyError as exc:
            raise GenomeError(f"required source artifact {source_id} is not registered") from exc
        payload = _contract_dict(artifact.payload)
        if expected_schema is not None and payload.get("schema_name") != expected_schema:
            raise GenomeError(f"source {source_id} is not a {expected_schema}")
        if schema_names is not None and payload.get("schema_name") not in schema_names:
            raise GenomeError(f"source {source_id} has an unsupported contract type")
        return artifact

    def _validated_payload(
        self, artifact: TemporalArtifact, *, require_contract: bool
    ) -> dict[str, Any]:
        if not isinstance(artifact, TemporalArtifact):
            raise GenomeError("source must be a TemporalArtifact")
        payload = _contract_dict(artifact.payload)
        if not payload:
            if require_contract:
                raise GenomeError("source artifact must include its persisted QC2 contract")
            return payload
        schema_name = payload.get("schema_name")
        contract_name = SCHEMA_TO_CONTRACT.get(schema_name)
        if (
            contract_name is None
            or payload.get("id") != artifact.artifact_id
            or payload.get("created_at") != artifact.created_at
            or schema_name != artifact.artifact_kind
        ):
            raise GenomeError("temporal artifact identity does not match its source contract")
        try:
            validate_contract(contract_name, payload)
            if contract_name in CONTENT_ADDRESSED:
                verify_content_hash(contract_name, payload)
        except ContractValidationError as exc:
            raise GenomeError(f"invalid {contract_name} contract: {exc}") from exc
        return payload

    def _append_temporal_source(self, artifact: TemporalArtifact) -> None:
        if not isinstance(artifact, TemporalArtifact):
            raise GenomeError("temporal dependency must be a TemporalArtifact")
        prior = self._sources.get(artifact.artifact_id)
        if prior is not None:
            if prior != artifact:
                raise GenomeError("temporal source IDs are immutable and cannot be replaced")
            return
        self._sources[artifact.artifact_id] = artifact

    def _append_genome(self, record: RunnerGenomeRecord) -> None:
        contract = record.contract
        genome_id = contract["id"]
        if genome_id in self._genomes or genome_id in self._sources or genome_id in self._indexes:
            raise GenomeError("RunnerGenome ID already exists in this store")
        self._genomes[genome_id] = record

    def _append_index(self, record: MemoryIndexRecord) -> None:
        index_id = record.contract["id"]
        if index_id in self._sources or index_id in self._genomes or index_id in self._indexes:
            raise GenomeError("memory-index ID already exists in this store")
        self._indexes[index_id] = record

    def _all_temporal_artifacts(self) -> tuple[TemporalArtifact, ...]:
        return (
            *self._sources.values(),
            *(record.temporal_artifact for record in self._genomes.values()),
            *(record.temporal_artifact for record in self._indexes.values()),
        )

    def _catalog_revision(self) -> str:
        rows = []
        for artifact in sorted(self._all_temporal_artifacts(), key=lambda item: item.artifact_id):
            rows.append(
                {
                    "id": artifact.artifact_id,
                    "kind": artifact.artifact_kind,
                    "revision": artifact.revision_id,
                    "hash": artifact.content_hash,
                    "created_at": artifact.created_at,
                    "known_at": artifact.known_at,
                    "event_time": artifact.event_time,
                    "available_for_learning_at": artifact.available_for_learning_at,
                    "historical_assumed_available_at": artifact.historical_assumed_available_at,
                    "historical_assumed_available_for_learning_at": (
                        artifact.historical_assumed_available_for_learning_at
                    ),
                    "dependency_refs": list(artifact.dependency_refs),
                    "index_member_refs": list(artifact.index_member_refs),
                }
            )
        return domain_separated_sha256(
            "qc2.apexlab.temporal-catalog.v1", canonical_json_bytes(rows)
        )

    def _revision_for_ids(self, artifact_ids: Sequence[str]) -> str:
        catalog = {
            artifact.artifact_id: artifact for artifact in self._all_temporal_artifacts()
        }
        rows = []
        for artifact_id in sorted(set(artifact_ids)):
            artifact = catalog.get(artifact_id)
            if artifact is None:
                raise GenomeError("temporal proof references an artifact outside the store")
            rows.append(
                {
                    "id": artifact.artifact_id,
                    "kind": artifact.artifact_kind,
                    "revision": artifact.revision_id,
                    "hash": artifact.content_hash,
                    "created_at": artifact.created_at,
                    "known_at": artifact.known_at,
                    "event_time": artifact.event_time,
                    "available_for_learning_at": artifact.available_for_learning_at,
                    "historical_assumed_available_at": artifact.historical_assumed_available_at,
                    "historical_assumed_available_for_learning_at": (
                        artifact.historical_assumed_available_for_learning_at
                    ),
                    "dependency_refs": list(artifact.dependency_refs),
                    "index_member_refs": list(artifact.index_member_refs),
                }
            )
        return domain_separated_sha256(
            "qc2.apexlab.temporal-view-revision.v1", canonical_json_bytes(rows)
        )

    def _firewall(self) -> TemporalFirewall:
        return TemporalFirewall(
            self._all_temporal_artifacts(),
            catalog_revision=self._catalog_revision(),
        )
