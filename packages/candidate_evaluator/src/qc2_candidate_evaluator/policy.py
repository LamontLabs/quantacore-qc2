"""Code-owned evaluation policy; candidates and trainers cannot provide policy data."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from qc2_contracts.runtime import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    version: str = "qc2-independent-evaluation-v1"
    decimal_places: int = 12
    calibration_bins: int = 10
    regression_baseline: str = "zero_prediction"
    classification_baseline: str = "fixed_probability_0.5"
    calibration_threshold_policy: str = "NOT_FROZEN"
    performance_policy: str = "REGRESSION_MUST_BEAT_DECLARED_BASELINE"


FROZEN_POLICY = EvaluationPolicy()
POLICY_HASH = hashlib.sha256(
    canonical_json_bytes(asdict(FROZEN_POLICY))
).hexdigest()


def policy_payload() -> dict[str, Any]:
    return {**asdict(FROZEN_POLICY), "policy_hash": POLICY_HASH}
