# API Layer Conventions

> Layer dependency rules: see [`docs/architecture/layers.md`](../architecture/layers.md).

## Two API trees

- `api/backoffice/` — operator-facing CRUD. Consumed by `hospcall-backoffice`.
  All endpoints live under `/backoffice/<resource>/`.
- `api/webhook/` — inbound from external providers (BlandAI today).

There is no public-mobile API in HOSPCALL.

## Naming

- Serializers: `Lv1Serializer` (list rows), `Lv2Serializer` (detail).
- `Lv2Serializer` extends `Lv1Serializer` and uses `[*Lv1.Meta.fields, ...]` to
  add fields. Don't redeclare base fields.
- URL paths use snake_case (`/call_status/`), not kebab-case.

## Pagination

- Page-number via `BackofficePageNumberPagination`
  (`api/backoffice/pagination.py`): `?page=N`, 20/page, response
  `{count, next, previous, results}` — the backoffice renders numbered pages.
- Page-number pagination does **not** impose ordering, so every paginated
  view must `.order_by(...)` deterministically (e.g. `-created_at, -id`) or
  the page split is unstable.
- Use `GenericAPIView` / `ListAPIView` (CBV). Don't paginate from FBVs.

## Client-facing messages

- Response strings (`error.message`, validation failures) are **English**.
  This API is consumed by Esmond / Rayer; English keeps it consistent with
  drtail/mochii conventions and avoids surprises if we ever expose anything
  beyond the team.

## SPEC docs

API spec lives next to the code as `SPEC.md`:
- `api/SPEC.md` — overview + tree
- `api/backoffice/SPEC.md` — backoffice endpoint table
- `api/backoffice/<resource>/SPEC.md` — request/response per endpoint

Keep them in sync when adding/changing endpoints.
