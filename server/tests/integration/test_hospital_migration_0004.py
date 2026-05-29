"""Verify migration 0004 backfilled the seeded dummy hospitals.

The dummy data lives in `calling/migrations/0002_seed_dummy_data.py`:
- dummy-1..4 — legacy LOCAL
- dummy-5    — legacy CHAIN (VCA Westside)
- dummy-6    — legacy ER_OR_URGENT (Citywide Pet Emergency)

0004 mapped the (now-dropped) `category` column to the 3-axis taxonomy.
Rows are identified by `source_external_id` here because the legacy
`category` column was removed in migration 0006.
"""

from __future__ import annotations

import pytest

from hospital.models import Hospital
from hospital.vars import (
    HospitalAppointmentMode,
    HospitalOwnership,
    HospitalServiceTag,
    HospitalSource,
)

LOCAL_DUMMY_IDS = ['dummy-1', 'dummy-2', 'dummy-3', 'dummy-4']


@pytest.mark.django_db
def test_local_dummies_map_to_independent_general_practice() -> None:
    locals_ = Hospital.objects.filter(
        source=HospitalSource.MANUAL,
        source_external_id__in=LOCAL_DUMMY_IDS,
    )
    assert locals_.count() == 4
    for h in locals_:
        assert h.ownership == HospitalOwnership.INDEPENDENT
        assert h.service_tags == [HospitalServiceTag.GENERAL_PRACTICE]
        assert h.appointment_mode == HospitalAppointmentMode.UNKNOWN
        assert h.label_locked is False


@pytest.mark.django_db
def test_chain_dummy_maps_to_chain_ownership() -> None:
    h = Hospital.objects.get(
        source=HospitalSource.MANUAL, source_external_id='dummy-5',
    )
    assert h.ownership == HospitalOwnership.CHAIN
    assert h.service_tags == [HospitalServiceTag.GENERAL_PRACTICE]


@pytest.mark.django_db
def test_er_dummy_keeps_emergency_service_drops_owner_axis() -> None:
    h = Hospital.objects.get(
        source=HospitalSource.MANUAL, source_external_id='dummy-6',
    )
    # Information loss intentional: owner axis unknown for legacy ER rows.
    assert h.ownership == HospitalOwnership.UNCLASSIFIED
    assert h.service_tags == [HospitalServiceTag.EMERGENCY]
    assert h.appointment_mode == HospitalAppointmentMode.UNKNOWN
