"""Explicit owned batch assessment request, current progress and verified results."""

import json
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.assessments import errors as assessment_errors
from app.api.csv_uploads import require_batch_uploader, unique_object
from app.models import User
from app.schemas.batch_assessments import BatchAssessmentStart, BatchProgress, BatchResultsPage
from app.services.assessment_api import AssessmentAPIService
from app.services.batch_assessments import BatchAssessmentService, BatchCapacity
from app.services.csv_staging import UploadDenied

router = APIRouter(tags=["Batch AML assessments"])


@contextmanager
def errors(request):
    with assessment_errors(request):
        try:
            yield
        except UploadDenied:
            raise HTTPException(403, "Batch assessment permission required") from None
        except BatchCapacity:
            raise HTTPException(
                429, "Active batch assessment capacity reached", headers={"Retry-After": "60"}
            ) from None


def reader(request: Request, user: User = Depends(require_batch_uploader)):
    with errors(request):
        AssessmentAPIService(request.app.state.engine, request.app.state.settings).consume(user.id)
    return user


def service(request):
    return BatchAssessmentService(
        request.app.state.engine, request.app.state.settings, request.app.state.telemetry
    )


@router.post(
    "/api/v1/batch-imports/{import_id}/assessments",
    response_model=BatchProgress,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": BatchAssessmentStart.model_json_schema()}},
        }
    },
)
async def start_batch_assessment(
    import_id: UUID,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"
        ),
    ],
    user: User = Depends(reader),
):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Start Assessment requires application/json")
    try:
        body = BatchAssessmentStart.model_validate(
            json.loads(await request.body(), object_pairs_hook=unique_object)
        )
    except (ValueError, ValidationError, RecursionError):
        raise HTTPException(422, "Invalid batch assessment request") from None
    with errors(request):
        result = await run_in_threadpool(
            service(request).start, user.id, import_id, body, idempotency_key
        )
    response.headers["Location"] = "/api/v1/batch-assessments/" + str(result.batch_id)
    response.headers["Retry-After"] = "2"
    return result


@router.get("/api/v1/batch-assessments/{batch_id}", response_model=BatchProgress)
def batch_assessment_status(
    batch_id: UUID, request: Request, response: Response, user: User = Depends(reader)
):
    with errors(request):
        result = service(request).get(user.id, batch_id)
    if result.status in {"dispatching", "processing"}:
        response.headers["Retry-After"] = "2"
    return result


@router.get("/api/v1/batch-assessments/{batch_id}/results", response_model=BatchResultsPage)
def batch_assessment_results(
    batch_id: UUID,
    request: Request,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
    user: User = Depends(reader),
):
    with errors(request):
        return service(request).get(user.id, batch_id, offset=offset, limit=limit)
