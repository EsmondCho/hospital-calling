# Backoffice API

Token-gated under `X-Backoffice-Token` for every non-`SAFE_METHODS` verb
(see `permissions.py`). GETs stay open behind the Vercel basic-auth wall.
The proxy also forwards the authenticated user as `X-Backoffice-User`
(`esmond` / `rayer`) — used to attribute call-log comments and gate
edit/delete to the author.

List endpoints use page-number pagination: `?page=N`, 20/page, response
`{count, next, previous, results}`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/backoffice/hospitals/` | GET, POST | list / create hospitals (`?q=` name and `?ownership=` filters supported); each row carries `call_attempt_count` |
| `/backoffice/hospitals/<id>/` | GET, PATCH, PUT, DELETE | hospital detail (soft delete); response carries `call_attempt_count` |
| `/backoffice/hospitals/bulk_delete/` | POST | bulk soft-delete |
| `/backoffice/prompts/` | GET, POST | list logical prompts (one row per `name`, aggregated, unpaginated) / create a version (auto-bumps `version`) |
| `/backoffice/prompts/<name>/versions/` | GET | all non-deleted versions of one logical prompt (`-version` order, includes `body`, unpaginated) |
| `/backoffice/prompts/<id>/` | GET, PATCH, PUT, DELETE | single version-row detail (soft delete) |
| `/backoffice/prompts/bulk_delete/` | POST | bulk soft-delete |
| `/backoffice/schedules/` | GET, POST | list / create call schedules. POST takes `hospitals: [id,...]` (ordered) — one schedule fans out to many hospitals dialed **sequentially**; auto-enqueues dispatch |
| `/backoffice/schedules/<id>/` | GET, PATCH, PUT, DELETE | schedule detail (`targets[]` = ordered hospital steps with per-step status; soft delete, re-enqueue on update) |
| `/backoffice/schedules/bulk_delete/` | POST | bulk soft-delete |
| `/backoffice/calls/` | GET | list call attempts (`?schedule=<id>`, `?hospital=<id>`, `?starred=true` filters); each row carries `comment_count` |
| `/backoffice/calls/<id>/` | GET, PATCH, DELETE | call detail (with transcript); PATCH toggles `is_starred`; DELETE soft-deletes |
| `/backoffice/calls/<id>/recording/` | GET | playable recording URL (`{url}`; S3-presigned, falls back to BlandAI url) |
| `/backoffice/calls/<id>/comments/` | GET, POST | list (newest first, with `author`) / add a comment (author = `X-Backoffice-User`) |
| `/backoffice/calls/<call_id>/comments/<id>/` | PATCH, DELETE | edit / hard-delete a comment — author only (403 otherwise) |
| `/backoffice/calls/bulk_delete/` | POST | bulk soft-delete |
| `/backoffice/sourcing/jobs/` | GET, POST | list / trigger hospital sourcing jobs |
| `/backoffice/sourcing/jobs/<id>/` | GET | sourcing job detail (counters + cost) |
| `/backoffice/sourcing/jobs/<id>/cancel/` | POST | cancel a running sourcing job |
| `/backoffice/sourcing/jobs/<id>/events/` | GET | `text/event-stream` progress |
| `/backoffice/sourcing/states/` | GET | states with non-deleted hospital counts |
| `/backoffice/sourcing/cities/` | GET | cities in a state (`?state=CA`) with hospital count + sourced flag |
| `/backoffice/chain_keywords/` | GET | sourcing rule-pass chain table (read-only) |

For per-resource request/response details see `<resource>/SPEC.md`.
