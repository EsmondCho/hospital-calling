"""BlandAI webhook handler.

BlandAI does not sign outbound webhooks, so we authenticate the request via
a secret token embedded in the URL path
(`/webhook/blandai/call_status/<token>/`). The token is compared
constant-time against `settings.BLANDAI_WEBHOOK_SECRET`.

Local env (`ENV=local`) skips the check so ngrok-based testing works
without setting up a fake secret.
"""

from __future__ import annotations

import hmac

import structlog
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from calling.models import CallAttempt
from calling.tasks import process_blandai_webhook

logger = structlog.get_logger(__name__)


def _token_matches(token: str) -> bool:
    secret = settings.BLANDAI_WEBHOOK_SECRET or ''
    env = getattr(settings, 'ENV', 'local')
    if not secret:
        if env == 'local':
            return True
        logger.warning('blandai.webhook.no_secret_configured')
        return False
    return hmac.compare_digest(secret, token)


@api_view(['POST'])
@permission_classes([AllowAny])
def call_status(request, token: str):
    if not _token_matches(token):
        return Response(
            {'error': 'Invalid webhook token'}, status=status.HTTP_403_FORBIDDEN
        )

    payload = request.data or {}
    call_id = payload.get('call_id') or payload.get('c_id')
    if not call_id:
        return Response(
            {'error': 'call_id is required'}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        attempt = CallAttempt.objects.get(blandai_call_id=call_id)
    except CallAttempt.DoesNotExist:
        logger.warning('blandai.webhook.call_attempt_not_found', call_id=call_id)
        return Response({'status': 'ignored'}, status=status.HTTP_200_OK)

    process_blandai_webhook.apply_async(kwargs={'call_attempt_id': attempt.id})
    return Response({'status': 'ok'}, status=status.HTTP_200_OK)
