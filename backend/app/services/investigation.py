"""Week 3 contract only; no configured provider and no simulated investigation endpoint."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class EvidencePassage:
    evidence_id: UUID
    source_sha256: str
    text: str


@dataclass(frozen=True)
class InvestigationDraft:
    summary: str
    cited_evidence_ids: tuple[UUID, ...]
    limitations: tuple[str, ...]


class InvestigationProvider(Protocol):
    async def draft(
        self, case_id: UUID, evidence: tuple[EvidencePassage, ...]
    ) -> InvestigationDraft: ...
