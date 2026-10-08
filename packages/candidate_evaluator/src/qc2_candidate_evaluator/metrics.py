"""Independent deterministic aggregate metrics for held-out candidate evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

from .models import EvaluationError
from .policy import FROZEN_POLICY


_QUANTUM = Decimal(1).scaleb(-FROZEN_POLICY.decimal_places)
_EPSILON = Decimal("0.000000000001")


def as_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise EvaluationError(f"{field} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EvaluationError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise EvaluationError(f"{field} must be a finite decimal")
    return result


def quantize(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def metric_text(value: Decimal) -> str:
    return format(quantize(value), "f")


def compute_metrics(
    task: str,
    labels: Sequence[Decimal],
    predictions: Sequence[Decimal],
) -> dict[str, str]:
    if not labels or len(labels) != len(predictions):
        raise EvaluationError("held-out labels and predictions must have equal nonzero length")
    count = Decimal(len(labels))
    with localcontext() as context:
        context.prec = 40
        if task == "REGRESSION":
            errors = [prediction - label for label, prediction in zip(labels, predictions)]
            mse = sum((error * error for error in errors), Decimal(0)) / count
            mae = sum((abs(error) for error in errors), Decimal(0)) / count
            baseline_mse = sum((label * label for label in labels), Decimal(0)) / count
            rmse = mse.sqrt()
            baseline_rmse = baseline_mse.sqrt()
            skill = (
                Decimal(1) - (rmse / baseline_rmse)
                if baseline_rmse != 0
                else Decimal(0)
            )
            return {
                "observation_count": str(len(labels)),
                "rmse": metric_text(rmse),
                "mae": metric_text(mae),
                "zero_baseline_rmse": metric_text(baseline_rmse),
                "rmse_skill_vs_zero": metric_text(skill),
            }

        if task != "BINARY_CLASSIFICATION":
            raise EvaluationError("candidate task is not allowlisted")
        if any(label not in (Decimal(0), Decimal(1)) for label in labels):
            raise EvaluationError("binary held-out labels must be exactly zero or one")
        if any(prediction < 0 or prediction > 1 for prediction in predictions):
            raise EvaluationError("binary predictions must lie in [0, 1]")

        brier = sum(
            ((prediction - label) ** 2 for label, prediction in zip(labels, predictions)),
            Decimal(0),
        ) / count
        baseline_brier = sum(
            ((Decimal("0.5") - label) ** 2 for label in labels),
            Decimal(0),
        ) / count
        log_loss = Decimal(0)
        for label, prediction in zip(labels, predictions):
            clipped = min(Decimal(1) - _EPSILON, max(_EPSILON, prediction))
            log_loss -= label * clipped.ln() + (Decimal(1) - label) * (
                Decimal(1) - clipped
            ).ln()
        log_loss /= count

        bin_count = FROZEN_POLICY.calibration_bins
        bin_rows: list[list[tuple[Decimal, Decimal]]] = [
            [] for _ in range(bin_count)
        ]
        for label, prediction in zip(labels, predictions):
            index = min(bin_count - 1, int(prediction * bin_count))
            bin_rows[index].append((label, prediction))
        ece = Decimal(0)
        for members in bin_rows:
            if not members:
                continue
            size = Decimal(len(members))
            observed = sum((item[0] for item in members), Decimal(0)) / size
            predicted = sum((item[1] for item in members), Decimal(0)) / size
            ece += (size / count) * abs(observed - predicted)

        return {
            "observation_count": str(len(labels)),
            "brier": metric_text(brier),
            "fixed_0_5_baseline_brier": metric_text(baseline_brier),
            "log_loss": metric_text(log_loss),
            "expected_calibration_error_10_bin": metric_text(ece),
        }
