"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createSSEConnection } from "@/lib/sse";
import { useActionStore } from "@/stores/action-store";
import type { AgentIteration, Task } from "@/types";

export function useActionEvents(actionId: string, enabled = true) {
  const queryClientRef = useRef(useQueryClient());
  const eventSourceRef = useRef<EventSource | null>(null);
  const errorCountRef = useRef(0);

  useEffect(() => {
    if (!enabled || !actionId) return;

    // Close stale connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const { setTaskOverride, setActionStatus, setRecoveryAttempt, setReplanning, setFailureReason, clearTaskState, appendTaskLog, setCodeExecution, addIteration, updateCurrentIteration, setRetryStatus, appendTaskStreamingText } =
      useActionStore.getState();
    const queryClient = queryClientRef.current;

    const es = createSSEConnection(
      actionId,
      (event, data) => {
        // Ignore events for a different action
        const currentId = useActionStore.getState().currentActionId;
        if (currentId && currentId !== actionId) return;

        errorCountRef.current = 0;

        switch (event) {
          case "snapshot": {
            const tasks = data.tasks as Task[];
            for (const t of tasks) {
              setTaskOverride(t.id, {
                status: t.status as Task["status"],
                output_summary: t.output_summary as string | null,
              });
            }
            if (data.status) {
              setActionStatus(data.status as string);
            }
            break;
          }
          case "task.started":
            setTaskOverride(data.task_id as string, { status: "running" });
            break;
          case "task.completed":
            setTaskOverride(data.task_id as string, {
              status: "completed",
              output_summary: data.output_summary as string,
            });
            // Refetch to get the persisted output
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "task.failed":
            setTaskOverride(data.task_id as string, {
              status: "failed",
              output_summary: (data.output_summary as string) || (data.error as string),
            });
            break;
          case "task.recovering":
            // Task is attempting inline recovery — keep it as "running"
            // so the UI shows the live activity feed with recovery logs
            appendTaskLog(data.task_id as string, {
              level: "warn",
              message: `Recovery attempt ${data.attempt}/${data.max_attempts}: ${(data.error as string) || "retrying..."}`,
            });
            break;
          case "log.append":
            appendTaskLog(data.task_id as string, {
              level: data.level as string,
              message: data.message as string,
            });
            break;
          case "action.completed":
            setActionStatus("completed");
            setRecoveryAttempt(null);
            setReplanning(false);
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            queryClient.invalidateQueries({ queryKey: ["actions"] });
            break;
          case "action.failed":
            setActionStatus("failed");
            setRecoveryAttempt(null);
            setReplanning(false);
            if (data.reason) {
              setFailureReason(data.reason as string);
            }
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            queryClient.invalidateQueries({ queryKey: ["actions"] });
            break;
          case "action.replanning":
            setActionStatus("running");
            setRecoveryAttempt(null);
            setReplanning(true);
            clearTaskState();
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "action.started":
            setActionStatus("running");
            break;
          case "action.retrying":
            setActionStatus("running");
            setRecoveryAttempt(data.attempt as number);
            // Refetch to get the patched task list
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "task.recovered":
            // Refetch so the replaced task(s) appear in the UI
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "sub_action.progress":
            // Refetch the child action data so inline progress updates
            if (data.sub_action_id) {
              queryClient.invalidateQueries({ queryKey: ["action", data.sub_action_id as string] });
            }
            break;
          case "task.acquisition":
            // Task was transformed into sub_action for data acquisition
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "code.started":
            setCodeExecution(data.task_id as string, {
              status: "running",
              stdout: "",
              stderr: "",
              artifactIds: [],
            });
            break;
          case "code.completed":
            setCodeExecution(data.task_id as string, {
              status: "completed",
              artifactIds: (data.artifact_ids as string[]) || [],
              stdout: (data.stdout_preview as string) || "",
            });
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            break;
          case "code.failed":
            setCodeExecution(data.task_id as string, {
              status: "failed",
              stderr: (data.stderr as string) || (data.error as string) || "",
            });
            break;
          case "code.log":
            appendTaskLog(data.task_id as string, {
              level: data.level as string,
              message: data.message as string,
            });
            break;

          // --- Iteration events ---
          case "iteration.started":
            updateCurrentIteration(data.task_id as string, {
              iteration_number: data.iteration_number as number,
              reasoning: null,
              tool: null,
              status: "running",
            });
            break;
          case "iteration.reasoning":
            updateCurrentIteration(data.task_id as string, {
              iteration_number: data.iteration_number as number,
              reasoning: data.reasoning as string,
            });
            break;
          case "iteration.tool_call":
            updateCurrentIteration(data.task_id as string, {
              iteration_number: data.iteration_number as number,
              tool: data.tool as string,
              status: "tool_calling",
            });
            break;
          case "iteration.tool_result":
            updateCurrentIteration(data.task_id as string, {
              iteration_number: data.iteration_number as number,
              tool: data.tool as string,
              status: "running",
            });
            break;
          case "iteration.completed": {
            const taskId = data.task_id as string;
            const outcome = data.outcome as string;
            updateCurrentIteration(taskId, {
              iteration_number: data.iteration_number as number,
              status: outcome === "failed" ? "failed" : outcome === "completed" ? "completed" : "running",
            });
            // Build an AgentIteration record from the completed event data
            addIteration(taskId, {
              id: (data.iteration_id as string) || `iter-${taskId}-${data.iteration_number}`,
              task_id: taskId,
              action_id: actionId,
              iteration_number: data.iteration_number as number,
              loop_type: (data.loop_type as "primary" | "retry" | "user_guidance") || "primary",
              attempt_number: (data.attempt_number as number) || 0,
              reasoning: (data.reasoning as string) || null,
              tool_calls: (data.tool_calls as AgentIteration["tool_calls"]) || [],
              outcome: outcome as AgentIteration["outcome"],
              error: (data.error as string) || null,
              lessons_learned: (data.lessons_learned as string) || null,
              created_at: new Date().toISOString(),
              duration_ms: (data.duration_ms as number) || 0,
            });
            break;
          }
          case "iteration.file_diff":
            // File diff events are associated with the current iteration
            // Append as a log for immediate visibility
            appendTaskLog(data.task_id as string, {
              level: "info",
              message: `File changed: ${data.file_path as string}`,
            });
            break;
          case "iteration.terminal":
            // Terminal output events — append as a log
            appendTaskLog(data.task_id as string, {
              level: (data.exit_code as number) === 0 ? "info" : "warn",
              message: `$ ${data.command as string} → exit ${data.exit_code as number}`,
            });
            break;

          // --- Recovery events (LLM-triaged retry/sub-action) ---
          case "task.recovery.started":
            setRetryStatus(data.task_id as string, {
              attempt: 1,
              max_attempts: data.max_attempts as number,
            });
            break;
          case "task.recovery.attempt":
            setRetryStatus(data.task_id as string, {
              attempt: data.attempt as number,
              max_attempts: data.max_attempts as number,
              strategy: data.strategy as string,
            });
            break;
          case "task.recovery.exhausted":
            setRetryStatus(data.task_id as string, {
              attempt: data.max_attempts as number,
              max_attempts: data.max_attempts as number,
            });
            break;

          // --- Pause/resume events ---
          case "task.paused":
            setTaskOverride(data.task_id as string, { status: "paused" });
            break;
          case "task.resumed":
            setTaskOverride(data.task_id as string, { status: "running" });
            break;
          case "task.user_guidance":
            appendTaskLog(data.task_id as string, {
              level: "info",
              message: `User guidance: ${(data.guidance as string) || "resumed"}`,
            });
            break;

          // --- Streaming LLM output ---
          case "task.llm_chunk":
            appendTaskStreamingText(data.task_id as string, data.chunk as string);
            break;
        }
      },
      () => {
        errorCountRef.current += 1;
        if (errorCountRef.current >= 3) {
          eventSourceRef.current?.close();
          eventSourceRef.current = null;
        }
      }
    );

    eventSourceRef.current = es;

    return () => {
      es.close();
      eventSourceRef.current = null;
      errorCountRef.current = 0;
    };
  }, [actionId, enabled]);
}
