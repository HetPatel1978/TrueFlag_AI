"""One approved academic attempt through existing jobs/ledger. Defaults to non-billable preflight."""

import argparse
import hashlib
import json
import os
import re
import sys
from uuid import UUID

from windows_runtime import ROOT, clean_env, connection, current, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,100}", args.approval_id) or not re.fullmatch(
        r"[a-f0-9]{64}", args.request_sha256
    ):
        raise ValueError("exact_approval_identity_required")
    directory, state = current()
    with connection(state):
        pass
    package = directory / "academic-demo" / args.approval_id
    raw = (package / "request.json").read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != args.request_sha256:
        raise ValueError("saved_request_changed")
    review = json.loads((package / "approval-package.json").read_text())
    if review["approval_id"] != args.approval_id or review["request_sha256"] != args.request_sha256:
        raise ValueError("saved_approval_scope_changed")
    if not state.get("research"):
        raise ValueError("native_research_scope_unavailable")
    os.environ.update(clean_env(state))
    sys.path.insert(0, os.environ["PYTHONPATH"])
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models.investigation_drafts import DraftAttempt, DraftRun
    from app.schemas.research_demo import ResearchClaudeConfig
    from app.services.ingestion import digest
    from app.services.research_drafts import ResearchDraftService
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    config = ResearchClaudeConfig.model_validate_json((package / "configuration.json").read_text())
    if digest(config.model_dump(mode="json")) != review["configuration_sha256"]:
        raise ValueError("configuration_changed")
    settings = Settings(
        _env_file=None,
        anthropic_research_dispatch_enabled=True,
        anthropic_research_approval_id=args.approval_id,
        anthropic_research_input_sha256=config.exact_input_sha256,
        anthropic_research_request_sha256=args.request_sha256,
        anthropic_terms_sha256=config.terms_sha256,
        academic_research_response_file=package / "http-response.json",
    )
    if settings.academic_research_response_file.exists():
        raise ValueError("response_capture_already_exists_no_retry")
    engine = make_engine(state["database_url"])
    service = ResearchDraftService(engine, settings)
    with Session(engine) as session, session.begin():
        service.coordinator._gate(session)
        run = service._run(session, UUID(review["draft_run_id"]))
        if service._configuration(run) != config:
            raise ValueError("stored_configuration_changed")
        service._approved_request(session, run)
        used = session.scalar(
            select(func.count())
            .select_from(DraftAttempt)
            .join(DraftRun)
            .where(DraftRun.configuration["approval_id"].as_string() == args.approval_id)
        )
        if used:
            raise ValueError("approval_already_consumed")
    if not args.execute:
        print(
            json.dumps(
                {
                    "preflight": "passed",
                    "paid_request_sent": False,
                    "request_sha256": args.request_sha256,
                }
            )
        )
        return
    # Credential is read only after exact owner/scope/source/clock checks; never printed.
    from dotenv import dotenv_values
    from pydantic import SecretStr

    credential = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY")
    if not credential:
        raise ValueError("provider_key_missing")
    settings.anthropic_api_key = SecretStr(credential)
    result = service.run_once(state["evidence_token"])  # One call; no loop or automatic retry.
    record = {
        "approval_id": args.approval_id,
        "request_sha256": args.request_sha256,
        "result": result,
        "general_analyst_generation_enabled": False,
        "production_source_publication": False,
    }
    if settings.academic_research_response_file.exists():
        captured = json.loads(settings.academic_research_response_file.read_text())
        record["http_status"] = captured["http_status"]
        record["sanitized_response_file"] = str(settings.academic_research_response_file)
    with Session(engine) as session:
        from app.models.investigation_drafts import DraftReceipt

        attempts = session.scalars(
            select(DraftAttempt).where(DraftAttempt.run_id == UUID(review["draft_run_id"]))
        ).all()
        record["attempts"] = len(attempts)
        if attempts:
            receipt = session.scalar(
                select(DraftReceipt).where(DraftReceipt.attempt_id == attempts[0].id)
            )
            record["receipt"] = (
                None
                if receipt is None
                else {
                    "status": receipt.status,
                    "elapsed_ms": receipt.elapsed_ms,
                    "usage": receipt.usage,
                }
            )
    write(package / "execution-result.json", record)
    print(json.dumps(record))
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
                    "paid_request_not_retried": True,
                }
            )
        )
        raise SystemExit(1) from None
