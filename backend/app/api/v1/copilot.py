"""Prompt-to-Workflow AI Copilot endpoint."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import ApiKey
from app.db.rls import get_tenant_db
from app.engine.copilot import CopilotGenerationError, generate_workflow_from_prompt
from app.schemas.workflow import WorkflowDefinition

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotGenerateRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=4000)
    provider: Literal["openai", "anthropic", "google", "groq", "mistral", "openrouter", "custom"] = "openai"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120)
    api_key_id: UUID | None = None
    existing_workflow: WorkflowDefinition | None = None


class CopilotGenerateResponse(BaseModel):
    workflow: WorkflowDefinition
    explanation: str
    attempts: int
    total_tokens: int
    estimated_cost_usd: float


@router.post("/generate", response_model=CopilotGenerateResponse)
async def generate_workflow(
    payload: CopilotGenerateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> CopilotGenerateResponse:
    api_key_plain: str | None = None
    if payload.api_key_id is not None:
        key_rec = await db.scalar(
            select(ApiKey).where(
                ApiKey.id == payload.api_key_id,
                ApiKey.tenant_id == ctx.tenant_id,
                ApiKey.workspace_id == ctx.workspace_id,
            )
        )
        if key_rec is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
        api_key_plain = decrypt_secret(key_rec.encrypted_key, aad=str(ctx.tenant_id))

    try:
        result = await generate_workflow_from_prompt(
            payload.prompt,
            provider=payload.provider,
            model=payload.model,
            api_key=api_key_plain,
            existing_workflow=payload.existing_workflow,
        )
    except CopilotGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return CopilotGenerateResponse(
        workflow=result.workflow,
        explanation=result.explanation,
        attempts=result.attempts,
        total_tokens=result.total_tokens,
        estimated_cost_usd=result.estimated_cost_usd,
    )
