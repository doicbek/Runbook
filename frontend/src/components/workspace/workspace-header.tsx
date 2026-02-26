"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRunAction, useBreadcrumbs } from "@/hooks/use-actions";
import { useActionStore } from "@/stores/action-store";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Action } from "@/types";

const statusColors: Record<string, string> = {
  draft: "bg-gray-50 text-gray-600 dark:bg-gray-800/50 dark:text-gray-400",
  running: "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
  completed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  failed: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300",
};

export function WorkspaceHeader({ action }: { action: Action }) {
  const runAction = useRunAction();
  const sseStatus = useActionStore((s) => s.actionStatus);
  const recoveryAttempt = useActionStore((s) => s.recoveryAttempt);
  const isReplanning = useActionStore((s) => s.isReplanning);
  const status = sseStatus || action.status;
  const hasPendingTasks = action.tasks.some((t) => t.status === "pending");
  const isRunning = status === "running";
  const isRecovering = isRunning && recoveryAttempt !== null && !isReplanning;

  const isSubAction = !!action.parent_action_id;
  const { data: breadcrumbs } = useBreadcrumbs(action.id, isSubAction);

  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Link href="/" className="hover:text-foreground transition-colors">
            Runbook
          </Link>
          {isSubAction && breadcrumbs && breadcrumbs.length > 1 ? (
            // Show full breadcrumb trail for sub-actions
            breadcrumbs.map((crumb, i) => {
              const isLast = i === breadcrumbs.length - 1;
              return (
                <span key={crumb.id} className="flex items-center gap-2">
                  <span>/</span>
                  {isLast ? (
                    <span className="text-foreground flex items-center gap-1.5">
                      {crumb.depth > 0 && (
                        <span className="text-[9px] font-mono text-violet-400 bg-violet-500/10 px-1 py-0.5 rounded">
                          L{crumb.depth}
                        </span>
                      )}
                      {crumb.title}
                    </span>
                  ) : (
                    <Link
                      href={`/actions/${crumb.id}`}
                      className="hover:text-foreground transition-colors flex items-center gap-1.5"
                    >
                      {crumb.depth > 0 && (
                        <span className="text-[9px] font-mono text-violet-400 bg-violet-500/10 px-1 py-0.5 rounded">
                          L{crumb.depth}
                        </span>
                      )}
                      {crumb.title}
                    </Link>
                  )}
                </span>
              );
            })
          ) : (
            <>
              <span>/</span>
              <span className="text-foreground">{action.title}</span>
            </>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{action.title}</h1>
            {isSubAction && (
              <Badge variant="secondary" className="bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300 text-[10px] gap-1">
                <span>&#8599;</span>
                Sub-action (depth {action.depth})
              </Badge>
            )}
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
            {isReplanning && (
              <Badge variant="secondary" className="bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300 gap-1">
                <svg className="w-3 h-3 animate-spin" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M10 6A4 4 0 112 6" strokeLinecap="round"/>
                  <path d="M10 3v3h-3" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Replanning
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {/* Resume button — only shown when there are pending tasks after an edit or failure */}
            {!isRunning && hasPendingTasks && (status === "draft" || status === "failed" || status === "completed") && (
              <Button
                size="sm"
                onClick={() => runAction.mutate(action.id)}
                disabled={runAction.isPending}
              >
                {runAction.isPending ? "Resuming..." : "Resume"}
              </Button>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          {action.root_prompt}
        </p>
      </div>
    </div>
  );
}
