"""Real PostgreSQL immutable reservation ceilings; all provider HTTP is mocked."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_investigation_coordinator import request as packet_request
from test_live_provider_integration import env as env_fixture
from test_live_provider_integration import evidence_setup as evidence_fixture
from test_live_provider_integration import setup
from test_luminal_provider import config, packet, settings

from app.models import Case
from app.models.investigation_drafts import DraftAttempt, DraftJob
from app.services.investigation_provider import ProviderFailure
from app.services.luminal_provider import LuminalProvider
from app.services.provider_budget import MAX_PROVIDER_SPEND_USD, call_limit, spend_limit

env, evidence_setup = env_fixture, evidence_fixture


@pytest.mark.parametrize("count", [0, -1, 4, True, None])
def test_invalid_or_absent_call_authority_never_opens_transport(count):
    calls = []
    value = settings(investigation_provider_call_limit=count)
    with pytest.raises(ProviderFailure):
        LuminalProvider(
            value, transport=httpx.MockTransport(lambda req: calls.append(req))
        ).propose(packet(), config())
    assert not calls and call_limit(value) == 0


def test_paid_retries_and_spend_above_one_USD_rejected_before_transport():
    calls = []
    for candidate in [
        config(max_attempts=2, total_token_budget=73728),
        config(max_cost_usd="1.01"),
    ]:
        with pytest.raises(ProviderFailure):
            LuminalProvider(
                settings(investigation_provider_spend_limit_usd=5),
                transport=httpx.MockTransport(lambda req: calls.append(req)),
            ).propose(packet(), candidate)
    assert (
        not calls
        and spend_limit(settings(investigation_provider_spend_limit_usd=5))
        == MAX_PROVIDER_SPEND_USD
    )


def add(env, service, index, **kwargs):
    return service.request(
        env["users"]["admin"],
        env["case"],
        f"bounded-probe-intent-{index}",
        packet_request(env),
        config(
            max_cost_usd="0.8",
            max_output_tokens=4096 + index,
            total_token_budget=36864 + index,
            **kwargs,
        ),
    )


@pytest.mark.postgres
def test_concurrent_workers_and_restart_cannot_reserve_a_fourth_request(env):
    service, _, calls = setup(env, cfg=config(max_cost_usd="0.8"))
    assert service.run_once(env["token"])["status"] == "succeeded"
    add(env, service, 1)
    assert service.run_once(env["token"])["status"] == "succeeded"
    receipts = [add(env, service, i) for i in [2, 3]]
    claims = [service.claim(env["token"]) for _ in receipts]
    assert all(claims)
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared = list(pool.map(lambda claim: service.prepare(env["token"], claim), claims))
    assert sum(value is not None for value in prepared) == 1
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 3
        assert session.get(Case, env["case"]).status == "open"
        assert (
            sum(session.get(DraftJob, UUID(r["draft_run_id"])).status == "failed" for r in receipts)
            == 1
        )
    # All three reservations are immutable, including the undelivered/unknown third attempt.
    from app.services.investigation_drafts import InvestigationDraftService

    restarted = InvestigationDraftService(env["platform"][1], env["platform"][2])
    extra = add(env, restarted, 4)
    claim = restarted.claim(env["token"])
    assert claim and restarted.prepare(env["token"], claim) is None
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 3
        assert session.get(DraftJob, UUID(extra["draft_run_id"])).error_code == "budget_exhausted"
    assert len(calls) == 2


@pytest.mark.postgres
def test_one_USD_grant_ceiling_applies_even_if_operator_configured_five(env):
    overrides = dict(
        investigation_provider_input_usd_per_million=10,
        investigation_provider_output_usd_per_million=20,
        investigation_provider_spend_limit_usd=5,
    )
    service, _, calls = setup(
        env,
        cfg=config(input_usd_per_million="10", output_usd_per_million="20", max_cost_usd="0.8"),
        provider_settings=overrides,
    )
    assert service.run_once(env["token"])["status"] == "succeeded"
    receipt = add(env, service, 1, input_usd_per_million="10", output_usd_per_million="20")
    result = service.run_once(env["token"])
    assert result["status"] == "failed" and result["error_code"] == "budget_exhausted"
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
        assert session.get(DraftJob, UUID(receipt["draft_run_id"])).status == "failed"
    assert len(calls) == 1
