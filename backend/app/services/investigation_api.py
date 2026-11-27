"""History projection over existing coordinator; result reads retain independent verification."""

from sqlalchemy import func, select

from app.models.investigations import InvestigationJob, InvestigationRun
from app.schemas.investigations import InputManifest
from app.services.evidence import EvidenceBlocked, atomic, audit
from app.services.ingestion import digest
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.investigation_verifier import VerificationFailed


class InvestigationAPIService:
    def __init__(self, engine, settings):
        self.engine = engine
        self.coordinator = InvestigationCoordinator(engine, settings)

    @atomic
    def history(self, session, actor_id, case_id, *, limit=10, offset=0):
        if (
            type(limit) is not int
            or not 1 <= limit <= 20
            or type(offset) is not int
            or not 0 <= offset <= 1000
        ):
            raise EvidenceBlocked("invalid_history_query")
        self.coordinator._gate(session)
        self.coordinator.reader._context(session, actor_id, case_id)
        selection = select(InvestigationRun).where(
            InvestigationRun.actor_id == actor_id, InvestigationRun.case_id == case_id
        )
        total = session.scalar(select(func.count()).select_from(selection.subquery()))
        runs = session.scalars(
            selection.order_by(InvestigationRun.created_at.desc(), InvestigationRun.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items = []
        for run in runs:
            manifest = InputManifest.model_validate(run.input_manifest)
            if digest(manifest.model_dump(mode="json")) != run.manifest_sha256:
                raise VerificationFailed("investigation_verification_failed")
            job = session.get(InvestigationJob, run.id)
            items.append(
                {
                    **self.coordinator._view(job),
                    "created_at": run.created_at,
                    "manifest_sha256": run.manifest_sha256,
                    "assessment_id": run.assessment_id,
                    "case_version": manifest.snapshot.case_version,
                    "evidence_revision": manifest.snapshot.evidence_revision,
                    "access_revision": manifest.snapshot.access_revision,
                    "validation_status": "stored_not_revalidated",
                }
            )
        audit(session, actor_id, "investigation.history", case_id, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}
