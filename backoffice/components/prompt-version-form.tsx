"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { promptsApi, type Prompt } from "@/lib/api";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

type Props = {
  // The version this new version is seeded from (usually the latest).
  basis: Prompt;
};

// Detail-page action: opens an editor prefilled from the latest version and,
// on submit, POSTs a brand-new version (server auto-bumps `version`).
export function PromptVersionForm({ basis }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  // `notes` describes *this* version's change, so it always starts empty
  // rather than inheriting the prior note.
  const [form, setForm] = useState({
    body: basis.body ?? "",
    notes: "",
  });

  const create = useMutation({
    mutationFn: () =>
      promptsApi.create({
        name: basis.name,
        body: form.body,
        notes: form.notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", basis.name] });
      setEditing(false);
    },
  });

  if (!editing) {
    return (
      <div className="mt-4">
        <Button variant="outline" onClick={() => setEditing(true)}>
          New version
        </Button>
      </div>
    );
  }

  return (
    <Card className="mt-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">
        New version (server auto-bumps the version number)
      </h2>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <input
          className={`${FIELD_CLASS} cursor-not-allowed opacity-60`}
          placeholder="Name"
          readOnly
          value={basis.name}
        />
        <textarea
          className={`${FIELD_CLASS} min-h-[240px] font-mono text-xs`}
          placeholder="Body"
          required
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="Notes (optional)"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            type="button"
            onClick={() => setEditing(false)}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Save version"}
          </Button>
        </div>
        {create.error && (
          <p className="text-sm text-destructive">
            {(create.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
