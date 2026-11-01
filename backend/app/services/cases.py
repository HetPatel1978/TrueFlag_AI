from datetime import timezone
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy import case as sql_case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Alert, AssessmentJob, AuditEvent, Case, User
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


def workbench_statement():
    # Scalar projections only: do not load raw predictors into a browser response.
    latest_id = (
        select(AssessmentJob.id)
        .where(AssessmentJob.case_id == Case.id)
        .order_by(AssessmentJob.created_at.desc(), AssessmentJob.id.desc())
        .limit(1)
        .correlate(Case)
        .scalar_subquery()
    )
    latest_status = (
        select(AssessmentJob.status)
        .where(AssessmentJob.id == latest_id)
        .correlate(Case)
        .scalar_subquery()
    )
    # Frozen policy mapping: KYC 0/1/2 Standard; 3/4/5/6 High. No RF invocation.
    priority = sql_case((Alert.features["kycRiskScore"].as_float() >= 3, "High"), else_="Standard")
    return select(
        Case,
        Alert.source_id,
        priority.label("priority"),
        func.coalesce(latest_status, "not_requested").label("assessment_status"),
        latest_id.label("latest_job_id"),
    ).join(Alert, Alert.id == Case.alert_id)


def workbench_summary(row):
    case, source, priority, status, job_id = row
    return {
        **summary(case),
        "source_id": source,
        "priority": priority,
        "assessment_status": status,
        "latest_job_id": job_id,
    }


def get_overview(session: Session, user: User, case_id: UUID) -> dict:
    row = session.execute(
        workbench_statement().where(Case.id == case_id, visible_cases(user))
    ).one_or_none()
    if row is None:
        raise CaseNotFound
    result = workbench_summary(row)
    session.add(AuditEvent(actor_id=user.id, action="case.overview_read", resource_id=str(case_id)))
    session.commit()
    return result


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
    statement = workbench_statement()
    if query.search:
        # SQL-bound literal substring; wildcard characters cannot expand the search scope.
        terms = [Alert.source_id.icontains(query.search, autoescape=True)]
        compact_id = query.search.replace("-", "")
        if compact_id:
            terms.extend(
                func.replace(cast(column, String), "-", "").icontains(compact_id, autoescape=True)
                for column in (Case.id, Case.alert_id)
            )
        predicates.append(or_(*terms))
    if query.priority:
        predicates.append(statement.selected_columns.priority == query.priority)
    if query.assessment_status:
        predicates.append(statement.selected_columns.assessment_status == query.assessment_status)
    columns = {"created_at": Case.created_at, "status": Case.status, "version": Case.version}
    column = columns[query.sort_by]
    order = (
        [column.asc(), Case.id.asc()]
        if query.sort_order == "asc"
        else [column.desc(), Case.id.desc()]
    )
    filtered = statement.where(*predicates)
    total = session.scalar(select(func.count()).select_from(filtered.subquery()))
    rows = session.execute(filtered.order_by(*order).offset(query.offset).limit(query.limit))
    return {
        "items": [workbench_summary(row) for row in rows],
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
