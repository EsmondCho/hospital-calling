import typing as t

from celery.schedules import crontab

# NOTE: 이 모듈은 Django settings configure 전에 import되므로 `django.conf.settings`
# 접근 금지. 환경변수 직접 읽기.


class Schedule:
    def __init__(self, name: str, task: str, schedule: crontab) -> None:
        self.name = name
        self.task = task
        self.schedule = schedule

    @property
    def values(self) -> dict[str, t.Any]:
        return {'task': self.task, 'schedule': self.schedule}


# ─────────────────────────────────────────────────────────────────────────────
# 10분 단위 — `HospcallTask`가 ScheduledTask DB에 저장해둔 long-eta task 재투입.
# 사용자가 만든 CallSchedule도 이 경로로 enqueue되므로 dispatch_due_calls beat는
# 더 이상 필요 없다.
# ─────────────────────────────────────────────────────────────────────────────
EXECUTE_SCHEDULED_TASKS = Schedule(
    'Execute scheduled ETA tasks',
    'schedule.execute_scheduled_tasks',
    crontab(minute='*/10'),
)

# ─────────────────────────────────────────────────────────────────────────────
# 15분 단위 — 결과 수집 (webhook 누락 대비 백업 폴링)
# ─────────────────────────────────────────────────────────────────────────────
RECONCILE_IN_PROGRESS_CALLS = Schedule(
    'Reconcile IN_PROGRESS CallAttempts via BlandAI poll',
    'calling.reconcile_in_progress_calls',
    crontab(minute='*/15'),
)


_active: list[Schedule] = [
    EXECUTE_SCHEDULED_TASKS,
    RECONCILE_IN_PROGRESS_CALLS,
]

schedules: dict[str, dict[str, t.Any]] = {s.name: s.values for s in _active}
