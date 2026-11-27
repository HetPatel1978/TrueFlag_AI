from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import User
from app.schemas.alerts import AlertIngestionInput, AlertIngestionResponse
from app.security.auth import require_admin
from app.services.ingestion import IngestionConflict, ingest_alert

router = APIRouter(prefix="/api/v1/alerts", tags=["Alert ingestion"])


@router.post(
    "",
    response_model=AlertIngestionResponse,
    status_code=201,
    responses={
        200: {"description": "Original creation receipt returned"},
        401: {"description": "Missing, invalid or inactive credentials"},
        403: {"description": "Current database role does not permit ingestion"},
        409: {"description": "Key or source identifier conflicts"},
        503: {"description": "Database operation unavailable; retry using the same key"},
    },
    summary="Ingest one synthetic AML alert without scoring or routing",
)
def ingest(
    body: AlertIngestionInput,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"
        ),
    ],
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        receipt, created = ingest_alert(session, body, idempotency_key, user.id)
    except IngestionConflict as error:
        raise HTTPException(409, str(error)) from None
    response.status_code = 201 if created else 200
    return receipt
