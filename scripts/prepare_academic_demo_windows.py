"""Native synthetic onboarding / research request preparation. Never sends paid requests."""

import argparse
import hashlib
import json
import os
import sys
import time
from uuid import UUID

import httpx
from windows_runtime import ROOT, clean_env, connection, current, write


def save(path, value):
    temporary = path.with_suffix(".new.json")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
    temporary.replace(path)


def install_research_scope(directory, state, actor, cases):
    private = directory / "academic-demo"
    scopefile = private / "research-scope.json"
    proposal_sha = hashlib.sha256(
        (ROOT / "contracts/regulatory_source_proposals.json").read_bytes()
    ).hexdigest()
    if proposal_sha != "832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1":
        raise RuntimeError("source_proposal_identity_changed")
    if not scopefile.exists():
        with connection(state) as c:
            cluster = c.execute(
                "SELECT system_identifier::text FROM pg_control_system()"
            ).fetchone()[0]
        from sqlalchemy.engine import make_url

        write(
            scopefile,
            {
                "purpose": "academic_research_unapproved_v1",
                "database": make_url(state["database_url"]).database,
                "cluster_id": cluster,
                "source_proposal_sha256": proposal_sha,
                "as_of": "2026-11-02",
                "actors": [str(actor)],
                "cases": list(cases.values()),
                "production_publication_authorized": False,
                "authority": "Owner requested isolated academic research mode; not a regulatory approval or paid-request approval.",
            },
        )
    state["research"] = {
        "scope_file": str(scopefile),
        "scope_sha256": hashlib.sha256(scopefile.read_bytes()).hexdigest(),
        "approval_file": str(private / "owner-exact-approval.json"),
    }
    save(directory / "state.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cases", "request"])
    parser.add_argument("--approval-id", default="academic-claude-research-review-2026-11-23-v1")
    args = parser.parse_args()
    directory, state = current()
    with connection(state):
        pass  # Verify native cluster/data directory before any application writes.
    private = directory / "academic-demo"
    private.mkdir(exist_ok=True)
    receiptfile = private / "onboarding.json"
    receipt = json.loads(receiptfile.read_text()) if receiptfile.exists() else {}
    os.environ.update(clean_env(state))
    sys.path.insert(0, os.environ["PYTHONPATH"])
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.services.synthetic_demo_cases import SyntheticDemoEvidenceService

    engine = make_engine(state["database_url"])
    logins = json.loads((directory / "login.json").read_text())
    with httpx.Client(
        base_url=f"http://127.0.0.1:{state['api_port']}", trust_env=False, timeout=45
    ) as client:

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                raise RuntimeError("local_api_http_" + str(response.status_code))
            return response.json()

        token = call(
            "POST",
            "/api/v1/auth/token",
            json={"username": "windowsadmin", "password": logins["windowsadmin"]["password"]},
        )
        client.headers["Authorization"] = "Bearer " + token["access_token"]
        me = call("GET", "/api/v1/auth/me")
        actor = UUID(me["id"])
        if args.action == "cases":
            workspace = call("GET", "/api/v1/upload-sessions")
            active = workspace["active"]
            if not active or not active["can_upload"]:
                raise RuntimeError("select_an_authorized_upload_session_before_preparation")
            if receipt.get("session_id") not in (None, active["id"]):
                raise RuntimeError("upload_session_changed_preserving_previous_demo")
            receipt["session_id"] = active["id"]
            save(receiptfile, receipt)
            if "upload_id" not in receipt:
                uploaded = call(
                    "POST",
                    "/api/v1/batch-uploads",
                    content=(
                        ROOT / "runtime/investigation-demo-20261120-v1/investigation-demo.csv"
                    ).read_bytes(),
                    headers={
                        "Content-Type": "text/csv",
                        "Idempotency-Key": "academic-demo-upload-" + active["id"],
                        "X-Upload-Session-ID": active["id"],
                    },
                )
                receipt["upload_id"] = uploaded["upload_id"]
                save(receiptfile, receipt)
            upload = receipt["upload_id"]
            if "preview" not in receipt:
                receipt["preview"] = call(
                    "POST",
                    f"/api/v1/batch-uploads/{upload}/validations",
                    json={"units": "baseline_source_units"},
                )
                save(receiptfile, receipt)
            preview = receipt["preview"]
            if (preview["total_rows"], preview["valid_rows"], preview["invalid_rows"]) != (3, 3, 0):
                raise RuntimeError("expected_three_valid_demo_rows")
            if "import_id" not in receipt:
                approval = {
                    key: preview[key]
                    for key in (
                        "upload_sha256",
                        "mapping_sha256",
                        "mapping_version",
                        "validator_version",
                        "units",
                    )
                }
                approval.update(approve_valid_rows=True, validation_version=preview["version"])
                imported = call(
                    "POST",
                    f"/api/v1/batch-uploads/{upload}/validations/{preview['validation_id']}/imports",
                    json=approval,
                    headers={"Idempotency-Key": "academic-demo-import-" + active["id"]},
                )
                receipt["import_id"] = imported["import_id"]
                save(receiptfile, receipt)
            identifier = receipt["import_id"]
            for _ in range(45):
                imported = call("GET", f"/api/v1/batch-imports/{identifier}")
                if imported["status"] in ("completed", "partially_completed", "failed"):
                    break
                time.sleep(2)
            if imported["status"] != "completed":
                raise RuntimeError("import_not_completed")
            rows = call("GET", f"/api/v1/batch-imports/{identifier}/rows?limit=10")["items"]
            if len(rows) != 3 or any(r["status"] not in ("created", "reused") for r in rows):
                raise RuntimeError("unexpected_import_rows")
            cases = dict(
                zip(
                    ("priority", "ordinary", "incomplete"),
                    (r["case_id"] for r in sorted(rows, key=lambda r: r["row_number"])),
                    strict=True,
                )
            )
            receipt["cases"] = cases
            save(receiptfile, receipt)
            service = SyntheticDemoEvidenceService(engine)
            receipt["evidence"] = [
                service.attach_uploaded_case(actor, UUID(case), key) for key, case in cases.items()
            ]
            save(receiptfile, receipt)
            if "batch_id" not in receipt:
                batch = call(
                    "POST",
                    f"/api/v1/batch-imports/{identifier}/assessments",
                    json={
                        "start_assessment": True,
                        "import_validation_sha256": imported["validation_sha256"],
                        "policy": "Balanced",
                    },
                    headers={"Idempotency-Key": "academic-demo-assess-" + active["id"]},
                )
                receipt["batch_id"] = batch["batch_id"]
                save(receiptfile, receipt)
            for _ in range(60):
                batch = call("GET", f"/api/v1/batch-assessments/{receipt['batch_id']}")
                if batch["status"] in ("completed", "partially_completed", "failed", "stopped"):
                    break
                time.sleep(2)
            receipt["assessment_status"] = batch["status"]
            save(receiptfile, receipt)
            if batch["status"] == "completed":
                install_research_scope(directory, state, actor, cases)
            print(
                json.dumps(
                    {
                        "cases": cases,
                        "assessment_status": batch["status"],
                        "succeeded": batch["succeeded"],
                        "failed": batch["failed_manual_review"],
                        "live_requests": 0,
                    }
                )
            )
            return
        if not receipt.get("cases") or receipt.get("assessment_status") != "completed":
            raise RuntimeError("complete_native_case_preparation_first")
        from app.schemas.investigations import InvestigationRequest
        from app.schemas.references import ReferenceQuery
        from app.schemas.research_demo import ResearchClaudeConfig
        from app.services.claude_contract import output_schema, request_body
        from app.services.ingestion import digest
        from app.services.investigation_coordinator import InvestigationCoordinator
        from app.services.research_demo import PROPOSAL_SHA, ResearchEvidenceService
        from app.services.research_drafts import ResearchDraftService
        from app.services.synthetic_demo_cases import demo_bundle

        case = UUID(receipt["cases"]["priority"])
        scopefile = private / "research-scope.json"
        if not scopefile.exists():
            with connection(state) as c:
                cluster = c.execute(
                    "SELECT system_identifier::text FROM pg_control_system()"
                ).fetchone()[0]
            from sqlalchemy.engine import make_url

            write(
                scopefile,
                {
                    "purpose": "academic_research_unapproved_v1",
                    "database": make_url(state["database_url"]).database,
                    "cluster_id": cluster,
                    "source_proposal_sha256": PROPOSAL_SHA,
                    "as_of": "2026-11-02",
                    "actors": [str(actor)],
                    "cases": list(receipt["cases"].values()),
                    "production_publication_authorized": False,
                    "authority": "Owner requested isolated academic research mode; not a regulatory approval or paid-request approval.",
                },
            )
        scope_sha = hashlib.sha256(scopefile.read_bytes()).hexdigest()
        settings = Settings(
            _env_file=None,
            academic_research_enabled=True,
            academic_research_scope_file=scopefile,
            academic_research_scope_sha256=scope_sha,
            academic_research_approval_file=private / "owner-exact-approval.json",
            anthropic_synthetic_demo_enabled=True,
        )
        coordinator = InvestigationCoordinator(engine, settings)
        context = coordinator.reader.get_case_context(actor, case)
        history = call("GET", f"/api/v1/cases/{case}/assessments?limit=1")
        assessment = history["items"][0]["assessment_id"]
        bundle = demo_bundle("priority")
        request = InvestigationRequest(
            expected_case_version=context.snapshot.case_version,
            expected_evidence_revision=context.snapshot.evidence_revision,
            expected_access_revision=context.snapshot.access_revision,
            assessment_id=UUID(assessment),
            without_assessment_reason=None,
            window={"start": bundle.window_start, "end": bundle.as_of},
            currencies=("USD",),
        )
        parent = coordinator.request(actor, case, "parent-" + args.approval_id, request)
        run = UUID(parent["run_id"])
        for _ in range(30):
            view = coordinator.get(actor, case, run)
            if view["status"] in ("succeeded", "abstained", "failed", "invalidated"):
                break
            time.sleep(1)
        if view["status"] not in ("succeeded", "abstained"):
            raise RuntimeError("verified_packet_not_ready")
        research = ResearchEvidenceService(engine, settings)
        binding = research.prepare(
            actor, case, run, ReferenceQuery(query="suspicious transactions")
        )
        packet = research.provider_input(actor, binding)
        termsfile = ROOT / "runtime/claude-demo-20261120/anthropic_public_terms_snapshot.json"
        terms_sha = hashlib.sha256(termsfile.read_bytes()).hexdigest()
        approval_id = args.approval_id
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{12,100}", approval_id):
            raise RuntimeError("bounded_approval_identity_required")
        config = ResearchClaudeConfig(
            approval_id=approval_id,
            terms_sha256=terms_sha,
            research_binding_sha256=binding.binding_sha256,
            research_scope_sha256=scope_sha,
            exact_input_sha256=digest(packet.model_dump(mode="json")),
            wire_schema_sha256=digest(
                output_schema(grounded=True, wire_format="flat_selection_v2")
            ),
            max_cost_usd="2.14",
        )
        draft = ResearchDraftService(engine, settings).stage(
            actor, case, "draft-" + approval_id, request, binding, config
        )
        raw = request_body(
            packet,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        output = private / approval_id
        output.mkdir(exist_ok=False)
        (output / "request.json").write_bytes(raw)
        write(output / "context.json", binding.model_dump(mode="json"))
        write(output / "configuration.json", config.model_dump(mode="json"))
        request_sha = hashlib.sha256(raw).hexdigest()
        write(
            output / "approval-package.json",
            {
                "status": "awaiting_explicit_owner_approval",
                "approval_id": approval_id,
                "request_sha256": request_sha,
                "request_bytes": len(raw),
                "endpoint": "https://api.anthropic.com/v1/messages",
                "model": config.model,
                "maximum_requests": 1,
                "automatic_retries": False,
                "synthetic_only": True,
                "max_input_tokens": config.max_input_tokens,
                "max_output_tokens": config.max_output_tokens,
                "timeout_seconds": config.request_deadline_seconds,
                "application_reservation_usd": str(config.max_cost_usd),
                "provider_invoice_guaranteed": False,
                "scope_sha256": scope_sha,
                "configuration_sha256": digest(config.model_dump(mode="json")),
                "terms_snapshot_sha256": terms_sha,
                "actor_id": str(actor),
                "case_id": str(case),
                "draft_run_id": draft["draft_run_id"],
                "packet_run_id": str(run),
                "expires_second": binding.expires_second,
                "source_approval": "UNAPPROVED_RESEARCH",
                "full_payload_file": str(output / "request.json"),
                "source_sections": [p.section for p in binding.passages],
                "live_requests": 0,
            },
        )
        state["research"] = {
            "scope_file": str(scopefile),
            "scope_sha256": scope_sha,
            "approval_file": str(settings.academic_research_approval_file),
        }
        save(directory / "state.json", state)
        print(
            json.dumps(
                {
                    "approval_package": str(output / "approval-package.json"),
                    "request_sha256": request_sha,
                    "request_bytes": len(raw),
                    "case_id": str(case),
                    "draft_run_id": draft["draft_run_id"],
                    "live_requests": 0,
                }
            )
        )
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(error).__name__,
                    "code": str(error) if isinstance(error, RuntimeError) else "details_withheld",
                }
            )
        )
        raise SystemExit(1) from None
