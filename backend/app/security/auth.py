from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_session
from app.models import AuditEvent, User
from app.security.browser_sessions import valid_grant

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def issue_token(user: User, settings: Settings, *, browser_session_id: UUID | None = None) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            **({"sid": str(browser_session_id)} if browser_session_id is not None else {}),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authenticate_token(credentials.credentials, request.app.state.settings, session)


def authenticate_token(token: str, settings: Settings, session: Session) -> User:
    """Same JWT/active-account checks for explicit bearer and browser restoration."""
    denied = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        user_id = UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise denied from None
    user = session.get(User, user_id)
    if user is None or not user.active:
        raise denied
    if "sid" in claims:
        try:
            grant_id = UUID(claims["sid"])
        except (ValueError, TypeError, AttributeError):
            raise denied from None
        if not valid_grant(session, session.get(AuditEvent, grant_id), user, settings):
            raise denied
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator permission required")
    return user


def require_case_reader(user: User = Depends(current_user)) -> User:
    if user.role not in {"analyst", "supervisor", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Case access is not permitted")
    return user


def require_case_manager(user: User = Depends(current_user)) -> User:
    if user.role not in {"supervisor", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Case assignment permission required")
    return user
