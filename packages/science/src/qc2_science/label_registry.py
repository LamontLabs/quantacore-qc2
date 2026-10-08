"""Versioned label definitions and production-registration guards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from qc2_contracts.runtime import (
    canonical_content_hash,
    validate_contract,
    verify_content_hash,
)

from .label_models import (
    LABEL_DEFINITION_SCHEMA,
    LABEL_REGISTRY_SCHEMA,
    LabelDefinitionSpec,
    LabelInputError,
)
from .models import (
    ContractRef,
    ProductionActivationDenied,
    as_date,
    as_utc,
    require_sha256,
)

PRIMARY_LABEL_KEY = "expansion_runner_5_session"
SUPPORTED_HORIZONS = (1, 3, 5, 10)
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_PROBABILITY_EVENTS = {"EXPANSION_RUNNER", "SESSION_MONSTER"}


@dataclass(frozen=True, slots=True)
class LabelProductionActivationGrant:
    """External evidence binding a frozen registry to calibration and owner gates."""

    registry_content_hash: str
    calibration_receipt_hash: str
    qualification_receipt_hash: str
    owner_decision_hash: str

    def __post_init__(self) -> None:
        require_sha256(self.registry_content_hash, "grant registry_content_hash")
        require_sha256(self.calibration_receipt_hash, "grant calibration_receipt_hash")
        require_sha256(self.qualification_receipt_hash, "grant qualification_receipt_hash")
        require_sha256(self.owner_decision_hash, "grant owner_decision_hash")


@dataclass(frozen=True, slots=True)
class LabelRegistryBundle:
    definitions: tuple[LabelDefinitionSpec, ...]
    definition_contracts: Mapping[str, dict[str, Any]]
    registry_contract: dict[str, Any]
    environment_namespace: str
    evidence_class: str

    @property
    def registry_ref(self) -> ContractRef:
        return ContractRef(
            LABEL_REGISTRY_SCHEMA,
            self.registry_contract["id"],
            self.registry_contract["content_hash"],
        )

    @property
    def primary_label_ref(self) -> ContractRef:
        record = self.definition_contracts[PRIMARY_LABEL_KEY]
        return ContractRef(LABEL_DEFINITION_SCHEMA, record["id"], record["content_hash"])

    def definition_ref(self, stable_key: str) -> ContractRef:
        try:
            record = self.definition_contracts[stable_key]
        except KeyError as exc:
            raise LabelInputError(f"unknown label definition: {stable_key}") from exc
        return ContractRef(LABEL_DEFINITION_SCHEMA, record["id"], record["content_hash"])


def _definition_text(horizon: int, family: str) -> tuple[str, str]:
    maturity = (
        f"Use the frozen exchange-calendar sessions t+1 through t+{horizon}; "
        "membership never comes from the next available bars and a missing or halted "
        "session never extends the horizon."
    )
    common_release = (
        "A full-horizon target is releasable only after every required horizon session, "
        "data-finalization conditions, corporate-action checks, and the label release "
        "transaction complete. An early threshold hit never releases the full label. "
        "Fractional-return outcomes and threshold comparisons use exactly 12 decimal "
        "places rounded with ROUND_HALF_EVEN; peak/trough selection uses observed "
        "prices and earliest-session tie-breaking."
    )
    if family == "expansion_runner":
        rule = (
            f"Expansion Runner(h={horizon}) iff max(H[t+1]..H[t+{horizon}])/C[t]-1 "
            ">= the frozen fractional-return threshold. No persistence or drawdown "
            "condition is currently frozen; none may be inferred."
        )
    elif family == "session_monster":
        rule = (
            f"Session Monster over h={horizon} iff any i in 1..{horizon} has "
            "H[t+i]/C[t+i-1]-1 >= the frozen fractional-return threshold. "
            "For each session retain H[t+i]/O[t+i]-1 (open-to-high) and "
            "O[t+i]/C[t+i-1]-1 (opening gap) as distinct measurements."
        )
    else:
        rule = (
            f"{family.replace('_', ' ').title()} at h={horizon} has no frozen target "
            "semantics; no binary outcome or probability target may be emitted."
        )
    if family in {"continuation", "failure", "time_to_expansion"}:
        release = (
            f"{rule} UNAVAILABLE_LABEL: target semantics are not frozen. Do not derive Failure "
            "as one minus Runner, map unknown outcomes to zero, or treat unavailable "
            "labels as negative examples."
        )
    else:
        release = (
            f"{rule} {common_release}"
            + " A null threshold means UNAVAILABLE_THRESHOLD; preserve unknown rather "
            "than outputting zero or a probability target."
        )
    return maturity, release


def build_label_definition_specs(
    thresholds: Mapping[str, Decimal | str | int] | None = None,
) -> tuple[LabelDefinitionSpec, ...]:
    """Build the primary five-session label and registered secondary horizons."""
    thresholds = dict(thresholds or {})
    allowed_keys = {
        f"{family}_{horizon}_session"
        for family in ("expansion_runner", "session_monster")
        for horizon in SUPPORTED_HORIZONS
    }
    unknown = set(thresholds) - allowed_keys
    if unknown:
        raise LabelInputError(f"thresholds supplied for unsupported labels: {sorted(unknown)}")

    specs: list[LabelDefinitionSpec] = []
    for family, target_event, price_reference in (
        (
            "expansion_runner",
            "EXPANSION_RUNNER",
            "PREDICTION_SESSION_DAILY_CLOSE",
        ),
        ("session_monster", "SESSION_MONSTER", "SPLIT_CONSISTENT_CLOSE"),
    ):
        for horizon in SUPPORTED_HORIZONS:
            key = f"{family}_{horizon}_session"
            maturity_rule, release_policy = _definition_text(horizon, family)
            specs.append(
                LabelDefinitionSpec(
                    stable_key=key,
                    target_event=target_event,
                    horizon_sessions=horizon,
                    price_reference=price_reference,
                    threshold=thresholds.get(key),
                    threshold_unit="fractional_return",
                    maturity_rule=maturity_rule,
                    release_policy=release_policy,
                )
            )

    for key, event, family in (
        ("continuation_5_session", "CONTINUATION", "continuation"),
        ("failure_5_session", "FAILURE", "failure"),
        ("time_to_expansion_5_session", "TIME_TO_EXPANSION", "time_to_expansion"),
    ):
        maturity_rule, release_policy = _definition_text(5, family)
        specs.append(
            LabelDefinitionSpec(
                stable_key=key,
                target_event=event,
                horizon_sessions=5,
                price_reference="PREDICTION_SESSION_DAILY_CLOSE",
                threshold=None,
                threshold_unit=None,
                maturity_rule=maturity_rule,
                release_policy=release_policy,
            )
        )
    return tuple(specs)


def _canonical_instant(value: datetime | str) -> str:
    return as_utc(value, "created_at").isoformat(timespec="seconds").replace("+00:00", "Z")


def _finalize_contract(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    verify_content_hash(name, payload)
    return payload


def _ref(schema_name: str, record: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": str(record["id"]),
        "content_hash": str(record["content_hash"]),
    }


def _threshold_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = f"{value:.12f}"
    if Decimal(text) != value:
        raise LabelInputError("threshold must be exactly representable at 12 decimal places")
    if text == "-0.000000000000":
        return "0.000000000000"
    return text


def _validate_ids(
    definition_ids: Mapping[str, str],
    registry_id: str,
    expected_keys: set[str],
) -> None:
    if set(definition_ids) != expected_keys:
        missing = sorted(expected_keys - set(definition_ids))
        extra = sorted(set(definition_ids) - expected_keys)
        raise LabelInputError(f"definition_ids mismatch; missing={missing}, extra={extra}")
    all_ids = [registry_id, *definition_ids.values()]
    if any(not isinstance(value, str) or not _UUID7.fullmatch(value) for value in all_ids):
        raise LabelInputError("registry and definition ids must be UUIDv7 values")
    if len(set(all_ids)) != len(all_ids):
        raise LabelInputError("registry and label definition ids must be unique")


def assert_label_registry_registrable(
    bundle: LabelRegistryBundle,
    *,
    target_environment: str,
    activation_grant: LabelProductionActivationGrant | None = None,
) -> None:
    """Deny production registration without frozen thresholds and bound external gates."""
    _validate_bundle(bundle)
    if target_environment != "production":
        return
    if bundle.evidence_class == "SYNTHETIC_FIXTURE":
        raise ProductionActivationDenied("synthetic label registries cannot be registered in production")
    unresolved = [
        spec.stable_key
        for spec in bundle.definitions
        if spec.target_event in _PROBABILITY_EVENTS and spec.threshold is None
    ]
    if unresolved:
        raise ProductionActivationDenied(
            f"production label registration has unresolved thresholds: {', '.join(unresolved)}"
        )
    if activation_grant is None:
        raise ProductionActivationDenied(
            "production label registration requires calibration, qualification, and owner evidence"
        )
    if activation_grant.registry_content_hash != bundle.registry_contract["content_hash"]:
        raise ProductionActivationDenied("activation evidence is bound to a different label registry")


def _validate_bundle(bundle: LabelRegistryBundle) -> None:
    if not isinstance(bundle, LabelRegistryBundle):
        raise LabelInputError("a materialized LabelRegistryBundle is required")
    validate_contract("LabelRegistry", bundle.registry_contract)
    verify_content_hash("LabelRegistry", bundle.registry_contract)
    specs_by_key = {spec.stable_key: spec for spec in bundle.definitions}
    records_by_key = dict(bundle.definition_contracts)
    if (
        any(not isinstance(spec, LabelDefinitionSpec) for spec in bundle.definitions)
        or len(specs_by_key) != len(bundle.definitions)
        or set(specs_by_key) != set(records_by_key)
    ):
        raise LabelInputError("label registry definitions and contracts do not match")
    canonical_specs = {
        spec.stable_key: spec for spec in build_label_definition_specs()
    }
    if set(specs_by_key) != set(canonical_specs):
        raise LabelInputError("label registry does not contain the canonical definition set")
    if (
        bundle.registry_contract["environment_namespace"] != bundle.environment_namespace
        or bundle.registry_contract["evidence_class"] != bundle.evidence_class
    ):
        raise LabelInputError("label registry bundle metadata differs from its contract")
    expected_refs = []
    for key, spec in specs_by_key.items():
        record = records_by_key[key]
        canonical = canonical_specs[key]
        if (
            spec.target_event != canonical.target_event
            or spec.horizon_sessions != canonical.horizon_sessions
            or spec.price_reference != canonical.price_reference
            or spec.threshold_unit != canonical.threshold_unit
            or spec.maturity_rule != canonical.maturity_rule
            or spec.release_policy != canonical.release_policy
        ):
            raise LabelInputError(f"label definition differs from canonical semantics: {key}")
        validate_contract("LabelDefinition", record)
        verify_content_hash("LabelDefinition", record)
        if (
            record["stable_key"] != spec.stable_key
            or record["target_event"] != spec.target_event
            or record["horizon_sessions"] != spec.horizon_sessions
            or record["price_reference"] != spec.price_reference
            or record["maturity_rule"] != spec.maturity_rule
            or record["release_policy"] != spec.release_policy
            or record["threshold"] != _threshold_text(spec.threshold)
            or record["threshold_unit"] != spec.threshold_unit
        ):
            raise LabelInputError(f"label definition contract does not match its spec: {key}")
        if (
            record["environment_namespace"] != bundle.environment_namespace
            or record["evidence_class"] != bundle.evidence_class
        ):
            raise LabelInputError(f"label definition metadata does not match its registry: {key}")
        expected_refs.append(_ref(LABEL_DEFINITION_SCHEMA, record))
    if bundle.registry_contract["definition_refs"] != expected_refs:
        raise LabelInputError("LabelRegistry definition_refs do not match its definitions")
    primary = records_by_key.get(PRIMARY_LABEL_KEY)
    if primary is None or bundle.registry_contract["primary_label_ref"] != _ref(
        LABEL_DEFINITION_SCHEMA,
        primary,
    ):
        raise LabelInputError("LabelRegistry does not point to the primary five-session label")


def materialize_label_registry(
    *,
    definition_ids: Mapping[str, str],
    registry_id: str,
    created_at: datetime | str,
    effective_from: date | str,
    environment_namespace: str = "test",
    evidence_class: str = "SYNTHETIC_FIXTURE",
    thresholds: Mapping[str, Decimal | str | int] | None = None,
    activation_grant: LabelProductionActivationGrant | None = None,
) -> LabelRegistryBundle:
    """Build immutable LabelDefinition and LabelRegistry contracts, defaulting to test-only."""
    if environment_namespace not in {"development", "test", "research", "production"}:
        raise LabelInputError("unsupported environment_namespace")
    created = _canonical_instant(created_at)
    effective = as_date(effective_from, "effective_from").isoformat()
    specs = build_label_definition_specs(thresholds)
    _validate_ids(definition_ids, registry_id, {spec.stable_key for spec in specs})

    definition_records: dict[str, dict[str, Any]] = {}
    for spec in specs:
        record = {
            "schema_name": LABEL_DEFINITION_SCHEMA,
            "schema_version": "1.0",
            "id": definition_ids[spec.stable_key],
            "created_at": created,
            "owning_authority": "label",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [],
            "stable_key": spec.stable_key,
            "version": 1,
            "horizon_sessions": spec.horizon_sessions,
            "price_reference": spec.price_reference,
            "target_event": spec.target_event,
            "maturity_rule": spec.maturity_rule,
            "release_policy": spec.release_policy,
            "threshold": _threshold_text(spec.threshold),
            "threshold_unit": spec.threshold_unit,
        }
        definition_records[spec.stable_key] = _finalize_contract("LabelDefinition", record)
        validate_contract("LabelDefinition", definition_records[spec.stable_key])

    primary_record = definition_records[PRIMARY_LABEL_KEY]
    registry_record = {
        "schema_name": LABEL_REGISTRY_SCHEMA,
        "schema_version": "1.0",
        "id": registry_id,
        "created_at": created,
        "owning_authority": "label",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "registry_version": 1,
        "definition_refs": [
            _ref(LABEL_DEFINITION_SCHEMA, definition_records[spec.stable_key])
            for spec in specs
        ],
        "primary_label_ref": _ref(LABEL_DEFINITION_SCHEMA, primary_record),
        "effective_from": effective,
    }
    registry_record = _finalize_contract("LabelRegistry", registry_record)
    validate_contract("LabelRegistry", registry_record)
    bundle = LabelRegistryBundle(
        definitions=specs,
        definition_contracts=MappingProxyType(definition_records),
        registry_contract=registry_record,
        environment_namespace=environment_namespace,
        evidence_class=evidence_class,
    )
    if environment_namespace == "production" and activation_grant is None:
        _validate_bundle(bundle)
        unresolved = [
            spec.stable_key
            for spec in bundle.definitions
            if spec.target_event in _PROBABILITY_EVENTS and spec.threshold is None
        ]
        if unresolved:
            raise ProductionActivationDenied(
                "production label registration has unresolved thresholds: "
                + ", ".join(unresolved)
            )
        return bundle
    assert_label_registry_registrable(
        bundle,
        target_environment=environment_namespace,
        activation_grant=activation_grant,
    )
    return bundle
