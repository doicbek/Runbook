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
import { useRunAction, useBreadcrumbs, useDeleteAction, useForkAction, useForks } from "@/hooks/use-actions";
import { useSaveAsTemplate } from "@/hooks/use-templates";
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
  const forkAction = useForkAction();
  const saveAsTemplate = useSaveAsTemplate();
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [savedAsTemplate, setSavedAsTemplate] = useState(false);
  const [costPanelOpen, setCostPanelOpen] = useState(false);
  const [forksDropdownOpen, setForksDropdownOpen] = useState(false);
  const sseStatus = useActionStore((s) => s.actionStatus);
  const recoveryAttempt = useActionStore((s) => s.recoveryAttempt);
  const isReplanning = useActionStore((s) => s.isReplanning);
  const failureReason = useActionStore((s) => s.failureReason);
  const sseConnected = useActionStore((s) => s.sseConnected);
  const actionCost = useActionStore((s) => s.actionCost);
  const costByTask = useActionStore((s) => s.costByTask);
  const costByModel = useActionStore((s) => s.costByModel);
  const status = sseStatus || action.status;
  const hasPendingTasks = action.tasks.some((t) => t.status === "pending");
  const isRunning = status === "running";
  const isRecovering = isRunning && recoveryAttempt !== null && !isReplanning;
  const canFork = status === "completed" || status === "failed";
  const { data: forks } = useForks(action.id, forksDropdownOpen);

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
            {actionCost > 0 && (
              <button
                onClick={() => setCostPanelOpen((v) => !v)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-950/70 transition-colors cursor-pointer border-0"
              >
                <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M6 1v10M3.5 3.5C3.5 2.67 4.62 2 6 2s2.5.67 2.5 1.5S7.38 5 6 5 3.5 5.67 3.5 6.5 4.62 8 6 8s2.5-.67 2.5-1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                ${actionCost.toFixed(2)}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {canFork && (
              <Button
                size="sm"
                variant="outline"
                disabled={forkAction.isPending}
                onClick={async () => {
                  const forked = await forkAction.mutateAsync(action.id);
                  router.push(`/actions/${forked.id}`);
                }}
                className="gap-1.5 text-xs"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="5" cy="3.5" r="1.5" />
                  <circle cx="11" cy="3.5" r="1.5" />
                  <circle cx="8" cy="12.5" r="1.5" />
                  <path d="M5 5v2a3 3 0 003 3m3-5v2a3 3 0 01-3 3m0 0v0" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {forkAction.isPending ? "Forking..." : "Fork"}
              </Button>
            )}
            {/* Forks count badge */}
            <div className="relative">
              <button
                onClick={() => setForksDropdownOpen((v) => !v)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors cursor-pointer border-0"
                title="View forks"
              >
                <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="5" cy="3.5" r="1.5" />
                  <circle cx="11" cy="3.5" r="1.5" />
                  <circle cx="8" cy="12.5" r="1.5" />
                  <path d="M5 5v2a3 3 0 003 3m3-5v2a3 3 0 01-3 3m0 0v0" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {forks ? forks.length : "..."}
              </button>
              {forksDropdownOpen && (
                <div className="absolute right-0 top-full mt-1 w-64 bg-popover border rounded-md shadow-md z-20 py-1">
                  <div className="px-3 py-1.5 text-[10px] font-medium uppercase text-muted-foreground tracking-wider border-b">
                    Forks
                  </div>
                  {forks && forks.length === 0 && (
                    <div className="px-3 py-2 text-xs text-muted-foreground">No forks yet</div>
                  )}
                  {forks?.map((fork) => (
                    <Link
                      key={fork.id}
                      href={`/actions/${fork.id}`}
                      className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-accent transition-colors"
                      onClick={() => setForksDropdownOpen(false)}
                    >
                      <Badge variant="secondary" className={`text-[9px] px-1 py-0 ${statusColors[fork.status]}`}>
                        {fork.status}
                      </Badge>
                      <span className="truncate flex-1">{fork.title}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
            {status === "completed" && (
              <Button
                size="sm"
                variant="outline"
                disabled={saveAsTemplate.isPending || savedAsTemplate}
                onClick={async () => {
                  await saveAsTemplate.mutateAsync(action.id);
                  setSavedAsTemplate(true);
                }}
                className="gap-1.5 text-xs"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V4a2 2 0 012-2z" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M5 2v4h6V2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M5 10h6" strokeLinecap="round" />
                </svg>
                {savedAsTemplate ? "Saved" : saveAsTemplate.isPending ? "Saving..." : "Save as Template"}
              </Button>
            )}
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
        {costPanelOpen && actionCost > 0 && (
          <div className="mt-3 rounded-md border bg-muted/30 p-3 max-w-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-muted-foreground">Cost Breakdown</span>
              <span className="text-sm font-semibold">${actionCost.toFixed(2)}</span>
            </div>
            {Object.keys(costByModel).length > 0 && (
              <div className="mb-2">
                <span className="text-[10px] font-medium uppercase text-muted-foreground tracking-wider">By Model</span>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(costByModel)
                    .sort(([, a], [, b]) => b.cost_usd - a.cost_usd)
                    .map(([model, info]) => (
                      <div key={model} className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground truncate mr-2">{model}</span>
                        <span className="font-mono tabular-nums">
                          ${info.cost_usd.toFixed(2)} <span className="text-muted-foreground">({info.calls} calls)</span>
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
            {Object.keys(costByTask).length > 0 && (
              <div>
                <span className="text-[10px] font-medium uppercase text-muted-foreground tracking-wider">By Task</span>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(costByTask)
                    .sort(([, a], [, b]) => b - a)
                    .map(([taskId, cost]) => {
                      const task = action.tasks.find((t) => t.id === taskId);
                      return (
                        <div key={taskId} className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground truncate mr-2">
                            {task ? task.prompt.slice(0, 50) + (task.prompt.length > 50 ? "..." : "") : taskId.slice(0, 8)}
                          </span>
                          <span className="font-mono tabular-nums">${cost.toFixed(2)}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        )}
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
