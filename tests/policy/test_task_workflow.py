from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parents[2] / "tools"
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from generate_task_docs import render_build_tasks, render_dependencies  # noqa: E402
from task_workflow import validate_registry  # noqa: E402


def _registry() -> dict[str, Any]:
    return json.loads((ROOT / "registry/BUILD_TASKS.json").read_text(encoding="utf-8"))


def _reset_task_states(registry: dict[str, Any]) -> None:
    for task in registry["tasks"]:
        task["status"] = "TODO"
        task["acceptance_receipt"] = None


def test_generated_task_docs_include_registry_status_and_receipts() -> None:
    registry = _registry()
    task = next(item for item in registry["tasks"] if item["task_id"] == "QC2-003")
    task["status"] = "PASS"
    task["acceptance_receipt"] = {
        "result": "PASS",
        "checked_at": "2026-10-07T14:00:00Z",
        "receipt": "docs/reference/QC2-003_ACCEPTANCE_RECEIPT.md",
        "contract_receipt": "docs/reference/QC2-003_ACCEPTANCE_RECORD.json",
        "task_record": "docs/reference/QC2-003_TASK_RECORD.json",
    }

    build_docs = render_build_tasks(registry)
    dependency_docs = render_dependencies(registry)
    assert "**Current status:** PASS" in build_docs
    assert "QC2-003_ACCEPTANCE_RECORD.json" in build_docs
    assert "Tasks with authorized original-protocol references" in dependency_docs
    assert "not source access or inspection" in dependency_docs


def test_pass_requires_durable_receipt() -> None:
    registry = _registry()
    _reset_task_states(registry)
    registry["tasks"][3]["status"] = "PASS"

    errors = validate_registry(registry, check_documents=False)
    assert any("QC2-003: PASS requires a PASS acceptance receipt" in error for error in errors)


def test_active_task_requires_every_declared_dependency_to_pass() -> None:
    registry = _registry()
    _reset_task_states(registry)
    registry["tasks"][4]["status"] = "IN_PROGRESS"

    errors = validate_registry(registry, check_documents=False)
    assert any("QC2-004: dependency QC2-003 is not PASS" in error for error in errors)


def test_registry_rejects_multiple_active_tasks() -> None:
    registry = _registry()
    _reset_task_states(registry)
    registry["tasks"][3]["status"] = "IN_PROGRESS"
    registry["tasks"][4]["status"] = "IN_PROGRESS"

    errors = validate_registry(registry, check_documents=False)
    assert any("more than one canonical task is IN_PROGRESS" in error for error in errors)
