"""API-based LiteLLM embeddings and tenant-scoped pgvector cosine retriever."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, KnowledgeDocument


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    score: float


class EmbeddingClient(Protocol):
    async def aembed(
        self,
        texts: list[str],
        *,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> list[list[float]]: ...


class LiteLLMEmbeddingClient:
    """In-process API embedding client via LiteLLM (no local ML models)."""

    async def aembed(
        self,
        texts: list[str],
        *,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> list[list[float]]:
        import litellm

        kwargs: dict = {"model": model, "input": texts}
        if api_key:
            kwargs["api_key"] = api_key
        response = await litellm.aembedding(**kwargs)
        return [list(item["embedding"]) for item in response.data]


async def retrieve_similar_chunks(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Query pgvector cosine similarity strictly scoped to tenant_id + workspace_id."""
    distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = (
        select(
            DocumentChunk.document_id,
            KnowledgeDocument.filename,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            distance_expr,
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance_expr.asc())
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [
        RetrievedChunk(
            document_id=row.document_id,
            filename=row.filename,
            chunk_index=row.chunk_index,
            content=row.content,
            score=round(max(0.0, 1.0 - float(row.distance)), 6),
        )
        for row in rows
    ]
