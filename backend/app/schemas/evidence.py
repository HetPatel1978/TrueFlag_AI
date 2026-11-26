"""Internal synthetic evidence contract. No public upload/retrieval interface."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

GENERATOR_VERSION = "trueflag.synthetic-evidence.v1"
CONFIG_VERSION = "trueflag.evidence-config.v1"
DICTIONARY_SHA = "6d262b3b8cce169fd3898019d46bb0dc542a3054f51ff3f2c80d5cf3b14de442"
PROFILES = (
    "g1_demo_priority",
    "g1_ordinary",
    "g1_related",
    "g1_concentration",
    "g1_flow_change",
    "g1_high_kyc",
    "g1_partial_customer",
    "normal",
    "burst",
    "partial",
    "unavailable",
    "missing_income",
    "zero_income",
    "corrections",
    "out_of_order",
    "multi_currency",
    "timezone_unknown",
    "timezone_offsets",
    "inconsistent_kyc",
    "incomplete_features",
    "decimal_precision",
)


def money(value):
    if type(value) not in (Decimal, str) or (
        isinstance(value, str) and not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?", value)
    ):
        raise ValueError("Exact non-negative decimal amount required")
    value = Decimal(value)
    if (
        not value.is_finite()
        or value < 0
        or value >= Decimal("10000000000000000")
        or value.as_tuple().exponent < -8
    ):
        raise ValueError("Exact finite amount required")
    return value


Money = Annotated[Decimal, BeforeValidator(money), Field(max_digits=24, decimal_places=8)]
Currency = Literal["USD", "CAD", "EUR", "GBP"]
Key = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CustomerObservation(Frozen):
    kind: Literal["customer"] = "customer"
    key: Key
    subject_key: Key
    alias: str = Field(pattern=r"^SYN-CUSTOMER-[0-9a-f]{8}$")
    observed_at: AwareDatetime
    annual_income: Money | None
    currency: Currency
    kyc_score: int = Field(ge=0, le=6)


class AccountObservation(Frozen):
    kind: Literal["account"] = "account"
    key: Key
    alias: str = Field(pattern=r"^SYN-ACCOUNT-[0-9a-f]{8}$")
    currency: Currency
    opened_at: AwareDatetime


class RelationshipObservation(Frozen):
    kind: Literal["relationship"] = "relationship"
    key: Key
    customer_key: Key
    account_key: Key
    relation: Literal["declared_holder"] = "declared_holder"
    observed_at: AwareDatetime


class TransactionObservation(Frozen):
    kind: Literal["transaction"] = "transaction"
    key: Key
    account_key: Key
    counterparty_key: Key | None
    amount: Money
    currency: Currency
    event_at: AwareDatetime | None
    original_time: str = Field(min_length=1, max_length=64)
    event_kind: Literal[
        "purchase", "payment", "transfer", "merchant_credit", "customer_refund", "reversal"
    ]
    direction: Literal["debit", "credit"]
    channel: Literal["card", "cashlike", "internal"]
    reverses_key: Key | None = None

    @model_validator(mode="after")
    def event_consistency(self):
        if (self.event_kind == "reversal") != (self.reverses_key is not None):
            raise ValueError("Explicit reversal identity required")
        if self.key == self.reverses_key:
            raise ValueError("Self reversal forbidden")
        if self.event_at is not None:
            try:
                original = datetime.fromisoformat(self.original_time)
            except ValueError:
                raise ValueError("Original offset timestamp required") from None
            if original.tzinfo is None or original != self.event_at:
                raise ValueError("Timestamp mismatch")
        return self


Observation = Annotated[
    CustomerObservation | AccountObservation | RelationshipObservation | TransactionObservation,
    Field(discriminator="kind"),
]


class SyntheticBundle(Frozen):
    generator_version: Literal["trueflag.synthetic-evidence.v1"] = GENERATOR_VERSION
    config_version: Literal["trueflag.evidence-config.v1"] = CONFIG_VERSION
    dictionary_sha256: Literal[
        "6d262b3b8cce169fd3898019d46bb0dc542a3054f51ff3f2c80d5cf3b14de442"
    ] = DICTIONARY_SHA
    data_classification: Literal["synthetic"] = "synthetic"
    origin_kind: Literal["generated_synthetic"] = "generated_synthetic"
    scenario_id: UUID
    seed: int = Field(ge=0, le=2**31 - 1)
    profile: str
    source_revision: int = Field(ge=1, le=100)
    as_of: AwareDatetime
    window_start: AwareDatetime
    coverage: Literal["complete_declared_window", "partial", "unavailable"]
    records: tuple[Observation, ...] = Field(max_length=200)
    declarations: dict[str, Any]

    @model_validator(mode="after")
    def bounded_configuration(self):
        if self.profile not in PROFILES or self.window_start >= self.as_of:
            raise ValueError("Unsupported synthetic configuration")
        if self.coverage == "unavailable" and any(r.kind == "transaction" for r in self.records):
            raise ValueError("Unavailable feed cannot contain observed transactions")
        return self
