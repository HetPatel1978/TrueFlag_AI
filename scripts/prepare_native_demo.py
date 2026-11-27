"""Prepare a NEW native Ubuntu launch directory. Never starts Docker or reads .env."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0023_durable_regulatory_start"
EXCLUDED = {
    ".git",
    ".venv",
    ".venv-ml",
    "node_modules",
    "runtime",
    "assets",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "_release.json",
    "release-build.json",
}


def copy_public(source, target):
    """Copy current work, including uncommitted files; reject symlinks and private paths."""

    def ignore(directory, names):
        omitted = []
        for name in names:
            path = Path(directory) / name
            if (
                name in EXCLUDED
                or name.startswith(".env")
                or name.endswith((".pyc", ".egg-info"))
                or path.suffix.lower()
                in {
                    ".csv",
                    ".jsonl",
                    ".joblib",
                    ".pkl",
                    ".pickle",
                    ".db",
                    ".sqlite",
                    ".pem",
                    ".key",
                    ".zip",
                    ".log",
                }
            ):
                omitted.append(name)
            elif path.is_symlink():
                raise ValueError("source_symlink_requires_review")
        return omitted

    for name in ("backend", "frontend", "scripts", "contracts"):
        shutil.copytree(source / name, target / name, ignore=ignore)
    for name in (
        "FINAL_LIVE_DEMO_EXECUTION.md",
        "NATIVE_REGULATORY_RUNNER_SETUP.md",
        "PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md",
        "G5_1_SOURCE_REVIEW_AND_GOVERNANCE.md",
    ):
        path = source / "docs" / name
        if path.is_file():
            if path.is_symlink():
                raise ValueError("source_symlink_requires_review")
            (target / "docs").mkdir(exist_ok=True)
            shutil.copyfile(path, target / "docs" / name)


def private_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def bind(source, target, *, writable=False):
    return dict(
        type="bind",
        source=source,
        target=target,
        read_only=not writable,
        bind={"create_host_path": False},
    )


def compose_document(uid, gid, database, baseline):
    runtime = bind("./source/scripts/native_demo_runtime.py", "/opt/native_runtime.py")
    control = bind("./control/control.json", "/run/native/control.json")
    cluster = bind("./control/cluster-id", "/run/native/cluster-id")
    acceptance = bind("./control/acceptance/results/evidence.json", "/run/native/acceptance.json")

    def service(role, *, ml=False):
        mounts = [
            runtime,
            control,
            cluster,
            acceptance,
            bind(f"./control/{role}.json", "/run/native/settings.json"),
        ]
        if baseline is not None:
            mounts.append(bind(str(baseline / "contracts"), "/app/assets/local/baseline/contracts"))
            if ml:
                mounts += [
                    bind(str(baseline / "model"), "/app/assets/local/baseline/model"),
                    bind(
                        str(baseline / "reference/research/src/trueflag"),
                        "/app/assets/local/baseline/reference/research/src/trueflag",
                    ),
                ]
        result = dict(
            build={
                "context": "./source/backend",
                "dockerfile": "Dockerfile.ml-worker" if ml else "Dockerfile",
            },
            user=f"{uid}:{gid}",
            entrypoint=["python", "-B", "/opt/native_runtime.py"],
            command=[role],
            volumes=mounts,
            networks=["application"],
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            tmpfs=["/tmp:rw,nosuid,nodev,size=256m"],
            mem_limit="3g" if ml else "768m",
            cpus=2 if ml else 1,
            pids_limit=128,
            restart="no",
            logging={"driver": "local", "options": {"max-size": "10m", "max-file": "2"}},
        )
        return result

    db = dict(
        image="postgres:17-alpine",
        networks=["application"],
        environment={
            "POSTGRES_USER": "tf_native",
            "POSTGRES_DB": database,
            "POSTGRES_PASSWORD_FILE": "/run/secrets/password",
        },
        volumes=[
            "database:/var/lib/postgresql/data",
            bind("./control/postgres-password", "/run/secrets/password"),
        ],
        healthcheck={
            "test": ["CMD", "pg_isready", "-U", "tf_native", "-d", database],
            "interval": "2s",
            "timeout": "3s",
            "retries": 30,
        },
        restart="no",
    )
    testdb = dict(
        image="postgres:17-alpine",
        profiles=["acceptance"],
        networks={"acceptance": {"aliases": ["db"]}},
        environment={
            "POSTGRES_USER": "tf_acceptance",
            "POSTGRES_DB": "tf_acceptance_rag",
            "POSTGRES_PASSWORD_FILE": "/run/secrets/password",
        },
        volumes=[
            "test-database:/var/lib/postgresql/data",
            bind("./control/acceptance/postgres-password", "/run/secrets/password"),
        ],
        healthcheck={
            "test": ["CMD", "pg_isready", "-U", "tf_acceptance", "-d", "tf_acceptance_rag"],
            "interval": "2s",
            "timeout": "3s",
            "retries": 30,
        },
        restart="no",
    )
    api = service("api")
    api.update(
        ports=["127.0.0.1:8010:8000"],
        healthcheck={
            "test": [
                "CMD",
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=3)",
            ],
            "interval": "10s",
            "timeout": "5s",
            "retries": 6,
        },
    )
    api["volumes"].append(bind("./control/staging", "/app/runtime/csv-staging", writable=True))
    importer = service("import-worker")
    importer["volumes"].append(bind("./control/staging", "/app/runtime/csv-staging"))
    operator = service("operator")
    operator.update(
        profiles=["operator"], stdin_open=True, tty=True, command=["operator", "status"]
    )
    operator["volumes"] += [
        bind("./control/assessment-worker.json", "/run/native/assessment-worker.json"),
        bind("./control/import-worker.json", "/run/native/import-worker.json"),
        bind("./control/investigation-token", "/run/secrets/investigation_worker_token"),
    ]
    ml = service("assessment-worker", ml=True)
    ml.update(profiles=["assessment"])
    evidence = service("evidence-worker")
    evidence["volumes"].append(
        bind("./control/investigation-token", "/run/secrets/investigation_worker_token")
    )
    draft = service("draft-worker")
    draft["profiles"] = ["gated-ai"]
    draft["volumes"].append(
        bind("./control/investigation-token", "/run/secrets/investigation_worker_token")
    )
    # No external network, provider keys or activation settings exist in this launch package.
    return dict(
        name="tf-native-" + database.removeprefix("tf_native_demo_"),
        services={
            "db": db,
            "testdb": testdb,
            "backend": api,
            "frontend": dict(
                build="./source/frontend",
                networks=["application"],
                ports=["127.0.0.1:8088:8080"],
                restart="no",
                depends_on={"backend": {"condition": "service_healthy"}},
            ),
            "operator": operator,
            "import-worker": importer,
            "assessment-worker": ml,
            "evidence-worker": evidence,
            "draft-worker": draft,
            "acceptance": dict(
                profiles=["acceptance"],
                build={"context": "./source/backend", "dockerfile": "Dockerfile.ml-worker"},
                user=f"{uid}:{gid}",
                networks=["acceptance"],
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs=["/tmp:rw,nosuid,nodev,size=512m"],
                mem_limit="3g",
                cpus=2,
                pids_limit=128,
                volumes=[
                    bind("./source/backend", "/workspace/backend"),
                    bind("./source/scripts", "/workspace/scripts"),
                    bind("./source/contracts", "/workspace/contracts"),
                    bind("./control/acceptance", "/acceptance", writable=True),
                ],
                working_dir="/workspace",
                entrypoint=["python", "-B"],
                command=[
                    "scripts/native_regulatory_acceptance.py",
                    "--database-url-file",
                    "/acceptance/database-url",
                    "--expected-cluster-file",
                    "/acceptance/cluster-id",
                    "--synchronization-evidence-file",
                    "/acceptance/ntp-status",
                    "--output",
                    "/acceptance/results",
                ],
            ),
        },
        networks={"application": {"internal": True}, "acceptance": {"internal": True}},
        volumes={"database": {}, "test-database": {}},
    )


def prepare(output, baseline):
    from native_regulatory_acceptance import native_linux

    native_linux()
    if (
        output.is_symlink()
        or output.exists()
        or not output.resolve().is_relative_to(ROOT / "runtime")
    ):
        raise ValueError("new_private_runtime_directory_required")
    if os.getuid() == 0:
        raise ValueError("nonroot_operator_required")
    if baseline is not None:
        baseline = baseline.resolve(strict=True)
        for name in ("contracts/data_dictionary.csv", "model", "reference/research/src/trueflag"):
            if not (baseline / name).exists():
                raise ValueError("approved_baseline_incomplete")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "control/acceptance").mkdir(mode=0o700, parents=True)
    (output / "control/staging").mkdir(mode=0o700)
    copy_public(ROOT, output / "source")
    stage = output / "source"
    for number in (
        "0020_claude_provider",
        "0021_regulatory_draft_bindings",
        "0022_claude_development_scope",
        "0023_durable_regulatory_start",
    ):
        shutil.copyfile(
            stage / f"backend/alembic/candidates/{number}.py",
            stage / f"backend/alembic/versions/{number}.py",
        )
    (stage / "backend/app/core/schema.py").write_text(f'EXPECTED_SCHEMA_REVISION = "{REVISION}"\n')
    subprocess.run(
        [sys.executable, str(stage / "scripts/build_release_manifest.py")],
        cwd=stage,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    database = "tf_native_demo_" + uuid4().hex
    password, test_password, jwt = (
        secrets.token_hex(32),
        secrets.token_hex(32),
        secrets.token_urlsafe(48),
    )
    control = output / "control"
    for path, value in (
        (control / "postgres-password", password),
        (control / "acceptance/postgres-password", test_password),
        (control / "investigation-token", secrets.token_hex(32)),
        (
            control / "acceptance/database-url",
            f"postgresql+psycopg://tf_acceptance:{test_password}@db:5432/tf_acceptance_rag",
        ),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(value)
    base = dict(
        DATABASE_URL=f"postgresql+psycopg://tf_native:{password}@db:5432/{database}",
        APP_ENV="native_demo",
        JWT_SECRET=jwt,
        ACCESS_TOKEN_MINUTES="60",
        CSV_STAGING_ROOT="/app/runtime/csv-staging",
        BATCH_ASSESSMENT_DISPATCH_ENABLED="true",
        INVESTIGATION_SIMULATION_ENABLED="false",
        INVESTIGATION_EXTERNAL_ENABLED="false",
        ANTHROPIC_SYNTHETIC_DEMO_ENABLED="false",
        ANTHROPIC_ANALYST_GENERATION_ENABLED="false",
        REGULATORY_INVESTIGATION_ENABLED="false",
    )
    for role in (
        "api",
        "operator",
        "import-worker",
        "assessment-worker",
        "evidence-worker",
        "draft-worker",
    ):
        settings = dict(base)
        if role not in ("api", "operator"):
            settings["JWT_SECRET"] = secrets.token_urlsafe(48)
        if role in ("import-worker", "assessment-worker"):
            settings["native_worker_token"] = secrets.token_hex(32)
        private_json(control / f"{role}.json", settings)
    private_json(
        control / "control.json",
        {"database": database, "schema": REVISION, "baseline_available": baseline is not None},
    )
    private_json(
        output / "compose.json", compose_document(os.getuid(), os.getgid(), database, baseline)
    )
    print(
        json.dumps(
            dict(
                status="prepared_not_started",
                directory=str(output),
                provider_requests=0,
                provider_enabled=False,
            )
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Copy public source only; works on Windows; no Docker",
    )
    parser.add_argument(
        "--baseline", type=Path, help="Already authorized private baseline on this host"
    )
    args = parser.parse_args()
    if args.export_only:
        output = args.output.resolve()
        if output.exists() or not output.is_relative_to(ROOT / "runtime") or args.baseline:
            raise ValueError("new_public_runtime_export_required")
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        copy_public(ROOT, output)
        manifest = {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
        }
        (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2))
        print(
            json.dumps(
                {"status": "public_source_exported", "files": len(manifest), "provider_requests": 0}
            )
        )
        return
    prepare(args.output.resolve(), args.baseline)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {"status": "blocked", "error_type": type(error).__name__, "provider_requests": 0}
            )
        )
        raise SystemExit(1) from None
