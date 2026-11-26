"""One separately reserved synthetic Claude diagnostic; never an automatic retry."""

import hashlib
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def inside():
    import rehearse_database_recovery as recovery
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models import AuditEvent
    from app.models.investigation_drafts import DraftAttempt, DraftReceipt, DraftRun
    from app.models.investigations import InvestigationRun
    from app.schemas.investigations import InputManifest, InvestigationPacketBody
    from app.schemas.provider_live import ClaudeProviderConfig
    from app.services.claude_contract import output_schema
    from app.services.ingestion import digest
    from app.services.investigation_coordinator import InvestigationCoordinator
    from app.services.investigation_draft_verifier import minimize
    from app.services.investigation_drafts import InvestigationDraftService
    from app.services.live_provider_runner import ProviderRunner
    from app.services.luminal_provider import ProviderRateLimited, ProviderRejected
    from app.services.provider_finance import reservation_totals
    from pydantic import SecretStr
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    payload = json.loads(sys.stdin.read(65537))
    schema, dry = payload["schema"], payload.get("dry_run") is True
    detail, fix, verify = (
        payload.get("detail") is True,
        payload.get("fix") is True,
        payload.get("verify") is True,
    )
    claim_fix = payload.get("claim_fix") is True
    preflight = payload.get("preflight") is True
    if not re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema):
        raise RuntimeError("invalid_isolated_schema")
    progress = Path(
        "/demo/claude_claim_fix_preflight_progress.json"
        if claim_fix and preflight
        else "/demo/claude_claim_fix_progress.json"
        if claim_fix
        else "/demo/claude_verification_progress.json"
        if verify
        else "/demo/claude_diagnostic_dry_progress.json"
        if dry
        else "/demo/claude_diagnostic_progress.json"
    )
    progress.write_text(json.dumps({"stage": "preparing"}))
    state, base_url, control = recovery.inside_connection()
    control.dispose()
    url = base_url.set(database=state["database"]).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    db_url = url.render_as_string(hide_password=False)
    engine = make_engine(db_url)
    with Session(engine) as session:
        previous = session.scalars(
            select(DraftRun)
            .where(DraftRun.configuration["provider"].as_string() == "anthropic")
            .where(DraftRun.configuration["purpose"].as_string() == "compatibility_probe")
        ).one()
        parent = session.get(InvestigationRun, previous.parent_run_id)
        attempt = session.scalars(
            select(DraftAttempt).where(DraftAttempt.run_id == previous.id)
        ).one()
        receipt = session.scalars(
            select(DraftReceipt).where(DraftReceipt.attempt_id == attempt.id)
        ).one()
        expected_attempts = 5 if claim_fix else 4 if verify else 3 if fix else 2 if detail else 1
        if (
            receipt.status == "completed"
            or reservation_totals(session, provider="anthropic")[0] != expected_attempts
        ):
            raise RuntimeError("diagnostic_not_permitted")
        actor, case = parent.actor_id, parent.case_id
        parent_id, request = parent.id, InputManifest.model_validate(parent.input_manifest).request
        prior_terms = previous.configuration["terms_sha256"]
    terms_sha = hashlib.sha256(
        Path("/demo/anthropic_public_terms_snapshot.json").read_bytes()
    ).hexdigest()
    if terms_sha != prior_terms:
        raise RuntimeError("provider_terms_snapshot_changed")
    settings = Settings(
        _env_file=None,
        database_url=db_url,
        jwt_secret=secrets.token_urlsafe(48),
        anthropic_api_key=SecretStr(payload["key"]),
        anthropic_synthetic_demo_enabled=True,
        anthropic_contract_verified=False,
        anthropic_diagnostic_enabled=not fix and not verify,
        anthropic_fix_verification_enabled=fix,
        anthropic_verification_diagnostic_enabled=verify,
        anthropic_claim_fix_enabled=claim_fix,
        anthropic_terms_sha256=terms_sha,
        anthropic_demo_spend_limit_usd=20,
        anthropic_demo_call_limit=10,
    )
    token = secrets.token_urlsafe(48)
    coordinator = InvestigationCoordinator(engine, settings)
    worker_name = (
        "claude-claim-fix-preflight-worker"
        if claim_fix and preflight
        else "claude-claim-fix-worker-v2"
        if claim_fix
        else "claude-verification-worker"
        if verify
        else "claude-fix-worker"
        if fix
        else "claude-diagnostic-detail-worker"
        if detail
        else "claude-diagnostic-worker"
    )
    coordinator.register_worker(actor, worker_name, token)
    if claim_fix:
        # A new, server-verified packet is needed after snapshot expiry or an epoch change.
        # The coordinator rechecks the original actor, case, sources and authorization.
        current = coordinator.reader.get_case_context(actor, case, request.assessment_id)
        request = request.model_copy(update={
            "expected_case_version": current.snapshot.case_version,
            "expected_evidence_revision": current.snapshot.evidence_revision,
            "expected_access_revision": current.snapshot.access_revision,
        })
        fresh = coordinator.request(actor, case, "claude-claim-fix-parent-001", request)
        fresh_id = UUID(fresh["run_id"])
        fresh_view = coordinator.get(actor, case, fresh_id)
        if fresh_view["status"] in {"pending", "running"}:
            coordinator.run_once(token)
            fresh_view = coordinator.get(actor, case, fresh_id)
        if fresh_view["status"] not in {"succeeded", "abstained"}:
            raise RuntimeError("fresh_authorized_packet_unavailable")
        parent_id = fresh_id
    parent_view = coordinator.get(actor, case, parent_id)
    packet = InvestigationPacketBody.model_validate(parent_view["packet"])
    exact = digest(minimize(packet).model_dump(mode="json"))
    if preflight:
        print(json.dumps({"isolated_schema": schema, "preflight": True,
                          "synthetic_only": True, "source_authorized": True,
                          "packet_verified": True, "dispatch_attempted": False}))
        engine.dispose()
        return
    settings.anthropic_diagnostic_input_sha256 = exact
    settings.anthropic_fix_input_sha256 = exact
    settings.anthropic_verification_input_sha256 = exact
    settings.anthropic_claim_fix_input_sha256 = exact
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256=terms_sha,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd="2.14" if claim_fix else "2.13" if verify else "2.12" if fix else "2.11" if detail else "2.10",
        purpose="claim_type_fix_verification"
        if claim_fix
        else "verification_diagnostic"
        if verify
        else "compatibility_fix_verification"
        if fix
        else "compatibility_diagnostic",
        exact_input_sha256=exact,
    )
    drafts = InvestigationDraftService(engine, settings)
    key = (
        "claude-claim-type-fix-verification-001"
        if claim_fix
        else "claude-grounding-diagnostic-001"
        if verify
        else "claude-fix-verification-001"
        if fix
        else "claude-diagnostic-detail-001"
        if detail
        else "claude-diagnostic-draft-001"
    )
    draft = drafts.request(actor, case, key, request, config)
    if dry:
        claim = drafts.claim(token)
        if claim is None or drafts.prepare(token, claim) is None:
            raise RuntimeError("diagnostic_reservation_unavailable")
        diagnostics = (
            {
                "parseable": True,
                "model_matches": True,
                "stop_reason": "end_turn",
                "text_blocks": 1,
                "other_blocks": 0,
                "schema_valid": False,
                "schema_errors": ["packet_sha256:string_pattern_mismatch"],
                "input_tokens": 10,
                "output_tokens": 10,
                "cache_tokens": 0,
            }
            if detail
            else None
        )
        drafts.fail(
            token,
            claim,
            "verification_failed" if fix else "provider_unavailable",
            diagnostics=diagnostics,
            verification_reason="question_mismatch" if fix else None,
        )
        print(json.dumps({"isolated_schema": schema, "dry_run": True, "dispatch_attempted": False}))
        return

    class CaptureRunner:
        invoked = False
        http_status = None
        diagnostics = None
        usage = None

        def invoke(self, provider_input, provider_config):
            self.invoked = True
            progress.write_text(json.dumps({"stage": "provider_invoked"}))
            try:
                reply = ProviderRunner(settings).invoke(provider_input, provider_config)
                self.http_status = 200
                self.usage = reply.usage.model_dump(mode="json")
                return reply
            except (ProviderRejected, ProviderRateLimited) as error:
                self.http_status = error.http_status
                self.diagnostics = getattr(error, "diagnostics", None)
                raise

    capture = CaptureRunner()
    drafts._runner = capture
    result = drafts.run_once(token) or {"status": "unavailable"}
    with Session(engine) as session:
        attempts, reserved = reservation_totals(session, provider="anthropic")
        event = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == "evidence.investigation.draft.attempt_failed")
            .where(AuditEvent.resource_id == draft["draft_run_id"])
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        verification_reason = event.details.get("verification_reason") if event else None
    report = {
        "isolated_schema": schema,
        "synthetic_only": True,
        "provider": "anthropic",
        "model_requested": config.model,
        "dispatch_attempted": capture.invoked,
        "http_status": capture.http_status,
        "diagnostics": capture.diagnostics,
        "usage": capture.usage,
        "worker_status": result.get("status"),
        "error_code": result.get("error_code"),
        "compatibility_verified": False,
        "ledger_attempts": attempts,
        "reserved_usd": str(reserved),
        "verification_reason": verification_reason,
    }
    result_path = (
        "/demo/claude_claim_fix_result.json"
        if claim_fix
        else "/demo/claude_verification_result.json"
        if verify
        else "/demo/claude_fix_result.json"
        if fix
        else "/demo/claude_diagnostic_detail_result.json"
        if detail
        else "/demo/claude_diagnostic_result.json"
    )
    Path(result_path).write_text(json.dumps(report, indent=2))
    progress.write_text(json.dumps({"stage": "finished"}))
    print(json.dumps(report))
    engine.dispose()


def main():
    import rehearse_database_recovery as recovery
    from app.core.config import Settings

    demo = ROOT / "runtime/claude-demo-20261120"
    dry = "--dry-run" in sys.argv
    detail = "--detail" in sys.argv
    fix = "--fix" in sys.argv
    verify = "--verify" in sys.argv
    claim_fix = "--claim-fix" in sys.argv
    preflight = "--preflight" in sys.argv
    recover = "--recover-pre-dispatch" in sys.argv
    if preflight and not claim_fix:
        raise RuntimeError("preflight_requires_claim_fix")
    if recover and (not claim_fix or preflight or dry):
        raise RuntimeError("invalid_predispatch_recovery")
    marker = demo / (
        "claude_claim_fix_attempt.json"
        if claim_fix
        else "claude_verification_attempt.json"
        if verify
        else "claude_fix_attempt.json"
        if fix
        else "claude_diagnostic_detail_attempt.json"
        if detail
        else "claude_diagnostic_attempt.json"
    )
    if recover:
        progress = json.loads((demo / "claude_claim_fix_progress.json").read_text())
        if not marker.exists() or progress.get("stage") != "preparing":
            raise RuntimeError("predispatch_recovery_not_permitted")
        marker = demo / "claude_claim_fix_recovery_attempt.json"
    if not dry and not preflight and marker.exists():
        raise RuntimeError("diagnostic_already_attempted")
    prior = json.loads(
        (
            demo / ("claude_probe_dry_run_result.json" if dry else "claude_probe_result.json")
        ).read_text()
    )
    if not dry and (prior.get("http_status") != 200 or prior.get("worker_status") != "failed"):
        raise RuntimeError("diagnostic_not_permitted")
    if detail and not dry:
        diagnostic = json.loads((demo / "claude_diagnostic_result.json").read_text())
        if diagnostic.get("http_status") != 200 or diagnostic.get("worker_status") != "failed":
            raise RuntimeError("detailed_diagnostic_not_permitted")
    if fix and not dry:
        diagnostic = json.loads((demo / "claude_diagnostic_detail_result.json").read_text())
        errors = (diagnostic.get("diagnostics") or {}).get("schema_errors", [])
        if "packet_sha256:string_pattern_mismatch" not in errors:
            raise RuntimeError("fix_verification_not_permitted")
    if verify and not dry:
        previous = json.loads((demo / "claude_fix_result.json").read_text())
        if previous.get("error_code") != "verification_failed":
            raise RuntimeError("verification_diagnostic_not_permitted")
    if claim_fix and not dry:
        previous = json.loads((demo / "claude_verification_result.json").read_text())
        if (previous.get("verification_reason") != "claim_type_mismatch"
                or previous.get("error_code") != "verification_failed"):
            raise RuntimeError("claim_fix_verification_not_permitted")
    schema = prior["isolated_schema"]
    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise RuntimeError("invalid_recovery_directory")
    key = "offline-test-only" if dry or preflight else Settings().anthropic_api_key.get_secret_value()
    if not key:
        raise RuntimeError("credential_unavailable")
    if not dry and not preflight:
        with marker.open("x", encoding="utf-8") as output:
            reason = (
                "confirmed_claim_type_mismatch_fix"
                if claim_fix
                else "evidence_verification_diagnostic"
                if verify
                else "confirmed_packet_hash_fix"
                if fix
                else "schema_field_diagnostic"
                if detail
                else "first_response_diagnostics_missing"
            )
            json.dump({"schema": schema, "reason": reason}, output)
    command = recovery.linux_args(state, directory)[:-4]
    command[1] = "create"
    image_index = command.index("trueflag-assessment-verify:phase2-5")
    command[image_index:image_index] = [
        "-v",
        f"{demo.as_posix()}:/demo:rw",
        "-v",
        f"{(demo / 'claude_candidate_schema.py').as_posix()}:/workspace/backend/app/core/schema.py:ro",
        "-v",
        f"{(demo / 'claude_candidate_release.json').as_posix()}:/workspace/backend/app/_release.json:ro",
    ]
    command += ["python", "-B", "/workspace/scripts/run_claude_diagnostic_probe.py", "--inside"]
    created = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    container_id = created.stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{64}", container_id):
        raise RuntimeError("isolated_container_invalid")
    try:
        if not dry and not preflight:
            subprocess.run(
                ["docker", "network", "connect", "bridge", container_id],
                capture_output=True,
                check=True,
                timeout=30,
            )
        result = subprocess.run(
            ["docker", "start", "-ai", container_id],
            input=json.dumps(
                {
                    "schema": schema,
                    "key": key,
                    "dry_run": dry,
                    "detail": detail,
                    "fix": fix,
                    "verify": verify,
                    "claim_fix": claim_fix,
                    "preflight": preflight,
                }
            ),
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
