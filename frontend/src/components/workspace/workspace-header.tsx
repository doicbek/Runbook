"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useRunAction, useBreadcrumbs, useDeleteAction } from "@/hooks/use-actions";
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
  const router = useRouter();
  const runAction = useRunAction();
  const deleteAction = useDeleteAction();
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const sseStatus = useActionStore((s) => s.actionStatus);
  const recoveryAttempt = useActionStore((s) => s.recoveryAttempt);
  const isReplanning = useActionStore((s) => s.isReplanning);
  const failureReason = useActionStore((s) => s.failureReason);
  const sseConnected = useActionStore((s) => s.sseConnected);
  const status = sseStatus || action.status;
  const hasPendingTasks = action.tasks.some((t) => t.status === "pending");
  const isRunning = status === "running";
  const isRecovering = isRunning && recoveryAttempt !== null && !isReplanning;

  const isSubAction = !!action.parent_action_id;
  const { data: breadcrumbs } = useBreadcrumbs(action.id, isSubAction);

  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <div className="px-6 py-4">
        {isSubAction && breadcrumbs && breadcrumbs.length > 1 && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
            {breadcrumbs.map((crumb, i) => {
              const isLast = i === breadcrumbs.length - 1;
              return (
                <span key={crumb.id} className="flex items-center gap-2">
                  {i > 0 && <span>/</span>}
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
            })}
          </div>
        )}
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
            {!sseConnected && (
              <Badge variant="secondary" className="bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-300 gap-1">
                <svg className="w-3 h-3 animate-pulse" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M1 9l2.5-2.5M3.5 6.5L6 4M6 4l2.5-2.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.4"/>
                  <path d="M9 1l-1 1" strokeLinecap="round" opacity="0.4"/>
                  <line x1="1" y1="1" x2="11" y2="11" strokeLinecap="round"/>
                </svg>
                Reconnecting...
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDeleteConfirmOpen(true)}
              className="text-muted-foreground hover:text-red-500 h-8 w-8 p-0"
              title="Delete action"
            >
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 4h10M6 4V3a1 1 0 011-1h2a1 1 0 011 1v1M5 4v9a1 1 0 001 1h4a1 1 0 001-1V4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Button>
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
        {status === "failed" && failureReason && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/30 px-3 py-2">
            <svg className="w-4 h-4 text-red-500 shrink-0 mt-0.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="6" cy="6" r="4.5" />
              <path d="M6 4v2.5M6 8h.01" strokeLinecap="round" />
            </svg>
            <p className="text-[12px] text-red-700 dark:text-red-300">
              {failureReason}
            </p>
          </div>
        )}
      </div>

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Action</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground py-2">
            This will permanently delete this action and all its tasks, outputs, and artifacts. This cannot be undone.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteAction.isPending}
              onClick={async () => {
                await deleteAction.mutateAsync(action.id);
                setDeleteConfirmOpen(false);
                router.push("/");
              }}
            >
              {deleteAction.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
