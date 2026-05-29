"""Pure-function tests for `services.internal.hospcall_calling.service`.

Run: `env=test make test tests/unit/test_hospcall_calling_service.py`
"""

import pytest

from calling.models import CallSchedule
from calling.vars import VOICE_POOL
from services.external.blandai import BlandAIAnsweredBy
from services.internal.hospcall_calling.service import (
    _annotate_summary_for_voicemail,
    _resolve_voice_model,
)


class TestAnnotateSummaryForVoicemail:
    """`_annotate_summary_for_voicemail` is the seam where the BlandAI
    `answered_by` signal becomes a human-readable surface in the backoffice.
    Wrong behaviour silently corrupts call labels, so all five branches are pinned.
    """

    @pytest.mark.parametrize(
        'answered_by',
        [BlandAIAnsweredBy.VOICEMAIL, BlandAIAnsweredBy.MACHINE],
    )
    def test_marker_prepended_when_summary_present(self, answered_by):
        result = _annotate_summary_for_voicemail('rang then went to vm', answered_by)
        assert result is not None
        assert result.startswith(f'[Detected as {answered_by.value} by BlandAI')
        assert result.endswith('rang then went to vm')
        assert '\n\n' in result

    @pytest.mark.parametrize(
        'answered_by',
        [BlandAIAnsweredBy.VOICEMAIL, BlandAIAnsweredBy.MACHINE],
    )
    def test_marker_only_when_summary_is_none(self, answered_by):
        result = _annotate_summary_for_voicemail(None, answered_by)
        assert result is not None
        assert result.startswith(f'[Detected as {answered_by.value} by BlandAI')
        assert '\n\n' not in result

    def test_human_passes_summary_through_unchanged(self):
        assert (
            _annotate_summary_for_voicemail('normal call', BlandAIAnsweredBy.HUMAN)
            == 'normal call'
        )

    def test_unknown_passes_summary_through_unchanged(self):
        assert (
            _annotate_summary_for_voicemail('partial', BlandAIAnsweredBy.UNKNOWN)
            == 'partial'
        )

    def test_no_answered_by_returns_summary_unchanged(self):
        assert _annotate_summary_for_voicemail('partial', None) == 'partial'

    def test_no_answered_by_and_no_summary_returns_none(self):
        assert _annotate_summary_for_voicemail(None, None) is None


class TestResolveVoiceModel:
    """`_resolve_voice_model` reads voice/model off a `CallSchedule`.

    The `random` sentinel must resolve to a pooled voice *per call*; a missing
    schedule must fall back to the settings defaults.
    """

    def test_fixed_voice_returns_it(self):
        schedule = CallSchedule(voice='ryan', model='turbo')
        voice, model = _resolve_voice_model(schedule)
        assert voice == 'ryan'
        assert model == 'turbo'

    def test_random_voice_resolves_to_pool_member(self):
        schedule = CallSchedule(voice='random', model='base')
        voice, model = _resolve_voice_model(schedule)
        assert voice in VOICE_POOL
        assert model == 'base'

    def test_none_schedule_falls_back_to_settings_defaults(self, settings):
        settings.BLANDAI_DEFAULT_VOICE = 'maya'
        settings.BLANDAI_DEFAULT_MODEL = 'base'
        voice, model = _resolve_voice_model(None)
        assert voice == 'maya'
        assert model == 'base'

    def test_model_passes_through(self):
        schedule = CallSchedule(voice='ryan', model='turbo')
        _, model = _resolve_voice_model(schedule)
        assert model == 'turbo'
