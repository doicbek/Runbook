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
  dependencies: string[];
  output_summary: string | null;
  created_at: string;
  updated_at: string;
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
