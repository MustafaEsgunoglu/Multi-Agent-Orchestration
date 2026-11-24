"use client";

import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { create } from "zustand";

import {
  WorkflowDefinition,
  WorkflowDefinitionSchema,
  WorkflowNodeType,
} from "@/schemas/workflow";

export type NodeRunStatus = "idle" | "running" | "completed" | "waiting_approval" | "failed";

export interface StudioNodeData extends Record<string, unknown> {
  label: string;
  description?: string | null;
  provider?: string;
  model?: string;
  system_prompt?: string;
  temperature?: number;
  rag_enabled?: boolean;
  rag_top_k?: number;
  tool_kind?: string;
  operation_name?: string | null;
  routing_strategy?: string;
  managed_agent_ids?: string[];
  mode?: string;
  prompt_message?: string;
  allowed_actions?: string[];
}

export const STARTER_WORKFLOW: WorkflowDefinition = {
  schema_version: "1.0",
  execution_config: {
    recursion_limit: 25,
    timeout_seconds: 300,
  },
  variables: {},
  nodes: [
    {
      id: "start_1",
      type: "start",
      position: { x: 60, y: 180 },
      data: { label: "User Trigger", input_schema: {} },
    },
    {
      id: "sup_1",
      type: "supervisor",
      position: { x: 320, y: 180 },
      data: {
        label: "Lead Supervisor",
        provider: "openai",
        model: "gpt-4o-mini",
        temperature: 0.2,
        system_prompt: "Route incoming requests to the best specialist agent.",
        routing_strategy: "llm_router",
        managed_agent_ids: ["agent_rag", "agent_tool"],
      },
    },
    {
      id: "agent_rag",
      type: "agent",
      position: { x: 620, y: 70 },
      data: {
        label: "RAG Researcher",
        provider: "anthropic",
        model: "claude-3-5-sonnet-20241022",
        temperature: 0.2,
        system_prompt: "Answer questions strictly using pgvector knowledge base citations.",
        tool_ids: [],
        mcp_server_ids: [],
        rag_enabled: true,
        rag_top_k: 5,
      },
    },
    {
      id: "agent_tool",
      type: "agent",
      position: { x: 620, y: 290 },
      data: {
        label: "MCP Action Agent",
        provider: "openai",
        model: "gpt-4o-mini",
        temperature: 0.1,
        system_prompt: "Execute external MCP & OpenAPI tools safely.",
        tool_ids: [],
        mcp_server_ids: [],
        rag_enabled: false,
        rag_top_k: 5,
      },
    },
    {
      id: "hitl_1",
      type: "human_approval",
      position: { x: 920, y: 180 },
      data: {
        label: "Human Approval",
        prompt_message: "Review agent output before finalizing.",
        timeout_seconds: 86400,
        allowed_actions: ["approve", "reject", "edit"],
      },
    },
    {
      id: "end_1",
      type: "end",
      position: { x: 1180, y: 180 },
      data: { label: "Final Output", output_mapping: {} },
    },
  ],
  edges: [
    { id: "e_start_sup", source: "start_1", target: "sup_1" },
    { id: "e_sup_rag", source: "sup_1", target: "agent_rag", condition: "agent_rag" },
    { id: "e_sup_tool", source: "sup_1", target: "agent_tool", condition: "agent_tool" },
    { id: "e_rag_hitl", source: "agent_rag", target: "hitl_1" },
    { id: "e_tool_hitl", source: "agent_tool", target: "hitl_1" },
    { id: "e_hitl_end", source: "hitl_1", target: "end_1", condition: "approve" },
  ],
};

export const RESEARCH_PIPELINE_WORKFLOW: WorkflowDefinition = {
  schema_version: "1.0",
  execution_config: {
    recursion_limit: 15,
    timeout_seconds: 240,
    max_cost_usd: 0.25,
  },
  variables: {},
  nodes: [
    {
      id: "start_doc",
      type: "start",
      position: { x: 80, y: 180 },
      data: { label: "PDF / Query Input", input_schema: {} },
    },
    {
      id: "rag_fetch",
      type: "tool",
      position: { x: 360, y: 180 },
      data: {
        label: "pgvector Retriever",
        tool_kind: "rag",
        operation_name: "cosine_search",
        static_params: { top_k: 6 },
      },
    },
    {
      id: "synth_agent",
      type: "agent",
      position: { x: 660, y: 180 },
      data: {
        label: "Synthesis Agent",
        provider: "anthropic",
        model: "claude-3-5-sonnet-20241022",
        temperature: 0.1,
        system_prompt:
          "Synthesize retrieved document chunks into a concise JSON summary with citations.",
        tool_ids: [],
        mcp_server_ids: [],
        rag_enabled: true,
        rag_top_k: 6,
      },
    },
    {
      id: "end_doc",
      type: "end",
      position: { x: 960, y: 180 },
      data: { label: "Structured JSON Output", output_mapping: {} },
    },
  ],
  edges: [
    { id: "e_doc_1", source: "start_doc", target: "rag_fetch" },
    { id: "e_doc_2", source: "rag_fetch", target: "synth_agent" },
    { id: "e_doc_3", source: "synth_agent", target: "end_doc" },
  ],
};

export const WORKFLOW_TEMPLATES: Record<
  string,
  { name: string; definition: WorkflowDefinition }
> = {
  starter: {
    name: "Customer Support Multi-Agent Flow",
    definition: STARTER_WORKFLOW,
  },
  "research-pipeline": {
    name: "Document Analysis & Synthesis",
    definition: RESEARCH_PIPELINE_WORKFLOW,
  },
};

function toReactFlowNodes(def: WorkflowDefinition): Node<StudioNodeData>[] {
  return def.nodes.map((n) => ({
    id: n.id,
    type: n.type,
    position: n.position,
    data: n.data as StudioNodeData,
  }));
}

function toReactFlowEdges(def: WorkflowDefinition): Edge[] {
  return def.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.source_handle ?? undefined,
    targetHandle: e.target_handle ?? undefined,
    label: e.condition ?? undefined,
    animated: true,
    style: { stroke: "#475569", strokeWidth: 2 },
  }));
}

interface WorkflowStoreState {
  activeWorkflowId: string;
  workflowName: string;
  recursionLimit: number;
  nodes: Node<StudioNodeData>[];
  edges: Edge[];
  selectedNodeId: string | null;
  nodeStatuses: Record<string, NodeRunStatus>;
  totalTokens: number;
  totalCostUsd: number;
  isRunning: boolean;
  lastError: string | null;

  setWorkflowName: (name: string) => void;
  setRecursionLimit: (limit: number) => void;
  onNodesChange: (changes: NodeChange<Node<StudioNodeData>>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  selectNode: (nodeId: string | null) => void;
  addNode: (type: WorkflowNodeType) => void;
  deleteNode: (nodeId: string) => void;
  updateNodeData: (nodeId: string, patch: Partial<StudioNodeData>) => void;
  loadTemplateById: (workflowId: string) => void;
  loadDefinition: (def: WorkflowDefinition) => void;
  exportDefinition: () => { ok: true; definition: WorkflowDefinition } | { ok: false; error: string };
  setNodeStatus: (nodeId: string, status: NodeRunStatus) => void;
  resetRunOverlay: () => void;
  setRunSummary: (tokens: number, costUsd: number, running: boolean) => void;
}

export const LAST_WORKFLOW_STORAGE_KEY = "orchestrator_last_workflow_id";

export const useWorkflowStore = create<WorkflowStoreState>((set, get) => ({
  activeWorkflowId: "starter",
  workflowName: "Customer Support Multi-Agent Flow",
  recursionLimit: STARTER_WORKFLOW.execution_config.recursion_limit,
  nodes: toReactFlowNodes(STARTER_WORKFLOW),
  edges: toReactFlowEdges(STARTER_WORKFLOW),
  selectedNodeId: null,
  nodeStatuses: {},
  totalTokens: 0,
  totalCostUsd: 0,
  isRunning: false,
  lastError: null,

  setWorkflowName: (workflowName) => set({ workflowName }),
  setRecursionLimit: (limit) =>
    set({ recursionLimit: Math.max(1, Math.min(50, Math.round(limit))) }),

  onNodesChange: (changes) =>
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) })),

  onEdgesChange: (changes) =>
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges) })),

  onConnect: (connection) =>
    set((state) => ({
      edges: addEdge(
        {
          ...connection,
          id: `e_${connection.source}_${connection.target}_${Date.now().toString(36)}`,
          animated: true,
          style: { stroke: "#475569", strokeWidth: 2 },
        },
        state.edges,
      ),
    })),

  selectNode: (selectedNodeId) => set({ selectedNodeId }),

  addNode: (type) => {
    const id = `${type}_${Date.now().toString(36).slice(-4)}`;
    const defaults: Record<WorkflowNodeType, StudioNodeData> = {
      start: { label: "Start", input_schema: {} },
      end: { label: "End", output_mapping: {} },
      supervisor: {
        label: "Supervisor",
        provider: "openai",
        model: "gpt-4o-mini",
        temperature: 0.2,
        system_prompt: "Coordinate specialist agents.",
        routing_strategy: "llm_router",
        managed_agent_ids: [],
      },
      agent: {
        label: "Specialist Agent",
        provider: "openai",
        model: "gpt-4o-mini",
        temperature: 0.2,
        system_prompt: "You are a helpful specialist AI agent.",
        tool_ids: [],
        mcp_server_ids: [],
        rag_enabled: false,
        rag_top_k: 5,
      },
      tool: {
        label: "MCP / OpenAPI Tool",
        tool_kind: "mcp",
        static_params: {},
      },
      router: {
        label: "Router",
        mode: "llm",
        provider: "openai",
        model: "gpt-4o-mini",
        routes: [],
      },
      human_approval: {
        label: "Human Approval",
        prompt_message: "Approve or edit the agent output.",
        timeout_seconds: 86400,
        allowed_actions: ["approve", "reject", "edit"],
      },
    };

    const count = get().nodes.length;
    const newNode: Node<StudioNodeData> = {
      id,
      type,
      position: { x: 180 + (count % 4) * 220, y: 120 + Math.floor(count / 4) * 140 },
      data: defaults[type],
    };
    set((state) => ({ nodes: [...state.nodes, newNode], selectedNodeId: id }));
  },

  deleteNode: (nodeId) =>
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== nodeId),
      edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
    })),

  updateNodeData: (nodeId, patch) =>
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === nodeId ? { ...node, data: { ...node.data, ...patch } } : node,
      ),
    })),

  loadTemplateById: (workflowId) => {
    const resolvedId = workflowId in WORKFLOW_TEMPLATES ? workflowId : "starter";
    const tpl = WORKFLOW_TEMPLATES[resolvedId]!;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LAST_WORKFLOW_STORAGE_KEY, resolvedId);
    }
    set({
      activeWorkflowId: resolvedId,
      workflowName: tpl.name,
      recursionLimit: tpl.definition.execution_config.recursion_limit,
      nodes: toReactFlowNodes(tpl.definition),
      edges: toReactFlowEdges(tpl.definition),
      selectedNodeId: null,
      nodeStatuses: {},
      totalTokens: 0,
      totalCostUsd: 0,
      lastError: null,
    });
  },

  loadDefinition: (def) =>
    set({
      recursionLimit: def.execution_config.recursion_limit,
      nodes: toReactFlowNodes(def),
      edges: toReactFlowEdges(def),
      selectedNodeId: null,
      nodeStatuses: {},
      lastError: null,
    }),

  exportDefinition: () => {
    const state = get();
    const candidate = {
      schema_version: "1.0" as const,
      execution_config: {
        recursion_limit: state.recursionLimit,
        timeout_seconds: 300,
      },
      variables: {},
      nodes: state.nodes.map((n) => ({
        id: n.id,
        type: (n.type || "agent") as WorkflowNodeType,
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
        data: n.data,
      })),
      edges: state.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle ?? null,
        target_handle: e.targetHandle ?? null,
        condition: typeof e.label === "string" ? e.label : null,
      })),
    };

    const parsed = WorkflowDefinitionSchema.safeParse(candidate);
    if (!parsed.success) {
      return {
        ok: false,
        error: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
      };
    }
    return { ok: true, definition: parsed.data };
  },

  setNodeStatus: (nodeId, status) =>
    set((state) => ({
      nodeStatuses: { ...state.nodeStatuses, [nodeId]: status },
    })),

  resetRunOverlay: () => set({ nodeStatuses: {}, totalTokens: 0, totalCostUsd: 0, lastError: null }),

  setRunSummary: (totalTokens, totalCostUsd, isRunning) =>
    set({ totalTokens, totalCostUsd, isRunning }),
}));
