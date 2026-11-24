"""Prompt-to-Workflow AI Copilot meta-agent generating canonical WorkflowDefinition JSON."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.engine.llm import LiteLLMClient, LLMClient
from app.schemas.workflow import WorkflowDefinition

COPILOT_SYSTEM_PROMPT = """You are an expert Multi-Agent Workflow Architect.
Given a user's natural language goal, produce a valid JSON object matching the canonical WorkflowDefinition schema.

STRICT RULES:
1. Return ONLY valid JSON with two top-level keys:
   - "explanation": concise summary of the workflow design.
   - "workflow": a valid WorkflowDefinition object.
2. "workflow" MUST have:
   - "schema_version": "1.0"
   - "execution_config": {"recursion_limit": 25, "timeout_seconds": 300} (recursion_limit MUST be between 1 and 50)
   - "nodes": list of nodes, each with {"id", "type", "position": {"x", "y"}, "data": {...}}
     Allowed node types: "start", "end", "supervisor", "agent", "tool", "router", "human_approval".
     MUST contain EXACTLY ONE "start" node and AT LEAST ONE "end" node.
     Node IDs must match ^[a-zA-Z0-9_-]+$ and be unique.
   - "edges": list of {"id", "source", "target", "condition" (optional)}
     No dangling edges, no self-loops, no edges targeting "start", no edges originating from "end".
3. Arrange node positions left-to-right cleanly (x increments by ~240, y spaced by ~140 for branches).
"""


class CopilotGenerationError(RuntimeError):
    """Raised when the Copilot cannot produce a valid WorkflowDefinition within retries."""


@dataclass(frozen=True, slots=True)
class CopilotResult:
    workflow: WorkflowDefinition
    explanation: str
    attempts: int
    total_tokens: int
    estimated_cost_usd: float


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract a JSON object from plain JSON or fenced ```json ... ``` blocks."""
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace : last_brace + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise TypeError("Copilot output must be a JSON object.")
    return parsed


async def generate_workflow_from_prompt(
    prompt: str,
    *,
    llm_client: LLMClient | None = None,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    existing_workflow: WorkflowDefinition | None = None,
    max_retries: int = 2,
) -> CopilotResult:
    """Generate and validate a canonical WorkflowDefinition with self-healing retries."""
    client = llm_client or LiteLLMClient()
    messages: list[dict[str, str]] = [{"role": "system", "content": COPILOT_SYSTEM_PROMPT}]

    user_content = f"Goal:\n{prompt}"
    if existing_workflow is not None:
        user_content += (
            "\n\nExisting WorkflowDefinition JSON to modify:\n"
            f"{existing_workflow.model_dump_json()}"
        )
    messages.append({"role": "user", "content": user_content})

    total_tokens = 0
    total_cost = 0.0
    last_error = ""

    for attempt in range(1, max_retries + 2):
        response = await client.acomplete(
            provider=provider,
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=0.1,
            max_tokens=4096,
        )
        total_tokens += response.total_tokens
        total_cost = round(total_cost + response.estimated_cost_usd, 6)

        try:
            parsed = _extract_json_object(response.content)
            raw_workflow = parsed.get("workflow", parsed)
            workflow = WorkflowDefinition.model_validate(raw_workflow)
            explanation = str(
                parsed.get("explanation") or "Generated multi-agent workflow from prompt."
            )
            return CopilotResult(
                workflow=workflow,
                explanation=explanation,
                attempts=attempt,
                total_tokens=total_tokens,
                estimated_cost_usd=total_cost,
            )
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous JSON failed WorkflowDefinition schema validation:\n"
                        f"{last_error}\n\n"
                        "Fix all issues and return ONLY the corrected JSON object."
                    ),
                }
            )

    raise CopilotGenerationError(
        f"Failed to generate a valid WorkflowDefinition after {max_retries + 1} attempts: "
        f"{last_error}"
    )
