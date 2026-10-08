"""Evidence-anchor adapter boundary for immutable prediction seals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from qc2_contracts.runtime import (
    ContractValidationError,
    validate_contract,
    verify_content_hash,
)
from qc2_integrity_build.verification import (
    INDEPENDENT_PROOF_LEVEL,
    AnchorPort,
    CheckpointRecord,
    VerificationStatus,
    verify_checkpoint_chain,
)


class PredictionAnchorError(ValueError):
    """The supplied checkpoint or anchor receipt does not prove the prediction seal."""


@dataclass(frozen=True, slots=True)
class PredictionAnchorResult:
    seal_id: str
    checkpoint_id: str
    receipt: Mapping[str, Any]
    signature_verified: bool
    on_time: bool
    independent_preoutcome: bool
    operating_seal: bool

    @property
    def qualification_eligible(self) -> bool:
        return (
            self.signature_verified
            and self.on_time
            and self.independent_preoutcome
            and self.operating_seal
        )


async def anchor_prediction_seal(
    *,
    seal: Mapping[str, Any],
    checkpoint: CheckpointRecord,
    anchor_port: AnchorPort,
    next_outcome_session_start: str,
) -> PredictionAnchorResult:
    """Submit and verify a checkpoint that explicitly inventories the sealed run.

    The port owns provider selection, key custody, signing and receipt
    verification. A locally chained checkpoint is retained but is not treated
    as an independent pre-outcome anchor.
    """
    seal_record = dict(seal)
    if not isinstance(checkpoint, CheckpointRecord):
        raise PredictionAnchorError("checkpoint must include its immutable artifact inventory")
    checkpoint_contract = dict(checkpoint.checkpoint_contract)
    try:
        validate_contract("PredictionSeal", seal_record)
        verify_content_hash("PredictionSeal", seal_record)
        checkpoint_result = verify_checkpoint_chain([checkpoint])
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        raise PredictionAnchorError("seal or checkpoint contract is invalid") from exc
    if checkpoint_result.status is VerificationStatus.FAILED:
        raise PredictionAnchorError("checkpoint hash chain or artifact root is invalid")
    expected_ref = {
        "target_schema_name": seal_record["schema_name"],
        "target_id": seal_record["id"],
        "content_hash": seal_record["content_hash"],
    }
    if expected_ref not in checkpoint.artifact_refs:
        raise PredictionAnchorError("checkpoint inventory does not include this exact seal")
    if (
        checkpoint_contract["evidence_class"] != seal_record["evidence_class"]
        or checkpoint_contract["environment_namespace"]
        != seal_record["environment_namespace"]
    ):
        raise PredictionAnchorError("checkpoint evidence context differs from the sealed run")
    if checkpoint_contract["created_at"] < seal_record["sealed_at"]:
        raise PredictionAnchorError("checkpoint predates the prediction seal")

    receipt = await anchor_port.submit_checkpoint(checkpoint_contract)
    if not isinstance(receipt, Mapping):
        raise PredictionAnchorError("anchor port returned no receipt")
    receipt_record = dict(receipt)
    try:
        validate_contract("AnchorReceipt", receipt_record)
    except ContractValidationError as exc:
        raise PredictionAnchorError("anchor port returned an invalid receipt") from exc
    checkpoint_ref = receipt_record["checkpoint_ref"]
    if (
        checkpoint_ref["target_schema_name"] != checkpoint_contract["schema_name"]
        or checkpoint_ref["target_id"] != checkpoint_contract["id"]
        or checkpoint_ref.get("content_hash") != checkpoint_contract["content_hash"]
    ):
        raise PredictionAnchorError("anchor receipt does not identify the submitted checkpoint")
    if (
        receipt_record["evidence_class"] != checkpoint_contract["evidence_class"]
        or receipt_record["environment_namespace"]
        != checkpoint_contract["environment_namespace"]
    ):
        raise PredictionAnchorError("anchor receipt evidence context differs from the checkpoint")
    verified = await anchor_port.verify_receipt(checkpoint_contract, receipt_record)
    if verified is not True:
        raise PredictionAnchorError("anchor port did not verify the receipt")
    try:
        accepted_at = datetime.fromisoformat(receipt_record["accepted_at"].replace("Z", "+00:00"))
        observed_at = datetime.fromisoformat(receipt_record["observed_at"].replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(seal_record["deadline"].replace("Z", "+00:00"))
        seal_at = datetime.fromisoformat(seal_record["sealed_at"].replace("Z", "+00:00"))
        next_outcome = datetime.fromisoformat(
            next_outcome_session_start.replace("Z", "+00:00")
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PredictionAnchorError("anchor timestamps must be valid UTC instants") from exc
    if any(
        value.utcoffset() is None or value.utcoffset().total_seconds() != 0
        for value in (accepted_at, observed_at, deadline, seal_at, next_outcome)
    ):
        raise PredictionAnchorError("anchor timestamps must use UTC")
    if observed_at < accepted_at or accepted_at < seal_at or deadline >= next_outcome:
        raise PredictionAnchorError("anchor receipt timing is inconsistent or outside the outcome fence")
    on_time = accepted_at <= deadline and accepted_at < next_outcome
    independent = (
        receipt_record["proof_level"] == INDEPENDENT_PROOF_LEVEL
        and checkpoint_contract["evidence_class"] == "FORWARD_SEALED"
    )
    return PredictionAnchorResult(
        seal_id=seal_record["id"],
        checkpoint_id=checkpoint_contract["id"],
        receipt=receipt_record,
        signature_verified=True,
        on_time=on_time,
        independent_preoutcome=independent,
        operating_seal=seal_record["role"] == "OPERATING",
    )
