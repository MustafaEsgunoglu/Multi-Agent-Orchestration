# AGENTS.md — Multi-Agent No-Code Orchestration Platform

## 1. Project Vision & Locked Architecture
We are building a **Multi-Tenant Cloud SaaS** no-code platform (inspired by Skymod) that enables users to visually design, test, and deploy multi-agent AI workflows.

**Strictly Locked Tech Stack (Do NOT introduce unapproved heavy services):**
- **Frontend:** Next.js 15 (App Router), TypeScript (Strict), Tailwind CSS, shadcn/ui, **React Flow** (`@xyflow/react`), Zustand (canvas state), Zod (schema validation).
- **Backend API:** Python 3.12+, **FastAPI** (async), Pydantic v2, SQLAlchemy 2.0 (async) + Alembic.
- **Orchestration Engine:** **LangGraph** (`StateGraph` dynamically compiled from canvas JSON) + PostgresSaver checkpointer (for Human-in-the-Loop persistence).
- **Background Workers:** **Celery** + **Redis** (async document ingestion & long-running workflow executions).
- **Database & RAG (Low-Cost Unified Store):** **PostgreSQL 16 + pgvector** with strict **Row-Level Security (RLS)**. Document parsing MUST use lightweight **PyMuPDF (`fitz`)** + recursive text chunking (DO NOT install Docling, Unstructured, or local ML/OCR models to keep RAM footprint under 1 GB).
- **Integrations:** Native **MCP (Model Context Protocol)** client (SSE & stdio transports) + dynamic **OpenAPI/Swagger-to-Tool** converter.
- **LLM Routing & Security:** In-process **LiteLLM** Python SDK (DO NOT deploy a separate LiteLLM proxy container). User API keys (BYOK) MUST be encrypted at rest using **AES-256-GCM**.
- **Observability:** **Langfuse Cloud** (via `@observe` / LangChain callback handler) + internal PostgreSQL `execution_runs` & `run_steps` tables for user-facing run history.

---

## 2. Non-Negotiable Engineering & Security Guardrails
1. **Strict Multi-Tenant Isolation:** Every database table holding customer data MUST include `tenant_id` (UUID, indexed) and `workspace_id`. All database sessions MUST set `app.current_tenant_id` so PostgreSQL RLS policies enforce isolation at the DB layer. Never trust client-supplied `tenant_id` without JWT/session verification.
2. **Low-RAM Infrastructure Constraint:** Target deployment is low-cost managed cloud (Vercel + Supabase/Neon + Railway/Render 1GB RAM containers) or a single small VPS. Avoid memory-heavy dependencies, local embedding models (use API embeddings via LiteLLM), or extra databases (no Qdrant, no ClickHouse, no MongoDB).
3. **Zero Plaintext Secrets:** Encrypt all BYOK LLM keys and MCP auth headers with `AES-256-GCM` using `MASTER_ENCRYPTION_KEY` from environment variables. Decrypt only in memory immediately before execution; never log decrypted secrets or full authorization headers.
4. **Execution Safety & Loop Protection:** Every dynamically compiled LangGraph workflow MUST enforce `recursion_limit` (default: `25`, max: `50`) and track token usage + estimated USD cost per step via LiteLLM response metadata.
5. **Single Source of Truth for Workflow JSON:** The React Flow canvas, the Prompt-to-Workflow AI Copilot, and the LangGraph backend compiler MUST share the exact same canonical JSON schema (`WorkflowDefinition`).

---

## 3. Repository Structure
```text
/
├── AGENTS.md                     # This architectural constitution
├── docker-compose.yml            # Local dev: postgres (pgvector) + redis
├── frontend/                     # Next.js 15 + React Flow Studio
│   ├── src/
│   │   ├── app/                  # App Router pages (dashboard, studio/[workflowId], runs)
│   │   ├── components/
│   │   │   ├── canvas/           # React Flow custom nodes, edges, controls, live status overlay
│   │   │   ├── copilot/          # Prompt-to-Workflow AI sidebar chat
│   │   │   └── panels/           # Node config inspector, MCP/RAG/API key drawers
│   │   ├── schemas/              # Zod schemas matching backend WorkflowDefinition
│   │   └── stores/               # Zustand canvas & execution state stores
└── backend/                      # FastAPI + LangGraph + Celery
    ├── app/
    │   ├── api/v1/               # REST & SSE streaming endpoints
    │   ├── core/                 # Config, JWT auth, tenant middleware, AES-256 crypto
    │   ├── db/                   # SQLAlchemy models, RLS session helper, Alembic migrations
    │   ├── engine/
    │   │   ├── compiler.py       # JSON WorkflowDefinition -> LangGraph StateGraph compiler
    │   │   ├── nodes.py          # Node executors (Supervisor, Agent, Tool, Router, HumanApproval)
    │   │   ├── copilot.py        # Meta-agent generating valid WorkflowDefinition JSON from prompts
    │   │   └── mcp_client.py     # MCP & OpenAPI dynamic tool loader
    │   ├── rag/                  # PyMuPDF parser, chunker, pgvector hybrid/cosine retriever
    │   └── workers/              # Celery tasks (ingest_document, execute_workflow_async)
    └── tests/                    # Pytest async tests (including cross-tenant isolation tests)