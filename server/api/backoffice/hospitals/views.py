from django.db.models import Count, Q
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS

from hospital.models import Hospital
from hospital.vars import HospitalOwnership

from .._soft_delete import BulkSoftDeleteView, SoftDeleteMixin
from ..pagination import BackofficePageNumberPagination
from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import (
    HospitalCreateSerializer,
    HospitalLv1Serializer,
    HospitalLv2Serializer,
)


def _save_with_autolock(serializer, request) -> None:
    """Persist an operator create/edit, auto-setting `label_locked=True`.

    A hand-entered or hand-corrected hospital should not be re-classified
    by the sourcing pipeline. If the operator passes `label_locked`
    explicitly we honor it (lets them deliberately unlock); otherwise we
    force the lock on.
    """
    if 'label_locked' in request.data:
        serializer.save()
    else:
        serializer.save(label_locked=True)


class HospitalListCreateView(TokenForUnsafeMethodsMixin, generics.ListCreateAPIView):
    pagination_class = BackofficePageNumberPagination

    def get_queryset(self):
        # `call_attempt_count` is a query annotation, not a stored column —
        # total contact volume so operators can spot an over-called hospital.
        # `CallAttempt.hospital` has no `related_name`, so the reverse query
        # name is the default `callattempt`.
        qs = (
            Hospital.objects.filter(is_deleted=False)
            .annotate(
                call_attempt_count=Count(
                    'callattempt',
                    filter=Q(callattempt__is_deleted=False),
                )
            )
            .order_by('-created_at', '-id')
        )
        # `?q=` is a name typeahead used by the schedule form's hospital picker.
        # Tiny dataset → icontains is fine; revisit when row count crosses ~10k.
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(name__icontains=q)
        # `?ownership=` is the backoffice list filter — an exact match on the
        # classification axis (see vars.HospitalOwnership). Composes with `?q=`
        # and cursor pagination; `idx_hospital_ownership` backs the lookup.
        ownership = self.request.query_params.get('ownership')
        if ownership:
            # Reject an unknown value up front — an out-of-set string would
            # silently return zero rows, hiding the operator's typo.
            if ownership not in HospitalOwnership.get_vals():
                raise ValidationError(
                    {'ownership': 'Must be a valid hospital ownership value.'}
                )
            qs = qs.filter(ownership=ownership)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return HospitalCreateSerializer
        return HospitalLv1Serializer

    def perform_create(self, serializer):
        _save_with_autolock(serializer, self.request)


class HospitalDetailView(
    SoftDeleteMixin,
    TokenForUnsafeMethodsMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    def get_queryset(self):
        # Annotate the count only for reads — a PATCH/PUT/DELETE serializes
        # via HospitalCreateSerializer, which never reads `call_attempt_count`,
        # so the aggregate would be wasted work on writes.
        qs = Hospital.objects.filter(is_deleted=False)
        if self.request.method in SAFE_METHODS:
            qs = qs.annotate(
                call_attempt_count=Count(
                    'callattempt',
                    filter=Q(callattempt__is_deleted=False),
                ),
            )
        return qs

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return HospitalCreateSerializer
        return HospitalLv2Serializer

    def perform_update(self, serializer):
        _save_with_autolock(serializer, self.request)


class HospitalBulkDeleteView(BulkSoftDeleteView):
    model = Hospital
