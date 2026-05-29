"use client";

import type { Prompt } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Props = {
  versions: Prompt[];
  selectedId: number | null;
  onSelect: (id: number) => void;
};

// Sidebar list of every version row for a prompt. Newest first (as returned
// by the API). The selected row is highlighted.
export function PromptVersionList({ versions, selectedId, onSelect }: Props) {
  return (
    <ul className="divide-y divide-border">
      {versions.map((v) => (
        <li key={v.id}>
          <button
            type="button"
            onClick={() => onSelect(v.id)}
            className={cn(
              "flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
              v.id === selectedId && "bg-accent font-medium",
            )}
          >
            <span>v{v.version}</span>
            <span className="text-xs text-muted-foreground">
              {formatDateTime(v.updated_at)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
