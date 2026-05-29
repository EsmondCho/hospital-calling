import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from celery import Celery, Task
from django.utils import timezone
from kombu import Queue

from hospcall.schedules import schedules

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hospcall.settings')

celery_app = Celery('hospcall')
celery_app.config_from_object('django.conf:settings', namespace='CELERY')
celery_app.conf.beat_schedule = schedules

# Explicit queue definitions (DRT-5265). `celery` is the default queue; the
# sourcing tile-search tasks are routed to `sourcing_search` via
# `CELERY_TASK_ROUTES` in settings so a concurrency-limited worker bounds
# the Google Places call rate.
celery_app.conf.task_default_queue = 'celery'
celery_app.conf.task_queues = (
    Queue('celery'),
    Queue('sourcing_search'),
)

celery_app.autodiscover_tasks()
celery_app.autodiscover_tasks(
    [
        'services.internal.hospcall_calling',
        'services.internal.sourcing',
    ]
)

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Datetime sign/unsign — JSONField loses tz info on round-trip; encode tz so
# `HospcallTask` can persist eta'd tasks safely and `execute_scheduled_tasks` can
# restore them.
# ─────────────────────────────────────────────────────────────────────────────
def sign_datetime(value):
    if not isinstance(value, datetime):
        return value
    tzinfo_str = str(value.tzinfo) if value.tzinfo else ''
    return f"__{value.strftime('%Y-%m-%dT%H:%M:%S.%f')}@@{tzinfo_str}__"


def unsign_datetime(value):
    if not isinstance(value, str):
        return value
    if not value.startswith('__') or not value.endswith('__'):
        return value
    try:
        inner = value[2:-2]
        dt_str, tzinfo_str = inner.split('@@')
        tz = ZoneInfo(tzinfo_str) if tzinfo_str else None
        return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=tz)
    except (ValueError, KeyError):
        logger.warning('failed_to_unsign_datetime', value=value)
        return value


# ─────────────────────────────────────────────────────────────────────────────
# HospcallTask — base task class. ETAs more than 10 minutes in the future are
# parked in `ScheduledTask` so a redis broker restart can't lose them; beat
# replays them via `schedule.execute_scheduled_tasks`.
# ─────────────────────────────────────────────────────────────────────────────
class HospcallTask(Task):
    SCHEDULING_BATCH_SECONDS = 60 * 10

    def apply_async(self, args=None, kwargs=None, **options):
        now = timezone.now()

        countdown = options.get('countdown')
        if countdown and countdown > self.SCHEDULING_BATCH_SECONDS:
            eta = now + timedelta(seconds=countdown)
            options.pop('countdown')
            return self._save_to_db(eta, args, kwargs, options)

        eta = options.get('eta')
        if eta and eta - now > timedelta(seconds=self.SCHEDULING_BATCH_SECONDS):
            options.pop('eta')
            return self._save_to_db(eta, args, kwargs, options)

        return super().apply_async(args, kwargs, **options)

    def _save_to_db(self, eta, args, kwargs, options):
        from celery.result import AsyncResult

        from schedule.models import ScheduledTask

        if args is not None:
            args = tuple(sign_datetime(a) for a in args)
        if kwargs is not None:
            kwargs = {k: sign_datetime(v) for k, v in kwargs.items()}

        st = ScheduledTask.objects.create(
            task_name=self.name,
            eta=eta,
            args=args or [],
            kwargs=kwargs or {},
            options=options or {},
        )
        return AsyncResult(id=f'scheduled-{st.id}')


celery_app.Task = HospcallTask  # type: ignore[misc]
