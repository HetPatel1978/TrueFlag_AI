"""Upload provenance and resumable user workspaces; no model or case mutations."""

import hashlib
from uuid import uuid4

from sqlalchemy import func, insert, literal, select, text
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    BatchAssessment,
    Case,
    CSVImport,
    CSVImportRow,
    CSVUpload,
    CSVValidation,
    UploadSession,
    UploadSessionItem,
    UploadWorkspace,
    User,
)
from app.services.cases import visible_cases


class WorkspaceNotFound(Exception):
    pass


class WorkspaceDenied(Exception):
    pass


class WorkspaceConflict(Exception):
    pass


def event(session, actor, action, resource, **details):
    session.add(
        AuditEvent(
            actor_id=actor,
            action="upload.session." + action,
            resource_id=str(resource),
            details=details,
        )
    )


def locked_actor(session, actor_id, *, admin=False):
    user = session.scalar(
        select(User)
        .where(User.id == actor_id, User.active.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.role not in (
        ["admin"] if admin else ["admin", "supervisor", "analyst"]
    ):
        raise WorkspaceDenied
    return user


def case_membership(session_id):
    return (
        select(CSVImportRow.case_id)
        .join(CSVImport, CSVImport.id == CSVImportRow.import_id)
        .join(UploadSessionItem, UploadSessionItem.upload_id == CSVImport.upload_id)
        .where(
            UploadSessionItem.session_id == session_id,
            CSVImportRow.status.in_(["created", "reused"]),
        )
    )


def visible_sessions(user):
    if user.role == "admin":
        return UploadSession.actor_id == user.id
    return (
        select(Case.id)
        .join(CSVImportRow, CSVImportRow.case_id == Case.id)
        .join(CSVImport, CSVImport.id == CSVImportRow.import_id)
        .join(UploadSessionItem, UploadSessionItem.upload_id == CSVImport.upload_id)
        .where(
            UploadSessionItem.session_id == UploadSession.id,
            CSVImportRow.status.in_(["created", "reused"]),
            visible_cases(user),
        )
        .correlate(UploadSession)
        .exists()
    )


def require_visible(session, user, session_id):
    row = session.scalar(
        select(UploadSession).where(UploadSession.id == session_id, visible_sessions(user))
    )
    if row is None:
        raise WorkspaceNotFound
    return row


def initialize(session, user):
    """One-time, audited adoption of this owner's existing uploads. Never adopt seed cases."""
    state = session.get(UploadWorkspace, user.id)
    if state is not None:
        return state
    state = UploadWorkspace(actor_id=user.id, version=1)
    if user.role == "admin":
        row = UploadSession(
            id=uuid4(),
            actor_id=user.id,
            key_sha256=hashlib.sha256(b"initial-upload-workspace-v1").hexdigest(),
        )
        session.add(row)
        session.flush()
        state.session_id = row.id
        session.execute(
            insert(UploadSessionItem).from_select(
                ["upload_id", "session_id"],
                select(CSVUpload.id, literal(row.id, type_=UploadSession.id.type)).where(
                    CSVUpload.actor_id == user.id,
                    ~select(UploadSessionItem.upload_id)
                    .where(UploadSessionItem.upload_id == CSVUpload.id)
                    .exists(),
                ),
            )
        )
        event(session, user.id, "initialized", row.id)
    session.add(state)
    session.flush()
    return state


def bind_upload(session, actor_id, upload, requested_session=None):
    """Called inside the existing staging transaction while its actor lock is held."""
    user = locked_actor(session, actor_id, admin=True)
    state = initialize(session, user)
    prior = session.get(UploadSessionItem, upload.id)
    if prior:
        if requested_session is not None and prior.session_id != requested_session:
            raise WorkspaceConflict
        return
    target = requested_session or state.session_id
    require_visible(session, user, target)
    if target != state.session_id:
        raise WorkspaceConflict
    session.add(UploadSessionItem(upload_id=upload.id, session_id=target))
    event(session, actor_id, "upload_linked", target, upload_id=str(upload.id))


def session_view(session, user, row):
    owned = user.role == "admin" and row.actor_id == user.id
    count = session.scalar(
        select(func.count())
        .select_from(Case)
        .where(Case.id.in_(case_membership(row.id)), visible_cases(user))
    )
    uploads = []
    upload_count = 0
    if owned:
        base = (
            select(CSVUpload)
            .join(UploadSessionItem, UploadSessionItem.upload_id == CSVUpload.id)
            .where(UploadSessionItem.session_id == row.id)
        )
        upload_count = session.scalar(select(func.count()).select_from(base.subquery()))
        # Metadata only, bounded recent receipts. Expired raw staging does not erase imported results.
        for upload in session.scalars(
            base.order_by(CSVUpload.created_at.desc(), CSVUpload.id.desc()).limit(20)
        ):
            imported = session.scalar(select(CSVImport).where(CSVImport.upload_id == upload.id))
            route = f"#/batch/upload/{upload.id}"
            status = upload.status
            if imported:
                route = f"#/batch/import/{imported.id}"
                status = imported.status
                batch = session.scalar(
                    select(BatchAssessment)
                    .where(BatchAssessment.import_id == imported.id)
                    .order_by(BatchAssessment.created_at.desc(), BatchAssessment.id.desc())
                    .limit(1)
                )
                if batch:
                    route += f"/assessment/{batch.id}"
                    status = batch.status
            else:
                validation = session.scalar(
                    select(CSVValidation)
                    .where(CSVValidation.upload_id == upload.id)
                    .order_by(CSVValidation.version.desc())
                    .limit(1)
                )
                if validation:
                    route += f"/validation/{validation.id}"
            uploads.append(
                dict(
                    upload_id=upload.id,
                    created_at=upload.created_at,
                    status=status,
                    resume_route=route,
                )
            )
    return dict(
        id=row.id,
        created_at=row.created_at,
        case_count=count,
        upload_count=upload_count,
        uploads=uploads,
        can_upload=owned,
    )


class UploadSessionService:
    def __init__(self, engine):
        self.engine = engine

    def lookup(self, actor_id, kind, reference_id):
        with Session(self.engine) as session, session.begin():
            user = locked_actor(session, actor_id, admin=True)
            initialize(session, user)
            statement = (
                select(UploadSessionItem.session_id)
                .join(CSVUpload, CSVUpload.id == UploadSessionItem.upload_id)
                .where(CSVUpload.actor_id == user.id)
            )
            if kind == "import":
                statement = statement.join(CSVImport, CSVImport.upload_id == CSVUpload.id).where(
                    CSVImport.id == reference_id
                )
            else:
                statement = statement.where(CSVUpload.id == reference_id)
            sid = session.scalar(statement)
            if sid is None:
                raise WorkspaceNotFound
            require_visible(session, user, sid)
            return dict(session_id=sid)

    def execute(
        self,
        actor_id,
        *,
        action="read",
        session_id=None,
        key=None,
        version=None,
        offset=0,
        limit=20,
    ):
        with Session(self.engine) as session, session.begin():
            if session.bind.dialect.name == "postgresql":
                session.execute(text("SET LOCAL lock_timeout='3s'"))
                session.execute(text("SET LOCAL statement_timeout='5s'"))
            user = locked_actor(session, actor_id, admin=action == "create")
            state = initialize(session, user)
            if action == "create":
                digest = hashlib.sha256(key.encode("ascii")).hexdigest()
                row = session.scalar(
                    select(UploadSession).where(
                        UploadSession.actor_id == user.id, UploadSession.key_sha256 == digest
                    )
                )
                if row is None:
                    if state.version != version:
                        raise WorkspaceConflict
                    row = UploadSession(
                        id=uuid4(), actor_id=user.id, key_sha256=digest, creation_version=version
                    )
                    session.add(row)
                    session.flush()
                    state.session_id, state.version = row.id, state.version + 1
                    event(session, user.id, "created", row.id, version=state.version)
                elif row.creation_version != version:
                    raise WorkspaceConflict
                # A retry must never reactivate a session superseded by a later user action.
            elif action == "select":
                row = require_visible(session, user, session_id)
                if state.session_id != row.id:
                    if state.version != version:
                        raise WorkspaceConflict
                    state.session_id, state.version = row.id, state.version + 1
                    event(session, user.id, "selected", row.id, version=state.version)
            active = (
                session.scalar(
                    select(UploadSession).where(
                        UploadSession.id == state.session_id, visible_sessions(user)
                    )
                )
                if state.session_id
                else None
            )
            if state.session_id and active is None:
                state.session_id, state.version = None, state.version + 1
            base = select(UploadSession).where(visible_sessions(user))
            total = session.scalar(select(func.count()).select_from(base.subquery()))
            rows = session.scalars(
                base.order_by(UploadSession.created_at.desc(), UploadSession.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            if active is None and rows:
                active = rows[0]
                state.session_id, state.version = active.id, state.version + 1
            return dict(
                version=state.version,
                active=session_view(session, user, active) if active else None,
                items=[dict(id=r.id, created_at=r.created_at) for r in rows],
                total=total,
                offset=offset,
                limit=limit,
            )
