"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Bot,
  Crown,
  Flag,
  GitBranch,
  Play,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { WorkflowNodeType } from "@/schemas/workflow";
import { NodeRunStatus, StudioNodeData, useWorkflowStore } from "@/stores/workflowStore";

const NODE_META: Record<
  WorkflowNodeType,
  { title: string; accent: string; border: string; icon: React.ComponentType<{ className?: string }> }
> = {
  start: { title: "START", accent: "text-emerald-400", border: "border-emerald-500/50", icon: Play },
  end: { title: "END", accent: "text-rose-400", border: "border-rose-500/50", icon: Flag },
  supervisor: { title: "SUPERVISOR", accent: "text-amber-400", border: "border-amber-500/50", icon: Crown },
  agent: { title: "AGENT", accent: "text-sky-400", border: "border-sky-500/50", icon: Bot },
  tool: { title: "TOOL", accent: "text-violet-400", border: "border-violet-500/50", icon: Wrench },
  router: { title: "ROUTER", accent: "text-cyan-400", border: "border-cyan-500/50", icon: GitBranch },
  human_approval: {
    title: "HUMAN GATE",
    accent: "text-fuchsia-400",
    border: "border-fuchsia-500/50",
    icon: ShieldCheck,
  },
};

const STATUS_BADGE: Record<NodeRunStatus, { label: string; cls: string }> = {
  idle: { label: "", cls: "" },
  running: { label: "Running", cls: "bg-sky-500/20 text-sky-300 border-sky-500/40 animate-pulse" },
  completed: { label: "Done", cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  waiting_approval: {
    label: "Awaiting Approval",
    cls: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40 animate-pulse",
  },
  failed: { label: "Failed", cls: "bg-rose-500/20 text-rose-300 border-rose-500/40" },
};

export function WorkflowNodeCard({ id, type, data, selected }: NodeProps) {
  const nodeType = (type || "agent") as WorkflowNodeType;
  const meta = NODE_META[nodeType] || NODE_META.agent;
  const Icon = meta.icon;
  const typedData = data as StudioNodeData;
  const status = useWorkflowStore((s) => s.nodeStatuses[id] ?? "idle");
  const badge = STATUS_BADGE[status];

  return (
    <div
      className={`min-w-[210px] max-w-[250px] rounded-xl border bg-slate-900/95 px-3.5 py-3 shadow-xl transition-all ${
        selected ? "ring-2 ring-sky-400 border-sky-400" : meta.border
      }`}
    >
      {nodeType !== "start" && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-2 !border-slate-900 !bg-slate-400"
        />
      )}

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Icon className={`h-4 w-4 ${meta.accent}`} />
          <span className={`text-[10px] font-semibold tracking-wider ${meta.accent}`}>
            {meta.title}
          </span>
        </div>
        {status !== "idle" && (
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${badge.cls}`}>
            {badge.label}
          </span>
        )}
      </div>

      <div className="mt-1.5 truncate text-sm font-semibold text-slate-100">
        {typedData.label || id}
      </div>

      {typedData.model && (
        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-400">
          <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {String(typedData.provider || "openai")}
          </span>
          <span className="truncate font-mono">{String(typedData.model)}</span>
        </div>
      )}

      {typedData.rag_enabled && (
        <div className="mt-1.5 inline-flex items-center rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
          pgvector RAG (top-{String(typedData.rag_top_k ?? 5)})
        </div>
      )}

      {nodeType !== "end" && (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !border-2 !border-slate-900 !bg-sky-400"
        />
      )}
    </div>
  );
}
