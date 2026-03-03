"use client";

import { useMemo } from "react";
import DOMPurify from "dompurify";
import { html as diff2html } from "diff2html";
import { ColorSchemeType } from "diff2html/lib/types";
import "diff2html/bundles/css/diff2html.min.css";

interface DiffViewerProps {
  filePath?: string;
  diff: string;
}

export function DiffViewer({ filePath, diff }: DiffViewerProps) {
  const htmlContent = useMemo(() => {
    // Ensure the diff has a proper unified diff header so diff2html can parse it
    let normalizedDiff = diff;
    if (!normalizedDiff.startsWith("---") && !normalizedDiff.startsWith("diff ")) {
      // Wrap raw diff content with minimal headers
      const name = filePath || "file";
      normalizedDiff = `--- a/${name}\n+++ b/${name}\n${normalizedDiff}`;
    }

    try {
      return diff2html(normalizedDiff, {
        outputFormat: "line-by-line",
        drawFileList: false,
        matching: "lines",
        colorScheme: ColorSchemeType.DARK,
      });
    } catch {
      return null;
    }
  }, [diff, filePath]);

  if (!htmlContent) {
    // Fallback: render raw diff with basic coloring
    return (
      <div className="rounded overflow-hidden">
        {filePath && (
          <div className="px-2 py-1 bg-muted/40 border-b border-border/30 text-[10px] font-mono text-muted-foreground">
            {filePath}
          </div>
        )}
        <pre className="text-[10px] font-mono p-2 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre bg-zinc-950">
          {diff.split("\n").map((line, i) => {
            let color = "text-muted-foreground";
            if (line.startsWith("+") && !line.startsWith("+++")) color = "text-emerald-400";
            else if (line.startsWith("-") && !line.startsWith("---")) color = "text-red-400";
            else if (line.startsWith("@@")) color = "text-blue-400";
            return (
              <span key={i} className={color}>
                {line}
                {"\n"}
              </span>
            );
          })}
        </pre>
      </div>
    );
  }

  return (
    <div className="rounded overflow-hidden diff-viewer-wrapper">
      {filePath && (
        <div className="px-2 py-1 bg-muted/40 border-b border-border/30 text-[10px] font-mono text-muted-foreground">
          {filePath}
        </div>
      )}
      <div
        className="text-[10px] max-h-[300px] overflow-auto"
        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(htmlContent) }}
      />
      <style jsx global>{`
        .diff-viewer-wrapper .d2h-wrapper {
          font-size: 10px;
        }
        .diff-viewer-wrapper .d2h-file-header {
          display: none;
        }
        .diff-viewer-wrapper .d2h-file-wrapper {
          border: none;
          margin: 0;
        }
        .diff-viewer-wrapper .d2h-code-line-ctn {
          font-size: 10px;
          font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
        }
        .diff-viewer-wrapper .d2h-code-line-prefix {
          font-size: 10px;
        }
        .diff-viewer-wrapper .d2h-code-linenumber {
          font-size: 9px;
        }
        .diff-viewer-wrapper .d2h-diff-table {
          font-size: 10px;
        }
        .diff-viewer-wrapper .d2h-ins.d2h-change,
        .diff-viewer-wrapper .d2h-ins {
          background-color: rgba(16, 185, 129, 0.1);
        }
        .diff-viewer-wrapper .d2h-del.d2h-change,
        .diff-viewer-wrapper .d2h-del {
          background-color: rgba(239, 68, 68, 0.1);
        }
        .diff-viewer-wrapper ins.d2h-change {
          background-color: rgba(16, 185, 129, 0.25);
        }
        .diff-viewer-wrapper del.d2h-change {
          background-color: rgba(239, 68, 68, 0.25);
        }
        .diff-viewer-wrapper .d2h-info {
          background-color: rgba(59, 130, 246, 0.05);
          color: rgb(147, 157, 173);
        }
        .diff-viewer-wrapper .d2h-code-side-line,
        .diff-viewer-wrapper .d2h-code-line {
          background-color: transparent;
        }
      `}</style>
    </div>
  );
}
