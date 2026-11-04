"""Local acceptance on two recoverable copies, never migrate the running demo database."""

import hashlib
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import make_engine  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

OLD = "0012_evidence_foundation"
NEW = "0013_reference_corpus"


def execute(argv, *, stdin=None, stdout=None):
    result = subprocess.run(
        argv,
        cwd=ROOT,
        stdin=stdin,
        stdout=stdout or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError("controlled_command_failed")
    return result.stdout


def secure_directory(path):
    path.mkdir(parents=True, exist_ok=False)
    if os.name == "nt":
        script = """$ErrorActionPreference='Stop';
        $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User;
        $acl=New-Object System.Security.AccessControl.DirectorySecurity;
        $acl.SetAccessRuleProtection($true,$false);
        $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow');
        $acl.AddAccessRule($rule);
        Set-Acl -LiteralPath $env:TRUEFLAG_GATE_BACKUP_DIR -AclObject $acl;
        $actual=Get-Acl -LiteralPath $env:TRUEFLAG_GATE_BACKUP_DIR;
        if (-not $actual.AreAccessRulesProtected) {throw 'ACL not protected'};
        foreach ($entry in $actual.Access) {
          if ($entry.AccessControlType -eq 'Allow' -and $entry.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) {throw 'Unexpected reader'}
        }"""
        env = {**os.environ, "TRUEFLAG_GATE_BACKUP_DIR": str(path)}
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode:
            raise RuntimeError("private_backup_acl_unavailable")
    else:
        path.chmod(0o700)


def scalar(engine, statement):
    with engine.connect() as connection:
        return connection.scalar(text(statement))


def fingerprints(engine, tables):
    result = {}
    quote = engine.dialect.identifier_preparer.quote_identifier
    with engine.connect() as connection:
        connection.execute(text("SET statement_timeout='60s'"))
        for table in tables:
            digest, count = hashlib.sha256(), 0
            rows = connection.execution_options(stream_results=True).execute(
                text(
                    f'SELECT row_to_json(t)::text FROM public.{quote(table)} AS t ORDER BY row_to_json(t)::text COLLATE "C"'
                )
            )
            for value in rows.scalars():
                data = value.encode()
                digest.update(len(data).to_bytes(8, "big"))
                digest.update(data)
                count += 1
            result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def schema_inventory(engine, tables, original_functions=None):
    catalog = inspect(engine)
    result = {}
    for table in tables:
        result[table] = {
            "columns": [
                (c["name"], str(c["type"]), c["nullable"], c["default"])
                for c in catalog.get_columns(table)
            ],
            "pk": catalog.get_pk_constraint(table),
            "fks": catalog.get_foreign_keys(table),
            "unique": catalog.get_unique_constraints(table),
            "checks": catalog.get_check_constraints(table),
            "indexes": catalog.get_indexes(table),
        }
    with engine.connect() as connection:
        for table in tables:
            result[table]["triggers"] = [
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT t.tgname,pg_get_triggerdef(t.oid,true) FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relname=:table AND NOT t.tgisinternal ORDER BY t.tgname"
                    ),
                    {"table": table},
                )
            ]
        functions = {
            row.name: row.definition
            for row in connection.execute(
                text(
                    "SELECT p.proname||'('||pg_get_function_identity_arguments(p.oid)||')' AS name, "
                    "pg_get_functiondef(p.oid) AS definition FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f'"
                )
            )
        }
    return {
        "tables": result,
        "functions": functions
        if original_functions is None
        else {name: functions.get(name) for name in original_functions},
    }


@contextmanager
def database_environment(url):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    try:
        yield Config(str(ROOT / "backend/alembic.ini"))
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def create_copy(control, name):
    if not re.fullmatch(r"tf_reference_gate_(?:clone|restore)_[a-f0-9]{32}", name):
        raise RuntimeError("unsafe_clone_name")
    with control.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))


def main():
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("local_postgres_required")
    live = make_engine(settings.database_url)
    assert scalar(live, "SELECT version_num FROM alembic_version") == OLD
    assert scalar(live, "SELECT pg_database_size(current_database())") <= 536870912
    token = uuid4().hex
    private = ROOT / "runtime" / "regulatory-approval-gate" / token
    assert private.resolve().is_relative_to((ROOT / "runtime").resolve())
    secure_directory(private)
    archive = private / "current-demo.pgcustom"
    docker = ["docker", "compose", "exec", "-T", "db"]
    with archive.open("xb") as output:
        execute(
            [
                *docker,
                "pg_dump",
                "-U",
                url.username,
                "-d",
                url.database,
                "-Fc",
                "--no-owner",
                "--no-acl",
                "--lock-wait-timeout=5s",
            ],
            stdout=output,
        )
    assert 0 < archive.stat().st_size <= 268435456
    with archive.open("rb") as source:
        execute([*docker, "pg_restore", "--list"], stdin=source)
    clone_name, restore_name = (
        "tf_reference_gate_clone_" + token,
        "tf_reference_gate_restore_" + token,
    )
    create_copy(live, clone_name)
    with archive.open("rb") as source:
        execute(
            [
                *docker,
                "pg_restore",
                "-U",
                url.username,
                "-d",
                clone_name,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            stdin=source,
        )
    copy_url = url.set(database=clone_name)
    copy = make_engine(copy_url.render_as_string(hide_password=False))
    tables = sorted(set(inspect(copy).get_table_names()) - {"alembic_version"})
    assert len(tables) == 36 and scalar(copy, "SELECT version_num FROM alembic_version") == OLD
    before = fingerprints(copy, tables)
    structure = schema_inventory(copy, tables)
    with database_environment(copy_url) as config:
        command.upgrade(config, NEW)
        command.check(config)
        assert len(inspect(copy).get_table_names()) == 47
        assert (
            fingerprints(copy, tables) == before
            and schema_inventory(copy, tables, structure["functions"]) == structure
        )
        assert (
            scalar(
                copy,
                "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated",
            )
            == 0
        )
        assert (
            scalar(
                copy,
                "SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname='ix_reference_chunks_fts' AND indexdef LIKE '%USING gin%'",
            )
            == 1
        )
        command.downgrade(config, OLD)
        assert len(inspect(copy).get_table_names()) == 37
        assert (
            fingerprints(copy, tables) == before
            and schema_inventory(copy, tables, structure["functions"]) == structure
        )
        command.upgrade(config, NEW)
        command.check(config)
        # A synthetic guard probe is inserted ONLY in the disposable clone, never approved.
        with copy.begin() as connection:
            actor = connection.scalar(
                text("SELECT id FROM users WHERE role='admin' AND active=true ORDER BY id LIMIT 1")
            )
            assert actor is not None
            connection.execute(
                text(
                    "INSERT INTO reference_sources (id,created_at,key,publisher,host,owner_id) VALUES (:id,now(),'migration-guard-probe','Synthetic guard probe, not authority','www.ecfr.gov',:actor)"
                ),
                {"id": uuid4(), "actor": actor},
            )
        try:
            command.downgrade(config, OLD)
        except RuntimeError as error:
            assert str(error) == "Refusing to erase retained regulatory history"
        else:
            raise AssertionError("retained_history_downgrade_not_blocked")
        assert scalar(copy, "SELECT version_num FROM alembic_version") == NEW
        assert fingerprints(copy, tables) == before
        assert scalar(copy, "SELECT count(*) FROM reference_approvals") == 0
        assert scalar(copy, "SELECT count(*) FROM corpus_releases") == 0
    create_copy(live, restore_name)
    with archive.open("rb") as source:
        execute(
            [
                *docker,
                "pg_restore",
                "-U",
                url.username,
                "-d",
                restore_name,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            stdin=source,
        )
    restored = make_engine(url.set(database=restore_name).render_as_string(hide_password=False))
    assert scalar(restored, "SELECT version_num FROM alembic_version") == OLD
    assert (
        fingerprints(restored, tables) == before and schema_inventory(restored, tables) == structure
    )
    assert scalar(live, "SELECT version_num FROM alembic_version") == OLD
    private_manifest = {
        "archive": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "clone_database": clone_name,
        "restored_database": restore_name,
        "legacy_fingerprints": before,
    }
    (private / "recovery-manifest.json").write_text(
        json.dumps(private_manifest, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS",
        "live_schema_before_after": OLD,
        "source_database_write_commands": 0,
        "legacy_tables_verified": len(tables),
        "archive_format": "PostgreSQL custom",
        "archive_bytes": archive.stat().st_size,
        "archive_access": "current_os_user_only",
        "restore_verified": True,
        "upgrade": NEW,
        "empty_rollback": OLD,
        "reupgrade": NEW,
        "schema_drift": False,
        "legacy_row_fingerprints_match": True,
        "legacy_schema_inventory_matches": True,
        "legacy_triggers_and_functions_match": True,
        "invalid_constraints": 0,
        "gin_index_verified": True,
        "retained_history_rollback": "blocked_as_required",
        "approved_sources": 0,
        "published_releases": 0,
        "private_recovery_directory": str(private.relative_to(ROOT)),
    }
    (ROOT / "runtime/phase3-4-approval-migration.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    restored.dispose()
    copy.dispose()
    live.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "migration_copy_verification_unavailable",
                    "live_migration_attempted": False,
                }
            )
        )
        raise SystemExit(1) from None
