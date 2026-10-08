"""Typed boundaries for offline replay."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


class ReplayError(ValueError):
    """The replay request, retained bundle, or result is invalid."""


class ReplayInputError(ReplayError):
    """A top-level QC2 contract or trusted executor binding is invalid."""


@dataclass(frozen=True, slots=True)
class ReplayLimits:
    """Caller-supplied limits, normally derived from a sealed ResourceBudget."""

    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    max_dependency_depth: int

    def __post_init__(self) -> None:
        for name, value in (
            ("max_files", self.max_files),
            ("max_file_bytes", self.max_file_bytes),
            ("max_total_bytes", self.max_total_bytes),
            ("max_dependency_depth", self.max_dependency_depth),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class StageExecutor:
    """Trusted application code bound to an immutable stage identity."""

    executor_id: str
    stage_kind: str
    implementation_hash: str
    execute: Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ReplayRunResult:
    """Receipt plus machine-readable stage and dependency diagnostics."""

    receipt: Mapping[str, Any]
    stage_comparisons: tuple[Mapping[str, Any], ...]
    dependency_closure: tuple[str, ...]
    scientific_payload_bytes: Mapping[str, bytes]
    corrected_input_identity: str | None
