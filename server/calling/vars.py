from utils.enums import StrEnum


class CallScheduleStatus(StrEnum):
    PENDING = 'PENDING'        # waiting for scheduled_at
    DISPATCHED = 'DISPATCHED'  # eta arrived; dialing the hospital sequence
    COMPLETED = 'COMPLETED'    # every target hospital has been dialed / skipped
    SKIPPED = 'SKIPPED'        # nothing callable in the sequence
    CANCELED = 'CANCELED'


class ScheduleTargetStatus(StrEnum):
    """Per-hospital step state inside a CallSchedule's dial sequence.

    A schedule fans out to its `CallScheduleHospital` targets in `order`.
    The eta dials the first PENDING+callable target (DIALING); when that
    call reaches a terminal status the step flips to DONE and the next
    target is dialed. Targets not eligible for the campaign go straight to
    SKIPPED without a call. Tracking it here makes the advance idempotent
    against a double webhook+reconcile refresh.
    """

    PENDING = 'PENDING'    # not yet reached
    DIALING = 'DIALING'    # CallAttempt created + in flight
    DONE = 'DONE'          # CallAttempt reached a terminal status
    SKIPPED = 'SKIPPED'    # hospital not callable — no call placed


class CallStatus(StrEnum):
    QUEUED = 'QUEUED'              # we sent send_call but no provider id yet
    IN_PROGRESS = 'IN_PROGRESS'    # provider accepted & is dialing/talking
    COMPLETED = 'COMPLETED'        # provider says completed
    FAILED = 'FAILED'              # provider error / busy / no-answer / etc.


class CallEndedBy(StrEnum):
    ASSISTANT = 'ASSISTANT'
    USER = 'USER'
    UNKNOWN = 'UNKNOWN'


class AnsweredBy(StrEnum):
    HUMAN = 'HUMAN'
    VOICEMAIL = 'VOICEMAIL'
    MACHINE = 'MACHINE'
    UNKNOWN = 'UNKNOWN'


class CallModel(StrEnum):
    """BlandAI call model. `base` = full-featured (default); `turbo` =
    lower latency but fewer features. Per BlandAI POST /v1/calls docs."""

    BASE = 'base'
    TURBO = 'turbo'


# Curated BlandAI voice pool for outbound calls. A CallSchedule with
# `voice == VOICE_RANDOM` is resolved to a random member of this pool
# *per call* at dispatch time, so a campaign rotates through voices.
# Each entry is the exact BlandAI voice identifier — case-sensitive, so
# the mixed casing ('Nat'/'June' capitalized) is intentional, matching
# the BlandAI voice catalog.
VOICE_POOL = ('ryan', 'david', 'mason', 'Nat', 'June', 'adriana', 'maya')

# Sentinel stored in `CallSchedule.voice` meaning "pick randomly from the
# pool on each call". Not a real BlandAI voice.
VOICE_RANDOM = 'random'

# Accepted values for `CallSchedule.voice` (schedule create API + UI).
VOICE_CHOICES = (VOICE_RANDOM, *VOICE_POOL)
