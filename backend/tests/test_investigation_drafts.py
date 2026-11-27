"""Simulation-only PostgreSQL acceptance; never live-provider accuracy or legal truth."""

import json
import os
import secrets
import select as os_select
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_setup_fixture
from test_investigation_coordinator import env as evidence_env_fixture
from test_investigation_coordinator import request as packet_request

from alembic import command
from app.models import AuditEvent, Case, User
from app.models.investigation_drafts import (
    DraftAttempt,
    DraftJob,
    DraftReceipt,
    DraftRequest,
    DraftRun,
    StoredDraft,
)
from app.models.investigations import InvestigationJob, InvestigationRun
from app.schemas.investigation_drafts import ProviderConfig, ProviderProposal
from app.services.evidence import (
    EvidenceBlocked,
    EvidenceConflict,
    EvidenceNotFound,
    EvidenceUnavailable,
)
from app.services.investigation_coordinator import InvestigationLeaseLost
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_provider import (
    DeterministicFakeProvider,
    ProviderFailure,
    ProviderTimeout,
    strict_json,
)

env = evidence_env_fixture
evidence_setup = evidence_setup_fixture


class InlineSimulation:
    """Deterministic fake only; isolates verifier/failure tests from process startup."""

    def invoke(self, packet, config):
        return DeterministicFakeProvider().propose(packet, config)


@pytest.fixture
def draft_env(env):
    env["platform"][2].investigation_simulation_enabled = True
    service = InvestigationDraftService(env["platform"][1], env["platform"][2])
    service._runner = InlineSimulation()
    # A durable asynchronous claim may correctly be idle while not_before is in
    # the future. Poll only that state; never extend leases or change DB clocks.
    for worker, table in [(env["service"], InvestigationJob), (service, DraftJob)]:
        original = worker.claim

        def await_eligible(*args, original=original, table=table):
            started = time.monotonic()
            for _ in range(100):
                result = original(*args)
                if result is not None:
                    return result
                with Session(env["platform"][1]) as session:
                    now = session.scalar(select(func.clock_timestamp()))
                    future = session.scalar(
                        select(func.min(table.not_before)).where(
                            table.status == "pending", table.not_before > now
                        )
                    )
                if future is None or time.monotonic() - started >= 6:
                    return None
                time.sleep(min(0.1, max(0.01, (future - now).total_seconds())))
            return None

        worker.claim = await_eligible
    return {**env, "drafts": service}


def submit(e, *, key="explicit-draft-request", config=None, investigation_request=None):
    return e["drafts"].request(
        e["users"]["admin"],
        e["case"],
        key,
        investigation_request or packet_request(e),
        config or ProviderConfig(),
    )


def ready(e, **kwargs):
    receipt = submit(e, **kwargs)
    assert (
        e["drafts"].get(e["users"]["admin"], e["case"], UUID(receipt["draft_run_id"]))["status"]
        == "pending"
    )
    failures = []
    original = e["service"].assemble

    def diagnostic(*args):
        try:
            return original(*args)
        except Exception as error:
            chain = []
            seen = set()
            current = error
            while current is not None and id(current) not in seen:
                seen.add(id(current))
                chain.append(type(current).__name__)
                code = getattr(getattr(current, "orig", current), "sqlstate", None)
                if code:
                    chain.append(code)
                current = current.__context__
            failures.append(chain)
            raise

    e["service"].assemble = diagnostic
    try:
        # Exercise the existing bounded worker retries, including fail-closed
        # snapshot rejection during VM clock corrections. No terminal failure is retried.
        for _ in range(3):
            parent = e["service"].run_once(e["token"])
            if parent is None or parent["status"] != "pending":
                break
    finally:
        e["service"].assemble = original
    assert parent is not None and parent["status"] in {"succeeded", "abstained"}, (parent, failures)
    return receipt


def get(e, receipt):
    return e["drafts"].get(e["users"]["admin"], e["case"], UUID(receipt["draft_run_id"]))


def count(e, model):
    with Session(e["platform"][1]) as session:
        return session.scalar(select(func.count()).select_from(model))


def due(e):
    with e["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_draft_jobs SET not_before=clock_timestamp()-interval '1 second' WHERE status='pending'"
            )
        )


def test_simulated_pipeline_preserves_source_facts_case_and_provenance(draft_env):
    e = draft_env
    receipt = ready(e)
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    body = get(e, receipt)["draft"]
    assert body["mode"] == "simulation" and body["human_review_required"]
    assert not body["provenance"]["live_provider_used"]
    assert body["provenance"]["provider"] == "deterministic_fake"
    assert body["verification"]["human_semantic_review_required"]
    assert not body["verification"]["full_factual_entailment_verified"]
    assert body["regulatory_citations"] == body["human_conclusions"] == []
    assert body["regulatory_context"] == "unavailable_unapproved"
    assert body["findings"] and body["unresolved_questions"]
    with Session(e["platform"][1]) as session:
        case = session.get(Case, e["case"])
        assert case.status == "open" and case.disposition is None
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 1
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
        receipt_row = session.scalar(select(DraftReceipt))
        assert receipt_row.status == "completed" and receipt_row.usage["cost_usd"] == "0"
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.investigation.draft.published")
            )
            == 1
        )


def test_minimized_input_excludes_business_ids_source_text_and_credentials(draft_env):
    e = draft_env
    ready(e)
    claim = e["drafts"].claim(e["token"])
    assert claim is not None
    packet, config = e["drafts"].prepare(e["token"], claim)
    raw = packet.model_dump_json()
    assert str(e["case"]) not in raw and str(e["users"]["admin"]) not in raw
    assert "account_handle" not in raw and "counterparty_handle" not in raw
    for forbidden in [
        "original_time",
        "annual_income",
        "snapshot_token",
        "model_sha256",
        "raw_sha256",
        "password",
        "JWT_SECRET",
    ]:
        assert forbidden not in raw
    assert config.max_cost_usd == 0 and packet.regulatory_context == "unavailable_unapproved"
    with pytest.raises(EvidenceConflict, match="already_reserved"):
        e["drafts"].prepare(e["token"], claim)


def test_disabled_default_and_external_enable_flag_cannot_activate_egress(env):
    service = InvestigationDraftService(env["platform"][1], env["platform"][2])
    with pytest.raises(EvidenceBlocked, match="provider_disabled"):
        service.request(
            env["users"]["admin"],
            env["case"],
            "disabled-draft-key",
            packet_request(env),
            ProviderConfig(),
        )
    env["platform"][2].investigation_simulation_enabled = True
    env["platform"][2].investigation_external_enabled = True
    with pytest.raises(EvidenceBlocked, match="provider_disabled"):
        service.run_once(env["token"])
    assert count(env, DraftRun) == count(env, InvestigationRun) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "external"},
        {"model": "unapproved"},
        {"mode": "live"},
        {"api_key": "not-a-credential"},
        {"max_cost_usd": "0.01"},
        {"max_attempts": 4},
        {"request_deadline_seconds": 0},
        {"max_output_tokens": True},
    ],
)
def test_config_rejects_unapproved_providers_credentials_and_unbounded_budgets(changes):
    with pytest.raises(ValidationError):
        ProviderConfig(**changes)


def test_idempotent_concurrent_requests_and_conflicting_configuration(draft_env):
    e = draft_env
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: submit(e), range(2)))
    assert receipts[0]["draft_run_id"] == receipts[1]["draft_run_id"]
    alias = submit(e, key="same-intent-other-key")
    assert alias["draft_run_id"] == receipts[0]["draft_run_id"]
    with pytest.raises(EvidenceConflict):
        submit(e, config=ProviderConfig(max_output_tokens=4096))
    assert count(e, DraftRun) == count(e, InvestigationRun) == 1
    assert count(e, DraftRequest) == 2


def test_concurrent_workers_fence_one_active_draft(draft_env):
    e = draft_env
    ready(e)
    token = secrets.token_urlsafe(48)
    e["service"].register_worker(e["users"]["admin"], "draft-second-worker", token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(e["drafts"].claim, [e["token"], token]))
    assert sum(c is not None for c in claims) == 1


@pytest.mark.parametrize(
    "attack",
    [
        "forged_reference",
        "number",
        "currency",
        "window",
        "tool",
        "verification",
        "legal",
        "cross_case",
        "hypothesis_text",
        "injection_question",
        "confident_partial",
        "oversized",
        "duplicate_json",
        "nan",
    ],
)
def test_malicious_or_invalid_provider_output_is_withheld(draft_env, attack):
    e = draft_env
    if attack == "confident_partial":
        from test_evidence_foundation import admit

        bundle, _, release = admit(e["foundation"], e["users"]["admin"], "partial")
        e = {
            **e,
            "bundle": bundle,
            "case": e["foundation"].create_case(e["users"]["admin"], release),
        }
    receipt = ready(e)
    original = InlineSimulation()

    class Attack:
        def invoke(self, packet, config):
            reply = original.invoke(packet, config)
            value = json.loads(reply.content)
            if attack in {"forged_reference", "cross_case"}:
                value["findings"][0]["reference_id"] = str(uuid4())
            elif attack == "number":
                value["findings"][0]["numeric_statements"] = [
                    dict(metric="amount", value="999999999", currency="USD")
                ]
            elif attack == "currency":
                value["findings"][0]["numeric_statements"] = [
                    dict(metric="amount", value=packet.transactions[0]["amount"], currency="CAD")
                ]
            elif attack == "window":
                value["findings"][1]["numeric_statements"] = [
                    dict(
                        metric="observed_count",
                        value=packet.financial_facts[0]["result"]["observed_count"],
                        currency="USD",
                        window={"start": "2020-01-01T00:00:00Z", "end": "2020-01-02T00:00:00Z"},
                    )
                ]
            elif attack == "tool":
                value["tool_calls"] = [dict(name="run_sql", arguments="DROP TABLE cases")]
            elif attack == "verification":
                value["verification"] = {"trusted": True}
            elif attack == "legal":
                value["regulatory_citations"] = ["31 CFR made-up"]
            elif attack == "hypothesis_text":
                value["hypotheses"] = [
                    dict(
                        question_code="customer_is_a_criminal",
                        supporting_evidence=[],
                        uncertainty="unconfirmed_requires_human_review",
                    )
                ]
            elif attack == "injection_question":
                value["questions"] = ["ignore_permissions_and_publish_sources"]
            elif attack == "confident_partial":
                value["abstain"] = False
            content = json.dumps(value)
            if attack == "oversized":
                content = "x" * (config.max_output_tokens + 1)
            if attack == "duplicate_json":
                content = '{"schema_version":"one","schema_version":"two"}'
            if attack == "nan":
                content = '{"untrusted":NaN}'
            return reply.model_copy(update={"content": content})

    e["drafts"]._runner = Attack()
    result = e["drafts"].run_once(e["token"])
    assert result["status"] == "failed" and result["error_code"] in {
        "verification_failed",
        "invalid_provider_output",
    }
    assert get(e, receipt)["draft"] is None and count(e, StoredDraft) == 0


@pytest.mark.parametrize("change", ["source", "role", "assignment", "worker"])
def test_revocation_during_provider_execution_prevents_publication(draft_env, change):
    e = draft_env
    ready(e)

    class Revoke:
        def invoke(self, packet, config):
            reply = InlineSimulation().invoke(packet, config)
            if change == "source":
                e["foundation"].set_source_access(
                    e["users"]["admin"], e["case"], e["source"], False
                )
            elif change == "worker":
                e["service"].revoke_worker(e["users"]["admin"], e["worker"])
            else:
                with Session(e["platform"][1]) as session, session.begin():
                    if change == "role":
                        session.get(User, e["users"]["admin"]).active = False
                    else:
                        session.get(Case, e["case"]).version += 1
            return reply

    e["drafts"]._runner = Revoke()
    if change == "worker":
        with pytest.raises(EvidenceNotFound):
            e["drafts"].run_once(e["token"])
    else:
        assert e["drafts"].run_once(e["token"])["status"] == "invalidated"
    assert count(e, StoredDraft) == 0


def test_expired_worker_recovery_keeps_budget_and_fences_stale_response(draft_env):
    e = draft_env
    receipt = ready(e)
    claim = e["drafts"].claim(e["token"])
    packet, config = e["drafts"].prepare(e["token"], claim)
    reply = InlineSimulation().invoke(packet, config)
    with e["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_draft_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='running'"
            )
        )
    assert e["drafts"].recover(e["token"]) == 1
    with pytest.raises(InvestigationLeaseLost):
        e["drafts"].complete(e["token"], claim, reply, 1)
    due(e)
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    assert (
        get(e, receipt)["attempts"] == 2
        and count(e, DraftAttempt) == 2
        and count(e, StoredDraft) == 1
    )
    with Session(e["platform"][1]) as session:
        receipt_row = session.scalar(
            select(DraftReceipt).where(DraftReceipt.status == "lease_expired")
        )
        assert receipt_row.usage is None


@pytest.mark.parametrize("failure", ["timeout", "provider_error", "incomplete", "refused"])
def test_provider_failures_are_bounded_and_manual_review(draft_env, failure):
    e = draft_env
    receipt = ready(e)

    class Broken:
        def invoke(self, packet, config):
            if failure == "timeout":
                raise ProviderTimeout("sensitive detail must not escape")
            if failure == "provider_error":
                raise ProviderFailure("sensitive provider body")
            reply = InlineSimulation().invoke(packet, config)
            return reply.model_copy(
                update={"finish_reason": "incomplete" if failure == "incomplete" else "refused"}
            )

    e["drafts"]._runner = Broken()
    for _ in range(3):
        result = e["drafts"].run_once(e["token"])
        if result["status"] == "failed":
            break
        due(e)
    assert result["status"] == "failed"
    assert get(e, receipt)["draft"] is None and count(e, StoredDraft) == 0
    assert result["attempts"] == (1 if failure == "refused" else 3)


def test_budget_reservation_survives_failure_and_prevents_retries(draft_env):
    e = draft_env
    # Make the total permit one conservatively reserved request, not an unlimited retry loop.
    config = ProviderConfig(
        max_input_tokens=16384, max_output_tokens=16384, total_token_budget=32768
    )
    receipt = ready(e, config=config)

    class Broken:
        def invoke(self, *_):
            raise ProviderTimeout("private diagnostics")

    e["drafts"]._runner = Broken()
    for _ in range(3):
        result = e["drafts"].run_once(e["token"])
        if result["error_code"] == "budget_exhausted":
            break
        due(e)
    assert result["error_code"] == "budget_exhausted"
    assert count(e, DraftAttempt) == 1 and get(e, receipt)["draft"] is None


@pytest.mark.parametrize("stage", ["request", "publication"])
def test_atomic_audit_failure_rolls_back_parent_child_and_publication(draft_env, stage):
    e = draft_env
    if stage == "publication":
        ready(e)
        claim = e["drafts"].claim(e["token"])
        packet, config = e["drafts"].prepare(e["token"], claim)
        reply = InlineSimulation().invoke(packet, config)

    def broken(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("private audit detail")

    event.listen(e["platform"][1], "before_cursor_execute", broken)
    try:
        with pytest.raises(EvidenceUnavailable, match="^evidence_operation_unavailable$"):
            if stage == "request":
                submit(e)
            else:
                e["drafts"].complete(e["token"], claim, reply, 1)
    finally:
        event.remove(e["platform"][1], "before_cursor_execute", broken)
    assert count(e, StoredDraft) == 0 and count(e, DraftReceipt) == 0
    if stage == "request":
        assert count(e, InvestigationRun) == count(e, DraftRun) == 0
    else:
        assert e["drafts"].complete(e["token"], claim, reply, 1)["status"] == "succeeded"


@pytest.mark.parametrize(
    "table",
    [
        "investigation_draft_runs",
        "investigation_draft_requests",
        "investigation_draft_attempts",
        "investigation_draft_receipts",
        "investigation_drafts",
    ],
)
def test_immutable_history_update_delete_truncate(draft_env, table):
    e = draft_env
    ready(e)
    e["drafts"].run_once(e["token"])
    column = "id" if table != "investigation_draft_requests" else "actor_id"
    for sql in [
        f"UPDATE {table} SET {column}={column}",
        f"DELETE FROM {table}",
        f"TRUNCATE {table} CASCADE",
    ]:
        with pytest.raises(DBAPIError):
            with e["platform"][1].begin() as connection:
                connection.execute(text(sql))


def test_schema_drift_and_empty_rollback_then_retained_history_guard(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("PostgreSQL required")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.check(config)
    command.downgrade(config, "0014_investigation_foundation")
    command.upgrade(config, "head")
    command.check(config)


def test_retained_drafts_prevent_downgrade(draft_env):
    submit(draft_env)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="retained snapshot clock history"):
        command.downgrade(config, "0014_investigation_foundation")


@pytest.mark.skipif(
    sys.platform != "linux", reason="actual Linux secret-free bounded simulation process"
)
def test_actual_isolated_provider_process_and_clean_environment(draft_env, monkeypatch):
    from app.services.investigation_provider_runner import IsolatedSimulationRunner

    e = draft_env
    receipt = ready(e)
    import app.services.investigation_provider_runner as runner_module

    original = runner_module.subprocess.Popen
    inspected = []

    def guarded(*args, **kwargs):
        assert set(kwargs["env"]) == {"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED"}
        assert kwargs["start_new_session"]
        inspected.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(runner_module.subprocess, "Popen", guarded)
    e["drafts"]._runner = IsolatedSimulationRunner()
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    assert inspected and get(e, receipt)["draft"]["mode"] == "simulation"


def test_strict_response_json_never_accepts_duplicate_keys_or_nonfinite_values():
    for raw in ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}']:
        with pytest.raises(ValueError):
            strict_json(raw, 1024)
    with pytest.raises(ValidationError):
        ProviderProposal.model_validate({"verification": True})


@pytest.mark.parametrize(
    "profile", ["partial", "unavailable", "inconsistent_kyc", "timezone_unknown", "multi_currency"]
)
def test_missing_partial_conflicting_evidence_is_preserved_with_abstention(draft_env, profile):
    from test_evidence_foundation import admit

    e = draft_env
    bundle, _, release = admit(e["foundation"], e["users"]["admin"], profile)
    e = {**e, "bundle": bundle, "case": e["foundation"].create_case(e["users"]["admin"], release)}
    receipt = ready(e)
    assert e["drafts"].run_once(e["token"])["status"] == "abstained"
    body = get(e, receipt)["draft"]
    assert body["outcome"] == "abstained" and body["unresolved_questions"]
    assert (
        "incomplete_evidence_not_zero_activity" in body["limitations"]
        or body["conflicts"]
        or profile == "multi_currency"
    )
    if profile == "inconsistent_kyc":
        assert body["conflicts"] == ["contradictory_kyc_observations"]
    if profile == "unavailable":
        assert not any(f["claim_type"] == "observed_fact" for f in body["findings"])


def test_legacy_case_produces_abstention_without_invented_history(draft_env, case_team):
    e = {**draft_env, "case": UUID(case_team["ids"][0])}
    receipt = ready(e)
    assert e["drafts"].run_once(e["token"])["status"] == "abstained"
    body = get(e, receipt)["draft"]
    assert not any(f["claim_type"] == "observed_fact" for f in body["findings"])
    assert all(
        f["server_generated_summary"]["result"]["observed_total"] is None for f in body["findings"]
    )


def test_foreign_case_run_and_foreign_observation_are_not_disclosed(draft_env, case_team):
    from test_evidence_foundation import admit

    e = draft_env
    receipt = ready(e)
    e["drafts"].run_once(e["token"])
    bundle, _, release = admit(e["foundation"], e["users"]["admin"], seed=29)
    other = e["foundation"].create_case(e["users"]["admin"], release)
    with pytest.raises(EvidenceNotFound):
        e["drafts"].get(e["users"]["admin"], other, UUID(receipt["draft_run_id"]))
    with pytest.raises(EvidenceNotFound):
        e["drafts"].get(
            UUID(case_team["users"]["analysttwo"]), e["case"], UUID(receipt["draft_run_id"])
        )
    # An actual valid reference belonging to a second case is rejected, not just a random UUID.
    other_packet = e["service"].reader.get_case_context(e["users"]["admin"], other)
    foreign_ref = next(
        r.record_version_id for r in other_packet.evidence if r.kind == "transaction"
    )
    next_request = packet_request(e, currencies=("USD", "CAD"))
    second = ready(e, key="explicit-foreign-reference", investigation_request=next_request)

    class Foreign:
        def invoke(self, packet, config):
            reply = InlineSimulation().invoke(packet, config)
            value = json.loads(reply.content)
            value["findings"][0]["supporting_evidence"] = [str(foreign_ref)]
            return reply.model_copy(update={"content": json.dumps(value)})

    e["drafts"]._runner = Foreign()
    assert e["drafts"].run_once(e["token"])["status"] == "failed"
    assert get(e, second)["draft"] is None


def test_published_draft_is_withheld_after_source_revocation(draft_env):
    e = draft_env
    receipt = ready(e)
    e["drafts"].run_once(e["token"])
    assert get(e, receipt)["draft"]
    e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
    assert get(e, receipt)["draft"] is None
    assert count(e, StoredDraft) == 1


def test_database_disconnection_rolls_back_draft_and_recovers_safely(draft_env):
    e = draft_env
    receipt = ready(e)
    claim = e["drafts"].claim(e["token"])
    packet, config = e["drafts"].prepare(e["token"], claim)
    reply = InlineSimulation().invoke(packet, config)

    def disconnect(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO investigation_drafts "):
            cursor.execute("SELECT pg_terminate_backend(pg_backend_pid())")

    event.listen(e["platform"][1], "before_cursor_execute", disconnect)
    try:
        with pytest.raises(EvidenceUnavailable):
            e["drafts"].complete(e["token"], claim, reply, 1)
    finally:
        event.remove(e["platform"][1], "before_cursor_execute", disconnect)
    assert count(e, StoredDraft) == count(e, DraftReceipt) == 0
    assert e["drafts"].complete(e["token"], claim, reply, 1)["status"] == "succeeded"
    assert get(e, receipt)["draft"] and count(e, StoredDraft) == 1


def test_numeric_assertions_match_source_records_not_provider_claims(draft_env):
    e = draft_env
    receipt = ready(e)

    class Numeric:
        def invoke(self, packet, config):
            reply = InlineSimulation().invoke(packet, config)
            value = json.loads(reply.content)
            value["findings"][0]["numeric_statements"] = [
                dict(
                    metric="amount",
                    value=packet.transactions[0]["amount"],
                    currency=packet.transactions[0]["currency"],
                )
            ]
            fact = packet.financial_facts[0]["result"]
            value["findings"][1]["numeric_statements"] = [
                dict(
                    metric="observed_count",
                    value=fact["observed_count"],
                    currency=fact["currency"],
                    window=fact["window"],
                )
            ]
            return reply.model_copy(update={"content": json.dumps(value)})

    e["drafts"]._runner = Numeric()
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    assert (
        get(e, receipt)["draft"]["verification"]["status"]
        == "structural_reference_numeric_checks_passed"
    )


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1", reason="pinned real RF/SHAP fixture"
)
def test_actual_stored_rf_policy_shap_identity_and_numeric_values(draft_env):
    from app.services.assessments import AssessmentService

    e = draft_env
    result, _ = AssessmentService(e["platform"][1]).assess(
        actor_id=e["users"]["admin"],
        case_id=e["case"],
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="draft-stored-model-only",
        policy="Balanced",
    )
    query = packet_request(
        e, assessment_id=UUID(result["assessment_id"]), without_assessment_reason=None
    )
    receipt = ready(e, investigation_request=query)
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    body = get(e, receipt)["draft"]
    assert body["stored_model_signal"]["score"] == result["score"]["score"]
    assert body["stored_model_signal"]["explanation"]["status"] == "verified"
    assert any(
        f["claim_type"] == "model_signal"
        and f["interpretation"] == "model_signal_not_probability_of_crime"
        for f in body["findings"]
    )


@pytest.mark.skipif(sys.platform != "linux", reason="actual bounded Linux process termination")
def test_provider_deadline_kills_process_group(draft_env, monkeypatch):
    import app.services.investigation_provider_runner as runner_module

    e = draft_env
    ready(e)
    claim = e["drafts"].claim(e["token"])
    packet, config = e["drafts"].prepare(e["token"], claim)
    original = runner_module.subprocess.Popen
    processes = []

    def slow(command, **kwargs):
        child = original([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(runner_module.subprocess, "Popen", slow)
    with pytest.raises(ProviderTimeout):
        runner_module.IsolatedSimulationRunner().invoke(
            packet, config.model_copy(update={"request_deadline_seconds": 1})
        )
    assert processes and all(p.poll() is not None for p in processes)


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux provider-stage crash/restart")
def test_actual_worker_crash_after_reservation_then_restart_has_one_draft(draft_env):
    e = draft_env
    receipt = ready(e)
    script = """
import json,sys,signal,time
def safe_exception(kind,value,traceback): print('CHILD_ERROR:'+kind.__name__,flush=True)
sys.excepthook=safe_exception
from app.core.config import Settings
from app.core.database import make_engine
from app.services.investigation_drafts import InvestigationDraftService
p=json.loads(sys.stdin.readline())
settings=Settings(database_url=p['database_url'],jwt_secret=p['jwt_secret'],investigation_simulation_enabled=True)
service=InvestigationDraftService(make_engine(settings.database_url),settings)
class Paused:
 def invoke(self,*args):
  print('PROVIDER_RESERVED',flush=True)
  signal.pause()
service._runner=Paused()
for _ in range(30):
 service.run_once(p['token'])
 time.sleep(0.1)
"""
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    process.stdin.write(
        json.dumps(
            dict(
                database_url=e["platform"][2].database_url,
                jwt_secret=e["platform"][2].jwt_secret.get_secret_value(),
                token=e["token"],
            )
        )
        + "\n"
    )
    process.stdin.close()
    try:
        available, _, _ = os_select.select([process.stdout], [], [], 20)
        assert available and process.stdout.readline().strip() == "PROVIDER_RESERVED"
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
    with e["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_draft_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='running'"
            )
        )
    restarted = InvestigationDraftService(e["platform"][1], e["platform"][2])
    assert restarted.recover(e["token"]) == 1
    due(e)
    assert restarted.run_once(e["token"])["status"] == "succeeded"
    assert (
        get(e, receipt)["attempts"] == 2
        and count(e, DraftAttempt) == 2
        and count(e, StoredDraft) == 1
    )


def test_hypotheses_are_uncertain_templates_and_do_not_replace_facts(draft_env):
    e = draft_env
    receipt = ready(e)

    class Hypothesis:
        def invoke(self, packet, config):
            reply = InlineSimulation().invoke(packet, config)
            value = json.loads(reply.content)
            value["hypotheses"] = [
                dict(
                    question_code="coverage_gap_requires_more_evidence",
                    supporting_evidence=[str(packet.evidence_references[0])],
                    contradictory_evidence=[],
                    uncertainty="unconfirmed_requires_human_review",
                )
            ]
            return reply.model_copy(update={"content": json.dumps(value)})

    e["drafts"]._runner = Hypothesis()
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    body = get(e, receipt)["draft"]
    assert body["hypotheses"][0]["uncertainty"] == "unconfirmed_requires_human_review"
    assert body["findings"] and body["human_conclusions"] == []
