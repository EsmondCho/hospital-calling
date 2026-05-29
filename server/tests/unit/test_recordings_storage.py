"""Unit tests for `services.internal.recordings.storage.archive_recording`.

Run: `env=test make test tests/unit/test_recordings_storage.py`
"""

import httpx
import pytest
from django.test import override_settings

from services.internal.recordings import storage as recordings_storage
from services.internal.recordings.storage import (
    RecordingsStorageError,
    archive_recording,
)


@pytest.fixture(autouse=True)
def reset_s3_singleton():
    """Each test gets a clean S3 client cache so mocks don't leak across cases."""
    recordings_storage._s3_client = None
    yield
    recordings_storage._s3_client = None


@override_settings(RECORDINGS_BUCKET_NAME='hospcall-call-recordings-prod')
def test_archive_recording_uploads_and_returns_key(mocker):
    audio = b'\xff\xfb\x90\x00fake-mp3-bytes'
    httpx_get = mocker.patch.object(
        httpx.Client, 'get',
        return_value=mocker.Mock(content=audio, raise_for_status=mocker.Mock()),
    )
    s3 = mocker.Mock()
    mocker.patch.object(recordings_storage, '_get_s3_client', return_value=s3)

    key = archive_recording(
        blandai_call_id='call-abc-123',
        recording_url='https://blandai.example/recordings/abc.mp3',
    )

    assert key == 'recordings/call-abc-123.mp3'
    httpx_get.assert_called_once_with(
        'https://blandai.example/recordings/abc.mp3'
    )
    s3.put_object.assert_called_once_with(
        Bucket='hospcall-call-recordings-prod',
        Key='recordings/call-abc-123.mp3',
        Body=audio,
        ContentType='audio/mpeg',
    )


@override_settings(RECORDINGS_BUCKET_NAME='')
def test_archive_recording_raises_when_bucket_not_configured(mocker):
    s3 = mocker.Mock()
    mocker.patch.object(recordings_storage, '_get_s3_client', return_value=s3)

    with pytest.raises(RecordingsStorageError, match='RECORDINGS_BUCKET_NAME'):
        archive_recording(blandai_call_id='c', recording_url='https://x/y')

    s3.put_object.assert_not_called()


@override_settings(RECORDINGS_BUCKET_NAME='hospcall-call-recordings-prod')
def test_archive_recording_raises_on_download_failure(mocker):
    mocker.patch.object(
        httpx.Client, 'get',
        side_effect=httpx.ConnectError('boom'),
    )
    s3 = mocker.Mock()
    mocker.patch.object(recordings_storage, '_get_s3_client', return_value=s3)

    with pytest.raises(RecordingsStorageError, match='download'):
        archive_recording(blandai_call_id='c', recording_url='https://x/y')

    s3.put_object.assert_not_called()


@override_settings(RECORDINGS_BUCKET_NAME='hospcall-call-recordings-prod')
def test_archive_recording_raises_on_s3_upload_failure(mocker):
    mocker.patch.object(
        httpx.Client, 'get',
        return_value=mocker.Mock(content=b'x', raise_for_status=mocker.Mock()),
    )
    s3 = mocker.Mock()
    s3.put_object.side_effect = RuntimeError('access denied')
    mocker.patch.object(recordings_storage, '_get_s3_client', return_value=s3)

    with pytest.raises(RecordingsStorageError, match='upload'):
        archive_recording(blandai_call_id='c', recording_url='https://x/y')
