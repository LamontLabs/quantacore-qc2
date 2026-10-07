"""Small immutable result types for universe decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EligibilityPolicy:
    """The initial conservative rule with an explicit, non-fallback data feed."""

    feed: str
    version: str = "qc2-initial-conservative-v1"
    required_classification: str = "US_COMMON_EQUITY"
    required_currency: str = "USD"
    required_mapping_confidence: str = "1.000000000000"

    def __post_init__(self) -> None:
        if self.feed not in {"SIP", "IEX"}:
            raise ValueError("feed must be explicitly selected as SIP or IEX")
        if (
            self.required_classification != "US_COMMON_EQUITY"
            or self.required_currency != "USD"
            or self.required_mapping_confidence != "1.000000000000"
        ):
            raise ValueError("the initial conservative eligibility rule is fixed")

    def as_record(self) -> dict[str, str]:
        return {
            "version": self.version,
            "required_feed": self.feed,
            "required_classification": self.required_classification,
            "required_currency": self.required_currency,
            "required_mapping_confidence": self.required_mapping_confidence,
            "listing_age_rule": "not_applied_without_verified_listing_date",
            "price_or_liquidity_cutoffs": "none",
        }


@dataclass(frozen=True)
class CandidateDisposition:
    """Exactly one scientific disposition for a census member."""

    instrument_id: str
    disposition: str
    reason_code: str
    decision_at: str
    symbol_assignment_id: str | None = None
    classification_id: str | None = None
    price_bar_id: str | None = None
    listing_age_status: str = "UNAVAILABLE"


@dataclass(frozen=True)
class FidelityAssessment:
    """Scope limits that must travel with a universe result."""

    status: str
    point_in_time_metadata_valid: bool
    historical_population_complete: bool
    listing_age_available: bool
    limitation_codes: tuple[str, ...]


@dataclass(frozen=True)
class UniverseBuildResult:
    """Deterministic candidate partitions and the scientific manifest."""

    candidate_ids: tuple[str, ...]
    scientific_eligible_ids: tuple[str, ...]
    unscorable_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    execution_eligible_ids: tuple[str, ...]
    execution_restricted_ids: tuple[str, ...]
    dispositions: tuple[CandidateDisposition, ...]
    universe_manifest: Mapping[str, Any]
    fidelity: FidelityAssessment
