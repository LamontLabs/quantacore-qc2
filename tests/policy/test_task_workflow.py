from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from generate_task_docs import render_build_tasks, render_dependencies  # noqa: E402
from task_workflow import (  # noqa: E402
    WorkflowError,
    _acceptance_checklist_errors,
    _authorized_artifact_drift,
    _artifact_hash,
    _artifact_hash_at_commit,
    _require_integrated_file,
    validate_registry,
)


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
    assert "**Acceptance workflow version:** 2.0." in build_docs
    assert "Native task-board status and merge labels are projections only" in build_docs
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


def test_artifact_drift_requires_explicit_scope_and_downstream_acceptance() -> None:
    registry = _registry()
    _reset_task_states(registry)
    task = next(item for item in registry["tasks"] if item["task_id"] == "QC2-007")
    task["status"] = "IN_PROGRESS"

    reason = _authorized_artifact_drift(
        registry, "QC2-003", "packages/contracts", "new-contract-hash"
    )
    assert reason and "adds required configuration contracts" in reason
    assert (
        _authorized_artifact_drift(
            registry, "QC2-003", "packages/integrity_build", "new-contract-hash"
        )
        is None
    )

    task["status"] = "PASS"
    task["acceptance_receipt"] = {
        "result": "PASS",
        "changed_paths": ["packages/contracts"],
        "artifact_hashes": {"packages/contracts": "accepted-contract-hash"},
    }
    assert (
        _authorized_artifact_drift(
            registry, "QC2-003", "packages/contracts", "accepted-contract-hash"
        )
        is not None
    )
    assert (
        _authorized_artifact_drift(
            registry, "QC2-003", "packages/contracts", "later-unaccepted-hash"
        )
        is None
    )


def test_acceptance_checklist_requires_every_exact_deliverable_and_test() -> None:
    task = {
        "task_id": "QC2-999",
        "required_deliverables": ["Versioned authority record."],
        "required_tests": ["pytest -q tests/test_authority.py"],
    }
    complete = """## Acceptance checklist
- [x] DELIVERABLE: Versioned authority record. | evidence: docs/authority.md
- [x] TEST: pytest -q tests/test_authority.py | evidence: 8 passed
"""
    assert _acceptance_checklist_errors(task, complete) == []

    incomplete = """## Acceptance checklist
- [x] DELIVERABLE: Versioned authority record. | evidence: docs/authority.md
"""
    errors = _acceptance_checklist_errors(task, incomplete)
    assert any("required test is not checked" in error for error in errors)

    wrong_contract = """## Acceptance checklist
- [x] DELIVERABLE: Versioned authority record. | evidence: docs/authority.md
- [x] TEST: pytest -q tests/other.py | evidence: 8 passed
"""
    errors = _acceptance_checklist_errors(task, wrong_contract)
    assert any("not in the task contract" in error for error in errors)


def test_receipt_artifact_hash_is_bound_to_commit_and_integrated_worktree(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Acceptance Test"],
        check=True,
    )
    artifact = tmp_path / "docs" / "output" / "receipt.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("tested bytes\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "docs/output"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "tested artifact"],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    committed_hash = _artifact_hash_at_commit(tmp_path, commit, "docs/output")
    assert committed_hash == _artifact_hash(tmp_path, "docs/output")
    _require_integrated_file(tmp_path, "docs/output/receipt.txt")

    artifact.write_text("uncommitted replacement\n", encoding="utf-8")
    assert _artifact_hash_at_commit(tmp_path, commit, "docs/output") == committed_hash
    assert _artifact_hash(tmp_path, "docs/output") != committed_hash
    with pytest.raises(WorkflowError, match="differs from workspace"):
        _require_integrated_file(tmp_path, "docs/output/receipt.txt")
