"use client";

import { useActions } from "@/hooks/use-actions";
import { ActionCard } from "@/components/action-card";

export function ActionList() {
  const { data: allActions, isLoading, error } = useActions();
  // Only show root actions (depth=0) — sub-actions are accessible from parent task cards
  const actions = allActions?.filter((a) => (a.depth ?? 0) === 0 && a.parent_action_id === null);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <div
            key={i}
            className="h-40 rounded-lg border bg-muted/50 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive">Failed to load actions</p>
        <p className="text-sm text-muted-foreground mt-1">
          Make sure the backend is running on port 8000
        </p>
      </div>
    );
  }

  if (!actions || actions.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground text-lg">No actions yet</p>
        <p className="text-sm text-muted-foreground mt-1">
          Create your first action to get started
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {actions.map((action) => (
        <ActionCard key={action.id} action={action} />
      ))}
    </div>
  );
}
