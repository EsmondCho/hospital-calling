"""Integration tests for `match_chain` — reads the `ChainKeyword` table
(seeded by migration 0007)."""

from __future__ import annotations

import pytest

from hospital.vars import HospitalOwnership, HospitalServiceTag
from services.internal.sourcing.rules import RuleLabel, match_chain

pytestmark = pytest.mark.django_db


def test_match_chain_hit_returns_full_label() -> None:
    label = match_chain('VCA Westside Animal Hospital')
    assert label.matched is True
    assert label.ownership == HospitalOwnership.MARS_VH
    assert HospitalServiceTag.GENERAL_PRACTICE in label.service_tags
    assert HospitalServiceTag.EMERGENCY in label.service_tags
    assert label.chain_brand_normalized == 'vca'


def test_match_chain_weak_brand_still_matches_on_literal_name() -> None:
    # VetCor-owned clinics usually keep a local name, but a literal
    # "VetCor" in the name still matches.
    label = match_chain('VetCor of Ohio')
    assert label.matched is True
    assert label.chain_brand_normalized == 'vetcor'


def test_match_chain_no_hit_returns_empty() -> None:
    label = match_chain('Sunset Pet Hospital')
    assert label == RuleLabel.empty()
    assert label.matched is False
    assert label.ownership == HospitalOwnership.UNCLASSIFIED
    assert label.service_tags == ()


def test_match_chain_skips_possessive_banfield_false_positive() -> None:
    # `\bBanfield\b(?!'s)` — possessive "Banfield's" must not match.
    label = match_chain("Dr. Banfield's Family Vet")
    assert label.matched is False


def test_match_chain_veg_requires_full_name() -> None:
    # The `veg` row uses the full "Veterinary Emergency Group" — the bare
    # syllable in "Vegetarian" must not match.
    label = match_chain('Vegetarian Pet Cafe')
    assert label.matched is False
