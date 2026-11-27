"""Read-only workflow projections over existing case and immutable workflow records."""

from datetime import timezone
from uuid import UUID

from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.models import Assessment, AssessmentJob, AuditEvent, Case, User
from app.models.casework import CaseworkEntry
from app.models.investigation_drafts import DraftRun
from app.models.investigations import InvestigationRun
from app.services.assessments import AssessmentNotFound, _locked_case, _read
from app.services.cases import (
    AssignmentPermissionDenied,
    CaseDataUnavailable,
    list_cases,
    workbench_statement,
    workbench_summary,
)
from app.services.evidence import EvidenceError, EvidenceNotFound, atomic, audit


class WorkflowForbidden(EvidenceError):
    pass


class WorkflowConflict(EvidenceError):
    pass


def locked_case(session, actor_id, case_id):
    try:
        return _locked_case(session, actor_id, case_id)
    except AssessmentNotFound:
        raise EvidenceNotFound("case_unavailable") from None


CASE_EVENTS = {
    "evidence.casework.note": ("casework_note", "recorded"),
    "evidence.casework.information_request": ("casework_information_request", "pending"),
    "evidence.casework.information_response": ("casework_information_response", "recorded"),
    "evidence.casework.finding_review": ("casework_finding_review", "recorded"),
    "evidence.casework.escalation": ("casework_escalation", "pending"),
    "evidence.casework.supervisor_response": ("casework_supervisor_response", "recorded"),
    "evidence.casework.resolution": ("casework_resolution", "completed"),
    "case.assignment_changed": ("assignment_changed", "recorded"),
    "assessment.completed": ("assessment_completed", "completed"),
    "evidence.case_bound": ("evidence_linked", "recorded"),
    "evidence.versions_linked": ("evidence_revised", "recorded"),
    "evidence.source_granted": ("evidence_access_granted", "recorded"),
    "evidence.source_revoked": ("evidence_access_revoked", "recorded"),
    "evidence.links_revoked": ("evidence_records_revoked", "recorded"),
}
ASSESSMENT_EVENTS = {
    "assessment.job.enqueued": ("assessment_enqueued", "pending"),
    "assessment.job.requested": ("assessment_requested", "recorded"),
    "assessment.job.claimed": ("assessment_processing", "running"),
    "assessment.job.retry_scheduled": ("assessment_retry_scheduled", "retry_scheduled"),
    "assessment.job.failed": ("assessment_failed", "failed"),
    "assessment.job.succeeded": ("assessment_processing_completed", "completed"),
}
INVESTIGATION_EVENTS = {
    "evidence.investigation.requested": ("summary_requested", "pending"),
    "evidence.investigation.claimed": ("summary_processing", "running"),
    "evidence.investigation.published": ("summary_published", "completed"),
    "evidence.investigation.attempt_failed": ("summary_attempt_failed", "recorded"),
    "evidence.investigation.invalidated": ("summary_invalidated", "invalidated"),
}


# AI investigation (draft) lifecycle; reads, history views and internal binding steps excluded.
DRAFT_EVENTS = {
    "evidence.investigation.draft.requested": ("ai_investigation_requested", "pending"),
    "evidence.investigation.draft.research_request_owner_approved": (
        "ai_investigation_approved",
        "recorded",
    ),
    "evidence.investigation.draft.claimed": ("ai_investigation_processing", "running"),
    "evidence.investigation.draft.published": ("ai_investigation_completed", "completed"),
    "evidence.investigation.draft.attempt_failed": ("ai_investigation_failed", "failed"),
}


FAILED_DRAFT = "evidence.investigation.draft.attempt_failed"


def _same_failure(earlier):
    """Identical failure record: same request, same reason, same attempt number."""
    return and_(
        earlier.resource_id == AuditEvent.resource_id,
        earlier.action == FAILED_DRAFT,
        earlier.details["reason"].as_string() == AuditEvent.details["reason"].as_string(),
        earlier.details["attempt"].as_string() == AuditEvent.details["attempt"].as_string(),
    )


def first_draft_failure():
    """Legacy re-reads appended identical failure records; show only the first of each."""
    earlier = aliased(AuditEvent)
    return or_(
        AuditEvent.action != FAILED_DRAFT,
        ~exists().where(
            _same_failure(earlier),
            or_(
                earlier.created_at < AuditEvent.created_at,
                and_(earlier.created_at == AuditEvent.created_at, earlier.id < AuditEvent.id),
            ),
        ),
    )


def duplicate_failures(session, row):
    """How many identical failure records followed this one (kept as audit data)."""
    later = aliased(AuditEvent)
    return session.scalar(
        select(func.count())
        .select_from(later)
        .where(
            later.resource_id == row.resource_id,
            later.action == FAILED_DRAFT,
            later.details["reason"].as_string() == (row.details or {}).get("reason"),
            later.details["attempt"].as_string() == str((row.details or {}).get("attempt")),
            or_(
                later.created_at > row.created_at,
                and_(later.created_at == row.created_at, later.id > row.id),
            ),
        )
    )


def draft_runs_of(case_id):
    return (
        select(cast(DraftRun.id, String))
        .join(InvestigationRun, DraftRun.parent_run_id == InvestigationRun.id)
        .where(InvestigationRun.case_id == case_id)
    )


def active_actor(session, actor_id, *, manager=False):
    roles = ["supervisor", "admin"] if manager else ["analyst", "supervisor", "admin"]
    user = session.scalar(
        select(User)
        .where(User.id == actor_id, User.active.is_(True), User.role.in_(roles))
        .with_for_update(read=True)
    )
    if user is None:
        raise WorkflowForbidden("case_workflow_forbidden")
    return user


def version(details, key):
    value = details.get(key)
    return value if type(value) is int and 0 <= value <= 2147483647 else None


RESOLUTIONS = {
    "additional_review_required",
    "no_further_action_recommended",
    "escalated_for_compliance_review",
    "investigation_completed",
}


class CaseWorkflowService:
    def __init__(self, engine):
        self.engine = engine

    @atomic
    def overview(self, session, actor_id, case_id):
        active_actor(session, actor_id)
        case = locked_case(session, actor_id, case_id)
        row = session.execute(workbench_statement().where(Case.id == case.id)).one()
        result = workbench_summary(row)
        result.update(self._enrichment(session, case))
        result["last_activity_at"] = last_activity(session, [case.id]).get(case.id)
        audit(session, actor_id, "case_workflow_read", case_id)
        return result

    def _enrichment(self, session, case):
        name = (
            session.scalar(select(User.username).where(User.id == case.assigned_to))
            if case.assigned_to
            else None
        )
        assessment = session.scalar(
            select(Assessment)
            .where(Assessment.case_id == case.id)
            .order_by(Assessment.version.desc(), Assessment.id.desc())
            .limit(1)
        )
        recommendation = score = None
        if assessment is not None:
            content = _read(session, assessment)  # integrity-verified
            recommendation = content["decision"]["route"]
            if content["score"]["status"] == "processed":
                score = content["score"]["score"]
            if recommendation not in {"retain_human_review", "review_reduction_candidate"}:
                raise CaseDataUnavailable
        resolution = session.scalar(
            select(CaseworkEntry.payload["outcome"].as_string())
            .where(CaseworkEntry.case_id == case.id, CaseworkEntry.kind == "resolution")
            .order_by(CaseworkEntry.revision.desc())
            .limit(1)
        )
        return dict(
            assigned_investigator=name,
            review_recommendation=recommendation,
            assessment_version=assessment.version if assessment else None,
            assessment_score=score,
            resolution=resolution if resolution in RESOLUTIONS else None,
        )

    @atomic
    def queue(self, session, actor_id, query):
        from app.services.upload_sessions import WorkspaceNotFound

        user = active_actor(session, actor_id)
        try:
            page = list_cases(session, user, query)
        except AssignmentPermissionDenied:
            raise WorkflowForbidden("case_workflow_forbidden") from None
        except WorkspaceNotFound:
            raise EvidenceNotFound("upload_session_unavailable") from None
        for item in page["items"]:
            case = locked_case(session, actor_id, item["id"])
            session.refresh(case)
            if case.version != item["version"] or case.assigned_to != item["assigned_to"]:
                raise WorkflowConflict("case_changed")
            item.update(self._enrichment(session, case))
        latest = last_activity(session, [item["id"] for item in page["items"]])
        for item in page["items"]:
            item["last_activity_at"] = latest.get(item["id"])
        audit(
            session,
            actor_id,
            "case_queue_read",
            "case-queue",
            queue=query.queue,
            returned=len(page["items"]),
        )
        return page

    @atomic
    def directory(self, session, actor_id, case_id, query):
        active_actor(session, actor_id, manager=True)
        case = locked_case(session, actor_id, case_id)
        if case.status == "closed":
            raise WorkflowConflict("case_closed")
        predicate = [User.role == "analyst", User.active.is_(True)]
        if query.search:
            predicate.append(User.username.icontains(query.search, autoescape=True))
        total = session.scalar(select(func.count()).select_from(User).where(*predicate))
        users = session.execute(
            select(User.id, User.username)
            .where(*predicate)
            .order_by(User.username, User.id)
            .offset(query.offset)
            .limit(query.limit)
        ).all()
        audit(session, actor_id, "assignment_options_read", case_id, returned=len(users))
        return {
            "items": [dict(id=u.id, username=u.username) for u in users],
            "total": total,
            "limit": query.limit,
            "offset": query.offset,
            "case_version": case.version,
        }

    @atomic
    def activity(self, session, actor_id, case_id, query):
        active_actor(session, actor_id)
        case = locked_case(session, actor_id, case_id)
        # Resource membership is bound through canonical FK tables, never JSON case_id claims.
        conditions = [
            and_(AuditEvent.resource_id == str(case_id), AuditEvent.action.in_(CASE_EVENTS))
        ]
        if query.category == "assignment":
            conditions = [
                and_(
                    AuditEvent.resource_id == str(case_id),
                    AuditEvent.action == "case.assignment_changed",
                )
            ]
        else:
            conditions += [
                and_(
                    AuditEvent.resource_id == str(case.alert_id),
                    AuditEvent.action == "alert.ingested",
                ),
                and_(
                    AuditEvent.resource_id.in_(
                        select(cast(AssessmentJob.id, String)).where(
                            AssessmentJob.case_id == case_id
                        )
                    ),
                    AuditEvent.action.in_(ASSESSMENT_EVENTS),
                ),
                and_(
                    AuditEvent.resource_id.in_(
                        select(cast(InvestigationRun.id, String)).where(
                            InvestigationRun.case_id == case_id
                        )
                    ),
                    AuditEvent.action.in_(INVESTIGATION_EVENTS),
                ),
                and_(
                    AuditEvent.resource_id.in_(draft_runs_of(case_id)),
                    AuditEvent.action.in_(DRAFT_EVENTS),
                    first_draft_failure(),
                ),
            ]
        predicate = or_(*conditions)
        total = session.scalar(select(func.count()).select_from(AuditEvent).where(predicate))
        rows = session.scalars(
            select(AuditEvent)
            .where(predicate)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(query.offset)
            .limit(query.limit)
        ).all()
        items = []
        for row in rows:
            event, outcome = (
                {
                    **CASE_EVENTS,
                    **ASSESSMENT_EVENTS,
                    **INVESTIGATION_EVENTS,
                    **DRAFT_EVENTS,
                    "alert.ingested": ("alert_ingested", "recorded"),
                }
            )[row.action]
            details = row.details if type(row.details) is dict else {}
            if row.action == "evidence.investigation.attempt_failed":
                if details.get("retryable") is True:
                    outcome = "retry_scheduled"
                elif details.get("retryable") is False:
                    outcome = "failed"
            if (
                row.action == "evidence.investigation.draft.attempt_failed"
                and details.get("reason") == "input_invalidated"
            ):
                outcome = "invalidated"
            duplicates = duplicate_failures(session, row) if row.action == FAILED_DRAFT else 0
            if row.action == "assessment.job.enqueued" and details.get("reused_assessment") is True:
                outcome = "completed"
            item = dict(
                id=row.id,
                case_id=case_id,
                recorded_at=row.created_at
                if row.created_at.tzinfo
                else row.created_at.replace(tzinfo=timezone.utc),
                event_type=event,
                actor="you"
                if row.actor_id == actor_id
                else "redacted"
                if row.actor_id
                else "system",
                outcome=outcome,
            )
            for key in ["evidence_revision", "access_revision"]:
                item[key] = version(details, key)
            if duplicates:
                item["duplicate_records"] = duplicates
            if row.action == "case.assignment_changed":
                item["case_version"] = version(details, "version")
                previous, assigned = details.get("previous_assigned_to"), details.get("assigned_to")
                # Historical transition only, never disclose identities from arbitrary payloads.
                if assigned is None:
                    item["assignment_change"] = "unassigned"
                elif type(assigned) is str and valid_uuid(assigned):
                    item["assignment_change"] = (
                        "reassigned"
                        if type(previous) is str and valid_uuid(previous)
                        else "assigned"
                    )
            if row.action == "assessment.completed":
                assessment = session.scalar(
                    select(Assessment).where(
                        Assessment.case_id == case_id, Assessment.audit_event_id == row.id
                    )
                )
                if assessment is not None:
                    _read(session, assessment)
                    item["assessment_version"] = assessment.version
            if (
                row.action == "evidence.investigation.published"
                and details.get("outcome") == "abstained"
            ):
                item["outcome"] = "abstained"
            items.append(item)
        # Read auditing excluded from the event allowlist, avoiding self-amplifying histories.
        audit(
            session,
            actor_id,
            "case_activity_read",
            case_id,
            category=query.category,
            returned=len(items),
        )
        return dict(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
            case_version=case.version,
            historical=True,
        )


def last_activity(session, case_ids):
    """Newest Activity-History event per case, for a whole page in one statement."""
    if not case_ids:
        return {}
    ids = [i if isinstance(i, UUID) else UUID(str(i)) for i in case_ids]
    sources = [
        select(Case.id.label("case_id"), AuditEvent.created_at)
        .join(AuditEvent, AuditEvent.resource_id == cast(Case.id, String))
        .where(Case.id.in_(ids), AuditEvent.action.in_(CASE_EVENTS)),
        select(Case.id.label("case_id"), AuditEvent.created_at)
        .join(AuditEvent, AuditEvent.resource_id == cast(Case.alert_id, String))
        .where(Case.id.in_(ids), AuditEvent.action == "alert.ingested"),
        select(AssessmentJob.case_id.label("case_id"), AuditEvent.created_at)
        .join(AuditEvent, AuditEvent.resource_id == cast(AssessmentJob.id, String))
        .where(AssessmentJob.case_id.in_(ids), AuditEvent.action.in_(ASSESSMENT_EVENTS)),
        select(InvestigationRun.case_id.label("case_id"), AuditEvent.created_at)
        .join(AuditEvent, AuditEvent.resource_id == cast(InvestigationRun.id, String))
        .where(InvestigationRun.case_id.in_(ids), AuditEvent.action.in_(INVESTIGATION_EVENTS)),
        select(InvestigationRun.case_id.label("case_id"), AuditEvent.created_at)
        .join(DraftRun, DraftRun.parent_run_id == InvestigationRun.id)
        .join(AuditEvent, AuditEvent.resource_id == cast(DraftRun.id, String))
        .where(
            InvestigationRun.case_id.in_(ids),
            AuditEvent.action.in_(DRAFT_EVENTS),
            first_draft_failure(),
        ),
    ]
    events = sources[0].union_all(*sources[1:]).subquery()
    rows = session.execute(
        select(events.c.case_id, func.max(events.c.created_at)).group_by(events.c.case_id)
    ).all()
    return {case_id: at if at.tzinfo else at.replace(tzinfo=timezone.utc) for case_id, at in rows}


def valid_uuid(value):
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False
