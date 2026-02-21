"use client";

import { use } from "react";
import Link from "next/link";
import { AgentBuilderForm } from "@/components/agents/agent-builder-form";
import { useAgentDefinition } from "@/hooks/use-agent-definitions";

export default function EditAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: agent, isLoading, error } = useAgentDefinition(id);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-sm text-muted-foreground">Loading agent...</div>
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-sm text-destructive">
          Failed to load agent: {(error as Error)?.message ?? "Not found"}
        </div>
      </div>
    );
  }

  if (agent.is_builtin) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-sm text-muted-foreground">Built-in agents cannot be edited.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/agents" className="text-xs text-muted-foreground hover:underline">
            ← Back to Agent Studio
          </Link>
          <h1 className="text-2xl font-bold mt-2">Edit Agent: {agent.name}</h1>
        </div>
        <AgentBuilderForm mode="edit" initialData={agent} />
      </div>
    </div>
  );
}
