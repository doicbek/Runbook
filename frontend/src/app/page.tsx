"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCreateAction } from "@/hooks/use-actions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ThemeToggle } from "@/components/theme-toggle";

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const router = useRouter();
  const createAction = useCreateAction();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    const action = await createAction.mutateAsync({
      root_prompt: prompt.trim(),
    });
    setPrompt("");
    router.push(`/actions/${action.id}`);
  };

  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <div className="absolute top-3 right-3">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-lg text-center">
        <h2 className="text-lg font-semibold text-foreground mb-1">
          Select an action or create a new one
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Choose from the sidebar, or describe a workflow below.
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Textarea
            placeholder="Describe what you want to accomplish..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="resize-none text-sm"
          />
          <Button
            type="submit"
            disabled={!prompt.trim() || createAction.isPending}
            className="w-full"
          >
            {createAction.isPending ? "Creating..." : "Create Action"}
          </Button>
        </form>
      </div>
    </div>
  );
}
