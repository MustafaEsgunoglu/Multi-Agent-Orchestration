"""MCP server registry (AES-256-GCM encrypted auth headers) & OpenAPI tool preview."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import McpServer
from app.db.rls import get_tenant_db
from app.engine.mcp_client import parse_openapi_spec

router = APIRouter(prefix="/integrations", tags=["integrations"])


class McpServerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transport: Literal["sse", "stdio"] = "sse"
    endpoint_or_command: str = Field(min_length=1, max_length=1000)
    auth_headers: dict[str, str] | None = None


class McpServerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    transport: str
    endpoint_or_command: str
    has_auth_headers: bool = False
    is_active: bool
    created_at: datetime


class OpenApiImportRequest(BaseModel):
    spec: dict[str, Any]
    base_url: str | None = None


@router.post(
    "/mcp-servers",
    response_model=McpServerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_mcp_server(
    payload: McpServerCreateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> McpServerResponse:
    encrypted_headers = (
        encrypt_secret(json.dumps(payload.auth_headers), aad=str(ctx.tenant_id))
        if payload.auth_headers
        else None
    )
    server = McpServer(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        name=payload.name,
        transport=payload.transport,
        endpoint_or_command=payload.endpoint_or_command,
        encrypted_auth_headers=encrypted_headers,
    )
    db.add(server)
    await db.flush()
    resp = McpServerResponse.model_validate(server)
    resp.has_auth_headers = server.encrypted_auth_headers is not None
    return resp


@router.get("/mcp-servers", response_model=list[McpServerResponse])
async def list_mcp_servers(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[McpServerResponse]:
    rows = await db.scalars(
        select(McpServer)
        .where(McpServer.tenant_id == ctx.tenant_id, McpServer.workspace_id == ctx.workspace_id)
        .order_by(McpServer.created_at.desc())
    )
    results: list[McpServerResponse] = []
    for s in rows.all():
        item = McpServerResponse.model_validate(s)
        item.has_auth_headers = s.encrypted_auth_headers is not None
        results.append(item)
    return results


@router.delete("/mcp-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: UUID,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    server = await db.scalar(
        select(McpServer).where(
            McpServer.id == server_id,
            McpServer.tenant_id == ctx.tenant_id,
            McpServer.workspace_id == ctx.workspace_id,
        )
    )
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found.")
    await db.delete(server)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/openapi/preview-tools")
async def preview_openapi_tools(payload: OpenApiImportRequest) -> dict[str, Any]:
    """Statelessly convert an OpenAPI/Swagger spec into DynamicToolSpec definitions."""
    tools = parse_openapi_spec(payload.spec, base_url=payload.base_url)
    return {
        "tool_count": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters_schema": t.parameters_schema,
                "metadata": t.metadata,
            }
            for t in tools
        ],
    }
