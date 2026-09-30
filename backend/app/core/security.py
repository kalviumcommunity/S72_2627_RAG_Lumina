"""Tokens and role checks.

Sessions are short-lived JWTs (SESSION_IDLE_MINUTES, default 15 for shared terminals). The web app
refreshes the token while the user is active, so an idle shared terminal locks itself.
DEV_AUTH=true issues tokens for seeded demo users; production uses OIDC (see api/v1/auth.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.models.enums import ROLE_RANK, Role

ALGORITHM = "HS256"
ISSUER = "protocite"


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: Role
    expires_at: datetime


def create_access_token(user_id: uuid.UUID, role: Role, *, minutes: int | None = None) -> tuple[str, int]:
    settings = get_settings()
    ttl = minutes or settings.session_idle_minutes
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), ttl * 60


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=Role(payload["role"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Session expired — please sign in again", code="session_expired") from exc
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid session token") from exc


def has_role(actual: Role, minimum: Role) -> bool:
    return ROLE_RANK[actual] >= ROLE_RANK[minimum]
