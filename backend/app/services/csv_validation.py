"""Streaming, value-free CSV preview. Never imports records or invokes a model."""

import csv
import hashlib
import io
import json
import math
import re
import time
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, insert, select

from app.models import AuditEvent, CSVValidation, CSVValidationIssue
from app.schemas.alerts import BASELINE_CONTRACT_SHA256, AlertFeatures, AlertIngestionInput
from app.schemas.csv_uploads import COLUMNS
from app.schemas.csv_validation import (
    VALIDATOR_VERSION,
    MappingInput,
    ValidationPage,
    ValidationSummary,
)
from app.services.csv_staging import (
    CSVStagingService,
    InvalidCSV,
    StagingUnavailable,
    UploadCapacity,
    UploadExpired,
    UploadLimit,
    UploadNotFound,
    _aware,
    _now,
)

NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")


class InvalidMapping(Exception):
    """Messages/values are intentionally never forwarded to the caller."""


def issue(field, code):
    return {"field": field, "code": code}


def numeric_cell(value):
    # JSON numeric grammar only. No trimming, locale/currency conversion or missing tokens.
    if len(value) > 512 or not NUMBER.fullmatch(value):
        raise ValueError
    number = json.loads(value)
    if isinstance(number, float):
        significand = value.lower().split("e", 1)[0]
        if not math.isfinite(number) or number == 0 and any(c in "123456789" for c in significand):
            raise ValueError
    return number


def validate_row(row, headers, mapping, seen):
    """Pure adapter to the unchanged Pydantic contract; never includes input in issues."""
    errors, warnings = [], []
    if len(row) != len(headers):
        return [issue("row", "column_count")], []
    cells = dict(zip(headers, row, strict=True))
    features, metadata = {}, {}
    for target in COLUMNS:
        value = cells[mapping[target]]
        if value.lstrip().startswith(("=", "+", "@")) or (
            value.lstrip().startswith("-") and target in {"state", "source_id"}
        ):
            warnings.append(issue(target, "spreadsheet_formula"))
        if target not in AlertFeatures.model_fields:
            metadata[target] = value
        elif target == "state":
            features[target] = value
        elif target == "income" and value == "":
            features[target] = None
        else:
            try:
                features[target] = numeric_cell(value)
            except (ValueError, OverflowError):
                errors.append(issue(target, "number_format"))
    if any(cells[h] for h in headers if h not in set(mapping.values())):
        warnings.append(issue("row", "unmapped_columns"))
    # Validate all independently parseable fields, including metadata, on every row.
    try:
        AlertIngestionInput.model_validate({**metadata, "features": features})
    except ValidationError as error:
        failed = {e["field"] for e in errors}
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            field = item["loc"][-1]
            if field in COLUMNS and field not in failed:
                errors.append(issue(field, "contract_value"))
                failed.add(field)
    source = metadata["source_id"]
    # Detect later occurrences without retaining source identifiers in diagnostic storage.
    fingerprint = hashlib.sha256(source.encode("utf-8")).digest()
    if fingerprint in seen:
        errors.append(issue("source_id", "duplicate_source_id"))
    seen.add(fingerprint)
    return errors, warnings


class CSVValidationService:
    def __init__(self, engine, settings):
        self.staging = CSVStagingService(engine, settings)
        self.settings = settings

    def _reader(self, stream):
        # Detach to preserve ownership of the verified binary stream in the staging service.
        text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        return text, csv.reader(text, strict=True)

    def _headers(self, reader):
        headers = next(reader, None)
        if (
            not headers
            or len(headers) > self.settings.csv_max_columns
            or len(set(h.casefold() for h in headers)) != len(headers)
            or any(
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _.-]{0,79}", h) or h != h.strip()
                for h in headers
            )
        ):
            raise InvalidCSV
        return headers

    def columns(self, actor_id, upload_id):
        try:
            with self.staging.validation_source(actor_id, upload_id) as (session, row, stream):
                text, reader = self._reader(stream)
                try:
                    headers = self._headers(reader)
                finally:
                    text.detach()
                session.add(
                    AuditEvent(
                        actor_id=actor_id,
                        action="batch.upload.columns_read",
                        resource_id=str(row.id),
                    )
                )
                return {
                    "upload_id": row.id,
                    "upload_sha256": row.sha256,
                    "columns": headers,
                    "required_columns": list(COLUMNS),
                    "exact_matches": {n: n for n in COLUMNS if n in headers},
                    "units": "baseline_source_units",
                }
        except (UnicodeError, csv.Error):
            raise InvalidCSV from None

    def _mapping(self, headers, request):
        if not isinstance(request, MappingInput):
            raise InvalidMapping
        mapping = request.mapping if request.mapping is not None else {n: n for n in COLUMNS}
        if set(mapping) != set(COLUMNS) or len(set(mapping.values())) != len(COLUMNS):
            raise InvalidMapping
        if any(h not in headers for h in mapping.values()):
            raise InvalidMapping
        return {n: mapping[n] for n in COLUMNS}

    def _summary(self, row, upload):
        return ValidationSummary(
            validation_id=row.id,
            upload_id=upload.id,
            version=row.version,
            mapping_version=row.mapping_version,
            validator_version=row.validator_version,
            csv_contract_version=upload.csv_contract_version,
            feature_contract_version=upload.feature_contract_version,
            feature_contract_sha256=row.feature_contract_sha256,
            upload_sha256=row.upload_sha256,
            mapping_sha256=row.mapping_sha256,
            mapping=row.mapping,
            units=row.units,
            total_rows=row.total_rows,
            valid_rows=row.valid_rows,
            invalid_rows=row.invalid_rows,
            warning_rows=row.warning_rows,
            created_at=_aware(row.created_at),
            expires_at=_aware(upload.expires_at),
        )

    def validate(self, actor_id, upload_id, request):
        started = time.monotonic()
        try:
            with self.staging.validation_source(actor_id, upload_id) as (session, upload, stream):
                text, reader = self._reader(stream)
                try:
                    headers = self._headers(reader)
                    mapping = self._mapping(headers, request)
                    identity = {
                        "mapping": mapping,
                        "units": request.units,
                        "mapping_version": request.mapping_version,
                        "validator_version": VALIDATOR_VERSION,
                        "upload_sha256": upload.sha256,
                        "feature_contract_sha256": BASELINE_CONTRACT_SHA256,
                        "csv_contract_version": upload.csv_contract_version,
                    }
                    digest = hashlib.sha256(
                        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    prior = session.scalar(
                        select(CSVValidation).where(
                            CSVValidation.upload_id == upload_id,
                            CSVValidation.mapping_sha256 == digest,
                        )
                    )
                    if prior:
                        session.add(
                            AuditEvent(
                                actor_id=actor_id,
                                action="batch.validation.replayed",
                                resource_id=str(prior.id),
                            )
                        )
                        return self._summary(prior, upload), False
                    count = session.scalar(
                        select(func.count())
                        .select_from(CSVValidation)
                        .where(CSVValidation.upload_id == upload_id)
                    )
                    if count >= self.settings.csv_max_validation_versions:
                        raise UploadCapacity
                    audit = AuditEvent(
                        id=uuid4(),
                        actor_id=actor_id,
                        action="batch.validation.completed",
                        resource_id=str(upload.id),
                        details={},
                    )
                    session.add(audit)
                    session.flush()
                    result = CSVValidation(
                        id=uuid4(),
                        upload_id=upload_id,
                        version=count + 1,
                        mapping_sha256=digest,
                        mapping=mapping,
                        mapping_version=request.mapping_version,
                        validator_version=VALIDATOR_VERSION,
                        units=request.units,
                        upload_sha256=upload.sha256,
                        feature_contract_sha256=BASELINE_CONTRACT_SHA256,
                        total_rows=upload.row_count,
                        valid_rows=upload.row_count,
                        invalid_rows=0,
                        warning_rows=0,
                        audit_event_id=audit.id,
                    )
                    session.add(result)
                    session.flush()
                    total, invalid, warnings, seen, batch = 0, 0, 0, set(), []
                    for total, row in enumerate(reader, start=1):
                        if (
                            total > self.settings.csv_max_rows
                            or len(row) > self.settings.csv_max_columns
                        ):
                            raise UploadLimit
                        if (
                            time.monotonic() - started
                            > self.settings.csv_validation_timeout_seconds
                        ):
                            raise StagingUnavailable
                        if any(
                            len(c.encode("utf-8")) > self.settings.csv_max_field_bytes for c in row
                        ):
                            raise UploadLimit
                        if any(
                            any(ord(c) < 32 and c not in "\r\n\t" or ord(c) == 127 for c in cell)
                            for cell in row
                        ):
                            raise InvalidCSV
                        errors, notices = validate_row(row, headers, mapping, seen)
                        invalid += bool(errors)
                        warnings += bool(notices)
                        if errors or notices:
                            batch.append(
                                {
                                    "validation_id": result.id,
                                    "row_number": total + 1,
                                    "invalid": bool(errors),
                                    "has_warnings": bool(notices),
                                    "errors": errors,
                                    "warnings": notices,
                                }
                            )
                        if len(batch) >= 100:
                            session.execute(insert(CSVValidationIssue), batch)
                            batch.clear()
                    if total != upload.row_count:
                        raise InvalidCSV
                    if batch:
                        session.execute(insert(CSVValidationIssue), batch)
                    result.valid_rows, result.invalid_rows, result.warning_rows = (
                        total - invalid,
                        invalid,
                        warnings,
                    )
                    audit.details = {
                        "validation_id": str(result.id),
                        "version": result.version,
                        "total_rows": total,
                        "valid_rows": total - invalid,
                        "invalid_rows": invalid,
                        "warning_rows": warnings,
                        "mapping_sha256": digest,
                    }
                    if _aware(upload.expires_at) <= _now(session):
                        raise UploadExpired
                    session.flush()
                    return self._summary(result, upload), True
                finally:
                    text.detach()
        except (UnicodeError, csv.Error):
            raise InvalidCSV from None

    def retrieve(
        self, actor_id, upload_id, validation_id, *, offset=None, limit=50, severity="all"
    ):
        if offset is not None and (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
            or severity not in {"all", "error", "warning"}
        ):
            raise InvalidMapping
        with self.staging.validation_source(actor_id, upload_id) as (session, upload, stream):
            row = session.scalar(
                select(CSVValidation).where(
                    CSVValidation.id == validation_id, CSVValidation.upload_id == upload_id
                )
            )
            if row is None:
                raise UploadNotFound
            if row.upload_sha256 != upload.sha256:
                raise StagingUnavailable
            session.add(
                AuditEvent(
                    actor_id=actor_id, action="batch.validation.read", resource_id=str(row.id)
                )
            )
            if offset is None:
                return self._summary(row, upload)
            filters = [CSVValidationIssue.validation_id == row.id]
            if severity == "error":
                filters.append(CSVValidationIssue.invalid.is_(True))
            elif severity == "warning":
                filters.append(CSVValidationIssue.has_warnings.is_(True))
            total = session.scalar(
                select(func.count()).select_from(CSVValidationIssue).where(*filters)
            )
            issues = session.scalars(
                select(CSVValidationIssue)
                .where(*filters)
                .order_by(CSVValidationIssue.row_number)
                .offset(offset)
                .limit(limit)
            ).all()
            return ValidationPage(
                validation_id=row.id,
                total=total,
                offset=offset,
                limit=limit,
                items=[
                    {"row_number": i.row_number, "errors": i.errors, "warnings": i.warnings}
                    for i in issues
                ],
            )
