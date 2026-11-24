"""PostgreSQL Row-Level Security (RLS) session context helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.base import get_session_factory

RLS_SETTING_NAME = "app.current_tenant_id"


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Bind the active PostgreSQL transaction to a single verified tenant_id.

    Uses transaction-local `set_config(..., is_local => true)` so pooled connections
    never leak tenant context across requests.
    """
    await session.execute(
        text("SELECT set_config(:setting, :tenant_id, true)"),
        {"setting": RLS_SETTING_NAME, "tenant_id": str(tenant_id)},
    )


def build_rls_enable_sql(table_name: str) -> tuple[str, str, str]:
    """Return SQL statements enabling and forcing strict tenant RLS on a table."""
    policy_name = f"{table_name}_tenant_isolation_policy"
    predicate = (
        f"tenant_id = NULLIF(current_setting('{RLS_SETTING_NAME}', true), '')::uuid"
    )
    return (
        f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY;',
        f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY;',
        (
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f"USING ({predicate}) WITH CHECK ({predicate});"
        ),
    )


async def get_tenant_db(
    ctx: TenantContext = Depends(get_current_tenant_context),
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession locked to the JWT's tenant_id via RLS."""
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, ctx.tenant_id)
        yield session


async def get_unscoped_db() -> AsyncGenerator[AsyncSession, None]:
    """Unscoped DB session reserved strictly for authentication (register/login)."""
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        yield session
