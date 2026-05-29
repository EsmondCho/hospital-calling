"""Unit tests for `should_exclude` — a pure function over the Google Places
payload shape (no DB).

`match_chain` is DB-backed (reads the ChainKeyword table) so its tests live
in `tests/integration/test_chain_keyword_rules.py`.
"""

from __future__ import annotations

from hospital.vars import HospitalOwnership
from services.internal.sourcing.rules import should_exclude


def _place(name: str, *, types=None, primary_type='veterinary_care', business_status='OPERATIONAL') -> dict:
    return {
        'displayName': {'text': name},
        'types': types if types is not None else ['veterinary_care', 'point_of_interest'],
        'primaryType': primary_type,
        'businessStatus': business_status,
    }


def test_should_exclude_keeps_normal_vet_clinic() -> None:
    decision = should_exclude(_place('Sunset Pet Hospital'))
    assert decision.reason is None
    assert decision.suggested_ownership is None


def test_should_exclude_drops_closed_locations() -> None:
    decision = should_exclude(_place('Closed Clinic', business_status='CLOSED_PERMANENTLY'))
    assert decision.reason == 'not_operational'


def test_should_exclude_drops_unnamed_rows() -> None:
    raw = _place('')
    raw['displayName'] = {}
    decision = should_exclude(raw)
    assert decision.reason == 'no_name'


def test_should_exclude_drops_non_clinic_by_name() -> None:
    decision = should_exclude(_place('Friendly Pet Store'))
    assert decision.reason == 'non_clinic'


def test_should_exclude_drops_when_vet_type_absent() -> None:
    decision = should_exclude(_place('Just a Shop', types=['point_of_interest'], primary_type='store'))
    assert decision.reason == 'no_vet_type'


def test_should_exclude_keeps_nonprofit_with_nonprofit_ownership() -> None:
    decision = should_exclude(_place('Brooklyn Animal Rescue', types=['veterinary_care']))
    assert decision.reason is None
    assert decision.suggested_ownership == HospitalOwnership.NONPROFIT
