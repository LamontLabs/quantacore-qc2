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

__all__ = [
    "BundleLimits",
    "PromotionBundleError",
    "SIGNATURE_ALGORITHM",
    "SIGNATURE_ENCODING",
    "SIGNATURE_PROFILE",
    "VerifiedPromotionBundle",
    "build_promotion_bundle_archive",
    "verify_promotion_bundle_archive",
]
