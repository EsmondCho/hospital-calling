# `/backoffice/sourcing/`

Drives the hospital sourcing pipeline (DRT-5204 §2). All verbs except
`GET` require the `X-Backoffice-Token` header.

## `POST /backoffice/sourcing/jobs/`

Trigger a new sourcing job for a US city. The operator supplies only the
target region as text; the server resolves the city viewport and
recursively tiles it (DRT-5265).

**Request**

```json
{
  "state_code": "CA",
  "city": "Los Angeles",
  "max_depth": 6,
  "call_limit": 300
}
```

| Field | Type | Constraints |
|---|---|---|
| `state_code` | string | required, `^[A-Z]{2}$` |
| `city` | string | required, 2–128 chars |
| `max_depth` | int | optional, 1–8, default `SOURCING_MAX_DEPTH` (6) — recursion depth cap |
| `call_limit` | int | optional, 1–600, default `SOURCING_CALL_LIMIT` (300) — per-job Google call cap |

**Responses**

- `201 Created` — `SourcingJob` Lv2 representation.
- `400 Bad Request` — validation error (missing `state_code`, `max_depth` / `call_limit` out of range, etc.).
- `403 Forbidden` — missing / invalid `X-Backoffice-Token`.
- `409 Conflict` — `{"detail": "Sourcing job already running for CA/Los Angeles", "code": "sourcing_already_running"}` when an active job exists for the same `(state_code, city)`. Wait for it to finish or cancel it before re-triggering.

## `GET /backoffice/sourcing/jobs/`

List recent sourcing jobs (cursor-paginated, newest first).

**Response item (Lv1)**

`id`, `created_at`, `state_code`, `city`, `status`, partial metadata
(`partial` / `partial_reason`), tile progress (`total_tiles` /
`completed_tiles` / `capped_tile_count` / `failed_tile_count`),
counters (`fetched_count` / `inserted_count` / `updated_count` /
`skipped_count` / `excluded_count` / `needs_review_count` /
`error_count`), `actual_cost_usd`.

`partial=true` means the job reached `COMPLETED` but some data is
missing. `partial_reason` is one of `call_limit` (per-job call cap
reached), `min_size_residual` (a minimum-size tile still hit the result
cap — potential miss), or `tile_failures` (≥1 tile failed after retries).

## `GET /backoffice/sourcing/jobs/<id>/`

Job detail.

**Response (Lv2)** — Lv1 plus `triggered_by`, `started_at`,
`completed_at`, `error_message`, `call_count`, `max_depth`, `call_limit`,
the resolved root viewport (`root_south` / `root_west` / `root_north` /
`root_east`), `llm_input_tokens`, `llm_output_tokens`.

`404 Not Found` if the id doesn't exist.

## `POST /backoffice/sourcing/jobs/<id>/cancel/`

Flip a non-terminal job to `CANCELLED`. The next Celery step in the
chain re-reads `status` on entry and exits cleanly. Idempotent: cancel
on an already-terminal job is a no-op (returns the unchanged row).

- `200 OK` — Lv2 representation with `status=CANCELLED`.
- `403 Forbidden` — missing / invalid token.
- `404 Not Found` — unknown id.

## `GET /backoffice/sourcing/jobs/<id>/events/`

Server-Sent Events stream. Polls the DB every 2 seconds and emits the
current Lv2 representation whenever any field changed since the last
poll; closes with `event: done` on terminal status.

Requires `Accept: text/event-stream` (browser `EventSource` sends this
automatically). Other `Accept` values get `406 Not Acceptable`.

**Frames**

- `data: <Lv2 JSON>` — incremental progress.
- `event: done\ndata: {}` — job reached `COMPLETED` / `FAILED` / `CANCELLED`.
- `event: timeout\ndata: {}` — connection hit the 30-minute lifetime cap.
- `event: error\ndata: {"error": "job_missing"}` — row deleted mid-stream.

**Operational note**

Each open SSE connection occupies one Gunicorn sync worker for up to
30 minutes. Operators rarely keep dozens of streams open simultaneously,
but provision `GUNICORN_WORKERS` ≥ `(expected concurrent operators) +
(REST headroom)` to avoid REST endpoints starving. The browser's
`EventSource` reconnects automatically after the 30-minute cap, so
nothing is lost; the worker is reclaimed.

`404 Not Found` (before stream opens) if the id doesn't exist.

## `GET /backoffice/sourcing/states/`

States that have at least one non-deleted `Hospital`, each with its
hospital count — drives the sourcing form's state dropdown. Open to
`GET` (no token). Unpaginated; a plain array.

**Response** — `200 OK`, sorted by `state_code`. States with zero
hospitals are omitted.

```json
[
  {"state_code": "CA", "hospital_count": 1204},
  {"state_code": "TX", "hospital_count": 88}
]
```

## `GET /backoffice/sourcing/cities/?state=CA`

Every `City` in a state (from the preloaded `city` reference table),
annotated for the sourcing form's city dropdown. Open to `GET` (no
token). Unpaginated; a plain array.

| Param | Type | Constraints |
|---|---|---|
| `state` | string | required, `^[A-Z]{2}$` |

**Response** — `200 OK`, sorted by `name` (abc).

```json
[
  {"name": "Acalanes Ridge", "hospital_count": 0, "sourced": false},
  {"name": "Los Angeles", "hospital_count": 56, "sourced": true}
]
```

- `hospital_count` — non-deleted `Hospital` rows with `state=<state>`
  and `city` matching `name` case-insensitively.
- `sourced` — `true` if a `COMPLETED` `SourcingJob` exists with
  `state_code=<state>` and `city` matching `name` case-insensitively.
  Failed / cancelled / in-flight jobs don't count.

`400 Bad Request` when `state` is missing or malformed:

```json
{"detail": "Query param `state` is required and must be a 2-letter uppercase code."}
```
