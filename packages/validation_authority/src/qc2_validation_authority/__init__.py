"""QC2 prospective validation authority."""

from .authority import ValidationAuthority
from .metrics import (
    METRIC_SPECIFICATIONS,
    PRIMARY_K,
    MetricSpecification,
    compute_session_metrics,
    mean_session_estimates,
)
from .models import (
    IntegrityFinding,
    MetricEstimate,
    OutcomeObservation,
    PredictionObservation,
    QualificationAssessment,
    QualificationEvidence,
    SessionMetricBundle,
    SplitRow,
    SplitValidation,
    ValidationAuthorityError,
)
from .splitting import validate_temporal_split
from .statistics import (
    MINIMUM_INITIAL_RESAMPLES,
    ClosureDecision,
    ClosureEvidence,
    DependenceEstimate,
    DependenceMethod,
    DependenceReadiness,
    FrozenAnalysisPlan,
    assess_dependence_readiness,
    decide_closure,
    normalize_public_verdict,
)

__all__ = [
    "MINIMUM_INITIAL_RESAMPLES",
    "METRIC_SPECIFICATIONS",
    "PRIMARY_K",
    "ClosureDecision",
    "ClosureEvidence",
    "DependenceEstimate",
    "DependenceMethod",
    "DependenceReadiness",
    "FrozenAnalysisPlan",
    "IntegrityFinding",
    "MetricEstimate",
    "MetricSpecification",
    "OutcomeObservation",
    "PredictionObservation",
    "QualificationAssessment",
    "QualificationEvidence",
    "SessionMetricBundle",
    "SplitRow",
    "SplitValidation",
    "ValidationAuthority",
    "ValidationAuthorityError",
    "assess_dependence_readiness",
    "compute_session_metrics",
    "decide_closure",
    "mean_session_estimates",
    "normalize_public_verdict",
    "validate_temporal_split",
]
