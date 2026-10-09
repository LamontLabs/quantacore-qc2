"""Provider-neutral page metadata returned by read-only activity queries."""

from __future__ import annotations

from dataclasses import dataclass

from .models import NormalizedFill


@dataclass(frozen=True, slots=True)
class ActivityPage:
    activities: tuple[NormalizedFill, ...]
    next_page_token: str | None
    direction: str = "desc"
