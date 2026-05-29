# Model Conventions

## Field rules

- **No `choices=`**. Enum changes shouldn't generate migrations. Validate on the
  serializer (`utils/enums.py::HospcallStrEnum.get_vals()`).
- **`metadata` JSONField**: always `default=dict`, never `null=True`. "No value"
  is the empty dict.
- **Optional string fields**: `null=True, blank=True`. No `default=''`.

## Foreign keys

- `db_constraint=False` on every FK (we manage referential integrity in code).
- `on_delete=SET_NULL` + `null=True` for FKs whose targets we want to keep
  history of after the parent is gone. `CASCADE` only when lifecycle is shared.

## Query efficiency

- `select_related()` / `prefetch_related()` whenever you cross a FK.
- Bulk: `bulk_create`, `bulk_update`, `values_list(... flat=True) + __in`.
  Don't loop singletons.
- Compound filters: prefer `Q()` / `~Q()` inside one `filter()` call.

## Transactions

- Multi-write logical units → `transaction.atomic()`.
- External API calls go OUTSIDE the transaction.
- If an external call fails after a DB write, either roll back or compensate.

## Migrations

- Generate via `make migrations`. Don't hand-edit machine-generated migration
  files.
- Hand-written **data migrations** (RunPython) are fine and encouraged for
  seeds and backfills. The dummy-data migration in `calling/migrations/` is
  the prototype.

## Indexes

- Declared in `Meta.indexes`. Don't mix with `db_index=True` on fields.
- Naming: `idx_{table-short}_{cols}` (≤ 30 chars; PostgreSQL identifier limit
  is 63 but short names age better).
