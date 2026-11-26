"""Real isolated PostgreSQL materialization and adversarial evaluation; no LLM calls."""

import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation.controlled import responses
from app.evaluation.dataset import dataset, source_bundle
from app.evaluation.evaluators import evaluate_response
from app.evaluation.harness import blocked_fixture, write_once
from app.evaluation.materialize import isolate, materialize_case
from app.evaluation.oracles import verify_fixture
from app.models import AssessmentJob, Case
from app.models.investigation_drafts import DraftRun
from app.schemas.evidence_read import AnalyticsRequest
from app.schemas.investigations import InvestigationPacketBody
from app.services.connected_scenarios import expected_activity
from app.services.evidence import EvidenceNotFound
from app.services.evidence_read import EvidenceReadService
from app.services.snapshot_clock import ClockUnavailable

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def require_explicit_isolated_evaluation_target():
    # General CI must never discover a target from application/demo configuration.
    if not all(
        os.environ.get(name)
        for name in [
            "TRUEFLAG_TEST_POSTGRES_URL",
            "TRUEFLAG_EVAL_EXPECTED_CLUSTER",
            "TRUEFLAG_EVAL_FORBIDDEN_CLUSTER",
            "TRUEFLAG_EVAL_EXPECTED_DATABASE",
        ]
    ):
        pytest.skip("requires explicit isolated PostgreSQL evaluation target")


def target():
    return dict(
        expected_cluster=os.environ.get("TRUEFLAG_EVAL_EXPECTED_CLUSTER"),
        forbidden_cluster=os.environ.get("TRUEFLAG_EVAL_FORBIDDEN_CLUSTER"),
        expected_database=os.environ.get("TRUEFLAG_EVAL_EXPECTED_DATABASE"),
    )


def save(spec, value):
    path = os.environ.get("TRUEFLAG_EVAL_FIXTURES")
    if path:
        write_once(Path(path) / (spec["case_key"] + ".json"), value)


@pytest.mark.parametrize("spec", dataset()["cases"], ids=lambda s: s["case_key"])
def test_materialized_scenario_source_oracles_and_controlled_outputs(platform, spec):
    client, engine, settings, _ = platform
    with Session(engine) as session:
        from app.models import User

        actor = session.scalar(select(User.id).where(User.username == "admin"))
    try:
        value = materialize_case(engine, settings, actor, spec, **target())
    except ClockUnavailable:
        save(spec, blocked_fixture(spec, "clock_unavailable"))
        raise
    except Exception:
        save(spec, blocked_fixture(spec, "materialization_failed"))
        raise
    save(spec, value)
    packet = InvestigationPacketBody.model_validate(value["packet"])
    bundle = source_bundle(spec)
    source = UUID(value["source_id"])
    assert verify_fixture(bundle, source, packet)
    if spec["category"] == "ordinary":
        from uuid import uuid4

        for change, failure in [
            ("transaction_direction", "transaction_values_failed"),
            ("transaction_reference", "source_version_failed"),
            ("evidence_reference", "source_version_failed"),
            ("duplicate_transaction", "transaction_membership_failed"),
            ("duplicate_fact", "financial_plan_failed"),
        ]:
            tampered = packet.model_dump(mode="json")
            if change == "transaction_direction":
                row = tampered["transactions"][0]
                row["direction"] = "debit" if row["direction"] == "credit" else "credit"
            elif change == "transaction_reference":
                tampered["transactions"][0]["reference"]["source_version_id"] = str(uuid4())
            elif change == "evidence_reference":
                tampered["evidence"][0]["identity_id"] = str(uuid4())
            elif change == "duplicate_transaction":
                tampered["transactions"].append(tampered["transactions"][0])
            else:
                tampered["facts"].append(tampered["facts"][0])
            with pytest.raises(ValueError, match=failure):
                verify_fixture(bundle, source, InvestigationPacketBody.model_validate(tampered))
    if spec["lifecycle"] in {"revoke", "revise"}:
        assert value["lifecycle_result"] == "denied_by_existing_service"
    else:
        for control, raw, expected in responses(packet):
            result = evaluate_response(bundle, source, packet, raw)
            assert result["accepted"] == expected, (
                spec["case_key"],
                control,
                result["failure_class"],
            )
        # A corrupt packet cannot become its own financial or source ground truth.
        data = packet.model_dump(mode="json")
        data["facts"][0]["result"]["observed_count"] += 1
        corrupt = InvestigationPacketBody.model_validate(data)
        with pytest.raises(ValueError, match="reconciliation_failed"):
            verify_fixture(bundle, source, corrupt)
    if spec["category"] == "description_injection":
        from app.services.investigation_draft_verifier import minimize

        annotation = value["untrusted_annotations"][0]
        assert "SYNTHETIC_EVAL_CANARY" in annotation["description"]
        assert "SYNTHETIC_EVAL_CANARY" not in minimize(packet).model_dump_json()
        assert (
            value["description_injection_coverage"]
            == "unsupported_source_field_test_annotation_only"
        )
    if spec["category"] == "reversals":
        reader = EvidenceReadService(engine, settings)
        context = reader.get_case_context(actor, UUID(value["application_case_id"]))
        actual = reader.calculate_activity(
            actor,
            context.snapshot.case_id,
            AnalyticsRequest(
                snapshot=context.data.snapshot_token,
                calculation="count_totals",
                window=dict(start=bundle.window_start, end=bundle.as_of),
                currency="USD",
                treatment="exclude_verified_reversals",
            ),
        )
        oracle = expected_activity(bundle, net=True)
        assert actual.data.observed_count == oracle["count"] == 11
        from decimal import Decimal

        assert actual.data.observed_total == Decimal(oracle["total"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DraftRun)) == 0
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 0
        assert all(
            c.status == "open" and c.disposition is None for c in session.scalars(select(Case))
        )


def test_materialization_rejects_wrong_cluster_or_schema_before_writes(platform):
    engine = platform[1]
    with pytest.raises(ValueError):
        isolate(
            engine, expected_cluster="same", forbidden_cluster="same", expected_database="live-demo"
        )


def test_materialization_cannot_use_analyst_as_source_owner(platform):
    from app.models import User

    with Session(platform[1]) as session:
        actor = session.scalar(select(User.id).where(User.username == "analyst"))
    with pytest.raises(EvidenceNotFound):
        materialize_case(platform[1], platform[2], actor, dataset()["cases"][0], **target())
