from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for package in ("packages/contracts/src", "packages/reporting/src"):
    sys.path.insert(0, str(ROOT / package))

from qc2_contracts.runtime import canonical_json_bytes, new_uuidv7  # noqa: E402
from qc2_reporting import (  # noqa: E402
    MetricFormula,
    MetricRegistry,
    ReportLedger,
    ReportSource,
    generate_report,
    render_markdown,
)
from qc2_reporting.reports import ReportError  # noqa: E402

METRIC_DEFINITION_ID = "018f0000-0000-7000-8000-000000000101"


def _metric_definition() -> dict:
    return {
        "schema_name": "qc2.validation.MetricDefinition.v1",
        "schema_version": "1.0",
        "id": METRIC_DEFINITION_ID,
        "created_at": "2026-10-10T00:00:00Z",
        "owning_authority": "validation",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "metric_key": "fixture_missing_rate",
        "version": 1,
        "estimand": "missing records / all eligible records",
        "unit": "ratio",
        "direction": "HIGHER_IS_BETTER",
        "missingness_policy": "UNSCORABLE",
        "tie_handling": "NOT_APPLICABLE",
    }


def _registry() -> MetricRegistry:
    return MetricRegistry(
        [
            MetricFormula(
                definition=_metric_definition(),
                source_schemas=("qc2.validation.MetricResult.v1",),
                numerator_field="missing_count",
                denominator_field="denominator",
            )
        ]
    )


def _source(
    *,
    scope: str = "COMPLETE_SOURCE",
    evidence: str = "SYNTHETIC_FIXTURE",
    missing_count: int = 3,
    denominator: int = 4,
) -> ReportSource:
    contract = {
        "schema_name": "qc2.validation.MetricResult.v1",
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": "2026-10-10T00:00:00Z",
        "owning_authority": "validation",
        "evidence_class": evidence,
        "environment_namespace": "test",
        "source_refs": [],
        "definition_ref": {
            "target_schema_name": "qc2.validation.MetricDefinition.v1",
            "target_id": METRIC_DEFINITION_ID,
        },
        "epoch_ref": {
            "target_schema_name": "qc2.validation.ValidationEpoch.v1",
            "target_id": new_uuidv7(),
            "content_hash": "a" * 64,
        },
        "session_id": None,
        "value": None,
        "lower_bound": None,
        "upper_bound": None,
        "denominator": denominator,
        "missing_count": missing_count,
        "computed_at": "2026-10-10T00:00:00Z",
    }
    return ReportSource(contract, scope)


def _report(
    sources: ReportSource | tuple[ReportSource, ...],
    key: str = "daily/2026-10-10",
    registry: MetricRegistry | None = None,
) -> dict:
    if isinstance(sources, ReportSource):
        sources = (sources,)
    return generate_report(
        report_kind="DAILY_RUNNER",
        report_key=key,
        period="2026-10-10",
        registry=registry or _registry(),
        metric_keys=["fixture_missing_rate"],
        sources=sources,
        scope_limitations=["FIXTURE_SCOPE_ONLY"],
    )


def test_report_recomputes_totals_and_renders_source_denominators() -> None:
    sources = (
        _source(missing_count=3, denominator=4),
        _source(missing_count=2, denominator=3),
    )
    report = _report(sources)

    assert report["metrics"][0]["numerator"] == "5"
    assert report["metrics"][0]["denominator"] == "7"
    assert report["metrics"][0]["value"] == "0.7142857142857142857142857143"
    markdown = render_markdown(report)
    assert "Denominator" in markdown
    assert sources[0].target_id in markdown
    assert report["report_hash"] in markdown


@pytest.mark.parametrize(
    "report_kind",
    [
        "DAILY_RUNNER",
        "WEEKLY_LEARNING",
        "MISSED_MONSTER",
        "FALSE_MONSTER",
        "PROMOTION",
        "F0_VALIDATION",
        "INTEGRITY",
    ],
)
def test_all_required_report_kinds_include_metric_and_source_manifest(
    report_kind: str,
) -> None:
    source = _source()
    report = generate_report(
        report_kind=report_kind,
        report_key=f"{report_kind}/fixture",
        period="fixture-period",
        registry=_registry(),
        metric_keys=["fixture_missing_rate"],
        sources=[source],
        scope_limitations=["SYNTHETIC_FIXTURE_ONLY"],
    )

    assert report["metrics"][0]["metric_definition_id"]
    assert report["metrics"][0]["source_refs"][0]["row_snapshot_hash"]
    assert report["source_refs"][0]["content_hash"] == hashlib.sha256(
        canonical_json_bytes(dict(source.rows[0]))
    ).hexdigest()
    assert report["source_refs"][0]["row_snapshot_hash"] == hashlib.sha256(
        canonical_json_bytes([dict(row) for row in source.rows])
    ).hexdigest()
    assert report["status"] == "PROVISIONAL"


def test_research_and_paper_sources_cannot_become_broader_proof() -> None:
    research = _source(
        scope="SURVIVOR_LIMITED_RESEARCH",
        evidence="HISTORICAL_RECONSTRUCTED",
    )
    paper = _source(
        missing_count=1,
        denominator=2,
        scope="PAPER_EXECUTION",
        evidence="FORWARD_OPERATIONAL",
    )
    report = generate_report(
        report_kind="WEEKLY_LEARNING",
        report_key="learning/2026-W41",
        period="2026-W41",
        registry=_registry(),
        metric_keys=["fixture_missing_rate"],
        sources=[research, paper],
        scope_limitations=["RESEARCH_SUMMARY_ONLY"],
    )

    assert report["status"] == "PROVISIONAL"
    assert "SURVIVOR_LIMITED_RESEARCH_ONLY" in report["scope_limitations"]
    assert "PAPER_FILLS_ARE_NOT_LIVE_EXECUTION_PROOF" in report["scope_limitations"]
    assert "PROVISIONAL" in render_markdown(report)


def test_changed_sources_append_revision_and_amendment_without_mutation() -> None:
    ledger = ReportLedger()
    registry = _registry()
    original_source = _source()
    corrected_source = _source(missing_count=2, denominator=4)
    original, no_amendment = ledger.publish(
        _report(original_source, registry=registry)
    )
    corrected, amendment = ledger.publish(
        _report(corrected_source, registry=registry),
        amendment_reason="The source artifact was corrected.",
    )

    assert no_amendment is None
    assert corrected["revision"] == 2
    assert corrected["supersedes_report_hash"] == original["report_hash"]
    assert amendment is not None
    assert (
        amendment["correction_refs"][0]["content_hash"]
        == corrected_source.content_hash
    )
    assert len(ledger.reports(original["report_key"])) == 2
    assert ledger.reports(original["report_key"])[0]["report_hash"] == original["report_hash"]
    assert len(ledger.amendments) == 1


def test_corrected_source_cannot_overwrite_without_amendment_reason() -> None:
    ledger = ReportLedger()
    registry = _registry()
    ledger.publish(_report(_source(), registry=registry))
    with pytest.raises(ReportError, match="amendment reason"):
        ledger.publish(
            _report(_source(missing_count=2), registry=registry)
        )
    assert len(ledger.reports("daily/2026-10-10")) == 1


def test_ledger_rejects_mutated_report_and_no_op_revision() -> None:
    ledger = ReportLedger()
    original_source = _source()
    registry = _registry()
    original = _report(original_source, registry=registry)
    mutated = dict(original)
    mutated["period"] = "forged"
    with pytest.raises(ReportError, match="report hash"):
        ledger.publish(mutated)

    ledger.publish(original)
    with pytest.raises(ReportError, match="no-op revision"):
        ledger.publish(
            _report(original_source, registry=registry), amendment_reason="No change."
        )
    assert len(ledger.reports(original["report_key"])) == 1


def test_ledger_rejects_rehashed_report_with_invalid_custom_shape() -> None:
    report = _report(_source())
    invalid = dict(report)
    invalid["status"] = "UNREVIEWED"
    payload = {key: value for key, value in invalid.items() if key != "report_hash"}
    invalid["report_hash"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    with pytest.raises(ReportError, match="report revision or status is invalid"):
        ReportLedger().publish(invalid)


def test_source_rows_are_detached_from_the_pinned_contract() -> None:
    source = _source()
    exposed_row = source.rows[0]
    exposed_row["missing_count"] = 99

    report = _report(source)

    assert report["metrics"][0]["numerator"] == "3"
    assert source.rows[0]["missing_count"] == 3


def test_source_must_match_registered_contract_schema() -> None:
    contract = dict(_source().rows[0])
    contract["unregistered_claim"] = True
    with pytest.raises(ReportError, match="source contract is invalid"):
        ReportSource(contract, "COMPLETE_SOURCE")


def test_metric_result_must_reference_registered_metric_definition() -> None:
    contract = dict(_source().rows[0])
    contract["definition_ref"] = dict(contract["definition_ref"])
    contract["definition_ref"]["target_id"] = new_uuidv7()
    source = ReportSource(contract, "COMPLETE_SOURCE")

    with pytest.raises(ReportError, match="does not match registered metric"):
        _report(source)


def test_denominator_is_not_inferred_when_missing_or_zero() -> None:
    invalid_formula = MetricFormula(
        definition=_metric_definition(),
        source_schemas=("qc2.validation.MetricResult.v1",),
        numerator_field="unregistered_row_field",
        denominator_field="denominator",
    )
    with pytest.raises(ReportError, match="missing registered field"):
        _report(_source(), registry=MetricRegistry([invalid_formula]))
    report = _report(_source(missing_count=0, denominator=0))
    assert report["metrics"][0]["value"] is None
    assert report["status"] == "PROVISIONAL"


def test_unregistered_metric_and_ineligible_sources_fail_closed() -> None:
    with pytest.raises(ReportError, match="unregistered metric"):
        generate_report(
            report_kind="PROMOTION",
            report_key="promotion/1",
            period="1",
            registry=_registry(),
            metric_keys=["unregistered"],
            sources=[_source()],
            scope_limitations=["PROMOTION_INPUTS_ONLY"],
        )
    other = ReportSource(_metric_definition(), "COMPLETE_SOURCE")
    with pytest.raises(ReportError, match="no eligible source artifacts"):
        _report(other)
