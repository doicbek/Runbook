"use client";

import Link from "next/link";
import { ActionList } from "@/components/action-list";
import { CreateActionDialog } from "@/components/create-action-dialog";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Runbook</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Agentic workflows
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link href="/agents">
              <Button variant="outline" size="sm" className="gap-1.5">
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="8" cy="6" r="2.5" />
                  <path d="M3 14c0-2.76 2.24-5 5-5s5 2.24 5 5" strokeLinecap="round" />
                  <path d="M6 6h0M10 6h0" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Agents
              </Button>
            </Link>
            <Link href="/planner">
              <Button variant="outline" size="sm" className="gap-1.5">
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 4h10M5 8h6M7 12h2" strokeLinecap="round" />
                </svg>
                Planner
              </Button>
            </Link>
            <CreateActionDialog />
          </div>
        </div>
        <ActionList />
      </div>
    </main>
  );
}
