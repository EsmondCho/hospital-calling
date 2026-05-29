"""Orchestration for HOSPCALL outbound calls.

Responsibilities:
- pick up due `CallSchedule` rows and create `CallAttempt`s
- send the actual BlandAI call and persist call_id / status
- refresh a `CallAttempt` from BlandAI (webhook-triggered or poll-triggered)

This module is the *only* place that should talk to BlandAI; tasks.py and
api/* layers go through here.
"""

from __future__ import annotations

import random
from datetime import timedelta

import structlog
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from calling.models import CallAttempt, CallSchedule, CallScheduleHospital
from calling.vars import (
    VOICE_POOL,
    VOICE_RANDOM,
    CallScheduleStatus,
    CallStatus,
    ScheduleTargetStatus,
)
from hospital.vars import HospitalOwnership
from services.external.blandai import (
    BlandAIAnsweredBy,
    BlandAICallConfig,
    BlandAICallStatus,
    BlandAIError,
    BlandAIPronunciation,
    BlandAIResponseStatus,
    BlandAIVoicemail,
    get_client,
)
from services.internal.recordings import (
    RecordingsStorageError,
    archive_recording,
)

logger = structlog.get_logger(__name__)

# Brand pronunciation so the agent says "Dr.Tail" as "Doctor Tail" — not
# "D-R Tail" or "Drtail". Applied to every outbound call. Immutable tuple
# (no global mutable state); copied to a list at the call site since the
# `pronunciation_guide` field is typed `list[...]`.
_PRONUNCIATION_GUIDE: tuple[BlandAIPronunciation, ...] = (
    BlandAIPronunciation(word='Dr.Tail', pronunciation='Doctor Tail'),
)


class HospcallCallingService:
    """Stateless orchestrator. Safe to instantiate per task."""

    def __init__(self) -> None:
        self.blandai = get_client()

    # ── Dispatch one schedule (eta-driven via `HospcallTask`) ─────────────────
    def dispatch_schedule(
        self, *, schedule_id: int, expected_scheduled_at_iso: str
    ) -> dict:
        """Begin a schedule's sequential dial when its eta arrives.

        The task carries the `scheduled_at` value at enqueue time so an edit
        between enqueue and execution is detectable: if the row's current
        `scheduled_at` doesn't match, this is a stale task and the freshly
        enqueued one will fire at the new time. We bail with `superseded`.

        ACKS_LATE replays can re-run this for the same row, so the
        PENDING→DISPATCHED transition is a conditional UPDATE: the second
        runner matches 0 rows and bails. Once DISPATCHED, `_advance_schedule`
        dials the first callable target; the rest are walked as each call
        finishes (see `_on_attempt_finished`).
        """
        from django.db import transaction

        try:
            schedule = CallSchedule.objects.get(id=schedule_id)
        except CallSchedule.DoesNotExist:
            logger.info(
                'calling.dispatch_schedule.not_found', schedule_id=schedule_id
            )
            return {'result': 'not_found'}

        if schedule.scheduled_at.isoformat() != expected_scheduled_at_iso:
            logger.info(
                'calling.dispatch_schedule.superseded',
                schedule_id=schedule_id,
                expected=expected_scheduled_at_iso,
                current=schedule.scheduled_at.isoformat(),
            )
            return {'result': 'superseded'}

        with transaction.atomic():
            updated = CallSchedule.objects.filter(
                id=schedule_id, status=CallScheduleStatus.PENDING
            ).update(status=CallScheduleStatus.DISPATCHED)
        if not updated:
            logger.info(
                'calling.dispatch_schedule.not_pending',
                schedule_id=schedule_id,
                status=schedule.status,
            )
            return {'result': 'not_pending'}

        return self._advance_schedule(schedule_id)

    def _advance_schedule(self, schedule_id: int) -> dict:
        """Dial the next callable target of a DISPATCHED schedule.

        Walks `targets` in order: a PENDING + callable hospital becomes
        DIALING (a fresh QUEUED `CallAttempt` is created, `send_call` fired
        after commit); a PENDING + uncallable hospital is marked SKIPPED and
        we keep walking. When no PENDING target remains the schedule closes
        COMPLETED (or SKIPPED if nothing was ever dialed). A target already
        DIALING means a call is in flight, so we no-op — that, plus the row
        lock, is what makes a double webhook+reconcile advance safe.
        """
        from django.db import transaction

        from calling.tasks import send_call as send_call_task

        attempt_id: int | None = None
        with transaction.atomic():
            # Lock the schedule so concurrent advances serialize; the DIALING
            # guard below then makes a duplicate advance idempotent.
            schedule = CallSchedule.objects.select_for_update().get(id=schedule_id)

            if schedule.targets.filter(
                status=ScheduleTargetStatus.DIALING
            ).exists():
                return {'result': 'in_flight'}

            # Load the remaining PENDING targets once and walk them in memory —
            # re-querying per skipped target would be N SELECTs for N
            # uncallable hospitals in a row.
            pending = list(
                schedule.targets.select_related('hospital')
                .filter(status=ScheduleTargetStatus.PENDING)
                .order_by('order')
            )
            for target in pending:
                if not _is_callable(target.hospital):
                    target.status = ScheduleTargetStatus.SKIPPED
                    target.save(update_fields=['status', 'updated_at'])
                    continue
                attempt = CallAttempt.objects.create(
                    schedule=schedule,
                    hospital=target.hospital,
                    prompt_id=schedule.prompt_id,
                    status=CallStatus.QUEUED,
                )
                target.status = ScheduleTargetStatus.DIALING
                target.call_attempt = attempt
                target.save(
                    update_fields=['status', 'call_attempt', 'updated_at']
                )
                attempt_id = attempt.id
                break
            else:
                # No PENDING target left — close out the schedule.
                dialed = schedule.targets.filter(
                    status=ScheduleTargetStatus.DONE
                ).exists()
                final = (
                    CallScheduleStatus.COMPLETED
                    if dialed
                    else CallScheduleStatus.SKIPPED
                )
                CallSchedule.objects.filter(id=schedule_id).update(status=final)
                logger.info(
                    'calling.dispatch_schedule.closed',
                    schedule_id=schedule_id,
                    status=final,
                )
                return {'result': 'completed' if dialed else 'skipped'}

        # Fire outside the transaction so the worker sees the committed row.
        send_call_task.apply_async(kwargs={'call_attempt_id': attempt_id})
        logger.info(
            'calling.dispatch_schedule.dispatched',
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        return {'result': 'dispatched', 'attempt_id': attempt_id}

    def _on_attempt_finished(self, attempt: CallAttempt) -> None:
        """Close a schedule's current target and dial the next one.

        Idempotent: the DIALING→DONE transition is a locked, status-gated
        update, so a duplicate webhook+reconcile refresh of the same call
        advances the sequence exactly once. No-op for ad-hoc attempts with
        no schedule.
        """
        if not attempt.schedule_id:
            return
        from django.db import transaction

        with transaction.atomic():
            target = (
                CallScheduleHospital.objects.select_for_update()
                .filter(
                    schedule_id=attempt.schedule_id,
                    call_attempt_id=attempt.id,
                    status=ScheduleTargetStatus.DIALING,
                )
                .first()
            )
            if target is None:
                return  # already advanced, or not a sequence step
            target.status = ScheduleTargetStatus.DONE
            target.save(update_fields=['status', 'updated_at'])

        self._advance_schedule(attempt.schedule_id)

    # ── Send (worker task → here) ───────────────────────────────────────────
    def send_call(self, *, call_attempt_id: int) -> CallAttempt:
        from django.db import transaction

        # Idempotency claim. `send_call` is acks_late, so a worker that dials
        # BlandAI then dies before acking gets the task redelivered — and the
        # reconcile sweep re-fires a QUEUED attempt whose original task was
        # lost. Only a QUEUED attempt may be dialed; claim it
        # (QUEUED→IN_PROGRESS) under a row lock so neither path places a
        # second real call. The provider call stays outside the transaction.
        with transaction.atomic():
            # `of=('self',)` locks only the call_attempt row — a plain
            # select_for_update with these nullable select_related joins is
            # rejected by Postgres ("FOR UPDATE cannot be applied to the
            # nullable side of an outer join").
            attempt = (
                CallAttempt.objects.select_for_update(of=('self',))
                .select_related('hospital', 'prompt', 'schedule')
                .get(id=call_attempt_id)
            )
            if attempt.status != CallStatus.QUEUED:
                logger.info(
                    'hospcall_calling.send_call.not_queued',
                    call_attempt_id=attempt.id,
                    status=attempt.status,
                )
                return attempt
            attempt.status = CallStatus.IN_PROGRESS
            attempt.save(update_fields=['status', 'updated_at'])

        if not attempt.hospital or not attempt.hospital.phone_e164:
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = 'Hospital has no phone number'
            attempt.save()
            return self._after_send(attempt)
        if not attempt.prompt:
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = 'No prompt attached'
            attempt.save()
            return self._after_send(attempt)

        voice, model = _resolve_voice_model(attempt.schedule)
        attempt.voice = voice
        attempt.model = model

        # AI & recording disclosure is handled by the prompt (the agent says it
        # mid-call), NOT by BlandAI's TCPA `guard_rails`. We deliberately omit
        # guard_rails: a TCPA guard rail is only a backstop that *ends* the call
        # if disclosure isn't made within a fixed window — it never speaks the
        # disclosure itself. Our script discloses *after* the opening exchange
        # (so the front desk engages first), so a time-boxed guard rail would
        # misfire and kill otherwise-good calls before the agent reaches the
        # disclosure. If stricter enforcement is ever needed, add guard_rails
        # with an end_seconds window comfortably longer than that opening.
        config = BlandAICallConfig(
            phone_number=attempt.hospital.phone_e164,
            task=attempt.prompt.body,
            voice=voice,
            model=model,
            language=settings.BLANDAI_DEFAULT_LANGUAGE,
            record=True,
            wait_for_greeting=True,
            max_duration=settings.BLANDAI_MAX_DURATION,
            # Voicemail: HOSPCALL doesn't leave messages — hangup on detection.
            # Sensitive=True uses BlandAI's LLM-based detection (more accurate
            # than the default heuristic, modest extra cost).
            voicemail=BlandAIVoicemail(action='hangup', sensitive=True),
            answered_by_enabled=True,
            pronunciation_guide=list(_PRONUNCIATION_GUIDE),
            webhook=_build_webhook_url(),
            metadata={
                'call_attempt_id': attempt.id,
                'hospital_id': attempt.hospital_id,
                'prompt_id': attempt.prompt_id,
                'prompt_name': attempt.prompt.name,
                'prompt_version': attempt.prompt.version,
            },
        )

        try:
            response = self.blandai.send_call(config)
        except BlandAIError as e:
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = f'BlandAI error: {e.message}'
            attempt.save()
            logger.error(
                'hospcall_calling.send_call.blandai_error',
                call_attempt_id=attempt.id,
                error_message=e.message,
            )
            return self._after_send(attempt)
        except Exception as e:
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = f'Unexpected error: {e}'
            attempt.save()
            logger.error(
                'hospcall_calling.send_call.unexpected',
                call_attempt_id=attempt.id,
                error=str(e),
                exc_info=e,
            )
            return self._after_send(attempt)

        if response.call_id:
            attempt.blandai_call_id = response.call_id

        if response.status == BlandAIResponseStatus.SUCCESS and response.call_id:
            attempt.status = CallStatus.IN_PROGRESS
        elif response.status == BlandAIResponseStatus.SUCCESS:
            # SUCCESS but no call_id: the webhook and reconcile poll both key
            # off `blandai_call_id`, so an untracked call would leave the
            # target DIALING forever. Fail it here so the sequence advances.
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = 'BlandAI returned SUCCESS without a call_id'
        else:
            attempt.status = CallStatus.FAILED
            attempt.failure_reason = response.message or 'Unknown BlandAI error'
        attempt.save()

        logger.info(
            'hospcall_calling.send_call.dispatched',
            call_attempt_id=attempt.id,
            blandai_call_id=attempt.blandai_call_id,
        )
        return self._after_send(attempt)

    def _after_send(self, attempt: CallAttempt) -> CallAttempt:
        """Advance the schedule if this send already reached a terminal state.

        A send that fails before dialing (no phone, BlandAI error, ...) ends
        the call right here, so the sequence must move on to the next
        hospital. An IN_PROGRESS send waits for the webhook/reconcile path
        (`refresh_call_attempt`) to finish it.
        """
        if attempt.status == CallStatus.FAILED:
            self._on_attempt_finished(attempt)
        return attempt

    # ── Refresh (webhook or poll → here) ───────────────────────────────────
    def refresh_call_attempt(self, *, call_attempt_id: int) -> CallAttempt:
        attempt = CallAttempt.objects.get(id=call_attempt_id)
        if not attempt.blandai_call_id:
            return attempt

        try:
            blandai_call = self.blandai.get_call(attempt.blandai_call_id)
        except BlandAIError as e:
            logger.warning(
                'hospcall_calling.refresh.blandai_error',
                call_attempt_id=attempt.id,
                error_message=e.message,
            )
            return attempt
        except Exception as e:
            logger.warning(
                'hospcall_calling.refresh.unexpected',
                call_attempt_id=attempt.id,
                error=str(e),
            )
            return attempt

        if blandai_call.recording_url:
            attempt.recording_url = blandai_call.recording_url
            if not attempt.recording_s3_key and attempt.blandai_call_id:
                try:
                    attempt.recording_s3_key = archive_recording(
                        blandai_call_id=attempt.blandai_call_id,
                        recording_url=blandai_call.recording_url,
                    )
                except RecordingsStorageError as e:
                    # Don't block the rest of the refresh — recording_url is
                    # still valid for ~7 days and the next reconcile pass will
                    # retry. Operator can also re-trigger refresh manually.
                    logger.warning(
                        'hospcall_calling.refresh.archive_failed',
                        call_attempt_id=attempt.id,
                        error=str(e),
                    )
        attempt.summary = _annotate_summary_for_voicemail(
            blandai_call.summary, blandai_call.answered_by
        )
        attempt.transcript = (
            [t.model_dump() for t in blandai_call.transcripts]
            if blandai_call.transcripts
            else []
        )
        attempt.metadata = blandai_call.metadata or {}
        if blandai_call.answered_by:
            attempt.answered_by = blandai_call.answered_by.value.upper()
        if blandai_call.call_ended_by:
            attempt.call_ended_by = blandai_call.call_ended_by.upper()
        if blandai_call.started_at:
            attempt.started_at = parse_datetime(blandai_call.started_at)
        if blandai_call.end_at:
            attempt.ended_at = parse_datetime(blandai_call.end_at)
        if attempt.started_at and attempt.ended_at:
            attempt.duration_seconds = max(
                0, int((attempt.ended_at - attempt.started_at).total_seconds())
            )

        if blandai_call.status:
            if blandai_call.status == BlandAICallStatus.COMPLETED:
                attempt.status = CallStatus.COMPLETED
            elif blandai_call.status == BlandAICallStatus.IN_PROGRESS:
                attempt.status = CallStatus.IN_PROGRESS
            elif blandai_call.status in (
                BlandAICallStatus.FAILED,
                BlandAICallStatus.NO_ANSWER,
                BlandAICallStatus.BUSY,
                BlandAICallStatus.CANCELED,
            ):
                attempt.status = CallStatus.FAILED
                attempt.failure_reason = (
                    blandai_call.error_message
                    or f'Call status: {blandai_call.status.value}'
                )

        attempt.save()

        # A terminal call advances its schedule to the next hospital. Both the
        # webhook and the reconcile poll land here; `_on_attempt_finished` is
        # idempotent so whichever runs second is a no-op.
        if attempt.status in (CallStatus.COMPLETED, CallStatus.FAILED):
            self._on_attempt_finished(attempt)
        return attempt

    # ── Reconcile (beat → here) ────────────────────────────────────────────
    # A QUEUED schedule attempt older than this had its `send_call` task lost
    # (broker/worker failure) before it dialed; reconcile re-fires it. The
    # send_call QUEUED-claim makes the re-fire safe against a late original.
    _QUEUED_RESCUE_AFTER = timedelta(minutes=5)

    def reconcile_in_progress_calls(self, *, max_rows: int = 50) -> dict:
        stuck = list(
            CallAttempt.objects.filter(status=CallStatus.IN_PROGRESS)
            .exclude(blandai_call_id='')
            .exclude(blandai_call_id__isnull=True)
            .order_by('-created_at')[:max_rows]
        )
        for attempt in stuck:
            self.refresh_call_attempt(call_attempt_id=attempt.id)

        rescued = self._rescue_stale_queued(max_rows=max_rows)
        return {'checked': len(stuck), 'rescued': rescued}

    def _rescue_stale_queued(self, *, max_rows: int) -> int:
        """Re-fire `send_call` for schedule attempts stuck QUEUED past the
        rescue window — their original task was lost before it dialed, which
        would otherwise stall the schedule on a DIALING target forever. Safe
        to re-fire: send_call only dials a still-QUEUED attempt."""
        from calling.tasks import send_call as send_call_task

        cutoff = timezone.now() - self._QUEUED_RESCUE_AFTER
        stale = list(
            CallAttempt.objects.filter(
                status=CallStatus.QUEUED,
                schedule__isnull=False,
                created_at__lt=cutoff,
            ).order_by('created_at')[:max_rows]
        )
        for attempt in stale:
            logger.warning(
                'hospcall_calling.reconcile.rescue_queued',
                call_attempt_id=attempt.id,
                schedule_id=attempt.schedule_id,
            )
            send_call_task.apply_async(kwargs={'call_attempt_id': attempt.id})
        return len(stale)


def _is_callable(hospital) -> bool:
    """Whether a hospital is eligible to be dialed by a campaign.

    Ownership scopes eligibility (DRT-5204: replaces the dropped
    `is_callable` flag). A SKIPPED schedule target is one whose hospital
    fails this check.
    """
    return bool(
        hospital
        and hospital.ownership == HospitalOwnership.INDEPENDENT
        and not hospital.excluded_reason
    )


def _resolve_voice_model(schedule: CallSchedule | None) -> tuple[str, str]:
    """Resolve the BlandAI voice + model for a call from its CallSchedule.

    voice/model are configured per schedule. `voice == VOICE_RANDOM` is a
    sentinel resolved here, *per call*, to a random member of `VOICE_POOL`
    so a campaign rotates through voices. A call with no schedule falls
    back to the settings defaults.
    """
    raw_voice = schedule.voice if schedule else None
    raw_model = schedule.model if schedule else None

    model = raw_model or settings.BLANDAI_DEFAULT_MODEL
    if not raw_voice:
        voice = settings.BLANDAI_DEFAULT_VOICE
    elif raw_voice == VOICE_RANDOM:
        voice = random.choice(VOICE_POOL)
    else:
        voice = raw_voice
    return voice, model


def _build_webhook_url() -> str | None:
    """Compose the BlandAI status webhook URL or return None when disabled.

    Form: `<BLANDAI_WEBHOOK_URL>/webhook/blandai/call_status/<SECRET>/`.
    The secret is embedded in the path so BlandAI (which doesn't sign
    outbound webhooks) authenticates implicitly via URL secrecy. Both
    settings have to be set — a half-configured pair returns None and the
    reconcile-poll path remains the only result-collection channel.
    """
    base = (settings.BLANDAI_WEBHOOK_URL or '').rstrip('/')
    secret = settings.BLANDAI_WEBHOOK_SECRET or ''
    if not base or not secret:
        return None
    return f'{base}/webhook/blandai/call_status/{secret}/'


def _annotate_summary_for_voicemail(
    summary: str | None,
    answered_by: BlandAIAnsweredBy | None,
) -> str | None:
    """Prepend an explicit marker when BlandAI says the call hit voicemail/machine.

    Backoffice readers shouldn't have to dig into `answered_by` separately to
    understand why a call ended; surface it inline at the top of the summary.
    BlandAI hangs up automatically (voicemail.action='hangup'), so no message
    is left.
    """
    if answered_by in (BlandAIAnsweredBy.VOICEMAIL, BlandAIAnsweredBy.MACHINE):
        marker = (
            f'[Detected as {answered_by.value} by BlandAI — '
            'call ended automatically, no message left.]'
        )
        return f'{marker}\n\n{summary}' if summary else marker
    return summary
