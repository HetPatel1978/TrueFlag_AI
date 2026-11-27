"""Read projection for academic jobs. Existing public generation remains disabled."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.investigation_drafts import DraftJob, DraftRequest, DraftRun
from app.models.investigations import InvestigationRun
from app.schemas.draft_api import ResearchLiveDraft
from app.schemas.research_demo import ResearchBindingV2, ResearchClaudeConfig
from app.services.draft_api import DraftAPIService
from app.services.evidence import (
    EvidenceBlocked,
    EvidenceConflict,
    EvidenceNotFound,
    atomic,
    audit,
)
from app.services.evidence_read import SnapshotStale
from app.services.claude_contract import request_body
from app.services.research_demo import ResearchEvidenceService
from app.services.research_drafts import (
    APPROVED_EVENT,
    CANCELLED_EVENT,
    INAPP_PREFIX,
    PREPARED_EVENT,
    ResearchDraftService,
    owner_approvers,
)
from app.services.investigation_verifier import VerificationFailed


class ResearchDraftAPIService(DraftAPIService):
    def __init__(self, engine, settings):
        super().__init__(engine, settings)
        self.drafts = ResearchDraftService(engine, settings)

    def _projection(self, config):
        return (
            ResearchLiveDraft
            if isinstance(config, ResearchClaudeConfig)
            else super()._projection(config)
        )

    def _project(self, session, run, config, body, values):
        if isinstance(config, ResearchClaudeConfig):
            binding = self.drafts._grounding(session, run)
            values = {
                **values,
                "finding_citations": body.get("finding_citations", []),
                "retrieval": (
                    binding.retrieval.model_dump(mode="json")
                    if isinstance(binding, ResearchBindingV2)
                    else None
                ),
                "source_texts": ResearchEvidenceService(self.engine, self.settings).source_texts(
                    binding
                ),
            }
        return super()._project(session, run, config, body, values)

    @atomic
    def case_capabilities(self, session, actor, case):
        result = self.capabilities()
        self.drafts.coordinator._gate(session)
        research = ResearchEvidenceService(self.engine, self.settings)
        try:
            research._scope(session, actor, case)
        except EvidenceBlocked as error:
            if str(error) == "research_scope_denied":
                return result
            raise
        run = self._latest(session, actor, case)
        status = "request_required"
        if owner_approvers(self.settings) is not None:
            return {
                **result,
                **self._inapp_state(session, actor, case),
                "general_generation_enabled": False,
            }
        if run is not None:
            binding = self.drafts._grounding(session, run)
            _, state = research.passages_for_read(session, actor, binding)
            status = "approval_required" if state == "current" else "request_expired"
            if state == "current":
                try:
                    self.drafts.approved_execution(session, run)
                    status = "approved"
                except (EvidenceBlocked, VerificationFailed, OSError, ValueError):
                    pass
        return {
            **result,
            "research_status": status,
            "research_run_id": str(run.id) if run is not None else None,
            "general_generation_enabled": False,
        }

    @atomic
    def execute(self, session, actor, case, run_id, key):
        run = self._owned(session, actor, case, run_id)
        service = self.drafts.approved_execution(session, run)
        job = session.scalar(select(DraftJob).where(DraftJob.run_id == run.id).with_for_update())
        if job.status == "pending":
            service._dispatch_window(session, run)
            marker = "research-ui-" + key
            prior = session.get(DraftRequest, (actor, marker))
            if prior is not None and prior.run_id != run.id:
                from app.services.evidence import EvidenceConflict

                raise EvidenceConflict("research_execution_conflict")
            if prior is None:
                session.add(DraftRequest(actor_id=actor, idempotency_key=marker, run_id=run.id, manifest_sha256=run.manifest_sha256))
                self.drafts._event(session, run, "research_execution_requested")
        return self._status(self.drafts._job_view(job, run), self.drafts._configuration(run))

    # ---- in-app exact-request approval ------------------------------------------------

    def _latest_inapp(self, session, actor, case):
        return session.scalar(
            select(DraftRun)
            .join(InvestigationRun, DraftRun.parent_run_id == InvestigationRun.id)
            .where(
                DraftRun.actor_id == actor,
                InvestigationRun.case_id == case,
                DraftRun.configuration["approval_id"].as_string().startswith(INAPP_PREFIX),
            )
            .order_by(DraftRun.created_at.desc(), DraftRun.id.desc())
            .limit(1)
        )

    def _phase(self, session, actor, run, job):
        """Where an in-app request is in its lifecycle (server-derived, never client state)."""
        if job.status != "pending":
            return job.status  # running / succeeded / abstained / failed / invalidated
        if self.drafts.recorded(session, run, CANCELLED_EVENT):
            return "cancelled"
        if self.drafts.recorded(session, run, APPROVED_EVENT):
            return "approved_queued"
        binding = self.drafts._grounding(session, run)
        _, state = ResearchEvidenceService(self.engine, self.settings).passages_for_read(
            session, actor, binding
        )
        return "awaiting_approval" if state == "current" else "request_expired"

    def _inapp_state(self, session, actor, case):
        run = self._latest_inapp(session, actor, case)
        phase = None
        if run is not None:
            job = session.get(DraftJob, run.id)
            try:
                phase = self._phase(session, actor, run, job)
            except (VerificationFailed, SnapshotStale):
                phase = "request_expired"
        if phase in ("awaiting_approval", "approved_queued", "running"):
            status = phase
        else:
            try:
                self.drafts.generation_admitted(session, actor)
                status = "request_expired" if phase == "request_expired" else "generate_ready"
            except EvidenceBlocked as error:
                status = (
                    "budget_exhausted"
                    if str(error) == "research_budget_exhausted"
                    else "request_required"
                )
        return {
            "research_status": status,
            "research_run_id": str(run.id) if run is not None else None,
            "research_run_phase": phase,
            "research_can_approve": self.drafts.can_approve(session, actor),
        }

    def _build(self, session, actor, run):
        """Rebuild the exact request from current evidence (raises when expired/changed)."""
        config = self.drafts._configuration(run)
        packet = self.drafts._provider_input(session, run, self.drafts._packet(session, run))
        raw = request_body(
            packet,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        return config, packet, raw

    def _inapp_run(self, session, actor, case, run_id):
        run = self._owned(session, actor, case, run_id)
        config = self.drafts._configuration(run)
        if not isinstance(config, ResearchClaudeConfig) or not config.approval_id.startswith(
            INAPP_PREFIX
        ):
            raise EvidenceNotFound("investigation_draft_not_found")
        return run

    @atomic
    def start_research(self, session, actor, case, key, body):
        """Generate AI Investigation: fresh snapshot and research-only binding taken now, the
        exact request built, hashed and staged for review. Nothing is queued or sent."""
        self.drafts.coordinator._gate(session)  # app-wide lock order: gate before row locks
        from app.schemas.investigations import InputManifest
        from app.services.claude_contract import output_schema
        from app.services.ingestion import digest

        coordinator = self.drafts.coordinator
        prior = session.get(DraftRequest, (actor, "research-start-" + key))
        if prior is not None:  # same click retried
            run = self._owned(session, actor, case, prior.run_id)
            return self._status(self.drafts._job_view(session.get(DraftJob, run.id), run),
                                self.drafts._configuration(run))
        grant = self.drafts.generation_admitted(session, actor)
        current = self._latest_inapp(session, actor, case)
        if current is not None:
            job = session.get(DraftJob, current.id)
            try:
                phase = self._phase(session, actor, current, job)
            except (VerificationFailed, SnapshotStale):
                phase = "request_expired"
            if phase in ("awaiting_approval", "approved_queued", "running"):
                # One open request per case: reuse it rather than preparing another.
                return self._status(self.drafts._job_view(job, current),
                                    self.drafts._configuration(current))
        parent_view = coordinator.get.__wrapped__(
            coordinator, session, actor, case, body.investigation_run_id
        )
        if parent_view.get("packet") is None:
            raise EvidenceConflict("verified_investigation_required")
        if digest(parent_view["packet"]) != body.expected_packet_sha256:
            raise EvidenceConflict("investigation_packet_changed")
        parent = coordinator._run(session, body.investigation_run_id)
        request = InputManifest.model_validate(parent.input_manifest).request
        research = ResearchEvidenceService(self.engine, self.settings)
        binding = research.prepare.__wrapped__(
            research, session, actor, case, parent.id  # per-case retrieval (binding v4)
        )
        packet = research.provider_input.__wrapped__(research, session, actor, binding)
        approval_id = INAPP_PREFIX + uuid4().hex
        config = ResearchClaudeConfig(
            approval_id=approval_id,
            terms_sha256=grant["terms_sha256"],
            research_binding_sha256=binding.binding_sha256,
            research_scope_sha256=grant["scope_sha256"],
            exact_input_sha256=digest(packet.model_dump(mode="json")),
            wire_format="flat_selection_v3",
            wire_schema_sha256=digest(output_schema(grounded=True, wire_format="flat_selection_v3")),
            max_cost_usd=grant["reservation_usd"],
        )
        if (
            config.model != grant["model"]
            or config.max_input_tokens != grant["maximum_input_tokens"]
            or config.max_output_tokens != grant["maximum_output_tokens"]
            or config.request_deadline_seconds != grant["timeout_seconds"]
        ):
            raise EvidenceBlocked("research_owner_policy_required")
        raw = request_body(
            packet,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        # stage() retires this user's expired drafts through the audited lifecycle.
        result = self.drafts.stage.__wrapped__(
            self.drafts, session, actor, case, "research-start-" + key, request, binding, config
        )
        run = self.drafts._run(session, UUID(result["draft_run_id"]))
        scope = Path(self.settings.academic_research_scope_file).resolve(strict=True)
        (scope.parent / "inapp" / approval_id).mkdir(parents=True, exist_ok=False)
        self.drafts._event(
            session,
            run,
            PREPARED_EVENT,
            request_sha256=hashlib.sha256(raw).hexdigest(),
            request_bytes=len(raw),
            expires_second=binding.expires_second,
        )
        session.flush()
        job = session.get(DraftJob, run.id)
        return self._status(self.drafts._job_view(job, run), config)

    @atomic
    def review(self, session, actor, case, run_id):
        """AI Request Review: the exact prepared request. Viewing never approves anything."""
        self.drafts.coordinator._gate(session)
        run = self._inapp_run(session, actor, case, run_id)
        job = session.get(DraftJob, run.id)
        try:
            phase = self._phase(session, actor, run, job)
        except (VerificationFailed, SnapshotStale):
            phase = "request_expired"
        config = self.drafts._configuration(run)
        binding = self.drafts._grounding(session, run)
        prepared = self.drafts.prepared_request_sha256(session, run)
        research = ResearchEvidenceService(self.engine, self.settings)
        packet = research.provider_input.__wrapped__(
            research, session, actor, binding, require_current=False
        )
        raw = request_body(
            packet,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        if hashlib.sha256(raw).hexdigest() != prepared and phase == "awaiting_approval":
            phase = "request_changed"
        grant = owner_approvers(self.settings)
        stamp = lambda second: datetime.fromtimestamp(second, timezone.utc).isoformat()  # noqa: E731
        return {
            "draft_run_id": str(run.id),
            "case_id": str(case),
            "phase": phase,
            "can_approve": self.drafts.can_approve(session, actor) and phase == "awaiting_approval",
            "is_approver": self.drafts.can_approve(session, actor),
            "model": config.model,
            "data_scope": "synthetic_only",
            "max_input_tokens": config.max_input_tokens,
            "max_output_tokens": config.max_output_tokens,
            "timeout_seconds": config.request_deadline_seconds,
            "maximum_requests": 1,
            "automatic_retries": False,
            "reservation_usd": str(config.max_cost_usd),
            "cumulative_cap_usd": grant["cumulative_cap_usd"] if grant else None,
            "spent_usd": str(self.drafts.research_spent(session, exclude_run=run.id)),
            "expires_at": stamp(binding.expires_second),
            "approve_before": stamp(binding.expires_second - config.request_deadline_seconds - 30),
            "financial_facts": [
                {
                    "reference_id": f["reference_id"],
                    "observed_total": f["result"].get("observed_total"),
                    "observed_count": f["result"].get("observed_count"),
                    "currency": f["result"].get("currency"),
                    "window": f["result"].get("window"),
                }
                for f in packet.financial_facts
            ],
            "transactions": len(packet.transactions),
            "model_signal": None
            if packet.model_signal is None
            else {"score": packet.model_signal["score"], "model_version": packet.model_signal["model_version"]},
            "missing_evidence": list(packet.missing_evidence),
            "limitations": list(packet.limitations),
            "regulatory_status": "UNAPPROVED RESEARCH — NOT PRODUCTION REGULATORY GUIDANCE",
            "regulatory_sources": [
                {
                    "reference_id": str(p.reference_id),
                    "section": p.section,
                    "approval_status": p.approval_status,
                    "historical_as_of": p.historical_as_of,
                    "text_sha256": p.text_sha256,
                    "source_url": p.source_url,
                }
                for p in binding.passages
            ],
            "request_sha256": prepared,
            "request_bytes": len(raw),
            "request": json.loads(raw),
        }

    @atomic
    def approve(self, session, actor, case, run_id, request_sha256):
        """Approve & Run Once. Every value is re-derived server-side; the browser supplies only
        the hash it displayed, which must equal the exact request rebuilt now."""
        self.drafts.coordinator._gate(session)
        run = self._inapp_run(session, actor, case, run_id)
        if not self.drafts.can_approve(session, actor):
            raise EvidenceBlocked("research_approver_required")
        job = session.scalar(select(DraftJob).where(DraftJob.run_id == run.id).with_for_update())
        marker = "research-ui-approve-" + str(run.id)
        if job.status != "pending" or self.drafts.recorded(session, run, APPROVED_EVENT):
            # Duplicate click, second tab, refresh or network retry: never a second dispatch.
            return self._status(self.drafts._job_view(job, run), self.drafts._configuration(run))
        if self.drafts.recorded(session, run, CANCELLED_EVENT):
            raise EvidenceConflict("research_request_cancelled")
        prepared = self.drafts.prepared_request_sha256(session, run)
        _, _, raw = self._build(session, actor, run)  # SnapshotStale once expired
        if not (hashlib.sha256(raw).hexdigest() == prepared == request_sha256):
            raise EvidenceConflict("research_request_changed")
        try:
            self.drafts._dispatch_window(session, run)
        except VerificationFailed:
            raise SnapshotStale("research_context_expired") from None
        grant = self.drafts.generation_admitted(session, run.actor_id, exclude_run=run.id)
        audit(
            session,
            actor,
            "investigation.draft." + APPROVED_EVENT,
            run.id,
            decision="approved",
            affirmative_click="Approve & Run Once",
            approver_id=str(actor),
            decided_at=datetime.now(timezone.utc).isoformat(),
            request_sha256=prepared,
            reservation_usd=grant["reservation_usd"],
            cumulative_cap_usd=grant["cumulative_cap_usd"],
            spent_before_usd=str(self.drafts.research_spent(session, exclude_run=run.id)),
            owner_policy_reference=grant["owner_decision_reference"],
        )
        session.flush()
        # The worker's own exact gate must accept the recorded approval before queueing.
        self.drafts.approved_execution(session, run)._dispatch_window(session, run)
        session.add(
            DraftRequest(
                actor_id=run.actor_id, idempotency_key=marker, run_id=run.id,
                manifest_sha256=run.manifest_sha256,
            )
        )
        self.drafts._event(session, run, "research_execution_requested")
        return self._status(self.drafts._job_view(job, run), self.drafts._configuration(run))

    @atomic
    def cancel(self, session, actor, case, run_id):
        """Cancel a request that has not been dispatched; retired through the audited path."""
        self.drafts.coordinator._gate(session)
        run = self._inapp_run(session, actor, case, run_id)
        job = session.scalar(select(DraftJob).where(DraftJob.run_id == run.id).with_for_update())
        if job.status == "pending":
            if not self.drafts.recorded(session, run, CANCELLED_EVENT):
                audit(session, actor, "investigation.draft." + CANCELLED_EVENT, run.id,
                      cancelled_at=datetime.now(timezone.utc).isoformat())
            self.drafts._fail(session, job, "input_invalidated", invalidated=True)
        return self._status(self.drafts._job_view(job, run), self.drafts._configuration(run))

    def _latest(self, session, actor, case):
        return session.scalar(
            select(DraftRun)
            .join(InvestigationRun, DraftRun.parent_run_id == InvestigationRun.id)
            .where(
                DraftRun.actor_id == actor,
                InvestigationRun.case_id == case,
                DraftRun.configuration["research_scope"].as_string() == "academic_research_v1",
            )
            .order_by(DraftRun.created_at.desc(), DraftRun.id.desc())
            .limit(1)
        )

    @atomic
    def context(self, session, actor, case):
        self.drafts.coordinator._gate(session)
        self.drafts.coordinator.reader._context(session, actor, case)
        research = ResearchEvidenceService(self.engine, self.settings)
        try:
            research._scope(session, actor, case)
        except EvidenceBlocked as error:
            if str(error) == "research_scope_denied":
                raise EvidenceNotFound("research_context_not_found") from None
            raise
        run = self._latest(session, actor, case)
        if run is None:
            raise EvidenceNotFound("research_context_not_found")
        binding = self.drafts._grounding(session, run)
        passages, dispatch_status = research.passages_for_read(session, actor, binding)
        audit(
            session,
            actor,
            "investigation.research_context_read",
            run.id,
            binding_sha256=binding.binding_sha256,
        )
        return {
            "status": "research_unapproved",
            "draft_run_id": str(run.id),
            "notice": binding.notice,
            "passages": [p.model_dump(mode="json") for p in passages],
            "dispatch_binding_status": dispatch_status,
            "authorizes_dispatch": False,
            "binding_sha256": binding.binding_sha256,
            "publication_approved": False,
        }
