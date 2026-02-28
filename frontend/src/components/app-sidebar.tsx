"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useActions, useCreateAction } from "@/hooks/use-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "now";
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d`;
}

const statusDot: Record<string, string> = {
  draft: "bg-gray-400 dark:bg-gray-500",
  running: "",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M8 2a6 6 0 014.24 1.76" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function AppSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: allActions } = useActions();
  const actions = allActions?.filter((a) => (a.depth ?? 0) === 0 && a.parent_action_id === null);
  const createAction = useCreateAction();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    const action = await createAction.mutateAsync({
      root_prompt: prompt.trim(),
      title: title.trim() || undefined,
    });
    setDialogOpen(false);
    setPrompt("");
    setTitle("");
    router.push(`/actions/${action.id}`);
  };

  if (collapsed) {
    return (
      <aside className="w-12 h-screen border-r border-border bg-muted/30 flex flex-col items-center py-3 shrink-0">
        <button
          onClick={onToggle}
          className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors mb-4"
          title="Expand sidebar"
        >
          <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M6 3l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <button
          onClick={() => setDialogOpen(true)}
          className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground border border-border rounded transition-colors mb-4"
          title="New action"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3v10M3 8h10" strokeLinecap="round" />
          </svg>
        </button>
        {actions?.slice(0, 8).map((action) => {
          const isActive = pathname === `/actions/${action.id}`;
          const dot = statusDot[action.status] || statusDot.draft;
          return (
            <Link
              key={action.id}
              href={`/actions/${action.id}`}
              className={`w-7 h-7 flex items-center justify-center rounded mb-1 transition-colors ${
                isActive ? "bg-accent" : "hover:bg-accent/50"
              }`}
              title={action.title}
            >
              {action.status === "running" ? (
                <Spinner className="w-3 h-3 text-blue-500" />
              ) : (
                <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
              )}
            </Link>
          );
        })}
        <div className="mt-auto space-y-1">
          <Link
            href="/agents"
            className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            title="Agents"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="6" r="2.5" />
              <path d="M3 14c0-2.76 2.24-5 5-5s5 2.24 5 5" strokeLinecap="round" />
            </svg>
          </Link>
          <Link
            href="/skills"
            className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            title="Skills"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M8 1l2 4 4.5.5-3.25 3 .75 4.5L8 11l-4 2 .75-4.5L1.5 5.5 6 5l2-4z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
          <Link
            href="/planner"
            className="w-7 h-7 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            title="Planner"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 4h10M5 8h6M7 12h2" strokeLinecap="round" />
            </svg>
          </Link>
        </div>
        <NewActionDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          prompt={prompt}
          setPrompt={setPrompt}
          title={title}
          setTitle={setTitle}
          onSubmit={handleCreate}
          isPending={createAction.isPending}
        />
      </aside>
    );
  }

  return (
    <aside className="w-[260px] h-screen border-r border-border bg-muted/30 flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-border">
        <Link href="/" className="text-sm font-semibold tracking-tight text-foreground font-mono">
          runbook
        </Link>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setDialogOpen(true)}
            className="h-6 px-2 text-[11px] font-medium border border-border rounded bg-background hover:bg-accent text-foreground transition-colors flex items-center gap-1"
          >
            <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 3v10M3 8h10" strokeLinecap="round" />
            </svg>
            New
          </button>
          <button
            onClick={onToggle}
            className="w-6 h-6 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            title="Collapse sidebar"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 3L5 8l5 5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>

      {/* Action list */}
      <div className="flex-1 overflow-y-auto py-1">
        {!actions && (
          <div className="px-3 py-2 space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-8 bg-muted/50 animate-pulse rounded" />
            ))}
          </div>
        )}
        {actions?.length === 0 && (
          <div className="px-3 py-6 text-center">
            <p className="text-[11px] text-muted-foreground">No actions yet</p>
          </div>
        )}
        {actions?.map((action) => {
          const isActive = pathname === `/actions/${action.id}`;
          const dot = statusDot[action.status] || statusDot.draft;
          return (
            <Link
              key={action.id}
              href={`/actions/${action.id}`}
              className={`flex items-center gap-2 px-3 py-1.5 text-[12px] transition-colors group ${
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              }`}
            >
              {action.status === "running" ? (
                <Spinner className="w-3 h-3 text-blue-500 shrink-0" />
              ) : (
                <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
              )}
              <span className="truncate flex-1 font-medium">{action.title}</span>
              <span className="text-[10px] text-muted-foreground/60 shrink-0 tabular-nums">
                {timeAgo(action.updated_at)}
              </span>
            </Link>
          );
        })}
      </div>

      {/* Footer nav */}
      <div className="border-t border-border px-3 py-2 space-y-0.5">
        <Link
          href="/agents"
          className={`flex items-center gap-2 px-2 py-1 text-[11px] rounded transition-colors ${
            pathname === "/agents"
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          }`}
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="6" r="2.5" />
            <path d="M3 14c0-2.76 2.24-5 5-5s5 2.24 5 5" strokeLinecap="round" />
          </svg>
          Agents
        </Link>
        <Link
          href="/skills"
          className={`flex items-center gap-2 px-2 py-1 text-[11px] rounded transition-colors ${
            pathname === "/skills"
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          }`}
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 1l2 4 4.5.5-3.25 3 .75 4.5L8 11l-4 2 .75-4.5L1.5 5.5 6 5l2-4z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Skills
        </Link>
        <Link
          href="/planner"
          className={`flex items-center gap-2 px-2 py-1 text-[11px] rounded transition-colors ${
            pathname === "/planner"
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          }`}
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 4h10M5 8h6M7 12h2" strokeLinecap="round" />
          </svg>
          Planner
        </Link>
      </div>

      <NewActionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        prompt={prompt}
        setPrompt={setPrompt}
        title={title}
        setTitle={setTitle}
        onSubmit={handleCreate}
        isPending={createAction.isPending}
      />
    </aside>
  );
}

function NewActionDialog({
  open,
  onOpenChange,
  prompt,
  setPrompt,
  title,
  setTitle,
  onSubmit,
  isPending,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  prompt: string;
  setPrompt: (v: string) => void;
  title: string;
  setTitle: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  isPending: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Create New Action</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label htmlFor="sidebar-title" className="text-sm font-medium mb-1.5 block">
                Title (optional)
              </label>
              <Input
                id="sidebar-title"
                placeholder="Give your action a name..."
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="sidebar-prompt" className="text-sm font-medium mb-1.5 block">
                Prompt
              </label>
              <Textarea
                id="sidebar-prompt"
                placeholder="Describe what you want to accomplish..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={4}
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!prompt.trim() || isPending}>
              {isPending ? "Creating..." : "Create Action"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
