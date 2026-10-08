"""Cutoff-scoped query, export, and transitive availability enforcement."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from .errors import TemporalViolation
from .models import (
    TemporalArtifact,
    TemporalExport,
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
    TemporalView,
    canonical_json_bytes,
    normalize_kind,
    parse_utc_instant,
)

_PROTECTED_QUERY_KINDS = {
    "FUTURELABEL",
    "GROUNDTRUTH",
    "LABEL",
    "LABELVALUE",
    "OUTCOME",
    "OUTCOMEREVISION",
}
_LEARNING_GATED_KINDS = {
    "CALIBRATOR",
    "EMBEDDING",
    "GENOME",
    "LABEL",
    "LABELVALUE",
    "MEMORYINDEX",
    "MEMORYINDEXMANIFEST",
    "NORMALIZER",
    "OUTCOME",
    "OUTCOMEREVISION",
    "RUNNERGENOME",
}
_LEARNED_KINDS = {
    "CALIBRATOR",
    "EMBEDDING",
    "ENCODER",
    "ENSEMBLEWEIGHTS",
    "FEATURESELECTOR",
    "GENOME",
    "IMPUTER",
    "MEMORYINDEX",
    "MEMORYINDEXMANIFEST",
    "MODEL",
    "MODELMANIFEST",
    "NORMALIZER",
    "PCA",
    "RUNNERGENOME",
    "SCOREMANIFEST",
}
_INDEX_KINDS = {"EMBEDDINGINDEX", "INDEX", "MEMORYINDEX", "MEMORYINDEXMANIFEST"}
_DERIVED_CUTOFF_KINDS = {"DATASETMANIFEST", "FEATURESNAPSHOT"}


def _time(value: str) -> datetime:
    return parse_utc_instant(value, "temporal boundary")


def _availability(
    artifact: TemporalArtifact,
    mode: TemporalMode,
    *,
    for_learning: bool,
) -> datetime | None:
    kind = normalize_kind(artifact.artifact_kind)
    if mode is TemporalMode.FORWARD:
        if artifact.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED":
            return None
        actual = (
            artifact.available_for_learning_at
            if for_learning and kind in _LEARNING_GATED_KINDS
            else artifact.known_at
        )
        if actual is None:
            return None
        return _time(actual)
    if for_learning and kind in _LEARNING_GATED_KINDS:
        simulated = artifact.historical_assumed_available_for_learning_at
        if simulated is None:
            return None
        return _time(simulated)
    if artifact.historical_assumed_available_at is None:
        return None
    return _time(artifact.historical_assumed_available_at)


def _is_reconstructed_derived(artifact: TemporalArtifact, mode: TemporalMode) -> bool:
    kind = normalize_kind(artifact.artifact_kind)
    return (
        mode is TemporalMode.HISTORICAL_RECONSTRUCTED
        and artifact.evidence_class.upper() == "HISTORICAL_RECONSTRUCTED"
        and (
            kind in _LEARNED_KINDS
            or kind in _DERIVED_CUTOFF_KINDS
            or kind in _INDEX_KINDS
        )
    )


@dataclass(frozen=True, slots=True)
class _CacheKey:
    catalog_revision: str
    catalog_fingerprint: str
    cutoff: str
    mode: str
    operation: str
    artifact_ids: tuple[str, ...]
    logical_keys: tuple[str, ...]
    training_cutoff: str | None
    operations: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    allow_reconstructed: bool


class TemporalResultCache:
    """Result cache whose identity includes the complete catalog and cutoff scope."""

    def __init__(self) -> None:
        self._entries: dict[_CacheKey, TemporalView] = {}

    def _get(self, key: _CacheKey) -> TemporalView | None:
        return self._entries.get(key)

    def _put(self, key: _CacheKey, value: TemporalView) -> None:
        self._entries[key] = value


class TemporalFirewall:
    """The only supported query/export boundary for cutoff-sensitive artifacts.

    Catalog inputs are an immutable snapshot. A storage adapter must provide this
    API instead of exposing unrestricted joins or post-retrieval filtering.
    """

    def __init__(
        self,
        artifacts: Iterable[TemporalArtifact],
        *,
        catalog_revision: str,
        result_cache: TemporalResultCache | None = None,
    ) -> None:
        if not isinstance(catalog_revision, str) or not catalog_revision.strip():
            raise TemporalViolation("catalog_revision_required", "catalog_revision is required")
        items: dict[str, TemporalArtifact] = {}
        for artifact in artifacts:
            if artifact.artifact_id in items:
                raise TemporalViolation(
                    "duplicate_artifact_id", f"duplicate artifact ID {artifact.artifact_id}"
                )
            items[artifact.artifact_id] = artifact
        self._artifacts: Mapping[str, TemporalArtifact] = MappingProxyType(items)
        self._catalog_revision = catalog_revision
        self._catalog_fingerprint = self._fingerprint(items.values())
        self._cache = result_cache or TemporalResultCache()

    @staticmethod
    def _fingerprint(artifacts: Iterable[TemporalArtifact]) -> str:
        rows = []
        for artifact in sorted(artifacts, key=lambda item: item.artifact_id):
            rows.append(
                {
                    "id": artifact.artifact_id,
                    "kind": artifact.artifact_kind,
                    "revision": artifact.revision_id,
                    "hash": artifact.content_hash,
                    "created_at": artifact.created_at,
                    "known_at": artifact.known_at,
                    "observed_at": artifact.observed_at,
                    "ingested_at": artifact.ingested_at,
                    "event_time": artifact.event_time,
                    "available_for_learning_at": artifact.available_for_learning_at,
                    "historical_assumed_available_at": artifact.historical_assumed_available_at,
                    "historical_assumed_available_for_learning_at": (
                        artifact.historical_assumed_available_for_learning_at
                    ),
                    "training_cutoff": artifact.training_cutoff,
                    "decision_cutoff": artifact.decision_cutoff,
                    "index_cutoff": artifact.index_cutoff,
                    "dependencies": artifact.dependency_refs,
                    "members": artifact.index_member_refs,
                    "logical_key": artifact.logical_key,
                    "alias_target": artifact.alias_target,
                    "evidence_class": artifact.evidence_class,
                    "payload": artifact.payload,
                }
            )
        return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()

    def query(
        self, query: TemporalQuery, permission: TemporalPermission
    ) -> TemporalView:
        if query.operation is not TemporalOperation.QUERY:
            raise TemporalViolation("operation_mismatch", "query() requires operation QUERY")
        return self._select(query, permission)

    def export(
        self, query: TemporalQuery, permission: TemporalPermission
    ) -> TemporalExport:
        if query.operation is not TemporalOperation.EXPORT:
            raise TemporalViolation("operation_mismatch", "export() requires operation EXPORT")
        view = self._select(query, permission)
        payload = {
            "format": "qc2.temporal_firewall.export.v1",
            "mode": view.mode.value,
            "evidence_class": view.evidence_class,
            "cutoff": view.cutoff,
            "training_cutoff": query.training_cutoff,
            "catalog_revision": view.catalog_revision,
            "resolved_aliases": view.resolved_aliases,
            "artifacts": [
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_kind": artifact.artifact_kind,
                    "revision_id": artifact.revision_id,
                    "content_hash": artifact.content_hash,
                    "created_at": artifact.created_at,
                    "known_at": artifact.known_at,
                    "observed_at": artifact.observed_at,
                    "ingested_at": artifact.ingested_at,
                    "event_time": artifact.event_time,
                    "available_for_learning_at": artifact.available_for_learning_at,
                    "historical_assumed_available_at": artifact.historical_assumed_available_at,
                    "historical_assumed_available_for_learning_at": (
                        artifact.historical_assumed_available_for_learning_at
                    ),
                    "payload": artifact.payload,
                }
                for artifact in view.artifacts
            ],
        }
        return TemporalExport(view=view, payload=canonical_json_bytes(payload))

    def _authorize(
        self, query: TemporalQuery, permission: TemporalPermission
    ) -> None:
        if not isinstance(permission, TemporalPermission):
            raise TemporalViolation("permission_required", "an explicit temporal permission is required")
        if query.operation not in permission.operations:
            raise TemporalViolation(
                "operation_not_permitted", f"{query.operation.value} is not permitted"
            )
        if (
            query.mode is TemporalMode.HISTORICAL_RECONSTRUCTED
            and not permission.allow_historical_reconstructed
        ):
            raise TemporalViolation(
                "reconstruction_not_permitted",
                "historical reconstruction requires an explicit permission",
            )
        if query.operation is TemporalOperation.EXPORT and query.training_cutoff is None:
            raise TemporalViolation("training_cutoff_required", "exports require a training cutoff")

    def _cache_key(
        self, query: TemporalQuery, permission: TemporalPermission
    ) -> _CacheKey:
        return _CacheKey(
            catalog_revision=self._catalog_revision,
            catalog_fingerprint=self._catalog_fingerprint,
            cutoff=query.cutoff,
            mode=query.mode.value,
            operation=query.operation.value,
            artifact_ids=query.artifact_ids,
            logical_keys=query.logical_keys,
            training_cutoff=query.training_cutoff,
            operations=tuple(sorted(item.value for item in permission.operations)),
            artifact_kinds=tuple(sorted(permission.artifact_kinds)),
            allow_reconstructed=permission.allow_historical_reconstructed,
        )

    def _select(
        self, query: TemporalQuery, permission: TemporalPermission
    ) -> TemporalView:
        self._authorize(query, permission)
        key = self._cache_key(query, permission)
        cached = self._cache._get(key)
        if cached is not None:
            from dataclasses import replace

            return replace(cached, cache_hit=True)

        eligible: dict[str, TemporalArtifact] = {}
        for artifact in self._artifacts.values():
            kind = normalize_kind(artifact.artifact_kind)
            if kind not in permission.artifact_kinds:
                continue
            if query.operation is TemporalOperation.QUERY and kind in _PROTECTED_QUERY_KINDS:
                continue
            available = _availability(
                artifact,
                query.mode,
                for_learning=query.operation is TemporalOperation.EXPORT,
            )
            if available is None or available > _time(query.cutoff):
                continue
            if artifact.event_time is not None and _time(artifact.event_time) > _time(query.cutoff):
                continue
            if query.mode is TemporalMode.FORWARD:
                if any(
                    timestamp is not None and _time(timestamp) > _time(query.cutoff)
                    for timestamp in (artifact.created_at, artifact.observed_at, artifact.ingested_at)
                ):
                    continue
            eligible[artifact.artifact_id] = artifact

        selected: dict[str, TemporalArtifact] = {}
        aliases: dict[str, str] = {}
        for artifact_id in query.artifact_ids:
            artifact = self._artifacts.get(artifact_id)
            if artifact is None:
                raise TemporalViolation("artifact_not_found", "requested artifact does not exist")
            if normalize_kind(artifact.artifact_kind) not in permission.artifact_kinds:
                raise TemporalViolation("permission_denied", "artifact kind is outside the grant")
            if artifact_id not in eligible:
                raise TemporalViolation(
                    "artifact_unavailable_at_cutoff",
                    "requested artifact is not available under this temporal scope",
                )
            selected[artifact_id] = artifact

        for logical_key in query.logical_keys:
            direct = [
                item
                for item in eligible.values()
                if item.logical_key == logical_key
                and normalize_kind(item.artifact_kind) != "METADATAALIAS"
            ]
            alias_records = [
                item
                for item in eligible.values()
                if item.logical_key == logical_key
                and normalize_kind(item.artifact_kind) == "METADATAALIAS"
            ]
            if alias_records:
                alias = self._latest(alias_records, query.mode)
                assert alias.alias_target is not None
                target = eligible.get(alias.alias_target)
                if target is None:
                    raise TemporalViolation(
                        "alias_target_unavailable_at_cutoff",
                        "metadata alias target is missing or outside the temporal scope",
                    )
                selected[alias.artifact_id] = alias
                selected[target.artifact_id] = target
                aliases[logical_key] = target.artifact_id
            elif direct:
                item = self._latest(direct, query.mode)
                selected[item.artifact_id] = item
            else:
                known_key = any(
                    item.logical_key == logical_key for item in self._artifacts.values()
                )
                code = "artifact_unavailable_at_cutoff" if known_key else "logical_key_not_found"
                raise TemporalViolation(code, "logical key has no eligible record at this cutoff")

        for artifact in selected.values():
            self._validate_selected(artifact, query)

        ordered = tuple(sorted(selected.values(), key=lambda item: item.artifact_id))
        if query.mode is TemporalMode.HISTORICAL_RECONSTRUCTED:
            evidence_class = "HISTORICAL_RECONSTRUCTED"
        elif any(item.evidence_class.upper() == "SYNTHETIC_FIXTURE" for item in ordered):
            evidence_class = "SYNTHETIC_FIXTURE"
        else:
            evidence_class = "FORWARD_OPERATIONAL"
        view = TemporalView(
            cutoff=query.cutoff,
            mode=query.mode,
            operation=query.operation,
            evidence_class=evidence_class,
            catalog_revision=self._catalog_revision,
            artifacts=ordered,
            resolved_aliases=aliases,
        )
        self._cache._put(key, view)
        return view

    def _latest(
        self, candidates: list[TemporalArtifact], mode: TemporalMode
    ) -> TemporalArtifact:
        by_availability: dict[datetime, list[TemporalArtifact]] = {}
        for artifact in candidates:
            availability = _availability(
                artifact,
                mode,
                for_learning=False,
            )
            if availability is None:
                continue
            by_availability.setdefault(availability, []).append(artifact)
        latest = max(by_availability, default=None)
        if latest is None:
            raise TemporalViolation(
                "artifact_unavailable_at_cutoff", "no version is available at this cutoff"
            )
        versions = by_availability[latest]
        if len(versions) != 1:
            raise TemporalViolation(
                "ambiguous_logical_revision",
                "multiple revisions have the same latest availability time",
            )
        return versions[0]

    def _validate_selected(self, artifact: TemporalArtifact, query: TemporalQuery) -> None:
        kind = normalize_kind(artifact.artifact_kind)
        if artifact.decision_cutoff is not None and _time(artifact.decision_cutoff) > _time(
            query.cutoff
        ):
            raise TemporalViolation(
                "artifact_cutoff_after_query",
                "artifact decision cutoff exceeds the query cutoff",
            )
        if artifact.index_cutoff is not None and _time(artifact.index_cutoff) > _time(query.cutoff):
            raise TemporalViolation(
                "index_cutoff_after_query", "index cutoff exceeds the query cutoff"
            )
        if query.operation is TemporalOperation.EXPORT:
            assert query.training_cutoff is not None
            self._validate_closure(
                (artifact.artifact_id,),
                cutoff=query.training_cutoff,
                mode=query.mode,
                learning_export=True,
            )
            return
        if kind in _LEARNED_KINDS:
            if artifact.training_cutoff is None:
                raise TemporalViolation(
                    "training_cutoff_missing", "learned artifacts require a declared training cutoff"
                )
            if _time(artifact.training_cutoff) > _time(query.cutoff):
                raise TemporalViolation(
                    "training_cutoff_after_query",
                    "learned artifact was trained after the query cutoff",
                )
            self._validate_closure(
                (artifact.artifact_id,),
                cutoff=artifact.training_cutoff,
                mode=query.mode,
                learning_export=True,
            )
            return
        if kind in _DERIVED_CUTOFF_KINDS:
            if kind == "FEATURESNAPSHOT" and artifact.decision_cutoff is None:
                raise TemporalViolation(
                    "decision_cutoff_missing", "feature snapshots require a declared decision cutoff"
                )
            if not artifact.dependency_refs:
                raise TemporalViolation(
                    "temporal_dependency_manifest_missing",
                    "derived artifacts require explicit temporal dependency references",
                )
            self._validate_closure(
                (artifact.artifact_id,),
                cutoff=artifact.decision_cutoff or query.cutoff,
                mode=query.mode,
                learning_export=False,
            )
            return
        if artifact.dependency_refs or artifact.index_member_refs:
            self._validate_closure(
                (artifact.artifact_id,),
                cutoff=query.cutoff,
                mode=query.mode,
                learning_export=False,
            )

    def _validate_closure(
        self,
        root_ids: tuple[str, ...],
        *,
        cutoff: str,
        mode: TemporalMode,
        learning_export: bool,
    ) -> tuple[str, ...]:
        cutoff_at = _time(cutoff)
        visited: set[str] = set()
        active: set[str] = set()
        closure: list[str] = []

        def visit(artifact_id: str, parent_cutoff: datetime, *, is_root: bool = False) -> None:
            if artifact_id in active:
                raise TemporalViolation(
                    "temporal_dependency_cycle", "temporal dependency graph contains a cycle"
                )
            if artifact_id in visited:
                return
            artifact = self._artifacts.get(artifact_id)
            if artifact is None:
                raise TemporalViolation(
                    "temporal_dependency_missing",
                    f"dependency {artifact_id} is absent from the catalog revision",
                )
            kind = normalize_kind(artifact.artifact_kind)
            if artifact.event_time is not None and _time(artifact.event_time) > parent_cutoff:
                raise TemporalViolation(
                    "dependency_event_after_cutoff",
                    f"dependency {artifact_id} has an event after its cutoff",
                )

            for declared in (
                artifact.training_cutoff,
                artifact.decision_cutoff,
                artifact.index_cutoff,
            ):
                if declared is not None and _time(declared) > parent_cutoff:
                    raise TemporalViolation(
                        "dependency_cutoff_after_parent",
                        f"dependency {artifact_id} declares a cutoff after its parent",
                    )

            reconstructed_derived = _is_reconstructed_derived(artifact, mode)
            if not (is_root and kind in _LEARNED_KINDS) and not reconstructed_derived:
                learning_guard = learning_export or kind in _LEARNING_GATED_KINDS
                available = _availability(artifact, mode, for_learning=learning_guard)
                if available is None or available > parent_cutoff:
                    raise TemporalViolation(
                        "dependency_unavailable_at_cutoff",
                        f"dependency {artifact_id} is not proven available by its cutoff",
                    )

            if kind in _LEARNED_KINDS:
                if artifact.training_cutoff is None:
                    raise TemporalViolation(
                        "training_cutoff_missing",
                        f"learned dependency {artifact_id} has no training cutoff",
                    )
                learned_cutoff = _time(artifact.training_cutoff)
                if learned_cutoff > parent_cutoff:
                    raise TemporalViolation(
                        "learned_dependency_cutoff_after_parent",
                        f"learned dependency {artifact_id} exceeds its parent cutoff",
                    )
                if not artifact.dependency_refs and not artifact.index_member_refs:
                    raise TemporalViolation(
                        "learned_dependency_manifest_missing",
                        f"learned artifact {artifact_id} has no dependency closure",
                    )
                child_cutoff = learned_cutoff
            elif kind == "FEATURESNAPSHOT":
                if artifact.decision_cutoff is None or not artifact.dependency_refs:
                    raise TemporalViolation(
                        "temporal_dependency_manifest_missing",
                        f"feature snapshot {artifact_id} lacks a cutoff or dependencies",
                    )
                child_cutoff = _time(artifact.decision_cutoff)
            elif kind in _INDEX_KINDS:
                if artifact.index_cutoff is None or not artifact.index_member_refs:
                    raise TemporalViolation(
                        "index_membership_manifest_missing",
                        f"index {artifact_id} lacks a cutoff or explicit member set",
                    )
                child_cutoff = _time(artifact.index_cutoff)
            else:
                child_cutoff = parent_cutoff

            active.add(artifact_id)
            closure.append(artifact_id)
            for dependency_id in (*artifact.dependency_refs, *artifact.index_member_refs):
                visit(dependency_id, child_cutoff)
            active.remove(artifact_id)
            visited.add(artifact_id)

        for root_id in root_ids:
            visit(root_id, cutoff_at, is_root=True)
        return tuple(closure)


__all__ = ["TemporalFirewall", "TemporalResultCache"]
