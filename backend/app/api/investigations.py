"""Protected, bounded evidence-only packet gateway; API never executes a worker or model."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.evidence import errors as evidence_errors
from app.api.evidence import read_body, reader, slot
from app.api.references import reference_errors
from app.models import User
from app.schemas.investigation_api import (
    InvestigationDetail,
    InvestigationHistory,
    InvestigationStatus,
)
from app.schemas.investigations import InvestigationRequest
from app.schemas.references import ReferenceQuery
from app.services.evidence import EvidenceConflict
from app.services.evidence_read import ReadLimit
from app.services.investigation_api import InvestigationAPIService
from app.services.investigation_coordinator import (
    InvestigationBusy,
    InvestigationCoordinator,
    InvestigationInvalid,
)
from app.services.regulatory_investigation import RegulatoryInvestigationService

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/investigations", tags=["Evidence-only investigations"]
)


@router.post("/{run_id}/regulatory-context")
async def regulatory_context(
    case_id: UUID, run_id: UUID, request: Request, user: User = Depends(reader)
):
    body = await read_body(request, ReferenceQuery)
    with slot(request), errors(), reference_errors():
        result = await run_in_threadpool(
            RegulatoryInvestigationService(
                request.app.state.engine, request.app.state.settings
            ).prepare,
            user.id,
            case_id,
            run_id,
            body,
        )
    return {
        **result.result.model_dump(mode="json"),
        "investigation_run_id": str(result.investigation_run_id),
        "packet_sha256": result.packet_sha256,
        "binding_sha256": result.binding_sha256,
    }


@contextmanager
def errors():
    # Specific mappings precede the existing sanitized evidence boundary.
    with evidence_errors():
        try:
            yield
        except EvidenceConflict:
            raise HTTPException(
                409, "Investigation request conflicts; refresh case context"
            ) from None
        except InvestigationInvalid:
            raise HTTPException(422, "Invalid investigation request") from None
        except InvestigationBusy:
            raise HTTPException(
                429, "Investigation capacity reached", headers={"Retry-After": "5"}
            ) from None


def coordinator(request):
    return InvestigationCoordinator(request.app.state.engine, request.app.state.settings)


@router.post(
    "",
    response_model=InvestigationStatus,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": InvestigationRequest.model_json_schema()}},
        }
    },
)
async def request_packet(
    case_id: UUID,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    user: User = Depends(reader),
):
    body = await read_body(request, InvestigationRequest)
    with slot(request), errors():
        result = await run_in_threadpool(
            coordinator(request).request, user.id, case_id, idempotency_key, body
        )
    response.headers["Location"] = f"/api/v1/cases/{case_id}/investigations/{result['run_id']}"
    response.headers["Retry-After"] = "2"
    return result


@router.get("", response_model=InvestigationHistory)
def history(
    case_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    user: User = Depends(reader),
):
    with slot(request), errors():
        return InvestigationAPIService(
            request.app.state.engine, request.app.state.settings
        ).history(user.id, case_id, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=InvestigationDetail)
def detail(
    case_id: UUID, run_id: UUID, request: Request, response: Response, user: User = Depends(reader)
):
    with slot(request), errors():
        result = coordinator(request).get(user.id, case_id, run_id)
        try:
            bounded = InvestigationDetail.model_validate(result)
        except ValidationError:
            raise HTTPException(503, "Investigation result unavailable") from None
        if len(bounded.model_dump_json().encode()) > 524288:
            raise ReadLimit("investigation_response_limit")
    response.headers["Retry-After"] = "2"
    return bounded
