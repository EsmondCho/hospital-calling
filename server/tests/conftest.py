"""Shared pytest fixtures.

Per `testing.md`, fixtures should be defined once and shared across
tests rather than re-declared inline.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def no_celery_dispatch(mocker):
    """Block real Celery enqueue from the sourcing pipeline.

    Used by every integration test that exercises the HTTP edge or the
    service layer — we want to assert on `SourcingJob` row state, not
    on whether tasks actually ran on a worker.
    """

    return mocker.patch(
        'services.internal.sourcing.tasks.start_job.apply_async'
    )
