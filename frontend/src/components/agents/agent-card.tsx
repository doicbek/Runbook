"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { AgentDefinition } from "@/types";

const statusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  draft: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const REAL_BUILTINS = new Set([
  "arxiv_search",
  "code_execution",
  "data_retrieval",
  "spreadsheet",
  "report",
  "general",
]);

function implBadge(agent: AgentDefinition) {
  if (!agent.is_builtin && agent.code) return { label: "Custom code", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" };
  if (!agent.is_builtin) return { label: "No code", cls: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400" };
  if (REAL_BUILTINS.has(agent.agent_type)) return { label: "Native Python", cls: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400" };
  return { label: "Mock (LLM)", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400" };
}

export function AgentCard({ agent }: { agent: AgentDefinition }) {
  const impl = implBadge(agent);

  return (
    <Link href={`/agents/${agent.id}`} className="block group">
      <Card className="flex flex-col h-full transition-shadow hover:shadow-md group-hover:ring-1 group-hover:ring-primary/30">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-2xl shrink-0" aria-hidden="true">{agent.icon}</span>
              <div className="min-w-0">
                <h3 className="font-semibold text-sm leading-tight truncate">{agent.name}</h3>
                <code className="text-xs text-muted-foreground font-mono">{agent.agent_type}</code>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${statusColors[agent.status] ?? ""}`}>
                {agent.status}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${impl.cls}`}>
                {impl.label}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col gap-3 pt-0">
          <p className="text-xs text-muted-foreground leading-relaxed">{agent.description}</p>
          {agent.tools.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-auto">
              {agent.tools.map((t) => (
                <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
              ))}
            </div>
          )}
          {agent.is_builtin && (
            <Badge variant="outline" className="text-xs w-fit">Built-in</Badge>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
