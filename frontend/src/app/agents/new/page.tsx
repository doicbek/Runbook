"use client";

import Link from "next/link";
import { AgentBuilderForm } from "@/components/agents/agent-builder-form";

export default function NewAgentPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/agents" className="text-xs text-muted-foreground hover:underline">
            ← Back to Agent Studio
          </Link>
          <h1 className="text-2xl font-bold mt-2">New Agent</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Describe your agent, select tools, and generate Python code.
          </p>
        </div>
        <AgentBuilderForm mode="create" />
      </div>
    </div>
  );
}
