"use client";

import { useMemo } from "react";
import type { Task } from "@/types";
import { TaskCard } from "./task-card";
import { AddTaskDialog } from "./add-task-dialog";

/** Group tasks into tiers for DAG visualization.
 *  Tier 0 = tasks with no dependencies (roots).
 *  Tier N = tasks whose dependencies are all in tiers < N.
 */
function computeTiers(tasks: Task[]): Task[][] {
  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const tierOf = new Map<string, number>();

  function getTier(id: string): number {
    if (tierOf.has(id)) return tierOf.get(id)!;
    const task = taskMap.get(id);
    if (!task || task.dependencies.length === 0) {
      tierOf.set(id, 0);
      return 0;
    }
    const maxDepTier = Math.max(
      ...task.dependencies
        .filter((d) => taskMap.has(d))
        .map((d) => getTier(d))
    );
    const tier = maxDepTier + 1;
    tierOf.set(id, tier);
    return tier;
  }

  for (const task of tasks) {
    getTier(task.id);
  }

  const tiers: Task[][] = [];
  for (const task of tasks) {
    const tier = tierOf.get(task.id) || 0;
    while (tiers.length <= tier) tiers.push([]);
    tiers[tier].push(task);
  }

  return tiers;
}

/** Build a global index map based on topological order */
function buildIndexMap(tiers: Task[][]): Map<string, number> {
  const map = new Map<string, number>();
  let idx = 0;
  for (const tier of tiers) {
    for (const task of tier) {
      map.set(task.id, idx++);
    }
  }
  return map;
}

export function TaskBoard({
  tasks,
  actionId,
}: {
  tasks: Task[];
  actionId: string;
}) {
  const tiers = useMemo(() => computeTiers(tasks), [tasks]);
  const indexMap = useMemo(() => buildIndexMap(tiers), [tiers]);

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <AddTaskDialog actionId={actionId} existingTasks={tasks} />
      </div>
      {tasks.length === 0 ? (
        <div className="text-center py-16">
          <div className="inline-flex flex-col items-center gap-2">
            <svg className="w-8 h-8 text-muted-foreground/30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="8.5" y="14" width="7" height="7" rx="1.5" />
              <path d="M6.5 10v2.5a1.5 1.5 0 001.5 1.5h.5M17.5 10v2.5a1.5 1.5 0 01-1.5 1.5h-.5" />
            </svg>
            <p className="text-sm text-muted-foreground">No tasks yet</p>
          </div>
        </div>
      ) : (
        <div className="space-y-0">
          {tiers.map((tier, tierIdx) => (
            <div key={tierIdx}>
              {/* Connector arrow between tiers */}
              {tierIdx > 0 && (
                <div className="dag-connector">
                  <svg width="16" height="24" viewBox="0 0 16 24" fill="none">
                    <path
                      d="M8 0v18M4 14l4 6 4-6"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              )}

              {/* Tier label */}
              <div className="flex items-center gap-2 mb-2 px-1">
                <div className="h-px flex-1 bg-border/50" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/50">
                  {tierIdx === 0
                    ? "Independent"
                    : tierIdx === tiers.length - 1 && tiers.length > 1
                      ? "Final"
                      : `Tier ${tierIdx + 1}`}
                </span>
                <div className="h-px flex-1 bg-border/50" />
              </div>

              {/* Cards in this tier */}
              <div className="grid grid-cols-1 gap-3">
                {tier.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    actionId={actionId}
                    allTasks={tasks}
                    index={indexMap.get(task.id) || 0}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
