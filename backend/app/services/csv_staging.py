"""Private bounded CSV staging. No mapping, row-value validation, import or ML dispatch."""

import csv
import hashlib
import io
import logging
import os
import re
import stat
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.models import AuditEvent, CSVUpload, User
from app.schemas.alerts import FEATURE_CONTRACT_VERSION
from app.schemas.csv_uploads import CSV_CONTRACT_VERSION, PREFIX, UploadMetadata
from app.services.upload_sessions import WorkspaceConflict, WorkspaceNotFound, bind_upload


class StagingError(Exception):
    pass


class InvalidCSV(StagingError):
    pass


class UploadLimit(StagingError):
    pass


class UploadConflict(StagingError):
    pass


class UploadNotFound(StagingError):
    pass


class UploadDenied(StagingError):
    pass


class UploadExpired(StagingError):
    pass


class UploadCapacity(StagingError):
    pass


class StagingUnavailable(StagingError):
    pass


def _admin(session, actor_id):
    # Serialize publication/quota per actor and fence simultaneous role revocation.
    if (
        session.scalar(
            select(User.id)
            .where(User.id == actor_id, User.active.is_(True), User.role == "admin")
            .with_for_update()
        )
        is None
    ):
        raise UploadDenied


def _now(session):
    return (
        session.scalar(select(func.clock_timestamp()))
        if session.bind.dialect.name == "postgresql"
        else datetime.now(timezone.utc)
    )


def _timeouts(session):
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        session.execute(text("SET LOCAL idle_in_transaction_session_timeout = '15s'"))


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _metadata(row):
    return UploadMetadata(
        upload_id=row.id,
        status=row.status,
        size_bytes=row.size_bytes,
        row_count=row.row_count,
        column_count=row.column_count,
        sha256=row.sha256,
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        csv_contract_version=row.csv_contract_version,
        feature_contract_version=row.feature_contract_version,
        template_url=PREFIX + "/template",
        contract_url=PREFIX + "/contract",
    )


def _secure_directory(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise StagingUnavailable
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise StagingUnavailable
    if os.name == "nt":
        # Native Windows chmod cannot restrict inherited ACLs. Restrict this dedicated directory.
        import ctypes
        from ctypes import wintypes

        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        sid = next(csv.reader(io.StringIO(result.stdout)))[1]
        if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
            raise StagingUnavailable
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
        present, defaulted = wintypes.BOOL(), wintypes.BOOL()
        convert = api.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD),
        ]
        convert.restype = wintypes.BOOL
        get_dacl = api.GetSecurityDescriptorDacl
        get_dacl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        get_dacl.restype = wintypes.BOOL
        set_dacl = api.SetNamedSecurityInfoW
        set_dacl.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        set_dacl.restype = wintypes.DWORD
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not convert(
            f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if (
                not get_dacl(
                    descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
                )
                or not present.value
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            # DACL only, protected from inheritance. Do not request SACL/SeSecurityPrivilege.
            error = set_dacl(
                ctypes.create_unicode_buffer(str(path)), 1, 0x80000004, None, None, dacl, None
            )
            if error:
                raise ctypes.WinError(error)
        finally:
            kernel.LocalFree(descriptor)
    else:
        os.chmod(path, 0o700)
        if path.stat().st_uid != os.geteuid():
            raise StagingUnavailable


class IncomingCSV:
    """One private uncommitted spool; close always removes unpromoted files."""

    def __init__(self, service):
        self.service = service
        self.id = uuid4()
        self.path = service.root / (self.id.hex + ".part")
        self.size = 0
        self.digest = hashlib.sha256()
        self.promoted = False
        descriptor = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        self.file = os.fdopen(descriptor, "wb")

    def append(self, chunk):
        if self.size + len(chunk) > self.service.settings.csv_max_bytes:
            raise UploadLimit
        self.file.write(chunk)
        self.digest.update(chunk)
        self.size += len(chunk)

    def inspect(self):
        if not self.size:
            raise InvalidCSV
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        rows, any_data = 0, False
        try:
            # Strict UTF-8, optional initial BOM. Do not change csv's process-global field limit.
            with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                headers = next(reader, None)
                if not headers:
                    raise InvalidCSV
                if len(headers) > self.service.settings.csv_max_columns:
                    raise UploadLimit
                if any(
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _.-]{0,79}", h) or h != h.strip()
                    for h in headers
                ) or len({h.casefold() for h in headers}) != len(headers):
                    raise InvalidCSV
                for row in reader:
                    rows += 1
                    any_data |= bool(row)
                    if (
                        rows > self.service.settings.csv_max_rows
                        or len(row) > self.service.settings.csv_max_columns
                    ):
                        raise UploadLimit
                    for cell in row:
                        if len(cell.encode("utf-8")) > self.service.settings.csv_max_field_bytes:
                            raise UploadLimit
                        if any(ord(c) < 32 and c not in "\r\n\t" or ord(c) == 127 for c in cell):
                            raise InvalidCSV
                if not rows or not any_data:
                    raise InvalidCSV
                return headers, rows
        except (UnicodeError, csv.Error):
            raise InvalidCSV from None

    def promote(self):
        destination = self.service.root / (self.id.hex + ".csv")
        if destination.exists() or destination.is_symlink():
            raise StagingUnavailable
        os.replace(self.path, destination)
        self.promoted = True
        # Ensure the rename is durable on Linux, including the directory entry.
        if os.name != "nt":
            descriptor = os.open(self.service.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def close(self):
        self.file.close()
        if not self.promoted:
            self.path.unlink(missing_ok=True)


class CSVStagingService:
    def __init__(self, engine, settings):
        self.engine = engine
        self.settings = settings
        self._orphan_scan = None
        self.root = Path(settings.csv_staging_root).absolute()
        # Config is operator-owned, never a request path; refuse public/build/source locations.
        if (
            not Path(settings.csv_staging_root).is_absolute()
            or self.root == Path(self.root.anchor)
            or any(
                p.lower() in {"public", "static", "dist", "node_modules", ".git", "assets"}
                for p in self.root.parts
            )
        ):
            raise StagingUnavailable
        if (
            PROJECT_ROOT != Path(PROJECT_ROOT.anchor)
            and self.root.is_relative_to(PROJECT_ROOT)
            and not self.root.is_relative_to(PROJECT_ROOT / "runtime")
        ):
            raise StagingUnavailable
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise StagingUnavailable

    def begin(self):
        try:
            _secure_directory(self.root)
            return IncomingCSV(self)
        except (OSError, subprocess.SubprocessError):
            raise StagingUnavailable from None

    def _path(self, row):
        if row.storage_key != row.id.hex + ".csv":
            raise StagingUnavailable
        path = self.root / row.storage_key
        if path.is_symlink():
            raise StagingUnavailable
        return path

    def _expire(self, session, row):
        self._path(row).unlink(missing_ok=True)
        if row.status != "expired":
            row.status = "expired"
            session.add(
                AuditEvent(
                    action="batch.upload.expired",
                    resource_id=str(row.id),
                    details={"upload_id": str(row.id)},
                )
            )

    def publish(self, actor_id, key, incoming, upload_session_id=None):
        if (
            type(actor_id) is not UUID
            or type(key) is not str
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", key)
        ):
            incoming.close()
            raise InvalidCSV
        commit_started = False
        created, expired = False, False
        try:
            with Session(self.engine) as session:
                with session.begin():
                    _timeouts(session)
                    _admin(session, actor_id)
                    now = _now(session)
                    key_hash = hashlib.sha256(key.encode("ascii")).hexdigest()
                    prior = session.scalar(
                        select(CSVUpload).where(
                            CSVUpload.actor_id == actor_id, CSVUpload.key_sha256 == key_hash
                        )
                    )
                    if prior:
                        try:
                            bind_upload(session, actor_id, prior, upload_session_id)
                        except (WorkspaceConflict, WorkspaceNotFound):
                            raise UploadConflict from None
                        if (
                            prior.sha256 != incoming.digest.hexdigest()
                            or prior.size_bytes != incoming.size
                            or prior.csv_contract_version != CSV_CONTRACT_VERSION
                        ):
                            raise UploadConflict
                        if prior.status == "expired" or _aware(prior.expires_at) <= now:
                            self._expire(session, prior)
                            expired = True
                        result = _metadata(prior)
                    else:
                        headers, rows = incoming.inspect()
                        active = session.scalar(
                            select(func.count())
                            .select_from(CSVUpload)
                            .where(
                                CSVUpload.actor_id == actor_id,
                                CSVUpload.status == "staged",
                                CSVUpload.expires_at > now,
                            )
                        )
                        if active >= self.settings.csv_max_active_uploads:
                            raise UploadCapacity
                        audit = AuditEvent(
                            id=uuid4(),
                            actor_id=actor_id,
                            action="batch.upload.staged",
                            resource_id=str(incoming.id),
                            details={
                                "upload_id": str(incoming.id),
                                "size_bytes": incoming.size,
                                "rows": rows,
                                "columns": len(headers),
                                "csv_contract_version": CSV_CONTRACT_VERSION,
                            },
                        )
                        session.add(audit)
                        session.flush()
                        row = CSVUpload(
                            id=incoming.id,
                            created_at=now,
                            actor_id=actor_id,
                            status="staged",
                            size_bytes=incoming.size,
                            row_count=rows,
                            column_count=len(headers),
                            sha256=incoming.digest.hexdigest(),
                            key_sha256=key_hash,
                            storage_key=incoming.id.hex + ".csv",
                            csv_contract_version=CSV_CONTRACT_VERSION,
                            feature_contract_version=FEATURE_CONTRACT_VERSION,
                            expires_at=now + timedelta(seconds=self.settings.csv_retention_seconds),
                            audit_event_id=audit.id,
                        )
                        session.add(row)
                        session.flush()
                        try:
                            bind_upload(session, actor_id, row, upload_session_id)
                        except (WorkspaceConflict, WorkspaceNotFound):
                            raise UploadConflict from None
                        incoming.promote()
                        result, created = _metadata(row), True
                    session.flush()
                    # Unknown COMMIT outcome: retain promoted bytes for retry/reconciliation.
                    commit_started = True
                if expired:
                    raise UploadExpired
            return result, created
        except BaseException as error:
            if incoming.promoted and not commit_started:
                (self.root / (incoming.id.hex + ".csv")).unlink(missing_ok=True)
            if isinstance(error, (SQLAlchemyError, OSError)):
                raise StagingUnavailable from None
            raise
        finally:
            incoming.close()

    def metadata(self, actor_id, upload_id):
        try:
            with Session(self.engine) as session, session.begin():
                _timeouts(session)
                _admin(session, actor_id)
                row = session.scalar(
                    select(CSVUpload)
                    .where(CSVUpload.id == upload_id, CSVUpload.actor_id == actor_id)
                    .with_for_update()
                )
                if row is None:
                    raise UploadNotFound
                if row.status == "expired" or _aware(row.expires_at) <= _now(session):
                    self._expire(session, row)
                session.add(
                    AuditEvent(
                        actor_id=actor_id,
                        action="batch.upload.metadata_read",
                        resource_id=str(row.id),
                    )
                )
                return _metadata(row)
        except (SQLAlchemyError, OSError):
            raise StagingUnavailable from None

    @contextmanager
    def open_for_validation(self, actor_id, upload_id):
        """Trusted consumer; preserve the original stream-only service interface."""
        with self.validation_source(actor_id, upload_id) as (_, _, stream):
            yield stream

    @contextmanager
    def validation_source(self, actor_id, upload_id):
        """Share the authorization transaction with the bounded validation writer."""
        try:
            with Session(self.engine) as session, session.begin():
                _timeouts(session)
                _admin(session, actor_id)
                row = session.scalar(
                    select(CSVUpload)
                    .where(CSVUpload.id == upload_id, CSVUpload.actor_id == actor_id)
                    .with_for_update(read=True)
                )
                if row is None:
                    raise UploadNotFound
                if row.status != "staged" or _aware(row.expires_at) <= _now(session):
                    raise UploadExpired
                descriptor = os.open(
                    self._path(row),
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                )
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise StagingUnavailable
                    digest, size = hashlib.sha256(), 0
                    while chunk := stream.read(65536):
                        size += len(chunk)
                        if size > row.size_bytes or size > self.settings.csv_max_bytes:
                            raise StagingUnavailable
                        digest.update(chunk)
                    if size != row.size_bytes or digest.hexdigest() != row.sha256:
                        raise StagingUnavailable
                    stream.seek(0)
                    yield session, row, stream
        except (SQLAlchemyError, OSError):
            raise StagingUnavailable from None

    def cleanup(self, limit=100):
        """Bounded expiry/orphan reconciliation; never a public or case-mutating operation."""
        from app.core.release import require_compatible, require_session_compatible
        from app.core.release_metadata import ReleaseCompatibilityError

        try:
            require_compatible(self.engine)
        except ReleaseCompatibilityError:
            raise StagingUnavailable from None
        if not self.root.exists():
            return 0
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise StagingUnavailable
        removed = 0
        with Session(self.engine) as session, session.begin():
            try:
                require_session_compatible(session)
            except ReleaseCompatibilityError:
                raise StagingUnavailable from None
            _timeouts(session)
            now = _now(session)
            rows = session.scalars(
                select(CSVUpload)
                .where(CSVUpload.status == "staged", CSVUpload.expires_at <= now)
                .order_by(CSVUpload.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                self._expire(session, row)
                removed += 1
            # Only generated keys, older than bounded requests/transactions, and unreferenced in DB.
            if self._orphan_scan is None:
                self._orphan_scan = os.scandir(self.root)
            for _ in range(limit):
                try:
                    path = Path(next(self._orphan_scan).path)
                except StopIteration:
                    self._orphan_scan.close()
                    self._orphan_scan = None
                    break
                match = re.fullmatch(r"([a-f0-9]{32})\.(part|csv)", path.name)
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if (
                    not match
                    or not stat.S_ISREG(info.st_mode)
                    or info.st_mtime > now.timestamp() - 3600
                ):
                    continue
                if (
                    match[2] == "part"
                    or session.scalar(
                        select(CSVUpload.id).where(CSVUpload.id == UUID(hex=match[1]))
                    )
                    is None
                ):
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed


class CSVRetention:
    def __init__(self, service, interval):
        self.service, self.interval = service, interval
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        def run():
            while not self.stop.wait(self.interval):
                try:
                    self.service.cleanup()
                except Exception:
                    logging.getLogger("trueflag.security").warning("csv.cleanup.unavailable")

        self.thread = threading.Thread(target=run, daemon=True, name="csv-retention")
        self.thread.start()
        return self

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
        if (
            not self.thread or not self.thread.is_alive()
        ) and self.service._orphan_scan is not None:
            self.service._orphan_scan.close()
            self.service._orphan_scan = None
