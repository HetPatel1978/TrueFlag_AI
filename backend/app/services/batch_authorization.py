"""Additional current authority for jobs originating in an explicit owned batch."""

from sqlalchemy import select

from app.models import BatchAssessment, BatchAssessmentItem, User
from app.services.assessments import AssessmentNotFound
from trueflag_ml.policy import POLICY_SHA256
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION


def check_batch_job(session, job):
    batch = session.scalar(
        select(BatchAssessment)
        .join(BatchAssessmentItem, BatchAssessmentItem.batch_id == BatchAssessment.id)
        .where(BatchAssessmentItem.job_id == job.id, BatchAssessmentItem.originated.is_(True))
    )
    # A direct case job may be observed by batches; its original authority remains independent.
    if batch is None:
        return
    allowed = session.scalar(
        select(User.id).where(
            User.id == batch.actor_id, User.active.is_(True), User.role == "admin"
        )
    )
    if (
        allowed is None
        or batch.status != "active"
        or batch.actor_id != job.actor_id
        or batch.policy != job.policy
        or batch.model_sha256 != APPROVED_SHA256[MODEL_PATH]
        or batch.model_version != MODEL_VERSION
        or batch.policy_sha256 != POLICY_SHA256
        or batch.policy_version != f"{MODEL_VERSION}:{POLICY_SHA256}"
    ):
        raise AssessmentNotFound("assessment_not_found")
