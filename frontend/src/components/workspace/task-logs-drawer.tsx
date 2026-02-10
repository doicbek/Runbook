"use client";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useMemo } from "react";
import { useTaskLogs } from "@/hooks/use-tasks";
import { useActionStore } from "@/stores/action-store";

const levelColors: Record<string, string> = {
  info: "text-blue-600",
  warn: "text-yellow-600",
  error: "text-red-600",
};

export function TaskLogsDrawer({
  open,
  onOpenChange,
  taskId,
  actionId,
  taskPrompt,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  taskId: string;
  actionId: string;
  taskPrompt: string;
}) {
  const { data: persistedLogs } = useTaskLogs(actionId, taskId, open);
  const allTaskLogs = useActionStore((s) => s.taskLogs);
  const realtimeLogs = allTaskLogs[taskId];

  const allLogs = useMemo(() => {
    const realtime = realtimeLogs || [];
    const persisted = (persistedLogs || []).map((l) => ({
      level: l.level,
      message: l.message,
      timestamp: l.timestamp,
    }));
    const filtered = realtime.filter(
      (rl) => !persisted.some((pl) => pl.message === rl.message)
    );
    return [...persisted, ...filtered];
  }, [persistedLogs, realtimeLogs]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] sm:w-[540px]">
        <SheetHeader>
          <SheetTitle className="text-base">Task Logs</SheetTitle>
          <p className="text-sm text-muted-foreground line-clamp-2">
            {taskPrompt}
          </p>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-120px)] mt-4">
          {allLogs.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No logs yet
            </p>
          ) : (
            <div className="space-y-1 font-mono text-xs">
              {allLogs.map((log, i) => (
                <div key={i} className="flex gap-2 py-0.5">
                  <span className="text-muted-foreground shrink-0">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span
                    className={`shrink-0 uppercase font-semibold ${
                      levelColors[log.level] || "text-gray-600"
                    }`}
                  >
                    {log.level}
                  </span>
                  <span className="text-foreground">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
