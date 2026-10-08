"""Feature definitions, parameter profiles, ordering, and contract materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Mapping

from qc2_contracts.runtime import canonical_content_hash, validate_contract, verify_content_hash

from .models import (
    ContractRef,
    FeatureInputError,
    ProductionActivationDenied,
    as_date,
    as_utc,
    require_sha256,
)

FEATURE_DEFINITION_SCHEMA = "qc2.scientific_definitions.FeatureDefinition.v1"
FEATURE_REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")


@dataclass(frozen=True, slots=True)
class FeatureProfile:
    profile_key: str
    parameter_values: tuple[tuple[str, int], ...]
    fixture_only: bool
    calibration_receipt_hash: str | None = None

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.profile_key):
            raise FeatureInputError("profile_key must be a lowercase slug")
        if type(self.fixture_only) is not bool:
            raise FeatureInputError("fixture_only must be a bool")
        items = tuple(sorted(self.parameter_values))
        if len({key for key, _ in items}) != len(items):
            raise FeatureInputError("profile parameters must have unique names")
        for key, value in items:
            if not _SLUG.fullmatch(key) or type(value) is not int or value < 1:
                raise FeatureInputError("profile parameters must be positive integer values")
        object.__setattr__(self, "parameter_values", items)
        if self.calibration_receipt_hash is not None:
            require_sha256(self.calibration_receipt_hash, "calibration_receipt_hash")

    def parameter(self, name: str) -> int:
        try:
            return dict(self.parameter_values)[name]
        except KeyError as exc:
            raise FeatureInputError(f"fixture profile has no parameter {name!r}") from exc


@dataclass(frozen=True, slots=True)
class ProductionActivationGrant:
    """Hashes returned by upstream qualification and owner-approval authorities."""

    registry_content_hash: str
    calibration_receipt_hash: str
    qualification_receipt_hash: str
    owner_decision_hash: str

    def __post_init__(self) -> None:
        require_sha256(self.registry_content_hash, "grant registry_content_hash")
        require_sha256(self.calibration_receipt_hash, "grant calibration_receipt_hash")
        require_sha256(self.qualification_receipt_hash, "grant qualification_receipt_hash")
        require_sha256(self.owner_decision_hash, "grant owner_decision_hash")


@dataclass(frozen=True, slots=True)
class FeatureDefinitionSpec:
    stable_key: str
    research_family: str
    operation: str
    equation: str
    input_units: tuple[str, ...]
    output_unit: str
    output_dtype: str
    lookback_sessions: int
    warmup_sessions: int
    alignment: str
    split_treatment: str
    precision: int
    normalization: str
    parameter_profile: str
    missingness_policy: str
    zero_denominator_policy: str
    supported_regime: str
    dependencies: tuple[str, ...]
    implementation_parameters: tuple[tuple[str, int], ...]
    invariance_properties: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeatureRegistryBundle:
    profile: FeatureProfile
    definitions: tuple[FeatureDefinitionSpec, ...]
    ordered_feature_ids: tuple[str, ...]
    definition_contracts: Mapping[str, dict[str, Any]]
    registry_contract: dict[str, Any]
    environment_namespace: str
    evidence_class: str

    @property
    def registry_ref(self) -> ContractRef:
        record = self.registry_contract
        return ContractRef(FEATURE_REGISTRY_SCHEMA, record["id"], record["content_hash"])


def fixture_daily_profile() -> FeatureProfile:
    """Return explicit, synthetic-only windows; these values are not calibrated."""
    return FeatureProfile(
        profile_key="fixture_daily_v1",
        fixture_only=True,
        parameter_values=(
            ("accumulation_window", 20),
            ("atr_period", 14),
            ("breakout_count_window", 5),
            ("breakout_reference_window", 20),
            ("momentum_window", 5),
            ("persistence_window", 10),
            ("relative_volume_window", 20),
            ("reversal_window", 5),
            ("rolling_high_window", 20),
            ("trend_window", 20),
            ("volatility_recent_period", 5),
            ("volatility_reference_period", 20),
            ("volatility_of_volatility_period", 20),
            ("volume_recent_period", 5),
            ("volume_reference_period", 20),
            ("volume_slope_window", 10),
        ),
    )


def assert_profile_activation(
    profile: FeatureProfile,
    *,
    target_environment: str,
    evidence_class: str,
    registry_content_hash: str | None = None,
    grant: ProductionActivationGrant | None = None,
) -> None:
    if target_environment != "production":
        return
    if profile.fixture_only or evidence_class == "SYNTHETIC_FIXTURE":
        raise ProductionActivationDenied("synthetic fixture feature profiles cannot run in production")
    if grant is None or registry_content_hash is None:
        raise ProductionActivationDenied("production activation requires registry-bound external evidence")
    if grant.registry_content_hash != registry_content_hash:
        raise ProductionActivationDenied("activation evidence is bound to a different registry")
    if profile.calibration_receipt_hash != grant.calibration_receipt_hash:
        raise ProductionActivationDenied("profile calibration and activation evidence disagree")


def _spec(
    key: str,
    family: str,
    operation: str,
    equation: str,
    inputs: tuple[str, ...],
    output_unit: str,
    lookback: int,
    warmup: int,
    normalization: str,
    profile: FeatureProfile,
    *,
    dependencies: tuple[str, ...] = (),
    parameters: tuple[tuple[str, int], ...] = (),
    invariances: tuple[str, ...] = (),
    precision: int = 12,
    output_dtype: str = "DECIMAL",
    zero_denominator: str = "MISSING",
) -> FeatureDefinitionSpec:
    return FeatureDefinitionSpec(
        stable_key=key,
        research_family=family,
        operation=operation,
        equation=equation,
        input_units=inputs,
        output_unit=output_unit,
        output_dtype=output_dtype,
        lookback_sessions=lookback,
        warmup_sessions=warmup,
        alignment="SESSION_CLOSE; every input known_at <= decision_cutoff",
        split_treatment="SPLIT_ADJUSTED_COMMON_BASIS_REQUIRED",
        precision=precision,
        normalization=normalization,
        parameter_profile=profile.profile_key,
        missingness_policy="EXPLICIT_REASON",
        zero_denominator_policy=zero_denominator,
        supported_regime="general",
        dependencies=dependencies,
        implementation_parameters=parameters,
        invariance_properties=invariances,
    )


def _topological_order(specs: tuple[FeatureDefinitionSpec, ...]) -> tuple[FeatureDefinitionSpec, ...]:
    by_key = {spec.stable_key: spec for spec in specs}
    if len(by_key) != len(specs):
        raise FeatureInputError("feature stable_key values must be unique")
    rank = {spec.stable_key: index for index, spec in enumerate(specs)}
    for spec in specs:
        unknown = set(spec.dependencies) - set(by_key)
        if unknown:
            raise FeatureInputError(f"{spec.stable_key} has unknown dependencies: {sorted(unknown)}")

    pending = {spec.stable_key: set(spec.dependencies) for spec in specs}
    ordered: list[FeatureDefinitionSpec] = []
    while pending:
        ready = sorted(
            (key for key, deps in pending.items() if not deps),
            key=rank.__getitem__,
        )
        if not ready:
            raise FeatureInputError("feature dependency graph contains a cycle")
        for key in ready:
            ordered.append(by_key[key])
            del pending[key]
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return tuple(ordered)


def build_feature_specs(profile: FeatureProfile | None = None) -> tuple[FeatureDefinitionSpec, ...]:
    profile = profile or fixture_daily_profile()
    specs: list[FeatureDefinitionSpec] = []
    price_inputs = ("open/high/low/close:currency_per_share on one split-adjusted basis",)
    close_inputs = ("close:currency_per_share on one split-adjusted basis",)
    volume_inputs = ("volume:shares on the same split-adjusted share basis",)
    bar_input = ("session_id:exchange session",) + price_inputs + volume_inputs

    for period in (1, 2, 3, 5, 10, 20):
        specs.append(
            _spec(
                f"return_{period}",
                "returns",
                "close_return",
                f"R_n(t) = C_t / C_(t-n) - 1; n={period}; close-to-close simple return.",
                close_inputs,
                "fraction",
                period,
                period + 1,
                "FRACTION",
                profile,
                parameters=(("period", period),),
                invariances=("invariant to positive uniform price scaling",),
            )
        )

    momentum = profile.parameter("momentum_window")
    specs.extend(
        (
            _spec(
                "momentum_slope",
                "momentum",
                "momentum_slope",
                f"mean(ln(C_i/C_(i-1))) over the latest {momentum} returns.",
                close_inputs,
                "log_return_per_session",
                momentum,
                momentum + 1,
                "LOG_RETURN_PER_SESSION",
                profile,
                dependencies=("return_1",),
                parameters=(("period", momentum),),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "momentum_acceleration",
                "momentum",
                "momentum_acceleration",
                f"mean(log returns in latest {momentum}) - mean(log returns in preceding {momentum}).",
                close_inputs,
                "log_return_per_session",
                2 * momentum,
                2 * momentum + 1,
                "LOG_RETURN_PER_SESSION",
                profile,
                dependencies=("momentum_slope",),
                parameters=(("period", momentum),),
                invariances=("invariant to positive uniform price scaling",),
            ),
        )
    )

    persistence = profile.parameter("persistence_window")
    specs.append(
        _spec(
            "directional_persistence",
            "directional_persistence",
            "directional_persistence",
            f"sum(sign(log(C_i/C_(i-1)))) / {persistence} over the latest returns.",
            close_inputs,
            "signed_fraction",
            persistence,
            persistence + 1,
            "SIGNED_UNIT",
            profile,
            dependencies=("return_1",),
            parameters=(("period", persistence),),
            invariances=("invariant to positive uniform price scaling",),
        )
    )

    atr_period = profile.parameter("atr_period")
    specs.extend(
        (
            _spec(
                "true_range",
                "range",
                "true_range",
                "TR_t = max(H_t-L_t, abs(H_t-C_(t-1)), abs(L_t-C_(t-1))).",
                ("high/low/previous close:currency_per_share on one split-adjusted basis",),
                "currency_per_share",
                1,
                2,
                "NONE",
                profile,
                invariances=("scales linearly under positive uniform price scaling",),
            ),
            _spec(
                "atr",
                "range",
                "atr",
                f"arithmetic mean of true range over the latest {atr_period} sessions.",
                ("true_range:currency_per_share",),
                "currency_per_share",
                atr_period,
                atr_period + 1,
                "NONE",
                profile,
                dependencies=("true_range",),
                parameters=(("period", atr_period),),
                invariances=("scales linearly under positive uniform price scaling",),
            ),
            _spec(
                "normalized_range",
                "range",
                "normalized_range",
                "(H_t-L_t)/C_(t-1).",
                ("high/low/previous close:currency_per_share on one split-adjusted basis",),
                "fraction",
                1,
                2,
                "FRACTION",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
        )
    )

    recent_volatility = profile.parameter("volatility_recent_period")
    reference_volatility = profile.parameter("volatility_reference_period")
    volatility_of_volatility = profile.parameter("volatility_of_volatility_period")
    specs.extend(
        (
            _spec(
                "volatility_expansion",
                "volatility",
                "volatility_expansion",
                f"mean(TR latest {recent_volatility}) / mean(TR preceding {reference_volatility}) - 1.",
                ("true_range:currency_per_share",),
                "fraction",
                recent_volatility + reference_volatility,
                recent_volatility + reference_volatility + 1,
                "FRACTION",
                profile,
                dependencies=("atr",),
                parameters=(("recent_period", recent_volatility), ("reference_period", reference_volatility)),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "volatility_compression",
                "volatility",
                "volatility_compression",
                f"mean(TR preceding {reference_volatility}) / mean(TR latest {recent_volatility}) - 1.",
                ("true_range:currency_per_share",),
                "fraction",
                recent_volatility + reference_volatility,
                recent_volatility + reference_volatility + 1,
                "FRACTION",
                profile,
                dependencies=("atr",),
                parameters=(("recent_period", recent_volatility), ("reference_period", reference_volatility)),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "volatility_of_volatility",
                "volatility",
                "volatility_of_volatility",
                f"population standard deviation of normalized_range over {volatility_of_volatility} sessions.",
                ("normalized_range:fraction",),
                "fraction",
                volatility_of_volatility,
                volatility_of_volatility + 1,
                "FRACTION",
                profile,
                dependencies=("normalized_range",),
                parameters=(("period", volatility_of_volatility),),
                invariances=("invariant to positive uniform price scaling",),
            ),
        )
    )

    relative_volume_window = profile.parameter("relative_volume_window")
    volume_recent = profile.parameter("volume_recent_period")
    volume_reference = profile.parameter("volume_reference_period")
    volume_slope_window = profile.parameter("volume_slope_window")
    accumulation_window = profile.parameter("accumulation_window")
    specs.extend(
        (
            _spec(
                "relative_volume",
                "volume",
                "relative_volume",
                f"V_t / arithmetic_mean(V over preceding {relative_volume_window} sessions).",
                volume_inputs,
                "ratio",
                relative_volume_window,
                relative_volume_window + 1,
                "RATIO",
                profile,
                parameters=(("period", relative_volume_window),),
                invariances=("invariant to positive uniform volume scaling",),
            ),
            _spec(
                "volume_acceleration",
                "volume",
                "volume_acceleration",
                f"mean(V latest {volume_recent}) / mean(V preceding {volume_reference}) - 1.",
                volume_inputs,
                "fraction",
                volume_recent + volume_reference - 1,
                volume_recent + volume_reference,
                "FRACTION",
                profile,
                parameters=(("recent_period", volume_recent), ("reference_period", volume_reference)),
                invariances=("invariant to positive uniform volume scaling",),
            ),
            _spec(
                "volume_slope",
                "volume",
                "volume_slope",
                f"OLS_slope(V over {volume_slope_window} sessions) / arithmetic_mean(V over same window).",
                volume_inputs,
                "relative_volume_per_session",
                volume_slope_window - 1,
                volume_slope_window,
                "RELATIVE_SLOPE",
                profile,
                parameters=(("period", volume_slope_window),),
                invariances=("invariant to positive uniform volume scaling",),
            ),
            _spec(
                "accumulation",
                "volume",
                "accumulation",
                f"sum(CLV_i*V_i)/sum(V_i) over {accumulation_window} sessions; CLV=(2C-H-L)/(H-L).",
                bar_input,
                "signed_fraction",
                accumulation_window - 1,
                accumulation_window,
                "SIGNED_UNIT",
                profile,
                dependencies=("close_location_value",),
                parameters=(("period", accumulation_window),),
                invariances=(
                    "invariant to positive uniform price scaling",
                    "invariant to positive uniform volume scaling",
                ),
            ),
        )
    )

    divergence_period = 20
    specs.append(
        _spec(
            "price_volume_divergence",
            "price_volume",
            "price_volume_divergence",
            "sign(return) when nonzero signs of return and volume-weighted CLV are opposite; otherwise 0.",
            ("close-to-close return:fraction", "accumulation:signed_fraction"),
            "signed_unit",
            divergence_period,
            divergence_period + 1,
            "SIGNED_UNIT",
            profile,
            dependencies=(f"return_{divergence_period}", "accumulation"),
            parameters=(("period", divergence_period),),
            invariances=(
                "invariant to positive uniform price scaling",
                "invariant to positive uniform volume scaling",
            ),
        )
    )

    specs.extend(
        (
            _spec(
                "gap_return",
                "gaps",
                "gap_return",
                "G_t = O_t/C_(t-1) - 1.",
                ("open/previous close:currency_per_share on one split-adjusted basis",),
                "fraction",
                1,
                2,
                "FRACTION",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "close_location_value",
                "candle_geometry",
                "close_location_value",
                "CLV_t = (2*C_t-H_t-L_t)/(H_t-L_t); undefined when H_t=L_t.",
                price_inputs,
                "signed_fraction",
                0,
                1,
                "SIGNED_UNIT",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "body_proportion",
                "candle_geometry",
                "body_proportion",
                "abs(C_t-O_t)/(H_t-L_t); undefined when H_t=L_t.",
                price_inputs,
                "fraction",
                0,
                1,
                "UNIT_INTERVAL",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "upper_wick_proportion",
                "candle_geometry",
                "upper_wick_proportion",
                "(H_t-max(O_t,C_t))/(H_t-L_t); undefined when H_t=L_t.",
                price_inputs,
                "fraction",
                0,
                1,
                "UNIT_INTERVAL",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "lower_wick_proportion",
                "candle_geometry",
                "lower_wick_proportion",
                "(min(O_t,C_t)-L_t)/(H_t-L_t); undefined when H_t=L_t.",
                price_inputs,
                "fraction",
                0,
                1,
                "UNIT_INTERVAL",
                profile,
                invariances=("invariant to positive uniform price scaling",),
            ),
        )
    )

    high_window = profile.parameter("rolling_high_window")
    breakout_ref = profile.parameter("breakout_reference_window")
    breakout_count = profile.parameter("breakout_count_window")
    specs.extend(
        (
            _spec(
                "rolling_high_distance",
                "rolling_structure",
                "rolling_high_distance",
                f"C_t/max(H over preceding {high_window} sessions)-1; current session excluded from high.",
                ("close/prior high:currency_per_share on one split-adjusted basis",),
                "fraction",
                high_window,
                high_window + 1,
                "FRACTION",
                profile,
                parameters=(("period", high_window),),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "breakout_proximity",
                "breakout",
                "breakout_proximity",
                f"(max(H over preceding {breakout_ref})-H_t)/max(prior H); negative after high breaks.",
                ("high/prior high:currency_per_share on one split-adjusted basis",),
                "fraction",
                breakout_ref,
                breakout_ref + 1,
                "FRACTION",
                profile,
                dependencies=("rolling_high_distance",),
                parameters=(("period", breakout_ref),),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "breakout_attempt_count",
                "breakout",
                "breakout_attempt_count",
                f"count(H_s >= max(prior {breakout_ref} highs)) over latest {breakout_count} sessions.",
                ("high:currency_per_share on one split-adjusted basis",),
                "events",
                breakout_ref + breakout_count - 1,
                breakout_ref + breakout_count,
                "COUNT",
                profile,
                dependencies=("rolling_high_distance",),
                parameters=(("reference_period", breakout_ref), ("count_period", breakout_count)),
                invariances=("invariant to positive uniform price scaling",),
                precision=0,
                output_dtype="INTEGER",
            ),
            _spec(
                "breakout_failure_count",
                "breakout",
                "breakout_failure_count",
                f"count(H_s >= max(prior {breakout_ref} highs) and C_s <= that high) over latest {breakout_count} sessions.",
                ("high/close:currency_per_share on one split-adjusted basis",),
                "events",
                breakout_ref + breakout_count - 1,
                breakout_ref + breakout_count,
                "COUNT",
                profile,
                dependencies=("rolling_high_distance",),
                parameters=(("reference_period", breakout_ref), ("count_period", breakout_count)),
                invariances=("invariant to positive uniform price scaling",),
                precision=0,
                output_dtype="INTEGER",
            ),
        )
    )

    trend_window = profile.parameter("trend_window")
    reversal_window = profile.parameter("reversal_window")
    specs.extend(
        (
            _spec(
                "trend_slope",
                "trend",
                "trend_slope",
                f"OLS_slope(ln(C)) per session over {trend_window+1} closes, including t.",
                close_inputs,
                "log_return_per_session",
                trend_window,
                trend_window + 1,
                "LOG_RETURN_PER_SESSION",
                profile,
                parameters=(("period", trend_window),),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "reversal_score",
                "reversal",
                "reversal_score",
                f"sign(prior {reversal_window}-session return) when latest 1-session return has opposite sign; else 0.",
                close_inputs,
                "signed_unit",
                reversal_window + 1,
                reversal_window + 2,
                "SIGNED_UNIT",
                profile,
                parameters=(("period", reversal_window),),
                invariances=("invariant to positive uniform price scaling",),
            ),
            _spec(
                "exhaustion_pressure",
                "exhaustion",
                "exhaustion_pressure",
                "sign(trend_slope)*((0.5-CLV_t)*2)*(TR_t/ATR_t); missing if ATR_t=0.",
                ("trend_slope:log_return_per_session", "CLV:signed_fraction", "TR/ATR:currency_per_share"),
                "signed_ratio",
                max(trend_window, atr_period),
                max(trend_window, atr_period) + 1,
                "NONE",
                profile,
                dependencies=("trend_slope", "close_location_value", "true_range", "atr"),
                parameters=(("atr_period", atr_period),),
                invariances=("invariant to positive uniform price scaling",),
            ),
        )
    )

    similarity_keys = (
        "return_1",
        "return_3",
        "return_5",
        "return_20",
        "momentum_slope",
        "volatility_expansion",
        "relative_volume",
        "trend_slope",
        "exhaustion_pressure",
    )
    similarity_warmup = max(
        spec.warmup_sessions for spec in specs if spec.stable_key in similarity_keys
    )
    for key, kind in (("runner_similarity", "RUNNER"), ("failure_similarity", "FAILURE")):
        specs.append(
            _spec(
                key,
                "historical_similarity",
                f"{kind.lower()}_similarity",
                "max(1 - mean(abs(b(x_i)-b(p_i)))); b(x)=x/(1+abs(x)); fixed registered dimensions.",
                tuple(f"{feature}:registered_value" for feature in similarity_keys),
                "signed_unit",
                similarity_warmup - 1,
                similarity_warmup,
                "SIGNED_UNIT",
                profile,
                dependencies=similarity_keys,
                invariances=("invariant to input order after canonical feature-key ordering",),
            )
        )

    ordered = _topological_order(tuple(specs))
    return _inherit_dependency_warmup(ordered)


def _inherit_dependency_warmup(
    ordered: tuple[FeatureDefinitionSpec, ...],
) -> tuple[FeatureDefinitionSpec, ...]:
    by_key: dict[str, FeatureDefinitionSpec] = {}
    rewritten: list[FeatureDefinitionSpec] = []
    for spec in ordered:
        warmup = max(
            (by_key[key].warmup_sessions for key in spec.dependencies),
            default=spec.warmup_sessions,
        )
        updated = replace(
            spec,
            lookback_sessions=max(spec.lookback_sessions, warmup - 1),
            warmup_sessions=max(spec.warmup_sessions, warmup),
        )
        rewritten.append(updated)
        by_key[updated.stable_key] = updated
    return tuple(rewritten)


def _canonical_instant(value: datetime | str) -> str:
    return as_utc(value, "created_at").isoformat(timespec="seconds").replace("+00:00", "Z")


def _finalize_contract(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    verify_content_hash(name, payload)
    return payload


def _ref(schema_name: str, record: Mapping[str, Any]) -> dict[str, str]:
    return ContractRef(schema_name, str(record["id"]), str(record["content_hash"])).to_payload()


def materialize_feature_registry(
    profile: FeatureProfile,
    *,
    definition_ids: Mapping[str, str],
    registry_id: str,
    created_at: datetime | str,
    effective_from: date | str,
    implementation_hash: str,
    environment_namespace: str = "test",
    evidence_class: str | None = None,
    activation_grant: ProductionActivationGrant | None = None,
) -> FeatureRegistryBundle:
    """Build and validate immutable FeatureDefinition and FeatureRegistry contracts."""
    require_sha256(implementation_hash, "implementation_hash")
    created = _canonical_instant(created_at)
    effective = as_date(effective_from, "effective_from").isoformat()
    evidence = evidence_class or ("SYNTHETIC_FIXTURE" if profile.fixture_only else "HISTORICAL_RECONSTRUCTED")
    if evidence == "SYNTHETIC_FIXTURE" and not profile.fixture_only:
        raise FeatureInputError("SYNTHETIC_FIXTURE evidence requires a fixture-only profile")
    specs = build_feature_specs(profile)
    keys = {spec.stable_key for spec in specs}
    if set(definition_ids) != keys:
        missing = sorted(keys - set(definition_ids))
        extra = sorted(set(definition_ids) - keys)
        raise FeatureInputError(f"definition_ids mismatch; missing={missing}, extra={extra}")
    if registry_id in set(definition_ids.values()) or len(set(definition_ids.values())) != len(definition_ids):
        raise FeatureInputError("registry and feature definition ids must be unique")

    definition_records: dict[str, dict[str, Any]] = {}
    for spec in specs:
        dependency_refs = [
            _ref(FEATURE_DEFINITION_SCHEMA, definition_records[key])
            for key in spec.dependencies
        ]
        record = {
            "schema_name": FEATURE_DEFINITION_SCHEMA,
            "schema_version": "1.0",
            "id": definition_ids[spec.stable_key],
            "created_at": created,
            "owning_authority": "feature",
            "evidence_class": evidence,
            "environment_namespace": environment_namespace,
            "source_refs": [],
            "stable_key": spec.stable_key,
            "version": 1,
            "research_family": spec.research_family,
            "equation": spec.equation,
            "input_refs": [],
            "input_units": list(spec.input_units),
            "output_unit": spec.output_unit,
            "output_dtype": spec.output_dtype,
            "lookback_sessions": spec.lookback_sessions,
            "warmup_sessions": spec.warmup_sessions,
            "alignment": spec.alignment,
            "split_treatment": spec.split_treatment,
            "precision": spec.precision,
            "normalization": spec.normalization,
            "parameter_profile": spec.parameter_profile,
            "missingness_policy": spec.missingness_policy,
            "zero_denominator_policy": spec.zero_denominator_policy,
            "supported_regime": spec.supported_regime,
            "dependency_refs": dependency_refs,
            "implementation_hash": implementation_hash,
            "invariance_properties": list(spec.invariance_properties),
        }
        definition_records[spec.stable_key] = _finalize_contract("FeatureDefinition", record)
        validate_contract("FeatureDefinition", definition_records[spec.stable_key])

    registry_record = {
        "schema_name": FEATURE_REGISTRY_SCHEMA,
        "schema_version": "1.0",
        "id": registry_id,
        "created_at": created,
        "owning_authority": "feature",
        "evidence_class": evidence,
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "registry_version": 1,
        "definition_refs": [
            _ref(FEATURE_DEFINITION_SCHEMA, definition_records[spec.stable_key])
            for spec in specs
        ],
        "ordered_feature_ids": [spec.stable_key for spec in specs],
        "effective_from": effective,
    }
    registry_record = _finalize_contract("FeatureRegistry", registry_record)
    validate_contract("FeatureRegistry", registry_record)
    assert_profile_activation(
        profile,
        target_environment=environment_namespace,
        evidence_class=evidence,
        registry_content_hash=registry_record["content_hash"],
        grant=activation_grant,
    )
    return FeatureRegistryBundle(
        profile=profile,
        definitions=specs,
        ordered_feature_ids=tuple(spec.stable_key for spec in specs),
        definition_contracts=definition_records,
        registry_contract=registry_record,
        environment_namespace=environment_namespace,
        evidence_class=evidence,
    )
