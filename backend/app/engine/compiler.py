"""Dynamic compiler translating canonical WorkflowDefinition JSON into LangGraph StateGraph."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.core.config import get_settings
from app.engine.nodes import (
    ExecutionRuntime,
    build_agent_node,
    build_end_node,
    build_human_approval_node,
    build_router_node,
    build_start_node,
    build_supervisor_node,
    build_tool_node,
)
from app.engine.state import ExecutionError, WorkflowState
from app.schemas.workflow import (
    AgentNode,
    EndNode,
    HumanApprovalNode,
    RouterNode,
    StartNode,
    SupervisorNode,
    ToolNode,
    WorkflowDefinition,
    WorkflowEdge,
)


def _extract_interrupt_payload(raw_result: dict[str, Any]) -> dict[str, Any] | None:
    """Return normalized interrupt payload if LangGraph paused at a human_approval node."""
    interrupts = raw_result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"value": value}


@dataclass(slots=True)
class ExecutionResult:
    status: str  # "completed" | "waiting_for_approval"
    thread_id: str
    output: dict[str, Any] | None
    interrupt_payload: dict[str, Any] | None
    total_tokens: int
    total_cost_usd: float
    step_metrics: list[dict[str, Any]]


class CompiledWorkflow:
    """Wrapper around a compiled LangGraph graph enforcing recursion_limit and SSE streaming."""

    def __init__(
        self,
        *,
        definition: WorkflowDefinition,
        graph: Any,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self.definition = definition
        self.graph = graph
        self.checkpointer = checkpointer
        max_limit = get_settings().max_recursion_limit
        self.recursion_limit = min(definition.execution_config.recursion_limit, max_limit)

    def _run_config(self, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.recursion_limit,
        }

    def _build_initial_state(self, input_payload: dict[str, Any]) -> WorkflowState:
        return {
            "input": input_payload,
            "messages": [],
            "context": dict(self.definition.variables),
            "last_output": "",
            "next_route": None,
            "step_metrics": [],
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "human_decision": None,
        }

    def _to_execution_result(self, raw: dict[str, Any], thread_id: str) -> ExecutionResult:
        interrupt_payload = _extract_interrupt_payload(raw)
        if interrupt_payload is not None:
            return ExecutionResult(
                status="waiting_for_approval",
                thread_id=thread_id,
                output=None,
                interrupt_payload=interrupt_payload,
                total_tokens=int(raw.get("total_tokens", 0)),
                total_cost_usd=float(raw.get("total_cost_usd", 0.0)),
                step_metrics=list(raw.get("step_metrics", [])),
            )
        return ExecutionResult(
            status="completed",
            thread_id=thread_id,
            output=raw.get("final_output") or {"result": raw.get("last_output", "")},
            interrupt_payload=None,
            total_tokens=int(raw.get("total_tokens", 0)),
            total_cost_usd=float(raw.get("total_cost_usd", 0.0)),
            step_metrics=list(raw.get("step_metrics", [])),
        )

    async def ainvoke(
        self,
        input_payload: dict[str, Any],
        *,
        thread_id: str,
    ) -> ExecutionResult:
        raw = await self.graph.ainvoke(
            self._build_initial_state(input_payload),
            config=self._run_config(thread_id),
        )
        return self._to_execution_result(raw, thread_id)

    async def aresume(
        self,
        resume_payload: dict[str, Any],
        *,
        thread_id: str,
    ) -> ExecutionResult:
        raw = await self.graph.ainvoke(
            Command(resume=resume_payload),
            config=self._run_config(thread_id),
        )
        return self._to_execution_result(raw, thread_id)

    async def astream_events(
        self,
        input_payload: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield structured real-time execution events suitable for SSE streaming."""
        yield {
            "event": "run_started",
            "data": {
                "thread_id": thread_id,
                "recursion_limit": self.recursion_limit,
            },
        }
        try:
            async for chunk in self.graph.astream(
                self._build_initial_state(input_payload),
                config=self._run_config(thread_id),
                stream_mode="updates",
            ):
                if "__interrupt__" in chunk:
                    payload = _extract_interrupt_payload(chunk)
                    yield {
                        "event": "human_approval_required",
                        "data": {"thread_id": thread_id, "interrupt": payload},
                    }
                    return

                for node_id, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    metrics = update.get("step_metrics") or []
                    latest_metric = metrics[-1] if metrics else {"node_id": node_id}
                    yield {
                        "event": "node_completed",
                        "data": {
                            "thread_id": thread_id,
                            "node_id": node_id,
                            "metric": latest_metric,
                            "last_output": update.get("last_output"),
                            "total_tokens": update.get("total_tokens"),
                            "total_cost_usd": update.get("total_cost_usd"),
                        },
                    }

            snapshot = await self.graph.aget_state(self._run_config(thread_id))
            values = snapshot.values if snapshot else {}
            yield {
                "event": "run_completed",
                "data": {
                    "thread_id": thread_id,
                    "output": values.get("final_output") or {"result": values.get("last_output", "")},
                    "total_tokens": int(values.get("total_tokens", 0)),
                    "total_cost_usd": float(values.get("total_cost_usd", 0.0)),
                },
            }
        except Exception as exc:  # noqa: BLE001 — SSE boundary must emit run_failed event
            yield {
                "event": "run_failed",
                "data": {"thread_id": thread_id, "error": str(exc)},
            }


def _build_conditional_router(
    path_map: dict[str, str],
    default_target: str,
) -> Any:
    def route(state: WorkflowState) -> str:
        chosen = state.get("next_route")
        if chosen and chosen in path_map:
            return chosen
        return default_target

    return route


def compile_workflow(
    definition: WorkflowDefinition | dict[str, Any],
    runtime: ExecutionRuntime,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledWorkflow:
    """Compile a canonical WorkflowDefinition into an executable LangGraph StateGraph."""
    wf = (
        definition
        if isinstance(definition, WorkflowDefinition)
        else WorkflowDefinition.model_validate(definition)
    )

    if runtime.max_cost_usd is None and wf.execution_config.max_cost_usd is not None:
        runtime.max_cost_usd = wf.execution_config.max_cost_usd

    outgoing: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in wf.edges:
        outgoing[edge.source].append(edge)

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    start_node_id: str | None = None
    end_node_ids: list[str] = []

    for node in wf.nodes:
        out_edges = outgoing.get(node.id, [])
        if isinstance(node, StartNode):
            start_node_id = node.id
            builder.add_node(node.id, build_start_node(node))
        elif isinstance(node, EndNode):
            end_node_ids.append(node.id)
            builder.add_node(node.id, build_end_node(node))
        elif isinstance(node, AgentNode):
            builder.add_node(node.id, build_agent_node(node, runtime))
        elif isinstance(node, SupervisorNode):
            candidates = [e.condition or e.target for e in out_edges]
            builder.add_node(node.id, build_supervisor_node(node, runtime, candidates))
        elif isinstance(node, RouterNode):
            fallback_routes = [e.condition or e.target for e in out_edges]
            builder.add_node(node.id, build_router_node(node, runtime, fallback_routes))
        elif isinstance(node, ToolNode):
            builder.add_node(node.id, build_tool_node(node, runtime))
        elif isinstance(node, HumanApprovalNode):
            builder.add_node(node.id, build_human_approval_node(node))
        else:
            raise ExecutionError(f"Unsupported node type: {getattr(node, 'type', 'unknown')}")

    if start_node_id is None:
        raise ExecutionError("WorkflowDefinition is missing a start node.")

    builder.add_edge(START, start_node_id)
    for end_id in end_node_ids:
        builder.add_edge(end_id, END)

    node_by_id = {n.id: n for n in wf.nodes}
    for source_id, edges in outgoing.items():
        source_node = node_by_id[source_id]
        has_conditions = any(e.condition for e in edges)
        is_branching_node = isinstance(source_node, (SupervisorNode, RouterNode, HumanApprovalNode))

        if len(edges) == 1 and not (is_branching_node and has_conditions):
            builder.add_edge(source_id, edges[0].target)
            continue

        path_map: dict[str, str] = {}
        for edge in edges:
            key = edge.condition or edge.target
            path_map[key] = edge.target
        default_key = next(iter(path_map))
        builder.add_conditional_edges(
            source_id,
            _build_conditional_router(path_map, default_key),
            path_map,
        )

    saver = checkpointer or MemorySaver()
    compiled_graph = builder.compile(checkpointer=saver)
    return CompiledWorkflow(definition=wf, graph=compiled_graph, checkpointer=saver)
