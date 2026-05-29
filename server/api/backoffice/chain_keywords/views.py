from rest_framework import generics

from hospital.models import ChainKeyword

from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import ChainKeywordLv1Serializer


class ChainKeywordListView(TokenForUnsafeMethodsMixin, generics.ListAPIView):
    """Read-only list of the sourcing rule-pass chain table.

    Manage rows via the Django admin console (`/admin/`) — the backoffice
    only displays them. Unpaginated: the table is ~20 rows and the
    operator wants the whole match-priority-ordered list at once.
    """

    serializer_class = ChainKeywordLv1Serializer
    pagination_class = None
    queryset = ChainKeyword.objects.all()   # Meta.ordering = match_priority, id
