"""Create a sanitized, authenticated, GET-only Alpaca paper identity observation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator
from qc2_alpaca_paper.identity import observe_account_identity
from qc2_alpaca_paper.models import (
    AlpacaPaperError,
    PaperHostViolation,
    ProviderRequestFailed,
)
from qc2_alpaca_paper.transport import StdlibPaperTransport
from qc2_alpaca_paper.fingerprint import FINGERPRINT_SCHEME_ID
from qc2_contracts.runtime import (
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
)


OBSERVATION_SCHEMA = "qc2.identity_market.AlpacaPaperIdentityObservation.v1"
OBSERVATION_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/QC2-047_PAPER_ACCOUNT_IDENTITY_OBSERVATION.schema.json"
)
OBSERVATION_HASH_DOMAIN = "qc2.alpaca-paper-identity-observation.v1"
ORDERS_PROBE_PATH = "/v2/orders?status=all&limit=1"


def _utc_instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def create_observation(source_identity: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_identity):
        raise RuntimeError("source_identity_must_be_a_full_git_commit")
    environment_namespace = os.environ.get("REPLIT_ENVIRONMENT")
    if environment_namespace not in {
        "development",
        "test",
        "research",
        "production",
    }:
        raise RuntimeError("replit_environment_namespace_missing_or_invalid")
    api_key = os.environ.get("APCA_API_KEY_ID")
    secret_key = os.environ.get("APCA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError("alpaca_paper_credentials_missing")

    transport = StdlibPaperTransport(api_key, secret_key)
    identity = observe_account_identity(transport)

    orders_response = transport.request("GET", ORDERS_PROBE_PATH)
    if 300 <= orders_response.status_code < 400:
        raise PaperHostViolation("paper_redirect_blocked")
    if orders_response.status_code != 200:
        raise ProviderRequestFailed(orders_response.status_code)
    orders_status = orders_response.status_code
    del orders_response
    observed_at = _utc_instant(datetime.now(UTC))

    observation: dict[str, object] = {
        "schema_name": OBSERVATION_SCHEMA,
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": observed_at,
        "owning_authority": "market_data",
        "evidence_class": "FORWARD_OPERATIONAL",
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "record_hash": "0" * 64,
        "fingerprint_scheme": FINGERPRINT_SCHEME_ID,
        "account_fingerprint": identity.account_fingerprint,
        "broker": identity.broker,
        "environment": identity.environment,
        "origin": identity.origin,
        "observed_at": observed_at,
        "tested_source_identity": source_identity,
        "capability": "PAPER_TRADING",
        "observed_result": "PARTIAL",
        "account_endpoint_http_status": 200,
        "orders_endpoint_http_status": orders_status,
        "account_status": identity.account_status,
        "trading_blocked": identity.trading_blocked,
        "account_blocked": identity.account_blocked,
        "historical_account_continuity": "UNVERIFIED",
        "execution_authorized": False,
        "evidence_refs": [
            "docs/reference/QC2-047_PAPER_ACCOUNT_IDENTITY_OBSERVATION.schema.json",
            "docs/reference/QC2-047_ACCOUNT_FINGERPRINT_V1.md",
            "tools/qc2_047_readonly_probe.py",
            "docs/reference/QC2-047_READ_ONLY_PROBE_REPORT.md",
            "docs/reference/QC2-010_ACCOUNT_IDENTITY_REVALIDATION_2026-10-09.md",
        ],
    }
    hash_payload = {
        key: value
        for key, value in observation.items()
        if key != "record_hash"
    }
    observation["record_hash"] = domain_separated_sha256(
        OBSERVATION_HASH_DOMAIN,
        canonical_json_bytes(hash_payload),
    )
    schema = json.loads(OBSERVATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(observation)
    return observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-identity", required=True)
    args = parser.parse_args()
    try:
        observation = create_observation(args.source_identity)
    except Exception as exc:
        detail = (
            str(exc)
            if isinstance(exc, (AlpacaPaperError, ConnectionError, RuntimeError))
            else type(exc).__name__
        )
        print(f"qc2_047_probe_failed:{detail}", file=sys.stderr)
        return 2
    print(json.dumps(observation, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
