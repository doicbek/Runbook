"use client";

import ReactMarkdown from "react-markdown";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";

const agentTypeConfig: Record<string, { label: string; icon: string }> = {
  data_retrieval: { label: "Data Retrieval", icon: "DB" },
  spreadsheet: { label: "Spreadsheet", icon: "TBL" },
  code_execution: { label: "Code Execution", icon: "{ }" },
  report: { label: "Report", icon: "DOC" },
  general: { label: "General", icon: "GEN" },
};

export function TaskOutputViewer({
  open,
  onOpenChange,
  output,
  agentType,
  taskPrompt,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  output: string;
  agentType: string;
  taskPrompt: string;
}) {
  const config = agentTypeConfig[agentType] || agentTypeConfig.general;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[520px] sm:w-[680px] lg:w-[780px] p-0 flex flex-col">
        {/* Header with task context */}
        <SheetHeader className="px-6 pt-6 pb-4 border-b shrink-0 space-y-3">
          <div className="flex items-center gap-3">
            <SheetTitle className="text-base font-semibold">
              Task Output
            </SheetTitle>
            <span className="text-[10px] font-mono font-semibold tracking-widest uppercase text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">
              {config.icon}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {config.label}
            </span>
          </div>

          {/* Task prompt as context */}
          <div className="bg-muted/30 rounded-md px-3 py-2 border border-border/50">
            <div className="flex items-center gap-1.5 mb-1">
              <svg className="w-3 h-3 text-muted-foreground/60" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2 3h8M2 6h6M2 9h4" strokeLinecap="round" />
              </svg>
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                Prompt
              </span>
            </div>
            <p className="text-[13px] text-foreground/80 leading-relaxed">
              {taskPrompt}
            </p>
          </div>
        </SheetHeader>

        {/* Output content */}
        <ScrollArea className="flex-1 px-6 py-5">
          <article className="output-prose prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-h1:text-xl prose-h1:mb-3 prose-h1:pb-2 prose-h1:border-b prose-h1:border-border/50 prose-h2:text-lg prose-h2:mt-6 prose-h2:mb-2 prose-h3:text-base prose-h3:mt-4 prose-p:text-[13px] prose-p:leading-relaxed prose-table:text-[12px] prose-table:border prose-table:border-border prose-table:rounded-md prose-table:overflow-hidden prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-semibold prose-th:text-[11px] prose-th:uppercase prose-th:tracking-wider prose-th:bg-muted/50 prose-th:border prose-th:border-border prose-td:px-3 prose-td:py-2 prose-td:border prose-td:border-border prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-pre:text-foreground prose-pre:text-[12px] prose-code:text-foreground prose-code:before:content-none prose-code:after:content-none prose-li:text-[13px] prose-blockquote:border-l-[3px] prose-blockquote:border-blue-400 prose-blockquote:dark:border-blue-600 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-muted-foreground prose-hr:border-border/50 prose-img:rounded-lg prose-img:shadow-md">
            <ReactMarkdown>{output}</ReactMarkdown>
          </article>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
