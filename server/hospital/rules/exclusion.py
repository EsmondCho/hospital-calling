"""Rule-stage exclusion regexes for the sourcing pipeline (DRT-5204 §3.2).

`services.internal.sourcing.rules.should_exclude` consumes these. The chain
keyword table moved to the `hospital.ChainKeyword` DB model — see
`match_chain` in the same module.
"""

import re

# Names that are not a paid vet clinic at all — pharmacy / pet store /
# grooming-only, plus manufacturers / distributors / wholesalers (e.g.
# "Diamond Pet Foods", "Acme Pharmaceutical") that show up in `searchText`
# results but never take patient calls. Rows matching this are persisted with
# an `excluded_reason` so re-runs skip them, and never enter the call queue.
# `\b` anchors the laboratory / distributor / biologic stems so we don't catch
# a clinic merely *describing* in-house lab work; bare "animal health" is
# deliberately omitted — it false-positives on real clinic names.
NON_CLINIC_REGEX: re.Pattern[str] = re.compile(
    r'pet store|pet supplies|grooming only|pharmacy'
    r'|manufactur|pharmaceutical|\blaboratory\b|\bdistribut|wholesale|\bbiologic',
    re.IGNORECASE,
)

# Names that signal a nonprofit / rescue rather than a paid clinic. Kept and
# labelled `ownership=NONPROFIT` (useful to track) — the ownership label
# alone is enough to scope them out of a campaign; no extra flag needed.
NONPROFIT_REGEX: re.Pattern[str] = re.compile(
    r'\bshelter\b|\brescue\b|\bspca\b|humane society',
    re.IGNORECASE,
)
