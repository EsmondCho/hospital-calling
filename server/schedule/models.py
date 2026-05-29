from django.db import models


class ScheduledTask(models.Model):
    """Tasks queued via `HospcallTask.apply_async` with eta > 10 min into the future.

    Beat-driven `schedule.execute_scheduled_tasks` polls this table every 10
    minutes and re-applies anything whose eta is now within the next batch
    window. This keeps the redis broker free of long-pending tasks (which
    would be lost on broker restart) and survives worker restarts.
    """

    task_name = models.CharField(max_length=120)
    eta = models.DateTimeField()
    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)
    options = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'scheduled_task'
        indexes = [
            models.Index(
                fields=['eta', 'dispatched_at'],
                name='idx_schtask_eta_dispatched',
            ),
        ]

    def __str__(self):
        return f'ScheduledTask(id={self.id}, task={self.task_name}, eta={self.eta})'
