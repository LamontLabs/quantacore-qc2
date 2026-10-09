from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
for package in ("contracts", "execution"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))


@pytest.fixture(scope="session")
def valid_intent_fixture() -> dict[str, Any]:
    path = ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json"
    values = json.loads(path.read_text(encoding="utf-8"))
    return deepcopy(next(row["payload"] for row in values if row["contract"] == "PaperOrderIntent"))
