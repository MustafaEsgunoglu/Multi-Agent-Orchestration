"""BYOK LLM API Key management with AES-256-GCM encryption at rest."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret, mask_secret
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import ApiKey
from app.db.rls import get_tenant_db
from app.schemas.api_key import ApiKeyCreateRequest, ApiKeyResponse

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> ApiKeyResponse:
    # Bind ciphertext to tenant_id via AES-256-GCM AAD
    encrypted = encrypt_secret(payload.api_key, aad=str(ctx.tenant_id))
    record = ApiKey(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        name=payload.name,
        provider=payload.provider,
        encrypted_key=encrypted,
        key_hint=mask_secret(payload.api_key),
    )
    db.add(record)
    await db.flush()
    return ApiKeyResponse.model_validate(record)


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[ApiKeyResponse]:
    result = await db.scalars(
        select(ApiKey)
        .where(ApiKey.tenant_id == ctx.tenant_id, ApiKey.workspace_id == ctx.workspace_id)
        .order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyResponse.model_validate(item) for item in result.all()]


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    api_key_id: UUID,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    record = await db.scalar(
        select(ApiKey).where(
            ApiKey.id == api_key_id,
            ApiKey.tenant_id == ctx.tenant_id,
            ApiKey.workspace_id == ctx.workspace_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    await db.delete(record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
