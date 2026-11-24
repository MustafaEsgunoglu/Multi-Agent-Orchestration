"""Canonical Single Source of Truth schema for multi-agent workflows.

Shared contract between:
1. Frontend React Flow canvas (mirrored in Zod schemas)
2. Prompt-to-Workflow AI Copilot (structured output target)
3. Backend LangGraph StateGraph compiler
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodePosition(BaseModel):
    x: float
    y: float


class BaseNodeData(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class StartNodeData(BaseNodeData):
    input_schema: dict[str, Any] = Field(default_factory=dict)


class EndNodeData(BaseNodeData):
    output_mapping: dict[str, str] = Field(default_factory=dict)


class LLMConfigMixin(BaseModel):
    provider: Literal["openai", "anthropic", "google", "groq", "mistral", "openrouter", "custom"] = "openai"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120)
    api_key_id: UUID | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=2048, ge=1, le=128000)


class SupervisorNodeData(BaseNodeData, LLMConfigMixin):
    system_prompt: str = Field(
        default="You are a supervisor orchestrating specialist agents to complete the user task.",
        min_length=1,
        max_length=16000,
    )
    routing_strategy: Literal["llm_router", "round_robin"] = "llm_router"
    managed_agent_ids: list[str] = Field(default_factory=list)


class AgentNodeData(BaseNodeData, LLMConfigMixin):
    system_prompt: str = Field(
        default="You are a helpful specialist AI agent.",
        min_length=1,
        max_length=16000,
    )
    tool_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[UUID] = Field(default_factory=list)
    rag_enabled: bool = False
    rag_top_k: int = Field(default=5, ge=1, le=20)
    structured_output_schema: dict[str, Any] | None = None


class ToolNodeData(BaseNodeData):
    tool_kind: Literal["mcp", "openapi", "rag", "http"] = "mcp"
    mcp_server_id: UUID | None = None
    openapi_spec_url: str | None = None
    operation_name: str | None = Field(default=None, max_length=120)
    static_params: dict[str, Any] = Field(default_factory=dict)


class RouterRoute(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=300)
    expression: str | None = None


class RouterNodeData(BaseNodeData):
    mode: Literal["llm", "expression"] = "llm"
    provider: Literal["openai", "anthropic", "google", "groq", "mistral", "openrouter", "custom"] = "openai"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120)
    api_key_id: UUID | None = None
    routes: list[RouterRoute] = Field(default_factory=list)


class HumanApprovalNodeData(BaseNodeData):
    prompt_message: str = Field(
        default="Review the agent output and approve or reject to continue.",
        min_length=1,
        max_length=2000,
    )
    timeout_seconds: int = Field(default=86400, ge=60, le=604800)
    allowed_actions: list[Literal["approve", "reject", "edit"]] = Field(
        default_factory=lambda: ["approve", "reject"]
    )


class _BaseNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    position: NodePosition


class StartNode(_BaseNode):
    type: Literal["start"] = "start"
    data: StartNodeData


class EndNode(_BaseNode):
    type: Literal["end"] = "end"
    data: EndNodeData


class SupervisorNode(_BaseNode):
    type: Literal["supervisor"] = "supervisor"
    data: SupervisorNodeData


class AgentNode(_BaseNode):
    type: Literal["agent"] = "agent"
    data: AgentNodeData


class ToolNode(_BaseNode):
    type: Literal["tool"] = "tool"
    data: ToolNodeData


class RouterNode(_BaseNode):
    type: Literal["router"] = "router"
    data: RouterNodeData


class HumanApprovalNode(_BaseNode):
    type: Literal["human_approval"] = "human_approval"
    data: HumanApprovalNodeData


WorkflowNode = Annotated[
    StartNode
    | EndNode
    | SupervisorNode
    | AgentNode
    | ToolNode
    | RouterNode
    | HumanApprovalNode,
    Field(discriminator="type"),
]


class WorkflowEdge(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    source_handle: str | None = None
    target_handle: str | None = None
    condition: str | None = Field(default=None, max_length=120)


class ExecutionConfig(BaseModel):
    """Execution safety & cost guardrails enforced by the LangGraph compiler."""

    recursion_limit: int = Field(default=25, ge=1, le=50)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)
    max_cost_usd: float | None = Field(default=None, gt=0.0, le=100.0)


class WorkflowDefinition(BaseModel):
    """Canonical workflow graph definition validated across Studio, Copilot, and Compiler."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    nodes: list[WorkflowNode] = Field(min_length=2, max_length=100)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=300)
    execution_config: ExecutionConfig = Field(default_factory=ExecutionConfig)
    variables: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> WorkflowDefinition:
        node_map: dict[str, WorkflowNode] = {}
        start_ids: set[str] = set()
        end_ids: set[str] = set()

        for node in self.nodes:
            if node.id in node_map:
                raise ValueError(f"Duplicate node id detected: '{node.id}'.")
            node_map[node.id] = node
            if node.type == "start":
                start_ids.add(node.id)
            elif node.type == "end":
                end_ids.add(node.id)

        if len(start_ids) != 1:
            raise ValueError(
                f"Workflow must contain exactly one 'start' node (found {len(start_ids)})."
            )
        if len(end_ids) < 1:
            raise ValueError("Workflow must contain at least one 'end' node.")

        seen_edges: set[str] = set()
        for edge in self.edges:
            if edge.id in seen_edges:
                raise ValueError(f"Duplicate edge id detected: '{edge.id}'.")
            seen_edges.add(edge.id)

            if edge.source not in node_map:
                raise ValueError(f"Edge '{edge.id}' references unknown source node '{edge.source}'.")
            if edge.target not in node_map:
                raise ValueError(f"Edge '{edge.id}' references unknown target node '{edge.target}'.")
            if edge.source == edge.target:
                raise ValueError(f"Edge '{edge.id}' cannot form a self-loop on node '{edge.source}'.")
            if edge.target in start_ids:
                raise ValueError(f"Edge '{edge.id}' cannot target the 'start' node '{edge.target}'.")
            if edge.source in end_ids:
                raise ValueError(f"Edge '{edge.id}' cannot originate from an 'end' node '{edge.source}'.")

        for node in self.nodes:
            if isinstance(node, SupervisorNode):
                for managed_id in node.data.managed_agent_ids:
                    if managed_id not in node_map:
                        raise ValueError(
                            f"Supervisor '{node.id}' references unknown managed node '{managed_id}'."
                        )
                    if managed_id == node.id:
                        raise ValueError(f"Supervisor '{node.id}' cannot manage itself.")

        return self


class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    definition: WorkflowDefinition


class WorkflowUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    definition: WorkflowDefinition | None = None
    is_active: bool | None = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    definition: WorkflowDefinition
    version: int
    is_active: bool
