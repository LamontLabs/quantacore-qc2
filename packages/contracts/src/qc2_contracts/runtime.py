"""Strict runtime validation helpers for generated QC2 v1 contracts."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .catalog import (
    AUTHORITY_OVERRIDES,
    CONTENT_ADDRESSED,
    CONTENT_HASH_ENVELOPE_FIELDS,
    CONTRACT_INVARIANTS,
    FAMILIES,
    IDENTITY_FIELDS,
    SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS,
    STATE_FIELD,
    STATE_GUARDS,
    STATE_MACHINES,
    contract_rows,
    serialization_field_metadata,
)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "v1"
CONTRACTS = {
    name: (family, f"qc2.{family.slug}.{name}.v1")
    for family in FAMILIES
    for name, _, _ in family.rows
}
SCHEMA_TO_CONTRACT = {schema_name: name for name, (_, schema_name) in CONTRACTS.items()}


class ContractValidationError(ValueError):
    """Raised when a QC2 payload or transition violates its contract."""


def _schema_for(name: str) -> dict[str, Any]:
    if name not in CONTRACTS:
        raise ContractValidationError(f"Unknown QC2 contract: {name}")
    path = SCHEMA_DIR / f"{name}.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractValidationError(f"Generated schema is missing: {path}") from exc


def _no_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractValidationError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractValidationError(f"Non-finite JSON number is forbidden: {value}")


def _reject_json_float(value: str) -> None:
    raise ContractValidationError(
        f"JSON decimal numbers are forbidden; encode exact decimals as strings: {value}"
    )


def parse_json_strict(text: str) -> Any:
    """Parse JSON without duplicate keys, non-finite values, or decimal coercion."""
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_object_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_json_float,
        )
    except ContractValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractValidationError(f"Invalid strict JSON: {exc}") from exc


_DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_DOMAIN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]{0,127}\Z")
_MAX_UUID7_TIMESTAMP = (1 << 48) - 1
_MAX_UUID7_RANDOM = (1 << 74) - 1
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ContractValidationError(
                "Canonical QC2 JSON integers must be exactly representable across platforms"
            )
        return value
    if isinstance(value, float):
        raise ContractValidationError("Canonical QC2 JSON does not permit binary floats")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractValidationError("JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ContractValidationError(
                    f"Unicode normalization creates duplicate key: {normalized_key!r}"
                )
            normalized[normalized_key] = _normalize_json(item)
        return normalized
    raise ContractValidationError(f"Unsupported canonical JSON value: {type(value).__name__}")


def _quote_canonical_string(value: str) -> str:
    try:
        normalized = unicodedata.normalize("NFC", value)
        normalized.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractValidationError(
            "Canonical QC2 JSON strings must contain valid Unicode scalar values"
        ) from exc
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _canonical_json_text(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _quote_canonical_string(value)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        ordered = sorted(
            value.items(),
            key=lambda item: item[0].encode("utf-8"),
        )
        return (
            "{"
            + ",".join(
                _quote_canonical_string(key) + ":" + _canonical_json_text(item)
                for key, item in ordered
            )
            + "}"
        )
    raise ContractValidationError(
        f"Unsupported canonical JSON value: {type(value).__name__}"
    )


def canonical_decimal_text(value: str, precision: int | None = None) -> str:
    """Validate an exact decimal string and canonicalize signed zero without rounding."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        raise ContractValidationError(
            "Canonical decimals must use plain base-10 notation without exponent or locale formatting"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractValidationError("Decimal fields must be exact decimal strings") from exc
    if not parsed.is_finite():
        raise ContractValidationError("Decimal fields must be finite")
    if precision is not None:
        if isinstance(precision, bool) or not isinstance(precision, int) or precision < 0:
            raise ContractValidationError("Decimal precision must be a nonnegative integer")
        places = len(value.partition(".")[2])
        if places != precision:
            raise ContractValidationError(
                f"Decimal value must have exactly {precision} fractional places"
            )
    return value[1:] if value.startswith("-") and parsed.is_zero() else value


def domain_separated_sha256(domain: str, payload: bytes) -> str:
    """Hash bytes with the QC2-HASH-V1 domain framing shared by all clients."""
    if not isinstance(domain, str) or not _DOMAIN_PATTERN.fullmatch(domain):
        raise ContractValidationError("Hash domain must be a lowercase ASCII identifier")
    if not isinstance(payload, bytes):
        raise ContractValidationError("Hash payload must be bytes")
    preimage = b"QC2-HASH-V1\x00" + domain.encode("ascii") + b"\x00" + payload
    return hashlib.sha256(preimage).hexdigest()


_DECIMAL_TYPES = {
    "decimal",
    "continuous_decimal",
    "positive_decimal",
    "nonnegative_decimal",
    "probability",
    "fraction",
    "score",
    "decimal_fraction",
}


def _canonical_decimal(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return canonical_decimal_text(value)


def _canonical_field_value(type_name: str, value: Any) -> Any:
    if value is None:
        return None
    if type_name.startswith("nullable_"):
        return _canonical_field_value(type_name.removeprefix("nullable_"), value)
    if type_name in _DECIMAL_TYPES:
        precision = (
            12
            if type_name in {"continuous_decimal", "probability", "fraction"}
            else 6 if type_name == "score" else None
        )
        return canonical_decimal_text(value, precision)
    if type_name == "decimal_list":
        return [_canonical_decimal(item) for item in value]
    if type_name == "continuous_decimal_list":
        return [canonical_decimal_text(item, 12) for item in value]
    if type_name == "feature_value_list":
        return [
            {
                **item,
                **(
                    {"value": _canonical_decimal(item["value"])}
                    if item.get("value") is not None
                    else {}
                ),
            }
            for item in value
        ]
    if type_name == "evidence_value_list":
        return [
            {
                **item,
                "value": canonical_decimal_text(item["value"], 12),
                "uncertainty": (
                    canonical_decimal_text(item["uncertainty"], 12)
                    if item["uncertainty"] is not None
                    else None
                ),
            }
            for item in value
        ]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Encode QC2 canonical JSON v1: NFC, UTF-8, UTF-8-key order, and compact form."""
    normalized = _normalize_json(value)
    try:
        return _canonical_json_text(normalized).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractValidationError(f"Cannot canonicalize QC2 JSON: {exc}") from exc


def validate_contract(name: str, payload: Any) -> None:
    """Validate a complete persisted object against its strict v1 schema and invariants."""
    schema = _schema_for(name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in errors
        )
        raise ContractValidationError(f"{name} v1 validation failed: {details}")
    _validate_semantics(name, payload)


def validate_json_text(name: str, text: str) -> dict[str, Any]:
    payload = parse_json_strict(text)
    validate_contract(name, payload)
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{name} must be a JSON object")
    return payload


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractValidationError("QC2 instants must be explicitly UTC")
    return parsed


def _decimal(payload: dict[str, Any], field: str) -> Decimal | None:
    value = payload.get(field)
    if value is None:
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ContractValidationError(f"{field} must be an exact decimal string") from exc
    if not result.is_finite():
        raise ContractValidationError(f"{field} must be finite")
    return result


def _validate_semantics(name: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{name} must be a JSON object")

    if name == "MarketSession":
        if not _instant(payload["opens_at"]) < _instant(payload["closes_at"]):
            raise ContractValidationError("MarketSession opens_at must precede closes_at")

    if name == "SymbolAssignment":
        effective_to = payload["effective_to"]
        if effective_to is not None and date.fromisoformat(
            payload["effective_from"]
        ) > date.fromisoformat(effective_to):
            raise ContractValidationError("SymbolAssignment effective interval is reversed")
        known_to = payload["known_to"]
        if known_to is not None and _instant(payload["known_from"]) > _instant(
            known_to
        ):
            raise ContractValidationError("SymbolAssignment known-at interval is reversed")

    if name == "DailyBar":
        opening = _decimal(payload, "open_price")
        high = _decimal(payload, "high_price")
        low = _decimal(payload, "low_price")
        close = _decimal(payload, "close_price")
        if low is None or high is None or opening is None or close is None:
            raise ContractValidationError("DailyBar OHLC values cannot be null")
        if low > min(opening, close) or high < max(opening, close) or low > high:
            raise ContractValidationError("DailyBar OHLC ordering is invalid")

    if name == "Outcome":
        mfe = _decimal(payload, "mfe")
        mae = _decimal(payload, "mae")
        proxy_mfe = _decimal(payload, "next_open_proxy_mfe")
        proxy_mae = _decimal(payload, "next_open_proxy_mae")
        if mfe is not None and mfe < 0:
            raise ContractValidationError("Outcome MFE must be nonnegative")
        if mae is not None and mae > 0:
            raise ContractValidationError("Outcome MAE must be nonpositive")
        if proxy_mfe is not None and proxy_mfe < 0:
            raise ContractValidationError("Outcome next-open-proxy MFE must be nonnegative")
        if proxy_mae is not None and proxy_mae > 0:
            raise ContractValidationError("Outcome next-open-proxy MAE must be nonpositive")
        value_fields = {
            "reference_price",
            "next_open_reference_price",
            "endpoint_return",
            "max_high_return",
            "min_low_return",
            "mfe",
            "mae",
            "max_high_price",
            "max_high_session",
            "max_high_session_offset",
            "min_low_price",
            "min_low_session",
            "min_low_session_offset",
            "opening_gap_return",
            "next_open_proxy_endpoint_return",
            "next_open_proxy_max_high_return",
            "next_open_proxy_min_low_return",
            "next_open_proxy_mfe",
            "next_open_proxy_mae",
        }
        validity = payload["field_validity"]
        seen_fields: set[str] = set()
        for item in validity:
            field = item["field_name"]
            if field not in value_fields or field in seen_fields:
                raise ContractValidationError(
                    f"Outcome field validity has an unknown or duplicate field: {field}"
                )
            seen_fields.add(field)
            value = payload[field]
            status = item["status"]
            if status == "VALID" and value is None:
                raise ContractValidationError(
                    f"Outcome {field} cannot be VALID while its value is null"
                )
            if status in {"MISSING", "UNRESOLVED", "CENSORED"}:
                if value is not None or item["reason_code"] is None:
                    raise ContractValidationError(
                        f"Outcome {field} missingness requires null plus an explicit reason"
                    )
            if status == "NOT_APPLICABLE" and value is not None:
                raise ContractValidationError(
                    f"Outcome {field} cannot be present when not applicable"
                )
        if seen_fields != value_fields:
            raise ContractValidationError(
                "Outcome requires a validity entry for every scientific measurement"
            )
        if payload["reference_price"] is None:
            raise ContractValidationError("Outcome requires its reference close price")
        for stem in ("max_high", "min_low"):
            parts = (
                payload[f"{stem}_return"],
                payload[f"{stem}_price"],
                payload[f"{stem}_session"],
                payload[f"{stem}_session_offset"],
            )
            if any(part is None for part in parts) and any(
                part is not None for part in parts
            ):
                raise ContractValidationError(
                    f"Outcome {stem} return, price, session, and offset must be jointly present or missing"
                )
        for return_field, extremum_field, derived_field, mode in (
            ("max_high_return", "max_high_return", "mfe", "max"),
            ("min_low_return", "min_low_return", "mae", "min"),
            (
                "next_open_proxy_max_high_return",
                "next_open_proxy_max_high_return",
                "next_open_proxy_mfe",
                "max",
            ),
            (
                "next_open_proxy_min_low_return",
                "next_open_proxy_min_low_return",
                "next_open_proxy_mae",
                "min",
            ),
        ):
            extremum = _decimal(payload, extremum_field)
            derived = _decimal(payload, derived_field)
            if (extremum is None) != (derived is None):
                raise ContractValidationError(
                    f"Outcome {return_field} and {derived_field} must share missingness"
                )
            if extremum is not None and derived is not None:
                expected = (
                    max(Decimal(0), extremum)
                    if mode == "max"
                    else min(Decimal(0), extremum)
                )
                if derived != expected:
                    raise ContractValidationError(
                        f"Outcome {derived_field} does not match its signed/clamped extremum"
                    )
        proxy_fields = (
            "next_open_proxy_endpoint_return",
            "next_open_proxy_max_high_return",
            "next_open_proxy_min_low_return",
            "next_open_proxy_mfe",
            "next_open_proxy_mae",
        )
        if payload["next_open_reference_price"] is None:
            if payload["next_open_bar_ref"] is not None or any(
                payload[field] is not None for field in proxy_fields
            ):
                raise ContractValidationError(
                    "Outcome next-open proxy values require a next-open bar and reference price"
                )
        elif payload["next_open_bar_ref"] is None:
            raise ContractValidationError(
                "Outcome next-open reference price requires its source bar reference"
            )

    if name == "PaperOrderIntent":
        action = payload["action_kind"]
        target = payload["source_ref"]["target_schema_name"]
        expected = {
            "OPEN_LONG": "Prediction",
            "REDUCE_LONG": "Position",
            "CLOSE_LONG": "Position",
            "CANCEL_PENDING_ENTRY": "PaperOrderIntent",
            "REPLACE_ORDER": "PaperOrderIntent",
        }[action]
        if target != CONTRACTS[expected][1]:
            raise ContractValidationError(
                f"{action} requires source_ref to target {expected}, not {target}"
            )
        if (
            payload["account_mode"] != "PAPER"
            or payload["extended_hours"] is not False
        ):
            raise ContractValidationError("F0 execution intents are paper-only and regular-session-only")

    if name == "ExecutionEpisode" and payload["account_mode"] != "PAPER":
        raise ContractValidationError("ExecutionEpisode account_mode must be PAPER")

    if name == "DatasetManifest":
        if date.fromisoformat(payload["time_start"]) > date.fromisoformat(
            payload["time_end"]
        ):
            raise ContractValidationError("DatasetManifest time range is reversed")

    if name == "ModelHeadDefinition":
        expected_precision = 6 if payload["output_kind"] == "SCORE" else 12
        if payload["output_precision"] != expected_precision:
            raise ContractValidationError(
                f"{payload['output_kind']} model heads require {expected_precision} decimal places"
            )

    if name == "ScoreManifest" and payload["score_precision"] != 6:
        raise ContractValidationError("QuantraScore uses exactly 6 decimal places")

    if name == "ArtifactManifest":
        paths = [
            unicodedata.normalize("NFC", item["relative_path"])
            for item in payload["files"]
        ]
        if len(paths) != len(set(paths)):
            raise ContractValidationError("ArtifactManifest file paths must be unique")
        if any(
            path.startswith("/")
            or re.match(r"^[A-Za-z]:", path) is not None
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            for path in paths
        ):
            raise ContractValidationError(
                "ArtifactManifest paths must be normalized relative paths"
            )

    if name == "ArtifactDependency":
        parent = payload["parent_ref"]
        dependency = payload["dependency_ref"]
        if (parent["target_schema_name"], parent["target_id"]) == (
            dependency["target_schema_name"],
            dependency["target_id"],
        ):
            raise ContractValidationError("ArtifactDependency cannot reference itself")


def _walk_references(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if {"target_schema_name", "target_id"} <= value.keys():
            yield value
            return
        for child in value.values():
            yield from _walk_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_references(child)


def _overlap(
    first_start: Any, first_end: Any, second_start: Any, second_end: Any
) -> bool:
    first_overlaps_second = first_end is None or second_start <= first_end
    second_overlaps_first = second_end is None or first_start <= second_end
    return first_overlaps_second and second_overlaps_first


def validate_contract_collection(
    objects: Iterable[tuple[str, Mapping[str, Any]]],
) -> None:
    """Validate one authority-owned snapshot, including identities and typed references."""
    entries = list(objects)
    by_schema_id: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    identities: set[tuple[str, str]] = set()
    for name, payload in entries:
        validate_contract(name, payload)
        schema_name = CONTRACTS[name][1]
        key = (schema_name, payload["id"])
        if key in by_schema_id:
            raise ContractValidationError(f"Duplicate object identity: {schema_name} {key[1]}")
        by_schema_id[key] = (name, payload)
        identity_fields = IDENTITY_FIELDS.get(name, ("id",))
        identity = json.dumps(
            [payload[field] for field in identity_fields],
            sort_keys=True,
            separators=(",", ":"),
        )
        identity_key = (name, identity)
        if identity_key in identities:
            raise ContractValidationError(f"Duplicate {name} composite identity: {identity}")
        identities.add(identity_key)

    dependency_edges: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    assignments: list[Mapping[str, Any]] = []
    for name, payload in entries:
        for reference in _walk_references(payload):
            target_name = SCHEMA_TO_CONTRACT.get(reference["target_schema_name"])
            if target_name is None:
                raise ContractValidationError(
                    f"Unknown reference target schema: {reference['target_schema_name']}"
                )
            target_key = (reference["target_schema_name"], reference["target_id"])
            target = by_schema_id.get(target_key)
            if target is None:
                raise ContractValidationError(
                    f"Unresolved foreign reference: {reference['target_schema_name']} "
                    f"{reference['target_id']}"
                )
            if target_name in CONTENT_ADDRESSED:
                expected_hash = target[1].get("content_hash")
                if reference.get("content_hash") != expected_hash:
                    raise ContractValidationError(
                        f"Foreign reference hash does not match {target_name} content"
                    )
        if name == "ArtifactDependency":
            parent = payload["parent_ref"]
            dependency = payload["dependency_ref"]
            parent_key = (parent["target_schema_name"], parent["target_id"])
            dependency_key = (
                dependency["target_schema_name"],
                dependency["target_id"],
            )
            dependency_edges[parent_key].add(dependency_key)
        if name == "ModelHeadOutput" and payload["availability"] == "AVAILABLE":
            head_ref = payload["head_ref"]
            head_key = (head_ref["target_schema_name"], head_ref["target_id"])
            head = by_schema_id[head_key][1]
            expected_precision = head["output_precision"]
            actual_precision = len(payload["output_value"].partition(".")[2])
            if "." not in payload["output_value"] or actual_precision != expected_precision:
                raise ContractValidationError(
                    "ModelHeadOutput decimal places must match its registered head precision"
                )
        if name == "SymbolAssignment":
            assignments.append(payload)

    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str]) -> None:
        if node in visiting:
            raise ContractValidationError("ArtifactDependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in dependency_edges.get(node, ()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in dependency_edges:
        visit(node)

    for index, first in enumerate(assignments):
        for second in assignments[index + 1 :]:
            if (first["symbol"], first["exchange"]) != (
                second["symbol"],
                second["exchange"],
            ):
                continue
            effective_overlap = _overlap(
                date.fromisoformat(first["effective_from"]),
                date.fromisoformat(first["effective_to"])
                if first["effective_to"]
                else None,
                date.fromisoformat(second["effective_from"]),
                date.fromisoformat(second["effective_to"])
                if second["effective_to"]
                else None,
            )
            known_overlap = _overlap(
                _instant(first["known_from"]),
                _instant(first["known_to"]) if first["known_to"] else None,
                _instant(second["known_from"]),
                _instant(second["known_to"]) if second["known_to"] else None,
            )
            if (
                effective_overlap
                and known_overlap
                and first["instrument_ref"]["target_id"]
                != second["instrument_ref"]["target_id"]
            ):
                raise ContractValidationError(
                    "Overlapping known SymbolAssignments resolve one symbol to multiple instruments"
                )


def assert_transition(contract_name: str, old_state: str, new_state: str) -> None:
    """Reject unlisted state changes; state-less and terminal objects are immutable."""
    if contract_name not in STATE_FIELD:
        raise ContractValidationError(f"{contract_name} has no mutable state field")
    allowed = STATE_MACHINES[contract_name].get(old_state, ())
    if new_state not in allowed:
        raise ContractValidationError(
            f"Invalid {contract_name} transition: {old_state} -> {new_state}"
        )


def assert_immutable_update(
    contract_name: str, before: dict[str, Any], after: dict[str, Any]
) -> None:
    """Permit only a declared, guarded state transition on an existing object."""
    validate_contract(contract_name, before)
    validate_contract(contract_name, after)
    state_field = STATE_FIELD.get(contract_name)
    if before.keys() != after.keys():
        raise ContractValidationError("Updates cannot add or remove contract fields")
    changed = {key for key in before if before[key] != after[key]}
    if not changed:
        return
    if state_field is None or changed != {state_field}:
        raise ContractValidationError(
            f"{contract_name} is immutable outside its declared state field"
        )
    assert_transition(contract_name, before[state_field], after[state_field])


def canonical_content_hash(contract_name: str, payload: dict[str, Any]) -> str:
    """Hash immutable content, separate from operational UUID/time identity."""
    if contract_name not in CONTENT_ADDRESSED:
        raise ContractValidationError(f"{contract_name} is not content-addressed")
    validate_contract(contract_name, payload)
    schema_name = CONTRACTS[contract_name][1]
    _, _, fields = next(row for row in contract_rows() if row[1] == contract_name)
    normalized = dict(payload)
    for field in fields:
        if field.name in normalized:
            normalized[field.name] = _canonical_field_value(
                field.type_name, normalized[field.name]
            )
    if contract_name == "ScientificPredictionPayload":
        normalized = {
            name: normalized[name] for name in SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS
        }
    else:
        for field_name in CONTENT_HASH_ENVELOPE_FIELDS:
            normalized.pop(field_name, None)
    if contract_name in STATE_FIELD:
        normalized.pop(STATE_FIELD[contract_name], None)
    if contract_name == "ArtifactManifest":
        normalized.pop("detached_signature", None)
        normalized.pop("transport_hash", None)
        normalized["files"] = _ordered_artifact_files(normalized["files"])
    domain = (
        f"qc2.contract-content.v1/{schema_name.lower()}/"
        f"{payload['schema_version'].lower()}"
    )
    return domain_separated_sha256(domain, canonical_json_bytes(normalized))


def _ordered_artifact_files(files: Any) -> list[dict[str, Any]]:
    if not isinstance(files, list):
        raise ContractValidationError("ArtifactManifest files must be an array")
    ordered: list[tuple[bytes, dict[str, Any]]] = []
    seen_paths: set[str] = set()
    required = {
        "relative_path",
        "length_bytes",
        "media_type",
        "schema_name",
        "schema_version",
        "sha256",
    }
    for record in files:
        if not isinstance(record, dict) or set(record) != required:
            raise ContractValidationError(
                "Artifact inventory entries must have exactly the declared file fields"
            )
        path = record["relative_path"]
        if not isinstance(path, str):
            raise ContractValidationError("Artifact inventory paths must be strings")
        normalized_path = unicodedata.normalize("NFC", path)
        if (
            normalized_path.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized_path) is not None
            or "\\" in normalized_path
            or any(part in {"", ".", ".."} for part in normalized_path.split("/"))
        ):
            raise ContractValidationError(
                "ArtifactManifest paths must be normalized relative paths"
            )
        if normalized_path in seen_paths:
            raise ContractValidationError(
                "ArtifactManifest paths must be unique after Unicode normalization"
            )
        seen_paths.add(normalized_path)
        length_bytes = record["length_bytes"]
        if (
            isinstance(length_bytes, bool)
            or not isinstance(length_bytes, int)
            or not 0 <= length_bytes <= _MAX_SAFE_INTEGER
        ):
            raise ContractValidationError(
                "Artifact inventory length_bytes must be a nonnegative safe integer"
            )
        if any(
            not isinstance(record[field], str)
            for field in ("media_type", "schema_name", "schema_version", "sha256")
        ) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ContractValidationError("Artifact inventory entry has invalid string fields")
        ordered.append((normalized_path.encode("utf-8"), record))
    ordered.sort(key=lambda item: item[0])
    return [record for _, record in ordered]


def artifact_inventory_hash(files: list[dict[str, Any]]) -> str:
    """Hash the ordered artifact file inventory, independent of archive metadata."""
    ordered_files = _ordered_artifact_files(files)
    return domain_separated_sha256(
        "qc2.artifact-inventory.v1", canonical_json_bytes(ordered_files)
    )


def scientific_payload_hash(payload: dict[str, Any]) -> str:
    """Hash only the declared scientific fields of ScientificPredictionPayload."""
    return canonical_content_hash("ScientificPredictionPayload", payload)


def verify_content_hash(contract_name: str, payload: dict[str, Any]) -> None:
    """Verify the stored hash for content-addressed immutable content."""
    if contract_name == "ArtifactManifest":
        actual_inventory_hash = artifact_inventory_hash(payload["files"])
        if payload["inventory_hash"] != actual_inventory_hash:
            raise ContractValidationError(
                "ArtifactManifest inventory_hash does not match its canonical file inventory"
            )
    expected = canonical_content_hash(contract_name, payload)
    if payload["content_hash"] != expected:
        raise ContractValidationError(
            f"{contract_name} content_hash does not match canonical immutable content"
        )


def _uuidv7_from_parts(timestamp_ms: int, random_bits: int) -> str:
    if not isinstance(timestamp_ms, int) or not 0 <= timestamp_ms <= _MAX_UUID7_TIMESTAMP:
        raise ContractValidationError("UUIDv7 timestamp must fit its 48-bit millisecond field")
    if not isinstance(random_bits, int) or not 0 <= random_bits <= _MAX_UUID7_RANDOM:
        raise ContractValidationError("UUIDv7 random component must fit 74 bits")
    uuid_bits = (timestamp_ms << 80) | (7 << 76)
    uuid_bits |= ((random_bits >> 62) & 0xFFF) << 64
    uuid_bits |= 0b10 << 62
    uuid_bits |= random_bits & ((1 << 62) - 1)
    return str(uuid.UUID(int=uuid_bits))


def new_uuidv7() -> str:
    """Create an RFC 9562 UUIDv7 with a UTC Unix-millisecond timestamp."""
    timestamp_ms = time.time_ns() // 1_000_000
    return _uuidv7_from_parts(timestamp_ms, secrets.randbits(74))


def contract_metadata(name: str) -> dict[str, Any]:
    """Return authority, state, identity, mutability, and field metadata for a contract."""
    family, schema_name = CONTRACTS[name]
    _, _, field_specs = next(row for row in contract_rows() if row[1] == name)
    owner = AUTHORITY_OVERRIDES[name]
    state_field = STATE_FIELD.get(name)
    serialization = serialization_field_metadata(name)
    return {
        "family": family.name,
        "schema_name": schema_name,
        "owner": owner,
        "readers": sorted(set(family.reader_roles) | {owner}),
        "identity_fields": list(IDENTITY_FIELDS.get(name, ("id",))),
        "content_addressed": name in CONTENT_ADDRESSED,
        **serialization,
        "state_field": state_field,
        "state_transitions": STATE_MACHINES.get(name, {}),
        "state_guard": STATE_GUARDS.get(name),
        "immutable_fields": [
            "schema_name",
            "schema_version",
            "id",
            "created_at",
            "owning_authority",
            "evidence_class",
            "environment_namespace",
            "source_refs",
            *(["content_hash"] if name in CONTENT_ADDRESSED else []),
            *(field.name for field in field_specs if field.name != state_field),
        ],
        "mutable_fields": [state_field] if state_field else [],
        "invariants": list(CONTRACT_INVARIANTS.get(name, ())),
    }
