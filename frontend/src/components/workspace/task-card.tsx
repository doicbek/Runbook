"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useActionStore } from "@/stores/action-store";
import { useRunCode } from "@/hooks/use-tasks";
import { getArtifactUrl } from "@/lib/api/tasks";
import type { Artifact, CodeExecutionState, Task } from "@/types";
import { TaskCardEditor } from "./task-card-editor";
import { TaskLogsDrawer } from "./task-logs-drawer";

const statusConfig: Record<
  string,
  { label: string; dotClass: string; badgeClass: string }
> = {
  pending: {
    label: "Pending",
    dotClass: "bg-gray-400 dark:bg-gray-500",
    badgeClass:
      "bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-800/50 dark:text-gray-400 dark:border-gray-700",
  },
  running: {
    label: "Running",
    dotClass: "bg-blue-500 animate-pulse",
    badgeClass:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-emerald-500",
    badgeClass:
      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800",
  },
  failed: {
    label: "Failed",
    dotClass: "bg-red-500",
    badgeClass:
      "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/50 dark:text-red-300 dark:border-red-800",
  },
};

const agentTypeConfig: Record<string, { label: string; icon: string }> = {
  data_retrieval: { label: "Data", icon: "DB" },
  spreadsheet: { label: "Sheet", icon: "TBL" },
  code_execution: { label: "Code", icon: "{ }" },
  report: { label: "Report", icon: "DOC" },
  general: { label: "General", icon: "GEN" },
};

function hasCodeBlocks(text: string | null | undefined): boolean {
  if (!text) return false;
  return /```(?:python|py)\s*\n/.test(text);
}

export function TaskCard({
  task,
  actionId,
  allTasks,
  index,
}: {
  task: Task;
  actionId: string;
  allTasks: Task[];
  index: number;
}) {
  const [editing, setEditing] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [outputExpanded, setOutputExpanded] = useState(false);
  const taskOverrides = useActionStore((s) => s.taskOverrides);
  const codeExecution = useActionStore((s) => s.codeExecutions[task.id]);
  const override = taskOverrides[task.id];
  const runCode = useRunCode();

  const status = override?.status || task.status;
  const outputSummary = override?.output_summary ?? task.output_summary;
  const config = statusConfig[status] || statusConfig.pending;
  const agentConfig = agentTypeConfig[task.agent_type] || agentTypeConfig.general;

  const depTasks = allTasks.filter((t) => task.dependencies.includes(t.id));
  const hasOutput = outputSummary && status === "completed";
  const showRunCode = hasOutput && hasCodeBlocks(outputSummary);
  const codeIsRunning = codeExecution?.status === "running" || runCode.isPending;

  const handleRunCode = () => {
    useActionStore.getState().setCodeExecution(task.id, {
      status: "running",
      stdout: "",
      stderr: "",
      artifactIds: [],
    });
    runCode.mutate(
      { actionId, taskId: task.id },
      {
        onSuccess: (data) => {
          useActionStore.getState().setCodeExecution(task.id, {
            status: data.exit_code === 0 ? "completed" : "failed",
            stdout: data.stdout,
            stderr: data.stderr,
            artifactIds: data.artifacts.map((a) => a.id),
          });
        },
        onError: (error) => {
          useActionStore.getState().setCodeExecution(task.id, {
            status: "failed",
            stderr: error.message,
          });
        },
      }
    );
  };

  if (editing) {
    return (
      <TaskCardEditor
        task={task}
        actionId={actionId}
        allTasks={allTasks}
        onClose={() => setEditing(false)}
      />
    );
  }

  return (
    <>
      <div
        className="task-card group rounded-lg border bg-card text-card-foreground shadow-sm"
        data-status={status}
      >
        {/* Header: index + agent type + status */}
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold text-muted-foreground/60 tabular-nums">
              #{index + 1}
            </span>
            <span className="text-[10px] font-mono font-semibold tracking-widest uppercase text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">
              {agentConfig.icon}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {agentConfig.label}
            </span>
          </div>
          <Badge
            variant="outline"
            className={`text-[10px] font-medium px-2 py-0.5 gap-1.5 ${config.badgeClass}`}
          >
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${config.dotClass}`} />
            {config.label}
          </Badge>
        </div>

        {/* Prompt section */}
        <div className="px-4 pb-3">
          <p className="text-[13px] leading-relaxed text-foreground">
            {task.prompt}
          </p>
        </div>

        {/* Dependencies */}
        {depTasks.length > 0 && (
          <div className="px-4 pb-3">
            <div className="flex items-center gap-1.5 flex-wrap">
              <svg className="w-3 h-3 text-muted-foreground/50 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2 6h3M8 3v6M5 4l3-1M5 8l3 1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {depTasks.map((d) => (
                <span
                  key={d.id}
                  className="text-[10px] text-muted-foreground bg-muted/40 border border-border/50 px-1.5 py-0.5 rounded-md truncate max-w-[140px]"
                >
                  {d.prompt.slice(0, 35)}{d.prompt.length > 35 ? "..." : ""}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Output section - inline expand/collapse */}
        {hasOutput && (
          <>
            <div className="border-t border-dashed mx-4" />
            <div className="px-4 py-3">
              {/* Output header - clickable to toggle */}
              <button
                onClick={() => setOutputExpanded((v) => !v)}
                className="flex items-center gap-1.5 mb-2 cursor-pointer group/output w-full text-left"
              >
                <svg className="w-3 h-3 text-emerald-500 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="1.5" y="1.5" width="9" height="9" rx="1.5" />
                  <path d="M4 6h4M4 4h2" strokeLinecap="round" />
                </svg>
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Output
                </span>
                <svg
                  className={`w-3 h-3 text-muted-foreground/50 ml-auto transition-transform duration-200 ${
                    outputExpanded ? "rotate-180" : ""
                  }`}
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <path d="M3 4.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {/* Collapsed preview */}
              {!outputExpanded && (
                <button
                  onClick={() => setOutputExpanded(true)}
                  className="w-full text-left cursor-pointer"
                >
                  <div className="output-preview max-h-[60px] overflow-hidden">
                    <div className="prose prose-sm dark:prose-invert max-w-none text-[12px] leading-relaxed prose-headings:text-[13px] prose-headings:font-semibold prose-headings:mb-1 prose-p:mb-0.5 prose-table:text-[10px] prose-th:px-1.5 prose-th:py-0.5 prose-td:px-1.5 prose-td:py-0.5 prose-li:text-[11px] prose-li:my-0">
                      <ReactMarkdown>{outputSummary.slice(0, 200)}</ReactMarkdown>
                    </div>
                  </div>
                </button>
              )}

              {/* Expanded full output */}
              {outputExpanded && (
                <article className="output-prose prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-h1:text-lg prose-h1:mb-2 prose-h1:pb-1.5 prose-h1:border-b prose-h1:border-border/50 prose-h2:text-base prose-h2:mt-4 prose-h2:mb-1.5 prose-h3:text-sm prose-h3:mt-3 prose-p:text-[13px] prose-p:leading-relaxed prose-table:text-[12px] prose-table:border prose-table:border-border prose-table:rounded-md prose-table:overflow-hidden prose-th:px-3 prose-th:py-1.5 prose-th:text-left prose-th:font-semibold prose-th:text-[11px] prose-th:uppercase prose-th:tracking-wider prose-th:bg-muted/50 prose-th:border prose-th:border-border prose-td:px-3 prose-td:py-1.5 prose-td:border prose-td:border-border prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:text-foreground prose-pre:text-[12px] prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none prose-li:text-[13px] prose-blockquote:border-l-[3px] prose-blockquote:border-blue-400 prose-blockquote:dark:border-blue-600 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-muted-foreground prose-hr:border-border/50 prose-img:rounded-lg prose-img:shadow-md">
                  <ReactMarkdown>{outputSummary}</ReactMarkdown>
                </article>
              )}
            </div>
          </>
        )}

        {/* Code Execution Section */}
        {showRunCode && (
          <CodeExecutionSection
            taskId={task.id}
            codeExecution={codeExecution}
            isRunning={codeIsRunning}
            onRunCode={handleRunCode}
          />
        )}

        {/* Error output */}
        {outputSummary && status === "failed" && (
          <div className="mx-4 mb-3 bg-red-50 dark:bg-red-950/20 rounded-md p-2.5 border border-red-200 dark:border-red-800/30">
            <p className="text-[11px] text-red-700 dark:text-red-300 font-mono leading-relaxed">
              {outputSummary}
            </p>
          </div>
        )}

        {/* Actions row */}
        <div className="flex items-center gap-1 px-3 py-2 border-t border-border/50">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] px-2 text-muted-foreground hover:text-foreground"
            onClick={() => setEditing(true)}
            disabled={status === "running"}
          >
            <svg className="w-3 h-3 mr-1" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M8.5 1.5l2 2M1.5 8.5l5-5 2 2-5 5H1.5v-2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] px-2 text-muted-foreground hover:text-foreground"
            onClick={() => setLogsOpen(true)}
          >
            <svg className="w-3 h-3 mr-1" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 3h8M2 6h6M2 9h4" strokeLinecap="round" />
            </svg>
            Logs
          </Button>
          {hasOutput && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[11px] px-2 text-muted-foreground hover:text-foreground"
              onClick={() => setOutputExpanded((v) => !v)}
            >
              <svg className="w-3 h-3 mr-1" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="1.5" y="1.5" width="9" height="9" rx="1.5" />
                <path d="M4 6h4M4 4h2" strokeLinecap="round" />
              </svg>
              {outputExpanded ? "Collapse" : "Expand"}
            </Button>
          )}
          {showRunCode && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[11px] px-2 text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 ml-auto"
              onClick={handleRunCode}
              disabled={codeIsRunning}
            >
              {codeIsRunning ? (
                <>
                  <svg className="w-3 h-3 mr-1 animate-spin" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M6 1v2M6 9v2M1 6h2M9 6h2" strokeLinecap="round" />
                  </svg>
                  Running...
                </>
              ) : (
                <>
                  <svg className="w-3 h-3 mr-1" viewBox="0 0 12 12" fill="currentColor">
                    <path d="M3 1.5l7 4.5-7 4.5V1.5z" />
                  </svg>
                  Run Code
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {logsOpen && (
        <TaskLogsDrawer
          open={logsOpen}
          onOpenChange={setLogsOpen}
          taskId={task.id}
          actionId={actionId}
          taskPrompt={task.prompt}
        />
      )}
    </>
  );
}

function CodeExecutionSection({
  taskId,
  codeExecution,
  isRunning,
  onRunCode,
}: {
  taskId: string;
  codeExecution: CodeExecutionState | undefined;
  isRunning: boolean;
  onRunCode: () => void;
}) {
  if (!codeExecution || codeExecution.status === "idle") return null;

  return (
    <>
      <div className="border-t border-dashed mx-4" />
      <div className="px-4 py-3">
        {/* Section header */}
        <div className="flex items-center gap-1.5 mb-2">
          <svg className="w-3 h-3 text-blue-500 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 3l3 3-3 3M7 9h3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Execution Result
          </span>
          {isRunning && (
            <span className="text-[10px] text-blue-500 animate-pulse ml-auto">Running...</span>
          )}
          {codeExecution.status === "completed" && (
            <span className="text-[10px] text-emerald-500 ml-auto">Success</span>
          )}
          {codeExecution.status === "failed" && (
            <span className="text-[10px] text-red-500 ml-auto">Failed</span>
          )}
        </div>

        {/* Stdout */}
        {codeExecution.stdout && (
          <div className="mb-2">
            <pre className="text-[11px] font-mono leading-relaxed bg-muted/50 border border-border rounded-md p-2.5 overflow-x-auto max-h-[200px] overflow-y-auto whitespace-pre-wrap">
              {codeExecution.stdout}
            </pre>
          </div>
        )}

        {/* Stderr */}
        {codeExecution.stderr && (
          <div className="mb-2">
            <pre className="text-[11px] font-mono leading-relaxed bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/30 rounded-md p-2.5 overflow-x-auto max-h-[200px] overflow-y-auto text-red-700 dark:text-red-300 whitespace-pre-wrap">
              {codeExecution.stderr}
            </pre>
          </div>
        )}

        {/* Artifacts - inline images and download links */}
        {codeExecution.artifactIds.length > 0 && (
          <div className="space-y-2">
            {codeExecution.artifactIds.map((artifactId) => (
              <ArtifactDisplay key={artifactId} artifactId={artifactId} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function ArtifactDisplay({ artifactId }: { artifactId: string }) {
  const url = getArtifactUrl(artifactId);

  // We render the image inline optimistically (the content endpoint will set correct mime type)
  // For non-images, we show a download link
  return (
    <div className="artifact-item">
      {/* Try rendering as image - if it fails, show download link */}
      <ArtifactImage url={url} artifactId={artifactId} />
    </div>
  );
}

function ArtifactImage({ url, artifactId }: { url: string; artifactId: string }) {
  const [isImage, setIsImage] = useState(true);
  const [loaded, setLoaded] = useState(false);

  if (!isImage) {
    return (
      <a
        href={url}
        download
        className="inline-flex items-center gap-1.5 text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
      >
        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M6 1v8M3 6l3 3 3-3M2 10h8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Download artifact
      </a>
    );
  }

  return (
    <div className="relative">
      {!loaded && (
        <div className="h-32 bg-muted/30 rounded-md animate-pulse flex items-center justify-center">
          <span className="text-[10px] text-muted-foreground">Loading...</span>
        </div>
      )}
      <img
        src={url}
        alt="Generated artifact"
        className={`rounded-md border border-border shadow-sm max-w-full ${loaded ? "" : "hidden"}`}
        onLoad={() => setLoaded(true)}
        onError={() => setIsImage(false)}
      />
    </div>
  );
}
