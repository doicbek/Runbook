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
  const status = sseStatus || action.status;
  const hasPendingTasks = action.tasks.some((t) => t.status === "pending");
  const isRunning = status === "running";

  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Link href="/" className="hover:text-foreground transition-colors">
            Actions
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
