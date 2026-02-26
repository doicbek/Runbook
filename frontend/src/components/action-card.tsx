"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { ActionListItem } from "@/types";

const statusConfig: Record<string, {
  badge: string;
  dot: string;
  border: string;
}> = {
  draft: {
    badge: "bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-800/50 dark:text-gray-400 dark:border-gray-700",
    dot: "bg-gray-400 dark:bg-gray-500",
    border: "border-l-gray-300 dark:border-l-gray-600",
  },
  running: {
    badge: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800",
    dot: "bg-blue-500 animate-pulse",
    border: "border-l-blue-400 dark:border-l-blue-500",
  },
  completed: {
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800",
    dot: "bg-emerald-500",
    border: "border-l-emerald-400 dark:border-l-emerald-500",
  },
  failed: {
    badge: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/50 dark:text-red-300 dark:border-red-800",
    dot: "bg-red-500",
    border: "border-l-red-400 dark:border-l-red-500",
  },
};

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function ActionCard({ action }: { action: ActionListItem }) {
  const config = statusConfig[action.status] || statusConfig.draft;

  return (
    <Link href={`/actions/${action.id}`} className="block h-full">
      <div
        className={`group rounded-xl border border-l-[3px] bg-card text-card-foreground shadow-sm hover:shadow-md transition-all duration-200 cursor-pointer h-full flex flex-col ${config.border}`}
      >
        <div className="p-4 flex flex-col h-full">
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="text-sm font-semibold leading-snug line-clamp-2 flex-1">
              {action.title}
            </h3>
            <Badge
              variant="outline"
              className={`shrink-0 text-[10px] font-medium gap-1.5 ${config.badge}`}
            >
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${config.dot}`} />
              {action.status}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed flex-1 mb-3">
            {action.root_prompt}
          </p>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="1" y="1" width="4" height="4" rx="0.75" />
                <rect x="7" y="1" width="4" height="4" rx="0.75" />
                <rect x="4" y="7" width="4" height="4" rx="0.75" />
              </svg>
              {action.task_count} task{action.task_count !== 1 ? "s" : ""}
            </span>
            <span>{timeAgo(action.updated_at)}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}
