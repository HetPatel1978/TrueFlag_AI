"""PostgreSQL approved imports: chunk transactions, fenced leases, no ML dispatch."""

import csv
import functools
import hashlib
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.release import require_session_compatible
from app.core.release_metadata import ReleaseCompatibilityError
from app.models import (
    Assessment,
    AuditEvent,
    Case,
    CSVImport,
    CSVImportRow,
    CSVImportWorker,
    CSVValidation,
    CSVValidationIssue,
    User,
)
from app.schemas.alerts import BASELINE_CONTRACT_SHA256, AlertFeatures, AlertIngestionInput
from app.schemas.csv_imports import ImportApproval, ImportRowsPage, ImportSummary
from app.schemas.csv_validation import MAPPING_VERSION, VALIDATOR_VERSION, MappingInput
from app.services.cases import visible_cases
from app.services.csv_staging import (
    CSVStagingService,
    InvalidCSV,
    StagingUnavailable,
    UploadDenied,
    UploadExpired,
    UploadNotFound,
    _admin,
    _aware,
    _now,
    _timeouts,
)
from app.services.csv_validation import CSVValidationService, numeric_cell
from app.services.ingestion import (
    IngestionConflict,
    digest,
    ingest_alert_in_transaction,
    unique_request_race,
)

ACTIVE = ("pending", "running")
FAILURES = {
    "lease_expired",
    "database_unavailable",
    "processing_unavailable",
    "authorization_changed",
    "source_expired",
    "validation_changed",
    "chunk_timeout",
}


class ImportErrorBase(Exception):
    pass


class ImportConflict(ImportErrorBase):
    pass


class ImportUnavailable(ImportErrorBase):
    pass


class ImportCapacity(ImportErrorBase):
    pass


class ImportInvalid(ImportErrorBase):
    pass


class ImportWorkerDenied(ImportErrorBase):
    pass


class ImportLeaseLost(ImportErrorBase):
    pass


class ImportTimeout(ImportErrorBase):
    pass


def safe(method):
    @functools.wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (ImportErrorBase, UploadDenied, UploadExpired, UploadNotFound):
            raise
        except ReleaseCompatibilityError as error:
            raise ImportUnavailable(error.code) from None
        except (SQLAlchemyError, StagingUnavailable, OSError):
            raise ImportUnavailable from None
        except Exception:
            raise ImportUnavailable from None

    return call


@dataclass(frozen=True)
class ImportClaim:
    import_id: UUID
    worker_id: UUID
    lease_token: UUID


def _token_hash(token):
    if type(token) is not str or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ImportWorkerDenied
    return hashlib.sha256(token.encode()).hexdigest()


def _worker(session, token):
    require_session_compatible(session)
    row = session.scalar(
        select(CSVImportWorker)
        .where(CSVImportWorker.token_sha256 == _token_hash(token), CSVImportWorker.active.is_(True))
        .with_for_update(read=True)
    )
    if row is None:
        raise ImportWorkerDenied
    return row.id


def _leased(session, claim, worker_id):
    if (
        type(claim) is not ImportClaim
        or any(type(x) is not UUID for x in (claim.import_id, claim.worker_id, claim.lease_token))
        or worker_id != claim.worker_id
    ):
        raise ImportLeaseLost
    row = session.scalar(
        select(CSVImport)
        .where(
            CSVImport.id == claim.import_id,
            CSVImport.status == "running",
            CSVImport.worker_id == worker_id,
            CSVImport.lease_token == claim.lease_token,
            CSVImport.lease_until > _now(session),
        )
        .with_for_update()
    )
    if row is None:
        raise ImportLeaseLost
    return row


def _event(session, row, action, **details):
    session.add(
        AuditEvent(
            actor_id=row.actor_id,
            action="batch.import." + action,
            resource_id=str(row.id),
            details={"import_id": str(row.id), **details},
        )
    )


def _snapshot(row, upload):
    return {
        "mapping": row.mapping,
        "mapping_version": row.mapping_version,
        "validator_version": row.validator_version,
        "units": row.units,
        "upload_sha256": row.upload_sha256,
        "mapping_sha256": row.mapping_sha256,
        "feature_contract_sha256": row.feature_contract_sha256,
        "feature_contract_version": upload.feature_contract_version,
        "csv_contract_version": upload.csv_contract_version,
        "validation_version": row.version,
        "total_rows": row.total_rows,
        "valid_rows": row.valid_rows,
        "invalid_rows": row.invalid_rows,
        "warning_rows": row.warning_rows,
    }


def _assessed_cases(session, row, actor_id):
    """Imported cases (visible to the reader) whose latest assessment is completed and passes
    the integrity check, whatever import, batch or case version produced it. Same rule as the
    Cases list score. Read-only; counted once the import is terminal (not while polling)."""
    from app.services.assessments import AssessmentUnavailable, _read

    if row.status not in {"completed", "partially_completed"}:
        return 0
    user = session.get(User, actor_id)
    cases = session.scalars(
        select(Case.id)
        .join(CSVImportRow, CSVImportRow.case_id == Case.id)
        .where(CSVImportRow.import_id == row.id, visible_cases(user))
        .distinct()
    ).all()
    assessed = 0
    for case_id in cases:
        latest = session.scalar(
            select(Assessment)
            .where(Assessment.case_id == case_id)
            .order_by(Assessment.version.desc(), Assessment.id.desc())
            .limit(1)
        )
        if latest is None:
            continue
        try:
            content = _read(session, latest)
        except AssessmentUnavailable:
            continue  # A record failing the integrity check never counts as assessed.
        if content["score"]["status"] == "processed":
            assessed += 1
    return assessed


def _view(row, assessed_cases=0):
    snap = row.snapshot
    return ImportSummary(
        assessed_cases=assessed_cases,
        import_id=row.id,
        upload_id=row.upload_id,
        validation_id=row.validation_id,
        status=row.status,
        total_rows=row.total_rows,
        valid_rows=row.valid_rows,
        invalid_rows=row.invalid_rows,
        processed_rows=row.processed_rows,
        created_rows=row.created_rows,
        reused_rows=row.reused_rows,
        conflict_rows=row.conflict_rows,
        excluded_rows=row.excluded_rows,
        unprocessed_rows=row.total_rows - row.processed_rows,
        chunk_size=row.chunk_size,
        attempts=row.attempts,
        failure_code=row.failure_code,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        source_expires_at=_aware(row.source_expires_at),
        validation_sha256=row.validation_sha256,
        **{
            n: snap[n]
            for n in (
                "upload_sha256",
                "mapping_sha256",
                "mapping_version",
                "validator_version",
                "units",
            )
        },
    )


def canonical_record(row, headers, mapping):
    if len(row) != len(headers):
        raise ImportInvalid
    cells = dict(zip(headers, row, strict=True))
    metadata, features = {}, {}
    for name, source in mapping.items():
        value = cells[source]
        if name not in AlertFeatures.model_fields:
            metadata[name] = value
        else:
            features[name] = (
                value
                if name == "state"
                else (None if name == "income" and value == "" else numeric_cell(value))
            )
    return AlertIngestionInput.model_validate({**metadata, "features": features})


class CSVImportService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        if engine.dialect.name != "postgresql":
            raise ImportUnavailable
        self.staging = CSVStagingService(engine, settings)
        self.validation = CSVValidationService(engine, settings)

    @safe
    def register_worker(self, admin_id, name, token):
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", name):
            raise ImportInvalid
        hashed = _token_hash(token)
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _admin(session, admin_id)
            worker = CSVImportWorker(name=name, token_sha256=hashed, provisioned_by=admin_id)
            session.add(worker)
            session.flush()
            session.add(
                AuditEvent(
                    actor_id=admin_id,
                    action="batch.import.worker_registered",
                    resource_id=str(worker.id),
                    details={"permission": "csv.import.execute"},
                )
            )
            return worker.id

    @safe
    def revoke_worker(self, admin_id, worker_id):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _admin(session, admin_id)
            row = session.get(CSVImportWorker, worker_id, with_for_update=True)
            if row is None:
                raise ImportWorkerDenied
            row.active = False
            session.add(
                AuditEvent(
                    actor_id=admin_id, action="batch.import.worker_revoked", resource_id=str(row.id)
                )
            )

    def _prior(self, session, actor_id, key_sha, request_sha):
        row = session.scalar(
            select(CSVImport).where(CSVImport.actor_id == actor_id, CSVImport.key_sha256 == key_sha)
        )
        if row and row.request_sha256 != request_sha:
            raise ImportConflict
        return row

    def _validate_preview(self, session, validation, upload):
        if validation is None:
            raise UploadNotFound
        snap = _snapshot(validation, upload)
        identity = {
            n: snap[n]
            for n in (
                "mapping",
                "units",
                "mapping_version",
                "validator_version",
                "upload_sha256",
                "feature_contract_sha256",
                "csv_contract_version",
            )
        }
        if (
            validation.upload_sha256 != upload.sha256
            or validation.total_rows != upload.row_count
            or validation.mapping_version != MAPPING_VERSION
            or validation.validator_version != VALIDATOR_VERSION
            or validation.units != "baseline_source_units"
            or validation.feature_contract_sha256 != BASELINE_CONTRACT_SHA256
            or digest(identity) != validation.mapping_sha256
        ):
            raise ImportConflict
        self.validation._mapping(
            list(validation.mapping.values()),
            MappingInput(mapping=validation.mapping, units=validation.units),
        )
        for flag, expected in (
            (CSVValidationIssue.invalid, validation.invalid_rows),
            (CSVValidationIssue.has_warnings, validation.warning_rows),
        ):
            count = session.scalar(
                select(func.count())
                .select_from(CSVValidationIssue)
                .where(CSVValidationIssue.validation_id == validation.id, flag.is_(True))
            )
            if count != expected:
                raise ImportConflict
        return snap

    @safe
    def approve(self, actor_id, upload_id, validation_id, approval, key):
        if (
            type(approval) is not ImportApproval
            or type(key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", key)
        ):
            raise ImportInvalid
        request_sha = digest(
            {
                "upload_id": str(upload_id),
                "validation_id": str(validation_id),
                "approval": approval.model_dump(),
            }
        )
        key_sha = hashlib.sha256(key.encode()).hexdigest()
        # Retry receipts survive source expiry; current owner/admin authority never expires open.
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _admin(session, actor_id)
            prior = self._prior(session, actor_id, key_sha, request_sha)
            if prior:
                _event(session, prior, "approval_replayed")
                return _view(prior)
        with self.staging.validation_source(actor_id, upload_id) as (session, upload, stream):
            prior = self._prior(session, actor_id, key_sha, request_sha)
            if prior:
                return _view(prior)
            validation = session.scalar(
                select(CSVValidation)
                .where(CSVValidation.id == validation_id, CSVValidation.upload_id == upload_id)
                .with_for_update()
            )
            snap = self._validate_preview(session, validation, upload)
            if any(
                getattr(approval, n) != snap[n]
                for n in (
                    "upload_sha256",
                    "mapping_sha256",
                    "mapping_version",
                    "validator_version",
                    "validation_version",
                    "units",
                )
            ):
                raise ImportConflict
            if not validation.valid_rows:
                raise ImportInvalid
            if session.scalar(select(CSVImport.id).where(CSVImport.validation_id == validation_id)):
                raise ImportConflict
            if not session.scalar(
                text(
                    "SELECT pg_try_advisory_xact_lock(6075990620000000000 + 'csv_imports'::regclass::oid::bigint)"
                )
            ):
                raise ImportUnavailable
            active = select(func.count()).select_from(CSVImport).where(CSVImport.status.in_(ACTIVE))
            if (
                session.scalar(active) >= self.settings.csv_import_queue_capacity
                or session.scalar(active.where(CSVImport.actor_id == actor_id))
                >= self.settings.csv_import_actor_capacity
            ):
                raise ImportCapacity
            now = _now(session)
            row = CSVImport(
                id=uuid4(),
                actor_id=actor_id,
                upload_id=upload_id,
                validation_id=validation_id,
                key_sha256=key_sha,
                request_sha256=request_sha,
                validation_sha256=digest(snap),
                snapshot=snap,
                audit_event_id=uuid4(),
                source_expires_at=upload.expires_at,
                status="pending",
                total_rows=validation.total_rows,
                valid_rows=validation.valid_rows,
                invalid_rows=validation.invalid_rows,
                chunk_size=self.settings.csv_import_chunk_size,
                available_at=now,
                updated_at=now,
            )
            session.add(
                AuditEvent(
                    id=row.audit_event_id,
                    actor_id=actor_id,
                    action="batch.import.approved",
                    resource_id=str(row.id),
                    details={
                        "validation_id": str(validation_id),
                        "validation_sha256": row.validation_sha256,
                        "valid_rows": row.valid_rows,
                        "invalid_rows": row.invalid_rows,
                        "units": approval.units,
                    },
                )
            )
            session.flush()
            session.add(row)
            session.flush()
            return _view(row)

    @safe
    def get(self, actor_id, import_id, *, offset=None, limit=50, status=None):
        if offset is not None and (
            type(offset) is not int
            or not 0 <= offset <= 10000
            or type(limit) is not int
            or not 1 <= limit <= 100
            or status not in {None, "created", "reused", "invalid", "conflict"}
        ):
            raise ImportInvalid
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _admin(session, actor_id)
            row = session.scalar(
                select(CSVImport).where(CSVImport.id == import_id, CSVImport.actor_id == actor_id)
            )
            if row is None:
                raise UploadNotFound
            _event(session, row, "read")
            if offset is None:
                return _view(row, _assessed_cases(session, row, actor_id))
            conditions = [CSVImportRow.import_id == row.id]
            if status:
                conditions.append(CSVImportRow.status == status)
            total = session.scalar(
                select(func.count()).select_from(CSVImportRow).where(*conditions)
            )
            rows = session.scalars(
                select(CSVImportRow)
                .where(*conditions)
                .order_by(CSVImportRow.row_number)
                .offset(offset)
                .limit(limit)
            ).all()
            cases = {r.case_id for r in rows if r.case_id}
            user = session.get(User, actor_id)
            allowed = set(
                session.scalars(select(Case.id).where(Case.id.in_(cases), visible_cases(user)))
            )
            if cases - allowed:
                raise UploadDenied
            diagnostics = {
                r.row_number: r
                for r in session.scalars(
                    select(CSVValidationIssue).where(
                        CSVValidationIssue.validation_id == row.validation_id,
                        CSVValidationIssue.row_number.in_([r.row_number for r in rows]),
                    )
                )
            }
            return ImportRowsPage(
                import_id=row.id,
                total=total,
                offset=offset,
                limit=limit,
                items=[
                    {
                        "row_number": r.row_number,
                        "status": r.status,
                        "reason_code": r.reason_code,
                        "alert_id": r.alert_id,
                        "case_id": r.case_id,
                        "errors": diagnostics[r.row_number].errors
                        if r.row_number in diagnostics
                        else [],
                        "warnings": diagnostics[r.row_number].warnings
                        if r.row_number in diagnostics
                        else [],
                    }
                    for r in rows
                ],
            )

    @safe
    def claim(self, token):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            worker_id = _worker(session, token)
            now = _now(session)
            row = session.scalar(
                select(CSVImport)
                .where(CSVImport.status == "pending", CSVImport.available_at <= now)
                .order_by(CSVImport.available_at, CSVImport.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.status = "running"
            row.worker_id = worker_id
            row.lease_token = uuid4()
            row.lease_until = now + timedelta(seconds=self.settings.csv_import_lease_seconds)
            row.attempts += 1
            row.updated_at = now
            _event(session, row, "claimed", attempt=row.attempts, worker_id=str(worker_id))
            return ImportClaim(row.id, worker_id, row.lease_token)

    def _retry_or_fail(self, session, row, reason, retryable):
        row.failure_code = reason
        row.updated_at = _now(session)
        row.status = "pending" if retryable and row.attempts < 3 else "failed"
        row.available_at = row.updated_at + timedelta(seconds=min(60, 2**row.attempts))
        row.lease_token = row.lease_until = row.worker_id = None
        _event(
            session,
            row,
            "retry" if row.status == "pending" else "failed",
            reason=reason,
            processed_rows=row.processed_rows,
        )

    @safe
    def recover_expired(self, token):
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            _worker(session, token)
            rows = session.scalars(
                select(CSVImport)
                .where(CSVImport.status == "running", CSVImport.lease_until <= _now(session))
                .order_by(CSVImport.lease_until)
                .with_for_update(skip_locked=True)
                .limit(50)
            ).all()
            for row in rows:
                self._retry_or_fail(session, row, "lease_expired", True)
                _event(session, row, "recovered", processed_rows=row.processed_rows)
            return len(rows)

    @safe
    def fail(self, token, claim, reason, *, retryable=True):
        if reason not in FAILURES:
            raise ImportInvalid
        with Session(self.engine) as session, session.begin():
            _timeouts(session)
            row = _leased(session, claim, _worker(session, token))
            self._retry_or_fail(session, row, reason, retryable)
            session.flush()
            return _view(row)

    def _ingest(self, session, body, key, actor_id):
        for attempt in range(2):
            try:
                with session.begin_nested():
                    return ingest_alert_in_transaction(session, body, key, actor_id)
            except IntegrityError as error:
                if attempt or not unique_request_race(error):
                    raise
        raise ImportUnavailable

    @safe
    def process_chunk(self, token, claim):
        if type(claim) is not ImportClaim:
            raise ImportLeaseLost
        started = time.monotonic()
        with Session(self.engine) as lookup:
            stub = lookup.get(CSVImport, claim.import_id)
            if stub is None:
                raise ImportLeaseLost
            actor_id, upload_id = stub.actor_id, stub.upload_id
        with self.staging.validation_source(actor_id, upload_id) as (session, upload, stream):
            row = _leased(session, claim, _worker(session, token))
            validation = session.get(CSVValidation, row.validation_id)
            if (
                validation is None
                or digest(_snapshot(validation, upload)) != row.validation_sha256
                or digest(row.snapshot) != row.validation_sha256
            ):
                raise ImportConflict
            mapping = self.validation._mapping(
                list(row.snapshot["mapping"].values()),
                MappingInput(mapping=row.snapshot["mapping"], units=row.snapshot["units"]),
            )
            reader_text, reader = self.validation._reader(stream)
            try:
                headers = self.validation._headers(reader)
                if any(h not in headers for h in mapping.values()):
                    raise ImportConflict
                end = min(row.total_rows, row.processed_rows + row.chunk_size)
                counts = {
                    n: getattr(row, n)
                    for n in ("created_rows", "reused_rows", "conflict_rows", "excluded_rows")
                }
                invalid = {
                    r.row_number
                    for r in session.scalars(
                        select(CSVValidationIssue).where(
                            CSVValidationIssue.validation_id == row.validation_id,
                            CSVValidationIssue.invalid.is_(True),
                            CSVValidationIssue.row_number > row.processed_rows + 1,
                            CSVValidationIssue.row_number <= end + 1,
                        )
                    )
                }
                for number in range(1, end + 1):
                    if time.monotonic() - started > self.settings.csv_import_chunk_timeout_seconds:
                        raise ImportTimeout
                    cells = next(reader, None)
                    if cells is None:
                        raise ImportConflict
                    if number <= row.processed_rows:
                        continue
                    row_number = number + 1
                    result = CSVImportRow(import_id=row.id, row_number=row_number)
                    if row_number in invalid:
                        result.status, result.reason_code = "invalid", "preview_invalid"
                        counts["excluded_rows"] += 1
                    else:
                        body = canonical_record(cells, headers, mapping)
                        try:
                            receipt, created = self._ingest(
                                session, body, f"batch.{row.id}.{row_number}", row.actor_id
                            )
                            result.alert_id = UUID(receipt["alert_id"])
                            result.case_id = UUID(receipt["case_id"])
                            result.status = "created" if created else "reused"
                            if created:
                                counts["created_rows"] += 1
                            else:
                                counts["reused_rows"] += 1
                        except IngestionConflict:
                            result.status, result.reason_code = "conflict", "source_conflict"
                            counts["conflict_rows"] += 1
                            _event(session, row, "row_conflict", row_number=row_number)
                    session.add(result)
                if end == row.total_rows and next(reader, None) is not None:
                    raise ImportConflict
                row.processed_rows = end
                for name, value in counts.items():
                    setattr(row, name, value)
                if _now(session) >= _aware(row.lease_until):
                    raise ImportLeaseLost
                if _now(session) >= _aware(row.source_expires_at):
                    raise UploadExpired
                finished_at = _now(session)
                if time.monotonic() - started > self.settings.csv_import_chunk_timeout_seconds:
                    raise ImportTimeout
                row.status = (
                    (
                        "partially_completed"
                        if row.conflict_rows or row.invalid_rows
                        else "completed"
                    )
                    if end == row.total_rows
                    else "pending"
                )
                row.failure_code = None
                row.attempts = 0
                row.updated_at = row.available_at = finished_at
                row.lease_until = row.lease_token = row.worker_id = None
                _event(
                    session,
                    row,
                    "chunk_committed",
                    processed_rows=end,
                    created_rows=row.created_rows,
                    reused_rows=row.reused_rows,
                    conflict_rows=row.conflict_rows,
                    excluded_rows=row.excluded_rows,
                )
                if end == row.total_rows:
                    if row.excluded_rows != row.invalid_rows:
                        raise ImportConflict
                    _event(session, row, "completed", status=row.status, processed_rows=end)
                session.flush()
                return _view(row)
            except (ValueError, ValidationError, InvalidCSV, csv.Error):
                raise ImportConflict from None
            finally:
                reader_text.detach()
