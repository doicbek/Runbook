"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import cronstrue from "cronstrue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useSchedules,
  useCreateSchedule,
  useUpdateSchedule,
  useDeleteSchedule,
  useRunScheduleNow,
} from "@/hooks/use-schedules";
import type { ActionSchedule } from "@/types";

const CRON_PRESETS: { label: string; value: string }[] = [
  { label: "Every hour", value: "0 * * * *" },
  { label: "Daily at 9 AM", value: "0 9 * * *" },
  { label: "Weekly (Monday 9 AM)", value: "0 9 * * 1" },
  { label: "Every 6 hours", value: "0 */6 * * *" },
  { label: "Custom", value: "" },
];

function formatCron(expression: string): string {
  try {
    return cronstrue.toString(expression);
  } catch {
    return expression;
  }
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const d = new Date(dateStr);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeUntil(dateStr: string): string {
  const target = new Date(dateStr).getTime();
  const now = Date.now();
  const diffMs = target - now;
  if (diffMs < 0) return "overdue";
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "< 1 min";
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ${diffMin % 60}m`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ${diffHr % 24}h`;
}

export default function SchedulesPage() {
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const { data: schedules, isLoading, error } = useSchedules();
  const createSchedule = useCreateSchedule();
  const updateSchedule = useUpdateSchedule();
  const deleteScheduleMut = useDeleteSchedule();
  const runNow = useRunScheduleNow();
  const router = useRouter();

  const handleDelete = async (id: string) => {
    await deleteScheduleMut.mutateAsync(id);
    setDeleteConfirmId(null);
  };

  const handleRunNow = async (id: string) => {
    await runNow.mutateAsync(id);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Schedules</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Automate actions with cron-based scheduling.
            </p>
          </div>
          <Button onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : "+ New Schedule"}
          </Button>
        </div>

        {showCreate && (
          <CreateScheduleForm
            onCreated={() => setShowCreate(false)}
            createMutation={createSchedule}
          />
        )}

        {isLoading && (
          <div className="text-sm text-muted-foreground">Loading schedules...</div>
        )}
        {error && (
          <div className="text-sm text-destructive">
            Failed to load schedules: {(error as Error).message}
          </div>
        )}
        {schedules && schedules.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-sm">
              No schedules yet. Create one to automate recurring actions.
            </p>
          </div>
        )}

        {schedules && schedules.length > 0 && (
          <div className="space-y-2">
            {/* Header */}
            <div className="grid grid-cols-[1fr_180px_120px_120px_80px_60px_auto] gap-3 px-4 py-2 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              <span>Schedule</span>
              <span>Cron</span>
              <span>Next run</span>
              <span>Last run</span>
              <span>Runs</span>
              <span>Status</span>
              <span></span>
            </div>

            {schedules.map((schedule) => (
              <div key={schedule.id}>
                {editingId === schedule.id ? (
                  <EditScheduleForm
                    schedule={schedule}
                    onCancel={() => setEditingId(null)}
                    updateMutation={updateSchedule}
                    onSaved={() => setEditingId(null)}
                  />
                ) : deleteConfirmId === schedule.id ? (
                  <div className="border border-destructive/50 rounded-lg p-4 bg-destructive/5">
                    <p className="text-sm mb-3">
                      Delete &ldquo;{schedule.title}&rdquo;? This cannot be undone.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDelete(schedule.id)}
                        disabled={deleteScheduleMut.isPending}
                      >
                        {deleteScheduleMut.isPending ? "Deleting..." : "Delete"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDeleteConfirmId(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <ScheduleRow
                    schedule={schedule}
                    onEdit={() => setEditingId(schedule.id)}
                    onDelete={() => setDeleteConfirmId(schedule.id)}
                    onRunNow={() => handleRunNow(schedule.id)}
                    onToggleActive={() =>
                      updateSchedule.mutate({
                        id: schedule.id,
                        body: { is_active: !schedule.is_active },
                      })
                    }
                    isRunning={runNow.isPending && runNow.variables === schedule.id}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ScheduleRow({
  schedule,
  onEdit,
  onDelete,
  onRunNow,
  onToggleActive,
  isRunning,
}: {
  schedule: ActionSchedule;
  onEdit: () => void;
  onDelete: () => void;
  onRunNow: () => void;
  onToggleActive: () => void;
  isRunning: boolean;
}) {
  const failureBadge =
    schedule.consecutive_failures >= 3
      ? "bg-red-500/10 text-red-500 border-red-500/20"
      : schedule.consecutive_failures >= 1
        ? "bg-orange-500/10 text-orange-500 border-orange-500/20"
        : null;

  return (
    <div className="grid grid-cols-[1fr_180px_120px_120px_80px_60px_auto] gap-3 items-center px-4 py-3 border border-border rounded-lg hover:border-foreground/20 transition-colors">
      {/* Title + prompt */}
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{schedule.title}</span>
          {failureBadge && (
            <span
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded border ${failureBadge}`}
            >
              <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 1l7 13H1L8 1z" strokeLinejoin="round" />
                <path d="M8 6v3M8 11v.5" strokeLinecap="round" />
              </svg>
              {schedule.consecutive_failures} fail{schedule.consecutive_failures !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">{schedule.root_prompt}</p>
      </div>

      {/* Cron */}
      <div className="min-w-0">
        <p className="text-xs text-foreground truncate">{formatCron(schedule.cron_expression)}</p>
        <p className="text-[10px] text-muted-foreground font-mono">{schedule.cron_expression}</p>
      </div>

      {/* Next run */}
      <div>
        <p className="text-xs text-foreground">{formatDateTime(schedule.next_run_at)}</p>
        <p className="text-[10px] text-muted-foreground">in {timeUntil(schedule.next_run_at)}</p>
      </div>

      {/* Last run */}
      <div>
        <p className="text-xs text-foreground">{formatDateTime(schedule.last_run_at)}</p>
      </div>

      {/* Run count */}
      <div>
        <span className="text-xs text-foreground tabular-nums">{schedule.run_count}</span>
      </div>

      {/* Active toggle */}
      <div>
        <button
          onClick={onToggleActive}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
            schedule.is_active ? "bg-emerald-500" : "bg-muted"
          }`}
          title={schedule.is_active ? "Active - click to pause" : "Paused - click to activate"}
        >
          <span
            className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
              schedule.is_active ? "translate-x-4.5" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant="ghost"
          onClick={onRunNow}
          disabled={isRunning}
          className="text-xs h-7 px-2"
          title="Run now"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4 2l10 6-10 6V2z" />
          </svg>
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onEdit}
          className="text-xs h-7 px-2 text-muted-foreground"
        >
          Edit
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onDelete}
          className="text-xs h-7 px-2 text-muted-foreground hover:text-destructive"
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

function CreateScheduleForm({
  onCreated,
  createMutation,
}: {
  onCreated: () => void;
  createMutation: ReturnType<typeof useCreateSchedule>;
}) {
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [cronExpression, setCronExpression] = useState("0 9 * * *");
  const [selectedPreset, setSelectedPreset] = useState("0 9 * * *");

  const handlePresetChange = (value: string) => {
    setSelectedPreset(value);
    if (value) setCronExpression(value);
  };

  const cronPreview = formatCron(cronExpression);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !prompt.trim() || !cronExpression.trim()) return;
    await createMutation.mutateAsync({
      title: title.trim(),
      root_prompt: prompt.trim(),
      cron_expression: cronExpression.trim(),
    });
    setTitle("");
    setPrompt("");
    setCronExpression("0 9 * * *");
    setSelectedPreset("0 9 * * *");
    onCreated();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-border rounded-lg p-4 mb-6 space-y-3"
    >
      <Input
        placeholder="Schedule title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-8 text-sm"
        required
      />
      <Textarea
        placeholder="Action prompt to run on each trigger..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        className="text-sm"
        required
      />
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Schedule</label>
        <div className="flex gap-2 flex-wrap">
          {CRON_PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => handlePresetChange(preset.value)}
              className={`px-2.5 py-1 text-xs rounded border transition-colors ${
                selectedPreset === preset.value
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Input
            placeholder="Cron expression (e.g. 0 9 * * *)"
            value={cronExpression}
            onChange={(e) => {
              setCronExpression(e.target.value);
              setSelectedPreset("");
            }}
            className="h-8 text-sm font-mono max-w-xs"
            required
          />
          <span className="text-xs text-muted-foreground">{cronPreview}</span>
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={createMutation.isPending}>
          {createMutation.isPending ? "Creating..." : "Create Schedule"}
        </Button>
      </div>
    </form>
  );
}

function EditScheduleForm({
  schedule,
  onCancel,
  updateMutation,
  onSaved,
}: {
  schedule: ActionSchedule;
  onCancel: () => void;
  updateMutation: ReturnType<typeof useUpdateSchedule>;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(schedule.title);
  const [prompt, setPrompt] = useState(schedule.root_prompt);
  const [cronExpression, setCronExpression] = useState(schedule.cron_expression);

  const cronPreview = formatCron(cronExpression);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateMutation.mutateAsync({
      id: schedule.id,
      body: {
        title: title.trim(),
        root_prompt: prompt.trim(),
        cron_expression: cronExpression.trim(),
      },
    });
    onSaved();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-primary/30 rounded-lg p-4 space-y-3"
    >
      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-8 text-sm"
        required
      />
      <Textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        className="text-sm"
        required
      />
      <div className="flex items-center gap-3">
        <Input
          value={cronExpression}
          onChange={(e) => setCronExpression(e.target.value)}
          className="h-8 text-sm font-mono max-w-xs"
          required
        />
        <span className="text-xs text-muted-foreground">{cronPreview}</span>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={updateMutation.isPending}>
          {updateMutation.isPending ? "Saving..." : "Save"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
