"use client";

interface TerminalViewerProps {
  command?: string;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
}

export function TerminalViewer({
  command,
  stdout,
  stderr,
  exitCode,
}: TerminalViewerProps) {
  const isSuccess = exitCode === 0;

  return (
    <div className="rounded overflow-hidden border border-border/30 bg-zinc-950">
      {/* Command prompt line */}
      {command && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border-b border-zinc-800">
          <span className="text-[10px] text-emerald-400 font-mono select-none shrink-0">
            $
          </span>
          <span className="text-[11px] font-mono text-zinc-200 break-all">
            {command}
          </span>
        </div>
      )}

      {/* Output area */}
      <div className="max-h-[300px] overflow-auto">
        {/* stdout */}
        {stdout && (
          <pre className="text-[10px] font-mono text-zinc-300 px-3 py-2 whitespace-pre-wrap break-all leading-relaxed">
            {stdout.slice(0, 5000)}
          </pre>
        )}

        {/* stderr */}
        {stderr && (
          <pre className="text-[10px] font-mono text-orange-400 px-3 py-2 whitespace-pre-wrap break-all leading-relaxed border-t border-zinc-800/50">
            {stderr.slice(0, 5000)}
          </pre>
        )}

        {/* Empty output */}
        {!stdout && !stderr && (
          <div className="px-3 py-2 text-[10px] text-zinc-600 italic font-mono">
            (no output)
          </div>
        )}
      </div>

      {/* Exit code footer */}
      {exitCode !== undefined && (
        <div className="flex items-center gap-1.5 px-3 py-1 bg-zinc-900 border-t border-zinc-800">
          {isSuccess ? (
            <span className="text-[10px] text-emerald-500">✓</span>
          ) : (
            <span className="text-[10px] text-red-500">✗</span>
          )}
          <span
            className={`text-[9px] font-mono ${
              isSuccess ? "text-emerald-500/70" : "text-red-500/70"
            }`}
          >
            exit {exitCode}
          </span>
        </div>
      )}
    </div>
  );
}
