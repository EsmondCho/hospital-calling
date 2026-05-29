"""Unit tests for BlandAI request schemas (`services/external/blandai/schemas.py`)."""

from __future__ import annotations

from services.external.blandai import BlandAIPronunciation


def test_pronunciation_serializes_without_optional_fields():
    # `exclude_none` must drop the unset case_sensitive / spaced so the
    # BlandAI payload carries only word + pronunciation (BlandAI defaults
    # both omitted fields to false).
    data = BlandAIPronunciation(
        word='Dr.Tail', pronunciation='Doctor Tail',
    ).model_dump(exclude_none=True)

    assert data == {'word': 'Dr.Tail', 'pronunciation': 'Doctor Tail'}
    assert 'case_sensitive' not in data
    assert 'spaced' not in data
