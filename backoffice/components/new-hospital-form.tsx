"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { hospitalsApi, type NewHospital } from "@/lib/api";
import { ALLOWED_TIMEZONES, HOSPITAL_OWNERSHIPS } from "@/lib/timezones";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// Manual hospitals are usually a deliberate call target → default
// INDEPENDENT (the only ownership the dispatch pipeline dials).
const EMPTY: NewHospital = {
  name: "",
  phone_e164: "",
  city: "",
  state: "",
  timezone: "",
  ownership: "INDEPENDENT",
};

export function NewHospitalForm() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<NewHospital>(EMPTY);

  const mutation = useMutation({
    mutationFn: hospitalsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hospitals"] });
      setForm(EMPTY);
      setOpen(false);
    },
  });

  if (!open) {
    // Manual hospital creation is disabled — hospitals are added only
    // through the sourcing pipeline. The form below is left intact so the
    // button can be re-enabled if that policy ever changes.
    return (
      <div className="mb-4 flex items-center justify-end gap-2">
        <span className="text-xs text-muted-foreground">
          Hospitals are added via sourcing.
        </span>
        <Button disabled title="Hospitals are added via sourcing only">
          + New hospital
        </Button>
      </div>
    );
  }

  return (
    <Card className="mb-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">New hospital (source = MANUAL)</h2>
      <form
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          // Drop empty-string timezone so the server keeps it null.
          const payload = { ...form, timezone: form.timezone || null };
          mutation.mutate(payload);
        }}
      >
        <input
          className={FIELD_CLASS}
          placeholder="Name"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="Phone (E.164, e.g. +15551234567)"
          value={form.phone_e164 ?? ""}
          onChange={(e) => setForm({ ...form, phone_e164: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="City"
          value={form.city ?? ""}
          onChange={(e) => setForm({ ...form, city: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="State (2-letter)"
          maxLength={2}
          value={form.state ?? ""}
          onChange={(e) => setForm({ ...form, state: e.target.value.toUpperCase() })}
        />
        <select
          className={FIELD_CLASS}
          value={form.timezone ?? ""}
          onChange={(e) => setForm({ ...form, timezone: e.target.value })}
        >
          <option value="">Timezone (none)</option>
          {ALLOWED_TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
        <select
          className={FIELD_CLASS}
          value={form.ownership ?? "INDEPENDENT"}
          onChange={(e) => setForm({ ...form, ownership: e.target.value })}
        >
          {HOSPITAL_OWNERSHIPS.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <div className="col-span-1 flex justify-end gap-2 sm:col-span-2">
          <Button variant="outline" type="button" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {mutation.error && (
          <p className="col-span-1 text-sm text-destructive sm:col-span-2">
            {(mutation.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
