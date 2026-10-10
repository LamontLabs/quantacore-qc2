"""Deterministic reports with pinned sources, registered metrics, and amendments."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from qc2_contracts.runtime import (
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

REPORT_KINDS = frozenset(
    {
        "DAILY_RUNNER",
        "WEEKLY_LEARNING",
        "MISSED_MONSTER",
        "FALSE_MONSTER",
        "PROMOTION",
        "F0_VALIDATION",
        "INTEGRITY",
    }
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_UUIDV7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_EVIDENCE_CLASSES = {
    "SYNTHETIC_FIXTURE",
    "HISTORICAL_RECONSTRUCTED",
    "FORWARD_OPERATIONAL",
    "FORWARD_SEALED",
}


class ReportError(ValueError):
    """Raised when a report cannot be tied to valid, sufficient evidence."""


@dataclass(frozen=True)
class MetricFormula:
    """A registered, explicit aggregation for a validated MetricDefinition."""

    definition: Mapping[str, Any]
    source_schemas: tuple[str, ...]
    numerator_field: str
    denominator_field: str

    def __post_init__(self) -> None:
        validate_contract("MetricDefinition", dict(self.definition))
        if not self.source_schemas or not self.numerator_field or not self.denominator_field:
            raise ReportError("metric formula requires source schemas and field paths")


class MetricRegistry:
    def __init__(self, formulas: Sequence[MetricFormula]) -> None:
        self._by_key: dict[str, MetricFormula] = {}
        for formula in formulas:
            key = formula.definition["metric_key"]
            if key in self._by_key:
                raise ReportError(f"duplicate metric definition: {key}")
            self._by_key[key] = copy.deepcopy(formula)

    def get(self, key: str) -> MetricFormula:
        try:
            return copy.deepcopy(self._by_key[key])
        except KeyError as exc:
            raise ReportError(f"unregistered metric definition: {key}") from exc


@dataclass(frozen=True, init=False)
class ReportSource:
    """A validated source contract and the exact contract fields used as rows."""

    schema_name: str
    target_id: str
    content_hash: str
    evidence_class: str
    scope: str
    _rows_payload: bytes

    def __init__(self, contract: Mapping[str, Any], scope: str) -> None:
        payload = copy.deepcopy(dict(contract))
        schema_name = payload.get("schema_name")
        if not isinstance(schema_name, str) or not schema_name.endswith(".v1"):
            raise ReportError("source must identify a registered v1 contract")
        contract_name = schema_name.split(".")[-2]
        try:
            validate_contract(contract_name, payload)
            if "content_hash" in payload:
                verify_content_hash(contract_name, payload)
        except Exception as exc:
            raise ReportError(f"source contract is invalid: {exc}") from exc

        target_id = payload.get("id")
        if not isinstance(target_id, str) or not _UUIDV7.fullmatch(target_id):
            raise ReportError("source target ID must be a UUIDv7")
        evidence_class = payload.get("evidence_class")
        if (
            evidence_class not in _EVIDENCE_CLASSES
            or not isinstance(scope, str)
            or not scope.strip()
        ):
            raise ReportError("source evidence class and scope must be explicit")
        content_hash = payload.get("content_hash") or hashlib.sha256(
            canonical_json_bytes(payload)
        ).hexdigest()
        if not _HASH.fullmatch(content_hash):
            raise ReportError("source contract does not have a valid content hash")

        object.__setattr__(self, "schema_name", schema_name)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(self, "evidence_class", evidence_class)
        object.__setattr__(self, "scope", scope.strip())
        object.__setattr__(self, "_rows_payload", canonical_json_bytes([payload]))

    @property
    def rows(self) -> tuple[Mapping[str, Any], ...]:
        """Return detached rows so callers cannot mutate the hashed snapshot."""
        return tuple(json.loads(self._rows_payload))

    @property
    def ref(self) -> dict[str, str]:
        return {
            "target_schema_name": self.schema_name,
            "target_id": self.target_id,
            "content_hash": self.content_hash,
            "row_snapshot_hash": hashlib.sha256(
                canonical_json_bytes([dict(row) for row in self.rows])
            ).hexdigest(),
        }


def _field(row: Mapping[str, Any], path: str) -> Decimal:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ReportError(f"source row is missing registered field {path}")
        value = value[part]
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ReportError(f"registered metric field {path} is not numeric") from exc
    if not result.is_finite():
        raise ReportError(f"registered metric field {path} must be finite")
    return result


def _validate_source_refs(refs: Any, *, allow_empty: bool = False) -> None:
    if not isinstance(refs, list) or (not refs and not allow_empty):
        raise ReportError("report schema requires source references")
    for ref in refs:
        if (
            not isinstance(ref, Mapping)
            or not isinstance(ref.get("target_schema_name"), str)
            or not _UUIDV7.fullmatch(str(ref.get("target_id", "")))
            or not _HASH.fullmatch(str(ref.get("content_hash", "")))
            or not _HASH.fullmatch(str(ref.get("row_snapshot_hash", "")))
        ):
            raise ReportError("report schema contains an invalid source reference")


def _validate_generated_report(report: Mapping[str, Any]) -> None:
    if report.get("schema_name") != "qc2.reporting.GeneratedReport.v1":
        raise ReportError("report schema name is invalid")
    if (
        report.get("report_kind") not in REPORT_KINDS
        or not isinstance(report.get("report_key"), str)
        or not report["report_key"].strip()
        or not isinstance(report.get("period"), str)
        or not report["period"].strip()
        or not _UUIDV7.fullmatch(str(report.get("id", "")))
    ):
        raise ReportError("report identity or period is invalid")
    if (
        isinstance(report.get("revision"), bool)
        or not isinstance(report.get("revision"), int)
        or report["revision"] < 1
        or report.get("status") not in {"FINAL", "PROVISIONAL"}
    ):
        raise ReportError("report revision or status is invalid")
    _validate_source_refs(report.get("source_refs"))
    if not isinstance(report.get("evidence_classes"), list) or not report[
        "evidence_classes"
    ]:
        raise ReportError("report schema requires evidence classes")
    if not isinstance(report.get("metric_definitions"), Mapping):
        raise ReportError("report schema requires metric definitions")
    metrics = report.get("metrics")
    manifest = report.get("metric_source_manifest")
    if (
        not isinstance(metrics, list)
        or not metrics
        or not isinstance(manifest, list)
        or len(manifest) != len(metrics)
    ):
        raise ReportError("report schema requires matching metrics and source manifest")
    for metric, metric_manifest in zip(metrics, manifest, strict=True):
        if not isinstance(metric, Mapping) or not isinstance(metric_manifest, Mapping):
            raise ReportError("report metric entries must be objects")
        for field in ("numerator", "denominator"):
            try:
                value = Decimal(str(metric[field]))
            except (KeyError, InvalidOperation, ValueError) as exc:
                raise ReportError(f"report metric {field} is invalid") from exc
            if not value.is_finite():
                raise ReportError(f"report metric {field} must be finite")
        if not isinstance(metric.get("metric_key"), str) or not metric.get(
            "metric_definition_id"
        ):
            raise ReportError("report metric is missing its registered definition")
        _validate_source_refs(metric.get("source_refs"))
        _validate_source_refs(metric_manifest.get("source_refs"))
    limitations = report.get("scope_limitations")
    if not isinstance(limitations, list) or not limitations or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise ReportError("report schema requires explicit scope limitations")
    if not _HASH.fullmatch(str(report.get("report_hash", ""))):
        raise ReportError("report hash must be lowercase SHA-256")
    expected = hashlib.sha256(
        canonical_json_bytes({k: v for k, v in report.items() if k != "report_hash"})
    ).hexdigest()
    if expected != report["report_hash"]:
        raise ReportError("report hash does not match immutable report content")


def _validate_amendment(amendment: Mapping[str, Any]) -> None:
    required_text = ("report_key", "reason", "impact_analysis")
    if amendment.get("schema_name") != "qc2.reporting.ReportAmendment.v1":
        raise ReportError("amendment schema name is invalid")
    if any(
        not isinstance(amendment.get(key), str) or not amendment[key].strip()
        for key in required_text
    ):
        raise ReportError("amendment schema requires report key, reason, and impact")
    if (
        not isinstance(amendment.get("revision_number"), int)
        or amendment["revision_number"] < 2
        or not _HASH.fullmatch(str(amendment.get("prior_report_hash", "")))
        or not _HASH.fullmatch(str(amendment.get("corrected_report_hash", "")))
    ):
        raise ReportError("amendment revision or report hashes are invalid")
    _validate_source_refs(amendment.get("correction_refs"), allow_empty=True)
    expected = hashlib.sha256(
        canonical_json_bytes({k: v for k, v in amendment.items() if k != "amendment_hash"})
    ).hexdigest()
    if expected != amendment.get("amendment_hash"):
        raise ReportError("amendment hash does not match its immutable content")


def generate_report(
    *,
    report_kind: str,
    report_key: str,
    period: str,
    registry: MetricRegistry,
    metric_keys: Sequence[str],
    sources: Sequence[ReportSource],
    scope_limitations: Sequence[str],
) -> dict[str, Any]:
    if report_kind not in REPORT_KINDS:
        raise ReportError(f"unsupported report kind: {report_kind}")
    if not report_key.strip() or not period.strip() or not metric_keys:
        raise ReportError("report key, period, and at least one metric are required")
    if not sources:
        raise ReportError("reports require immutable source references")

    results: list[dict[str, Any]] = []
    metric_source_manifest: list[dict[str, Any]] = []
    metric_definitions: dict[str, dict[str, Any]] = {}
    limitations = set(scope_limitations)
    provisional = False
    for source in sources:
        if source.evidence_class in {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED"}:
            provisional = True
            limitations.add("NON_FORWARD_EVIDENCE_CANNOT_ESTABLISH_OPERATIONAL_PROOF")
        if source.scope == "SURVIVOR_LIMITED_RESEARCH":
            provisional = True
            limitations.add("SURVIVOR_LIMITED_RESEARCH_ONLY")
        if source.scope == "PAPER_EXECUTION":
            provisional = True
            limitations.add("PAPER_FILLS_ARE_NOT_LIVE_EXECUTION_PROOF")

    if not limitations:
        raise ReportError("scope limitations must be explicit, including an explicit none")

    for key in metric_keys:
        formula = registry.get(key)
        metric_definitions[key] = {
            "target_schema_name": formula.definition["schema_name"],
            "target_id": formula.definition["id"],
            "metric_key": key,
            "version": formula.definition["version"],
            "unit": formula.definition["unit"],
            "estimand": formula.definition["estimand"],
            "numerator_field": formula.numerator_field,
            "denominator_field": formula.denominator_field,
            "source_schemas": list(formula.source_schemas),
        }
        eligible = [s for s in sources if s.schema_name in formula.source_schemas]
        if not eligible:
            raise ReportError(f"metric {key} has no eligible source artifacts")
        numerator = Decimal(0)
        denominator = Decimal(0)
        row_count = 0
        for source in eligible:
            for row in source.rows:
                source_definition = row.get("definition_ref")
                if (
                    isinstance(source_definition, Mapping)
                    and source_definition.get("target_id") != formula.definition["id"]
                ):
                    raise ReportError(
                        f"source metric definition does not match registered metric {key}"
                    )
                numerator += _field(row, formula.numerator_field)
                denominator += _field(row, formula.denominator_field)
                row_count += 1
        if denominator == 0:
            value = None
            provisional = True
            limitations.add("ZERO_DENOMINATOR_INSUFFICIENT_EVIDENCE")
        elif formula.definition["unit"].lower() in {"ratio", "rate", "percent"}:
            value = str(numerator / denominator)
        else:
            value = str(numerator)
        results.append(
            {
                "metric_key": key,
                "metric_definition_id": formula.definition["id"],
                "numerator": str(numerator),
                "denominator": str(denominator),
                "value": value,
                "row_count": row_count,
                "source_refs": [source.ref for source in eligible],
            }
        )
        metric_source_manifest.append(
            {
                "metric_key": key,
                "metric_definition_id": formula.definition["id"],
                "numerator_field": formula.numerator_field,
                "denominator_field": formula.denominator_field,
                "source_refs": [source.ref for source in eligible],
                "recomputed_numerator": str(numerator),
                "recomputed_denominator": str(denominator),
                "source_row_count": row_count,
            }
        )

    report = {
        "schema_name": "qc2.reporting.GeneratedReport.v1",
        "id": new_uuidv7(),
        "report_key": report_key,
        "report_kind": report_kind,
        "period": period,
        "revision": 1,
        "status": "PROVISIONAL" if provisional else "FINAL",
        "source_refs": [
            source.ref
            for source in sorted(sources, key=lambda item: (item.schema_name, item.target_id))
        ],
        "evidence_classes": sorted({source.evidence_class for source in sources}),
        "metric_definitions": metric_definitions,
        "metric_source_manifest": metric_source_manifest,
        "metrics": results,
        "scope_limitations": sorted(limitations),
    }
    report["report_hash"] = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    _validate_generated_report(report)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render only registered values and declared limitations; no generated claims."""
    lines = [
        f"# {report['report_kind'].replace('_', ' ').title()} Report",
        "",
        f"- Report key: `{report['report_key']}`",
        f"- Period: `{report['period']}`",
        f"- Revision: {report['revision']}",
        f"- Status: **{report['status']}**",
        f"- Report hash: `{report['report_hash']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Numerator | Denominator | Rows | Definition |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for metric in report["metrics"]:
        lines.append(
            f"| `{metric['metric_key']}` | {metric['value'] if metric['value'] is not None else 'insufficient evidence'} "
            f"| {metric['numerator']} | {metric['denominator']} | {metric['row_count']} "
            f"| `{metric['metric_definition_id']}` |"
        )
    lines.extend(["", "## Scope limitations", ""])
    lines.extend(f"- {item}" for item in report["scope_limitations"])
    lines.extend(["", "## Immutable sources", ""])
    lines.extend(
        f"- `{ref['target_schema_name']}` / `{ref['target_id']}` — "
        f"artifact `{ref['content_hash']}`, rows `{ref['row_snapshot_hash']}`"
        for ref in report["source_refs"]
    )
    lines.append("")
    return "\n".join(lines)


class ReportLedger:
    """Append-only report storage. Corrections append a new revision and amendment."""

    def __init__(self) -> None:
        self._reports: dict[str, list[bytes]] = {}
        self._amendments: list[bytes] = []

    def publish(
        self, report: Mapping[str, Any], *, amendment_reason: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        _validate_generated_report(report)
        key = str(report["report_key"])
        prior_versions = self._reports.setdefault(key, [])
        amended = copy.deepcopy(dict(report))
        amendment: dict[str, Any] | None = None
        if prior_versions:
            if not amendment_reason or not amendment_reason.strip():
                raise ReportError("corrected source requires an amendment reason")
            prior = json.loads(prior_versions[-1])
            comparable = {
                k: v
                for k, v in amended.items()
                if k not in {"id", "report_hash", "revision", "supersedes_report_hash"}
            }
            prior_comparable = {
                k: v
                for k, v in prior.items()
                if k not in {"id", "report_hash", "revision", "supersedes_report_hash"}
            }
            if comparable == prior_comparable:
                raise ReportError("a no-op revision cannot be amended")
            amended["revision"] = prior["revision"] + 1
            amended["supersedes_report_hash"] = prior["report_hash"]
            amended["report_hash"] = hashlib.sha256(
                canonical_json_bytes(
                    {k: v for k, v in amended.items() if k != "report_hash"}
                )
            ).hexdigest()
            changed_refs = [
                ref for ref in amended["source_refs"] if ref not in prior["source_refs"]
            ]
            amendment = {
                "schema_name": "qc2.reporting.ReportAmendment.v1",
                "report_key": key,
                "revision_number": amended["revision"],
                "prior_report_hash": prior["report_hash"],
                "corrected_report_hash": amended["report_hash"],
                "reason": amendment_reason.strip(),
                "impact_analysis": "Report values were recomputed from the listed corrected immutable sources.",
                "correction_refs": changed_refs,
            }
            amendment["amendment_hash"] = hashlib.sha256(
                canonical_json_bytes(amendment)
            ).hexdigest()
            _validate_amendment(amendment)
            self._amendments.append(canonical_json_bytes(amendment))
        prior_versions.append(canonical_json_bytes(amended))
        return copy.deepcopy(amended), copy.deepcopy(amendment)

    def reports(self, report_key: str) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(json.loads(item)) for item in self._reports.get(report_key, ()))

    @property
    def amendments(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(json.loads(item)) for item in self._amendments)
