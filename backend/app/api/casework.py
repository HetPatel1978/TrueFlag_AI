"""Protected human-only casework commands; no provider execution."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.api.case_workflows import errors as workflow_errors
from app.api.evidence import read_body, reader, slot
from app.models import User
from app.schemas.casework import ActionBody, CaseworkPage, Entry
from app.services.casework import CaseworkService
from app.services.evidence import EvidenceConflict

router = APIRouter(prefix="/api/v1", tags=["Human investigation casework"])


@contextmanager
def errors():
    with workflow_errors():
        try:
            yield
        except EvidenceConflict:
            raise HTTPException(
                409, "Casework changed or required review steps are incomplete; refresh and review"
            ) from None


def service(request):
    return CaseworkService(request.app.state.engine, request.app.state.settings)


@router.get("/cases/{case_id}/casework", response_model=CaseworkPage)
def history(
    case_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    user: User = Depends(reader),
):
    with slot(request), errors():
        return service(request).history(user.id, case_id, limit=limit, offset=offset)


@router.post("/cases/{case_id}/casework", response_model=Entry, status_code=201)
async def submit(
    case_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    ],
    user: User = Depends(reader),
):
    body = (await read_body(request, ActionBody)).root
    with slot(request), errors():
        return await run_in_threadpool(
            service(request).submit, user.id, case_id, idempotency_key, body
        )


@router.get("/supervisor-review-queue")
def supervisor_queue(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    user: User = Depends(reader),
):
    with slot(request), errors():
        return service(request).supervisor_queue(user.id, limit=limit, offset=offset)
