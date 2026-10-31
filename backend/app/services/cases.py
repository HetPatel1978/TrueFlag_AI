from datetime import timezone
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Alert, AuditEvent, Case, User
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.schemas.cases import AssignmentInput, CaseQuery


class CaseNotFound(Exception):
    pass


class AssignmentConflict(Exception):
    pass


class InvalidAssignee(Exception):
    pass


class AssignmentPermissionDenied(Exception):
    pass


class CaseDataUnavailable(SQLAlchemyError):
    pass


def visible_cases(user: User):
    # Recheck active role in the same SQL snapshot as the protected data read.
    return (
        select(User.id)
        .where(
            User.id == user.id,
            User.active.is_(True),
            or_(
                User.role.in_(["supervisor", "admin"]),
                and_(User.role == "analyst", Case.assigned_to == user.id),
            ),
        )
        .correlate(Case)
        .exists()
    )


def summary(case: Case) -> dict:
    created = case.created_at
    return {
        "id": case.id,
        "alert_id": case.alert_id,
        "assigned_to": case.assigned_to,
        "status": case.status,
        "disposition": case.disposition,
        "version": case.version,
        "created_at": created if created.tzinfo else created.replace(tzinfo=timezone.utc),
    }


def list_cases(session: Session, user: User, query: CaseQuery) -> dict:
    predicates = [visible_cases(user)]
    if query.status is not None:
        predicates.append(Case.status == query.status)
    if query.assigned_to is not None:
        predicates.append(Case.assigned_to == query.assigned_to)
    if query.assignment == "assigned":
        predicates.append(Case.assigned_to.is_not(None))
    elif query.assignment == "unassigned":
        predicates.append(Case.assigned_to.is_(None))
    columns = {"created_at": Case.created_at, "status": Case.status, "version": Case.version}
    column = columns[query.sort_by]
    order = (
        [column.asc(), Case.id.asc()]
        if query.sort_order == "asc"
        else [column.desc(), Case.id.desc()]
    )
    total = session.scalar(select(func.count()).select_from(Case).where(*predicates))
    rows = session.scalars(
        select(Case).where(*predicates).order_by(*order).offset(query.offset).limit(query.limit)
    )
    return {
        "items": [summary(row) for row in rows],
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
    }


def get_case(session: Session, user: User, case_id: UUID) -> dict:
    # Scope and fetch case/customer data in one SQL statement, including under reassignment.
    row = session.execute(
        select(Case, Alert)
        .join(Alert, Alert.id == Case.alert_id)
        .where(Case.id == case_id, visible_cases(user))
    ).one_or_none()
    if row is None:
        raise CaseNotFound
    case, alert = row
    if (
        alert is None
        or alert.data_classification != "synthetic"
        or alert.feature_contract_version != FEATURE_CONTRACT_VERSION
    ):
        raise CaseDataUnavailable
    try:
        values = {name: alert.features[name] for name in AlertFeatures.model_fields}
        features = AlertFeatures.model_validate(values)
    except (KeyError, TypeError, ValidationError):
        raise CaseDataUnavailable from None
    return {
        **summary(case),
        "alert": {
            "source_id": alert.source_id,
            "data_classification": alert.data_classification,
            "feature_contract_version": alert.feature_contract_version,
            "features": features,
        },
    }


def assign_case(session: Session, actor_id: UUID, case_id: UUID, body: AssignmentInput) -> dict:
    try:
        manager = session.scalar(
            select(User.id)
            .where(
                User.id == actor_id, User.active.is_(True), User.role.in_(["supervisor", "admin"])
            )
            .with_for_update(read=True)
        )
        if manager is None:
            raise AssignmentPermissionDenied
        case = session.get(Case, case_id)
        if case is None:
            raise CaseNotFound
        if case.version != body.expected_version or case.status == "closed":
            raise AssignmentConflict
        if body.assigned_to is not None:
            target = session.scalar(
                select(User)
                .where(User.id == body.assigned_to, User.active.is_(True), User.role == "analyst")
                .with_for_update(read=True)
            )
            if target is None:
                raise InvalidAssignee
        previous = case.assigned_to
        unchanged = previous == body.assigned_to
        changed = session.scalar(
            update(Case)
            .where(
                Case.id == case_id, Case.version == body.expected_version, Case.status != "closed"
            )
            .values(
                assigned_to=body.assigned_to,
                version=Case.version if unchanged else Case.version + 1,
            )
            .returning(Case)
            .execution_options(populate_existing=True)
        )
        if changed is None:
            raise AssignmentConflict
        result = summary(changed)
        if not unchanged:
            session.add(
                AuditEvent(
                    actor_id=actor_id,
                    action="case.assignment_changed",
                    resource_id=str(case_id),
                    details={
                        "previous_assigned_to": str(previous) if previous else None,
                        "assigned_to": str(body.assigned_to) if body.assigned_to else None,
                        "previous_version": body.expected_version,
                        "version": changed.version,
                    },
                )
            )
        session.flush()
        session.commit()
        return result
    except BaseException:
        session.rollback()
        raise
