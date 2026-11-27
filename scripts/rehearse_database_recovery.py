"""G0.3 isolated recovery rehearsal. Never migrates, restarts or writes the source DB.

Run --step backup, provision, rehearse, restart, recover, tests, finalize in that order.
Private state and dumps stay in an owner-only, Git-ignored runtime directory.
Docker access is required. Source credentials are read in-process, never printed.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path("/workspace") if sys.platform == "linux" else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
OLD = "0012_evidence_foundation"
STAGES = ["0013_reference_corpus", "0014_investigation_foundation", "0015_investigation_drafts"]
IMAGE = "trueflag-assessment-verify:phase2-5"
MARKER = ROOT / "runtime/g0-3/current.json"


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def run(args, *, data=None, output=None, timeout=240, accept_failure=False):
    result = subprocess.run(
        args,
        cwd=ROOT,
        input=data,
        stdout=output or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if not accept_failure:
        check(result.returncode == 0, "controlled_subprocess_failed")
    return result


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_bytes())


def private_state():
    state = load(MARKER)
    directory = (ROOT / state["directory"]).resolve(strict=True)
    check(directory.is_relative_to((ROOT / "runtime/g0-3").resolve()), "unsafe_private_directory")
    check(re.fullmatch(r"[a-f0-9]{32}", state["token"]) is not None, "invalid_run_identity")
    return state, directory


def fingerprints(connection, tables, schema="public"):
    from sqlalchemy import text

    result = {}
    quote = connection.dialect.identifier_preparer.quote_identifier
    for table in tables:
        digest, count = hashlib.sha256(), 0
        rows = connection.execution_options(stream_results=True).execute(
            text(
                f"SELECT row_to_json(t)::text FROM {quote(schema)}.{quote(table)} t "
                'ORDER BY row_to_json(t)::text COLLATE "C"'
            )
        )
        for value in rows.scalars():
            data = value.encode()
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
            count += 1
        rows.close()
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    connection.execution_options(stream_results=False)
    return result


def canonical_catalog(catalog):
    """Normalize only pg_dump's equivalent varchar-literal-array text-cast rewrite."""
    result = json.loads(json.dumps(catalog))
    literal = r"'(?:[^']|'')*'::character varying"

    def rewrite(match):
        body = match.group(1)
        if re.fullmatch(literal + r"(?:,\s*" + literal + r")*", body) is None:
            return match.group(0)
        elements = re.sub(
            r"('(?:[^']|'')*')::character varying", r"\1::character varying::text", body
        )
        return "ARRAY[" + elements + "]"

    for row in result["constraints"]:
        row[3] = re.sub(r"ARRAY\[([^\[\]]+)\]::text\[\]", rewrite, row[3])
    return result


def inventory(connection, schema="public"):
    from sqlalchemy import text

    queries = {
        "tables": "SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1",
        "columns": "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
        "constraints": "SELECT c.relname,k.conname,k.contype,pg_get_constraintdef(k.oid,true),k.convalidated FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2",
        "indexes": "SELECT c.relname,i.relname,pg_get_indexdef(x.indexrelid),x.indisvalid,x.indisready FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2",
        "triggers": "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid,true),t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2",
        "functions": "SELECT p.proname||'('||pg_get_function_identity_arguments(p.oid)||')',pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f' ORDER BY 1",
    }
    return {
        key: [
            list(row)
            for row in connection.execute(
                text(sql.replace("n.nspname='public'", "n.nspname=:inventory_schema")),
                {"inventory_schema": schema},
            )
        ]
        for key, sql in queries.items()
    }


def integrity(connection, schema="public"):
    from sqlalchemy import inspect, text

    catalog = inventory(connection, schema)
    check(all(row[-1] for row in catalog["constraints"]), "unvalidated_constraint")
    check(all(row[-1] and row[-2] for row in catalog["indexes"]), "invalid_index")
    quote = connection.dialect.identifier_preparer.quote_identifier
    fk_count = 0
    for table in inspect(connection).get_table_names(schema=schema):
        for fk in inspect(connection).get_foreign_keys(table, schema=schema):
            child = fk["constrained_columns"]
            parent = fk["referred_columns"]
            nonnull = " AND ".join(f"a.{quote(c)} IS NOT NULL" for c in child)
            match = " AND ".join(f"b.{quote(p)}=a.{quote(c)}" for c, p in zip(child, parent))
            referred_schema = fk["referred_schema"] or schema
            query = (
                f"SELECT count(*) FROM {quote(schema)}.{quote(table)} a WHERE {nonnull} AND NOT EXISTS "
                f"(SELECT 1 FROM {quote(referred_schema)}.{quote(fk['referred_table'])} b WHERE {match})"
            )
            check(connection.scalar(text(query)) == 0, "orphan_foreign_key")
            fk_count += 1
    return {
        "foreign_keys_checked": fk_count,
        "orphan_rows": 0,
        "invalid_constraints": 0,
        "invalid_indexes": 0,
        "tables": len(catalog["tables"]),
        "indexes": len(catalog["indexes"]),
        "constraints": len(catalog["constraints"]),
        "triggers": len(catalog["triggers"]),
        "functions": len(catalog["functions"]),
    }


def subset_preserved(original, current):
    original, current = canonical_catalog(original), canonical_catalog(current)
    for key, rows in original.items():
        check(all(row in current[key] for row in rows), "original_schema_object_changed_" + key)


def preserved_files():
    paths = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    ).stdout.split(b"\0")
    values = {}
    for raw in paths:
        if raw:
            relative = raw.decode()
            path = ROOT / relative
            if path.is_file() and relative != "scripts/rehearse_database_recovery.py":
                values[relative] = sha(path)
    for relative in [".env", "backend/app/_release.json", "frontend/release-build.json"]:
        path = ROOT / relative
        if path.is_file():
            values[relative] = sha(path)
    manifest = load(ROOT / "assets/local/baseline/baseline.manifest.json")
    # All private scientific inputs, including explanation references, not just the model pickle.
    for subdirectory in ["assets/local/baseline", "assets/local/explanation_reference"]:
        for path in (ROOT / subdirectory).rglob("*"):
            if path.is_file():
                values[path.relative_to(ROOT).as_posix()] = sha(path)
    check(manifest is not None, "scientific_manifest_missing")
    return values


def backup():
    from app.core.config import Settings
    from app.core.database import make_engine
    from sqlalchemy import inspect, text
    from sqlalchemy.engine import make_url
    from verify_regulatory_migration_copy import secure_directory

    check(not MARKER.exists(), "existing_rehearsal_use_current_state")
    original = make_url(Settings().database_url)
    check(
        original.get_backend_name() == "postgresql" and original.host in {"localhost", "127.0.0.1"},
        "local_source_required",
    )
    token = uuid4().hex
    directory = ROOT / "runtime/g0-3" / token
    secure_directory(directory)
    check(
        run(["git", "check-ignore", str(directory / "source.pgcustom")]).returncode == 0,
        "private_directory_not_ignored",
    )
    save(directory / "original-files.json", preserved_files())
    container = run(["docker", "compose", "ps", "-q", "db"]).stdout.decode().strip()
    check(re.fullmatch(r"[a-f0-9]{64}", container) is not None, "source_container_missing")
    detail = load_json_docker(container)
    check(
        detail["Config"]["Labels"].get("com.docker.compose.project") == "trueflag-ai"
        and detail["Config"]["Labels"].get("com.docker.compose.service") == "db",
        "wrong_source_container",
    )
    engine = make_engine(original.render_as_string(hide_password=False))
    archive = directory / "source.pgcustom"
    started = time.monotonic()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout='60s'"))
        connection.execute(text("SET LOCAL lock_timeout='5s'"))
        check(
            connection.scalar(text("SELECT current_database()")) == original.database,
            "wrong_source_database",
        )
        check(
            connection.scalar(text("SELECT version_num FROM alembic_version")) == OLD,
            "source_not_0012",
        )
        check(
            connection.scalar(text("SELECT pg_database_size(current_database())")) < 536870912,
            "source_exceeds_rehearsal_limit",
        )
        schemas = list(
            connection.execute(
                text(
                    "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname!='information_schema' ORDER BY 1"
                )
            ).scalars()
        )
        check("public" in schemas and len(schemas) <= 10, "unexpected_source_schema_count")
        system_id = str(
            connection.scalar(text("SELECT system_identifier FROM pg_control_system()"))
        )
        check(
            run(
                [
                    "docker",
                    "exec",
                    container,
                    "psql",
                    "-XAt",
                    "-U",
                    original.username,
                    "-d",
                    original.database,
                    "-c",
                    "SELECT system_identifier FROM pg_control_system()",
                ]
            )
            .stdout.decode()
            .strip()
            == system_id,
            "source_host_container_identity_mismatch",
        )
        snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
        tables = sorted(inspect(connection).get_table_names(schema="public"))
        records = fingerprints(connection, [t for t in tables if t != "alembic_version"])
        catalog = inventory(connection)
        checks = integrity(connection)
        extra = {}
        for schema in schemas:
            if schema == "public":
                continue
            extra_tables = sorted(inspect(connection).get_table_names(schema=schema))
            extra[schema] = {
                "records": fingerprints(connection, extra_tables, schema),
                "catalog": inventory(connection, schema),
                "integrity": integrity(connection, schema),
            }
        source = {
            "container": container,
            "image": detail["Image"],
            "system_identifier": system_id,
            "database": original.database,
            "host": original.host,
            "port": original.port,
            "server_version": connection.scalar(text("SHOW server_version")),
            "revision": OLD,
            "snapshot": snapshot,
            "schemas": schemas,
            "captured_at": str(connection.scalar(text("SELECT transaction_timestamp()"))),
        }
        with archive.open("xb") as target:
            run(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_dump",
                    "-U",
                    original.username,
                    "-d",
                    original.database,
                    "-Fc",
                    "--snapshot",
                    snapshot,
                    "--lock-wait-timeout=5s",
                ],
                output=target,
            )
    engine.dispose()
    check(0 < archive.stat().st_size <= 268435456, "invalid_backup_size")
    with archive.open("rb") as stream:
        listing = subprocess.run(
            ["docker", "exec", "-i", container, "pg_restore", "--list"],
            stdin=stream,
            capture_output=True,
            timeout=60,
        )
    check(listing.returncode == 0, "backup_toc_invalid")
    toc = listing.stdout.decode()
    (directory / "source.toc.txt").write_text(toc, encoding="utf-8")
    for table in tables:
        check("TABLE DATA public " + table + " " in toc, "backup_missing_table_data")
    state = {
        "token": token,
        "directory": directory.relative_to(ROOT).as_posix(),
        "network": "tf-g0-3-" + token,
        "container_name": "tf-g0-3-db-" + token,
        "volume": "tf-g0-3-data-" + token,
        "source": source,
        "database": "tf_g0_3_primary_" + token,
        "archive_sha256": sha(archive),
        "archive_bytes": archive.stat().st_size,
        "backup_seconds": round(time.monotonic() - started, 3),
    }
    save(directory / "source-records.json", records)
    save(directory / "source-catalog.json", catalog)
    save(directory / "source-integrity.json", checks)
    save(directory / "source-extra-schemas.json", extra)
    save(directory / "state.json", state)
    save(MARKER, state)
    print(
        json.dumps(
            {
                "step": "backup",
                "status": "PASS",
                "tables": len(tables),
                "bytes": state["archive_bytes"],
                "seconds": state["backup_seconds"],
                "rows": {k: v["rows"] for k, v in records.items()},
            }
        ),
        flush=True,
    )


def load_json_docker(container):
    return json.loads(run(["docker", "inspect", container]).stdout)[0]


def verify_container(state):
    detail = load_json_docker(state["container_name"])
    check(detail["Id"] != state["source"]["container"], "source_container_rejected")
    check(
        detail["Config"]["Labels"].get("trueflag.g0-3.run") == state["token"], "unowned_container"
    )
    check(detail["Image"] == state["source"]["image"], "postgres_image_mismatch")
    check(
        set(detail["NetworkSettings"]["Networks"]) == {state["network"]},
        "container_network_not_isolated",
    )
    check(not detail["HostConfig"]["PortBindings"], "unexpected_published_port")
    network = json.loads(run(["docker", "network", "inspect", state["network"]]).stdout)[0]
    check(
        network["Internal"] and network["Labels"].get("trueflag.g0-3.run") == state["token"],
        "unowned_or_external_network",
    )
    check(
        any(m["Name"] == state["volume"] for m in detail["Mounts"] if m["Type"] == "volume"),
        "unexpected_data_volume",
    )
    return detail


def provision():
    state, directory = private_state()
    check("container_id" not in state, "already_provisioned")
    password = secrets.token_hex(32)
    (directory / "isolated-password").write_text(password, encoding="ascii")
    run(
        [
            "docker",
            "network",
            "create",
            "--internal",
            "--label",
            "trueflag.g0-3.run=" + state["token"],
            state["network"],
        ]
    )
    run(
        [
            "docker",
            "volume",
            "create",
            "--label",
            "trueflag.g0-3.run=" + state["token"],
            state["volume"],
        ]
    )
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            state["container_name"],
            "--label",
            "trueflag.g0-3.run=" + state["token"],
            "--network",
            state["network"],
            "--network-alias",
            "db",
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "-e",
            "POSTGRES_USER=rehearsal",
            "-e",
            "POSTGRES_DB=postgres",
            "-e",
            "POSTGRES_PASSWORD_FILE=/run/secrets/isolated-password",
            "-v",
            f"{(directory / 'isolated-password').as_posix()}:/run/secrets/isolated-password:ro",
            "-v",
            state["volume"] + ":/var/lib/postgresql/data",
            state["source"]["image"],
        ]
    )
    state["container_id"] = result.stdout.decode().strip()
    for _ in range(60):
        ready = run(
            ["docker", "exec", state["container_id"], "pg_isready", "-U", "rehearsal"],
            accept_failure=True,
        )
        if ready.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("isolated_database_not_ready")
    verify_container(state)
    identifier = (
        run(
            [
                "docker",
                "exec",
                state["container_id"],
                "psql",
                "-XAt",
                "-U",
                "rehearsal",
                "-d",
                "postgres",
                "-c",
                "SELECT system_identifier FROM pg_control_system()",
            ]
        )
        .stdout.decode()
        .strip()
    )
    check(identifier != state["source"]["system_identifier"], "cluster_not_separate")
    state["isolated_system_identifier"] = identifier
    save(directory / "state.json", state)
    save(MARKER, state)
    print(
        json.dumps(
            {
                "step": "provision",
                "status": "PASS",
                "separate_cluster": True,
                "internal_network": True,
                "published_ports": 0,
            }
        ),
        flush=True,
    )


def linux_args(state, directory):
    verify_container(state)
    args = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        state["network"],
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "3g",
        "--cpus",
        "2",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "-e",
        "PYTHONPATH=/workspace/backend:/workspace/scripts:/audit",
        "-e",
        "OPENBLAS_NUM_THREADS=1",
        "-e",
        "OMP_NUM_THREADS=1",
        "-e",
        "MKL_NUM_THREADS=1",
    ]
    for relative in [
        "backend",
        "scripts",
        "contracts",
        "assets/local/baseline",
        "assets/local/explanation_reference",
        "assets/local/regulatory/proposed",
        "assets/local/regulatory/research_v2",
    ]:
        path = (ROOT / relative).resolve(strict=True)
        check(path.is_relative_to(ROOT), "invalid_readonly_mount")
        args += ["-v", f"{path.as_posix()}:/workspace/{relative}:ro"]
    args += [
        "-v",
        f"{directory.as_posix()}:/recovery:rw",
        "-v",
        f"{(ROOT / 'runtime/g0-2').as_posix()}:/audit:ro",
        IMAGE,
        "python",
        "-B",
        "/workspace/scripts/rehearse_database_recovery.py",
        "--inside",
    ]
    return args


def inside_connection():
    from app.core.database import make_engine
    from sqlalchemy import text
    from sqlalchemy.engine import URL

    state = load(Path("/recovery/state.json"))
    check(
        re.fullmatch(r"tf_g0_3_primary_[a-f0-9]{32}", state["database"]) is not None,
        "unsafe_copy_database",
    )
    password = Path("/recovery/isolated-password").read_text()
    url = URL.create(
        "postgresql+psycopg",
        username="rehearsal",
        password=password,
        host="db",
        port=5432,
        database="postgres",
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        check(
            str(connection.scalar(text("SELECT system_identifier FROM pg_control_system()")))
            == state["isolated_system_identifier"],
            "wrong_target_cluster",
        )
        check(
            state["isolated_system_identifier"] != state["source"]["system_identifier"],
            "live_cluster_rejected",
        )
    return state, url, engine


def restore_host(state, directory, kind):
    check(
        kind in {"primary", "repeat", "failure", "interrupt", "synthetic", "invalid", "rollback"},
        "unsafe_restore_kind",
    )
    verify_container(state)
    name = f"tf_g0_3_{kind}_{state['token']}"
    run(
        [
            "docker",
            "exec",
            state["container_id"],
            "createdb",
            "-U",
            "rehearsal",
            "-T",
            "template0",
            name,
        ]
    )
    archive = directory / ("truncated.pgcustom" if kind == "invalid" else "source.pgcustom")
    with archive.open("rb") as source:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                state["container_id"],
                "pg_restore",
                "-U",
                "rehearsal",
                "-d",
                name,
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
            ],
            stdin=source,
            capture_output=True,
            timeout=180,
        )
    check(
        (result.returncode != 0) if kind == "invalid" else (result.returncode == 0),
        "unexpected_restore_outcome",
    )
    return {"database": name, "exit_code": result.returncode}


def migrate(url, target, *, hook=None, downgrade=False):
    from alembic import command
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from verify_regulatory_migration_copy import database_environment

    if hook:
        event.listen(Engine, "after_cursor_execute", hook)
    try:
        with database_environment(url) as config:
            (command.downgrade if downgrade else command.upgrade)(config, target)
    finally:
        if hook:
            event.remove(Engine, "after_cursor_execute", hook)


def copy_state(engine):
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout='60s'"))
        catalog = canonical_catalog(inventory(connection))
        records = fingerprints(
            connection, [r[0] for r in catalog["tables"] if r[0] != "alembic_version"]
        )
        revision = list(
            connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    return {"catalog": catalog, "records": records, "revision": revision}


def verify_extra_schemas(engine):
    expected = load(Path("/recovery/source-extra-schemas.json"))
    with engine.connect() as connection:
        for schema, baseline in expected.items():
            check(
                canonical_catalog(inventory(connection, schema))
                == canonical_catalog(baseline["catalog"]),
                "extra_schema_changed",
            )
            check(
                fingerprints(connection, sorted(baseline["records"]), schema)
                == baseline["records"],
                "extra_schema_records_changed",
            )
            integrity(connection, schema)
    return len(expected)


def verify_original(engine, baseline, catalog):
    from sqlalchemy import text

    with engine.connect() as connection:
        check(fingerprints(connection, sorted(baseline)) == baseline, "historical_records_changed")
        subset_preserved(catalog, inventory(connection))
        checks = integrity(connection)
        for name in ["reference_approvals", "corpus_releases", "reference_versions"]:
            if name in {r[0] for r in inventory(connection)["tables"]}:
                check(
                    connection.scalar(text("SELECT count(*) FROM " + name)) == 0,
                    "regulatory_history_unexpected",
                )
    checks["additional_schemas_preserved"] = verify_extra_schemas(engine)
    return checks


def inside_rehearse():
    from alembic import command
    from app.core.database import make_engine
    from app.core.release import release_report, require_compatible, verify_worker_artifacts
    from app.core.release_metadata import ReleaseCompatibilityError
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from verify_regulatory_migration_copy import database_environment

    state, url, control = inside_connection()
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    directory = Path("/recovery")
    baseline = load(directory / "source-records.json")
    catalog = canonical_catalog(load(directory / "source-catalog.json"))
    report = {"status": "RUNNING", "restore": {}, "migrations": [], "failures": {}}
    for kind in ["primary", "repeat", "failure", "interrupt", "synthetic", "rollback"]:
        engine = make_engine(
            url.set(database=f"tf_g0_3_{kind}_{state['token']}").render_as_string(
                hide_password=False
            )
        )
        actual = copy_state(engine)
        check(
            actual == {"catalog": catalog, "records": baseline, "revision": [OLD]},
            "restore_not_exact",
        )
        report["restore"][kind] = verify_original(engine, baseline, catalog)
        engine.dispose()
    target = url.set(database=state["database"])
    primary = make_engine(target.render_as_string(hide_password=False))
    check(
        release_report(primary)["compatibility"] == "schema_incompatible", "old_schema_not_fenced"
    )
    try:
        require_compatible(primary)
    except ReleaseCompatibilityError as error:
        check(error.code == "schema_incompatible", "wrong_schema_rejection")
    else:
        raise RuntimeError("old_schema_accepted")
    report["incompatible_schema"] = "rejected_without_job_writes"
    previous = OLD
    for revision, expected in zip(STAGES, [47, 52, 58]):
        started = time.monotonic()
        migrate(target, revision)
        checks = verify_original(primary, baseline, catalog)
        check(checks["tables"] == expected, "unexpected_table_count")
        with primary.connect() as connection:
            check(
                connection.scalar(text("SELECT version_num FROM alembic_version")) == revision,
                "wrong_migration_revision",
            )
        report["migrations"].append(
            {
                "from": previous,
                "to": revision,
                "seconds": round(time.monotonic() - started, 3),
                **checks,
            }
        )
        previous = revision
    with database_environment(target) as config:
        command.check(config)
    check(release_report(primary)["status"] == "ready", "upgraded_schema_rejected")
    require_compatible(primary)
    report["worker_artifacts"] = verify_worker_artifacts()
    # Read-only HTTP probes; no lifespan starts background writers on retained records.
    from app.core.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    client = TestClient(
        create_app(Settings(database_url=target.render_as_string(hide_password=False)), primary)
    )
    check(
        client.get("/health").status_code == 200 and client.get("/ready").status_code == 200,
        "upgraded_api_not_ready",
    )
    client.close()
    report["api_ready"] = True
    report["post_upgrade"] = copy_state(primary)
    save(directory / "post-upgrade.json", report["post_upgrade"])
    del report["post_upgrade"]
    for kind in ["failure", "interrupt"]:
        failure_url = url.set(database=f"tf_g0_3_{kind}_{state['token']}")
        engine = make_engine(failure_url.render_as_string(hide_password=False))
        before = copy_state(engine)
        triggered = []

        def hook(connection, cursor, statement, parameters, context, many):
            if triggered or not statement.lstrip().upper().startswith("CREATE TABLE"):
                return
            check(
                connection.engine.url.database == failure_url.database, "fault_target_not_verified"
            )
            triggered.append(True)
            if kind == "interrupt":
                pid = connection.scalar(text("SELECT pg_backend_pid()"))
                with control.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as controller:
                    check(
                        controller.scalar(
                            text("SELECT datname FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": pid},
                        )
                        == failure_url.database,
                        "backend_not_in_disposable_database",
                    )
                    check(
                        controller.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}),
                        "termination_failed",
                    )
            else:
                raise RuntimeError("injected_after_first_ddl")

        try:
            migrate(failure_url, STAGES[0], hook=hook)
        except Exception as error:
            check(triggered, "fault_not_injected")
            report["failures"][kind] = {
                "exception_type": type(error).__name__,
                "rolled_back": copy_state(engine) == before,
            }
            check(report["failures"][kind]["rolled_back"], "failed_migration_not_atomic")
        else:
            raise RuntimeError("injected_migration_unexpectedly_succeeded")
        migrate(failure_url, STAGES[-1])
        verify_original(engine, baseline, catalog)
        report["failures"][kind]["retry_to_head"] = True
        engine.dispose()
    # Existing typed history is empty. Seed NEW source-bound synthetic cases only in an isolated 0012 copy.
    from app.models import User
    from app.services.evidence import EvidenceService
    from app.services.synthetic_evidence import generate_scenario

    synthetic_url = url.set(database=f"tf_g0_3_synthetic_{state['token']}")
    synthetic = make_engine(synthetic_url.render_as_string(hide_password=False))
    with Session(synthetic) as session:
        actor = session.scalar(select(User.id).where(User.role == "admin", User.active.is_(True)))
    check(actor is not None, "synthetic_admin_unavailable")
    service = EvidenceService(synthetic)
    for profile in [
        "normal",
        "partial",
        "missing_income",
        "zero_income",
        "multi_currency",
        "inconsistent_kyc",
    ]:
        bundle = generate_scenario(uuid4(), 17, profile)
        source = service.register_source(actor, bundle.scenario_id)
        version = service.admit_version(actor, source, bundle)
        service.create_case(actor, version)
    seeded = copy_state(synthetic)
    check(seeded["records"]["evidence_transactions"]["rows"] > 0, "synthetic_evidence_empty")
    save(directory / "synthetic-before.json", seeded)
    for revision in STAGES:
        migrate(synthetic_url, revision)
        verify_original(synthetic, seeded["records"], seeded["catalog"])
    report["synthetic_preservation"] = {
        k: v["rows"]
        for k, v in seeded["records"].items()
        if k.startswith("evidence") or k in {"case_evidence_links", "cases"}
    }
    report["synthetic_rows_exact_after_each_stage"] = True
    synthetic.dispose()
    # Downgrade only the copy whose newly added tables are empty, then test retained-history guards.
    rollback_url = url.set(database=f"tf_g0_3_rollback_{state['token']}")
    rollback = make_engine(rollback_url.render_as_string(hide_password=False))
    migrate(rollback_url, STAGES[-1])
    for revision in [STAGES[1], STAGES[0], OLD]:
        migrate(rollback_url, revision, downgrade=True)
    check(
        copy_state(rollback) == {"catalog": catalog, "records": baseline, "revision": [OLD]},
        "empty_downgrade_not_exact",
    )
    report["empty_downgrade"] = "0015_to_0012_exact"
    # Nonempty synthetic audit histories are sufficient to exercise refusal without publishing sources.
    guard_results = []
    for revision, lower, action in [
        (STAGES[0], OLD, "evidence.reference.recovery_probe"),
        (STAGES[1], STAGES[0], "evidence.investigation.recovery_probe"),
        (STAGES[2], STAGES[1], "evidence.investigation.draft.recovery_probe"),
    ]:
        migrate(rollback_url, revision)
        with rollback.begin() as connection:
            # Match the real audit schema; no raw customer data in the marker.
            connection.execute(
                text(
                    "INSERT INTO audit_events (id,created_at,actor_id,action,details) VALUES (:id,now(),:actor,:action,'{}')"
                ),
                {"id": uuid4(), "actor": actor, "action": action},
            )
        before = copy_state(rollback)
        try:
            migrate(rollback_url, lower, downgrade=True)
        except RuntimeError as error:
            check(str(error).startswith("Refusing to erase "), "unexpected_downgrade_error")
            check(copy_state(rollback) == before, "guarded_downgrade_changed_history")
            guard_results.append(revision)
        else:
            raise RuntimeError("retained_history_downgrade_not_refused")
    report["retained_history_guards"] = guard_results
    rollback.dispose()
    invalid = make_engine(
        url.set(database=f"tf_g0_3_invalid_{state['token']}").render_as_string(hide_password=False)
    )
    with invalid.connect() as connection:
        check(inventory(connection)["tables"] == [], "partial_restore_not_atomic")
    invalid.dispose()
    report["invalid_backup"] = "truncated_copy_rejected_atomic_restore_empty"
    report["status"] = "PASS"
    save(directory / "rehearsal.json", report)
    print(
        "G03_REPORT:" + json.dumps({k: v for k, v in report.items() if k != "restore"}), flush=True
    )
    primary.dispose()
    control.dispose()


def inside_restart():
    from app.core.database import make_engine
    from app.core.release import release_report

    state, url, control = inside_connection()
    engine = make_engine(url.set(database=state["database"]).render_as_string(hide_password=False))
    check(
        copy_state(engine) == load(Path("/recovery/post-upgrade.json")),
        "restart_changed_data_or_schema",
    )
    check(release_report(engine)["status"] == "ready", "restart_not_ready")
    verify_extra_schemas(engine)
    save(
        Path("/recovery/restart.json"),
        {"status": "PASS", "records_and_catalog_identical": True, "schema_ready": True},
    )
    print("G03_REPORT:" + json.dumps({"step": "restart", "status": "PASS"}), flush=True)
    engine.dispose()
    control.dispose()


def inside_recover():
    from app.core.database import make_engine

    state, url, control = inside_connection()
    engine = make_engine(
        url.set(database=f"tf_g0_3_invalid_{state['token']}").render_as_string(hide_password=False)
    )
    actual = copy_state(engine)
    expected = {
        "catalog": canonical_catalog(load(Path("/recovery/source-catalog.json"))),
        "records": load(Path("/recovery/source-records.json")),
        "revision": [OLD],
    }
    check(actual == expected, "known_good_recovery_not_exact")
    checks = verify_original(engine, expected["records"], expected["catalog"])
    save(
        Path("/recovery/known-good-recovery.json"),
        {"status": "PASS", "after_truncated_restore": True, **checks},
    )
    print("G03_REPORT:" + json.dumps({"step": "recover", "status": "PASS", **checks}), flush=True)
    engine.dispose()
    control.dispose()


def inside_finalize():
    from app.core.database import make_engine
    from app.core.release import release_report
    from sqlalchemy import text

    state, url, control = inside_connection()
    engine = make_engine(url.set(database=state["database"]).render_as_string(hide_password=False))
    check(
        copy_state(engine) == load(Path("/recovery/post-upgrade.json")),
        "retained_copy_changed_by_tests",
    )
    verify_extra_schemas(engine)
    check(release_report(engine)["status"] == "ready", "final_copy_not_ready")
    with engine.connect() as connection:
        schemas = list(
            connection.execute(
                text(
                    "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname!='information_schema' ORDER BY 1"
                )
            ).scalars()
        )
        check(schemas == state["source"]["schemas"], "test_schema_cleanup_incomplete")
        checks = integrity(connection)
        check(
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname='ix_reference_chunks_fts' AND indexdef LIKE '%USING gin%'"
                )
            )
            == 1,
            "reference_gin_index_missing",
        )
    save(
        Path("/recovery/post-tests-preservation.json"),
        {
            "status": "PASS",
            "records_and_schema_unchanged": True,
            "test_schemas_cleaned": True,
            "reference_gin_index": True,
            **checks,
        },
    )
    print(
        "G03_REPORT:" + json.dumps({"step": "finalize", "status": "PASS", "copy_unchanged": True}),
        flush=True,
    )
    engine.dispose()
    control.dispose()


def inside_tests():
    import pytest

    state, url, control = inside_connection()
    control.dispose()
    selected = url.set(database=state["database"]).render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=selected,
        TRUEFLAG_TEST_POSTGRES_URL=selected,
        TRUEFLAG_TEST_REAL_ASSESSMENT="1",
        JWT_SECRET=secrets.token_urlsafe(48),
    )
    return pytest.main(
        [
            "backend/tests",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "-p",
            "g0_probe",
            "--basetemp",
            "/tmp/g03-tests",
        ]
    )


def linux_step(step):
    state, directory = private_state()
    if step == "rehearse":
        check(
            sha(directory / "source.pgcustom") == state["archive_sha256"], "backup_digest_mismatch"
        )
        archive = directory / "source.pgcustom"
        (directory / "truncated.pgcustom").write_bytes(
            archive.read_bytes()[: archive.stat().st_size // 2]
        )
        restores = (
            load(directory / "restore-commands.json")
            if (directory / "restore-commands.json").exists()
            else {
                kind: restore_host(state, directory, kind)
                for kind in [
                    "primary",
                    "repeat",
                    "failure",
                    "interrupt",
                    "synthetic",
                    "rollback",
                    "invalid",
                ]
            }
        )
        save(directory / "restore-commands.json", restores)
    elif step == "recover":
        check(
            sha(directory / "source.pgcustom") == state["archive_sha256"], "backup_digest_mismatch"
        )
        verify_container(state)
        name = f"tf_g0_3_invalid_{state['token']}"
        if not (directory / "known-good-recovery.json").exists():
            count = (
                run(
                    [
                        "docker",
                        "exec",
                        state["container_id"],
                        "psql",
                        "-XAt",
                        "-U",
                        "rehearsal",
                        "-d",
                        name,
                        "-c",
                        "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
                    ]
                )
                .stdout.decode()
                .strip()
            )
            check(count == "0", "recovery_target_not_empty")
            with (directory / "source.pgcustom").open("rb") as source:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        state["container_id"],
                        "pg_restore",
                        "-U",
                        "rehearsal",
                        "-d",
                        name,
                        "--single-transaction",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                    ],
                    stdin=source,
                    capture_output=True,
                    timeout=180,
                )
            check(result.returncode == 0, "known_good_restore_failed")
    elif step == "restart":
        detail = verify_container(state)
        check(detail["Id"] == state["container_id"], "container_id_changed")
        run(["docker", "restart", "--time", "10", state["container_id"]])
        for _ in range(60):
            if (
                run(
                    ["docker", "exec", state["container_id"], "pg_isready", "-U", "rehearsal"],
                    accept_failure=True,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.5)
    process = subprocess.Popen(
        [*linux_args(state, directory), "--step", step],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process.stdin.close()
    summary = None
    for line in process.stdout:
        if line.startswith("G0_SUMMARY:"):
            summary = json.loads(line.split(":", 1)[1])
        elif line.startswith("G03_REPORT:"):
            print(line.strip(), flush=True)
        elif line.startswith('{"status": "FAIL", "code": '):
            print(line.strip(), flush=True)
        elif re.fullmatch(r"[.EFs \[\]0-9%\r\n]+", line):
            print(line, end="", flush=True)
        # Suppress all raw tracebacks/SQL/pytest failure locals to avoid customer data or tokens.
    code = process.wait()
    if summary is not None:
        summary["exit_code"] = code
        save(directory / "backend-tests.json", summary)
        print(
            json.dumps(
                {"step": step, "counts": summary["counts"], "failures": summary["failures"]}
            ),
            flush=True,
        )
    check(code == 0, "isolated_linux_step_failed")


def finalize():
    from app.core.config import Settings
    from app.core.database import make_engine
    from sqlalchemy import text

    state, directory = private_state()
    before = load(directory / "original-files.json")
    check(
        all(
            (ROOT / name).is_file() and sha(ROOT / name) == value for name, value in before.items()
        ),
        "preexisting_file_changed",
    )
    check(
        sha(directory / "source.pgcustom") == state["archive_sha256"], "known_good_backup_changed"
    )
    engine = make_engine(Settings().database_url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        check(
            str(connection.scalar(text("SELECT system_identifier FROM pg_control_system()")))
            == state["source"]["system_identifier"],
            "source_identity_changed",
        )
        check(
            connection.scalar(text("SELECT version_num FROM alembic_version")) == OLD,
            "live_revision_changed",
        )
        check(
            canonical_catalog(inventory(connection))
            == canonical_catalog(load(directory / "source-catalog.json")),
            "live_schema_changed",
        )
        current = fingerprints(connection, sorted(load(directory / "source-records.json")))
    engine.dispose()
    report = {
        "status": "PASS",
        "live_schema": OLD,
        "live_records_same_as_snapshot": current == load(directory / "source-records.json"),
        "live_changed_tables": [
            table
            for table, baseline in load(directory / "source-records.json").items()
            if current[table] != baseline
        ],
        "preexisting_files_preserved": len(before),
        "backup_digest_unchanged": True,
    }
    save(directory / "preservation.json", report)
    print(json.dumps(report), flush=True)
    linux_step("finalize")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step",
        required=True,
        choices=["backup", "provision", "rehearse", "restart", "recover", "tests", "finalize"],
    )
    parser.add_argument("--inside", action="store_true")
    args = parser.parse_args()
    if args.inside:
        check(
            sys.platform == "linux" and Path("/recovery/state.json").is_file(),
            "isolated_runtime_required",
        )
        return {
            "rehearse": inside_rehearse,
            "restart": inside_restart,
            "recover": inside_recover,
            "tests": inside_tests,
            "finalize": inside_finalize,
        }[args.step]()
    if args.step in {"rehearse", "restart", "recover", "tests"}:
        linux_step(args.step)
    else:
        {"backup": backup, "provision": provision, "finalize": finalize}[args.step]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Fixed internal assertion codes/type only, never raw database/subprocess exception text.
        code = (
            str(error)
            if type(error) is RuntimeError and re.fullmatch("[a-z0-9_]+", str(error))
            else type(error).__name__
        )
        import traceback

        frames = [
            {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)
        ]
        if (
            sys.platform == "linux"
            and "--inside" in sys.argv
            and Path("/recovery/state.json").is_file()
        ):
            save(Path("/recovery/last-error.json"), {"code": code, "frames": frames})
        print(
            json.dumps(
                {"status": "FAIL", "code": code, "last_frame": frames[-1] if frames else None}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
