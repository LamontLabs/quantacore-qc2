"""Immutable domain values and validation helpers for QC2 validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from qc2_contracts.runtime import ContractValidationError, canonical_decimal_text

UTC = timezone.utc
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
SLUG_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
SESSION_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
DECIMAL_QUANTUM = Decimal("0.000000000001")


class ValidationAuthorityError(ValueError):
    """A validation operation violates an evidence, integrity, or policy boundary."""


def session_date(value: str, field: str = "session_id") -> date:
    if not isinstance(value, str) or not SESSION_PATTERN.fullmatch(value):
        raise ValidationAuthorityError(f"{field} must be an ISO exchange session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationAuthorityError(f"{field} must be a real calendar date") from exc
    if parsed.isoformat() != value:
        raise ValidationAuthorityError(f"{field} must be a canonical ISO date")
    return parsed


def utc_instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationAuthorityError(f"{field} must be a UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationAuthorityError(f"{field} must be a UTC instant") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValidationAuthorityError(f"{field} must use UTC")
    return parsed.astimezone(UTC)


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValidationAuthorityError("timestamps must be timezone-aware UTC values")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def exact_decimal(value: str | Decimal, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
        raise ValidationAuthorityError(f"{field} must be an exact decimal")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(canonical_decimal_text(value))
    except (InvalidOperation, ContractValidationError) as exc:
        raise ValidationAuthorityError(f"{field} must be a finite exact decimal") from exc
    if not parsed.is_finite():
        raise ValidationAuthorityError(f"{field} must be finite")
    return parsed


def decimal_12(value: Decimal) -> str:
    if not value.is_finite():
        raise ValidationAuthorityError("metric decimals must be finite")
    rounded = value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.12f}"


def reference(
    value: Mapping[str, Any],
    expected_schema: str,
    field: str,
    *,
    require_content_hash: bool = False,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValidationAuthorityError(f"{field} must be a typed reference")
    if set(value) - {"target_schema_name", "target_id", "content_hash"}:
        raise ValidationAuthorityError(f"{field} contains an unknown reference field")
    schema = value.get("target_schema_name")
    target_id = value.get("target_id")
    content_hash = value.get("content_hash")
    if schema != expected_schema or not isinstance(target_id, str) or not target_id:
        raise ValidationAuthorityError(f"{field} must reference {expected_schema}")
    result = {"target_schema_name": schema, "target_id": target_id}
    if content_hash is not None:
        if not isinstance(content_hash, str) or not SHA256_PATTERN.fullmatch(content_hash):
            raise ValidationAuthorityError(f"{field}.content_hash must be lowercase SHA-256")
        result["content_hash"] = content_hash
    elif require_content_hash:
        raise ValidationAuthorityError(f"{field} must pin a lowercase SHA-256 content hash")
    return result


def unique_session_ids(
    values: Sequence[str],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
        or (not values and not allow_empty)
    ):
        qualifier = "an ordered session list" if allow_empty else "a non-empty ordered session list"
        raise ValidationAuthorityError(f"{field} must be {qualifier}")
    normalized = tuple(session_date(value, field).isoformat() for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValidationAuthorityError(f"{field} must not contain duplicate sessions")
    if tuple(sorted(normalized)) != normalized:
        raise ValidationAuthorityError(f"{field} must be in chronological order")
    return normalized


@dataclass(frozen=True, slots=True)
class QualificationEvidence:
    """Inputs sealed before outcome inspection; no performance or broker fields exist."""

    prediction_seal_ref: Mapping[str, Any]
    prediction_integrity: str
    denominator_status: str
    prediction_sealed_at: str
    anchor_created_at: str
    receipt_sealed_at: str
    comparator_available: bool
    protocol_conformity: bool
    checkpoint_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.prediction_integrity not in {
            "FULL_VERIFIED",
            "PARTIAL_SCAN",
            "FAILED",
            "UNAVAILABLE",
            "VALID",
            "INVALID",
        }:
            raise ValidationAuthorityError("prediction_integrity is not a contract state")
        if self.denominator_status not in {"VALID", "INSUFFICIENT", "MISSING", "UNKNOWN"}:
            raise ValidationAuthorityError("denominator_status is not a contract state")
        if not isinstance(self.comparator_available, bool):
            raise ValidationAuthorityError("comparator_available must be boolean")
        if not isinstance(self.protocol_conformity, bool):
            raise ValidationAuthorityError("protocol_conformity must be boolean")
        utc_instant(self.prediction_sealed_at, "prediction_sealed_at")
        utc_instant(self.anchor_created_at, "anchor_created_at")
        utc_instant(self.receipt_sealed_at, "receipt_sealed_at")


@dataclass(frozen=True, slots=True)
class QualificationAssessment:
    """A sealed receipt plus a derived status; the receipt itself is never rewritten."""

    state: str
    reason_codes: tuple[str, ...]
    contract: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    """A later integrity discovery appended without editing the original receipt."""

    finding_id: str
    session_id: str
    severity: str
    reason_code: str
    found_at: str


@dataclass(frozen=True, slots=True)
class SplitRow:
    row_id: str
    session_id: str
    stage: str
    dependency_end_session: str
    available_for_learning_at: str


@dataclass(frozen=True, slots=True)
class SplitValidation:
    training_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    qualification_sessions: tuple[str, ...]
    purged_sessions: tuple[str, ...]
    embargo_sessions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PredictionObservation:
    instrument_id: str
    rank: int | None
    feed_hash: str
    split_stage: str


@dataclass(frozen=True, slots=True)
class OutcomeObservation:
    instrument_id: str
    is_event: bool | None
    label_registry_hash: str
    split_stage: str


@dataclass(frozen=True, slots=True)
class MetricEstimate:
    metric_key: str
    status: str
    value: Decimal | None
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    denominator: int
    missing_count: int
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class SessionMetricBundle:
    session_id: str
    feed_hash: str
    label_registry_hash: str
    operating_precision_at_10: MetricEstimate
    comparator_precision_at_10: MetricEstimate
    paired_precision_difference: MetricEstimate
    operating_recall_at_10: MetricEstimate
    comparator_recall_at_10: MetricEstimate
    operating_coverage: MetricEstimate
    comparator_coverage: MetricEstimate
    precision_lift: MetricEstimate
