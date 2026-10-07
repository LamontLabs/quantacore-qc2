from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations" / "0002_evidence_authority.sql").read_text()
RUNNER = (
    ROOT / "lib" / "db" / "test" / "run-qc2-006-postgres-integration.mjs"
).read_text()


def test_evidence_append_uses_locked_head_and_unique_committed_sequence() -> None:
    assert re.search(
        r"SELECT \* INTO stream_row\s+FROM qc2_integrity_build\.evidence_stream_head"
        r"\s+WHERE active\s+FOR UPDATE",
        MIGRATION,
        re.IGNORECASE,
    )
    assert re.search(
        r"UNIQUE\s*\(stream_id,\s*sequence\)",
        MIGRATION,
        re.IGNORECASE,
    )
    assert "MAX(sequence)" not in MIGRATION.upper()
    assert "nextval(" not in MIGRATION.lower()


def test_domain_mutation_capture_is_transactional_for_protected_tables() -> None:
    trigger_names = {
        "job_definition": "evidence_job_definition_mutations",
        "job_lease": "evidence_job_lease_mutations",
        "outbox_message": "evidence_outbox_mutations",
        "reservation_resource": "evidence_reservation_resource_mutations",
        "resource_reservation": "evidence_resource_reservation_mutations",
    }
    for table, trigger_name in trigger_names.items():
        trigger = re.compile(
            rf"CREATE TRIGGER {trigger_name}.*?"
            rf"AFTER INSERT OR UPDATE OR DELETE ON [\w.]+\.",
            re.IGNORECASE | re.DOTALL,
        )
        assert trigger.search(MIGRATION), f"missing mutation evidence trigger: {table}"
    assert "append_event_internal(" in MIGRATION
    assert "RAISE EXCEPTION 'No active evidence stream is configured'" in MIGRATION


def test_evidence_and_checkpoints_are_append_only_even_for_migrator() -> None:
    for table in ("evidence_event", "evidence_checkpoint"):
        assert re.search(
            rf"BEFORE UPDATE OR DELETE ON qc2_integrity_build\.{table}",
            MIGRATION,
            re.IGNORECASE,
        )
        assert re.search(
            rf"BEFORE TRUNCATE ON qc2_integrity_build\.{table}",
            MIGRATION,
            re.IGNORECASE,
        )


def test_sealed_evidence_requires_external_anchor_and_never_falls_back() -> None:
    assert "FORWARD_SEALED writes require an approved independent anchor" in MIGRATION
    assert "FORWARD_SEALED checkpoints require an approved independent anchor" in MIGRATION
    assert "FORWARD_SEALED requires an approved independent anchor" in MIGRATION
    assert "independent anchor" in MIGRATION


def test_postgres_acceptance_runs_in_order_and_rolls_back() -> None:
    assert RUNNER.index("migrations/0001_postgresql_authority_foundation.sql") < RUNNER.index(
        "tests/database/qc2_005_postgres_acceptance.sql"
    )
    assert RUNNER.index("tests/database/qc2_005_postgres_acceptance.sql") < RUNNER.index(
        "migrations/0002_evidence_authority.sql"
    )
    assert RUNNER.index("migrations/0002_evidence_authority.sql") < RUNNER.index(
        "tests/database/qc2_006_postgres_acceptance.sql"
    )
    assert 'await client.query("ROLLBACK")' in RUNNER
