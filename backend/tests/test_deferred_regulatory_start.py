"""Offline admission/worker-boundary tests; these do not claim PostgreSQL acceptance."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.draft_api import DraftStartInput
from app.schemas.investigation_drafts import ProviderConfig
from app.schemas.investigations import InvestigationRequest
from app.schemas.provider_live import (
    RegulatoryQueryClaudeConfig,
    RegulatoryQuerySimulationConfig,
    configuration,
)
from app.schemas.references import ReferenceQuery
from app.services.claude_contract import output_schema
from app.services.draft_api import DraftAPIService
from app.services.evidence import EvidenceBlocked
from app.services.ingestion import digest
from app.services.investigation_drafts import (
    InvestigationDraftService,
    RegulatoryContextUnavailable,
)
from app.services.investigation_verifier import VerificationFailed


def request():
    return InvestigationRequest(
        expected_case_version=1,
        expected_evidence_revision=0,
        expected_access_revision=0,
        without_assessment_reason="not_selected",
        window={
            "start": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 11, 2, tzinfo=timezone.utc),
        },
        currencies=("USD",),
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_start_admits_one_server_owned_parent_child_intent_without_frontend_chaining(enabled):
    gateway = object.__new__(DraftAPIService)
    gateway.settings = SimpleNamespace(regulatory_investigation_enabled=enabled)
    gateway._offline = lambda: None
    gateway.capabilities = lambda: {"provider": "simulation"}
    parent, child = uuid4(), uuid4()
    admitted = []

    def admit(*args):
        admitted.append(args)
        return {"draft_run_id": str(child), "status": "pending", "attempts": 0, "error_code": None}

    gateway.drafts = SimpleNamespace(
        request=SimpleNamespace(__wrapped__=admit),
        _run=lambda *_: SimpleNamespace(parent_run_id=parent),
    )
    body = DraftStartInput(investigation_request=request())
    status = gateway.start.__wrapped__(gateway, object(), uuid4(), uuid4(), "offline-start", body)
    assert status.investigation_run_id == parent and status.draft_run_id == child
    assert len(admitted) == 1
    config = admitted[0][-1]
    assert isinstance(config, RegulatoryQuerySimulationConfig if enabled else ProviderConfig)
    assert (getattr(config, "regulatory_query", None) is not None) is enabled


def test_query_is_versioned_in_configuration_identity_and_survives_serialization():
    first = RegulatoryQuerySimulationConfig(regulatory_query=ReferenceQuery(section="sar"))
    second = first.model_copy(update={"regulatory_query": ReferenceQuery(section="aml")})
    assert configuration(first.model_dump(mode="json")) == first
    assert digest(first.model_dump(mode="json")) != digest(second.model_dump(mode="json"))
    old_grant = first.model_copy(update={"regulatory_authority_sha256": "a" * 64})
    new_grant = first.model_copy(update={"regulatory_authority_sha256": "b" * 64})
    assert digest(old_grant.model_dump(mode="json")) != digest(new_grant.model_dump(mode="json"))


def test_client_query_cannot_enable_disabled_regulatory_integration():
    gateway = object.__new__(DraftAPIService)
    gateway.settings = SimpleNamespace(regulatory_investigation_enabled=False)
    gateway._offline = lambda: None
    gateway.capabilities = lambda: {"provider": "simulation"}
    body = DraftStartInput(
        investigation_request=request(), regulatory_query=ReferenceQuery(section="sar")
    )
    with pytest.raises(EvidenceBlocked, match="regulatory_investigation_disabled"):
        gateway.start.__wrapped__(gateway, object(), uuid4(), uuid4(), "offline-denied", body)


def test_client_cannot_supply_passages_or_source_approval_in_start_contract():
    with pytest.raises(ValidationError):
        DraftStartInput.model_validate(
            {
                "investigation_request": request().model_dump(mode="json"),
                "regulatory_query": {"section": "sar", "passages": [], "approved": True},
            }
        )


def test_development_probe_cannot_gain_deferred_regulatory_scope():
    with pytest.raises(ValidationError):
        RegulatoryQueryClaudeConfig(
            approval_id="claude-development-review-2026-11-22-v2",
            terms_sha256="a" * 64,
            regulatory_query=ReferenceQuery(section="sar"),
            purpose="development_validation",
            financial_scope="development_no_spend_cap_v1",
            wire_format="flat_selection_v2",
            max_cost_usd=0,
            exact_input_sha256="b" * 64,
            wire_schema_sha256=digest(output_schema(wire_format="flat_selection_v2")),
        )


@pytest.mark.parametrize("revision", ["0019_upload_sessions", "0022_claude_development_scope"])
def test_deferred_workflow_fails_closed_without_candidate_database_guard(revision):
    service = object.__new__(InvestigationDraftService)
    config = RegulatoryQuerySimulationConfig(regulatory_query=ReferenceQuery(section="sar"))
    with pytest.raises(EvidenceBlocked, match="deferred_regulatory_schema_required"):
        service._deferred_schema(SimpleNamespace(scalar=lambda _: revision), config)


def service_boundary(monkeypatch, *, existing=False, available=True):
    from app.services import investigation_drafts as module

    service = object.__new__(InvestigationDraftService)
    service.engine = object()
    service.settings = SimpleNamespace(regulatory_investigation_enabled=True)
    config = RegulatoryQuerySimulationConfig(
        regulatory_query=ReferenceQuery(section="sar"), regulatory_authority_sha256="a" * 64
    )
    service._configuration = lambda _: config
    service._deferred_schema = lambda *_: None
    service._regulatory_authority = lambda *_: "a" * 64
    run = SimpleNamespace(
        id=uuid4(), actor_id=uuid4(), parent_run_id=uuid4(), manifest_sha256="a" * 64
    )
    case = uuid4()
    service.coordinator = SimpleNamespace(_run=lambda *_: SimpleNamespace(case_id=case))
    calls = []
    service._event = lambda *_args, **_kwargs: calls.append("audit")
    service._grounding = lambda *_: calls.append("reuse")
    binding = SimpleNamespace(
        case_id=case,
        binding_sha256="b" * 64,
        grounding=object() if available else None,
        result=SimpleNamespace(
            status="available" if available else "unavailable", passages=[object()]
        ),
        model_dump=lambda **_: {"query": config.regulatory_query.model_dump(mode="json")},
    )
    fake_bridge = SimpleNamespace(
        prepare=SimpleNamespace(__wrapped__=lambda *_: calls.append("retrieve") or binding),
        provider_input=SimpleNamespace(__wrapped__=lambda *_: calls.append("validate")),
    )
    monkeypatch.setattr(module, "RegulatoryInvestigationService", lambda *_: fake_bridge)
    session = SimpleNamespace(
        get=lambda *_: object() if existing else None,
        scalar=lambda *_: None,
        add=lambda _: calls.append("store"),
        flush=lambda: calls.append("flush"),
    )
    return service, session, run, calls


def test_worker_freezes_and_validates_context_before_storing_binding(monkeypatch):
    service, session, run, calls = service_boundary(monkeypatch)
    service._prepare_regulatory_context(session, run)
    assert calls == ["retrieve", "validate", "store", "flush", "audit"]


def test_retry_reuses_frozen_binding_without_retrieval_or_expiry_renewal(monkeypatch):
    service, session, run, calls = service_boundary(monkeypatch, existing=True)
    service._prepare_regulatory_context(session, run)
    assert calls == ["reuse"]


def test_missing_approved_context_stops_before_binding_or_provider_reservation(monkeypatch):
    service, session, run, calls = service_boundary(monkeypatch, available=False)
    with pytest.raises(RegulatoryContextUnavailable):
        service._prepare_regulatory_context(session, run)
    assert calls == ["retrieve"]


def test_no_rebinding_after_an_existing_attempt(monkeypatch):
    service, session, run, calls = service_boundary(monkeypatch)
    session.scalar = lambda *_: uuid4()
    with pytest.raises(VerificationFailed):
        service._prepare_regulatory_context(session, run)
    assert calls == []


def test_changed_admission_authority_stops_before_retrieval(monkeypatch):
    service, session, run, calls = service_boundary(monkeypatch)
    service._regulatory_authority = lambda *_: "c" * 64
    with pytest.raises(VerificationFailed, match="regulatory_authority_changed"):
        service._prepare_regulatory_context(session, run)
    assert calls == []


def test_permission_or_database_failure_does_not_store_unvalidated_context(monkeypatch):
    from app.services import investigation_drafts as module

    service, session, run, calls = service_boundary(monkeypatch)

    def reject(*_):
        raise EvidenceBlocked("official_source_review_required")

    monkeypatch.setattr(
        module,
        "RegulatoryInvestigationService",
        lambda *_: SimpleNamespace(prepare=SimpleNamespace(__wrapped__=reject)),
    )
    with pytest.raises(EvidenceBlocked):
        service._prepare_regulatory_context(session, run)
    assert calls == []


@pytest.mark.parametrize(
    "system,kernel", [("Windows", "10"), ("Linux", "6.6-microsoft-standard-WSL2")]
)
def test_native_acceptance_helper_refuses_windows_and_wsl_before_credentials(system, kernel):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/native_regulatory_acceptance.py"
    spec = importlib.util.spec_from_file_location("native_regulatory_guard_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match="independent_native_linux_required"):
        module.native_linux(system, kernel)


def test_worker_parser_preserves_grounded_selection_contract_for_deferred_intent():
    from app.schemas.investigation_drafts import ProviderReply, Usage
    from app.schemas.regulatory_investigation import GroundedSimulationProposal
    from app.services.investigation_draft_verifier import parse_proposal

    config = RegulatoryQuerySimulationConfig(regulatory_query=ReferenceQuery(section="sar"))
    proposal = GroundedSimulationProposal(
        packet_sha256="a" * 64,
        findings=[],
        hypotheses=[],
        questions=[],
        unresolved_questions=[],
        next_steps=["human_review"],
        abstain=True,
        uncertainty="requires_human_semantic_review",
        regulatory_binding_sha256="b" * 64,
        regulatory_citations=[uuid4()],
    )
    reply = ProviderReply(
        content=proposal.model_dump_json(),
        finish_reason="complete",
        provider="deterministic_fake",
        model="trueflag-fake-selection.v1",
        usage=Usage(
            input_tokens=10,
            output_tokens=10,
            cost_usd=0,
            basis="simulated_utf8_byte_units_not_vendor_tokens",
        ),
    )
    assert parse_proposal(reply, config) == proposal


def test_native_acceptance_reports_skips_as_incomplete(tmp_path):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/native_regulatory_acceptance.py"
    spec = importlib.util.spec_from_file_location("native_regulatory_counts_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite><testcase name="pass"/>'
        '<testcase name="skip"><skipped/></testcase>'
        '<testcase name="fail"><failure/></testcase>'
        '<testcase name="error"><error/></testcase></testsuite></testsuites>'
    )
    assert module.required_test_counts(report) == dict(total=4, skipped=1, failed=1, errors=1)
