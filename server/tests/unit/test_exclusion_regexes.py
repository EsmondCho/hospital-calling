"""Coverage for the rule-stage exclusion regexes (`hospital/rules/exclusion.py`).

These are pure module-level constants — no DB. The chain keyword table
itself is now the `hospital.ChainKeyword` model; see
`tests/unit/test_sourcing_rules.py` for `match_chain` coverage.
"""

from __future__ import annotations

import pytest

from hospital.rules.exclusion import NON_CLINIC_REGEX, NONPROFIT_REGEX


@pytest.mark.parametrize(
    'name',
    [
        'Friendly Pet Store',
        'Downtown Pet Supplies',
        'Top Dog Grooming Only',
        'Animal Compounding Pharmacy',
        # Manufacturers / distributors / wholesalers / labs — never call targets.
        'Acme Pharmaceutical',
        'Foo Animal Distributors',
        'Diamond Pet Foods Manufacturing',
        'Midwest Veterinary Wholesale',
        'Heartland Diagnostic Laboratory',
        'Zoetis Biologics',
    ],
)
def test_non_clinic_regex_catches(name: str) -> None:
    assert NON_CLINIC_REGEX.search(name) is not None


@pytest.mark.parametrize(
    'name',
    [
        'Shore SPCA',
        'Brooklyn Animal Rescue',
        'County Animal Shelter',
        'Humane Society of Boulder',
    ],
)
def test_nonprofit_regex_catches(name: str) -> None:
    assert NONPROFIT_REGEX.search(name) is not None


def test_exclusion_regexes_do_not_eat_real_clinics() -> None:
    # A real vet clinic name shouldn't trip either exclusion regex.
    for ok in ['Sunset Pet Hospital', 'VCA Westside Animal Hospital']:
        assert NON_CLINIC_REGEX.search(ok) is None
        assert NONPROFIT_REGEX.search(ok) is None


def test_non_clinic_regex_allows_clinic_with_laboratory_stem_in_name() -> None:
    # `\blaboratory\b` matches only the standalone word "laboratory", so a real
    # clinic whose name carries a laboratory *stem* word (e.g. the plural
    # "Laboratories") is not excluded (P3-b). The pre-fix `\blaborator` stem
    # would have false-positived on these.
    for ok in [
        'Northwest Animal Hospital & Laboratories',
        'Animal Hospital Laboratorium',
    ]:
        assert NON_CLINIC_REGEX.search(ok) is None
