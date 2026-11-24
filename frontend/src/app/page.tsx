"use client";

import { ArrowRight, Bot, Database, ShieldCheck, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  deleteWorkflowRecord,
  getStoredToken,
  listWorkflows,
  WorkflowRecord,
} from "@/lib/api";

const TEMPLATES = [
  {
    id: "starter",
    name: "Customer Support Multi-Agent Flow",
    description:
      "Lead Supervisor routing between a pgvector RAG Researcher and an MCP Action Agent with Human-in-the-Loop approval.",
    nodes: 6,
  },
  {
    id: "research-pipeline",
    name: "Document Analysis & Synthesis",
    description:
      "PyMuPDF + pgvector document retrieval pipeline with cost guardrails and structured JSON output.",
    nodes: 4,
  },
];

export default function DashboardPage() {
  const [savedWorkflows, setSavedWorkflows] = useState<WorkflowRecord[]>([]);
  const [signedIn, setSignedIn] = useState(false);

  async function refreshWorkflows() {
    if (!getStoredToken()) {
      setSignedIn(false);
      setSavedWorkflows([]);
      return;
    }
    setSignedIn(true);
    try {
      const rows = await listWorkflows();
      setSavedWorkflows(rows);
    } catch {
      setSavedWorkflows([]);
    }
  }

  useEffect(() => {
    void refreshWorkflows();
  }, []);

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    await deleteWorkflowRecord(id);
    await refreshWorkflows();
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 p-8">
      <section className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-950 to-sky-950/30 p-8 md:flex-row md:items-center">
        <div className="space-y-2">
          <span className="inline-block rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-0.5 text-xs font-medium text-sky-300">
            Multi-Tenant LangGraph SaaS
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Visual Multi-Agent Orchestration Studio
          </h1>
          <p className="max-w-2xl text-sm text-slate-400">
            Design, test, and deploy multi-agent workflows backed by Supabase PostgreSQL RLS,
            AES-256-GCM BYOK vaults, lightweight PyMuPDF + pgvector RAG, and native MCP integrations.
          </p>
        </div>

        <Link
          href="/studio/starter"
          className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500"
        >
          Open Studio
          <ArrowRight className="h-4 w-4" />
        </Link>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        {[
          { icon: Workflow, label: "Canonical Graph Schema", value: "Zod + Pydantic v2" },
          { icon: Bot, label: "Orchestration Engine", value: "LangGraph + LiteLLM" },
          { icon: Database, label: "Unified Low-RAM Store", value: "Supabase Postgres + pgvector" },
          { icon: ShieldCheck, label: "Security Isolation", value: "RLS + AES-256-GCM" },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
          >
            <card.icon className="h-5 w-5 text-sky-400" />
            <div className="mt-3 text-xs text-slate-400">{card.label}</div>
            <div className="mt-0.5 text-sm font-semibold text-slate-100">{card.value}</div>
          </div>
        ))}
      </section>

      {signedIn && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-emerald-400">
              Your Saved Workflows (Supabase)
            </h2>
            <span className="text-xs text-slate-500">{savedWorkflows.length} saved</span>
          </div>

          {savedWorkflows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/30 p-6 text-center text-xs text-slate-400">
              No saved workflows yet. Open a template below and click <strong>Save</strong> in the
              Studio!
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {savedWorkflows.map((wf) => (
                <Link
                  key={wf.id}
                  href={`/studio/${wf.id}`}
                  className="group rounded-xl border border-emerald-500/30 bg-slate-900/70 p-5 transition hover:border-emerald-400"
                >
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-slate-100 group-hover:text-emerald-300">
                      {wf.name}
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
                        v{wf.version} · {wf.definition.nodes.length} nodes
                      </span>
                      <button
                        type="button"
                        onClick={(e) => void handleDelete(e, wf.id)}
                        title="Delete workflow"
                        className="rounded p-1 text-slate-500 hover:bg-rose-950/60 hover:text-rose-400"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-slate-400">
                    {wf.description || "Persisted multi-agent workflow under PostgreSQL RLS."}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Starter Templates
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {TEMPLATES.map((tpl) => (
            <Link
              key={tpl.id}
              href={`/studio/${tpl.id}`}
              className="group rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-sky-500/60"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-100 group-hover:text-sky-300">
                  {tpl.name}
                </h3>
                <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                  {tpl.nodes} nodes
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">{tpl.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
