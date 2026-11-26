"""Durable draft stage. Candidate provider uses the existing evidence coordinator/verifier."""

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text

from app.models import Alert, AuditEvent
from app.models.evidence import EvidenceSource
from app.models.investigation_drafts import (
    DraftAttempt,
    DraftJob,
    DraftReceipt,
    DraftRequest,
    DraftRun,
    StoredDraft,
)
from app.models.investigations import (
    InvestigationJob,
    InvestigationPacket,
    InvestigationRun,
    InvestigationWorker,
)
from app.models.references import ReferenceGrant
from app.models.regulatory_drafts import DraftRegulatoryBinding
from app.schemas.investigation_drafts import (
    DRAFT_VERSION,
    PROMPT,
    DraftBody,
    ProviderConfig,
    ProviderReply,
)
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.provider_live import (
    LIVE_PROMPT_SHA,
    AIDraftBody,
    AIProposal,
    ClaudeProviderConfig,
    ClaudeResponseDiagnostics,
    LiveProviderConfig,
    RegulatoryQueryClaudeConfig,
    RegulatoryQuerySimulationConfig,
    configuration,
)
from app.schemas.regulatory_investigation import (
    GroundedAIDraftBody,
    GroundedDraftBody,
    InvestigationRegulatoryContext,
)
from app.services.claude_provider import authorize_claude
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
from app.services.investigation_verifier import VerificationFailed, verify_packet
from app.services.live_provider_runner import ProviderRunner
from app.services.luminal_provider import ProviderRateLimited, ProviderRejected, authorize
from app.services.provider_budget import call_limit, finance_dispatch_allowed, spend_limit
from app.services.provider_finance import lock_reservations, reservation_totals
from app.services.regulatory_investigation import RegulatoryInvestigationService

PROMPT_SHA = hashlib.sha256(PROMPT.encode()).hexdigest()


class InvalidDraftOutput(EvidenceBlocked):
    """Invalid model content is a terminal validation failure, not a DB retry."""


class RegulatoryContextUnavailable(EvidenceBlocked):
    pass


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
VERIFICATION_REASONS = {
    "regulatory_context_unavailable",
    "regulatory_authority_changed",
    "supporting_reference_invalid",
    "missing_evidence_mismatch",
    "limitations_mismatch",
    "claim_type_mismatch",
    "overview_mismatch",
    "packet_hash_mismatch",
    "question_mismatch",
    "duplicate_finding",
    "reference_not_authorized",
    "transaction_reference_mismatch",
    "calculation_reference_mismatch",
    "model_signal_mismatch",
    "numeric_feature_mismatch",
    "numeric_value_mismatch",
    "hypothesis_reference_invalid",
    "conflicts_hypothesis_unsupported",
    "coverage_hypothesis_unsupported",
    "concentration_hypothesis_unsupported",
    "abstention_required",
    "conflict_step_unsupported",
    "research_citation_invalid",
    "research_finding_citation_invalid",
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
        self._runner = ProviderRunner(settings)

    def _enabled(self, config=None):
        if isinstance(config, ClaudeProviderConfig):
            try:
                authorize_claude(self.settings, config)
            except ProviderFailure:
                raise EvidenceBlocked("investigation_provider_disabled") from None
        elif config is None and getattr(self.settings, "anthropic_synthetic_demo_enabled", False):
            return
        elif isinstance(config, LiveProviderConfig):
            try:
                authorize(self.settings, config)
            except ProviderFailure:
                raise EvidenceBlocked("investigation_provider_disabled") from None
        elif self.settings.investigation_external_enabled:
            if config is not None or not (
                finance_dispatch_allowed(self.settings)
                and self.settings.investigation_provider_approval_id
                and self.settings.investigation_provider_terms_sha256
                and self.settings.investigation_provider_contract_verified
                and self.settings.investigation_provider_api_key.get_secret_value()
                and self.settings.investigation_provider_spend_limit_usd > 0
                and call_limit(self.settings) > 0
            ):
                raise EvidenceBlocked("investigation_provider_disabled")
        elif not self.settings.investigation_simulation_enabled or isinstance(
            config, LiveProviderConfig
        ):
            raise EvidenceBlocked("investigation_provider_disabled")

    def _event(self, session, run, action, **details):
        audit(
            session,
            run.actor_id,
            "investigation.draft." + action,
            run.id,
            manifest_sha256=run.manifest_sha256,
            mode=run.configuration["mode"],
            **details,
        )

    def _job_view(self, job, run=None):
        return dict(
            draft_run_id=str(job.run_id),
            status=job.status,
            attempts=job.attempts,
            error_code=job.error_code,
            mode=run.configuration["mode"] if run else "simulation",
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
        config = configuration(run.configuration)
        if digest(config.model_dump(mode="json")) != run.config_sha256 or run.prompt_sha256 != (
            LIVE_PROMPT_SHA if isinstance(config, LiveProviderConfig) else PROMPT_SHA
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
        config = self._configuration(run)
        parent = self.coordinator._run(session, run.parent_run_id)
        context, manifest = self.coordinator._current(session, parent)
        if isinstance(config, ClaudeProviderConfig):
            alert = session.get(Alert, manifest.alert_id)
            if alert is None or alert.data_classification != "synthetic" or not manifest.sources:
                raise EvidenceBlocked("synthetic_evidence_required")
            for reference in manifest.sources:
                source = session.get(EvidenceSource, reference.source_id)
                if source is None or source.classification != "synthetic":
                    raise EvidenceBlocked("synthetic_evidence_required")
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
        self.coordinator.reader.ensure_clock(context.clock_epoch)
        return packet

    def _grounding(self, session, run):
        config = self._configuration(run)
        expected = getattr(config, "regulatory_binding_sha256", None)
        query = getattr(config, "regulatory_query", None)
        if expected is None and query is None:
            return None
        row = session.get(DraftRegulatoryBinding, run.id)
        if (
            row is None
            or row.actor_id != run.actor_id
            or row.parent_run_id != run.parent_run_id
            or row.run_manifest_sha256 != run.manifest_sha256
            or expected is not None
            and row.binding_sha256 != expected
        ):
            raise VerificationFailed("regulatory_binding_invalid")
        binding = InvestigationRegulatoryContext.model_validate(row.body)
        if (
            binding.binding_sha256 != row.binding_sha256
            or binding.investigation_run_id != run.parent_run_id
            or binding.case_id != row.case_id
            or query is not None
            and binding.query != query
        ):
            raise VerificationFailed("regulatory_binding_invalid")
        if (
            query is not None
            and self._regulatory_authority(session, run.actor_id, row.case_id)
            != config.regulatory_authority_sha256
        ):
            raise VerificationFailed("regulatory_authority_changed")
        return binding

    def _regulatory_authority(self, session, actor, case):
        bridge = RegulatoryInvestigationService(self.engine, self.settings)
        context, release = bridge.references._context(session, actor, case)
        if context is None or release is None:
            raise RegulatoryContextUnavailable("approved_regulatory_context_unavailable")
        grant = session.get(ReferenceGrant, (context.id, actor))
        if grant is None or not grant.active:
            raise EvidenceNotFound("reference_not_found")
        return digest(
            dict(
                context_id=str(context.id),
                release_id=str(release.id),
                release_sha256=release.manifest_sha256,
                grant_revision=grant.revision,
                jurisdiction=context.jurisdiction,
                entity=context.entity,
                language=context.language,
                as_of=context.as_of.isoformat(),
                knowledge_cutoff=context.knowledge_cutoff.isoformat(),
            )
        )

    def _deferred_schema(self, session, config):
        if isinstance(config, (RegulatoryQueryClaudeConfig, RegulatoryQuerySimulationConfig)) and (
            session.scalar(text("SELECT version_num FROM alembic_version"))
            != "0023_durable_regulatory_start"
        ):
            raise EvidenceBlocked("deferred_regulatory_schema_required")

    def _prepare_regulatory_context(self, session, run):
        config = self._configuration(run)
        if not isinstance(config, (RegulatoryQueryClaudeConfig, RegulatoryQuerySimulationConfig)):
            return
        self._deferred_schema(session, config)
        if not self.settings.regulatory_investigation_enabled:
            raise EvidenceBlocked("regulatory_investigation_disabled")
        if (
            self._regulatory_authority(
                session, run.actor_id, self.coordinator._run(session, run.parent_run_id).case_id
            )
            != config.regulatory_authority_sha256
        ):
            raise VerificationFailed("regulatory_authority_changed")
        if session.get(DraftRegulatoryBinding, run.id) is not None:
            self._grounding(session, run)
            return  # Retries never refresh a frozen context or its expiration.
        if session.scalar(select(DraftAttempt.id).where(DraftAttempt.run_id == run.id).limit(1)):
            raise VerificationFailed("regulatory_binding_invalid")
        bridge = RegulatoryInvestigationService(self.engine, self.settings)
        binding = bridge.prepare.__wrapped__(
            bridge,
            session,
            run.actor_id,
            self.coordinator._run(session, run.parent_run_id).case_id,
            run.parent_run_id,
            config.regulatory_query,
        )
        if binding.grounding is None or binding.result.status != "available":
            raise RegulatoryContextUnavailable("approved_regulatory_context_unavailable")
        # Missing/unapproved/withdrawn context cannot reach a provider reservation.
        bridge.provider_input.__wrapped__(bridge, session, run.actor_id, binding)
        session.add(
            DraftRegulatoryBinding(
                run_id=run.id,
                actor_id=run.actor_id,
                case_id=binding.case_id,
                parent_run_id=run.parent_run_id,
                run_manifest_sha256=run.manifest_sha256,
                binding_sha256=binding.binding_sha256,
                body=binding.model_dump(mode="json"),
            )
        )
        session.flush()
        self._event(
            session,
            run,
            "regulatory_bound",
            binding_sha256=binding.binding_sha256,
            query_sha256=digest(config.regulatory_query.model_dump(mode="json")),
            passages=len(binding.result.passages),
        )

    def _provider_input(self, session, run, packet):
        binding = self._grounding(session, run)
        if binding is None:
            return minimize(packet)
        if not self.settings.regulatory_investigation_enabled:
            raise EvidenceBlocked("regulatory_investigation_disabled")
        bridge = RegulatoryInvestigationService(self.engine, self.settings)
        return bridge.provider_input.__wrapped__(bridge, session, run.actor_id, binding)

    @atomic
    def request(
        self,
        session,
        actor_id,
        case_id,
        key,
        investigation_request,
        configuration,
        regulatory_binding=None,
    ):
        self._enabled(configuration)
        if (
            type(key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key)
            or not isinstance(configuration, (ProviderConfig, LiveProviderConfig))
        ):
            raise EvidenceBlocked("invalid_draft_request")
        config = configuration.__class__.model_validate_json(
            configuration.model_dump_json(warnings="error")
        )
        prompt_sha = LIVE_PROMPT_SHA if isinstance(config, LiveProviderConfig) else PROMPT_SHA
        self.coordinator._gate(session)
        self._deferred_schema(session, config)
        if (
            getattr(config, "regulatory_query", None) is not None
            and not self.settings.regulatory_investigation_enabled
        ):
            raise EvidenceBlocked("regulatory_investigation_disabled")
        expected_binding = getattr(config, "regulatory_binding_sha256", None)
        if expected_binding is not None:
            if not self.settings.regulatory_investigation_enabled:
                raise EvidenceBlocked("regulatory_investigation_disabled")
            if (
                not isinstance(regulatory_binding, InvestigationRegulatoryContext)
                or regulatory_binding.binding_sha256 != expected_binding
                or regulatory_binding.case_id != case_id
            ):
                raise EvidenceBlocked("regulatory_binding_required")
            bridge = RegulatoryInvestigationService(self.engine, self.settings)
            bridge.provider_input.__wrapped__(bridge, session, actor_id, regulatory_binding)
        elif regulatory_binding is not None:
            raise EvidenceBlocked("unexpected_regulatory_binding")
        # Same transaction: parent evidence admission, child intent, key, job and audit.
        parent_key = "draft-" + digest(dict(actor=str(actor_id), key=key))
        receipt = self.coordinator.request_in_transaction(
            session, actor_id, case_id, parent_key, investigation_request
        )
        parent = self.coordinator._run(session, UUID(receipt["run_id"]))
        if isinstance(config, (RegulatoryQueryClaudeConfig, RegulatoryQuerySimulationConfig)):
            authority = self._regulatory_authority(session, actor_id, case_id)
            if config.regulatory_authority_sha256 not in (None, authority):
                raise EvidenceConflict("regulatory_authority_changed")
            config = config.model_copy(update={"regulatory_authority_sha256": authority})
        if regulatory_binding is not None and regulatory_binding.investigation_run_id != parent.id:
            raise EvidenceConflict("regulatory_parent_mismatch")
        csha = digest(config.model_dump(mode="json"))
        msha = digest(
            dict(
                parent_run_id=str(parent.id),
                parent_manifest_sha256=parent.manifest_sha256,
                config_sha256=csha,
                prompt_sha256=prompt_sha,
                schema=DRAFT_VERSION,
            )
        )
        previous = session.get(DraftRequest, (actor_id, key))
        if previous:
            if previous.manifest_sha256 != msha:
                raise EvidenceConflict("draft_idempotency_conflict")
            return self._job_view(
                session.get(DraftJob, previous.run_id), self._run(session, previous.run_id)
            )
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
                prompt_sha256=prompt_sha,
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
        if regulatory_binding is not None and session.get(DraftRegulatoryBinding, run.id) is None:
            session.add(
                DraftRegulatoryBinding(
                    run_id=run.id,
                    actor_id=actor_id,
                    case_id=case_id,
                    parent_run_id=parent.id,
                    run_manifest_sha256=run.manifest_sha256,
                    binding_sha256=regulatory_binding.binding_sha256,
                    body=regulatory_binding.model_dump(mode="json"),
                )
            )
        session.flush()
        return self._job_view(session.get(DraftJob, run.id), run)

    def _clear(self, job):
        job.worker_id = job.lease_token = job.lease_until = job.deadline = None

    def _attempt(self, session, job):
        return session.scalar(
            select(DraftAttempt).where(
                DraftAttempt.run_id == job.run_id, DraftAttempt.attempt == job.attempts
            )
        )

    def _receipt(self, session, attempt, status, reply=None, elapsed=None, diagnostics=None):
        if attempt is not None and not session.scalar(
            select(DraftReceipt.id).where(DraftReceipt.attempt_id == attempt.id)
        ):
            usage = reply.usage.model_dump(mode="json") if reply else None
            if reply is None and diagnostics is not None:
                usage = {"basis": "provider_response_diagnostics", "diagnostics": diagnostics}
                incoming, outgoing = diagnostics["input_tokens"], diagnostics["output_tokens"]
                if (
                    incoming is not None
                    and outgoing is not None
                    and diagnostics["cache_tokens"] == 0
                ):
                    usage.update(
                        basis="provider_reported_tokens_configured_rate_estimate",
                        input_tokens=incoming,
                        output_tokens=outgoing,
                        cost_usd=str((Decimal(incoming) * 2 + Decimal(outgoing) * 10) / 1_000_000),
                    )
            session.add(
                DraftReceipt(
                    attempt_id=attempt.id,
                    status=status,
                    response_sha256=hashlib.sha256(reply.content.encode()).hexdigest()
                    if reply
                    else None,
                    usage=usage,
                    elapsed_ms=elapsed if elapsed is not None and 0 <= elapsed <= 60000 else None,
                )
            )

    def _fail(
        self,
        session,
        job,
        reason,
        *,
        retryable=False,
        invalidated=False,
        reply=None,
        elapsed=None,
        diagnostics=None,
        verification_reason=None,
    ):
        run = self._run(session, job.run_id)
        if invalidated and self._already_invalidated(session, job, reason):
            # One invalidation record per request: callers hold the job row lock, and this
            # existence check runs in the same transaction, so a repeat never writes again.
            return self._job_view(job, run)
        config = self._configuration(run)
        self._receipt(session, self._attempt(session, job), reason, reply, elapsed, diagnostics)
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
            **(
                {"verification_reason": verification_reason}
                if verification_reason is not None
                else {}
            ),
        )
        return self._job_view(job, run)

    def _already_invalidated(self, session, job, reason):
        if job.status == "invalidated":
            return True
        return (
            session.scalar(
                select(AuditEvent.id)
                .where(AuditEvent.resource_id == str(job.run_id))
                .where(AuditEvent.action == "evidence.investigation.draft.attempt_failed")
                .where(AuditEvent.details["reason"].as_string() == reason)
                .where(AuditEvent.details["attempt"].as_string() == str(job.attempts))
                .limit(1)
            )
            is not None
        )

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
                self._job_scope(),
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
            deadline_seconds, lease_seconds = self._execution_limits(self._configuration(run))
            job.lease_until = now + timedelta(seconds=lease_seconds)
            job.deadline = now + timedelta(seconds=deadline_seconds)
            self._event(session, run, "claimed", attempt=job.attempts, worker_id=str(worker.id))
            return DraftClaim(run.id, worker.id, job.lease_token)
        return None

    def _execution_limits(self, config):
        return 30, 60

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
        self._prepare_regulatory_context(session, run)
        minimized = self._provider_input(session, run, packet)
        self._enabled(config)
        if (
            isinstance(config, ClaudeProviderConfig)
            and config.purpose != "investigation"
            and digest(minimized.model_dump(mode="json")) != config.exact_input_sha256
        ):
            raise EvidenceBlocked("synthetic_probe_input_mismatch")
        reserved = (
            config.max_input_tokens
            if isinstance(config, LiveProviderConfig)
            else len(minimized.model_dump_json(warnings="error").encode()) + len(PROMPT.encode())
        )
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
        if isinstance(config, LiveProviderConfig):
            # Policies use a provider-wide ledger; serialize across distinct grants too.
            lock_reservations(session)
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:grant, 411))"),
                {"grant": config.approval_id},
            )
            claude = isinstance(config, ClaudeProviderConfig)
            used_calls, spent = reservation_totals(
                session,
                config.approval_id
                if not claude
                and self.settings.investigation_provider_financial_policy == "legacy_probe_v1"
                else None,
                provider="anthropic" if claude else "luminal",
            )
            upper = (
                config.max_cost_usd
                if claude
                else (
                    Decimal(reserved + config.max_output_tokens)
                    * max(config.input_usd_per_million, config.output_usd_per_million)
                    / 1_000_000
                )
            )
            max_calls = (
                self.settings.anthropic_demo_call_limit if claude else call_limit(self.settings)
            )
            max_spend = (
                Decimal(str(self.settings.anthropic_demo_spend_limit_usd))
                if claude
                else spend_limit(self.settings)
            )
            outstanding = (
                session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .outerjoin(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(DraftReceipt.id.is_(None))
                )
                if claude
                else 0
            )
            previous_probe = (
                session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(DraftRun.configuration["purpose"].as_string() == "compatibility_probe")
                )
                if claude and config.purpose == "compatibility_probe"
                else 0
            )
            diagnostic_denied = False
            if claude and config.purpose == "compatibility_diagnostic":
                diagnostic_attempts = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string() == "compatibility_diagnostic"
                    )
                )
                failed_probe_receipts = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .join(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(DraftRun.configuration["purpose"].as_string() == "compatibility_probe")
                    .where(DraftReceipt.status != "completed")
                )
                failed_diagnostics = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .join(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string() == "compatibility_diagnostic"
                    )
                    .where(DraftReceipt.status != "completed")
                )
                diagnostic_denied = (
                    diagnostic_attempts >= 2
                    or failed_probe_receipts != 1
                    or failed_diagnostics != diagnostic_attempts
                )
            if claude and config.purpose == "compatibility_fix_verification":
                verification_attempts = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string()
                        == "compatibility_fix_verification"
                    )
                )
                prior_receipts = session.scalars(
                    select(DraftReceipt)
                    .join(DraftAttempt, DraftAttempt.id == DraftReceipt.attempt_id)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string() == "compatibility_diagnostic"
                    )
                ).all()
                observed = any(
                    receipt.status != "completed"
                    and "packet_sha256:string_pattern_mismatch"
                    in (receipt.usage or {}).get("diagnostics", {}).get("schema_errors", [])
                    for receipt in prior_receipts
                )
                diagnostic_denied = verification_attempts > 0 or not observed
            if claude and config.purpose == "verification_diagnostic":
                prior_attempts = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string() == "verification_diagnostic"
                    )
                )
                verifier_failures = session.scalar(
                    select(func.count())
                    .select_from(DraftReceipt)
                    .join(DraftAttempt, DraftAttempt.id == DraftReceipt.attempt_id)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string()
                        == "compatibility_fix_verification"
                    )
                    .where(DraftReceipt.status == "verification_failed")
                )
                diagnostic_denied = prior_attempts > 0 or verifier_failures != 1
            if claude and config.purpose == "claim_type_fix_verification":
                prior_attempts = session.scalar(
                    select(func.count())
                    .select_from(DraftAttempt)
                    .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(
                        DraftRun.configuration["purpose"].as_string()
                        == "claim_type_fix_verification"
                    )
                )
                previous = session.scalars(
                    select(DraftRun)
                    .join(DraftAttempt, DraftAttempt.run_id == DraftRun.id)
                    .join(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
                    .join(InvestigationRun, InvestigationRun.id == DraftRun.parent_run_id)
                    .where(DraftRun.actor_id == run.actor_id)
                    .where(
                        InvestigationRun.case_id
                        == self.coordinator._run(session, run.parent_run_id).case_id
                    )
                    .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                    .where(DraftRun.configuration["approval_id"].as_string() == config.approval_id)
                    .where(
                        DraftRun.configuration["terms_sha256"].as_string() == config.terms_sha256
                    )
                    .where(
                        DraftRun.configuration["purpose"].as_string() == "verification_diagnostic"
                    )
                    .where(DraftReceipt.status == "verification_failed")
                ).all()
                observed = len(previous) == 1 and bool(
                    session.scalar(
                        select(AuditEvent.id)
                        .where(AuditEvent.actor_id == run.actor_id)
                        .where(AuditEvent.action == "evidence.investigation.draft.attempt_failed")
                        .where(AuditEvent.resource_id == str(previous[0].id))
                        .where(
                            AuditEvent.details["verification_reason"].as_string()
                            == "claim_type_mismatch"
                        )
                    )
                )
                diagnostic_denied = prior_attempts > 0 or not observed
            if claude and config.purpose == "live_validation":
                # One manually authorized validation per exact wire-schema version.
                # The global reservation lock, account allowance and no-retry limit
                # remain identical to ordinary paid attempts.
                diagnostic_denied = bool(
                    session.scalar(
                        select(DraftAttempt.id)
                        .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                        .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                        .where(DraftRun.configuration["purpose"].as_string() == "live_validation")
                        .where(
                            DraftRun.configuration["wire_schema_sha256"].as_string()
                            == config.wire_schema_sha256
                        )
                        .limit(1)
                    )
                )
            development = claude and config.financial_scope == "development_no_spend_cap_v1"
            if development or getattr(config, "research_scope", None) == "academic_research_v1":
                diagnostic_denied = bool(
                    session.scalar(
                        select(DraftAttempt.id)
                        .join(DraftRun, DraftRun.id == DraftAttempt.run_id)
                        .where(DraftRun.configuration["provider"].as_string() == "anthropic")
                        .where(
                            DraftRun.configuration["approval_id"].as_string() == config.approval_id
                        )
                        .limit(1)
                    )
                )
            if (
                (not development and (used_calls >= max_calls or spent + upper > max_spend))
                or outstanding
                or previous_probe
                or diagnostic_denied
            ):
                self._event(
                    session,
                    run,
                    "admission_denied",
                    reason="call_limit" if used_calls >= max_calls else "spend_limit",
                )
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
            cost_upper_bound_usd=None
            if getattr(config, "financial_scope", None) == "development_no_spend_cap_v1"
            else str(config.max_cost_usd),
            financial_scope=getattr(config, "financial_scope", "reserved_v1"),
            egress=isinstance(config, LiveProviderConfig),
        )
        return minimized, config

    def _build(self, run, packet, reply, proposal, findings, attempt):
        selection = proposal.selection() if isinstance(proposal, AIProposal) else proposal
        body = DraftBody(
            mode=self._configuration(run).mode,
            draft_run_id=run.id,
            investigation_run_id=run.parent_run_id,
            input_manifest_sha256=run.manifest_sha256,
            packet_sha256=attempt.packet_sha256,
            findings=findings,
            hypotheses=selection.hypotheses,
            questions=selection.questions,
            unresolved_questions=sorted(
                set(packet.questions) | set(selection.unresolved_questions)
            ),
            next_steps=sorted(set(selection.next_steps) | {"human_review"}),
            missing_evidence=packet.missing_evidence,
            conflicts=packet.conflicts,
            limitations=packet.limitations,
            stored_model_signal=packet.model_signal.model_dump(mode="json")
            if packet.model_signal
            else None,
            provenance=dict(
                provider=reply.provider,
                model=reply.model,
                prompt_version=run.configuration["prompt_version"],
                prompt_sha256=run.prompt_sha256,
                attempt_id=str(attempt.id),
                parent_manifest_sha256=run.parent_manifest_sha256,
                minimized_packet_sha256=attempt.minimized_sha256,
                configuration_sha256=run.config_sha256,
                simulation=reply.provider == "deterministic_fake",
                live_provider_used=reply.provider != "deterministic_fake",
                approval_id=run.configuration.get("approval_id")
                if reply.provider != "deterministic_fake"
                else None,
                usage=reply.usage.model_dump(mode="json"),
            ),
            verification=dict(
                status="structural_reference_numeric_checks_passed",
                verifier="trueflag.draft-verifier.v1",
                human_semantic_review_required=True,
                full_factual_entailment_verified=False,
                legal_correctness_verified=False,
            ),
            outcome="abstained" if selection.abstain or not findings else "draft_ready",
        )
        if isinstance(proposal, AIProposal):
            data = body.model_dump(mode="json")
            data.update(
                schema_version="trueflag.ai-investigation-draft.v1",
                overview=proposal.overview,
                supporting_records=proposal.supporting_records,
                financial_observations=[
                    f for f in findings if f["claim_type"] == "calculated_fact"
                ],
                unusual_activity=[f for f in findings if f["claim_type"] == "observed_fact"],
                additional_information_needed=body.unresolved_questions,
            )
            return AIDraftBody.model_validate(data)
        return body

    @atomic
    def recheck_dispatch(self, session, token, claim):
        self.coordinator._gate(session)
        job = self._leased(session, token, claim)
        run = self._run(session, job.run_id)
        self._enabled(self._configuration(run))
        packet = self._packet(session, run)
        attempt = self._attempt(session, job)
        if attempt is None or attempt.minimized_sha256 != digest(
            self._provider_input(session, run, packet).model_dump(mode="json")
        ):
            raise VerificationFailed("draft_verification_failed")

    @atomic
    def complete(self, session, token, claim, reply, elapsed_ms):
        self._enabled()
        self.coordinator._gate(session)
        job = self._leased(session, token, claim)
        clock_epoch = self.coordinator.reader.clock.observe().epoch
        run = self._run(session, job.run_id)
        packet = self._packet(session, run)
        config = self._configuration(run)
        self._enabled(config)
        attempt = self._attempt(session, job)
        minimized = self._provider_input(session, run, packet)
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
        if (
            isinstance(config, LiveProviderConfig)
            and reply.usage.cost_usd
            != (
                reply.usage.input_tokens * config.input_usd_per_million
                + reply.usage.output_tokens * config.output_usd_per_million
            )
            / 1_000_000
        ):
            raise VerificationFailed("draft_verification_failed")
        try:
            reply = ProviderReply.model_validate_json(reply.model_dump_json(warnings="error"))
            proposal = parse_proposal(reply, config)
        except (ValueError, TypeError, ProviderLimit, ProviderFailure):
            raise InvalidDraftOutput("invalid_provider_output") from None
        findings = validate_proposal(packet, proposal)
        body = self._build(run, packet, reply, proposal, findings, attempt)
        body = self._complete_grounding(session, run, proposal, body)
        if len(body.model_dump_json(warnings="error").encode()) > 524288:
            raise ProviderLimit("draft_response_limit")
        if job.deadline <= self.coordinator._now(session):
            raise InvestigationLeaseLost("draft_lease_lost")
        self.coordinator.reader.ensure_clock(clock_epoch)
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
        return self._job_view(job, run)

    def _complete_grounding(self, session, run, proposal, body):
        binding = self._grounding(session, run)
        if binding is None:
            return body
        bridge = RegulatoryInvestigationService(self.engine, self.settings)
        verified = bridge.verify.__wrapped__(bridge, session, run.actor_id, binding, proposal)
        cls = GroundedAIDraftBody if isinstance(proposal, AIProposal) else GroundedDraftBody
        return cls.model_validate(
            {
                **body.model_dump(mode="json"),
                "regulatory_context": "approved_context_human_review_required",
                "regulatory_binding_sha256": binding.binding_sha256,
                "regulatory_citations": verified["regulatory_passages"],
            }
        )

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
        retry_after=0,
        diagnostics=None,
        verification_reason=None,
    ):
        self.coordinator._gate(session)
        if reason not in FAILURES or type(retryable) is not bool or type(invalidated) is not bool:
            raise EvidenceBlocked("invalid_draft_failure")
        if verification_reason is not None and (
            reason != "verification_failed" or verification_reason not in VERIFICATION_REASONS
        ):
            raise EvidenceBlocked("invalid_verification_reason")
        job = self._leased(session, token, claim, expired=True)
        if diagnostics is not None:
            try:
                diagnostics = ClaudeResponseDiagnostics.model_validate(diagnostics).model_dump(
                    mode="json"
                )
            except (TypeError, ValueError):
                raise EvidenceBlocked("invalid_provider_diagnostics") from None
        result = self._fail(
            session,
            job,
            reason,
            retryable=retryable,
            invalidated=invalidated,
            reply=reply,
            elapsed=elapsed,
            diagnostics=diagnostics,
            verification_reason=verification_reason,
        )
        if job.status == "pending" and retry_after:
            job.not_before = self.coordinator._now(session) + timedelta(
                seconds=max(2**job.attempts, min(30, retry_after))
            )
        return result

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
                self._job_scope(),
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
                retryable=self._configuration(self._run(session, job.run_id)).provider
                == "deterministic_fake"
                or self._attempt(session, job) is None,
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
                return {**self._job_view(job, run), "draft": None}
            packet = self._packet(session, run)
            if (
                getattr(self._configuration(run), "regulatory_query", None) is not None
                and session.get(DraftRegulatoryBinding, run.id) is None
                and job.status not in {"succeeded", "abstained"}
            ):
                return {**self._job_view(job, run), "draft": None}
            self._provider_input(session, run, packet)
        except SnapshotStale:
            # Reading never writes. The view reports the invalid state; the single audited
            # transition happens where the request is acted on (claim, retire, cancel).
            view = self._job_view(job, run)
            if job.status != "invalidated":
                view.update(status="invalidated", error_code="input_invalidated")
            return {**view, "draft": None}
        stored = session.scalar(select(StoredDraft).where(StoredDraft.run_id == run.id))
        if job.status not in {"succeeded", "abstained"} or stored is None:
            return {**self._job_view(job, run), "draft": None}
        if (
            digest(stored.body) != stored.content_sha256
            or stored.manifest_sha256 != run.manifest_sha256
        ):
            raise VerificationFailed("draft_verification_failed")
        cls = AIDraftBody if stored.body.get("mode") == "provider_candidate" else DraftBody
        config = self._configuration(run)
        if (
            getattr(config, "regulatory_binding_sha256", None) is not None
            or getattr(config, "regulatory_query", None) is not None
        ):
            cls = (
                GroundedAIDraftBody
                if stored.body.get("mode") == "provider_candidate"
                else GroundedDraftBody
            )
        body = self._stored_body_class(run, cls).model_validate(stored.body)
        if body.packet_sha256 != digest(packet.model_dump(mode="json")):
            raise VerificationFailed("draft_verification_failed")
        self._event(session, run, "read", result_sha256=stored.content_sha256)
        return {**self._job_view(job, run), "draft": body.model_dump(mode="json")}

    def _stored_body_class(self, run, default):
        return default

    def _job_scope(self):
        return True

    def run_once(self, token):
        self._enabled()
        self.recover(token)
        claim = self.claim(token)
        if claim is None:
            return None
        started = time.monotonic()
        reply = None
        config = None

        def failure(reason, **kwargs):
            return self.fail(
                token, claim, reason, elapsed=int((time.monotonic() - started) * 1000), **kwargs
            )

        try:
            prepared = self.prepare(token, claim)
            if prepared is None:
                return dict(
                    status="failed", error_code="budget_exhausted", human_review_required=True
                )
            packet, config = prepared
            self.recheck_dispatch(token, claim)
            reply = self._runner.invoke(packet, config)
            reply = ProviderReply.model_validate_json(reply.model_dump_json(warnings="error"))
            if reply.finish_reason == "refused":
                return failure("provider_refused", reply=reply)
            if reply.finish_reason == "incomplete":
                return failure(
                    "provider_incomplete",
                    retryable=config is not None and config.provider == "deterministic_fake",
                    reply=reply,
                )
            return self.complete(token, claim, reply, int((time.monotonic() - started) * 1000))
        except RegulatoryContextUnavailable:
            return failure(
                "verification_failed", verification_reason="regulatory_context_unavailable"
            )
        except SnapshotStale:
            return failure("input_invalidated", invalidated=True, reply=reply)
        except EvidenceNotFound:
            return failure("authorization_revoked", invalidated=True, reply=reply)
        except ProviderTimeout:
            return failure(
                "provider_timeout",
                retryable=config is not None and config.provider == "deterministic_fake",
            )
        except InvalidDraftOutput:
            return failure("invalid_provider_output")
        except VerificationFailed as error:
            return failure(
                "verification_failed",
                reply=reply,
                verification_reason=getattr(error, "reason", None),
            )
        except ProviderLimit:
            return failure("invalid_provider_output")
        except InvestigationLeaseLost:
            return None
        except ProviderRateLimited as error:
            return failure(
                "provider_unavailable",
                retryable=config is not None and config.provider == "deterministic_fake",
                retry_after=error.retry_after,
            )
        except ProviderRejected as error:
            diagnostics = error.diagnostics or {}
            if (
                getattr(error, "http_status", None) == 200
                and diagnostics.get("parseable") is True
                and diagnostics.get("schema_valid") is False
            ):
                # The provider answered; its output failed TrueFlag's local contract.
                return failure("invalid_provider_output", diagnostics=error.diagnostics)
            return failure("provider_unavailable", diagnostics=error.diagnostics)
        except ProviderFailure:
            return failure(
                "provider_unavailable",
                retryable=config is not None and config.provider == "deterministic_fake",
            )
        except (ValueError, TypeError):
            return failure("invalid_provider_output")
        except EvidenceError:
            return failure(
                "database_unavailable",
                retryable=config is not None and config.provider == "deterministic_fake",
            )
        except Exception:
            return failure(
                "provider_unavailable",
                retryable=config is not None and config.provider == "deterministic_fake",
            )
