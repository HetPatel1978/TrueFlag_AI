"""Authorized HTTP application boundary: shared budgets, projections and sensitive-read audit."""

import math
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Assessment, AssessmentAPIThrottle, AssessmentJob, AuditEvent, Case, User
from app.schemas.assessments import AssessmentDetail, AssessmentPage, AssessmentSummary, JobStatus
from app.services.assessment_jobs import FAILURES, AssessmentJobService, _timeouts, _view
from app.services.assessments import AssessmentNotFound, AssessmentUnavailable, _locked_case, _read
from app.services.cases import visible_cases


class AssessmentRateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__("assessment_rate_limit")


def _budget(session, actor_id, settings):
    from app.models.domain import utcnow

    postgres = session.get_bind().dialect.name == "postgresql"
    now = session.scalar(select(func.clock_timestamp())) if postgres else utcnow()
    table = AssessmentAPIThrottle.__table__
    expired = table.c.window_start <= now - timedelta(
        seconds=settings.assessment_api_window_seconds
    )
    statement = (
        (pg_insert if postgres else sqlite_insert)(table)
        .values(
            actor_id=actor_id,
            window_start=now,
            request_count=1,
        )
        .on_conflict_do_update(
            index_elements=[table.c.actor_id],
            set_={
                "window_start": case((expired, now), else_=table.c.window_start),
                "request_count": case((expired, 1), else_=table.c.request_count + 1),
            },
            where=or_(expired, table.c.request_count < settings.assessment_api_rate_limit),
        )
        .returning(table.c.request_count)
    )
    if session.scalar(statement) is None:
        start = session.scalar(
            select(AssessmentAPIThrottle.window_start).where(
                AssessmentAPIThrottle.actor_id == actor_id,
            )
        )
        if start.tzinfo is None:
            start = start.replace(tzinfo=now.tzinfo)
        raise AssessmentRateLimited(
            max(
                1,
                math.ceil(
                    (
                        start + timedelta(seconds=settings.assessment_api_window_seconds) - now
                    ).total_seconds(),
                ),
            )
        )


def _summary(stored):
    p = stored["provenance"]
    return dict(
        assessment_id=stored["assessment_id"],
        case_id=stored["case_id"],
        alert_id=stored["alert_id"],
        run_id=stored["run_id"],
        version=stored["version"],
        case_version=stored["case_version"],
        status=stored["status"],
        processed_at=p["processed_at"],
        score=stored["score"]["score"],
        model_version=stored["score"]["model_version"],
        model_sha256=stored["score"]["model_sha256"],
        selected_policy=stored["decision"]["mode"],
        policy_version=stored["decision"]["policy_version"],
        recommended_route=stored["decision"]["route"],
        input_sha256=stored["input_sha256"],
        content_sha256=stored["content_sha256"],
        human_decision_required=True,
    )


def _detail(stored):
    p, e = stored["provenance"], stored["explanation"]
    snapshot, policy = p["snapshot"], p["policy"]
    verification = {k: v for k, v in stored["verification"].items() if k != "encoded_to_original"}
    return AssessmentDetail.model_validate(
        {
            **_summary(stored),
            "input_provenance": {
                "hash_schema": snapshot["input_hash_schema"],
                "ingestion_input_sha256": snapshot["ingestion_input_sha256"],
                "feature_contract_version": snapshot["feature_contract_version"],
                "contract_sha256": p["contract_sha256"],
            },
            "policy_trace": {
                name: policy[name]
                for name in (
                    "policy_sha256",
                    "threshold",
                    "priority_group",
                    "override_reason",
                    "routing_reason",
                    "score_based_retention",
                    "coverage_protection",
                    "coverage_changed_route",
                )
            },
            "explanation": {
                **{
                    name: e[name]
                    for name in (
                        "status",
                        "base_value",
                        "features",
                        "ranking",
                        "top_features",
                        "other_features_contribution",
                        "reconstruction_residual",
                        "method",
                    )
                },
                "verification": verification,
            },
        }
    )


def public_job(stored):
    value = dict(stored)
    if value["failure_code"] is not None and value["failure_code"] not in FAILURES:
        value["failure_code"] = "processing_unavailable"
    return JobStatus.model_validate(value)


def _audit(session, actor_id, case_id, action, **details):
    session.add(
        AuditEvent(actor_id=actor_id, action=action, resource_id=str(case_id), details=details)
    )


class AssessmentAPIService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def _timeouts(self, session):
        if self.engine.dialect.name == "postgresql":
            _timeouts(session)

    def consume(self, actor_id):
        # Independent budget: hidden IDs, failed reads and conflicts still count.
        with Session(self.engine) as session, session.begin():
            self._timeouts(session)
            actor = session.scalar(
                select(User.id)
                .where(
                    User.id == actor_id,
                    User.active.is_(True),
                    User.role.in_(["analyst", "supervisor", "admin"]),
                )
                .with_for_update(read=True)
            )
            if actor is None:
                raise AssessmentNotFound("assessment_not_found")
            _budget(session, actor_id, self.settings)

    def request(self, actor_id, case_id, body, key):
        job, _ = AssessmentJobService(self.engine).enqueue(
            actor_id=actor_id,
            case_id=case_id,
            **body.model_dump(),
            idempotency_key=key,
            capacity=self.settings.assessment_queue_capacity,
            request_audit=True,
        )
        return public_job(job)

    def job(self, actor_id, job_id):
        with Session(self.engine) as session, session.begin():
            self._timeouts(session)
            case_id = session.scalar(
                select(Case.id)
                .join(
                    AssessmentJob,
                    AssessmentJob.case_id == Case.id,
                )
                .where(AssessmentJob.id == job_id, visible_cases(SimpleNamespace(id=actor_id)))
            )
            if case_id is None:
                raise AssessmentNotFound("assessment_not_found")
            _locked_case(session, actor_id, case_id)
            job = session.scalar(
                select(AssessmentJob).where(
                    AssessmentJob.id == job_id,
                    AssessmentJob.case_id == case_id,
                )
            )
            result = public_job(_view(job))
            _audit(session, actor_id, case_id, "assessment.job.status_read", job_id=str(job_id))
            return result

    def history(self, actor_id, case_id, query):
        with Session(self.engine) as session, session.begin():
            self._timeouts(session)
            _locked_case(session, actor_id, case_id)
            total = session.scalar(
                select(func.count())
                .select_from(Assessment)
                .where(
                    Assessment.case_id == case_id,
                )
            )
            rows = session.scalars(
                select(Assessment)
                .where(Assessment.case_id == case_id)
                .order_by(Assessment.version.desc())
                .limit(query.limit)
                .offset(query.offset)
            )
            try:
                result = AssessmentPage(
                    items=[
                        AssessmentSummary.model_validate(_summary(_read(session, row)))
                        for row in rows
                    ],
                    total=total,
                    limit=query.limit,
                    offset=query.offset,
                )
            except Exception:
                raise AssessmentUnavailable("assessment_response_unavailable") from None
            _audit(
                session,
                actor_id,
                case_id,
                "assessment.history_read",
                limit=query.limit,
                offset=query.offset,
                returned=len(result.items),
            )
            return result

    def detail(self, actor_id, case_id, assessment_id):
        with Session(self.engine) as session, session.begin():
            self._timeouts(session)
            _locked_case(session, actor_id, case_id)
            row = session.scalar(
                select(Assessment).where(
                    Assessment.id == assessment_id,
                    Assessment.case_id == case_id,
                )
            )
            if row is None:
                raise AssessmentNotFound("assessment_not_found")
            try:
                result = _detail(_read(session, row))
            except Exception:
                raise AssessmentUnavailable("assessment_response_unavailable") from None
            _audit(
                session,
                actor_id,
                case_id,
                "assessment.detail_read",
                assessment_id=str(assessment_id),
            )
            return result
