export interface Action {
  id: string;
  title: string;
  root_prompt: string;
  status: "draft" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  tasks: Task[];
}

export interface ActionListItem {
  id: string;
  title: string;
  root_prompt: string;
  status: "draft" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  task_count: number;
}

export interface Task {
  id: string;
  action_id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed";
  agent_type: string;
  model: string | null;
  dependencies: string[];
  output_summary: string | null;
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
