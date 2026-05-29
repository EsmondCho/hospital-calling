"""DRF permission classes for backoffice mutating endpoints.

Read endpoints stay open to anyone behind the Vercel basic-auth wall; write
endpoints additionally require an `X-Backoffice-Token` header that matches
`settings.BACKOFFICE_API_TOKEN`. The token is rotated by re-deploying the
SSM parameter `/hospcall/BACKOFFICE_API_TOKEN`.
"""

from __future__ import annotations

import hmac

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission

HEADER = 'HTTP_X_BACKOFFICE_TOKEN'


class TokenForUnsafeMethodsMixin:
    """View mixin: GET/HEAD/OPTIONS open, every other verb requires token."""

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsBackofficeToken()]


class IsBackofficeToken(BasePermission):
    """Header `X-Backoffice-Token` must match `settings.BACKOFFICE_API_TOKEN`.

    Denies if the server-side token is unset (so a misconfigured prod env
    fails closed instead of accepting any caller).
    """

    message = 'Invalid or missing backoffice token.'

    def has_permission(self, request, view) -> bool:
        expected = getattr(settings, 'BACKOFFICE_API_TOKEN', '')
        if not expected:
            return False
        provided = request.META.get(HEADER, '')
        if not provided:
            return False
        return hmac.compare_digest(expected, provided)
