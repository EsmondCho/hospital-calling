"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { hospitalsApi, type Hospital, type HospitalUpdate } from "@/lib/api";
import { ALLOWED_TIMEZONES, HOSPITAL_OWNERSHIPS } from "@/lib/timezones";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

type Props = {
  hospital: Hospital;
};

export function EditHospitalForm({ hospital }: Props) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<HospitalUpdate>({
    name: hospital.name,
    phone_e164: hospital.phone_e164 ?? "",
    city: hospital.city ?? "",
    state: hospital.state ?? "",
    timezone: hospital.timezone ?? "",
    ownership: hospital.ownership,
  });

  const update = useMutation({
    mutationFn: (input: HospitalUpdate) =>
      hospitalsApi.update(hospital.id, {
        ...input,
        timezone: input.timezone || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hospitals"] });
      queryClient.invalidateQueries({ queryKey: ["hospital", String(hospital.id)] });
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => hospitalsApi.remove(hospital.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hospitals"] });
      router.push("/hospitals");
    },
  });

  if (!editing) {
    return (
      <div className="mt-4 flex gap-2">
        <Button variant="outline" onClick={() => setEditing(true)}>
          Edit
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            if (confirm(`Delete hospital "${hospital.name}"? This cannot be undone.`)) {
              remove.mutate();
            }
          }}
          disabled={remove.isPending}
        >
          {remove.isPending ? "Deleting…" : "Delete"}
        </Button>
        {remove.error && (
          <p className="text-sm text-destructive">
            {(remove.error as Error).message}
          </p>
        )}
      </div>
    );
  }

  return (
    <Card className="mt-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">Edit hospital</h2>
      <p className="text-xs text-muted-foreground">
        Saving locks this row — the sourcing pipeline won&apos;t re-classify
        a hand-edited hospital.
      </p>
      <form
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate(form);
        }}
      >
        <input
          className={FIELD_CLASS}
          placeholder="Name"
          required
          value={form.name ?? ""}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className={FIELD_CLASS}
          placeholder="Phone"
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
          placeholder="State"
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
          value={form.ownership ?? "UNCLASSIFIED"}
          onChange={(e) => setForm({ ...form, ownership: e.target.value })}
        >
          {HOSPITAL_OWNERSHIPS.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <div className="col-span-1 flex justify-end gap-2 sm:col-span-2">
          <Button variant="outline" type="button" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {update.error && (
          <p className="col-span-1 text-sm text-destructive sm:col-span-2">
            {(update.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
