import { WorkflowDefinition } from "@/schemas/workflow";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000/api/v1";

export const JWT_STORAGE_KEY = "orchestrator_jwt";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(JWT_STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(JWT_STORAGE_KEY, token);
  }
}

export function clearStoredToken(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(JWT_STORAGE_KEY);
  }
}

function getAuthHeaders(): HeadersInit {
  const token = getStoredToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function parseError(res: Response, fallback: string): Promise<string> {
  const err = await res.json().catch(() => ({ detail: res.statusText }));
  if (typeof err.detail === "string") return err.detail;
  if (err.detail) return JSON.stringify(err.detail);
  return fallback;
}

export interface UserMeRecord {
  user_id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  workspace_id: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  tenant_id: string;
  workspace_id: string;
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
  steps?: {
    id: string;
    node_id: string;
    node_type: string;
    status: string;
    prompt_tokens: number;
    completion_tokens: number;
    estimated_cost_usd: string;
    latency_ms: number | null;
  }[];
}

export async function registerAccount(payload: {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Registration failed"));
  const data = (await res.json()) as TokenResponse;
  setStoredToken(data.access_token);
  return data;
}

export async function loginAccount(payload: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Invalid credentials"));
  const data = (await res.json()) as TokenResponse;
  setStoredToken(data.access_token);
  return data;
}

export async function getMe(): Promise<UserMeRecord | null> {
  if (!getStoredToken()) return null;
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (res.status === 401) {
    clearStoredToken();
    return null;
  }
  if (!res.ok) return null;
  return res.json();
}

export async function listWorkflows(): Promise<WorkflowRecord[]> {
  const res = await fetch(`${API_BASE}/workflows`, {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to load workflows"));
  return res.json();
}

export async function getWorkflowById(workflowId: string): Promise<WorkflowRecord> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}`, {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res, "Workflow not found"));
  return res.json();
}

export async function createWorkflow(payload: {
  name: string;
  description?: string | null;
  definition: WorkflowDefinition;
}): Promise<WorkflowRecord> {
  const res = await fetch(`${API_BASE}/workflows`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to save workflow"));
  return res.json();
}

export async function updateWorkflow(
  workflowId: string,
  payload: {
    name?: string;
    description?: string | null;
    definition?: WorkflowDefinition;
  },
): Promise<WorkflowRecord> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to update workflow"));
  return res.json();
}

export async function deleteWorkflowRecord(workflowId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to delete workflow"));
}

export async function executeWorkflowOnBackend(
  workflowId: string,
  input: Record<string, unknown>,
): Promise<ExecutionRunRecord> {
  const res = await fetch(`${API_BASE}/workflows/${workflowId}/execute`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ input }),
  });
  if (!res.ok) throw new Error(await parseError(res, "Workflow execution failed"));
  return res.json();
}

export async function resumeExecutionRun(
  runId: string,
  payload: { action: "approve" | "reject" | "edit"; edited_output?: string },
): Promise<ExecutionRunRecord> {
  const res = await fetch(`${API_BASE}/runs/${runId}/resume`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to resume run"));
  return res.json();
}

export async function resumeDevWorkflowRun(payload: {
  definition: WorkflowDefinition;
  thread_id: string;
  action: "approve" | "reject" | "edit";
  edited_output?: string;
}): Promise<{
  status: string;
  thread_id: string;
  output: Record<string, unknown> | null;
  interrupt_payload: Record<string, unknown> | null;
  total_tokens: number;
  total_cost_usd: number;
  step_metrics: { node_id: string; status: string }[];
}> {
  const res = await fetch(`${API_BASE}/workflows/resume-dev`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to resume dev run"));
  return res.json();
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
  if (!res.ok) throw new Error(await parseError(res, "Validation failed"));
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
  const endpoint = getStoredToken()
    ? `${API_BASE}/copilot/generate`
    : `${API_BASE}/copilot/generate-dev`;

  const res = await fetch(endpoint, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      provider: "deepseek",
      model: "deepseek-chat",
      ...payload,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res, "Copilot generation failed"));
  return res.json();
}

export async function listExecutionRuns(): Promise<ExecutionRunRecord[]> {
  const res = await fetch(`${API_BASE}/runs`, {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res, "Failed to fetch execution runs"));
  return res.json();
}

export async function streamDevWorkflowRun(
  definition: WorkflowDefinition,
  input: Record<string, unknown>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/workflows/stream-dev`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ definition, input }),
  });
  if (!res.ok || !res.body) {
    throw new Error(await parseError(res, `Stream failed (${res.status})`));
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
