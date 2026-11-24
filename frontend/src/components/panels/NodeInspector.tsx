"use client";

import { SlidersHorizontal, Trash2 } from "lucide-react";

import { useWorkflowStore } from "@/stores/workflowStore";

export const PROVIDER_MODELS: Record<string, { id: string; label: string }[]> = {
  deepseek: [
    { id: "deepseek-chat", label: "deepseek-chat (V3)" },
    { id: "deepseek-reasoner", label: "deepseek-reasoner (R1)" },
  ],
  openai: [
    { id: "gpt-4o-mini", label: "gpt-4o-mini" },
    { id: "gpt-4o", label: "gpt-4o" },
    { id: "o3-mini", label: "o3-mini" },
    { id: "gpt-4.1-mini", label: "gpt-4.1-mini" },
  ],
  anthropic: [
    { id: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet" },
    { id: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
    { id: "claude-3-7-sonnet-20250219", label: "Claude 3.7 Sonnet" },
  ],
  google: [
    { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
    { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
  ],
  groq: [
    { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B" },
    { id: "deepseek-r1-distill-llama-70b", label: "DeepSeek R1 Distill 70B" },
  ],
  mistral: [
    { id: "mistral-large-latest", label: "Mistral Large" },
    { id: "mistral-small-latest", label: "Mistral Small" },
  ],
  openrouter: [
    { id: "deepseek/deepseek-chat", label: "DeepSeek Chat (OR)" },
    { id: "anthropic/claude-3.5-sonnet", label: "Claude 3.5 Sonnet (OR)" },
    { id: "openai/gpt-4o-mini", label: "GPT-4o Mini (OR)" },
  ],
};

export function NodeInspector() {
  const {
    nodes,
    selectedNodeId,
    updateNodeData,
    deleteNode,
    recursionLimit,
    setRecursionLimit,
  } = useWorkflowStore();

  const selected = nodes.find((n) => n.id === selectedNodeId);
  const currentProvider = String(selected?.data.provider || "deepseek");
  const currentModel = String(selected?.data.model || "deepseek-chat");
  const presetModels = PROVIDER_MODELS[currentProvider] ?? [];
  const isCustomModel =
    presetModels.length > 0 && !presetModels.some((m) => m.id === currentModel);

  return (
    <aside className="flex h-full w-80 flex-col border-l border-slate-800 bg-slate-950/95">
      <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
        <SlidersHorizontal className="h-4 w-4 text-sky-400" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
          {selected ? `Inspector — ${selected.type}` : "Workflow Guardrails"}
        </h2>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-xs">
        {!selected ? (
          <div className="space-y-4">
            <p className="text-slate-400">
              Select any node on the canvas to configure its LLM provider, model, prompt, RAG, MCP
              tools, or Human-in-the-Loop policy.
            </p>
            <div>
              <label className="mb-1 block font-medium text-slate-300">
                LangGraph Recursion Limit (1–50)
              </label>
              <input
                type="number"
                min={1}
                max={50}
                value={recursionLimit}
                onChange={(e) => setRecursionLimit(Number(e.target.value))}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-slate-100 focus:border-sky-500 focus:outline-none"
              />
              <p className="mt-1 text-[11px] text-slate-500">
                Enforced strictly by the backend compiler to prevent infinite agent loops.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block font-medium text-slate-300">Node ID</label>
              <input
                type="text"
                readOnly
                value={selected.id}
                className="w-full rounded-md border border-slate-800 bg-slate-900/60 px-3 py-1.5 font-mono text-slate-400"
              />
            </div>

            <div>
              <label className="mb-1 block font-medium text-slate-300">Label</label>
              <input
                type="text"
                value={selected.data.label || ""}
                onChange={(e) => updateNodeData(selected.id, { label: e.target.value })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-slate-100 focus:border-sky-500 focus:outline-none"
              />
            </div>

            {(selected.type === "agent" ||
              selected.type === "supervisor" ||
              selected.type === "router") && (
              <>
                <div className="space-y-2.5">
                  <div>
                    <label className="mb-1 block font-medium text-slate-300">Provider</label>
                    <select
                      value={currentProvider}
                      onChange={(e) => {
                        const nextProvider = e.target.value;
                        const firstModel = PROVIDER_MODELS[nextProvider]?.[0]?.id ?? currentModel;
                        updateNodeData(selected.id, {
                          provider: nextProvider,
                          model: firstModel,
                        });
                      }}
                      className="w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 focus:border-sky-500 focus:outline-none"
                    >
                      <option value="deepseek">DeepSeek</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="google">Google Gemini</option>
                      <option value="groq">Groq</option>
                      <option value="mistral">Mistral</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block font-medium text-slate-300">Model</label>
                    <select
                      value={isCustomModel ? "__custom__" : currentModel}
                      onChange={(e) => {
                        if (e.target.value === "__custom__") {
                          updateNodeData(selected.id, { model: "" });
                        } else {
                          updateNodeData(selected.id, { model: e.target.value });
                        }
                      }}
                      className="w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-slate-100 focus:border-sky-500 focus:outline-none"
                    >
                      {presetModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                      <option value="__custom__">Custom model ID...</option>
                    </select>

                    {isCustomModel && (
                      <input
                        type="text"
                        placeholder="e.g. deepseek-chat"
                        value={currentModel}
                        onChange={(e) => updateNodeData(selected.id, { model: e.target.value })}
                        className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-slate-100 focus:border-sky-500 focus:outline-none"
                      />
                    )}
                  </div>
                </div>

                {selected.type !== "router" && (
                  <div>
                    <label className="mb-1 block font-medium text-slate-300">System Prompt</label>
                    <textarea
                      rows={5}
                      value={String(selected.data.system_prompt || "")}
                      onChange={(e) =>
                        updateNodeData(selected.id, { system_prompt: e.target.value })
                      }
                      className="w-full rounded-md border border-slate-700 bg-slate-900 p-2.5 text-slate-100 focus:border-sky-500 focus:outline-none"
                    />
                  </div>
                )}
              </>
            )}

            {selected.type === "agent" && (
              <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                <label className="flex items-center justify-between font-medium text-slate-200">
                  <span>Enable pgvector RAG</span>
                  <input
                    type="checkbox"
                    checked={Boolean(selected.data.rag_enabled)}
                    onChange={(e) =>
                      updateNodeData(selected.id, { rag_enabled: e.target.checked })
                    }
                    className="h-4 w-4 accent-emerald-500"
                  />
                </label>
                {selected.data.rag_enabled && (
                  <div className="mt-2">
                    <label className="mb-1 block text-[11px] text-slate-400">Top-K Chunks</label>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={Number(selected.data.rag_top_k ?? 5)}
                      onChange={(e) =>
                        updateNodeData(selected.id, { rag_top_k: Number(e.target.value) })
                      }
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2.5 py-1 text-slate-100"
                    />
                  </div>
                )}
              </div>
            )}

            {selected.type === "human_approval" && (
              <div>
                <label className="mb-1 block font-medium text-slate-300">Approval Prompt</label>
                <textarea
                  rows={3}
                  value={String(selected.data.prompt_message || "")}
                  onChange={(e) =>
                    updateNodeData(selected.id, { prompt_message: e.target.value })
                  }
                  className="w-full rounded-md border border-slate-700 bg-slate-900 p-2.5 text-slate-100"
                />
              </div>
            )}

            <div className="border-t border-slate-800 pt-4">
              <button
                type="button"
                onClick={() => deleteNode(selected.id)}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-xs font-medium text-rose-300 transition hover:bg-rose-900/50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Node
              </button>
              <p className="mt-1.5 text-center text-[11px] text-slate-500">
                Or press Delete / Backspace while selected
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
