"""Pure offline evaluation and canonical FeatureSnapshot construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable, Mapping

from qc2_contracts.runtime import canonical_content_hash, validate_contract, verify_content_hash

from .models import (
    ContractRef,
    DailyFeatureBar,
    FeatureInput,
    FeatureInputError,
    SimilarityPrototype,
    TemporalLeakageError,
    as_utc,
    require_sha256,
)
from .registry import (
    FEATURE_DEFINITION_SCHEMA,
    FEATURE_REGISTRY_SCHEMA,
    FeatureDefinitionSpec,
    FeatureRegistryBundle,
    ProductionActivationGrant,
    assert_profile_activation,
)

FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
_SIMILARITY_FEATURE_KEYS = (
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
_SOURCE_SCHEMA_ORDER = (
    "qc2.time_operation.CalendarManifest.v1",
    "qc2.identity_market.Instrument.v1",
    "qc2.identity_market.AdjustmentManifest.v1",
    "qc2.identity_market.DailyBar.v1",
    "qc2.identity_market.SymbolAssignment.v1",
    "qc2.scientific_definitions.FeatureSnapshot.v1",
    "qc2.outcomes_research.RunnerGenome.v1",
    "qc2.outcomes_research.FailureGenome.v1",
)


@dataclass(frozen=True, slots=True)
class FeatureResult:
    value: Decimal | None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.missing_reason is None):
            raise FeatureInputError("a feature result must contain exactly one of value or missing_reason")
        if self.value is not None and not self.value.is_finite():
            raise FeatureInputError("feature results must be finite")


def _missing(reason: str) -> FeatureResult:
    return FeatureResult(None, reason)


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _mean(values: Iterable[Decimal]) -> Decimal:
    materialized = tuple(values)
    if not materialized:
        raise FeatureInputError("mean requires at least one value")
    return sum(materialized, Decimal(0)) / Decimal(len(materialized))


def _stddev(values: Iterable[Decimal]) -> Decimal:
    materialized = tuple(values)
    center = _mean(materialized)
    variance = _mean((value - center) ** 2 for value in materialized)
    return variance.sqrt()


def _ols_slope(values: Iterable[Decimal]) -> Decimal:
    materialized = tuple(values)
    if len(materialized) < 2:
        raise FeatureInputError("OLS slope requires at least two values")
    xs = tuple(Decimal(index) for index in range(len(materialized)))
    x_center = _mean(xs)
    y_center = _mean(materialized)
    numerator = sum(
        ((x - x_center) * (y - y_center) for x, y in zip(xs, materialized)),
        Decimal(0),
    )
    denominator = sum(((x - x_center) ** 2 for x in xs), Decimal(0))
    return numerator / denominator


def _log_returns(bars: list[DailyFeatureBar]) -> list[Decimal]:
    return [
        (current.close_price / previous.close_price).ln()
        for previous, current in zip(bars, bars[1:])
    ]


def _true_ranges(bars: list[DailyFeatureBar]) -> list[Decimal]:
    return [
        max(
            current.high_price - current.low_price,
            abs(current.high_price - previous.close_price),
            abs(current.low_price - previous.close_price),
        )
        for previous, current in zip(bars, bars[1:])
    ]


def _required_bars(
    calendar_sessions: tuple[date, ...],
    bars_by_session: Mapping[date, DailyFeatureBar],
    count: int,
) -> tuple[list[DailyFeatureBar] | None, str | None]:
    if len(calendar_sessions) < count:
        return None, "WARMUP_REQUIRED"
    selected_sessions = calendar_sessions[-count:]
    if any(session not in bars_by_session for session in selected_sessions):
        return None, "SOURCE_FIELD_MISSING"
    return [bars_by_session[session] for session in selected_sessions], None


def _required_volumes(bars: list[DailyFeatureBar]) -> tuple[list[Decimal] | None, str | None]:
    if any(bar.volume is None for bar in bars):
        return None, "SOURCE_FIELD_MISSING"
    return [bar.volume for bar in bars if bar.volume is not None], None


def _clv(bar: DailyFeatureBar) -> tuple[Decimal | None, str | None]:
    spread = bar.high_price - bar.low_price
    if spread == 0:
        return None, "DIVISION_BY_ZERO"
    return (Decimal(2) * bar.close_price - bar.high_price - bar.low_price) / spread, None


def _dependency_missing(
    spec: FeatureDefinitionSpec,
    results: Mapping[str, FeatureResult],
) -> str | None:
    for key in spec.dependencies:
        result = results[key]
        if result.value is None:
            return result.missing_reason
    return None


def _feature_value(
    spec: FeatureDefinitionSpec,
    inputs: FeatureInput,
    bars_by_session: Mapping[date, DailyFeatureBar],
    results: Mapping[str, FeatureResult],
    prototypes: tuple[SimilarityPrototype, ...],
    registry_hash: str,
) -> FeatureResult:
    dependency_reason = _dependency_missing(spec, results)
    if dependency_reason is not None:
        return _missing(dependency_reason)
    window, window_reason = _required_bars(
        inputs.calendar_sessions,
        bars_by_session,
        spec.warmup_sessions,
    )
    if window_reason is not None:
        return _missing(window_reason)
    assert window is not None
    params = dict(spec.implementation_parameters)
    op = spec.operation

    if op == "close_return":
        period = params["period"]
        return FeatureResult(window[-1].close_price / window[-period - 1].close_price - 1)

    if op == "momentum_slope":
        period = params["period"]
        return FeatureResult(_mean(_log_returns(window[-period - 1 :])))

    if op == "momentum_acceleration":
        period = params["period"]
        returns = _log_returns(window[-(2 * period + 1) :])
        return FeatureResult(_mean(returns[-period:]) - _mean(returns[:period]))

    if op == "directional_persistence":
        period = params["period"]
        returns = _log_returns(window[-period - 1 :])
        return FeatureResult(
            Decimal(sum(_sign(item) for item in returns)) / Decimal(period)
        )

    if op == "true_range":
        return FeatureResult(_true_ranges(window[-2:])[-1])

    if op == "atr":
        period = params["period"]
        return FeatureResult(_mean(_true_ranges(window[-period - 1 :])))

    if op == "normalized_range":
        previous, current = window[-2:]
        return FeatureResult((current.high_price - current.low_price) / previous.close_price)

    if op in {"volatility_expansion", "volatility_compression"}:
        recent = params["recent_period"]
        reference = params["reference_period"]
        ranges = _true_ranges(window[-(recent + reference + 1) :])
        recent_atr = _mean(ranges[-recent:])
        reference_atr = _mean(ranges[:reference])
        if op == "volatility_expansion":
            if reference_atr == 0:
                return _missing("DIVISION_BY_ZERO")
            return FeatureResult(recent_atr / reference_atr - 1)
        if recent_atr == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(reference_atr / recent_atr - 1)

    if op == "volatility_of_volatility":
        period = params["period"]
        bars = window[-period - 1 :]
        normalized = [
            (current.high_price - current.low_price) / previous.close_price
            for previous, current in zip(bars, bars[1:])
        ]
        return FeatureResult(_stddev(normalized))

    if op == "relative_volume":
        period = params["period"]
        volumes, reason = _required_volumes(window[-period - 1 :])
        if reason is not None:
            return _missing(reason)
        assert volumes is not None
        prior_mean = _mean(volumes[:-1])
        if prior_mean == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(volumes[-1] / prior_mean)

    if op == "volume_acceleration":
        recent = params["recent_period"]
        reference = params["reference_period"]
        volumes, reason = _required_volumes(window[-(recent + reference) :])
        if reason is not None:
            return _missing(reason)
        assert volumes is not None
        recent_mean = _mean(volumes[-recent:])
        reference_mean = _mean(volumes[:reference])
        if reference_mean == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(recent_mean / reference_mean - 1)

    if op == "volume_slope":
        period = params["period"]
        volumes, reason = _required_volumes(window[-period:])
        if reason is not None:
            return _missing(reason)
        assert volumes is not None
        average = _mean(volumes)
        if average == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(_ols_slope(volumes) / average)

    if op == "accumulation":
        period = params["period"]
        bars = window[-period:]
        volumes, reason = _required_volumes(bars)
        if reason is not None:
            return _missing(reason)
        assert volumes is not None
        weighted_values: list[Decimal] = []
        for bar, volume in zip(bars, volumes):
            value, clv_reason = _clv(bar)
            if clv_reason is not None:
                return _missing(clv_reason)
            assert value is not None
            weighted_values.append(value * volume)
        total_volume = sum(volumes, Decimal(0))
        if total_volume == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(sum(weighted_values, Decimal(0)) / total_volume)

    if op == "price_volume_divergence":
        price_direction = _sign(results[f"return_{params['period']}"].value or Decimal(0))
        accumulation_direction = _sign(results["accumulation"].value or Decimal(0))
        if price_direction == 0 or accumulation_direction == 0:
            return FeatureResult(Decimal(0))
        return FeatureResult(
            Decimal(price_direction) if price_direction != accumulation_direction else Decimal(0)
        )

    if op == "gap_return":
        previous, current = window[-2:]
        return FeatureResult(current.open_price / previous.close_price - 1)

    if op == "close_location_value":
        value, reason = _clv(window[-1])
        return _missing(reason) if reason is not None else FeatureResult(value or Decimal(0))

    if op in {"body_proportion", "upper_wick_proportion", "lower_wick_proportion"}:
        bar = window[-1]
        spread = bar.high_price - bar.low_price
        if spread == 0:
            return _missing("DIVISION_BY_ZERO")
        if op == "body_proportion":
            numerator = abs(bar.close_price - bar.open_price)
        elif op == "upper_wick_proportion":
            numerator = bar.high_price - max(bar.open_price, bar.close_price)
        else:
            numerator = min(bar.open_price, bar.close_price) - bar.low_price
        return FeatureResult(numerator / spread)

    if op == "rolling_high_distance":
        period = params["period"]
        prior_high = max(bar.high_price for bar in window[-period - 1 : -1])
        return FeatureResult(window[-1].close_price / prior_high - 1)

    if op == "breakout_proximity":
        period = params["period"]
        prior_high = max(bar.high_price for bar in window[-period - 1 : -1])
        return FeatureResult((prior_high - window[-1].high_price) / prior_high)

    if op in {"breakout_attempt_count", "breakout_failure_count"}:
        reference = params["reference_period"]
        count_period = params["count_period"]
        attempts = 0
        failures = 0
        first = len(window) - count_period
        for index in range(first, len(window)):
            prior_high = max(bar.high_price for bar in window[index - reference : index])
            current = window[index]
            if current.high_price >= prior_high:
                attempts += 1
                if current.close_price <= prior_high:
                    failures += 1
        value = attempts if op == "breakout_attempt_count" else failures
        return FeatureResult(Decimal(value))

    if op == "trend_slope":
        period = params["period"]
        closes = window[-period - 1 :]
        return FeatureResult(_ols_slope([bar.close_price.ln() for bar in closes]))

    if op == "reversal_score":
        period = params["period"]
        bars = window[-period - 2 :]
        prior_direction = _sign(bars[-2].close_price / bars[0].close_price - 1)
        latest_direction = _sign(bars[-1].close_price / bars[-2].close_price - 1)
        if prior_direction != 0 and latest_direction == -prior_direction:
            return FeatureResult(Decimal(prior_direction))
        return FeatureResult(Decimal(0))

    if op == "exhaustion_pressure":
        trend = results["trend_slope"].value
        location = results["close_location_value"].value
        true_range = results["true_range"].value
        atr = results["atr"].value
        assert trend is not None and location is not None and true_range is not None and atr is not None
        if atr == 0:
            return _missing("DIVISION_BY_ZERO")
        return FeatureResult(
            Decimal(_sign(trend)) * ((Decimal("0.5") - location) * 2) * (true_range / atr)
        )

    if op in {"runner_similarity", "failure_similarity"}:
        kind = "RUNNER" if op == "runner_similarity" else "FAILURE"
        candidates = [item for item in prototypes if item.kind == kind]
        if not candidates:
            return _missing("NOT_APPLICABLE")
        current = {
            key: results[key].value
            for key in _SIMILARITY_FEATURE_KEYS
        }
        scores: list[Decimal] = []
        for prototype in sorted(candidates, key=lambda item: item.source_ref.content_hash):
            values = dict(prototype.feature_values)
            distance = _mean(
                abs(_bounded(current[key]) - _bounded(values[key]))
                for key in _SIMILARITY_FEATURE_KEYS
            )
            scores.append(Decimal(1) - distance)
        return FeatureResult(max(scores))

    raise FeatureInputError(f"unsupported feature operation: {op}")


def _bounded(value: Decimal | None) -> Decimal:
    if value is None:
        raise FeatureInputError("similarity cannot consume a missing feature")
    return value / (Decimal(1) + abs(value))


def _validate_inputs(
    inputs: FeatureInput,
    registry: FeatureRegistryBundle,
) -> tuple[dict[date, DailyFeatureBar], tuple[DailyFeatureBar, ...], tuple[SimilarityPrototype, ...]]:
    for label, known_at in (
        ("instrument", inputs.instrument_known_at),
        ("calendar", inputs.calendar_known_at),
        ("adjustment manifest", inputs.adjustment_known_at),
    ):
        if known_at > inputs.decision_cutoff:
            raise TemporalLeakageError(f"{label} metadata is after the decision cutoff")

    bars_by_session: dict[date, DailyFeatureBar] = {}
    ordered_bars = tuple(sorted(inputs.bars, key=lambda item: item.session_id))
    share_basis_keys: set[str] = set()
    assignment_claims: dict[str, tuple[date, date | None, str, str]] = {}
    for bar in ordered_bars:
        assert isinstance(bar.session_id, date)
        if bar.session_id in bars_by_session:
            raise FeatureInputError(f"duplicate daily bar for session {bar.session_id.isoformat()}")
        if bar.session_id > inputs.target_session:
            raise TemporalLeakageError("bar session is after the target session")
        if bar.session_id not in inputs.calendar_sessions:
            raise FeatureInputError("bar session is outside the supplied frozen calendar")
        if bar.known_at > inputs.decision_cutoff:
            raise TemporalLeakageError("bar known_at is after the decision cutoff")
        if bar.symbol_assignment_known_at > inputs.decision_cutoff:
            raise TemporalLeakageError("symbol assignment metadata is after the decision cutoff")
        if bar.source_ref.target_schema_name != "qc2.identity_market.DailyBar.v1":
            raise FeatureInputError("bar source_ref must reference DailyBar")
        if bar.instrument_ref != inputs.instrument_ref:
            raise FeatureInputError("history crosses canonical instrument identity")
        if bar.symbol_assignment_ref.target_schema_name != "qc2.identity_market.SymbolAssignment.v1":
            raise FeatureInputError("bar symbol_assignment_ref must reference SymbolAssignment")
        if bar.symbol_assignment_instrument_ref != inputs.instrument_ref:
            raise FeatureInputError("symbol assignment resolves to a different canonical instrument")
        if bar.symbol_assignment_effective_from > bar.session_id:
            raise FeatureInputError("symbol assignment is not yet effective for its bar session")
        if (
            bar.symbol_assignment_effective_to is not None
            and bar.symbol_assignment_effective_to < bar.session_id
        ):
            raise FeatureInputError("symbol assignment expired before its bar session")
        assignment_claim = (
            bar.symbol_assignment_effective_from,
            bar.symbol_assignment_effective_to,
            bar.symbol_assignment_instrument_ref.target_id,
            bar.symbol_assignment_instrument_ref.content_hash,
        )
        prior_claim = assignment_claims.setdefault(bar.symbol_assignment_ref.target_id, assignment_claim)
        if prior_claim != assignment_claim:
            raise FeatureInputError("one symbol assignment reference has conflicting effective intervals")
        if bar.adjustment_ref != inputs.adjustment_ref:
            raise FeatureInputError("history mixes adjustment manifests or split bases")
        share_basis_keys.add(bar.share_basis_key)
        bars_by_session[bar.session_id] = bar

    if len(share_basis_keys) > 1:
        raise FeatureInputError("history mixes share bases; adjust all bars to one common basis")

    prototype_order = tuple(
        sorted(
            inputs.prototypes,
            key=lambda item: (
                item.kind,
                item.event_session,
                item.source_ref.content_hash,
            ),
        )
    )
    seen_prototypes: set[tuple[str, str]] = set()
    registry_hash = registry.registry_contract["content_hash"]
    for prototype in prototype_order:
        if prototype.feature_snapshot_session != prototype.event_session:
            raise FeatureInputError("prototype feature snapshot must be from its event session")
        if prototype.event_session >= inputs.target_session:
            raise TemporalLeakageError("similarity prototype event is not strictly historical")
        if prototype.available_at > inputs.decision_cutoff:
            raise TemporalLeakageError("similarity source was not available by the decision cutoff")
        evidence = prototype.temporal_access_evidence
        if evidence.decision_cutoff != inputs.decision_cutoff:
            raise TemporalLeakageError("similarity access receipt is bound to a different decision cutoff")
        if evidence.artifact_available_at != prototype.available_at:
            raise TemporalLeakageError("similarity availability differs from the receipted availability")
        if evidence.artifact_available_at > inputs.decision_cutoff:
            raise TemporalLeakageError("similarity artifacts were not available by the decision cutoff")
        if evidence.authorized_at > inputs.decision_cutoff:
            raise TemporalLeakageError("similarity access receipt was not available by the decision cutoff")
        if prototype.registry_content_hash != registry_hash:
            raise FeatureInputError("similarity prototype was built under a different feature registry")
        if set(dict(prototype.feature_values)) != set(_SIMILARITY_FEATURE_KEYS):
            raise FeatureInputError("similarity prototype must provide the exact registered feature vector")
        identity = (prototype.kind, prototype.source_ref.content_hash)
        if identity in seen_prototypes:
            raise FeatureInputError("duplicate similarity prototype reference")
        seen_prototypes.add(identity)
    return bars_by_session, ordered_bars, prototype_order


def _format_value(value: Decimal, precision: int, output_dtype: str) -> str:
    if output_dtype == "INTEGER":
        with localcontext() as context:
            context.prec = max(96, len(value.as_tuple().digits) + 16)
            rounded = value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        if rounded != value:
            raise FeatureInputError("integer feature produced a fractional value")
        return str(int(rounded))
    if output_dtype != "DECIMAL":
        raise FeatureInputError("feature definition declares an unsupported output data type")
    quantum = Decimal(1).scaleb(-precision)
    with localcontext() as context:
        context.prec = max(96, len(value.as_tuple().digits) + precision + 16)
        rounded = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, "f")


def _stable_source_refs(inputs: FeatureInput, bars: tuple[DailyFeatureBar, ...],
                        prototypes: tuple[SimilarityPrototype, ...]) -> list[dict[str, str]]:
    refs: list[ContractRef] = [
        inputs.calendar_ref,
        inputs.instrument_ref,
        inputs.adjustment_ref,
    ]
    for bar in bars:
        refs.extend((bar.source_ref, bar.symbol_assignment_ref))
    for prototype in prototypes:
        refs.extend((prototype.feature_snapshot_ref, prototype.source_ref))

    rank = {schema: index for index, schema in enumerate(_SOURCE_SCHEMA_ORDER)}
    unique: dict[tuple[str, str], ContractRef] = {}
    for ref in refs:
        key = (ref.target_schema_name, ref.target_id)
        previous = unique.get(key)
        if previous is not None and previous != ref:
            raise FeatureInputError("the same source id has conflicting content hashes")
        unique[key] = ref
    return [
        ref.to_payload()
        for ref in sorted(
            unique.values(),
            key=lambda item: (
                rank.get(item.target_schema_name, len(rank)),
                item.target_id,
                item.content_hash,
            ),
        )
    ]


def _input_hashes(
    inputs: FeatureInput,
    bars: tuple[DailyFeatureBar, ...],
    prototypes: tuple[SimilarityPrototype, ...],
) -> list[str]:
    hashes = [
        inputs.instrument_ref.content_hash,
        inputs.calendar_ref.content_hash,
        inputs.adjustment_ref.content_hash,
    ]
    for bar in bars:
        hashes.extend((bar.source_ref.content_hash, bar.symbol_assignment_ref.content_hash))
    for prototype in prototypes:
        hashes.extend(
            (
                prototype.feature_snapshot_ref.content_hash,
                prototype.source_ref.content_hash,
                prototype.temporal_access_evidence.receipt_hash,
            )
        )
    return hashes


def compute_feature_snapshot(
    inputs: FeatureInput,
    registry: FeatureRegistryBundle,
    *,
    snapshot_id: str,
    created_at: datetime | str,
    code_hash: str,
    environment_fingerprint: str,
    activation_grant: ProductionActivationGrant | None = None,
) -> dict[str, Any]:
    """Compute and content-address a QC2 FeatureSnapshot without I/O or mutation."""
    require_sha256(code_hash, "code_hash")
    require_sha256(environment_fingerprint, "environment_fingerprint")
    created = as_utc(created_at, "created_at")
    if created < inputs.decision_cutoff:
        raise FeatureInputError("snapshot created_at cannot precede its decision cutoff")
    validate_contract("FeatureRegistry", registry.registry_contract)
    verify_content_hash("FeatureRegistry", registry.registry_contract)
    if registry.registry_contract["ordered_feature_ids"] != list(registry.ordered_feature_ids):
        raise FeatureInputError("registry order and in-memory column order disagree")
    for key in registry.ordered_feature_ids:
        record = registry.definition_contracts[key]
        validate_contract("FeatureDefinition", record)
        verify_content_hash("FeatureDefinition", record)
        if record["implementation_hash"] != code_hash:
            raise FeatureInputError("snapshot code_hash differs from a registered feature implementation")
    assert_profile_activation(
        registry.profile,
        target_environment=registry.environment_namespace,
        evidence_class=registry.evidence_class,
        registry_content_hash=registry.registry_contract["content_hash"],
        grant=activation_grant,
    )

    bars_by_session, bars, prototypes = _validate_inputs(inputs, registry)
    results: dict[str, FeatureResult] = {}
    with localcontext() as context:
        context.prec = 128
        for spec in registry.definitions:
            results[spec.stable_key] = _feature_value(
                spec,
                inputs,
                bars_by_session,
                results,
                prototypes,
                registry.registry_contract["content_hash"],
            )

    specs_by_key = {spec.stable_key: spec for spec in registry.definitions}
    feature_values: list[dict[str, str]] = []
    for key in registry.ordered_feature_ids:
        result = results[key]
        spec = specs_by_key[key]
        if result.value is None:
            feature_values.append(
                {
                    "feature_id": key,
                    "unit": spec.output_unit,
                    "output_dtype": spec.output_dtype,
                    "missing_reason": result.missing_reason or "UNKNOWN",
                }
            )
        else:
            feature_values.append(
                {
                    "feature_id": key,
                    "unit": spec.output_unit,
                    "output_dtype": spec.output_dtype,
                    "value": _format_value(result.value, spec.precision, spec.output_dtype),
                }
            )

    definition_refs = [
        {
            "target_schema_name": FEATURE_DEFINITION_SCHEMA,
            "target_id": registry.definition_contracts[key]["id"],
            "content_hash": registry.definition_contracts[key]["content_hash"],
        }
        for key in registry.ordered_feature_ids
    ]
    sources = _stable_source_refs(inputs, bars, prototypes)
    hashes = _input_hashes(inputs, bars, prototypes)
    payload: dict[str, Any] = {
        "schema_name": FEATURE_SNAPSHOT_SCHEMA,
        "schema_version": "1.0",
        "id": snapshot_id,
        "created_at": created.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owning_authority": "feature",
        "evidence_class": registry.evidence_class,
        "environment_namespace": registry.environment_namespace,
        "source_refs": sources,
        "session_id": inputs.target_session.isoformat(),
        "instrument_ref": {
            "target_schema_name": inputs.instrument_ref.target_schema_name,
            "target_id": inputs.instrument_ref.target_id,
        },
        "registry_ref": {
            "target_schema_name": FEATURE_REGISTRY_SCHEMA,
            "target_id": registry.registry_contract["id"],
            "content_hash": registry.registry_contract["content_hash"],
        },
        "feature_values": feature_values,
        "input_hashes": hashes,
        "transform_refs": definition_refs,
        "decision_cutoff": inputs.decision_cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "code_hash": code_hash,
        "environment_fingerprint": environment_fingerprint,
    }
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash("FeatureSnapshot", payload)
    validate_contract("FeatureSnapshot", payload)
    verify_content_hash("FeatureSnapshot", payload)
    return payload
