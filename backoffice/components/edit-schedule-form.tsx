"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DualTzInput } from "@/components/dual-tz-input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { Field } from "@/components/ui/field";
import {
  promptsApi,
  schedulesApi,
  SCHEDULE_MODELS,
  SCHEDULE_VOICES,
  type CallSchedule,
} from "@/lib/api";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// "random" gets a descriptive label; the rest show their plain name.
const voiceLabel = (v: string) => (v === "random" ? "Random (pooled)" : v);

const VOICE_OPTIONS: ComboboxOption[] = SCHEDULE_VOICES.map((v) => ({
  value: v,
  label: voiceLabel(v),
}));
const MODEL_OPTIONS: ComboboxOption[] = SCHEDULE_MODELS.map((m) => ({
  value: m,
  label: m,
}));

type Props = {
  schedule: CallSchedule;
};

// Edits a schedule's timing/content only — the hospital list is fixed at
// creation time and can't be edited (PATCH ignores it). The first target's
// timezone drives the local clock on the time picker.
export function EditScheduleForm({ schedule }: Props) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const isEditable = schedule.status === "PENDING";

  const prompts = useQuery({ queryKey: ["prompts"], queryFn: promptsApi.list });

  const [editing, setEditing] = useState(false);
  const [promptName, setPromptName] = useState<string | null>(
    schedule.prompt_name ?? null
  );
  const [versionId, setVersionId] = useState<string | null>(
    schedule.prompt_id ? String(schedule.prompt_id) : null
  );
  const [scheduledAt, setScheduledAt] = useState<string>(schedule.scheduled_at);
  const [memo, setMemo] = useState<string>(schedule.memo ?? "");
  // Old rows may carry an empty voice/model — fall back to the defaults so
  // the dropdown always shows a valid selection.
  const [voice, setVoice] = useState<string>(schedule.voice || "random");
  const [model, setModel] = useState<string>(schedule.model || "base");
  const [timeError, setTimeError] = useState<string | null>(null);

  const hospitalTimezone = schedule.targets[0]?.hospital_timezone ?? null;

  const versions = useQuery({
    queryKey: ["prompt", promptName],
    queryFn: () => promptsApi.versions(promptName as string),
    enabled: promptName != null,
  });

  // `versionId` is seeded from `schedule.prompt_id`, but the fetched versions
  // list may not contain it (e.g. that version was soft-deleted). Once the
  // list resolves, clear a stale id so it can't be silently re-submitted.
  useEffect(() => {
    if (!versions.data) return;
    setVersionId((prev) =>
      prev != null && versions.data.some((v) => String(v.id) === prev)
        ? prev
        : null,
    );
  }, [versions.data]);

  const update = useMutation({
    mutationFn: () =>
      schedulesApi.update(schedule.id, {
        prompt: versionId ? Number(versionId) : undefined,
        scheduled_at: scheduledAt,
        memo: memo || null,
        voice,
        model,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      queryClient.invalidateQueries({ queryKey: ["schedule", String(schedule.id)] });
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => schedulesApi.remove(schedule.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      router.push("/schedules");
    },
  });

  if (!editing) {
    return (
      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="outline"
          onClick={() => setEditing(true)}
          disabled={!isEditable}
        >
          Edit
        </Button>
        <Button
          variant="outline"
          disabled={!isEditable || remove.isPending}
          onClick={() => {
            if (confirm(`Delete schedule #${schedule.id}? This cannot be undone.`)) {
              remove.mutate();
            }
          }}
        >
          {remove.isPending ? "Deleting…" : "Delete"}
        </Button>
        {!isEditable && (
          <span className="text-xs text-muted-foreground">
            Schedule has been {schedule.status.toLowerCase()} — edit/delete locked.
          </span>
        )}
        {remove.error && (
          <p className="text-sm text-destructive">
            {(remove.error as Error).message}
          </p>
        )}
      </div>
    );
  }

  const promptOptions: ComboboxOption[] = (prompts.data ?? []).map((p) => ({
    value: p.name,
    label: p.name,
  }));
  const versionOptions: ComboboxOption[] = (versions.data ?? []).map((v) => ({
    value: String(v.id),
    label: `v${v.version}`,
  }));

  return (
    <Card className="mt-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">Edit schedule</h2>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!versionId) return;
          if (new Date(scheduledAt).getTime() <= Date.now()) {
            setTimeError("Scheduled time must be in the future.");
            return;
          }
          setTimeError(null);
          update.mutate();
        }}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Prompt" htmlFor="edit-schedule-prompt">
            <Combobox
              id="edit-schedule-prompt"
              options={promptOptions}
              value={promptName}
              onChange={(next) => {
                setPromptName(next);
                setVersionId(null);
              }}
              placeholder="Prompt…"
              searchPlaceholder="Search prompts…"
            />
          </Field>
          <Field label="Version" htmlFor="edit-schedule-version">
            <Combobox
              id="edit-schedule-version"
              options={versionOptions}
              value={versionId}
              onChange={setVersionId}
              placeholder="Version…"
              searchPlaceholder="Search versions…"
              disabled={promptName == null}
            />
          </Field>
        </div>
        <Field
          label="Scheduled at"
          hint="KST (Asia/Seoul) and the first hospital's local time stay in sync."
        >
          <DualTzInput
            value={scheduledAt}
            onChange={setScheduledAt}
            hospitalTimezone={hospitalTimezone}
            min={new Date().toISOString()}
            required
          />
        </Field>
        {timeError && <p className="text-sm text-destructive">{timeError}</p>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Voice" htmlFor="edit-schedule-voice">
            <Combobox
              id="edit-schedule-voice"
              options={VOICE_OPTIONS}
              value={voice}
              onChange={(next) => setVoice(next ?? "random")}
              placeholder="Voice…"
              searchPlaceholder="Search voices…"
            />
          </Field>
          <Field label="Model" htmlFor="edit-schedule-model">
            <Combobox
              id="edit-schedule-model"
              options={MODEL_OPTIONS}
              value={model}
              onChange={(next) => setModel(next ?? "base")}
              placeholder="Model…"
              searchPlaceholder="Search models…"
            />
          </Field>
        </div>
        <Field label="Memo" htmlFor="edit-schedule-memo">
          <input
            id="edit-schedule-memo"
            className={FIELD_CLASS}
            placeholder="Optional note for this schedule"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={update.isPending || !versionId}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {update.error && (
          <p className="text-sm text-destructive">
            {(update.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
