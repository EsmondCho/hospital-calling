from django.db import models


class CallSchedule(models.Model):
    """A planned outbound call campaign: which hospitals, which prompt, when.

    A schedule fans out to one or more hospitals (ordered `targets`,
    `CallScheduleHospital`) dialed **sequentially** — the next hospital is
    dialed only after the previous call reaches a terminal status.

    Created via the backoffice POST endpoint, which immediately enqueues
    `calling.dispatch_schedule(eta=scheduled_at)`. `HospcallTask` parks long-eta
    tasks in `ScheduledTask` (replayed every 10 min by
    `schedule.execute_scheduled_tasks`); short-eta tasks go straight to
    redis. At execution time `dispatch_schedule` re-checks status PENDING +
    `scheduled_at` match (so a user edit invalidates stale tasks), then
    dials the first callable target; `_advance_schedule` walks the rest as
    each call finishes. See `HospcallCallingService`.
    """

    prompt = models.ForeignKey(
        'prompt.Prompt',
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
    )

    # Wall-clock target moment (UTC). Worker picks up rows where
    # `scheduled_at <= now()`.
    scheduled_at = models.DateTimeField()

    status = models.CharField(max_length=20, default='PENDING')  # see vars.CallScheduleStatus

    # Operator memo for this schedule (e.g. "first batch — referral test").
    memo = models.CharField(max_length=200, null=True, blank=True)

    # BlandAI voice + model for this call, configured per schedule (not per
    # prompt). `voice='random'` is a sentinel — dispatch resolves it to a
    # random pooled voice per call. See vars.VOICE_CHOICES / CallModel.
    voice = models.CharField(max_length=20, default='random')
    model = models.CharField(max_length=20, default='base')
    metadata = models.JSONField(default=dict)

    # Soft delete: see Hospital.is_deleted.
    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'call_schedule'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at'], name='idx_csched_status_at'),
        ]

    def __str__(self) -> str:
        return f'CallSchedule #{self.id}'


class CallAttempt(models.Model):
    """One actual BlandAI call. 1 schedule -> 1+ attempts (in case we retry)."""

    schedule = models.ForeignKey(
        CallSchedule,
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
    )
    hospital = models.ForeignKey(
        'hospital.Hospital',
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
    )
    prompt = models.ForeignKey(
        'prompt.Prompt',
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
    )

    # BlandAI voice + model actually used for this call, captured at send
    # time. The schedule's `voice='random'` is resolved per call, so this
    # records which voice was really dialed. Empty until the call is sent.
    voice = models.CharField(max_length=20, blank=True, default='')
    model = models.CharField(max_length=20, blank=True, default='')

    # Provider linkage
    blandai_call_id = models.CharField(
        max_length=128, null=True, blank=True, unique=True
    )
    recording_url = models.URLField(max_length=500, null=True, blank=True)
    # S3 key (within RECORDINGS_BUCKET_NAME) of our archived copy.
    # BlandAI's recording_url is a 7-day pre-signed URL; this column lets us
    # locate the recording after that window expires.
    recording_s3_key = models.CharField(max_length=500, null=True, blank=True)

    status = models.CharField(max_length=20, default='QUEUED')  # see vars.CallStatus
    answered_by = models.CharField(max_length=20, null=True, blank=True)
    call_ended_by = models.CharField(max_length=20, null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)

    # Derived from BlandAI payload
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    # Content
    summary = models.TextField(null=True, blank=True)
    transcript = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)

    # Operator bookmark: starred from the backoffice (list + detail) so the
    # team can flag calls worth revisiting and filter `?starred=true`.
    is_starred = models.BooleanField(default=False, db_index=True)

    # Soft delete: see Hospital.is_deleted.
    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'call_attempt'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='idx_cattempt_status_at'),
            models.Index(fields=['hospital', '-created_at'], name='idx_cattempt_hosp_at'),
            models.Index(fields=['schedule'], name='idx_cattempt_schedule'),
            models.Index(fields=['is_starred', '-created_at'], name='idx_cattempt_starred_at'),
        ]

    def __str__(self) -> str:
        return f'CallAttempt #{self.id}'


class CallScheduleHospital(models.Model):
    """One hospital target inside a CallSchedule's ordered dial sequence.

    A schedule fans out to its targets sequentially (see
    `HospcallCallingService._advance_schedule`): the eta dials `order=0`, and
    each call's terminal status advances to the next target. `status`
    (see vars.ScheduleTargetStatus) tracks the step so a double
    webhook+reconcile refresh can't double-dial. `call_attempt` links the
    step to the CallAttempt it produced (null for a SKIPPED step).
    """

    schedule = models.ForeignKey(
        CallSchedule,
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='targets',
    )
    hospital = models.ForeignKey(
        'hospital.Hospital',
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
    )
    # 0-based dial position within the schedule.
    order = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default='PENDING')  # see vars.ScheduleTargetStatus
    call_attempt = models.ForeignKey(
        CallAttempt,
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
        related_name='+',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'call_schedule_hospital'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['schedule', 'order'], name='uq_csh_schedule_order'
            ),
        ]
        indexes = [
            models.Index(fields=['schedule', 'order'], name='idx_csh_schedule_order'),
        ]

    def __str__(self) -> str:
        return f'CallScheduleHospital(schedule={self.schedule_id}, order={self.order})'


class CallComment(models.Model):
    """A free-text operator note attached to a CallAttempt.

    A call log can carry many comments (the team listens to a recording and
    leaves notes over time). `author` is the backoffice username (esmond /
    rayer) that the proxy forwards as `X-Backoffice-User`; only the author
    may edit or delete their own comment. Hard-deleted from the backoffice.
    """

    call_attempt = models.ForeignKey(
        CallAttempt,
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name='comments',
    )
    body = models.TextField()
    # Backoffice username of the writer. Blank for legacy rows written before
    # accounts were split (DRT-5347).
    author = models.CharField(max_length=50, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'call_comment'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['call_attempt', 'created_at'], name='idx_ccomment_attempt_at'),
        ]

    def __str__(self) -> str:
        return f'CallComment #{self.id} on attempt {self.call_attempt_id}'
