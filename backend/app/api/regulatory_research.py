"""Administrator-only metadata search for unapproved regulatory research."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.api.assessments import errors
from app.core.database import get_session
from app.models import AuditEvent, User
from app.models.references import (
    ReferenceApproval,
    ReferenceChunk,
    ReferenceDocument,
    ReferenceSource,
    ReferenceVersion,
)
from app.security.auth import require_admin
from app.services.assessment_api import AssessmentAPIService

router = APIRouter(prefix="/api/v1/internal/regulatory-research", tags=["Internal research"])


@router.get("")
def search_research(
    request: Request,
    q: str = Query(default="", max_length=100),
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    # Metadata only: never return unapproved passage text or grant AI eligibility.
    with errors(request):
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    approved = exists(
        select(ReferenceApproval.id).where(ReferenceApproval.version_id == ReferenceVersion.id)
    )
    indexed = exists(
        select(ReferenceChunk.id).where(ReferenceChunk.version_id == ReferenceVersion.id)
    )
    query = (
        select(
            ReferenceDocument.id.label("document_id"),
            ReferenceVersion.id.label("version_id"),
            ReferenceDocument.title,
            ReferenceSource.publisher,
            ReferenceDocument.url,
            ReferenceDocument.origin,
            ReferenceDocument.authority,
            ReferenceDocument.jurisdiction,
            ReferenceDocument.entity,
            ReferenceVersion.version,
            ReferenceVersion.raw_sha256,
            ReferenceVersion.retrieved_at,
            ReferenceVersion.publication_date,
            ReferenceVersion.effective_from,
            ReferenceVersion.effective_to,
            ReferenceVersion.verified_through,
            ReferenceVersion.snapshot_date,
            ReferenceVersion.temporal_basis,
            ReferenceVersion.sections,
            indexed.label("indexed"),
        )
        .join(ReferenceVersion, ReferenceVersion.document_id == ReferenceDocument.id)
        .join(ReferenceSource, ReferenceSource.id == ReferenceDocument.source_id)
        .where(~approved)
        .order_by(ReferenceDocument.title, ReferenceVersion.version.desc())
        .limit(20)
    )
    if q.strip():
        query = query.where(
            or_(
                ReferenceDocument.title.icontains(q.strip(), autoescape=True),
                ReferenceDocument.key.icontains(q.strip(), autoescape=True),
            )
        )
    rows = session.execute(query).mappings().all()
    if (
        session.scalar(
            select(User.id).where(User.id == user.id, User.active.is_(True), User.role == "admin")
        )
        is None
    ):
        raise HTTPException(403, "Administrator access unavailable")
    session.add(AuditEvent(actor_id=user.id, action="regulatory.research_viewed"))
    session.commit()
    return {
        "status": "unapproved_research_only",
        "limit": 20,
        "results": [
            {
                "document_id": str(row["document_id"]),
                "version_id": str(row["version_id"]),
                "title": row["title"],
                "publisher": row["publisher"],
                "url": row["url"],
                "origin": row["origin"],
                "authority": row["authority"],
                "jurisdiction": row["jurisdiction"],
                "entity": row["entity"],
                "version": row["version"],
                "raw_sha256": row["raw_sha256"],
                "retrieved_at": row["retrieved_at"].isoformat(),
                "publication_date": row["publication_date"].isoformat()
                if row["publication_date"]
                else None,
                "effective_from": row["effective_from"].isoformat()
                if row["effective_from"]
                else None,
                "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
                "verified_through": row["verified_through"].isoformat()
                if row["verified_through"]
                else None,
                "snapshot_date": row["snapshot_date"].isoformat() if row["snapshot_date"] else None,
                "temporal_basis": row["temporal_basis"],
                "sections": row["sections"],
                "indexed": row["indexed"],
                "independently_approved": False,
                "published": False,
                "eligible_for_ai_grounding": False,
            }
            for row in rows
        ],
    }


def _corpus_call(request, user, call):
    """Read-only transaction; the snapshot hashes are re-verified on every call."""
    from sqlalchemy import text

    from app.services.evidence import EvidenceBlocked
    from app.services.research_demo import ResearchEvidenceService

    with errors(request):
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    service = ResearchEvidenceService(request.app.state.engine, request.app.state.settings)
    try:
        with Session(request.app.state.engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            return call(service, session)
    except EvidenceBlocked:
        raise HTTPException(409, "Retrieval corpus unavailable or failed verification") from None


@router.get("/corpus")
def retrieval_corpus(request: Request, user: User = Depends(require_admin)):
    return _corpus_call(request, user, lambda service, session: service.corpus_view(session))


@router.get("/corpus/search")
def test_retrieval(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    user: User = Depends(require_admin),
):
    return _corpus_call(
        request, user, lambda service, session: service.test_retrieval(session, q)
    )
