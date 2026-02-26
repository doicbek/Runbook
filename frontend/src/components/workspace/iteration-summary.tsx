"use client";

import { useActionStore } from "@/stores/action-store";
import type { CurrentIterationInfo, RetryStatus } from "@/stores/action-store";
import type { AgentIteration } from "@/types";

const MAX_ITERATIONS = 50;

function formatToolAction(current: CurrentIterationInfo): string {
  if (!current.tool) return "Thinking...";
  const toolLabels: Record<string, string> = {
    read_file: "Reading file",
    write_file: "Writing file",
    edit_file: "Editing file",
    glob: "Searching files",
    grep: "Searching code",
    bash: "Running command",
    done: "Finishing up",
    fail: "Reporting failure",
  };
  return toolLabels[current.tool] || `Using ${current.tool}`;
}

function CompletedSummary({ iterations }: { iterations: AgentIteration[] }) {
  const total = iterations.length;
  const failed = iterations.filter((i) => i.outcome === "failed").length;
  const tools = iterations.flatMap((i) => i.tool_calls);
  const totalDuration = iterations.reduce((s, i) => s + (i.duration_ms || 0), 0);
  const seconds = Math.round(totalDuration / 1000);

  return (
    <div className="flex items-center gap-2">
      <svg className="w-3 h-3 text-emerald-500 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M2.5 6.5l2.5 2.5 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[11px] text-muted-foreground">
        Completed in {total} iteration{total !== 1 ? "s" : ""}
        {tools.length > 0 && <> &middot; {tools.length} tool call{tools.length !== 1 ? "s" : ""}</>}
        {failed > 0 && <> &middot; <span className="text-amber-500">{failed} failed</span></>}
        {seconds > 0 && <> &middot; {seconds}s</>}
      </span>
    </div>
  );
}

function RunningStatus({
  current,
  iterationCount,
}: {
  current: CurrentIterationInfo;
  iterationCount: number;
}) {
  const actionText = formatToolAction(current);
  const reasoningSnippet = current.reasoning
    ? current.reasoning.slice(0, 80) + (current.reasoning.length > 80 ? "..." : "")
    : null;

  return (
    <div className="space-y-1.5">
      {/* Status line */}
      <div className="flex items-center gap-2">
        <svg className="w-3 h-3 text-blue-400 animate-spin shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M6 1v2M6 9v2M1 6h2M9 6h2" strokeLinecap="round" />
        </svg>
        <span className="text-[11px] text-blue-400 font-medium">
          Iteration {current.iteration_number}/{MAX_ITERATIONS}
        </span>
        <span className="text-[10px] text-muted-foreground/60">&middot;</span>
        <span className="text-[11px] text-muted-foreground truncate">
          {actionText}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-muted/30 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500/60 rounded-full transition-all duration-300"
          style={{ width: `${Math.min((iterationCount / MAX_ITERATIONS) * 100, 100)}%` }}
        />
      </div>

      {/* Reasoning snippet */}
      {reasoningSnippet && (
        <p className="text-[10px] text-muted-foreground/70 italic truncate">
          {reasoningSnippet}
        </p>
      )}
    </div>
  );
}

function RetryBanner({ retry }: { retry: RetryStatus }) {
  return (
    <div className="flex items-center gap-2 px-2 py-1 rounded bg-amber-500/10 border border-amber-500/20">
      <svg className="w-3 h-3 text-amber-500 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M1.5 6a4.5 4.5 0 018.18-2.6M10.5 6a4.5 4.5 0 01-8.18 2.6" strokeLinecap="round" />
        <path d="M10.5 1v2.4h-2.4M1.5 11V8.6h2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[11px] text-amber-500 font-medium">
        Retry {retry.attempt}/{retry.max_attempts}
      </span>
      <span className="text-[10px] text-muted-foreground">
        &mdash; trying alternative approach
      </span>
    </div>
  );
}

export function IterationSummary({ taskId }: { taskId: string }) {
  const iterations = useActionStore((s) => s.taskIterations[taskId]);
  const current = useActionStore((s) => s.currentIteration[taskId]);
  const retry = useActionStore((s) => s.retryStatus[taskId]);

  const hasIterations = (iterations && iterations.length > 0) || current;
  if (!hasIterations) return null;

  const iterationCount = iterations?.length ?? 0;
  const lastIteration = iterations?.[iterationCount - 1];

  // Determine if the task completed or is still running based on current iteration state
  const isCompleted = !current && lastIteration?.outcome === "completed";
  const isFailed = !current && lastIteration?.outcome === "failed";

  return (
    <div className="mx-4 mb-3 rounded-md border border-border/50 bg-muted/20 px-3 py-2 space-y-2">
      {/* Retry banner */}
      {retry && <RetryBanner retry={retry} />}

      {/* Main status */}
      {isCompleted && iterations && (
        <CompletedSummary iterations={iterations} />
      )}
      {isFailed && (
        <div className="flex items-center gap-2">
          <svg className="w-3 h-3 text-red-500 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 3l6 6M9 3l-6 6" strokeLinecap="round" />
          </svg>
          <span className="text-[11px] text-red-400">
            Failed after {iterationCount} iteration{iterationCount !== 1 ? "s" : ""}
            {lastIteration?.error && <> &mdash; {lastIteration.error.slice(0, 60)}</>}
          </span>
        </div>
      )}
      {current && (
        <RunningStatus current={current} iterationCount={iterationCount} />
      )}

      {/* Latest tool call one-liner (when running and we have completed iterations) */}
      {current && lastIteration && lastIteration.tool_calls.length > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-muted-foreground/60">Last:</span>
          <span className="text-[10px] text-muted-foreground truncate">
            {(() => {
              const lastCall = lastIteration.tool_calls[lastIteration.tool_calls.length - 1];
              const truncOutput = lastCall.output?.slice(0, 60) || "";
              return `${lastCall.tool} ${lastCall.success ? "\u2713" : "\u2717"} ${truncOutput}${(lastCall.output?.length ?? 0) > 60 ? "..." : ""}`;
            })()}
          </span>
        </div>
      )}
    </div>
  );
}
