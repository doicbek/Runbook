import { API_BASE } from "@/lib/api";

export type SSEHandler = (event: string, data: Record<string, unknown>) => void;

export interface SSEConnection {
  close: () => void;
}

export function createSSEConnection(
  actionId: string,
  onEvent: SSEHandler,
  onError?: (error: Event) => void,
  onOpen?: () => void
): SSEConnection {
  const url = `${API_BASE}/actions/${actionId}/events`;

  const eventTypes = [
    "snapshot",
    "task.started",
    "task.completed",
    "task.failed",
    "task.retrying",
    "task.recovering",
    "task.recovered",
    "log.append",
    "action.completed",
    "action.failed",
    "action.started",
    "action.replanning",
    "action.retrying",
    "code.started",
    "code.completed",
    "code.failed",
    "code.log",
    "task.llm_chunk",
    "sub_action.progress",
    "task.acquisition",
    "iteration.started",
    "iteration.reasoning",
    "iteration.tool_call",
    "iteration.tool_result",
    "iteration.completed",
    "iteration.file_diff",
    "iteration.terminal",
    "task.recovery.started",
    "task.recovery.attempt",
    "task.recovery.exhausted",
    "task.paused",
    "task.resumed",
    "task.user_guidance",
    "cost.update",
    "ping",
  ];

  let closed = false;
  let backoffMs = 1000;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let currentSource: EventSource | null = null;

  function connect() {
    if (closed) return;

    const es = new EventSource(url);
    currentSource = es;

    for (const type of eventTypes) {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          onEvent(type, data);
        } catch {
          // ignore parse errors
        }
      });
    }

    es.onopen = () => {
      backoffMs = 1000; // reset backoff on successful connection
      onOpen?.();
    };

    es.onerror = (e) => {
      onError?.(e);
      es.close();
      currentSource = null;

      if (!closed) {
        reconnectTimer = setTimeout(() => {
          connect();
        }, backoffMs);
        backoffMs = Math.min(backoffMs * 2, 30000); // cap at 30s
      }
    };
  }

  connect();

  return {
    close() {
      closed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (currentSource) {
        currentSource.close();
        currentSource = null;
      }
    },
  };
}
