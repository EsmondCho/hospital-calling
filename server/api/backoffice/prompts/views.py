from django.db.models import Count, Max
from rest_framework import generics, serializers
from rest_framework.response import Response

from prompt.models import Prompt

from .._soft_delete import BulkSoftDeleteView, SoftDeleteMixin
from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import (
    PromptCreateSerializer,
    PromptListSerializer,
    PromptLv2Serializer,
    PromptVersionSerializer,
)


class PromptListCreateView(TokenForUnsafeMethodsMixin, generics.ListCreateAPIView):
    """`GET` aggregates one row per logical prompt; `POST` creates a version.

    The list is one entry per `name` (a logical prompt) — aggregated, not
    paginated, mirroring `chain_keywords`. `POST` auto-bumps `version`.
    """

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PromptCreateSerializer
        return PromptListSerializer

    def get_queryset(self):
        return Prompt.objects.filter(is_deleted=False).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        rows = (
            Prompt.objects.filter(is_deleted=False)
            .values('name')
            .annotate(
                version_count=Count('id'),
                latest_version=Max('version'),
                latest_updated=Max('updated_at'),
            )
            .order_by('-latest_updated')
        )
        entries = [
            {
                'name': row['name'],
                'version_count': row['version_count'],
                'latest_version': row['latest_version'],
                'updated_at': row['latest_updated'],
            }
            for row in rows
        ]
        return Response(PromptListSerializer(entries, many=True).data)


class PromptVersionListView(TokenForUnsafeMethodsMixin, generics.ListAPIView):
    """`GET /backoffice/prompts/versions/?name=<name>` — all versions of one prompt.

    Every non-deleted row sharing `name`, newest version first, body included.
    Unpaginated — a logical prompt has only a handful of versions. `name` is a
    query parameter (not a path segment) so free-form names need no encoding.
    """

    serializer_class = PromptVersionSerializer
    pagination_class = None

    def get_queryset(self):
        name = self.request.query_params.get('name')
        if not name:
            raise serializers.ValidationError(
                {'name': 'The `name` query parameter is required.'}
            )
        return Prompt.objects.filter(
            is_deleted=False, name=name
        ).order_by('-version')


class PromptDetailView(
    SoftDeleteMixin,
    TokenForUnsafeMethodsMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    queryset = Prompt.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return PromptCreateSerializer
        return PromptLv2Serializer


class PromptBulkDeleteView(BulkSoftDeleteView):
    model = Prompt
