"""Bridge existing authorized retrieval and verified packets, without publication authority."""

from sqlalchemy import select

from app.models import Alert
from app.models.investigations import InvestigationPacket
from app.models.references import ReferenceGrant
from app.schemas.investigations import InputManifest, InvestigationPacketBody
from app.schemas.regulatory_investigation import (
    GroundedAIProposal,
    GroundedProviderInput,
    GroundedSimulationProposal,
    InvestigationRegulatoryContext,
)
from app.services.evidence import EvidenceBlocked, atomic, audit
from app.services.ingestion import digest
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.investigation_draft_verifier import minimize, validate_proposal
from app.services.investigation_verifier import VerificationFailed
from app.services.references import ReferenceService


class RegulatoryInvestigationService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.coordinator = InvestigationCoordinator(engine, settings)
        self.references = ReferenceService(engine, settings)

    def _packet(self, session, actor, case, run):
        view = self.coordinator.get.__wrapped__(self.coordinator, session, actor, case, run)
        if view["status"] not in {"succeeded", "abstained"} or not view.get("packet"):
            raise EvidenceBlocked("verified_investigation_required")
        return InvestigationPacketBody.model_validate(view["packet"])

    @atomic
    def prepare(self, session, actor, case, run, query):
        self.coordinator._gate(session)
        packet = self._packet(session, actor, case, run)
        result = self.references.retrieve_reference_context.__wrapped__(
            self.references, session, actor, case, query
        )
        grounding = None
        if result.status == "available" and result.passages:
            grounding = self.references.validate_regulatory_selection.__wrapped__(
                self.references, session, actor, case, tuple(result.passages)
            )
            self._origin(grounding)
        payload = dict(
            case_id=case,
            investigation_run_id=run,
            packet_id=session.scalar(
                select(InvestigationPacket.id).where(InvestigationPacket.run_id == run)
            ),
            packet_sha256=digest(packet.model_dump(mode="json")),
            result=result,
            query=query,
            grounding=grounding,
        )
        observed = self.coordinator.reader.clock.observe()
        parent = self.coordinator._run(session, run)
        grant = (
            session.get(ReferenceGrant, (result.context_id, actor)) if result.context_id else None
        )
        payload.update(
            snapshot=InputManifest.model_validate(parent.input_manifest).snapshot,
            grant_revision=grant.revision if grant else None,
            clock_epoch=observed.epoch,
            prepared_second=observed.second,
            expires_second=observed.second + 900,
        )
        binding = InvestigationRegulatoryContext(**payload, binding_sha256="0" * 64)
        binding = binding.model_copy(
            update={
                "binding_sha256": digest(
                    binding.model_dump(mode="json", exclude={"binding_sha256"})
                )
            }
        )
        if len(binding.model_dump_json().encode()) > 49152:
            raise EvidenceBlocked("regulatory_grounding_size_limit")
        audit(
            session,
            actor,
            "investigation.regulatory_prepared",
            run,
            binding_sha256=binding.binding_sha256,
            passages=len(result.passages),
            status=result.status,
        )
        return binding

    def _origin(self, grounding):
        if self.settings.app_env != "test" and any(
            source.citation.origin != "official_curated" or source.review_kind != "human"
            for source in grounding.sources
        ):
            raise EvidenceBlocked("official_source_review_required")

    def _revalidate(self, session, actor, binding):
        if (
            not isinstance(binding, InvestigationRegulatoryContext)
            or digest(binding.model_dump(mode="json", exclude={"binding_sha256"}))
            != binding.binding_sha256
        ):
            raise VerificationFailed("regulatory_binding_invalid")
        packet = self._packet(session, actor, binding.case_id, binding.investigation_run_id)
        observed = self.coordinator.reader.clock.observe()
        if (
            observed.epoch != binding.clock_epoch
            or observed.second < binding.prepared_second
            or observed.second >= binding.expires_second
            or binding.expires_second - binding.prepared_second != 900
        ):
            raise VerificationFailed("regulatory_binding_expired")
        parent = self.coordinator._run(session, binding.investigation_run_id)
        if (
            session.scalar(
                select(InvestigationPacket.id).where(InvestigationPacket.run_id == parent.id)
            )
            != binding.packet_id
        ):
            raise VerificationFailed("regulatory_packet_changed")
        if InputManifest.model_validate(parent.input_manifest).snapshot != binding.snapshot:
            raise VerificationFailed("regulatory_snapshot_changed")
        if digest(packet.model_dump(mode="json")) != binding.packet_sha256:
            raise VerificationFailed("regulatory_packet_changed")
        if binding.grounding is None or binding.result.status != "available":
            raise EvidenceBlocked("approved_regulatory_context_unavailable")
        current = self.references.validate_regulatory_selection.__wrapped__(
            self.references, session, actor, binding.case_id, tuple(binding.result.passages)
        )
        self._origin(current)
        grant = session.get(ReferenceGrant, (binding.result.context_id, actor))
        if grant is None or not grant.active or grant.revision != binding.grant_revision:
            raise VerificationFailed("regulatory_grant_changed")
        if current != binding.grounding:
            raise VerificationFailed("regulatory_context_changed")
        return packet

    @atomic
    def provider_input(self, session, actor, binding):
        self.coordinator._gate(session)
        packet = self._revalidate(session, actor, binding)
        parent = self.coordinator._run(session, binding.investigation_run_id)
        alert = session.get(Alert, parent.alert_id)
        if alert is None or alert.data_classification != "synthetic":
            raise EvidenceBlocked("synthetic_scope_required")
        values = minimize(packet).model_dump(exclude={"regulatory_context"})
        return GroundedProviderInput.model_validate(
            {
                **values,
                "regulatory_binding_sha256": binding.binding_sha256,
                "regulatory_passages": binding.result.passages,
            }
        )

    @atomic
    def verify(self, session, actor, binding, proposal):
        self.coordinator._gate(session)
        packet = self._revalidate(session, actor, binding)
        if not isinstance(proposal, (GroundedAIProposal, GroundedSimulationProposal)):
            raise VerificationFailed("grounded_response_required")
        allowed = {c.reference_id for c in binding.result.passages}
        cited = proposal.regulatory_citations
        if (
            proposal.regulatory_binding_sha256 != binding.binding_sha256
            or len(cited) != len(set(cited))
            or not set(cited) <= allowed
        ):
            raise VerificationFailed("regulatory_citation_invalid")
        findings = validate_proposal(packet, proposal)
        audit(
            session,
            actor,
            "investigation.regulatory_verified",
            binding.investigation_run_id,
            binding_sha256=binding.binding_sha256,
            citations=len(cited),
        )
        return {
            "financial_findings": findings,
            "regulatory_passages": [
                c.model_dump(mode="json")
                for c in binding.result.passages
                if c.reference_id in cited
            ],
            "legal_correctness_verified": False,
            "human_review_required": True,
        }
