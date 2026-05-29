"""Rule-stage labelling and exclusion for the sourcing pipeline (DRT-5204 §3.2).

The deterministic first pass: chain-name regex (the `hospital.ChainKeyword`
DB table) + Google `businessStatus` / name checks. The LLM stage in
`classifier.py` reads `RuleLabel` and either confirms or overrides it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from hospital.rules.exclusion import NON_CLINIC_REGEX, NONPROFIT_REGEX
from hospital.vars import HospitalAppointmentMode, HospitalOwnership, HospitalServiceTag

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RuleLabel:
    """A single chain-rule hit, or the empty no-hit case."""

    ownership: HospitalOwnership = HospitalOwnership.UNCLASSIFIED
    service_tags: tuple[HospitalServiceTag, ...] = ()
    appointment_mode: HospitalAppointmentMode = HospitalAppointmentMode.UNKNOWN
    chain_brand_normalized: str | None = None
    matched: bool = False

    @classmethod
    def empty(cls) -> 'RuleLabel':
        return cls()


@dataclass(frozen=True)
class ExclusionDecision:
    """`reason=None` means keep the row."""

    reason: str | None = None
    suggested_ownership: HospitalOwnership | None = None


def match_chain(name: str) -> RuleLabel:
    """Regex-match `name` against the ChainKeyword table.

    First hit wins; the table's `Meta.ordering` (match_priority, id) means
    a more specific pattern can be ordered ahead of a broader one. The
    table is small (~20 rows) so a query per call is cheap; sourcing is
    bottlenecked on the Google + LLM calls, not this.
    """

    # Imported here, not at module load, so this usecase module doesn't pull
    # the model at import time.
    from hospital.models import ChainKeyword

    for kw in ChainKeyword.objects.all():
        try:
            hit = re.search(kw.regex_pattern, name, re.IGNORECASE)
        except re.error:
            # An operator can save a malformed regex via the admin console.
            # Skip that row rather than crash the whole sourcing run.
            logger.warning(
                'sourcing.match_chain.invalid_regex',
                chain_brand_normalized=kw.chain_brand_normalized,
                regex_pattern=kw.regex_pattern,
            )
            continue
        if hit:
            return RuleLabel(
                ownership=HospitalOwnership(kw.ownership),
                service_tags=tuple(
                    HospitalServiceTag(t) for t in kw.service_tags
                ),
                appointment_mode=HospitalAppointmentMode.UNKNOWN,
                chain_brand_normalized=kw.chain_brand_normalized,
                matched=True,
            )
    return RuleLabel.empty()


def should_exclude(raw_place: dict) -> ExclusionDecision:
    """Decide whether a Google Places candidate is worth keeping at all.

    Returns an `ExclusionDecision` whose `reason` is `None` for keepers.
    Non-clinic rows (pharmacy / pet store / grooming-only) are still
    persisted (so re-runs skip them) with the `excluded_reason` stamped on
    the row — `dispatch_schedule` skips any row that carries one.
    Nonprofit / rescue rows are kept with `suggested_ownership=NONPROFIT`;
    the ownership label alone is enough to scope them out of a campaign.
    """

    if raw_place.get('businessStatus') and raw_place['businessStatus'] != 'OPERATIONAL':
        return ExclusionDecision(reason='not_operational')

    name = ((raw_place.get('displayName') or {}).get('text')) or ''
    if not name:
        return ExclusionDecision(reason='no_name')

    if NON_CLINIC_REGEX.search(name):
        return ExclusionDecision(reason='non_clinic')

    if NONPROFIT_REGEX.search(name):
        return ExclusionDecision(
            reason=None,
            suggested_ownership=HospitalOwnership.NONPROFIT,
        )

    types = raw_place.get('types') or []
    primary = raw_place.get('primaryType')
    if 'veterinary_care' not in types and primary != 'veterinary_care':
        return ExclusionDecision(reason='no_vet_type')

    return ExclusionDecision(reason=None)
