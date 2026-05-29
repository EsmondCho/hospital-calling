"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { promptsApi, type NewPrompt } from "@/lib/api";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

const EMPTY: NewPrompt = {
  name: "",
  body: "",
  notes: "",
};

export function NewPromptForm() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<NewPrompt>(EMPTY);

  const mutation = useMutation({
    mutationFn: promptsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      setForm(EMPTY);
      setOpen(false);
    },
  });

  if (!open) {
    return (
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setOpen(true)}>+ New prompt</Button>
      </div>
    );
  }

  return (
    <Card className="mb-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">
        New prompt (created as version 1)
      </h2>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({
            ...form,
            notes: form.notes || null,
          });
        }}
      >
        <input
          className={FIELD_CLASS}
          placeholder="Name (e.g. Referral policy)"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <textarea
          className={`${FIELD_CLASS} min-h-[200px] font-mono text-xs`}
          placeholder="Body (BlandAI task prompt)"
          required
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="Notes (optional)"
          value={form.notes ?? ""}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {mutation.error && (
          <p className="text-sm text-destructive">
            {(mutation.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
