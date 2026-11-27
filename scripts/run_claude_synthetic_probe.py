"""One synthetic Claude compatibility attempt on a persistent isolated PostgreSQL schema.

No automatic retries. The source demo database, release metadata and .env are never changed.
The generated attempt and conservative reservation remain in the isolated schema.
"""

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
APPROVAL = "synthetic-claude-demo-2026-11-20"


def inside():
    import rehearse_database_recovery as recovery
    from alembic import command
    from alembic.config import Config
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models import User
    from app.schemas.investigations import InvestigationPacketBody, InvestigationRequest
    from app.schemas.provider_live import ClaudeProviderConfig
    from app.security.auth import password_hash
    from app.services.claude_contract import output_schema
    from app.services.evidence import EvidenceService
    from app.services.ingestion import digest
    from app.services.investigation_coordinator import InvestigationCoordinator
    from app.services.investigation_draft_verifier import minimize
    from app.services.investigation_drafts import InvestigationDraftService
    from app.services.live_provider_runner import ProviderRunner
    from app.services.luminal_provider import ProviderRateLimited, ProviderRejected
    from app.services.synthetic_evidence import generate_scenario
    from pydantic import SecretStr
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    payload = json.loads(sys.stdin.read(65537))
    progress = Path(
        "/demo/claude_probe_dry_run_progress.json"
        if payload.get("dry_run") is True
        else "/demo/claude_probe_progress.json"
    )
    progress.write_text(json.dumps({"stage": "preparing"}) + "\n")
    schema = payload["schema"]
    if not re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema):
        raise RuntimeError("invalid_isolated_schema")
    state, base_url, control = recovery.inside_connection()
    control.dispose()
    base_url = base_url.set(database=state["database"])
    admin_engine = make_engine(base_url.render_as_string(hide_password=False))
    with admin_engine.begin() as connection:
        connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    admin_engine.dispose()
    url = base_url.update_query_dict({"options": "-csearch_path=" + schema})
    db_url = url.render_as_string(hide_password=False)
    jwt = secrets.token_urlsafe(48)
    os.environ.update(DATABASE_URL=db_url, JWT_SECRET=jwt)
    command.upgrade(Config("/workspace/backend/alembic.ini"), "head")
    terms_path = Path("/demo/anthropic_public_terms_snapshot.json")
    terms_sha = hashlib.sha256(terms_path.read_bytes()).hexdigest()
    settings = Settings(
        _env_file=None,
        database_url=db_url,
        jwt_secret=jwt,
        anthropic_api_key=SecretStr(payload["key"]),
        anthropic_synthetic_demo_enabled=True,
        anthropic_contract_verified=False,
        anthropic_bootstrap_enabled=True,
        anthropic_terms_sha256=terms_sha,
        anthropic_demo_spend_limit_usd=20,
        anthropic_demo_call_limit=10,
    )
    engine = make_engine(db_url)
    token = secrets.token_urlsafe(48)
    with Session(engine) as session, session.begin():
        actor = User(
            username="syntheticprobe" + uuid4().hex[:12],
            role="admin",
            password_hash=password_hash.hash(secrets.token_urlsafe(32)),
        )
        session.add(actor)
        session.flush()
        actor_id = actor.id
    foundation = EvidenceService(engine)
    bundle = generate_scenario(uuid4(), 1701, "g1_concentration")
    source = foundation.register_source(actor_id, bundle.scenario_id)
    source_version = foundation.admit_version(actor_id, source, bundle)
    case = foundation.create_case(actor_id, source_version)
    coordinator = InvestigationCoordinator(engine, settings)
    coordinator.register_worker(actor_id, "claude-probe-worker", token)
    context = coordinator.reader.get_case_context(actor_id, case)
    request = InvestigationRequest(
        expected_case_version=context.snapshot.case_version,
        expected_evidence_revision=context.snapshot.evidence_revision,
        expected_access_revision=context.snapshot.access_revision,
        without_assessment_reason="not_selected",
        window={"start": bundle.window_start, "end": bundle.as_of},
        currencies=("USD",),
    )
    parent = coordinator.request(actor_id, case, "claude-probe-parent-001", request)
    parent_result = coordinator.run_once(token)
    if parent_result is None or parent_result["status"] not in {"succeeded", "abstained"}:
        raise RuntimeError("verified_evidence_packet_unavailable")
    parent_view = coordinator.get(actor_id, case, UUID(parent["run_id"]))
    packet = InvestigationPacketBody.model_validate(parent_view["packet"])
    exact = digest(minimize(packet).model_dump(mode="json"))
    settings.anthropic_bootstrap_input_sha256 = exact
    config = ClaudeProviderConfig(
        approval_id=APPROVAL,
        terms_sha256=terms_sha,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd="2.10",
        purpose="compatibility_probe",
        exact_input_sha256=exact,
    )
    drafts = InvestigationDraftService(engine, settings)
    drafts.request(actor_id, case, "claude-probe-draft-001", request, config)
    if payload.get("dry_run") is True:
        claim = drafts.claim(token)
        if claim is None or drafts.prepare(token, claim) is None:
            raise RuntimeError("synthetic_probe_reservation_unavailable")
        drafts.fail(token, claim, "provider_unavailable")
        report = {
            "isolated_schema": schema,
            "dry_run": True,
            "synthetic_only": True,
            "packet_sha256": exact,
            "reservation_usd": "2.10",
            "dispatch_attempted": False,
        }
        Path("/demo/claude_probe_dry_run_result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
        engine.dispose()
        return

    class CaptureRunner:
        invoked = False
        http_status = None
        usage = None

        def invoke(self, provider_input, provider_config):
            self.invoked = True
            progress.write_text(json.dumps({"stage": "provider_invoked"}) + "\n")
            try:
                reply = ProviderRunner(settings).invoke(provider_input, provider_config)
                self.http_status = 200
                self.usage = reply.usage.model_dump(mode="json")
                return reply
            except (ProviderRejected, ProviderRateLimited) as error:
                self.http_status = error.http_status
                raise

    capture = CaptureRunner()
    drafts._runner = capture
    result = drafts.run_once(token)
    result = result or {"status": "unavailable"}
    report = {
        "isolated_schema": schema,
        "case_id": str(case),
        "synthetic_only": True,
        "packet_sha256": exact,
        "provider": "anthropic",
        "model_requested": config.model,
        "dispatch_attempted": capture.invoked,
        "http_status": capture.http_status,
        "usage": capture.usage,
        "worker_status": result.get("status"),
        "error_code": result.get("error_code"),
        "compatibility_verified": False,
        "reservation_usd": "2.10" if capture.invoked else None,
    }
    Path("/demo/claude_probe_result.json").write_text(json.dumps(report, indent=2) + "\n")
    progress.write_text(json.dumps({"stage": "finished"}) + "\n")
    print(json.dumps(report))
    engine.dispose()


def main():
    import rehearse_database_recovery as recovery
    from app.core.config import Settings
    from app.core.release_metadata import unknown_identity
    from claude_migration_overlay import create_overlay

    directory = ROOT / "runtime/claude-demo-20261120"
    marker = directory / "claude_probe_attempt.json"
    dry_run = "--dry-run" in sys.argv
    if not dry_run and marker.exists():
        raise RuntimeError("probe_already_attempted")
    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    recovery_dir = (ROOT / state["directory"]).resolve(strict=True)
    if not recovery_dir.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise RuntimeError("invalid_recovery_directory")
    key = "offline-test-only" if dry_run else Settings().anthropic_api_key.get_secret_value()
    if not key:
        raise RuntimeError("credential_unavailable")
    schema = "tf_claude_demo_" + uuid4().hex
    terms = {
        "snapshot_date": "2026-11-20",
        "scope": "synthetic_data_only",
        "owner_authorized_total_usd": "20.00",
        "per_attempt_reservation_usd": "2.10",
        "provider": "anthropic",
        "model": "claude-sonnet-5-5",
        "privacy_retention_source": "https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data",
        "training_source": "https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training",
        "pricing_source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "qualification": "Public-source summary; not legal certification or account-specific terms review.",
    }
    (directory / "anthropic_public_terms_snapshot.json").write_text(
        json.dumps(terms, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    identity = unknown_identity()
    identity["expected_schema_revision"] = "0020_claude_provider"
    (directory / "claude_candidate_release.json").write_text(json.dumps(identity) + "\n")
    (directory / "claude_candidate_schema.py").write_text(
        'EXPECTED_SCHEMA_REVISION = "0020_claude_provider"\n'
    )
    if not dry_run:
        with marker.open("x", encoding="utf-8") as output:
            json.dump({"schema": schema, "approval_id": APPROVAL, "max_total_usd": "20.00"}, output)
    command = recovery.linux_args(state, recovery_dir)[:-4]
    command[1] = "create"
    index = command.index("trueflag-assessment-verify:phase2-5")
    overlay = create_overlay()
    command[index:index] = ["-v", f"{overlay.as_posix()}:/workspace/backend/alembic/versions:ro"]
    command += [
        "-v",
        f"{directory.as_posix()}:/demo:rw",
        "-v",
        f"{(directory / 'claude_candidate_schema.py').as_posix()}:/workspace/backend/app/core/schema.py:ro",
        "-v",
        f"{(directory / 'claude_candidate_release.json').as_posix()}:/workspace/backend/app/_release.json:ro",
        "python",
        "-B",
        "/workspace/scripts/run_claude_synthetic_probe.py",
        "--inside",
    ]
    # linux_args places the image immediately before the original four command arguments.
    image_index = command.index("trueflag-assessment-verify:phase2-5")
    mounts = command[image_index + 1 : image_index + 7]
    command[image_index : image_index + 7] = mounts + [command[image_index]]
    created = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    container_id = created.stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{64}", container_id):
        raise RuntimeError("isolated_container_invalid")
    try:
        if not dry_run:
            subprocess.run(
                ["docker", "network", "connect", "bridge", container_id],
                capture_output=True,
                check=True,
                timeout=30,
            )
        result = subprocess.run(
            ["docker", "start", "-ai", container_id],
            input=json.dumps({"schema": schema, "key": key, "dry_run": dry_run}),
            text=True,
            capture_output=True,
            timeout=120,
        )
        for line in result.stdout.splitlines():
            if line.startswith('{"isolated_schema"'):
                print(line)
        if result.returncode:
            print(json.dumps({"status": "unavailable", "dispatch": "inspect retained ledger"}))
        return result.returncode
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, timeout=30)


if __name__ == "__main__":
    try:
        if "--inside" in sys.argv:
            inside()
        else:
            raise SystemExit(main())
    except Exception:
        print(
            json.dumps({"status": "unavailable", "details": "withheld", "live_request": "unknown"})
        )
        raise SystemExit(1) from None
