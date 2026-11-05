"""Durable evidence-only state machine. No inference, provider, regulatory or case actions."""

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text

from app.models import Alert
from app.models.investigations import (
    InvestigationJob,
    InvestigationPacket,
    InvestigationRequestKey,
    InvestigationRun,
    InvestigationWorker,
)
from app.schemas.investigations import (
    COORDINATOR_VERSION,
    InputManifest,
    InvestigationPacketBody,
    InvestigationRequest,
)
from app.services.evidence import (
    EvidenceConflict,
    EvidenceError,
    EvidenceNotFound,
    EvidenceUnavailable,
    actor_lock,
    atomic,
    audit,
)
from app.services.evidence_read import EvidenceReadService, ReadLimit, SnapshotStale
from app.services.ingestion import digest
from app.services.investigation_packets import assemble
from app.services.investigation_verifier import VerificationFailed, verify_packet

FAILURES = {
    "lease_expired",
    "execution_timeout",
    "processing_unavailable",
    "verification_failed",
    "input_invalidated",
    "authorization_revoked",
    "worker_revoked",
    "resource_limit",
}


class InvestigationInvalid(EvidenceError):
    pass


class InvestigationBusy(EvidenceUnavailable):
    pass


class InvestigationLeaseLost(EvidenceError):
    pass


@dataclass(frozen=True)
class InvestigationClaim:
    run_id: UUID
    worker_id: UUID
    lease_token: UUID


def token_hash(token):
    if type(token) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise EvidenceNotFound("investigation_worker_not_found")
    return hashlib.sha256(b"trueflag.investigation.evidence-only.v1:" + token.encode()).hexdigest()


class InvestigationCoordinator:
    def __init__(self, engine, settings, *, queue_capacity=100, actor_capacity=3):
        if (
            type(queue_capacity) is not int
            or not 1 <= queue_capacity <= 100
            or type(actor_capacity) is not int
            or not 1 <= actor_capacity <= 3
        ):
            raise ValueError("Invalid investigation capacity")
        self.engine, self.settings = engine, settings
        self.reader = EvidenceReadService(engine, settings)
        self.queue_capacity, self.actor_capacity = queue_capacity, actor_capacity

    def _gate(self, session):
        # Short coordination transactions are serialized; assembly executes outside this gate.
        session.execute(
            text(
                "SELECT pg_advisory_xact_lock(6075990650000000000 + 'investigation_jobs'::regclass::oid::bigint)"
            )
        )

    def _now(self, session):
        return session.scalar(select(func.clock_timestamp()))

    def _worker(self, session, token):
        worker = session.scalar(
            select(InvestigationWorker)
            .where(
                InvestigationWorker.token_sha256 == token_hash(token),
                InvestigationWorker.active.is_(True),
            )
            .with_for_update(read=True)
        )
        if worker is None:
            raise EvidenceNotFound("investigation_worker_not_found")
        return worker

    def _run(self, session, identity):
        if type(identity) is not UUID:
            raise InvestigationInvalid("invalid_investigation_identity")
        run = session.get(InvestigationRun, identity)
        if run is None:
            raise EvidenceNotFound("investigation_not_found")
        return run

    def _manifest(self, session, actor, case, request):
        context = self.reader._context(session, actor, case, assessment_id=request.assessment_id)
        if (
            context.snapshot.case_version,
            context.snapshot.evidence_revision,
            context.snapshot.access_revision,
        ) != (
            request.expected_case_version,
            request.expected_evidence_revision,
            request.expected_access_revision,
        ):
            raise SnapshotStale("investigation_input_invalidated")
        model = self.reader._assessment(session, context)
        manifest = InputManifest(
            actor_id=actor,
            case_id=case,
            alert_id=context.case.alert_id,
            alert_feature_fingerprint_sha256=digest(
                {
                    "hash_schema": "trueflag.investigation-alert-fingerprint.v1",
                    "alert_id": str(context.case.alert_id),
                    "features": session.get(Alert, context.case.alert_id).features,
                }
            ),
            request=request,
            snapshot=context.snapshot,
            sources=context.sources,
            evidence=context.refs,
            assessment_sha256=digest(model.model_dump(mode="json")) if model else None,
        )
        if len(manifest.model_dump_json(warnings="error").encode()) > 131072:
            raise ReadLimit("investigation_manifest_limit")
        return context, manifest

    def _current(self, session, run):
        manifest = InputManifest.model_validate(run.input_manifest)
        context, current = self._manifest(session, run.actor_id, run.case_id, manifest.request)
        if (
            run.coordinator_version != COORDINATOR_VERSION
            or digest(current.model_dump(mode="json")) != run.manifest_sha256
        ):
            raise SnapshotStale("investigation_input_invalidated")
        return context, manifest

    def _view(self, job):
        return dict(
            run_id=str(job.run_id),
            status=job.status,
            attempts=job.attempts,
            error_code=job.error_code,
            human_review_required=True,
            mode="deterministic_evidence_only",
        )

    def _clear(self, job):
        job.worker_id = job.lease_token = job.lease_until = job.deadline = None

    def _event(self, session, run, action, job=None, **details):
        audit(
            session,
            run.actor_id,
            "investigation." + action,
            run.id,
            manifest_sha256=run.manifest_sha256,
            attempt=job.attempts if job else 0,
            **details,
        )

    @atomic
    def register_worker(self, session, admin_id, name, token):
        self._gate(session)
        actor_lock(session, admin_id, write=True)
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", name):
            raise InvestigationInvalid("invalid_investigation_worker")
        sha = token_hash(token)
        prior = session.scalar(select(InvestigationWorker).where(InvestigationWorker.name == name))
        if prior:
            if prior.active and prior.token_sha256 == sha and prior.provisioned_by == admin_id:
                return prior.id
            raise EvidenceConflict("investigation_worker_conflict")
        if session.scalar(
            select(InvestigationWorker.id).where(InvestigationWorker.token_sha256 == sha)
        ):
            raise EvidenceConflict("investigation_worker_conflict")
        worker = InvestigationWorker(name=name, token_sha256=sha, provisioned_by=admin_id)
        session.add(worker)
        session.flush()
        audit(
            session,
            admin_id,
            "investigation.worker_registered",
            worker.id,
            permission="investigation.evidence.execute",
        )
        return worker.id

    @atomic
    def revoke_worker(self, session, admin_id, worker_id):
        self._gate(session)
        actor_lock(session, admin_id, write=True)
        if type(worker_id) is not UUID:
            raise InvestigationInvalid("invalid_investigation_identity")
        worker = session.get(InvestigationWorker, worker_id)
        if worker is None:
            raise EvidenceNotFound("investigation_worker_not_found")
        if worker.active:
            worker.active = False
            audit(session, admin_id, "investigation.worker_revoked", worker.id)

    @atomic
    def request(self, session, actor_id, case_id, idempotency_key, request):
        self._gate(session)
        if (
            not isinstance(request, InvestigationRequest)
            or type(idempotency_key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", idempotency_key)
        ):
            raise InvestigationInvalid("invalid_investigation_request")
        request = InvestigationRequest.model_validate_json(
            request.model_dump_json(warnings="error")
        )
        context, manifest = self._manifest(session, actor_id, case_id, request)
        sha = digest(manifest.model_dump(mode="json"))
        prior = session.get(InvestigationRequestKey, (actor_id, idempotency_key))
        if prior:
            if prior.manifest_sha256 != sha:
                raise EvidenceConflict("investigation_idempotency_conflict")
            return self._view(session.get(InvestigationJob, prior.run_id))
        run = session.scalar(
            select(InvestigationRun).where(
                InvestigationRun.actor_id == actor_id,
                InvestigationRun.case_id == case_id,
                InvestigationRun.manifest_sha256 == sha,
            )
        )
        if run is None:
            active = (
                select(func.count())
                .select_from(InvestigationJob)
                .join(InvestigationRun)
                .where(InvestigationJob.status.in_(["pending", "running"]))
            )
            if (
                session.scalar(active) >= self.queue_capacity
                or session.scalar(active.where(InvestigationRun.actor_id == actor_id))
                >= self.actor_capacity
            ):
                raise InvestigationBusy("investigation_queue_full")
            run = InvestigationRun(
                id=uuid4(),
                actor_id=actor_id,
                case_id=case_id,
                alert_id=context.case.alert_id,
                assessment_id=request.assessment_id,
                manifest_sha256=sha,
                input_manifest=manifest.model_dump(mode="json"),
                coordinator_version=COORDINATOR_VERSION,
            )
            session.add(run)
            session.flush()
            session.add(
                InvestigationJob(
                    run_id=run.id, status="pending", attempts=0, not_before=self._now(session)
                )
            )
            self._event(session, run, "requested")
        elif (
            session.scalar(
                select(func.count())
                .select_from(InvestigationRequestKey)
                .where(InvestigationRequestKey.run_id == run.id)
            )
            >= 100
        ):
            raise InvestigationBusy("investigation_idempotency_capacity")
        session.add(
            InvestigationRequestKey(
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                run_id=run.id,
                manifest_sha256=sha,
            )
        )
        session.flush()
        return self._view(session.get(InvestigationJob, run.id))

    @atomic
    def claim(self, session, token):
        self._gate(session)
        worker = self._worker(session, token)
        now = self._now(session)
        job = session.scalar(
            select(InvestigationJob)
            .where(
                InvestigationJob.status == "pending",
                InvestigationJob.not_before <= now,
                InvestigationJob.attempts < 3,
            )
            .order_by(InvestigationJob.not_before, InvestigationJob.run_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.worker_id = worker.id
        job.lease_token = uuid4()
        job.lease_until = now + timedelta(seconds=60)
        job.deadline = now + timedelta(seconds=45)
        job.error_code = None
        self._event(
            session, self._run(session, job.run_id), "claimed", job, worker_id=str(worker.id)
        )
        return InvestigationClaim(job.run_id, worker.id, job.lease_token)

    def _leased(self, session, token, claim, *, expired=False):
        if not isinstance(claim, InvestigationClaim) or any(
            type(v) is not UUID for v in (claim.run_id, claim.worker_id, claim.lease_token)
        ):
            raise InvestigationLeaseLost("investigation_lease_lost")
        worker = self._worker(session, token)
        job = session.scalar(
            select(InvestigationJob)
            .where(InvestigationJob.run_id == claim.run_id)
            .with_for_update()
        )
        now = self._now(session)
        if (
            job is None
            or job.status != "running"
            or job.worker_id != worker.id
            or worker.id != claim.worker_id
            or job.lease_token != claim.lease_token
            or not expired
            and (job.lease_until <= now or job.deadline <= now)
        ):
            raise InvestigationLeaseLost("investigation_lease_lost")
        return job

    @atomic
    def current(self, session, token, claim):
        self._gate(session)
        self._leased(session, token, claim)
        run = self._run(session, claim.run_id)
        self._current(session, run)
        return run

    def assemble(self, token, claim):
        started = time.monotonic()
        steps = 0
        run = self.current(token, claim)
        manifest = InputManifest.model_validate(run.input_manifest)

        def step(operation):
            nonlocal steps
            if steps >= 32 or time.monotonic() - started >= 45:
                raise ReadLimit("investigation_execution_limit")
            self.current(token, claim)
            steps += 1
            value = operation()
            if time.monotonic() - started >= 45:
                raise ReadLimit("investigation_execution_limit")
            return value

        body = assemble(self.reader, run, manifest, step)
        self.current(token, claim)
        if len(body.model_dump_json(warnings="error").encode()) > 524288:
            raise ReadLimit("investigation_packet_limit")
        return body

    @atomic
    def complete(self, session, token, claim, body):
        self._gate(session)
        job = self._leased(session, token, claim)
        run = self._run(session, claim.run_id)
        context, manifest = self._current(session, run)
        if not isinstance(body, InvestigationPacketBody):
            raise VerificationFailed("investigation_verification_failed")
        body = InvestigationPacketBody.model_validate_json(body.model_dump_json(warnings="error"))
        if body.run_id != run.id or len(body.model_dump_json(warnings="error").encode()) > 524288:
            raise VerificationFailed("investigation_verification_failed")
        verification = verify_packet(session, self.reader, context, manifest, body)
        now = self._now(session)
        if job.deadline <= now or job.lease_until <= now:
            raise InvestigationLeaseLost("investigation_lease_lost")
        session.add(
            InvestigationPacket(
                run_id=run.id,
                manifest_sha256=run.manifest_sha256,
                body=body.model_dump(mode="json"),
                content_sha256=digest(body.model_dump(mode="json")),
                verification=verification,
            )
        )
        job.status = "abstained" if body.outcome == "abstained" else "succeeded"
        self._clear(job)
        self._event(
            session,
            run,
            "published",
            job,
            packet_sha256=verification["packet_sha256"],
            verifier=verification["verifier"],
            outcome=body.outcome,
        )
        session.flush()
        return self._view(job)

    def _fail(self, session, job, reason, *, retryable, invalidated=False):
        run = self._run(session, job.run_id)
        job.error_code = reason
        self._clear(job)
        job.status = (
            "invalidated"
            if invalidated
            else "pending"
            if retryable and job.attempts < 3
            else "failed"
        )
        if job.status == "pending":
            job.not_before = self._now(session) + timedelta(seconds=min(30, 2**job.attempts))
        self._event(
            session,
            run,
            "attempt_failed",
            job,
            reason=reason,
            retryable=job.status == "pending",
            manual_review_required=True,
        )
        return self._view(job)

    @atomic
    def fail(self, session, token, claim, reason, *, retryable=False, invalidated=False):
        self._gate(session)
        if reason not in FAILURES or type(retryable) is not bool or type(invalidated) is not bool:
            raise InvestigationInvalid("invalid_investigation_failure")
        job = self._leased(session, token, claim, expired=True)
        return self._fail(session, job, reason, retryable=retryable, invalidated=invalidated)

    @atomic
    def recover(self, session, token):
        self._gate(session)
        self._worker(session, token)
        now = self._now(session)
        jobs = session.scalars(
            select(InvestigationJob)
            .join(InvestigationWorker, InvestigationJob.worker_id == InvestigationWorker.id)
            .where(
                InvestigationJob.status == "running",
                or_(
                    InvestigationJob.lease_until <= now,
                    InvestigationJob.deadline <= now,
                    InvestigationWorker.active.is_(False),
                ),
            )
            .order_by(InvestigationJob.run_id)
            .with_for_update(skip_locked=True)
            .limit(20)
        ).all()
        for job in jobs:
            worker = session.get(InvestigationWorker, job.worker_id)
            reason = (
                "worker_revoked"
                if not worker.active
                else "execution_timeout"
                if job.deadline <= now
                else "lease_expired"
            )
            self._fail(session, job, reason, retryable=True)
        return len(jobs)

    @atomic
    def get(self, session, actor_id, case_id, run_id):
        self._gate(session)
        self.reader._context(session, actor_id, case_id)
        run = self._run(session, run_id)
        if run.actor_id != actor_id or run.case_id != case_id:
            raise EvidenceNotFound("investigation_not_found")
        job = session.get(InvestigationJob, run_id)
        try:
            context, manifest = self._current(session, run)
        except SnapshotStale:
            if job.status != "invalidated":
                job.status = "invalidated"
                job.error_code = "input_invalidated"
                self._clear(job)
                self._event(session, run, "invalidated", job)
            return {**self._view(job), "packet": None}
        packet = session.scalar(
            select(InvestigationPacket).where(InvestigationPacket.run_id == run_id)
        )
        if job.status not in {"succeeded", "abstained"}:
            return {**self._view(job), "packet": None}
        if packet is None:
            return {**self._view(job), "packet": None}
        body = InvestigationPacketBody.model_validate(packet.body)
        if (
            digest(packet.body) != packet.content_sha256
            or packet.manifest_sha256 != run.manifest_sha256
        ):
            raise VerificationFailed("investigation_verification_failed")
        verification = verify_packet(session, self.reader, context, manifest, body)
        if verification != packet.verification:
            raise VerificationFailed("investigation_verification_failed")
        self._event(session, run, "read", job, packet_sha256=packet.content_sha256)
        return {
            **self._view(job),
            "packet": body.model_dump(mode="json"),
            "verification": verification,
        }

    def run_once(self, token):
        self.recover(token)
        claim = self.claim(token)
        if claim is None:
            return None
        try:
            return self.complete(token, claim, self.assemble(token, claim))
        except SnapshotStale:
            return self.fail(token, claim, "input_invalidated", invalidated=True)
        except EvidenceNotFound:
            # A revoked worker cannot mutate its old job; a different active worker recovers it.
            try:
                return self.fail(token, claim, "authorization_revoked", invalidated=True)
            except EvidenceNotFound:
                raise EvidenceNotFound("investigation_worker_not_found") from None
        except VerificationFailed:
            return self.fail(token, claim, "verification_failed")
        except ReadLimit:
            return self.fail(token, claim, "resource_limit")
        except InvestigationLeaseLost:
            return None
        except EvidenceError:
            return self.fail(token, claim, "processing_unavailable", retryable=True)
        except Exception:
            return self.fail(token, claim, "processing_unavailable", retryable=True)
