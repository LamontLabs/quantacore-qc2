"""Point-in-time identity resolution and deterministic universe construction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from qc2_contracts.runtime import (
    CONTRACTS,
    ContractValidationError,
    validate_contract_collection,
)

from .errors import UniverseAuthorityError
from .models import (
    CandidateDisposition,
    EligibilityPolicy,
    FidelityAssessment,
    UniverseBuildResult,
)

Contract = Mapping[str, Any]
ContractRow = tuple[str, Contract]

INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
SYMBOL_ASSIGNMENT_SCHEMA = "qc2.identity_market.SymbolAssignment.v1"
CLASSIFICATION_SCHEMA = "qc2.identity_market.InstrumentClassification.v1"
CENSUS_SCHEMA = "qc2.identity_market.CandidateCensus.v1"
DATA_BUNDLE_SCHEMA = "qc2.identity_market.DataBundle.v1"
UNIVERSE_SCHEMA = "qc2.identity_market.UniverseManifest.v1"
SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
EVIDENCE_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
DAILY_BAR_SCHEMA = "qc2.identity_market.DailyBar.v1"

def _fail(code: str, detail: str | None = None) -> None:
    raise UniverseAuthorityError(code, detail)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise UniverseAuthorityError("date_invalid", str(value)) from exc


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        _fail("utc_instant_invalid", repr(value))
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise UniverseAuthorityError("utc_instant_invalid", value) from exc
    if parsed.utcoffset() != timedelta(0):
        _fail("utc_instant_invalid", value)
    return parsed.astimezone(timezone.utc)


def _ref(schema_name: str, object_id: str) -> dict[str, str]:
    return {"target_schema_name": schema_name, "target_id": object_id}


def _ref_key(reference: Contract) -> tuple[str, str]:
    return (str(reference["target_schema_name"]), str(reference["target_id"]))


def _ref_id(reference: Contract, expected_schema: str) -> str:
    if reference.get("target_schema_name") != expected_schema:
        _fail("typed_reference_schema_mismatch", str(reference.get("target_schema_name")))
    return str(reference["target_id"])


def _validate_collection(
    supporting_objects: Sequence[ContractRow],
    domain_objects: Sequence[ContractRow],
) -> dict[tuple[str, str], Contract]:
    """Validate a closed object graph, rejecting conflicting duplicate IDs."""
    rows: list[ContractRow] = []
    index: dict[tuple[str, str], Contract] = {}
    for name, payload in (*supporting_objects, *domain_objects):
        if name not in CONTRACTS:
            _fail("contract_name_unknown", name)
        key = (CONTRACTS[name][1], str(payload.get("id", "")))
        existing = index.get(key)
        if existing is not None:
            if dict(existing) != dict(payload):
                _fail("duplicate_contract_identity_conflict", f"{key[0]} {key[1]}")
            continue
        index[key] = payload
        rows.append((name, payload))
    try:
        validate_contract_collection(rows)
    except ContractValidationError:
        raise
    return index


def _unique_records(
    records: Sequence[Contract],
    *,
    label: str,
) -> dict[str, Contract]:
    result: dict[str, Contract] = {}
    for record in records:
        object_id = str(record.get("id", ""))
        if not object_id:
            _fail(f"{label}_id_missing")
        if object_id in result:
            _fail(f"{label}_duplicate_id", object_id)
        result[object_id] = record
    return result


def _evidence_known_at(
    record: Contract,
    object_index: Mapping[tuple[str, str], Contract],
    cutoff: datetime,
) -> bool:
    reference = record.get("source_evidence_ref")
    if not isinstance(reference, Mapping):
        return False
    evidence = object_index.get(_ref_key(reference))
    if evidence is None or evidence.get("schema_name") != EVIDENCE_SCHEMA:
        return False
    return _parse_utc(str(evidence["wall_clock_at"])) <= cutoff


def _date_in_range(start: str, end: str | None, target: date) -> bool:
    first = _parse_date(start)
    last = _parse_date(end) if end is not None else None
    return first <= target and (last is None or target <= last)


def _known_in_range(start: str, end: str | None, cutoff: datetime) -> bool:
    first = _parse_utc(start)
    last = _parse_utc(end) if end is not None else None
    return first <= cutoff and (last is None or cutoff <= last)


def _hash_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _membership_hash(instrument_ids: Sequence[str]) -> str:
    material = "qc2-candidate-membership-v1\n" + "\n".join(instrument_ids)
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def _source_manifests_known_by_cutoff(
    census: Contract,
    object_index: Mapping[tuple[str, str], Contract],
    cutoff: datetime,
) -> bool:
    for reference in census["source_manifest_refs"]:
        record = object_index.get(_ref_key(reference))
        if record is None or _parse_utc(str(record["created_at"])) > cutoff:
            return False
    return bool(census["source_manifest_refs"])


def _manifest_ref_set(references: Sequence[Contract], schema: str) -> set[str]:
    result: set[str] = set()
    for reference in references:
        result.add(_ref_id(reference, schema))
    return result


class UniverseAuthority:
    """Builds census and scientific universe contracts without provider access."""

    def __init__(self, policy: EligibilityPolicy) -> None:
        self.policy = policy

    def build_candidate_census(
        self,
        *,
        instruments: Sequence[Contract],
        session_id: str,
        cutoff: str,
        census_id: str,
        created_at: str,
        evidence_class: str,
        environment_namespace: str,
        source_manifest_refs: Sequence[Contract],
        source_refs: Sequence[Contract] = (),
        supporting_objects: Sequence[ContractRow] = (),
    ) -> dict[str, Any]:
        """Freeze the complete observed candidate set; never filter candidates silently."""
        session_date = _parse_date(session_id)
        cutoff_at = _parse_utc(cutoff)
        _parse_utc(created_at)
        if not source_manifest_refs:
            _fail("candidate_source_manifest_required")

        instrument_by_id = _unique_records(instruments, label="instrument")
        stable_keys: dict[str, str] = {}
        for instrument in instruments:
            stable_key = str(instrument.get("stable_instrument_key", ""))
            prior_id = stable_keys.get(stable_key)
            if prior_id is not None and prior_id != instrument["id"]:
                _fail("stable_instrument_key_collision", stable_key)
            stable_keys[stable_key] = str(instrument["id"])

        if len({_ref_key(ref) for ref in source_manifest_refs}) != len(source_manifest_refs):
            _fail("candidate_source_manifest_duplicate")

        ordered_ids = sorted(instrument_by_id)
        record = {
            "schema_name": CENSUS_SCHEMA,
            "schema_version": "1.0",
            "id": census_id,
            "created_at": created_at,
            "owning_authority": "instrument_universe",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [dict(ref) for ref in source_refs],
            "session_id": session_date.isoformat(),
            "instrument_refs": [_ref(INSTRUMENT_SCHEMA, object_id) for object_id in ordered_ids],
            "cutoff": cutoff,
            "source_manifest_refs": [
                dict(ref)
                for ref in sorted(
                    source_manifest_refs,
                    key=lambda item: (str(item["target_schema_name"]), str(item["target_id"])),
                )
            ],
            "membership_hash": _membership_hash(ordered_ids),
        }
        _validate_collection(
            supporting_objects,
            [("Instrument", item) for item in instruments] + [("CandidateCensus", record)],
        )
        if _parse_date(record["session_id"]) != session_date:
            _fail("candidate_session_invalid")
        if cutoff_at.utcoffset() != timedelta(0):
            _fail("candidate_cutoff_invalid")
        return record

    def build_universe_manifest(
        self,
        *,
        candidate_census: Contract,
        instruments: Sequence[Contract],
        symbol_assignments: Sequence[Contract],
        classifications: Sequence[Contract],
        data_bundle: Contract,
        daily_bars: Sequence[Contract],
        universe_id: str,
        created_at: str,
        evidence_class: str,
        environment_namespace: str,
        broker_restricted_instrument_ids: Sequence[str] = (),
        source_refs: Sequence[Contract] = (),
        supporting_objects: Sequence[ContractRow] = (),
    ) -> UniverseBuildResult:
        """Classify each candidate once, then apply broker limits separately."""
        session_id = str(candidate_census["session_id"])
        session_date = _parse_date(session_id)
        cutoff_text = str(candidate_census["cutoff"])
        cutoff = _parse_utc(cutoff_text)
        _parse_utc(created_at)

        instrument_by_id = _unique_records(instruments, label="instrument")
        _unique_records(symbol_assignments, label="symbol_assignment")
        _unique_records(classifications, label="classification")
        bar_by_id = _unique_records(daily_bars, label="daily_bar")
        candidate_ids = tuple(
            sorted(
                _ref_id(reference, INSTRUMENT_SCHEMA)
                for reference in candidate_census["instrument_refs"]
            )
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            _fail("candidate_census_duplicate_member")
        if set(candidate_ids) != set(instrument_by_id):
            _fail("candidate_instrument_inventory_mismatch")
        if str(data_bundle["census_ref"]["target_id"]) != str(candidate_census["id"]):
            _fail("data_bundle_census_mismatch")
        if data_bundle["census_ref"]["target_schema_name"] != CENSUS_SCHEMA:
            _fail("data_bundle_census_reference_invalid")

        expected_bar_ids = _manifest_ref_set(data_bundle["bar_refs"], DAILY_BAR_SCHEMA)
        if (
            expected_bar_ids != set(bar_by_id)
            or len(expected_bar_ids) != len(data_bundle["bar_refs"])
        ):
            _fail("data_bundle_bar_inventory_mismatch")

        for assignment in symbol_assignments:
            instrument_id = _ref_id(assignment["instrument_ref"], INSTRUMENT_SCHEMA)
            if instrument_id not in instrument_by_id:
                _fail("symbol_assignment_outside_census", instrument_id)
        for classification in classifications:
            instrument_id = _ref_id(classification["instrument_ref"], INSTRUMENT_SCHEMA)
            if instrument_id not in instrument_by_id:
                _fail("classification_outside_census", instrument_id)

        domain_objects: list[ContractRow] = [
            ("Instrument", item) for item in instruments
        ] + [
            ("SymbolAssignment", item) for item in symbol_assignments
        ] + [
            ("InstrumentClassification", item) for item in classifications
        ] + [
            ("DailyBar", item) for item in daily_bars
        ] + [
            ("CandidateCensus", candidate_census),
            ("DataBundle", data_bundle),
        ]
        object_index = _validate_collection(supporting_objects, domain_objects)

        assignments_by_instrument: dict[str, list[Contract]] = defaultdict(list)
        for assignment in symbol_assignments:
            assignments_by_instrument[str(assignment["instrument_ref"]["target_id"])].append(
                assignment
            )
        classifications_by_instrument: dict[str, list[Contract]] = defaultdict(list)
        for classification in classifications:
            classifications_by_instrument[
                str(classification["instrument_ref"]["target_id"])
            ].append(classification)
        bars_by_instrument: dict[str, list[Contract]] = defaultdict(list)
        for bar in daily_bars:
            bar_instrument_id = _ref_id(bar["instrument_ref"], INSTRUMENT_SCHEMA)
            if bar_instrument_id not in instrument_by_id:
                _fail("data_bundle_bar_outside_census", bar_instrument_id)
            bars_by_instrument[bar_instrument_id].append(bar)

        source_available = _source_manifests_known_by_cutoff(
            candidate_census, object_index, cutoff
        )
        dispositions: list[CandidateDisposition] = []
        for instrument_id in candidate_ids:
            disposition = self._assess_candidate(
                instrument=instrument_by_id[instrument_id],
                assignments=assignments_by_instrument[instrument_id],
                classifications=classifications_by_instrument[instrument_id],
                bars=bars_by_instrument[instrument_id],
                session_date=session_date,
                cutoff=cutoff,
                cutoff_text=cutoff_text,
                source_available=source_available,
                object_index=object_index,
                data_bundle=data_bundle,
            )
            dispositions.append(disposition)

        eligible_ids = tuple(
            item.instrument_id
            for item in dispositions
            if item.disposition == "SCIENTIFIC_ELIGIBLE"
        )
        unscorable_ids = tuple(
            item.instrument_id
            for item in dispositions
            if item.disposition == "UNSCORABLE"
        )
        excluded_ids = tuple(
            item.instrument_id
            for item in dispositions
            if item.disposition == "EXCLUDED"
        )
        if set(eligible_ids) | set(unscorable_ids) | set(excluded_ids) != set(candidate_ids):
            _fail("candidate_disposition_partition_invalid")
        if (
            set(eligible_ids) & set(unscorable_ids)
            or set(eligible_ids) & set(excluded_ids)
            or set(unscorable_ids) & set(excluded_ids)
        ):
            _fail("candidate_disposition_overlap")

        restricted = set(broker_restricted_instrument_ids)
        unknown_restricted = restricted - set(candidate_ids)
        if unknown_restricted:
            _fail("broker_restriction_outside_census", ",".join(sorted(unknown_restricted)))
        execution_restricted = tuple(sorted(restricted & set(eligible_ids)))
        execution_eligible = tuple(
            object_id for object_id in eligible_ids if object_id not in restricted
        )

        reason_counts = Counter(item.reason_code for item in dispositions)
        manifest = {
            "schema_name": UNIVERSE_SCHEMA,
            "schema_version": "1.0",
            "id": universe_id,
            "created_at": created_at,
            "owning_authority": "instrument_universe",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [dict(ref) for ref in source_refs],
            "session_id": session_id,
            "census_ref": _ref(CENSUS_SCHEMA, str(candidate_census["id"])),
            "data_bundle_ref": _ref(DATA_BUNDLE_SCHEMA, str(data_bundle["id"])),
            "eligibility_rule_hash": _hash_json(self.policy.as_record()),
            "eligible_instrument_refs": [
                _ref(INSTRUMENT_SCHEMA, object_id) for object_id in eligible_ids
            ],
            "unscorable_instrument_refs": [
                _ref(INSTRUMENT_SCHEMA, object_id) for object_id in unscorable_ids
            ],
            "reason_counts": [
                f"{reason_code}={count}" for reason_code, count in sorted(reason_counts.items())
            ],
            "cutoff": cutoff_text,
        }
        _validate_collection(supporting_objects, [*domain_objects, ("UniverseManifest", manifest)])

        limitation_codes = {
            "CANDIDATE_CENSUS_SCOPE_NOT_PROVEN_HISTORICALLY_COMPLETE",
            "LISTING_DATE_UNAVAILABLE_IN_CONTRACTS",
        }
        if data_bundle.get("completeness") != "COMPLETE":
            limitation_codes.add("DATA_BUNDLE_NOT_DECLARED_COMPLETE")
        if not source_available:
            limitation_codes.add("CENSUS_SOURCE_NOT_AVAILABLE_BY_CUTOFF")
        if any(
            item.reason_code in {
                "instrument_identity_not_known_at_cutoff",
                "symbol_assignment_not_known_at_cutoff",
                "classification_not_known_at_cutoff",
                "price_data_after_cutoff",
                "candidate_source_not_known_at_cutoff",
            }
            for item in dispositions
        ):
            limitation_codes.add("POST_CUTOFF_METADATA_OR_DATA_PRESENT")
        fidelity = FidelityAssessment(
            status=(
                "POINT_IN_TIME_SOURCE_BOUNDED"
                if "POST_CUTOFF_METADATA_OR_DATA_PRESENT" not in limitation_codes
                else "POINT_IN_TIME_LIMITED"
            ),
            point_in_time_metadata_valid=(
                "POST_CUTOFF_METADATA_OR_DATA_PRESENT" not in limitation_codes
                and source_available
            ),
            historical_population_complete=False,
            listing_age_available=False,
            limitation_codes=tuple(sorted(limitation_codes)),
        )
        return UniverseBuildResult(
            candidate_ids=candidate_ids,
            scientific_eligible_ids=eligible_ids,
            unscorable_ids=unscorable_ids,
            excluded_ids=excluded_ids,
            execution_eligible_ids=execution_eligible,
            execution_restricted_ids=execution_restricted,
            dispositions=tuple(dispositions),
            universe_manifest=manifest,
            fidelity=fidelity,
        )

    def _assess_candidate(
        self,
        *,
        instrument: Contract,
        assignments: Sequence[Contract],
        classifications: Sequence[Contract],
        bars: Sequence[Contract],
        session_date: date,
        cutoff: datetime,
        cutoff_text: str,
        source_available: bool,
        object_index: Mapping[tuple[str, str], Contract],
        data_bundle: Contract,
    ) -> CandidateDisposition:
        instrument_id = str(instrument["id"])

        def decision(
            disposition: str,
            reason_code: str,
            *,
            assignment: Contract | None = None,
            classification: Contract | None = None,
            bar: Contract | None = None,
        ) -> CandidateDisposition:
            return CandidateDisposition(
                instrument_id=instrument_id,
                disposition=disposition,
                reason_code=reason_code,
                decision_at=cutoff_text,
                symbol_assignment_id=str(assignment["id"]) if assignment else None,
                classification_id=str(classification["id"]) if classification else None,
                price_bar_id=str(bar["id"]) if bar else None,
            )

        if not source_available:
            return decision("UNSCORABLE", "candidate_source_not_known_at_cutoff")
        if _parse_utc(str(instrument["first_known_at"])) > cutoff:
            return decision("UNSCORABLE", "instrument_identity_not_known_at_cutoff")
        if instrument["identity_status"] == "RETIRED":
            return decision("EXCLUDED", "instrument_identity_retired")
        if instrument["identity_status"] != "VERIFIED":
            return decision("UNSCORABLE", "instrument_identity_unresolved")

        effective_assignments = [
            item
            for item in assignments
            if _date_in_range(
                str(item["effective_from"]),
                item.get("effective_to"),
                session_date,
            )
        ]
        known_assignments = [
            item
            for item in assignments
            if _known_in_range(str(item["known_from"]), item.get("known_to"), cutoff)
            and _evidence_known_at(item, object_index, cutoff)
        ]
        historically_known_assignments = [
            item
            for item in assignments
            if _parse_utc(str(item["known_from"])) <= cutoff
            and _evidence_known_at(item, object_index, cutoff)
        ]
        active_assignments = [
            item for item in effective_assignments if item in known_assignments
        ]
        if len(active_assignments) > 1:
            return decision("UNSCORABLE", "symbol_assignment_ambiguous")
        if not active_assignments:
            if effective_assignments:
                return decision("UNSCORABLE", "symbol_assignment_not_known_at_cutoff")
            if historically_known_assignments:
                return decision("EXCLUDED", "symbol_not_effective_for_session")
            if not assignments:
                return decision("UNSCORABLE", "symbol_assignment_missing")
            return decision("UNSCORABLE", "symbol_assignment_not_known_at_cutoff")
        assignment = active_assignments[0]
        try:
            confidence = Decimal(str(assignment["mapping_confidence"]))
        except InvalidOperation:
            return decision(
                "UNSCORABLE", "symbol_mapping_confidence_invalid", assignment=assignment
            )
        if confidence != Decimal(self.policy.required_mapping_confidence):
            return decision("UNSCORABLE", "symbol_mapping_uncertain", assignment=assignment)
        if not str(assignment["exchange"]).strip():
            return decision("UNSCORABLE", "symbol_exchange_unavailable", assignment=assignment)
        if assignment["currency"] != self.policy.required_currency:
            return decision("EXCLUDED", "instrument_currency_not_usd", assignment=assignment)

        session_classifications = [
            item
            for item in classifications
            if _date_in_range(str(item["valid_from"]), item.get("valid_to"), session_date)
        ]
        known_classifications = [
            item
            for item in session_classifications
            if _parse_utc(str(item["created_at"])) <= cutoff
            and _evidence_known_at(item, object_index, cutoff)
        ]
        if len(known_classifications) > 1:
            return decision("UNSCORABLE", "classification_ambiguous", assignment=assignment)
        if not known_classifications:
            if session_classifications:
                return decision(
                    "UNSCORABLE",
                    "classification_not_known_at_cutoff",
                    assignment=assignment,
                    classification=session_classifications[0],
                )
            if not classifications:
                return decision(
                    "EXCLUDED", "classification_unresolved", assignment=assignment
                )
            return decision(
                "EXCLUDED", "classification_not_valid_for_session", assignment=assignment
            )
        classification = known_classifications[0]
        if not classification["verified"] or classification["classification"] == "UNKNOWN":
            return decision(
                "EXCLUDED",
                "classification_unverified_or_unknown",
                assignment=assignment,
                classification=classification,
            )
        if classification["classification"] != self.policy.required_classification:
            return decision(
                "EXCLUDED",
                "classification_outside_initial_scope",
                assignment=assignment,
                classification=classification,
            )

        if data_bundle["completeness"] == "FAILED":
            return decision(
                "UNSCORABLE",
                "data_bundle_failed",
                assignment=assignment,
                classification=classification,
            )
        if not (
            _parse_date(str(data_bundle["history_start"]))
            <= session_date
            <= _parse_date(str(data_bundle["history_end"]))
        ):
            return decision(
                "UNSCORABLE",
                "data_bundle_does_not_cover_session",
                assignment=assignment,
                classification=classification,
            )
        current_bars = [
            item
            for item in bars
            if item["session_id"] == session_date.isoformat()
            and item["feed"] == self.policy.feed
        ]
        if not current_bars:
            return decision(
                "UNSCORABLE",
                "price_data_missing_for_session",
                assignment=assignment,
                classification=classification,
            )
        if len(current_bars) > 1:
            return decision(
                "UNSCORABLE",
                "price_data_ambiguous",
                assignment=assignment,
                classification=classification,
            )
        bar = current_bars[0]
        if bar["currency"] != self.policy.required_currency:
            return decision(
                "UNSCORABLE",
                "price_data_currency_mismatch",
                assignment=assignment,
                classification=classification,
                bar=bar,
            )
        if bar["bar_status"] not in {"FINAL", "REVISED"}:
            return decision(
                "UNSCORABLE",
                "price_data_not_final",
                assignment=assignment,
                classification=classification,
                bar=bar,
            )
        if (
            _parse_utc(str(bar["observed_at"])) > cutoff
            or bar.get("finalized_at") is None
            or _parse_utc(str(bar["finalized_at"])) > cutoff
        ):
            return decision(
                "UNSCORABLE",
                "price_data_after_cutoff",
                assignment=assignment,
                classification=classification,
                bar=bar,
            )
        return decision(
            "SCIENTIFIC_ELIGIBLE",
            "scientific_eligible",
            assignment=assignment,
            classification=classification,
            bar=bar,
        )

    def validate_snapshot_chain(
        self,
        *,
        candidate_census: Contract,
        data_bundle: Contract,
        universe_manifest: Contract,
        market_snapshot: Contract,
        supporting_objects: Sequence[ContractRow] = (),
        identity_records: Sequence[Contract] = (),
        symbol_assignments: Sequence[Contract] = (),
        classifications: Sequence[Contract] = (),
        daily_bars: Sequence[Contract] = (),
    ) -> None:
        """Check the prescribed census → bundle → universe → snapshot references."""
        expected_refs = (
            (data_bundle["census_ref"], CENSUS_SCHEMA, candidate_census["id"]),
            (universe_manifest["census_ref"], CENSUS_SCHEMA, candidate_census["id"]),
            (universe_manifest["data_bundle_ref"], DATA_BUNDLE_SCHEMA, data_bundle["id"]),
            (market_snapshot["census_ref"], CENSUS_SCHEMA, candidate_census["id"]),
            (market_snapshot["data_bundle_ref"], DATA_BUNDLE_SCHEMA, data_bundle["id"]),
            (market_snapshot["universe_ref"], UNIVERSE_SCHEMA, universe_manifest["id"]),
        )
        for reference, schema_name, object_id in expected_refs:
            if (
                reference.get("target_schema_name") != schema_name
                or reference.get("target_id") != object_id
            ):
                _fail("snapshot_chain_reference_mismatch", schema_name)
        session_id = str(candidate_census["session_id"])
        if (
            str(universe_manifest["session_id"]) != session_id
            or str(market_snapshot["session_id"]) != session_id
        ):
            _fail("snapshot_chain_session_mismatch")

        snapshot_key = (SNAPSHOT_SCHEMA, str(market_snapshot["id"]))
        for name, payload in (
            ("CandidateCensus", candidate_census),
            ("DataBundle", data_bundle),
            ("UniverseManifest", universe_manifest),
        ):
            for reference in _walk_references(payload):
                if _ref_key(reference) == snapshot_key:
                    _fail("snapshot_chain_cycle", name)

        objects: list[ContractRow] = [
            ("Instrument", item) for item in identity_records
        ] + [
            ("SymbolAssignment", item) for item in symbol_assignments
        ] + [
            ("InstrumentClassification", item) for item in classifications
        ] + [
            ("DailyBar", item) for item in daily_bars
        ] + [
            ("CandidateCensus", candidate_census),
            ("DataBundle", data_bundle),
            ("UniverseManifest", universe_manifest),
            ("MarketSnapshot", market_snapshot),
        ]
        _validate_collection(supporting_objects, objects)

def _walk_references(value: Any):
    if isinstance(value, Mapping):
        if {"target_schema_name", "target_id"} <= value.keys():
            yield value
            return
        for child in value.values():
            yield from _walk_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_references(child)
