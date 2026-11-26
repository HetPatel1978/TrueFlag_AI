"""Explicit isolated PostgreSQL fixture preparation using the existing evidence coordinator."""

import re
import secrets
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.snapshot_clock import SnapshotClock
from app.schemas.investigations import InvestigationPacketBody, InvestigationRequest
from app.services.evidence import EvidenceNotFound, EvidenceService
from app.services.evidence_read import SnapshotStale
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.snapshot_clock import ClockUnavailable
from app.services.synthetic_evidence import generate_scenario

from .dataset import source_bundle
from .harness import fixture


def isolate(engine, *, expected_cluster, forbidden_cluster, expected_database):
    if (
        engine.dialect.name != "postgresql"
        or not expected_cluster
        or expected_cluster == forbidden_cluster
        or not expected_database
        or not expected_database.startswith("tf_g0_3_primary_")
    ):
        raise ValueError("evaluation_isolation_required")
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        cluster = str(connection.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        database = connection.scalar(text("SELECT current_database()"))
        schema = connection.scalar(text("SELECT current_schema()"))
    if (
        cluster != expected_cluster
        or database != expected_database
        or re.fullmatch(r"tf_ingestion_test_[a-f0-9]{32}", schema or "") is None
    ):
        raise ValueError("evaluation_isolation_mismatch")


def materialize_case(engine, settings, actor_id, spec, **isolation):
    isolate(engine, **isolation)
    if settings.investigation_external_enabled:
        raise ValueError("offline_evaluation_external_disabled_required")
    bundle = source_bundle(spec)
    foundation = EvidenceService(engine)
    source = foundation.register_source(actor_id, bundle.scenario_id)
    release = foundation.admit_version(actor_id, source, bundle)
    case = foundation.create_case(actor_id, release)
    coordinator = InvestigationCoordinator(engine, settings)
    token = secrets.token_urlsafe(48)
    coordinator.register_worker(actor_id, "offline-evaluation-worker", token)
    context = coordinator.reader.get_case_context(actor_id, case)
    epoch = coordinator.reader.clock.observe().epoch
    currencies = sorted({r.currency for r in bundle.records if r.kind == "transaction"} or {"USD"})
    request = InvestigationRequest(
        expected_case_version=context.snapshot.case_version,
        expected_evidence_revision=context.snapshot.evidence_revision,
        expected_access_revision=context.snapshot.access_revision,
        without_assessment_reason="not_selected",
        window=dict(start=bundle.window_start, end=bundle.as_of),
        currencies=tuple(currencies),
    )
    receipt = coordinator.request(actor_id, case, "offline-evaluation-" + spec["case_key"], request)
    coordinator.run_once(token)
    result = coordinator.get(actor_id, case, UUID(receipt["run_id"]))
    if result.get("packet") is None:
        with Session(engine) as session:
            clock = session.get(SnapshotClock, 1)
            if clock and (clock.regressed or clock.epoch != epoch):
                raise ClockUnavailable("evaluation_materialization_clock_denied")
        raise ValueError("evaluation_materialization_failed")
    packet = InvestigationPacketBody.model_validate(result["packet"])
    lifecycle = "not_applicable"
    if spec["lifecycle"] in {"revoke", "revise"}:
        if spec["lifecycle"] == "revoke":
            foundation.set_source_access(actor_id, case, source, False)
        else:
            revised = generate_scenario(
                bundle.scenario_id,
                bundle.seed,
                bundle.profile,
                source_revision=2,
                as_of=bundle.as_of,
            )
            next_release = foundation.admit_version(actor_id, source, revised)
            foundation.link_version(actor_id, case, next_release)
        try:
            after = coordinator.get(actor_id, case, UUID(receipt["run_id"]))
            denied = after.get("packet") is None and after["status"] == "invalidated"
        except (EvidenceNotFound, SnapshotStale):
            denied = True
        # A clock denial cannot substitute for a source/authorization denial.
        lifecycle = "denied_by_existing_service" if denied else "unexpectedly_disclosed"
    return fixture(spec, source, case, packet, lifecycle_result=lifecycle)
