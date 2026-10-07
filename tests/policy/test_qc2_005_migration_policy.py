import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(REPOSITORY_ROOT / "packages" / "contracts" / "src"),
)

from qc2_contracts.catalog import AUTHORITY_OVERRIDES, FAMILIES  # noqa: E402


MIGRATION = (
    REPOSITORY_ROOT
    / "migrations"
    / "0001_postgresql_authority_foundation.sql"
).read_text()


def test_migration_roles_and_family_reader_grants_match_contract_catalog():
    expected_roles = set(AUTHORITY_OVERRIDES.values())
    expected_roles.update(
        role for family in FAMILIES for role in family.reader_roles
    )
    roles_block = re.search(
        r"authorities constant text\[\] := ARRAY\[(.*?)\];",
        MIGRATION,
        re.DOTALL,
    )
    assert roles_block is not None
    actual_roles = set(re.findall(r"'([a-z][a-z0-9_]*)'", roles_block.group(1)))
    assert actual_roles == expected_roles

    runtime_source = (
        REPOSITORY_ROOT / "lib" / "db" / "src" / "environment.js"
    ).read_text()
    runtime_roles_block = re.search(
        r"DATABASE_AUTHORITIES = Object\.freeze\(\[(.*?)\]\)",
        runtime_source,
        re.DOTALL,
    )
    assert runtime_roles_block is not None
    assert set(
        re.findall(r'"([a-z][a-z0-9_]*)"', runtime_roles_block.group(1))
    ) == expected_roles

    expected_schemas = {
        f"qc2_{family.slug}": set(family.reader_roles)
        for family in FAMILIES
    }
    created_schemas = set(
        re.findall(
            r"CREATE SCHEMA (qc2_[a-z_]+) AUTHORIZATION qc2_migrator;",
            MIGRATION,
        )
    )
    assert created_schemas == {"qc2_control", *expected_schemas}

    granted_roles = {}
    for schema, grant_body in re.findall(
        r"GRANT USAGE ON SCHEMA (qc2_[a-z_]+) TO(.*?);",
        MIGRATION,
        re.DOTALL,
    ):
        if schema in expected_schemas:
            granted_roles[schema] = set(
                re.findall(r"qc2_runtime_([a-z][a-z0-9_]*)", grant_body)
            )
    assert granted_roles == expected_schemas


def test_runtime_identity_is_explicit_and_non_privileged():
    environment_source = (
        REPOSITORY_ROOT / "lib" / "db" / "src" / "environment.js"
    ).read_text()
    runtime_source = (REPOSITORY_ROOT / "lib" / "db" / "src" / "index.ts").read_text()

    assert "QC2_DATABASE_URL_${suffix}" in environment_source
    assert "QC2_EXPECTED_DATABASE_${qc2Environment.toUpperCase()}" in environment_source
    assert "generic DATABASE_URL is not an allowed fallback" in environment_source
    assert "current_database() AS database_name" in runtime_source
    assert "roles.rolsuper AS is_superuser" in runtime_source
    assert "roles.rolbypassrls AS bypasses_rls" in runtime_source
    assert "roles.rolinherit AS inherits_roles" in runtime_source
    assert "pg_catalog.pg_has_role(" in runtime_source
    assert "has_role_membership" in runtime_source


def test_schema_sync_is_not_available_from_runtime_or_post_merge():
    package = json.loads(
        (REPOSITORY_ROOT / "lib" / "db" / "package.json").read_text()
    )
    assert "push" not in package["scripts"]
    assert "push-force" not in package["scripts"]
    assert "migrate" in package["scripts"]
    assert package["scripts"]["migrate"] == "node ./run-migrations.mjs"

    post_merge = (REPOSITORY_ROOT / "scripts" / "post-merge.sh").read_text()
    assert "push" not in post_merge
    assert "migrate" not in post_merge

    config = (REPOSITORY_ROOT / "lib" / "db" / "drizzle.config.ts").read_text()
    assert "push-force" in config and "Drizzle Kit database mutation commands are disabled" in config
    assert "process.env.DATABASE_URL" not in config

    runner = (REPOSITORY_ROOT / "lib" / "db" / "run-migrations.mjs").read_text()
    assert 'process.argv.includes("--apply")' in runner
    assert '["development", "test"].includes(migrationEnvironment)' in runner
    assert "Migration connection is not the isolated qc2_migrator identity." in runner
    assert "has_qc2_role_membership" in runner


def test_forward_migration_has_no_destructive_ddl():
    assert not re.search(r"\b(DROP|TRUNCATE)\b", MIGRATION, re.IGNORECASE)
