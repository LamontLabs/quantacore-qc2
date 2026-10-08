"""Append-only FailureGenome storage and cutoff-bound failure indexes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qc2_contracts.runtime import (
    ContractValidationError,
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall import (
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
)
from qc2_temporal_firewall.models import canonical_json_bytes

from .failure_models import (
    FAILURE_GENOME_SCHEMA,
    FailureCategory,
    FailureGenomeDraft,
    FailureGenomeLookup,
    FailureGenomeRecord,
    FailureMemoryIndexLookup,
    failure_category_for_type,
    failure_member_inventory_hash,
)
from .models import (
    ARTIFACT_MANIFEST_SCHEMA,
    MEMORY_INDEX_SCHEMA,
    OUTCOME_SCHEMA,
    PREDICTION_SCHEMA,
    RUNNER_EVENT_SCHEMA,
    GenomeError,
    MemoryIndexRecord,
    _PROVENANCE_SCHEMAS,
    _SNAPSHOT_SCHEMAS,
    _TEMPORAL_DEPENDENCY_SCHEMAS,
    _artifact_ref,
    _assert_historical_sources,
    _contract_dict,
    _date,
    _max_actual_source_time,
    _max_timestamp,
    _ordered_refs,
    _timestamp_text,
    _utc,
    contract_artifact,
    eligibility_proof_hash,
)
from .store import RunnerGenomeStore

_EVIDENCE_EVENT_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
_OUTCOME_REVISION_SCHEMA = "qc2.outcomes_research.OutcomeRevision.v1"
_POSITIVE_EVENT_TYPES = frozenset(
    {"EXPANSION_RUNNER", "SESSION_MONSTER", "NEAR_RUNNER"}
)
_CORE_OUTCOME_FIELDS = frozenset(
    {"endpoint_return", "max_high_return", "min_low_return", "mfe", "mae"}
)


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str | None]:
    return (
        str(ref["target_schema_name"]),
        str(ref["target_id"]),
        ref.get("content_hash"),
    )


class FailureGenomeStore(RunnerGenomeStore):
    """Research-only immutable failure memories alongside RunnerGenome records.

    Failure types are explicit curated labels. Outcome values and runner
    probabilities are validated for completeness and temporal eligibility but
    never used to infer the type.
    """

    def __init__(self) -> None:
        super().__init__()
        self._failures: dict[str, FailureGenomeRecord] = {}

    def create_failure_genome(self, draft: FailureGenomeDraft) -> FailureGenomeRecord:
        """Append the first curation version for one independently labeled event."""
        if not isinstance(draft, FailureGenomeDraft):
            raise GenomeError("create_failure_genome requires a FailureGenomeDraft")
        if draft.curation_version != 1:
            raise GenomeError("initial FailureGenome curation_version must be 1")
        return self._create_failure_genome(draft, prior=None)

    def append_correction(
        self, prior_genome_id: str, draft: FailureGenomeDraft
    ) -> FailureGenomeRecord:
        """Append the next curation version and retain the prior record unchanged."""
        if not isinstance(draft, FailureGenomeDraft):
            raise GenomeError("append_correction requires a FailureGenomeDraft")
        try:
            prior = self._failures[prior_genome_id]
        except KeyError as exc:
            raise GenomeError("prior FailureGenome does not exist in this store") from exc

        prior_contract = prior.contract
        event_id = prior_contract["event_ref"]["target_id"]
        latest_version = max(
            int(record.contract["curation_version"])
            for record in self._failures.values()
            if record.contract["event_ref"]["target_id"] == event_id
        )
        if prior_genome_id != self._latest_failure_id(event_id):
            raise GenomeError("corrections must branch from the latest curation version")
        if draft.event_id != event_id:
            raise GenomeError("a correction must retain its RunnerEvent")
        if draft.curation_version != latest_version + 1:
            raise GenomeError("correction curation_version must increment by exactly one")
        return self._create_failure_genome(draft, prior=prior)

    def lookup_failure_genome(
        self,
        genome_id: str,
        *,
        cutoff: str,
        mode: TemporalMode = TemporalMode.FORWARD,
    ) -> FailureGenomeLookup:
        """Return a single memory only after its full dependency closure passes."""
        cutoff = _timestamp_text(cutoff, "cutoff")
        try:
            record = self._failures[genome_id]
        except KeyError as exc:
            raise GenomeError("FailureGenome does not exist in this store") from exc
        query_mode = TemporalMode(mode)
        view = self._firewall().query(
            TemporalQuery(
                cutoff=cutoff,
                mode=query_mode,
                operation=TemporalOperation.QUERY,
                artifact_ids=(genome_id,),
            ),
            TemporalPermission(
                operations=frozenset({TemporalOperation.QUERY}),
                artifact_kinds=frozenset({FAILURE_GENOME_SCHEMA}),
                allow_historical_reconstructed=(
                    query_mode is TemporalMode.HISTORICAL_RECONSTRUCTED
                ),
            ),
        )
        dependencies = view.dependency_closure.get(genome_id, ())
        revision = self._revision_for_ids((genome_id, *dependencies))
        proof = eligibility_proof_hash(
            artifact_ref=record.replay_dependency_ref,
            cutoff=cutoff,
            mode=query_mode.value,
            catalog_revision=revision,
            dependency_closure=dependencies,
        )
        return FailureGenomeLookup(
            record,
            cutoff,
            query_mode.value,
            revision,
            tuple(dependencies),
            proof,
        )

    def build_failure_index(
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
        """Snapshot the latest eligible FailureGenome version per event."""
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
            historical_learning = _utc(
                historical_assumed_available_for_learning_at,
                "historical index learning availability",
            )
            if historical_learning > cutoff_dt:
                raise GenomeError("historical index learning assumption exceeds the cutoff")
            if historical_learning < _utc(
                historical_assumed_available_at, "historical index availability"
            ):
                raise GenomeError("historical learning availability precedes availability")
        else:
            if evidence_class.upper() == "HISTORICAL_RECONSTRUCTED":
                raise GenomeError("historical evidence requires reconstruction mode")
            if historical_assumed_available_at is not None or (
                historical_assumed_available_for_learning_at is not None
            ):
                raise GenomeError("forward indexes cannot carry retrospective assumptions")
            if created_dt > cutoff_dt:
                raise GenomeError("forward index cannot exist before its actual creation time")

        members = self._eligible_failures(
            cutoff_dt=cutoff_dt,
            evidence_class=evidence_class,
            historical=is_historical,
        )
        member_refs = _ordered_refs([record.replay_dependency_ref for record in members])
        embedding = (
            self._source(embedding_artifact_id, ARTIFACT_MANIFEST_SCHEMA)
            if embedding_artifact_id is not None
            else None
        )
        if embedding is not None:
            self._assert_embedding_eligible(
                embedding,
                cutoff_dt=cutoff_dt,
                historical=is_historical,
            )

        actual_learning_times = [created_at]
        input_learning_times: list[str] = []
        for member in members:
            available = str(member.contract["available_for_learning_at"])
            actual_learning_times.append(available)
            input_learning_times.append(available)
        if embedding is not None:
            embedding_learning = (
                embedding.available_for_learning_at or embedding.known_at
            )
            actual_learning_times.append(embedding_learning)
            input_learning_times.append(embedding_learning)
        if input_learning_times and created_dt < max(
            _utc(value, "index source learning availability")
            for value in input_learning_times
        ):
            raise GenomeError("index creation cannot precede its eligible source artifacts")

        if is_historical:
            member_availability = [
                member.temporal_artifact.historical_assumed_available_at
                for member in members
            ]
            member_learning = [
                member.temporal_artifact.historical_assumed_available_for_learning_at
                for member in members
            ]
            if any(value is None for value in (*member_availability, *member_learning)):
                raise GenomeError("historical member lacks explicit temporal assumptions")
            availability_times = [
                _utc(value, "historical member availability")
                for value in member_availability
                if value is not None
            ]
            learning_times = [
                _utc(value, "historical member learning availability")
                for value in member_learning
                if value is not None
            ]
            if embedding is not None:
                embedding_available = embedding.historical_assumed_available_at
                embedding_learning = (
                    embedding.historical_assumed_available_for_learning_at
                )
                if embedding_available is None or embedding_learning is None:
                    raise GenomeError("historical embedding lacks temporal assumptions")
                availability_times.append(
                    _utc(embedding_available, "historical embedding availability")
                )
                learning_times.append(
                    _utc(embedding_learning, "historical embedding learning availability")
                )
            if availability_times and _utc(
                historical_assumed_available_at, "historical index availability"
            ) < max(availability_times):
                raise GenomeError("historical index availability precedes a member or embedding")
            if learning_times and _utc(
                historical_assumed_available_for_learning_at,
                "historical index learning availability",
            ) < max(learning_times):
                raise GenomeError("historical index cannot be learnable before its members")

        actual_available_for_learning = _max_timestamp(
            actual_learning_times, "index available_for_learning_at"
        )
        embedding_ref = _artifact_ref(embedding) if embedding is not None else None
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
            "index_kind": "FAILURE",
            "member_refs": member_refs,
            "member_inventory_hash": failure_member_inventory_hash(cutoff, member_refs),
            "cutoff": cutoff,
            "available_for_learning_at": actual_available_for_learning,
            "embedding_artifact_ref": embedding_ref,
        }
        try:
            payload["content_hash"] = canonical_content_hash(
                "MemoryIndexManifest", payload
            )
            validate_contract("MemoryIndexManifest", payload)
            verify_content_hash("MemoryIndexManifest", payload)
        except ContractValidationError as exc:
            raise GenomeError(f"failure index manifest is invalid: {exc}") from exc

        temporal = contract_artifact(
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

    def lookup_failure_index(
        self,
        index_id: str,
        *,
        cutoff: str,
        mode: TemporalMode | None = None,
    ) -> FailureMemoryIndexLookup:
        """Verify the manifest, every member hash, and temporal dependency closure."""
        cutoff = _timestamp_text(cutoff, "cutoff")
        try:
            record = self._indexes[index_id]
        except KeyError as exc:
            raise GenomeError("failure memory index does not exist in this store") from exc
        query_mode = TemporalMode(mode or record.mode)
        payload = record.contract
        if payload["index_kind"] != "FAILURE":
            raise GenomeError("index is not a FAILURE memory index")
        if query_mode.value != record.mode:
            raise GenomeError("index lookup mode must match its construction mode")
        if _utc(payload["cutoff"], "index cutoff") != _utc(cutoff, "consumer cutoff"):
            raise GenomeError("failure index must be built for the exact consumer cutoff")
        expected_inventory = failure_member_inventory_hash(cutoff, payload["member_refs"])
        if payload["member_inventory_hash"] != expected_inventory:
            raise GenomeError("failure index member inventory hash does not match the manifest")

        members: list[FailureGenomeRecord] = []
        for ref in payload["member_refs"]:
            if ref["target_schema_name"] != FAILURE_GENOME_SCHEMA:
                raise GenomeError("FAILURE index contains a non-FailureGenome member")
            member = self._failures.get(ref["target_id"])
            if member is None or member.replay_dependency_ref != ref:
                raise GenomeError("failure index member is missing or its hash has changed")
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
        return FailureMemoryIndexLookup(
            record,
            tuple(members),
            cutoff,
            query_mode.value,
            revision,
            tuple(dependencies),
            proof,
        )

    def _create_failure_genome(
        self,
        draft: FailureGenomeDraft,
        *,
        prior: FailureGenomeRecord | None,
    ) -> FailureGenomeRecord:
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
        outcomes = [
            self._source(source_id, OUTCOME_SCHEMA) for source_id in draft.outcome_ids
        ]
        provenance = [
            self._source(source_id, schema_names=_PROVENANCE_SCHEMAS)
            for source_id in draft.provenance_ids
        ]
        if not any(item.artifact_kind == _EVIDENCE_EVENT_SCHEMA for item in provenance):
            raise GenomeError("FailureGenome requires independent EvidenceEvent adjudication")
        if draft.failure_type == "DATA_ERROR" and not any(
            item.artifact_kind == _OUTCOME_REVISION_SCHEMA for item in provenance
        ):
            raise GenomeError("DATA_ERROR requires a linked OutcomeRevision")

        selected_sources = [event_artifact, *snapshots, *predictions, *outcomes, *provenance]
        if prior is not None:
            selected_sources.append(prior.temporal_artifact)
        self._assert_coherent_sources(selected_sources, event_artifact.evidence_class)
        self._assert_failure_event_and_sources(
            event,
            event_artifact,
            snapshots,
            predictions,
            outcomes,
            provenance,
            failure_type=draft.failure_type,
            requested_event_time=draft.event_time,
            historical_reconstructed=(
                event_artifact.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED"
            ),
            prior=prior,
        )

        created_at = _timestamp_text(draft.created_at, "created_at")
        reviewed_at = _timestamp_text(draft.review_completed_at, "review_completed_at")
        event_time = _timestamp_text(draft.event_time, "event_time")
        revision_discovery_times = [
            str(_contract_dict(item.payload)["discovered_at"])
            for item in provenance
            if item.artifact_kind == _OUTCOME_REVISION_SCHEMA
        ]
        latest_actual_source = _max_timestamp(
            [
                _max_actual_source_time(selected_sources),
                str(event["detected_at"]),
                *revision_discovery_times,
            ],
            "FailureGenome source availability",
        )
        if _utc(created_at, "created_at") < _utc(
            latest_actual_source, "source availability"
        ):
            raise GenomeError("FailureGenome creation cannot precede actual source availability")
        if _utc(created_at, "created_at") < _utc(reviewed_at, "review_completed_at"):
            raise GenomeError("FailureGenome creation cannot precede completed curation review")

        evidence_class = event_artifact.evidence_class
        historical = evidence_class.upper() == "HISTORICAL_RECONSTRUCTED"
        if historical:
            _assert_historical_sources(selected_sources)
            assumed_available = draft.historical_assumed_available_at
            assumed_learning = draft.historical_assumed_available_for_learning_at
            if assumed_available is None or assumed_learning is None:
                raise GenomeError("reconstructed FailureGenome needs explicit availability claims")
            if _utc(assumed_available, "historical_assumed_available_at") < _utc(
                event_time, "event_time"
            ):
                raise GenomeError("historical availability cannot precede the failure event")
            source_available = [
                _utc(source.historical_assumed_available_at, "source historical availability")
                for source in selected_sources
                if source.historical_assumed_available_at is not None
            ]
            source_learning = [
                _utc(
                    source.historical_assumed_available_for_learning_at,
                    "source historical learning availability",
                )
                for source in selected_sources
                if source.historical_assumed_available_for_learning_at is not None
            ]
            if source_available and _utc(
                assumed_available, "historical_assumed_available_at"
            ) < max(source_available):
                raise GenomeError("historical availability precedes a source assumption")
            if _utc(assumed_learning, "historical_assumed_available_for_learning_at") < _utc(
                assumed_available, "historical_assumed_available_at"
            ):
                raise GenomeError("historical learning availability precedes availability")
            if source_learning and _utc(
                assumed_learning, "historical_assumed_available_for_learning_at"
            ) < max(source_learning):
                raise GenomeError("historical learning availability precedes a source assumption")
        elif (
            draft.historical_assumed_available_at is not None
            or draft.historical_assumed_available_for_learning_at is not None
        ):
            raise GenomeError("forward FailureGenome cannot carry retrospective assumptions")

        learning_times = [
            created_at,
            reviewed_at,
            event["detected_at"],
            *(source.known_at for source in selected_sources),
            *(
                source.available_for_learning_at
                for source in selected_sources
                if source.available_for_learning_at is not None
            ),
            *(
                str(_contract_dict(outcome.payload)["available_for_learning_at"])
                for outcome in outcomes
                if _contract_dict(outcome.payload)["available_for_learning_at"] is not None
            ),
            *(
                str(_contract_dict(item.payload)["discovered_at"])
                for item in provenance
                if item.artifact_kind == _OUTCOME_REVISION_SCHEMA
            ),
        ]
        if draft.learning_embargo_until is not None:
            learning_times.append(
                _timestamp_text(draft.learning_embargo_until, "learning_embargo_until")
            )
        available_for_learning_at = _max_timestamp(
            learning_times, "FailureGenome available_for_learning_at"
        )

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
        payload: dict[str, Any] = {
            "schema_name": FAILURE_GENOME_SCHEMA,
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": created_at,
            "owning_authority": "apexlab",
            "evidence_class": evidence_class,
            "environment_namespace": event["environment_namespace"],
            "source_refs": source_refs,
            "content_hash": "0" * 64,
            "event_ref": _artifact_ref(event_artifact),
            "failure_type": draft.failure_type,
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
            payload["content_hash"] = canonical_content_hash("FailureGenome", payload)
            validate_contract("FailureGenome", payload)
            verify_content_hash("FailureGenome", payload)
        except ContractValidationError as exc:
            raise GenomeError(f"FailureGenome contract is invalid: {exc}") from exc

        temporal = contract_artifact(
            payload,
            known_at=created_at,
            historical_assumed_available_at=draft.historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                draft.historical_assumed_available_for_learning_at
            ),
        )
        record = FailureGenomeRecord(
            canonical_json=canonical_json_bytes(payload).decode("utf-8"),
            temporal_artifact=temporal,
        )
        self._append_failure(record)
        return record

    def _assert_failure_event_and_sources(
        self,
        event: Mapping[str, Any],
        event_artifact: Any,
        snapshots: Sequence[Any],
        predictions: Sequence[Any],
        outcomes: Sequence[Any],
        provenance: Sequence[Any],
        *,
        failure_type: str,
        requested_event_time: str,
        historical_reconstructed: bool,
        prior: FailureGenomeRecord | None,
    ) -> None:
        category = failure_category_for_type(failure_type)
        event_type = event.get("event_type")
        if category is FailureCategory.MISSED_RUNNER:
            if event_type not in _POSITIVE_EVENT_TYPES:
                raise GenomeError("MISSED_RUNNER must retain a positive ground-truth RunnerEvent")
        elif event_type != "FAILURE":
            raise GenomeError("negative FailureGenome labels require a FAILURE RunnerEvent")

        event_time = _utc(requested_event_time, "event_time")
        detected_at = _utc(event.get("detected_at"), "RunnerEvent.detected_at")
        if event_time > detected_at:
            raise GenomeError("failure event time cannot follow RunnerEvent detection")
        if prior is not None and _utc(
            prior.contract["event_time"], "prior FailureGenome event_time"
        ) != event_time:
            raise GenomeError("a correction must retain the original failure event time")

        outcome_ref_list = [_artifact_ref(outcome) for outcome in outcomes]
        outcome_ref_keys = {_ref_key(ref) for ref in outcome_ref_list}
        revisions = [
            _contract_dict(item.payload)
            for item in provenance
            if item.artifact_kind == _OUTCOME_REVISION_SCHEMA
        ]
        event_outcome_ref = event["outcome_ref"]
        event_outcome_resolved = _ref_key(event_outcome_ref) in outcome_ref_keys or any(
            _ref_key(revision["prior_outcome_ref"]) == _ref_key(event_outcome_ref)
            and _ref_key(revision["replacement_outcome_ref"]) in outcome_ref_keys
            for revision in revisions
        )
        if not event_outcome_resolved:
            raise GenomeError(
                "RunnerEvent's Outcome must be included or linked to its resolved replacement"
            )

        if prior is not None:
            prior_outcomes = {
                _ref_key(ref) for ref in prior.contract["outcome_refs"]
            }
            changed_prior = prior_outcomes - outcome_ref_keys
            changed_replacements = outcome_ref_keys - prior_outcomes
            revision_pairs = {
                (
                    _ref_key(revision["prior_outcome_ref"]),
                    _ref_key(revision["replacement_outcome_ref"]),
                )
                for revision in revisions
            }
            if bool(changed_prior) != bool(changed_replacements) or any(
                not any(
                    prior_ref == old and replacement in changed_replacements
                    for prior_ref, replacement in revision_pairs
                )
                for old in changed_prior
            ) or any(
                not any(
                    prior_ref in changed_prior and replacement == new
                    for prior_ref, replacement in revision_pairs
                )
                for new in changed_replacements
            ):
                raise GenomeError("outcome-changing corrections require linked OutcomeRevisions")
        if category is FailureCategory.DATA_ERROR and not any(
            _ref_key(revision["replacement_outcome_ref"]) in outcome_ref_keys
            and _ref_key(revision["prior_outcome_ref"])
            != _ref_key(revision["replacement_outcome_ref"])
            for revision in revisions
        ):
            raise GenomeError("DATA_ERROR requires a revision to a resolved replacement outcome")

        start_session = _date(event["start_session"], "RunnerEvent.start_session")
        for snapshot_artifact in snapshots:
            snapshot = _contract_dict(snapshot_artifact.payload)
            if _date(snapshot["session_id"], "snapshot.session_id") >= start_session:
                raise GenomeError("pre-event snapshots must precede the failure session")
            snapshot_available = (
                snapshot_artifact.historical_assumed_available_at
                if historical_reconstructed
                else snapshot_artifact.known_at
            )
            if snapshot_available is None or _utc(
                snapshot_available, "snapshot availability"
            ) > event_time:
                raise GenomeError("pre-event snapshot was unavailable at failure time")
            if snapshot.get("instrument_ref") not in (None, event.get("instrument_ref")):
                raise GenomeError("pre-event snapshot instrument does not match the event")
            if snapshot.get("decision_cutoff") is not None and _utc(
                snapshot["decision_cutoff"], "snapshot decision_cutoff"
            ) > event_time:
                raise GenomeError("snapshot decision cutoff follows the failure event")

        for prediction_artifact in predictions:
            prediction = _contract_dict(prediction_artifact.payload)
            if _date(prediction["session_id"], "Prediction.session_id") >= start_session:
                raise GenomeError("failure predictions must precede the event session")
            if prediction.get("instrument_ref") != event.get("instrument_ref"):
                raise GenomeError("failure prediction instrument does not match the event")
            prediction_available = (
                prediction_artifact.historical_assumed_available_at
                if historical_reconstructed
                else prediction_artifact.known_at
            )
            if prediction_available is None or _utc(
                prediction_available, "prediction availability"
            ) > event_time:
                raise GenomeError("failure prediction was unavailable at event time")

        linked_replacement_refs = {
            _ref_key(revision["replacement_outcome_ref"]) for revision in revisions
        }
        for outcome_artifact in outcomes:
            outcome = _contract_dict(outcome_artifact.payload)
            if outcome.get("outcome_state") != "RESOLVED":
                raise GenomeError("FailureGenome requires fully resolved outcomes")
            available = outcome.get("available_for_learning_at")
            if not isinstance(available, str):
                raise GenomeError("resolved failure outcome is not available for learning")
            if outcome.get("instrument_ref") != event.get("instrument_ref"):
                raise GenomeError("FailureGenome outcomes must match the RunnerEvent instrument")
            if outcome.get("label_ref") != event.get("label_ref"):
                raise GenomeError("FailureGenome outcomes must match the RunnerEvent label")
            statuses: dict[str, str] = {}
            for item in outcome.get("field_validity", []):
                field_name = item["field_name"]
                if field_name in statuses:
                    raise GenomeError("Outcome field_validity cannot repeat a field")
                statuses[field_name] = item["status"]
            if any(status == "UNRESOLVED" for status in statuses.values()):
                raise GenomeError("unresolved Outcome fields cannot enter FailureGenome")
            missing_core = _CORE_OUTCOME_FIELDS.difference(statuses)
            invalid_core = {
                field_name
                for field_name in _CORE_OUTCOME_FIELDS
                if statuses.get(field_name) != "VALID"
            }
            if missing_core or invalid_core:
                raise GenomeError(
                    "FailureGenome requires valid endpoint, extrema, MFE and MAE fields"
                )
            outcome_ref_key = _ref_key(_artifact_ref(outcome_artifact))
            if _utc(available, "Outcome available_for_learning_at") > _utc(
                event_artifact.known_at, "RunnerEvent known_at"
            ) and outcome_ref_key not in linked_replacement_refs:
                raise GenomeError(
                    "RunnerEvent preceded its unresolved replacement Outcome"
                )
            if _utc(available, "Outcome available_for_learning_at") > _utc(
                event_artifact.known_at, "RunnerEvent known_at"
            ):
                matching_revision = next(
                    (
                        revision
                        for revision in revisions
                        if revision["replacement_outcome_ref"] == _artifact_ref(outcome_artifact)
                    ),
                    None,
                )
                if matching_revision is None or _utc(
                    matching_revision["discovered_at"], "OutcomeRevision.discovered_at"
                ) < _utc(available, "Outcome available_for_learning_at"):
                    raise GenomeError(
                        "corrected Outcome must be discovered after its learning maturity"
                    )

    def _eligible_failures(
        self,
        *,
        cutoff_dt: Any,
        evidence_class: str,
        historical: bool,
    ) -> list[FailureGenomeRecord]:
        eligible_by_event: dict[str, FailureGenomeRecord] = {}
        for record in self._failures.values():
            contract = record.contract
            temporal = record.temporal_artifact
            if contract["evidence_class"] != evidence_class:
                continue
            if _utc(contract["event_time"], "FailureGenome.event_time") > cutoff_dt:
                continue
            if historical:
                if contract["evidence_class"] != "HISTORICAL_RECONSTRUCTED":
                    continue
                learning_at = temporal.historical_assumed_available_for_learning_at
                if learning_at is None or _utc(
                    learning_at, "historical FailureGenome learning availability"
                ) > cutoff_dt:
                    continue
            else:
                if contract["evidence_class"] == "HISTORICAL_RECONSTRUCTED":
                    continue
                if _utc(contract["created_at"], "FailureGenome.created_at") > cutoff_dt:
                    continue
                if _utc(
                    contract["available_for_learning_at"],
                    "FailureGenome.available_for_learning_at",
                ) > cutoff_dt:
                    continue
            event_id = contract["event_ref"]["target_id"]
            previous = eligible_by_event.get(event_id)
            if previous is None or int(contract["curation_version"]) > int(
                previous.contract["curation_version"]
            ):
                eligible_by_event[event_id] = record
        return sorted(
            eligible_by_event.values(),
            key=lambda record: (
                str(record.contract["event_time"]),
                str(record.contract["id"]),
            ),
        )

    def _latest_failure_id(self, event_id: str) -> str:
        records = [
            record
            for record in self._failures.values()
            if record.contract["event_ref"]["target_id"] == event_id
        ]
        if not records:
            raise GenomeError("failure event has no curation records")
        latest = max(records, key=lambda record: int(record.contract["curation_version"]))
        return str(latest.contract["id"])

    def _append_failure(self, record: FailureGenomeRecord) -> None:
        contract = record.contract
        genome_id = str(contract["id"])
        event_id = str(contract["event_ref"]["target_id"])
        version = int(contract["curation_version"])
        if (
            genome_id in self._sources
            or genome_id in self._genomes
            or genome_id in self._failures
            or genome_id in self._indexes
        ):
            raise GenomeError("FailureGenome ID already exists in this store")
        if any(
            record.contract["event_ref"]["target_id"] == event_id
            and int(record.contract["curation_version"]) == version
            for record in self._failures.values()
        ):
            raise GenomeError("FailureGenome curation version already exists for this event")
        self._failures[genome_id] = record

    def _append_temporal_source(self, artifact: Any) -> None:
        artifact_id = artifact.artifact_id
        if (
            artifact_id in self._failures
            or artifact_id in self._genomes
            or artifact_id in self._indexes
        ):
            raise GenomeError("temporal source ID conflicts with an existing memory artifact")
        super()._append_temporal_source(artifact)

    def _append_index(self, record: MemoryIndexRecord) -> None:
        index_id = str(record.contract["id"])
        if index_id in self._failures:
            raise GenomeError("memory-index ID conflicts with a FailureGenome")
        super()._append_index(record)

    def _all_temporal_artifacts(self) -> tuple[Any, ...]:
        return (
            *super()._all_temporal_artifacts(),
            *(record.temporal_artifact for record in self._failures.values()),
        )
