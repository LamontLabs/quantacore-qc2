"""Strict runtime validation helpers for generated QC2 v1 contracts."""

from __future__ import annotations

import hashlib
import json
import unicodedata
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
    CONTRACT_INVARIANTS,
    FAMILIES,
    IDENTITY_FIELDS,
    STATE_FIELD,
    STATE_GUARDS,
    STATE_MACHINES,
    contract_rows,
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


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
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
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractValidationError("Decimal fields must be exact decimal strings") from exc
    if not parsed.is_finite():
        raise ContractValidationError("Decimal fields must be finite")
    return format(parsed.copy_abs(), "f") if parsed.is_zero() else value


def _canonical_field_value(type_name: str, value: Any) -> Any:
    if value is None:
        return None
    if type_name.startswith("nullable_"):
        return _canonical_field_value(type_name.removeprefix("nullable_"), value)
    if type_name in _DECIMAL_TYPES:
        return _canonical_decimal(value)
    if type_name == "decimal_list":
        return [_canonical_decimal(item) for item in value]
    if type_name == "continuous_decimal_list":
        return [_canonical_decimal(item) for item in value]
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
                "value": _canonical_decimal(item["value"]),
                "uncertainty": (
                    _canonical_decimal(item["uncertainty"])
                    if item["uncertainty"] is not None
                    else None
                ),
            }
            for item in value
        ]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Encode normalized UTF-8 JSON with sorted object keys and stable separators."""
    normalized = _normalize_json(value)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
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
        paths = [item["relative_path"] for item in payload["files"]]
        if len(paths) != len(set(paths)):
            raise ContractValidationError("ArtifactManifest file paths must be unique")
        if any(
            path.startswith("/")
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
    """Hash validated canonical content with a schema-specific domain separator."""
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
    normalized.pop("content_hash", None)
    if contract_name in STATE_FIELD:
        normalized.pop(STATE_FIELD[contract_name], None)
    if contract_name == "ArtifactManifest":
        normalized.pop("detached_signature", None)
        normalized.pop("transport_hash", None)
    prefix = f"QC2-CONTENT\0{schema_name}\0".encode("utf-8")
    return hashlib.sha256(prefix + canonical_json_bytes(normalized)).hexdigest()


def verify_content_hash(contract_name: str, payload: dict[str, Any]) -> None:
    """Verify the stored hash for content-addressed immutable content."""
    expected = canonical_content_hash(contract_name, payload)
    if payload["content_hash"] != expected:
        raise ContractValidationError(
            f"{contract_name} content_hash does not match canonical immutable content"
        )


def contract_metadata(name: str) -> dict[str, Any]:
    """Return authority, state, identity, mutability, and field metadata for a contract."""
    family, schema_name = CONTRACTS[name]
    _, _, field_specs = next(row for row in contract_rows() if row[1] == name)
    owner = AUTHORITY_OVERRIDES[name]
    state_field = STATE_FIELD.get(name)
    return {
        "family": family.name,
        "schema_name": schema_name,
        "owner": owner,
        "readers": sorted(set(family.reader_roles) | {owner}),
        "identity_fields": list(IDENTITY_FIELDS.get(name, ("id",))),
        "content_addressed": name in CONTENT_ADDRESSED,
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
