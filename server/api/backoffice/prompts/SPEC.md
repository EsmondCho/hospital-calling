# `/backoffice/prompts/`

BlandAI task prompts (`prompt.Prompt`). Each row is exactly one **version**.
A **logical prompt** is the set of all non-deleted rows sharing a `name`; the
row with the highest `version` is the latest. `(name, version)` is unique, so
publishing a new version means creating a new row — older rows stay in the DB
because `CallSchedule.prompt` / `CallAttempt.prompt` reference an exact
version.

## `GET /backoffice/prompts/`

One entry per logical prompt, aggregated over its versions. Ordered by the
most recently updated version first. Unpaginated (mirrors
`chain_keywords` — the table is small).

**Response** — plain array:

```json
[
  {
    "name": "referral-policy",
    "version_count": 2,
    "latest_version": 2,
    "updated_at": "2026-05-18T13:00:00Z"
  }
]
```

`version_count` — number of non-deleted versions.
`latest_version` — highest `version` among them.
`updated_at` — `max(updated_at)` across the versions.

## `POST /backoffice/prompts/`

Creates a new version. Token-gated (`X-Backoffice-Token`).

`version` is auto-assigned and should be omitted:
- new `name` → version 1
- existing `name` → `max(version) + 1`

**Request**:

```json
{
  "name": "referral-policy",
  "body": "You are calling a US local vet hospital ...",
  "notes": "v2 — tighter silence rule",
  "metadata": {}
}
```

**Response** — `201`, the created version row (`id`, `name`, `version`,
`body`, `notes`, `metadata`, `created_at`, `updated_at`).

## `GET /backoffice/prompts/versions/?name=<name>`

All non-deleted version rows for one logical prompt, `-version` order
(newest first). Includes `body`. Unpaginated.

`name` is a required query parameter (URL-encode it — names are free-form
and may contain spaces or non-ASCII characters). A missing `name` returns
`400`.

**Response** — plain array:

```json
[
  {
    "id": 12,
    "name": "referral-policy",
    "version": 2,
    "updated_at": "2026-05-18T13:00:00Z",
    "body": "...",
    "notes": "v2 — tighter silence rule",
    "metadata": {},
    "created_at": "2026-05-18T13:00:00Z"
  }
]
```

## `GET|PATCH|PUT|DELETE /backoffice/prompts/<id>/`

A single version row by primary key. `GET` returns the full row including
`body`. `PATCH`/`PUT` edit that version in place (token-gated). `DELETE`
soft-deletes it (`is_deleted=True`).
