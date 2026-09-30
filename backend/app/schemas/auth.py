from __future__ import annotations

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.document import UserOut


class AuthConfig(APIModel):
    dev_auth: bool
    oidc_enabled: bool
    session_idle_minutes: int
    llm_provider: str
    llm_model: str | None
    demo_corpus: bool = True


class DevLoginRequest(APIModel):
    email: str = Field(max_length=320)


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (OAuth token type, not a secret)
    expires_in: int
    user: UserOut
