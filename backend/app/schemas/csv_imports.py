"""Explicit approval and value-free import progress contracts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ImportState = Literal["pending", "running", "completed", "partially_completed", "failed"]


class ImportApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approve_valid_rows: Literal[True]
    upload_sha256: SHA
    mapping_sha256: SHA
    mapping_version: Literal["trueflag.csv-mapping.v1"]
    validator_version: Literal["trueflag.csv-validation.v1"]
    validation_version: int = Field(ge=1)
    units: Literal["baseline_source_units"]

    @field_validator("approve_valid_rows", mode="before")
    @classmethod
    def explicit_approval(cls, value):
        if value is not True:
            raise ValueError("Explicit valid-row import approval is required")
        return value


class ImportSummary(BaseModel):
    import_id: UUID
    upload_id: UUID
    validation_id: UUID
    status: ImportState
    total_rows: int
    valid_rows: int
    invalid_rows: int
    processed_rows: int
    created_rows: int
    reused_rows: int
    conflict_rows: int
    excluded_rows: int
    unprocessed_rows: int
    chunk_size: int
    attempts: int
    failure_code: str | None
    created_at: datetime
    updated_at: datetime
    source_expires_at: datetime
    upload_sha256: str
    mapping_sha256: str
    mapping_version: str
    validator_version: str
    units: str
    validation_sha256: str
    # Imported cases (visible to the reader) with an assessment of their current case version.
    assessed_cases: int = 0


class ImportRowResult(BaseModel):
    row_number: int
    status: Literal["created", "reused", "invalid", "conflict"]
    reason_code: str | None
    alert_id: UUID | None
    case_id: UUID | None
    errors: list[dict[str, str]]
    warnings: list[dict[str, str]]


class ImportRowsPage(BaseModel):
    import_id: UUID
    total: int
    offset: int
    limit: int
    items: list[ImportRowResult]
