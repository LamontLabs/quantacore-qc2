from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migrations_do_not_grant_apexlab_direct_outcome_table_reads() -> None:
    sql = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "migrations").glob("*.sql"))
    )
    direct_apexlab_grant = re.compile(
        r"""
        \bGRANT\s+(?:SELECT|ALL(?:\s+PRIVILEGES)?)\s+ON\s+
        (?:
            TABLE\s+qc2_outcomes_research\.
            |
            ALL\s+TABLES\s+IN\s+SCHEMA\s+qc2_outcomes_research\b
        )
        [^;]*\bTO\b[^;]*\b(?:qc2_runtime_apexlab|PUBLIC)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    default_apexlab_grant = re.compile(
        r"""
        \bALTER\s+DEFAULT\s+PRIVILEGES\b[^;]*
        \bIN\s+SCHEMA\s+qc2_outcomes_research\b[^;]*
        \bGRANT\s+(?:SELECT|ALL(?:\s+PRIVILEGES)?)\b[^;]*
        \bTO\b[^;]*\b(?:qc2_runtime_apexlab|PUBLIC)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    assert "GRANT USAGE ON SCHEMA qc2_outcomes_research" in sql
    assert direct_apexlab_grant.search(sql) is None
    assert default_apexlab_grant.search(sql) is None
