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
import { CheckCircle2, Play, Plus, RotateCcw, Save, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { WorkflowNodeCard } from "@/components/canvas/WorkflowNodeCard";
import {
  HumanApprovalModal,
  PendingApprovalState,
} from "@/components/panels/HumanApprovalModal";
import {
  createWorkflow,
  executeWorkflowOnBackend,
  getStoredToken,
  resumeDevWorkflowRun,
  resumeExecutionRun,
  streamDevWorkflowRun,
  updateWorkflow,
  validateWorkflowOnBackend,
} from "@/lib/api";
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

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function WorkflowCanvas() {
  const router = useRouter();
  const {
    activeWorkflowId,
    workflowName,
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    selectNode,
    addNode,
    exportDefinition,
    loadSavedWorkflow,
    setNodeStatus,
    resetRunOverlay,
    setRunSummary,
    totalTokens,
    totalCostUsd,
    isRunning,
  } = useWorkflowStore();

  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<PendingApprovalState | null>(null);
  const [livePrompt, setLivePrompt] = useState("Merhaba, bu akışı kısaca test et.");
  const [liveOutput, setLiveOutput] = useState<string | null>(null);

  function openApprovalModal(
    mode: "saved" | "dev",
    runOrThreadId: string,
    intr: Record<string, unknown>,
  ) {
    const allowedRaw = Array.isArray(intr.allowed_actions)
      ? (intr.allowed_actions as ("approve" | "reject" | "edit")[])
      : (["approve", "reject", "edit"] as ("approve" | "reject" | "edit")[]);
    setPendingApproval({
      mode,
      runOrThreadId,
      nodeId: String(intr.node_id || "human_approval"),
      label: String(intr.label || "Human Approval"),
      promptMessage: String(
        intr.prompt_message || "Review the agent output and approve or reject to continue.",
      ),
      lastOutput: String(intr.last_output || ""),
      allowedActions: allowedRaw,
    });
  }

  async function handleApprovalDecision(
    action: "approve" | "reject" | "edit",
    editedOutput?: string,
  ) {
    if (!pendingApproval) return;
    setResuming(true);
    try {
      if (pendingApproval.mode === "saved") {
        const resumed = await resumeExecutionRun(pendingApproval.runOrThreadId, {
          action,
          edited_output: editedOutput,
        });
        for (const step of resumed.steps ?? []) {
          setNodeStatus(step.node_id, step.status === "failed" ? "failed" : "completed");
        }
        setNodeStatus(pendingApproval.nodeId, "completed");
        const out = resumed.output_payload?.result;
        if (out) setLiveOutput(String(out));
        setRunSummary(resumed.total_tokens, Number(resumed.estimated_cost_usd), false);
        setToast({
          kind: "ok",
          text: `Resumed (${action}) & completed run #${resumed.id.slice(0, 8)}!`,
        });
        setPendingApproval(null);
      } else {
        const exported = exportDefinition();
        if (!exported.ok) {
          setToast({ kind: "err", text: exported.error });
          return;
        }
        const resumed = await resumeDevWorkflowRun({
          definition: exported.definition,
          thread_id: pendingApproval.runOrThreadId,
          action,
          edited_output: editedOutput,
        });
        for (const step of resumed.step_metrics ?? []) {
          setNodeStatus(step.node_id, "completed");
        }
        setNodeStatus(pendingApproval.nodeId, "completed");
        const out = resumed.output?.result;
        if (out) setLiveOutput(String(out));
        setRunSummary(resumed.total_tokens, Number(resumed.total_cost_usd), false);
        setToast({
          kind: "ok",
          text: `Resumed (${action}) & completed: ${resumed.total_tokens} tokens ($${Number(resumed.total_cost_usd).toFixed(6)})`,
        });
        setPendingApproval(null);
      }
    } catch (err) {
      setToast({
        kind: "err",
        text: err instanceof Error ? err.message : "Failed to resume approval",
      });
    } finally {
      setResuming(false);
    }
  }

  async function handleSave() {
    if (!getStoredToken()) {
      setToast({
        kind: "err",
        text: "Sign in first (top-right Sign In button) to save workflows to Supabase.",
      });
      return;
    }
    const exported = exportDefinition();
    if (!exported.ok) {
      setToast({ kind: "err", text: `Cannot save invalid graph: ${exported.error}` });
      return;
    }
    setSaving(true);
    try {
      if (UUID_REGEX.test(activeWorkflowId)) {
        const updated = await updateWorkflow(activeWorkflowId, {
          name: workflowName.trim() || "Untitled Workflow",
          definition: exported.definition,
        });
        setToast({
          kind: "ok",
          text: `Saved '${updated.name}' (v${updated.version}) to Supabase!`,
        });
      } else {
        const created = await createWorkflow({
          name: workflowName.trim() || "Untitled Workflow",
          definition: exported.definition,
        });
        loadSavedWorkflow({
          id: created.id,
          name: created.name,
          definition: created.definition,
        });
        router.replace(`/studio/${created.id}`);
        setToast({
          kind: "ok",
          text: `Created & saved '${created.name}' in Supabase!`,
        });
      }
    } catch (err) {
      setToast({
        kind: "err",
        text: err instanceof Error ? err.message : "Failed to save workflow",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleLiveRun() {
    const exported = exportDefinition();
    if (!exported.ok) {
      setToast({ kind: "err", text: exported.error });
      return;
    }
    resetRunOverlay();
    setLiveOutput(null);
    setRunSummary(0, 0, true);

    // If signed in and working on a saved Supabase workflow, persist run & steps to DB!
    if (getStoredToken() && UUID_REGEX.test(activeWorkflowId)) {
      setToast({ kind: "ok", text: "Executing saved workflow via DeepSeek & recording to Supabase..." });
      try {
        const run = await executeWorkflowOnBackend(activeWorkflowId, { prompt: livePrompt });
        for (const step of run.steps ?? []) {
          setNodeStatus(step.node_id, step.status === "failed" ? "failed" : "completed");
        }
        if (run.status === "waiting_for_approval" && run.interrupt_payload) {
          const pausedId = String(run.interrupt_payload.node_id || "");
          if (pausedId) setNodeStatus(pausedId, "waiting_approval");
          setLiveOutput(String(run.interrupt_payload.last_output || ""));
          openApprovalModal("saved", run.id, run.interrupt_payload);
          setToast({
            kind: "ok",
            text: `Saved run #${run.id.slice(0, 8)} paused at Human Approval (${pausedId}).`,
          });
        } else {
          const out = run.output_payload?.result;
          if (out) setLiveOutput(String(out));
          setToast({
            kind: "ok",
            text: `Saved run #${run.id.slice(0, 8)} completed: ${run.total_tokens} tokens ($${Number(run.estimated_cost_usd).toFixed(6)}) — visible in Execution Runs!`,
          });
        }
        setRunSummary(run.total_tokens, Number(run.estimated_cost_usd), false);
        return;
      } catch (err) {
        setToast({
          kind: "err",
          text: err instanceof Error ? err.message : "Live execution failed",
        });
        setRunSummary(0, 0, false);
        return;
      }
    }

    setToast({ kind: "ok", text: "Running live LangGraph workflow via DeepSeek..." });

    let latestTokens = 0;
    let latestCost = 0;
    try {
      await streamDevWorkflowRun(exported.definition, { prompt: livePrompt }, (event, data) => {
        if (event === "node_completed") {
          const nodeId = String(data.node_id || "");
          if (nodeId) setNodeStatus(nodeId, "completed");
          if (typeof data.total_tokens === "number") latestTokens = data.total_tokens;
          if (typeof data.total_cost_usd === "number") latestCost = data.total_cost_usd;
          if (typeof data.last_output === "string" && data.last_output) {
            setLiveOutput(data.last_output);
          }
          setRunSummary(latestTokens, latestCost, true);
        } else if (event === "human_approval_required") {
          const intr = data.interrupt as Record<string, unknown> | undefined;
          const threadId = String(data.thread_id || "");
          const nodeId = String(intr?.node_id || "");
          if (nodeId) setNodeStatus(nodeId, "waiting_approval");
          if (intr && threadId) {
            openApprovalModal("dev", threadId, intr);
          }
          setToast({
            kind: "ok",
            text: `Paused at Human Approval (${nodeId}) — waiting for your decision.`,
          });
        } else if (event === "run_completed") {
          const out = data.output as Record<string, unknown> | undefined;
          if (out?.result) setLiveOutput(String(out.result));
          latestTokens = Number(data.total_tokens ?? latestTokens);
          latestCost = Number(data.total_cost_usd ?? latestCost);
          setToast({
            kind: "ok",
            text: `Live run completed: ${latestTokens} tokens ($${latestCost.toFixed(6)})`,
          });
        } else if (event === "run_failed") {
          setToast({ kind: "err", text: `Run failed: ${String(data.error || "Unknown error")}` });
        }
      });
    } catch (err) {
      setToast({
        kind: "err",
        text: err instanceof Error ? err.message : "Live execution failed",
      });
    } finally {
      setRunSummary(latestTokens, latestCost, false);
    }
  }

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
            disabled={saving}
            onClick={handleSave}
            className="inline-flex items-center gap-1.5 rounded-md border border-sky-500/50 bg-sky-950/50 px-3 py-1.5 text-xs font-semibold text-sky-200 hover:bg-sky-900/60 disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? "Saving..." : "Save"}
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
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" />
            Simulate
          </button>

          <button
            type="button"
            disabled={isRunning}
            onClick={handleLiveRun}
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
          >
            <Zap className="h-3.5 w-3.5" />
            {isRunning ? "Running..." : "Run Live (DeepSeek)"}
          </button>
        </div>
      </div>

      {/* Live Prompt Input Strip */}
      <div className="flex items-center gap-2 border-b border-slate-800/80 bg-slate-950/60 px-4 py-1.5">
        <span className="text-[11px] font-medium text-slate-400">Live Input:</span>
        <input
          type="text"
          value={livePrompt}
          onChange={(e) => setLivePrompt(e.target.value)}
          placeholder="Enter prompt for live LangGraph execution..."
          className="flex-1 rounded border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
        />
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

      {liveOutput && (
        <div className="max-h-36 overflow-y-auto border-b border-slate-800 bg-slate-900/90 px-4 py-2 text-xs text-slate-200">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
            Live Output (DeepSeek)
          </div>
          <div className="whitespace-pre-wrap leading-relaxed">{liveOutput}</div>
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

      {pendingApproval && (
        <HumanApprovalModal
          pending={pendingApproval}
          submitting={resuming}
          onDecision={(action, edited) => void handleApprovalDecision(action, edited)}
          onClose={() => setPendingApproval(null)}
        />
      )}
    </div>
  );
}
