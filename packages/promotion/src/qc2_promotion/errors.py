"""Stable failure categories for independent promotion verification."""

from __future__ import annotations

from enum import StrEnum


class VerificationErrorCode(StrEnum):
    ARCHIVE_INVALID = "ARCHIVE_INVALID"
    BUNDLE_INVALID = "BUNDLE_INVALID"
    KEY_UNKNOWN = "KEY_UNKNOWN"
    KEY_ROLE_MISMATCH = "KEY_ROLE_MISMATCH"
    KEY_REVOKED = "KEY_REVOKED"
    KEY_NOT_ACTIVE = "KEY_NOT_ACTIVE"
    EVALUATOR_IDENTITY_MISMATCH = "EVALUATOR_IDENTITY_MISMATCH"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"
    LABEL_MISMATCH = "LABEL_MISMATCH"
    COMPATIBILITY_MISMATCH = "COMPATIBILITY_MISMATCH"
    POLICY_UNTRUSTED = "POLICY_UNTRUSTED"
    GATE_RECOMPUTATION_MISMATCH = "GATE_RECOMPUTATION_MISMATCH"
    MODEL_UNSAFE = "MODEL_UNSAFE"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"


class PromotionVerificationError(ValueError):
    """A verification failure with a stable machine-readable code."""

    def __init__(self, code: VerificationErrorCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail
