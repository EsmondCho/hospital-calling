"""Pydantic schemas mirroring the BlandAI v1 REST contract.

Trimmed from drtail-server2's `services/external/blandai/schemas.py` — only
the fields HOSPCALL actually consumes are kept. Add more on demand.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BlandAIResponseStatus(str, Enum):
    SUCCESS = 'success'
    ERROR = 'error'


class BlandAICallStatus(str, Enum):
    COMPLETED = 'completed'
    FAILED = 'failed'
    BUSY = 'busy'
    NO_ANSWER = 'no-answer'
    CANCELED = 'canceled'
    UNKNOWN = 'unknown'
    IN_PROGRESS = 'in-progress'


class BlandAIAnsweredBy(str, Enum):
    HUMAN = 'human'
    VOICEMAIL = 'voicemail'
    MACHINE = 'machine'
    UNKNOWN = 'unknown'


class BlandAITranscript(BaseModel):
    id: int
    created_at: str
    text: str
    user: str


class BlandAIVoicemail(BaseModel):
    """Voicemail handling config for outbound calls.

    HOSPCALL uses `action='hangup'` (we don't leave messages — voicemails are
    treated as failed contact attempts) with `sensitive=True` (LLM-based
    detection) for accuracy.
    """

    action: Literal['hangup', 'leave_message', 'ignore'] | None = None
    message: str | None = None      # only used when action == "leave_message"
    sensitive: bool | None = None   # LLM-based detection (more accurate, costs more)


class BlandAIPronunciation(BaseModel):
    """One entry in BlandAI's `pronunciation_guide` — tells the agent how to
    say a specific word/brand (e.g. "Dr.Tail" → "Doctor Tail"). See
    POST /v1/calls. `case_sensitive`/`spaced` are left unset (BlandAI
    defaults both to false) and dropped by `exclude_none` serialization."""

    word: str
    pronunciation: str
    case_sensitive: bool | None = None
    spaced: bool | None = None


class BlandAICallConfig(BaseModel):
    """Subset of BlandAI POST /v1/calls request body."""

    model_config = ConfigDict(populate_by_name=True)

    phone_number: str
    task: str | None = Field(default=None, max_length=4000)
    voice: str | None = None
    model: str | None = None
    language: str | None = None
    wait_for_greeting: bool | None = None
    record: bool | None = None
    max_duration: int | None = None
    webhook: str | None = None
    metadata: dict[str, Any] | None = None
    from_: str | None = Field(default=None, alias='from')
    voicemail: BlandAIVoicemail | None = None
    answered_by_enabled: bool | None = None
    pronunciation_guide: list[BlandAIPronunciation] | None = None


class BlandAICallResponse(BaseModel):
    status: BlandAIResponseStatus
    message: str | None = None
    call_id: str | None = None


class BlandAICall(BaseModel):
    """Subset of GET /v1/calls/<id> response."""

    model_config = ConfigDict(populate_by_name=True)

    call_id: str
    call_length: float | None = None
    to: str | None = None
    from_: str | None = Field(default=None, alias='from')
    completed: bool | None = None
    created_at: str | None = None
    started_at: str | None = None
    end_at: str | None = None
    error_message: str | None = None
    answered_by: BlandAIAnsweredBy | None = None
    recording_url: str | None = None
    metadata: dict[str, Any] | None = None
    summary: str | None = None
    concatenated_transcript: str | None = None
    transcripts: list[BlandAITranscript] | None = None
    status: BlandAICallStatus | None = None
    call_ended_by: str | None = None
    corrected_duration: str | None = None


class BlandAIError(Exception):
    def __init__(
        self,
        status: BlandAIResponseStatus,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details
