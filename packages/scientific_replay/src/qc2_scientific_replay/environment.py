"""Qualified runtime fingerprints for exact and compatibility replay."""

from __future__ import annotations

import decimal
import hashlib
import locale
import platform
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qc2_contracts.runtime import canonical_json_bytes


PROFILE_SCHEMA = "qc2.scientific_replay.QualifiedEnvironmentProfile.v1"
ENVIRONMENT_DOMAIN = b"qc2.scientific-replay-environment.v1\0"


def capture_runtime_environment() -> dict[str, Any]:
    """Capture deterministic runtime facts that can affect scientific output."""
    try:
        locale_name = list(locale.getlocale())
    except (TypeError, ValueError):
        locale_name = [None, None]
    local_timezone = datetime.now().astimezone().tzname() or ""
    context = decimal.getcontext()
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": list(sys.version_info[:3]),
        "python_cache_tag": sys.implementation.cache_tag or "",
        "python_platform": sys.platform,
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
        "byteorder": sys.byteorder,
        "preferred_encoding": locale.getpreferredencoding(False),
        "locale": locale_name,
        "timezone_name": local_timezone,
        "decimal_precision": context.prec,
        "decimal_rounding": context.rounding,
        "decimal_emin": context.Emin,
        "decimal_emax": context.Emax,
        "decimal_clamp": context.clamp,
        "monotonic_clock_implementation": time.get_clock_info("monotonic").implementation,
    }


def environment_fingerprint(profile_body: Mapping[str, Any]) -> str:
    """Return the versioned digest of the profile body, excluding its digest."""
    body = dict(profile_body)
    body.pop("fingerprint", None)
    return hashlib.sha256(ENVIRONMENT_DOMAIN + canonical_json_bytes(body)).hexdigest()


def build_environment_profile(
    *,
    package_lock_hash: str,
    executor_hashes: Mapping[str, str],
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the complete qualified profile pinned by ReplayRequest."""
    if len(package_lock_hash) != 64 or any(c not in "0123456789abcdef" for c in package_lock_hash):
        raise ValueError("package_lock_hash must be lowercase SHA-256")
    normalized_hashes = dict(sorted(executor_hashes.items()))
    if not normalized_hashes or any(
        len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
        for value in normalized_hashes.values()
    ):
        raise ValueError("executor_hashes must contain lowercase SHA-256 values")
    profile: dict[str, Any] = {
        "schema_name": PROFILE_SCHEMA,
        "schema_version": "1.0",
        "package_lock_hash": package_lock_hash,
        "runtime": dict(runtime or capture_runtime_environment()),
        "executor_hashes": normalized_hashes,
    }
    profile["fingerprint"] = environment_fingerprint(profile)
    return profile
