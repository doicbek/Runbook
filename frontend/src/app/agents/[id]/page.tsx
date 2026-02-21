"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ToolSelector } from "@/components/agents/tool-selector";
import {
  useAgentDefinition,
  useUpdateAgentDefinition,
  useDeleteAgentDefinition,
  useModifyAgent,
} from "@/hooks/use-agent-definitions";
import { useAvailableModels } from "@/hooks/use-models";

const REAL_BUILTINS = new Set(["arxiv_search", "code_execution"]);

const statusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  draft: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

function implLabel(agentType: string, isBuiltin: boolean, hasCode: boolean) {
  if (!isBuiltin && hasCode) return { text: "Custom code", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" };
  if (!isBuiltin) return { text: "No code", cls: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400" };
  if (REAL_BUILTINS.has(agentType)) return { text: "Native Python", cls: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400" };
  return { text: "Mock (LLM-generated output)", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400" };
}

export default function AgentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: agent, isLoading, error } = useAgentDefinition(id);
  const updateAgent = useUpdateAgentDefinition();
  const deleteAgent = useDeleteAgentDefinition();
  const modifyAgent = useModifyAgent(id);
  const { data: modelsData } = useAvailableModels();

  // All editable — null means "not yet edited, show saved value"
  const [description, setDescription] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [requirements, setRequirements] = useState<string | null>(null);
  const [setupNotes, setSetupNotes] = useState<string | null>(null);
  const [tools, setTools] = useState<string[] | null>(null);

  const [modifyPrompt, setModifyPrompt] = useState("");
  const [modifyModel, setModifyModel] = useState("");
  const [saveError, setSaveError] = useState("");

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading...</span>
      </div>
    );
  }
  if (error || !agent) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-destructive">
          {(error as Error)?.message ?? "Agent not found"}
        </span>
      </div>
    );
  }

  const displayDescription = description ?? agent.description;
  const displayCode = code ?? agent.code ?? "";
  const displayRequirements = requirements ?? agent.requirements ?? "";
  const displaySetupNotes = setupNotes ?? agent.setup_notes ?? "";
  const displayTools = tools ?? agent.tools;

  const impl = implLabel(agent.agent_type, agent.is_builtin, !!(agent.code || code));
  const hasLocalChanges = description !== null || code !== null || requirements !== null || setupNotes !== null || tools !== null;
  const hasCodeOverride = !!displayCode && agent.is_builtin;

  const providerLabels: Record<string, string> = {
    openai: "OpenAI", anthropic: "Anthropic", deepseek: "DeepSeek", google: "Google",
  };
  const modelsByProvider: Record<string, { name: string; display_name: string }[]> = {};
  if (modelsData?.models) {
    for (const m of modelsData.models) {
      if (!modelsByProvider[m.provider]) modelsByProvider[m.provider] = [];
      modelsByProvider[m.provider].push(m);
    }
  }

  const handleApplyAI = async () => {
    if (!modifyPrompt.trim()) return;
    const result = await modifyAgent.mutateAsync({
      prompt: modifyPrompt.trim(),
      current_code: displayCode || undefined,
      model: modifyModel || undefined,
    });
    setCode(result.code);
    setModifyPrompt("");
  };

  const handleSave = async () => {
    setSaveError("");
    try {
      await updateAgent.mutateAsync({
        id: agent.id,
        body: {
          description: displayDescription,
          code: displayCode || null,
          requirements: displayRequirements || null,
          setup_notes: displaySetupNotes || null,
          tools: displayTools,
        },
      });
      setDescription(null);
      setCode(null);
      setRequirements(null);
      setSetupNotes(null);
      setTools(null);
    } catch (e: unknown) {
      setSaveError((e as Error)?.message ?? "Save failed");
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return;
    await deleteAgent.mutateAsync(agent.id);
    router.push("/agents");
  };

  const codeHelperText = (() => {
    if (displayCode) return null;
    if (REAL_BUILTINS.has(agent.agent_type)) {
      return "This agent runs native Python code (not stored here). Use AI Modify to generate a custom override — once saved, it will run instead of the native implementation.";
    }
    return "This agent currently runs as a mock (LLM generates fake output). Use AI Modify below to generate a real implementation.";
  })();

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

        {/* Header */}
        <div>
          <Link href="/agents" className="text-xs text-muted-foreground hover:underline">
            ← Agent Studio
          </Link>
          <div className="flex items-start justify-between mt-3 gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-4xl">{agent.icon}</span>
              <div className="min-w-0">
                <h1 className="text-2xl font-bold truncate">{agent.name}</h1>
                <code className="text-sm text-muted-foreground font-mono">{agent.agent_type}</code>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              <span className={`text-xs px-2 py-1 rounded font-medium ${statusColors[agent.status] ?? ""}`}>
                {agent.status}
              </span>
              <span className={`text-xs px-2 py-1 rounded font-medium ${hasCodeOverride ? "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" : impl.cls}`}>
                {hasCodeOverride ? "Custom override" : impl.text}
              </span>
              {agent.is_builtin && (
                <Badge variant="outline" className="text-xs">Built-in</Badge>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Description</h2>
          </CardHeader>
          <CardContent>
            <Textarea
              value={displayDescription}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="text-sm"
            />
          </CardContent>
        </Card>

        {/* Tools */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Tools</h2>
          </CardHeader>
          <CardContent>
            <ToolSelector selected={displayTools} onChange={setTools} />
          </CardContent>
        </Card>

        {/* AI Modify + Code */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Code</h2>
            {codeHelperText && (
              <p className="text-xs text-muted-foreground mt-1">{codeHelperText}</p>
            )}
          </CardHeader>
          <CardContent className="space-y-4">

            {/* AI Modify panel */}
            <div className="border rounded-lg p-4 space-y-3 bg-muted/30">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">✨ AI Modify</span>
                <span className="text-xs text-muted-foreground">
                  Describe what to change — the LLM rewrites the code.
                </span>
              </div>
              <Textarea
                value={modifyPrompt}
                onChange={(e) => setModifyPrompt(e.target.value)}
                rows={3}
                placeholder={
                  displayCode
                    ? 'e.g. "add retry logic with exponential backoff" or "also output a JSON artifact"'
                    : 'e.g. "implement real HTTP fetching using httpx" or "read CSV files from disk"'
                }
                className="text-sm"
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
                  onClick={handleApplyAI}
                  disabled={modifyAgent.isPending || !modifyPrompt.trim()}
                >
                  {modifyAgent.isPending ? "Applying..." : "Apply with AI"}
                </Button>
                {modifyAgent.isError && (
                  <span className="text-xs text-destructive">
                    {(modifyAgent.error as Error)?.message}
                  </span>
                )}
                {modifyAgent.isSuccess && !modifyAgent.isPending && (
                  <span className="text-xs text-green-600 dark:text-green-400">
                    ✓ Code updated — review below, then Save.
                  </span>
                )}
              </div>
            </div>

            {/* Code editor */}
            <Textarea
              value={displayCode}
              onChange={(e) => setCode(e.target.value)}
              rows={22}
              className="font-mono text-xs"
              placeholder="# No code stored. Use AI Modify above to generate an implementation."
              spellCheck={false}
            />
          </CardContent>
        </Card>

        {/* Requirements & Notes */}
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">Requirements & Notes</h2>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-medium">pip install command</label>
              <Input
                value={displayRequirements}
                onChange={(e) => setRequirements(e.target.value)}
                placeholder="pip install python-docx httpx"
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Setup Notes</label>
              <Textarea
                value={displaySetupNotes}
                onChange={(e) => setSetupNotes(e.target.value)}
                rows={3}
                className="text-xs"
                placeholder="Any setup steps, warnings, environment variables..."
              />
            </div>

            <div className="grid grid-cols-2 gap-2 pt-2 border-t text-xs text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">ID</span>
                <p className="font-mono truncate">{agent.id}</p>
              </div>
              <div>
                <span className="font-medium text-foreground">Created</span>
                <p>{new Date(agent.created_at).toLocaleString()}</p>
              </div>
              <div>
                <span className="font-medium text-foreground">Updated</span>
                <p>{new Date(agent.updated_at).toLocaleString()}</p>
              </div>
              {agent.mcp_config && (
                <div className="col-span-2">
                  <span className="font-medium text-foreground">MCP Config</span>
                  <pre className="font-mono text-xs mt-1 bg-muted rounded p-2 overflow-x-auto">
                    {JSON.stringify(agent.mcp_config, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Actions */}
        {saveError && <p className="text-sm text-destructive">{saveError}</p>}
        <div className="flex items-center gap-3">
          <Button
            onClick={handleSave}
            disabled={updateAgent.isPending || !hasLocalChanges}
          >
            {updateAgent.isPending ? "Saving..." : "Save Changes"}
          </Button>
          {updateAgent.isSuccess && !updateAgent.isPending && (
            <span className="text-xs text-green-600 dark:text-green-400">✓ Saved</span>
          )}
          {!agent.is_builtin && (
            <Button
              variant="outline"
              className="text-destructive hover:text-destructive ml-auto"
              onClick={handleDelete}
              disabled={deleteAgent.isPending}
            >
              {deleteAgent.isPending ? "Deleting..." : "Delete Agent"}
            </Button>
          )}
          <Link href="/agents" className={agent.is_builtin ? "ml-auto" : ""}>
            <Button variant="ghost" size="sm">← Back</Button>
          </Link>
        </div>

      </div>
    </div>
  );
}
