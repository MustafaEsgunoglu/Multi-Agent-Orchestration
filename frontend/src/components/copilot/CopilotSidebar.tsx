"use client";

import { Send, Sparkles } from "lucide-react";
import { useState } from "react";

import { generateWorkflowWithCopilot } from "@/lib/api";
import { useWorkflowStore } from "@/stores/workflowStore";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export function CopilotSidebar() {
  const { exportDefinition, loadDefinition } = useWorkflowStore();
  const [prompt, setPrompt] = useState("");
  const [copilotModel, setCopilotModel] = useState("deepseek-chat");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Describe the multi-agent workflow you want to build (e.g. 'Build a support triage supervisor with RAG researcher and human approval').",
    },
  ]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setPrompt("");
    setLoading(true);

    try {
      const current = exportDefinition();
      const res = await generateWorkflowWithCopilot({
        prompt: trimmed,
        provider: "deepseek",
        model: copilotModel,
        existing_workflow: current.ok ? current.definition : undefined,
      });
      loadDefinition(res.workflow);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `${res.explanation}\n\nLoaded ${res.workflow.nodes.length} nodes (${res.attempts} attempt, ${res.total_tokens} tokens).`,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Copilot request failed";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Backend Copilot unavailable (${msg}). Sign in and start FastAPI on :8000 to generate live graphs.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="flex h-full w-80 flex-col border-r border-slate-800 bg-slate-950/95">
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-amber-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
            AI Copilot
          </h2>
        </div>
        <select
          value={copilotModel}
          onChange={(e) => setCopilotModel(e.target.value)}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-200 focus:border-sky-500 focus:outline-none"
        >
          <option value="deepseek-chat">deepseek-chat</option>
          <option value="deepseek-reasoner">deepseek-reasoner</option>
        </select>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4 text-xs">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`whitespace-pre-wrap rounded-lg px-3 py-2 leading-relaxed ${
              m.role === "user"
                ? "ml-6 bg-sky-600/20 text-sky-100 border border-sky-500/30"
                : "mr-4 bg-slate-900 text-slate-300 border border-slate-800"
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-800 p-3">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe your workflow..."
            className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-sky-600 text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
    </aside>
  );
}
