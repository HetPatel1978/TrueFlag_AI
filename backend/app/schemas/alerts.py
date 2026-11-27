"""Transport representation of the unchanged structured 27-predictor baseline."""

import math
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

FEATURE_CONTRACT_VERSION = "datarobot_provisional_v1"
BASELINE_CONTRACT_SHA256 = "97ec1a8c39bb368621609ea66d1a652179dee8a1c910bc7c14c1b3ff81f72747"


def finite_number(value):
    # bool is an int subclass. Never allow it, numeric strings, rounding or imputation.
    if type(value) not in (int, float):
        raise ValueError("A JSON number is required")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("A finite JSON number is required")
    return value


Number = Annotated[int | float, BeforeValidator(finite_number)]


class AlertFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kycRiskScore: Number
    income: Number | None
    tenureMonths: Number
    creditScore: Number
    state: str = Field(min_length=1, max_length=128)
    nbrPurchases90d: Number
    avgTxnSize90d: Number
    totalSpend90d: Number
    nbrDistinctMerch90d: Number
    nbrMerchCredits90d: Number
    nbrMerchCreditsRndDollarAmt90d: Number
    totalMerchCred90d: Number
    nbrMerchCreditsWoOffsettingPurch: Number
    nbrPayments90d: Number
    totalPaymentAmt90d: Number
    overpaymentAmt90d: Number
    overpaymentInd90d: Number
    nbrCustReqRefunds90d: Number
    totalRefundsToCust90d: Number
    nbrPaymentsCashLike90d: Number
    maxRevolveLine: Number
    indOwnsHome: Number
    nbrInquiries1y: Number
    nbrCollections3y: Number
    nbrWebLogins90d: Number
    nbrPointRed90d: Number
    PEP: Number

    @field_validator("kycRiskScore")
    @classmethod
    def supported_kyc(cls, value):
        if value not in range(7):
            raise ValueError("KYC must be a whole-valued number between 0 and 6")
        return value

    @field_validator("state")
    @classmethod
    def recorded_category(cls, value):
        if not value.strip():
            raise ValueError("State must contain a recorded category")
        # Preserve case/value; the fitted encoder handles previously unknown categories.
        return value


class AlertIngestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    data_classification: Literal["synthetic"]
    feature_contract_version: Literal["datarobot_provisional_v1"]
    features: AlertFeatures


class AlertIngestionResponse(BaseModel):
    alert_id: UUID
    case_id: UUID
    case_status: Literal["open"]
    scoring_status: Literal["not_requested"]
    routing_status: Literal["not_evaluated"]
    feature_contract_version: Literal["datarobot_provisional_v1"]
