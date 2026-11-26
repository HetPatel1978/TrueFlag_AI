"""Academic-only contracts. These are deliberately not approved regulatory citations."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.assessments import SHA256
from app.schemas.evidence_read import SnapshotIdentity
from app.schemas.provider_live import AIDraftBody, ClaudeProviderConfig
from app.schemas.references import Contract, ReferenceQuery
from app.schemas.regulatory_investigation import GroundedAIProposal, GroundedProviderInput

NOTICE = (
    "AI-assisted academic research demonstration. Regulatory sources have not completed "
    "independent compliance approval."
)


class ResearchStartInput(Contract):
    """The verified parent investigation the user is viewing when they click Generate."""

    investigation_run_id: UUID
    expected_packet_sha256: SHA256


class ResearchApproveInput(Contract):
    """Only the hash the approver was shown; the server rebuilds and compares the request."""

    request_sha256: SHA256


class ResearchCitation(Contract):
    reference_id: UUID
    source_key: Literal["ecfr-us-banks"] = "ecfr-us-banks"
    source_url: str
    publisher: str
    # Any section of the same hash-verified 31 CFR Part 1020 snapshot (per-case retrieval).
    section: str = Field(pattern=r"^1020\.[0-9]{3}$")
    locator: str
    raw_sha256: SHA256
    extracted_sha256: SHA256
    text_sha256: SHA256
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    text: str = Field(max_length=32768)
    parser_version: Literal["trueflag.reference-parser.v1"]
    historical_as_of: Literal["2026-11-02"] = "2026-11-02"
    acquisition_date: Literal["2026-11-04"] = "2026-11-04"
    applicability: Literal["historical_us_bank_research_only_not_legally_adjudicated"] = (
        "historical_us_bank_research_only_not_legally_adjudicated"
    )
    approval_status: Literal["unapproved_research"] = "unapproved_research"
    origin: Literal["official_public_research"] = "official_public_research"
    is_customer_violation_evidence: Literal[False] = False


EXCERPT_METHOD = "query_relevant_lines_v1"


class ResearchExcerptCitation(ResearchCitation):
    """A bounded excerpt of one section: ``text`` holds only the query-relevant lines sent to
    Claude. ``text_sha256`` still identifies the full hash-verified section."""

    excerpt_method: Literal["query_relevant_lines_v1"] = EXCERPT_METHOD
    excerpt_sha256: SHA256
    section_text_bytes: int = Field(strict=True, ge=1)


class ResearchBinding(Contract):
    schema_version: Literal["trueflag.academic-research-binding.v1"] = (
        "trueflag.academic-research-binding.v1"
    )
    case_id: UUID
    actor_id: UUID
    investigation_run_id: UUID
    packet_sha256: SHA256
    scope_sha256: SHA256
    query: ReferenceQuery
    passages: list[ResearchCitation] = Field(min_length=1, max_length=2)
    snapshot: SnapshotIdentity
    clock_epoch: int = Field(ge=1)
    prepared_second: int
    expires_second: int
    binding_sha256: SHA256
    notice: Literal[NOTICE] = NOTICE
    publication_approved: Literal[False] = False
    legal_correctness_verified: Literal[False] = False


RETRIEVAL_METHOD = "postgresql_english_ts_rank_cd_or_v1"


class RetrievalResult(Contract):
    reference_id: UUID
    rank: int = Field(strict=True, ge=1, le=3)
    section: str = Field(pattern=r"^1020\.[0-9]{3}$")
    title: str = Field(max_length=200)
    # Raw PostgreSQL ts_rank_cd value (6 dp text). A text-match score, not a 0-1 similarity.
    score: str = Field(pattern=r"^[0-9]+\.[0-9]{6}$")
    chunk_sha256: SHA256
    text_bytes: int = Field(strict=True, ge=0)
    # False: ranked in the top 3 but not sent because it would exceed the passage budget.
    sent: bool = Field(strict=True)


class ResearchRetrieval(Contract):
    method: Literal["postgresql_english_ts_rank_cd_or_v1"] = RETRIEVAL_METHOD
    # Case inputs that produced the query, e.g. "risk_driver:nbrPaymentsCashLike90d".
    inputs: list[str] = Field(min_length=1, max_length=20)
    terms: list[str] = Field(min_length=1, max_length=40)
    query: str = Field(min_length=1, max_length=1024)  # exact to_tsquery expression
    total_chunks: int = Field(strict=True, ge=1, le=200)
    matched_chunks: int = Field(strict=True, ge=1, le=200)
    passage_budget_bytes: int = Field(strict=True, ge=1)
    results: list[RetrievalResult] = Field(min_length=1, max_length=3)


RETRIEVAL_METHOD_V2 = "postgresql_english_ts_rank_cd_or_relative_v2"


class ResearchRetrievalV2(ResearchRetrieval):
    """Top 3 by ts_rank_cd, then results below 25% of the top score dropped (top always kept)."""

    method: Literal["postgresql_english_ts_rank_cd_or_relative_v2"] = RETRIEVAL_METHOD_V2
    min_relative_score: Literal["0.25"] = "0.25"
    strong_matches: int = Field(strict=True, ge=1, le=3)


class ResearchBindingV2(ResearchBinding):
    """Per-case retrieval. v1 bindings (fixed query, 2 sections) remain readable unchanged."""

    schema_version: Literal["trueflag.academic-research-binding.v2"] = (
        "trueflag.academic-research-binding.v2"
    )
    passages: list[ResearchCitation] = Field(min_length=1, max_length=3)
    retrieval: ResearchRetrieval


class ResearchBindingV3(ResearchBindingV2):
    """Per-case retrieval with the relative-score threshold stored in the record.
    v1/v2 bindings keep their original retrieval rule, shape and hash."""

    schema_version: Literal["trueflag.academic-research-binding.v3"] = (
        "trueflag.academic-research-binding.v3"
    )
    retrieval: ResearchRetrievalV2


class ExcerptSpan(Contract):
    """Byte range [start, end) within the section text (UTF-8)."""

    start: int = Field(strict=True, ge=0)
    end: int = Field(strict=True, gt=0)


class RetrievalResultV2(RetrievalResult):
    """Adds the excerpt actually sent: its byte ranges in the section, size and hash."""

    excerpt_sha256: SHA256
    excerpt_bytes: int = Field(strict=True, ge=1)
    excerpt_spans: list[ExcerptSpan] = Field(min_length=1, max_length=200)


RETRIEVAL_METHOD_V3 = "postgresql_english_ts_rank_cd_or_relative_excerpt_v3"


class ResearchRetrievalV3(ResearchRetrievalV2):
    """v2 ranking and threshold, then each strong match is sent as a bounded excerpt of its
    most query-relevant lines (heading always kept) so every strong match fits the request."""

    method: Literal["postgresql_english_ts_rank_cd_or_relative_excerpt_v3"] = (
        RETRIEVAL_METHOD_V3
    )
    excerpt_method: Literal["query_relevant_lines_v1"] = EXCERPT_METHOD
    excerpt_cap_bytes: Literal[4000] = 4000
    results: list[RetrievalResultV2] = Field(min_length=1, max_length=3)


class ResearchBindingV4(ResearchBindingV3):
    """Strong matches sent as bounded excerpts. v1-v3 bindings keep their rule and hash."""

    schema_version: Literal["trueflag.academic-research-binding.v4"] = (
        "trueflag.academic-research-binding.v4"
    )
    passages: list[ResearchExcerptCitation] = Field(min_length=1, max_length=3)
    retrieval: ResearchRetrievalV3


class ResearchSourceText(Contract):
    """Full text of one retrieved section, re-read from the hash-verified snapshot."""

    reference_id: UUID
    section: str = Field(pattern=r"^1020\.[0-9]{3}$")
    chunk_sha256: SHA256
    text: str = Field(max_length=32768)


def parse_binding(value):
    if isinstance(value, dict) and value.get("schema_version") == (
        "trueflag.academic-research-binding.v4"
    ):
        return ResearchBindingV4.model_validate(value)
    if isinstance(value, dict) and value.get("schema_version") == (
        "trueflag.academic-research-binding.v3"
    ):
        return ResearchBindingV3.model_validate(value)
    if isinstance(value, dict) and value.get("schema_version") == (
        "trueflag.academic-research-binding.v2"
    ):
        return ResearchBindingV2.model_validate(value)
    return ResearchBinding.model_validate(value)


class FindingCitation(Contract):
    finding_reference_id: UUID
    regulatory_citation: UUID


class ResearchProviderInput(GroundedProviderInput):
    regulatory_context: Literal["research_unapproved"] = "research_unapproved"
    regulatory_passages: list[ResearchExcerptCitation | ResearchCitation] = Field(
        min_length=1, max_length=3
    )
    research_notice: Literal[NOTICE] = NOTICE


class ResearchClaudeConfig(ClaudeProviderConfig):
    request_deadline_seconds: int = Field(default=120, strict=True, ge=1, le=120)
    # A lower cap does not shorten generation; it only risks a truncated, rejected reply.
    max_output_tokens: int = Field(default=4096, strict=True, ge=256, le=4096)
    research_scope: Literal["academic_research_v1"] = "academic_research_v1"
    research_binding_sha256: SHA256
    research_scope_sha256: SHA256
    purpose: Literal["research_validation"] = "research_validation"
    exact_input_sha256: SHA256
    # v3 adds per-finding regulatory citations; stored v2 runs keep their recorded format.
    wire_format: Literal["flat_selection_v2", "flat_selection_v3"] = "flat_selection_v2"


class ResearchAIDraftBody(AIDraftBody):
    regulatory_context: Literal["research_unapproved"] = "research_unapproved"
    regulatory_citations: list[ResearchExcerptCitation | ResearchCitation] = Field(max_length=3)
    research_notice: Literal[NOTICE] = NOTICE
    research_binding_sha256: SHA256
    publication_approved: Literal[False] = False


class ResearchAIDraftBodyV3(ResearchAIDraftBody):
    """Adds verified finding-to-source links; earlier stored bodies are never re-shaped."""

    finding_citations: list[FindingCitation] = Field(max_length=40)


class ResearchAIProposal(GroundedAIProposal):
    finding_citations: list[FindingCitation] = Field(default_factory=list, max_length=40)
