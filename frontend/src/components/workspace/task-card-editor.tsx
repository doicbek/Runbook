"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateTask } from "@/hooks/use-tasks";
import { useAvailableModels } from "@/hooks/use-models";
import { useAgentDefinitions } from "@/hooks/use-agent-definitions";
import type { Task } from "@/types";

export function TaskCardEditor({
  task,
  actionId,
  allTasks,
  onClose,
}: {
  task: Task;
  actionId: string;
  allTasks: Task[];
  onClose: () => void;
}) {
  const [prompt, setPrompt] = useState(task.prompt);
  const [selectedDeps, setSelectedDeps] = useState<string[]>(task.dependencies);
  const [selectedModel, setSelectedModel] = useState<string>(task.model || "");
  const [selectedAgentType, setSelectedAgentType] = useState<string>(task.agent_type || "");
  const updateTask = useUpdateTask();
  const { data: modelsData } = useAvailableModels();
  const { data: agentsData } = useAgentDefinitions();

  // Tasks that can be dependencies (exclude self)
  const availableDeps = allTasks.filter((t) => t.id !== task.id);

  // Group models by provider
  const modelsByProvider: Record<string, { name: string; display_name: string }[]> = {};
  if (modelsData?.models) {
    for (const m of modelsData.models) {
      if (!modelsByProvider[m.provider]) {
        modelsByProvider[m.provider] = [];
      }
      modelsByProvider[m.provider].push(m);
    }
  }

  const providerLabels: Record<string, string> = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    deepseek: "DeepSeek",
    google: "Google",
  };

  const toggleDep = (taskId: string) => {
    setSelectedDeps((prev) =>
      prev.includes(taskId)
        ? prev.filter((id) => id !== taskId)
        : [...prev, taskId]
    );
  };

  const handleSave = async () => {
    if (!prompt.trim()) return;
    await updateTask.mutateAsync({
      actionId,
      taskId: task.id,
      prompt: prompt.trim(),
      model: selectedModel || null,
      agent_type: selectedAgentType || undefined,
      dependencies: selectedDeps,
    });
    onClose();
  };

  return (
    <Card className="ring-2 ring-primary">
      <CardHeader className="pb-2">
        <span className="text-sm font-medium">Editing task</span>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          autoFocus
        />
        {/* Agent type selector */}
        {agentsData && agentsData.length > 0 && (
          <div>
            <label className="text-xs font-medium mb-1 block">
              Agent Type
            </label>
            <select
              value={selectedAgentType}
              onChange={(e) => setSelectedAgentType(e.target.value)}
              className="w-full text-xs border rounded-md px-2 py-1.5 bg-background text-foreground"
            >
              {agentsData.map((a) => (
                <option key={a.agent_type} value={a.agent_type}>
                  {a.icon} {a.name} ({a.agent_type})
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Can&apos;t find the right agent?{" "}
              <Link href="/agents/new" className="underline hover:text-foreground">
                Build one in Agent Studio →
              </Link>
            </p>
          </div>
        )}
        {/* Model selector */}
        {modelsData?.models && modelsData.models.length > 0 && (
          <div>
            <label className="text-xs font-medium mb-1 block">
              Model
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full text-xs border rounded-md px-2 py-1.5 bg-background text-foreground"
            >
              <option value="">Default for agent type</option>
              {Object.entries(modelsByProvider).map(([provider, models]) => (
                <optgroup key={provider} label={providerLabels[provider] || provider}>
                  {models.map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.display_name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        )}
        {availableDeps.length > 0 && (
          <div>
            <label className="text-xs font-medium mb-1 block">
              Depends on
            </label>
            <div className="space-y-1 max-h-32 overflow-y-auto border rounded-md p-1.5">
              {availableDeps.map((t) => (
                <label
                  key={t.id}
                  className="flex items-start gap-2 cursor-pointer hover:bg-muted/50 rounded p-1"
                >
                  <input
                    type="checkbox"
                    checked={selectedDeps.includes(t.id)}
                    onChange={() => toggleDep(t.id)}
                    className="mt-0.5"
                  />
                  <span className="text-xs line-clamp-1">{t.prompt}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!prompt.trim() || updateTask.isPending}
          >
            {updateTask.isPending ? "Saving..." : "Save"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onClose}
            disabled={updateTask.isPending}
          >
            Cancel
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Saving will reset this task and all downstream tasks to pending.
        </p>
      </CardContent>
    </Card>
  );
}
