"""QC2 immutable promotion bundle packaging and verification."""

from .bundle import (
    SIGNATURE_ALGORITHM,
    SIGNATURE_ENCODING,
    SIGNATURE_PROFILE,
    VerifiedPromotionBundle,
    build_promotion_bundle_archive,
    verify_promotion_bundle_archive,
)
from .limits import BundleLimits, PromotionBundleError
from .errors import PromotionVerificationError, VerificationErrorCode
from .trust import KeyRole, KeyRoleRegistry, VerificationKey
from .sandbox import CandidateProbeResult, SandboxLimits
from .verifier import (
    GateVerificationReceipt,
    PromotionVerificationPolicy,
    PromotionVerificationResult,
    verify_promotion_bundle,
)

__all__ = [
    "BundleLimits",
    "CandidateProbeResult",
    "GateVerificationReceipt",
    "KeyRole",
    "KeyRoleRegistry",
    "PromotionBundleError",
    "PromotionVerificationError",
    "PromotionVerificationPolicy",
    "PromotionVerificationResult",
    "SIGNATURE_ALGORITHM",
    "SIGNATURE_ENCODING",
    "SIGNATURE_PROFILE",
    "SandboxLimits",
    "VerifiedPromotionBundle",
    "VerificationErrorCode",
    "VerificationKey",
    "build_promotion_bundle_archive",
    "verify_promotion_bundle",
    "verify_promotion_bundle_archive",
]
