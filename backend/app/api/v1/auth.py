from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ServicesDep
from app.core.config import get_settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import AuthConfig, DevLoginRequest, TokenResponse
from app.schemas.document import UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfig)
async def auth_config(services: ServicesDep) -> AuthConfig:
    settings = get_settings()
    return AuthConfig(
        dev_auth=settings.dev_auth,
        oidc_enabled=settings.oidc_enabled,
        session_idle_minutes=settings.session_idle_minutes,
        llm_provider=services.llm.name if services.llm else "none",
        llm_model=services.llm.model_id if services.llm else None,
    )


@router.get("/dev-users", response_model=list[UserOut])
async def dev_users(session: DbSession) -> list[User]:
    if not get_settings().dev_auth:
        raise NotFoundError("Not available")
    rows = await session.execute(select(User).where(User.is_active.is_(True)).order_by(User.role, User.email))
    return list(rows.scalars())


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(body: DevLoginRequest, session: DbSession) -> TokenResponse:
    if not get_settings().dev_auth:
        raise NotFoundError("Not available")
    user = (await session.execute(select(User).where(User.email == body.email.lower().strip()))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("Unknown demo user")
    token, expires_in = create_access_token(user.id, user.role)
    await audit.record(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        payload={"method": "dev"},
    )
    await session.commit()
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(user: CurrentUser) -> TokenResponse:
    token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


# --- OIDC (production) -----------------------------------------------------------------------------

_oauth: Any = None


def _oidc_client() -> Any:
    global _oauth
    settings = get_settings()
    if not settings.oidc_enabled:
        raise NotFoundError("OIDC is not configured")
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth

        _oauth = OAuth()
        _oauth.register(
            "hospital",
            server_metadata_url=settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            client_kwargs={"scope": "openid email profile"},
        )
    return _oauth.hospital


@router.get("/oidc/login")
async def oidc_login(request: Request) -> Any:
    client = _oidc_client()
    redirect_uri = get_settings().api_base_url.rstrip("/") + "/api/v1/auth/oidc/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oidc/callback")
async def oidc_callback(request: Request, session: DbSession) -> RedirectResponse:
    client = _oidc_client()
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or {}
    email = str(claims.get("email", "")).lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("No active ProtoCite account for this identity")
    access, _ = create_access_token(user.id, user.role)
    await audit.record(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        payload={"method": "oidc"},
    )
    await session.commit()
    # Fragment (never sent to servers or written to access logs) carries the token to the SPA.
    return RedirectResponse(get_settings().web_base_url.rstrip("/") + f"/auth/callback#token={access}")
