"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateTask } from "@/hooks/use-tasks";
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
  const updateTask = useUpdateTask();

  // Tasks that can be dependencies (exclude self)
  const availableDeps = allTasks.filter((t) => t.id !== task.id);

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
