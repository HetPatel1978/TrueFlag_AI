"""PostgreSQL queue: idempotent envelopes, DB-clock leases, fencing and atomic publication."""

import functools
import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AssessmentJob, AssessmentWorker, AuditEvent, User
from app.services.assessments import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
    AssessmentService,
    _arguments,
    _locked_case,
    _prior,
    _read,
    _request,
    _snapshot,
)
from app.services.ingestion import digest

MAX_ATTEMPTS = 3
FAILURES = {
    "execution_timeout",
    "child_failed",
    "invalid_child_output",
    "lease_expired",
    "database_unavailable",
    "processing_unavailable",
    "authorization_changed",
    "stale_case",
}


class JobError(AssessmentError):
    pass


class JobUnavailable(JobError):
    pass


class WorkerDenied(JobError):
    pass


class LeaseLost(JobError):
    pass


def safe(method):
    @functools.wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except AssessmentError:
            raise
        except SQLAlchemyError:
            raise JobUnavailable("job_database_unavailable") from None
        except Exception:
            raise JobUnavailable("job_processing_unavailable") from None

    return call


@dataclass(frozen=True)
class WorkerLimits:
    lease_seconds: int = 30
    timeout_seconds: int = 120
    heartbeat_seconds: int = 5

    def __post_init__(self):
        if (
            any(
                type(x) is not int
                for x in (
                    self.lease_seconds,
                    self.timeout_seconds,
                    self.heartbeat_seconds,
                )
            )
            or not 3 <= self.lease_seconds <= 60
            or not 1 <= self.timeout_seconds <= 300
            or not 1 <= self.heartbeat_seconds <= self.lease_seconds // 3
        ):
            raise JobError("invalid_worker_limits")


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    lease_token: UUID
    worker_id: UUID


def _token_hash(token):
    if type(token) is not str or re.fullmatch(r"[a-f0-9]{64}", token, re.ASCII) is None:
        raise WorkerDenied("worker_not_authorized")
    return hashlib.sha256(token.encode()).hexdigest()


def _worker(session, token):
    identity = session.scalar(
        select(AssessmentWorker)
        .where(
            AssessmentWorker.token_sha256 == _token_hash(token),
            AssessmentWorker.active.is_(True),
        )
        .with_for_update(read=True)
    )
    if identity is None:
        raise WorkerDenied("worker_not_authorized")
    return identity.id


def _now(session):
    return session.scalar(select(func.clock_timestamp()))


def _timeouts(session):
    # No queue operation waits indefinitely for database locks or statements.
    session.execute(text("SET LOCAL lock_timeout = '2s'"))
    session.execute(text("SET LOCAL statement_timeout = '5s'"))


def _leased(session, claim, worker_id, *, allow_expired=False):
    if (
        type(claim) is not Claim
        or any(
            type(x) is not UUID
            for x in (
                claim.job_id,
                claim.worker_id,
                claim.lease_token,
            )
        )
        or worker_id != claim.worker_id
    ):
        raise LeaseLost("job_lease_lost")
    now = _now(session)
    query = select(AssessmentJob).where(
        AssessmentJob.id == claim.job_id,
        AssessmentJob.status == "running",
        AssessmentJob.worker_id == worker_id,
        AssessmentJob.lease_token == claim.lease_token,
    )
    if not allow_expired:
        query = query.where(AssessmentJob.lease_until > now, AssessmentJob.deadline > now)
    job = session.scalar(query.with_for_update())
    if job is None:
        raise LeaseLost("job_lease_lost")
    return job


def _event(session, job, action, **details):
    session.add(
        AuditEvent(
            actor_id=job.actor_id,
            action="assessment.job." + action,
            resource_id=str(job.id),
            details={
                "job_id": str(job.id),
                "case_id": str(job.case_id),
                "run_id": str(job.run_id),
                "attempt": job.attempts,
                "worker_id": str(job.worker_id) if job.worker_id else None,
                **details,
            },
        )
    )


def _view(job):
    return {
        "job_id": str(job.id),
        "case_id": str(job.case_id),
        "run_id": str(job.run_id),
        "status": job.status,
        "attempts": job.attempts,
        "policy": job.policy,
        "assessment_id": str(job.assessment_id) if job.assessment_id else None,
        "failure_code": job.failure_code,
        "fallback_route": job.fallback_route,
        "human_decision_required": True,
    }


def _fail(session, job, reason, retryable):
    reason = reason if reason in FAILURES else "processing_unavailable"
    job.failure_code = reason
    job.status = "pending" if retryable and job.attempts < MAX_ATTEMPTS else "failed"
    job.fallback_route = "manual_review" if job.status == "failed" else None
    job.available_at = _now(session) + timedelta(seconds=min(60, 5 * 2 ** (job.attempts - 1)))
    job.lease_token = job.lease_until = job.deadline = None
    _event(session, job, "retry_scheduled" if job.status == "pending" else "failed", reason=reason)


class AssessmentJobService:
    def __init__(self, engine, artifact_root=None, limits=None):
        if engine.dialect.name != "postgresql":
            raise JobUnavailable("postgresql_required")
        self.engine = engine
        self.assessments = AssessmentService(engine, artifact_root)
        self.limits = WorkerLimits() if limits is None else limits
        if type(self.limits) is not WorkerLimits:
            raise JobError("invalid_worker_limits")

    @safe
    def register_worker(self, *, admin_id, name, token):
        if (
            type(admin_id) is not UUID
            or type(name) is not str
            or not re.fullmatch(
                r"[a-z][a-z0-9-]{2,63}",
                name,
                re.ASCII,
            )
        ):
            raise JobError("invalid_worker_identity")
        token_sha = _token_hash(token)
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            admin = session.scalar(
                select(User.id)
                .where(
                    User.id == admin_id,
                    User.active.is_(True),
                    User.role == "admin",
                )
                .with_for_update(read=True)
            )
            if admin is None:
                raise WorkerDenied("worker_provisioning_denied")
            worker = AssessmentWorker(name=name, token_sha256=token_sha, provisioned_by=admin_id)
            session.add(worker)
            session.flush()
            session.add(
                AuditEvent(
                    actor_id=admin_id,
                    action="worker.provisioned",
                    resource_id=str(worker.id),
                    details={"permission": "assessment.execute"},
                )
            )
            return worker.id

    @safe
    def revoke_worker(self, *, admin_id, worker_id):
        if type(admin_id) is not UUID or type(worker_id) is not UUID:
            raise JobError("invalid_worker_identity")
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            admin = session.scalar(
                select(User.id)
                .where(
                    User.id == admin_id,
                    User.active.is_(True),
                    User.role == "admin",
                )
                .with_for_update(read=True)
            )
            if admin is None:
                raise WorkerDenied("worker_provisioning_denied")
            worker = session.get(AssessmentWorker, worker_id, with_for_update=True)
            if worker is None:
                raise WorkerDenied("worker_not_authorized")
            worker.active = False
            session.add(
                AuditEvent(actor_id=admin_id, action="worker.revoked", resource_id=str(worker_id))
            )

    @safe
    def enqueue(self, *, actor_id, case_id, expected_version, run_id, idempotency_key, policy):
        _arguments(actor_id, case_id, expected_version, run_id, idempotency_key, policy)
        key_sha = digest({"actor_id": str(actor_id), "key": idempotency_key})
        for attempt in range(2):
            try:
                with Session(self.engine) as session, session.begin():
                    _timeouts(session)
                    case = _locked_case(session, actor_id, case_id)
                    snapshot, _ = _snapshot(session, case)
                    request_sha = _request(
                        actor_id, case_id, expected_version, run_id, policy, snapshot
                    )
                    rows = session.scalars(
                        select(AssessmentJob).where(
                            or_(
                                AssessmentJob.run_id == run_id,
                                AssessmentJob.key_sha256 == key_sha,
                            )
                        )
                    ).all()
                    if rows:
                        if (
                            len(rows) != 1
                            or rows[0].request_sha256 != request_sha
                            or rows[0].key_sha256 != key_sha
                            or rows[0].run_id != run_id
                        ):
                            raise AssessmentConflict("job_idempotency_conflict")
                        return _view(rows[0]), False
                    prior = _prior(session, key_sha, run_id, request_sha)
                    if prior is None and (
                        case.version != expected_version or case.status == "closed"
                    ):
                        raise AssessmentConflict("job_stale_case")
                    if prior is not None:
                        _read(session, prior)
                    job = AssessmentJob(
                        id=uuid4(),
                        case_id=case_id,
                        actor_id=actor_id,
                        run_id=run_id,
                        expected_version=expected_version,
                        policy=policy,
                        key_sha256=key_sha,
                        request_sha256=request_sha,
                        snapshot=snapshot,
                        attempts=0,
                        status="succeeded" if prior else "pending",
                        available_at=_now(session),
                        assessment_id=prior.id if prior else None,
                    )
                    session.add(job)
                    session.flush()
                    _event(session, job, "enqueued", reused_assessment=prior is not None)
                    return _view(job), True
            except IntegrityError as error:
                if getattr(getattr(error.orig, "diag", None), "constraint_name", None) not in {
                    "uq_job_key",
                    "uq_job_run",
                }:
                    raise
                if attempt:
                    raise AssessmentConflict("job_idempotency_conflict") from None

    @safe
    def get(self, *, actor_id, case_id, job_id):
        if any(type(x) is not UUID for x in (actor_id, case_id, job_id)):
            raise JobError("invalid_job_request")
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _locked_case(session, actor_id, case_id)
            job = session.scalar(
                select(AssessmentJob).where(
                    AssessmentJob.id == job_id,
                    AssessmentJob.case_id == case_id,
                )
            )
            if job is None:
                raise AssessmentNotFound("assessment_not_found")
            return _view(job)

    @safe
    def claim(self, token):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            worker_id = _worker(session, token)
            now = _now(session)
            job = session.scalar(
                select(AssessmentJob)
                .where(
                    AssessmentJob.status == "pending",
                    AssessmentJob.available_at <= now,
                    AssessmentJob.attempts < MAX_ATTEMPTS,
                )
                .order_by(AssessmentJob.available_at, AssessmentJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            job.worker_id = worker_id
            job.lease_token = uuid4()
            job.deadline = now + timedelta(seconds=self.limits.timeout_seconds)
            job.lease_until = min(job.deadline, now + timedelta(seconds=self.limits.lease_seconds))
            _event(
                session,
                job,
                "claimed",
                lease_until=job.lease_until.isoformat(),
                deadline=job.deadline.isoformat(),
            )
            return Claim(job.id, job.lease_token, worker_id)

    @safe
    def heartbeat(self, token, claim):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            job = _leased(session, claim, _worker(session, token))
            job.lease_until = min(
                job.deadline, _now(session) + timedelta(seconds=self.limits.lease_seconds)
            )

    @safe
    def recover_expired(self, token):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _worker(session, token)
            now = _now(session)
            jobs = session.scalars(
                select(AssessmentJob)
                .where(
                    AssessmentJob.status == "running",
                    or_(AssessmentJob.lease_until <= now, AssessmentJob.deadline <= now),
                )
                .order_by(AssessmentJob.lease_until, AssessmentJob.id)
                .limit(100)
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                _fail(session, job, "lease_expired", True)
            return len(jobs)

    @safe
    def prepare(self, token, claim):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            worker_id = _worker(session, token)
            # Read identity first; re-fetch with fencing after taking the case lock.
            row = session.get(AssessmentJob, claim.job_id)
            if row is None:
                raise LeaseLost("job_lease_lost")
            case = _locked_case(session, row.actor_id, row.case_id)
            job = _leased(session, claim, worker_id)
            snapshot, features = _snapshot(session, case)
            if (
                snapshot != job.snapshot
                or case.status == "closed"
                or _request(
                    job.actor_id,
                    job.case_id,
                    job.expected_version,
                    job.run_id,
                    job.policy,
                    snapshot,
                )
                != job.request_sha256
            ):
                raise AssessmentConflict("job_stale_case")
            return {
                "actor_id": job.actor_id,
                "case_id": job.case_id,
                "policy": job.policy,
                "snapshot": snapshot,
                "features": features,
            }

    @safe
    def complete(self, token, claim, result):
        # Trusted worker-only method. JSON comes from our fixed isolated producer, never HTTP.
        data = self.prepare(token, claim)
        self.assessments._validate_result(
            result, data["case_id"], data["features"], data["policy"], data["snapshot"]
        )
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            worker_id = _worker(session, token)
            _locked_case(session, data["actor_id"], data["case_id"])
            job = _leased(session, claim, worker_id)
            assessment, _ = self.assessments._persist_in_session(
                session,
                job.actor_id,
                job.case_id,
                job.expected_version,
                job.run_id,
                job.key_sha256,
                job.request_sha256,
                job.snapshot,
                result,
            )
            # Never publish after a deadline passed while database writes were in progress.
            now = _now(session)
            if job.lease_until <= now or job.deadline <= now:
                raise LeaseLost("job_lease_lost")
            job.status = "succeeded"
            job.assessment_id = UUID(assessment["assessment_id"])
            job.failure_code = None
            job.lease_token = job.lease_until = job.deadline = None
            _event(session, job, "succeeded", assessment_id=str(job.assessment_id))
            session.flush()
            return _view(job)

    @safe
    def fail(self, token, claim, reason, *, retryable=True):
        if type(retryable) is not bool:
            raise JobError("invalid_failure_request")
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            # The unchanged generation may abort after timeout, but never publish a result.
            job = _leased(session, claim, _worker(session, token), allow_expired=True)
            _fail(session, job, reason, retryable)
            session.flush()
            return _view(job)
