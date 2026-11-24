"""LangGraph node executor factories for every canonical WorkflowNode type."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langgraph.types import interrupt

from app.engine.llm import LiteLLMClient, LLMClient
from app.engine.state import CostLimitExceededError, WorkflowState
from app.schemas.workflow import (
    AgentNode,
    EndNode,
    HumanApprovalNode,
    RouterNode,
    StartNode,
    SupervisorNode,
    ToolNode,
)

ApiKeyResolver = Callable[[UUID | None], Awaitable[str | None]]
ToolExecutor = Callable[[ToolNode, WorkflowState], Awaitable[dict[str, Any]]]


async def _noop_api_key_resolver(_api_key_id: UUID | None) -> str | None:
    return None


@dataclass(slots=True)
class ExecutionRuntime:
    """Per-run execution dependencies injected into compiled LangGraph nodes."""

    tenant_id: UUID
    workspace_id: UUID
    llm_client: LLMClient = field(default_factory=LiteLLMClient)
    api_key_resolver: ApiKeyResolver = _noop_api_key_resolver
    tool_executor: ToolExecutor | None = None
    max_cost_usd: float | None = None


def _check_cost_guardrail(state: WorkflowState, runtime: ExecutionRuntime) -> None:
    if runtime.max_cost_usd is None:
        return
    current_cost = float(state.get("total_cost_usd", 0.0))
    if current_cost >= runtime.max_cost_usd:
        raise CostLimitExceededError(
            f"Execution halted: accumulated cost ${current_cost:.6f} reached "
            f"limit ${runtime.max_cost_usd:.6f}."
        )


def _extract_initial_prompt(payload: dict[str, Any]) -> str:
    for key in ("prompt", "message", "query", "input", "text"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return str(payload) if payload else ""


def _evaluate_simple_expression(expression: str, state: WorkflowState) -> bool:
    """Safe, eval-free expression evaluator for RouterNode expression mode.

    Supports:
    - `contains:<text>` (case-insensitive check against last_output)
    - `equals:<text>` (case-insensitive exact match against last_output)
    - `key==value` (checks state['input'][key] or state['context'][key])
    """
    expr = expression.strip()
    last_out = (state.get("last_output") or "").strip().lower()
    if expr.startswith("contains:"):
        needle = expr[len("contains:") :].strip().lower()
        return bool(needle) and needle in last_out
    if expr.startswith("equals:"):
        target = expr[len("equals:") :].strip().lower()
        return last_out == target
    if "==" in expr:
        key, expected = expr.split("==", 1)
        key = key.strip()
        expected = expected.strip().strip("\"'")
        actual = state.get("input", {}).get(key, state.get("context", {}).get(key))
        return str(actual) == expected
    return False


def build_start_node(node: StartNode) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        started = time.perf_counter()
        prompt = _extract_initial_prompt(state.get("input", {}))
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "last_output": prompt,
            "context": {**state.get("context", {}), node.id: prompt},
            "messages": [{"role": "user", "content": prompt, "node_id": node.id}] if prompt else [],
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_end_node(node: EndNode) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        started = time.perf_counter()
        context = state.get("context", {})
        if node.data.output_mapping:
            final_output = {
                out_key: context.get(src_key, state.get("last_output", ""))
                for out_key, src_key in node.data.output_mapping.items()
            }
        else:
            final_output = {"result": state.get("last_output", "")}

        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "final_output": final_output,
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_agent_node(
    node: AgentNode,
    runtime: ExecutionRuntime,
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        _check_cost_guardrail(state, runtime)
        started = time.perf_counter()

        api_key = await runtime.api_key_resolver(node.data.api_key_id)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": node.data.system_prompt}
        ]
        for msg in state.get("messages", []):
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": str(msg["content"])})
        if len(messages) == 1:
            messages.append({"role": "user", "content": state.get("last_output", "")})

        result = await runtime.llm_client.acomplete(
            provider=node.data.provider,
            model=node.data.model,
            messages=messages,
            api_key=api_key,
            temperature=node.data.temperature,
            max_tokens=node.data.max_tokens,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        new_total_tokens = int(state.get("total_tokens", 0)) + result.total_tokens
        new_total_cost = round(
            float(state.get("total_cost_usd", 0.0)) + result.estimated_cost_usd, 6
        )

        return {
            "last_output": result.content,
            "context": {**state.get("context", {}), node.id: result.content},
            "messages": [{"role": "assistant", "content": result.content, "node_id": node.id}],
            "total_tokens": new_total_tokens,
            "total_cost_usd": new_total_cost,
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "estimated_cost_usd": result.estimated_cost_usd,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_supervisor_node(
    node: SupervisorNode,
    runtime: ExecutionRuntime,
    candidate_routes: list[str],
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        _check_cost_guardrail(state, runtime)
        started = time.perf_counter()

        options = list(dict.fromkeys([*node.data.managed_agent_ids, *candidate_routes]))
        if not options:
            return {"next_route": "FINISH"}

        if node.data.routing_strategy == "round_robin":
            visited = [
                m["node_id"]
                for m in state.get("step_metrics", [])
                if m.get("node_id") in options
            ]
            chosen = next((opt for opt in options if opt not in visited), options[-1])
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "next_route": chosen,
                "context": {**state.get("context", {}), node.id: chosen},
                "step_metrics": [
                    {
                        "node_id": node.id,
                        "node_type": node.type,
                        "status": "completed",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "estimated_cost_usd": 0.0,
                        "latency_ms": latency_ms,
                    }
                ],
            }

        api_key = await runtime.api_key_resolver(node.data.api_key_id)
        routing_instruction = (
            f"{node.data.system_prompt}\n\n"
            f"Choose the single best next route from: {', '.join(options)}.\n"
            "Respond with ONLY the exact route key."
        )
        result = await runtime.llm_client.acomplete(
            provider=node.data.provider,
            model=node.data.model,
            messages=[
                {"role": "system", "content": routing_instruction},
                {"role": "user", "content": state.get("last_output", "")},
            ],
            api_key=api_key,
            temperature=0.0,
            max_tokens=64,
        )
        raw_choice = result.content.strip()
        chosen = next((opt for opt in options if opt == raw_choice or opt in raw_choice), options[0])
        latency_ms = int((time.perf_counter() - started) * 1000)

        return {
            "next_route": chosen,
            "context": {**state.get("context", {}), node.id: chosen},
            "total_tokens": int(state.get("total_tokens", 0)) + result.total_tokens,
            "total_cost_usd": round(
                float(state.get("total_cost_usd", 0.0)) + result.estimated_cost_usd, 6
            ),
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "estimated_cost_usd": result.estimated_cost_usd,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_router_node(
    node: RouterNode,
    runtime: ExecutionRuntime,
    fallback_routes: list[str],
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        _check_cost_guardrail(state, runtime)
        started = time.perf_counter()

        route_keys = [r.key for r in node.data.routes] or fallback_routes
        if not route_keys:
            return {"next_route": "default"}

        if node.data.mode == "expression":
            chosen = route_keys[0]
            for route in node.data.routes:
                if route.expression and _evaluate_simple_expression(route.expression, state):
                    chosen = route.key
                    break
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "next_route": chosen,
                "context": {**state.get("context", {}), node.id: chosen},
                "step_metrics": [
                    {
                        "node_id": node.id,
                        "node_type": node.type,
                        "status": "completed",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "estimated_cost_usd": 0.0,
                        "latency_ms": latency_ms,
                    }
                ],
            }

        api_key = await runtime.api_key_resolver(node.data.api_key_id)
        routes_desc = "\n".join(f"- {r.key}: {r.description}" for r in node.data.routes)
        result = await runtime.llm_client.acomplete(
            provider=node.data.provider,
            model=node.data.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the input into exactly one of the following route keys:\n"
                        f"{routes_desc}\nRespond with ONLY the route key."
                    ),
                },
                {"role": "user", "content": state.get("last_output", "")},
            ],
            api_key=api_key,
            temperature=0.0,
            max_tokens=32,
        )
        raw_choice = result.content.strip()
        chosen = next(
            (key for key in route_keys if key == raw_choice or key in raw_choice),
            route_keys[0],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "next_route": chosen,
            "context": {**state.get("context", {}), node.id: chosen},
            "total_tokens": int(state.get("total_tokens", 0)) + result.total_tokens,
            "total_cost_usd": round(
                float(state.get("total_cost_usd", 0.0)) + result.estimated_cost_usd, 6
            ),
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "estimated_cost_usd": result.estimated_cost_usd,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_tool_node(
    node: ToolNode,
    runtime: ExecutionRuntime,
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        started = time.perf_counter()
        if runtime.tool_executor is not None:
            tool_result = await runtime.tool_executor(node, state)
        else:
            tool_result = {
                "tool_kind": node.data.tool_kind,
                "operation": node.data.operation_name,
                "status": "no_executor_bound",
            }
        output_text = str(tool_result.get("output", tool_result))
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "last_output": output_text,
            "context": {**state.get("context", {}), node.id: tool_result},
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute


def build_human_approval_node(
    node: HumanApprovalNode,
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState) -> dict[str, Any]:
        started = time.perf_counter()
        decision_payload = interrupt(
            {
                "node_id": node.id,
                "label": node.data.label,
                "prompt_message": node.data.prompt_message,
                "allowed_actions": node.data.allowed_actions,
                "last_output": state.get("last_output", ""),
            }
        )

        if isinstance(decision_payload, dict):
            action = str(decision_payload.get("action", "approve"))
            edited_output = decision_payload.get("edited_output")
        else:
            action = str(decision_payload)
            edited_output = None

        if action not in node.data.allowed_actions:
            action = node.data.allowed_actions[0]

        next_output = (
            str(edited_output)
            if action == "edit" and edited_output is not None
            else state.get("last_output", "")
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "human_decision": action,
            "next_route": action,
            "last_output": next_output,
            "context": {**state.get("context", {}), node.id: {"action": action, "output": next_output}},
            "step_metrics": [
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "status": "completed",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": latency_ms,
                }
            ],
        }

    return execute
