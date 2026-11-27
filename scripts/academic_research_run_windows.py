"""One owner-approved academic Claude + research-RAG request, without manual package juggling.

    review                       the owner's one-step path, run in the owner's own terminal:
                                 only now take a fresh evidence snapshot and build the exact
                                 request, show it (full payload on request), and if the owner
                                 types its complete SHA-256, record that approval and submit
                                 it once immediately. No approval, no request. Requires an
                                 interactive terminal; piped or automated input is refused.
    status                       show the current exact request and its dispatch deadline
    prepare                      reuse the current request if it is still approvable, otherwise
                                 refresh the 900 s evidence snapshot and generate a new request
    approve-and-run --approval-id ID --request-sha256 SHA --decision-text TEXT
                                 if (and only if) SHA is the current, unexpired, never-attempted
                                 request: record the owner approval, re-run the worker's own
                                 gates, submit once through the existing Generate AI Investigation
                                 endpoint and verify the stored result. Otherwise nothing is
                                 recorded or sent; an expired request is refreshed and the new
                                 hash is printed for a new explicit approval.

Snapshot lifetime, clock protections, exact-hash authorization, one request with zero retries
and independent verification are unchanged. Expired drafts retire through the app's audited
path when the next request is staged. Secrets are never printed.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
SERIES = re.compile(r"^academic-claude-research-review-(\d{4}-\d{2}-\d{2})-v(\d+)$")
# The worker refuses dispatch unless more than request_deadline+30 s (150 s) remain; keep a
# small extra margin for recording, preflight and submission latency.
DISPATCH_FLOOR_SECONDS = 150
SUBMIT_MARGIN_SECONDS = 30
# Reuse an existing request for a new approval only if a reviewer still has this long.
REUSE_MINIMUM_SECONDS = DISPATCH_FLOOR_SECONDS + 300


def decide(package, *, approved_sha256, approval_id, now_second, latest_id, job):
    """Pure gate: 'execute', or the reason nothing may be recorded or sent."""
    if approval_id != package["approval_id"] or approval_id != latest_id:
        return "superseded"
    if approved_sha256 != package["request_sha256"]:
        return "hash_mismatch"
    if job != ("pending", 0):
        return "not_pending"
    if package["expires_second"] - now_second <= DISPATCH_FLOOR_SECONDS + SUBMIT_MARGIN_SECONDS:
        return "expired"
    return "execute"


def owner_confirms(answer, request_sha256):
    """Only the complete, exact SHA-256 of the displayed request counts as approval."""
    return (
        isinstance(answer, str)
        and re.fullmatch(r"[0-9a-f]{64}", request_sha256 or "") is not None
        and answer.strip().lower() == request_sha256
    )


def runtime():
    sys.path.insert(0, str(ROOT / "scripts"))
    from windows_runtime import clean_env, current

    directory, state = current()
    os.environ.update(clean_env(state))
    sys.path.insert(0, os.environ["PYTHONPATH"])
    return directory, state


def latest_package(demo):
    found = []
    for path in demo.iterdir():
        match = SERIES.match(path.name)
        if match and (path / "approval-package.json").is_file():
            found.append((int(match.group(2)), path))
    if not found:
        return None
    return json.loads((max(found)[1] / "approval-package.json").read_text())


def next_approval_id(demo):
    versions = [int(m.group(2)) for p in demo.iterdir() if (m := SERIES.match(p.name))]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"academic-claude-research-review-{today}-v{max(versions, default=0) + 1}"


def observe(state, package):
    """App snapshot clock plus the package's durable job state (read-only)."""
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models.investigation_drafts import DraftAttempt, DraftJob
    from app.services.research_drafts import ResearchDraftService
    from sqlalchemy import func, select

    engine = make_engine(state["database_url"])
    try:
        service = ResearchDraftService(engine, Settings(_env_file=None))
        with Session(engine) as session:
            run = UUID(package["draft_run_id"])
            job = session.get(DraftJob, run)
            attempts = session.scalar(
                select(func.count()).select_from(DraftAttempt).where(DraftAttempt.run_id == run)
            )
            observed = service.coordinator.reader.clock.observe()
        return observed.second, (job.status, job.attempts), attempts
    finally:
        engine.dispose()


def summary(package, now_second):
    deadline = package["expires_second"] - DISPATCH_FLOOR_SECONDS
    stamp = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%H:%M:%S UTC")  # noqa: E731
    return {
        "approval_id": package["approval_id"],
        "request_sha256": package["request_sha256"],
        "request_bytes": package["request_bytes"],
        "model": package["model"],
        "timeout_seconds": package["timeout_seconds"],
        "maximum_requests": package["maximum_requests"],
        "automatic_retries": package["automatic_retries"],
        "synthetic_only": package["synthetic_only"],
        "max_output_tokens": package["max_output_tokens"],
        "reservation_usd": package["application_reservation_usd"],
        "source_approval": package["source_approval"],
        "source_sections": package["source_sections"],
        "full_request": package["full_payload_file"],
        "snapshot_expires": stamp(package["expires_second"]),
        "dispatch_deadline": stamp(deadline),
        "seconds_remaining_to_approve": max(0, deadline - SUBMIT_MARGIN_SECONDS - now_second),
    }


def prepare(directory, state, *, force=False):
    demo = directory / "academic-demo"
    package = latest_package(demo)
    if package is not None and not force:
        now, job, _ = observe(state, package)
        if job == ("pending", 0) and package["expires_second"] - now > REUSE_MINIMUM_SECONDS:
            return package, now, "reused"
    approval_id = next_approval_id(demo)
    # Existing preparation path: fresh snapshot, binding, staged draft (which retires expired
    # drafts through the audited path) and exact request file. No provider call.
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_academic_demo_windows.py"), "request",
         "--approval-id", approval_id],
        cwd=ROOT / "scripts", capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    outcome = json.loads(lines[-1]) if lines else {"status": "blocked", "code": "no_output"}
    if result.returncode or "request_sha256" not in outcome:
        raise SystemExit(json.dumps({"status": "prepare_blocked", **outcome}))
    package = json.loads((demo / approval_id / "approval-package.json").read_text())
    now, _, _ = observe(state, package)
    return package, now, "prepared"


def record_approval(directory, state, package, decision_text):
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models.investigation_drafts import DraftRun
    from app.services.ingestion import digest
    from app.services.research_drafts import ResearchDraftService

    demo = directory / "academic-demo"
    folder = demo / package["approval_id"]
    if hashlib.sha256((folder / "request.json").read_bytes()).hexdigest() != package["request_sha256"]:
        raise SystemExit(json.dumps({"status": "stopped", "reason": "request_file_changed"}))
    engine = make_engine(state["database_url"])
    try:
        with Session(engine) as session:
            run = session.get(DraftRun, UUID(package["draft_run_id"]))
            config = ResearchDraftService(engine, Settings(_env_file=None))._configuration(run)
        if digest(config.model_dump(mode="json")) != package["configuration_sha256"]:
            raise SystemExit(json.dumps({"status": "stopped", "reason": "configuration_changed"}))
        record = {
            "decision": "approved",
            "approval_id": package["approval_id"],
            "request_sha256": package["request_sha256"],
            "scope_sha256": package["scope_sha256"],
            "configuration_sha256": package["configuration_sha256"],
            "maximum_input_tokens": config.max_input_tokens,
            "maximum_output_tokens": config.max_output_tokens,
            "timeout_seconds": config.request_deadline_seconds,
            "actor_id": package["actor_id"],
            "case_id": package["case_id"],
            "maximum_requests": 1,
            "automatic_retries": False,
            "synthetic_only": True,
            "application_reservation_usd": package["application_reservation_usd"],
            "expires_second": package["expires_second"],
            "production_publication_authorized": False,
            "general_analyst_generation_authorized": False,
            "owner_decision_reference": "owner-chat-approval-" + package["approval_id"],
            "owner_decision_text": decision_text,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        body = json.dumps(record, indent=1)
        (folder / "owner-approval-record.json").write_text(body)
        temporary = demo / "owner-exact-approval.json.tmp"
        temporary.write_text(body)
        temporary.replace(demo / "owner-exact-approval.json")
        # The worker's own gates, rolled back: exact rebuilt body/hash, scope, configuration,
        # synthetic evidence, source permissions and the clock window. No provider call.
        service = ResearchDraftService(engine, Settings(_env_file=None))
        with Session(engine) as session, session.begin():
            run = session.get(DraftRun, UUID(package["draft_run_id"]))
            granted = service.approved_execution(session, run)
            granted._dispatch_window(session, run)
            session.rollback()
    finally:
        engine.dispose()


def submit_and_verify(directory, state, package):
    import httpx
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.core.database import make_engine
    from app.models.domain import AuditEvent
    from app.models.investigation_drafts import DraftAttempt, DraftReceipt, StoredDraft

    case, run = package["case_id"], package["draft_run_id"]
    password = json.loads((directory / "login.json").read_text())["windowsadmin"]["password"]
    api = f"http://127.0.0.1:{state['api_port']}/api/v1"
    base = f"{api}/cases/{case}/investigation-drafts"
    report = {"approval_id": package["approval_id"], "request_sha256": package["request_sha256"]}
    with httpx.Client(timeout=30, trust_env=False) as http:
        token = http.post(
            f"{api}/auth/token", json={"username": "windowsadmin", "password": password}
        ).json()["access_token"]
        h = {"Authorization": "Bearer " + token}
        if http.get(f"{api}/auth/me", headers=h).json().get("id") != package["actor_id"]:
            raise SystemExit(json.dumps({"status": "stopped", "reason": "actor_mismatch"}))
        cap = http.get(f"{base}/capabilities", headers=h).json()
        if cap.get("research_status") != "approved" or cap.get("research_run_id") != run:
            raise SystemExit(json.dumps({"status": "stopped", "reason": "not_approved_in_app",
                                         "research_status": cap.get("research_status")}))
        # Exactly one submission through the existing button endpoint and idempotency key.
        post = http.post(f"{base}/{run}/execute-research",
                         headers={**h, "Idempotency-Key": f"research-execute-{run}"}, json={})
        report["submitted_http_status"] = post.status_code
        if post.status_code >= 400:
            report["status"] = "stopped"
            report["reason"] = "submission_refused"
            return report
        start = time.monotonic()
        view = {}
        while time.monotonic() - start < 240:
            view = http.get(f"{base}/{run}", headers=h).json()
            if view.get("status") in ("succeeded", "abstained", "failed", "invalidated"):
                break
            time.sleep(2)
        report["elapsed_seconds"] = round(time.monotonic() - start, 1)
        first = http.get(f"{base}/{run}", headers=h).json()
        again = http.get(f"{base}/{run}", headers=h).json()
    draft = first.get("draft") or {}
    report.update(
        status=first.get("status"),
        error_code=first.get("error_code"),
        refresh_stable=first == again,
        regulatory_context=draft.get("regulatory_context"),
        publication_approved=draft.get("publication_approved"),
        verification=draft.get("verification"),
        findings=len(draft.get("findings", [])),
        hypotheses=len(draft.get("hypotheses", [])),
        regulatory_citations=draft.get("regulatory_citations"),
    )
    engine = make_engine(state["database_url"])
    try:
        with Session(engine) as session:
            run_id = UUID(run)
            report["attempts_for_request"] = session.scalar(
                select(func.count()).select_from(DraftAttempt).where(DraftAttempt.run_id == run_id)
            )
            receipt = session.scalar(
                select(DraftReceipt).join(DraftAttempt).where(DraftAttempt.run_id == run_id)
            )
            report["receipt_status"] = receipt.status if receipt else None
            report["stored_result"] = session.scalar(
                select(func.count()).select_from(StoredDraft).where(StoredDraft.run_id == run_id)
            ) == 1
            binding = json.loads(
                (directory / "academic-demo" / package["approval_id"] / "context.json").read_text()
            )["binding_sha256"]
            report["research_citations_verified_event"] = session.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action.endswith("investigation.research_verified"),
                    AuditEvent.details["binding_sha256"].as_string() == binding,
                )
            ) == 1
            if receipt and receipt.usage:
                report["usage"] = {k: receipt.usage.get(k) for k in ("input_tokens", "output_tokens", "cost_usd")}
                diagnostics = receipt.usage.get("diagnostics") or {}
                if diagnostics.get("schema_errors"):
                    report["schema_errors"] = diagnostics["schema_errors"]
    finally:
        engine.dispose()
    (directory / "academic-demo" / package["approval_id"] / "run-report.json").write_text(
        json.dumps(report, indent=1)
    )
    return report


def execute(directory, state, package, decision_text):
    """Shared by both approval paths: gate, record exact approval, preflight, submit once."""
    demo = directory / "academic-demo"
    latest = latest_package(demo)
    now, job, _ = observe(state, package)
    verdict = decide(package, approved_sha256=package["request_sha256"],
                     approval_id=package["approval_id"], now_second=now,
                     latest_id=latest["approval_id"], job=job)
    if verdict != "execute":
        print(json.dumps({"status": "not_sent", "reason": verdict, "approval_recorded": False}, indent=1))
        raise SystemExit(2)
    try:
        record_approval(directory, state, package, decision_text)
    except SystemExit:
        raise
    except Exception as error:  # A worker gate refused: report its code, send nothing.
        print(json.dumps({"status": "not_sent", "reason": "preflight_failed",
                          "code": str(error)[:120], "approval_recorded": True,
                          "note": "approval is bound to this exact hash and cannot authorize another"}))
        raise SystemExit(4) from None
    report = submit_and_verify(directory, state, package)
    print(json.dumps(report, indent=1))
    if report.get("status") not in ("succeeded", "abstained"):
        raise SystemExit(3)


def review(directory, state):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SystemExit(json.dumps({"status": "not_sent", "reason": "interactive_owner_terminal_required"}))
    # The freshness window starts here, when the owner is present to review.
    package, now, _ = prepare(directory, state, force=True)
    request_file = Path(package["full_payload_file"])
    raw = request_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != package["request_sha256"]:
        raise SystemExit(json.dumps({"status": "not_sent", "reason": "request_file_changed"}))
    body = json.loads(raw)
    packet = json.loads(body["messages"][0]["content"])
    info = summary(package, now)
    print("\nEXACT CLAUDE REQUEST FOR OWNER REVIEW (nothing has been sent)\n")
    for label, key in (("Approval ID", "approval_id"), ("Model", "model"),
                       ("Max output tokens", "max_output_tokens"), ("Timeout (s)", "timeout_seconds"),
                       ("Requests / retries", None), ("Reservation (USD)", "reservation_usd"),
                       ("Synthetic only", "synthetic_only"), ("Regulatory sources", None),
                       ("Request bytes", "request_bytes"), ("Full request file", "full_request"),
                       ("Dispatch deadline", "dispatch_deadline")):
        if key:
            value = info[key]
        elif label.startswith("Requests"):
            value = f"{info['maximum_requests']} request, automatic retries: {info['automatic_retries']}"
        else:
            value = f"{info['source_approval']} eCFR sections {', '.join(info['source_sections'])}"
        print(f"  {label:<20} {value}")
    print("  Financial facts      " + "; ".join(
        f"{f['result'].get('observed_total')} {f['result'].get('currency')} over "
        f"{f['result'].get('observed_count')} transactions" for f in packet["financial_facts"]))
    print(f"  Transactions         {len(packet['transactions'])} synthetic records")
    print(f"  Research notice      {packet.get('research_notice')}")
    print(f"\n  REQUEST SHA-256      {package['request_sha256']}\n")
    while True:
        answer = input("Type 'show' to print the full request, the complete SHA-256 above to "
                       "approve and send it once now, or press Enter to cancel: ")
        if answer.strip().lower() == "show":
            print(json.dumps(body, indent=1))
            continue
        break
    if not owner_confirms(answer, package["request_sha256"]):
        print(json.dumps({"status": "not_sent", "reason": "owner_did_not_approve",
                          "approval_recorded": False}))
        raise SystemExit(2)
    decision = (f"Owner typed the complete request SHA-256 {package['request_sha256']} at the "
                f"interactive review prompt for {package['approval_id']}.")
    execute(directory, state, package, decision)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("action", choices=["review", "status", "prepare", "approve-and-run"])
    parser.add_argument("--approval-id")
    parser.add_argument("--request-sha256")
    parser.add_argument("--decision-text")
    args = parser.parse_args()
    directory, state = runtime()
    demo = directory / "academic-demo"
    if args.action == "review":
        review(directory, state)
        return
    if args.action == "status":
        package = latest_package(demo)
        if package is None:
            print(json.dumps({"status": "no_request"}))
            return
        now, job, attempts = observe(state, package)
        print(json.dumps({**summary(package, now), "job": job, "attempts": attempts}, indent=1))
        return
    if args.action == "prepare":
        package, now, how = prepare(directory, state)
        print(json.dumps({"status": "awaiting_explicit_owner_approval", "request": how,
                          **summary(package, now), "live_requests": 0}, indent=1))
        return
    if not (args.approval_id and args.request_sha256 and args.decision_text):
        raise SystemExit("approve-and-run requires --approval-id, --request-sha256, --decision-text")
    package = json.loads((demo / args.approval_id / "approval-package.json").read_text())
    latest = latest_package(demo)
    now, job, _ = observe(state, package)
    verdict = decide(package, approved_sha256=args.request_sha256, approval_id=args.approval_id,
                     now_second=now, latest_id=latest["approval_id"], job=job)
    if verdict != "execute":
        out = {"status": "not_sent", "reason": verdict, "approval_recorded": False}
        if verdict == "expired":
            # Never reuse the old approval: refresh, regenerate and present the new hash.
            fresh, fresh_now, how = prepare(directory, state, force=True)
            out["new_request_for_explicit_approval"] = {**summary(fresh, fresh_now), "request": how}
        print(json.dumps(out, indent=1))
        raise SystemExit(2)
    try:
        record_approval(directory, state, package, args.decision_text)
    except SystemExit:
        raise
    except Exception as error:  # A worker gate refused: report its code, send nothing.
        print(json.dumps({"status": "not_sent", "reason": "preflight_failed",
                          "code": str(error)[:120], "approval_recorded": True,
                          "note": "approval is bound to this exact hash and cannot authorize another"}))
        raise SystemExit(4) from None
    report = submit_and_verify(directory, state, package)
    print(json.dumps(report, indent=1))
    if report.get("status") not in ("succeeded", "abstained"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
