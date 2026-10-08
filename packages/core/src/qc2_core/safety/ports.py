"""Capability boundary with explicit unavailable stubs and no live adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import (
    CapabilityDomain,
    GateObservation,
    GateStatus,
    SafetyGatePolicy,
    SafetyViolation,
)


class SafetyCapabilityPort(Protocol):
    """Injected capability boundary; implementations return evidence, not side effects."""

    def observe(
        self,
        policy: SafetyGatePolicy,
        *,
        evaluated_at: str,
        input_generation: int,
    ) -> GateObservation: ...


@dataclass(frozen=True, slots=True)
class UnavailableCapabilityPort:
    """Honest stub for an unconfigured capability; it never claims availability."""

    domain: CapabilityDomain
    reason_code: str = "CAPABILITY_UNAVAILABLE"

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "domain", CapabilityDomain(self.domain))
        except ValueError as exc:
            raise SafetyViolation("unavailable port has an unsupported domain") from exc
        if not self.reason_code or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
            for character in self.reason_code
        ):
            raise SafetyViolation("unavailable port reason must be an uppercase reason code")

    def observe(
        self,
        policy: SafetyGatePolicy,
        *,
        evaluated_at: str,
        input_generation: int,
    ) -> GateObservation:
        if policy.domain is not self.domain:
            raise SafetyViolation("capability port domain does not match the gate policy")
        return GateObservation(
            gate_id=policy.gate_id,
            action=policy.action,
            domain=policy.domain,
            status=GateStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            freshness_deadline=evaluated_at,
            input_generation=input_generation,
            reason_codes=(self.reason_code,),
        )
