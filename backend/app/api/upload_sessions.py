"""Protected, versioned upload workspace selection and bounded resume receipts."""

from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.models import User
from app.security.auth import require_case_reader
from app.services.upload_sessions import (
    UploadSessionService,
    WorkspaceConflict,
    WorkspaceDenied,
    WorkspaceNotFound,
)

router = APIRouter(prefix="/api/v1/upload-sessions", tags=["Upload workspaces"])


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=1, le=2147483647)


@contextmanager
def errors():
    try:
        yield
    except WorkspaceNotFound:
        raise HTTPException(404, "Upload session not found") from None
    except WorkspaceDenied:
        raise HTTPException(403, "Upload session permission required") from None
    except WorkspaceConflict:
        raise HTTPException(409, "Upload session changed; reload before continuing") from None


@router.get("")
def workspace(
    request: Request,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    user: User = Depends(require_case_reader),
):
    with errors():
        return UploadSessionService(request.app.state.engine).execute(
            user.id, offset=offset, limit=limit
        )


@router.post("", status_code=201)
def new_session(
    request: Request,
    body: Selection,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"
        ),
    ],
    user: User = Depends(require_case_reader),
):
    with errors():
        return UploadSessionService(request.app.state.engine).execute(
            user.id, action="create", key=idempotency_key, version=body.version
        )


@router.put("/{session_id}/selection")
def select_session(
    session_id: UUID, request: Request, body: Selection, user: User = Depends(require_case_reader)
):
    with errors():
        return UploadSessionService(request.app.state.engine).execute(
            user.id, action="select", session_id=session_id, version=body.version
        )


@router.get("/lookup/{kind}/{reference_id}")
def lookup(
    kind: Literal["upload", "import"],
    reference_id: UUID,
    request: Request,
    user: User = Depends(require_case_reader),
):
    with errors():
        return UploadSessionService(request.app.state.engine).lookup(user.id, kind, reference_id)
