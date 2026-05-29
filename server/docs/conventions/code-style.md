# Code Style Conventions

## Basics

- Ruff for formatting and linting. Early returns. Comments only when WHY is
  non-obvious.
- No `global` mutable state. Use `@functools.cache` (always-on) or
  `@function_cache(minutes=N)` (off in tests) from `utils/cache_utils.py`.
- Variable names spell out meaning. Don't use 1-letter or `tmp` / `data`.

## Logging

- `structlog` only. Keys in lowercase snake. Values are usually primitives.
- `logger.info()` and above. Don't ship `logger.debug()`.

```python
logger.info('hospcall_calling.dispatch.dispatched', count=count)
logger.error(
    'hospcall_calling.send_call.unexpected',
    call_attempt_id=attempt.id,
    error=str(e),
    exc_info=e,
)
```

## Types

- Type hints on every function signature.
- 3+ field dicts as function args → use a `@dataclass`. Pydantic only at
  external API boundary.
- `StrEnum` values are usable as strings — no need to `str()` wrap.

## Imports

- Order: stdlib, third-party, first-party (`api.*`, `services.*`, `calling.*`,
  etc.), local relative. Ruff `I` rule autoformats this.
- Avoid `from foo import *` outside `hospcall/settings/__init__.py`.

## mypy

- `uv run mypy .` is part of the verify loop. Local checks before PR.
- Type narrowing precedence: real fix > `cast(...)` > `# type: ignore[code]`
  with a specific code. Bare `# type: ignore` is rejected.
- Don't use `assert` for runtime narrowing — `python -O` strips it.
