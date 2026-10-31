from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import AuditEvent, User
from app.security.auth import current_user, issue_token, password_hash, require_admin

router = APIRouter(prefix="/api/v1")
# Equal password-verification work for an unknown username; never an account credential.
dummy_hash = password_hash.hash("invalid-account-timing-reference")


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(min_length=1, max_length=1024)


@router.post("/auth/token")
def login(body: LoginInput, request: Request, session: Session = Depends(get_session)) -> dict:
    user = session.scalar(select(User).where(User.username == body.username.lower()))
    valid = password_hash.verify(body.password, user.password_hash if user else dummy_hash)
    if user is None or not valid or not user.active:
        session.add(AuditEvent(action="auth.login_failed"))
        session.commit()
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    token = issue_token(user, request.app.state.settings)
    session.add(AuditEvent(actor_id=user.id, action="auth.login", resource_id=str(user.id)))
    session.commit()
    return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": str(user.id), "username": user.username, "role": user.role}


@router.get("/admin/audit-events")
def audit_events(
    user: User = Depends(require_admin), session: Session = Depends(get_session)
) -> dict:
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100))
    return {
        "items": [
            {
                "id": str(row.id),
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "action": row.action,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
