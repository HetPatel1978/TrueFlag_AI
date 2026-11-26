"""Protected workflow gateways; existing listing, assignment and history records are reused."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.evidence import errors as evidence_errors
from app.api.evidence import reader, slot
from app.models import User
from app.schemas.case_workflows import (
    ActivityPage,
    ActivityQuery,
    DirectoryPage,
    DirectoryQuery,
    QueueCase,
    QueuePage,
    QueueQuery,
)
from app.security.auth import require_case_manager
from app.services.case_workflows import CaseWorkflowService, WorkflowConflict, WorkflowForbidden
from app.services.upload_sessions import WorkspaceNotFound

router = APIRouter(prefix="/api/v1", tags=["Case workflows"])


@contextmanager
def errors():
    with evidence_errors():
        try:
            yield
        except WorkflowForbidden:
            raise HTTPException(403, "Case workflow access is not permitted") from None
        except WorkspaceNotFound:
            raise HTTPException(404, "Upload session not found") from None
        except WorkflowConflict:
            raise HTTPException(
                409, "Case changed or is closed; refresh before continuing"
            ) from None


@router.get("/case-queue", response_model=QueuePage)
def queue(request: Request, query: Annotated[QueueQuery, Query()], user: User = Depends(reader)):
    with slot(request), errors():
        return CaseWorkflowService(request.app.state.engine).queue(user.id, query)


@router.get("/cases/{case_id}/workflow", response_model=QueueCase)
def workflow(case_id: UUID, request: Request, user: User = Depends(reader)):
    with slot(request), errors():
        return CaseWorkflowService(request.app.state.engine).overview(user.id, case_id)


@router.get(
    "/cases/{case_id}/assignment-options",
    response_model=DirectoryPage,
    dependencies=[Depends(require_case_manager)],
)
def assignment_options(
    case_id: UUID,
    request: Request,
    query: Annotated[DirectoryQuery, Query()],
    user: User = Depends(reader),
):
    with slot(request), errors():
        return CaseWorkflowService(request.app.state.engine).directory(user.id, case_id, query)


@router.get("/cases/{case_id}/activity", response_model=ActivityPage)
def activity(
    case_id: UUID,
    request: Request,
    query: Annotated[ActivityQuery, Query()],
    user: User = Depends(reader),
):
    with slot(request), errors():
        return CaseWorkflowService(request.app.state.engine).activity(user.id, case_id, query)
