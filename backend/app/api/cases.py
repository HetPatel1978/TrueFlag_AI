from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import User
from app.schemas.cases import (
    AssignmentInput,
    CaseDetail,
    CasePage,
    CaseQuery,
    CaseSummary,
    WorkbenchCase,
)
from app.security.auth import require_case_manager, require_case_reader
from app.services.cases import (
    AssignmentConflict,
    AssignmentPermissionDenied,
    CaseNotFound,
    InvalidAssignee,
    assign_case,
    get_case,
    get_overview,
    list_cases,
)

router = APIRouter(prefix="/api/v1/cases", tags=["Case access"])


@router.get("", response_model=CasePage)
def case_list(
    query: Annotated[CaseQuery, Query()],
    user: User = Depends(require_case_reader),
    session: Session = Depends(get_session),
):
    return list_cases(session, user, query)


@router.get("/{case_id}", response_model=CaseDetail)
def case_detail(
    case_id: UUID,
    user: User = Depends(require_case_reader),
    session: Session = Depends(get_session),
):
    try:
        return get_case(session, user, case_id)
    except CaseNotFound:
        raise HTTPException(404, "Case not found") from None


@router.get("/{case_id}/overview", response_model=WorkbenchCase)
def case_overview(
    case_id: UUID,
    user: User = Depends(require_case_reader),
    session: Session = Depends(get_session),
):
    try:
        return get_overview(session, user, case_id)
    except CaseNotFound:
        raise HTTPException(404, "Case not found") from None


@router.put("/{case_id}/assignment", response_model=CaseSummary)
def case_assignment(
    case_id: UUID,
    body: AssignmentInput,
    user: User = Depends(require_case_manager),
    session: Session = Depends(get_session),
):
    try:
        return assign_case(session, user.id, case_id, body)
    except CaseNotFound:
        raise HTTPException(404, "Case not found") from None
    except AssignmentConflict:
        raise HTTPException(409, "Case changed or is closed; reload before assigning") from None
    except InvalidAssignee:
        raise HTTPException(422, "Assignee must be an active analyst") from None
    except AssignmentPermissionDenied:
        raise HTTPException(403, "Case assignment permission required") from None
