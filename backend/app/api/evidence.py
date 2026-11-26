"""Narrow authenticated evidence reads; no generic tool execution, inference or writes."""

import json
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.csv_uploads import unique_object
from app.models import User
from app.schemas.evidence_read import (
    AnalyticsRequest,
    AnalyticsResult,
    CaseContext,
    ContextQuery,
    CustomerPage,
    CustomerRequest,
    EvidenceResponse,
    ModelSignal,
    ReadRequest,
    RelatedPage,
    RelatedRequest,
    TransactionPage,
    TransactionRequest,
)
from app.security.auth import require_case_reader
from app.services.assessment_api import AssessmentAPIService, AssessmentRateLimited
from app.services.assessments import AssessmentError, AssessmentNotFound
from app.services.evidence import EvidenceError, EvidenceNotFound
from app.services.evidence_read import EvidenceReadService, ReadInvalid, ReadLimit, SnapshotStale
from app.services.snapshot_clock import ClockUnavailable

router = APIRouter(prefix="/api/v1/cases/{case_id}/evidence", tags=["Case evidence"])


@contextmanager
def errors():
    try:
        yield
    except (EvidenceNotFound, AssessmentNotFound):
        raise HTTPException(404, "Evidence resource not found") from None
    except SnapshotStale:
        raise HTTPException(
            409,
            "Evidence snapshot invalidated; obtain a new case context",
            headers={"X-TrueFlag-Reason": "snapshot_stale"},
        ) from None
    except ReadInvalid:
        raise HTTPException(422, "Invalid evidence request, snapshot or cursor") from None
    except ReadLimit:
        raise HTTPException(413, "Evidence request exceeds supported bounds") from None
    except AssessmentRateLimited as error:
        raise HTTPException(
            429,
            "Shared authenticated request limit reached",
            headers={"Retry-After": str(error.retry_after)},
        ) from None
    except ClockUnavailable:
        raise HTTPException(
            503,
            "Evidence clock safety unavailable",
            headers={"Retry-After": "2", "X-TrueFlag-Reason": "clock_uncertainty"},
        ) from None
    except (EvidenceError, AssessmentError, ValidationError):
        raise HTTPException(
            503, "Evidence service unavailable", headers={"Retry-After": "2"}
        ) from None


def reader(request: Request, user: User = Depends(require_case_reader)):
    with errors():
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    return user


@contextmanager
def slot(request):
    slots = request.app.state.evidence_read_slots
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Evidence read capacity reached", headers={"Retry-After": "1"})
    try:
        yield
    finally:
        slots.release()


def service(request):
    return EvidenceReadService(request.app.state.engine, request.app.state.settings)


async def read_body(request, model):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Evidence queries require application/json")
    raw = await request.body()
    if len(raw) > 12288:
        raise HTTPException(413, "Evidence query exceeds request limit")
    try:
        parsed = json.loads(raw, object_pairs_hook=unique_object)
        return model.model_validate_json(json.dumps(parsed, allow_nan=False))
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise HTTPException(422, "Invalid evidence query") from None


@router.get("", response_model=EvidenceResponse[CaseContext])
def case_context(
    case_id: UUID,
    query: Annotated[ContextQuery, Query()],
    request: Request,
    user: User = Depends(reader),
):
    with slot(request), errors():
        return service(request).get_case_context(user.id, case_id, query.assessment_id)


@router.post(
    "/transactions",
    response_model=EvidenceResponse[TransactionPage],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": TransactionRequest.model_json_schema()}},
        }
    },
)
async def transactions(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, TransactionRequest)
    with slot(request), errors():
        return await run_in_threadpool(service(request).get_transactions, user.id, case_id, body)


@router.post(
    "/customers",
    response_model=EvidenceResponse[CustomerPage],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": CustomerRequest.model_json_schema()}},
        }
    },
)
async def customers(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, CustomerRequest)
    with slot(request), errors():
        return await run_in_threadpool(
            service(request).get_customer_context, user.id, case_id, body
        )


@router.post(
    "/related",
    response_model=EvidenceResponse[RelatedPage],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": RelatedRequest.model_json_schema()}},
        }
    },
)
async def related(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, RelatedRequest)
    with slot(request), errors():
        return await run_in_threadpool(
            service(request).get_related_evidence, user.id, case_id, body
        )


@router.post(
    "/model",
    response_model=EvidenceResponse[ModelSignal],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ReadRequest.model_json_schema()}},
        }
    },
)
async def model_signal(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, ReadRequest)
    with slot(request), errors():
        return await run_in_threadpool(
            service(request).get_model_assessment, user.id, case_id, body
        )


@router.post(
    "/activity",
    response_model=EvidenceResponse[AnalyticsResult],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": AnalyticsRequest.model_json_schema()}},
        }
    },
)
async def activity(case_id: UUID, request: Request, user: User = Depends(reader)):
    body = await read_body(request, AnalyticsRequest)
    with slot(request), errors():
        return await run_in_threadpool(service(request).calculate_activity, user.id, case_id, body)
