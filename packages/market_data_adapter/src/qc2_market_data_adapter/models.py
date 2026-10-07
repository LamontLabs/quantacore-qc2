"""Explicit inputs and immutable outputs for the Alpaca market-data adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

Contract = Mapping[str, Any]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded, deterministic retry and pagination limits supplied by the caller."""

    maximum_attempts: int
    maximum_total_wait_seconds: Decimal
    fallback_initial_delay_seconds: Decimal
    fallback_maximum_delay_seconds: Decimal
    maximum_pages: int


@dataclass(frozen=True)
class CorporateActionVersion:
    """Append-only action observation metadata paired with its QC2 contract."""

    provider_action_id: str
    terms_hash: str
    observed_at: str
    contract: Contract
    core_terms_hash: str
    split_new_rate: Decimal | None
    split_old_rate: Decimal | None


@dataclass(frozen=True)
class MarketDataRequest:
    """Every provider choice and point-in-time boundary is a required input."""

    provider: str
    feed: str
    adjustment: str
    timeframe: str
    currency: str
    asof: str
    start: str
    end: str
    action_process_start: str
    action_process_end: str
    cutoff: str
    session_deadline_at: str
    page_limit: int
    calendar_manifest: Contract
    candidate_census: Contract
    bar_semantics_manifest: Contract
    instrument_records: tuple[Contract, ...]
    symbol_assignments: tuple[Contract, ...]
    expected_sessions_by_symbol: Mapping[str, tuple[str, ...]]
    finalization_deadlines: Mapping[str, str]
    retry_policy: RetryPolicy
    mapping_policy: str
    evidence_class: str
    environment_namespace: str
    quarantine_evidence_ref: Contract | None
    known_action_versions: tuple[CorporateActionVersion, ...]
    supporting_objects: tuple[tuple[str, Contract], ...]


@dataclass(frozen=True)
class SanitizedRequestEvidence:
    request_ref: Contract
    request_hash: str
    storage_ref: str
    descriptor: Contract


@dataclass(frozen=True)
class RateLimitObservation:
    request_hash: str
    status_code: int
    limit: str | None
    remaining: str | None
    reset_epoch: str | None
    retry_after: str | None
    retry_delay_seconds: str | None


@dataclass(frozen=True)
class SplitAdjustedBar:
    raw_bar_ref: Contract
    adjustment_manifest_ref: Contract
    basis_session: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    adjustment_status: str


@dataclass(frozen=True)
class DataAnomaly:
    reason_code: str
    symbol: str | None
    session_id: str | None
    raw_receipt_refs: tuple[Contract, ...]
    details_hash: str


@dataclass(frozen=True)
class MarketDataResult:
    data_bundle: Contract
    artifact_inventory: tuple[Contract, ...]
    bar_semantics_manifest: Contract
    request_manifests: tuple[Contract, ...]
    raw_receipts: tuple[Contract, ...]
    daily_bars: tuple[Contract, ...]
    quarantine_cases: tuple[Contract, ...]
    corporate_action_records: tuple[Contract, ...]
    corporate_action_versions: tuple[CorporateActionVersion, ...]
    adjustment_manifests: tuple[Contract, ...]
    split_adjusted_bars: tuple[SplitAdjustedBar, ...]
    data_anomalies: tuple[DataAnomaly, ...]
    request_evidence: tuple[SanitizedRequestEvidence, ...]
    rate_limit_observations: tuple[RateLimitObservation, ...]
    missing_symbols: tuple[str, ...]
    failure_codes: tuple[str, ...]
