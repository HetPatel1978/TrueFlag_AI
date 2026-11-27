"""Academic extension of the existing durable draft service; no production source approvals."""

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import or_, select, text

from app.models import User
from app.models.domain import AuditEvent
from app.models.investigation_drafts import (
    DraftAttempt,
    DraftJob,
    DraftReceipt,
    DraftRequest,
    DraftRun,
)
from app.models.regulatory_drafts import DraftRegulatoryBinding
from app.schemas.research_demo import (
    ResearchAIDraftBody,
    ResearchAIDraftBodyV3,
    ResearchBinding,
    ResearchClaudeConfig,
    parse_binding,
)
from app.services.claude_contract import request_body
from app.services.evidence import EvidenceBlocked, EvidenceConflict, EvidenceError, atomic
from app.services.evidence_read import SnapshotStale
from app.services.ingestion import digest
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_provider import strict_json
from app.services.investigation_verifier import VerificationFailed
from app.services.research_demo import ResearchEvidenceService


INAPP_PREFIX = "inapp-"
PREPARED_EVENT = "research_request_prepared"
APPROVED_EVENT = "research_request_owner_approved"
CANCELLED_EVENT = "research_request_cancelled"


def owner_approvers(settings):
    """Owner-written spending-approver policy, kept outside the web app, or None.

    It names the individual user IDs allowed to approve paid research inference; no role
    (analyst, supervisor or admin) receives this permission implicitly.
    """
    if not settings.academic_research_approver_file or not settings.academic_research_scope_file:
        return None
    try:
        path = Path(settings.academic_research_approver_file).resolve(strict=True)
        scope = Path(settings.academic_research_scope_file).resolve(strict=True)
        if path.parent != scope.parent:
            return None
        with path.open("rb") as stream:
            grant = strict_json(stream.read(8193).decode(), 8192)
        cap = Decimal(grant.get("cumulative_cap_usd", ""))
        reservation = Decimal(grant.get("reservation_usd", ""))
        recorded = datetime.fromisoformat(grant.get("recorded_at", ""))
        approvers = [str(UUID(value)) for value in grant.get("approver_user_ids", [])]
    except (OSError, TypeError, ValueError, ArithmeticError, AttributeError):
        return None
    if (
        grant.get("decision") != "in_app_exact_request_approval"
        or grant.get("scope_sha256") != settings.academic_research_scope_sha256
        or not 1 <= len(approvers) <= 10
        or approvers != grant.get("approver_user_ids")
        or grant.get("maximum_requests_per_approval") != 1
        or grant.get("automatic_retries") is not False
        or grant.get("synthetic_only") is not True
        or grant.get("production_publication_authorized") is not False
        or not grant.get("owner_decision_reference")
        or not re.fullmatch(r"[a-f0-9]{64}", grant.get("terms_sha256", ""))
        or recorded.utcoffset() is None
        or not Decimal("0") < reservation <= cap <= Decimal("50")
    ):
        return None
    return grant


class ResearchDraftService(InvestigationDraftService):
    def research_spent(self, session, exclude_run=None):
        """Estimated spend of in-app approved attempts; unknown cost counts as reserved."""
        grant = owner_approvers(self.settings)
        reservation = Decimal(grant["reservation_usd"]) if grant else Decimal("2.14")
        rows = session.execute(
            select(DraftAttempt.id, DraftAttempt.run_id, DraftReceipt.usage)
            .join(DraftRun, DraftAttempt.run_id == DraftRun.id)
            .outerjoin(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
            .where(DraftRun.configuration["approval_id"].as_string().startswith(INAPP_PREFIX))
        ).all()
        spent = Decimal("0")
        for _, run_id, usage in rows:
            if run_id == exclude_run:
                continue
            cost = (usage or {}).get("cost_usd")
            try:
                spent += Decimal(str(cost)) if cost is not None else reservation
            except ArithmeticError:
                spent += reservation
        return spent

    def anthropic_usage(self, session, now):
        """Read-only aggregate for the admin Provider Usage card. No credential is read."""
        grant = owner_approvers(self.settings)
        reservation = Decimal(grant["reservation_usd"]) if grant else Decimal("2.14")
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = session.execute(
            select(DraftAttempt.created_at, DraftReceipt.usage)
            .join(DraftRun, DraftAttempt.run_id == DraftRun.id)
            .outerjoin(DraftReceipt, DraftReceipt.attempt_id == DraftAttempt.id)
            .where(DraftRun.configuration["approval_id"].as_string().startswith(INAPP_PREFIX))
        ).all()
        month_requests, month_spend = 0, Decimal("0")
        for created, usage in rows:
            created = created if created.tzinfo else created.replace(tzinfo=now.tzinfo)
            if created < start:
                continue
            month_requests += 1
            cost = (usage or {}).get("cost_usd")
            try:
                month_spend += Decimal(str(cost)) if cost is not None else reservation
            except ArithmeticError:
                month_spend += reservation
        enabled = bool(self.settings.academic_research_enabled)
        return {
            "provider": "anthropic",
            "status": (
                "available"
                if enabled and grant is not None
                else "approval_policy_missing"
                if enabled
                else "disabled"
            ),
            "model": grant.get("model") if grant else None,
            "runs_investigations": enabled,
            "requests_this_month": month_requests,
            "requests_total": len(rows),
            "spent_this_month_usd": str(month_spend.quantize(Decimal("0.01"))),
            "spent_total_usd": str(self.research_spent(session).quantize(Decimal("0.01"))),
            "cumulative_cap_usd": grant["cumulative_cap_usd"] if grant else None,
            "reservation_usd": grant["reservation_usd"] if grant else None,
            "approval_rule": (
                "Each request is approved individually by a named spending approver; "
                "one request per approval, no automatic retries."
            ),
        }

    def generation_admitted(self, session, actor, exclude_run=None):
        """Raise unless the owner policy exists and the cap still covers one reservation."""
        grant = owner_approvers(self.settings)
        if grant is None:
            raise EvidenceBlocked("research_owner_policy_required")
        user = session.get(User, actor)
        if user is None or not user.active:
            raise EvidenceBlocked("research_user_inactive")
        if self.research_spent(session, exclude_run) + Decimal(grant["reservation_usd"]) > Decimal(
            grant["cumulative_cap_usd"]
        ):
            raise EvidenceBlocked("research_budget_exhausted")
        return grant

    def can_approve(self, session, actor):
        """Server-side spending permission: an active user named by the owner policy."""
        grant = owner_approvers(self.settings)
        user = session.get(User, actor) if actor is not None else None
        return bool(
            grant is not None
            and user is not None
            and user.active
            and str(actor) in grant["approver_user_ids"]
        )

    def recorded(self, session, run, action):
        return session.scalars(
            select(AuditEvent).where(
                AuditEvent.resource_id == str(run.id),
                AuditEvent.action == "evidence.investigation.draft." + action,
            )
        ).all()

    def prepared_request_sha256(self, session, run):
        """The exact request hash recorded when the request was prepared for review."""
        events = self.recorded(session, run, PREPARED_EVENT)
        if len(events) != 1 or not re.fullmatch(
            r"[a-f0-9]{64}", str(events[0].details.get("request_sha256", ""))
        ):
            raise EvidenceBlocked("research_exact_approval_required")
        return events[0].details["request_sha256"]

    def owner_approval(self, session, run):
        """The approver's affirmative decision on this exact request, under current policy."""
        events = self.recorded(session, run, APPROVED_EVENT)
        if len(events) != 1 or self.recorded(session, run, CANCELLED_EVENT):
            raise EvidenceBlocked("research_exact_approval_required")
        decision = events[0]
        if not self.can_approve(session, decision.actor_id):  # stale permission
            raise EvidenceBlocked("research_exact_approval_required")
        if decision.details.get("request_sha256") != self.prepared_request_sha256(session, run):
            raise EvidenceBlocked("research_exact_approval_required")
        return decision.details["request_sha256"]

    def approved_execution(self, session, run):
        """Derive only the exact owner grant; this never enables ordinary inference."""
        config = self._configuration(run)
        if not isinstance(config, ResearchClaudeConfig):
            raise EvidenceBlocked("research_config_required")
        if config.approval_id.startswith(INAPP_PREFIX):
            # In-app approval: an authorized approver's decision on the exact prepared request.
            self.generation_admitted(session, run.actor_id, exclude_run=run.id)
            scope = Path(self.settings.academic_research_scope_file).resolve(strict=True)
            settings = self.settings.model_copy(
                update=dict(
                    anthropic_research_dispatch_enabled=True,
                    anthropic_research_approval_id=config.approval_id,
                    anthropic_research_input_sha256=config.exact_input_sha256,
                    anthropic_research_request_sha256=self.owner_approval(session, run),
                    anthropic_terms_sha256=config.terms_sha256,
                    academic_research_response_file=scope.parent
                    / "inapp"
                    / config.approval_id
                    / "http-response.json",
                )
            )
            service = ResearchDraftService(self.engine, settings)
            service._approved_request(session, run)
            return service
        try:
            path = Path(self.settings.academic_research_approval_file).resolve(strict=True)
            scope = Path(self.settings.academic_research_scope_file).resolve(strict=True)
            if path.parent != scope.parent:
                raise EvidenceBlocked("research_private_approval_required")
            with path.open("rb") as stream:
                approval = strict_json(stream.read(8193).decode(), 8192)
        except (OSError, TypeError, ValueError):
            raise EvidenceBlocked("research_exact_approval_required") from None
        settings = self.settings.model_copy(
            update=dict(
                anthropic_research_dispatch_enabled=True,
                anthropic_research_approval_id=approval.get("approval_id", ""),
                anthropic_research_input_sha256=config.exact_input_sha256,
                anthropic_research_request_sha256=approval.get("request_sha256", ""),
                anthropic_terms_sha256=config.terms_sha256,
                academic_research_response_file=scope.parent / config.approval_id / "http-response.json",
            )
        )
        service = ResearchDraftService(self.engine, settings)
        service._approved_request(session, run)
        return service

    def run_requested_once(self, token):
        try:
            return self._run_requested_once(token)
        except (EvidenceError, VerificationFailed, OSError, ValueError):
            return None  # No dispatch; preserve pending authority for explicit operator review.

    def _run_requested_once(self, token):
        """Existing worker: one owner-approved job, only after an explicit UI request."""
        if not self.settings.academic_research_enabled:
            return None
        path = self.settings.academic_research_approval_file
        granted = []
        if path is not None and Path(path).is_file():
            with Path(path).open("rb") as stream:
                approval = strict_json(stream.read(8193).decode(), 8192)
            granted.append(
                DraftRun.configuration["approval_id"].as_string() == approval.get("approval_id")
            )
        if owner_approvers(self.settings) is not None:
            granted.append(
                DraftRun.configuration["approval_id"].as_string().startswith(INAPP_PREFIX)
            )
        if not granted:
            return None
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import Session

        try:
            service = self._requested_service(Session, granted)
        except OperationalError:
            # A transient lock conflict (e.g. deadlock with an approval or status request)
            # before any provider request: nothing was sent and the transaction rolled back.
            # The job stays as it was and is re-checked on the next tick; this is not a
            # provider retry. Previously this escaped and stopped the worker process.
            return None
        if service is None:
            return None
        # API credentials are read only by the worker after exact grant/source/clock checks.
        from dotenv import dotenv_values
        from pydantic import SecretStr

        credential_file = self.settings.academic_research_credential_file
        if credential_file is None:
            raise EvidenceBlocked("research_credential_unavailable")
        credential = dotenv_values(credential_file).get("ANTHROPIC_API_KEY")
        if not credential:
            raise EvidenceBlocked("research_credential_unavailable")
        service.settings.anthropic_api_key = SecretStr(credential)
        return service.run_once(token)

    def _requested_service(self, Session, granted):
        """Pre-dispatch checks for the newest owner-approved job (no provider contact)."""
        with Session(self.engine) as session, session.begin():
            # Bounded waits so a lock conflict fails fast instead of stalling the worker.
            session.execute(text("SET LOCAL lock_timeout='2s'"))
            session.execute(text("SET LOCAL statement_timeout='5s'"))
            run = session.scalar(
                select(DraftRun)
                .join(DraftJob)
                .where(
                    or_(*granted),
                    DraftJob.status.in_(["pending", "running"]),
                    select(DraftRequest.run_id)
                    .where(
                        DraftRequest.run_id == DraftRun.id,
                        DraftRequest.actor_id == DraftRun.actor_id,
                        DraftRequest.idempotency_key.startswith("research-ui-"),
                    )
                    .exists(),
                )
                .order_by(DraftRun.created_at.desc(), DraftRun.id.desc())
                .limit(1)
            )
            if run is None:
                return None
            service = self.approved_execution(session, run)
            service._dispatch_window(session, run)
        return service

    def _execution_limits(self, config):
        if isinstance(config, ResearchClaudeConfig):
            return config.request_deadline_seconds + 30, config.request_deadline_seconds + 60
        return super()._execution_limits(config)

    def _receipt(self, session, attempt, status, reply=None, elapsed=None, diagnostics=None):
        super()._receipt(session, attempt, status, reply, elapsed, diagnostics)
        # The original receipt schema caps elapsed_ms at 60 seconds. Preserve its
        # constraint and record longer bounded durations in immutable audit history.
        if attempt is not None and elapsed is not None and 60000 < elapsed <= 180000:
            run = self._run(session, attempt.run_id)
            self._event(session, run, "provider_duration", elapsed_ms=elapsed, status=status)

    def _dispatch_window(self, session, run):
        binding = self._grounding(session, run)
        config = self._configuration(run)
        observed = self.coordinator.reader.clock.observe()
        if (
            observed.epoch != binding.clock_epoch
            or binding.expires_second - observed.second <= config.request_deadline_seconds + 30
        ):
            raise VerificationFailed("research_dispatch_window_insufficient")

    def _enabled(self, config=None):
        if config is None and self.settings.academic_research_enabled:
            return
        if isinstance(config, ResearchClaudeConfig):
            if not self.settings.academic_research_enabled:
                raise EvidenceBlocked("academic_research_disabled")
            return  # Staging is permitted; prepare/recheck/provider enforce exact paid authority.
        return super()._enabled(config)

    def _job_scope(self):
        query = select(DraftRun.id).where(
            DraftRun.configuration["research_scope"].as_string() == "academic_research_v1"
        )
        if self.settings.anthropic_research_dispatch_enabled:
            query = query.where(
                DraftRun.configuration["approval_id"].as_string()
                == self.settings.anthropic_research_approval_id
            )
        return DraftJob.run_id.in_(query)

    def _grounding(self, session, run):
        config = self._configuration(run)
        if not isinstance(config, ResearchClaudeConfig):
            return super()._grounding(session, run)
        row = session.get(DraftRegulatoryBinding, run.id)
        if (
            row is None
            or row.actor_id != run.actor_id
            or row.parent_run_id != run.parent_run_id
            or row.run_manifest_sha256 != run.manifest_sha256
            or row.binding_sha256 != config.research_binding_sha256
        ):
            raise VerificationFailed("research_binding_invalid")
        binding = parse_binding(row.body)
        if (
            binding.case_id != row.case_id
            or binding.actor_id != run.actor_id
            or binding.investigation_run_id != run.parent_run_id
            or binding.binding_sha256 != row.binding_sha256
            or binding.scope_sha256 != config.research_scope_sha256
        ):
            raise VerificationFailed("research_binding_invalid")
        return binding

    def _provider_input(self, session, run, packet):
        if not isinstance(self._configuration(run), ResearchClaudeConfig):
            return super()._provider_input(session, run, packet)
        research = ResearchEvidenceService(self.engine, self.settings)
        job = session.get(DraftJob, run.id)
        # A completed result stays readable after the dispatch window; unfinished work expires.
        completed = job is not None and job.status in {"succeeded", "abstained"}
        return research.provider_input.__wrapped__(
            research,
            session,
            run.actor_id,
            self._grounding(session, run),
            require_current=not completed,
        )

    def _retire_expired(self, session, actor):
        """Invalidate this actor's expired, unclaimed research drafts via the audited path."""
        jobs = session.scalars(
            select(DraftJob)
            .join(DraftRun)
            .where(
                DraftRun.actor_id == actor,
                DraftJob.status == "pending",
                DraftRun.configuration["research_scope"].as_string() == "academic_research_v1",
            )
            .with_for_update(of=DraftJob, skip_locked=True)
        ).all()
        for job in jobs:
            run = self._run(session, job.run_id)
            try:
                self._provider_input(session, run, self._packet(session, run))
            except SnapshotStale:
                self._fail(session, job, "input_invalidated", invalidated=True)

    @atomic
    def stage(self, session, actor, case, key, request, binding, config):
        if (
            not isinstance(config, ResearchClaudeConfig)
            or not isinstance(binding, ResearchBinding)
            or binding.actor_id != actor
            or binding.case_id != case
            or config.research_binding_sha256 != binding.binding_sha256
        ):
            raise EvidenceBlocked("research_binding_required")
        research = ResearchEvidenceService(self.engine, self.settings)
        packet = research.provider_input.__wrapped__(research, session, actor, binding)
        if digest(packet.model_dump(mode="json")) != config.exact_input_sha256:
            raise EvidenceConflict("research_input_changed")
        self._retire_expired(session, actor)
        result = super().request.__wrapped__(self, session, actor, case, key, request, config)
        run = self._run(session, UUID(result["draft_run_id"]))
        if run.parent_run_id != binding.investigation_run_id:
            raise EvidenceConflict("research_parent_changed")
        prior = session.get(DraftRegulatoryBinding, run.id)
        if prior is None:
            session.add(
                DraftRegulatoryBinding(
                    run_id=run.id,
                    actor_id=actor,
                    case_id=case,
                    parent_run_id=run.parent_run_id,
                    run_manifest_sha256=run.manifest_sha256,
                    binding_sha256=binding.binding_sha256,
                    body=binding.model_dump(mode="json"),
                )
            )
            self._event(
                session,
                run,
                "research_bound",
                binding_sha256=binding.binding_sha256,
                production_publication_authorized=False,
            )
            session.flush()
        elif prior.binding_sha256 != binding.binding_sha256:
            raise EvidenceConflict("research_binding_changed")
        return result

    def _approved_request(self, session, run):
        settings = self.settings
        config = self._configuration(run)
        if not isinstance(config, ResearchClaudeConfig):
            raise EvidenceBlocked("research_config_required")
        packet = self._packet(session, run)
        minimized = self._provider_input(session, run, packet)
        raw = request_body(
            minimized,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        if config.approval_id.startswith(INAPP_PREFIX):
            grant = self.generation_admitted(session, run.actor_id, exclude_run=run.id)
            sha = hashlib.sha256(raw).hexdigest()
            if (
                not settings.anthropic_research_dispatch_enabled
                or settings.anthropic_research_approval_id != config.approval_id
                or sha != settings.anthropic_research_request_sha256
                or sha != self.owner_approval(session, run)
                or config.research_scope_sha256 != grant["scope_sha256"]
                or config.terms_sha256 != grant["terms_sha256"]
                or config.model != grant["model"]
                or config.max_input_tokens != grant["maximum_input_tokens"]
                or config.max_output_tokens != grant["maximum_output_tokens"]
                or config.request_deadline_seconds != grant["timeout_seconds"]
                or config.max_cost_usd != Decimal(grant["reservation_usd"])
            ):
                raise EvidenceBlocked("research_exact_approval_required")
            return minimized
        if (
            not settings.anthropic_research_dispatch_enabled
            or not settings.academic_research_approval_file
        ):
            raise EvidenceBlocked("research_exact_approval_required")
        path = Path(settings.academic_research_approval_file).resolve(strict=True)
        scope = Path(settings.academic_research_scope_file).resolve(strict=True)
        if path.parent != scope.parent:
            raise EvidenceBlocked("research_private_approval_required")
        with path.open("rb") as stream:
            approval = strict_json(stream.read(8193).decode(), 8192)
        if (
            approval.get("decision") != "approved"
            or approval.get("approval_id") != config.approval_id
            or approval.get("request_sha256") != hashlib.sha256(raw).hexdigest()
            or approval.get("request_sha256") != settings.anthropic_research_request_sha256
            or approval.get("scope_sha256") != config.research_scope_sha256
            or approval.get("configuration_sha256") != digest(config.model_dump(mode="json"))
            or approval.get("maximum_input_tokens") != config.max_input_tokens
            or approval.get("maximum_output_tokens") != config.max_output_tokens
            or approval.get("timeout_seconds") != config.request_deadline_seconds
            or approval.get("actor_id") != str(run.actor_id)
            or approval.get("case_id") != str(self._grounding(session, run).case_id)
            or type(approval.get("maximum_requests")) is not int
            or approval.get("maximum_requests") != 1
            or approval.get("automatic_retries") is not False
            or approval.get("synthetic_only") is not True
            or not approval.get("owner_decision_reference")
            or datetime.fromisoformat(approval.get("recorded_at", "")).utcoffset() is None
        ):
            raise EvidenceBlocked("research_exact_approval_required")
        return minimized

    @atomic
    def prepare(self, session, token, claim):
        self.coordinator._gate(session)
        job = self._leased(session, token, claim)
        run = self._run(session, job.run_id)
        self._approved_request(session, run)
        self._dispatch_window(session, run)
        self._event(
            session,
            run,
            "research_request_authorized",
            request_sha256=self.settings.anthropic_research_request_sha256,
            approval_id=self._configuration(run).approval_id,
        )
        return super().prepare.__wrapped__(self, session, token, claim)

    @atomic
    def recheck_dispatch(self, session, token, claim):
        super().recheck_dispatch.__wrapped__(self, session, token, claim)
        job = self._leased(session, token, claim)
        run = self._run(session, job.run_id)
        self._approved_request(session, run)
        self._dispatch_window(session, run)

    def _complete_grounding(self, session, run, proposal, body):
        if not isinstance(self._configuration(run), ResearchClaudeConfig):
            return super()._complete_grounding(session, run, proposal, body)
        self._approved_request(session, run)
        binding = self._grounding(session, run)
        research = ResearchEvidenceService(self.engine, self.settings)
        cited = research.verify.__wrapped__(research, session, run.actor_id, binding, proposal)
        values = {
            **body.model_dump(mode="json"),
            "regulatory_context": "research_unapproved",
            "regulatory_citations": cited,
            "research_binding_sha256": binding.binding_sha256,
        }
        if self._configuration(run).wire_format == "flat_selection_v3":
            values["finding_citations"] = [
                link.model_dump(mode="json") for link in proposal.finding_citations
            ]
            return ResearchAIDraftBodyV3.model_validate(values)
        return ResearchAIDraftBody.model_validate(values)

    def _stored_body_class(self, run, default):
        config = self._configuration(run)
        if not isinstance(config, ResearchClaudeConfig):
            return default
        return (
            ResearchAIDraftBodyV3
            if config.wire_format == "flat_selection_v3"
            else ResearchAIDraftBody
        )

    def run_once(self, token):
        if not self.settings.anthropic_research_dispatch_enabled:
            return None  # Approval wait does not claim/fail jobs or reserve paid attempts.
        return super().run_once(token)
