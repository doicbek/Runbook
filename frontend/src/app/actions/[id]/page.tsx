"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useAction } from "@/hooks/use-actions";
import { useActionEvents } from "@/hooks/use-action-events";
import { useActionStore } from "@/stores/action-store";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { TaskBoard } from "@/components/workspace/task-board";

export default function ActionWorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: action, isLoading, error } = useAction(id);

  // Clear stale state from other actions when action ID changes
  useEffect(() => {
    const store = useActionStore.getState();
    store.resetForAction(id);
    return () => {
      // Clean up when leaving this action page — only if still viewing this action
      if (useActionStore.getState().currentActionId === id) {
        useActionStore.getState().resetForAction("");
      }
    };
  }, [id]);

  // Connect SSE for real-time updates
  useActionEvents(id, !!action);

  if (isLoading) {
    return (
      <div className="px-6 py-8">
        <div className="h-8 w-48 bg-muted animate-pulse rounded mb-4" />
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-28 border border-l-[3px] border-l-border bg-muted/30 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error || !action) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-destructive text-lg">Action not found</p>
          <Link
            href="/"
            className="text-sm text-muted-foreground hover:text-foreground mt-2 inline-block"
          >
            Back to Actions
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <WorkspaceHeader action={action} />
      <div className="px-6 py-6">
        <TaskBoard tasks={action.tasks} actionId={action.id} />
      </div>
    </div>
  );
}
