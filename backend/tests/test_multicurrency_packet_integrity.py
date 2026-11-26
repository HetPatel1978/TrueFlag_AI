"""Currency-scoped source membership and arithmetic without requiring model scoring."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import admit
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import submit

from app.models.investigations import InvestigationPacket
from app.services.investigation_verifier import VerificationFailed

evidence_setup = evidence_fixture
env = investigation_fixture
pytestmark = pytest.mark.postgres


def test_later_currency_references_and_totals_remain_independently_verified(env):
    bundle, source, release = admit(env["foundation"], env["users"]["admin"], "multi_currency")
    env.update(
        bundle=bundle,
        source=source,
        release=release,
        case=env["foundation"].create_case(env["users"]["admin"], release),
    )
    # Explicit evidence-only selection: no fabricated model score, pipeline or provider.
    receipt = submit(env, currencies=("USD", "CAD"))
    service, token = env["service"], env["token"]
    claim = service.claim(token)
    body = service.assemble(token, claim)
    assert [(f.result.currency, f.result.calculation) for f in body.facts] == [
        ("USD", "count_totals"),
        ("USD", "concentration"),
        ("CAD", "count_totals"),
        ("CAD", "concentration"),
    ]
    later = body.facts[2]
    invalid = [
        later.model_copy(update={"input_record_ids": [uuid4()]}),
        later.model_copy(update={"input_record_ids": body.facts[0].input_record_ids}),
        later.model_copy(
            update={
                "result": later.result.model_copy(
                    update={"observed_total": later.result.observed_total + Decimal(1)}
                )
            }
        ),
    ]
    for changed in invalid:
        forged = body.model_copy(update={"facts": body.facts[:2] + [changed] + body.facts[3:]})
        with pytest.raises(VerificationFailed):
            service.complete(token, claim, forged)
        with Session(env["platform"][1]) as session:
            assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0
    assert service.complete(token, claim, body)["status"] == "succeeded"
    result = service.get(env["users"]["admin"], env["case"], UUID(receipt["run_id"]))
    assert result["verification"]["financial_facts"] == 4
    assert result["packet"]["model_signal"] is None
    assert result["packet"]["human_review_required"]
    assert result["packet"]["regulatory_citations"] == []
