"""Archive BlandAI call recordings to S3.

BlandAI's `recording_url` is a 7-day pre-signed URL. We pull the bytes once
during reconciliation and persist them to `RECORDINGS_BUCKET_NAME` so they
survive past the BlandAI window. Backoffice viewers continue to use the
original BlandAI URL while it's valid; once expired, recordings can be
fetched directly from S3 by the operator.
"""

from __future__ import annotations

import boto3
import httpx
import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)

_DOWNLOAD_TIMEOUT_SECONDS = 30
_DEFAULT_CONTENT_TYPE = 'audio/mpeg'
# Long enough for an operator to listen and jot a few comments; short enough
# that a leaked URL ages out. The backoffice re-fetches per page view.
_PRESIGN_EXPIRY_SECONDS = 60 * 60


class RecordingsStorageError(Exception):
    """Raised when archiving fails. Caller decides whether to retry."""


_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3', region_name=settings.AWS_REGION)
    return _s3_client


def archive_recording(*, blandai_call_id: str, recording_url: str) -> str:
    """Stream the BlandAI recording into S3. Returns the saved object key.

    Raises `RecordingsStorageError` if the bucket isn't configured, the
    download fails, or the upload fails. Caller should swallow + log so the
    rest of `refresh_call_attempt` still completes.
    """
    bucket = getattr(settings, 'RECORDINGS_BUCKET_NAME', '')
    if not bucket:
        raise RecordingsStorageError('RECORDINGS_BUCKET_NAME is not set')

    key = f'recordings/{blandai_call_id}.mp3'

    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_SECONDS) as client:
            response = client.get(recording_url)
            response.raise_for_status()
            audio_bytes = response.content
    except httpx.HTTPError as e:
        raise RecordingsStorageError(
            f'Failed to download recording: {e}'
        ) from e

    try:
        _get_s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=audio_bytes,
            ContentType=_DEFAULT_CONTENT_TYPE,
        )
    except Exception as e:
        raise RecordingsStorageError(f'Failed to upload to S3: {e}') from e

    logger.info(
        'recordings.archived',
        blandai_call_id=blandai_call_id,
        bucket=bucket,
        key=key,
        size_bytes=len(audio_bytes),
    )
    return key


def presign_recording(
    s3_key: str, *, expires_in: int = _PRESIGN_EXPIRY_SECONDS
) -> str:
    """Return a short-lived presigned GET URL for an archived recording.

    Lets the backoffice call-log player keep working after BlandAI's 7-day
    `recording_url` expires. Raises `RecordingsStorageError` if the bucket
    isn't configured, the key is empty, or presigning fails — the caller
    falls back to the BlandAI URL.
    """
    bucket = getattr(settings, 'RECORDINGS_BUCKET_NAME', '')
    if not bucket:
        raise RecordingsStorageError('RECORDINGS_BUCKET_NAME is not set')
    if not s3_key:
        raise RecordingsStorageError('s3_key is empty')

    try:
        return _get_s3_client().generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        raise RecordingsStorageError(
            f'Failed to presign recording: {e}'
        ) from e
