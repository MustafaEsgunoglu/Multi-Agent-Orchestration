"""Tenant-scoped RAG document ingestion & pgvector similarity search endpoints."""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.tenant import TenantContext, get_current_tenant_context
from app.db.models import ApiKey, DocumentChunk, KnowledgeDocument
from app.db.rls import get_tenant_db
from app.rag.chunker import chunk_text
from app.rag.parser import parse_document_bytes
from app.rag.retriever import LiteLLMEmbeddingClient, retrieve_similar_chunks

router = APIRouter(prefix="/rag", tags=["rag"])


class DocumentIngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="text/plain", max_length=120)
    content_base64: str | None = None
    content_text: str | None = None
    api_key_id: UUID | None = None
    embedding_model: str = Field(default="text-embedding-3-small", max_length=120)


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    filename: str
    content_type: str
    status: str
    chunk_count: int
    created_at: datetime


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    api_key_id: UUID | None = None
    embedding_model: str = Field(default="text-embedding-3-small", max_length=120)


class RagSearchHit(BaseModel):
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    score: float


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    payload: DocumentIngestRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> KnowledgeDocumentResponse:
    if payload.content_base64:
        raw_bytes = base64.b64decode(payload.content_base64.encode("ascii"))
    elif payload.content_text is not None:
        raw_bytes = payload.content_text.encode("utf-8")
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either content_base64 or content_text is required.",
        )

    parsed = parse_document_bytes(
        raw_bytes, filename=payload.filename, content_type=payload.content_type
    )
    chunks = chunk_text(parsed.text)

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

    embeddings: list[list[float] | None] = [None] * len(chunks)
    if chunks and api_key_plain:
        vectors = await LiteLLMEmbeddingClient().aembed(
            [c.content for c in chunks],
            model=payload.embedding_model,
            api_key=api_key_plain,
        )
        embeddings = list(vectors)

    doc = KnowledgeDocument(
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        filename=payload.filename,
        content_type=payload.content_type,
        status="indexed" if any(v is not None for v in embeddings) else "parsed",
        chunk_count=len(chunks),
        metadata_json={"page_count": parsed.page_count, **parsed.metadata},
    )
    db.add(doc)
    await db.flush()

    for chunk, vec in zip(chunks, embeddings, strict=False):
        db.add(
            DocumentChunk(
                tenant_id=ctx.tenant_id,
                workspace_id=ctx.workspace_id,
                document_id=doc.id,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=vec,
                metadata_json={"char_start": chunk.char_start, "char_end": chunk.char_end},
            )
        )
    await db.flush()
    return KnowledgeDocumentResponse.model_validate(doc)


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
async def list_documents(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[KnowledgeDocumentResponse]:
    rows = await db.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.tenant_id == ctx.tenant_id,
            KnowledgeDocument.workspace_id == ctx.workspace_id,
        )
        .order_by(KnowledgeDocument.created_at.desc())
    )
    return [KnowledgeDocumentResponse.model_validate(d) for d in rows.all()]


@router.post("/search", response_model=list[RagSearchHit])
async def search_knowledge_base(
    payload: RagSearchRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: AsyncSession = Depends(get_tenant_db),
) -> list[RagSearchHit]:
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

    vectors = await LiteLLMEmbeddingClient().aembed(
        [payload.query],
        model=payload.embedding_model,
        api_key=api_key_plain,
    )
    hits = await retrieve_similar_chunks(
        db,
        tenant_id=ctx.tenant_id,
        workspace_id=ctx.workspace_id,
        query_embedding=vectors[0],
        top_k=payload.top_k,
    )
    return [
        RagSearchHit(
            document_id=h.document_id,
            filename=h.filename,
            chunk_index=h.chunk_index,
            content=h.content,
            score=h.score,
        )
        for h in hits
    ]
