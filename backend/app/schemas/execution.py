"""Request and response schemas for workflow execution, HITL resume, and run history."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecuteWorkflowRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class ResumeRunRequest(BaseModel):
    action: Literal["approve", "reject", "edit"] = "approve"
    edited_output: str | None = None


class RunStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    status: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: Decimal
    latency_ms: int | None
    created_at: datetime


class ExecutionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    workflow_id: UUID
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    total_tokens: int
    estimated_cost_usd: Decimal
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    interrupt_payload: dict[str, Any] | None = None
    steps: list[RunStepResponse] = Field(default_factory=list)
