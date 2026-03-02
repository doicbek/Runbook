"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateAction } from "@/hooks/use-actions";
import { useTemplates, useUseTemplate } from "@/hooks/use-templates";
import type { ActionTemplate } from "@/types";

type Tab = "new" | "template";

export function CreateActionDialog() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("new");
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const router = useRouter();
  const createAction = useCreateAction();
  const useTemplate = useUseTemplate();
  const { data: templates } = useTemplates();

  // Sort templates by usage_count desc for "popular" ordering
  const sortedTemplates = templates
    ? [...templates].sort((a, b) => b.usage_count - a.usage_count)
    : [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    const action = await createAction.mutateAsync({
      root_prompt: prompt.trim(),
      title: title.trim() || undefined,
    });

    setOpen(false);
    setPrompt("");
    setTitle("");
    setTab("new");
    router.push(`/actions/${action.id}`);
  };

  const handleUseTemplate = async (tpl: ActionTemplate) => {
    const action = await useTemplate.mutateAsync(tpl.id);
    setOpen(false);
    setTab("new");
    router.push(`/actions/${action.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setTab("new"); }}>
      <DialogTrigger asChild>
        <Button size="lg" className="gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M5 12h14" />
            <path d="M12 5v14" />
          </svg>
          New Action
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Action</DialogTitle>
        </DialogHeader>

        {/* Tab switcher */}
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            onClick={() => setTab("new")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === "new"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            New Action
          </button>
          <button
            type="button"
            onClick={() => setTab("template")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === "template"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            From Template
          </button>
        </div>

        {tab === "new" ? (
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-2">
              <div>
                <label
                  htmlFor="title"
                  className="text-sm font-medium mb-1.5 block"
                >
                  Title (optional)
                </label>
                <Input
                  id="title"
                  placeholder="Give your action a name..."
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div>
                <label
                  htmlFor="prompt"
                  className="text-sm font-medium mb-1.5 block"
                >
                  Prompt
                </label>
                <Textarea
                  id="prompt"
                  placeholder="Describe what you want to accomplish..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={4}
                  required
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!prompt.trim() || createAction.isPending}
              >
                {createAction.isPending ? "Creating..." : "Create Action"}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="py-2">
            {sortedTemplates.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No templates yet. Save a completed action as a template to get started.
              </p>
            ) : (
              <div className="space-y-2 max-h-[340px] overflow-y-auto">
                {sortedTemplates.map((tpl) => (
                  <button
                    key={tpl.id}
                    type="button"
                    disabled={useTemplate.isPending}
                    onClick={() => handleUseTemplate(tpl)}
                    className="w-full text-left rounded-lg border p-3 hover:bg-muted/50 transition-colors disabled:opacity-50"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{tpl.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {tpl.usage_count} use{tpl.usage_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    {tpl.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {tpl.description}
                      </p>
                    )}
                    {tpl.tags.length > 0 && (
                      <div className="flex gap-1 mt-1.5 flex-wrap">
                        {tpl.tags.map((tag) => (
                          <span
                            key={tag}
                            className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
            <div className="flex justify-end mt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
