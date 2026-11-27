"""Owner-scoped explicit import approval, progress and redacted row receipts."""

import json
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.csv_uploads import errors as staging_errors
from app.api.csv_uploads import require_batch_uploader, unique_object, validation_slot
from app.models import User
from app.schemas.csv_imports import ImportApproval, ImportRowsPage, ImportSummary
from app.services.csv_imports import (
    CSVImportService,
    ImportCapacity,
    ImportConflict,
    ImportInvalid,
    ImportUnavailable,
)

router = APIRouter(tags=["CSV imports"])


@contextmanager
def errors():
    with staging_errors():
        try:
            yield
        except ImportConflict:
            raise HTTPException(
                409, "Approval identity conflicts with its preview or existing import"
            ) from None
        except ImportInvalid:
            raise HTTPException(
                422, "A completed preview with valid rows and explicit approval is required"
            ) from None
        except ImportCapacity:
            raise HTTPException(
                429, "Import queue capacity reached", headers={"Retry-After": "60"}
            ) from None
        except ImportUnavailable:
            raise HTTPException(
                503, "Import service unavailable; retry with the same key"
            ) from None


@router.post(
    "/api/v1/batch-uploads/{upload_id}/validations/{validation_id}/imports",
    response_model=ImportSummary,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ImportApproval.model_json_schema()}},
        }
    },
)
async def approve_csv_import(
    upload_id: UUID,
    validation_id: UUID,
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
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Approval requires application/json")
    try:
        body = ImportApproval.model_validate(
            json.loads(await request.body(), object_pairs_hook=unique_object)
        )
    except (ValueError, ValidationError, RecursionError):
        raise HTTPException(422, "Invalid import approval request") from None
    with validation_slot(request), errors():
        service = CSVImportService(request.app.state.engine, request.app.state.settings)
        result = await run_in_threadpool(
            service.approve, user.id, upload_id, validation_id, body, idempotency_key
        )
    response.headers["Location"] = "/api/v1/batch-imports/" + str(result.import_id)
    return result


@router.get("/api/v1/batch-imports/{import_id}", response_model=ImportSummary)
def csv_import_status(
    import_id: UUID, request: Request, user: User = Depends(require_batch_uploader)
):
    with errors():
        return CSVImportService(request.app.state.engine, request.app.state.settings).get(
            user.id, import_id
        )


@router.get("/api/v1/batch-imports/{import_id}/rows", response_model=ImportRowsPage)
def csv_import_rows(
    import_id: UUID,
    request: Request,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Literal["created", "reused", "invalid", "conflict"] | None = None,
    user: User = Depends(require_batch_uploader),
):
    with errors():
        return CSVImportService(request.app.state.engine, request.app.state.settings).get(
            user.id, import_id, offset=offset, limit=limit, status=status
        )
