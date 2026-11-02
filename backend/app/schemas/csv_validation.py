"""Value-free, versioned mapping and preview contracts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAPPING_VERSION = "trueflag.csv-mapping.v1"
VALIDATOR_VERSION = "trueflag.csv-validation.v1"
HeaderName = Annotated[
    str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9 _.-]*$")
]


class MappingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mapping_version: Literal["trueflag.csv-mapping.v1"] = MAPPING_VERSION
    units: Literal["baseline_source_units"]
    # None means exact case-sensitive names. Explicit maps must cover every target.
    mapping: dict[HeaderName, HeaderName] | None = Field(default=None, max_length=30)


class ValidationSummary(BaseModel):
    validation_id: UUID
    upload_id: UUID
    version: int
    mapping_version: str
    validator_version: str
    csv_contract_version: str
    feature_contract_version: str
    feature_contract_sha256: str
    upload_sha256: str
    mapping_sha256: str
    mapping: dict[str, str]
    units: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    warning_rows: int
    created_at: datetime
    expires_at: datetime


class FieldIssue(BaseModel):
    field: str
    code: str


class RowIssues(BaseModel):
    row_number: int
    errors: list[FieldIssue]
    warnings: list[FieldIssue]


class ValidationPage(BaseModel):
    validation_id: UUID
    total: int
    offset: int
    limit: int
    items: list[RowIssues]
