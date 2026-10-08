"""Prospective qualification ledger and immutable validation artifacts."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from threading import RLock
from typing import Any, Callable

from qc2_contracts.runtime import (
    ContractValidationError,
    assert_immutable_update,
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .metrics import METRIC_SPECIFICATIONS, compute_session_metrics, normalized_metric_value
from .models import (
    IntegrityFinding,
    QualificationAssessment,
    QualificationEvidence,
    SHA256_PATTERN,
    SLUG_PATTERN,
    ValidationAuthorityError,
    reference,
    session_date,
    unique_session_ids,
    utc_instant,
)
from .statistics import FrozenAnalysisPlan

EPOCH_SCHEMA = "qc2.validation.ValidationEpoch.v1"
SCHEDULE_SCHEMA = "qc2.validation.ScheduledAttempt.v1"
QUALIFICATION_SCHEMA = "qc2.validation.QualificationReceipt.v1"
METRIC_DEFINITION_SCHEMA = "qc2.validation.MetricDefinition.v1"
METRIC_RESULT_SCHEMA = "qc2.validation.MetricResult.v1"
REPORT_SCHEMA = "qc2.validation.ValidationReport.v1"
ANALYSIS_PLAN_SCHEMA = "qc2.validation.StatisticalAnalysisPlan.v1"
DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
HOLDOUT_ACCESS_SCHEMA = "qc2.outcomes_research.HoldoutAccessReceipt.v1"
RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
CHECKPOINT_SCHEMA = "qc2.integrity_build.Checkpoint.v1"
HOLDOUT_HASH_DOMAIN = "qc2.validation.holdout-access.v1"
REPORT_HASH_DOMAIN = "qc2.validation-report.v1"
UUID7_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


def _reference_id(contract: Mapping[str, Any], field: str) -> str:
    value = contract.get(field)
    if not isinstance(value, Mapping) or not isinstance(value.get("target_id"), str):
        raise ValidationAuthorityError(f"{field} must be a typed reference")
    return value["target_id"]


def _holdout_key(dataset_ref: Mapping[str, Any]) -> tuple[str, str, str]:
    normalized = reference(
        dataset_ref,
        DATASET_SCHEMA,
        "dataset_ref",
        require_content_hash=True,
    )
    return (
        normalized["target_schema_name"],
        normalized["target_id"],
        normalized["content_hash"],
    )


class ValidationAuthority:
    """Owns scheduled opportunities, pre-outcome receipts, and one-use evaluation."""

    def __init__(
        self,
        *,
        epoch_ref: Mapping[str, Any],
        evidence_class: str = "SYNTHETIC_FIXTURE",
        environment_namespace: str = "test",
        id_factory: Callable[[], str] = new_uuidv7,
    ) -> None:
        self._epoch_ref = reference(epoch_ref, EPOCH_SCHEMA, "epoch_ref", require_content_hash=True)
        if environment_namespace == "production":
            raise ValidationAuthorityError(
                "ValidationAuthority is policy/framework only and cannot run in production."
            )
        if evidence_class not in {
            "SYNTHETIC_FIXTURE",
            "HISTORICAL_RECONSTRUCTED",
            "FORWARD_OPERATIONAL",
            "FORWARD_SEALED",
        }:
            raise ValidationAuthorityError("unsupported evidence class")
        if not isinstance(environment_namespace, str) or not SLUG_PATTERN.fullmatch(
            environment_namespace
        ):
            raise ValidationAuthorityError("environment_namespace must be a lowercase slug")
        self._evidence_class = evidence_class
        self._environment_namespace = environment_namespace
        self._id_factory = id_factory
        self._lock = RLock()
        self._scheduled: dict[str, dict[str, Any]] = {}
        self._schedule_signature: tuple[Any, ...] | None = None
        self._qualifications: dict[str, QualificationAssessment] = {}
        self._findings: list[IntegrityFinding] = []
        self._holdouts: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._evaluated_holdouts: set[tuple[str, str, str]] = set()
        self._metric_definitions: dict[str, dict[str, Any]] = {}
        self._metric_definition_keys: dict[str, str] = {}
        self._metric_results: list[dict[str, Any]] = []
        self._metric_result_sessions: set[tuple[tuple[str, str, str], str]] = set()
        self._analysis_plan: dict[str, Any] | None = None
        self._report: dict[str, Any] | None = None
        self._initialize_metric_definitions()

    def _assert_nonproduction(self) -> None:
        if self._environment_namespace == "production":
            raise ValidationAuthorityError("production validation is disabled in QC2-026")

    def _new_id(self) -> str:
        value = self._id_factory()
        if not isinstance(value, str) or not UUID7_PATTERN.fullmatch(value):
            raise ValidationAuthorityError("id_factory must return a lowercase UUIDv7")
        return value

    def _envelope(self, schema_name: str, created_at: str, object_id: str) -> dict[str, Any]:
        return {
            "schema_name": schema_name,
            "schema_version": "1.0",
            "id": object_id,
            "created_at": created_at,
            "owning_authority": "validation",
            "evidence_class": self._evidence_class,
            "environment_namespace": self._environment_namespace,
            "source_refs": [],
        }

    def _initialize_metric_definitions(self) -> None:
        for spec in METRIC_SPECIFICATIONS:
            payload = {
                **self._envelope(METRIC_DEFINITION_SCHEMA, "2026-10-08T00:00:00Z", self._new_id()),
                "metric_key": spec.metric_key,
                "version": 1,
                "estimand": spec.estimand,
                "unit": spec.unit,
                "direction": spec.direction,
                "missingness_policy": spec.missingness_policy,
                "tie_handling": spec.tie_handling,
            }
            try:
                validate_contract("MetricDefinition", payload)
            except ContractValidationError as exc:
                raise ValidationAuthorityError(str(exc)) from exc
            self._metric_definitions[spec.metric_key] = payload
            self._metric_definition_keys[payload["id"]] = spec.metric_key

    @property
    def epoch_ref(self) -> dict[str, str]:
        return copy.deepcopy(self._epoch_ref)

    @property
    def scheduled_opportunities(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(copy.deepcopy(item) for item in self._scheduled.values())

    @property
    def qualification_receipts(self) -> tuple[QualificationAssessment, ...]:
        with self._lock:
            return tuple(copy.deepcopy(item) for item in self._qualifications.values())

    @property
    def integrity_findings(self) -> tuple[IntegrityFinding, ...]:
        with self._lock:
            return tuple(self._findings)

    @property
    def metric_definitions(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(copy.deepcopy(item) for item in self._metric_definitions.values())

    @property
    def metric_results(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(copy.deepcopy(item) for item in self._metric_results)

    @property
    def analysis_plan(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._analysis_plan)

    def schedule_sessions(
        self,
        *,
        session_ids: Sequence[str],
        deadlines: Mapping[str, str],
        created_at: str,
    ) -> tuple[dict[str, Any], ...]:
        """Freeze one chronological opportunity schedule for the epoch."""
        self._assert_nonproduction()
        sessions = unique_session_ids(session_ids, "session_ids")
        created = utc_instant(created_at, "created_at")
        if set(deadlines) != set(sessions):
            raise ValidationAuthorityError("deadlines must cover every scheduled session exactly")
        normalized_deadlines = {
            session: deadlines[session]
            for session in sessions
        }
        for session, deadline_text in normalized_deadlines.items():
            session_date(session)
            if utc_instant(deadline_text, f"deadlines[{session}]") < created:
                raise ValidationAuthorityError("a scheduled deadline cannot precede schedule creation")
        signature = (
            sessions,
            tuple((session, normalized_deadlines[session]) for session in sessions),
            created_at,
        )
        with self._lock:
            if self._schedule_signature is not None:
                if self._schedule_signature == signature:
                    return self.scheduled_opportunities
                raise ValidationAuthorityError("the prospective schedule is already frozen")
            created_rows: dict[str, dict[str, Any]] = {}
            for session in sessions:
                item = {
                    **self._envelope(SCHEDULE_SCHEMA, created_at, self._new_id()),
                    "epoch_ref": copy.deepcopy(self._epoch_ref),
                    "session_id": session,
                    "schedule_created_at": created_at,
                    "expected_deadline": normalized_deadlines[session],
                    "attempt_state": "SCHEDULED",
                    "run_ref": None,
                    "missed_reason": None,
                }
                try:
                    validate_contract("ScheduledAttempt", item)
                except ContractValidationError as exc:
                    raise ValidationAuthorityError(str(exc)) from exc
                created_rows[session] = item
            self._scheduled = created_rows
            self._schedule_signature = signature
            return tuple(copy.deepcopy(item) for item in created_rows.values())

    def record_attempt_state(
        self,
        *,
        session_id: str,
        new_state: str,
        run_ref: Mapping[str, Any] | None = None,
        missed_reason: str | None = None,
    ) -> dict[str, Any]:
        """Mirror a prediction-attempt transition while preserving schedule identity."""
        self._assert_nonproduction()
        session_date(session_id)
        with self._lock:
            current = self._scheduled.get(session_id)
            if current is None:
                raise ValidationAuthorityError("attempt state cannot be recorded for an unscheduled session")
            updated = copy.deepcopy(current)
            updated["attempt_state"] = new_state
            if new_state in {"SCHEDULED", "MISSED_START"}:
                updated["run_ref"] = None
            else:
                if run_ref is None:
                    raise ValidationAuthorityError("started or completed attempts require a run reference")
                updated["run_ref"] = reference(run_ref, RUN_SCHEMA, "run_ref")
            updated["missed_reason"] = missed_reason
            try:
                assert_immutable_update("ScheduledAttempt", current, updated)
                validate_contract("ScheduledAttempt", updated)
            except ContractValidationError as exc:
                raise ValidationAuthorityError(str(exc)) from exc
            self._scheduled[session_id] = updated
            return copy.deepcopy(updated)

    def reconcile_missed_start(
        self,
        *,
        session_id: str,
        reason: str,
        observed_at: str,
    ) -> dict[str, Any]:
        """Record an absent start only after its frozen opportunity deadline."""
        if not isinstance(reason, str) or not SLUG_PATTERN.fullmatch(reason):
            raise ValidationAuthorityError("missed-start reason must be a lowercase reason code")
        with self._lock:
            current = self._scheduled.get(session_id)
            if current is None:
                raise ValidationAuthorityError("cannot reconcile an unscheduled session")
            if utc_instant(observed_at, "observed_at") < utc_instant(
                current["expected_deadline"], "expected_deadline"
            ):
                raise ValidationAuthorityError("a start cannot be marked missed before its deadline")
        return self.record_attempt_state(
            session_id=session_id,
            new_state="MISSED_START",
            missed_reason=reason,
        )

    def qualify_session(
        self,
        *,
        session_id: str,
        evidence: QualificationEvidence,
    ) -> QualificationAssessment:
        """Seal prospective facts before labels, broker results, or future events are read."""
        self._assert_nonproduction()
        session_date(session_id)
        with self._lock:
            schedule = self._scheduled.get(session_id)
            if schedule is None or schedule["attempt_state"] != "SEALED":
                raise ValidationAuthorityError(
                    "qualification requires a scheduled attempt with a sealed prediction run"
                )
            if session_id in self._qualifications:
                raise ValidationAuthorityError("a session qualification receipt is immutable")

            deadline = utc_instant(schedule["expected_deadline"], "expected_deadline")
            prediction_sealed_at = utc_instant(
                evidence.prediction_sealed_at, "prediction_sealed_at"
            )
            anchor_at = utc_instant(evidence.anchor_created_at, "anchor_created_at")
            receipt_sealed_at = utc_instant(evidence.receipt_sealed_at, "receipt_sealed_at")
            if prediction_sealed_at > anchor_at or anchor_at > receipt_sealed_at:
                raise ValidationAuthorityError(
                    "prediction seal, anchor, and qualification receipt must be chronological"
                )

            prediction_seal_ref = reference(
                evidence.prediction_seal_ref,
                "qc2.models_prediction.PredictionSeal.v1",
                "prediction_seal_ref",
                require_content_hash=True,
            )
            checkpoint_ref = reference(
                evidence.checkpoint_ref,
                CHECKPOINT_SCHEMA,
                "checkpoint_ref",
                require_content_hash=True,
            )
            on_time_seal = prediction_sealed_at <= deadline
            on_time_anchor = anchor_at <= deadline
            on_time_receipt = receipt_sealed_at <= deadline
            payload = {
                **self._envelope(
                    QUALIFICATION_SCHEMA,
                    evidence.receipt_sealed_at,
                    self._new_id(),
                ),
                "epoch_ref": copy.deepcopy(self._epoch_ref),
                "session_id": session_id,
                "prediction_seal_ref": prediction_seal_ref,
                "prediction_integrity": evidence.prediction_integrity,
                "denominator_status": evidence.denominator_status,
                "on_time_seal": on_time_seal,
                "on_time_anchor": on_time_anchor,
                "comparator_available": evidence.comparator_available,
                "protocol_conformity": evidence.protocol_conformity,
                "sealed_at": evidence.receipt_sealed_at,
                "checkpoint_ref": checkpoint_ref,
                "content_hash": "0" * 64,
            }
            try:
                validate_contract("QualificationReceipt", payload)
                payload["content_hash"] = canonical_content_hash(
                    "QualificationReceipt", payload
                )
                verify_content_hash("QualificationReceipt", payload)
            except ContractValidationError as exc:
                raise ValidationAuthorityError(str(exc)) from exc

            hard_failures: list[str] = []
            unknowns: list[str] = []
            if evidence.prediction_integrity in {"FAILED", "INVALID"}:
                hard_failures.append("prediction_integrity_failed")
            elif evidence.prediction_integrity not in {"FULL_VERIFIED", "VALID"}:
                unknowns.append("prediction_integrity_not_fully_verified")
            if evidence.denominator_status in {"INSUFFICIENT", "MISSING"}:
                hard_failures.append("denominator_not_valid")
            elif evidence.denominator_status == "UNKNOWN":
                unknowns.append("denominator_status_unknown")
            if not on_time_seal:
                hard_failures.append("prediction_seal_late")
            if not on_time_anchor:
                hard_failures.append("anchor_late")
            if not on_time_receipt:
                hard_failures.append("qualification_receipt_late")
            if not evidence.comparator_available:
                hard_failures.append("required_comparator_unavailable")
            if not evidence.protocol_conformity:
                hard_failures.append("protocol_nonconformity")
            state = (
                "NONQUALIFYING"
                if hard_failures
                else "INDETERMINATE"
                if unknowns
                else "QUALIFYING"
            )
            assessment = QualificationAssessment(
                state=state,
                reason_codes=tuple(hard_failures or unknowns),
                contract=copy.deepcopy(payload),
            )
            self._qualifications[session_id] = assessment
            return copy.deepcopy(assessment)

    def record_later_integrity_finding(
        self,
        *,
        session_id: str,
        severity: str,
        reason_code: str,
        found_at: str,
    ) -> IntegrityFinding:
        """Append later evidence without changing the sealed qualification receipt."""
        session_date(session_id)
        if severity not in {"INFO", "WARNING", "CRITICAL"}:
            raise ValidationAuthorityError("integrity finding severity is invalid")
        if not isinstance(reason_code, str) or not SLUG_PATTERN.fullmatch(reason_code):
            raise ValidationAuthorityError("integrity finding reason must be a lowercase code")
        utc_instant(found_at, "found_at")
        with self._lock:
            if session_id not in self._scheduled:
                raise ValidationAuthorityError("integrity findings must name a scheduled session")
            finding = IntegrityFinding(
                finding_id=self._new_id(),
                session_id=session_id,
                severity=severity,
                reason_code=reason_code,
                found_at=found_at,
            )
            self._findings.append(finding)
            return finding

    def consume_holdout(
        self,
        *,
        dataset_ref: Mapping[str, Any],
        evaluator_identity: str,
        access_scope: str,
        requested_at: str,
        granted_at: str,
        consumed_fields: Sequence[str],
        released_metrics: Sequence[str],
    ) -> dict[str, Any]:
        """Grant one narrow access receipt per content-addressed holdout dataset."""
        self._assert_nonproduction()
        key = _holdout_key(dataset_ref)
        if not evaluator_identity or not evaluator_identity.strip():
            raise ValidationAuthorityError("evaluator_identity is required")
        if access_scope not in {"METRICS_ONLY", "AGGREGATES_ONLY"}:
            raise ValidationAuthorityError("holdout access must not release row-level data")
        requested = utc_instant(requested_at, "requested_at")
        granted = utc_instant(granted_at, "granted_at")
        if granted < requested:
            raise ValidationAuthorityError("holdout access cannot be granted before it is requested")
        if any(not isinstance(item, str) or not item for item in (*consumed_fields, *released_metrics)):
            raise ValidationAuthorityError("holdout field and metric names must be non-empty strings")
        payload: dict[str, Any] = {
            **self._envelope(HOLDOUT_ACCESS_SCHEMA, granted_at, self._new_id()),
            "dataset_ref": dict(dataset_ref),
            "evaluator_identity": evaluator_identity,
            "access_scope": access_scope,
            "requested_at": requested_at,
            "granted_at": granted_at,
            "consumed_fields": list(consumed_fields),
            "released_metrics": list(released_metrics),
            "receipt_hash": "0" * 64,
        }
        payload["receipt_hash"] = domain_separated_sha256(
            HOLDOUT_HASH_DOMAIN,
            canonical_json_bytes({key_name: value for key_name, value in payload.items()
                                  if key_name != "receipt_hash"}),
        )
        try:
            validate_contract("HoldoutAccessReceipt", payload)
        except ContractValidationError as exc:
            raise ValidationAuthorityError(str(exc)) from exc
        with self._lock:
            if key in self._holdouts:
                raise ValidationAuthorityError("qualification holdout access has already been consumed")
            self._holdouts[key] = copy.deepcopy(payload)
            return copy.deepcopy(payload)

    def evaluate_dataset(
        self,
        *,
        holdout_receipt_ref: Mapping[str, Any],
        expected_session_ids: Sequence[str],
        session_slices: Sequence[Mapping[str, Any]],
        computed_at: str,
    ) -> tuple[tuple[Any, ...], tuple[dict[str, Any], ...]]:
        """Release only aggregate metrics, once, for a consumed qualification holdout."""
        self._assert_nonproduction()
        utc_instant(computed_at, "computed_at")
        holdout_reference = reference(
            holdout_receipt_ref,
            HOLDOUT_ACCESS_SCHEMA,
            "holdout_receipt_ref",
            require_content_hash=False,
        )
        session_ids = unique_session_ids(expected_session_ids, "expected_session_ids")
        slice_by_session: dict[str, Mapping[str, Any]] = {}
        for item in session_slices:
            session_id = item.get("session_id")
            if not isinstance(session_id, str) or session_id in slice_by_session:
                raise ValidationAuthorityError("dataset session slices must have unique session IDs")
            slice_by_session[session_id] = item
        if set(slice_by_session) != set(session_ids):
            raise ValidationAuthorityError(
                "metric evaluation must include every expected session exactly once"
            )

        with self._lock:
            holdout = next(
                (
                    item
                    for item in self._holdouts.values()
                    if item["id"] == holdout_reference["target_id"]
                ),
                None,
            )
            if holdout is None:
                raise ValidationAuthorityError("holdout access receipt was not issued by this authority")
            key = _holdout_key(holdout["dataset_ref"])
            if holdout_reference.get("content_hash") not in (None, holdout["receipt_hash"]):
                raise ValidationAuthorityError("holdout access receipt hash does not match")
            if key in self._evaluated_holdouts:
                raise ValidationAuthorityError("qualification holdout has already been evaluated")
            all_qualifying_sessions = {
                session_id
                for session_id, assessment in self._qualifications.items()
                if assessment.state == "QUALIFYING"
            }
            if set(session_ids) != all_qualifying_sessions:
                raise ValidationAuthorityError(
                    "holdout evaluation must include every qualifying session, without selection"
                )
            for session_id in session_ids:
                assessment = self._qualifications.get(session_id)
                if assessment is None or assessment.state != "QUALIFYING":
                    raise ValidationAuthorityError(
                        f"session {session_id} lacks a sealed qualifying receipt"
                    )

            bundles = tuple(
                compute_session_metrics(
                    session_id=session_id,
                    eligible_instrument_ids=slice_by_session[session_id]["eligible_instrument_ids"],
                    operating_rows=slice_by_session[session_id]["operating_rows"],
                    comparator_rows=slice_by_session[session_id]["comparator_rows"],
                    outcomes=slice_by_session[session_id]["outcomes"],
                )
                for session_id in session_ids
            )
            result_contracts: list[dict[str, Any]] = []
            for bundle in bundles:
                if (key, bundle.session_id) in self._metric_result_sessions:
                    raise ValidationAuthorityError("metrics for this holdout session already exist")
                estimates = (
                    bundle.operating_precision_at_10,
                    bundle.comparator_precision_at_10,
                    bundle.operating_recall_at_10,
                    bundle.comparator_recall_at_10,
                    bundle.operating_coverage,
                    bundle.comparator_coverage,
                    bundle.paired_precision_difference,
                    bundle.precision_lift,
                )
                for estimate in estimates:
                    definition = self._metric_definitions.get(estimate.metric_key)
                    if definition is None:
                        raise ValidationAuthorityError(
                            f"no frozen metric definition for {estimate.metric_key}"
                        )
                    payload = {
                        **self._envelope(METRIC_RESULT_SCHEMA, computed_at, self._new_id()),
                        "definition_ref": {
                            "target_schema_name": METRIC_DEFINITION_SCHEMA,
                            "target_id": definition["id"],
                        },
                        "epoch_ref": copy.deepcopy(self._epoch_ref),
                        "session_id": bundle.session_id,
                        "value": normalized_metric_value(estimate.value),
                        "lower_bound": normalized_metric_value(estimate.lower_bound),
                        "upper_bound": normalized_metric_value(estimate.upper_bound),
                        "denominator": estimate.denominator,
                        "missing_count": estimate.missing_count,
                        "computed_at": computed_at,
                    }
                    try:
                        validate_contract("MetricResult", payload)
                    except ContractValidationError as exc:
                        raise ValidationAuthorityError(str(exc)) from exc
                    result_contracts.append(payload)
            self._evaluated_holdouts.add(key)
            for bundle in bundles:
                self._metric_result_sessions.add((key, bundle.session_id))
            self._metric_results.extend(copy.deepcopy(result_contracts))
            return bundles, tuple(copy.deepcopy(result) for result in result_contracts)

    def freeze_analysis_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        """Freeze the existing v1 plan contract; calibration approval remains separate."""
        self._assert_nonproduction()
        payload = copy.deepcopy(dict(plan))
        if payload.get("epoch_ref") != self._epoch_ref:
            raise ValidationAuthorityError("analysis plan must pin this epoch")
        if payload.get("resample_count", 0) < 10_000:
            raise ValidationAuthorityError(
                "the governing specification requires at least 10,000 initial resamples"
            )
        method = str(payload.get("interval_method", "")).lower()
        if not method or "iid" in method or "independent_observation" in method:
            raise ValidationAuthorityError("analysis plans must name a dependence-aware method")
        with self._lock:
            if self._analysis_plan is not None:
                raise ValidationAuthorityError("the statistical analysis plan is immutable")
            payload["content_hash"] = "0" * 64
            try:
                validate_contract("StatisticalAnalysisPlan", payload)
                payload["content_hash"] = canonical_content_hash(
                    "StatisticalAnalysisPlan", payload
                )
                verify_content_hash("StatisticalAnalysisPlan", payload)
            except ContractValidationError as exc:
                raise ValidationAuthorityError(str(exc)) from exc
            self._analysis_plan = copy.deepcopy(payload)
            return copy.deepcopy(payload)

    def analysis_plan_for_closure(self) -> FrozenAnalysisPlan | None:
        """Project the frozen contract into the interface while leaving calibration unknown."""
        with self._lock:
            if self._analysis_plan is None:
                return None
            payload = self._analysis_plan
            from decimal import Decimal

            return FrozenAnalysisPlan(
                interval_method=payload["interval_method"],
                alpha=Decimal(payload["alpha"]),
                practical_minimum_effect=Decimal(payload["practical_minimum_effect"]),
                minimum_event_clusters=payload["minimum_event_clusters"],
                minimum_effective_blocks=payload["minimum_effective_blocks"],
                resample_count=payload["resample_count"],
                missingness_method=payload["missingness_method"],
                stopping_rule=payload["stopping_rule"],
                calibration_status="UNEVALUATED",
                frozen_at=payload["frozen_at"],
            )

    def build_report(
        self,
        *,
        decision: Any,
        sealed_at: str,
    ) -> dict[str, Any]:
        """Create one immutable report using only the required three public states."""
        self._assert_nonproduction()
        utc_instant(sealed_at, "sealed_at")
        verdict = getattr(decision, "verdict", None)
        reasons = getattr(decision, "reason_codes", None)
        if not isinstance(verdict, str) or not isinstance(reasons, tuple):
            raise ValidationAuthorityError("decision must be a ClosureDecision")
        if verdict == "NOT_INTERPRETABLE":
            verdict = "INSUFFICIENT_EVIDENCE"
        if verdict not in {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}:
            raise ValidationAuthorityError("reports can only use the three public closure states")

        with self._lock:
            if self._report is not None:
                raise ValidationAuthorityError("the final validation report is immutable")
            critical_finding = any(item.severity == "CRITICAL" for item in self._findings)
            if critical_finding:
                verdict = "FAIL"
                reasons = (*reasons, "later_critical_integrity_finding")
            scheduled_refs = [
                {
                    "target_schema_name": SCHEDULE_SCHEMA,
                    "target_id": item["id"],
                }
                for item in self._scheduled.values()
            ]
            qualifications = [
                item.contract
                for item in self._qualifications.values()
            ]
            qualification_refs = [
                {
                    "target_schema_name": QUALIFICATION_SCHEMA,
                    "target_id": item["id"],
                    "content_hash": item["content_hash"],
                }
                for item in qualifications
            ]
            metric_refs = [
                {
                    "target_schema_name": METRIC_RESULT_SCHEMA,
                    "target_id": item["id"],
                }
                for item in self._metric_results
            ]
            missingness_bounds: list[str] = []
            for result in self._metric_results:
                if result["lower_bound"] is not None or result["upper_bound"] is not None:
                    missingness_bounds.append(
                        "session={};metric={};lower={};upper={};missing={}".format(
                            result["session_id"],
                            self._metric_definition_keys[
                                result["definition_ref"]["target_id"]
                            ],
                            result["lower_bound"],
                            result["upper_bound"],
                            result["missing_count"],
                        )
                    )
            limitation_codes = list(reasons)
            if critical_finding:
                limitation_codes.append("LATER_CRITICAL_INTEGRITY_FINDING")
            payload: dict[str, Any] = {
                **self._envelope(REPORT_SCHEMA, sealed_at, self._new_id()),
                "epoch_ref": copy.deepcopy(self._epoch_ref),
                "verdict": verdict,
                "scheduled_attempt_refs": scheduled_refs,
                "qualification_refs": qualification_refs,
                "metric_refs": metric_refs,
                "missingness_bounds": missingness_bounds,
                "limitation_codes": sorted(set(limitation_codes)),
                "report_hash": "0" * 64,
                "sealed_at": sealed_at,
            }
            hash_payload = {
                key: value for key, value in payload.items() if key != "report_hash"
            }
            payload["report_hash"] = domain_separated_sha256(
                REPORT_HASH_DOMAIN,
                canonical_json_bytes(hash_payload),
            )
            try:
                validate_contract("ValidationReport", payload)
            except ContractValidationError as exc:
                raise ValidationAuthorityError(str(exc)) from exc
            self._report = copy.deepcopy(payload)
            return copy.deepcopy(payload)

    @property
    def report(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._report)
