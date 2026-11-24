"""Authentication endpoints: register (creates Tenant + Workspace + Owner), login, and me."""

from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import Tenant, User, Workspace
from app.db.rls import get_tenant_db, get_unscoped_db, set_tenant_context
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserMeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base[:48]}-{uuid4().hex[:8]}"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_unscoped_db),
) -> TokenResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    tenant = Tenant(name=payload.organization_name, slug=_slugify(payload.organization_name))
    db.add(tenant)
    await db.flush()

    # Bind PostgreSQL RLS context before inserting into RLS-protected tables (workspaces)
    await set_tenant_context(db, tenant.id)

    workspace = Workspace(tenant_id=tenant.id, name="Default Workspace")
    db.add(workspace)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    await db.flush()

    token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        role=user.role,
    )
    return TokenResponse(
        access_token=token,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_unscoped_db),
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
        role=user.role,
    )
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> UserMeResponse:
    user = await db.scalar(
        select(User).where(User.id == ctx.user_id, User.tenant_id == ctx.tenant_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserMeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        role=ctx.role,
    )
