"""Shared helpers for backoffice soft-delete + bulk-delete endpoints.

Every model that powers a backoffice list (Hospital, Prompt, CallSchedule,
CallAttempt) carries an `is_deleted` flag. Users delete via the UI; the
flag flips to True and lists/details filter the row out — DB rows persist
so historical relations stay intact.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsBackofficeToken


class SoftDeleteMixin:
    """View mixin: DELETE flips `is_deleted=True` instead of removing the row."""

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])


class BulkSoftDeleteView(APIView):
    """POST `/<resource>/bulk_delete/` body `{"ids": [1,2,3]}`.

    Subclass and set `model`. Returns `{'deleted_count': N}`.
    """

    permission_classes = [IsBackofficeToken]
    model = None  # type: ignore[assignment]

    def post(self, request):
        ids = request.data.get('ids') or []
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return Response(
                {'detail': 'Body must be {"ids": [int, ...]}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ids:
            return Response({'deleted_count': 0}, status=status.HTTP_200_OK)

        deleted = self.model.objects.filter(id__in=ids, is_deleted=False).update(
            is_deleted=True
        )
        return Response({'deleted_count': deleted}, status=status.HTTP_200_OK)
