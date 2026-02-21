"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AgentCard } from "@/components/agents/agent-card";
import { useAgentDefinitions } from "@/hooks/use-agent-definitions";

export default function AgentsPage() {
  const { data: agents, isLoading, error } = useAgentDefinitions();

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Agent Studio</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Define custom agents with their own tools and code.
            </p>
          </div>
          <Link href="/agents/new">
            <Button>+ New Agent</Button>
          </Link>
        </div>

        {isLoading && (
          <div className="text-sm text-muted-foreground">Loading agents...</div>
        )}

        {error && (
          <div className="text-sm text-destructive">
            Failed to load agents: {(error as Error).message}
          </div>
        )}

        {agents && agents.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-4xl mb-3">🤖</p>
            <p className="text-sm">No agents yet. Create your first custom agent.</p>
          </div>
        )}

        {agents && agents.length > 0 && (
          <>
            {/* Builtins section */}
            {agents.some((a) => a.is_builtin) && (
              <section className="mb-8">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  Built-in Agents
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {agents.filter((a) => a.is_builtin).map((agent) => (
                    <AgentCard key={agent.id} agent={agent} />
                  ))}
                </div>
              </section>
            )}

            {/* Custom agents section */}
            {agents.some((a) => !a.is_builtin) && (
              <section>
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  Custom Agents
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {agents.filter((a) => !a.is_builtin).map((agent) => (
                    <AgentCard key={agent.id} agent={agent} />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
