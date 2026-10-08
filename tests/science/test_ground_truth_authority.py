from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from qc2_contracts.runtime import new_uuidv7, validate_contract, verify_content_hash
from qc2_science import (
    ContractRef,
    DailyLabelBar,
    LabelInput,
    build_label_definition_specs,
    materialize_label_registry,
)
from qc2_science.ground_truth import (
    record_action_review_decision,
    resolve_eligible_rows,
)
from qc2_science.ground_truth_ledger import (
    LearningReleaseRequest,
    OutcomeCorrectionRequest,
    OutcomeLedger,
    append_learning_release,
    append_outcome_revision,
)
from qc2_science.ground_truth_models import (
    GroundTruthEligibleRow,
    GroundTruthError,
    SymbolAssignmentEvidence,
    TerminalEventEvidence,
    freeze_contract_record,
)

UTC = timezone.utc
CALENDAR = tuple(
    date.fromisoformat(item)
    for item in (
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
        "2026-05-12",
        "2026-05-13",
        "2026-05-14",
        "2026-05-15",
    )
)
CREATED = datetime(2026, 5, 20, 12, tzinfo=UTC)
REGISTRY_CREATED = datetime(2026, 5, 1, 12, tzinfo=UTC)
CORRECTION_POLICY_SCHEMA = "qc2.integrity_build.ConfigurationManifest.v1"


def _ref(schema_name: str, value: str | None = None) -> ContractRef:
    return ContractRef(schema_name, value or new_uuidv7(), "a" * 64)


def _registry(*, with_thresholds: bool = True):
    thresholds = (
        {
            "expansion_runner_5_session": "0.100000000000",
            "session_monster_5_session": "0.100000000000",
        }
        if with_thresholds
        else {}
    )
    specs = build_label_definition_specs(thresholds)
    return materialize_label_registry(
        definition_ids={spec.stable_key: new_uuidv7() for spec in specs},
        registry_id=new_uuidv7(),
        created_at=REGISTRY_CREATED,
        effective_from=CALENDAR[0],
        environment_namespace="test",
        evidence_class="SYNTHETIC_FIXTURE",
        thresholds=thresholds,
    )


def _bar(
    session_index: int,
    *,
    instrument_ref: ContractRef,
    adjustment_ref: ContractRef,
    share_basis_key: str = "basis-2026-05",
    values: tuple[int, int, int, int] | None = None,
    source_ref: ContractRef | None = None,
) -> DailyLabelBar:
    defaults = {
        0: (100, 102, 98, 100),
        1: (100, 105, 97, 103),
        2: (103, 115, 100, 110),
        3: (110, 120, 105, 118),
        4: (118, 119, 112, 115),
        5: (115, 117, 110, 116),
    }
    open_price, high_price, low_price, close_price = values or defaults[session_index]
    session = CALENDAR[session_index]
    return DailyLabelBar(
        session_id=session,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        source_ref=source_ref or _ref("qc2.identity_market.DailyBar.v1"),
        instrument_ref=instrument_ref,
        adjustment_ref=adjustment_ref,
        share_basis_key=share_basis_key,
        finalized_at=datetime(
            session.year,
            session.month,
            session.day,
            22,
            tzinfo=UTC,
        ),
    )


def _label_input(
    *,
    instrument_ref: ContractRef | None = None,
    adjustment_ref: ContractRef | None = None,
    future_indices: tuple[int, ...] = (1, 2, 3, 4, 5),
    corporate_action_status: str = "FINALIZED",
    terminal_event_session: date | None = None,
    prediction_bar: DailyLabelBar | None = None,
    future_bars: tuple[DailyLabelBar, ...] | None = None,
) -> LabelInput:
    instrument = instrument_ref or _ref("qc2.identity_market.Instrument.v1")
    adjustment = adjustment_ref or _ref("qc2.identity_market.AdjustmentManifest.v1")
    prediction = prediction_bar or _bar(
        0,
        instrument_ref=instrument,
        adjustment_ref=adjustment,
    )
    future = future_bars or tuple(
        _bar(index, instrument_ref=instrument, adjustment_ref=adjustment)
        for index in future_indices
    )
    finalized = corporate_action_status == "FINALIZED"
    observation_session = (
        terminal_event_session
        if terminal_event_session is not None
        else CALENDAR[-1]
    )
    return LabelInput(
        prediction_bar=prediction,
        calendar_ref=_ref("qc2.time_operation.CalendarManifest.v1"),
        calendar_sessions=CALENDAR,
        observation_session=observation_session,
        future_bars=future,
        corporate_action_status=corporate_action_status,
        corporate_action_finalized_at=(
            datetime(2026, 5, 19, 10, tzinfo=UTC) if finalized else None
        ),
        data_finalization_complete_at=(
            datetime(2026, 5, 19, 11, tzinfo=UTC) if finalized else None
        ),
        label_release_transaction_complete_at=(
            datetime(2026, 5, 19, 12, tzinfo=UTC) if finalized else None
        ),
        terminal_event_session=terminal_event_session,
    )


def _row(
    row_key: str,
    *,
    definition_key: str = "expansion_runner_5_session",
    label_input: LabelInput | None = None,
    symbol_assignments: tuple[SymbolAssignmentEvidence, ...] | None = None,
    action_refs: tuple[ContractRef, ...] = (),
    terminal_event: TerminalEventEvidence | None = None,
) -> GroundTruthEligibleRow:
    source = label_input or _label_input()
    assignments = symbol_assignments or (
        SymbolAssignmentEvidence(
            assignment_ref=_ref("qc2.identity_market.SymbolAssignment.v1"),
            instrument_ref=source.prediction_bar.instrument_ref,
            symbol="TEST",
            effective_from=CALENDAR[0] - timedelta(days=30),
        ),
    )
    return GroundTruthEligibleRow(
        row_key=row_key,
        definition_key=definition_key,
        label_input=source,
        symbol_assignments=assignments,
        corporate_action_refs=action_refs,
        terminal_event=terminal_event,
    )


def _outcome(result, row_key: str):
    return next(item.outcome for item in result.rows if item.row_key == row_key)


def _policy_ref() -> ContractRef:
    return _ref(CORRECTION_POLICY_SCHEMA)


def test_full_eligible_rows_resolve_across_split_and_symbol_rename():
    registry = _registry()
    label_input = _label_input()
    instrument_ref = label_input.prediction_bar.instrument_ref
    assignments = (
        SymbolAssignmentEvidence(
            assignment_ref=_ref("qc2.identity_market.SymbolAssignment.v1"),
            instrument_ref=instrument_ref,
            symbol="OLD",
            effective_from=CALENDAR[0] - timedelta(days=30),
            effective_to_exclusive=CALENDAR[3],
        ),
        SymbolAssignmentEvidence(
            assignment_ref=_ref("qc2.identity_market.SymbolAssignment.v1"),
            instrument_ref=instrument_ref,
            symbol="NEW",
            effective_from=CALENDAR[3],
        ),
    )
    # Future bars represent post-split observations normalized by the same
    # AdjustmentManifest and share basis as the prediction-session reference.
    result = resolve_eligible_rows(
        registry,
        (
            _row("eligible-z", label_input=label_input, symbol_assignments=assignments),
            _row("eligible-a", label_input=label_input, symbol_assignments=assignments),
        ),
        created_at=CREATED,
    )

    assert [item.row_key for item in result.rows] == ["eligible-a", "eligible-z"]
    for item in result.rows:
        payload = item.outcome.payload
        verify_content_hash("Outcome", payload)
        assert payload["outcome_state"] == "RESOLVED"
        assert payload["instrument_ref"] == instrument_ref.to_payload()
        assert payload["reference_price"] == "100"
        assert payload["next_open_reference_price"] == "100"
        assert payload["max_high_price"] == "120"
        assert payload["max_high_return"] == "0.200000000000"
        assert payload["max_high_session"] == CALENDAR[3].isoformat()
        assert payload["max_high_session_offset"] == 3
        assert payload["available_for_learning_at"] == "2026-05-19T12:00:00.000000Z"
    assert len(result.runner_events) == 2
    assert all(event.payload["event_type"] == "EXPANSION_RUNNER" for event in result.runner_events)
    assert all(event.payload["start_session"] == CALENDAR[2].isoformat() for event in result.runner_events)
    assert all(event.payload["end_session"] == CALENDAR[3].isoformat() for event in result.runner_events)
    assert not result.action_reviews


def test_halt_delisting_and_unresolved_corporate_action_stay_explicit():
    registry = _registry()
    action_ref = _ref("qc2.identity_market.CorporateActionRecord.v1")
    missing_bar = _row(
        "halted",
        label_input=_label_input(future_indices=(1, 2, 3, 4)),
    )
    terminal_session = CALENDAR[2]
    delisted_input = _label_input(
        future_indices=(1, 2),
        terminal_event_session=terminal_session,
    )
    delisted = _row(
        "delisted",
        label_input=delisted_input,
        action_refs=(action_ref,),
    )
    action_review = _row(
        "action-review",
        label_input=_label_input(corporate_action_status="REVIEW"),
        action_refs=(action_ref,),
    )
    result = resolve_eligible_rows(
        registry,
        (missing_bar, delisted, action_review),
        created_at=CREATED,
    )

    assert len(result.rows) == 3
    assert _outcome(result, "halted").payload["outcome_state"] == "PARTIALLY_RESOLVABLE"
    assert _outcome(result, "halted").payload["available_for_learning_at"] is None
    assert _outcome(result, "delisted").payload["outcome_state"] == "CENSORED_TERMINAL_EVENT"
    assert _outcome(result, "action-review").payload["outcome_state"] == "CORPORATE_ACTION_REVIEW"
    assert {item.review_type for item in result.action_reviews} == {
        "CORPORATE_ACTION",
        "TERMINAL_EVENT",
    }
    assert not result.runner_events

    case = next(item for item in result.action_reviews if item.review_type == "CORPORATE_ACTION")
    decision = record_action_review_decision(
        case,
        decision="REMAIN_UNRESOLVED",
        evidence_refs=(action_ref,),
        decided_at=CREATED + timedelta(days=1),
    )
    assert decision.case_id == case.case_id
    assert _outcome(result, "action-review").payload["outcome_state"] == "CORPORATE_ACTION_REVIEW"


def test_verified_terminal_cash_is_partial_and_never_released_as_full_horizon():
    registry = _registry()
    event_session = CALENDAR[2]
    action_ref = _ref("qc2.identity_market.CorporateActionRecord.v1")
    label_input = _label_input(
        future_indices=(1, 2),
        terminal_event_session=event_session,
    )
    terminal = TerminalEventEvidence(
        event_session=event_session,
        status="VERIFIED_CASH_CONSIDERATION",
        corporate_action_ref=action_ref,
        cash_consideration_per_share=Decimal("110"),
        share_basis_key="basis-2026-05",
        currency="USD",
        finalized_at=CREATED - timedelta(days=1),
    )
    result = resolve_eligible_rows(
        registry,
        (_row("cash-merger", label_input=label_input, action_refs=(action_ref,), terminal_event=terminal),),
        created_at=CREATED,
    )
    outcome = result.rows[0].outcome

    assert outcome.payload["outcome_state"] == "PARTIALLY_RESOLVABLE"
    assert outcome.payload["endpoint_return"] == "0.100000000000"
    assert outcome.payload["max_high_return"] is None
    assert outcome.payload["available_for_learning_at"] is None
    assert all(
        item["status"] == "CENSORED"
        for item in outcome.payload["field_validity"]
        if item["field_name"] in {"max_high_return", "mfe", "mae"}
    )
    zero_terminal = TerminalEventEvidence(
        event_session=event_session,
        status="VERIFIED_CASH_CONSIDERATION",
        corporate_action_ref=action_ref,
        cash_consideration_per_share=Decimal("0"),
        share_basis_key="basis-2026-05",
        currency="USD",
        finalized_at=CREATED - timedelta(days=1),
    )
    zero_result = resolve_eligible_rows(
        registry,
        (
            _row(
                "worthless-terminal",
                label_input=label_input,
                action_refs=(action_ref,),
                terminal_event=zero_terminal,
            ),
        ),
        created_at=CREATED,
    )
    assert _outcome(zero_result, "worthless-terminal").payload["endpoint_return"] == "-1.000000000000"
    with pytest.raises(GroundTruthError, match="fully RESOLVED"):
        append_learning_release(
            OutcomeLedger(outcomes=(outcome,)),
            LearningReleaseRequest(
                outcome_refs=(outcome.ref,),
                release_policy_ref=_policy_ref(),
                created_at=CREATED + timedelta(days=2),
            ),
        )

    unfinalized_input = _label_input(
        future_indices=(1, 2),
        corporate_action_status="REVIEW",
        terminal_event_session=event_session,
    )
    unfinalized_result = resolve_eligible_rows(
        registry,
        (
            _row(
                "cash-but-action-unresolved",
                label_input=unfinalized_input,
                action_refs=(action_ref,),
                terminal_event=terminal,
            ),
        ),
        created_at=CREATED,
    )
    unresolved_payload = _outcome(
        unfinalized_result,
        "cash-but-action-unresolved",
    ).payload
    assert unresolved_payload["outcome_state"] == "CENSORED_TERMINAL_EVENT"
    assert unresolved_payload["endpoint_return"] is None
    assert any(case.review_type == "CORPORATE_ACTION" for case in unfinalized_result.action_reviews)


def test_session_monster_events_are_emitted_from_label_evidence_only():
    registry = _registry()
    row = _row(
        "monster",
        definition_key="session_monster_5_session",
    )
    result = resolve_eligible_rows(registry, (row,), created_at=CREATED)

    assert _outcome(result, "monster").payload["outcome_state"] == "RESOLVED"
    assert [event.payload["event_type"] for event in result.runner_events] == [
        "SESSION_MONSTER"
    ]
    assert result.runner_events[0].payload["start_session"] == CALENDAR[2].isoformat()
    assert result.runner_events[0].payload["outcome_ref"] == _outcome(
        result, "monster"
    ).ref.to_payload()


def test_unfrozen_threshold_stays_unavailable_and_cannot_emit_or_release_an_event():
    registry = _registry(with_thresholds=False)
    result = resolve_eligible_rows(
        registry,
        (_row("no-threshold"),),
        created_at=CREATED,
    )
    outcome = result.rows[0].outcome

    assert outcome.payload["outcome_state"] == "RESOLVED"
    assert outcome.payload["available_for_learning_at"] is None
    assert not result.runner_events
    with pytest.raises(GroundTruthError, match="available_for_learning_at"):
        append_learning_release(
            OutcomeLedger(outcomes=(outcome,)),
            LearningReleaseRequest(
                outcome_refs=(outcome.ref,),
                release_policy_ref=_policy_ref(),
                created_at=CREATED + timedelta(days=2),
            ),
        )


def test_resolution_is_idempotent_and_imports_no_model_score_or_strategy_package():
    registry = _registry()
    row = _row("repeat")
    first = resolve_eligible_rows(registry, (row,), created_at=CREATED)
    second = resolve_eligible_rows(registry, (row,), created_at=CREATED)
    assert first == second

    root = Path(__file__).resolve().parents[2]
    forbidden_roots = {
        "qc2.models_prediction",
        "qc2.scientific_definitions.ScoreDefinition",
        "qc2.execution",
        "qc2_strategy",
        "qc2_score",
    }
    for module_name in ("ground_truth.py", "ground_truth_models.py", "ground_truth_ledger.py"):
        tree = ast.parse(
            (root / "packages/science/src/qc2_science" / module_name).read_text()
        )
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(
            any(name == banned or name.startswith(banned + ".") for banned in forbidden_roots)
            for name in imports
        )

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(root / "packages/science/src"),
            str(root / "packages/contracts/src"),
        )
    )
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import qc2_science.ground_truth; "
            "bad=('qc2.models_prediction','qc2.execution','qc2_strategy','qc2_score'); "
            "assert not [name for name in sys.modules if any(name == x or name.startswith(x+'.') for x in bad)]",
        ],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_corrections_append_idempotently_and_preserve_prediction_seals_and_prior_releases():
    registry = _registry()
    original_row = _row("corrected")
    original = resolve_eligible_rows(registry, (original_row,), created_at=CREATED).rows[0].outcome
    original_payload = original.payload
    sealed_prediction_ref = _ref("qc2.models_prediction.PredictionSeal.v1")
    ledger = OutcomeLedger(
        outcomes=(original,),
        sealed_prediction_refs=(sealed_prediction_ref,),
    )
    ledger, initial_release = append_learning_release(
        ledger,
        LearningReleaseRequest(
            outcome_refs=(original.ref,),
            release_policy_ref=_policy_ref(),
            created_at=CREATED + timedelta(days=2),
        ),
    )
    original_input = original_row.label_input
    corrected_bars = list(original_input.future_bars)
    corrected_bars[2] = replace(
        corrected_bars[2],
        high_price=Decimal("125"),
        source_ref=_ref("qc2.identity_market.DailyBar.v1"),
    )
    corrected_input = replace(original_input, future_bars=tuple(corrected_bars))
    corrected_row = _row("corrected", label_input=corrected_input)
    replacement = resolve_eligible_rows(
        registry,
        (corrected_row,),
        created_at=CREATED + timedelta(days=3),
    ).rows[0].outcome
    correction = OutcomeCorrectionRequest(
        prior_outcome_ref=original.ref,
        replacement_outcome=replacement,
        revision_reason="split_adjustment_corrected",
        correction_policy_ref=_policy_ref(),
        discovered_at=CREATED + timedelta(days=4),
        evidence_refs=(_ref("qc2.identity_market.CorporateActionRecord.v1"),),
    )
    corrected_ledger = append_outcome_revision(ledger, correction)
    repeated = append_outcome_revision(corrected_ledger, correction)

    assert corrected_ledger == repeated
    assert len(corrected_ledger.outcomes) == 2
    assert len(corrected_ledger.revisions) == 1
    assert corrected_ledger.outcomes[0].payload == original_payload
    assert corrected_ledger.sealed_prediction_refs == (sealed_prediction_ref,)
    assert corrected_ledger.learning_releases == (initial_release,)
    validate_contract("OutcomeRevision", corrected_ledger.revisions[0].payload)
    revision = corrected_ledger.revisions[0].payload
    assert revision["prior_outcome_ref"] == original.ref.to_payload()
    assert revision["replacement_outcome_ref"] == replacement.ref.to_payload()

    with pytest.raises(GroundTruthError, match="superseded Outcome"):
        append_learning_release(
            corrected_ledger,
            LearningReleaseRequest(
                outcome_refs=(original.ref,),
                release_policy_ref=_policy_ref(),
                created_at=CREATED + timedelta(days=5),
            ),
        )
    released, replacement_release = append_learning_release(
        corrected_ledger,
        LearningReleaseRequest(
            outcome_refs=(replacement.ref,),
            release_policy_ref=_policy_ref(),
            created_at=CREATED + timedelta(days=5),
        ),
    )
    assert replacement_release.outcome_refs == (replacement.ref,)
    assert released.learning_releases == (initial_release, replacement_release)
    assert released.outcomes[0].payload == original_payload
    repeated_release, repeated_batch = append_learning_release(
        released,
        LearningReleaseRequest(
            outcome_refs=(replacement.ref,),
            release_policy_ref=replacement_release.release_policy_ref,
            created_at=CREATED + timedelta(days=5),
        ),
    )
    assert repeated_release == released
    assert repeated_batch == replacement_release


def test_corrections_cannot_change_logical_outcome_identity():
    registry = _registry()
    first = resolve_eligible_rows(
        registry,
        (_row("identity-a"),),
        created_at=CREATED,
    ).rows[0].outcome
    other_instrument = _label_input()
    replacement = resolve_eligible_rows(
        registry,
        (_row("identity-b", label_input=other_instrument),),
        created_at=CREATED + timedelta(days=1),
    ).rows[0].outcome
    with pytest.raises(GroundTruthError, match="identity"):
        append_outcome_revision(
            OutcomeLedger(outcomes=(first,)),
            OutcomeCorrectionRequest(
                prior_outcome_ref=first.ref,
                replacement_outcome=replacement,
                revision_reason="identity_changed",
                correction_policy_ref=_policy_ref(),
                discovered_at=CREATED + timedelta(days=2),
                    evidence_refs=(_ref("qc2.identity_market.CorporateActionRecord.v1"),),
            ),
        )

    no_op_payload = first.payload
    no_op_payload["id"] = new_uuidv7()
    no_op_payload["created_at"] = "2026-05-21T12:00:00.000000Z"
    no_op_replacement = freeze_contract_record("Outcome", no_op_payload)
    with pytest.raises(GroundTruthError, match="must change the content-addressed"):
        append_outcome_revision(
            OutcomeLedger(outcomes=(first,)),
            OutcomeCorrectionRequest(
                prior_outcome_ref=first.ref,
                replacement_outcome=no_op_replacement,
                revision_reason="no_op",
                correction_policy_ref=_policy_ref(),
                discovered_at=CREATED + timedelta(days=2),
                evidence_refs=(_ref("qc2.identity_market.CorporateActionRecord.v1"),),
            ),
        )

    promoted_payload = first.payload
    promoted_payload["environment_namespace"] = "production"
    promoted = freeze_contract_record("Outcome", promoted_payload)
    with pytest.raises(GroundTruthError, match="evidence class or environment"):
        append_outcome_revision(
            OutcomeLedger(outcomes=(first,)),
            OutcomeCorrectionRequest(
                prior_outcome_ref=first.ref,
                replacement_outcome=promoted,
                revision_reason="environment_changed",
                correction_policy_ref=_policy_ref(),
                discovered_at=CREATED + timedelta(days=2),
                evidence_refs=(_ref("qc2.identity_market.CorporateActionRecord.v1"),),
            ),
        )


def test_symbol_assignment_gaps_and_mixed_terminal_currencies_fail_closed():
    registry = _registry()
    label_input = _label_input()
    instrument_ref = label_input.prediction_bar.instrument_ref
    incomplete = SymbolAssignmentEvidence(
        assignment_ref=_ref("qc2.identity_market.SymbolAssignment.v1"),
        instrument_ref=instrument_ref,
        symbol="TEST",
        effective_from=CALENDAR[0],
        effective_to_exclusive=CALENDAR[3],
    )
    with pytest.raises(GroundTruthError, match="coverage"):
        resolve_eligible_rows(
            registry,
            (_row("assignment-gap", label_input=label_input, symbol_assignments=(incomplete,)),),
            created_at=CREATED,
        )

    action_ref = _ref("qc2.identity_market.CorporateActionRecord.v1")
    event_session = CALENDAR[2]
    terminal = TerminalEventEvidence(
        event_session=event_session,
        status="VERIFIED_CASH_CONSIDERATION",
        corporate_action_ref=action_ref,
        cash_consideration_per_share="110",
        share_basis_key="basis-2026-05",
        currency="EUR",
        finalized_at=CREATED - timedelta(days=1),
    )
    terminal_input = _label_input(
        future_indices=(1, 2),
        terminal_event_session=event_session,
    )
    with pytest.raises(GroundTruthError, match="different currency"):
        resolve_eligible_rows(
            registry,
            (
                _row(
                    "currency-mismatch",
                    label_input=terminal_input,
                    action_refs=(action_ref,),
                    terminal_event=terminal,
                ),
            ),
            created_at=CREATED,
        )
    wrong_basis = TerminalEventEvidence(
        event_session=event_session,
        status="VERIFIED_CASH_CONSIDERATION",
        corporate_action_ref=action_ref,
        cash_consideration_per_share="110",
        share_basis_key="basis-other",
        currency="USD",
        finalized_at=CREATED - timedelta(days=1),
    )
    with pytest.raises(GroundTruthError, match="reference share basis"):
        _row(
            "basis-mismatch",
            label_input=terminal_input,
            action_refs=(action_ref,),
            terminal_event=wrong_basis,
        )
