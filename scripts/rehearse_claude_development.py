"""Back up/rehearse candidate 0022 on the isolated probe only; never live-demo migration."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def inside():
    import rehearse_database_recovery as r
    from alembic import command
    from alembic.config import Config
    from app.core.database import make_engine
    from app.core.release import require_compatible
    from app.services.ingestion import digest
    from sqlalchemy import text

    args = json.loads(sys.stdin.read(4096))
    state, url, control = r.inside_connection()
    control.dispose()
    schema = args["schema"]
    target = args["database"]
    assert re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema)
    assert target == state["database"] or re.fullmatch(
        r"tf_claude_dev_restore_[a-f0-9]{32}", target
    )
    assert target != state["source"]["database"]
    url = url.set(database=target).update_query_dict({"options": "-csearch_path=" + schema})
    os.environ.update(
        DATABASE_URL=url.render_as_string(hide_password=False),
        JWT_SECRET="isolated-migration-no-browser-auth",
    )
    engine = make_engine(os.environ["DATABASE_URL"])

    def snapshot():
        result = {}
        with engine.connect() as connection:
            for table in [
                "investigation_draft_runs",
                "investigation_draft_attempts",
                "investigation_draft_receipts",
            ]:
                result[table] = (
                    connection.execute(
                        text("SELECT row_to_json(t) FROM " + table + " t ORDER BY id")
                    )
                    .scalars()
                    .all()
                )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM investigation_draft_jobs WHERE status='running'")
                )
                == 0
            )
            result["audit"] = (
                connection.execute(
                    text(
                        "SELECT row_to_json(t) FROM audit_events t WHERE action LIKE 'evidence.investigation.draft.%' ORDER BY id"
                    )
                )
                .scalars()
                .all()
            )
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        return digest(result), {key: len(value) for key, value in result.items()}, revision

    before, counts, old = snapshot()
    assert old == "0020_claude_provider"
    command.upgrade(Config("/workspace/backend/alembic.ini"), "0022_claude_development_scope")
    after, new_counts, new = snapshot()
    assert before == after and counts == new_counts and new == "0022_claude_development_scope"
    require_compatible(engine)
    report = dict(
        isolated_identity_verified=True,
        revision_before=old,
        revision_after=new,
        history_unchanged=True,
        history_counts=counts,
        release_compatible=True,
        restore_rehearsal=target != state["database"],
        provider_requests=0,
    )
    print(json.dumps(report))
    engine.dispose()


def main():
    import rehearse_database_recovery as r
    from claude_migration_overlay import create_overlay
    from verify_regulatory_migration_copy import secure_directory

    state = r.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    assert directory.is_relative_to((ROOT / "runtime/g0-3").resolve())
    r.verify_container(state)
    demo = ROOT / "runtime/claude-demo-20261120"
    schema = json.loads((demo / "claude_probe_attempt.json").read_text())["schema"]
    assert re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema)
    review = demo / "development-v2"
    receipt = review / "isolated_migration_receipt.json"
    if receipt.exists():
        raise RuntimeError("rehearsal_already_recorded")
    backup = review / ("recovery-" + uuid4().hex)
    secure_directory(backup)
    container = state["container_id"]
    dumped = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "rehearsal",
            "-d",
            state["database"],
            "--format=custom",
            "--no-owner",
            "--schema=" + schema,
        ],
        capture_output=True,
        timeout=60,
        check=True,
    )
    assert 0 < len(dumped.stdout) < 134217728
    archive = backup / "probe-before-0022.pgcustom"
    with archive.open("xb") as file:
        file.write(dumped.stdout)
    listed = subprocess.run(
        ["docker", "exec", "-i", container, "pg_restore", "--list"],
        input=dumped.stdout,
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert b"TABLE DATA " + schema.encode() + b" investigation_draft_attempts " in listed.stdout
    restored = "tf_claude_dev_restore_" + uuid4().hex
    subprocess.run(
        ["docker", "exec", container, "createdb", "-U", "rehearsal", "-T", "template0", restored],
        capture_output=True,
        timeout=30,
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "pg_restore",
            "-U",
            "rehearsal",
            "-d",
            restored,
            "--no-owner",
            "--exit-on-error",
            "--single-transaction",
        ],
        input=dumped.stdout,
        capture_output=True,
        timeout=60,
        check=True,
    )
    overlay = create_overlay(development=True)

    def migrate(database):
        command = r.linux_args(state, directory)[:-4]
        index = command.index("trueflag-assessment-verify:phase2-5")
        command[index:index] = [
            "-v",
            f"{overlay.as_posix()}:/workspace/backend/alembic/versions:ro",
            "-v",
            f"{(review / 'candidate_schema.py').as_posix()}:/workspace/backend/app/core/schema.py:ro",
            "-v",
            f"{(review / 'candidate_release.json').as_posix()}:/workspace/backend/app/_release.json:ro",
        ]
        command += ["python", "-B", "/workspace/scripts/rehearse_claude_development.py", "--inside"]
        result = subprocess.run(
            command,
            input=json.dumps(dict(database=database, schema=schema)),
            text=True,
            capture_output=True,
            timeout=90,
        )
        reports = [
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.startswith('{"isolated_identity_verified"')
        ]
        if result.returncode or len(reports) != 1:
            raise RuntimeError("isolated_migration_failed_details_withheld")
        return reports[0]

    rehearsal = migrate(restored)
    assert rehearsal["history_unchanged"] and rehearsal["restore_rehearsal"]
    applied = migrate(state["database"])
    report = dict(
        backup=archive.relative_to(ROOT).as_posix(),
        backup_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        restored_database=restored,
        restore_rehearsal=rehearsal,
        isolated_probe_migration=applied,
        original_demo_modified=False,
        provider_requests=0,
    )
    with receipt.open("x") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    print(
        json.dumps(
            dict(
                backup_restored_and_verified=True,
                isolated_probe_revision=applied["revision_after"],
                historical_attempts=applied["history_counts"]["investigation_draft_attempts"],
                history_unchanged=True,
                original_demo_modified=False,
                provider_requests=0,
            )
        )
    )


if __name__ == "__main__":
    try:
        inside() if "--inside" in sys.argv else main()
    except Exception as error:
        print(
            json.dumps(
                dict(
                    blocked=True,
                    error_type=type(error).__name__,
                    details="withheld; preserve recovery artifacts",
                )
            )
        )
        raise SystemExit(1) from None
