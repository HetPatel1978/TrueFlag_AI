"""Canonical downloadable transport contract generated from the retained Pydantic models."""

import csv
import io
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.alerts import (
    BASELINE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    AlertFeatures,
    AlertIngestionInput,
)

CSV_CONTRACT_VERSION = "trueflag.alert-csv.v1"
PREFIX = "/api/v1/batch-uploads"
METADATA = tuple(name for name in AlertIngestionInput.model_fields if name != "features")
COLUMNS = METADATA + tuple(AlertFeatures.model_fields)


def csv_template():
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerow(COLUMNS)
    return output.getvalue().encode("utf-8")


def csv_contract():
    features = AlertFeatures.model_json_schema()["properties"]
    envelope = AlertIngestionInput.model_json_schema()["properties"]
    return {
        "csv_contract_version": CSV_CONTRACT_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": BASELINE_CONTRACT_SHA256,
        "encoding": "UTF-8; optional initial BOM",
        "delimiter": ",",
        "quote": '"',
        "template_url": PREFIX + "/template",
        "metadata": [{"name": n, "definition": envelope[n]} for n in METADATA],
        "predictors": [
            {"name": n, "required": True, "definition": features[n]}
            for n in AlertFeatures.model_fields
        ],
        "missing_values": {"income": [""]},
        "notes": [
            "Only an empty income cell maps to JSON null; numeric zero stays zero.",
            "No other missing-value tokens, numeric coercion, imputation or state normalization.",
            "KYC must be a whole-valued finite number from 0 through 6.",
            "Staging checks syntax and limits only; row values and column mappings are not validated yet.",
        ],
    }


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: UUID
    status: Literal["staged", "expired"]
    size_bytes: int
    row_count: int
    column_count: int
    sha256: str
    created_at: datetime
    expires_at: datetime
    csv_contract_version: Literal["trueflag.alert-csv.v1"]
    feature_contract_version: Literal["datarobot_provisional_v1"]
    template_url: str
    contract_url: str
