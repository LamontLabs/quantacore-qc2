# QC2-031 — Missed Monster Review

## Acceptance assessment

- **Result:** PASS
- The research-only queue binds a frozen event definition, rank rule, coverage rule and primary-rank cutoff. It maps the five failure categories onto the existing strict `ReviewCase` contract without adding mutable scientific fields. Each case has deterministic identity, typed event/outcome references, an evidence-linked explanation and immutable research annotations. The generator has no API for writing outcomes, ranks or denominators, and no trade or live-provider input.

## Acceptance checklist

- [x] DELIVERABLE: Deterministic review queue and case schema with frozen trigger parameters. | evidence: `packages/apexlab/src/qc2_apexlab/missed_monster_review.py`, `packages/apexlab/src/qc2_apexlab/__init__.py`, `tests/apexlab/test_missed_monster_review.py`
- [x] DELIVERABLE: Ranked-low/unscorable/excluded/unobserved/missed-session categories. | evidence: `packages/apexlab/src/qc2_apexlab/missed_monster_review.py`, `tests/apexlab/test_missed_monster_review.py::test_all_five_categories_are_evidence_linked_and_deterministic`
- [x] DELIVERABLE: Evidence-linked explanation template and research-only annotations. | evidence: `packages/apexlab/src/qc2_apexlab/missed_monster_review.py`, `tests/apexlab/test_missed_monster_review.py::test_all_five_categories_are_evidence_linked_and_deterministic`
- [x] TEST: Major fixture runners appear even when no prediction or trade existed. | evidence: `tests/apexlab/test_missed_monster_review.py::test_major_runner_genome_is_reviewed_without_prediction_or_trade`
- [x] TEST: Review cannot modify outcomes, ranks or official denominators. | evidence: `tests/apexlab/test_missed_monster_review.py::test_major_runner_genome_is_reviewed_without_prediction_or_trade`
- [x] TEST: Repeated generation yields the same case identity. | evidence: `tests/apexlab/test_missed_monster_review.py::test_all_five_categories_are_evidence_linked_and_deterministic`

## Verification

- Focused missed-monster tests: 4 passed.
- Full ApexLab suite: 23 passed.
- Full Python test suite: 338 passed.
- Ruff checks passed for the review queue, package exports and focused tests.
- Python compile check passed.
- QC2-031 dependency and acceptance preflight passed.
