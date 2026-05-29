from django.db import models


class Prompt(models.Model):
    """One version of a BlandAI task prompt.

    A single row is exactly one version. A *logical prompt* is the set of all
    non-deleted rows sharing the same `name`; the row with the highest
    `version` is the latest. `(name, version)` is unique, so a new version is
    a new row — older versions stay in the DB so `CallSchedule.prompt` /
    `CallAttempt.prompt` can keep pointing at the exact text used at call time.
    """

    name = models.CharField(max_length=80)
    version = models.PositiveIntegerField()
    body = models.TextField()

    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    # Soft delete: see Hospital.is_deleted.
    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prompt'
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'version'], name='uq_prompt_name_version'
            ),
        ]
        indexes = [
            models.Index(fields=['name', '-version'], name='idx_prompt_name_ver'),
        ]

    def __str__(self) -> str:
        return f'Prompt {self.name} v{self.version}'
