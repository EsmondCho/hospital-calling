# `/backoffice/chain_keywords/`

Read-only view of the sourcing pipeline's chain keyword table
(`hospital.ChainKeyword`). The rule pass (`match_chain`) regex-matches a
hospital name against these rows to seed ownership + service tags before
the LLM second pass.

Rows are created / edited / deleted via the Django admin console
(`/admin/`), not this API — regex precision is hand-tuned there.

## `GET /backoffice/chain_keywords/`

Returns the full table, ordered by `match_priority` then `id`.
Unpaginated (the table is ~20 rows).

**Response** — plain array:

```json
[
  {
    "id": 1,
    "match_priority": 10,
    "chain_brand_normalized": "vca",
    "display_name": "VCA Animal Hospitals",
    "ownership": "MARS_VH",
    "service_tags": ["GENERAL_PRACTICE", "SPECIALTY", "EMERGENCY"],
    "regex_pattern": "\\bVCA\\b",
    "notes": "Individual locations vary in ER coverage — LLM verifies per-site.",
    "created_at": "2026-05-16T03:00:00Z",
    "updated_at": "2026-05-16T03:00:00Z"
  }
]
```

`match_priority` — lower runs first in `match_chain`; lets a specific
pattern be ordered ahead of a broader one.
