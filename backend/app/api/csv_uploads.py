"""Admin-only raw UTF-8 CSV staging; no multipart dependency or public file download."""

import asyncio
import json
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.models import User
from app.schemas.csv_uploads import UploadMetadata, csv_contract, csv_template
from app.schemas.csv_validation import MappingInput, ValidationPage, ValidationSummary
from app.security.auth import require_admin
from app.services.csv_staging import (
    CSVStagingService,
    InvalidCSV,
    StagingUnavailable,
    UploadCapacity,
    UploadConflict,
    UploadDenied,
    UploadExpired,
    UploadLimit,
    UploadNotFound,
)
from app.services.csv_validation import CSVValidationService, InvalidMapping

router = APIRouter(prefix="/api/v1/batch-uploads", tags=["CSV staging"])


def require_batch_uploader(user: User = Depends(require_admin)):
    # Dedicated permission boundary. No importer role exists; initial grant is admin only.
    return user


@contextmanager
def upload_slot(request):
    slots = request.app.state.csv_upload_slots
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "CSV upload capacity is busy", headers={"Retry-After": "5"})
    try:
        yield
    finally:
        slots.release()


@contextmanager
def errors():
    try:
        yield
    except UploadLimit:
        raise HTTPException(413, "CSV exceeds a configured staging limit") from None
    except InvalidCSV:
        raise HTTPException(
            422, "CSV encoding, syntax, header or data presence is invalid"
        ) from None
    except InvalidMapping:
        raise HTTPException(
            422,
            "Mapping must uniquely cover all required fields using existing exact column names and baseline source units",
        ) from None
    except UploadConflict:
        raise HTTPException(409, "Upload key was used for different content") from None
    except UploadNotFound:
        raise HTTPException(404, "Upload not found") from None
    except UploadDenied:
        raise HTTPException(403, "Batch upload permission required") from None
    except UploadExpired:
        raise HTTPException(410, "Upload expired; use a new upload key") from None
    except UploadCapacity:
        raise HTTPException(
            429, "Active upload capacity reached", headers={"Retry-After": "60"}
        ) from None
    except StagingUnavailable:
        raise HTTPException(503, "CSV staging unavailable; retry using the same key") from None


@router.get("/template")
def csv_upload_template(user: User = Depends(require_batch_uploader)):
    return Response(
        csv_template(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trueflag-alerts-v1.csv"'},
    )


@router.get("/contract")
def csv_upload_contract(user: User = Depends(require_batch_uploader)):
    return csv_contract()


@router.post("", response_model=UploadMetadata, status_code=201)
async def csv_upload(
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"
        ),
    ],
    user: User = Depends(require_batch_uploader),
):
    # No filename/path parameter; names and storage keys are exclusively server-generated.
    media = request.headers.get("content-type", "").lower().replace(" ", "")
    if media not in {"text/csv", "text/csv;charset=utf-8", 'text/csv;charset="utf-8"'}:
        raise HTTPException(415, "Only UTF-8 text/csv is supported")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(415, "Compressed uploads are not supported")
    if (
        request.url.query
        or request.headers.get("content-disposition")
        or request.headers.get("x-upload-filename")
    ):
        raise HTTPException(422, "Filename and path parameters are not accepted")
    incoming = None
    with upload_slot(request), errors():
        service = CSVStagingService(request.app.state.engine, request.app.state.settings)
        try:
            incoming = await run_in_threadpool(service.begin)
            async with asyncio.timeout(60):
                async for chunk in request.stream():
                    await run_in_threadpool(incoming.append, chunk)
            result, created = await run_in_threadpool(
                service.publish, user.id, idempotency_key, incoming
            )
        except (TimeoutError, ClientDisconnect):
            raise HTTPException(408, "CSV upload interrupted or timed out") from None
        except OSError:
            raise HTTPException(503, "CSV staging unavailable; retry using the same key") from None
        finally:
            if incoming:
                await run_in_threadpool(incoming.close)
    response.status_code = 201 if created else 200
    response.headers["Location"] = "/api/v1/batch-uploads/" + str(result.upload_id)
    return result


@router.get("/{upload_id}", response_model=UploadMetadata)
def csv_upload_metadata(
    upload_id: UUID, request: Request, user: User = Depends(require_batch_uploader)
):
    with errors():
        return CSVStagingService(request.app.state.engine, request.app.state.settings).metadata(
            user.id, upload_id
        )


@contextmanager
def validation_slot(request):
    slots = request.app.state.csv_validation_slots
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "CSV validation capacity is busy", headers={"Retry-After": "5"})
    try:
        yield
    finally:
        slots.release()


def validation_service(request):
    return CSVValidationService(request.app.state.engine, request.app.state.settings)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError
        result[name] = value
    return result


@router.get("/{upload_id}/columns")
def csv_upload_columns(
    upload_id: UUID, request: Request, user: User = Depends(require_batch_uploader)
):
    with validation_slot(request), errors():
        return validation_service(request).columns(user.id, upload_id)


@router.post(
    "/{upload_id}/validations",
    response_model=ValidationSummary,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": MappingInput.model_json_schema()}},
        }
    },
)
async def csv_validate(
    upload_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(require_batch_uploader),
):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Mapping requires application/json")
    # Parse strictly to reject duplicate JSON keys and suppress untrusted mapping-key locations.
    try:
        body = json.loads(await request.body(), object_pairs_hook=unique_object)
        mapping = MappingInput.model_validate(body)
    except (ValueError, ValidationError, RecursionError):
        raise HTTPException(422, "Invalid mapping request or units declaration") from None
    with validation_slot(request), errors():
        result, created = await run_in_threadpool(
            validation_service(request).validate, user.id, upload_id, mapping
        )
    response.status_code = 201 if created else 200
    response.headers["Location"] = (
        f"/api/v1/batch-uploads/{upload_id}/validations/{result.validation_id}"
    )
    return result


@router.get("/{upload_id}/validations/{validation_id}", response_model=ValidationSummary)
def csv_validation_summary(
    upload_id: UUID,
    validation_id: UUID,
    request: Request,
    user: User = Depends(require_batch_uploader),
):
    with validation_slot(request), errors():
        return validation_service(request).retrieve(user.id, upload_id, validation_id)


@router.get("/{upload_id}/validations/{validation_id}/errors", response_model=ValidationPage)
def csv_validation_errors(
    upload_id: UUID,
    validation_id: UUID,
    request: Request,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    severity: Literal["all", "error", "warning"] = "all",
    user: User = Depends(require_batch_uploader),
):
    with validation_slot(request), errors():
        return validation_service(request).retrieve(
            user.id, upload_id, validation_id, offset=offset, limit=limit, severity=severity
        )
