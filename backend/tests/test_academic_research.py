"""Native PostgreSQL academic boundary. Mock HTTP results never establish live acceptance."""

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from test_claude_development_postgres import reply as financial_reply
from test_foundation import headers
from test_investigation_coordinator import env as evidence_env
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import evidence_setup as evidence_fixture

from app.models import Case, User
from app.models.investigation_drafts import DraftAttempt, DraftJob, DraftReceipt, StoredDraft
from app.models.references import CorpusRelease, ReferenceApproval
from app.schemas.draft_api import DraftDetail
from app.schemas.references import ReferenceQuery
from app.schemas.regulatory_investigation import GroundedAIProposal, InvestigationRegulatoryContext
from app.schemas.research_demo import ResearchClaudeConfig
from app.services.claude_contract import output_schema, request_body
from app.services.claude_provider import ClaudeProvider
from app.services.evidence import EvidenceBlocked, EvidenceNotFound, EvidenceUnavailable
from app.services.evidence_read import SnapshotStale
from app.services.ingestion import digest
from app.services.investigation_verifier import VerificationFailed
from app.services.luminal_provider import ProviderRejected
from app.services.research_api import ResearchDraftAPIService
from app.services.research_demo import PROPOSAL_SHA, ResearchEvidenceService
from app.services.research_drafts import ResearchDraftService

env = evidence_env
evidence_setup = evidence_fixture
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        sys.platform != "win32" or not os.environ.get("TRUEFLAG_TEST_POSTGRES_URL"),
        reason="isolated native Windows PostgreSQL required",
    ),
    # Research tables come from candidate migrations 0020-0023, which only the native
    # runtime's staged copy applies. Run with scripts/run_staged_tests.py.
    pytest.mark.skipif(
        not (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0023_durable_regulatory_start.py"
        ).exists(),
        reason="Needs the staged 0020-0023 chain; run scripts/run_staged_tests.py",
    ),
]


@pytest.fixture
def research(env, tmp_path):
    e = env
    settings = e["platform"][2]
    engine = e["platform"][1]
    settings.app_env = "test"
    actor, case = e["users"]["admin"], e["case"]
    private = tmp_path / "runtime/windows-native/research"
    private.mkdir(parents=True)
    with engine.connect() as c:
        db, cluster = c.execute(
            text("SELECT current_database(),system_identifier::text FROM pg_control_system()")
        ).one()
    scope = {
        "purpose": "academic_research_unapproved_v1",
        "production_publication_authorized": False,
        "as_of": "2026-11-02",
        "source_proposal_sha256": PROPOSAL_SHA,
        "database": db,
        "cluster_id": cluster,
        "actors": [str(actor)],
        "cases": [str(case)],
    }
    raw = json.dumps(scope).encode()
    scopefile = private / "scope.json"
    scopefile.write_bytes(raw)
    settings.academic_research_enabled = True
    settings.academic_research_scope_file = scopefile
    settings.academic_research_scope_sha256 = hashlib.sha256(raw).hexdigest()
    settings.academic_research_approval_file = private / "approval.json"
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_contract_verified = False
    settings.anthropic_api_key = SecretStr("offline-test-placeholder")
    settings.anthropic_terms_sha256 = "a" * 64
    request = packet_request(e)
    parent = e["service"].request(actor, case, "research-parent-key", request)
    result = e["service"].run_once(e["token"])
    assert result["status"] == "succeeded", result
    bridge = ResearchEvidenceService(engine, settings)
    binding = bridge.prepare(
        actor,
        case,
        UUID(parent["run_id"]),
        ReferenceQuery(query="suspicious transactions"),
    )
    packet = bridge.provider_input(actor, binding)
    config = ResearchClaudeConfig(
        approval_id="research-offline-" + uuid4().hex,
        terms_sha256="a" * 64,
        research_binding_sha256=binding.binding_sha256,
        research_scope_sha256=binding.scope_sha256,
        exact_input_sha256=digest(packet.model_dump(mode="json")),
        wire_schema_sha256=digest(output_schema(grounded=True, wire_format="flat_selection_v2")),
        max_cost_usd="2.14",
    )
    service = ResearchDraftService(engine, settings)
    e.update(
        actor=actor,
        bridge=bridge,
        binding=binding,
        packet=packet,
        config=config,
        research=service,
        request=request,
    )
    return e


def stage(e, key="research-draft-key"):
    return e["research"].stage(e["actor"], e["case"], key, e["request"], e["binding"], e["config"])


def approve_fixture(e):
    """Synthetic test approval only, confined to disposable schema and temp directory."""
    settings = e["platform"][2]
    config = e["config"]
    raw = request_body(
        e["packet"], max_output_tokens=config.max_output_tokens, wire_format=config.wire_format
    )
    request_sha = hashlib.sha256(raw).hexdigest()
    record = {
        "decision": "approved",
        "approval_id": config.approval_id,
        "request_sha256": request_sha,
        "scope_sha256": config.research_scope_sha256,
        "configuration_sha256": digest(config.model_dump(mode="json")),
        "maximum_input_tokens": config.max_input_tokens,
        "maximum_output_tokens": config.max_output_tokens,
        "timeout_seconds": config.request_deadline_seconds,
        "actor_id": str(e["actor"]),
        "case_id": str(e["case"]),
        "maximum_requests": 1,
        "automatic_retries": False,
        "synthetic_only": True,
        "owner_decision_reference": "SYNTHETIC_TEST_ONLY_NOT_REAL_OWNER_APPROVAL",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    settings.academic_research_approval_file.write_text(json.dumps(record))
    settings.anthropic_research_dispatch_enabled = True
    settings.anthropic_research_approval_id = config.approval_id
    settings.anthropic_research_input_sha256 = config.exact_input_sha256
    settings.anthropic_research_request_sha256 = request_sha


def response(e, tamper=None):
    reply = financial_reply(
        e["packet"], e["config"], tamper if tamper in ("amount", "reference") else None
    )
    value = json.loads(reply.content)
    value.update(
        regulatory_binding_sha256=e["binding"].binding_sha256,
        regulatory_citations=[str(p.reference_id) for p in e["binding"].passages],
    )
    if tamper == "citation":
        value["regulatory_citations"] = [str(uuid4())]
    if tamper == "question":  # V10: a missing-evidence code is not a supplied question.
        value["additional_information_needed"] = ["comparable_expected_activity"]
    if tamper in ("link", "bad_link"):  # flat_selection_v3 per-finding source links
        from app.schemas.research_demo import ResearchAIProposal

        finding = next(
            f["reference_id"]
            for group in ("financial_observations", "unusual_activity", "model_signals")
            for f in value[group]
        )
        source = value["regulatory_citations"][0] if tamper == "link" else str(uuid4())
        value["finding_citations"] = [
            {"finding_reference_id": finding, "regulatory_citation": source}
        ]
        return reply.model_copy(
            update={"content": ResearchAIProposal.model_validate(value).model_dump_json()}
        )
    return reply.model_copy(
        update={"content": GroundedAIProposal.model_validate(value).model_dump_json()}
    )


def test_real_retrieval_has_complete_verified_text_without_approval(research):
    e = research
    b = e["binding"]
    assert b.passages and all(p.approval_status == "unapproved_research" for p in b.passages)
    assert all(hashlib.sha256(p.text.encode()).hexdigest() == p.text_sha256 for p in b.passages)
    assert all(p.source_key == "ecfr-us-banks" for p in b.passages)
    with pytest.raises(ValidationError):
        InvestigationRegulatoryContext.model_validate(b.model_dump())
    with Session(e["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(ReferenceApproval)) == 0
        assert s.scalar(select(func.count()).select_from(CorpusRelease)) == 0


def test_missing_approval_never_claims_or_reserves(research):
    e = research
    stage(e)
    assert e["research"].run_once(e["token"]) is None
    claim = e["research"].claim(e["token"])
    assert claim
    with pytest.raises(EvidenceBlocked, match="research_exact_approval_required"):
        e["research"].prepare(e["token"], claim)
    with Session(e["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_research_request_constrains_question_fields_to_supplied_questions(research):
    e = research
    raw = json.loads(
        request_body(e["packet"], max_output_tokens=4096, wire_format="flat_selection_v2")
    )
    props = raw["output_config"]["format"]["schema"]["properties"]
    assert e["packet"].questions
    for field in ("follow_up_questions", "additional_information_needed"):
        assert props[field]["items"]["enum"] == list(dict.fromkeys(e["packet"].questions))
    assert "never missing evidence codes" in raw["system"]


@pytest.mark.parametrize("tamper", [None, "amount", "reference", "citation", "question"])
def test_atomic_worker_verification_and_refresh(research, tamper):
    e = research
    receipt = stage(e)
    approve_fixture(e)

    class Runner:
        def invoke(self, *args):
            return response(e, tamper)

    e["research"]._runner = Runner()
    result = e["research"].run_once(e["token"])
    assert result["status"] == ("succeeded" if tamper is None else "failed"), result
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    first = gateway.detail(e["actor"], e["case"], UUID(receipt["draft_run_id"]))
    again = gateway.detail(e["actor"], e["case"], UUID(receipt["draft_run_id"]))
    assert first == again
    with Session(e["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(StoredDraft)) == (tamper is None)
        assert s.get(Case, e["case"]).status == "open"
    if tamper is None:
        assert first.draft.regulatory_context == "research_unapproved"
        assert first.draft.publication_approved is False
        assert DraftDetail.model_validate_json(first.model_dump_json()) == first


def test_idempotent_stage_and_binding_immutability(research):
    e = research
    assert stage(e) == stage(e)
    with pytest.raises(Exception):
        with e["platform"][1].begin() as c:
            c.execute(text("UPDATE draft_regulatory_bindings SET body=body"))


@pytest.mark.parametrize(
    "change",
    [
        "disabled",
        "production",
        "wrong_case",
        "wrong_actor",
        "scope_tamper",
        "epoch",
        "expired",
        "source_tamper",
        "passage_tamper",
    ],
)
def test_fail_closed_research_scope_and_source(research, monkeypatch, change):
    e = research
    settings = e["platform"][2]
    binding = e["binding"]
    if change == "disabled":
        settings.academic_research_enabled = False
    if change == "production":
        settings.app_env = "production"
    if change == "wrong_case":
        binding = binding.model_copy(update={"case_id": uuid4()})
    if change == "wrong_actor":
        with pytest.raises((EvidenceBlocked, EvidenceNotFound, VerificationFailed)):
            e["bridge"].provider_input(e["users"]["analyst"], binding)
        return
    if change == "scope_tamper":
        settings.academic_research_scope_file.write_text("{}")
    if change in ("epoch", "expired", "passage_tamper"):
        binding = binding.model_copy(
            update={"clock_epoch": binding.clock_epoch + 1}
            if change == "epoch"
            else {"passages": binding.passages[:-1]}
            if change == "passage_tamper"
            else {
                "prepared_second": binding.prepared_second - 901,
                "expires_second": binding.expires_second - 901,
            }
        )
        binding = binding.model_copy(
            update={
                "binding_sha256": digest(
                    binding.model_dump(mode="json", exclude={"binding_sha256"})
                )
            }
        )
    if change == "source_tamper":
        monkeypatch.setattr(
            e["bridge"],
            "_catalog",
            lambda: (_ for _ in ()).throw(EvidenceBlocked("research_source_changed")),
        )
    if change in ("epoch", "expired"):
        # Genuine lifecycle expiry is retirable staleness, never a tamper finding.
        with pytest.raises(SnapshotStale, match="research_context_expired"):
            e["bridge"].provider_input(e["actor"], binding)
        return
    if change == "passage_tamper":
        with pytest.raises(VerificationFailed, match="research_context_invalidated"):
            e["bridge"].provider_input(e["actor"], binding)
        return
    with pytest.raises((EvidenceBlocked, EvidenceNotFound, VerificationFailed)):
        e["bridge"].provider_input(e["actor"], binding)


def test_claude_exact_body_gate_precedes_offline_transport(research):
    e = research
    calls = []

    def handler(request):
        calls.append(True)
        return httpx.Response(
            400,
            stream=httpx.ByteStream(
                b'{"error":{"type":"invalid_request_error","message":"offline fixture"}}'
            ),
            headers={"content-type": "application/json"},
        )

    adapter = ClaudeProvider(e["platform"][2], transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderRejected):
        adapter.propose(e["packet"], e["config"])
    assert calls == []
    approve_fixture(e)
    e["platform"][2].anthropic_research_request_sha256 = "0" * 64
    with pytest.raises(ProviderRejected):
        adapter.propose(e["packet"], e["config"])
    assert calls == []
    raw = request_body(
        e["packet"],
        max_output_tokens=e["config"].max_output_tokens,
        wire_format="flat_selection_v2",
    )
    e["platform"][2].anthropic_research_request_sha256 = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ProviderRejected) as error:
        adapter.propose(e["packet"], e["config"])
    assert error.value.http_status == 400 and len(calls) == 1


def test_research_http_is_scoped_and_refresh_safe(research):
    e = research
    stage(e)
    client = e["platform"][0]
    base = f"/api/v1/cases/{e['case']}/investigation-drafts/research-context/latest"
    assert client.get(base).status_code == 401
    auth = headers(e["platform"], "admin")
    first = client.get(base, headers=auth)
    again = client.get(base, headers=auth)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert first.json()["publication_approved"] is False
    assert client.get(base, headers=headers(e["platform"], "analyst")).status_code in (403, 404)
    e["platform"][2].academic_research_enabled = False
    assert client.get(base, headers=auth).status_code == 404


def test_expired_dispatch_binding_keeps_public_research_readable(research, monkeypatch):
    from app.services.snapshot_clock import ClockObservation, SnapshotTime

    e = research
    stage(e)
    observed = SnapshotTime.observe

    def future(clock):
        current = observed(clock)
        return ClockObservation(max(current.second, e["binding"].expires_second + 1), current.epoch)

    monkeypatch.setattr(SnapshotTime, "observe", future)
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    result = gateway.context(e["actor"], e["case"])
    assert result["status"] == "research_unapproved" and result["passages"]
    assert result["dispatch_binding_status"] == "expired"
    assert result["authorizes_dispatch"] is False
    with pytest.raises(SnapshotStale, match="research_context_expired"):
        e["bridge"].provider_input(e["actor"], e["binding"])
    assert gateway.case_capabilities(e["actor"], e["case"])["research_status"] == "request_expired"
    with Session(e["platform"][1]) as session:
        from app.models.regulatory_drafts import DraftRegulatoryBinding

        row = session.scalars(select(DraftRegulatoryBinding)).one()
        assert row.body == e["binding"].model_dump(mode="json")
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def advance_snapshot_clock(monkeypatch, seconds):
    from app.services.snapshot_clock import ClockObservation, SnapshotTime

    observed = SnapshotTime.observe
    monkeypatch.setattr(
        SnapshotTime,
        "observe",
        lambda clock: ClockObservation(observed(clock).second + seconds, observed(clock).epoch),
    )


def retirement_events(session, run_id):
    from app.models.domain import AuditEvent

    return session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_id == str(run_id),
            AuditEvent.action.endswith("investigation.draft.attempt_failed"),
        )
    ).all()


def test_viewing_an_expired_request_never_writes_and_retirement_records_once(research, monkeypatch):
    from app.models.regulatory_drafts import DraftRegulatoryBinding

    e = research
    run_id = UUID(stage(e)["draft_run_id"])
    advance_snapshot_clock(monkeypatch, 901)
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    # Opening the investigation view N times reports the invalid state and writes nothing.
    for _ in range(5):
        view = gateway.detail(e["actor"], e["case"], run_id)
        assert view.status == "invalidated" and view.draft is None
    with Session(e["platform"][1]) as session:
        assert retirement_events(session, run_id) == []
        job = session.get(DraftJob, run_id)
        assert (job.status, job.error_code, job.attempts) == ("pending", None, 0)
    # The audited transition happens once, where the request is acted on.
    for _ in range(2):  # the retirement path runs when a new request is staged
        with Session(e["platform"][1]) as session, session.begin():
            e["research"]._retire_expired(session, e["actor"])
    for _ in range(5):
        assert gateway.detail(e["actor"], e["case"], run_id).status == "invalidated"
    with Session(e["platform"][1]) as session:
        job = session.get(DraftJob, run_id)
        assert (job.status, job.error_code, job.attempts) == ("invalidated", "input_invalidated", 0)
        assert job.lease_token is None and job.worker_id is None
        events = retirement_events(session, run_id)
        assert len(events) == 1 and events[0].details["reason"] == "input_invalidated"
        assert events[0].details["retryable"] is False
        # Binding, attempts and receipts are preserved; nothing is deleted or dispatched.
        row = session.get(DraftRegulatoryBinding, run_id)
        assert row.body == e["binding"].model_dump(mode="json")
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_invalidation_is_recorded_once_even_if_requested_twice(research, monkeypatch):
    e = research
    run_id = UUID(stage(e)["draft_run_id"])
    drafts = e["research"]
    with Session(e["platform"][1]) as session, session.begin():
        job = session.get(DraftJob, run_id)
        drafts._fail(session, job, "input_invalidated", invalidated=True)
        drafts._fail(session, job, "input_invalidated", invalidated=True)
    with Session(e["platform"][1]) as session:
        assert len(retirement_events(session, run_id)) == 1


def test_expired_research_drafts_release_pending_slots(research, monkeypatch):
    from app.services.investigation_coordinator import InvestigationBusy

    e = research
    configs = [
        e["config"].model_copy(update={"approval_id": f"research-slot-{n}-" + uuid4().hex})
        for n in range(4)
    ]
    runs = [
        UUID(
            e["research"].stage(
                e["actor"], e["case"], f"research-slot-{n}", e["request"], e["binding"], configs[n]
            )["draft_run_id"]
        )
        for n in range(3)
    ]
    # Three unexpired drafts legitimately hold the per-actor limit and are never retired.
    with pytest.raises(InvestigationBusy, match="draft_queue_full"):
        e["research"].stage(
            e["actor"], e["case"], "research-slot-3", e["request"], e["binding"], configs[3]
        )
    with Session(e["platform"][1]) as session:
        assert {session.get(DraftJob, r).status for r in runs} == {"pending"}
    advance_snapshot_clock(monkeypatch, 901)
    fresh = e["bridge"].prepare(
        e["actor"],
        e["case"],
        e["binding"].investigation_run_id,
        ReferenceQuery(query="suspicious transactions"),
    )
    packet = e["bridge"].provider_input(e["actor"], fresh)
    config = configs[3].model_copy(
        update={
            "research_binding_sha256": fresh.binding_sha256,
            "exact_input_sha256": digest(packet.model_dump(mode="json")),
        }
    )
    new = e["research"].stage(e["actor"], e["case"], "research-slot-3", e["request"], fresh, config)
    with Session(e["platform"][1]) as session:
        for run_id in runs:
            job = session.get(DraftJob, run_id)
            assert (job.status, job.error_code, job.attempts) == (
                "invalidated",
                "input_invalidated",
                0,
            )
            assert len(retirement_events(session, run_id)) == 1
        assert session.get(DraftJob, UUID(new["draft_run_id"])).status == "pending"
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_completed_research_result_survives_refresh_after_expiry(research, monkeypatch):
    e = research
    run_id = UUID(stage(e)["draft_run_id"])
    approve_fixture(e)

    class Runner:
        def invoke(self, *args):
            return response(e)

    e["research"]._runner = Runner()
    assert e["research"].run_once(e["token"])["status"] == "succeeded"
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    before = gateway.detail(e["actor"], e["case"], run_id)
    advance_snapshot_clock(monkeypatch, 901)
    after = gateway.detail(e["actor"], e["case"], run_id)
    assert after == before and after.status == "succeeded"
    assert after.draft.regulatory_context == "research_unapproved"
    with Session(e["platform"][1]) as session:
        assert session.get(DraftJob, run_id).status == "succeeded"
        assert retirement_events(session, run_id) == []


@pytest.mark.parametrize("received", [True, False])
def test_invalid_claude_output_is_not_reported_as_provider_unavailable(research, received):
    from pathlib import Path

    from app.services.claude_contract import response_diagnostics

    e = research
    run_id = UUID(stage(e)["draft_run_id"])
    approve_fixture(e)
    raw = (Path(__file__).parent / "fixtures" / "claude_research_v8_response.json").read_bytes()
    diagnostics = response_diagnostics(raw, wire_format="flat_selection_v2", grounded=True)

    class Runner:
        def invoke(self, *args):
            if received:  # HTTP 200, parseable, but outside TrueFlag's output contract.
                raise ProviderRejected(
                    "provider_unavailable", http_status=200, diagnostics=diagnostics
                )
            raise ProviderRejected("provider_unavailable", http_status=503)

    e["research"]._runner = Runner()
    result = e["research"].run_once(e["token"])
    expected = "invalid_provider_output" if received else "provider_unavailable"
    assert (result["status"], result["error_code"]) == ("failed", expected)
    view = ResearchDraftAPIService(e["platform"][1], e["platform"][2]).detail(
        e["actor"], e["case"], run_id
    )
    assert view.status == "failed" and view.error_code == expected and view.draft is None
    with Session(e["platform"][1]) as session:
        receipt = session.scalar(select(DraftReceipt))
        assert receipt.status == expected
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0
        if received:
            assert receipt.usage["diagnostics"]["schema_valid"] is False


def test_public_research_read_still_rechecks_source_revocation(research):
    e = research
    stage(e)
    e["foundation"].set_source_access(e["actor"], e["case"], e["source"], False)
    with pytest.raises((EvidenceBlocked, EvidenceNotFound, VerificationFailed, SnapshotStale)):
        ResearchDraftAPIService(e["platform"][1], e["platform"][2]).context(e["actor"], e["case"])


def test_current_research_capability_requires_owner_approval(research):
    e = research
    stage(e)
    client = e["platform"][0]
    auth = headers(e["platform"], "admin")
    result = client.get(
        f"/api/v1/cases/{e['case']}/investigation-drafts/capabilities", headers=auth
    )
    assert result.status_code == 200
    assert result.json()["provider"] == "unavailable"
    assert result.json()["research_status"] == "approval_required"
    assert result.json()["general_generation_enabled"] is False


def test_long_research_completion_preserves_lease_and_exact_duration(research, monkeypatch):
    from app.models.domain import AuditEvent

    e = research
    receipt = stage(e)
    approve_fixture(e)
    service = e["research"]
    claim = service.claim(e["token"])
    service.prepare(e["token"], claim)
    service.recheck_dispatch(e["token"], claim)
    with Session(e["platform"][1]) as session:
        job = session.get(DraftJob, UUID(receipt["draft_run_id"]))
        assert (job.lease_until - job.deadline).total_seconds() == 30
    original_now = service.coordinator._now
    monkeypatch.setattr(
        service.coordinator, "_now", lambda session: original_now(session) + timedelta(seconds=125)
    )
    # Simulate elapsed time without changing the host or durable snapshot clock.
    result = service.complete(e["token"], claim, response(e), 125000)
    assert result["status"] == "succeeded"
    with Session(e["platform"][1]) as session:
        stored = session.scalar(select(StoredDraft))
        assert stored is not None
        row = session.scalar(select(DraftReceipt))
        assert row.status == "completed" and row.elapsed_ms is None
        duration = session.scalar(
            select(AuditEvent).where(AuditEvent.action.endswith(".provider_duration"))
        )
        assert duration.details["elapsed_ms"] == 125000


def test_research_dispatch_requires_full_execution_window(research, monkeypatch):
    from app.services.snapshot_clock import ClockObservation

    e = research
    stage(e)
    approve_fixture(e)
    service = e["research"]
    claim = service.claim(e["token"])
    clock = service.coordinator.reader.clock
    observation = clock.observe()
    monkeypatch.setattr(
        clock,
        "observe",
        lambda: ClockObservation(e["binding"].expires_second - 150, observation.epoch),
    )
    with pytest.raises(VerificationFailed, match="research_dispatch_window_insufficient"):
        service.prepare(e["token"], claim)
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_research_worker_is_fenced_after_long_job_deadline(research, monkeypatch):
    from app.services.investigation_coordinator import InvestigationLeaseLost

    e = research
    stage(e)
    approve_fixture(e)
    service = e["research"]
    claim = service.claim(e["token"])
    service.prepare(e["token"], claim)
    original_now = service.coordinator._now
    monkeypatch.setattr(
        service.coordinator, "_now", lambda session: original_now(session) + timedelta(seconds=151)
    )
    with pytest.raises(InvestigationLeaseLost):
        service.complete(e["token"], claim, response(e), 151000)
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0


def test_new_research_defaults_preserve_historical_configurations(research):
    config = research["config"]
    assert config.request_deadline_seconds == 120 and config.max_output_tokens == 4096
    raw = json.loads(
        request_body(
            research["packet"],
            max_output_tokens=config.max_output_tokens,
            wire_format=config.wire_format,
        )
    )
    assert raw["output_config"]["effort"] == "medium" and raw["thinking"] == {
        "type": "between_tools"
    }
    assert raw["max_tokens"] == 4096
    original = config.model_dump(mode="json")
    original.update(request_deadline_seconds=20, max_output_tokens=4096)
    assert ResearchClaudeConfig.model_validate(original).model_dump(mode="json") == original
    with pytest.raises(ValidationError):
        ResearchClaudeConfig.model_validate({**original, "request_deadline_seconds": 121})


def test_native_research_worker_waits_for_explicit_click(research):
    e = research
    stage(e)
    approve_fixture(e)
    assert e["research"].run_requested_once(e["token"]) is None
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_protected_research_button_uses_one_existing_job(research, monkeypatch, tmp_path):
    from app.models.investigation_drafts import DraftRequest
    from app.services.live_provider_runner import ProviderRunner

    e = research
    staged = stage(e)
    approve_fixture(e)
    client = e["platform"][0]
    path = (
        f"/api/v1/cases/{e['case']}/investigation-drafts/{staged['draft_run_id']}/execute-research"
    )
    assert client.post(path, headers={"Idempotency-Key": "synthetic-button"}).status_code == 401
    assert client.post(
        path, headers={**headers(e["platform"], "analyst"), "Idempotency-Key": "synthetic-button"}
    ).status_code in (403, 404)
    auth = {**headers(e["platform"], "admin"), "Idempotency-Key": "synthetic-button"}
    for _ in range(2):
        accepted = client.post(path, headers=auth)
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["draft_run_id"] == staged["draft_run_id"]
    credential = tmp_path / "test-provider.env"
    credential.write_text("ANTHROPIC_API_KEY=offline-placeholder\n")
    e["platform"][2].academic_research_credential_file = credential
    monkeypatch.setattr(ProviderRunner, "invoke", lambda *args, **kwargs: response(e))
    assert e["research"].run_requested_once(e["token"])["status"] == "succeeded"
    assert e["research"].run_requested_once(e["token"]) is None
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(DraftRequest)
                .where(DraftRequest.idempotency_key.startswith("research-ui-"))
            )
            == 1
        )
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    first = gateway.detail(e["actor"], e["case"], UUID(staged["draft_run_id"]))
    assert first == gateway.detail(e["actor"], e["case"], UUID(staged["draft_run_id"]))
    assert first.draft.publication_approved is False


def test_research_button_does_not_run_after_source_revocation(research):
    e = research
    staged = stage(e)
    approve_fixture(e)
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    gateway.execute(e["actor"], e["case"], UUID(staged["draft_run_id"]), "synthetic-button")
    e["foundation"].set_source_access(e["actor"], e["case"], e["source"], False)
    assert e["research"].run_requested_once(e["token"]) is None
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0


def test_source_revocation_denies_existing_research(research):
    e = research
    e["foundation"].set_source_access(e["actor"], e["case"], e["source"], False)
    with pytest.raises((EvidenceBlocked, EvidenceNotFound, VerificationFailed)):
        e["bridge"].provider_input(e["actor"], e["binding"])


def test_role_revocation_denies_existing_research(research):
    e = research
    with Session(e["platform"][1]) as session, session.begin():
        session.get(User, e["actor"]).active = False
    with pytest.raises((EvidenceBlocked, EvidenceNotFound, VerificationFailed)):
        e["bridge"].provider_input(e["actor"], e["binding"])


def test_concurrent_staging_creates_one_immutable_job(research):
    e = research
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: stage(e), range(2)))
    assert results[0] == results[1]
    with Session(e["platform"][1]) as session:
        from app.models.investigation_drafts import DraftRun

        assert session.scalar(select(func.count()).select_from(DraftRun)) == 1


def test_binding_insert_failure_rolls_back_job_and_audit(research):
    e = research
    engine = e["platform"][1]

    def stop(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO draft_regulatory_bindings"):
            raise RuntimeError("controlled_synthetic_binding_failure")

    event.listen(engine, "before_cursor_execute", stop)
    try:
        with pytest.raises(EvidenceUnavailable, match="evidence_operation_unavailable"):
            stage(e)
    finally:
        event.remove(engine, "before_cursor_execute", stop)
    with Session(engine) as session:
        from app.models.investigation_drafts import DraftRequest, DraftRun

        assert session.scalar(select(func.count()).select_from(DraftRun)) == 0
        assert session.scalar(select(func.count()).select_from(DraftRequest)) == 0


def test_paid_reservation_crash_is_terminal_and_not_replayed(research):
    e = research
    stage(e)
    approve_fixture(e)
    claim = e["research"].claim(e["token"])
    assert claim
    assert e["research"].prepare(e["token"], claim)
    with e["platform"][1].begin() as c:
        c.execute(
            text(
                "UPDATE investigation_draft_jobs SET lease_until=clock_timestamp()-interval '1 second',deadline=clock_timestamp()-interval '1 second' WHERE run_id=:run"
            ),
            {"run": claim.run_id},
        )
    assert e["research"].recover(e["token"]) == 1
    assert e["research"].claim(e["token"]) is None
    with Session(e["platform"][1]) as session:
        from app.models.investigation_drafts import DraftJob

        assert session.get(DraftJob, claim.run_id).status == "failed"
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0


# ---- in-app exact-request approval by a named spending approver ---------------------------


def approver_policy(e, tmp_path, approvers=None, cap="10.00"):
    """Synthetic test policy only, in the disposable private directory."""
    settings = e["platform"][2]
    grant = {
        "decision": "in_app_exact_request_approval",
        "approver_user_ids": [str(a) for a in (approvers or [e["actor"]])],
        "scope_sha256": settings.academic_research_scope_sha256,
        "terms_sha256": "a" * 64,
        "model": "claude-sonnet-5-5",
        "maximum_input_tokens": e["config"].max_input_tokens,
        "maximum_output_tokens": e["config"].max_output_tokens,
        "timeout_seconds": e["config"].request_deadline_seconds,
        "maximum_requests_per_approval": 1,
        "automatic_retries": False,
        "synthetic_only": True,
        "production_publication_authorized": False,
        "cumulative_cap_usd": cap,
        "reservation_usd": "2.14",
        "owner_decision_reference": "SYNTHETIC_TEST_ONLY_NOT_REAL_OWNER_APPROVAL",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path = settings.academic_research_scope_file.parent / "approvers.json"
    path.write_text(json.dumps(grant))
    settings.academic_research_approver_file = path
    credential = tmp_path / "test-provider.env"
    credential.write_text("ANTHROPIC_API_KEY=offline-placeholder\n")
    settings.academic_research_credential_file = credential


def drafts_path(e):
    return f"/api/v1/cases/{e['case']}/investigation-drafts"


def generate_request(e, role="admin", key="synthetic-generate-click"):
    parent = e["binding"].investigation_run_id
    view = e["service"].get(e["actor"], e["case"], parent)
    return e["platform"][0].post(
        f"{drafts_path(e)}/research-start",
        headers={**headers(e["platform"], role), "Idempotency-Key": key},
        json={
            "investigation_run_id": str(parent),
            "expected_packet_sha256": digest(view["packet"]),
        },
    )


def review(e, run_id, role="admin"):
    return e["platform"][0].get(
        f"{drafts_path(e)}/{run_id}/research-review", headers=headers(e["platform"], role)
    )


def approve(e, run_id, sha, role="admin", key="synthetic-approve-click"):
    return e["platform"][0].post(
        f"{drafts_path(e)}/{run_id}/research-approve",
        headers={**headers(e["platform"], role), "Idempotency-Key": key},
        json={"request_sha256": sha},
    )


def bind_response_to(e, run_id):
    """The fake provider answers for the binding the click actually created."""
    from app.models.investigation_drafts import DraftRun

    with Session(e["platform"][1]) as session:
        run = session.get(DraftRun, run_id)
        e["binding"] = e["research"]._grounding(session, run)
        e["config"] = e["research"]._configuration(run)
    e["packet"] = e["bridge"].provider_input(e["actor"], e["binding"])


def attempts(e):
    with Session(e["platform"][1]) as session:
        return session.scalar(select(func.count()).select_from(DraftAttempt))


def prepared(e):
    accepted = generate_request(e)
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["draft_run_id"]
    shown = review(e, run_id)
    assert shown.status_code == 200, shown.text
    return run_id, shown.json()


@pytest.mark.parametrize(
    "tamper", [None, "link", "amount", "reference", "citation", "question", "bad_link"]
)
def test_owner_reviews_and_approves_exact_request_in_app(research, monkeypatch, tmp_path, tamper):
    from app.models.domain import AuditEvent
    from app.services.live_provider_runner import ProviderRunner

    e = research
    approver_policy(e, tmp_path)
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    caps = gateway.case_capabilities(e["actor"], e["case"])
    assert caps["research_status"] == "generate_ready" and caps["research_can_approve"] is True
    run_id, shown = prepared(e)
    # Preparing and viewing never queue or send anything.
    assert shown["phase"] == "awaiting_approval" and shown["can_approve"] is True
    assert shown["regulatory_status"].startswith("UNAPPROVED RESEARCH")
    assert all(s["approval_status"] == "unapproved_research" for s in shown["regulatory_sources"])
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0
    raw = json.dumps(shown["request"], separators=(",", ":")).encode()
    assert hashlib.sha256(raw).hexdigest() == shown["request_sha256"]
    # Duplicate clicks, a second tab and a retried request all resolve to one dispatch.
    for key in ("synthetic-approve-click", "synthetic-approve-click", "synthetic-other-tab"):
        accepted = approve(e, run_id, shown["request_sha256"], key=key)
        assert accepted.status_code == 202, accepted.text
    assert gateway.case_capabilities(e["actor"], e["case"])["research_status"] == "approved_queued"
    bind_response_to(e, UUID(run_id))
    monkeypatch.setattr(ProviderRunner, "invoke", lambda *args, **kwargs: response(e, tamper))
    result = e["research"].run_requested_once(e["token"])
    ok = tamper in (None, "link")
    assert result["status"] == ("succeeded" if ok else "failed"), result
    assert e["research"].run_requested_once(e["token"]) is None  # never a second request
    assert attempts(e) == 1
    with Session(e["platform"][1]) as session:
        decision = session.scalars(
            select(AuditEvent).where(
                AuditEvent.resource_id == run_id,
                AuditEvent.action.endswith("research_request_owner_approved"),
            )
        ).one()
        assert decision.actor_id == e["actor"]
        assert decision.details["request_sha256"] == shown["request_sha256"]
        assert decision.details["decision"] == "approved" and decision.details["decided_at"]
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == ok
        if tamper == "bad_link":
            failure = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == run_id,
                    AuditEvent.details["verification_reason"].as_string()
                    == "research_finding_citation_invalid",
                )
            ).all()
            assert failure  # recorded in the verification result
    detail = gateway.detail(e["actor"], e["case"], UUID(run_id))
    assert detail == gateway.detail(e["actor"], e["case"], UUID(run_id))  # refresh-stable
    if ok:
        # A resolution needs a reviewed finding: casework must accept a finding from this
        # verified live research result, bound to its content hash, and reject a stale hash.
        from types import SimpleNamespace

        from app.services.casework import CaseworkService
        from app.services.evidence import EvidenceConflict

        casework = CaseworkService(e["platform"][1], e["platform"][2])
        reference = detail.draft.findings[0].reference_id
        command = SimpleNamespace(
            draft_run_id=UUID(run_id),
            reference_id=reference,
            expected_draft_sha256=detail.draft.content_sha256,
        )
        with Session(e["platform"][1]) as session, session.begin():
            bound = casework._finding(session, e["actor"], e["case"], command)
        assert bound["mode"] == "claude_live"
        assert bound["draft_sha256"] == detail.draft.content_sha256
        stale = SimpleNamespace(**{**vars(command), "expected_draft_sha256": "0" * 64})
        with pytest.raises(EvidenceConflict), Session(e["platform"][1]) as session:
            casework._finding(session, e["actor"], e["case"], stale)
        assert detail.draft.regulatory_context == "research_unapproved"
        assert detail.draft.publication_approved is False
        retrieval = detail.draft.retrieval
        assert retrieval is not None and retrieval.total_chunks == 24
        assert retrieval.min_relative_score == "0.25"  # new runs store the threshold
        assert retrieval.strong_matches == len(retrieval.results)
        # v4: every strong match is sent as a bounded excerpt with its hash stored.
        assert retrieval.excerpt_cap_bytes == 4000
        assert all(r.sent and r.excerpt_bytes <= 4000 for r in retrieval.results)
        sent = {str(c.reference_id): c for c in detail.draft.regulatory_citations}
        for r in retrieval.results:
            if str(r.reference_id) in sent:
                assert sent[str(r.reference_id)].excerpt_sha256 == r.excerpt_sha256
        # Full section text of every retrieved source is available for display.
        assert [t.section for t in detail.draft.source_texts] == [
            r.section for r in retrieval.results
        ]
        assert all(
            t.chunk_sha256 == r.chunk_sha256
            for t, r in zip(detail.draft.source_texts, retrieval.results)
        )
        assert retrieval.query and retrieval.inputs and retrieval.results
        assert {str(p.reference_id) for p in detail.draft.regulatory_citations} <= {
            str(r.reference_id) for r in retrieval.results if r.sent
        }
        assert len(detail.draft.finding_citations) == (1 if tamper == "link" else 0)
    caps = gateway.case_capabilities(e["actor"], e["case"])
    assert caps["research_run_id"] == run_id and caps["research_status"] == "generate_ready"
    from datetime import datetime, timezone

    with Session(e["platform"][1]) as session:
        usage = e["research"].anthropic_usage(session, datetime.now(timezone.utc))
    assert usage["requests_this_month"] == 1 and usage["runs_investigations"] is True
    assert usage["status"] == "available" and usage["cumulative_cap_usd"]
    assert usage["spent_total_usd"] == usage["spent_this_month_usd"]
    # Activity History shows the AI investigation lifecycle; "Updated" agrees with it.
    from app.schemas.case_workflows import ActivityQuery
    from app.services.case_workflows import CaseWorkflowService, last_activity

    history = CaseWorkflowService(e["platform"][1]).activity(
        e["actor"], e["case"], ActivityQuery(limit=50)
    )
    kinds = {i["event_type"]: i["outcome"] for i in history["items"]}
    assert {"ai_investigation_requested", "ai_investigation_approved"} <= set(kinds)
    assert "ai_investigation_processing" in kinds
    assert ("ai_investigation_completed" in kinds) == ok
    assert ("ai_investigation_failed" in kinds) == (not ok)
    with Session(e["platform"][1]) as session:
        updated = last_activity(session, [e["case"]])[e["case"]]
    assert updated == max(i["recorded_at"] for i in history["items"])
    if not ok:
        # A repeated failure record for the same request (e.g. written again on re-read)
        # is not new activity: one failure line, "Updated" unchanged.
        from app.models.domain import AuditEvent as Event

        with Session(e["platform"][1]) as session, session.begin():
            (first,) = retirement_events(session, run_id)
            session.add(
                Event(
                    actor_id=first.actor_id,
                    action=first.action,
                    resource_id=first.resource_id,
                    details=dict(first.details),
                )
            )
        again = CaseWorkflowService(e["platform"][1]).activity(
            e["actor"], e["case"], ActivityQuery(limit=50)
        )
        failed = [i for i in again["items"] if i["event_type"] == "ai_investigation_failed"]
        assert len(failed) == 1 and failed[0]["duplicate_records"] == 1
        with Session(e["platform"][1]) as session:
            assert last_activity(session, [e["case"]])[e["case"]] == updated


def test_lock_conflict_before_dispatch_keeps_the_worker_alive_and_sends_nothing(
    research, monkeypatch, tmp_path
):
    """Regression: a deadlock in the pre-dispatch checks used to stop the worker process,
    stranding an approved request until its evidence window expired."""
    from sqlalchemy.exc import OperationalError

    from app.services.live_provider_runner import ProviderRunner
    from app.services.research_drafts import ResearchDraftService

    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, shown["request_sha256"]).status_code == 202
    bind_response_to(e, UUID(run_id))
    sent = []
    monkeypatch.setattr(
        ProviderRunner, "invoke", lambda *a, **k: sent.append(1) or response(e, None)
    )
    original = ResearchDraftService.approved_execution

    def deadlock(self, session, run):
        raise OperationalError("SELECT 1", {}, Exception("deadlock detected"))

    monkeypatch.setattr(ResearchDraftService, "approved_execution", deadlock)
    assert e["research"].run_requested_once(e["token"]) is None  # no exception escapes
    assert sent == [] and attempts(e) == 0
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    assert gateway.case_capabilities(e["actor"], e["case"])["research_status"] == "approved_queued"
    # Next tick, the conflict is gone: the one approved request is sent exactly once.
    monkeypatch.setattr(ResearchDraftService, "approved_execution", original)
    assert e["research"].run_requested_once(e["token"])["status"] == "succeeded"
    assert e["research"].run_requested_once(e["token"]) is None
    assert sent == [1] and attempts(e) == 1


def test_only_named_approvers_can_authorize_spending(research, tmp_path):
    e = research
    approver_policy(e, tmp_path, approvers=[uuid4()])  # the admin is not a named approver
    run_id, shown = prepared(e)
    assert shown["can_approve"] is False and shown["is_approver"] is False
    assert approve(e, run_id, shown["request_sha256"]).status_code == 403
    assert approve(e, run_id, shown["request_sha256"], role="analyst").status_code in (403, 404)
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_no_owner_policy_means_no_in_app_generation(research):
    e = research
    assert generate_request(e).status_code == 409
    assert attempts(e) == 0


def test_approval_is_bound_to_the_exact_displayed_hash(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, "f" * 64).status_code == 409
    assert approve(e, run_id, "nothex").status_code == 422
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_expired_request_is_not_approved_and_refresh_builds_a_new_one(
    research, monkeypatch, tmp_path
):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    advance_snapshot_clock(monkeypatch, 901)
    assert review(e, run_id).json()["phase"] == "request_expired"
    assert approve(e, run_id, shown["request_sha256"]).status_code == 409
    gateway = ResearchDraftAPIService(e["platform"][1], e["platform"][2])
    assert gateway.case_capabilities(e["actor"], e["case"])["research_status"] == "request_expired"
    monkeypatch.undo()
    approver_policy(e, tmp_path)
    advance_snapshot_clock(monkeypatch, 901)
    fresh = generate_request(e, key="synthetic-refresh-click")  # "Refresh Request"
    assert fresh.status_code == 202, fresh.text
    assert fresh.json()["draft_run_id"] != run_id
    renewed = review(e, fresh.json()["draft_run_id"]).json()
    assert renewed["phase"] == "awaiting_approval"
    assert attempts(e) == 0


def test_generate_reuses_the_open_request_instead_of_preparing_another(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    first = generate_request(e, key="synthetic-click-one").json()["draft_run_id"]
    second = generate_request(e, key="synthetic-click-two").json()["draft_run_id"]
    assert first == second


def test_cancelled_request_is_retired_and_cannot_be_approved(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    cancelled = e["platform"][0].post(
        f"{drafts_path(e)}/{run_id}/research-cancel",
        headers={**headers(e["platform"], "admin"), "Idempotency-Key": "synthetic-cancel"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "invalidated"
    approve(e, run_id, shown["request_sha256"])
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_permission_revoked_after_approval_stops_dispatch(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, shown["request_sha256"]).status_code == 202
    approver_policy(e, tmp_path, approvers=[uuid4()])  # stale permission
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_source_revocation_after_approval_stops_dispatch(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, shown["request_sha256"]).status_code == 202
    e["foundation"].set_source_access(e["actor"], e["case"], e["source"], False)
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_spending_cap_blocks_dispatch(research, monkeypatch, tmp_path):
    from decimal import Decimal

    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, shown["request_sha256"]).status_code == 202
    monkeypatch.setattr(ResearchDraftService, "research_spent", lambda *a, **k: Decimal("9.00"))
    assert e["research"].run_requested_once(e["token"]) is None and attempts(e) == 0


def test_approval_audit_history_is_immutable(research, tmp_path):
    e = research
    approver_policy(e, tmp_path)
    run_id, shown = prepared(e)
    assert approve(e, run_id, shown["request_sha256"]).status_code == 202
    with pytest.raises(Exception):
        with e["platform"][1].begin() as c:
            c.execute(
                text("UPDATE audit_events SET details='{}' WHERE resource_id=:r"), {"r": run_id}
            )
