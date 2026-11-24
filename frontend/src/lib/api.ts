import { WorkflowDefinition } from "@/schemas/workflow";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000/api/v1";

function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? window.localStorage.getItem("orchestrator_jwt") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface WorkflowRecord {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  definition: WorkflowDefinition;
  version: number;
  is_active: boolean;
}

export interface ExecutionRunRecord {
  id: string;
  workflow_id: string;
  status: string;
  total_tokens: number;
  estimated_cost_usd: string;
  created_at: string;
  output_payload: Record<string, unknown> | null;
  interrupt_payload?: Record<string, unknown> | null;
}

export async function validateWorkflowOnBackend(definition: WorkflowDefinition): Promise<{
  valid: boolean;
  node_count: number;
  edge_count: number;
  recursion_limit: number;
}> {
  const res = await fetch(`${API_BASE}/workflows/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

export async function generateWorkflowWithCopilot(payload: {
  prompt: string;
  provider?: string;
  model?: string;
  existing_workflow?: WorkflowDefinition;
}): Promise<{
  workflow: WorkflowDefinition;
  explanation: string;
  attempts: number;
  total_tokens: number;
  estimated_cost_usd: number;
}> {
  const res = await fetch(`${API_BASE}/copilot/generate`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Copilot generation failed");
  }
  return res.json();
}

export async function listExecutionRuns(): Promise<ExecutionRunRecord[]> {
  const res = await fetch(`${API_BASE}/runs`, {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error("Failed to fetch execution runs");
  }
  return res.json();
}

export async function streamWorkflowRun(
  workflowId: string,
  input: Record<string, unknown>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/stream`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ input }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      let eventName = "message";
      let dataLine = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (dataLine) {
        onEvent(eventName, JSON.parse(dataLine) as Record<string, unknown>);
      }
    }
  }
}
