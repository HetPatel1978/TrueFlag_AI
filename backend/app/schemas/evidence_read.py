"""Bounded evidence projections. Decimal JSON values are strings; no arbitrary tools/SQL."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.assessments import SHA256, AssessmentDetail
from app.schemas.evidence import Currency, Money

RETRIEVAL_VERSION = "trueflag.evidence-read.v1"
CALCULATION_VERSION = "trueflag.transaction-analytics.v1"
Token = Annotated[str, Field(strict=True, min_length=32, max_length=4096)]
Kind = Literal["customer", "account", "relationship", "transaction"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class ReadRequest(Contract):
    snapshot: Token


class ContextQuery(Contract):
    assessment_id: UUID | None = None


class Window(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @field_validator("start", "end", mode="before")
    @classmethod
    def explicit_offset(cls, value):
        # Epoch numbers/numeric strings would silently invent a unit and timezone.
        if type(value) is str:
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("Explicit offset timestamp required") from None
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("Explicit offset timestamp required")
        return value

    @model_validator(mode="after")
    def bounded_window(self):
        if not 0 < (self.end - self.start).total_seconds() <= 366 * 86400:
            raise ValueError("Window must be positive and at most 366 days")
        return self


class TransactionRequest(ReadRequest):
    account_handle: UUID | None = None
    window: Window | None = None
    currency: Currency | None = None
    direction: Literal["credit", "debit"] | None = None
    status: Literal["not_recorded"] | None = None
    event_kind: (
        Literal["purchase", "payment", "transfer", "merchant_credit", "customer_refund", "reversal"]
        | None
    ) = None
    limit: int = Field(default=25, strict=True, ge=1, le=50)
    cursor: Token | None = None


class CustomerRequest(ReadRequest):
    stale_after_days: int | None = Field(default=None, strict=True, ge=1, le=3650)
    limit: int = Field(default=10, strict=True, ge=1, le=20)
    cursor: Token | None = None


class RelatedRequest(ReadRequest):
    entity_handle: UUID | None = None
    limit: int = Field(default=10, strict=True, ge=1, le=20)
    cursor: Token | None = None


Calculation = Literal[
    "count_totals", "incoming_outgoing", "velocity", "concentration", "patterns", "kyc_comparison"
]


class AnalyticsRequest(ReadRequest):
    calculation: Calculation
    window: Window
    currency: Currency
    account_handle: UUID | None = None
    direction: Literal["credit", "debit"] | None = None
    treatment: Literal["gross_observations", "exclude_verified_reversals"] = "gross_observations"
    bucket_seconds: Literal[3600, 86400] = 86400
    large_amount: Money | None = None
    repeated_minimum: int = Field(default=2, strict=True, ge=2, le=20)

    @model_validator(mode="after")
    def calculation_arguments(self):
        if self.calculation == "patterns" and self.large_amount is None:
            raise ValueError("Explicit large amount criterion is required")
        if self.calculation == "velocity" and (
            (self.window.end - self.window.start).total_seconds() / self.bucket_seconds > 128
            or isinstance(self.bucket_seconds, bool)
        ):
            raise ValueError("Velocity is bounded to 128 buckets")
        return self


class SnapshotIdentity(Contract):
    id: UUID
    sha256: SHA256
    case_id: UUID
    case_version: int
    evidence_revision: int
    access_revision: int
    retrieval_version: Literal["trueflag.evidence-read.v1"] = RETRIEVAL_VERSION
    selection: Literal["latest_authorized_linked_release_per_source"] = (
        "latest_authorized_linked_release_per_source"
    )


class SourceReference(Contract):
    source_id: UUID
    source_version_id: UUID
    version: int
    sha256: SHA256
    generator_version: str = Field(max_length=80)
    coverage: Literal["complete_declared_window", "partial", "unavailable"]
    window: Window
    membership_complete: bool
    case_input_reconciliation: Literal[
        "matches_declared_inputs", "differs_from_immutable_case_input"
    ]
    synthetic: Literal[True] = True


class EvidenceReference(Contract):
    record_version_id: UUID
    identity_id: UUID
    source_version_id: UUID
    kind: Kind
    version: int
    sha256: SHA256


class Coverage(Contract):
    status: Literal["complete_declared_window", "partial", "unavailable"]
    requested: Window | None
    sampling: Literal["not_recorded"] = "not_recorded"
    unknown_time_excluded: int = Field(ge=0)
    outside_window_excluded: int = Field(default=0, ge=0)
    filter_excluded: int = Field(default=0, ge=0)
    historical_versions_excluded: int = Field(default=0, ge=0)
    limitations: list[str] = Field(max_length=20)


class CaseContext(Contract):
    case_id: UUID
    state: str = Field(max_length=30)
    disposition: str | None = Field(max_length=30)
    snapshot_token: Token
    selected_assessment_id: UUID | None
    model_signal: AssessmentDetail | None
    available_categories: list[Kind] = Field(max_length=4)
    missing_categories: list[Kind] = Field(max_length=4)
    account_handles: list[UUID] = Field(max_length=200)


class TransactionItem(Contract):
    reference: EvidenceReference
    account_handle: UUID | None
    counterparty_handle: UUID | None
    amount: Decimal
    currency: Currency
    event_at: datetime | None
    original_time: str = Field(max_length=64)
    event_kind: str = Field(max_length=32)
    direction: Literal["credit", "debit"]
    channel: str = Field(max_length=16)
    settlement_status: Literal["not_recorded"] = "not_recorded"
    reverses_handle: UUID | None


class TransactionPage(Contract):
    items: list[TransactionItem] = Field(max_length=50)
    total: int = Field(ge=0, le=200)
    next_cursor: Token | None


class CustomerItem(Contract):
    reference: EvidenceReference
    customer_handle: UUID
    alias: str = Field(max_length=32)
    observed_at: datetime
    annual_income: Decimal | None
    currency: Currency
    declared_kyc_score: int
    age_days_at_source_as_of: int
    stale: bool | None
    contradictory_observations: bool
    expected_activity: None = None
    expected_activity_status: Literal["not_recorded"] = "not_recorded"


class CustomerPage(Contract):
    items: list[CustomerItem] = Field(max_length=20)
    total: int = Field(ge=0, le=200)
    next_cursor: Token | None


class RelatedItem(Contract):
    reference: EvidenceReference
    kind: Literal["account", "relationship"]
    account_handle: UUID
    customer_handle: UUID | None
    alias: str | None = Field(max_length=32)
    currency: Currency | None
    relation: Literal["declared_holder"] | None
    observed_at: datetime | None
    opened_at: datetime | None = None


class RelatedPage(Contract):
    items: list[RelatedItem] = Field(max_length=20)
    total: int = Field(ge=0, le=200)
    next_cursor: Token | None


class ModelSignal(Contract):
    assessment: AssessmentDetail | None
    interpretation: Literal["model_signal_not_observed_transaction_or_proof_of_crime"] = (
        "model_signal_not_observed_transaction_or_proof_of_crime"
    )


class VelocityBucket(Contract):
    window: Window
    observed_count: int
    observed_total: Decimal | None


class Concentration(Contract):
    counterparty_handle: UUID
    observed_count: int
    observed_total: Decimal
    share_of_observed_amount: Decimal | None


class RepeatedAmount(Contract):
    amount: Decimal
    direction: Literal["credit", "debit"]
    counterparty_handle: UUID | None
    count: int


class AnalyticsResult(Contract):
    calculation: Calculation
    calculation_version: Literal["trueflag.transaction-analytics.v1"] = CALCULATION_VERSION
    status: Literal["observed_only", "complete_declared_window", "insufficient_evidence"]
    currency: Currency
    unit: Literal["currency_major_units"] = "currency_major_units"
    window: Window
    treatment: Literal["gross_observations", "exclude_verified_reversals"]
    observed_count: int
    observed_total: Decimal | None
    incoming_count: int
    outgoing_count: int
    incoming_total: Decimal | None
    outgoing_total: Decimal | None
    reversal_observations: int
    verified_reversal_pairs_excluded: int
    unmatched_reversals: int
    buckets: list[VelocityBucket] = Field(default_factory=list, max_length=128)
    concentration: list[Concentration] = Field(default_factory=list, max_length=10)
    unknown_counterparty_count: int = 0
    concentration_truncated: bool = False
    large_amount_criterion: Decimal | None = None
    large_observed_count: int | None = None
    repeated_minimum: int | None = None
    repeated_amounts: list[RepeatedAmount] = Field(default_factory=list, max_length=10)
    repeated_groups_truncated: bool = False
    expected_activity_comparison: Literal[
        "not_requested", "insufficient_comparable_declared_expectations"
    ] = "not_requested"


T = TypeVar("T")


class QueryParameters(Contract):
    assessment_id: UUID | None = None
    account_handle: UUID | None = None
    entity_handle: UUID | None = None
    window: Window | None = None
    currency: Currency | None = None
    direction: Literal["credit", "debit"] | None = None
    status: Literal["not_recorded"] | None = None
    event_kind: str | None = Field(default=None, max_length=32)
    limit: int | None = Field(default=None, ge=1, le=50)
    stale_after_days: int | None = Field(default=None, ge=1, le=3650)
    calculation: Calculation | None = None
    treatment: Literal["gross_observations", "exclude_verified_reversals"] | None = None
    bucket_seconds: Literal[3600, 86400] | None = None
    large_amount: Decimal | None = None
    repeated_minimum: int | None = Field(default=None, ge=2, le=20)


class EvidenceResponse(Contract, Generic[T]):
    reference_id: UUID
    reference_sha256: SHA256
    classification: Literal["source_observations", "derived_fact", "model_signal", "case_context"]
    snapshot: SnapshotIdentity
    sources: list[SourceReference] = Field(max_length=10)
    evidence: list[EvidenceReference] = Field(max_length=200)
    coverage: Coverage
    parameters: QueryParameters
    data: T
