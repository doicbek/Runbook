"use client";

import { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  useSkills,
  useCreateSkill,
  useUpdateSkill,
  useDeleteSkill,
  useConcepts,
  useCreateConcept,
  useDeleteConcept,
  useOntologyGraph,
  useCreateRelation,
  useDeleteRelation,
} from "@/hooks/use-agent-skills";
import type { AgentSkill, OntologyNode, OntologyEdge } from "@/types";

const AGENT_TYPES = [
  "arxiv_search",
  "code_execution",
  "coding",
  "data_retrieval",
  "spreadsheet",
  "report",
  "general",
  "sub_action",
  "mcp",
];

const CATEGORIES = ["learning", "error_pattern", "correction", "best_practice"] as const;
const PRIORITIES = ["low", "medium", "high", "critical"] as const;
const CONCEPT_TYPES = ["tool", "library", "api", "data_format", "anti_pattern", "technique"] as const;
const RELATION_TYPES = ["depends_on", "supersedes", "related_to", "fixes", "uses_tool", "produces", "avoids"] as const;

const sourceBadge: Record<string, string> = {
  manual: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  auto: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  correction: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
};

const categoryBadge: Record<string, string> = {
  learning: "bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-400",
  error_pattern: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  correction: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  best_practice: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
};

const priorityBadge: Record<string, string> = {
  low: "text-gray-500 dark:text-gray-400",
  medium: "text-blue-600 dark:text-blue-400",
  high: "text-orange-600 dark:text-orange-400",
  critical: "text-red-600 dark:text-red-400 font-bold",
};

const statusBadge: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  resolved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  promoted: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  "won't_fix": "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
};

const conceptTypeColors: Record<string, string> = {
  tool: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  library: "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-400",
  api: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400",
  data_format: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
  anti_pattern: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400",
  technique: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
};

const relationTypeColors: Record<string, string> = {
  depends_on: "text-blue-600 dark:text-blue-400",
  supersedes: "text-orange-600 dark:text-orange-400",
  related_to: "text-gray-600 dark:text-gray-400",
  fixes: "text-green-600 dark:text-green-400",
  uses_tool: "text-indigo-600 dark:text-indigo-400",
  produces: "text-teal-600 dark:text-teal-400",
  avoids: "text-rose-600 dark:text-rose-400",
};

// ── Skills Tab ──────────────────────────────────────────────────────────

function SkillsTab({ filterType }: { filterType: string }) {
  const [filterCategory, setFilterCategory] = useState<string>("");
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const [formAgentType, setFormAgentType] = useState(AGENT_TYPES[0]);
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState<string>("learning");
  const [formPriority, setFormPriority] = useState<string>("medium");

  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editPriority, setEditPriority] = useState("");
  const [editStatus, setEditStatus] = useState("");

  const { data: skills, isLoading } = useSkills(filterType || undefined);
  const createSkill = useCreateSkill();
  const updateSkill = useUpdateSkill();
  const deleteSkill = useDeleteSkill();

  const filtered = filterCategory
    ? skills?.filter((s) => s.category === filterCategory)
    : skills;

  const stats = skills
    ? {
        total: skills.length,
        promoted: skills.filter((s) => s.status === "promoted").length,
        errors: skills.filter((s) => s.category === "error_pattern").length,
        corrections: skills.filter((s) => s.category === "correction").length,
        highPri: skills.filter(
          (s) => s.status === "pending" && (s.priority === "high" || s.priority === "critical")
        ).length,
      }
    : null;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim() || !formDescription.trim()) return;
    await createSkill.mutateAsync({
      agent_type: formAgentType,
      title: formTitle.trim(),
      description: formDescription.trim(),
      category: formCategory,
      priority: formPriority,
    });
    setFormTitle("");
    setFormDescription("");
    setShowForm(false);
  };

  const handleStartEdit = (skill: AgentSkill) => {
    setEditingId(skill.id);
    setEditTitle(skill.title);
    setEditDescription(skill.description);
    setEditPriority(skill.priority);
    setEditStatus(skill.status);
  };

  const handleSaveEdit = async (id: string) => {
    await updateSkill.mutateAsync({
      id,
      title: editTitle.trim(),
      description: editDescription.trim(),
      priority: editPriority,
      status: editStatus,
    });
    setEditingId(null);
  };

  const handleToggleActive = async (skill: AgentSkill) => {
    await updateSkill.mutateAsync({
      id: skill.id,
      is_active: !skill.is_active,
    });
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this skill? This cannot be undone.")) return;
    await deleteSkill.mutateAsync(id);
  };

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      {stats && stats.total > 0 && (
        <div className="flex gap-4 text-xs">
          <span className="text-muted-foreground">{stats.total} total</span>
          {stats.promoted > 0 && (
            <span className="text-yellow-600 dark:text-yellow-400">{stats.promoted} promoted</span>
          )}
          {stats.errors > 0 && (
            <span className="text-red-600 dark:text-red-400">{stats.errors} error patterns</span>
          )}
          {stats.corrections > 0 && (
            <span className="text-amber-600 dark:text-amber-400">{stats.corrections} corrections</span>
          )}
          {stats.highPri > 0 && (
            <span className="text-orange-600 dark:text-orange-400">{stats.highPri} high priority pending</span>
          )}
        </div>
      )}

      {/* Add form */}
      <div className="flex items-center justify-between">
        <Button size="sm" variant="outline" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : "Add Skill"}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader className="pb-2">
            <h2 className="font-semibold text-sm">New Skill</h2>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-3">
              <div className="flex gap-3 flex-wrap">
                <div className="space-y-1">
                  <label className="text-xs font-medium">Agent Type</label>
                  <select
                    value={formAgentType}
                    onChange={(e) => setFormAgentType(e.target.value)}
                    className="w-full text-sm border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    {AGENT_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Category</label>
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="w-full text-sm border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c.replace("_", " ")}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Priority</label>
                  <select
                    value={formPriority}
                    onChange={(e) => setFormPriority(e.target.value)}
                    className="w-full text-sm border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1 space-y-1 min-w-[200px]">
                  <label className="text-xs font-medium">Title</label>
                  <Input
                    value={formTitle}
                    onChange={(e) => setFormTitle(e.target.value)}
                    placeholder="e.g. Always install scipy before curve fitting"
                    className="text-sm"
                    required
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Description</label>
                <Textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  rows={5}
                  placeholder="Detailed instructions for the agent..."
                  className="text-sm"
                  required
                />
              </div>
              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={createSkill.isPending}>
                  {createSkill.isPending ? "Creating..." : "Create Skill"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs font-medium text-muted-foreground">Category:</label>
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="text-sm border rounded px-2 py-1 bg-background text-foreground"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace("_", " ")}</option>
          ))}
        </select>
        {filtered && (
          <span className="text-xs text-muted-foreground ml-2">
            {filtered.length} skill{filtered.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Skills list */}
      {isLoading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-16 bg-muted/50 animate-pulse rounded-lg" />
          ))}
        </div>
      )}

      {filtered?.length === 0 && !isLoading && (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-sm">No skills yet.</p>
          <p className="text-xs mt-1">
            Skills are auto-generated from successes and failures, or create them manually.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {filtered?.map((skill) => (
          <div
            key={skill.id}
            className={`border rounded-lg transition-colors ${
              !skill.is_active
                ? "bg-muted/30 opacity-60"
                : skill.status === "promoted"
                ? "bg-yellow-50/50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800/30"
                : skill.category === "error_pattern"
                ? "bg-red-50/30 dark:bg-red-900/5 border-red-200/50 dark:border-red-800/20"
                : "bg-background"
            }`}
          >
            <div className="flex items-center gap-2 px-4 py-3">
              <button
                onClick={() => setExpandedId(expandedId === skill.id ? null : skill.id)}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <svg
                  className={`w-3.5 h-3.5 transition-transform ${expandedId === skill.id ? "rotate-90" : ""}`}
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M6 3l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <span className={`text-[10px] font-mono ${priorityBadge[skill.priority] ?? ""}`} title={`Priority: ${skill.priority}`}>
                {skill.priority === "critical" ? "!!!" : skill.priority === "high" ? "!!" : skill.priority === "medium" ? "!" : "\u00b7"}
              </span>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {skill.status === "promoted" && <span className="text-yellow-600 dark:text-yellow-400 mr-1">*</span>}
                  {skill.title}
                </p>
              </div>

              <Badge variant="outline" className="text-[10px] shrink-0">{skill.agent_type}</Badge>
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${categoryBadge[skill.category] ?? ""}`}>
                {skill.category.replace("_", " ")}
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${sourceBadge[skill.source] ?? ""}`}>
                {skill.source}
              </span>

              {skill.recurrence_count > 1 && (
                <span className="text-[10px] text-muted-foreground tabular-nums shrink-0" title="Recurrence count">
                  {skill.recurrence_count}x
                </span>
              )}

              <button
                onClick={() => handleToggleActive(skill)}
                className={`w-8 h-4 rounded-full relative transition-colors shrink-0 ${
                  skill.is_active ? "bg-emerald-500" : "bg-gray-300 dark:bg-gray-600"
                }`}
                title={skill.is_active ? "Active" : "Inactive"}
              >
                <span
                  className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
                    skill.is_active ? "left-4" : "left-0.5"
                  }`}
                />
              </button>

              <button
                onClick={() => handleStartEdit(skill)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                title="Edit"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <button
                onClick={() => handleDelete(skill.id)}
                className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                title="Delete"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M2 4h12M5.33 4V2.67a1.33 1.33 0 011.34-1.34h2.66a1.33 1.33 0 011.34 1.34V4m2 0v9.33a1.33 1.33 0 01-1.34 1.34H4.67a1.33 1.33 0 01-1.34-1.34V4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>

            {expandedId === skill.id && editingId !== skill.id && (
              <div className="px-4 pb-3 pt-0 border-t mx-4 mb-2 mt-1">
                <p className="text-xs text-muted-foreground whitespace-pre-wrap pt-2">{skill.description}</p>
                <div className="flex gap-4 mt-3 text-[10px] text-muted-foreground/60 flex-wrap">
                  {skill.pattern_key && <span>Pattern: <code className="font-mono">{skill.pattern_key}</code></span>}
                  <span className={`${statusBadge[skill.status] ?? ""} px-1 rounded`}>{skill.status}</span>
                  <span>Seen {skill.recurrence_count}x</span>
                  <span>First: {new Date(skill.first_seen).toLocaleDateString()}</span>
                  <span>Last: {new Date(skill.last_seen).toLocaleDateString()}</span>
                  {skill.source_action_id && (
                    <Link href={`/actions/${skill.source_action_id}`} className="hover:underline">Source action</Link>
                  )}
                </div>
              </div>
            )}

            {editingId === skill.id && (
              <div className="px-4 pb-3 border-t mx-4 mb-2 mt-1 space-y-2 pt-2">
                <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} className="text-sm" />
                <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} rows={5} className="text-sm" />
                <div className="flex gap-3 items-center">
                  <div className="space-y-1">
                    <label className="text-[10px] font-medium text-muted-foreground">Priority</label>
                    <select
                      value={editPriority}
                      onChange={(e) => setEditPriority(e.target.value)}
                      className="text-xs border rounded px-1.5 py-1 bg-background text-foreground"
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] font-medium text-muted-foreground">Status</label>
                    <select
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value)}
                      className="text-xs border rounded px-1.5 py-1 bg-background text-foreground"
                    >
                      <option value="pending">pending</option>
                      <option value="resolved">resolved</option>
                      <option value="promoted">promoted</option>
                      <option value="won't_fix">won&apos;t fix</option>
                    </select>
                  </div>
                  <div className="flex gap-2 ml-auto">
                    <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>Cancel</Button>
                    <Button size="sm" onClick={() => handleSaveEdit(skill.id)} disabled={updateSkill.isPending}>
                      {updateSkill.isPending ? "Saving..." : "Save"}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Ontology Graph Visualization (SVG) ──────────────────────────────────

function OntologyGraphView({ nodes, edges }: { nodes: OntologyNode[]; edges: OntologyEdge[] }) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Simple force-directed-ish layout using deterministic positions
  const positions = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    if (nodes.length === 0) return pos;

    const skills = nodes.filter((n) => n.type === "skill");
    const concepts = nodes.filter((n) => n.type === "concept");

    // Skills in a circle on the left side
    skills.forEach((node, i) => {
      const angle = (i / Math.max(skills.length, 1)) * Math.PI * 2 - Math.PI / 2;
      const rx = Math.min(skills.length * 20, 180);
      const ry = Math.min(skills.length * 20, 140);
      pos[node.id] = {
        x: 250 + Math.cos(angle) * rx,
        y: 200 + Math.sin(angle) * ry,
      };
    });

    // Concepts in a circle on the right side
    concepts.forEach((node, i) => {
      const angle = (i / Math.max(concepts.length, 1)) * Math.PI * 2 - Math.PI / 2;
      const rx = Math.min(concepts.length * 18, 150);
      const ry = Math.min(concepts.length * 18, 120);
      pos[node.id] = {
        x: 550 + Math.cos(angle) * rx,
        y: 200 + Math.sin(angle) * ry,
      };
    });

    return pos;
  }, [nodes]);

  const connectedEdges = useMemo(() => {
    if (!hoveredNode) return new Set<string>();
    return new Set(
      edges.filter((e) => e.from_id === hoveredNode || e.to_id === hoveredNode).map((e) => e.id)
    );
  }, [hoveredNode, edges]);

  const connectedNodes = useMemo(() => {
    if (!hoveredNode) return new Set<string>();
    const set = new Set<string>([hoveredNode]);
    edges.forEach((e) => {
      if (e.from_id === hoveredNode) set.add(e.to_id);
      if (e.to_id === hoveredNode) set.add(e.from_id);
    });
    return set;
  }, [hoveredNode, edges]);

  if (nodes.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-sm">No graph data yet.</p>
        <p className="text-xs mt-1">Concepts and relations will appear here as skills are created.</p>
      </div>
    );
  }

  return (
    <div className="border rounded-lg bg-muted/20 overflow-hidden">
      <svg viewBox="0 0 800 400" className="w-full h-[400px]">
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" className="fill-muted-foreground/40" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map((edge) => {
          const from = positions[edge.from_id];
          const to = positions[edge.to_id];
          if (!from || !to) return null;
          const isHighlighted = hoveredNode ? connectedEdges.has(edge.id) : true;
          return (
            <g key={edge.id}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className={`transition-opacity ${isHighlighted ? "opacity-60" : "opacity-10"}`}
                stroke="currentColor"
                strokeWidth={isHighlighted ? 1.5 : 0.5}
                markerEnd="url(#arrowhead)"
              />
              {isHighlighted && (
                <text
                  x={(from.x + to.x) / 2}
                  y={(from.y + to.y) / 2 - 4}
                  textAnchor="middle"
                  className={`text-[8px] ${relationTypeColors[edge.relation_type] ?? "text-muted-foreground"}`}
                  fill="currentColor"
                >
                  {edge.relation_type.replace("_", " ")}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const pos = positions[node.id];
          if (!pos) return null;
          const isHighlighted = hoveredNode ? connectedNodes.has(node.id) : true;
          const isSkill = node.type === "skill";

          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              className="cursor-pointer"
            >
              {isSkill ? (
                <rect
                  x={pos.x - 8}
                  y={pos.y - 8}
                  width={16}
                  height={16}
                  rx={3}
                  className={`transition-opacity ${
                    node.status === "promoted"
                      ? "fill-yellow-500 dark:fill-yellow-400"
                      : node.category === "error_pattern"
                      ? "fill-red-500 dark:fill-red-400"
                      : node.category === "correction"
                      ? "fill-amber-500 dark:fill-amber-400"
                      : "fill-sky-500 dark:fill-sky-400"
                  } ${isHighlighted ? "opacity-100" : "opacity-20"}`}
                />
              ) : (
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={8}
                  className={`transition-opacity ${
                    node.concept_type === "anti_pattern"
                      ? "fill-rose-500 dark:fill-rose-400"
                      : node.concept_type === "library"
                      ? "fill-violet-500 dark:fill-violet-400"
                      : node.concept_type === "api"
                      ? "fill-cyan-500 dark:fill-cyan-400"
                      : "fill-indigo-500 dark:fill-indigo-400"
                  } ${isHighlighted ? "opacity-100" : "opacity-20"}`}
                />
              )}
              <text
                x={pos.x}
                y={pos.y + 20}
                textAnchor="middle"
                className={`text-[9px] transition-opacity fill-current ${
                  isHighlighted ? "text-foreground opacity-100" : "text-muted-foreground opacity-20"
                }`}
              >
                {node.label.length > 20 ? node.label.slice(0, 18) + "..." : node.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-t text-[10px] text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-sky-500 inline-block" /> Skill
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-indigo-500 inline-block" /> Concept
        </span>
        <span className="text-muted-foreground/50">|</span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-yellow-500 inline-block" /> Promoted
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-red-500 inline-block" /> Error Pattern
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-violet-500 inline-block" /> Library
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-rose-500 inline-block" /> Anti-pattern
        </span>
      </div>
    </div>
  );
}

// ── Ontology Tab ────────────────────────────────────────────────────────

function OntologyTab({ filterType }: { filterType: string }) {
  const [showConceptForm, setShowConceptForm] = useState(false);
  const [showRelationForm, setShowRelationForm] = useState(false);
  const [conceptName, setConceptName] = useState("");
  const [conceptType, setConceptType] = useState<string>("tool");
  const [conceptDesc, setConceptDesc] = useState("");

  const [relFromId, setRelFromId] = useState("");
  const [relType, setRelType] = useState<string>("uses_tool");
  const [relToId, setRelToId] = useState("");

  const { data: concepts, isLoading: conceptsLoading } = useConcepts();
  const { data: graph, isLoading: graphLoading } = useOntologyGraph(filterType || undefined);
  const createConceptMut = useCreateConcept();
  const deleteConceptMut = useDeleteConcept();
  const createRelationMut = useCreateRelation();
  const deleteRelationMut = useDeleteRelation();

  // Build a node lookup from graph for the relation form
  const allNodes = useMemo(() => graph?.nodes ?? [], [graph]);

  const handleCreateConcept = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!conceptName.trim()) return;
    await createConceptMut.mutateAsync({
      name: conceptName.trim().toLowerCase(),
      concept_type: conceptType,
      description: conceptDesc.trim() || undefined,
    });
    setConceptName("");
    setConceptDesc("");
    setShowConceptForm(false);
  };

  const handleCreateRelation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!relFromId || !relToId) return;
    try {
      await createRelationMut.mutateAsync({
        from_id: relFromId,
        relation_type: relType,
        to_id: relToId,
      });
      setRelFromId("");
      setRelToId("");
      setShowRelationForm(false);
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <div className="space-y-6">
      {/* Graph visualization */}
      <div>
        <h3 className="text-sm font-semibold mb-2">Knowledge Graph</h3>
        {graphLoading ? (
          <div className="h-[400px] bg-muted/50 animate-pulse rounded-lg" />
        ) : (
          <OntologyGraphView nodes={graph?.nodes ?? []} edges={graph?.edges ?? []} />
        )}
      </div>

      {/* Concepts section */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Concepts</h3>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowRelationForm(!showRelationForm)}>
              {showRelationForm ? "Cancel" : "Add Relation"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowConceptForm(!showConceptForm)}>
              {showConceptForm ? "Cancel" : "Add Concept"}
            </Button>
          </div>
        </div>

        {/* Add concept form */}
        {showConceptForm && (
          <Card className="mb-3">
            <CardContent className="pt-4">
              <form onSubmit={handleCreateConcept} className="flex gap-3 items-end flex-wrap">
                <div className="space-y-1">
                  <label className="text-xs font-medium">Name</label>
                  <Input
                    value={conceptName}
                    onChange={(e) => setConceptName(e.target.value)}
                    placeholder="e.g. scipy, csv, rate_limiting"
                    className="text-sm w-48"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Type</label>
                  <select
                    value={conceptType}
                    onChange={(e) => setConceptType(e.target.value)}
                    className="text-sm border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    {CONCEPT_TYPES.map((t) => (
                      <option key={t} value={t}>{t.replace("_", " ")}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1 flex-1 min-w-[150px]">
                  <label className="text-xs font-medium">Description (optional)</label>
                  <Input
                    value={conceptDesc}
                    onChange={(e) => setConceptDesc(e.target.value)}
                    placeholder="Brief description"
                    className="text-sm"
                  />
                </div>
                <Button type="submit" size="sm" disabled={createConceptMut.isPending}>
                  {createConceptMut.isPending ? "Creating..." : "Create"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Add relation form */}
        {showRelationForm && (
          <Card className="mb-3">
            <CardContent className="pt-4">
              <form onSubmit={handleCreateRelation} className="flex gap-3 items-end flex-wrap">
                <div className="space-y-1">
                  <label className="text-xs font-medium">From</label>
                  <select
                    value={relFromId}
                    onChange={(e) => setRelFromId(e.target.value)}
                    className="text-sm border rounded px-2 py-1.5 bg-background text-foreground max-w-[200px]"
                    required
                  >
                    <option value="">Select node...</option>
                    <optgroup label="Skills">
                      {allNodes.filter((n) => n.type === "skill").map((n) => (
                        <option key={n.id} value={n.id}>{n.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Concepts">
                      {allNodes.filter((n) => n.type === "concept").map((n) => (
                        <option key={n.id} value={n.id}>{n.label}</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Relation</label>
                  <select
                    value={relType}
                    onChange={(e) => setRelType(e.target.value)}
                    className="text-sm border rounded px-2 py-1.5 bg-background text-foreground"
                  >
                    {RELATION_TYPES.map((t) => (
                      <option key={t} value={t}>{t.replace("_", " ")}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">To</label>
                  <select
                    value={relToId}
                    onChange={(e) => setRelToId(e.target.value)}
                    className="text-sm border rounded px-2 py-1.5 bg-background text-foreground max-w-[200px]"
                    required
                  >
                    <option value="">Select node...</option>
                    <optgroup label="Skills">
                      {allNodes.filter((n) => n.type === "skill").map((n) => (
                        <option key={n.id} value={n.id}>{n.label}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Concepts">
                      {allNodes.filter((n) => n.type === "concept").map((n) => (
                        <option key={n.id} value={n.id}>{n.label}</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
                <Button type="submit" size="sm" disabled={createRelationMut.isPending}>
                  {createRelationMut.isPending ? "Creating..." : "Create"}
                </Button>
              </form>
              {createRelationMut.isError && (
                <p className="text-xs text-destructive mt-2">
                  Failed to create relation. Check for duplicates or self-loops.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Concept list */}
        {conceptsLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-10 bg-muted/50 animate-pulse rounded" />
            ))}
          </div>
        ) : concepts?.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm">No concepts yet.</p>
            <p className="text-xs mt-1">Concepts are auto-extracted from skills or can be added manually.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {concepts?.map((concept) => (
              <div
                key={concept.id}
                className="border rounded-lg px-3 py-2 flex items-center gap-2 bg-background hover:bg-muted/30 transition-colors"
              >
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${conceptTypeColors[concept.concept_type] ?? ""}`}>
                  {concept.concept_type.replace("_", " ")}
                </span>
                <span className="text-sm font-medium flex-1 truncate">{concept.name}</span>
                <button
                  onClick={() => {
                    if (confirm(`Delete concept "${concept.name}"?`)) {
                      deleteConceptMut.mutate(concept.id);
                    }
                  }}
                  className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
                  title="Delete concept"
                >
                  <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Relations in graph edges section */}
      {graph?.edges && graph.edges.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2">Relations ({graph.edges.length})</h3>
          <div className="space-y-1 max-h-[200px] overflow-y-auto">
            {graph.edges.map((edge) => {
              const fromNode = allNodes.find((n) => n.id === edge.from_id);
              const toNode = allNodes.find((n) => n.id === edge.to_id);
              return (
                <div key={edge.id} className="flex items-center gap-2 text-xs px-3 py-1.5 border rounded bg-background">
                  <span className="font-medium truncate max-w-[150px]">{fromNode?.label ?? edge.from_id.slice(0, 8)}</span>
                  <span className={`shrink-0 ${relationTypeColors[edge.relation_type] ?? ""}`}>
                    {edge.relation_type.replace("_", " ")}
                  </span>
                  <span className="font-medium truncate max-w-[150px]">{toNode?.label ?? edge.to_id.slice(0, 8)}</span>
                  <button
                    onClick={() => deleteRelationMut.mutate(edge.id)}
                    className="ml-auto text-muted-foreground hover:text-destructive transition-colors shrink-0"
                    title="Delete relation"
                  >
                    <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────

export default function SkillsPage() {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<"skills" | "ontology">("skills");
  const [filterType, setFilterType] = useState<string>(searchParams.get("agent_type") || "");

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Skills</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Self-improving knowledge base. Learnings, error patterns, corrections, and best practices.
          </p>
        </div>

        {/* Tabs + Agent filter */}
        <div className="flex items-center gap-4 border-b">
          <button
            onClick={() => setActiveTab("skills")}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "skills"
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Skills
          </button>
          <button
            onClick={() => setActiveTab("ontology")}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "ontology"
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Ontology
          </button>
          <div className="ml-auto pb-2">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="text-sm border rounded px-2 py-1 bg-background text-foreground"
            >
              <option value="">All agents</option>
              {AGENT_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Tab content */}
        {activeTab === "skills" ? (
          <SkillsTab filterType={filterType} />
        ) : (
          <OntologyTab filterType={filterType} />
        )}
      </div>
    </div>
  );
}
