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
            className="h-36 rounded-xl border border-l-[3px] border-l-border bg-muted/30 animate-pulse"
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
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="w-12 h-12 rounded-xl border border-dashed border-border flex items-center justify-center mb-4">
          <svg className="w-5 h-5 text-muted-foreground/40" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="6" height="6" rx="1.25" />
            <rect x="12" y="2" width="6" height="6" rx="1.25" />
            <rect x="7" y="12" width="6" height="6" rx="1.25" />
            <path d="M5 8v2a1.5 1.5 0 001.5 1.5H7M15 8v2a1.5 1.5 0 01-1.5 1.5H13" strokeLinecap="round" />
          </svg>
        </div>
        <p className="text-sm font-medium text-foreground/70 mb-1">No actions yet</p>
        <p className="text-xs text-muted-foreground">
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
