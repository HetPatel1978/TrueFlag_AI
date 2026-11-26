"""Aggregate financial metadata only. No model requests or activation controls."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.assessments import errors
from app.models import User
from app.security.auth import require_admin
from app.services.assessment_api import AssessmentAPIService
from app.services.evidence import EvidenceBlocked, EvidenceNotFound, EvidenceUnavailable
from app.services.provider_usage import ProviderUsageService

router = APIRouter(prefix="/api/v1/internal/provider-usage", tags=["Internal operations"])


def execute(request, user, *, refresh=False):
    with errors(request):
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    service = ProviderUsageService(request.app.state.engine, request.app.state.settings)
    try:
        return service.refresh(user.id) if refresh else service.status(user.id)
    except EvidenceNotFound:
        raise HTTPException(403, "Administrator access unavailable") from None
    except EvidenceBlocked:
        raise HTTPException(
            409, "Provider balance refresh is disabled or temporarily limited"
        ) from None
    except EvidenceUnavailable:
        raise HTTPException(503, "Provider usage information unavailable") from None


@router.get("")
def usage(request: Request, user: User = Depends(require_admin)):
    return execute(request, user)


@router.post("/balance-refresh")
def refresh_balance(request: Request, user: User = Depends(require_admin)):
    return execute(request, user, refresh=True)


@router.get("/anthropic")
def anthropic_usage(request: Request, user: User = Depends(require_admin)):
    """Read-only Anthropic research usage: status, model, this month's requests and spend."""
    from datetime import datetime, timezone

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.services.research_drafts import ResearchDraftService

    with errors(request):
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    service = ResearchDraftService(request.app.state.engine, request.app.state.settings)
    try:
        with Session(request.app.state.engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            return service.anthropic_usage(session, datetime.now(timezone.utc))
    except Exception:
        raise HTTPException(503, "Provider usage information unavailable") from None
