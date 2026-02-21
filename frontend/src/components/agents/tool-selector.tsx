"use client";

import { useToolCatalog } from "@/hooks/use-agent-definitions";
import type { ToolCatalogEntry } from "@/types";

const WSL2_UNAVAILABLE = new Set(["win32com"]);

interface ToolSelectorProps {
  selected: string[];
  onChange: (selected: string[]) => void;
}

export function ToolSelector({ selected, onChange }: ToolSelectorProps) {
  const { data: tools, isLoading } = useToolCatalog();

  if (isLoading) {
    return <div className="text-xs text-muted-foreground">Loading tools...</div>;
  }

  if (!tools?.length) return null;

  // Group by category
  const byCategory: Record<string, ToolCatalogEntry[]> = {};
  for (const t of tools) {
    if (!byCategory[t.category]) byCategory[t.category] = [];
    byCategory[t.category].push(t);
  }

  const toggle = (id: string) => {
    onChange(
      selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]
    );
  };

  return (
    <div className="space-y-3">
      {Object.entries(byCategory).map(([category, entries]) => (
        <fieldset key={category} className="border rounded-md p-3">
          <legend className="text-xs font-semibold px-1">{category}</legend>
          <div className="space-y-2 mt-1">
            {entries.map((tool) => {
              const unavailable = WSL2_UNAVAILABLE.has(tool.id);
              return (
                <label
                  key={tool.id}
                  className={`flex items-start gap-2 cursor-pointer rounded p-1 hover:bg-muted/50 ${unavailable ? "opacity-50" : ""}`}
                  title={unavailable ? "Not available in WSL2" : undefined}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(tool.id)}
                    onChange={() => !unavailable && toggle(tool.id)}
                    disabled={unavailable}
                    className="mt-0.5 shrink-0"
                  />
                  <div className="min-w-0">
                    <span className="text-xs font-medium">{tool.name}</span>
                    {unavailable && (
                      <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">
                        (WSL2 unavailable)
                      </span>
                    )}
                    <p className="text-xs text-muted-foreground">{tool.description}</p>
                  </div>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
