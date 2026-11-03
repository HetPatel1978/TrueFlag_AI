"""Bounded durable orchestration; all scientific work stays in the existing ML queue."""

import functools
import hashlib
import logging
import re
import threading
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import case as sql_case
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    Assessment,
    AssessmentJob,
    AuditEvent,
    BatchAssessment,
    BatchAssessmentItem,
    BatchAssessmentRequest,
    Case,
    CSVImport,
    CSVImportRow,
    Decision,
    ModelScore,
    User,
)
from app.schemas.batch_assessments import BatchAssessmentStart, BatchProgress, BatchResultsPage
from app.services.assessment_api import AssessmentRateLimited, _budget, _detail
from app.services.assessment_jobs import FAILURES, AssessmentJobService, QueueFull
from app.services.assessments import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
    AssessmentUnavailable,
    _locked_case,
    _read,
    _request,
    _snapshot,
)
from app.services.batch_authorization import check_batch_job
from app.services.cases import visible_cases
from app.services.csv_staging import UploadDenied, _admin, _aware, _now, _timeouts
from app.services.ingestion import digest
from trueflag_ml.policy import POLICY_SHA256
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION

POLICY_VERSION = f"{MODEL_VERSION}:{POLICY_SHA256}"
MODEL_SHA = APPROVED_SHA256[MODEL_PATH]


class BatchCapacity(AssessmentError):
    pass


def safe(method):
    @functools.wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (AssessmentError, AssessmentRateLimited, UploadDenied):
            raise
        except Exception:
            raise AssessmentUnavailable("batch_service_unavailable") from None

    return call


def event(session, batch, action, **details):
    session.add(
        AuditEvent(
            actor_id=batch.actor_id,
            action="batch.assessment." + action,
            resource_id=str(batch.id),
            details={"batch_id": str(batch.id), **details},
        )
    )


def outcome_expression():
    return sql_case(
        (BatchAssessmentItem.status == "ready", "pending_dispatch"),
        (BatchAssessmentItem.status == "skipped", "skipped"),
        (BatchAssessmentItem.status == "failed", "failed_manual_review"),
        (AssessmentJob.status == "pending", "queued"),
        (AssessmentJob.status == "running", "running"),
        (AssessmentJob.status == "succeeded", "succeeded"),
        else_="failed_manual_review",
    )


def counts(session, batch_id):
    state = outcome_expression()
    expressions = {
        name: func.count().filter(state == name)
        for name in (
            "pending_dispatch",
            "queued",
            "running",
            "succeeded",
            "failed_manual_review",
            "skipped",
        )
    }
    expressions.update(
        total_cases=func.count(),
        total_eligible_cases=func.count().filter(BatchAssessmentItem.eligible.is_(True)),
        already_assessed=func.count().filter(BatchAssessmentItem.reason_code == "already_assessed"),
        retrying=func.count().filter(
            BatchAssessmentItem.status == "job",
            AssessmentJob.status == "pending",
            AssessmentJob.attempts > 0,
        ),
    )
    return dict(
        session.execute(
            select(*[v.label(k) for k, v in expressions.items()])
            .select_from(BatchAssessmentItem)
            .outerjoin(AssessmentJob, AssessmentJob.id == BatchAssessmentItem.job_id)
            .where(BatchAssessmentItem.batch_id == batch_id)
        )
        .mappings()
        .one()
    )


def progress(batch, c):
    status = batch.status
    if status == "active":
        status = "dispatching" if c["pending_dispatch"] else "processing"
    return BatchProgress(
        batch_id=batch.id,
        import_id=batch.import_id,
        status=status,
        **c,
        policy=batch.policy,
        model_version=batch.model_version,
        model_sha256=batch.model_sha256,
        policy_version=batch.policy_version,
        policy_sha256=batch.policy_sha256,
        import_validation_sha256=batch.import_sha256,
        group_size=batch.group_size,
        backpressure_count=batch.backpressure_count,
        reason_code=batch.reason_code,
        created_at=_aware(batch.created_at),
        updated_at=_aware(batch.updated_at),
        finished_at=_aware(batch.finished_at) if batch.finished_at else None,
    )


class BatchAssessmentService:
    def __init__(self, engine, settings, telemetry=None):
        self.engine, self.settings, self.telemetry = engine, settings, telemetry
        if engine.dialect.name != "postgresql":
            raise AssessmentUnavailable("postgresql_required")
        self.queue = AssessmentJobService(engine)

    def _authorized(self, session, actor_id, batch_id):
        _admin(session, actor_id)
        batch = session.scalar(
            select(BatchAssessment)
            .where(BatchAssessment.id == batch_id, BatchAssessment.actor_id == actor_id)
            .with_for_update()
        )
        if batch is None:
            raise AssessmentNotFound("batch_not_found")
        hidden = session.scalar(
            select(BatchAssessmentItem.case_id)
            .join(Case, Case.id == BatchAssessmentItem.case_id)
            .where(
                BatchAssessmentItem.batch_id == batch.id,
                ~visible_cases(SimpleNamespace(id=actor_id)),
            )
            .limit(1)
        )
        if hidden is not None:
            raise AssessmentNotFound("batch_not_found")
        return batch

    def _finish(self, session, batch):
        session.flush()
        c = counts(session, batch.id)
        if batch.status == "active" and not (c["pending_dispatch"] or c["queued"] or c["running"]):
            now = _now(session)
            batch.status = (
                ("partially_completed" if c["succeeded"] or c["skipped"] else "failed")
                if c["failed_manual_review"]
                else "completed"
            )
            batch.updated_at = batch.finished_at = now
            event(session, batch, "completed", status=batch.status, **c)
            session.flush()
        return c

    @safe
    def start(self, actor_id, import_id, body, key):
        if (
            type(body) is not BatchAssessmentStart
            or type(key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", key)
        ):
            raise AssessmentConflict("invalid_batch_request")
        request_sha = digest(
            {
                "import_id": str(import_id),
                "body": body.model_dump(),
                "model_sha256": MODEL_SHA,
                "policy_sha256": POLICY_SHA256,
            }
        )
        key_sha = hashlib.sha256(key.encode()).hexdigest()
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _admin(session, actor_id)
            receipt = session.scalar(
                select(BatchAssessmentRequest).where(
                    BatchAssessmentRequest.actor_id == actor_id,
                    BatchAssessmentRequest.key_sha256 == key_sha,
                )
            )
            if receipt:
                if receipt.request_sha256 != request_sha:
                    raise AssessmentConflict("batch_key_conflict")
                batch = self._authorized(session, actor_id, receipt.batch_id)
                event(session, batch, "request_replayed")
                return progress(batch, self._finish(session, batch))
            source = session.scalar(
                select(CSVImport).where(CSVImport.id == import_id, CSVImport.actor_id == actor_id)
            )
            if source is None:
                raise AssessmentNotFound("batch_not_found")
            if (
                source.status not in {"completed", "partially_completed"}
                or source.processed_rows != source.total_rows
            ):
                raise AssessmentConflict("import_not_complete")
            if body.import_validation_sha256 != source.validation_sha256:
                raise AssessmentConflict("import_identity_conflict")
            batch = session.scalar(
                select(BatchAssessment).where(
                    BatchAssessment.import_id == import_id,
                    BatchAssessment.policy == body.policy,
                    BatchAssessment.model_sha256 == MODEL_SHA,
                    BatchAssessment.policy_sha256 == POLICY_SHA256,
                )
            )
            if batch is None:
                if not session.scalar(
                    text(
                        "SELECT pg_try_advisory_xact_lock(6075990630000000000 + 'batch_assessments'::regclass::oid::bigint)"
                    )
                ):
                    raise AssessmentUnavailable("batch_admission_busy")
                active = (
                    select(func.count())
                    .select_from(BatchAssessment)
                    .where(BatchAssessment.status == "active")
                )
                if (
                    session.scalar(active) >= self.settings.batch_assessment_capacity
                    or session.scalar(active.where(BatchAssessment.actor_id == actor_id))
                    >= self.settings.batch_assessment_actor_capacity
                ):
                    raise BatchCapacity("batch_capacity")
                now = _now(session)
                batch = BatchAssessment(
                    id=uuid4(),
                    import_id=import_id,
                    actor_id=actor_id,
                    import_sha256=source.validation_sha256,
                    policy=body.policy,
                    model_version=MODEL_VERSION,
                    model_sha256=MODEL_SHA,
                    policy_version=POLICY_VERSION,
                    policy_sha256=POLICY_SHA256,
                    group_size=self.settings.batch_assessment_group_size,
                    status="active",
                    available_at=now,
                    updated_at=now,
                    audit_event_id=uuid4(),
                )
                session.add(
                    AuditEvent(
                        id=batch.audit_event_id,
                        actor_id=actor_id,
                        action="batch.assessment.requested",
                        resource_id=str(batch.id),
                        details={
                            "import_id": str(import_id),
                            "policy": body.policy,
                            "model_sha256": MODEL_SHA,
                            "policy_sha256": POLICY_SHA256,
                            "import_validation_sha256": source.validation_sha256,
                        },
                    )
                )
                session.flush()
                session.add(batch)
                session.flush()
                # Stream metadata only; no feature values or ML jobs are loaded/created here.
                candidates = (
                    select(
                        Case.id,
                        Case.alert_id,
                        Case.version,
                        Case.status,
                        func.min(CSVImportRow.row_number).label("source_row"),
                    )
                    .join(CSVImportRow, CSVImportRow.case_id == Case.id)
                    .where(
                        CSVImportRow.import_id == import_id,
                        CSVImportRow.status.in_(["created", "reused"]),
                        CSVImportRow.alert_id == Case.alert_id,
                        visible_cases(SimpleNamespace(id=actor_id)),
                    )
                    .group_by(Case.id, Case.alert_id, Case.version, Case.status)
                    .order_by(func.min(CSVImportRow.row_number))
                )
                values = []
                for item in session.execute(candidates.execution_options(yield_per=100)):
                    eligible = item.status != "closed"
                    values.append(
                        {
                            "batch_id": batch.id,
                            "case_id": item.id,
                            "alert_id": item.alert_id,
                            "case_version": item.version,
                            "source_row_number": item.source_row,
                            "eligible": eligible,
                            "run_id": uuid4(),
                            "status": "ready" if eligible else "skipped",
                            "reason_code": None if eligible else "case_closed",
                            "originated": False,
                        }
                    )
                    if len(values) == 100:
                        session.execute(insert(BatchAssessmentItem), values)
                        values.clear()
                if values:
                    session.execute(insert(BatchAssessmentItem), values)
                if not counts(session, batch.id)["total_cases"]:
                    raise AssessmentNotFound("batch_not_found")
                event(session, batch, "members_frozen", **counts(session, batch.id))
            else:
                batch = self._authorized(session, actor_id, batch.id)
                event(session, batch, "request_reused")
            session.add(
                BatchAssessmentRequest(
                    batch_id=batch.id,
                    actor_id=actor_id,
                    key_sha256=key_sha,
                    request_sha256=request_sha,
                )
            )
            return progress(batch, self._finish(session, batch))

    def _prior_assessment(self, session, batch, item, snapshot):
        found = session.scalar(
            select(Assessment)
            .join(ModelScore, ModelScore.id == Assessment.score_id)
            .join(Decision, Decision.id == Assessment.decision_id)
            .where(
                Assessment.case_id == item.case_id,
                Assessment.case_version == item.case_version,
                ModelScore.model_sha256 == batch.model_sha256,
                Assessment.input_sha256 == snapshot["input_sha256"],
                Decision.mode == batch.policy,
                Decision.policy_version == batch.policy_version,
            )
            .order_by(Assessment.version.desc())
            .limit(1)
        )
        if found:
            _read(session, found)
        return found

    def _active_job(self, session, batch, item, snapshot):
        rows = session.scalars(
            select(AssessmentJob)
            .where(
                AssessmentJob.case_id == item.case_id,
                AssessmentJob.expected_version == item.case_version,
                AssessmentJob.policy == batch.policy,
                AssessmentJob.status.in_(["pending", "running"]),
            )
            .order_by(AssessmentJob.created_at)
            .limit(25)
        )
        for job in rows:
            if job.snapshot != snapshot or job.request_sha256 != _request(
                job.actor_id, job.case_id, job.expected_version, job.run_id, job.policy, snapshot
            ):
                continue
            if (
                session.scalar(
                    select(Case.id).where(
                        Case.id == item.case_id, visible_cases(SimpleNamespace(id=job.actor_id))
                    )
                )
                is None
            ):
                continue
            try:
                check_batch_job(session, job)
            except AssessmentNotFound:
                continue
            return job
        return None

    def _pressure(self, session, batch, reason, seconds):
        now = _now(session)
        batch.backpressure_count += 1
        batch.reason_code = reason
        batch.available_at = now + timedelta(seconds=max(1, seconds))
        if self.telemetry is not None:
            self.telemetry.observe(
                "api.queue_saturation" if reason == "queue_capacity" else "api.queue_contention"
            )
        event(session, batch, "backpressure", reason=reason)

    @safe
    def advance(self, batch_id):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            stub = session.get(BatchAssessment, batch_id)
            if stub is None:
                return None
            actor = session.scalar(select(User).where(User.id == stub.actor_id).with_for_update())
            batch = session.scalar(
                select(BatchAssessment)
                .where(BatchAssessment.id == batch_id)
                .with_for_update(skip_locked=True)
            )
            if batch is None:
                return None
            if batch.status != "active":
                return progress(batch, counts(session, batch.id))
            now = _now(session)
            if _aware(batch.available_at) > now:
                return progress(batch, counts(session, batch.id))
            stop_reason = (
                "authorization_changed"
                if actor is None or not actor.active or actor.role != "admin"
                else (
                    "provenance_changed"
                    if batch.model_sha256 != MODEL_SHA
                    or batch.model_version != MODEL_VERSION
                    or batch.policy_sha256 != POLICY_SHA256
                    or batch.policy_version != POLICY_VERSION
                    else None
                )
            )
            if stop_reason:
                session.execute(
                    update(BatchAssessmentItem)
                    .where(
                        BatchAssessmentItem.batch_id == batch.id,
                        BatchAssessmentItem.status == "ready",
                    )
                    .values(status="failed", reason_code=stop_reason)
                )
                batch.status, batch.reason_code = "stopped", stop_reason
                batch.finished_at = batch.updated_at = now
                event(session, batch, "stopped", reason=stop_reason)
                session.flush()
                return progress(batch, counts(session, batch.id))
            items = session.scalars(
                select(BatchAssessmentItem)
                .where(
                    BatchAssessmentItem.batch_id == batch.id, BatchAssessmentItem.status == "ready"
                )
                .order_by(BatchAssessmentItem.source_row_number)
                .limit(batch.group_size)
                .with_for_update()
            ).all()
            batch.available_at = now + timedelta(
                seconds=self.settings.batch_assessment_interval_seconds
            )
            batch.updated_at = now
            batch.reason_code = None
            dispatched, reused, skipped = 0, 0, 0
            for item in items:
                try:
                    case = _locked_case(session, batch.actor_id, item.case_id)
                    if (
                        session.scalar(
                            select(Case.id).where(Case.id == case.id, visible_cases(actor))
                        )
                        is None
                    ):
                        raise AssessmentNotFound("case_not_found")
                    if (
                        case.version != item.case_version
                        or case.alert_id != item.alert_id
                        or case.status == "closed"
                    ):
                        item.status, item.reason_code = "skipped", "case_changed"
                        skipped += 1
                        continue
                    snapshot, _ = _snapshot(session, case)
                    prior = self._prior_assessment(session, batch, item, snapshot)
                    if prior:
                        item.status, item.reason_code, item.assessment_id = (
                            "skipped",
                            "already_assessed",
                            prior.id,
                        )
                        skipped += 1
                        continue
                    existing = self._active_job(session, batch, item, snapshot)
                    if existing:
                        item.status, item.job_id = "job", existing.id
                        reused += 1
                        continue
                    # Each new job shares the normal authenticated request budget and capacity.
                    _budget(session, batch.actor_id, self.settings)
                    result, _ = self.queue.enqueue_in_transaction(
                        session,
                        actor_id=batch.actor_id,
                        case_id=item.case_id,
                        expected_version=item.case_version,
                        run_id=item.run_id,
                        idempotency_key=f"batch.{batch.id}.{item.case_id}",
                        policy=batch.policy,
                        capacity=self.settings.assessment_queue_capacity,
                        request_audit=True,
                    )
                    item.status, item.job_id, item.originated = "job", UUID(result["job_id"]), True
                    dispatched += 1
                except QueueFull:
                    self._pressure(
                        session,
                        batch,
                        "queue_capacity",
                        self.settings.batch_assessment_interval_seconds,
                    )
                    break
                except AssessmentRateLimited as error:
                    self._pressure(session, batch, "rate_limit", error.retry_after)
                    break
                except AssessmentNotFound:
                    item.status, item.reason_code = "failed", "authorization_changed"
                except AssessmentConflict:
                    item.status, item.reason_code = "skipped", "case_changed"
                except AssessmentUnavailable:
                    # Corrupt/unavailable input is a case-level manual-review outcome, not a fake score.
                    item.status, item.reason_code = "failed", "case_unavailable"
            if items:
                event(
                    session,
                    batch,
                    "group_dispatched",
                    new_jobs=dispatched,
                    reused_jobs=reused,
                    skipped=skipped,
                )
            c = self._finish(session, batch)
            return progress(batch, c)

    @safe
    def run_once(self):
        with Session(self.engine) as session:
            _timeouts(session)
            batch_id = session.scalar(
                select(BatchAssessment.id)
                .where(
                    BatchAssessment.status == "active",
                    BatchAssessment.available_at <= _now(session),
                )
                .order_by(BatchAssessment.available_at, BatchAssessment.id)
                .limit(1)
            )
        return self.advance(batch_id) if batch_id else None

    @safe
    def get(self, actor_id, batch_id, *, offset=None, limit=10):
        if offset is not None and (
            type(offset) is not int
            or not 0 <= offset <= 10000
            or type(limit) is not int
            or not 1 <= limit <= 25
        ):
            raise AssessmentConflict("invalid_batch_page")
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            batch = self._authorized(session, actor_id, batch_id)
            c = self._finish(session, batch)
            event(session, batch, "status_read" if offset is None else "results_read")
            if offset is None:
                return progress(batch, c)
            results = list(self._results_in_session(session, batch, offset, limit))
            return BatchResultsPage(
                batch_id=batch_id, total=c["total_cases"], offset=offset, limit=limit, items=results
            )

    def _results_in_session(self, session, batch, offset, limit):
        batch_id = batch.id
        actor_id = batch.actor_id
        rows = session.execute(
            select(BatchAssessmentItem, AssessmentJob)
            .outerjoin(AssessmentJob, AssessmentJob.id == BatchAssessmentItem.job_id)
            .where(BatchAssessmentItem.batch_id == batch_id)
            .order_by(BatchAssessmentItem.source_row_number)
            .offset(offset)
            .limit(limit)
        ).all()
        for item, job in rows:
            _locked_case(session, actor_id, item.case_id)
            assessment = None
            stored_id = job.assessment_id if job else item.assessment_id
            if stored_id:
                stored = session.scalar(
                    select(Assessment).where(
                        Assessment.id == stored_id, Assessment.case_id == item.case_id
                    )
                )
                if stored is None:
                    raise AssessmentUnavailable("batch_result_unavailable")
                assessment = _detail(_read(session, stored))
                if (
                    assessment.model_sha256 != batch.model_sha256
                    or assessment.selected_policy != batch.policy
                    or assessment.policy_version != batch.policy_version
                ):
                    raise AssessmentUnavailable("batch_result_unavailable")
            state = (
                (
                    "queued"
                    if job.status == "pending"
                    else "failed_manual_review"
                    if job.status == "failed"
                    else job.status
                )
                if job
                else {
                    "ready": "pending_dispatch",
                    "failed": "failed_manual_review",
                    "skipped": "skipped",
                }[item.status]
            )
            reason = job.failure_code if job and job.failure_code in FAILURES else item.reason_code
            yield (
                {
                    "case_id": item.case_id,
                    "source_row_number": item.source_row_number,
                    "outcome": state,
                    "reason_code": reason,
                    "job_id": job.id if job else None,
                    "retrying": bool(job and job.status == "pending" and job.attempts > 0),
                    "attempts": job.attempts if job else 0,
                    "assessment": assessment,
                }
            )


class BatchDispatcher:
    def __init__(self, service):
        self.service = service
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        def run():
            while not self.stop.wait(self.service.settings.batch_assessment_interval_seconds):
                try:
                    for _ in range(self.service.settings.batch_assessment_groups_per_tick):
                        if self.stop.is_set() or self.service.run_once() is None:
                            break
                except Exception:
                    logging.getLogger("trueflag.security").warning(
                        "batch.dispatch.unavailable", extra={"correlation_id": uuid4().hex}
                    )

        self.thread = threading.Thread(target=run, daemon=True, name="batch-assessment-dispatch")
        self.thread.start()
        return self

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
