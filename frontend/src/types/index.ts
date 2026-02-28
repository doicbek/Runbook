export interface Action {
  id: string;
  title: string;
  root_prompt: string;
  status: "draft" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  tasks: Task[];
  parent_action_id: string | null;
  parent_task_id: string | null;
  output_contract: string | null;
  depth: number;
  retry_count: number;
}

export interface ActionListItem {
  id: string;
  title: string;
  root_prompt: string;
  status: "draft" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  task_count: number;
  parent_action_id: string | null;
  depth: number;
}

export interface Task {
  id: string;
  action_id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  agent_type: string;
  model: string | null;
  dependencies: string[];
  output_summary: string | null;
  sub_action_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelInfo {
  name: string;
  display_name: string;
  provider: string;
}

export interface ModelsResponse {
  models: ModelInfo[];
  defaults_by_agent_type: Record<string, string>;
}

export interface LogEntry {
  id: string;
  task_id: string;
  level: "info" | "warn" | "error";
  message: string;
  timestamp: string;
  structured: Record<string, unknown> | null;
}

export interface Artifact {
  id: string;
  task_id: string;
  action_id: string;
  type: "file" | "image" | "markdown";
  mime_type: string | null;
  storage_path: string | null;
  size_bytes: number | null;
  created_at: string;
}

export interface CodeExecutionResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  artifacts: Artifact[];
}

export interface CodeExecutionState {
  status: "idle" | "running" | "completed" | "failed";
  stdout: string;
  stderr: string;
  artifactIds: string[];
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface AgentDefinition {
  id: string;
  agent_type: string;
  name: string;
  description: string;
  code: string | null;
  tools: string[];
  requirements: string | null;
  setup_notes: string | null;
  mcp_config: Record<string, unknown> | null;
  status: "draft" | "active" | "error";
  is_builtin: boolean;
  icon: string;
  created_at: string;
  updated_at: string;
}

export interface ToolCatalogEntry {
  id: string;
  name: string;
  category: string;
  description: string;
  import_snippet: string;
  usage_snippet: string;
  pip_package: string | null;
}

export interface ScaffoldRequest {
  name: string;
  description: string;
  tools: string[];
  model?: string;
}

export interface ScaffoldResponse {
  code: string;
  requirements: string;
  setup_notes: string;
}

export interface PlannerConfig {
  id: string;
  system_prompt: string;
  model: string;
  max_tasks: number;
  max_retries: number;
  updated_at: string;
}

export interface ApiKeyStatus {
  provider: string;
  configured: boolean;
  models: string[];
}

export interface PlannerPreviewTask {
  prompt: string;
  agent_type: string;
  dependencies: number[];
  model: string | null;
}

export interface PlannerPreviewResponse {
  tasks: PlannerPreviewTask[];
  used_system_prompt: string;
}

export interface ModifyRequest {
  prompt: string;
  current_code?: string;
  model?: string;
}

export interface ModifyResponse {
  code: string;
}

export interface AgentSkill {
  id: string;
  agent_type: string;
  title: string;
  description: string;
  source: "manual" | "auto" | "error" | "correction";
  source_task_id: string | null;
  source_action_id: string | null;
  is_active: boolean;
  usage_count: number;
  category: "learning" | "error_pattern" | "correction" | "best_practice";
  priority: "low" | "medium" | "high" | "critical";
  status: "pending" | "resolved" | "promoted" | "won't_fix";
  pattern_key: string | null;
  recurrence_count: number;
  first_seen: string;
  last_seen: string;
  created_at: string;
  updated_at: string;
}

export interface SkillConcept {
  id: string;
  name: string;
  concept_type: "tool" | "library" | "api" | "data_format" | "anti_pattern" | "technique";
  description: string | null;
  created_at: string;
}

export interface SkillRelation {
  id: string;
  from_id: string;
  relation_type: "depends_on" | "supersedes" | "related_to" | "fixes" | "uses_tool" | "produces" | "avoids";
  to_id: string;
  properties: Record<string, unknown> | null;
  created_at: string;
}

export interface OntologyNode {
  id: string;
  type: "skill" | "concept";
  label: string;
  agent_type?: string;
  category?: string;
  priority?: string;
  status?: string;
  recurrence_count?: number;
  concept_type?: string;
}

export interface OntologyEdge {
  id: string;
  from_id: string;
  relation_type: string;
  to_id: string;
  properties: Record<string, unknown> | null;
}

export interface OntologyGraph {
  nodes: OntologyNode[];
  edges: OntologyEdge[];
}

export interface AgentIterationToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: string;
  duration_ms: number;
  success: boolean;
}

export interface AgentIteration {
  id: string;
  task_id: string;
  action_id: string;
  iteration_number: number;
  loop_type: "primary" | "retry" | "user_guidance";
  attempt_number: number;
  reasoning: string | null;
  tool_calls: AgentIterationToolCall[];
  outcome: "continue" | "completed" | "failed" | "paused" | "user_redirected" | "user_guidance";
  error: string | null;
  lessons_learned: string | null;
  created_at: string;
  duration_ms: number;
}
