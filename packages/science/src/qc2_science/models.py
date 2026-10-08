"""Immutable, explicit inputs for offline QC2 feature calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FeatureInputError(ValueError):
    """An input does not satisfy the feature calculation contract."""


class TemporalLeakageError(FeatureInputError):
    """An input is from after the decision cutoff or target session."""


class ProductionActivationDenied(RuntimeError):
    """A fixture or unsupported profile was offered to production."""


def require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise FeatureInputError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def as_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        raise FeatureInputError(f"{field_name} must be a session date, not datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise FeatureInputError(f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FeatureInputError(f"{field_name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise FeatureInputError(f"{field_name} must be canonical YYYY-MM-DD")
    return parsed


def as_utc(value: datetime | str, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeatureInputError(f"{field_name} must be an ISO-8601 UTC instant") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise FeatureInputError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise FeatureInputError(f"{field_name} must use UTC")
    return value.astimezone(timezone.utc)


def as_decimal(value: Decimal | str | int, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise FeatureInputError(f"{field_name} must not be a bool or binary float")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FeatureInputError(f"{field_name} must be an exact decimal") from exc
    if not parsed.is_finite():
        raise FeatureInputError(f"{field_name} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class ContractRef:
    """A typed, content-addressed reference supplied by an upstream authority."""

    target_schema_name: str
    target_id: str
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_schema_name, str) or not self.target_schema_name:
            raise FeatureInputError("reference target_schema_name is required")
        if not isinstance(self.target_id, str) or not self.target_id:
            raise FeatureInputError("reference target_id is required")
        require_sha256(self.content_hash, "reference content_hash")

    def to_payload(self) -> dict[str, str]:
        return {
            "target_schema_name": self.target_schema_name,
            "target_id": self.target_id,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class TemporalAccessEvidence:
    """Cutoff-bound, artifact-scoped receipt returned by a temporal authority."""

    receipt_hash: str
    artifact_hashes: tuple[str, ...]
    decision_cutoff: datetime | str
    artifact_available_at: datetime | str
    authorized_at: datetime | str
    operation: str = "READ_HISTORICAL_FEATURE_VECTOR"
    access_mode: str = "STRICT_POINT_IN_TIME"

    def __post_init__(self) -> None:
        require_sha256(self.receipt_hash, "temporal receipt_hash")
        hashes = tuple(sorted(self.artifact_hashes))
        if len(hashes) != 2 or len(set(hashes)) != 2:
            raise FeatureInputError("temporal evidence must bind exactly two distinct source artifacts")
        for value in hashes:
            require_sha256(value, "temporal artifact hash")
        object.__setattr__(self, "artifact_hashes", hashes)
        object.__setattr__(
            self,
            "decision_cutoff",
            as_utc(self.decision_cutoff, "temporal decision_cutoff"),
        )
        object.__setattr__(
            self,
            "artifact_available_at",
            as_utc(self.artifact_available_at, "temporal artifact_available_at"),
        )
        object.__setattr__(self, "authorized_at", as_utc(self.authorized_at, "temporal authorized_at"))
        if self.operation != "READ_HISTORICAL_FEATURE_VECTOR":
            raise FeatureInputError("unsupported temporal access operation")
        if self.access_mode != "STRICT_POINT_IN_TIME":
            raise FeatureInputError("similarity requires strict point-in-time access")


@dataclass(frozen=True, slots=True)
class DailyFeatureBar:
    """One validated daily bar with its temporal and identity provenance."""

    session_id: date | str
    open_price: Decimal | str | int
    high_price: Decimal | str | int
    low_price: Decimal | str | int
    close_price: Decimal | str | int
    volume: Decimal | str | int | None
    known_at: datetime | str
    source_ref: ContractRef
    instrument_ref: ContractRef
    symbol_assignment_ref: ContractRef
    symbol_assignment_instrument_ref: ContractRef
    symbol_assignment_known_at: datetime | str
    symbol_assignment_effective_from: date | str
    symbol_assignment_effective_to: date | str | None
    adjustment_ref: ContractRef
    share_basis_key: str

    def __post_init__(self) -> None:
        session_id = as_date(self.session_id, "bar session_id")
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "known_at", as_utc(self.known_at, "bar known_at"))
        object.__setattr__(
            self,
            "symbol_assignment_known_at",
            as_utc(self.symbol_assignment_known_at, "symbol_assignment_known_at"),
        )
        object.__setattr__(
            self,
            "symbol_assignment_effective_from",
            as_date(self.symbol_assignment_effective_from, "symbol_assignment_effective_from"),
        )
        if self.symbol_assignment_effective_to is not None:
            object.__setattr__(
                self,
                "symbol_assignment_effective_to",
                as_date(self.symbol_assignment_effective_to, "symbol_assignment_effective_to"),
            )

        for field_name in ("open_price", "high_price", "low_price", "close_price"):
            value = as_decimal(getattr(self, field_name), field_name)
            if value <= 0:
                raise FeatureInputError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)

        if self.volume is not None:
            volume = as_decimal(self.volume, "volume")
            if volume < 0:
                raise FeatureInputError("volume must be nonnegative")
            object.__setattr__(self, "volume", volume)

        if self.low_price > min(self.open_price, self.close_price):
            raise FeatureInputError("bar low_price exceeds open_price or close_price")
        if self.high_price < max(self.open_price, self.close_price):
            raise FeatureInputError("bar high_price is below open_price or close_price")
        if self.low_price > self.high_price:
            raise FeatureInputError("bar low_price exceeds high_price")
        if not isinstance(self.share_basis_key, str) or not self.share_basis_key:
            raise FeatureInputError("share_basis_key is required")


@dataclass(frozen=True, slots=True)
class SimilarityPrototype:
    """A previously available genome summary with an external access receipt."""

    kind: str
    source_ref: ContractRef
    feature_snapshot_ref: ContractRef
    feature_snapshot_session: date | str
    event_session: date | str
    available_at: datetime | str
    registry_content_hash: str
    temporal_access_evidence: TemporalAccessEvidence
    feature_values: Mapping[str, Decimal | str | int] | tuple[tuple[str, Decimal | str | int], ...]

    def __post_init__(self) -> None:
        if self.kind not in {"RUNNER", "FAILURE"}:
            raise FeatureInputError("similarity prototype kind must be RUNNER or FAILURE")
        expected_schema = (
            "qc2.outcomes_research.RunnerGenome.v1"
            if self.kind == "RUNNER"
            else "qc2.outcomes_research.FailureGenome.v1"
        )
        if self.source_ref.target_schema_name != expected_schema:
            raise FeatureInputError("prototype kind and source reference disagree")
        if self.feature_snapshot_ref.target_schema_name != "qc2.scientific_definitions.FeatureSnapshot.v1":
            raise FeatureInputError("prototype feature_snapshot_ref must reference FeatureSnapshot")
        object.__setattr__(
            self,
            "feature_snapshot_session",
            as_date(self.feature_snapshot_session, "prototype feature_snapshot_session"),
        )
        object.__setattr__(self, "event_session", as_date(self.event_session, "prototype event_session"))
        object.__setattr__(self, "available_at", as_utc(self.available_at, "prototype available_at"))
        require_sha256(self.registry_content_hash, "prototype registry_content_hash")
        if not isinstance(self.temporal_access_evidence, TemporalAccessEvidence):
            raise FeatureInputError("similarity requires typed temporal-access evidence")
        if set(self.temporal_access_evidence.artifact_hashes) != {
            self.source_ref.content_hash,
            self.feature_snapshot_ref.content_hash,
        }:
            raise FeatureInputError("temporal evidence does not bind the prototype source artifacts")

        raw_items = (
            tuple(self.feature_values.items())
            if isinstance(self.feature_values, Mapping)
            else tuple(self.feature_values)
        )
        names: set[str] = set()
        normalized: list[tuple[str, Decimal]] = []
        for name, value in raw_items:
            if not isinstance(name, str) or not name or name in names:
                raise FeatureInputError("prototype feature keys must be unique nonempty strings")
            names.add(name)
            normalized.append((name, as_decimal(value, f"prototype feature {name}")))
        object.__setattr__(self, "feature_values", tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class FeatureInput:
    """All data required to compute one instrument/session snapshot."""

    target_session: date | str
    decision_cutoff: datetime | str
    calendar_sessions: tuple[date | str, ...]
    bars: tuple[DailyFeatureBar, ...]
    instrument_ref: ContractRef
    calendar_ref: ContractRef
    adjustment_ref: ContractRef
    instrument_known_at: datetime | str
    calendar_known_at: datetime | str
    adjustment_known_at: datetime | str
    prototypes: tuple[SimilarityPrototype, ...] = ()

    def __post_init__(self) -> None:
        target = as_date(self.target_session, "target_session")
        object.__setattr__(self, "target_session", target)
        object.__setattr__(self, "decision_cutoff", as_utc(self.decision_cutoff, "decision_cutoff"))
        for field_name in ("instrument_known_at", "calendar_known_at", "adjustment_known_at"):
            object.__setattr__(
                self,
                field_name,
                as_utc(getattr(self, field_name), field_name),
            )

        sessions = tuple(as_date(item, "calendar session") for item in self.calendar_sessions)
        if len(set(sessions)) != len(sessions):
            raise FeatureInputError("calendar_sessions contains duplicate sessions")
        sessions = tuple(sorted(sessions))
        if not sessions or sessions[-1] != target:
            raise FeatureInputError("calendar_sessions must end at target_session")
        object.__setattr__(self, "calendar_sessions", sessions)
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "prototypes", tuple(self.prototypes))
        if any(not isinstance(bar, DailyFeatureBar) for bar in self.bars):
            raise FeatureInputError("bars must contain DailyFeatureBar inputs")
        if any(not isinstance(item, SimilarityPrototype) for item in self.prototypes):
            raise FeatureInputError("prototypes must contain SimilarityPrototype inputs")

        expected = {
            "instrument_ref": "qc2.identity_market.Instrument.v1",
            "calendar_ref": "qc2.time_operation.CalendarManifest.v1",
            "adjustment_ref": "qc2.identity_market.AdjustmentManifest.v1",
        }
        for field_name, schema_name in expected.items():
            reference = getattr(self, field_name)
            if reference.target_schema_name != schema_name:
                raise FeatureInputError(f"{field_name} must reference {schema_name}")
