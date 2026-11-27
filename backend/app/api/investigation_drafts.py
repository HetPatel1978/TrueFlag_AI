"""Protected drafts with server-owned provider configuration and independent activation gates."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.evidence import read_body, reader, slot
from app.api.investigations import errors as investigation_errors
from app.models import User
from app.schemas.draft_api import (
    DraftDetail,
    DraftHistory,
    DraftRequestInput,
    DraftStartInput,
    DraftStartStatus,
    DraftStatus,
)
from app.services.draft_api import DraftAPIService
from app.services.evidence import EvidenceBlocked

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/investigation-drafts", tags=["Investigation drafts"]
)


def service(request):
    if request.app.state.settings.academic_research_enabled:
        from app.services.research_api import ResearchDraftAPIService

        return ResearchDraftAPIService(request.app.state.engine, request.app.state.settings)
    return DraftAPIService(request.app.state.engine, request.app.state.settings)


@router.get("/capabilities")
def capabilities(case_id: UUID, request: Request, user: User = Depends(reader)):
    with slot(request), errors():
        gateway = service(request)
        gateway.drafts.coordinator.reader.get_case_context(user.id, case_id)
        if request.app.state.settings.academic_research_enabled:
            return gateway.case_capabilities(user.id, case_id)
        return gateway.capabilities()


@router.post("/start", response_model=DraftStartStatus, status_code=202)
async def start(
    case_id: UUID,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    body = await read_body(request, DraftStartInput)
    with slot(request), errors():
        result = await run_in_threadpool(
            service(request).start, user.id, case_id, idempotency_key, body
        )
    response.headers["Location"] = (
        f"/api/v1/cases/{case_id}/investigation-drafts/{result.draft_run_id}"
    )
    response.headers["Retry-After"] = "2"
    return result


@contextmanager
def errors():
    with investigation_errors():
        try:
            yield
        except EvidenceBlocked as error:
            if str(error) == "offline_simulation_unavailable":
                raise HTTPException(
                    503,
                    "Offline simulation unavailable",
                    headers={"X-TrueFlag-Reason": "simulation_unavailable"},
                ) from None
            raise


@router.post(
    "",
    response_model=DraftStatus,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DraftRequestInput.model_json_schema()}},
        }
    },
)
async def submit(
    case_id: UUID,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    body = await read_body(request, DraftRequestInput)
    with slot(request), errors():
        result = await run_in_threadpool(
            service(request).request, user.id, case_id, idempotency_key, body
        )
    response.headers["Location"] = (
        f"/api/v1/cases/{case_id}/investigation-drafts/{result.draft_run_id}"
    )
    response.headers["Retry-After"] = "2"
    return result


@router.get("", response_model=DraftHistory)
def history(
    case_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    user: User = Depends(reader),
):
    with slot(request), errors():
        return service(request).history(user.id, case_id, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=DraftDetail)
def detail(
    case_id: UUID, run_id: UUID, request: Request, response: Response, user: User = Depends(reader)
):
    with slot(request), errors():
        result = service(request).detail(user.id, case_id, run_id)
    response.headers["Retry-After"] = "2"
    return result


@router.get("/research-context/latest")
def research_context(case_id: UUID, request: Request, user: User = Depends(reader)):
    with slot(request), errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        return service(request).context(user.id, case_id)


@router.post("/research-start", response_model=DraftStatus, status_code=202)
async def research_start(
    case_id: UUID,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    """Generate AI Investigation: prepare the exact request for review. Nothing is sent."""
    from app.schemas.research_demo import ResearchStartInput

    body = await read_body(request, ResearchStartInput)
    with slot(request), research_errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        result = await run_in_threadpool(
            service(request).start_research, user.id, case_id, idempotency_key, body
        )
    response.headers["Retry-After"] = "2"
    return result


@contextmanager
def research_errors():
    """Specific, non-revealing reasons for the AI request review actions."""
    reasons = {
        "research_approver_required": (403, "Not authorized to approve AI spending"),
        "research_budget_exhausted": (409, "AI spending cap reached"),
        "research_owner_policy_required": (409, "AI request approval is not configured"),
    }
    with errors():
        try:
            yield
        except EvidenceBlocked as error:
            if str(error) in reasons:
                status, detail = reasons[str(error)]
                raise HTTPException(
                    status, detail, headers={"X-TrueFlag-Reason": str(error)}
                ) from None
            raise


@router.get("/{run_id}/research-review")
def research_review(case_id: UUID, run_id: UUID, request: Request, user: User = Depends(reader)):
    with slot(request), research_errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        return service(request).review(user.id, case_id, run_id)


@router.post("/{run_id}/research-approve", response_model=DraftStatus, status_code=202)
async def research_approve(
    case_id: UUID,
    run_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    """Approve & Run Once. Authorization, hash, evidence and cap are re-derived server-side."""
    from app.schemas.research_demo import ResearchApproveInput

    body = await read_body(request, ResearchApproveInput)
    with slot(request), research_errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        return await run_in_threadpool(
            service(request).approve, user.id, case_id, run_id, body.request_sha256
        )


@router.post("/{run_id}/research-cancel", response_model=DraftStatus)
def research_cancel(
    case_id: UUID,
    run_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    with slot(request), research_errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        return service(request).cancel(user.id, case_id, run_id)


@router.post("/{run_id}/execute-research", response_model=DraftStatus, status_code=202)
def execute_research(
    case_id: UUID,
    run_id: UUID,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")],
    user: User = Depends(reader),
):
    with slot(request), errors():
        if not request.app.state.settings.academic_research_enabled:
            raise HTTPException(404, "Research context unavailable")
        return service(request).execute(user.id, case_id, run_id, idempotency_key)
