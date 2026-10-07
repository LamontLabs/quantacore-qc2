from __future__ import annotations

import copy
import hashlib
from decimal import Decimal
from typing import Any

import pytest
from qc2_instrument_universe import EligibilityPolicy, UniverseAuthority, UniverseAuthorityError

SESSION = "2026-10-06"
CUTOFF = "2026-10-06T21:00:00Z"
PRE_CUTOFF = "2026-10-05T20:00:00Z"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
SYMBOL_ASSIGNMENT_SCHEMA = "qc2.identity_market.SymbolAssignment.v1"
CLASSIFICATION_SCHEMA = "qc2.identity_market.InstrumentClassification.v1"
CENSUS_SCHEMA = "qc2.identity_market.CandidateCensus.v1"
DATA_BUNDLE_SCHEMA = "qc2.identity_market.DataBundle.v1"
UNIVERSE_SCHEMA = "qc2.identity_market.UniverseManifest.v1"
SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
DAILY_BAR_SCHEMA = "qc2.identity_market.DailyBar.v1"


def _id(number: int) -> str:
    return f"018f0000-0000-7000-8000-{number:012x}"


def _ref(schema_name: str, object_id: str) -> dict[str, str]:
    return {"target_schema_name": schema_name, "target_id": object_id}


def _make_instrument(
    fixtures: dict[str, dict[str, Any]],
    *,
    number: int,
    key: str,
    status: str = "VERIFIED",
    first_known_at: str = PRE_CUTOFF,
) -> dict[str, Any]:
    record = copy.deepcopy(fixtures["Instrument"])
    record.update(
        {
            "id": _id(number),
            "stable_instrument_key": key,
            "first_known_at": first_known_at,
            "identity_status": status,
        }
    )
    return record


def _make_assignment(
    fixtures: dict[str, dict[str, Any]],
    *,
    number: int,
    instrument: dict[str, Any],
    symbol: str,
    effective_from: str = "2026-10-05",
    effective_to: str | None = None,
    known_from: str = PRE_CUTOFF,
    known_to: str | None = None,
    currency: str = "USD",
    exchange: str = "NASDAQ",
    confidence: str = "1.000000000000",
) -> dict[str, Any]:
    record = copy.deepcopy(fixtures["SymbolAssignment"])
    record.update(
        {
            "id": _id(number),
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument["id"]),
            "symbol": symbol,
            "exchange": exchange,
            "currency": currency,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "known_from": known_from,
            "known_to": known_to,
            "source_evidence_ref": copy.deepcopy(
                fixtures["SymbolAssignment"]["source_evidence_ref"]
            ),
            "mapping_confidence": confidence,
        }
    )
    return record


def _make_classification(
    fixtures: dict[str, dict[str, Any]],
    *,
    number: int,
    instrument: dict[str, Any],
    classification: str = "US_COMMON_EQUITY",
    verified: bool = True,
    valid_from: str = "2026-10-05",
    valid_to: str | None = None,
    created_at: str = PRE_CUTOFF,
) -> dict[str, Any]:
    record = copy.deepcopy(fixtures["InstrumentClassification"])
    record.update(
        {
            "id": _id(number),
            "created_at": created_at,
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument["id"]),
            "classification": classification,
            "verified": verified,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "source_evidence_ref": copy.deepcopy(
                fixtures["InstrumentClassification"]["source_evidence_ref"]
            ),
        }
    )
    return record


def _make_bar(
    fixtures: dict[str, dict[str, Any]],
    *,
    number: int,
    instrument: dict[str, Any],
    session_id: str = SESSION,
    feed: str = "SIP",
    currency: str = "USD",
    status: str = "FINAL",
    observed_at: str | None = None,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    record = copy.deepcopy(fixtures["DailyBar"])
    record.update(
        {
            "id": _id(number),
            "created_at": "2026-10-06T20:10:00Z",
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument["id"]),
            "session_id": session_id,
            "feed": feed,
            "currency": currency,
            "open_price": "10.00",
            "high_price": "11.00",
            "low_price": "9.00",
            "close_price": "10.50",
            "volume": "1000",
            "observed_at": observed_at or f"{session_id}T20:00:00Z",
            "finalized_at": finalized_at or f"{session_id}T20:05:00Z",
            "bar_status": status,
        }
    )
    return record


def _build_case(
    fixtures: dict[str, dict[str, Any]],
    supporting_contracts: tuple[tuple[str, dict[str, Any]], ...],
    specs: list[dict[str, Any]],
    *,
    restricted_ids: tuple[str, ...] = (),
    policy_feed: str = "SIP",
    universe_id: str = _id(900),
    data_bundle_completeness: str | None = None,
) -> dict[str, Any]:
    authority = UniverseAuthority(EligibilityPolicy(feed=policy_feed))
    instruments: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []
    bars: list[dict[str, Any]] = []
    next_assignment = 200
    next_classification = 300
    next_bar = 400

    for index, spec in enumerate(specs):
        instrument = _make_instrument(
            fixtures,
            number=100 + index,
            key=spec.get("key", f"instrument_{index}"),
            status=spec.get("identity_status", "VERIFIED"),
            first_known_at=spec.get("first_known_at", PRE_CUTOFF),
        )
        instruments.append(instrument)

        assignment_specs = spec.get("assignments")
        if assignment_specs is None:
            assignment_specs = [
                {
                    "symbol": spec.get("symbol", f"Q{index}"),
                    "effective_from": spec.get("effective_from", "2026-10-05"),
                    "effective_to": spec.get("effective_to"),
                    "known_from": spec.get("known_from", PRE_CUTOFF),
                    "known_to": spec.get("known_to"),
                    "currency": spec.get("currency", "USD"),
                    "exchange": spec.get("exchange", "NASDAQ"),
                    "confidence": spec.get("confidence", "1.000000000000"),
                }
            ]
        for assignment_spec in assignment_specs:
            assignments.append(
                _make_assignment(
                    fixtures,
                    number=next_assignment,
                    instrument=instrument,
                    **assignment_spec,
                )
            )
            next_assignment += 1

        classification_specs = spec.get("classifications")
        if classification_specs is None:
            classification_name = spec.get("classification", "US_COMMON_EQUITY")
            classification_specs = (
                []
                if classification_name is None
                else [
                    {
                        "classification": classification_name,
                        "verified": spec.get("classification_verified", True),
                        "created_at": spec.get("classification_created_at", PRE_CUTOFF),
                    }
                ]
            )
        for classification_spec in classification_specs:
            classifications.append(
                _make_classification(
                    fixtures,
                    number=next_classification,
                    instrument=instrument,
                    **classification_spec,
                )
            )
            next_classification += 1

        if spec.get("has_bar", True):
            bars.append(
                _make_bar(
                    fixtures,
                    number=next_bar,
                    instrument=instrument,
                    **spec.get("bar", {}),
                )
            )
            next_bar += 1
        for historical_session in spec.get("historical_sessions", ()):
            bars.append(
                _make_bar(
                    fixtures,
                    number=next_bar,
                    instrument=instrument,
                    session_id=historical_session,
                    observed_at=f"{historical_session}T20:00:00Z",
                    finalized_at=f"{historical_session}T20:05:00Z",
                )
            )
            next_bar += 1

    source_ref = _ref(
        fixtures["RequestManifest"]["schema_name"],
        fixtures["RequestManifest"]["id"],
    )
    census = authority.build_candidate_census(
        instruments=instruments,
        session_id=SESSION,
        cutoff=CUTOFF,
        census_id=_id(500),
        created_at="2026-10-06T20:30:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        source_manifest_refs=[source_ref],
        supporting_objects=supporting_contracts,
    )

    bar_sessions = [str(bar["session_id"]) for bar in bars]
    bundle = copy.deepcopy(fixtures["DataBundle"])
    bundle.update(
        {
            "id": _id(501),
            "created_at": "2026-10-06T20:20:00Z",
            "census_ref": _ref(CENSUS_SCHEMA, census["id"]),
            "bar_refs": [_ref(DAILY_BAR_SCHEMA, bar["id"]) for bar in bars],
            "history_start": min(bar_sessions, default=SESSION),
            "history_end": max(bar_sessions, default=SESSION),
            "coverage": (
                format(
                    Decimal(
                        len(
                            {
                                bar["instrument_ref"]["target_id"]
                                for bar in bars
                                if bar["session_id"] == SESSION and bar["feed"] == policy_feed
                            }
                        )
                    )
                    / Decimal(max(len(instruments), 1)),
                    ".12f",
                )
            ),
            "completeness": (
                data_bundle_completeness
                if data_bundle_completeness is not None
                else (
                    "COMPLETE"
                    if all(
                    any(
                        bar["instrument_ref"]["target_id"] == instrument["id"]
                        and bar["session_id"] == SESSION
                        and bar["feed"] == policy_feed
                        for bar in bars
                    )
                    for instrument in instruments
                )
                    else "PARTIAL"
                )
            ),
            "content_inventory_hash": hashlib.sha256(
                "\n".join(sorted(str(bar["id"]) for bar in bars)).encode("ascii")
            ).hexdigest(),
        }
    )

    result = authority.build_universe_manifest(
        candidate_census=census,
        instruments=instruments,
        symbol_assignments=assignments,
        classifications=classifications,
        data_bundle=bundle,
        daily_bars=bars,
        universe_id=universe_id,
        created_at="2026-10-06T21:05:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        broker_restricted_instrument_ids=restricted_ids,
        supporting_objects=supporting_contracts,
    )
    return {
        "authority": authority,
        "census": census,
        "bundle": bundle,
        "instruments": instruments,
        "assignments": assignments,
        "classifications": classifications,
        "bars": bars,
        "result": result,
        "supporting": supporting_contracts,
    }


def _by_key(case: dict[str, Any], index: int):
    instrument_id = case["instruments"][index]["id"]
    return next(
        item for item in case["result"].dispositions if item.instrument_id == instrument_id
    )


def test_ticker_reuse_and_rename_preserve_stable_instrument_identity(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [
            {
                "key": "former_company",
                "assignments": [
                    {
                        "symbol": "REUSE",
                        "effective_from": "2026-10-05",
                        "effective_to": "2026-10-05",
                        "known_from": PRE_CUTOFF,
                        "known_to": "2026-10-06T19:59:59Z",
                    }
                ],
            },
            {
                "key": "new_company",
                "assignments": [
                    {
                        "symbol": "REUSE",
                        "effective_from": "2026-10-06",
                        "known_from": "2026-10-06T20:00:00Z",
                    }
                ],
            },
            {
                "key": "renamed_company",
                "assignments": [
                    {
                        "symbol": "OLDNAME",
                        "effective_from": "2026-10-05",
                        "effective_to": "2026-10-05",
                        "known_from": PRE_CUTOFF,
                        "known_to": "2026-10-06T19:59:59Z",
                    },
                    {
                        "symbol": "NEWNAME",
                        "effective_from": "2026-10-06",
                        "known_from": "2026-10-06T20:00:00Z",
                    },
                ],
            },
        ],
    )

    old_company = _by_key(case, 0)
    new_company = _by_key(case, 1)
    renamed_company = _by_key(case, 2)
    assert (old_company.disposition, old_company.reason_code) == (
        "EXCLUDED",
        "symbol_not_effective_for_session",
    )
    assert new_company.disposition == "SCIENTIFIC_ELIGIBLE"
    assert renamed_company.disposition == "SCIENTIFIC_ELIGIBLE"
    assert renamed_company.instrument_id == case["assignments"][3]["instrument_ref"]["target_id"]
    assert renamed_company.symbol_assignment_id == case["assignments"][3]["id"]
    assert len(set(case["result"].candidate_ids)) == 3


def test_ipo_delisting_and_ambiguous_classes_get_explicit_dispositions(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [
            {
                "key": "not_yet_listed",
                "effective_from": "2026-10-07",
                "symbol": "IPO",
            },
            {
                "key": "delisted",
                "effective_from": "2026-10-05",
                "effective_to": "2026-10-05",
                "known_to": "2026-10-06T19:59:59Z",
                "symbol": "DEAD",
            },
            {"key": "etf", "classification": "ETF", "symbol": "FUND"},
            {
                "key": "unknown_class",
                "classification": "UNKNOWN",
                "classification_verified": False,
                "symbol": "UNK",
            },
            {
                "key": "conflicting_classification",
                "classifications": [
                    {"classification": "US_COMMON_EQUITY"},
                    {"classification": "ETF"},
                ],
                "symbol": "AMB",
            },
        ],
    )

    assert _by_key(case, 0).reason_code == "symbol_not_effective_for_session"
    assert _by_key(case, 1).reason_code == "symbol_not_effective_for_session"
    assert _by_key(case, 2).reason_code == "classification_outside_initial_scope"
    assert _by_key(case, 3).reason_code == "classification_unverified_or_unknown"
    assert _by_key(case, 4).reason_code == "classification_ambiguous"
    assert all(_by_key(case, index).disposition != "SCIENTIFIC_ELIGIBLE" for index in range(5))


def test_missing_listing_age_is_not_inferred_from_observed_bar_history(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [
            {
                "key": "age_unknown",
                "symbol": "AGE",
                "historical_sessions": ("2026-01-02",),
            }
        ],
    )

    disposition = case["result"].dispositions[0]
    assert disposition.disposition == "SCIENTIFIC_ELIGIBLE"
    assert disposition.listing_age_status == "UNAVAILABLE"
    assert case["bundle"]["history_start"] == "2026-01-02"
    assert case["result"].fidelity.listing_age_available is False
    assert case["result"].fidelity.historical_population_complete is False
    assert "LISTING_DATE_UNAVAILABLE_IN_CONTRACTS" in case["result"].fidelity.limitation_codes
    assert "CANDIDATE_CENSUS_SCOPE_NOT_PROVEN_HISTORICALLY_COMPLETE" in (
        case["result"].fidelity.limitation_codes
    )


def test_candidate_partitions_and_broker_restrictions_are_separate_and_reproducible(
    valid_contract_fixtures, supporting_contracts
) -> None:
    specs = [{"key": "eligible_one", "symbol": "ONE"}, {"key": "eligible_two", "symbol": "TWO"}]
    unrestricted = _build_case(valid_contract_fixtures, supporting_contracts, specs)
    restricted_id = unrestricted["instruments"][0]["id"]
    restricted = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        specs,
        restricted_ids=(restricted_id,),
    )
    repeated = _build_case(valid_contract_fixtures, supporting_contracts, specs)

    result = unrestricted["result"]
    assert len(result.dispositions) == len(result.candidate_ids) == 2
    assert set(result.scientific_eligible_ids) | set(result.unscorable_ids) | set(
        result.excluded_ids
    ) == set(result.candidate_ids)
    assert not (set(result.scientific_eligible_ids) & set(result.unscorable_ids))
    assert not (set(result.scientific_eligible_ids) & set(result.excluded_ids))
    assert len({item.instrument_id for item in result.dispositions}) == len(result.candidate_ids)

    assert restricted["result"].scientific_eligible_ids == result.scientific_eligible_ids
    assert restricted["result"].universe_manifest == result.universe_manifest
    assert restricted["result"].execution_eligible_ids == (unrestricted["instruments"][1]["id"],)
    assert repeated["result"].universe_manifest == result.universe_manifest
    assert repeated["result"].dispositions == result.dispositions
    assert result.execution_eligible_ids == result.scientific_eligible_ids


def test_future_identity_metadata_and_nonfinal_price_data_are_unscorable(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [
            {"key": "identity_future", "first_known_at": "2026-10-06T21:01:00Z"},
            {
                "key": "classification_future",
                "classification_created_at": "2026-10-06T21:01:00Z",
            },
            {"key": "bar_future", "bar": {"finalized_at": "2026-10-06T21:01:00Z"}},
            {"key": "bar_missing", "has_bar": False},
        ],
    )

    assert _by_key(case, 0).reason_code == "instrument_identity_not_known_at_cutoff"
    assert _by_key(case, 1).reason_code == "classification_not_known_at_cutoff"
    assert _by_key(case, 2).reason_code == "price_data_after_cutoff"
    assert _by_key(case, 3).reason_code == "price_data_missing_for_session"
    assert case["result"].fidelity.status == "POINT_IN_TIME_LIMITED"


def test_uncertain_lineage_and_unselected_feed_never_fall_back(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [
            {"key": "uncertain_mapping", "confidence": "0.900000000000"},
            {"key": "other_feed_only", "bar": {"feed": "IEX"}},
        ],
        policy_feed="SIP",
    )

    assert _by_key(case, 0).reason_code == "symbol_mapping_uncertain"
    assert _by_key(case, 1).reason_code == "price_data_missing_for_session"


def test_failed_data_bundle_cannot_admit_a_candidate(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [{"key": "failed_bundle", "symbol": "FAIL"}],
        data_bundle_completeness="FAILED",
    )
    assert case["result"].unscorable_ids == (case["instruments"][0]["id"],)
    assert case["result"].dispositions[0].reason_code == "data_bundle_failed"


def test_snapshot_must_follow_the_census_bundle_universe_chain(
    valid_contract_fixtures, supporting_contracts
) -> None:
    case = _build_case(
        valid_contract_fixtures,
        supporting_contracts,
        [{"key": "chain_candidate", "symbol": "CHAIN"}],
    )
    result = case["result"]
    snapshot = copy.deepcopy(valid_contract_fixtures["MarketSnapshot"])
    snapshot.update(
        {
            "id": _id(950),
            "created_at": "2026-10-06T21:10:00Z",
            "session_id": SESSION,
            "census_ref": _ref(CENSUS_SCHEMA, case["census"]["id"]),
            "data_bundle_ref": _ref(DATA_BUNDLE_SCHEMA, case["bundle"]["id"]),
            "universe_ref": _ref(UNIVERSE_SCHEMA, result.universe_manifest["id"]),
        }
    )
    case["authority"].validate_snapshot_chain(
        candidate_census=case["census"],
        data_bundle=case["bundle"],
        universe_manifest=result.universe_manifest,
        market_snapshot=snapshot,
        supporting_objects=case["supporting"],
        identity_records=case["instruments"],
        symbol_assignments=case["assignments"],
        classifications=case["classifications"],
        daily_bars=case["bars"],
    )

    cyclic_bundle = copy.deepcopy(case["bundle"])
    cyclic_bundle["source_refs"] = [_ref(SNAPSHOT_SCHEMA, snapshot["id"])]
    with pytest.raises(UniverseAuthorityError, match="snapshot_chain_cycle"):
        case["authority"].validate_snapshot_chain(
            candidate_census=case["census"],
            data_bundle=cyclic_bundle,
            universe_manifest=result.universe_manifest,
            market_snapshot=snapshot,
            supporting_objects=case["supporting"],
            identity_records=case["instruments"],
            symbol_assignments=case["assignments"],
            classifications=case["classifications"],
            daily_bars=case["bars"],
        )
