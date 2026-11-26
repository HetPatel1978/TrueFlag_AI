from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import AuditEvent, User
from app.security.auth import (
    authenticate_token,
    current_user,
    issue_token,
    password_hash,
    require_admin,
)
from app.security.browser_sessions import (
    COOKIE_SECONDS,
    PREFIX,
    cookie_grant,
    create_grant,
    enabled,
    revoke_grant,
    valid_grant,
)
from app.security.throttle import consume_login_attempt

router = APIRouter(prefix="/api/v1")
# Equal password-verification work for an unknown username; never an account credential.
dummy_hash = password_hash.hash("invalid-account-timing-reference")
SESSION_COOKIE = "trueflag_session"
SESSION_PATH = "/api/v1/auth/session"


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(min_length=1, max_length=1024)


def _login(body: LoginInput, request: Request, session: Session) -> dict:
    settings = request.app.state.settings
    client = request.client.host if request.client else "unknown"
    if not consume_login_attempt(session, client, settings):
        raise HTTPException(
            429,
            "Too many sign-in attempts",
            headers={"Retry-After": str(settings.login_window_seconds)},
        )
    user = session.scalar(select(User).where(User.username == body.username.lower()))
    valid = password_hash.verify(body.password, user.password_hash if user else dummy_hash)
    if user is None or not valid or not user.active:
        session.add(AuditEvent(action="auth.login_failed"))
        session.commit()
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    token = issue_token(user, settings)
    session.add(AuditEvent(actor_id=user.id, action="auth.login", resource_id=str(user.id)))
    session.commit()
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/token")
def login(body: LoginInput, request: Request, session: Session = Depends(get_session)) -> dict:
    # API clients retain the existing explicit bearer-only contract; no browser cookie.
    return _login(body, request, session)


def browser_origin(request):
    origin = request.headers.get("origin")
    allowed = {*request.app.state.settings.cors_origins, str(request.base_url).rstrip("/")}
    if (
        request.headers.get("sec-fetch-site") == "cross-site"
        or origin is not None
        and origin not in allowed
    ):
        raise HTTPException(403, "Browser session origin is not permitted")


def cookie_secure(request):
    return request.url.scheme == "https" or request.app.state.settings.app_env != "local"


def clear_cookie(response, request):
    response.delete_cookie(
        SESSION_COOKIE,
        path=SESSION_PATH,
        httponly=True,
        secure=cookie_secure(request),
        samesite="strict",
    )


def set_session_cookie(response, request, token, seconds):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        path=SESSION_PATH,
        max_age=seconds,
        expires=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        httponly=True,
        secure=cookie_secure(request),
        samesite="strict",
    )


@router.post("/auth/session")
def browser_login(
    body: LoginInput, request: Request, response: Response, session: Session = Depends(get_session)
):
    browser_origin(request)
    result = _login(body, request, session)
    settings = request.app.state.settings
    user = authenticate_token(result["access_token"], settings, session)
    previous = request.cookies.get(SESSION_COOKIE, "")
    if previous.startswith(PREFIX):
        old = cookie_grant(session, previous)
        if old is not None:
            revoke_grant(session, old)
    if enabled(user, settings):
        grant, cookie = create_grant(session, user, settings)
        result["access_token"] = issue_token(user, settings, browser_session_id=grant.id)
        session.commit()
        set_session_cookie(response, request, cookie, COOKIE_SECONDS)
    else:
        session.commit()
        set_session_cookie(
            response, request, result["access_token"], settings.access_token_minutes * 60
        )
    return result


@router.get("/auth/session")
def restore_browser_session(
    request: Request, response: Response, session: Session = Depends(get_session)
):
    browser_origin(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        if not token or len(token) > 4096:
            raise HTTPException(401, "Browser session unavailable")
        settings = request.app.state.settings
        remembered = token.startswith(PREFIX)
        if remembered:
            grant = cookie_grant(session, token)
            user = session.get(User, grant.actor_id) if grant is not None else None
            if user is None or not valid_grant(session, grant, user, settings):
                raise HTTPException(401, "Browser session unavailable")
            access_token = issue_token(user, settings, browser_session_id=grant.id)
        else:
            user = authenticate_token(token, settings, session)
            access_token = token
    except HTTPException:
        # Return the deletion header as well as the denial; no expired-token refresh.
        from fastapi.responses import JSONResponse

        denied = JSONResponse({"detail": "Browser session unavailable"}, status_code=401)
        clear_cookie(denied, request)
        return denied
    session.add(
        AuditEvent(actor_id=user.id, action="auth.session_restored", resource_id=str(user.id))
    )
    session.commit()
    if remembered:
        set_session_cookie(response, request, token, COOKIE_SECONDS)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": str(user.id), "username": user.username, "role": user.role},
    }


@router.post("/auth/session/logout")
def logout_browser_session(
    request: Request, response: Response, session: Session = Depends(get_session)
):
    browser_origin(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    if token.startswith(PREFIX):
        grant = cookie_grant(session, token)
        if grant is not None:
            revoke_grant(session, grant)
            session.commit()
    clear_cookie(response, request)
    return {"status": "signed_out"}


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
