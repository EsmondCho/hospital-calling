# Testing Conventions

## Layout

```
tests/
├── unit/                # pure-function tests, no DB
├── integration/         # touches DB / Celery
└── factories.py         # factory_boy factories per model
```

## Run

```
make test                      # full suite
make test tests/integration/   # one path
```

`pytest-django` is configured; use the `db` fixture (or the `transactional_db`
variant) for DB tests.

## Don't mock the boundary you're testing

When testing `services/internal/hospcall_calling/service.py`, mock `BlandAIClient`
at the module level — don't mock the underlying `httpx` calls inside it. The
goal is to verify our orchestration, not BlandAI's.

For tests that *do* exercise BlandAI's wire format, hit a recorded VCR cassette
or a stub server, not the live API.

## DB isolation

Tests use `env=test` which points at the `hospcall_test` database. Each test
function gets a fresh transaction (rolled back at the end) so order doesn't
matter.
