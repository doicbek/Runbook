"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useTemplates,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useUseTemplate,
} from "@/hooks/use-templates";
import type { ActionTemplate } from "@/types";

export default function TemplatesPage() {
  const [search, setSearch] = useState("");
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const { data: templates, isLoading, error } = useTemplates({
    search: search || undefined,
    tag: tagFilter || undefined,
  });
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const deleteTemplate = useDeleteTemplate();
  const useTemplate = useUseTemplate();
  const router = useRouter();

  // Collect all unique tags
  const allTags = useMemo(() => {
    if (!templates) return [];
    const tags = new Set<string>();
    templates.forEach((t) => t.tags.forEach((tag) => tags.add(tag)));
    return Array.from(tags).sort();
  }, [templates]);

  const handleUse = async (id: string) => {
    try {
      const action = await useTemplate.mutateAsync(id);
      router.push(`/actions/${action.id}`);
    } catch {
      // error shown via mutation state
    }
  };

  const handleDelete = async (id: string) => {
    await deleteTemplate.mutateAsync(id);
    setDeleteConfirmId(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Templates</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Reusable action templates for common workflows.
            </p>
          </div>
          <Button onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : "+ New Template"}
          </Button>
        </div>

        {/* Create form */}
        {showCreate && (
          <CreateTemplateForm
            onCreated={() => setShowCreate(false)}
            createMutation={createTemplate}
          />
        )}

        {/* Search and tag filters */}
        <div className="flex items-center gap-3 mb-4">
          <Input
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs h-8 text-sm"
          />
          {allTags.length > 0 && (
            <div className="flex gap-1.5 flex-wrap">
              <button
                onClick={() => setTagFilter(null)}
                className={`px-2 py-0.5 text-[11px] rounded-full border transition-colors ${
                  !tagFilter
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                All
              </button>
              {allTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => setTagFilter(tag === tagFilter ? null : tag)}
                  className={`px-2 py-0.5 text-[11px] rounded-full border transition-colors ${
                    tag === tagFilter
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Loading / error / empty */}
        {isLoading && (
          <div className="text-sm text-muted-foreground">Loading templates...</div>
        )}
        {error && (
          <div className="text-sm text-destructive">
            Failed to load templates: {(error as Error).message}
          </div>
        )}
        {templates && templates.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-sm">
              No templates yet. Create one or save a completed action as a template.
            </p>
          </div>
        )}

        {/* Template grid */}
        {templates && templates.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((template) => (
              <div key={template.id}>
                {editingId === template.id ? (
                  <EditTemplateForm
                    template={template}
                    onCancel={() => setEditingId(null)}
                    updateMutation={updateTemplate}
                    onSaved={() => setEditingId(null)}
                  />
                ) : deleteConfirmId === template.id ? (
                  <div className="border border-destructive/50 rounded-lg p-4 bg-destructive/5">
                    <p className="text-sm mb-3">
                      Delete &ldquo;{template.title}&rdquo;? This cannot be undone.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDelete(template.id)}
                        disabled={deleteTemplate.isPending}
                      >
                        {deleteTemplate.isPending ? "Deleting..." : "Delete"}
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
                  <TemplateCard
                    template={template}
                    onUse={() => handleUse(template.id)}
                    onEdit={() => setEditingId(template.id)}
                    onDelete={() => setDeleteConfirmId(template.id)}
                    isUsing={useTemplate.isPending}
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

function TemplateCard({
  template,
  onUse,
  onEdit,
  onDelete,
  isUsing,
}: {
  template: ActionTemplate;
  onUse: () => void;
  onEdit: () => void;
  onDelete: () => void;
  isUsing: boolean;
}) {
  return (
    <div className="border border-border rounded-lg p-4 hover:border-foreground/20 transition-colors">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium leading-tight">{template.title}</h3>
        {template.usage_count > 0 && (
          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
            {template.usage_count} use{template.usage_count !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {template.description && (
        <p className="text-xs text-muted-foreground mb-2 line-clamp-2">
          {template.description}
        </p>
      )}

      <p className="text-xs text-muted-foreground/70 mb-3 line-clamp-2 italic">
        {template.root_prompt}
      </p>

      {template.tags.length > 0 && (
        <div className="flex gap-1 flex-wrap mb-3">
          {template.tags.map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 text-[10px] rounded bg-accent text-accent-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 border-t border-border">
        <Button size="sm" onClick={onUse} disabled={isUsing} className="text-xs h-7">
          Use
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onEdit}
          className="text-xs h-7 text-muted-foreground"
        >
          Edit
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onDelete}
          className="text-xs h-7 text-muted-foreground hover:text-destructive"
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

function CreateTemplateForm({
  onCreated,
  createMutation,
}: {
  onCreated: () => void;
  createMutation: ReturnType<typeof useCreateTemplate>;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [tagsInput, setTagsInput] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !prompt.trim()) return;
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await createMutation.mutateAsync({
      title: title.trim(),
      description: description.trim() || undefined,
      root_prompt: prompt.trim(),
      tags,
    });
    setTitle("");
    setDescription("");
    setPrompt("");
    setTagsInput("");
    onCreated();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-border rounded-lg p-4 mb-6 space-y-3"
    >
      <Input
        placeholder="Template title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-8 text-sm"
        required
      />
      <Input
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        className="h-8 text-sm"
      />
      <Textarea
        placeholder="Action prompt..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        className="text-sm"
        required
      />
      <Input
        placeholder="Tags (comma-separated, e.g. data, analysis)"
        value={tagsInput}
        onChange={(e) => setTagsInput(e.target.value)}
        className="h-8 text-sm"
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={createMutation.isPending}>
          {createMutation.isPending ? "Creating..." : "Create Template"}
        </Button>
      </div>
    </form>
  );
}

function EditTemplateForm({
  template,
  onCancel,
  updateMutation,
  onSaved,
}: {
  template: ActionTemplate;
  onCancel: () => void;
  updateMutation: ReturnType<typeof useUpdateTemplate>;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(template.title);
  const [description, setDescription] = useState(template.description || "");
  const [tagsInput, setTagsInput] = useState(template.tags.join(", "));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await updateMutation.mutateAsync({
      id: template.id,
      body: {
        title: title.trim(),
        description: description.trim() || undefined,
        tags,
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
      <Input
        placeholder="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        className="h-8 text-sm"
      />
      <Input
        placeholder="Tags (comma-separated)"
        value={tagsInput}
        onChange={(e) => setTagsInput(e.target.value)}
        className="h-8 text-sm"
      />
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
