"""Unit tests for the practice-dedup pure helpers (DRT-5297).

`_is_toll_free` and `_is_practitioner_name` are module-level pure functions in
`services.internal.sourcing.tasks` — no DB, no Celery. The DB-backed sibling
lookup + merge path is covered in `tests/integration/test_sourcing_tasks.py`.
"""

from __future__ import annotations

import pytest

from services.internal.sourcing.tasks import _is_practitioner_name, _is_toll_free

# ---- _is_practitioner_name -------------------------------------------------

@pytest.mark.parametrize(
    'name',
    [
        'Dr. Brian Martz',
        'Halligan Lori DVM',
        'Iowa Veterinary Specialties: Nestor Derek D DVM',
        'Jane Smith, DVM',
        'Dr Pat OBrien',          # "Dr" without the trailing dot
    ],
)
def test_is_practitioner_name_true(name: str) -> None:
    assert _is_practitioner_name(name) is True


@pytest.mark.parametrize(
    'name',
    [
        'Starch Pet Hospital',
        'Union Animal Hospital',
        'VCA Westside Animal Hospital',
        "Dr. Marc's Animal Clinic",       # clinic name leading with "Dr." (P2-1)
        "Dr. Smith's Pet Hospital",       # clinic name leading with "Dr." (P2-1)
        'Dr. Jones Veterinary Center',    # clinic name leading with "Dr." (P2-1)
        "Dr. Smith's Veterinary Practice",  # clinic name leading with "Dr." (P3-a)
        '',
        None,
    ],
)
def test_is_practitioner_name_false(name: str | None) -> None:
    assert _is_practitioner_name(name) is False


# ---- _is_toll_free ---------------------------------------------------------

@pytest.mark.parametrize(
    'e164',
    ['+18005551234', '+18885551234', '+18335551234', '+18225551234'],
)
def test_is_toll_free_true(e164: str) -> None:
    assert _is_toll_free(e164) is True


@pytest.mark.parametrize(
    'e164',
    ['+15095551234', '+12125551234', '+447911123456', '', None],
)
def test_is_toll_free_false(e164: str | None) -> None:
    assert _is_toll_free(e164) is False
