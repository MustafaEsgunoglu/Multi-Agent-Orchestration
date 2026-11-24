"""Comprehensive tests for LangGraph compiler, node executors, HITL, cost guardrails & SSE."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.errors import GraphRecursionError

from app.engine.compiler import compile_workflow
from app.engine.llm import LLMCallResult
from app.engine.nodes import ExecutionRuntime
from app.engine.state import CostLimitExceededError


class FakeLLMClient:
    """Deterministic mock LLMClient returning queued responses with token & USD metrics."""

    def __init__(self, responses: list[str], cost_per_call: float = 0.0025) -> None:
        self._responses = list(responses)
        self._cost = cost_per_call
        self.calls: list[dict] = []

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
        self.calls.append({"provider": provider, "model": model, "api_key": api_key})
        text = self._responses.pop(0) if self._responses else "default-reply"
        return LLMCallResult(
            content=text,
            model=f"{provider}/{model}",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=self._cost,
        )


def _runtime(fake_llm: FakeLLMClient, max_cost_usd: float | None = None) -> ExecutionRuntime:
    return ExecutionRuntime(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        llm_client=fake_llm,
        max_cost_usd=max_cost_usd,
    )


@pytest.mark.asyncio
async def test_linear_agent_workflow_tracks_tokens_and_cost() -> None:
    definition = {
        "schema_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {
                "id": "writer",
                "type": "agent",
                "position": {"x": 200, "y": 0},
                "data": {"label": "Writer", "provider": "openai", "model": "gpt-4o-mini"},
            },
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "writer"},
            {"id": "e2", "source": "writer", "target": "end"},
        ],
    }

    fake_llm = FakeLLMClient(["Hello from multi-agent platform!"], cost_per_call=0.0042)
    compiled = compile_workflow(definition, _runtime(fake_llm))
    result = await compiled.ainvoke({"prompt": "Say hi"}, thread_id="t-linear-1")

    assert result.status == "completed"
    assert result.output == {"result": "Hello from multi-agent platform!"}
    assert result.total_tokens == 150
    assert result.total_cost_usd == pytest.approx(0.0042)
    assert [m["node_id"] for m in result.step_metrics] == ["start", "writer", "end"]


@pytest.mark.asyncio
async def test_supervisor_routes_to_selected_specialist_agent() -> None:
    definition = {
        "schema_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {
                "id": "sup",
                "type": "supervisor",
                "position": {"x": 200, "y": 0},
                "data": {
                    "label": "Supervisor",
                    "managed_agent_ids": ["agent_billing", "agent_tech"],
                },
            },
            {
                "id": "agent_billing",
                "type": "agent",
                "position": {"x": 400, "y": -80},
                "data": {"label": "Billing Agent"},
            },
            {
                "id": "agent_tech",
                "type": "agent",
                "position": {"x": 400, "y": 80},
                "data": {"label": "Tech Agent"},
            },
            {"id": "end", "type": "end", "position": {"x": 600, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "sup"},
            {"id": "e2", "source": "sup", "target": "agent_billing", "condition": "agent_billing"},
            {"id": "e3", "source": "sup", "target": "agent_tech", "condition": "agent_tech"},
            {"id": "e4", "source": "agent_billing", "target": "end"},
            {"id": "e5", "source": "agent_tech", "target": "end"},
        ],
    }

    fake_llm = FakeLLMClient(["agent_tech", "Restarted your pod successfully."])
    compiled = compile_workflow(definition, _runtime(fake_llm))
    result = await compiled.ainvoke({"prompt": "My server crashed"}, thread_id="t-sup-1")

    assert result.status == "completed"
    assert result.output == {"result": "Restarted your pod successfully."}
    visited = [m["node_id"] for m in result.step_metrics]
    assert "agent_tech" in visited
    assert "agent_billing" not in visited


@pytest.mark.asyncio
async def test_expression_router_branches_without_llm_call() -> None:
    definition = {
        "schema_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {
                "id": "router",
                "type": "router",
                "position": {"x": 200, "y": 0},
                "data": {
                    "label": "Urgency Router",
                    "mode": "expression",
                    "routes": [
                        {"key": "urgent", "description": "Urgent tickets", "expression": "contains:urgent"},
                        {"key": "normal", "description": "Normal tickets", "expression": "contains:hello"},
                    ],
                },
            },
            {"id": "tool_page", "type": "tool", "position": {"x": 400, "y": -60}, "data": {"label": "Pager"}},
            {"id": "end", "type": "end", "position": {"x": 600, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "router"},
            {"id": "e2", "source": "router", "target": "tool_page", "condition": "urgent"},
            {"id": "e3", "source": "router", "target": "end", "condition": "normal"},
            {"id": "e4", "source": "tool_page", "target": "end"},
        ],
    }

    fake_llm = FakeLLMClient([])
    compiled = compile_workflow(definition, _runtime(fake_llm))
    result = await compiled.ainvoke({"prompt": "URGENT outage in eu-west"}, thread_id="t-router-1")

    assert result.status == "completed"
    assert len(fake_llm.calls) == 0
    assert "tool_page" in [m["node_id"] for m in result.step_metrics]


@pytest.mark.asyncio
async def test_human_approval_interrupt_and_resume_with_edit() -> None:
    definition = {
        "schema_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {"id": "draft", "type": "agent", "position": {"x": 200, "y": 0}, "data": {"label": "Draft Agent"}},
            {
                "id": "approval",
                "type": "human_approval",
                "position": {"x": 400, "y": 0},
                "data": {
                    "label": "Manager Gate",
                    "prompt_message": "Approve draft?",
                    "allowed_actions": ["approve", "reject", "edit"],
                },
            },
            {"id": "end", "type": "end", "position": {"x": 600, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "draft"},
            {"id": "e2", "source": "draft", "target": "approval"},
            {"id": "e3", "source": "approval", "target": "end", "condition": "approve"},
            {"id": "e4", "source": "approval", "target": "end", "condition": "edit"},
        ],
    }

    fake_llm = FakeLLMClient(["Initial AI draft"])
    compiled = compile_workflow(definition, _runtime(fake_llm))

    paused = await compiled.ainvoke({"prompt": "Write email"}, thread_id="t-hitl-1")
    assert paused.status == "waiting_for_approval"
    assert paused.interrupt_payload is not None
    assert paused.interrupt_payload["node_id"] == "approval"
    assert paused.interrupt_payload["last_output"] == "Initial AI draft"

    resumed = await compiled.aresume(
        {"action": "edit", "edited_output": "Manager-approved final email"},
        thread_id="t-hitl-1",
    )
    assert resumed.status == "completed"
    assert resumed.output == {"result": "Manager-approved final email"}


@pytest.mark.asyncio
async def test_cost_limit_guardrail_halts_execution() -> None:
    definition = {
        "schema_version": "1.0",
        "execution_config": {"recursion_limit": 10, "max_cost_usd": 0.005},
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {"id": "a1", "type": "agent", "position": {"x": 200, "y": 0}, "data": {"label": "Agent 1"}},
            {"id": "a2", "type": "agent", "position": {"x": 400, "y": 0}, "data": {"label": "Agent 2"}},
            {"id": "end", "type": "end", "position": {"x": 600, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "a1"},
            {"id": "e2", "source": "a1", "target": "a2"},
            {"id": "e3", "source": "a2", "target": "end"},
        ],
    }

    fake_llm = FakeLLMClient(["Step 1", "Step 2"], cost_per_call=0.006)
    compiled = compile_workflow(definition, _runtime(fake_llm))
    with pytest.raises(CostLimitExceededError):
        await compiled.ainvoke({"prompt": "Go"}, thread_id="t-cost-1")


@pytest.mark.asyncio
async def test_recursion_limit_stops_infinite_cycles() -> None:
    definition = {
        "schema_version": "1.0",
        "execution_config": {"recursion_limit": 4},
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {"id": "a1", "type": "agent", "position": {"x": 200, "y": 0}, "data": {"label": "Loop A"}},
            {"id": "a2", "type": "agent", "position": {"x": 400, "y": 0}, "data": {"label": "Loop B"}},
            {"id": "end", "type": "end", "position": {"x": 600, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "a1"},
            {"id": "e2", "source": "a1", "target": "a2"},
            {"id": "e3", "source": "a2", "target": "a1"},
        ],
    }

    fake_llm = FakeLLMClient(["ping"] * 20)
    compiled = compile_workflow(definition, _runtime(fake_llm))
    with pytest.raises(GraphRecursionError):
        await compiled.ainvoke({"prompt": "Loop forever"}, thread_id="t-cycle-1")


@pytest.mark.asyncio
async def test_sse_stream_events_emit_node_progress() -> None:
    definition = {
        "schema_version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
            {"id": "agent_1", "type": "agent", "position": {"x": 200, "y": 0}, "data": {"label": "Worker"}},
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "agent_1"},
            {"id": "e2", "source": "agent_1", "target": "end"},
        ],
    }

    fake_llm = FakeLLMClient(["Streamed answer"])
    compiled = compile_workflow(definition, _runtime(fake_llm))
    events = [evt async for evt in compiled.astream_events({"prompt": "Stream"}, thread_id="t-sse-1")]

    event_types = [e["event"] for e in events]
    assert event_types[0] == "run_started"
    assert event_types[-1] == "run_completed"
    completed_nodes = [e["data"]["node_id"] for e in events if e["event"] == "node_completed"]
    assert completed_nodes == ["start", "agent_1", "end"]
