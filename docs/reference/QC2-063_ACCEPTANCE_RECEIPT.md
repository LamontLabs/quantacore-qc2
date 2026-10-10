# QC2-063 — Generated Reports Acceptance

## Acceptance assessment

- **Result:** PASS
- **Evidence class/environment:** `SYNTHETIC_FIXTURE` / `test`
- **Scope:** Deterministic report generation and correction handling using schema-validated fixture contracts. This does not claim live operational report evidence.

## Acceptance checklist

- [x] DELIVERABLE: Daily Runner, Weekly Learning, Missed Monster, False Monster, Promotion, F0 Validation and Integrity reports. | evidence: `packages/reporting/src/qc2_reporting/reports.py`; parametrized report-kind coverage in `tests/reporting/test_reports.py`.
- [x] DELIVERABLE: Machine-readable metric source manifests and human-readable versions. | evidence: `metric_source_manifest` and `render_markdown` in `packages/reporting/src/qc2_reporting/reports.py`; `docs/GENERATED_REPORTS.md`.
- [x] DELIVERABLE: Report revisions/amendments, scope limitations and provisional status. | evidence: append-only `ReportLedger`, scope/evidence classification, and correction tests in `packages/reporting/src/qc2_reporting/reports.py` and `tests/reporting/test_reports.py`.
- [x] TEST: Recompute report totals from source artifacts; denominators match. | evidence: `test_report_recomputes_totals_and_renders_source_denominators`; source contracts are validated and numerator/denominator totals are recomputed.
- [x] TEST: No report presents survivor-limited research or paper fills as broader proof. | evidence: `test_research_and_paper_sources_cannot_become_broader_proof`; both scopes force provisional status and explicit limitations.
- [x] TEST: Changed source correction produces amendment, not overwritten final report. | evidence: `test_changed_sources_append_revision_and_amendment_without_mutation`; prior revision remains available and corrected source is appended.

## Commands executed

- `PYTHONPATH=<workspace package and test sources> PYTEST_ADDOPTS=--import-mode=importlib uv run pytest -q tests/reporting/test_reports.py` — 18 passed.
- `uv run ruff check packages/reporting tests/reporting` — passed.
- `python3 tools/generate_task_docs.py --check` — passed.
- `DANGEROUSLY_ALLOW_GIT=1 python3 tools/task_workflow.py preflight QC2-063` — passed.
- `git diff --check` — passed.
