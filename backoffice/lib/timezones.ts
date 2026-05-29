// Hospital ownership axis. Mirrors `hospital.vars.HospitalOwnership` on
// the server. Call targeting dials only INDEPENDENT hospitals.
export const HOSPITAL_OWNERSHIPS = [
  "INDEPENDENT",
  "CHAIN",
  "MARS_VH",
  "RETAIL_EMBEDDED",
  "NONPROFIT",
  "UNIVERSITY",
  "FRANCHISE",
  "UNCLASSIFIED",
] as const;

export type HospitalOwnership = (typeof HOSPITAL_OWNERSHIPS)[number];

// Show a dash for nullish / empty values in list and detail views.
export function valueOrDash<T>(v: T | null | undefined): T | "—" {
  if (v == null) return "—";
  if (typeof v === "string" && v.trim() === "") return "—";
  return v;
}

// Timezones offered as the hospital local TZ. Restricted to the operator's
// home zone (Asia/Seoul) plus the US zones the HOSPCALL calling pipeline targets.
export const ALLOWED_TIMEZONES = [
  "Asia/Seoul",
  "America/New_York", // ET
  "America/Chicago", // CT
  "America/Denver", // MT
  "America/Phoenix", // MST (no DST)
  "America/Los_Angeles", // PT
  "America/Anchorage", // AKT
  "Pacific/Honolulu", // HST
] as const;

export type AllowedTimezone = (typeof ALLOWED_TIMEZONES)[number];

export const KST = "Asia/Seoul";

export function formatInTimezone(
  isoString: string | null | undefined,
  timezone: string
): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return isoString;
  }
}

// Convert an ISO UTC string to the `YYYY-MM-DDTHH:mm` form `<input type="datetime-local">`
// expects, but in `timezone` rather than the browser's local zone.
export function isoToLocalInputValue(
  isoString: string,
  timezone: string
): string {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

// Inverse: a `YYYY-MM-DDTHH:mm` value entered as wall-clock time *in*
// `timezone` is converted back to the absolute UTC ISO string.
// Implemented by binary search using formatInTimezone — avoids pulling in
// a TZ library for one form.
export function localInputValueToIso(
  inputValue: string,
  timezone: string
): string {
  if (!inputValue) return "";
  // Treat the input as UTC first, then offset by the difference between the
  // browser's local interpretation and the target zone.
  const probe = new Date(`${inputValue}:00Z`);
  if (Number.isNaN(probe.getTime())) return "";

  const wallInTz = isoToLocalInputValue(probe.toISOString(), timezone);
  const wallTarget = inputValue;
  // wallInTz tells us what the timezone reads when the absolute moment is
  // probe. The delta between that and the desired wall clock is the offset
  // we need to subtract.
  const deltaMinutes = wallClockMinutes(wallTarget) - wallClockMinutes(wallInTz);
  const adjusted = new Date(probe.getTime() + deltaMinutes * 60_000);
  return adjusted.toISOString();
}

function wallClockMinutes(value: string): number {
  // value: 'YYYY-MM-DDTHH:mm'
  const [datePart, timePart] = value.split("T");
  if (!datePart || !timePart) return 0;
  const [y, mo, d] = datePart.split("-").map(Number);
  const [h, m] = timePart.split(":").map(Number);
  return Date.UTC(y, mo - 1, d, h, m) / 60_000;
}
