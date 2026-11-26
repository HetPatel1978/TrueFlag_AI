"""Local-only remembered login, backed by immutable audit grants and revocations.

No migration or immortal bearer token: only a credential-bound, revocable browser
grant for the explicitly configured local account. Enterprise session management
must use a dedicated session store before expanding this development-only mode.
"""

import hashlib
import hmac
import re
import secrets
from uuid import UUID, uuid4

from sqlalchemy import select

from app.models import AuditEvent

PREFIX = "remembered.v1."
COOKIE_SECONDS = 365 * 24 * 60 * 60
CREATED = "auth.remembered_session.created"
REVOKED = "auth.remembered_session.revoked"
COOKIE = re.compile(r"remembered\.v1\.([a-f0-9]{32})\.([A-Za-z0-9_-]{64})\Z")


def enabled(user, settings):
    return (
        settings.app_env == "local"
        and bool(settings.local_persistent_login_username)
        and user.active
        and user.username == settings.local_persistent_login_username
    )


def stamp(user, settings):
    # Password/role/signing-key changes invalidate the grant without storing a password hash twice.
    material = "\0".join(
        ["trueflag.local-browser.v1", str(user.id), user.role, user.password_hash]
    ).encode()
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), material, hashlib.sha256
    ).hexdigest()


def valid_grant(session, grant, user, settings):
    if (
        grant is None
        or grant.action != CREATED
        or grant.actor_id != user.id
        or not enabled(user, settings)
        or not isinstance(grant.details, dict)
        or not isinstance(grant.details.get("credential_stamp"), str)
        or not hmac.compare_digest(grant.details.get("credential_stamp", ""), stamp(user, settings))
    ):
        return False
    return (
        session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.action == REVOKED,
                AuditEvent.resource_id == str(grant.id),
                AuditEvent.actor_id == user.id,
            )
            .limit(1)
        )
        is None
    )


def create_grant(session, user, settings):
    ident = uuid4()
    cookie = PREFIX + ident.hex + "." + secrets.token_urlsafe(48)
    grant = AuditEvent(
        id=ident,
        actor_id=user.id,
        action=CREATED,
        resource_id=str(user.id),
        details={
            "token_sha256": hashlib.sha256(cookie.encode()).hexdigest(),
            "credential_stamp": stamp(user, settings),
            "scope": "local_account_only",
        },
    )
    session.add(grant)
    session.flush()
    return grant, cookie


def cookie_grant(session, cookie):
    match = COOKIE.fullmatch(cookie)
    if match is None:
        return None
    grant = session.scalar(
        select(AuditEvent).where(AuditEvent.id == UUID(match[1])).with_for_update()
    )
    if (
        grant is None
        or grant.action != CREATED
        or not isinstance(grant.details, dict)
        or not isinstance(grant.details.get("token_sha256"), str)
        or not hmac.compare_digest(
            grant.details.get("token_sha256", ""), hashlib.sha256(cookie.encode()).hexdigest()
        )
    ):
        return None
    return grant


def revoke_grant(session, grant):
    if (
        session.scalar(
            select(AuditEvent.id)
            .where(AuditEvent.action == REVOKED, AuditEvent.resource_id == str(grant.id))
            .limit(1)
        )
        is None
    ):
        session.add(AuditEvent(actor_id=grant.actor_id, action=REVOKED, resource_id=str(grant.id)))
