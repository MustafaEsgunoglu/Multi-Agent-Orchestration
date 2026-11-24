"""Workflow CRUD and canonical WorkflowDefinition schema validation endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import Workflow
from app.db.rls import get_tenant_db
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowDefinition,
    WorkflowResponse,
    WorkflowUpdateRequest,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/schema", response_model=dict[str, Any])
async def get_workflow_json_schema() -> dict[str, Any]:
    """Export the canonical JSON Schema for frontend Zod & Copilot alignment."""
    return WorkflowDefinition.model_json_schema()


@router.post("/validate")
async def validate_workflow_definition(definition: WorkflowDefinition) -> dict[str, Any]:
    """Statelessly validate a WorkflowDefinition graph against canonical rules."""
    return {
        "valid": True,
        "schema_version": definition.schema_version,
        "node_count": len(definition.nodes),
        "edge_count": len(definition.edges),
        "recursion_limit": definition.execution_config.recursion_limit,
    }


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> WorkflowResponse:
    workflow = Workflow(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        name=payload.name,
        description=payload.description,
        definition=payload.definition.model_dump(mode="json"),
        version=1,
    )
    db.add(workflow)
    await db.flush()
    return WorkflowResponse.model_validate(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[WorkflowResponse]:
    result = await db.scalars(
        select(Workflow)
        .where(Workflow.tenant_id == ctx.tenant_id, Workflow.workspace_id == ctx.workspace_id)
        .order_by(Workflow.updated_at.desc())
    )
    return [WorkflowResponse.model_validate(wf) for wf in result.all()]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> WorkflowResponse:
    workflow = await db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.workspace_id == ctx.workspace_id,
        )
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return WorkflowResponse.model_validate(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> WorkflowResponse:
    workflow = await db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.workspace_id == ctx.workspace_id,
        )
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")

    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if payload.is_active is not None:
        workflow.is_active = payload.is_active
    if payload.definition is not None:
        workflow.definition = payload.definition.model_dump(mode="json")
        workflow.version += 1

    await db.flush()
    return WorkflowResponse.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    workflow = await db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.workspace_id == ctx.workspace_id,
        )
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    await db.delete(workflow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
