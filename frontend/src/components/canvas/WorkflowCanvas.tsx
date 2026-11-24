"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type NodeTypes,
} from "@xyflow/react";
import { CheckCircle2, Play, Plus, RotateCcw } from "lucide-react";
import { useState } from "react";

import { WorkflowNodeCard } from "@/components/canvas/WorkflowNodeCard";
import { validateWorkflowOnBackend } from "@/lib/api";
import { WorkflowNodeType } from "@/schemas/workflow";
import { useWorkflowStore } from "@/stores/workflowStore";

const nodeTypes: NodeTypes = {
  start: WorkflowNodeCard,
  end: WorkflowNodeCard,
  supervisor: WorkflowNodeCard,
  agent: WorkflowNodeCard,
  tool: WorkflowNodeCard,
  router: WorkflowNodeCard,
  human_approval: WorkflowNodeCard,
};

const PALETTE_ITEMS: { type: WorkflowNodeType; label: string }[] = [
  { type: "supervisor", label: "Supervisor" },
  { type: "agent", label: "Agent" },
  { type: "tool", label: "Tool" },
  { type: "router", label: "Router" },
  { type: "human_approval", label: "Human Gate" },
];

export function WorkflowCanvas() {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    selectNode,
    addNode,
    exportDefinition,
    setNodeStatus,
    resetRunOverlay,
    setRunSummary,
    totalTokens,
    totalCostUsd,
    isRunning,
  } = useWorkflowStore();

  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function handleValidate() {
    const exported = exportDefinition();
    if (!exported.ok) {
      setToast({ kind: "err", text: `Zod error: ${exported.error}` });
      return;
    }
    try {
      const res = await validateWorkflowOnBackend(exported.definition);
      setToast({
        kind: "ok",
        text: `Valid graph (${res.node_count} nodes, ${res.edge_count} edges, limit=${res.recursion_limit})`,
      });
    } catch {
      setToast({
        kind: "ok",
        text: `Zod schema valid (${exported.definition.nodes.length} nodes). Start backend API for server-side check.`,
      });
    }
  }

  async function handleDryRunPreview() {
    const exported = exportDefinition();
    if (!exported.ok) {
      setToast({ kind: "err", text: exported.error });
      return;
    }
    resetRunOverlay();
    setRunSummary(0, 0, true);
    setToast({ kind: "ok", text: "Simulating live LangGraph execution overlay..." });

    let tokens = 0;
    let cost = 0;
    for (const node of exported.definition.nodes) {
      setNodeStatus(node.id, node.type === "human_approval" ? "waiting_approval" : "running");
      await new Promise((r) => setTimeout(r, 420));
      if (node.type === "agent" || node.type === "supervisor") {
        tokens += 320;
        cost = Number((cost + 0.0012).toFixed(6));
      }
      setNodeStatus(node.id, "completed");
      setRunSummary(tokens, cost, true);
    }
    setRunSummary(tokens, cost, false);
    setToast({ kind: "ok", text: `Preview completed: ${tokens} tokens ($${cost.toFixed(4)})` });
  }

  return (
    <div className="relative flex h-full flex-1 flex-col bg-[#0b0f19]">
      {/* Studio Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-950/90 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-medium text-slate-400">Add Node:</span>
          {PALETTE_ITEMS.map((item) => (
            <button
              key={item.type}
              type="button"
              onClick={() => addNode(item.type)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-sky-500 hover:text-sky-300"
            >
              <Plus className="h-3.5 w-3.5" />
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-3 rounded-md border border-slate-800 bg-slate-900 px-3 py-1 text-xs text-slate-300 md:flex">
            <span>Tokens: {totalTokens}</span>
            <span className="text-emerald-400">Est. ${totalCostUsd.toFixed(4)}</span>
          </div>

          <button
            type="button"
            onClick={resetRunOverlay}
            title="Reset live status"
            className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={handleValidate}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-emerald-500 hover:text-emerald-300"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Validate JSON
          </button>

          <button
            type="button"
            disabled={isRunning}
            onClick={handleDryRunPreview}
            className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" />
            {isRunning ? "Running..." : "Test Flow"}
          </button>
        </div>
      </div>

      {toast && (
        <div
          className={`border-b px-4 py-1.5 text-xs ${
            toast.kind === "ok"
              ? "border-emerald-500/30 bg-emerald-950/50 text-emerald-300"
              : "border-rose-500/30 bg-rose-950/50 text-rose-300"
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* React Flow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => selectNode(node.id)}
          onPaneClick={() => selectNode(null)}
          deleteKeyCode={["Backspace", "Delete"]}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
          <Controls />
          <MiniMap nodeColor="#38bdf8" maskColor="rgba(11, 15, 25, 0.75)" />
        </ReactFlow>
      </div>
    </div>
  );
}
