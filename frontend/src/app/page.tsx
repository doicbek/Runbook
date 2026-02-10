"use client";

import { ActionList } from "@/components/action-list";
import { CreateActionDialog } from "@/components/create-action-dialog";
import { ThemeToggle } from "@/components/theme-toggle";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Actions</h1>
            <p className="text-muted-foreground mt-1">
              Create and manage agentic workflows
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <CreateActionDialog />
          </div>
        </div>
        <ActionList />
      </div>
    </main>
  );
}
