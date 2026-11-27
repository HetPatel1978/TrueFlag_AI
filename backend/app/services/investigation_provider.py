"""Provider-neutral boundary; offline simulation and a separately gated candidate adapter."""

import json
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.schemas.provider_live import LiveProviderConfig

from app.schemas.investigation_drafts import (
    ProviderConfig,
    ProviderInput,
    ProviderProposal,
    ProviderReply,
    Usage,
)


class ProviderFailure(Exception):
    pass


class ProviderTimeout(ProviderFailure):
    pass


class ProviderLimit(ProviderFailure):
    pass


class InvestigationLLMProvider(Protocol):
    def propose(
        self, packet: ProviderInput, config: "ProviderConfig | LiveProviderConfig"
    ) -> ProviderReply: ...


def strict_json(raw, limit):
    if type(raw) is not str or len(raw.encode("utf-8")) > limit:
        raise ProviderLimit("provider_response_limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite_json")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class DeterministicFakeProvider:
    """Test simulation: selects supplied references, never predicts real-world correctness."""

    def propose(self, packet, config):
        findings = []
        if packet.transactions:
            tx = packet.transactions[0]
            findings.append(
                dict(
                    claim_type="observed_fact",
                    reference_id=tx["reference_id"],
                    supporting_evidence=[tx["reference_id"]],
                )
            )
        for fact in packet.financial_facts[:2]:
            findings.append(
                dict(
                    claim_type="calculated_fact",
                    reference_id=fact["reference_id"],
                    supporting_evidence=fact["input_record_ids"],
                )
            )
        if packet.model_signal:
            findings.append(
                dict(claim_type="model_signal", reference_id=packet.model_signal["assessment_id"])
            )
        proposal = ProviderProposal(
            packet_sha256=packet.packet_sha256,
            findings=findings,
            hypotheses=[],
            questions=packet.questions,
            unresolved_questions=packet.questions,
            next_steps=["human_review"],
            abstain=packet.evidence_requires_abstention,
            uncertainty="requires_human_semantic_review",
        )
        if hasattr(packet, "regulatory_passages"):
            from app.schemas.regulatory_investigation import GroundedSimulationProposal

            proposal = GroundedSimulationProposal(
                **proposal.model_dump(),
                regulatory_binding_sha256=packet.regulatory_binding_sha256,
                regulatory_citations=[c.reference_id for c in packet.regulatory_passages],
            )
        content = proposal.model_dump_json(warnings="error")
        if len(content.encode()) > config.max_output_tokens:
            raise ProviderLimit("provider_response_limit")
        return ProviderReply(
            content=content,
            finish_reason="complete",
            provider=config.provider,
            model=config.model,
            usage=Usage(
                input_tokens=len(packet.model_dump_json().encode()),
                output_tokens=len(content.encode()),
                cost_usd=0,
                basis="simulated_utf8_byte_units_not_vendor_tokens",
            ),
        )
