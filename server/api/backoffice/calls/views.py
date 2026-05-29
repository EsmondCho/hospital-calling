from django.db.models import Count
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from calling.models import CallAttempt, CallComment
from services.internal.recordings import (
    RecordingsStorageError,
    presign_recording,
)

from .._soft_delete import BulkSoftDeleteView, SoftDeleteMixin
from ..pagination import BackofficePageNumberPagination
from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import (
    CallAttemptLv1Serializer,
    CallAttemptLv2Serializer,
    CallAttemptStarSerializer,
    CallCommentSerializer,
)

_TRUTHY = {'1', 'true', 'yes', 'on'}


def _current_user(request) -> str:
    """Backoffice username for write-attribution / ownership checks.

    The Next proxy decodes the Basic-Auth user and forwards it as
    `X-Backoffice-User`. Empty in local dev with no auth configured.
    """
    return request.META.get('HTTP_X_BACKOFFICE_USER', '') or ''


class CallAttemptListView(generics.ListAPIView):
    serializer_class = CallAttemptLv1Serializer
    pagination_class = BackofficePageNumberPagination

    def get_queryset(self):
        qs = (
            CallAttempt.objects.filter(is_deleted=False)
            .select_related('hospital', 'prompt')
            .annotate(comment_count=Count('comments'))
            .order_by('-created_at', '-id')
        )
        # `?schedule=<id>` powers the schedule detail page's "calls bound to
        # this schedule" panel — now 1+ rows per schedule (sequential fan-out).
        schedule_id = self.request.query_params.get('schedule')
        if schedule_id:
            # `int()` rather than `str.isdigit()` — the latter accepts
            # Unicode digit chars (e.g. '²') that then blow up at the ORM.
            try:
                schedule_id = int(schedule_id)
            except ValueError:
                raise ValidationError(
                    {'schedule': 'Must be a numeric schedule id.'}
                )
            qs = qs.filter(schedule_id=schedule_id)
        # `?hospital=<id>` powers the hospital detail page's call-history
        # panel and lets operators audit a single hospital's contact volume.
        hospital_id = self.request.query_params.get('hospital')
        if hospital_id:
            try:
                hospital_id = int(hospital_id)
            except ValueError:
                raise ValidationError(
                    {'hospital': 'Must be a numeric hospital id.'}
                )
            qs = qs.filter(hospital_id=hospital_id)
        # `?starred=true` powers the call-log list's "starred only" filter.
        starred = self.request.query_params.get('starred')
        if starred is not None and starred.lower() in _TRUTHY:
            qs = qs.filter(is_starred=True)
        return qs


class CallAttemptDetailView(
    SoftDeleteMixin,
    TokenForUnsafeMethodsMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    queryset = CallAttempt.objects.filter(is_deleted=False).select_related(
        'hospital', 'prompt'
    )
    # PATCH is a star-only partial update; full-replace PUT is not supported
    # (it would silently ignore every field but `is_starred`), so disallow it.
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        # PATCH is star-only; the read path returns the full detail.
        if self.request.method == 'PATCH':
            return CallAttemptStarSerializer
        return CallAttemptLv2Serializer


class CallAttemptBulkDeleteView(BulkSoftDeleteView):
    model = CallAttempt


class CallRecordingView(APIView):
    """`GET /backoffice/calls/<id>/recording/` → `{ "url": <playable url> }`.

    Prefers a freshly-presigned URL off our S3 archive (`recording_s3_key`),
    which keeps playing after BlandAI's 7-day `recording_url` expires; falls
    back to the BlandAI URL when the archive key is missing or S3 presign
    fails. `null` when neither is available.
    """

    def get(self, request, pk: int):
        attempt = get_object_or_404(
            CallAttempt.objects.filter(is_deleted=False), pk=pk
        )
        url = None
        if attempt.recording_s3_key:
            try:
                url = presign_recording(attempt.recording_s3_key)
            except RecordingsStorageError:
                url = attempt.recording_url
        else:
            url = attempt.recording_url
        return Response({'url': url})


class CallCommentListCreateView(
    TokenForUnsafeMethodsMixin, generics.ListCreateAPIView
):
    """`/backoffice/calls/<call_id>/comments/` — list (newest first) / add.

    Unpaginated: a call carries a handful of operator notes at most. POST
    stamps the comment with the authenticated user (`X-Backoffice-User`).
    """

    serializer_class = CallCommentSerializer
    pagination_class = None

    def get_queryset(self):
        # 404 a GET on an unknown / deleted call so the listing is consistent
        # with POST (which 404s in perform_create) instead of returning [].
        get_object_or_404(
            CallAttempt.objects.filter(is_deleted=False),
            pk=self.kwargs['call_id'],
        )
        return CallComment.objects.filter(
            call_attempt_id=self.kwargs['call_id']
        ).order_by('-created_at')

    def perform_create(self, serializer):
        # 404 on an unknown / deleted call rather than silently orphaning a
        # comment (the FK has no DB constraint, so we guard in code).
        call = get_object_or_404(
            CallAttempt.objects.filter(is_deleted=False),
            pk=self.kwargs['call_id'],
        )
        serializer.save(call_attempt=call, author=_current_user(self.request))


class CallCommentDetailView(
    TokenForUnsafeMethodsMixin, generics.RetrieveUpdateDestroyAPIView
):
    """`/backoffice/calls/<call_id>/comments/<id>/` — edit / hard-delete.

    Only the comment's `author` may edit (PATCH body) or delete it. Legacy
    comments (`author=''`, written before accounts) are owned by nobody, so
    no operator can edit or delete them via the API.
    """

    serializer_class = CallCommentSerializer
    http_method_names = ['patch', 'delete', 'head', 'options']

    def get_queryset(self):
        # 404 when the parent call is unknown / soft-deleted — a deleted call
        # exposes none of its comments (matches the list endpoint).
        get_object_or_404(
            CallAttempt.objects.filter(is_deleted=False),
            pk=self.kwargs['call_id'],
        )
        return CallComment.objects.filter(
            call_attempt_id=self.kwargs['call_id']
        )

    def check_object_permissions(self, request, obj):
        # Author check runs at get_object() — before serializer validation —
        # so a non-author PATCH with an invalid body gets 403, not 400.
        super().check_object_permissions(request, obj)
        self._assert_author(obj)

    def _assert_author(self, instance) -> None:
        user = _current_user(self.request)
        # An empty user (proxy bypassed) or a non-author is denied; this also
        # means legacy `author=''` comments are editable/deletable by nobody.
        if not user or instance.author != user:
            raise PermissionDenied('You can only modify your own comments.')
