"""Strict JWT-verified tenant context dependencies for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import AuthenticationError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Verified identity & tenant scope derived exclusively from a signed JWT."""

    user_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    role: str


async def get_current_tenant_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TenantContext:
    """Extract and verify TenantContext from Authorization: Bearer <jwt>.

    Never trusts client-supplied tenant_id headers or query parameters.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return TenantContext(
        user_id=payload.sub,
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        role=payload.role,
    )
