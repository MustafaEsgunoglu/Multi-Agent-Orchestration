import Link from "next/link";
import { ArrowRight, Bot, Database, ShieldCheck, Workflow } from "lucide-react";

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
            Design, test, and deploy multi-agent workflows backed by PostgreSQL RLS, AES-256-GCM
            BYOK vaults, lightweight PyMuPDF + pgvector RAG, and native MCP integrations.
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
          { icon: Database, label: "Unified Low-RAM Store", value: "Postgres 16 + pgvector" },
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

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Workspace Workflows
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
