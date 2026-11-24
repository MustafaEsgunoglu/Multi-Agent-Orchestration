"""Workflow execution, live SSE streaming, HITL resume, and run history endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import ApiKey, ExecutionRun, RunStep, Workflow
from app.db.rls import get_tenant_db
from app.engine.compiler import compile_workflow
from app.engine.nodes import ExecutionRuntime
from app.schemas.execution import (
    ExecuteWorkflowRequest,
    ExecutionRunResponse,
    ResumeRunRequest,
    RunStepResponse,
)

router = APIRouter(tags=["executions"])

# Process-local checkpointer fallback for local dev/HITL testing.
# Production deployments inject AsyncPostgresSaver backed by PostgreSQL.
_DEFAULT_CHECKPOINTER = MemorySaver()


def _make_api_key_resolver(db: AsyncSession, ctx: TenantContext):
    async def resolve(api_key_id: UUID | None) -> str | None:
        if api_key_id is None:
            return None
        record = await db.scalar(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.tenant_id == ctx.tenant_id,
                ApiKey.workspace_id == ctx.workspace_id,
            )
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referenced API key '{api_key_id}' not found in workspace.",
            )
        return decrypt_secret(record.encrypted_key, aad=str(ctx.tenant_id))

    return resolve


async def _load_workflow(
    db: AsyncSession,
    ctx: TenantContext,
    workflow_id: UUID,
) -> Workflow:
    workflow = await db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.workspace_id == ctx.workspace_id,
        )
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return workflow


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post(
    "/workflows/{workflow_id}/execute",
    response_model=ExecutionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_workflow(
    workflow_id: UUID,
    payload: ExecuteWorkflowRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> ExecutionRunResponse:
    workflow = await _load_workflow(db, ctx, workflow_id)

    run = ExecutionRun(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        workflow_id=workflow.id,
        status="running",
        input_payload=payload.input,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()

    runtime = ExecutionRuntime(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        api_key_resolver=_make_api_key_resolver(db, ctx),
    )
    compiled = compile_workflow(
        workflow.definition,
        runtime,
        checkpointer=_DEFAULT_CHECKPOINTER,
    )

    try:
        result = await compiled.ainvoke(payload.input, thread_id=str(run.id))
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(UTC)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {exc}",
        ) from exc

    run.status = result.status
    run.output_payload = result.output
    run.total_tokens = result.total_tokens
    run.estimated_cost_usd = Decimal(str(result.total_cost_usd))
    if result.status == "completed":
        run.completed_at = datetime.now(UTC)

    persisted_steps: list[RunStep] = []
    for metric in result.step_metrics:
        step = RunStep(
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            run_id=run.id,
            node_id=str(metric.get("node_id", "unknown")),
            node_type=str(metric.get("node_type", "unknown")),
            status=str(metric.get("status", "completed")),
            prompt_tokens=int(metric.get("prompt_tokens", 0)),
            completion_tokens=int(metric.get("completion_tokens", 0)),
            estimated_cost_usd=Decimal(str(metric.get("estimated_cost_usd", 0.0))),
            latency_ms=metric.get("latency_ms"),
        )
        db.add(step)
        persisted_steps.append(step)

    await db.flush()
    response = ExecutionRunResponse.model_validate(run)
    response.interrupt_payload = result.interrupt_payload
    response.steps = [RunStepResponse.model_validate(s) for s in persisted_steps]
    return response


@router.post("/workflows/{workflow_id}/stream")
async def stream_workflow_execution(
    workflow_id: UUID,
    payload: ExecuteWorkflowRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> StreamingResponse:
    """Stream real-time node execution events via Server-Sent Events (SSE)."""
    workflow = await _load_workflow(db, ctx, workflow_id)

    run = ExecutionRun(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        workflow_id=workflow.id,
        status="running",
        input_payload=payload.input,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()

    runtime = ExecutionRuntime(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        api_key_resolver=_make_api_key_resolver(db, ctx),
    )
    compiled = compile_workflow(
        workflow.definition,
        runtime,
        checkpointer=_DEFAULT_CHECKPOINTER,
    )
    thread_id = str(run.id)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for evt in compiled.astream_events(payload.input, thread_id=thread_id):
            yield _format_sse(evt["event"], evt["data"])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/resume", response_model=ExecutionRunResponse)
async def resume_human_approval_run(
    run_id: UUID,
    payload: ResumeRunRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> ExecutionRunResponse:
    """Resume a workflow paused at a human_approval interrupt node."""
    run = await db.scalar(
        select(ExecutionRun).where(
            ExecutionRun.id == run_id,
            ExecutionRun.tenant_id == ctx.tenant_id,
            ExecutionRun.workspace_id == ctx.workspace_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution run not found.")
    if run.status != "waiting_for_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is in state '{run.status}' and cannot be resumed.",
        )

    workflow = await _load_workflow(db, ctx, run.workflow_id)
    runtime = ExecutionRuntime(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        api_key_resolver=_make_api_key_resolver(db, ctx),
    )
    compiled = compile_workflow(
        workflow.definition,
        runtime,
        checkpointer=_DEFAULT_CHECKPOINTER,
    )

    result = await compiled.aresume(
        {"action": payload.action, "edited_output": payload.edited_output},
        thread_id=str(run.id),
    )
    run.status = result.status
    run.output_payload = result.output
    run.total_tokens = result.total_tokens
    run.estimated_cost_usd = Decimal(str(result.total_cost_usd))
    if result.status == "completed":
        run.completed_at = datetime.now(UTC)

    await db.flush()
    response = ExecutionRunResponse.model_validate(run)
    response.interrupt_payload = result.interrupt_payload
    return response


@router.get("/runs", response_model=list[ExecutionRunResponse])
async def list_execution_runs(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[ExecutionRunResponse]:
    rows = await db.scalars(
        select(ExecutionRun)
        .where(
            ExecutionRun.tenant_id == ctx.tenant_id,
            ExecutionRun.workspace_id == ctx.workspace_id,
        )
        .order_by(ExecutionRun.created_at.desc())
        .limit(50)
    )
    return [ExecutionRunResponse.model_validate(r) for r in rows.all()]


@router.get("/runs/{run_id}", response_model=ExecutionRunResponse)
async def get_execution_run(
    run_id: UUID,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> ExecutionRunResponse:
    run = await db.scalar(
        select(ExecutionRun).where(
            ExecutionRun.id == run_id,
            ExecutionRun.tenant_id == ctx.tenant_id,
            ExecutionRun.workspace_id == ctx.workspace_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution run not found.")

    steps = await db.scalars(
        select(RunStep)
        .where(RunStep.run_id == run.id, RunStep.tenant_id == ctx.tenant_id)
        .order_by(RunStep.created_at.asc())
    )
    response = ExecutionRunResponse.model_validate(run)
    response.steps = [RunStepResponse.model_validate(s) for s in steps.all()]
    return response
