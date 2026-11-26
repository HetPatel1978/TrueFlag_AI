"""Real PostgreSQL import-to-synthetic-evidence provenance and authorization tests."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid5

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_csv_imports import approve, finish
from test_csv_imports import base_upload as base_upload_fixture
from test_csv_imports import imports as imports_fixture
from test_csv_validation import data, staged, validate

from app.models import Alert, AuditEvent, Case, CSVImportRow, User
from app.models.evidence import CaseEvidenceLink, EvidenceCaseBinding, EvidenceSource
from app.schemas.evidence_read import AnalyticsRequest, Window
from app.services.evidence import EvidenceConflict, EvidenceNotFound, EvidenceUnavailable
from app.services.evidence_read import EvidenceReadService
from app.services.synthetic_demo_cases import (
    SyntheticDemoEvidenceService,
    demo_bundle,
    demo_source_id,
)

base_upload = base_upload_fixture
imports = imports_fixture
pytestmark = pytest.mark.postgres


def import_scenario(env, scenario="priority"):
    bundle = demo_bundle(scenario)
    values = {
        key: "" if value is None else str(value) for key, value in bundle.declarations.items()
    }
    values["source_id"] = demo_source_id(bundle)
    uid = staged(env, data([values]))
    response = validate(env, uid)
    assert response.status_code == 201
    preview = response.json()
    assert (preview["total_rows"], preview["valid_rows"]) == (1, 1)
    approval = {
        name: preview[name]
        for name in (
            "upload_sha256",
            "mapping_sha256",
            "mapping_version",
            "validator_version",
            "units",
        )
    }
    approval.update(approve_valid_rows=True, validation_version=preview["version"])
    result = approve(env, (uid, preview, approval))
    assert result.status_code == 202
    assert finish(env)[-1].status == "completed"
    with Session(env["engine"]) as session:
        row = session.scalar(select(CSVImportRow))
        return bundle, row.case_id, row.alert_id


def test_imported_demo_evidence_is_linked_and_financial_totals_are_correct(imports):
    env = imports
    bundle, case_id, alert_id = import_scenario(env)
    service = SyntheticDemoEvidenceService(env["engine"])
    first = service.attach_uploaded_case(env["actor_id"], case_id, "priority")
    assert first["already_linked"] is False
    assert (
        service.attach_uploaded_case(env["actor_id"], case_id, "priority")["already_linked"] is True
    )
    reader = EvidenceReadService(env["engine"], env["settings"])
    context = reader.get_case_context(env["actor_id"], case_id)
    activity = reader.calculate_activity(
        env["actor_id"],
        case_id,
        AnalyticsRequest(
            snapshot=context.data.snapshot_token,
            calculation="incoming_outgoing",
            currency="USD",
            window=Window(start=bundle.window_start, end=bundle.as_of),
        ),
    ).data
    assert activity.observed_count == 12 and str(activity.observed_total) == "10020.00000000"
    with Session(env["engine"]) as session:
        assert session.get(Alert, alert_id).features == bundle.declarations
        assert session.get(Case, case_id).status == "open"
        assert session.scalar(select(func.count()).select_from(EvidenceCaseBinding)) == 1
        assert session.scalar(
            select(AuditEvent.id).where(AuditEvent.action == "evidence.demo_case_bound")
        )


def test_no_cross_user_or_cross_scenario_binding(imports):
    env = imports
    _, case_id, _ = import_scenario(env)
    with Session(env["engine"]) as session, session.begin():
        foreign = User(username="demootheradmin", role="admin", password_hash="synthetic")
        session.add(foreign)
        session.flush()
        foreign_id = foreign.id
    service = SyntheticDemoEvidenceService(env["engine"])
    with pytest.raises(EvidenceNotFound):
        service.attach_uploaded_case(foreign_id, case_id, "priority")
    with pytest.raises(EvidenceConflict, match="demo_source_mismatch"):
        service.attach_uploaded_case(env["actor_id"], case_id, "ordinary")
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceSource)) == 0
        assert session.scalar(select(func.count()).select_from(EvidenceCaseBinding)) == 0


def test_revoked_evidence_is_not_restored_by_replay(imports):
    env = imports
    bundle, case_id, _ = import_scenario(env)
    actor = env["actor_id"]
    service = SyntheticDemoEvidenceService(env["engine"])
    service.attach_uploaded_case(actor, case_id, "priority")
    source_id = uuid5(actor, str(bundle.scenario_id))
    with Session(env["engine"]) as session:
        record = session.scalar(
            select(CaseEvidenceLink.record_version_id).where(CaseEvidenceLink.case_id == case_id)
        )
    service.revoke_links(actor, case_id, source_id, (record,))
    assert service.attach_uploaded_case(actor, case_id, "priority")["already_linked"] is True
    with Session(env["engine"]) as session:
        assert session.get(CaseEvidenceLink, (case_id, record)).active is False
    service.set_source_access(actor, case_id, source_id, False)
    with pytest.raises(EvidenceNotFound):
        service.attach_uploaded_case(actor, case_id, "priority")


def test_binding_failure_rolls_back_sources_and_case_links(imports, monkeypatch):
    env = imports
    _, case_id, _ = import_scenario(env)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic test failure")

    monkeypatch.setattr("app.services.synthetic_demo_cases.audit", fail)
    with pytest.raises(EvidenceUnavailable):
        SyntheticDemoEvidenceService(env["engine"]).attach_uploaded_case(
            env["actor_id"], case_id, "priority"
        )
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceSource)) == 0
        assert session.scalar(select(func.count()).select_from(EvidenceCaseBinding)) == 0


def test_concurrent_attaches_create_one_binding(imports):
    env = imports
    _, case_id, _ = import_scenario(env)
    service = SyntheticDemoEvidenceService(env["engine"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: service.attach_uploaded_case(env["actor_id"], case_id, "priority"),
                range(2),
            )
        )
    assert sorted(value["already_linked"] for value in results) == [False, True]
    with Session(env["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceCaseBinding)) == 1


@pytest.mark.parametrize("scenario", ["ordinary", "incomplete"])
def test_all_demo_profiles_import_and_bind(imports, scenario):
    env = imports
    _, case_id, _ = import_scenario(env, scenario)
    result = SyntheticDemoEvidenceService(env["engine"]).attach_uploaded_case(
        env["actor_id"], case_id, scenario
    )
    assert result["already_linked"] is False
