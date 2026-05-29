import { API_BASE_URL } from "@/lib/config";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const payload = await res.json();
      detail = payload?.error?.message ?? payload?.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// Mutating calls go through the Next.js API route at /api/proxy/* so the
// X-Backoffice-Token header (set from a server-side env var) never appears in
// the browser bundle.
export async function apiMutate<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const proxyPath = path.startsWith("/") ? path.slice(1) : path;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`/api/proxy/${proxyPath}`, { ...init, headers });
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const payload = await res.json();
      detail = payload?.error?.message ?? payload?.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ── Offset/page-number DRF response shape ──────────────────────────────────
// The server uses PageNumberPagination: `count` is the total row count across
// all pages (used to compute the page count), `next`/`previous` are absolute
// URLs (kept for completeness — navigation is by `?page=N`).
export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

// Back-compat alias — older imports referenced `CursorPage`. It now carries
// `count` like every other paged response.
export type CursorPage<T> = Page<T>;

// ── Resource shapes (mirror hospcall-server serializers) ───────────────────────
export type Hospital = {
  id: number;
  name: string;
  // 3-axis classification (DRT-5204 §1).
  ownership: string;
  service_tags: string[];
  specialty_areas: string[];
  appointment_mode: string;
  label_locked: boolean;
  phone_e164: string | null;
  city: string | null;
  state: string | null;
  timezone?: string | null;
  created_at: string;
  // Lv2 only
  source?: string;
  source_external_id?: string | null;
  website?: string | null;
  formatted_address?: string | null;
  postal_code?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  excluded_reason?: string | null;
  metadata?: Record<string, unknown>;
  reviewed_at?: string | null;
  reviewed_by?: number | null;
  updated_at?: string;
  // Number of call attempts made to this hospital — surfaced so operators
  // avoid over-calling and making hospitals defensive.
  call_attempt_count?: number;
};

export type SourcingPartialReason =
  | "call_limit"
  | "min_size_residual"
  | "tile_failures";

export type SourcingJob = {
  id: number;
  created_at: string;
  state_code: string;
  city: string | null;
  status: string;
  // Partial metadata — `partial=true` means the job reached COMPLETED but
  // some data is missing (DRT-5265).
  partial: boolean;
  partial_reason: SourcingPartialReason | null;
  // Tile progress
  total_tiles: number;
  completed_tiles: number;
  capped_tile_count: number;
  failed_tile_count: number;
  fetched_count: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  excluded_count: number;
  needs_review_count: number;
  error_count: number;
  actual_cost_usd: string;
  // Lv2 only
  triggered_by?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  call_count?: number;
  max_depth?: number;
  call_limit?: number;
  root_south?: string | null;
  root_west?: string | null;
  root_north?: string | null;
  root_east?: string | null;
  llm_input_tokens?: number;
  llm_output_tokens?: number;
};

// Per-state hospital tally for the sourcing-job state picker. The endpoint
// only returns states with ≥1 hospital — any state absent from the array
// is treated as count 0.
export type SourcingStateStat = {
  state_code: string;
  hospital_count: number;
};

// A city option for the sourcing-job city picker. The endpoint returns ALL
// cities in the state, already abc-sorted by `name`.
// `hospital_count` = hospitals we have stored for that city.
// `sourced` = whether a sourcing job has ever run for that city.
export type SourcingCityOption = {
  name: string;
  hospital_count: number;
  sourced: boolean;
};

export type Prompt = {
  id: number;
  name: string;
  version: number;
  updated_at: string;
  // Lv2 only
  body?: string;
  notes?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

// One row per logical prompt (grouped by `name`) for the prompts list.
// Returned unpaginated by `GET /backoffice/prompts/`.
export type PromptListEntry = {
  name: string;
  version_count: number;
  latest_version: number;
  updated_at: string;
};

// One hospital a schedule dials, in order. A single CallSchedule targets many
// hospitals and dials them sequentially (ordered by `order`).
export type CallScheduleTarget = {
  hospital_id: number | null;
  hospital_name: string | null;
  hospital_timezone: string | null;
  order: number;
  status: "PENDING" | "DIALING" | "DONE" | "SKIPPED";
  call_attempt_id?: number | null;
};

export type CallSchedule = {
  id: number;
  status: string;
  scheduled_at: string;
  memo: string | null;
  voice: string;
  model: string;
  prompt_id: number | null;
  prompt_name: string | null;
  prompt_version: number | null;
  // How many hospitals this schedule dials.
  hospital_count: number;
  // Ordered dial targets (by `order`). Empty on a freshly created schedule
  // only if the server hasn't materialized them yet.
  targets: CallScheduleTarget[];
  created_at: string;
  // Detail only
  metadata?: Record<string, unknown>;
  updated_at?: string;
};

export type CallAttempt = {
  id: number;
  status: string;
  answered_by: string | null;
  duration_seconds: number | null;
  started_at: string | null;
  ended_at: string | null;
  failure_reason: string | null;
  hospital_id: number | null;
  hospital_name: string | null;
  prompt_id: number | null;
  prompt_name: string | null;
  prompt_version: number | null;
  blandai_call_id: string | null;
  recording_url: string | null;
  // Voice / model actually used for the call. Empty string for attempts
  // that failed before dialing. Returned by both list and detail endpoints.
  voice: string;
  model: string;
  // Operator-toggled star. Returned by both list and detail endpoints.
  is_starred: boolean;
  // Number of operator comments on this attempt. Returned on list rows so the
  // call list can surface it without a per-row fetch.
  comment_count: number;
  created_at: string;
  // Lv2 only
  call_ended_by?: string | null;
  summary?: string | null;
  transcript?: Array<{ user: string; text: string }>;
  metadata?: Record<string, unknown>;
  schedule_id?: number | null;
  updated_at?: string;
};

// A free-text operator comment on a call attempt. Returned newest-first and
// unpaginated by `GET /backoffice/calls/<id>/comments/`. `author` is the
// operator (X-Backoffice-User) the server attributed the comment to.
export type CallComment = {
  id: number;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
};

// ── Fetchers ───────────────────────────────────────────────────────────────
const list = <T>(resource: string, query: Record<string, string> = {}) => {
  const qs = new URLSearchParams(query).toString();
  return apiFetch<Page<T>>(
    `/backoffice/${resource}/${qs ? `?${qs}` : ""}`
  );
};

const detail = <T>(resource: string, id: number | string) =>
  apiFetch<T>(`/backoffice/${resource}/${id}/`);

const patch = <T>(resource: string, id: number | string, body: unknown) =>
  apiMutate<T>(`backoffice/${resource}/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

const destroy = (resource: string, id: number | string) =>
  apiMutate<void>(`backoffice/${resource}/${id}/`, { method: "DELETE" });

const create = <T>(resource: string, body: unknown) =>
  apiMutate<T>(`backoffice/${resource}/`, {
    method: "POST",
    body: JSON.stringify(body),
  });

const bulkDelete = (resource: string, ids: Array<number>) =>
  apiMutate<{ deleted_count: number }>(
    `backoffice/${resource}/bulk_delete/`,
    {
      method: "POST",
      body: JSON.stringify({ ids }),
    }
  );

// ── Input shapes ───────────────────────────────────────────────────────────
export type NewHospital = {
  name: string;
  phone_e164?: string | null;
  website?: string | null;
  formatted_address?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  timezone?: string | null;
  ownership?: string;
};

export type HospitalUpdate = Partial<NewHospital>;

// Schedule creation. `hospitals` array order IS the dial order — the backend
// sends one call per hospital sequentially in this order.
export type NewSchedule = {
  hospitals: number[];
  prompt: number;
  scheduled_at: string;
  memo?: string | null;
  voice?: string;
  model?: string;
};

// PATCH never edits the hospital list — only timing/content fields.
export type ScheduleUpdate = {
  prompt?: number;
  scheduled_at?: string;
  memo?: string | null;
  voice?: string;
  model?: string;
};

// Mirrors `calling/vars.py` (VOICE_CHOICES) on the server. "random" is a
// sentinel — the server resolves it to a pooled voice per call.
export const SCHEDULE_VOICES = [
  "random", "ryan", "david", "mason", "Nat", "June", "adriana", "maya",
] as const;
// Mirrors `CallModel` on the server.
export const SCHEDULE_MODELS = ["base", "turbo"] as const;

export type NewSourcingJob = {
  state_code: string;
  city: string;
  max_depth?: number;
  call_limit?: number;
};

export type NewPrompt = {
  name: string;
  body: string;
  notes?: string | null;
  // version is optional — server auto-bumps when omitted.
  version?: number;
};

// Filters/paging for the hospitals list. `page` is the 1-based page number
// (PageNumberPagination, page_size 20).
export type HospitalListParams = {
  q?: string;
  ownership?: string;
  page?: number;
};

// ── Resource APIs ──────────────────────────────────────────────────────────
export const hospitalsApi = {
  list: (params: HospitalListParams = {}) => {
    const query: Record<string, string> = {};
    if (params.q) query.q = params.q;
    if (params.ownership) query.ownership = params.ownership;
    if (params.page && params.page > 1) query.page = String(params.page);
    return list<Hospital>("hospitals", query);
  },
  get: (id: number | string) => detail<Hospital>("hospitals", id),
  create: (input: NewHospital) => create<Hospital>("hospitals", input),
  update: (id: number | string, input: HospitalUpdate) =>
    patch<Hospital>("hospitals", id, input),
  remove: (id: number | string) => destroy("hospitals", id),
  bulkRemove: (ids: Array<number>) => bulkDelete("hospitals", ids),
};

export const promptsApi = {
  // Unpaginated: one entry per logical prompt name.
  list: () => apiFetch<PromptListEntry[]>("/backoffice/prompts/"),
  // Unpaginated: all version rows for a prompt name, newest first.
  // `name` is a query parameter (not a path segment) so free-form names
  // with spaces or non-ASCII characters need no special routing.
  versions: (name: string) =>
    apiFetch<Prompt[]>(
      `/backoffice/prompts/versions/?name=${encodeURIComponent(name)}`
    ),
  get: (id: number | string) => detail<Prompt>("prompts", id),
  create: (input: NewPrompt) => create<Prompt>("prompts", input),
};

export const schedulesApi = {
  list: (params: { page?: number } = {}) => {
    const query: Record<string, string> = {};
    if (params.page && params.page > 1) query.page = String(params.page);
    return list<CallSchedule>("schedules", query);
  },
  get: (id: number | string) => detail<CallSchedule>("schedules", id),
  create: (input: NewSchedule) => create<CallSchedule>("schedules", input),
  update: (id: number | string, input: ScheduleUpdate) =>
    patch<CallSchedule>("schedules", id, input),
  remove: (id: number | string) => destroy("schedules", id),
  bulkRemove: (ids: Array<number>) => bulkDelete("schedules", ids),
};

export const sourcingApi = {
  list: (params: { page?: number } = {}) => {
    const query: Record<string, string> = {};
    if (params.page && params.page > 1) query.page = String(params.page);
    return list<SourcingJob>("sourcing/jobs", query);
  },
  get: (id: number | string) => detail<SourcingJob>("sourcing/jobs", id),
  create: (input: NewSourcingJob) =>
    apiMutate<SourcingJob>(`backoffice/sourcing/jobs/`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  cancel: (id: number | string) =>
    apiMutate<SourcingJob>(`backoffice/sourcing/jobs/${id}/cancel/`, {
      method: "POST",
    }),
  states: () =>
    apiFetch<SourcingStateStat[]>(`/backoffice/sourcing/states/`),
  cities: (state: string) =>
    apiFetch<SourcingCityOption[]>(
      `/backoffice/sourcing/cities/?state=${encodeURIComponent(state)}`
    ),
};

export const callsApi = {
  list: (
    filters: {
      page?: number;
      scheduleId?: number | string;
      hospitalId?: number | string;
      starred?: boolean;
    } = {}
  ) => {
    const query: Record<string, string> = {};
    if (filters.page && filters.page > 1) query.page = String(filters.page);
    if (filters.scheduleId != null)
      query.schedule = String(filters.scheduleId);
    if (filters.hospitalId != null)
      query.hospital = String(filters.hospitalId);
    if (filters.starred) query.starred = "true";
    return list<CallAttempt>("calls", query);
  },
  get: (id: number | string) => detail<CallAttempt>("calls", id),
  remove: (id: number | string) => destroy("calls", id),
  bulkRemove: (ids: Array<number>) => bulkDelete("calls", ids),
  // Toggle the star flag (mutation → proxy attaches the token). The server's
  // star endpoint returns only {id, is_starred} — callers invalidate rather
  // than read the body, but type it honestly.
  setStar: (id: number | string, is_starred: boolean) =>
    patch<Pick<CallAttempt, "id" | "is_starred">>("calls", id, { is_starred }),
  // Comments — list is a plain read; add/delete are mutations.
  comments: (id: number | string) =>
    apiFetch<CallComment[]>(`/backoffice/calls/${id}/comments/`),
  addComment: (id: number | string, body: string) =>
    apiMutate<CallComment>(`backoffice/calls/${id}/comments/`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  updateComment: (
    callId: number | string,
    commentId: number | string,
    body: string
  ) =>
    apiMutate<CallComment>(
      `backoffice/calls/${callId}/comments/${commentId}/`,
      {
        method: "PATCH",
        body: JSON.stringify({ body }),
      }
    ),
  deleteComment: (callId: number | string, commentId: number | string) =>
    apiMutate<void>(`backoffice/calls/${callId}/comments/${commentId}/`, {
      method: "DELETE",
    }),
  // Freshly-presigned S3 recording url (or null if no recording exists).
  recording: (id: number | string) =>
    apiFetch<{ url: string | null }>(`/backoffice/calls/${id}/recording/`),
};

// ── Chain keywords (sourcing rule-pass table — read-only) ──────────────────
export type ChainKeyword = {
  id: number;
  match_priority: number;
  chain_brand_normalized: string;
  display_name: string;
  ownership: string;
  service_tags: string[];
  regex_pattern: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export const chainKeywordsApi = {
  // Read-only and unpaginated (~20 rows). Rows are managed via the
  // hospcall-server Django admin console, not the backoffice.
  list: () => apiFetch<ChainKeyword[]>("/backoffice/chain_keywords/"),
};

// ── Current operator ───────────────────────────────────────────────────────
// Hits the same-origin Next route `/api/me` (NOT the Django base URL), so it
// uses a plain fetch instead of `apiFetch` (which prepends API_BASE_URL). The
// route reads the `x-backoffice-user` header middleware injects.
export const meApi = {
  get: (): Promise<{ user: string | null }> =>
    fetch("/api/me").then((r) => r.json()),
};
