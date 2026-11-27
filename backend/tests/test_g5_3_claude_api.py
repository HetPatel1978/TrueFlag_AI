"""Controlled Claude contract fixture over real PostgreSQL/API; zero external calls."""

import json

import httpx
import pytest
from pydantic import SecretStr
from test_draft_api import parent, path
from test_foundation import headers
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as draft_fixture
from test_investigation_drafts import env as env_fixture
from test_investigation_drafts import evidence_setup as evidence_fixture

from app.services.claude_contract import MODEL
from app.services.claude_provider import ClaudeProvider

draft_env = draft_fixture
env = env_fixture
evidence_setup = evidence_fixture
pytestmark = pytest.mark.postgres


def test_protected_claude_request_worker_and_verified_projection(draft_env):
    e = draft_env
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_analyst_generation_enabled = True
    settings.anthropic_contract_verified = True
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    calls = []

    class Stream(httpx.SyncByteStream):
        def __init__(self, packet):
            self.packet = packet

        def __iter__(self):
            p = self.packet
            ref = p["transactions"][0]["reference_id"]
            proposal = dict(
                packet_sha256=p["packet_sha256"],
                overview="review_supplied_evidence",
                supporting_records=[ref],
                financial_observations=[],
                model_signals=[],
                risk_indicators=[],
                unusual_activity=[
                    dict(
                        claim_type="observed_fact",
                        reference_id=ref,
                        supporting_evidence=[ref],
                        contradictory_evidence=[],
                        numeric_statements=[],
                    )
                ],
                missing_or_contradictory_evidence=p["missing_evidence"] + p["conflicts"],
                follow_up_questions=p["questions"],
                additional_information_needed=p["questions"],
                uncertainty_limitations=p["limitations"],
                next_steps=["human_review"],
                abstain=p["evidence_requires_abstention"],
                uncertainty="requires_human_semantic_review",
            )
            yield json.dumps(
                dict(
                    type="message",
                    role="assistant",
                    model=MODEL,
                    stop_reason="end_turn",
                    content=[dict(type="text", text=json.dumps(proposal))],
                    usage=dict(input_tokens=500, output_tokens=300),
                )
            ).encode()

    def receive(request):
        calls.append(request)
        packet = json.loads(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(
            200, headers={"content-type": "application/json"}, stream=Stream(packet)
        )

    class Runner:
        def invoke(self, packet, config):
            return ClaudeProvider(settings, transport=httpx.MockTransport(receive)).propose(
                packet, config
            )

    e["drafts"]._runner = Runner()
    client = e["platform"][0]
    auth = headers(e["platform"])
    body = {**parent(e), "provider": "claude"}
    assert client.post(path(e), json=body).status_code == 401
    response = client.post(
        path(e), json=body, headers={**auth, "Idempotency-Key": "claude-api-contract-fixture"}
    )
    assert response.status_code == 202, response.text
    assert e["drafts"].run_once(e["token"])["status"] in {"succeeded", "abstained"}
    detail = client.get(response.headers["location"], headers=auth)
    assert detail.status_code == 200, detail.text
    value = detail.json()
    assert value["mode"] == "claude_live" and value["live_provider_used"]
    assert value["draft"]["provenance"]["provider"] == "anthropic"
    assert value["draft"]["simulation"] is False and value["draft"]["findings"]
    assert len(calls) == 1
    assert "offline-test-only" not in detail.text and '"features"' not in detail.text


def test_claude_is_not_enabled_by_a_key_or_missing_regulatory_approval(draft_env):
    e = draft_env
    e["platform"][2].anthropic_api_key = SecretStr("offline-test-only")
    client = e["platform"][0]
    response = client.post(
        path(e),
        json={**parent(e), "provider": "claude"},
        headers={**headers(e["platform"]), "Idempotency-Key": "claude-api-denied-fixture"},
    )
    assert response.status_code == 503


def test_atomic_start_queues_parent_and_child_without_browser_chaining(draft_env):
    e = draft_env
    client = e["platform"][0]
    auth = {**headers(e["platform"]), "Idempotency-Key": "atomic-start-fixture-001"}
    body = {
        "investigation_request": packet_request(e).model_dump(mode="json"),
        "provider": "simulation",
    }
    assert client.post(path(e) + "/start", json=body).status_code == 401
    receipt = client.post(path(e) + "/start", json=body, headers=auth)
    assert receipt.status_code == 202, receipt.text
    again = client.post(path(e) + "/start", json=body, headers=auth)
    assert again.json() == receipt.json()
    assert e["drafts"].claim(e["token"]) is None  # parent is still pending
    assert e["service"].run_once(e["token"])["status"] == "succeeded"
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    detail = client.get(receipt.headers["location"], headers=auth)
    assert detail.json()["draft"]["investigation_run_id"] == receipt.json()["investigation_run_id"]
