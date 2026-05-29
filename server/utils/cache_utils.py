"""Caching helpers used by external service clients.

`function_cache` mirrors `functools.cache` but is a no-op in test/local-dev so
mocks can replace clients freely. Default behavior caches indefinitely; pass
`minutes=N` for time-bounded caches (matching mochii-server's API).
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec('P')
R = TypeVar('R')

_BYPASS_ENVS = {'test'}


def function_cache(
    minutes: int | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        if os.environ.get('ENV', '') in _BYPASS_ENVS:
            return fn

        cache: dict[tuple[Any, ...], tuple[float, R]] = {}
        ttl_seconds = minutes * 60 if minutes else None

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            cached = cache.get(key)
            if cached is not None and (ttl_seconds is None or now - cached[0] < ttl_seconds):
                return cached[1]
            value = fn(*args, **kwargs)
            cache[key] = (now, value)
            return value

        return wrapper

    return decorator
