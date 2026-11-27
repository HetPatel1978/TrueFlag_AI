"""New synthetic probe preparation through real source services; zero provider transport."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture

from app.evaluation.harness import write_once
from app.evaluation.luminal_probe import approval_package, prepare_request
from app.evaluation.oracles import verify_fixture
from app.models import User
from app.schemas.investigations import InvestigationPacketBody, InvestigationRequest
from app.services.ingestion import digest
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.synthetic_evidence import generate_scenario

evidence_setup = evidence_fixture
pytestmark = pytest.mark.postgres


@pytest.mark.skipif(
    not all(
        os.environ.get(key)
        for key in (
            "TRUEFLAG_EVAL_EXPECTED_CLUSTER",
            "TRUEFLAG_EVAL_FORBIDDEN_CLUSTER",
            "TRUEFLAG_EVAL_EXPECTED_DATABASE",
            "TRUEFLAG_EVAL_FIXTURES",
        )
    ),
    reason="Requires explicitly authorized legacy isolated probe environment",
)
def test_prepare_three_source_verified_requests_without_provider_or_scientific_assets(
    platform, evidence_setup
):
    from app.evaluation.materialize import isolate

    isolate(
        platform[1],
        expected_cluster=os.environ["TRUEFLAG_EVAL_EXPECTED_CLUSTER"],
        forbidden_cluster=os.environ["TRUEFLAG_EVAL_FORBIDDEN_CLUSTER"],
        expected_database=os.environ["TRUEFLAG_EVAL_EXPECTED_DATABASE"],
    )
    foundation, users = evidence_setup
    service = InvestigationCoordinator(platform[1], platform[2])
    token = "probe-offline-worker-token-not-a-provider-key-" + uuid4().hex
    service.register_worker(users["admin"], "probe-preparation", token)
    prepared = []
    artifacts = Path(os.environ["TRUEFLAG_EVAL_FIXTURES"]) / "probe-package"
    artifacts.mkdir(exist_ok=False)
    for index, probe in enumerate(["A", "B", "C"]):
        bundle = generate_scenario(
            uuid4(),
            942100 + index,
            "partial" if probe == "C" else "unavailable",
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        source = foundation.register_source(users["admin"], bundle.scenario_id)
        release = foundation.admit_version(users["admin"], source, bundle)
        case = foundation.create_case(users["admin"], release)
        context = service.reader.get_case_context(users["admin"], case)
        request = InvestigationRequest(
            expected_case_version=context.snapshot.case_version,
            expected_evidence_revision=context.snapshot.evidence_revision,
            expected_access_revision=context.snapshot.access_revision,
            without_assessment_reason="not_selected",
            window=dict(start=bundle.window_start, end=bundle.as_of),
            currencies=("USD",),
        )
        receipt = service.request(users["admin"], case, "probe-preparation-" + probe, request)
        claim = None
        # The existing worker has bounded not_before semantics; no clock mutation or guard bypass.
        import time

        for _ in range(30):
            result = service.run_once(token)
            if result is not None:
                claim = result
                break
            time.sleep(0.05)
        assert claim is not None and claim["status"] == "abstained"
        result = service.get(users["admin"], case, UUID(receipt["run_id"]))
        packet = InvestigationPacketBody.model_validate(result["packet"])
        verify_fixture(bundle, source, packet)
        wire, item = prepare_request(packet, probe)
        assert b'"type":"json_schema"' in wire and b'"strict":true' in wire
        assert all(
            term not in wire
            for term in [
                b'"features"',
                b'"api_key"',
                b'"customer_id"',
                b'"account_id"',
                b'"model_sha256"',
            ]
        )
        assert len(packet.transactions) == (4 if probe == "C" else 0)
        if probe == "C":
            expected = sum(
                (r.amount for r in bundle.records if r.kind == "transaction"), Decimal(0)
            )
            total = next(f.result for f in packet.facts if f.result.calculation == "count_totals")
            assert total.observed_total == expected and total.observed_count == 4
            item["financial_oracle"] = dict(
                currency="USD",
                observed_count=4,
                observed_total=str(expected),
                amounts=[str(r.amount) for r in bundle.records if r.kind == "transaction"],
            )
        with (artifacts / (probe + ".request.json")).open("xb") as stream:
            stream.write(wire)
        write_once(
            artifacts / (probe + ".sources.json"),
            dict(
                bundle=bundle.model_dump(mode="json"),
                source_id=str(source),
                packet=packet.model_dump(mode="json"),
                independent_oracle="existing_canonical_source_and_decimal_recomputation",
                source_sha256=digest(bundle.model_dump(mode="json")),
            ),
        )
        prepared.append(item)
    package = approval_package(prepared)
    assert (
        package["approval_status"] == "pending_human_review"
        and not package["activation_authorized"]
    )
    assert package["proposed_reservation_total_usd"] == "0.06945792"
    assert all(value is None for value in package["approvals"].values())
    write_once(artifacts / "approval-package.json", package)
    with Session(platform[1]) as session:
        assert session.scalar(select(User.id).where(User.username == "admin")) == users["admin"]
