from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import APIException

from calling.models import CallSchedule
from calling.tasks import dispatch_schedule as dispatch_schedule_task
from calling.vars import CallScheduleStatus

from .._soft_delete import BulkSoftDeleteView, SoftDeleteMixin
from ..pagination import BackofficePageNumberPagination
from ..permissions import TokenForUnsafeMethodsMixin
from .serializers import (
    CallScheduleCreateSerializer,
    CallScheduleLv1Serializer,
    CallScheduleLv2Serializer,
)


class ScheduleAlreadyDispatched(APIException):
    """409 — schedule has been picked up by the worker; can no longer edit."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Schedule has already been dispatched; edit is no longer allowed.'
    default_code = 'schedule_already_dispatched'


def _enqueue_dispatch(schedule: CallSchedule) -> None:
    """Queue `dispatch_schedule` for `schedule` at its eta.

    HospcallTask intercepts long ETAs (>10 min) and parks them in `ScheduledTask`
    so a redis broker restart can't lose them. Short ETAs go straight to
    redis. The schedule's current `scheduled_at` is snapshotted as
    `expected_scheduled_at_iso` so the worker can detect a later edit and
    bail (the freshly enqueued task will fire at the new time).
    """
    dispatch_schedule_task.apply_async(
        kwargs={
            'schedule_id': schedule.id,
            'expected_scheduled_at_iso': schedule.scheduled_at.isoformat(),
        },
        eta=schedule.scheduled_at,
    )


class CallScheduleListCreateView(
    TokenForUnsafeMethodsMixin, generics.ListCreateAPIView
):
    # Sort by most-recently-created so a fresh "+ New schedule" lands at the
    # top of the table even if its scheduled_at is far in the past or future.
    queryset = (
        CallSchedule.objects.filter(is_deleted=False)
        .select_related('prompt')
        .prefetch_related('targets__hospital')
        .order_by('-created_at', '-id')
    )
    pagination_class = BackofficePageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CallScheduleCreateSerializer
        return CallScheduleLv1Serializer

    def perform_create(self, serializer):
        # Atomic so that an enqueue failure (long-eta path writes to
        # ScheduledTask) doesn't leave a PENDING CallSchedule with no task
        # bound to it — that orphan would never be picked up now that
        # `dispatch_due_calls` beat is gone.
        with transaction.atomic():
            schedule = serializer.save()
            _enqueue_dispatch(schedule)


class CallScheduleDetailView(
    SoftDeleteMixin,
    TokenForUnsafeMethodsMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    queryset = (
        CallSchedule.objects.filter(is_deleted=False)
        .select_related('prompt')
        .prefetch_related('targets__hospital')
    )

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return CallScheduleCreateSerializer
        return CallScheduleLv2Serializer

    def perform_update(self, serializer):
        if serializer.instance.status != CallScheduleStatus.PENDING:
            raise ScheduleAlreadyDispatched()
        # Re-enqueue so a changed scheduled_at takes effect. The previously-
        # queued task will see the row's new scheduled_at and bail with
        # `superseded` instead of double-dispatching. Atomic so a partial
        # failure can't update CallSchedule without queuing a new task.
        with transaction.atomic():
            schedule = serializer.save()
            _enqueue_dispatch(schedule)


class CallScheduleBulkDeleteView(BulkSoftDeleteView):
    model = CallSchedule
