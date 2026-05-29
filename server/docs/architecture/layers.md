# Architecture Layers & Dependency Rules

## 4-Layer Architecture

```
Views (api/backoffice/*/views.py, api/webhook/*/views.py)
  ↓
Serializers (api/backoffice/*/serializers.py)
  ↓
Services (services/internal/*, services/external/*)
  ↓
Models (*/models.py) + Vars (*/vars.py)
  ↓
Utils (utils/)
```

**Tasks** are usecase-layer:
- `calling/tasks.py` — public Celery entry points
- Service-internal tasks live in `services/internal/<scope>/tasks.py`

## Dependency direction

**Allowed:**
```
views → serializers → services
tasks → services
all layers → models, vars, utils
```

**Forbidden (CI-enforced via import-linter):**
- `services` import from `api`
- Model modules (`hospital`, `prompt`, `calling`) import from `api` or `services`
  - Exception: `*/tasks.py` may import services (tasks are usecase-layer)
- `utils` import from app code
- External service modules import each other
  (`services.external.blandai` ⊥ `services.external.google_places` ⊥ `services.external.ssm`)

## Maintaining import-linter

When adding a new domain module or external service, update
`pyproject.toml` `[tool.importlinter]` accordingly. Run `uv run lint-imports`
locally to verify.

## Escalation triggers

Files in these areas are higher-blast-radius and warrant a closer look:

| Area | Pattern |
|------|---------|
| DB schema | `**/models.py`, `**/migrations/**` |
| External clients | `services/external/*/client.py` |
| Settings | `hospcall/settings/**` |
| Infra | `infrastructure/**` |
| Deps | `pyproject.toml` |
| CI/CD | `.github/workflows/**` |
