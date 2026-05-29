# External Services Conventions

## SDK first, then httpx

If a vendor ships an official Python SDK, use it. Fall back to `httpx`
otherwise. Don't mix `requests` into this codebase.

- BlandAI — no official Python SDK; we use `httpx`
  (`services/external/blandai/client.py`)
- Google Places — `httpx` (stub today)
- AWS — `boto3`

## Single client per service

One `client.py` per service module. Wrap construction in a `get_client()` so
callers don't instantiate directly. Cache it with `@function_cache(minutes=N)`
from `utils/cache_utils.py` so tests can swap implementations.

## Module independence

External service modules must not import each other. The import-linter contract
in `pyproject.toml` enforces this.

## Schemas

For typed request/response shapes, use Pydantic `BaseModel` only at the API
boundary (request build / response parse). Don't leak Pydantic models into
the rest of the codebase — convert to plain dataclasses or pass primitive
attributes through.
