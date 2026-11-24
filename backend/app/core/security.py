"""Password hashing (bcrypt) and JWT token issuance/verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

from app.core.config import get_settings


class AuthenticationError(ValueError):
    """Raised when JWT decoding or validation fails."""


class TokenPayload(BaseModel):
    sub: UUID
    tenant_id: UUID
    workspace_id: UUID
    role: str
    iat: datetime
    exp: datetime


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification of a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    role: str = "owner",
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed JWT embedding verified tenant_id and workspace_id claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Verify JWT signature/expiration and return typed claims."""
    settings = get_settings()
    try:
        decoded = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tenant_id", "workspace_id", "role", "exp", "iat"]},
        )
        return TokenPayload.model_validate(decoded)
    except (InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired authentication token.") from exc
