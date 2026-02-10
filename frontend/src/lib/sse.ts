import { API_BASE } from "@/lib/api";

export type SSEHandler = (event: string, data: Record<string, unknown>) => void;

export function createSSEConnection(
  actionId: string,
  onEvent: SSEHandler,
  onError?: (error: Event) => void
): EventSource {
  const url = `${API_BASE}/actions/${actionId}/events`;
  const eventSource = new EventSource(url);

  const eventTypes = [
    "snapshot",
    "task.started",
    "task.completed",
    "task.failed",
    "task.retrying",
    "log.append",
    "action.completed",
    "action.failed",
    "action.started",
    "code.started",
    "code.completed",
    "code.failed",
    "code.log",
    "ping",
  ];

  for (const type of eventTypes) {
    eventSource.addEventListener(type, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent(type, data);
      } catch {
        // ignore parse errors
      }
    });
  }

  eventSource.onerror = (e) => {
    onError?.(e);
  };

  return eventSource;
}
