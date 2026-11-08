"""Optional durable simulation stage. Reuses the authorized evidence coordinator/verifier."""

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select

from app.models.investigation_drafts import (
    DraftAttempt,
    DraftJob,
    DraftReceipt,
    DraftRequest,
    DraftRun,
    StoredDraft,
)
from app.models.investigations import InvestigationJob, InvestigationPacket, InvestigationWorker
from app.schemas.investigation_drafts import (
    DRAFT_VERSION,
    PROMPT,
    PROMPT_VERSION,
    DraftBody,
    ProviderConfig,
    ProviderReply,
)
from app.schemas.investigations import InvestigationPacketBody
from app.services.evidence import (
    EvidenceBlocked,
    EvidenceConflict,
    EvidenceError,
    EvidenceNotFound,
    atomic,
    audit,
)
from app.services.evidence_read import SnapshotStale
from app.services.ingestion import digest
from app.services.investigation_coordinator import (
    InvestigationBusy,
    InvestigationCoordinator,
    InvestigationLeaseLost,
)
from app.services.investigation_draft_verifier import minimize, parse_proposal, validate_proposal
from app.services.investigation_provider import ProviderFailure, ProviderLimit, ProviderTimeout
from app.services.investigation_provider_runner import IsolatedSimulationRunner
from app.services.investigation_verifier import VerificationFailed, verify_packet

PROMPT_SHA = hashlib.sha256(PROMPT.encode()).hexdigest()


class InvalidDraftOutput(EvidenceBlocked):
    """Invalid model content is a terminal validation failure, not a DB retry."""


FAILURES = {
    "provider_timeout",
    "provider_unavailable",
    "provider_incomplete",
    "provider_refused",
    "invalid_provider_output",
    "verification_failed",
    "budget_exhausted",
    "authorization_revoked",
    "input_invalidated",
    "worker_revoked",
    "lease_expired",
    "database_unavailable",
}


@dataclass(frozen=True)
class DraftClaim:
    run_id: UUID
    worker_id: UUID
    lease_token: UUID


class InvestigationDraftService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.coordinator = InvestigationCoordinator(engine, settings)
        self._runner = IsolatedSimulationRunner()

    def _enabled(self):
        if (
            self.settings.investigation_external_enabled
            or not self.settings.investigation_simulation_enabled
        ):
            raise EvidenceBlocked("investigation_provider_disabled")

    def _event(self, session, run, action, **details):
        audit(
            session,
            run.actor_id,
            "investigation.draft." + action,
            run.id,
            manifest_sha256=run.manifest_sha256,
            mode="simulation",
            **details,
        )

    def _job_view(self, job):
        return dict(
            draft_run_id=str(job.run_id),
            status=job.status,
            attempts=job.attempts,
            error_code=job.error_code,
            mode="simulation",
            human_review_required=True,
        )

    def _run(self, session, run_id):
        if type(run_id) is not UUID:
            raise EvidenceNotFound("investigation_draft_not_found")
        run = session.get(DraftRun, run_id)
        if run is None:
            raise EvidenceNotFound("investigation_draft_not_found")
        return run

    def _configuration(self, run):
        config = ProviderConfig.model_validate(run.configuration)
        if (
            digest(config.model_dump(mode="json")) != run.config_sha256
            or run.prompt_sha256 != PROMPT_SHA
        ):
            raise SnapshotStale("investigation_draft_invalidated")
        manifest = dict(
            parent_run_id=str(run.parent_run_id),
            parent_manifest_sha256=run.parent_manifest_sha256,
            config_sha256=run.config_sha256,
            prompt_sha256=run.prompt_sha256,
            schema=DRAFT_VERSION,
        )
        if digest(manifest) != run.manifest_sha256:
            raise SnapshotStale("investigation_draft_invalidated")
        return config

    def _packet(self, session, run):
        self._configuration(run)
        parent = self.coordinator._run(session, run.parent_run_id)
        context, manifest = self.coordinator._current(session, parent)
        if parent.actor_id != run.actor_id or parent.manifest_sha256 != run.parent_manifest_sha256:
            raise SnapshotStale("investigation_draft_invalidated")
        job = session.get(InvestigationJob, parent.id)
        if job.status not in {"succeeded", "abstained"}:
            raise SnapshotStale("investigation_draft_invalidated")
        record = session.scalar(
            select(InvestigationPacket).where(InvestigationPacket.run_id == parent.id)
        )
        if (
            record is None
            or digest(record.body) != record.content_sha256
            or record.manifest_sha256 != parent.manifest_sha256
        ):
            raise VerificationFailed("draft_verification_failed")
        packet = InvestigationPacketBody.model_validate(record.body)
        if (
            packet.run_id != parent.id
            or verify_packet(session, self.coordinator.reader, context, manifest, packet)
            != record.verification
        ):
            raise VerificationFailed("draft_verification_failed")
        return packet

    @atomic
    def request(self, session, actor_id, case_id, key, investigation_request, configuration):
        self._enabled()
        if (
            type(key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key)
            or not isinstance(configuration, ProviderConfig)
        ):
            raise EvidenceBlocked("invalid_draft_request")
        config = ProviderConfig.model_validate_json(configuration.model_dump_json(warnings="error"))
        self.coordinator._gate(session)
        # Same transaction: parent evidence admission, child intent, key, job and audit.
        parent_key = "draft-" + digest(dict(actor=str(actor_id), key=key))
        receipt = self.coordinator.request_in_transaction(
            session, actor_id, case_id, parent_key, investigation_request
        )
        parent = self.coordinator._run(session, UUID(receipt["run_id"]))
        csha = digest(config.model_dump(mode="json"))
        msha = digest(
            dict(
                parent_run_id=str(parent.id),
                parent_manifest_sha256=parent.manifest_sha256,
                config_sha256=csha,
                prompt_sha256=PROMPT_SHA,
                schema=DRAFT_VERSION,
            )
        )
        previous = session.get(DraftRequest, (actor_id, key))
        if previous:
            if previous.manifest_sha256 != msha:
                raise EvidenceConflict("draft_idempotency_conflict")
            return self._job_view(session.get(DraftJob, previous.run_id))
        run = session.scalar(
            select(DraftRun).where(
                DraftRun.parent_run_id == parent.id, DraftRun.config_sha256 == csha
            )
        )
        if run is None:
            active = (
                select(func.count())
                .select_from(DraftJob)
                .join(DraftRun)
                .where(DraftJob.status.in_(["pending", "running"]))
            )
            if (
                session.scalar(active) >= 100
                or session.scalar(active.where(DraftRun.actor_id == actor_id)) >= 3
            ):
                raise InvestigationBusy("draft_queue_full")
            run = DraftRun(
                id=uuid4(),
                parent_run_id=parent.id,
                actor_id=actor_id,
                parent_manifest_sha256=parent.manifest_sha256,
                config_sha256=csha,
                manifest_sha256=msha,
                configuration=config.model_dump(mode="json"),
                prompt_sha256=PROMPT_SHA,
            )
            session.add(run)
            session.flush()
            session.add(
                DraftJob(
                    run_id=run.id,
                    status="pending",
                    attempts=0,
                    not_before=self.coordinator._now(session),
                )
            )
            self._event(session, run, "requested", parent_run_id=str(parent.id))
        elif (
            session.scalar(
                select(func.count()).select_from(DraftRequest).where(DraftRequest.run_id == run.id)
            )
            >= 100
        ):
            raise InvestigationBusy("draft_idempotency_capacity")
        session.add(
            DraftRequest(
                actor_id=actor_id, idempotency_key=key, run_id=run.id, manifest_sha256=msha
            )
        )
        session.flush()
        return self._job_view(session.get(DraftJob, run.id))

    def _clear(self, job):
        job.worker_id = job.lease_token = job.lease_until = job.deadline = None

    def _attempt(self, session, job):
        return session.scalar(
            select(DraftAttempt).where(
                DraftAttempt.run_id == job.run_id, DraftAttempt.attempt == job.attempts
            )
        )

    def _receipt(self, session, attempt, status, reply=None, elapsed=None):
        if attempt is not None and not session.scalar(
            select(DraftReceipt.id).where(DraftReceipt.attempt_id == attempt.id)
        ):
            session.add(
                DraftReceipt(
                    attempt_id=attempt.id,
                    status=status,
                    response_sha256=hashlib.sha256(reply.content.encode()).hexdigest()
                    if reply
                    else None,
                    usage=reply.usage.model_dump(mode="json") if reply else None,
                    elapsed_ms=elapsed if elapsed is not None and 0 <= elapsed <= 60000 else None,
                )
            )

    def _fail(
        self, session, job, reason, *, retryable=False, invalidated=False, reply=None, elapsed=None
    ):
        run = self._run(session, job.run_id)
        config = self._configuration(run)
        self._receipt(session, self._attempt(session, job), reason, reply, elapsed)
        job.error_code = reason
        self._clear(job)
        job.status = (
            "invalidated"
            if invalidated
            else "pending"
            if retryable and job.attempts < config.max_attempts
            else "failed"
        )
        if job.status == "pending":
            job.not_before = self.coordinator._now(session) + timedelta(seconds=2**job.attempts)
        self._event(
            session,
            run,
            "attempt_failed",
            attempt=job.attempts,
            reason=reason,
            retryable=job.status == "pending",
            manual_review_required=True,
        )
        return self._job_view(job)

    @atomic
    def claim(self, session, token):
        self._enabled()
        self.coordinator._gate(session)
        worker = self.coordinator._worker(session, token)
        jobs = session.scalars(
            select(DraftJob)
            .join(DraftRun)
            .join(InvestigationJob, DraftRun.parent_run_id == InvestigationJob.run_id)
            .where(
                DraftJob.status == "pending",
                DraftJob.not_before <= self.coordinator._now(session),
                InvestigationJob.status.in_(["succeeded", "abstained", "failed", "invalidated"]),
            )
            .order_by(DraftJob.not_before, DraftJob.run_id)
            .with_for_update(of=DraftJob, skip_locked=True)
            .limit(20)
        ).all()
        for job in jobs:
            run = self._run(session, job.run_id)
            try:
                self._packet(session, run)
            except EvidenceNotFound:
                self._fail(session, job, "authorization_revoked", invalidated=True)
                continue
            except SnapshotStale:
                self._fail(session, job, "input_invalidated", invalidated=True)
                continue
            now = self.coordinator._now(session)
            job.status = "running"
            job.attempts += 1
            job.error_code = None
            job.worker_id = worker.id
            job.lease_token = uuid4()
            job.lease_until = now + timedelta(seconds=60)
            job.deadline = now + timedelta(seconds=30)
            self._event(session, run, "claimed", attempt=job.attempts, worker_id=str(worker.id))
            return DraftClaim(run.id, worker.id, job.lease_token)
        return None

    def _leased(self, session, token, claim, *, expired=False):
        if not isinstance(claim, DraftClaim) or any(
            type(v) is not UUID for v in (claim.run_id, claim.worker_id, claim.lease_token)
        ):
            raise InvestigationLeaseLost("draft_lease_lost")
        worker = self.coordinator._worker(session, token)
        job = session.scalar(
            select(DraftJob).where(DraftJob.run_id == claim.run_id).with_for_update()
        )
        now = self.coordinator._now(session)
        if (
            job is None
            or job.status != "running"
            or job.worker_id != worker.id
            or worker.id != claim.worker_id
            or job.lease_token != claim.lease_token
            or not expired
            and (job.deadline <= now or job.lease_until <= now)
        ):
            raise InvestigationLeaseLost("draft_lease_lost")
        return job

    @atomic
    def prepare(self, session, token, claim):
        self._enabled()
        self.coordinator._gate(session)
        job = self._leased(session, token, claim)
        run = self._run(session, job.run_id)
        packet = self._packet(session, run)
        config = self._configuration(run)
        minimized = minimize(packet)
        reserved = len(minimized.model_dump_json(warnings="error").encode()) + len(PROMPT.encode())
        existing = self._attempt(session, job)
        if existing is not None:
            # An ambiguously delivered request cannot be sent a second time on the same claim.
            raise EvidenceConflict("draft_attempt_already_reserved")
        total = session.scalar(
            select(
                func.coalesce(
                    func.sum(DraftAttempt.input_reservation + DraftAttempt.output_reservation), 0
                )
            ).where(DraftAttempt.run_id == run.id)
        )
        if (
            reserved > config.max_input_tokens
            or total + reserved + config.max_output_tokens > config.total_token_budget
        ):
            self._fail(session, job, "budget_exhausted")
            return None
        attempt = DraftAttempt(
            id=uuid4(),
            run_id=run.id,
            attempt=job.attempts,
            lease_sha256=digest(str(claim.lease_token)),
            packet_sha256=minimized.packet_sha256,
            minimized_sha256=digest(minimized.model_dump(mode="json")),
            input_reservation=reserved,
            output_reservation=config.max_output_tokens,
        )
        session.add(attempt)
        self._event(
            session,
            run,
            "provider_reserved",
            attempt=job.attempts,
            reserved_input=reserved,
            reserved_output=config.max_output_tokens,
            cost_upper_bound_usd="0",
            egress=False,
        )
        return minimized, config

    def _build(self, run, packet, reply, proposal, findings, attempt):
        return DraftBody(
            draft_run_id=run.id,
            investigation_run_id=run.parent_run_id,
            input_manifest_sha256=run.manifest_sha256,
            packet_sha256=attempt.packet_sha256,
            findings=findings,
            hypotheses=proposal.hypotheses,
            questions=proposal.questions,
            unresolved_questions=sorted(set(packet.questions) | set(proposal.unresolved_questions)),
            next_steps=sorted(set(proposal.next_steps) | {"human_review"}),
            missing_evidence=packet.missing_evidence,
            conflicts=packet.conflicts,
            limitations=packet.limitations,
            stored_model_signal=packet.model_signal.model_dump(mode="json")
            if packet.model_signal
            else None,
            provenance=dict(
                provider=reply.provider,
                model=reply.model,
                prompt_version=PROMPT_VERSION,
                prompt_sha256=PROMPT_SHA,
                attempt_id=str(attempt.id),
                parent_manifest_sha256=run.parent_manifest_sha256,
                minimized_packet_sha256=attempt.minimized_sha256,
                configuration_sha256=run.config_sha256,
                simulation=True,
                live_provider_used=False,
                usage=reply.usage.model_dump(mode="json"),
            ),
            verification=dict(
                status="structural_reference_numeric_checks_passed",
                verifier="trueflag.draft-verifier.v1",
                human_semantic_review_required=True,
                full_factual_entailment_verified=False,
                legal_correctness_verified=False,
            ),
            outcome="abstained" if proposal.abstain or not findings else "draft_ready",
        )

    @atomic
    def complete(self, session, token, claim, reply, elapsed_ms):
        self._enabled()
        self.coordinator._gate(session)
        job = self._leased(session, token, claim)
        run = self._run(session, job.run_id)
        packet = self._packet(session, run)
        config = self._configuration(run)
        attempt = self._attempt(session, job)
        minimized = minimize(packet)
        if (
            attempt is None
            or attempt.lease_sha256 != digest(str(claim.lease_token))
            or attempt.minimized_sha256 != digest(minimized.model_dump(mode="json"))
        ):
            raise VerificationFailed("draft_verification_failed")
        if reply.finish_reason != "complete":
            raise ProviderFailure("provider_incomplete")
        if (
            reply.usage.input_tokens > attempt.input_reservation
            or reply.usage.output_tokens > attempt.output_reservation
        ):
            raise VerificationFailed("draft_verification_failed")
        try:
            reply = ProviderReply.model_validate_json(reply.model_dump_json(warnings="error"))
            proposal = parse_proposal(reply, config)
        except (ValueError, TypeError, ProviderLimit, ProviderFailure):
            raise InvalidDraftOutput("invalid_provider_output") from None
        findings = validate_proposal(packet, proposal)
        body = self._build(run, packet, reply, proposal, findings, attempt)
        if len(body.model_dump_json(warnings="error").encode()) > 524288:
            raise ProviderLimit("draft_response_limit")
        if job.deadline <= self.coordinator._now(session):
            raise InvestigationLeaseLost("draft_lease_lost")
        self._receipt(session, attempt, "completed", reply, elapsed_ms)
        session.add(
            StoredDraft(
                run_id=run.id,
                attempt_id=attempt.id,
                manifest_sha256=run.manifest_sha256,
                content_sha256=digest(body.model_dump(mode="json")),
                body=body.model_dump(mode="json"),
            )
        )
        job.status = "abstained" if body.outcome == "abstained" else "succeeded"
        self._clear(job)
        self._event(
            session,
            run,
            "published",
            attempt=job.attempts,
            result_sha256=digest(body.model_dump(mode="json")),
            semantic_review_required=True,
        )
        session.flush()
        return self._job_view(job)

    @atomic
    def fail(
        self,
        session,
        token,
        claim,
        reason,
        *,
        retryable=False,
        invalidated=False,
        reply=None,
        elapsed=None,
    ):
        self.coordinator._gate(session)
        if reason not in FAILURES or type(retryable) is not bool or type(invalidated) is not bool:
            raise EvidenceBlocked("invalid_draft_failure")
        job = self._leased(session, token, claim, expired=True)
        return self._fail(
            session,
            job,
            reason,
            retryable=retryable,
            invalidated=invalidated,
            reply=reply,
            elapsed=elapsed,
        )

    @atomic
    def recover(self, session, token):
        self.coordinator._gate(session)
        self.coordinator._worker(session, token)
        now = self.coordinator._now(session)
        jobs = session.scalars(
            select(DraftJob)
            .join(InvestigationWorker, DraftJob.worker_id == InvestigationWorker.id)
            .where(
                DraftJob.status == "running",
                or_(
                    DraftJob.lease_until <= now,
                    DraftJob.deadline <= now,
                    InvestigationWorker.active.is_(False),
                ),
            )
            .order_by(DraftJob.run_id)
            .with_for_update(of=DraftJob, skip_locked=True)
            .limit(20)
        ).all()
        for job in jobs:
            worker = session.get(InvestigationWorker, job.worker_id)
            self._fail(
                session,
                job,
                "worker_revoked" if not worker.active else "lease_expired",
                retryable=True,
            )
        return len(jobs)

    @atomic
    def get(self, session, actor_id, case_id, run_id):
        self.coordinator._gate(session)
        self.coordinator.reader._context(session, actor_id, case_id)
        run = self._run(session, run_id)
        parent = self.coordinator._run(session, run.parent_run_id)
        if run.actor_id != actor_id or parent.case_id != case_id:
            raise EvidenceNotFound("investigation_draft_not_found")
        job = session.get(DraftJob, run.id)
        try:
            self.coordinator._current(session, parent)
            parent_job = session.get(InvestigationJob, parent.id)
            if parent_job.status in {"pending", "running"}:
                return {**self._job_view(job), "draft": None}
            packet = self._packet(session, run)
        except SnapshotStale:
            self._fail(session, job, "input_invalidated", invalidated=True)
            return {**self._job_view(job), "draft": None}
        stored = session.scalar(select(StoredDraft).where(StoredDraft.run_id == run.id))
        if job.status not in {"succeeded", "abstained"} or stored is None:
            return {**self._job_view(job), "draft": None}
        if (
            digest(stored.body) != stored.content_sha256
            or stored.manifest_sha256 != run.manifest_sha256
        ):
            raise VerificationFailed("draft_verification_failed")
        body = DraftBody.model_validate(stored.body)
        if body.packet_sha256 != digest(packet.model_dump(mode="json")):
            raise VerificationFailed("draft_verification_failed")
        self._event(session, run, "read", result_sha256=stored.content_sha256)
        return {**self._job_view(job), "draft": body.model_dump(mode="json")}

    def run_once(self, token):
        self._enabled()
        self.recover(token)
        claim = self.claim(token)
        if claim is None:
            return None
        started = time.monotonic()
        reply = None
        try:
            prepared = self.prepare(token, claim)
            if prepared is None:
                return dict(
                    status="failed", error_code="budget_exhausted", human_review_required=True
                )
            packet, config = prepared
            reply = self._runner.invoke(packet, config)
            reply = ProviderReply.model_validate_json(reply.model_dump_json(warnings="error"))
            if reply.finish_reason == "refused":
                return self.fail(token, claim, "provider_refused", reply=reply)
            if reply.finish_reason == "incomplete":
                return self.fail(token, claim, "provider_incomplete", retryable=True, reply=reply)
            return self.complete(token, claim, reply, int((time.monotonic() - started) * 1000))
        except SnapshotStale:
            return self.fail(token, claim, "input_invalidated", invalidated=True, reply=reply)
        except EvidenceNotFound:
            return self.fail(token, claim, "authorization_revoked", invalidated=True, reply=reply)
        except ProviderTimeout:
            return self.fail(token, claim, "provider_timeout", retryable=True)
        except InvalidDraftOutput:
            return self.fail(token, claim, "invalid_provider_output")
        except VerificationFailed:
            return self.fail(token, claim, "verification_failed", reply=reply)
        except ProviderLimit:
            return self.fail(token, claim, "invalid_provider_output")
        except InvestigationLeaseLost:
            return None
        except ProviderFailure:
            return self.fail(token, claim, "provider_unavailable", retryable=True)
        except (ValueError, TypeError):
            return self.fail(token, claim, "invalid_provider_output")
        except EvidenceError:
            return self.fail(token, claim, "database_unavailable", retryable=True)
        except Exception:
            return self.fail(token, claim, "provider_unavailable", retryable=True)
