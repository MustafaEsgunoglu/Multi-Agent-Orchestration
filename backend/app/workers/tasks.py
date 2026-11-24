"""Background Celery tasks for async RAG document ingestion and long-running workflows."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.crypto import decrypt_secret
from app.db.base import get_session_factory
from app.db.models import ApiKey, DocumentChunk, ExecutionRun, KnowledgeDocument, RunStep, Workflow
from app.db.rls import set_tenant_context
from app.engine.compiler import compile_workflow
from app.engine.nodes import ExecutionRuntime
from app.rag.chunker import chunk_text
from app.rag.parser import parse_document_bytes
from app.rag.retriever import LiteLLMEmbeddingClient
from app.workers.celery_app import celery_app


async def _ingest_document_async(
    *,
    document_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    raw_bytes: bytes,
    filename: str,
    content_type: str,
    api_key_id: UUID | None = None,
    embedding_model: str = "text-embedding-3-small",
) -> dict[str, Any]:
    parsed = parse_document_bytes(raw_bytes, filename=filename, content_type=content_type)
    chunks = chunk_text(parsed.text)

    session_factory = get_session_factory()
    async with session_factory() as db, db.begin():
        await set_tenant_context(db, tenant_id)

        api_key_plain: str | None = None
        if api_key_id is not None:
            key_record = await db.scalar(
                select(ApiKey).where(
                    ApiKey.id == api_key_id,
                    ApiKey.tenant_id == tenant_id,
                    ApiKey.workspace_id == workspace_id,
                )
            )
            if key_record is not None:
                api_key_plain = decrypt_secret(key_record.encrypted_key, aad=str(tenant_id))

        embeddings: list[list[float] | None] = [None] * len(chunks)
        if chunks and api_key_plain:
            embedder = LiteLLMEmbeddingClient()
            vectors = await embedder.aembed(
                [c.content for c in chunks],
                model=embedding_model,
                api_key=api_key_plain,
            )
            embeddings = list(vectors)

        for chunk, vec in zip(chunks, embeddings, strict=False):
            db.add(
                DocumentChunk(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    embedding=vec,
                    metadata_json={
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                    },
                )
            )

        doc = await db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
            )
        )
        if doc is not None:
            doc.status = "indexed" if any(v is not None for v in embeddings) else "parsed"
            doc.chunk_count = len(chunks)
            doc.metadata_json = {**doc.metadata_json, "page_count": parsed.page_count}

    return {"document_id": str(document_id), "chunk_count": len(chunks)}


@celery_app.task(name="orchestrator.ingest_document")
def ingest_document_task(
    document_id: str,
    tenant_id: str,
    workspace_id: str,
    raw_bytes_b64: str,
    filename: str,
    content_type: str = "application/pdf",
    api_key_id: str | None = None,
    embedding_model: str = "text-embedding-3-small",
) -> dict[str, Any]:
    """Celery task: parse PDF/text with PyMuPDF, chunk, embed via LiteLLM, persist to pgvector."""
    return asyncio.run(
        _ingest_document_async(
            document_id=UUID(document_id),
            tenant_id=UUID(tenant_id),
            workspace_id=UUID(workspace_id),
            raw_bytes=base64.b64decode(raw_bytes_b64.encode("ascii")),
            filename=filename,
            content_type=content_type,
            api_key_id=UUID(api_key_id) if api_key_id else None,
            embedding_model=embedding_model,
        )
    )


async def _execute_workflow_bg(
    *,
    run_id: UUID,
    workflow_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as db, db.begin():
        await set_tenant_context(db, tenant_id)
        workflow = await db.scalar(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        )
        run = await db.scalar(
            select(ExecutionRun).where(ExecutionRun.id == run_id, ExecutionRun.tenant_id == tenant_id)
        )
        if workflow is None or run is None:
            return {"status": "not_found"}

        async def resolve_key(key_id: UUID | None) -> str | None:
            if key_id is None:
                return None
            rec = await db.scalar(
                select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
            )
            return decrypt_secret(rec.encrypted_key, aad=str(tenant_id)) if rec else None

        runtime = ExecutionRuntime(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            api_key_resolver=resolve_key,
        )
        compiled = compile_workflow(workflow.definition, runtime)
        result = await compiled.ainvoke(input_payload, thread_id=str(run.id))

        run.status = result.status
        run.output_payload = result.output
        run.total_tokens = result.total_tokens
        run.estimated_cost_usd = Decimal(str(result.total_cost_usd))
        if result.status == "completed":
            run.completed_at = datetime.now(UTC)

        for metric in result.step_metrics:
            db.add(
                RunStep(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    run_id=run.id,
                    node_id=str(metric.get("node_id", "unknown")),
                    node_type=str(metric.get("node_type", "unknown")),
                    status=str(metric.get("status", "completed")),
                    prompt_tokens=int(metric.get("prompt_tokens", 0)),
                    completion_tokens=int(metric.get("completion_tokens", 0)),
                    estimated_cost_usd=Decimal(str(metric.get("estimated_cost_usd", 0.0))),
                    latency_ms=metric.get("latency_ms"),
                )
            )

    return {"run_id": str(run_id), "status": result.status}


@celery_app.task(name="orchestrator.execute_workflow_async")
def execute_workflow_async_task(
    run_id: str,
    workflow_id: str,
    tenant_id: str,
    workspace_id: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    """Celery task: execute a long-running multi-agent workflow under strict tenant RLS."""
    return asyncio.run(
        _execute_workflow_bg(
            run_id=UUID(run_id),
            workflow_id=UUID(workflow_id),
            tenant_id=UUID(tenant_id),
            workspace_id=UUID(workspace_id),
            input_payload=input_payload,
        )
    )
