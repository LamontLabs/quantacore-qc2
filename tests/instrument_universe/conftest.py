from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "instrument_universe" / "src"))


@pytest.fixture(scope="session")
def valid_contract_fixtures() -> dict[str, dict[str, Any]]:
    path = ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["contract"]: row["payload"] for row in rows}


@pytest.fixture(scope="session")
def supporting_contracts(
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> tuple[tuple[str, dict[str, Any]], ...]:
    objects = [(name, deepcopy(record)) for name, record in valid_contract_fixtures.items()]
    second_manifest = deepcopy(valid_contract_fixtures["ArtifactManifest"])
    second_manifest["id"] = "018f0000-0000-7000-8000-000000000002"
    second_manifest["content_hash"] = "b" * 64
    objects.append(("ArtifactManifest", second_manifest))
    return tuple(objects)
