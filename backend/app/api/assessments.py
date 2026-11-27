"""Protected asynchronous assessment APIs; API processes never load a model."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.models import User
from app.schemas.assessments import (
    AssessmentDetail,
    AssessmentPage,
    AssessmentQuery,
    AssessmentRequest,
    JobStatus,
)
from app.security.auth import require_case_reader
from app.services.assessment_api import AssessmentAPIService, AssessmentRateLimited
from app.services.assessment_jobs import QueueFull
from app.services.assessments import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
    AssessmentUnavailable,
)

router = APIRouter(prefix="/api/v1", tags=["AML assessments"])


@contextmanager
def errors(request=None):
    try:
        yield
    except AssessmentRateLimited as error:
        raise HTTPException(
            429,
            "Assessment request limit reached",
            headers={
                "Retry-After": str(error.retry_after),
            },
        ) from None
    except AssessmentNotFound:
        raise HTTPException(404, "Assessment resource not found") from None
    except AssessmentConflict:
        raise HTTPException(
            409, "Assessment request conflicts with existing content or case state"
        ) from None
    except QueueFull:
        if request is not None:
            request.app.state.telemetry.observe("api.queue_saturation")
        raise HTTPException(
            503, "Assessment queue is full; retry using the same key", headers={"Retry-After": "5"}
        ) from None
    except (AssessmentUnavailable, ValidationError):
        raise HTTPException(
            503, "Assessment service unavailable", headers={"Retry-After": "2"}
        ) from None
    except AssessmentError as error:
        if request is not None and str(error) == "job_admission_busy":
            request.app.state.telemetry.observe("api.queue_contention")
        raise HTTPException(
            503, "Assessment service unavailable", headers={"Retry-After": "2"}
        ) from None


def service(request):
    return AssessmentAPIService(request.app.state.engine, request.app.state.settings)


def assessment_reader(request: Request, user: User = Depends(require_case_reader)):
    with errors(request):
        service(request).consume(user.id)
    return user


@router.post(
    "/cases/{case_id}/assessments",
    response_model=JobStatus,
    status_code=202,
    responses={
        404: {"description": "Hidden or missing case"},
        409: {"description": "Stale case or idempotency conflict"},
        429: {"description": "Shared authenticated request budget exhausted"},
        503: {"description": "Queue full, busy or unavailable"},
    },
)
def request_assessment(
    case_id: UUID,
    body: AssessmentRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
        ),
    ],
    user: User = Depends(assessment_reader),
):
    with errors(request):
        result = service(request).request(user.id, case_id, body, idempotency_key)
    response.headers["Location"] = f"/api/v1/assessment-jobs/{result.job_id}"
    response.headers["Retry-After"] = "2"
    return result


@router.get("/assessment-jobs/{job_id}", response_model=JobStatus)
def assessment_job(
    job_id: UUID, request: Request, response: Response, user: User = Depends(assessment_reader)
):
    with errors(request):
        result = service(request).job(user.id, job_id)
    if result.status in {"pending", "running"}:
        response.headers["Retry-After"] = "2"
    return result


@router.get("/cases/{case_id}/assessments", response_model=AssessmentPage)
def assessment_history(
    case_id: UUID,
    query: Annotated[AssessmentQuery, Query()],
    request: Request,
    user: User = Depends(assessment_reader),
):
    with errors(request):
        return service(request).history(user.id, case_id, query)


@router.get("/cases/{case_id}/assessments/{assessment_id}", response_model=AssessmentDetail)
def assessment_detail(
    case_id: UUID, assessment_id: UUID, request: Request, user: User = Depends(assessment_reader)
):
    with errors(request):
        return service(request).detail(user.id, case_id, assessment_id)
