"use client";

import { useState } from "react";
import Link from "next/link";
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
} from "@/hooks/use-agent-skills";
import type { AgentSkill } from "@/types";

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

export default function SkillsPage() {
  const [filterType, setFilterType] = useState<string>("");
  const [filterCategory, setFilterCategory] = useState<string>("");
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [formAgentType, setFormAgentType] = useState(AGENT_TYPES[0]);
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState<string>("learning");
  const [formPriority, setFormPriority] = useState<string>("medium");

  // Edit state
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editPriority, setEditPriority] = useState("");
  const [editStatus, setEditStatus] = useState("");

  const { data: skills, isLoading } = useSkills(filterType || undefined);
  const createSkill = useCreateSkill();
  const updateSkill = useUpdateSkill();
  const deleteSkill = useDeleteSkill();

  // Client-side category filter (API already filters by agent_type)
  const filtered = filterCategory
    ? skills?.filter((s) => s.category === filterCategory)
    : skills;

  // Stats
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
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Skills</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Self-improving knowledge base. Learnings, error patterns, corrections, and best practices.
            </p>
          </div>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            {showForm ? "Cancel" : "Add Skill"}
          </Button>
        </div>

        {/* Stats bar */}
        {stats && stats.total > 0 && (
          <div className="flex gap-4 text-xs">
            <span className="text-muted-foreground">
              {stats.total} total
            </span>
            {stats.promoted > 0 && (
              <span className="text-yellow-600 dark:text-yellow-400">
                {stats.promoted} promoted
              </span>
            )}
            {stats.errors > 0 && (
              <span className="text-red-600 dark:text-red-400">
                {stats.errors} error patterns
              </span>
            )}
            {stats.corrections > 0 && (
              <span className="text-amber-600 dark:text-amber-400">
                {stats.corrections} corrections
              </span>
            )}
            {stats.highPri > 0 && (
              <span className="text-orange-600 dark:text-orange-400">
                {stats.highPri} high priority pending
              </span>
            )}
          </div>
        )}

        {/* Add form */}
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
                    placeholder="Detailed instructions for the agent — what to do, what to avoid, specific libraries/APIs/patterns..."
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
          <label className="text-xs font-medium text-muted-foreground">Filter:</label>
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
              {/* Row */}
              <div className="flex items-center gap-2 px-4 py-3">
                <button
                  onClick={() => setExpandedId(expandedId === skill.id ? null : skill.id)}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  <svg
                    className={`w-3.5 h-3.5 transition-transform ${
                      expandedId === skill.id ? "rotate-90" : ""
                    }`}
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M6 3l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>

                {/* Priority indicator */}
                <span className={`text-[10px] font-mono ${priorityBadge[skill.priority] ?? ""}`} title={`Priority: ${skill.priority}`}>
                  {skill.priority === "critical" ? "!!!" : skill.priority === "high" ? "!!" : skill.priority === "medium" ? "!" : "·"}
                </span>

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {skill.status === "promoted" && <span className="text-yellow-600 dark:text-yellow-400 mr-1">*</span>}
                    {skill.title}
                  </p>
                </div>

                <Badge variant="outline" className="text-[10px] shrink-0">
                  {skill.agent_type}
                </Badge>
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

              {/* Expanded description */}
              {expandedId === skill.id && editingId !== skill.id && (
                <div className="px-4 pb-3 pt-0 border-t mx-4 mb-2 mt-1">
                  <p className="text-xs text-muted-foreground whitespace-pre-wrap pt-2">
                    {skill.description}
                  </p>
                  <div className="flex gap-4 mt-3 text-[10px] text-muted-foreground/60 flex-wrap">
                    {skill.pattern_key && <span>Pattern: <code className="font-mono">{skill.pattern_key}</code></span>}
                    <span className={`${statusBadge[skill.status] ?? ""} px-1 rounded`}>
                      {skill.status}
                    </span>
                    <span>Seen {skill.recurrence_count}x</span>
                    <span>First: {new Date(skill.first_seen).toLocaleDateString()}</span>
                    <span>Last: {new Date(skill.last_seen).toLocaleDateString()}</span>
                    {skill.source_action_id && (
                      <Link href={`/actions/${skill.source_action_id}`} className="hover:underline">
                        Source action
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {/* Edit form */}
              {editingId === skill.id && (
                <div className="px-4 pb-3 border-t mx-4 mb-2 mt-1 space-y-2 pt-2">
                  <Input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="text-sm"
                  />
                  <Textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={5}
                    className="text-sm"
                  />
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
                      <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleSaveEdit(skill.id)}
                        disabled={updateSkill.isPending}
                      >
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
    </div>
  );
}
