"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useApiStatus,
  useModifySystemPrompt,
  usePlannerConfig,
  usePreviewPlan,
  useUpdatePlannerConfig,
} from "@/hooks/use-planner-config";
import { useAgentDefinitions } from "@/hooks/use-agent-definitions";
import { useAvailableModels } from "@/hooks/use-models";
import type { PlannerPreviewTask } from "@/types";

const providerColors: Record<string, string> = {
  openai: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  anthropic: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  deepseek: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  google: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
};

const providerIcons: Record<string, string> = {
  openai: "🟢", anthropic: "🟠", deepseek: "🔵", google: "🟡",
};

function TaskPreviewCard({ task, index }: { task: PlannerPreviewTask; index: number }) {
  return (
    <div className="border rounded-lg p-3 space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-mono text-muted-foreground">#{index + 1}</span>
        <div className="flex gap-1">
          <Badge variant="secondary" className="text-xs">{task.agent_type}</Badge>
          {task.model && (
            <Badge variant="outline" className="text-xs font-mono">{task.model.split("/")[1] ?? task.model}</Badge>
          )}
        </div>
      </div>
      <p className="text-sm">{task.prompt}</p>
      {task.dependencies.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Depends on: {task.dependencies.map((d) => `#${d + 1}`).join(", ")}
        </p>
      )}
    </div>
  );
}

export default function PlannerPage() {
  const { data: config, isLoading } = usePlannerConfig();
  const { data: apiStatus } = useApiStatus();
  const { data: agents } = useAgentDefinitions();
  const { data: modelsData } = useAvailableModels();
  const updateConfig = useUpdatePlannerConfig();
  const previewPlan = usePreviewPlan();
  const modifyPrompt = useModifySystemPrompt();

  // Local editable state
  const [systemPrompt, setSystemPrompt] = useState("");
  const [planningModel, setPlanningModel] = useState("");
  const [maxTasks, setMaxTasks] = useState(8);
  const [maxRetries, setMaxRetries] = useState(2);
  const [initialized, setInitialized] = useState(false);

  // AI modify state
  const [modifyInstruction, setModifyInstruction] = useState("");
  const [modifyModel, setModifyModel] = useState("");

  // Preview state
  const [previewPrompt, setPreviewPrompt] = useState("");
  const [previewResult, setPreviewResult] = useState<PlannerPreviewTask[] | null>(null);

  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (config && !initialized) {
      setSystemPrompt(config.system_prompt);
      setPlanningModel(config.model);
      setMaxTasks(config.max_tasks);
      setMaxRetries(config.max_retries);
      setInitialized(true);
    }
  }, [config, initialized]);

  const modelsByProvider: Record<string, { name: string; display_name: string }[]> = {};
  if (modelsData?.models) {
    for (const m of modelsData.models) {
      if (!modelsByProvider[m.provider]) modelsByProvider[m.provider] = [];
      modelsByProvider[m.provider].push(m);
    }
  }
  const providerLabels: Record<string, string> = {
    openai: "OpenAI", anthropic: "Anthropic", deepseek: "DeepSeek", google: "Google",
  };

  // Only OpenAI models support structured output (used by planner)
  const openaiModels = modelsByProvider["openai"] ?? [];

  const customAgents = agents?.filter((a) => !a.is_builtin && a.status === "active") ?? [];

  const hasChanges =
    config &&
    (systemPrompt !== config.system_prompt ||
      planningModel !== config.model ||
      maxTasks !== config.max_tasks ||
      maxRetries !== config.max_retries);

  const handleSave = async () => {
    setSaveError("");
    try {
      await updateConfig.mutateAsync({
        system_prompt: systemPrompt,
        model: planningModel,
        max_tasks: maxTasks,
        max_retries: maxRetries,
      });
    } catch (e: unknown) {
      setSaveError((e as Error)?.message ?? "Save failed");
    }
  };

  const handleAIModify = async () => {
    if (!modifyInstruction.trim()) return;
    const result = await modifyPrompt.mutateAsync({
      instruction: modifyInstruction.trim(),
      current_prompt: systemPrompt,
      model: modifyModel || undefined,
    });
    setSystemPrompt(result.system_prompt);
    setModifyInstruction("");
  };

  const handlePreview = async () => {
    if (!previewPrompt.trim()) return;
    setPreviewResult(null);
    const result = await previewPlan.mutateAsync({
      prompt: previewPrompt.trim(),
      systemPrompt,
    });
    setPreviewResult(result.tasks);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading planner config...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Header */}
        <div>
          <Link href="/" className="text-xs text-muted-foreground hover:underline">← Home</Link>
          <div className="flex items-center justify-between mt-3">
            <div>
              <h1 className="text-2xl font-bold">🧠 Planner Configuration</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Control how your prompts get decomposed into tasks.
                {config && (
                  <span className="ml-2 text-xs">
                    Last updated: {new Date(config.updated_at).toLocaleString()}
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>

        {/* API Key Status */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">API Key Status</h2>
            <p className="text-xs text-muted-foreground">Set keys in your <code className="bg-muted px-1 rounded">.env</code> file and restart the backend.</p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {apiStatus?.map((p) => (
                <div key={p.provider} className="border rounded-lg p-3 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <span>{providerIcons[p.provider] ?? "⚫"}</span>
                    <span className="text-sm font-medium capitalize">{p.provider}</span>
                  </div>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                    p.configured
                      ? providerColors[p.provider]
                      : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  }`}>
                    {p.configured ? "✓ Configured" : "✗ Not set"}
                  </span>
                  {p.configured && (
                    <p className="text-xs text-muted-foreground">{p.models.length} model{p.models.length !== 1 ? "s" : ""}</p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Planning Settings */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Planning Settings</h2>
            <p className="text-xs text-muted-foreground">
              The planning model must support structured outputs (OpenAI models only).
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-1 space-y-1">
                <label className="text-xs font-medium">Planning Model</label>
                {openaiModels.length > 0 ? (
                  <select
                    value={planningModel}
                    onChange={(e) => setPlanningModel(e.target.value)}
                    className="w-full text-xs border rounded-md px-2 py-1.5 bg-background text-foreground"
                  >
                    {openaiModels.map((m) => (
                      <option key={m.name} value={m.name.split("/")[1] ?? m.name}>
                        {m.display_name}
                      </option>
                    ))}
                    {/* Fallback if not in available list */}
                    {!openaiModels.find((m) => m.name.split("/")[1] === planningModel) && (
                      <option value={planningModel}>{planningModel}</option>
                    )}
                  </select>
                ) : (
                  <Input
                    value={planningModel}
                    onChange={(e) => setPlanningModel(e.target.value)}
                    placeholder="gpt-4o"
                    className="font-mono text-xs"
                  />
                )}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Max Tasks</label>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={maxTasks}
                  onChange={(e) => setMaxTasks(parseInt(e.target.value) || 8)}
                  className="text-xs"
                />
                <p className="text-xs text-muted-foreground">Upper bound in system prompt</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Max Retries</label>
                <Input
                  type="number"
                  min={1}
                  max={5}
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(parseInt(e.target.value) || 2)}
                  className="text-xs"
                />
                <p className="text-xs text-muted-foreground">On invalid DAG output</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Custom Agents Context */}
        {customAgents.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <h2 className="font-semibold text-sm">Active Custom Agents (auto-injected)</h2>
              <p className="text-xs text-muted-foreground">
                These are appended to the system prompt so the planner can assign tasks to them.
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {customAgents.map((a) => (
                  <div key={a.id} className="flex items-start gap-2 text-sm">
                    <span className="shrink-0">{a.icon}</span>
                    <div>
                      <span className="font-mono text-xs text-primary">{a.agent_type}</span>
                      <span className="text-muted-foreground ml-2 text-xs">— {a.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* System Prompt */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">System Prompt</h2>
            <p className="text-xs text-muted-foreground">
              The full prompt sent to the LLM when decomposing a user request into tasks.
              Edit directly or use AI Modify below.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* AI Modify */}
            <div className="border rounded-lg p-4 space-y-3 bg-muted/30">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">✨ AI Modify</span>
                <span className="text-xs text-muted-foreground">
                  Describe a change — the LLM rewrites the prompt.
                </span>
              </div>
              <Textarea
                value={modifyInstruction}
                onChange={(e) => setModifyInstruction(e.target.value)}
                rows={2}
                className="text-sm"
                placeholder='e.g. "always include a validation task at the end" or "prefer smaller tasks with fewer dependencies"'
              />
              <div className="flex items-center gap-2 flex-wrap">
                {modelsData?.models && modelsData.models.length > 0 && (
                  <select
                    value={modifyModel}
                    onChange={(e) => setModifyModel(e.target.value)}
                    className="text-xs border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    <option value="">Default model</option>
                    {Object.entries(modelsByProvider).map(([provider, models]) => (
                      <optgroup key={provider} label={providerLabels[provider] || provider}>
                        {models.map((m) => (
                          <option key={m.name} value={m.name}>{m.display_name}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                )}
                <Button
                  size="sm"
                  onClick={handleAIModify}
                  disabled={modifyPrompt.isPending || !modifyInstruction.trim()}
                >
                  {modifyPrompt.isPending ? "Rewriting..." : "Apply with AI"}
                </Button>
                {modifyPrompt.isError && (
                  <span className="text-xs text-destructive">
                    {(modifyPrompt.error as Error)?.message}
                  </span>
                )}
                {modifyPrompt.isSuccess && !modifyPrompt.isPending && (
                  <span className="text-xs text-green-600 dark:text-green-400">
                    ✓ Prompt updated — review below, then Save.
                  </span>
                )}
              </div>
            </div>

            {/* System prompt editor */}
            <Textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={28}
              className="font-mono text-xs"
              spellCheck={false}
            />
          </CardContent>
        </Card>

        {/* Test Planning */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Test Planning</h2>
            <p className="text-xs text-muted-foreground">
              Preview how a prompt would be decomposed using the current (unsaved) system prompt.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Textarea
                value={previewPrompt}
                onChange={(e) => setPreviewPrompt(e.target.value)}
                rows={2}
                className="text-sm flex-1"
                placeholder="Enter a prompt to test, e.g. &quot;Analyze temperature trends in London for 2024&quot;"
              />
              <Button
                onClick={handlePreview}
                disabled={previewPlan.isPending || !previewPrompt.trim()}
                className="self-end"
              >
                {previewPlan.isPending ? "Planning..." : "Preview Plan"}
              </Button>
            </div>
            {previewPlan.isError && (
              <p className="text-xs text-destructive">
                {(previewPlan.error as Error)?.message}
              </p>
            )}
            {previewResult && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  {previewResult.length} task{previewResult.length !== 1 ? "s" : ""} planned
                </p>
                {previewResult.map((task, i) => (
                  <TaskPreviewCard key={i} task={task} index={i} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Save */}
        {saveError && <p className="text-sm text-destructive">{saveError}</p>}
        <div className="flex items-center gap-3">
          <Button
            onClick={handleSave}
            disabled={updateConfig.isPending || !hasChanges}
          >
            {updateConfig.isPending ? "Saving..." : "Save Changes"}
          </Button>
          {updateConfig.isSuccess && !updateConfig.isPending && (
            <span className="text-xs text-green-600 dark:text-green-400">✓ Saved</span>
          )}
          {hasChanges && (
            <span className="text-xs text-amber-600 dark:text-amber-400">● Unsaved changes</span>
          )}
        </div>

      </div>
    </div>
  );
}
