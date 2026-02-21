"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ToolSelector } from "@/components/agents/tool-selector";
import {
  useCreateAgentDefinition,
  useScaffoldAgent,
  useUpdateAgentDefinition,
} from "@/hooks/use-agent-definitions";
import { useAvailableModels } from "@/hooks/use-models";
import type { AgentDefinition } from "@/types";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s_]/g, "")
    .replace(/\s+/g, "_")
    .replace(/^([^a-z])/, "a$1")
    .slice(0, 60);
}

interface AgentBuilderFormProps {
  mode: "create" | "edit";
  initialData?: AgentDefinition;
}

export function AgentBuilderForm({ mode, initialData }: AgentBuilderFormProps) {
  const router = useRouter();
  const [name, setName] = useState(initialData?.name ?? "");
  const [agentType, setAgentType] = useState(initialData?.agent_type ?? "");
  const [agentTypeManual, setAgentTypeManual] = useState(false);
  const [description, setDescription] = useState(initialData?.description ?? "");
  const [selectedTools, setSelectedTools] = useState<string[]>(initialData?.tools ?? []);
  const [scaffoldModel, setScaffoldModel] = useState("");
  const [code, setCode] = useState(initialData?.code ?? "");
  const [requirements, setRequirements] = useState(initialData?.requirements ?? "");
  const [setupNotes, setSetupNotes] = useState(initialData?.setup_notes ?? "");
  const [mcpConfig, setMcpConfig] = useState(
    initialData?.mcp_config ? JSON.stringify(initialData.mcp_config, null, 2) : ""
  );
  const [icon, setIcon] = useState(initialData?.icon ?? "🤖");
  const [saveError, setSaveError] = useState("");

  const scaffold = useScaffoldAgent();
  const createAgent = useCreateAgentDefinition();
  const updateAgent = useUpdateAgentDefinition();
  const { data: modelsData } = useAvailableModels();

  const handleNameChange = (val: string) => {
    setName(val);
    if (!agentTypeManual) {
      setAgentType(slugify(val));
    }
  };

  const handleGenerate = async () => {
    if (!name.trim() || !description.trim()) return;
    const result = await scaffold.mutateAsync({
      name: name.trim(),
      description: description.trim(),
      tools: selectedTools,
      model: scaffoldModel || undefined,
    });
    setCode(result.code);
    setRequirements(result.requirements);
    setSetupNotes(result.setup_notes);
  };

  const handleSave = async () => {
    setSaveError("");
    try {
      let mcpConfigParsed: Record<string, unknown> | null = null;
      if (mcpConfig.trim()) {
        try {
          mcpConfigParsed = JSON.parse(mcpConfig);
        } catch {
          setSaveError("MCP Config is not valid JSON");
          return;
        }
      }

      const body = {
        agent_type: agentType,
        name: name.trim(),
        description: description.trim(),
        code: code || null,
        tools: selectedTools,
        requirements: requirements || null,
        setup_notes: setupNotes || null,
        mcp_config: mcpConfigParsed,
        icon,
        status: "active" as const,
      };

      if (mode === "create") {
        await createAgent.mutateAsync(body);
      } else if (initialData) {
        await updateAgent.mutateAsync({ id: initialData.id, body });
      }
      router.push("/agents");
    } catch (err: unknown) {
      const e = err as { message?: string };
      setSaveError(e?.message ?? "Save failed");
    }
  };

  const isSaving = createAgent.isPending || updateAgent.isPending;
  const showMcpConfig = selectedTools.includes("mcp");

  // Group models by provider for the scaffold model selector
  const modelsByProvider: Record<string, { name: string; display_name: string }[]> = {};
  if (modelsData?.models) {
    for (const m of modelsData.models) {
      if (!modelsByProvider[m.provider]) modelsByProvider[m.provider] = [];
      modelsByProvider[m.provider].push(m);
    }
  }

  const providerLabels: Record<string, string> = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    deepseek: "DeepSeek",
    google: "Google",
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Basic info */}
      <Card>
        <CardHeader className="pb-2">
          <h2 className="font-semibold">Agent Details</h2>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-[1fr_auto] gap-3 items-start">
            <div className="space-y-1">
              <label className="text-xs font-medium">Name</label>
              <Input
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="e.g. Word Document Reader"
              />
            </div>
            <div className="space-y-1 w-12 text-center">
              <label className="text-xs font-medium">Icon</label>
              <Input
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                className="text-center text-lg"
                maxLength={2}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">
              Agent Type Slug{" "}
              <span className="text-muted-foreground font-normal">(unique identifier used in tasks)</span>
            </label>
            <Input
              value={agentType}
              onChange={(e) => {
                setAgentType(e.target.value);
                setAgentTypeManual(true);
              }}
              placeholder="e.g. word_doc_reader"
              className="font-mono text-sm"
              disabled={mode === "edit"}
            />
            <p className="text-xs text-muted-foreground">
              Lowercase letters, digits, underscores. Cannot be changed after creation.
            </p>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium">Description</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Describe what this agent does, what inputs it needs, and what it produces."
            />
          </div>
        </CardContent>
      </Card>

      {/* Tool selection */}
      <Card>
        <CardHeader className="pb-2">
          <h2 className="font-semibold">Tools</h2>
          <p className="text-xs text-muted-foreground">
            Select tools to include in the generated agent code.
          </p>
        </CardHeader>
        <CardContent>
          <ToolSelector selected={selectedTools} onChange={setSelectedTools} />
        </CardContent>
      </Card>

      {/* Code generation */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Agent Code</h2>
              <p className="text-xs text-muted-foreground">
                Generate a scaffold or write your own. The class must subclass BaseAgent.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {modelsData?.models && modelsData.models.length > 0 && (
                <select
                  value={scaffoldModel}
                  onChange={(e) => setScaffoldModel(e.target.value)}
                  className="text-xs border rounded px-2 py-1 bg-background text-foreground"
                >
                  <option value="">Default model</option>
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
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={handleGenerate}
                disabled={scaffold.isPending || !name.trim() || !description.trim()}
              >
                {scaffold.isPending ? "Generating..." : "Generate Code"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {scaffold.isError && (
            <p className="text-xs text-destructive">
              Generation failed: {(scaffold.error as Error)?.message}
            </p>
          )}
          <Textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={18}
            className="font-mono text-xs"
            placeholder="# Agent code will appear here after generation, or write your own..."
            spellCheck={false}
          />
        </CardContent>
      </Card>

      {/* Requirements & notes */}
      <Card>
        <CardHeader className="pb-2">
          <h2 className="font-semibold">Requirements & Notes</h2>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">pip install command</label>
            <Textarea
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              rows={2}
              className="font-mono text-xs"
              placeholder="pip install python-docx httpx"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">Setup Notes</label>
            <Textarea
              value={setupNotes}
              onChange={(e) => setSetupNotes(e.target.value)}
              rows={3}
              placeholder="Any special setup steps, environment variables, or warnings..."
            />
          </div>
          {showMcpConfig && (
            <div className="space-y-1">
              <label className="text-xs font-medium">MCP Config (JSON)</label>
              <Textarea
                value={mcpConfig}
                onChange={(e) => setMcpConfig(e.target.value)}
                rows={5}
                className="font-mono text-xs"
                placeholder='{"servers": [{"name": "filesystem", "command": "mcp-server-filesystem", "args": ["/path"]}]}'
              />
            </div>
          )}
        </CardContent>
      </Card>

      {saveError && (
        <p className="text-sm text-destructive">{saveError}</p>
      )}

      <div className="flex gap-3">
        <Button
          onClick={handleSave}
          disabled={isSaving || !name.trim() || !agentType.trim()}
        >
          {isSaving ? "Saving..." : mode === "create" ? "Save Agent" : "Update Agent"}
        </Button>
        <Button variant="outline" onClick={() => router.push("/agents")}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
