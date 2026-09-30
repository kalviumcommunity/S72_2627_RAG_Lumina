"""FastAPI dependencies: DB session, current user, role guards, rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import decode_access_token, has_role
from app.db.session import get_sessionmaker
from app.models.enums import Role
from app.models.user import User
from app.services.registry import Services, get_services

log = get_logger(__name__)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def services_dep() -> Services:
    return get_services()


ServicesDep = Annotated[Services, Depends(services_dep)]


async def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise UnauthorizedError("Sign in required")
    claims = decode_access_token(token)
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is not active")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def guard(user: CurrentUser) -> User:
        if not has_role(user.role, minimum):
            raise ForbiddenError(f"Requires the {minimum.value} role or higher")
        return user

    return guard


AuthorUser = Annotated[User, Depends(require_role(Role.author))]
ApproverUser = Annotated[User, Depends(require_role(Role.approver))]
AdminUser = Annotated[User, Depends(require_role(Role.admin))]


class RateLimiter:
    """Fixed per-minute budget per user. Uses Redis when reachable, else an in-process window."""

    def __init__(self) -> None:
        self._local: dict[str, deque[float]] = defaultdict(deque)
        self._redis: Any = None
        self._redis_checked = False

    async def _get_redis(self) -> Any:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            import redis.asyncio as redis

            client = redis.from_url(  # type: ignore[no-untyped-call]
                get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            await client.ping()
            self._redis = client
        except Exception:
            self._redis = None
        return self._redis

    async def hit(self, key: str, limit: int) -> None:
        if limit <= 0:
            return
        client = await self._get_redis()
        if client is not None:
            try:
                bucket = f"protocite:rl:{key}:{int(time.time() // 60)}"
                count = await client.incr(bucket)
                if count == 1:
                    await client.expire(bucket, 70)
                if count > limit:
                    raise RateLimitedError("Too many questions in a minute — please wait a moment")
                return
            except RateLimitedError:
                raise
            except Exception as exc:  # Redis hiccup: fall through to the local window
                log.debug("rate_limit_redis_unavailable", error_type=type(exc).__name__)
        now = time.monotonic()
        window = self._local[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            raise RateLimitedError("Too many questions in a minute — please wait a moment")
        window.append(now)

    def reset(self) -> None:
        self._local.clear()


rate_limiter = RateLimiter()


async def query_rate_limit(user: CurrentUser) -> User:
    await rate_limiter.hit(f"query:{user.id}", get_settings().query_rate_limit_per_minute)
    return user


RateLimitedUser = Annotated[User, Depends(query_rate_limit)]


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ForbiddenError(message)
