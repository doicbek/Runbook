"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createSSEConnection } from "@/lib/sse";
import { useActionStore } from "@/stores/action-store";
import type { Task } from "@/types";

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

    const { setTaskOverride, setActionStatus, setRecoveryAttempt, appendTaskLog, setCodeExecution } =
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
              output_summary: data.error as string,
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
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            queryClient.invalidateQueries({ queryKey: ["actions"] });
            break;
          case "action.failed":
            setActionStatus("failed");
            setRecoveryAttempt(null);
            queryClient.invalidateQueries({ queryKey: ["action", actionId] });
            queryClient.invalidateQueries({ queryKey: ["actions"] });
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
