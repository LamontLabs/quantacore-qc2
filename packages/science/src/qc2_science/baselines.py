"""Deterministic, outcome-blind QC2 comparator rankings."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Any

from qc2_contracts.runtime import (
    canonical_content_hash,
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .models import as_date, as_decimal, as_utc

_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BASELINE_SCHEMA = "qc2.scientific_definitions.BaselineManifest.v1"
_FEATURE_REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
_CONFIGURATION_SCHEMA = "qc2.integrity_build.ConfigurationManifest.v1"
_UNIVERSE_SCHEMA = "qc2.identity_market.UniverseManifest.v1"
_FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
_TOP_K_TIE_RULE = (
    "AVERAGE_CROSS_SECTIONAL_MIDRANK_PERCENTILES;"
    "FINAL_SCORE_TIES_ASC_STABLE_INSTRUMENT_ID;"
    "TOP_K_EXACT"
)
_DECIMAL_PRECISION = 64
PRIMARY_REPORTING_K = 10
SECONDARY_REPORTING_K = (1, 5)


class BaselineError(ValueError):
    """A baseline definition or input is incomplete, ambiguous, or invalid."""


class InsufficientScoreableRows(BaselineError):
    """The requested Top-K exceeds a baseline's scoreable row count."""


class BaselineKind(StrEnum):
    RANDOM = "RANDOM"
    MOMENTUM_1 = "MOMENTUM_1"
    MOMENTUM_5 = "MOMENTUM_5"
    MOMENTUM_20 = "MOMENTUM_20"
    RELATIVE_VOLUME = "RELATIVE_VOLUME"
    BREAKOUT_PROXIMITY = "BREAKOUT_PROXIMITY"
    TRANSPARENT_COMPOSITE = "TRANSPARENT_COMPOSITE"


class BaselineDisposition(StrEnum):
    SCORED = "SCORED"
    UNSCORABLE = "UNSCORABLE"


@dataclass(frozen=True, slots=True)
class BaselineRunRow:
    """One eligible instrument's complete scored or reason-coded disposition."""

    instrument_id: str
    display_symbol: str | None
    disposition: BaselineDisposition
    rank: int | None
    score: Decimal | None
    percentile: Decimal | None
    reason_codes: tuple[str, ...] = ()
    component_percentiles: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        if not _UUID7.fullmatch(self.instrument_id):
            raise BaselineError("instrument_id must be a stable UUIDv7 identity")
        if self.display_symbol is not None and (
            not isinstance(self.display_symbol, str) or not self.display_symbol.strip()
        ):
            raise BaselineError("display_symbol must be non-empty when supplied")
        disposition = BaselineDisposition(self.disposition)
        reasons = tuple(self.reason_codes)
        components = tuple(self.component_percentiles)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason for reason in reasons
        ):
            raise BaselineError("reason_codes must be unique non-empty strings")
        component_names = tuple(name for name, _ in components)
        if len(component_names) != len(set(component_names)):
            raise BaselineError("component percentiles must have unique feature IDs")
        for _, value in components:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise BaselineError("component percentiles must be finite Decimals")
            if value < 0 or value > 1:
                raise BaselineError("component percentiles must be in [0, 1]")

        if disposition is BaselineDisposition.SCORED:
            if (
                isinstance(self.rank, bool)
                or not isinstance(self.rank, int)
                or self.rank < 1
                or not isinstance(self.score, Decimal)
                or not self.score.is_finite()
                or not isinstance(self.percentile, Decimal)
                or not self.percentile.is_finite()
                or self.percentile < 0
                or self.percentile > 1
                or reasons
            ):
                raise BaselineError("scored rows require rank, score, percentile, and no reasons")
        elif (
            self.rank is not None
            or self.score is not None
            or self.percentile is not None
            or not reasons
        ):
            raise BaselineError("unscorable rows require reasons and no rank or score")

        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "component_percentiles", components)


@dataclass(frozen=True, slots=True)
class BaselineRun:
    """Immutable rankings for one baseline, universe, session, and cutoff."""

    baseline_kind: BaselineKind
    manifest_id: str
    manifest_hash: str
    universe_manifest_id: str
    data_bundle_id: str
    data_bundle_hash: str | None
    epoch_id: str | None
    session_id: str
    decision_cutoff: datetime
    feature_registry_id: str
    feature_registry_hash: str
    feature_snapshot_refs: tuple[tuple[str, str, str], ...]
    seed_digest: str | None
    rows: tuple[BaselineRunRow, ...]

    def __post_init__(self) -> None:
        kind = BaselineKind(self.baseline_kind)
        for name in ("manifest_id", "universe_manifest_id", "data_bundle_id"):
            if not _UUID7.fullmatch(getattr(self, name)):
                raise BaselineError(f"{name} must be a UUIDv7")
        if self.data_bundle_hash is not None and not _SHA256.fullmatch(
            self.data_bundle_hash
        ):
            raise BaselineError("data_bundle_hash must be lowercase SHA-256 when supplied")
        if self.epoch_id is not None and not _UUID7.fullmatch(self.epoch_id):
            raise BaselineError("epoch_id must be a UUIDv7 when supplied")
        if not _SHA256.fullmatch(self.manifest_hash):
            raise BaselineError("manifest_hash must be a lowercase SHA-256 digest")
        if not _UUID7.fullmatch(self.feature_registry_id):
            raise BaselineError("feature_registry_id must be a UUIDv7")
        if not _SHA256.fullmatch(self.feature_registry_hash):
            raise BaselineError("feature_registry_hash must be a lowercase SHA-256 digest")
        if self.seed_digest is not None and not _SHA256.fullmatch(self.seed_digest):
            raise BaselineError("seed_digest must be a lowercase SHA-256 digest")
        session = as_date(self.session_id, "session_id").isoformat()
        cutoff = as_utc(self.decision_cutoff, "decision_cutoff")
        refs = tuple(sorted(tuple(ref) for ref in self.feature_snapshot_refs))
        if any(
            len(ref) != 3
            or not _UUID7.fullmatch(ref[0])
            or not _UUID7.fullmatch(ref[1])
            or not _SHA256.fullmatch(ref[2])
            for ref in refs
        ):
            raise BaselineError(
                "feature_snapshot_refs must bind instrument IDs, snapshot IDs, and hashes"
            )
        if len({ref[0] for ref in refs}) != len(refs):
            raise BaselineError("feature_snapshot_refs contain duplicate instrument IDs")
        if len({ref[1] for ref in refs}) != len(refs):
            raise BaselineError("feature_snapshot_refs contain duplicate snapshot IDs")
        rows = tuple(self.rows)
        if not rows or any(not isinstance(row, BaselineRunRow) for row in rows):
            raise BaselineError("baseline run must account for every eligible row")
        instrument_ids = tuple(row.instrument_id for row in rows)
        if len(instrument_ids) != len(set(instrument_ids)):
            raise BaselineError("baseline run contains duplicate instrument rows")
        ranks = tuple(
            row.rank
            for row in rows
            if row.disposition is BaselineDisposition.SCORED
        )
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise BaselineError("scored row ranks must be contiguous and one-based")
        if kind is BaselineKind.RANDOM and (
            self.epoch_id is None or self.seed_digest is None
        ):
            raise BaselineError("random baseline runs require epoch and seed identity")
        if kind is not BaselineKind.RANDOM and self.seed_digest is not None:
            raise BaselineError("only random baseline runs may carry a seed digest")

        object.__setattr__(self, "baseline_kind", kind)
        object.__setattr__(self, "session_id", session)
        object.__setattr__(self, "decision_cutoff", cutoff)
        object.__setattr__(self, "feature_snapshot_refs", refs)
        object.__setattr__(self, "rows", rows)

    @property
    def scoreable_count(self) -> int:
        return sum(row.disposition is BaselineDisposition.SCORED for row in self.rows)

    @property
    def unscorable_count(self) -> int:
        return len(self.rows) - self.scoreable_count


@dataclass(frozen=True, slots=True)
class BaselineExecution:
    """Retains every ranking in a preregistered random seed set."""

    manifest_id: str
    manifest_hash: str
    baseline_kind: BaselineKind
    seed_set_hash: str | None
    runs: tuple[BaselineRun, ...]

    def __post_init__(self) -> None:
        kind = BaselineKind(self.baseline_kind)
        runs = tuple(self.runs)
        if not runs or any(run.baseline_kind is not kind for run in runs):
            raise BaselineError("execution must retain one or more matching baseline runs")
        if any(
            run.manifest_id != self.manifest_id
            or run.manifest_hash != self.manifest_hash
            for run in runs
        ):
            raise BaselineError("execution runs must bind to the same baseline manifest")
        seed_digests = tuple(run.seed_digest for run in runs)
        if kind is BaselineKind.RANDOM:
            if (
                self.seed_set_hash is None
                or not _SHA256.fullmatch(self.seed_set_hash)
                or any(digest is None for digest in seed_digests)
                or len(set(seed_digests)) != len(seed_digests)
            ):
                raise BaselineError("random execution must retain a unique digest per seed")
        elif len(runs) != 1 or self.seed_set_hash is not None:
            raise BaselineError("non-random executions contain exactly one run and no seed set")
        object.__setattr__(self, "baseline_kind", kind)
        object.__setattr__(self, "runs", runs)


@dataclass(frozen=True, slots=True)
class _FeatureDatum:
    value: Decimal | None
    missing_reason: str | None


@dataclass(frozen=True, slots=True)
class _PreparedInput:
    universe_id: str
    data_bundle_id: str
    data_bundle_hash: str | None
    session_id: str
    decision_cutoff: datetime
    eligible_ids: tuple[str, ...]
    display_symbols: tuple[tuple[str, str], ...]
    features_by_instrument: tuple[
        tuple[str, tuple[tuple[str, _FeatureDatum], ...]], ...
    ]
    feature_snapshot_instrument_ids: tuple[str, ...]
    feature_snapshot_refs: tuple[tuple[str, str, str], ...]
    feature_registry_id: str
    feature_registry_hash: str


_FEATURES: dict[str, tuple[str, bool]] = {
    "return_1": ("fraction", True),
    "return_5": ("fraction", True),
    "return_20": ("fraction", True),
    "relative_volume": ("ratio", True),
    "breakout_proximity": ("fraction", False),
}
_COMPOSITE_FEATURES = (
    "return_1",
    "return_5",
    "return_20",
    "relative_volume",
    "breakout_proximity",
)
_KIND_FEATURE = {
    BaselineKind.MOMENTUM_1: "return_1",
    BaselineKind.MOMENTUM_5: "return_5",
    BaselineKind.MOMENTUM_20: "return_20",
    BaselineKind.RELATIVE_VOLUME: "relative_volume",
    BaselineKind.BREAKOUT_PROXIMITY: "breakout_proximity",
}
_ALGORITHM = {
    BaselineKind.RANDOM: (
        "rank ascending by SHA256(canonical JSON [seed, epoch_id, session_id, "
        "stable instrument UUIDv7]); retain every preregistered seed."
    ),
    BaselineKind.MOMENTUM_1: (
        "score=FeatureSnapshot.return_1=C_t/C_(t-1)-1; higher is better."
    ),
    BaselineKind.MOMENTUM_5: (
        "score=FeatureSnapshot.return_5=C_t/C_(t-5)-1; higher is better."
    ),
    BaselineKind.MOMENTUM_20: (
        "score=FeatureSnapshot.return_20=C_t/C_(t-20)-1; higher is better."
    ),
    BaselineKind.RELATIVE_VOLUME: (
        "score=FeatureSnapshot.relative_volume=V_t/arithmetic_mean(V over prior "
        "relative_volume_lookback_sessions); higher is better."
    ),
    BaselineKind.BREAKOUT_PROXIMITY: (
        "score=FeatureSnapshot.breakout_proximity=(max(prior "
        "breakout_proximity_lookback_sessions highs)-H_t)/max(prior highs); "
        "lower is better."
    ),
    BaselineKind.TRANSPARENT_COMPOSITE: (
        "score=equal-weight mean of the cross-sectional average-rank percentiles for "
        "return_1, return_5, return_20, relative_volume, and breakout_proximity; "
        "higher is better for the first four and lower is better for breakout_proximity; "
        "all five use the complete composite-scoreable intersection; each weight is 1/5."
    ),
}
_ROLE = {
    BaselineKind.RANDOM: "SECONDARY",
    BaselineKind.MOMENTUM_1: "SECONDARY",
    BaselineKind.MOMENTUM_5: "SECONDARY",
    BaselineKind.MOMENTUM_20: "SECONDARY",
    BaselineKind.RELATIVE_VOLUME: "SECONDARY",
    BaselineKind.BREAKOUT_PROXIMITY: "SECONDARY",
    BaselineKind.TRANSPARENT_COMPOSITE: "PRIMARY",
}
_PARAMETERIZED_KINDS = {
    BaselineKind.RELATIVE_VOLUME,
    BaselineKind.BREAKOUT_PROXIMITY,
    BaselineKind.TRANSPARENT_COMPOSITE,
}
_PARAMETER_KEYS = {
    BaselineKind.RELATIVE_VOLUME: ("relative_volume_lookback_sessions",),
    BaselineKind.BREAKOUT_PROXIMITY: ("breakout_proximity_lookback_sessions",),
    BaselineKind.TRANSPARENT_COMPOSITE: (
        "relative_volume_lookback_sessions",
        "breakout_proximity_lookback_sessions",
    ),
}


def _normalise_parameters(
    kind: BaselineKind,
    parameter_values: Mapping[str, int] | None,
) -> dict[str, int]:
    values = parameter_values or {}
    if not isinstance(values, Mapping):
        raise BaselineError("parameter_values must be a mapping")
    expected_keys = _PARAMETER_KEYS.get(kind, ())
    if set(values) != set(expected_keys):
        if expected_keys:
            raise BaselineError(
                f"{kind.value} requires exactly these pinned parameters: "
                + ", ".join(expected_keys)
            )
        if values:
            raise BaselineError(f"{kind.value} does not accept fitted parameters")
        return {}
    normalized: dict[str, int] = {}
    for key in expected_keys:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise BaselineError(f"{key} must be a positive integer")
        normalized[key] = value
    return normalized


def _algorithm_text(
    kind: BaselineKind,
    parameter_values: Mapping[str, int] | None = None,
) -> str:
    base = _ALGORITHM[kind]
    normalized = _normalise_parameters(kind, parameter_values)
    if not normalized:
        return base
    return (
        base
        + " Calibration parameters: "
        + canonical_json_bytes(normalized).decode("utf-8")
        + "; values must match the referenced configuration and feature registry."
    )


def _parameters_from_algorithm(kind: BaselineKind, algorithm: str) -> dict[str, int]:
    if kind not in _PARAMETERIZED_KINDS:
        if algorithm != _ALGORITHM[kind]:
            raise BaselineError("manifest does not match the frozen baseline definition")
        return {}
    prefix = _ALGORITHM[kind] + " Calibration parameters: "
    suffix = "; values must match the referenced configuration and feature registry."
    if not algorithm.startswith(prefix) or not algorithm.endswith(suffix):
        raise BaselineError("parameterized manifest omits its explicit calibration values")
    encoded = algorithm[len(prefix) : -len(suffix)]
    try:
        parsed = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise BaselineError("calibration parameters are not valid canonical JSON") from exc
    if not isinstance(parsed, dict):
        raise BaselineError("calibration parameters must be a JSON object")
    normalized = _normalise_parameters(kind, parsed)
    if canonical_json_bytes(normalized).decode("utf-8") != encoded:
        raise BaselineError("calibration parameters must use canonical QC2 JSON")
    return normalized


def _contract_ref(
    value: Mapping[str, Any],
    *,
    schema_name: str,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise BaselineError(f"{field_name} must be a contract reference")
    reference = dict(value)
    if set(reference) - {"target_schema_name", "target_id", "content_hash"}:
        raise BaselineError(f"{field_name} contains unsupported reference fields")
    if reference.get("target_schema_name") != schema_name:
        raise BaselineError(f"{field_name} must reference {schema_name}")
    if not isinstance(reference.get("target_id"), str) or not _UUID7.fullmatch(
        reference["target_id"]
    ):
        raise BaselineError(f"{field_name}.target_id must be a UUIDv7")
    digest = reference.get("content_hash")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise BaselineError(f"{field_name}.content_hash must be lowercase SHA-256")
    return {
        "target_schema_name": schema_name,
        "target_id": reference["target_id"],
        "content_hash": digest,
    }


def _normalise_seeds(seed_values: Sequence[str] | None) -> tuple[str, ...]:
    if seed_values is None or isinstance(seed_values, (str, bytes)):
        raise BaselineError("random baseline requires an explicit seed set")
    if not isinstance(seed_values, Sequence):
        raise BaselineError("seed_values must be a sequence")
    raw_seeds = tuple(seed_values)
    if any(not isinstance(seed, str) or not seed for seed in raw_seeds):
        raise BaselineError("seed set values must be non-empty strings")
    seeds = tuple(unicodedata.normalize("NFC", seed) for seed in raw_seeds)
    if len(seeds) != len(set(seeds)):
        raise BaselineError("seed set must not contain duplicates after canonicalization")
    if not seeds:
        raise BaselineError("random baseline seed set must not be empty")
    return tuple(sorted(seeds))


def _seed_set_hash(seeds: Sequence[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(list(seeds))).hexdigest()


def materialize_baseline_manifest(
    baseline_kind: BaselineKind | str,
    *,
    feature_registry_ref: Mapping[str, Any],
    parameter_refs: Sequence[Mapping[str, Any]] = (),
    parameter_values: Mapping[str, int] | None = None,
    seed_values: Sequence[str] | None = None,
    manifest_id: str | None = None,
    created_at: datetime | str,
    evidence_class: str,
    environment_namespace: str,
) -> dict[str, Any]:
    """Create a content-addressed manifest with fixed equations and no fitted weights."""
    try:
        kind = BaselineKind(baseline_kind)
    except ValueError as exc:
        raise BaselineError("unsupported baseline kind") from exc
    registry_ref = _contract_ref(
        feature_registry_ref,
        schema_name=_FEATURE_REGISTRY_SCHEMA,
        field_name="feature_registry_ref",
    )
    if isinstance(parameter_refs, (str, bytes)) or not isinstance(
        parameter_refs, Sequence
    ):
        raise BaselineError("parameter_refs must be a sequence")
    normalized_parameters = tuple(
        _contract_ref(
            reference,
            schema_name=_CONFIGURATION_SCHEMA,
            field_name="parameter_ref",
        )
        for reference in parameter_refs
    )
    if len({ref["target_id"] for ref in normalized_parameters}) != len(
        normalized_parameters
    ):
        raise BaselineError("parameter_refs must be unique")
    if kind in _PARAMETERIZED_KINDS and len(normalized_parameters) != 1:
        raise BaselineError(
            "relative-volume, breakout, and composite manifests require one pinned calibration ref"
        )
    if kind not in _PARAMETERIZED_KINDS and normalized_parameters:
        raise BaselineError("this baseline kind does not accept fitted parameters")
    normalized_parameter_values = _normalise_parameters(kind, parameter_values)

    if kind is BaselineKind.RANDOM:
        seeds = _normalise_seeds(seed_values)
        seed_hash: str | None = _seed_set_hash(seeds)
    else:
        if seed_values not in (None, (), []):
            raise BaselineError("only the random baseline accepts seed values")
        seeds = ()
        seed_hash = None

    created = as_utc(created_at, "created_at")
    if environment_namespace == "production":
        raise BaselineError("QC2-022 baselines have no production activation path")
    if evidence_class == "SYNTHETIC_FIXTURE" and environment_namespace != "test":
        raise BaselineError("synthetic baseline parameters are restricted to the test environment")
    payload: dict[str, Any] = {
        "schema_name": _BASELINE_SCHEMA,
        "schema_version": "1.0",
        "id": manifest_id or new_uuidv7(),
        "created_at": created.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owning_authority": "validation",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [registry_ref],
        "content_hash": "0" * 64,
        "baseline_kind": kind.value,
        "version": 1,
        "algorithm": _algorithm_text(kind, normalized_parameter_values),
        "parameter_refs": list(normalized_parameters),
        "seed_hash": seed_hash,
        "comparator_role": _ROLE[kind],
        "tie_break_rule": _TOP_K_TIE_RULE,
    }
    payload["content_hash"] = canonical_content_hash("BaselineManifest", payload)
    validate_contract("BaselineManifest", payload)
    verify_content_hash("BaselineManifest", payload)
    return payload


def _manifest_context(
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], BaselineKind, dict[str, str]]:
    if not isinstance(manifest, Mapping):
        raise BaselineError("baseline manifest must be an object")
    payload = dict(manifest)
    validate_contract("BaselineManifest", payload)
    verify_content_hash("BaselineManifest", payload)
    try:
        kind = BaselineKind(payload["baseline_kind"])
    except ValueError as exc:
        raise BaselineError("unsupported baseline kind") from exc
    if payload["version"] != 1 or payload["comparator_role"] != _ROLE[kind] or (
        payload["tie_break_rule"] != _TOP_K_TIE_RULE
    ):
        raise BaselineError("manifest does not match the frozen baseline definition")
    if payload["environment_namespace"] == "production" or (
        payload["evidence_class"] == "SYNTHETIC_FIXTURE"
        and payload["environment_namespace"] != "test"
    ):
        raise BaselineError("baseline manifest uses an unapproved evidence environment")
    _parameters_from_algorithm(kind, payload["algorithm"])
    source_refs = payload["source_refs"]
    if len(source_refs) != 1:
        raise BaselineError("baseline manifest must bind exactly one feature registry")
    registry_ref = _contract_ref(
        source_refs[0],
        schema_name=_FEATURE_REGISTRY_SCHEMA,
        field_name="baseline feature registry",
    )
    parameters = payload["parameter_refs"]
    if kind in _PARAMETERIZED_KINDS:
        if len(parameters) != 1:
            raise BaselineError("baseline manifest is missing its calibration reference")
        _contract_ref(
            parameters[0],
            schema_name=_CONFIGURATION_SCHEMA,
            field_name="baseline calibration reference",
        )
    elif parameters:
        raise BaselineError("baseline manifest contains unapproved fitted parameters")
    return payload, kind, registry_ref


def _feature_value_map(
    snapshot: Mapping[str, Any],
) -> dict[str, _FeatureDatum]:
    values: dict[str, _FeatureDatum] = {}
    seen: set[str] = set()
    for item in snapshot["feature_values"]:
        feature_id = item["feature_id"]
        if feature_id in seen:
            raise BaselineError("FeatureSnapshot contains duplicate feature IDs")
        seen.add(feature_id)
        if feature_id not in _FEATURES:
            continue
        expected_unit, _ = _FEATURES[feature_id]
        if item["unit"] != expected_unit or item["output_dtype"] != "DECIMAL":
            raise BaselineError(f"{feature_id} has the wrong unit or output dtype")
        if "value" in item:
            values[feature_id] = _FeatureDatum(
                value=as_decimal(item["value"], feature_id),
                missing_reason=None,
            )
        else:
            values[feature_id] = _FeatureDatum(
                value=None,
                missing_reason=item["missing_reason"],
            )
    return values


def _prepare_input(
    manifest_payload: Mapping[str, Any],
    registry_ref: Mapping[str, str],
    universe_manifest: Mapping[str, Any],
    feature_snapshots: Sequence[Mapping[str, Any]],
    display_symbols_by_instrument_id: Mapping[str, str] | None,
) -> _PreparedInput:
    if not isinstance(universe_manifest, Mapping):
        raise BaselineError("universe_manifest must be an object")
    universe = dict(universe_manifest)
    validate_contract("UniverseManifest", universe)
    if (
        universe["evidence_class"] != manifest_payload["evidence_class"]
        or universe["environment_namespace"]
        != manifest_payload["environment_namespace"]
    ):
        raise BaselineError("baseline manifest and universe evidence contexts differ")
    eligible_refs = tuple(universe["eligible_instrument_refs"])
    eligible_ids = tuple(sorted(ref["target_id"] for ref in eligible_refs))
    if not eligible_ids:
        raise BaselineError("eligible universe must contain at least one instrument")
    if len(eligible_ids) != len(set(eligible_ids)):
        raise BaselineError("eligible universe contains duplicate stable instrument IDs")
    unscorable_ids = {
        ref["target_id"] for ref in universe["unscorable_instrument_refs"]
    }
    if unscorable_ids & set(eligible_ids):
        raise BaselineError("an instrument cannot be both eligible and upstream-unscorable")

    symbols = display_symbols_by_instrument_id or {}
    if not isinstance(symbols, Mapping):
        raise BaselineError("display_symbols_by_instrument_id must be a mapping")
    if set(symbols) - set(eligible_ids):
        raise BaselineError("display symbol map contains an instrument outside the universe")
    normalized_symbols: list[tuple[str, str]] = []
    for instrument_id, symbol in symbols.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise BaselineError("display symbols must be non-empty strings")
        normalized_symbols.append((instrument_id, symbol.strip()))

    if isinstance(feature_snapshots, (str, bytes)) or not isinstance(
        feature_snapshots, Sequence
    ):
        raise BaselineError("feature_snapshots must be a sequence")
    cutoff = as_utc(universe["cutoff"], "universe cutoff")
    session = as_date(universe["session_id"], "universe session_id").isoformat()
    feature_map: dict[str, dict[str, _FeatureDatum]] = {}
    snapshot_refs: list[tuple[str, str, str]] = []
    expected_context: tuple[str, str, str, str, str] | None = None
    for raw_snapshot in feature_snapshots:
        if not isinstance(raw_snapshot, Mapping):
            raise BaselineError("feature_snapshots must contain contract objects")
        snapshot = dict(raw_snapshot)
        validate_contract("FeatureSnapshot", snapshot)
        verify_content_hash("FeatureSnapshot", snapshot)
        instrument_id = snapshot["instrument_ref"]["target_id"]
        if instrument_id not in set(eligible_ids):
            raise BaselineError("FeatureSnapshot instrument is outside the eligible universe")
        if instrument_id in feature_map:
            raise BaselineError("duplicate FeatureSnapshot for one instrument/session")
        if snapshot["session_id"] != session:
            raise BaselineError("FeatureSnapshot session differs from the universe")
        if as_utc(snapshot["decision_cutoff"], "FeatureSnapshot decision_cutoff") != cutoff:
            raise BaselineError("FeatureSnapshot cutoff differs from the universe")
        snapshot_registry = _contract_ref(
            snapshot["registry_ref"],
            schema_name=_FEATURE_REGISTRY_SCHEMA,
            field_name="FeatureSnapshot registry_ref",
        )
        if snapshot_registry != dict(registry_ref):
            raise BaselineError("FeatureSnapshot uses a different feature registry")
        context = (
            snapshot_registry["target_id"],
            snapshot_registry["content_hash"],
            snapshot["code_hash"],
            snapshot["environment_fingerprint"],
            snapshot["evidence_class"] + ":" + snapshot["environment_namespace"],
        )
        if expected_context is None:
            expected_context = context
        elif context != expected_context:
            raise BaselineError("FeatureSnapshots mix registries, code, or evidence contexts")
        if (
            snapshot["evidence_class"] != manifest_payload["evidence_class"]
            or snapshot["environment_namespace"]
            != manifest_payload["environment_namespace"]
        ):
            raise BaselineError("FeatureSnapshot and baseline evidence contexts differ")
        feature_map[instrument_id] = _feature_value_map(snapshot)
        snapshot_refs.append((instrument_id, snapshot["id"], snapshot["content_hash"]))

    registry_id = registry_ref["target_id"]
    registry_hash = registry_ref["content_hash"]
    return _PreparedInput(
        universe_id=universe["id"],
        data_bundle_id=universe["data_bundle_ref"]["target_id"],
        data_bundle_hash=universe["data_bundle_ref"].get("content_hash"),
        session_id=session,
        decision_cutoff=cutoff,
        eligible_ids=eligible_ids,
        display_symbols=tuple(sorted(normalized_symbols)),
        features_by_instrument=tuple(
            (instrument_id, tuple(sorted(feature_map.get(instrument_id, {}).items())))
            for instrument_id in eligible_ids
        ),
        feature_snapshot_instrument_ids=tuple(sorted(feature_map)),
        feature_snapshot_refs=tuple(sorted(snapshot_refs)),
        feature_registry_id=registry_id,
        feature_registry_hash=registry_hash,
    )


def _percentiles(
    values: Mapping[str, Decimal],
    *,
    higher_is_better: bool,
) -> dict[str, Decimal]:
    if not values:
        return {}
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        total = Decimal(len(values))
        result: dict[str, Decimal] = {}
        for instrument_id, value in values.items():
            equal_count = sum(candidate == value for candidate in values.values())
            better_count = sum(
                candidate < value if higher_is_better else candidate > value
                for candidate in values.values()
            )
            result[instrument_id] = (
                Decimal(better_count) + Decimal(equal_count) / Decimal(2)
            ) / total
        return result


def _run_from_scores(
    *,
    manifest: Mapping[str, Any],
    kind: BaselineKind,
    prepared: _PreparedInput,
    scores: Mapping[str, Decimal],
    unscorable: Mapping[str, tuple[str, ...]],
    higher_is_better: bool,
    epoch_id: str | None,
    seed_digest: str | None = None,
    component_percentiles: Mapping[str, tuple[tuple[str, Decimal], ...]] | None = None,
) -> BaselineRun:
    if set(scores) & set(unscorable):
        raise BaselineError("a row cannot be both scored and unscorable")
    if set(scores) | set(unscorable) != set(prepared.eligible_ids):
        raise BaselineError("baseline run does not account for the complete eligible universe")
    percentiles = _percentiles(scores, higher_is_better=higher_is_better)
    ordered_ids = sorted(
        scores,
        key=lambda instrument_id: (
            -scores[instrument_id] if higher_is_better else scores[instrument_id],
            instrument_id,
        ),
    )
    symbol_map = dict(prepared.display_symbols)
    components = component_percentiles or {}
    rows: list[BaselineRunRow] = []
    for rank, instrument_id in enumerate(ordered_ids, start=1):
        rows.append(
            BaselineRunRow(
                instrument_id=instrument_id,
                display_symbol=symbol_map.get(instrument_id),
                disposition=BaselineDisposition.SCORED,
                rank=rank,
                score=scores[instrument_id],
                percentile=percentiles[instrument_id],
                component_percentiles=components.get(instrument_id, ()),
            )
        )
    for instrument_id in sorted(unscorable):
        rows.append(
            BaselineRunRow(
                instrument_id=instrument_id,
                display_symbol=symbol_map.get(instrument_id),
                disposition=BaselineDisposition.UNSCORABLE,
                rank=None,
                score=None,
                percentile=None,
                reason_codes=unscorable[instrument_id],
            )
        )
    return BaselineRun(
        baseline_kind=kind,
        manifest_id=manifest["id"],
        manifest_hash=manifest["content_hash"],
        universe_manifest_id=prepared.universe_id,
        data_bundle_id=prepared.data_bundle_id,
        data_bundle_hash=prepared.data_bundle_hash,
        epoch_id=epoch_id,
        session_id=prepared.session_id,
        decision_cutoff=prepared.decision_cutoff,
        feature_registry_id=prepared.feature_registry_id,
        feature_registry_hash=prepared.feature_registry_hash,
        feature_snapshot_refs=prepared.feature_snapshot_refs,
        seed_digest=seed_digest,
        rows=tuple(rows),
    )


def _unscorable_reason(
    features: Mapping[str, _FeatureDatum],
    required_feature_ids: Sequence[str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    for feature_id in required_feature_ids:
        datum = features.get(feature_id)
        if datum is None:
            reasons.append(f"FEATURE_RECORD_MISSING:{feature_id}")
        elif datum.value is None:
            reasons.append(
                f"FEATURE_UNSCORABLE:{feature_id}:{datum.missing_reason or 'UNKNOWN'}"
            )
    return tuple(reasons)


def _single_feature_run(
    *,
    manifest: Mapping[str, Any],
    kind: BaselineKind,
    prepared: _PreparedInput,
    epoch_id: str | None,
) -> BaselineRun:
    feature_id = _KIND_FEATURE[kind]
    higher_is_better = _FEATURES[feature_id][1]
    feature_rows = {
        instrument_id: dict(values)
        for instrument_id, values in prepared.features_by_instrument
    }
    snapshot_ids = set(prepared.feature_snapshot_instrument_ids)
    scores: dict[str, Decimal] = {}
    unscorable: dict[str, tuple[str, ...]] = {}
    for instrument_id in prepared.eligible_ids:
        if instrument_id not in snapshot_ids:
            unscorable[instrument_id] = ("FEATURE_SNAPSHOT_MISSING",)
            continue
        features = feature_rows[instrument_id]
        reasons = _unscorable_reason(features, (feature_id,))
        if reasons:
            unscorable[instrument_id] = reasons
            continue
        datum = features[feature_id]
        assert datum.value is not None
        scores[instrument_id] = datum.value
    return _run_from_scores(
        manifest=manifest,
        kind=kind,
        prepared=prepared,
        scores=scores,
        unscorable=unscorable,
        higher_is_better=higher_is_better,
        epoch_id=epoch_id,
    )


def _composite_run(
    *,
    manifest: Mapping[str, Any],
    prepared: _PreparedInput,
    epoch_id: str | None,
) -> BaselineRun:
    feature_rows = {
        instrument_id: dict(values)
        for instrument_id, values in prepared.features_by_instrument
    }
    snapshot_ids = set(prepared.feature_snapshot_instrument_ids)
    scores: dict[str, Decimal] = {}
    component_percentiles: dict[str, tuple[tuple[str, Decimal], ...]] = {}
    unscorable: dict[str, tuple[str, ...]] = {}
    component_values = {feature_id: {} for feature_id in _COMPOSITE_FEATURES}

    for instrument_id in prepared.eligible_ids:
        if instrument_id not in snapshot_ids:
            unscorable[instrument_id] = ("FEATURE_SNAPSHOT_MISSING",)
            continue
        features = feature_rows[instrument_id]
        reasons = _unscorable_reason(features, _COMPOSITE_FEATURES)
        if reasons:
            unscorable[instrument_id] = reasons
            continue
        for feature_id in _COMPOSITE_FEATURES:
            datum = features[feature_id]
            assert datum.value is not None
            component_values[feature_id][instrument_id] = datum.value

    ranked_components = {
        feature_id: _percentiles(
            values,
            higher_is_better=_FEATURES[feature_id][1],
        )
        for feature_id, values in component_values.items()
    }
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        for instrument_id in sorted(set.intersection(
            *(set(values) for values in component_values.values())
        )):
            contributions = tuple(
                (
                    feature_id,
                    ranked_components[feature_id][instrument_id],
                )
                for feature_id in _COMPOSITE_FEATURES
            )
            scores[instrument_id] = sum(
                (value for _, value in contributions),
                Decimal(0),
            ) / Decimal(len(_COMPOSITE_FEATURES))
            component_percentiles[instrument_id] = contributions
    return _run_from_scores(
        manifest=manifest,
        kind=BaselineKind.TRANSPARENT_COMPOSITE,
        prepared=prepared,
        scores=scores,
        unscorable=unscorable,
        higher_is_better=True,
        epoch_id=epoch_id,
        component_percentiles=component_percentiles,
    )


def _random_runs(
    *,
    manifest: Mapping[str, Any],
    prepared: _PreparedInput,
    seeds: Sequence[str],
    epoch_id: str,
) -> tuple[BaselineRun, ...]:
    session_id = prepared.session_id
    runs: list[BaselineRun] = []
    for seed in seeds:
        seed_digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        scores: dict[str, Decimal] = {}
        for instrument_id in prepared.eligible_ids:
            payload = canonical_json_bytes([seed, epoch_id, session_id, instrument_id])
            digest = hashlib.sha256(payload).hexdigest()
            scores[instrument_id] = Decimal(int(digest, 16))
        runs.append(
            _run_from_scores(
                manifest=manifest,
                kind=BaselineKind.RANDOM,
                prepared=prepared,
                scores=scores,
                unscorable={},
                higher_is_better=False,
                epoch_id=epoch_id,
                seed_digest=seed_digest,
            )
        )
    return tuple(sorted(runs, key=lambda run: run.seed_digest or ""))


def evaluate_baseline_manifest(
    manifest: Mapping[str, Any],
    universe_manifest: Mapping[str, Any],
    feature_snapshots: Sequence[Mapping[str, Any]],
    *,
    seed_values: Sequence[str] | None = None,
    epoch_id: str | None = None,
    display_symbols_by_instrument_id: Mapping[str, str] | None = None,
) -> BaselineExecution:
    """Evaluate a frozen baseline against a validated universe and feature snapshots.

    No outcomes, labels, trained weights, or model objects are accepted by this API.
    Random executions return every preregistered seed run and provide no best-seed selector.
    """
    payload, kind, registry_ref = _manifest_context(manifest)
    prepared = _prepare_input(
        payload,
        registry_ref,
        universe_manifest,
        feature_snapshots,
        display_symbols_by_instrument_id,
    )
    normalized_epoch: str | None = None
    if epoch_id is not None:
        if not isinstance(epoch_id, str) or not _UUID7.fullmatch(epoch_id):
            raise BaselineError("epoch_id must be a UUIDv7")
        normalized_epoch = epoch_id

    if kind is BaselineKind.RANDOM:
        seeds = _normalise_seeds(seed_values)
        seed_hash = _seed_set_hash(seeds)
        if payload["seed_hash"] != seed_hash:
            raise BaselineError("seed set differs from the frozen baseline manifest")
        if normalized_epoch is None:
            raise BaselineError("random baseline requires an epoch_id")
        runs = _random_runs(
            manifest=payload,
            prepared=prepared,
            seeds=seeds,
            epoch_id=normalized_epoch,
        )
        return BaselineExecution(
            manifest_id=payload["id"],
            manifest_hash=payload["content_hash"],
            baseline_kind=kind,
            seed_set_hash=seed_hash,
            runs=runs,
        )

    if seed_values not in (None, (), []):
        raise BaselineError("non-random baseline evaluation cannot receive random seeds")
    if kind is BaselineKind.TRANSPARENT_COMPOSITE:
        run = _composite_run(
            manifest=payload,
            prepared=prepared,
            epoch_id=normalized_epoch,
        )
    else:
        run = _single_feature_run(
            manifest=payload,
            kind=kind,
            prepared=prepared,
            epoch_id=normalized_epoch,
        )
    return BaselineExecution(
        manifest_id=payload["id"],
        manifest_hash=payload["content_hash"],
        baseline_kind=kind,
        seed_set_hash=None,
        runs=(run,),
    )


def select_top_k(run: BaselineRun, k: int) -> tuple[BaselineRunRow, ...]:
    """Select exactly K rows, or fail explicitly if fewer than K can be scored."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise BaselineError("Top-K must be a positive integer")
    scoreable = tuple(
        row for row in run.rows if row.disposition is BaselineDisposition.SCORED
    )
    if len(scoreable) < k:
        raise InsufficientScoreableRows(
            f"Top-{k} requires {k} scoreable rows; found {len(scoreable)}"
        )
    return scoreable[:k]


def select_top_percentile(
    run: BaselineRun,
    minimum_percentile: Decimal | str | int,
) -> tuple[BaselineRunRow, ...]:
    """Select the inclusive higher-is-better percentile band; tied rows stay together."""
    threshold = as_decimal(minimum_percentile, "minimum_percentile")
    if threshold < 0 or threshold > 1:
        raise BaselineError("minimum_percentile must be in [0, 1]")
    return tuple(
        row
        for row in run.rows
        if row.disposition is BaselineDisposition.SCORED
        and row.percentile is not None
        and row.percentile >= threshold
    )


def scoreable_intersection(*runs: BaselineRun) -> tuple[str, ...]:
    """Return the secondary common-row view without changing any baseline ranking."""
    if not runs or any(not isinstance(run, BaselineRun) for run in runs):
        raise BaselineError("scoreable_intersection requires one or more baseline runs")
    first = runs[0]
    identity = (
        first.universe_manifest_id,
        first.data_bundle_id,
        first.data_bundle_hash,
        first.session_id,
        first.decision_cutoff,
        first.feature_registry_id,
        first.feature_registry_hash,
        first.feature_snapshot_refs,
        frozenset(row.instrument_id for row in first.rows),
    )
    common: set[str] | None = None
    for run in runs:
        current = (
            run.universe_manifest_id,
            run.data_bundle_id,
            run.data_bundle_hash,
            run.session_id,
            run.decision_cutoff,
            run.feature_registry_id,
            run.feature_registry_hash,
            run.feature_snapshot_refs,
            frozenset(row.instrument_id for row in run.rows),
        )
        if current != identity:
            raise BaselineError("baseline runs do not share the same universe and cutoff input")
        scoreable = {
            row.instrument_id
            for row in run.rows
            if row.disposition is BaselineDisposition.SCORED
        }
        common = scoreable if common is None else common & scoreable
    return tuple(sorted(common or ()))
