from importlib.metadata import version
import sys
from pathlib import Path

import pytest
import ruff


ROOT = Path(__file__).resolve().parents[2]


def test_python_runtime_and_tool_versions_are_pinned() -> None:
    assert sys.version_info[:3] == (3, 13, 11)
    assert pytest.__version__ == "9.1.1"
    assert ruff.__file__ is not None
    assert version("ruff") == "0.16.10"


def test_required_repository_boundaries_exist() -> None:
    required_paths = [
        "packages/contracts",
        "packages/science",
        "packages/core",
        "packages/execution",
        "packages/apexlab",
        "packages/owner_api",
        "packages/promotion",
        "apps/android",
        "migrations",
        "tests",
        "docs",
        "tools",
    ]

    missing = [path for path in required_paths if not (ROOT / path).is_dir()]
    assert not missing, f"Missing repository boundaries: {missing}"
