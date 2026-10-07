# QC2-008 — Market Calendar Authority

## Acceptance assessment

- **Result:** PASS
- **Scope:** QC2-008 only. No downstream task was started.
- **Evidence class/environment:** `SYNTHETIC_FIXTURE` / `test`.
- **Calendar authority:** The package validates versioned manifests, revisions, full session inventories, and the typed-reference closure, including source evidence hashes. Missing coverage, sessions, or references fail closed.
- **Calendar behavior:** Provider rows are normalized from `America/New_York` into UTC. Phase, deadline, and next-session queries use the pinned inventory; there is no weekday or next-N-bars fallback.
- **Clock behavior:** Uncertainty thresholds are supplied by the caller, not guessed. Backward jumps latch in the process-local monitor. Production callers must restore prior samples and latched faults durably before enabling deadline-sensitive actions.
- **Provider scope:** The adapter has no network access, retry, or provider fallback. No live provider capability or calendar completeness is claimed; live measurement remains out of scope.
- **Owner authorization:** No F0 activation or owner-authorization path was changed. The existing exact epoch, manifest, and prospective-start-session authorization rule remains unchanged.
- **Legacy scope:** No legacy scheduler was inspected or modified.

## Acceptance checklist

- [x] DELIVERABLE: Calendar manifests/revisions, UTC and New York conversion, phase/deadline APIs. | evidence: `packages/calendar_authority/src/qc2_calendar_authority/records.py`, `provider.py`, `authority.py`; `test_alpaca_adapter_converts_new_york_times_across_dst`, `test_phase_and_deadline_use_early_close_not_a_fixed_close_time`
- [x] DELIVERABLE: Clock uncertainty/rollback assessment and scheduled-session inventory. | evidence: `packages/calendar_authority/src/qc2_calendar_authority/clock.py`, `authority.py`; `test_backward_jump_is_latched_and_blocks_deadline_sensitive_action`, `test_manifest_hash_and_market_session_inventory_are_validated`
- [x] DELIVERABLE: Provider calendar adapter plus deterministic pinned test calendars. | evidence: `packages/calendar_authority/src/qc2_calendar_authority/provider.py`; fixed synthetic calendar rows in `tests/calendar_authority/test_calendar_authority.py`
- [x] TEST: Holidays, early closes, DST transitions, exceptional closure, missing calendar range. | evidence: `test_holiday_and_exceptional_closure_are_closed_not_missing`, `test_alpaca_adapter_preserves_early_close_and_requires_boundary_coverage`, `test_alpaca_adapter_converts_new_york_times_across_dst`, `test_next_session_follows_calendar_and_missing_range_is_unavailable`
- [x] TEST: No next-N-bars horizon logic; next session follows the calendar. | evidence: `CalendarAuthority.next_session`; `test_next_session_follows_calendar_and_missing_range_is_unavailable`
- [x] TEST: Backward clock and expired calendar prevent deadline-sensitive actions. | evidence: `test_backward_jump_is_latched_and_blocks_deadline_sensitive_action`, `test_missing_clock_limit_and_expired_calendar_both_block_deadlines`

## Verification

- `python3 -m pytest -q tests/calendar_authority` — PASS, 17 passed.
- `python3 -m ruff check packages/calendar_authority tests/calendar_authority` — PASS.
- `python3 -m ruff format --check packages/calendar_authority tests/calendar_authority` — PASS.
- `pnpm run verify` — PASS, 98 Python tests and 7 database guard tests; typecheck, smoke checks, and task-workflow validation also passed.
