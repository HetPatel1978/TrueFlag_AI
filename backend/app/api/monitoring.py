"""Internal aggregate-only operational endpoint; no per-case monitoring view."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models import User
from app.security.auth import require_admin
from app.services.assessments import AssessmentNotFound
from app.services.monitoring import collect

router = APIRouter(prefix="/api/v1/internal", tags=["Internal operations"])


@router.get("/metrics")
def operational_metrics(
    request: Request,
    minutes: int = Query(default=15, ge=1, le=60),
    user: User = Depends(require_admin),
):
    try:
        return collect(request.app.state.engine, request.app.state.telemetry, user.id, minutes)
    except AssessmentNotFound:
        raise HTTPException(403, "Internal monitoring permission required") from None
