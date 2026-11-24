import { z } from "zod";

/**
 * Canonical Single Source of Truth WorkflowDefinition Zod schema.
 * Mirrors backend/app/schemas/workflow.py 1-to-1.
 */

export const ProviderSchema = z.enum([
  "openai",
  "anthropic",
  "google",
  "groq",
  "mistral",
  "openrouter",
  "deepseek",
  "custom",
]);

export const NodePositionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

const BaseNodeDataSchema = z.object({
  label: z.string().min(1).max(120),
  description: z.string().max(500).nullable().optional(),
});

const LLMConfigSchema = z.object({
  provider: ProviderSchema.default("openai"),
  model: z.string().min(1).max(120).default("gpt-4o-mini"),
  api_key_id: z.string().uuid().nullable().optional(),
  temperature: z.number().min(0).max(2).default(0.2),
  max_tokens: z.number().int().min(1).max(128000).nullable().optional(),
});

export const StartNodeDataSchema = BaseNodeDataSchema.extend({
  input_schema: z.record(z.unknown()).default({}),
});

export const EndNodeDataSchema = BaseNodeDataSchema.extend({
  output_mapping: z.record(z.string()).default({}),
});

export const SupervisorNodeDataSchema = BaseNodeDataSchema.merge(LLMConfigSchema).extend({
  system_prompt: z
    .string()
    .min(1)
    .max(16000)
    .default("You are a supervisor orchestrating specialist agents to complete the user task."),
  routing_strategy: z.enum(["llm_router", "round_robin"]).default("llm_router"),
  managed_agent_ids: z.array(z.string()).default([]),
});

export const AgentNodeDataSchema = BaseNodeDataSchema.merge(LLMConfigSchema).extend({
  system_prompt: z
    .string()
    .min(1)
    .max(16000)
    .default("You are a helpful specialist AI agent."),
  tool_ids: z.array(z.string()).default([]),
  mcp_server_ids: z.array(z.string().uuid()).default([]),
  rag_enabled: z.boolean().default(false),
  rag_top_k: z.number().int().min(1).max(20).default(5),
  structured_output_schema: z.record(z.unknown()).nullable().optional(),
});

export const ToolNodeDataSchema = BaseNodeDataSchema.extend({
  tool_kind: z.enum(["mcp", "openapi", "rag", "http"]).default("mcp"),
  mcp_server_id: z.string().uuid().nullable().optional(),
  openapi_spec_url: z.string().nullable().optional(),
  operation_name: z.string().max(120).nullable().optional(),
  static_params: z.record(z.unknown()).default({}),
});

export const RouterRouteSchema = z.object({
  key: z.string().min(1).max(64),
  description: z.string().min(1).max(300),
  expression: z.string().nullable().optional(),
});

export const RouterNodeDataSchema = BaseNodeDataSchema.extend({
  mode: z.enum(["llm", "expression"]).default("llm"),
  provider: ProviderSchema.default("openai"),
  model: z.string().min(1).max(120).default("gpt-4o-mini"),
  api_key_id: z.string().uuid().nullable().optional(),
  routes: z.array(RouterRouteSchema).default([]),
});

export const HumanApprovalNodeDataSchema = BaseNodeDataSchema.extend({
  prompt_message: z
    .string()
    .min(1)
    .max(2000)
    .default("Review the agent output and approve or reject to continue."),
  timeout_seconds: z.number().int().min(60).max(604800).default(86400),
  allowed_actions: z
    .array(z.enum(["approve", "reject", "edit"]))
    .default(["approve", "reject"]),
});

const NodeIdSchema = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[a-zA-Z0-9_-]+$/, "Node ID must be alphanumeric, '_' or '-'");

export const WorkflowNodeSchema = z.discriminatedUnion("type", [
  z.object({ id: NodeIdSchema, type: z.literal("start"), position: NodePositionSchema, data: StartNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("end"), position: NodePositionSchema, data: EndNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("supervisor"), position: NodePositionSchema, data: SupervisorNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("agent"), position: NodePositionSchema, data: AgentNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("tool"), position: NodePositionSchema, data: ToolNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("router"), position: NodePositionSchema, data: RouterNodeDataSchema }),
  z.object({ id: NodeIdSchema, type: z.literal("human_approval"), position: NodePositionSchema, data: HumanApprovalNodeDataSchema }),
]);

export const WorkflowEdgeSchema = z.object({
  id: z.string().min(1).max(64),
  source: z.string().min(1).max(64),
  target: z.string().min(1).max(64),
  source_handle: z.string().nullable().optional(),
  target_handle: z.string().nullable().optional(),
  condition: z.string().max(120).nullable().optional(),
});

export const ExecutionConfigSchema = z.object({
  recursion_limit: z.number().int().min(1).max(50).default(25),
  timeout_seconds: z.number().int().min(5).max(3600).default(300),
  max_cost_usd: z.number().positive().max(100).nullable().optional(),
});

export const WorkflowDefinitionSchema = z
  .object({
    schema_version: z.literal("1.0").default("1.0"),
    nodes: z.array(WorkflowNodeSchema).min(2).max(100),
    edges: z.array(WorkflowEdgeSchema).max(300).default([]),
    execution_config: ExecutionConfigSchema.default({
      recursion_limit: 25,
      timeout_seconds: 300,
    }),
    variables: z.record(z.unknown()).default({}),
  })
  .strict();

export type WorkflowNodeType = WorkflowNode["type"];
export type WorkflowNode = z.infer<typeof WorkflowNodeSchema>;
export type WorkflowEdge = z.infer<typeof WorkflowEdgeSchema>;
export type WorkflowDefinition = z.infer<typeof WorkflowDefinitionSchema>;
