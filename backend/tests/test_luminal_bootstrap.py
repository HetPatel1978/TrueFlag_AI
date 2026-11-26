"""Offline first-probe package and current-authority preflight checks."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_investigation_drafts import draft_env as draft_env_fixture
from test_investigation_drafts import env, evidence_setup, ready  # noqa: F401

from app.models.investigation_drafts import DraftRun
from app.models.investigations import InvestigationPacket
from app.schemas.investigations import InvestigationPacketBody
from app.services.evidence import EvidenceNotFound
from app.services.luminal_bootstrap import (
    PROBE_A_SHA,
    ProbeBootstrapPreflight,
    ProbePreflightError,
    VerifiedProbe,
    verify_probe_a,
)
from app.services.provider_finance import PROVIDER_LEDGER_LOCK, lock_reservations

draft_env = draft_env_fixture
APPROVAL = Path(__file__).resolve().parents[2] / "runtime/g4-2b-1/approval"


@pytest.fixture
def artifacts():
    names = ["approval-package.json", "A.request.json", "A.sources.json"]
    if not all((APPROVAL / name).is_file() for name in names):
        pytest.skip("locally staged synthetic probe package unavailable")
    return [(APPROVAL / name).read_bytes() for name in names]


def test_actual_synthetic_package_and_oracle_validate_without_transport(artifacts):
    result = verify_probe_a(*artifacts)
    assert result.wire_sha256 == PROBE_A_SHA


@pytest.mark.parametrize("index", range(3))
def test_modified_probe_artifacts_are_rejected(artifacts, index):
    artifacts[index] += b" "
    if index != 1:
        # Whitespace alone leaves JSON semantics unchanged; mutate actual content.
        artifacts[index] = (
            artifacts[index].replace(b"luminal", b"Luminal", 1) if index == 0 else b"{}"
        )
    with pytest.raises(ProbePreflightError, match="approved_probe_invalid"):
        verify_probe_a(*artifacts)


@pytest.mark.postgres
def test_provider_ledger_lock_is_shared_across_transactions(platform):
    engine = platform[1]
    with Session(engine) as first, first.begin():
        lock_reservations(first)
        with Session(engine) as second, second.begin():
            assert (
                second.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:lock)"), {"lock": PROVIDER_LEDGER_LOCK}
                )
                is False
            )
    with Session(engine) as second, second.begin():
        assert (
            second.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock)"), {"lock": PROVIDER_LEDGER_LOCK}
            )
            is True
        )


@pytest.mark.postgres
def test_current_case_and_admin_are_required_before_any_bootstrap(draft_env, monkeypatch):
    receipt = ready(draft_env)
    run_id = UUID(receipt["draft_run_id"])
    with Session(draft_env["platform"][1]) as session:
        run = session.get(DraftRun, run_id)
        record = session.scalar(
            select(InvestigationPacket).where(InvestigationPacket.run_id == run.parent_run_id)
        )
        packet = InvestigationPacketBody.model_validate_json(json.dumps(record.body))
    probe = VerifiedProbe(packet=packet, wire_sha256=PROBE_A_SHA)
    service = ProbeBootstrapPreflight(draft_env["platform"][1], draft_env["platform"][2])
    with pytest.raises(EvidenceNotFound):
        service.inspect(draft_env["users"]["analyst"], run_id, probe)
    result = service.inspect(draft_env["users"]["admin"], run_id, probe)
    assert result == {"status": "blocked", "reason": "approved_case_or_payload_changed"}
    # Even a matching synthetic test fixture cannot pass the unresolved billing
    # and transport gate, and does not need or set provider compatibility.
    from app.services import luminal_bootstrap as module

    fake_wire = b"synthetic-test-wire"
    fake_hash = hashlib.sha256(fake_wire).hexdigest()
    monkeypatch.setattr(module, "PROBE_A_SHA", fake_hash)
    monkeypatch.setattr(module, "prepare_request", lambda packet, name: (fake_wire, {}))
    draft_env["platform"][2].investigation_provider_contract_verified = False
    result = service.inspect(
        draft_env["users"]["admin"], run_id, VerifiedProbe(packet=packet, wire_sha256=fake_hash)
    )
    assert result["reason"] == "vendor_charge_bound_and_bootstrap_transport_unverified"
    assert result["external_requests"] == 0 and result["prior_attempts"] == 0
