"use client";

import { useQuery } from "@tanstack/react-query";

import { DualTzInput } from "@/components/dual-tz-input";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { Field } from "@/components/ui/field";
import {
  promptsApi,
  SCHEDULE_MODELS,
  SCHEDULE_VOICES,
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

// Everything a schedule needs except the hospital selection. Held by the
// parent so both `NewScheduleForm` and the hospitals-page modal can drive it;
// the parent maps this into the `create` input.
export type ScheduleBatchValue = {
  promptName: string | null;
  versionId: string | null;
  scheduledAt: string;
  memo: string;
  voice: string;
  model: string;
};

export function emptyScheduleBatchValue(): ScheduleBatchValue {
  return {
    promptName: null,
    versionId: null,
    // Default: now + 5 minutes (gives time to fill the form before dispatch).
    scheduledAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    memo: "",
    voice: "random",
    model: "base",
  };
}

type Props = {
  value: ScheduleBatchValue;
  onChange: (next: ScheduleBatchValue) => void;
  /** IANA tz of the first selected hospital — drives the local-time input. */
  hospitalTimezone: string | null;
  /** Surface a scheduled-time validation error under the time picker. */
  timeError?: string | null;
};

/**
 * Shared schedule input fields: prompt/version comboboxes, the dual-tz time
 * picker, voice/model selectors and a memo line. Extracted so the
 * Schedules-page form and the Hospitals-page "create schedule" modal share one
 * implementation — only the hospital-selection UX differs between them.
 */
export function ScheduleBatchFields({
  value,
  onChange,
  hospitalTimezone,
  timeError,
}: Props) {
  const prompts = useQuery({ queryKey: ["prompts"], queryFn: promptsApi.list });
  const versions = useQuery({
    queryKey: ["prompt", value.promptName],
    queryFn: () => promptsApi.versions(value.promptName as string),
    enabled: value.promptName != null,
  });

  const promptOptions: ComboboxOption[] = (prompts.data ?? []).map((p) => ({
    value: p.name,
    label: p.name,
  }));
  const versionOptions: ComboboxOption[] = (versions.data ?? []).map((v) => ({
    value: String(v.id),
    label: `v${v.version}`,
  }));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Prompt" htmlFor="schedule-prompt">
          <Combobox
            id="schedule-prompt"
            options={promptOptions}
            value={value.promptName}
            onChange={(next) =>
              onChange({ ...value, promptName: next, versionId: null })
            }
            placeholder="Prompt…"
            searchPlaceholder="Search prompts…"
          />
        </Field>
        <Field label="Version" htmlFor="schedule-version">
          <Combobox
            id="schedule-version"
            options={versionOptions}
            value={value.versionId}
            onChange={(next) => onChange({ ...value, versionId: next })}
            placeholder="Version…"
            searchPlaceholder="Search versions…"
            disabled={value.promptName == null}
          />
        </Field>
      </div>
      <Field
        label="Scheduled at"
        hint="KST (Asia/Seoul) and hospital local time stay in sync — the first hospital's timezone drives the local clock."
      >
        <DualTzInput
          value={value.scheduledAt}
          onChange={(next) => onChange({ ...value, scheduledAt: next })}
          hospitalTimezone={hospitalTimezone}
          min={new Date().toISOString()}
          required
        />
      </Field>
      {timeError && <p className="text-sm text-destructive">{timeError}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Voice" htmlFor="schedule-voice">
          <Combobox
            id="schedule-voice"
            options={VOICE_OPTIONS}
            value={value.voice}
            onChange={(next) => onChange({ ...value, voice: next ?? "random" })}
            placeholder="Voice…"
            searchPlaceholder="Search voices…"
          />
        </Field>
        <Field label="Model" htmlFor="schedule-model">
          <Combobox
            id="schedule-model"
            options={MODEL_OPTIONS}
            value={value.model}
            onChange={(next) => onChange({ ...value, model: next ?? "base" })}
            placeholder="Model…"
            searchPlaceholder="Search models…"
          />
        </Field>
      </div>
      <Field label="Memo" htmlFor="schedule-memo">
        <input
          id="schedule-memo"
          className={FIELD_CLASS}
          placeholder="Optional note for this schedule"
          value={value.memo}
          onChange={(e) => onChange({ ...value, memo: e.target.value })}
        />
      </Field>
    </div>
  );
}
