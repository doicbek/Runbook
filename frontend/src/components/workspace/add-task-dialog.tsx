"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useCreateTask } from "@/hooks/use-tasks";
import type { Task } from "@/types";

export function AddTaskDialog({
  actionId,
  existingTasks,
}: {
  actionId: string;
  existingTasks: Task[];
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [selectedDeps, setSelectedDeps] = useState<string[]>([]);
  const createTask = useCreateTask();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    await createTask.mutateAsync({
      actionId,
      prompt: prompt.trim(),
      dependencies: selectedDeps,
    });

    setOpen(false);
    setPrompt("");
    setSelectedDeps([]);
  };

  const toggleDep = (taskId: string) => {
    setSelectedDeps((prev) =>
      prev.includes(taskId)
        ? prev.filter((id) => id !== taskId)
        : [...prev, taskId]
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
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
          Add Task
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Task</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label
                htmlFor="task-prompt"
                className="text-sm font-medium mb-1.5 block"
              >
                Task prompt
              </label>
              <Textarea
                id="task-prompt"
                placeholder="Describe what this task should do..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                required
                autoFocus
              />
            </div>
            {existingTasks.length > 0 && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Depends on (select tasks whose output this task needs)
                </label>
                <div className="space-y-1.5 max-h-48 overflow-y-auto border rounded-md p-2">
                  {existingTasks.map((task) => (
                    <label
                      key={task.id}
                      className="flex items-start gap-2 cursor-pointer hover:bg-muted/50 rounded p-1.5"
                    >
                      <input
                        type="checkbox"
                        checked={selectedDeps.includes(task.id)}
                        onChange={() => toggleDep(task.id)}
                        className="mt-0.5"
                      />
                      <span className="text-sm line-clamp-2">
                        {task.prompt}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}
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
              disabled={!prompt.trim() || createTask.isPending}
            >
              {createTask.isPending ? "Adding..." : "Add Task"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
