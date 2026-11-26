"""Protected gateway over existing durable draft services and independent provider gates."""

from uuid import UUID

from sqlalchemy import func, select

from app.models.investigation_drafts import DraftJob, DraftRequest, DraftRun
from app.models.investigations import InvestigationRun
from app.schemas.draft_api import (
    DraftDetail,
    DraftHistory,
    DraftHistoryItem,
    DraftStartStatus,
    DraftStatus,
    LiveDraft,
    SimulationDraft,
)
from app.schemas.investigation_drafts import ProviderConfig
from app.schemas.investigations import InputManifest
from app.schemas.provider_live import (
    ClaudeProviderConfig,
    GroundedClaudeConfig,
    GroundedSimulationConfig,
    RegulatoryQueryClaudeConfig,
    RegulatoryQuerySimulationConfig,
)
from app.schemas.references import ReferenceQuery
from app.services.claude_contract import output_schema
from app.services.evidence import EvidenceBlocked, EvidenceConflict, EvidenceNotFound, atomic, audit
from app.services.evidence_read import ReadLimit
from app.services.ingestion import digest
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_verifier import VerificationFailed
from app.services.regulatory_investigation import RegulatoryInvestigationService

ERRORS = {
    "lease_expired",
    "execution_timeout",
    "processing_unavailable",
    "verification_failed",
    "input_invalidated",
    "authorization_revoked",
    "worker_revoked",
    "resource_limit",
    "provider_timeout",
    "provider_unavailable",
    "provider_incomplete",
    "provider_refused",
    "invalid_provider_output",
    "budget_exhausted",
    "database_unavailable",
}


class DraftAPIService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.drafts = InvestigationDraftService(engine, settings)

    def _offline(self):
        if (
            not self.settings.investigation_simulation_enabled
            or self.settings.investigation_external_enabled
        ):
            raise EvidenceBlocked("offline_simulation_unavailable")

    def _owned(self, session, actor, case_id, run_id):
        self.drafts.coordinator.reader._context(session, actor, case_id)
        run = session.scalar(
            select(DraftRun)
            .join(InvestigationRun, DraftRun.parent_run_id == InvestigationRun.id)
            .where(
                DraftRun.id == run_id,
                DraftRun.actor_id == actor,
                InvestigationRun.actor_id == actor,
                InvestigationRun.case_id == case_id,
            )
        )
        if run is None or not isinstance(
            self.drafts._configuration(run), (ProviderConfig, ClaudeProviderConfig)
        ):
            raise EvidenceNotFound("investigation_draft_not_found")
        return run

    def _status(self, values, config=None):
        return DraftStatus(
            draft_run_id=values["draft_run_id"],
            status=values["status"],
            attempts=values["attempts"],
            error_code=values["error_code"]
            if values["error_code"] in ERRORS
            else "processing_unavailable"
            if values["error_code"]
            else None,
            mode="claude_live"
            if isinstance(config, ClaudeProviderConfig)
            else "offline_simulation",
            live_provider_used=isinstance(config, ClaudeProviderConfig)
            and values["status"] in {"succeeded", "abstained"},
        )

    def capabilities(self):
        live = bool(
            self.settings.anthropic_analyst_generation_enabled
            and self.settings.anthropic_contract_verified
            and self.settings.anthropic_synthetic_demo_enabled
        )
        return {
            "provider": "claude"
            if live
            else "simulation"
            if self.settings.investigation_simulation_enabled
            else "unavailable",
            "regulatory_grounding_enabled": bool(self.settings.regulatory_investigation_enabled),
        }

    def _bounded(self, value):
        if len(value.model_dump_json().encode()) > 524288:
            raise ReadLimit("draft_response_limit")
        return value

    @atomic
    def start(self, session, actor, case_id, key, body):
        """Admit parent and child jobs in one transaction; workers enforce dependencies."""
        provider = self.capabilities()["provider"] if body.provider == "auto" else body.provider
        if provider == "simulation":
            self._offline()
            config = ProviderConfig()
        elif provider == "claude" and self.capabilities()["provider"] == "claude":
            config = ClaudeProviderConfig(
                approval_id="synthetic-claude-demo-2026-11-20",
                terms_sha256=self.settings.anthropic_terms_sha256,
                wire_schema_sha256=digest(output_schema()),
                max_cost_usd="2.14",
            )
        else:
            raise EvidenceBlocked("investigation_provider_unavailable")
        query = body.regulatory_query
        if query is None and self.settings.regulatory_investigation_enabled:
            # The existing primary action requests the complete enabled workflow.
            # This public search text contains no customer features; applicability
            # and source publication are still enforced by the existing G5 service.
            query = ReferenceQuery(
                query="bank anti-money laundering program suspicious activity report", limit=5
            )
        if query is not None:
            if not self.settings.regulatory_investigation_enabled:
                raise EvidenceBlocked("regulatory_investigation_disabled")
            values = config.model_dump()
            if isinstance(config, ClaudeProviderConfig):
                values["wire_schema_sha256"] = digest(output_schema(grounded=True))
            config = (
                RegulatoryQueryClaudeConfig
                if isinstance(config, ClaudeProviderConfig)
                else RegulatoryQuerySimulationConfig
            )(**values, regulatory_query=query)
        result = self.drafts.request.__wrapped__(
            self.drafts, session, actor, case_id, key, body.investigation_request, config
        )
        run = self.drafts._run(session, UUID(result["draft_run_id"]))
        return DraftStartStatus(
            **self._status(result, config).model_dump(), investigation_run_id=run.parent_run_id
        )

    @atomic
    def request(self, session, actor, case_id, key, body):
        if body.provider == "simulation":
            self._offline()
            config = ProviderConfig()
        else:
            if self.capabilities()["provider"] != "claude":
                raise EvidenceBlocked("claude_analyst_activation_unavailable")
            config = ClaudeProviderConfig(
                approval_id="synthetic-claude-demo-2026-11-20",
                terms_sha256=self.settings.anthropic_terms_sha256,
                wire_schema_sha256=digest(output_schema()),
                max_cost_usd="2.14",
            )
        coordinator = self.drafts.coordinator
        # The existing authority does all raw-source/numeric/snapshot revalidation.
        parent_view = coordinator.get.__wrapped__(
            coordinator, session, actor, case_id, body.investigation_run_id
        )
        if parent_view.get("packet") is None:
            raise EvidenceConflict("verified_investigation_required")
        if digest(parent_view["packet"]) != body.expected_packet_sha256:
            raise EvidenceConflict("investigation_packet_changed")
        parent = coordinator._run(session, body.investigation_run_id)
        request = InputManifest.model_validate(parent.input_manifest).request
        previous = session.get(DraftRequest, (actor, key))
        if previous is not None:
            prior = self._owned(session, actor, case_id, previous.run_id)
            prior_config = self.drafts._configuration(prior)
            prior_binding = self.drafts._grounding(session, prior)
            if (
                prior.parent_run_id != parent.id
                or isinstance(prior_config, ClaudeProviderConfig) != (body.provider == "claude")
                or (prior_binding.query if prior_binding else None) != body.regulatory_query
            ):
                raise EvidenceConflict("draft_idempotency_conflict")
            packet = self.drafts._packet(session, prior)
            self.drafts._provider_input(session, prior, packet)
            return self._status(
                self.drafts._job_view(session.get(DraftJob, prior.id), prior), prior_config
            )
        binding = None
        if body.regulatory_query is not None:
            if not self.settings.regulatory_investigation_enabled:
                raise EvidenceBlocked("regulatory_investigation_disabled")
            bridge = RegulatoryInvestigationService(self.engine, self.settings)
            binding = bridge.prepare.__wrapped__(
                bridge, session, actor, case_id, parent.id, body.regulatory_query
            )
            values = config.model_dump()
            if isinstance(config, ClaudeProviderConfig):
                values["wire_schema_sha256"] = digest(output_schema(grounded=True))
            config = (
                GroundedClaudeConfig
                if isinstance(config, ClaudeProviderConfig)
                else GroundedSimulationConfig
            )(**values, regulatory_binding_sha256=binding.binding_sha256)
        result = self.drafts.request.__wrapped__(
            self.drafts, session, actor, case_id, key, request, config, binding
        )
        # Existing manifest deduplication must reuse precisely the chosen verified parent.
        child = self.drafts._run(session, UUID(result["draft_run_id"]))
        if child.parent_run_id != parent.id:
            raise VerificationFailed("draft_parent_mismatch")
        return self._status(result, config)

    @atomic
    def detail(self, session, actor, case_id, run_id):
        # Match every worker: advisory coordination gate precedes actor/case row locks.
        self.drafts.coordinator._gate(session)
        run = self._owned(session, actor, case_id, run_id)
        config = self.drafts._configuration(run)
        if not isinstance(config, ClaudeProviderConfig):
            self._offline()
        result = self.drafts.get.__wrapped__(self.drafts, session, actor, case_id, run_id)
        status = self._status(result, config)
        body = result.get("draft")
        projected = None
        if body is not None:
            provenance = body["provenance"]
            if (
                body["mode"] != config.mode
                or provenance.get("simulation")
                is not (not isinstance(config, ClaudeProviderConfig))
                or provenance.get("live_provider_used")
                is not isinstance(config, ClaudeProviderConfig)
                or body["verification"]["status"] != "structural_reference_numeric_checks_passed"
            ):
                raise VerificationFailed("draft_projection_invalid")
            projected = self._project(session, run, config, body, dict(
                content_sha256=digest(body),
                draft_run_id=body["draft_run_id"],
                investigation_run_id=body["investigation_run_id"],
                manifest_sha256=body["input_manifest_sha256"],
                packet_sha256=body["packet_sha256"],
                outcome=body["outcome"],
                findings=[
                    dict(
                        claim_type=f["claim_type"],
                        reference_id=f["reference_id"],
                        supporting_evidence=f["supporting_evidence"],
                        contradictory_evidence=f["contradictory_evidence"],
                        summary=f["server_generated_summary"],
                    )
                    for f in body["findings"]
                ],
                hypotheses=body["hypotheses"],
                questions=body["questions"],
                unresolved_questions=body["unresolved_questions"],
                next_steps=body["next_steps"],
                missing_evidence=body["missing_evidence"],
                conflicts=body["conflicts"],
                limitations=body["limitations"],
                provenance={
                    k: provenance[k]
                    for k in [
                        "provider",
                        "model",
                        "prompt_version",
                        "prompt_sha256",
                        "configuration_sha256",
                        "parent_manifest_sha256",
                    ]
                },
                verification="source_reference_numeric_checks_passed",
                regulatory_context=body["regulatory_context"],
                regulatory_citations=body.get("regulatory_citations", []),
            ))
        return self._bounded(DraftDetail(**status.model_dump(), draft=projected))

    def _project(self, session, run, config, body, values):
        return self._projection(config)(**values)

    def _projection(self, config):
        return LiveDraft if isinstance(config, ClaudeProviderConfig) else SimulationDraft

    @atomic
    def history(self, session, actor, case_id, *, limit=10, offset=0):
        if not self.settings.anthropic_synthetic_demo_enabled:
            self._offline()
        if (
            type(limit) is not int
            or not 1 <= limit <= 20
            or type(offset) is not int
            or not 0 <= offset <= 1000
        ):
            raise EvidenceBlocked("invalid_draft_history")
        self.drafts.coordinator._gate(session)
        self.drafts.coordinator.reader._context(session, actor, case_id)
        query = (
            select(DraftRun, InvestigationRun)
            .join(InvestigationRun, DraftRun.parent_run_id == InvestigationRun.id)
            .where(
                DraftRun.actor_id == actor,
                InvestigationRun.actor_id == actor,
                InvestigationRun.case_id == case_id,
                DraftRun.configuration["provider"]
                .as_string()
                .in_(["deterministic_fake", "anthropic"]),
            )
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.execute(
            query.order_by(DraftRun.created_at.desc(), DraftRun.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items = []
        for run, parent in rows:
            config = self.drafts._configuration(run)
            manifest = InputManifest.model_validate(parent.input_manifest)
            if digest(manifest.model_dump(mode="json")) != parent.manifest_sha256:
                raise VerificationFailed("draft_parent_invalid")
            status = self._status(self.drafts._job_view(session.get(DraftJob, run.id), run), config)
            items.append(
                DraftHistoryItem(
                    **status.model_dump(),
                    investigation_run_id=parent.id,
                    created_at=run.created_at,
                    manifest_sha256=run.manifest_sha256,
                    case_version=manifest.snapshot.case_version,
                    evidence_revision=manifest.snapshot.evidence_revision,
                    access_revision=manifest.snapshot.access_revision,
                )
            )
        audit(session, actor, "investigation.draft.history", case_id, limit=limit, offset=offset)
        return self._bounded(DraftHistory(items=items, total=total, limit=limit, offset=offset))
