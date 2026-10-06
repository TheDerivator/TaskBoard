"""API token shapes (D-097): a token as listed (never its secret), creating one, the new secret."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.access import TokenScope

# The choice offered when creating a token (None: it never expires).
MAX_TOKEN_DAYS = 3650


class ApiTokenOut(BaseModel):
    id: int
    name: str
    prefix: str  # how the token starts ("tb_x7Kq9w"), to recognize it
    scope: TokenScope
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    expired: bool


class ApiTokenCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    scope: TokenScope = TokenScope.READ
    expires_in_days: int | None = Field(default=90, ge=1, le=MAX_TOKEN_DAYS)


class ApiTokenCreated(BaseModel):
    token: ApiTokenOut
    secret: str  # shown once: only its hash is kept


class TokenInfo(BaseModel):
    """The token a request came with (in GET /api/auth/me)."""

    name: str
    scope: TokenScope
