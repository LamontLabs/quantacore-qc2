"""FailureGenome taxonomy and cutoff-proof result types."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from qc2_contracts.runtime import domain_separated_sha256
from qc2_temporal_firewall import TemporalArtifact
from qc2_temporal_firewall.models import canonical_json_bytes

from .models import (
    MEMORY_INDEX_SCHEMA,
    GenomeDraft,
    GenomeError,
    MemoryIndexRecord,
    _contract_dict,
)

FAILURE_GENOME_SCHEMA = "qc2.outcomes_research.FailureGenome.v1"
FAILURE_MEMORY_INDEX_BUILDER_VERSION = "qc2.failure_memory_index.v1"


class FailureCategory(StrEnum):
    """Readable categories mapped to the existing strict FailureType contract."""

    NON_EVENT = "NON_EVENT"
    DOWNSIDE = "DOWNSIDE"
    DATA_ERROR = "DATA_ERROR"
    TIMING_MISS = "TIMING_MISS"
    MISSED_RUNNER = "MISSED_RUNNER"


_FAILURE_CATEGORY_BY_TYPE = {
    "FALSE_MONSTER": FailureCategory.NON_EVENT,
    "COLLAPSE": FailureCategory.DOWNSIDE,
    "DATA_ERROR": FailureCategory.DATA_ERROR,
    "TIMING_MISS": FailureCategory.TIMING_MISS,
    "MISSED_RUNNER": FailureCategory.MISSED_RUNNER,
}
_NEGATIVE_TRAINING_CATEGORIES = frozenset(
    {
        FailureCategory.NON_EVENT,
        FailureCategory.DOWNSIDE,
        FailureCategory.TIMING_MISS,
    }
)


def failure_category_for_type(failure_type: str) -> FailureCategory:
    """Map the canonical FailureType without deriving it from outcome values."""
    try:
        return _FAILURE_CATEGORY_BY_TYPE[failure_type]
    except (KeyError, TypeError) as exc:
        raise GenomeError(f"unsupported FailureType: {failure_type!r}") from exc


@dataclass(frozen=True, slots=True)
class FailureGenomeDraft:
    """Explicit failure adjudication request using the strict QC2 source IDs."""

    failure_type: str
    event_id: str
    pre_event_snapshot_ids: tuple[str, ...]
    prediction_ids: tuple[str, ...]
    outcome_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]
    event_time: str
    created_at: str
    review_completed_at: str
    curation_version: int
    learning_embargo_until: str | None = None
    historical_assumed_available_at: str | None = None
    historical_assumed_available_for_learning_at: str | None = None

    def __post_init__(self) -> None:
        failure_category_for_type(self.failure_type)
        validated = GenomeDraft(
            event_id=self.event_id,
            pre_event_snapshot_ids=self.pre_event_snapshot_ids,
            prediction_ids=self.prediction_ids,
            outcome_ids=self.outcome_ids,
            provenance_ids=self.provenance_ids,
            event_time=self.event_time,
            created_at=self.created_at,
            review_completed_at=self.review_completed_at,
            curation_version=self.curation_version,
            learning_embargo_until=self.learning_embargo_until,
            historical_assumed_available_at=self.historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                self.historical_assumed_available_for_learning_at
            ),
        )
        for name in (
            "event_id",
            "pre_event_snapshot_ids",
            "prediction_ids",
            "outcome_ids",
            "provenance_ids",
            "event_time",
            "created_at",
            "review_completed_at",
            "curation_version",
            "learning_embargo_until",
            "historical_assumed_available_at",
            "historical_assumed_available_for_learning_at",
        ):
            object.__setattr__(self, name, getattr(validated, name))


@dataclass(frozen=True, slots=True)
class FailureGenomeRecord:
    """Immutable FailureGenome contract and its actual temporal catalog entry."""

    canonical_json: str
    temporal_artifact: TemporalArtifact

    @property
    def contract(self) -> dict[str, object]:
        return json.loads(self.canonical_json)

    @property
    def category(self) -> FailureCategory:
        return failure_category_for_type(str(self.contract["failure_type"]))

    @property
    def replay_dependency_ref(self) -> dict[str, str]:
        contract = self.contract
        return {
            "target_schema_name": FAILURE_GENOME_SCHEMA,
            "target_id": str(contract["id"]),
            "content_hash": str(contract["content_hash"]),
        }


@dataclass(frozen=True, slots=True)
class FailureGenomeLookup:
    """A single failure memory after the temporal firewall proves its cutoff."""

    record: FailureGenomeRecord
    cutoff: str
    mode: str
    catalog_revision: str
    dependency_closure: tuple[str, ...]
    eligibility_proof_hash: str

    @property
    def is_negative_training_example(self) -> bool:
        return self.record.category in _NEGATIVE_TRAINING_CATEGORIES


@dataclass(frozen=True, slots=True)
class FailureMemoryIndexLookup:
    """A failure-only index and its cutoff-eligible immutable members."""

    index: MemoryIndexRecord
    members: tuple[FailureGenomeRecord, ...]
    cutoff: str
    mode: str
    catalog_revision: str
    dependency_closure: tuple[str, ...]
    eligibility_proof_hash: str

    @property
    def negative_training_members(self) -> tuple[FailureGenomeRecord, ...]:
        return tuple(
            member for member in self.members
            if member.category in _NEGATIVE_TRAINING_CATEGORIES
        )


def failure_member_inventory_hash(
    cutoff: str, member_refs: Sequence[Mapping[str, str]]
) -> str:
    """Bind FAILURE index membership to its cutoff and independent builder version."""
    payload = {
        "builder_version": FAILURE_MEMORY_INDEX_BUILDER_VERSION,
        "index_kind": "FAILURE",
        "cutoff": cutoff,
        "member_refs": [_contract_dict(ref) for ref in member_refs],
    }
    return domain_separated_sha256(
        "qc2.apexlab.failure-memory-index-members.v1",
        canonical_json_bytes(payload),
    )


def failure_index_reference(index: MemoryIndexRecord) -> dict[str, str]:
    """Return the content-addressed reference used by replay proofs."""
    contract = index.contract
    return {
        "target_schema_name": MEMORY_INDEX_SCHEMA,
        "target_id": str(contract["id"]),
        "content_hash": str(contract["content_hash"]),
    }
