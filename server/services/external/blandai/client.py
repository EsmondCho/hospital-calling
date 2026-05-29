"""BlandAI HTTP client (httpx-based).

Ported and trimmed from drtail-server2's `services/external/blandai/client.py`.
We use httpx (mochii-server's standard) instead of `requests`.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from django.conf import settings

from utils.cache_utils import function_cache

from .schemas import (
    BlandAICall,
    BlandAICallConfig,
    BlandAICallResponse,
    BlandAIError,
    BlandAIResponseStatus,
)

logger = structlog.get_logger(__name__)


@function_cache(minutes=60)
def get_client() -> 'BlandAIClient':
    return BlandAIClient(
        api_key=settings.BLANDAI_API_KEY,
        base_url=settings.BLANDAI_BASE_URL,
    )


class BlandAIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = 'https://api.bland.ai/v1',
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.headers = {
            'Content-Type': 'application/json',
            'authorization': api_key,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f'{self.base_url}{endpoint}'

        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                payload = e.response.json()
            except Exception:
                payload = {}
            if isinstance(payload, dict) and payload.get('status') == 'error':
                raise BlandAIError(
                    status=BlandAIResponseStatus.ERROR,
                    message=payload.get('message') or str(e),
                    details=payload,
                ) from e
            raise

    def send_call(self, config: BlandAICallConfig) -> BlandAICallResponse:
        body = config.model_dump(exclude_none=True, by_alias=True)
        data = self._request('POST', '/calls', json=body)
        return BlandAICallResponse(**data)

    def get_call(self, call_id: str) -> BlandAICall:
        data = self._request('GET', f'/calls/{call_id}')
        return BlandAICall(**data)
