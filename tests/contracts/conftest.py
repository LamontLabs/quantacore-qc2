from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def valid_contract_fixtures() -> dict[str, dict[str, Any]]:
    path = ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json"
    values = json.loads(path.read_text(encoding="utf-8"))
    return {item["contract"]: item["payload"] for item in values}


@pytest.fixture
def copy_payload():
    return deepcopy
