"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { pauseTask, resumeTask } from "@/lib/api/tasks";

export function PauseButton({
  actionId,
  taskId,
}: {
  actionId: string;
  taskId: string;
}) {
  const [isPausing, setIsPausing] = useState(false);

  const handlePause = async () => {
    setIsPausing(true);
    try {
      await pauseTask(actionId, taskId);
    } catch (e) {
      console.error("Failed to pause task:", e);
    } finally {
      setIsPausing(false);
    }
  };

  return (
    <button
      onClick={handlePause}
      disabled={isPausing}
      className="p-1 rounded hover:bg-amber-500/20 text-muted-foreground hover:text-amber-500 transition-colors disabled:opacity-50"
      title="Pause task"
    >
      <svg className="w-3.5 h-3.5" viewBox="0 0 12 12" fill="currentColor">
        <rect x="2.5" y="2" width="2.5" height="8" rx="0.5" />
        <rect x="7" y="2" width="2.5" height="8" rx="0.5" />
      </svg>
    </button>
  );
}

export function PauseGuidancePanel({
  actionId,
  taskId,
}: {
  actionId: string;
  taskId: string;
}) {
  const [guidance, setGuidance] = useState("");
  const [isRedirect, setIsRedirect] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleResume = async (withGuidance: boolean) => {
    setIsSubmitting(true);
    try {
      await resumeTask(actionId, taskId, {
        guidance: withGuidance && guidance.trim() ? guidance.trim() : undefined,
        redirect: withGuidance ? isRedirect : false,
      });
      setGuidance("");
      setIsRedirect(false);
    } catch (e) {
      console.error("Failed to resume task:", e);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-4 mb-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
      <div className="flex items-center gap-2 mb-2">
        <svg className="w-3.5 h-3.5 text-amber-500 shrink-0" viewBox="0 0 12 12" fill="currentColor">
          <rect x="2.5" y="2" width="2.5" height="8" rx="0.5" />
          <rect x="7" y="2" width="2.5" height="8" rx="0.5" />
        </svg>
        <span className="text-[11px] font-medium text-amber-500 uppercase tracking-wider">
          Task Paused
        </span>
      </div>

      <textarea
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        placeholder="Provide guidance to the agent..."
        className="w-full text-[12px] bg-background border border-border rounded-md p-2 resize-none focus:outline-none focus:ring-1 focus:ring-amber-500/50 placeholder:text-muted-foreground/50"
        rows={3}
        disabled={isSubmitting}
      />

      <div className="flex items-center justify-between mt-2">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={isRedirect}
            onChange={(e) => setIsRedirect(e.target.checked)}
            className="w-3 h-3 rounded border-border accent-amber-500"
            disabled={isSubmitting}
          />
          <span className="text-[10px] text-muted-foreground">
            Redirect (replace remaining plan)
          </span>
        </label>

        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] px-2"
            onClick={() => handleResume(false)}
            disabled={isSubmitting}
          >
            Resume
          </Button>
          {guidance.trim() && (
            <Button
              variant="default"
              size="sm"
              className="h-6 text-[11px] px-2 bg-amber-600 hover:bg-amber-700 text-white"
              onClick={() => handleResume(true)}
              disabled={isSubmitting}
            >
              Submit &amp; Resume
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
