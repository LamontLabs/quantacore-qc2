"""Canonical run creation, complete row accounting, ranking, and sealing."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any, Protocol

from qc2_contracts.runtime import (
    assert_transition,
    canonical_content_hash,
    canonical_decimal_text,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    scientific_payload_hash,
    validate_contract,
    verify_content_hash,
)

from .models import (
    REFERENCE_SCHEMAS,
    FeatureRow,
    NormalizedBindings,
    PredictionAuthorityError,
    PredictionBindings,
    ScoreResult,
    _reference,
    _references,
    utc_instant,
    utc_text,
)

RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
ROW_SCHEMA = "qc2.models_prediction.Prediction.v1"
PAYLOAD_SCHEMA = "qc2.models_prediction.ScientificPredictionPayload.v1"
SEAL_SCHEMA = "qc2.models_prediction.PredictionSeal.v1"
SCHEDULE_SCHEMA = "qc2.validation.ScheduledAttempt.v1"
INVENTORY_HASH_DOMAIN = "qc2.prediction-inventory.v1"
BINDING_HASH_DOMAIN = "qc2.prediction-run-bindings.v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class PredictionInputPort(Protocol):
    """Atomic read port for the epoch's Champion and scientific dependencies."""

    def capture_bindings(
        self, epoch_ref: Mapping[str, Any], session_id: str
    ) -> PredictionBindings:
        """Read every run dependency from one serializable snapshot, without fallback."""


@dataclass(slots=True)
class _Scheduled:
    contract: dict[str, Any]


@dataclass(slots=True)
class _Run:
    contract: dict[str, Any]
    bindings: NormalizedBindings
    binding_document: dict[str, Any]
    binding_hash: str
    feature_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    current_scores: dict[str, ScoreResult] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    pending_attempt: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    scientific_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    seal: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SealResult:
    seal: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    scientific_payloads: Mapping[str, Mapping[str, Any]]
    on_time: bool
    production_activation_eligible: bool


class PredictionAuthority:
    """Owns the one frozen operating run and its irreversible scientific seal.

    This in-process implementation is the domain reference for the PostgreSQL
    constraints in the prediction migration. All mutating methods serialize
    through one lock; the production source port must separately provide the
    serializable, atomic read that pins upstream authority records.
    """

    def __init__(self, *, id_factory=new_uuidv7) -> None:
        self._id_factory = id_factory
        self._lock = RLock()
        self._scheduled: dict[str, _Scheduled] = {}
        self._schedule_keys: dict[tuple[str, str], str] = {}
        self._runs: dict[str, _Run] = {}
        self._run_keys: dict[tuple[str, str], str] = {}
        self._official_seals: dict[tuple[str, str], str] = {}

    def schedule_sessions(
        self,
        *,
        epoch_ref: Mapping[str, Any],
        session_ids: Sequence[str],
        deadlines: Mapping[str, str],
        created_at: str,
        evidence_class: str,
        environment_namespace: str,
    ) -> tuple[dict[str, Any], ...]:
        """Create one immutable schedule fact for every expected exchange session."""
        epoch = _reference(
            epoch_ref,
            REFERENCE_SCHEMAS["epoch"],
            "epoch_ref",
            require_content_hash=True,
        )
        if not session_ids or tuple(session_ids) != tuple(sorted(set(session_ids))):
            raise PredictionAuthorityError("scheduled sessions must be sorted and unique")
        created_instant = utc_instant(created_at, "created_at")
        created = utc_text(created_instant)
        normalized_sessions: list[tuple[str, str]] = []
        for session_id in session_ids:
            try:
                if datetime.fromisoformat(session_id).date().isoformat() != session_id:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise PredictionAuthorityError("scheduled session must be an ISO date") from exc
            if session_id not in deadlines:
                raise PredictionAuthorityError(f"scheduled session {session_id} has no deadline")
            deadline_instant = utc_instant(deadlines[session_id], "expected_deadline")
            if deadline_instant < created_instant:
                raise PredictionAuthorityError("schedule deadline cannot precede schedule creation")
            normalized_sessions.append((session_id, utc_text(deadline_instant)))

        contracts: list[dict[str, Any]] = []
        staged: list[tuple[tuple[str, str], _Scheduled]] = []
        with self._lock:
            for session_id, deadline in normalized_sessions:
                key = (epoch["target_id"], session_id)
                existing_id = self._schedule_keys.get(key)
                if existing_id is not None:
                    existing = self._scheduled[existing_id].contract
                    if existing["expected_deadline"] != deadline:
                        raise PredictionAuthorityError("scheduled session deadline is immutable")
                    contracts.append(copy.deepcopy(existing))
                    continue
                contract = {
                    "schema_name": SCHEDULE_SCHEMA,
                    "schema_version": "1.0",
                    "id": self._id_factory(),
                    "created_at": created,
                    "owning_authority": "validation",
                    "evidence_class": evidence_class,
                    "environment_namespace": environment_namespace,
                    "source_refs": [],
                    "epoch_ref": dict(epoch),
                    "session_id": session_id,
                    "schedule_created_at": created,
                    "expected_deadline": deadline,
                    "attempt_state": "SCHEDULED",
                    "run_ref": None,
                    "missed_reason": None,
                }
                validate_contract("ScheduledAttempt", contract)
                staged.append((key, _Scheduled(contract)))
                contracts.append(copy.deepcopy(contract))
            for key, scheduled in staged:
                self._scheduled[scheduled.contract["id"]] = scheduled
                self._schedule_keys[key] = scheduled.contract["id"]
        return tuple(contracts)

    def reconcile_missed_starts(self, *, observed_at: str) -> tuple[dict[str, Any], ...]:
        """Append MISSED_START facts for elapsed sessions with no worker start."""
        observed = utc_instant(observed_at, "observed_at")
        reconciled: list[dict[str, Any]] = []
        with self._lock:
            for scheduled in self._scheduled.values():
                contract = scheduled.contract
                if (
                    contract["attempt_state"] == "SCHEDULED"
                    and utc_instant(contract["expected_deadline"], "expected_deadline") <= observed
                ):
                    candidate = copy.deepcopy(contract)
                    candidate["attempt_state"] = "MISSED_START"
                    candidate["missed_reason"] = "worker_not_started_by_expected_deadline"
                    validate_contract("ScheduledAttempt", candidate)
                    scheduled.contract = candidate
                    reconciled.append(copy.deepcopy(candidate))
        return tuple(reconciled)

    def create_run(
        self,
        *,
        scheduled_attempt_id: str,
        source: PredictionInputPort,
        created_at: str,
    ) -> dict[str, Any]:
        """Atomically bind all run inputs before features or inference may begin."""
        created = utc_text(utc_instant(created_at, "created_at"))
        with self._lock:
            scheduled = self._scheduled.get(scheduled_attempt_id)
            if scheduled is None:
                raise PredictionAuthorityError("scheduled attempt does not exist")
            scheduled_contract = scheduled.contract
            if scheduled_contract["attempt_state"] != "SCHEDULED":
                raise PredictionAuthorityError("scheduled attempt is not available to start")
            if utc_instant(created, "created_at") > utc_instant(
                scheduled_contract["expected_deadline"], "expected_deadline"
            ):
                raise PredictionAuthorityError("scheduled attempt missed its start deadline")
            key = (scheduled_contract["epoch_ref"]["target_id"], scheduled_contract["session_id"])
            if key in self._run_keys:
                raise PredictionAuthorityError("canonical run already exists for this epoch session")

            raw_bindings = source.capture_bindings(
                copy.deepcopy(scheduled_contract["epoch_ref"]),
                scheduled_contract["session_id"],
            )
            if not isinstance(raw_bindings, PredictionBindings):
                raise PredictionAuthorityError("input port returned no typed binding snapshot")
            bindings = raw_bindings.normalized()
            if (
                bindings.session_id != scheduled_contract["session_id"]
                or bindings.refs["epoch_ref"]["target_id"]
                != scheduled_contract["epoch_ref"]["target_id"]
            ):
                raise PredictionAuthorityError("binding snapshot does not match scheduled session")
            if (
                bindings.environment_namespace != scheduled_contract["environment_namespace"]
                or bindings.evidence_class != scheduled_contract["evidence_class"]
            ):
                raise PredictionAuthorityError("scheduled attempt and run evidence contexts differ")
            if utc_instant(bindings.pointer["transitioned_at"], "ChampionPointer.transitioned_at") > utc_instant(
                created, "created_at"
            ):
                raise PredictionAuthorityError("ChampionPointer was transitioned after run creation")
            if utc_instant(bindings.pointer["created_at"], "ChampionPointer.created_at") > utc_instant(
                created, "created_at"
            ):
                raise PredictionAuthorityError("ChampionPointer was created after run creation")

            run_id = self._id_factory()
            run_ref = {
                "target_schema_name": RUN_SCHEMA,
                "target_id": run_id,
            }
            contract = {
                "schema_name": RUN_SCHEMA,
                "schema_version": "1.0",
                "id": run_id,
                "created_at": created,
                "owning_authority": "prediction",
                "evidence_class": bindings.evidence_class,
                "environment_namespace": bindings.environment_namespace,
                "source_refs": bindings.source_refs(),
                "epoch_ref": dict(bindings.refs["epoch_ref"]),
                "session_id": bindings.session_id,
                "snapshot_ref": dict(bindings.refs["snapshot_ref"]),
                "dependency_refs": bindings.dependency_refs(),
                "decision_deadline": bindings.decision_deadline,
                "seal_deadline": bindings.seal_deadline,
                "run_state": "CREATED",
                "generation": bindings.champion_generation,
            }
            validate_contract("PredictionRun", contract)
            assert_transition("PredictionRun", "CREATED", "INPUTS_BOUND")
            contract["run_state"] = "INPUTS_BOUND"
            validate_contract("PredictionRun", contract)
            binding_document = bindings.binding_document()
            binding_hash = domain_separated_sha256(
                BINDING_HASH_DOMAIN, canonical_json_bytes(binding_document)
            )
            if not SHA256_PATTERN.fullmatch(binding_hash):
                raise PredictionAuthorityError("binding snapshot hash is invalid")

            updated_scheduled = copy.deepcopy(scheduled_contract)
            updated_scheduled["attempt_state"] = "STARTED"
            updated_scheduled["run_ref"] = run_ref
            validate_contract("ScheduledAttempt", updated_scheduled)
            self._runs[run_id] = _Run(
                contract=contract,
                bindings=bindings,
                binding_document=binding_document,
                binding_hash=binding_hash,
            )
            self._run_keys[key] = run_id
            scheduled.contract = updated_scheduled
            return self.get_run(run_id)

    def record_feature_rows(
        self,
        *,
        run_id: str,
        feature_rows: Sequence[FeatureRow],
    ) -> None:
        """Commit feature/protocol/head references for every frozen eligible instrument."""
        with self._lock:
            run = self._require_run(run_id, "INPUTS_BOUND")
            normalized: dict[str, dict[str, Any]] = {}
            for row in feature_rows:
                if not isinstance(row, FeatureRow):
                    raise PredictionAuthorityError("feature input must use FeatureRow records")
                instrument_ref = _reference(
                    row.instrument_ref,
                    REFERENCE_SCHEMAS["instrument"],
                    "instrument_ref",
                    require_content_hash=True,
                )
                instrument_id = instrument_ref["target_id"]
                if instrument_id in normalized:
                    raise PredictionAuthorityError("feature rows contain duplicate instruments")
                if instrument_id not in run.bindings.eligible_instrument_ids:
                    raise PredictionAuthorityError("feature row is outside the frozen eligible set")
                if not isinstance(row.reference_price, str):
                    raise PredictionAuthorityError("reference_price must be an exact decimal string")
                try:
                    reference_price = Decimal(row.reference_price)
                except InvalidOperation as exc:
                    raise PredictionAuthorityError("reference_price is not a decimal") from exc
                if not reference_price.is_finite() or reference_price <= 0:
                    raise PredictionAuthorityError("reference_price must be finite and positive")
                horizon_refs = _references(
                    row.horizon_label_refs,
                    "qc2.scientific_definitions.LabelDefinition.v1",
                    "horizon_label_refs",
                    require_content_hash=True,
                )
                if not horizon_refs:
                    raise PredictionAuthorityError("each prediction row requires a label reference")
                head_refs = _references(
                    row.head_output_refs,
                    "qc2.models_prediction.ModelHeadOutput.v1",
                    "head_output_refs",
                    require_content_hash=True,
                )
                feature_ref = _reference(
                    row.feature_snapshot_ref,
                    "qc2.scientific_definitions.FeatureSnapshot.v1",
                    "feature_snapshot_ref",
                    require_content_hash=True,
                )
                protocol_refs = _references(
                    row.protocol_result_refs,
                    "qc2.scientific_definitions.RunnerProtocolResult.v1",
                    "protocol_result_refs",
                    require_content_hash=True,
                )
                allowed_learned_schemas = {
                    "qc2.outcomes_research.RunnerGenome.v1",
                    "qc2.outcomes_research.FailureGenome.v1",
                    "qc2.outcomes_research.MemoryIndexManifest.v1",
                    "qc2.outcomes_research.MatchedDecoySet.v1",
                }
                learned_refs_list: list[dict[str, str]] = []
                for index, value in enumerate(row.learned_memory_refs):
                    if not isinstance(value, Mapping):
                        raise PredictionAuthorityError(
                            f"learned_memory_refs[{index}] must be a reference object"
                        )
                    schema = value.get("target_schema_name")
                    if schema not in allowed_learned_schemas:
                        raise PredictionAuthorityError(
                            "learned memory reference type is not permitted"
                        )
                    learned_refs_list.append(
                        _reference(
                            value,
                            schema,
                            f"learned_memory_refs[{index}]",
                            require_content_hash=True,
                        )
                    )
                learned_refs = tuple(learned_refs_list)
                normalized[instrument_id] = {
                    "instrument_ref": instrument_ref,
                    "reference_kind": row.reference_kind,
                    "reference_price": canonical_decimal_text(row.reference_price),
                    "horizon_label_refs": list(horizon_refs),
                    "head_output_refs": list(head_refs),
                    "feature_snapshot_ref": feature_ref,
                    "protocol_result_refs": list(protocol_refs),
                    "learned_memory_refs": list(learned_refs),
                }
            expected_ids = set(run.bindings.eligible_instrument_ids)
            if set(normalized) != expected_ids:
                missing = sorted(expected_ids - set(normalized))
                extra = sorted(set(normalized) - expected_ids)
                raise PredictionAuthorityError(
                    f"feature row coverage differs from frozen universe; missing={missing}, extra={extra}"
                )
            run.feature_rows = normalized
            self._transition(run, "FEATURES_COMPLETE")

    def record_scores(
        self,
        *,
        run_id: str,
        score_results: Mapping[str, ScoreResult],
        completed_at: str,
    ) -> None:
        """Store the first complete score attempt without dropping unscorable rows."""
        completed = utc_text(utc_instant(completed_at, "completed_at"))
        with self._lock:
            run = self._require_run(run_id, "FEATURES_COMPLETE")
            if set(score_results) != set(run.bindings.eligible_instrument_ids):
                raise PredictionAuthorityError("initial score attempt must account for every eligible row")
            normalized = {
                instrument_id: self._normalize_score(result)
                for instrument_id, result in score_results.items()
            }
            run.current_scores = normalized
            run.attempts.append(
                {
                    "attempt_number": 1,
                    "attempt_event": "COMPLETED",
                    "attempt_state": "COMPLETED",
                    "started_at": completed,
                    "completed_at": completed,
                    "results": self._attempt_results(normalized),
                }
            )
            self._transition(run, "SCORED")

    def begin_repair_attempt(
        self,
        *,
        run_id: str,
        instrument_ids: Sequence[str],
        started_at: str,
    ) -> dict[str, Any]:
        """Begin the only permitted retry: sorted repair of currently unscorable rows."""
        started = utc_text(utc_instant(started_at, "started_at"))
        with self._lock:
            run = self._require_run(run_id, "SCORED")
            if run.pending_attempt is not None:
                raise PredictionAuthorityError("another deterministic repair attempt is active")
            attempt_number = max(
                item["attempt_number"] for item in run.attempts
            ) + 1
            policy = run.bindings.retry_policy
            if attempt_number > policy.max_attempts:
                raise PredictionAuthorityError("run retry budget is exhausted")
            repairable = tuple(
                sorted(
                    (
                        instrument_id
                        for instrument_id, result in run.current_scores.items()
                        if result.score is None
                        and result.reason_code in policy.retryable_reason_codes
                    ),
                    key=lambda item: item.encode("utf-8"),
                )
            )
            requested = tuple(instrument_ids)
            if requested != repairable or not requested:
                raise PredictionAuthorityError(
                    "repair must request exactly the unresolved retryable rows in stable ID order"
                )
            attempt = {
                "attempt_number": attempt_number,
                "attempt_state": "STARTED",
                "started_at": started,
                "instrument_ids": list(requested),
            }
            run.attempts.append(
                {
                    **copy.deepcopy(attempt),
                    "attempt_event": "STARTED",
                }
            )
            run.pending_attempt = attempt
            return copy.deepcopy(attempt)

    def complete_repair_attempt(
        self,
        *,
        run_id: str,
        score_results: Mapping[str, ScoreResult],
        completed_at: str,
    ) -> None:
        """Repair only missing rows; an existing score can never be overwritten."""
        completed = utc_text(utc_instant(completed_at, "completed_at"))
        with self._lock:
            run = self._require_run(run_id, "SCORED")
            pending = run.pending_attempt
            if pending is None:
                raise PredictionAuthorityError("there is no repair attempt in progress")
            expected = set(pending["instrument_ids"])
            if set(score_results) != expected:
                raise PredictionAuthorityError("repair result coverage differs from requested rows")
            if utc_instant(completed, "completed_at") < utc_instant(
                pending["started_at"], "started_at"
            ):
                raise PredictionAuthorityError("repair completion precedes its start")
            normalized = {
                instrument_id: self._normalize_score(result)
                for instrument_id, result in score_results.items()
            }
            for instrument_id in expected:
                existing = run.current_scores[instrument_id]
                if existing.score is not None:
                    raise PredictionAuthorityError("a scored row cannot be replaced by a retry")
                run.current_scores[instrument_id] = normalized[instrument_id]
            run.attempts.append(
                {
                    "attempt_number": pending["attempt_number"],
                    "attempt_event": "COMPLETED",
                    "attempt_state": "COMPLETED",
                    "started_at": pending["started_at"],
                    "completed_at": completed,
                    "results": self._attempt_results(normalized),
                }
            )
            run.pending_attempt = None

    def rank(self, *, run_id: str, created_at: str) -> tuple[dict[str, Any], ...]:
        """Materialize the full deterministic ranking and scientific row payloads."""
        created = utc_text(utc_instant(created_at, "created_at"))
        with self._lock:
            run = self._require_run(run_id, "SCORED")
            if run.pending_attempt is not None:
                raise PredictionAuthorityError("cannot rank while a repair attempt is active")
            if set(run.current_scores) != set(run.bindings.eligible_instrument_ids):
                raise PredictionAuthorityError("score ledger does not cover the frozen eligible set")

            scored = sorted(
                (
                    instrument_id
                    for instrument_id, result in run.current_scores.items()
                    if result.score is not None
                ),
                key=lambda instrument_id: (
                    -Decimal(run.current_scores[instrument_id].score or "0"),
                    instrument_id.encode("utf-8"),
                ),
            )
            unscorable = sorted(
                (
                    instrument_id
                    for instrument_id, result in run.current_scores.items()
                    if result.score is None
                ),
                key=lambda instrument_id: instrument_id.encode("utf-8"),
            )
            ranks = {instrument_id: rank for rank, instrument_id in enumerate(scored, start=1)}
            rows: list[dict[str, Any]] = []
            payloads: dict[str, dict[str, Any]] = {}
            for instrument_id in (*scored, *unscorable):
                feature_row = run.feature_rows[instrument_id]
                score_result = run.current_scores[instrument_id]
                row_id = self._id_factory()
                disposition = "SCORED" if score_result.score is not None else "UNSCORABLE"
                row_contract: dict[str, Any] = {
                    "schema_name": ROW_SCHEMA,
                    "schema_version": "1.0",
                    "id": row_id,
                    "created_at": created,
                    "owning_authority": "prediction",
                    "evidence_class": run.bindings.evidence_class,
                    "environment_namespace": run.bindings.environment_namespace,
                    "source_refs": [],
                    "content_hash": "0" * 64,
                    "run_ref": {"target_schema_name": RUN_SCHEMA, "target_id": run_id},
                    "session_id": run.bindings.session_id,
                    "instrument_ref": feature_row["instrument_ref"],
                    "reference_kind": feature_row["reference_kind"],
                    "reference_price": feature_row["reference_price"],
                    "horizon_label_refs": feature_row["horizon_label_refs"],
                    "head_output_refs": feature_row["head_output_refs"],
                    "feature_snapshot_ref": feature_row["feature_snapshot_ref"],
                    "protocol_result_refs": feature_row["protocol_result_refs"],
                    "score_manifest_ref": dict(run.bindings.refs["score_manifest_ref"]),
                    "score": score_result.score,
                    "rank": ranks.get(instrument_id),
                    "disposition": disposition,
                    "unscorable_reason": score_result.reason_code,
                    "model_ref": dict(run.bindings.refs["operating_model_ref"]),
                    "learned_memory_refs": feature_row["learned_memory_refs"],
                    "epoch_ref": dict(run.bindings.refs["epoch_ref"]),
                }
                row_contract["content_hash"] = canonical_content_hash("Prediction", row_contract)
                validate_contract("Prediction", row_contract)
                verify_content_hash("Prediction", row_contract)
                rows.append(row_contract)
                if disposition == "SCORED":
                    payload = self._scientific_payload(
                        run=run,
                        row_id=row_id,
                        feature_row=feature_row,
                        instrument_id=instrument_id,
                        score=score_result.score or "",
                        rank=ranks[instrument_id],
                        created_at=created,
                    )
                    payloads[instrument_id] = payload
            if len(rows) != len(run.bindings.eligible_instrument_ids):
                raise PredictionAuthorityError("rank materialization dropped an eligible row")
            run.rows = rows
            run.scientific_payloads = payloads
            self._transition(run, "RANKED")
            return tuple(copy.deepcopy(rows))

    def seal(
        self,
        *,
        run_id: str,
        sealed_at: str,
        evidence_refs: Sequence[Mapping[str, Any]],
    ) -> SealResult:
        """Seal once; a late completion is preserved as DIAGNOSTIC, never official."""
        sealed = utc_text(utc_instant(sealed_at, "sealed_at"))
        refs = _references(
            evidence_refs,
            "qc2.integrity_build.EvidenceEvent.v1",
            "evidence_refs",
            require_content_hash=True,
        )
        if not refs:
            raise PredictionAuthorityError("prediction seal requires evidence references")
        with self._lock:
            run = self._require_run(run_id, "RANKED")
            if run.seal is not None:
                raise PredictionAuthorityError("prediction run is already sealed")
            session_key = (
                run.bindings.refs["epoch_ref"]["target_id"],
                run.bindings.session_id,
            )
            decision_deadline = utc_instant(run.bindings.decision_deadline, "decision_deadline")
            seal_deadline = utc_instant(run.bindings.seal_deadline, "seal_deadline")
            actual = utc_instant(sealed, "sealed_at")
            on_time = actual <= decision_deadline and actual <= seal_deadline
            role = "OPERATING" if on_time else "DIAGNOSTIC"
            if role == "OPERATING" and session_key in self._official_seals:
                raise PredictionAuthorityError("official operating seal already exists")
            inventory = [
                {
                    "instrument_id": row["instrument_ref"]["target_id"],
                    "prediction_ref": {
                        "target_schema_name": ROW_SCHEMA,
                        "target_id": row["id"],
                        "content_hash": row["content_hash"],
                    },
                    "disposition": row["disposition"],
                    "rank": row["rank"],
                    "unscorable_reason": row["unscorable_reason"],
                    "scientific_payload_hash": (
                        scientific_payload_hash(
                            run.scientific_payloads[row["instrument_ref"]["target_id"]]
                        )
                        if row["disposition"] == "SCORED"
                        else None
                    ),
                }
                for row in run.rows
            ]
            inventory_hash = domain_separated_sha256(
                INVENTORY_HASH_DOMAIN, canonical_json_bytes(inventory)
            )
            counts: dict[str, int] = {"SCORED": 0, "UNSCORABLE": 0}
            for row in run.rows:
                counts[row["disposition"]] += 1
            seal_contract: dict[str, Any] = {
                "schema_name": SEAL_SCHEMA,
                "schema_version": "1.0",
                "id": self._id_factory(),
                "created_at": sealed,
                "owning_authority": "prediction",
                "evidence_class": run.bindings.evidence_class,
                "environment_namespace": run.bindings.environment_namespace,
                "source_refs": [],
                "content_hash": "0" * 64,
                "run_ref": {"target_schema_name": RUN_SCHEMA, "target_id": run_id},
                "session_id": run.bindings.session_id,
                "role": role,
                "ordered_prediction_refs": [
                    {
                        "target_schema_name": ROW_SCHEMA,
                        "target_id": row["id"],
                        "content_hash": row["content_hash"],
                    }
                    for row in run.rows
                ],
                "disposition_counts": [
                    f"{name}={counts[name]}" for name in sorted(counts)
                ],
                "payload_inventory_hash": inventory_hash,
                "deadline": run.bindings.seal_deadline,
                "sealed_at": sealed,
                "evidence_refs": [dict(ref) for ref in refs],
            }
            seal_contract["content_hash"] = canonical_content_hash(
                "PredictionSeal", seal_contract
            )
            validate_contract("PredictionSeal", seal_contract)
            verify_content_hash("PredictionSeal", seal_contract)

            self._transition(run, "SEALED")
            run.seal = seal_contract
            if role == "OPERATING":
                self._official_seals[session_key] = seal_contract["id"]
            scheduled_id = self._schedule_keys[session_key]
            scheduled = self._scheduled[scheduled_id].contract
            scheduled["attempt_state"] = "SEALED" if role == "OPERATING" else "NONQUALIFYING"
            validate_contract("ScheduledAttempt", scheduled)
            production_eligible = (
                role == "OPERATING"
                and run.bindings.evidence_class == "FORWARD_SEALED"
                and run.bindings.environment_namespace == "production"
            )
            return SealResult(
                seal=copy.deepcopy(seal_contract),
                rows=tuple(copy.deepcopy(run.rows)),
                scientific_payloads=copy.deepcopy(run.scientific_payloads),
                on_time=on_time,
                production_activation_eligible=production_eligible,
            )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise PredictionAuthorityError("prediction run does not exist")
            return {
                "contract": copy.deepcopy(run.contract),
                "binding_snapshot": copy.deepcopy(run.binding_document),
                "binding_hash": run.binding_hash,
                "attempts": copy.deepcopy(run.attempts),
                "sealed": run.seal is not None,
            }

    def get_scheduled_attempt(self, scheduled_attempt_id: str) -> dict[str, Any]:
        with self._lock:
            scheduled = self._scheduled.get(scheduled_attempt_id)
            if scheduled is None:
                raise PredictionAuthorityError("scheduled attempt does not exist")
            return copy.deepcopy(scheduled.contract)

    def _require_run(self, run_id: str, expected_state: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise PredictionAuthorityError("prediction run does not exist")
        if run.contract["run_state"] != expected_state:
            raise PredictionAuthorityError(
                f"run must be {expected_state}; found {run.contract['run_state']}"
            )
        return run

    @staticmethod
    def _transition(run: _Run, new_state: str) -> None:
        old_state = run.contract["run_state"]
        assert_transition("PredictionRun", old_state, new_state)
        updated = copy.deepcopy(run.contract)
        updated["run_state"] = new_state
        validate_contract("PredictionRun", updated)
        run.contract = updated

    @staticmethod
    def _normalize_score(result: ScoreResult) -> ScoreResult:
        if not isinstance(result, ScoreResult):
            raise PredictionAuthorityError("score attempt must contain ScoreResult values")
        if result.score is None:
            if not isinstance(result.reason_code, str) or not re.fullmatch(
                r"[a-z][a-z0-9_-]{0,95}", result.reason_code
            ):
                raise PredictionAuthorityError("unscorable rows require a reason code")
            return ScoreResult(score=None, reason_code=result.reason_code)
        if result.reason_code is not None:
            raise PredictionAuthorityError("scored rows cannot carry an unscorable reason")
        if not isinstance(result.score, str):
            raise PredictionAuthorityError("scores must be exact decimal strings")
        try:
            decimal_score = Decimal(result.score)
        except InvalidOperation as exc:
            raise PredictionAuthorityError("score is not a decimal") from exc
        if not decimal_score.is_finite():
            raise PredictionAuthorityError("score must be finite")
        return ScoreResult(score=canonical_decimal_text(result.score, precision=6))

    @staticmethod
    def _attempt_results(results: Mapping[str, ScoreResult]) -> list[dict[str, Any]]:
        return [
            {
                "instrument_id": instrument_id,
                "disposition": "SCORED" if result.score is not None else "UNSCORABLE",
                "score": result.score,
                "reason_code": result.reason_code,
            }
            for instrument_id, result in sorted(
                results.items(), key=lambda item: item[0].encode("utf-8")
            )
        ]

    def _scientific_payload(
        self,
        *,
        run: _Run,
        row_id: str,
        feature_row: Mapping[str, Any],
        instrument_id: str,
        score: str,
        rank: int,
        created_at: str,
    ) -> dict[str, Any]:
        model_ref = dict(run.bindings.refs["operating_model_ref"])
        dependency_refs = [
            dict(feature_row["feature_snapshot_ref"]),
            *[dict(item) for item in feature_row["protocol_result_refs"]],
            dict(run.bindings.refs["score_manifest_ref"]),
            model_ref,
            *[
                dict(item)
                for item in run.bindings.collections["memory_index_refs"]
            ],
            dict(run.bindings.refs["epoch_ref"]),
        ]
        unique: dict[tuple[str, str], dict[str, str]] = {}
        for ref in dependency_refs:
            key = (ref["target_schema_name"], ref["target_id"])
            prior = unique.get(key)
            if prior is not None and prior != ref:
                raise PredictionAuthorityError(
                    "scientific payload has conflicting dependency references"
                )
            unique[key] = ref
        payload: dict[str, Any] = {
            "schema_name": PAYLOAD_SCHEMA,
            "schema_version": "1.0",
            "id": self._id_factory(),
            "created_at": created_at,
            "owning_authority": "prediction",
            "evidence_class": run.bindings.evidence_class,
            "environment_namespace": run.bindings.environment_namespace,
            "source_refs": [],
            "content_hash": "0" * 64,
            "session_id": run.bindings.session_id,
            "reference_kind": feature_row["reference_kind"],
            "reference_price": feature_row["reference_price"],
            "instrument_ref": dict(feature_row["instrument_ref"]),
            "horizon_label_refs": copy.deepcopy(feature_row["horizon_label_refs"]),
            "head_output_refs": copy.deepcopy(feature_row["head_output_refs"]),
            "dependency_refs": [
                unique[key]
                for key in sorted(unique, key=lambda pair: (pair[0].encode(), pair[1].encode()))
            ],
            "score": score,
            "rank": rank,
            "disposition": "SCORED",
            "model_hash": model_ref["content_hash"],
            "epoch_ref": dict(run.bindings.refs["epoch_ref"]),
            "regime": run.bindings.regime,
        }
        payload["content_hash"] = canonical_content_hash(
            "ScientificPredictionPayload", payload
        )
        validate_contract("ScientificPredictionPayload", payload)
        verify_content_hash("ScientificPredictionPayload", payload)
        if scientific_payload_hash(payload) != payload["content_hash"]:
            raise PredictionAuthorityError(
                f"scientific payload hash mismatch for instrument {instrument_id}"
            )
        return payload
