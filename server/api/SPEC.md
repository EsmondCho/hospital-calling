# API

| Tree | Mount | Purpose |
|------|-------|---------|
| `backoffice/` | `/backoffice/` | Operator-facing CRUD (consumed by `hospcall-backoffice`) |
| `webhook/` | `/webhook/` | Inbound from external providers (BlandAI today) |

There is no public/mobile API in HOSPCALL.

Per `docs/conventions/api-layer.md`, the SPEC tree mirrors the URL tree:
- This file — overview.
- `backoffice/SPEC.md` — endpoint table across all resources.
- `backoffice/<resource>/SPEC.md` — request/response per endpoint.

## Webhook tree

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/webhook/blandai/call_status/` | POST | BlandAI call lifecycle callback |
