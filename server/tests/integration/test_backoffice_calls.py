"""Integration tests for the backoffice call-log endpoints: starring,
comments, and the recording-playback URL.

Run: `env=test make test tests/integration/test_backoffice_calls.py`
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from calling.models import CallAttempt, CallComment
from calling.vars import CallStatus
from hospital.models import Hospital
from hospital.vars import HospitalSource

TOKEN = 'test-token-deadbeef'

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _backoffice_token(settings):
    settings.BACKOFFICE_API_TOKEN = TOKEN


@pytest.fixture
def hospital() -> Hospital:
    return Hospital.objects.create(
        name='Test Vet', source=HospitalSource.MANUAL.value,
        phone_e164='+15551234567',
    )


@pytest.fixture
def attempt(hospital) -> CallAttempt:
    return CallAttempt.objects.create(
        hospital=hospital, status=CallStatus.COMPLETED
    )


# ── starring ─────────────────────────────────────────────────────────────────


def test_list_carries_is_starred(api_client, attempt):
    response = api_client.get('/backoffice/calls/')
    assert response.status_code == 200
    assert response.json()['results'][0]['is_starred'] is False


def test_patch_star_requires_token(api_client, attempt):
    response = api_client.patch(
        f'/backoffice/calls/{attempt.id}/',
        {'is_starred': True},
        format='json',
    )
    assert response.status_code in (401, 403)
    attempt.refresh_from_db()
    assert attempt.is_starred is False


def test_patch_star_toggles(api_client, attempt):
    response = api_client.patch(
        f'/backoffice/calls/{attempt.id}/',
        {'is_starred': True},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 200, response.content
    assert response.json()['is_starred'] is True
    attempt.refresh_from_db()
    assert attempt.is_starred is True


def test_starred_filter(api_client, hospital):
    starred = CallAttempt.objects.create(
        hospital=hospital, status=CallStatus.COMPLETED, is_starred=True
    )
    CallAttempt.objects.create(hospital=hospital, status=CallStatus.COMPLETED)
    response = api_client.get('/backoffice/calls/?starred=true')
    assert response.status_code == 200
    ids = [row['id'] for row in response.json()['results']]
    assert ids == [starred.id]


# ── comments ─────────────────────────────────────────────────────────────────


def test_add_and_list_comments(api_client, attempt):
    create = api_client.post(
        f'/backoffice/calls/{attempt.id}/comments/',
        {'body': 'first note'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='esmond',
    )
    assert create.status_code == 201, create.content
    assert create.json()['author'] == 'esmond'
    api_client.post(
        f'/backoffice/calls/{attempt.id}/comments/',
        {'body': 'second note'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='rayer',
    )
    listing = api_client.get(f'/backoffice/calls/{attempt.id}/comments/')
    assert listing.status_code == 200
    rows = listing.json()
    assert [c['body'] for c in rows] == ['second note', 'first note']  # newest first
    assert [c['author'] for c in rows] == ['rayer', 'esmond']


def test_list_comments_unknown_call_404(api_client):
    response = api_client.get('/backoffice/calls/999999/comments/')
    assert response.status_code == 404


def test_put_call_not_allowed(api_client, attempt):
    # The detail view is star-only PATCH — full-replace PUT is disallowed.
    response = api_client.put(
        f'/backoffice/calls/{attempt.id}/',
        {'is_starred': True},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 405


def test_add_comment_requires_token(api_client, attempt):
    response = api_client.post(
        f'/backoffice/calls/{attempt.id}/comments/',
        {'body': 'nope'},
        format='json',
    )
    assert response.status_code in (401, 403)
    assert CallComment.objects.count() == 0


def test_empty_comment_rejected(api_client, attempt):
    response = api_client.post(
        f'/backoffice/calls/{attempt.id}/comments/',
        {'body': '   '},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 400


def test_comment_on_unknown_call_404(api_client):
    response = api_client.post(
        '/backoffice/calls/999999/comments/',
        {'body': 'note'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert response.status_code == 404


def test_delete_own_comment(api_client, attempt):
    comment = CallComment.objects.create(
        call_attempt=attempt, body='bye', author='esmond'
    )
    response = api_client.delete(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='esmond',
    )
    assert response.status_code == 204
    assert not CallComment.objects.filter(id=comment.id).exists()


def test_delete_other_users_comment_forbidden(api_client, attempt):
    comment = CallComment.objects.create(
        call_attempt=attempt, body='mine', author='esmond'
    )
    response = api_client.delete(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='rayer',
    )
    assert response.status_code == 403
    assert CallComment.objects.filter(id=comment.id).exists()


def test_edit_own_comment(api_client, attempt):
    comment = CallComment.objects.create(
        call_attempt=attempt, body='v1', author='esmond'
    )
    response = api_client.patch(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        {'body': 'v2'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='esmond',
    )
    assert response.status_code == 200, response.content
    comment.refresh_from_db()
    assert comment.body == 'v2'


def test_edit_other_users_comment_forbidden(api_client, attempt):
    comment = CallComment.objects.create(
        call_attempt=attempt, body='v1', author='esmond'
    )
    response = api_client.patch(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        {'body': 'hacked'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='rayer',
    )
    assert response.status_code == 403
    comment.refresh_from_db()
    assert comment.body == 'v1'


def test_legacy_authorless_comment_not_editable(api_client, attempt):
    # Comments written before accounts (author='') are owned by nobody —
    # neither a proxy-bypass (no user header) nor an authed user may touch them.
    comment = CallComment.objects.create(
        call_attempt=attempt, body='legacy', author=''
    )
    no_user = api_client.patch(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        {'body': 'tampered'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
    )
    assert no_user.status_code == 403
    authed = api_client.delete(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='esmond',
    )
    assert authed.status_code == 403
    assert CallComment.objects.filter(id=comment.id).exists()


def test_edit_comment_on_deleted_call_404(api_client, attempt):
    comment = CallComment.objects.create(
        call_attempt=attempt, body='x', author='esmond'
    )
    attempt.is_deleted = True
    attempt.save(update_fields=['is_deleted'])
    response = api_client.patch(
        f'/backoffice/calls/{attempt.id}/comments/{comment.id}/',
        {'body': 'y'},
        format='json',
        HTTP_X_BACKOFFICE_TOKEN=TOKEN,
        HTTP_X_BACKOFFICE_USER='esmond',
    )
    assert response.status_code == 404


def test_list_carries_comment_count(api_client, hospital):
    a = CallAttempt.objects.create(hospital=hospital, status=CallStatus.COMPLETED)
    CallComment.objects.create(call_attempt=a, body='one', author='esmond')
    CallComment.objects.create(call_attempt=a, body='two', author='rayer')
    response = api_client.get('/backoffice/calls/')
    assert response.status_code == 200
    row = next(r for r in response.json()['results'] if r['id'] == a.id)
    assert row['comment_count'] == 2


def test_detail_carries_comment_count(api_client, attempt):
    # The detail view isn't annotated, so this exercises the obj.comments
    # COUNT fallback in get_comment_count.
    CallComment.objects.create(call_attempt=attempt, body='note', author='esmond')
    response = api_client.get(f'/backoffice/calls/{attempt.id}/')
    assert response.status_code == 200
    assert response.json()['comment_count'] == 1


def test_calls_list_is_page_numbered(api_client, attempt):
    response = api_client.get('/backoffice/calls/')
    assert response.status_code == 200
    body = response.json()
    # Page-number pagination exposes a total `count` (cursor pagination didn't).
    assert 'count' in body
    assert body['count'] >= 1


# ── recording ────────────────────────────────────────────────────────────────


def test_recording_presigns_s3_archive(api_client, hospital, mocker):
    attempt = CallAttempt.objects.create(
        hospital=hospital,
        status=CallStatus.COMPLETED,
        recording_s3_key='recordings/abc.mp3',
        recording_url='https://blandai.example/abc.mp3',
    )
    mocker.patch(
        'api.backoffice.calls.views.presign_recording',
        return_value='https://s3.example/presigned',
    )
    response = api_client.get(f'/backoffice/calls/{attempt.id}/recording/')
    assert response.status_code == 200
    assert response.json()['url'] == 'https://s3.example/presigned'


def test_recording_falls_back_to_blandai_url(api_client, hospital):
    attempt = CallAttempt.objects.create(
        hospital=hospital,
        status=CallStatus.COMPLETED,
        recording_url='https://blandai.example/abc.mp3',
    )
    response = api_client.get(f'/backoffice/calls/{attempt.id}/recording/')
    assert response.status_code == 200
    assert response.json()['url'] == 'https://blandai.example/abc.mp3'


def test_recording_null_when_none(api_client, attempt):
    response = api_client.get(f'/backoffice/calls/{attempt.id}/recording/')
    assert response.status_code == 200
    assert response.json()['url'] is None
