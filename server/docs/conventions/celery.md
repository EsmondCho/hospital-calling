# Celery Task Conventions

## Register every services-internal scope

When you add `services/internal/<scope>/tasks.py`, append `'services.internal.<scope>'`
to `hospcall/celery.py::autodiscover_tasks([...])`. Without it, `apply_async`
fails with `NotRegistered: <task_name>` and the failure may not surface in
your error tracker.

Domain-app tasks (`calling/tasks.py`) are picked up by the empty
`celery_app.autodiscover_tasks()` call automatically — no extra registration.

## Always `apply_async(kwargs=...)`

```python
# bad
my_task.delay(call_attempt_id)
my_task.apply_async(args=[call_attempt_id])

# good
my_task.apply_async(kwargs={'call_attempt_id': call_attempt_id})
```

Keyword args survive signature changes; positional args don't.

## No datetime in kwargs

JSON serializer can't carry `datetime`. Convert to ISO string before sending,
parse on the worker side.

```python
# good
my_task.apply_async(kwargs={'scheduled_for_iso': dt.isoformat()})
```

## Idempotency

`acks_late=True` is on for our tasks (set in `hospcall/settings/base.py`). A task
may run twice. Build with that in mind:
- `get_or_create()` over `create()` where uniqueness matters
- `filter(status=ACTIVE).update(status=ENDED)` — narrow by current state

## Naming & periodic tasks

Periodic tasks live in `hospcall/schedules.py`. Name them in lowercase dotted form
(`calling.dispatch_due_calls`) and register the same name on
`@shared_task(name=...)`.
