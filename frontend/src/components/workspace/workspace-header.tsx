"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRunAction } from "@/hooks/use-actions";
import { useActionStore } from "@/stores/action-store";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Action } from "@/types";

const statusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function WorkspaceHeader({ action }: { action: Action }) {
  const runAction = useRunAction();
  const sseStatus = useActionStore((s) => s.actionStatus);
  const recoveryAttempt = useActionStore((s) => s.recoveryAttempt);
  const status = sseStatus || action.status;
  const hasPendingTasks = action.tasks.some((t) => t.status === "pending");
  const isRunning = status === "running";
  const isRecovering = isRunning && recoveryAttempt !== null;

  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Link href="/" className="hover:text-foreground transition-colors">
            Runbook
          </Link>
          <span>/</span>
          <span className="text-foreground">{action.title}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{action.title}</h1>
            <Badge variant="secondary" className={statusColors[status]}>
              {isRunning && (
                <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse mr-1.5" />
              )}
              {status}
            </Badge>
            {isRecovering && (
              <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 gap-1">
                <svg className="w-3 h-3 animate-spin" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M6 1v2M6 9v2M1 6h2M9 6h2M2.2 2.2l1.4 1.4M8.4 8.4l1.4 1.4M2.2 9.8l1.4-1.4M8.4 3.6l1.4-1.4" strokeLinecap="round"/>
                </svg>
                Recovering ({recoveryAttempt}/{action.retry_count > 0 ? action.retry_count : recoveryAttempt})
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button
              onClick={() => runAction.mutate(action.id)}
              disabled={runAction.isPending || isRunning || !hasPendingTasks}
            >
              {isRunning ? "Running..." : "Run"}
            </Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          {action.root_prompt}
        </p>
      </div>
    </div>
  );
}
