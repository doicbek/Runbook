"use client";

import { useEffect, useRef, useState } from "react";
import { useActionStore } from "@/stores/action-store";
import type { RetryStatus } from "@/stores/action-store";
import type { AgentIteration, AgentIterationToolCall } from "@/types";
import { DiffViewer } from "./diff-viewer";
import { TerminalViewer } from "./terminal-viewer";

const toolIcons: Record<string, string> = {
  read_file: "📄",
  write_file: "✏️",
  edit_file: "🔧",
  glob: "🔍",
  grep: "🔎",
  bash: "💻",
  done: "✅",
  fail: "❌",
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = (ms / 1000).toFixed(1);
  return `${s}s`;
}

function iterationSummaryLine(iteration: AgentIteration): string {
  if (iteration.tool_calls.length === 0) {
    if (iteration.outcome === "user_guidance") return "User guidance provided";
    return iteration.reasoning?.slice(0, 80) || "No tool calls";
  }
  const tools = iteration.tool_calls.map((tc) => tc.tool);
  const uniqueTools = [...new Set(tools)];
  const failed = iteration.tool_calls.filter((tc) => !tc.success).length;
  let line = uniqueTools.join(", ");
  if (failed > 0) line += ` (${failed} failed)`;
  return line;
}

function parseBashOutput(
  output: string | undefined,
  success: boolean
): { stdout?: string; stderr?: string; exitCode?: number } {
  if (!output) return { exitCode: success ? 0 : 1 };
  try {
    const parsed = JSON.parse(output);
    if (typeof parsed === "object" && parsed !== null && ("stdout" in parsed || "stderr" in parsed)) {
      return {
        stdout: parsed.stdout || undefined,
        stderr: parsed.stderr || undefined,
        exitCode: typeof parsed.exit_code === "number" ? parsed.exit_code : (success ? 0 : 1),
      };
    }
  } catch {
    // Not JSON — treat as raw output
  }
  return {
    stdout: success ? output : undefined,
    stderr: !success ? output : undefined,
    exitCode: success ? 0 : 1,
  };
}

function ToolCallDetail({ call }: { call: AgentIterationToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const icon = toolIcons[call.tool] || "⚙️";

  return (
    <div className="border border-border/30 rounded bg-muted/10">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-muted/20 transition-colors"
      >
        <span className="text-[11px]">{icon}</span>
        <span className="text-[11px] font-mono text-foreground">
          {call.tool}
        </span>
        {call.success ? (
          <span className="text-[10px] text-emerald-500">✓</span>
        ) : (
          <span className="text-[10px] text-red-500">✗</span>
        )}
        <span className="text-[10px] text-muted-foreground/60 ml-auto tabular-nums">
          {formatDuration(call.duration_ms)}
        </span>
        <svg
          className={`w-2.5 h-2.5 text-muted-foreground/40 transition-transform ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M3 4.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {expanded && (
        <div className="px-2 pb-2 space-y-1.5 border-t border-border/20">
          {/* Input */}
          <div className="mt-1.5">
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60 font-medium">
              Input
            </span>
            <pre className="text-[10px] font-mono text-muted-foreground bg-muted/30 rounded p-1.5 mt-0.5 overflow-x-auto max-h-[120px] overflow-y-auto whitespace-pre-wrap break-all">
              {typeof call.input === "object"
                ? JSON.stringify(call.input, null, 2).slice(0, 2000)
                : String(call.input).slice(0, 2000)}
            </pre>
          </div>
          {/* Output */}
          <div>
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60 font-medium">
              Output
            </span>
            {(call.tool === "edit_file" || call.tool === "write_file") &&
            call.output &&
            (call.output.includes("---") || call.output.includes("+++") || call.output.includes("@@") || call.output.startsWith("+") || call.output.startsWith("-")) ? (
              <div className="mt-0.5">
                <DiffViewer
                  filePath={
                    typeof call.input === "object" && call.input !== null
                      ? (call.input as Record<string, unknown>).path as string | undefined
                      : undefined
                  }
                  diff={call.output.slice(0, 5000)}
                />
              </div>
            ) : call.tool === "bash" ? (
              <div className="mt-0.5">
                <TerminalViewer
                  command={
                    typeof call.input === "object" && call.input !== null
                      ? (call.input as Record<string, unknown>).command as string | undefined
                      : undefined
                  }
                  {...parseBashOutput(call.output, call.success)}
                />
              </div>
            ) : (
              <pre
                className={`text-[10px] font-mono rounded p-1.5 mt-0.5 overflow-x-auto max-h-[120px] overflow-y-auto whitespace-pre-wrap break-all ${
                  call.success
                    ? "text-muted-foreground bg-muted/30"
                    : "text-red-400 bg-red-500/5"
                }`}
              >
                {(call.output || "(empty)").slice(0, 2000)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function IterationRow({
  iteration,
  isLatest,
}: {
  iteration: AgentIteration;
  isLatest: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess =
    iteration.outcome === "completed" || iteration.outcome === "continue";
  const isFailed = iteration.outcome === "failed";
  const isGuidance = iteration.outcome === "user_guidance";

  const borderColor = isFailed
    ? "border-l-red-500"
    : isGuidance
      ? "border-l-blue-400"
      : isSuccess
        ? "border-l-emerald-500/50"
        : "border-l-border";

  const allToolsSucceeded =
    iteration.tool_calls.length > 0 &&
    iteration.tool_calls.every((tc) => tc.success);
  const anyToolFailed = iteration.tool_calls.some((tc) => !tc.success);

  return (
    <div className={`border-l-2 ${borderColor}`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-muted/20 transition-colors"
      >
        {/* Iteration number */}
        <span className="text-[10px] font-mono text-muted-foreground/60 tabular-nums w-5 shrink-0">
          #{iteration.iteration_number}
        </span>

        {/* Tool icons */}
        <span className="flex items-center gap-0.5 shrink-0">
          {iteration.tool_calls.length > 0
            ? [...new Set(iteration.tool_calls.map((tc) => tc.tool))].map(
                (tool, i) => (
                  <span key={i} className="text-[10px]" title={tool}>
                    {toolIcons[tool] || "⚙️"}
                  </span>
                )
              )
            : isGuidance
              ? <span className="text-[10px]" title="User guidance">👤</span>
              : <span className="text-[10px]" title="Thinking">💭</span>}
        </span>

        {/* Summary */}
        <span className="text-[11px] text-muted-foreground truncate flex-1">
          {iterationSummaryLine(iteration)}
        </span>

        {/* Success/fail badge */}
        {allToolsSucceeded && (
          <span className="text-[10px] text-emerald-500 shrink-0">✓</span>
        )}
        {anyToolFailed && (
          <span className="text-[10px] text-red-500 shrink-0">✗</span>
        )}
        {iteration.outcome === "completed" && (
          <span className="text-[9px] bg-emerald-500/10 text-emerald-500 px-1 py-0.5 rounded shrink-0">
            done
          </span>
        )}
        {isFailed && (
          <span className="text-[9px] bg-red-500/10 text-red-500 px-1 py-0.5 rounded shrink-0">
            fail
          </span>
        )}

        {/* Duration */}
        {iteration.duration_ms > 0 && (
          <span className="text-[10px] text-muted-foreground/50 tabular-nums shrink-0">
            {formatDuration(iteration.duration_ms)}
          </span>
        )}

        <svg
          className={`w-2.5 h-2.5 text-muted-foreground/40 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M3 4.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-3 pb-2.5 space-y-2 bg-muted/5">
          {/* Reasoning */}
          {iteration.reasoning && (
            <div>
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60 font-medium">
                Reasoning
              </span>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 whitespace-pre-wrap">
                {iteration.reasoning}
              </p>
            </div>
          )}

          {/* Tool calls */}
          {iteration.tool_calls.length > 0 && (
            <div className="space-y-1">
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60 font-medium">
                Tool Calls ({iteration.tool_calls.length})
              </span>
              {iteration.tool_calls.map((call, i) => (
                <ToolCallDetail key={i} call={call} />
              ))}
            </div>
          )}

          {/* Error */}
          {iteration.error && (
            <div>
              <span className="text-[9px] uppercase tracking-wider text-red-400/60 font-medium">
                Error
              </span>
              <p className="text-[11px] text-red-400 font-mono mt-0.5 whitespace-pre-wrap">
                {iteration.error}
              </p>
            </div>
          )}

          {/* Lessons learned */}
          {iteration.lessons_learned && (
            <div>
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60 font-medium">
                Lessons Learned
              </span>
              <p className="text-[11px] text-muted-foreground italic mt-0.5">
                {iteration.lessons_learned}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function IterationTimeline({ taskId }: { taskId: string }) {
  const iterations = useActionStore((s) => s.taskIterations[taskId]);
  const current = useActionStore((s) => s.currentIteration[taskId]);
  const retry = useActionStore((s) => s.retryStatus[taskId]);
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const hasIterations = iterations && iterations.length > 0;
  const isRunning = !!current;

  // Auto-scroll to latest iteration when running
  useEffect(() => {
    if (isRunning && expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [iterations?.length, isRunning, expanded]);

  if (!hasIterations) return null;

  // Group iterations by attempt for visual sectioning
  const primaryIterations = iterations.filter(
    (i) => i.loop_type === "primary" || i.loop_type === "user_guidance"
  );
  const retryGroups: Record<number, AgentIteration[]> = {};
  for (const iter of iterations) {
    if (iter.loop_type === "retry") {
      if (!retryGroups[iter.attempt_number]) {
        retryGroups[iter.attempt_number] = [];
      }
      retryGroups[iter.attempt_number].push(iter);
    }
  }
  const retryAttemptNumbers = Object.keys(retryGroups)
    .map(Number)
    .sort((a, b) => a - b);
  const hasRetries = retryAttemptNumbers.length > 0;

  return (
    <div className="mx-4 mb-3">
      {/* Expand/collapse toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 w-full text-left py-1 group/toggle"
      >
        <svg
          className={`w-3 h-3 text-muted-foreground/50 transition-transform duration-200 ${
            expanded ? "rotate-180" : ""
          }`}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path
            d="M3 4.5l3 3 3-3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 group-hover/toggle:text-muted-foreground transition-colors">
          Iteration Timeline
        </span>
        <span className="text-[10px] text-muted-foreground/40 tabular-nums">
          ({iterations.length})
        </span>
      </button>

      {/* Timeline content */}
      {expanded && (
        <div
          ref={scrollRef}
          className="mt-1 rounded-md border border-border/50 bg-muted/10 overflow-hidden max-h-[400px] overflow-y-auto"
        >
          {/* Primary attempt section */}
          {primaryIterations.length > 0 && (
            <div>
              {hasRetries && (
                <div className="px-2.5 py-1 bg-muted/30 border-b border-border/30">
                  <span className="text-[9px] uppercase tracking-wider font-semibold text-muted-foreground/70">
                    Primary Attempt
                  </span>
                </div>
              )}
              {primaryIterations.map((iter, i) => (
                <IterationRow
                  key={iter.id}
                  iteration={iter}
                  isLatest={
                    !isRunning &&
                    !hasRetries &&
                    i === primaryIterations.length - 1
                  }
                />
              ))}
            </div>
          )}

          {/* Retry attempt sections */}
          {retryAttemptNumbers.map((attemptNum) => (
            <div key={attemptNum}>
              <div className="px-2.5 py-1 bg-amber-500/5 border-y border-amber-500/10">
                <span className="text-[9px] uppercase tracking-wider font-semibold text-amber-500/70">
                  Retry Attempt {attemptNum}
                </span>
              </div>
              {retryGroups[attemptNum].map((iter, i) => (
                <IterationRow
                  key={iter.id}
                  iteration={iter}
                  isLatest={
                    !isRunning &&
                    attemptNum === retryAttemptNumbers[retryAttemptNumbers.length - 1] &&
                    i === retryGroups[attemptNum].length - 1
                  }
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
