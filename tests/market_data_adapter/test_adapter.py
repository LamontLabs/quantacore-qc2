from __future__ import annotations

import hashlib
import json
import sys
import uuid
from collections import defaultdict
from copy import deepcopy
from dataclasses import MISSING, replace
from datetime import datetime
from decimal import Decimal
from itertools import count
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "market_data_adapter" / "src"))

from qc2_contracts.runtime import (  # noqa: E402
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    artifact_inventory_hash,
    verify_content_hash,
)
from qc2_market_data_adapter import (  # noqa: E402
    AlpacaMarketDataAdapter,
    ContentAddressedStore,
    HttpResponse,
    MarketDataRequest,
    RetryPolicy,
)

UTC_NOW = "2026-10-07T22:00:00Z"
BAR_SESSION = "2026-10-06"
BAR_TIMESTAMP = "2026-10-06T04:00:00Z"
ASOF_SESSION = "2026-10-07"


@pytest.fixture
def valid_contract_fixtures() -> dict[str, dict[str, Any]]:
    fixture_path = ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json"
    values = json.loads(fixture_path.read_text(encoding="utf-8"))
    return {item["contract"]: item["payload"] for item in values}


def _deterministic_uuid7(sequence: int) -> str:
    timestamp_ms = 1_800_000_000_000
    random_bits = sequence
    value = timestamp_ms << 80
    value |= 7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def _make_evidence_event(payloads: dict[str, dict[str, Any]], identifier: str) -> dict[str, Any]:
    event = deepcopy(payloads["EvidenceEvent"])
    event.update(
        id=identifier,
        created_at=UTC_NOW,
        source_refs=[],
        content_hash="0" * 64,
        installation_id="adapter-test",
        stream_id="adapter-test-stream",
        sequence=1,
        event_type="fixture_quarantine_evidence",
        actor_identity="test",
        correlation_id="adapter-quarantine-fixture",
        payload_hash="a" * 64,
        dependency_refs=[],
        previous_event_hash=None,
        event_hash="0" * 64,
        wall_clock_at=UTC_NOW,
        monotonic_generation=0,
    )
    hash_basis = {
        key: value for key, value in event.items() if key not in {"content_hash", "event_hash"}
    }
    event["event_hash"] = domain_separated_sha256(
        "qc2.evidence-event.v1",
        canonical_json_bytes(hash_basis),
    )
    event["content_hash"] = canonical_content_hash("EvidenceEvent", event)
    verify_content_hash("EvidenceEvent", event)
    return event


def make_request(
    payloads: dict[str, dict[str, Any]],
    symbols: tuple[str, ...] = ("AAA", "BBB"),
    *,
    expected_sessions: dict[str, tuple[str, ...]] | None = None,
    cutoff: str = UTC_NOW,
    evidence_class: str = "SYNTHETIC_FIXTURE",
) -> MarketDataRequest:
    next_input_id = count(1)
    def new_id() -> str:
        return _deterministic_uuid7(next(next_input_id))

    event = _make_evidence_event(payloads, new_id())

    calendar = deepcopy(payloads["CalendarManifest"])
    calendar.update(
        id=new_id(),
        created_at=UTC_NOW,
        source_refs=[],
        content_hash="0" * 64,
        valid_from="2026-10-05",
        valid_through=ASOF_SESSION,
        sessions=["2026-10-05", BAR_SESSION, ASOF_SESSION],
    )
    calendar["content_hash"] = canonical_content_hash("CalendarManifest", calendar)
    verify_content_hash("CalendarManifest", calendar)

    instruments = []
    assignments = []
    for symbol in symbols:
        instrument = deepcopy(payloads["Instrument"])
        instrument.update(
            id=new_id(),
            created_at=UTC_NOW,
            stable_instrument_key=f"test-instrument-{symbol.lower()}",
            first_known_at="2020-01-01T00:00:00Z",
            identity_status="VERIFIED",
        )
        instruments.append(instrument)

        assignment = deepcopy(payloads["SymbolAssignment"])
        assignment.update(
            id=new_id(),
            created_at=UTC_NOW,
            instrument_ref={
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": instrument["id"],
            },
            symbol=symbol,
            exchange="NASDAQ",
            currency="USD",
            effective_from="2020-01-01",
            effective_to=None,
            known_from="2026-10-05T20:00:00Z",
            known_to=None,
            source_evidence_ref={
                "target_schema_name": "qc2.integrity_build.EvidenceEvent.v1",
                "target_id": event["id"],
                "content_hash": event["content_hash"],
            },
            mapping_confidence="0.990000000000",
        )
        assignments.append(assignment)

    census = deepcopy(payloads["CandidateCensus"])
    instrument_refs = [
        {
            "target_schema_name": "qc2.identity_market.Instrument.v1",
            "target_id": item["id"],
        }
        for item in instruments
    ]
    census.update(
        id=new_id(),
        created_at=UTC_NOW,
        session_id=ASOF_SESSION,
        instrument_refs=instrument_refs,
        cutoff=cutoff,
        source_manifest_refs=[],
        membership_hash=hashlib.sha256(canonical_json_bytes(instrument_refs)).hexdigest(),
    )

    semantics = deepcopy(payloads["BarSemanticsManifest"])
    semantics.update(
        id=new_id(),
        created_at=UTC_NOW,
        provider="alpaca",
        feed="SIP",
        timeframe="1DAY",
        interval_timezone="America/New_York",
        field_meanings=[
            "Daily OHLC is not an official auction execution; volume can include extended-hours trade conditions."
        ],
        revision_policy="Preserve each raw response; later provider revisions remain separately observable.",
        finalization_rule=(
            "Finalize only after the last interval affecting every included field has ended "
            "and the supplied session deadline has passed."
        ),
        tested_at=UTC_NOW,
    )

    sessions_by_symbol = expected_sessions or {
        symbol: (BAR_SESSION,) for symbol in symbols
    }
    history_sessions = [
        session for values in sessions_by_symbol.values() for session in values
    ]
    history_start, history_end = min(history_sessions), max(history_sessions)
    finalization_deadlines = {
        session: f"{session}T21:00:00Z"
        for session in sorted(set(history_sessions))
    }
    source_objects = [
        ("CalendarManifest", calendar),
        ("CandidateCensus", census),
        ("BarSemanticsManifest", semantics),
        *(("Instrument", item) for item in instruments),
        *(("SymbolAssignment", item) for item in assignments),
        ("EvidenceEvent", event),
    ]
    return MarketDataRequest(
        provider="alpaca",
        feed="SIP",
        adjustment="RAW",
        timeframe="1DAY",
        currency="USD",
        asof=ASOF_SESSION,
        start=history_start,
        end=history_end,
        action_process_start="2026-10-05",
        action_process_end=ASOF_SESSION,
        cutoff=cutoff,
        session_deadline_at="2026-10-07T23:00:00Z",
        page_limit=100,
        calendar_manifest=calendar,
        candidate_census=census,
        bar_semantics_manifest=semantics,
        instrument_records=tuple(instruments),
        symbol_assignments=tuple(assignments),
        expected_sessions_by_symbol=sessions_by_symbol,
        finalization_deadlines=finalization_deadlines,
        retry_policy=RetryPolicy(
            maximum_attempts=3,
            maximum_total_wait_seconds=Decimal("30"),
            fallback_initial_delay_seconds=Decimal("1"),
            fallback_maximum_delay_seconds=Decimal("4"),
            maximum_pages=10,
        ),
        mapping_policy="ALPACA_ASOF",
        evidence_class=evidence_class,
        environment_namespace="test",
        quarantine_evidence_ref={
            "target_schema_name": "qc2.integrity_build.EvidenceEvent.v1",
            "target_id": event["id"],
            "content_hash": event["content_hash"],
        },
        known_action_versions=(),
        supporting_objects=tuple(source_objects),
    )


def bar(
    *,
    opening: int = 10,
    high: int = 12,
    low: int = 9,
    close: int = 11,
    volume: int = 1000,
) -> dict[str, Any]:
    return {
        "t": BAR_TIMESTAMP,
        "o": opening,
        "h": high,
        "l": low,
        "c": close,
        "v": volume,
        "n": 10,
        "vw": "10.5",
    }


def json_response(
    document: dict[str, Any],
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> HttpResponse:
    raw = body or json.dumps(
        document,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    response_headers = {
        "content-type": "application/json",
        "content-length": str(len(raw)),
    }
    response_headers.update(headers or {})
    return HttpResponse(status, response_headers, raw)


class ScriptedTransport:
    def __init__(self, scripts: dict[str, list[HttpResponse]]) -> None:
        self.scripts = defaultdict(list, {path: list(values) for path, values in scripts.items()})
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.responses: list[HttpResponse] = []

    def get(self, path: str, params: dict[str, str]) -> HttpResponse:
        self.calls.append((path, dict(params)))
        if not self.scripts[path]:
            raise AssertionError(f"Unexpected request for {path}")
        response = self.scripts[path].pop(0)
        self.responses.append(response)
        return response


def make_adapter(tmp_path: Path, transport: ScriptedTransport, now: str = UTC_NOW):
    next_output_id = count(10000)
    fixed_time = datetime.fromisoformat(now.replace("Z", "+00:00"))
    store = ContentAddressedStore(tmp_path / "artifacts")
    adapter = AlpacaMarketDataAdapter(
        transport=transport,
        store=store,
        clock=lambda: fixed_time,
        sleeper=lambda _: None,
        id_factory=lambda: _deterministic_uuid7(next(next_output_id)),
    )
    return adapter, store


def empty_actions() -> HttpResponse:
    return json_response({"corporate_actions": {}, "next_page_token": None})


def test_explicit_feed_adjustment_asof_and_multisymbol_short_pages(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures)
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response(
                    {"bars": {"AAA": [bar()]}, "next_page_token": "bars-page-2"}
                ),
                json_response(
                    {"bars": {"BBB": [bar(opening=20, high=22, low=19, close=21)]},
                     "next_page_token": None}
                ),
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, store = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "COMPLETE"
    assert result.data_bundle["coverage"] == "1.000000000000"
    assert len(result.daily_bars) == 2
    assert len(result.raw_receipts) == 3
    assert len(result.request_manifests) == 3
    assert transport.calls[0][1]["feed"] == "sip"
    assert transport.calls[0][1]["adjustment"] == "raw"
    assert transport.calls[0][1]["asof"] == request.asof
    assert "page_token" not in transport.calls[0][1]
    assert transport.calls[1][1]["page_token"] == "bars-page-2"
    assert transport.calls[2][1]["data_quality"] == "all"
    assert all(
        "apca-api-key-id" not in evidence.descriptor
        and "apca-api-secret-key" not in evidence.descriptor
        for evidence in result.request_evidence
    )
    for receipt, response in zip(result.raw_receipts, transport.responses, strict=True):
        digest = receipt["raw_sha256"]
        assert (tmp_path / "artifacts" / "raw" / f"{digest}.bin").read_bytes() == response.body
    for adjusted in result.split_adjusted_bars:
        assert adjusted.adjustment_status == "ACTION_ABSENCE_UNVERIFIED"
    assert len(result.artifact_inventory) > len(result.raw_receipts)
    for item in result.request_evidence:
        assert item.request_hash == hashlib.sha256(
            canonical_json_bytes(item.descriptor)
        ).hexdigest()
        assert item.storage_ref == f"qc2blob:sha256:{item.request_hash}"
    assert artifact_inventory_hash(list(result.artifact_inventory)) == result.data_bundle[
        "content_inventory_hash"
    ]


def test_429_retries_the_same_pinned_request_with_recorded_delay(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response(
                    {"error": "limited"},
                    status=429,
                    headers={"retry-after": "2", "x-ratelimit-remaining": "0"},
                ),
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None}),
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    sleeps: list[float] = []
    adapter, _ = make_adapter(tmp_path, transport)
    adapter._sleeper = sleeps.append

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "COMPLETE"
    assert transport.calls[0] == transport.calls[1]
    assert sleeps == [2.0]
    assert any(
        observation.status_code == 429
        and observation.retry_delay_seconds == "2"
        for observation in result.rate_limit_observations
    )


def test_403_and_missing_symbol_are_explicit_not_substituted(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"error": "forbidden"}, status=403)
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "FAILED"
    assert "alpaca_forbidden" in result.failure_codes
    assert result.daily_bars == ()
    assert result.missing_symbols == ("AAA",)


def test_short_terminal_coverage_reports_missing_symbol(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures)
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None})
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "PARTIAL"
    assert result.data_bundle["coverage"] == "0.500000000000"
    assert result.missing_symbols == ("BBB",)
    assert "requested_symbol_coverage_missing" in result.failure_codes


def test_bar_is_not_final_while_daily_volume_interval_is_pending(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    original = make_request(valid_contract_fixtures, symbols=("AAA",))
    request = replace(
        original,
        finalization_deadlines={BAR_SESSION: "2026-10-07T22:30:00Z"},
    )
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None})
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport, now=UTC_NOW)

    result = adapter.acquire(request)

    assert result.daily_bars[0]["bar_status"] == "PROVISIONAL"
    assert result.data_bundle["completeness"] == "FAILED"
    assert result.data_bundle["coverage"] == "0.000000000000"
    assert "requested_symbol_coverage_missing" in result.failure_codes
    assert result.split_adjusted_bars == ()


def test_repeated_pagination_token_fails_without_discarding_prior_page(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": "repeat"}),
                json_response({"bars": {}, "next_page_token": "repeat"}),
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert len(result.daily_bars) == 1
    assert result.data_bundle["completeness"] == "PARTIAL"
    assert "repeated_page_token" in result.failure_codes


def test_invalid_ohlc_is_an_anomaly_not_a_fabricated_quarantined_bar(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response(
                    {
                        "bars": {"AAA": [bar(opening=12, high=11, low=9, close=10)]},
                        "next_page_token": None,
                    }
                )
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.daily_bars == ()
    assert result.quarantine_cases == ()
    assert result.data_bundle["completeness"] == "FAILED"
    assert "invalid_ohlc_ordering" in result.failure_codes
    anomaly = next(
        item for item in result.data_anomalies if item.reason_code == "invalid_ohlc_ordering"
    )
    assert anomaly.raw_receipt_refs[0]["target_id"] == result.raw_receipts[0]["id"]


def test_conflicting_valid_duplicates_are_quarantined_with_both_receipts(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": "page-2"}),
                json_response(
                    {
                        "bars": {"AAA": [bar(opening=10, high=13, low=8, close=11)]},
                        "next_page_token": None,
                    }
                ),
            ],
            "/v1/corporate-actions": [empty_actions()],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert len(result.daily_bars) == 1
    assert result.daily_bars[0]["bar_status"] == "QUARANTINED"
    assert len(result.quarantine_cases) == 1
    assert result.quarantine_cases[0]["reason_code"] == "conflicting_duplicate_bar"
    assert len(result.daily_bars[0]["source_refs"]) == 2
    assert result.data_bundle["completeness"] == "FAILED"


@pytest.mark.parametrize(
    ("group", "old_rate", "new_rate", "expected_price", "expected_volume"),
    [
        ("forward_splits", 1, 2, "5", "2000"),
        ("reverse_splits", 2, 1, "20", "500"),
    ],
)
def test_split_views_transform_price_and_volume_consistently(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
    group: str,
    old_rate: int,
    new_rate: int,
    expected_price: str,
    expected_volume: str,
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    action = {
        "id": "189bd849-ab9f-4b4d-aaaa-a6d415fd976d",
        "symbol": "AAA",
        "ex_date": ASOF_SESSION,
        "process_date": ASOF_SESSION,
        "old_rate": old_rate,
        "new_rate": new_rate,
    }
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None})
            ],
            "/v1/corporate-actions": [
                json_response(
                    {
                        "corporate_actions": {group: [action]},
                        "next_page_token": None,
                    }
                )
            ],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "COMPLETE"
    assert len(result.corporate_action_versions) == 1
    adjusted = result.split_adjusted_bars[0]
    assert adjusted.open_price == expected_price
    assert adjusted.volume == expected_volume
    assert adjusted.adjustment_status == "KNOWN_ACTIONS_ONLY"
    manifest = result.adjustment_manifests[0]
    assert Decimal(manifest["price_factor"]) * Decimal(manifest["volume_factor"]) == 1


def test_future_observed_split_is_excluded_from_point_in_time_adjustment(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None})
            ],
            "/v1/corporate-actions": [
                json_response(
                    {
                        "corporate_actions": {
                            "forward_splits": [
                                {
                                    "id": "189bd849-ab9f-4b4d-aaaa-a6d415fd976d",
                                    "symbol": "AAA",
                                    "ex_date": ASOF_SESSION,
                                    "process_date": ASOF_SESSION,
                                    "old_rate": 1,
                                    "new_rate": 2,
                                }
                            ]
                        },
                        "next_page_token": None,
                    }
                )
            ],
        }
    )
    after_cutoff = "2026-10-07T22:01:00Z"
    adapter, _ = make_adapter(tmp_path, transport, now=after_cutoff)

    result = adapter.acquire(request)

    assert result.data_bundle["completeness"] == "PARTIAL"
    assert "corporate_action_version_after_cutoff" in result.failure_codes
    assert result.split_adjusted_bars[0].open_price == "10"
    assert (
        result.split_adjusted_bars[0].adjustment_status
        == "FUTURE_ACTION_VERSION_EXCLUDED"
    )
    assert not any(
        ref["target_schema_name"] == "qc2.identity_market.CorporateActionRecord.v1"
        for ref in result.data_bundle["source_refs"]
    )


def test_failed_action_acquisition_disables_split_view(
    tmp_path: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    request = make_request(valid_contract_fixtures, symbols=("AAA",))
    transport = ScriptedTransport(
        {
            "/v2/stocks/bars": [
                json_response({"bars": {"AAA": [bar()]}, "next_page_token": None})
            ],
            "/v1/corporate-actions": [
                json_response({"error": "forbidden"}, status=403)
            ],
        }
    )
    adapter, _ = make_adapter(tmp_path, transport)

    result = adapter.acquire(request)

    assert result.split_adjusted_bars == ()
    assert result.data_bundle["completeness"] == "PARTIAL"
    assert "alpaca_forbidden" in result.failure_codes
    assert "corporate_action_pagination_incomplete" in result.failure_codes


def test_feed_adjustment_and_asof_have_no_constructor_defaults() -> None:
    for name in ("feed", "adjustment", "asof"):
        field = MarketDataRequest.__dataclass_fields__[name]
        assert field.default is MISSING
        assert field.default_factory is MISSING
