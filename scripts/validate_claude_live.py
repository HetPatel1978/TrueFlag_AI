"""Explicit synthetic live validation through the existing durable ledger and verifier.

Default is network-isolated preflight. --execute permits one attempt per wire version;
it does not enable general analyst generation or modify the local application.
"""

import hashlib
import json
import re
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def approved_request(demo, wire_sha256):
    """Read an explicit owner record; never infer approval or rewrite it."""
    approval = json.loads((demo / "live_validation_owner_approval.json").read_text())
    preflight = json.loads((demo / "live_validation_preflight.json").read_text())
    if (
        approval.get("decision") != "approved"
        or approval.get("provider") != "anthropic"
        or approval.get("model") != "claude-sonnet-5-5"
        or approval.get("endpoint") != "https://api.anthropic.com/v1/messages"
        or type(approval.get("request_limit")) is not int
        or approval["request_limit"] != 1
        or approval.get("reservation_usd") != "2.15"
        or approval.get("request_sha256") != preflight["request_sha256"]
        or approval.get("wire_schema_sha256") != wire_sha256
    ):
        raise RuntimeError("exact_owner_approval_required")
    return approval["request_sha256"]


def approved_development_request(demo, wire_sha256):
    """A new approval namespace; a consumed reserved-demo approval is never reused."""
    approval = json.loads((demo / "development-v2/owner_approval.json").read_text())
    preflight = json.loads((demo / "development-v2/preflight.json").read_text())
    limits = dict(
        max_input_tokens=32768,
        max_output_tokens=4096,
        total_token_budget=36864,
        max_request_bytes=65536,
        max_response_bytes=65536,
        request_deadline_seconds=20,
        request_limit=1,
        max_attempts=1,
        max_outstanding_requests=1,
    )
    valid = (
        approval.get("decision") == "approved"
        and approval.get("record_id") == "claude-development-review-2026-11-22-v2"
        and approval.get("provider") == "anthropic"
        and approval.get("model") == "claude-sonnet-5-5"
        and approval.get("endpoint") == "https://api.anthropic.com/v1/messages"
        and approval.get("financial_scope") == "development_no_spend_cap_v1"
        and approval.get("wire_format") == "flat_selection_v2"
        and approval.get("wire_schema_sha256") == wire_sha256
        and approval.get("request_sha256") == preflight["request_sha256"]
        and approval.get("automatic_retries") is False
        and approval.get("general_analyst_activation_authorized") is False
        and approval.get("application_reservation_required") is False
        and approval.get("total_spend_cap_usd") is None
        and approval.get("per_request_spend_cap_usd") is None
        and approval.get("follow_redirects") is False
        and approval.get("tools_enabled") is False
        and approval.get("streaming") is False
        and approval.get("regulatory_grounding_enabled") is False
        and approval.get("financial_authorization_sha256")
        == __import__("hashlib")
        .sha256((ROOT / "contracts/claude_development_financial_scope_v1.json").read_bytes())
        .hexdigest()
        and all(type(approval.get(k)) is int and approval[k] == v for k, v in limits.items())
    )
    if not valid:
        raise RuntimeError("exact_development_owner_approval_required")
    raw = (demo / "development-v2/request.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != approval["request_sha256"]
        or len(raw) != approval["payload_bytes"]
    ):
        raise RuntimeError("approved_payload_changed_no_dispatch")
    from app.schemas.investigation_drafts import ProviderInput
    from app.services.claude_contract import request_body
    from app.services.ingestion import digest

    body = json.loads(raw)
    packet = ProviderInput.model_validate_json(body["messages"][0]["content"])
    if (
        request_body(packet, wire_format="flat_selection_v2") != raw
        or approval.get("embedded_schema_sha256")
        != digest(body["output_config"]["format"]["schema"])
        or approval.get("exact_input_sha256") != digest(packet.model_dump(mode="json"))
        or approval.get("provider_terms_sha256")
        != hashlib.sha256((demo / "anthropic_public_terms_snapshot.json").read_bytes()).hexdigest()
    ):
        raise RuntimeError("approved_schema_input_or_terms_changed")
    return approval["request_sha256"]


def inside():
    import rehearse_database_recovery as recovery
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models import AuditEvent
    from app.models.investigation_drafts import DraftAttempt, DraftRun
    from app.models.investigations import InvestigationRun
    from app.schemas.investigations import InputManifest, InvestigationPacketBody
    from app.schemas.provider_live import ClaudeProviderConfig
    from app.services.claude_contract import MODEL, output_schema, request_body
    from app.services.ingestion import digest
    from app.services.investigation_coordinator import InvestigationCoordinator
    from app.services.investigation_draft_verifier import minimize
    from app.services.investigation_drafts import InvestigationDraftService
    from app.services.live_provider_runner import ProviderRunner
    from app.services.luminal_provider import ProviderRejected
    from app.services.provider_finance import reservation_totals
    from app.services.snapshot_clock import SnapshotTime
    from pydantic import SecretStr
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    args = json.loads(sys.stdin.read(65537))
    demo = Path("/demo")
    development = args.get("development") is True
    review = demo / "development-v2" if development else demo
    review.mkdir(exist_ok=True)
    wire_format = "flat_selection_v2" if development else "legacy_v1"
    original = json.loads((demo / "claude_probe_attempt.json").read_text())
    schema = original["schema"]
    if not re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema):
        raise RuntimeError("invalid_isolated_schema")
    state, url, control = recovery.inside_connection()
    control.dispose()
    url = url.set(database=state["database"]).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    settings = Settings(
        _env_file=None,
        database_url=url.render_as_string(hide_password=False),
        jwt_secret="isolated-live-validation-no-browser-session",
        anthropic_api_key=SecretStr(args.get("key", "")),
        anthropic_synthetic_demo_enabled=True,
        anthropic_contract_verified=False,
        anthropic_live_validation_enabled=True,
        anthropic_demo_spend_limit_usd=0 if development else 20,
        anthropic_demo_call_limit=0 if development else 10,
    )
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        previous = session.scalars(
            select(DraftRun).where(
                DraftRun.configuration["provider"].as_string() == "anthropic",
                DraftRun.configuration["purpose"].as_string() == "compatibility_probe",
            )
        ).one()
        parent = session.get(InvestigationRun, previous.parent_run_id)
        actor, case = parent.actor_id, parent.case_id
        request = InputManifest.model_validate(parent.input_manifest).request
        terms = hashlib.sha256(
            (demo / "anthropic_public_terms_snapshot.json").read_bytes()
        ).hexdigest()
        if terms != previous.configuration["terms_sha256"]:
            raise RuntimeError("terms_changed")
        calls, reserved = reservation_totals(session, provider="anthropic")
        if args["execute"] and session.scalar(
            select(DraftAttempt.id)
            .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
            .where(
                DraftRun.configuration["provider"].as_string() == "anthropic",
                DraftRun.configuration["purpose"].as_string()
                == ("development_validation" if development else "live_validation"),
                DraftRun.configuration["wire_schema_sha256"].as_string()
                == digest(output_schema(wire_format=wire_format)),
            )
            .limit(1)
        ):
            raise RuntimeError("wire_validation_already_reserved_no_retry")
        if not development and (calls >= 10 or reserved + Decimal("2.15") > 20):
            raise RuntimeError("budget_exhausted")
    settings.anthropic_terms_sha256 = terms
    for _ in range(3):
        SnapshotTime(engine).observe()
        time.sleep(1)
    coordinator = InvestigationCoordinator(engine, settings)
    token = __import__("secrets").token_urlsafe(48)
    coordinator.register_worker(
        actor, "claude-live-validation-" + __import__("uuid").uuid4().hex[:12], token
    )
    current = coordinator.reader.get_case_context(actor, case, request.assessment_id)
    request = request.model_copy(
        update=dict(
            expected_case_version=current.snapshot.case_version,
            expected_evidence_revision=current.snapshot.evidence_revision,
            expected_access_revision=current.snapshot.access_revision,
        )
    )
    wire = digest(output_schema(wire_format=wire_format))
    # A fresh run is needed when old 900-second snapshots have expired. Sources
    # are reused with their true identities; only the authorized snapshot is new.
    key = "live-validation-" + wire[:24] + "-" + __import__("uuid").uuid4().hex[:12]
    parent = coordinator.request(actor, case, key, request)
    parent_id = UUID(parent["run_id"])
    if coordinator.get(actor, case, parent_id)["status"] in {"pending", "running"}:
        coordinator.run_once(token)
    view = coordinator.get(actor, case, parent_id)
    if view["status"] not in {"succeeded", "abstained"}:
        raise RuntimeError("verified_parent_unavailable")
    packet = InvestigationPacketBody.model_validate(view["packet"])
    minimized = minimize(packet)
    exact = digest(minimized.model_dump(mode="json"))
    settings.anthropic_live_validation_input_sha256 = exact
    if development:
        settings.anthropic_live_validation_enabled = False
        settings.anthropic_development_validation_enabled = True
        settings.anthropic_development_input_sha256 = exact
        settings.anthropic_development_approval_id = "claude-development-review-2026-11-22-v2"
    config = ClaudeProviderConfig(
        approval_id=settings.anthropic_development_approval_id
        if development
        else "synthetic-claude-demo-2026-11-20",
        terms_sha256=terms,
        wire_schema_sha256=wire,
        max_cost_usd="0" if development else "2.15",
        purpose="development_validation" if development else "live_validation",
        financial_scope="development_no_spend_cap_v1" if development else "reserved_demo_v1",
        wire_format=wire_format,
        exact_input_sha256=exact,
    )
    raw = request_body(minimized, wire_format=wire_format)
    # Local synthetic-only review copy. Never includes the API key; preflight's
    # Docker network has no external egress. Live dispatch still needs approval.
    request_path = review / (
        "request.json"
        if development
        else "live_validation_payload_" + hashlib.sha256(raw).hexdigest() + ".json"
    )
    if request_path.exists() and request_path.read_bytes() != raw:
        raise RuntimeError("prepared_payload_changed_review_required")
    if not request_path.exists():
        request_path.write_bytes(raw)
    if args["execute"] and args.get("approved_request_sha256") != hashlib.sha256(raw).hexdigest():
        raise RuntimeError("approved_payload_changed_no_dispatch")
    report = dict(
        provider="anthropic",
        model_requested=MODEL,
        synthetic_only=True,
        wire_schema_sha256=wire,
        exact_input_sha256=exact,
        request_sha256=hashlib.sha256(raw).hexdigest(),
        source_authorized=True,
        packet_verified=True,
        clock_observations=3,
        prior_attempts=calls,
        prior_reserved_usd=str(reserved),
        attempt_reservation_usd=None if development else "2.15",
        financial_scope=config.financial_scope,
        dispatch_attempted=False,
        compatibility_verified=False,
    )
    if not args["execute"]:
        (
            review / ("preflight.json" if development else "live_validation_preflight.json")
        ).write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
        return

    class Capture:
        def invoke(self, provider_input, provider_config):
            report["dispatch_attempted"] = True
            (
                review / ("progress.json" if development else "live_validation_progress.json")
            ).write_text(json.dumps(report))
            start = time.monotonic()
            try:
                reply = ProviderRunner(settings).invoke(provider_input, provider_config)
                report.update(
                    http_status=200,
                    model_returned=reply.model,
                    usage=reply.usage.model_dump(mode="json"),
                )
                return reply
            except ProviderRejected as error:
                report.update(http_status=error.http_status, diagnostics=error.diagnostics)
                raise
            finally:
                report["latency_ms"] = round((time.monotonic() - start) * 1000)

    drafts = InvestigationDraftService(engine, settings)
    drafts._runner = Capture()
    result = drafts.request(
        actor, case, ("development-" if development else "live-validation-") + wire, request, config
    )
    outcome = drafts.run_once(token) or {}
    with Session(engine) as session:
        calls, reserved = reservation_totals(session, provider="anthropic")
        event = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.action == "evidence.investigation.draft.attempt_failed",
                AuditEvent.resource_id == result["draft_run_id"],
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
    report.update(
        worker_status=outcome.get("status"),
        error_code=outcome.get("error_code"),
        verification_reason=event.details.get("verification_reason") if event else None,
        ledger_attempts=calls,
        reserved_usd=str(reserved),
        compatibility_verified=outcome.get("status") == "succeeded",
        draft_run_id=result["draft_run_id"],
        parent_run_id=str(parent_id),
    )
    result_path = review / ("result.json" if development else "live_validation_result.json")
    if development:
        with result_path.open("x") as output:
            json.dump(report, output, indent=2)
    else:
        result_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


def main():
    import rehearse_database_recovery as recovery
    from app.core.config import Settings
    from app.services.claude_contract import output_schema
    from app.services.ingestion import digest

    execute = "--execute" in sys.argv
    development = "--development" in sys.argv
    wire_format = "flat_selection_v2" if development else "legacy_v1"
    demo = ROOT / "runtime/claude-demo-20261120"
    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise RuntimeError("isolated_clone_required")
    key = Settings().anthropic_api_key.get_secret_value() if execute else ""
    if execute and not key:
        raise RuntimeError("credential_missing")
    approved_hash = None
    if execute:
        approved_hash = (approved_development_request if development else approved_request)(
            demo, digest(output_schema(wire_format=wire_format))
        )
    if execute:
        marker = demo / (
            ("development-v2/attempt-" if development else "live-validation-")
            + digest(output_schema(wire_format=wire_format))
            + ".attempt.json"
        )
        if "--recover-pre-dispatch" in sys.argv:
            if not marker.exists():
                raise RuntimeError("no_predispatch_attempt_to_recover")
            # Never remove the original marker. The DB must prove no reservation
            # for this wire version before execution can progress.
            marker = demo / (marker.stem + ".recovery-" + __import__("uuid").uuid4().hex + ".json")
        with marker.open("x") as file:
            json.dump(
                dict(
                    authorization="synthetic-claude-demo-2026-11-20",
                    max_reservation_usd=None if development else "2.15",
                    automatic_retries=False,
                ),
                file,
            )
    command = recovery.linux_args(state, directory)[:-4]
    command[1] = "create"
    idx = command.index("trueflag-assessment-verify:phase2-5")
    schema_path, release_path = (
        demo / "claude_candidate_schema.py",
        demo / "claude_candidate_release.json",
    )
    if development and (
        execute or (demo / "development-v2/isolated_migration_receipt.json").exists()
    ):
        # Candidate schema is required, never silently installed on a database.
        # Operator must first rehearse/back up and upgrade the isolated probe only.
        candidate = demo / "development-v2"
        schema_path, release_path = (
            candidate / "candidate_schema.py",
            candidate / "candidate_release.json",
        )
    command[idx:idx] = [
        "-v",
        f"{demo.as_posix()}:/demo:rw",
        "-v",
        f"{schema_path.as_posix()}:/workspace/backend/app/core/schema.py:ro",
        "-v",
        f"{release_path.as_posix()}:/workspace/backend/app/_release.json:ro",
    ]
    command += ["python", "-B", "/workspace/scripts/validate_claude_live.py", "--inside"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    container = process.stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{64}", container):
        raise RuntimeError("invalid_container")
    try:
        if execute:
            subprocess.run(
                ["docker", "network", "connect", "bridge", container],
                capture_output=True,
                check=True,
                timeout=30,
            )
        result = subprocess.run(
            ["docker", "start", "-ai", container],
            input=json.dumps(
                dict(
                    key=key,
                    execute=execute,
                    development=development,
                    approved_request_sha256=approved_hash,
                )
            ),
            capture_output=True,
            text=True,
            timeout=120,
        )
        for line in result.stdout.splitlines():
            if line.startswith('{"provider"') or line.startswith('{"blocked"'):
                print(line)
        if result.returncode:
            print(json.dumps(dict(blocked=True, details="withheld; inspect safe progress/ledger")))
        return result.returncode
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)


if __name__ == "__main__":
    try:
        if "--inside" in sys.argv:
            inside()
        else:
            raise SystemExit(main())
    except Exception as error:
        import traceback

        print(
            json.dumps(
                dict(
                    blocked=True,
                    error_type=type(error).__name__,
                    locations=[
                        dict(file=Path(f.filename).name, line=f.lineno)
                        for f in traceback.extract_tb(error.__traceback__)[-5:]
                    ],
                )
            )
        )
        raise SystemExit(1) from None
