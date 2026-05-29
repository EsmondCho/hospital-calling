"use client";

import { useEffect, useState } from "react";

import {
  KST,
  isoToLocalInputValue,
  localInputValueToIso,
} from "@/lib/timezones";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

type Props = {
  /** Absolute UTC ISO string. Source of truth. */
  value: string;
  /** Called with the new UTC ISO string whenever either input changes. */
  onChange: (isoUtc: string) => void;
  /** IANA tz name for the hospital local clock (e.g. America/Los_Angeles). */
  hospitalTimezone: string | null;
  required?: boolean;
  /** Earliest selectable moment, as an absolute UTC ISO string. The native
   *  picker greys out slots before this in each zone. */
  min?: string;
};

/**
 * Two `<input type="datetime-local">` fields side-by-side: KST and the
 * hospital's local time. Editing either one updates the absolute UTC value;
 * the sibling field is then re-derived from that UTC moment so the two
 * stay in sync.
 *
 * If `hospitalTimezone` is null/missing, only the KST input is shown — the
 * operator can still pick the call time, just without the hospital-local
 * preview.
 */
export function DualTzInput({
  value,
  onChange,
  hospitalTimezone,
  required,
  min,
}: Props) {
  const [kstInput, setKstInput] = useState("");
  const [localInput, setLocalInput] = useState("");

  const kstMin = min ? isoToLocalInputValue(min, KST) : undefined;
  const localMin =
    min && hospitalTimezone
      ? isoToLocalInputValue(min, hospitalTimezone)
      : undefined;

  useEffect(() => {
    setKstInput(value ? isoToLocalInputValue(value, KST) : "");
    setLocalInput(
      value && hospitalTimezone
        ? isoToLocalInputValue(value, hospitalTimezone)
        : ""
    );
  }, [value, hospitalTimezone]);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <label className="mb-1 block text-xs text-muted-foreground">
          KST (Asia/Seoul)
        </label>
        <input
          className={FIELD_CLASS}
          type="datetime-local"
          required={required}
          min={kstMin}
          value={kstInput}
          onChange={(e) => {
            setKstInput(e.target.value);
            const iso = localInputValueToIso(e.target.value, KST);
            if (iso) onChange(iso);
          }}
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-muted-foreground">
          {hospitalTimezone
            ? `Hospital local (${hospitalTimezone})`
            : "Hospital local"}
        </label>
        <input
          className={FIELD_CLASS}
          type="datetime-local"
          disabled={!hospitalTimezone}
          min={localMin}
          value={localInput}
          onChange={(e) => {
            if (!hospitalTimezone) return;
            setLocalInput(e.target.value);
            const iso = localInputValueToIso(e.target.value, hospitalTimezone);
            if (iso) onChange(iso);
          }}
        />
      </div>
    </div>
  );
}
