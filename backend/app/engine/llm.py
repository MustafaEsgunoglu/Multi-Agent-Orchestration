"""In-process LiteLLM SDK adapter with token usage & USD cost tracking.

Security & Architecture rules:
- Runs strictly in-process via LiteLLM Python SDK (no separate proxy container).
- Accepts decrypted BYOK API keys in memory only; never logs keys or headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class LLMClient(Protocol):
    async def acomplete(
        self,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMCallResult: ...


def format_litellm_model(provider: str, model: str) -> str:
    """Normalize provider + model into LiteLLM's expected model identifier."""
    if "/" in model or provider in ("openai", "custom"):
        return model
    provider_prefix = {
        "anthropic": "anthropic",
        "google": "gemini",
        "groq": "groq",
        "mistral": "mistral",
        "openrouter": "openrouter",
        "deepseek": "deepseek",
    }.get(provider, provider)
    return f"{provider_prefix}/{model}"


class LiteLLMClient:
    """Production in-process LiteLLM SDK client."""

    async def acomplete(
        self,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMCallResult:
        import litellm

        model_name = format_litellm_model(provider, model)
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        resolved_key = api_key
        if not resolved_key and provider == "deepseek":
            from app.core.config import get_settings

            resolved_key = get_settings().deepseek_api_key
        if resolved_key:
            kwargs["api_key"] = resolved_key

        response = await litellm.acompletion(**kwargs)

        choice = response.choices[0]
        content = (choice.message.content or "") if choice.message else ""

        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", prompt_tokens + completion_tokens)
            or (prompt_tokens + completion_tokens)
        )

        try:
            cost = float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:  # noqa: BLE001 — unknown/custom models may lack LiteLLM pricing table
            cost = 0.0

        return LLMCallResult(
            content=content,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 6),
        )
