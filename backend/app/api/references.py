"""Case-authenticated reference reads only; no curation/publication/upload capability."""

from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.evidence import errors as evidence_errors
from app.api.evidence import read_body, reader, slot
from app.models import User
from app.schemas.references import ReferenceQuery, ReferenceResult
from app.services.references import ReferenceBlocked, ReferenceInvalid, ReferenceService

router = APIRouter(prefix="/api/v1/cases/{case_id}/references", tags=["Regulatory context"])


def service(request):
    return ReferenceService(request.app.state.engine, request.app.state.settings)


@contextmanager
def reference_errors():
    try:
        yield
    except ReferenceInvalid:
        raise HTTPException(422, "Invalid regulatory reference request") from None
    except ReferenceBlocked:
        raise HTTPException(503, "Regulatory reference context unavailable") from None


@router.post(
    "/search",
    response_model=ReferenceResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ReferenceQuery.model_json_schema()}},
        }
    },
)
async def search(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, ReferenceQuery)
    with slot(request), evidence_errors(), reference_errors():
        return await run_in_threadpool(
            service(request).retrieve_reference_context, user.id, case_id, body
        )


@router.get("/{reference_id}", response_model=ReferenceResult)
def citation(case_id: UUID, reference_id: UUID, request: Request, user: User = Depends(reader)):
    with slot(request), evidence_errors(), reference_errors():
        return service(request).resolve_citation(user.id, case_id, reference_id)
