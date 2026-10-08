"""Deterministic offline feature authority for QC2."""

from .engine import compute_feature_snapshot
from .models import (
    ContractRef,
    DailyFeatureBar,
    FeatureInput,
    FeatureInputError,
    ProductionActivationDenied,
    SimilarityPrototype,
    TemporalAccessEvidence,
    TemporalLeakageError,
)
from .registry import (
    FeatureDefinitionSpec,
    FeatureProfile,
    FeatureRegistryBundle,
    ProductionActivationGrant,
    assert_profile_activation,
    build_feature_specs,
    fixture_daily_profile,
    materialize_feature_registry,
)

__all__ = [
    "ContractRef",
    "DailyFeatureBar",
    "FeatureDefinitionSpec",
    "FeatureInput",
    "FeatureInputError",
    "FeatureProfile",
    "FeatureRegistryBundle",
    "ProductionActivationDenied",
    "ProductionActivationGrant",
    "SimilarityPrototype",
    "TemporalAccessEvidence",
    "TemporalLeakageError",
    "assert_profile_activation",
    "build_feature_specs",
    "compute_feature_snapshot",
    "fixture_daily_profile",
    "materialize_feature_registry",
]
