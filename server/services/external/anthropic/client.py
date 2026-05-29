"""Anthropic SDK client wrapper (DRT-5204 §2.3).

Thin `get_client()` wrapper around the official `anthropic` SDK. The
classifier in PR 3 calls `client.messages.create(...)` directly with the
SDK's typed surface.

`settings.ANTHROPIC_API_KEY` is loaded from SSM `/hospcall/ANTHROPIC_API_KEY`
in prod — the app key, distinct from the GitHub Actions repo secret of
the same name that the `claude-review` CI uses (separate systems).

Note: Python 3 uses absolute imports, so `import anthropic` here resolves
to the installed SDK package, not the local `services.external.anthropic`
submodule.
"""

from __future__ import annotations

import anthropic
import structlog
from django.conf import settings

from utils.cache_utils import function_cache

logger = structlog.get_logger(__name__)


@function_cache(minutes=60)
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        base_url=settings.ANTHROPIC_BASE_URL,
        timeout=60.0,
        max_retries=3,
    )
