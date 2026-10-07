"""Typed failures for the QC2 instrument-universe authority."""

from __future__ import annotations


class UniverseAuthorityError(ValueError):
    """A universe input or construction rule was violated."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)
