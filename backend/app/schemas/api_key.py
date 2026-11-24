"""BYOK LLM API Key schemas (never expose plaintext secrets in responses)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["openai", "anthropic", "google", "groq", "mistral", "openrouter", "custom"]
    api_key: str = Field(min_length=8, max_length=512)


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    provider: str
    key_hint: str
    created_at: datetime
