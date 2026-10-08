"""Explicit resource and expiry limits for promotion bundle archives."""

from __future__ import annotations

from dataclasses import dataclass


class PromotionBundleError(ValueError):
    """A promotion bundle is malformed, unsafe, expired, or incomplete."""


@dataclass(frozen=True, slots=True)
class BundleLimits:
    """Caller-supplied archive and bundle lifetime policy; no implicit defaults."""

    max_archive_bytes: int
    max_uncompressed_bytes: int
    max_file_bytes: int
    max_entries: int
    max_compression_ratio: int
    max_lifetime_seconds: int

    def __post_init__(self) -> None:
        values = {
            "max_archive_bytes": self.max_archive_bytes,
            "max_uncompressed_bytes": self.max_uncompressed_bytes,
            "max_file_bytes": self.max_file_bytes,
            "max_entries": self.max_entries,
            "max_compression_ratio": self.max_compression_ratio,
            "max_lifetime_seconds": self.max_lifetime_seconds,
        }
        if any(type(value) is not int or value < 1 for value in values.values()):
            raise PromotionBundleError("all bundle limits must be explicit positive integers")
        if self.max_file_bytes > self.max_uncompressed_bytes:
            raise PromotionBundleError("per-file limit cannot exceed the total unpacked limit")
        if self.max_entries < 4:
            raise PromotionBundleError("bundle limit must allow three metadata files and one payload")
