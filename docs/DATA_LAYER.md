# Portal request migration - `request_type` and nullable `category`

This note documents the one-time migration applied by
`portal.db.migrate_portal_requests()`. It applies only to the portal SQLite
database selected by `CSS_PORTAL_DB_PATH` (by default
`backend/data/css_demo.db`). It never touches any external database.

## Trigger

`init_db()` runs `Base.metadata.create_all()` and then
`migrate_portal_requests(engine)` on startup. The migration rebuilds
`portal_requests` only when either condition is true:

- the `request_type` column is absent, or
- `category` is still `NOT NULL`.

On an already-migrated database it returns `False` without writing anything.

## Rebuild sequence

1. `PRAGMA foreign_keys=OFF` on the raw connection, before any transaction.
2. `BEGIN IMMEDIATE`.
3. Create `portal_requests_migrated` with the new schema.
4. Copy every existing row with an explicit column list. `request_type` is
   absent from the old table, so legacy rows receive `NULL`. All other values,
   including `id`, are copied verbatim.
5. Drop the old `portal_requests` table while enforcement is off, so child
   `ON DELETE CASCADE` rules do not fire.
6. Rename `portal_requests_migrated` to `portal_requests`.
7. Recreate the `ix_portal_requests_user_id` index.
8. Run `PRAGMA foreign_key_check` inside the transaction.
9. Commit, or roll back and re-raise if the check reports any violation.
10. Restore `PRAGMA foreign_keys=ON` on the pooled connection in `finally`.

## Preserved schema objects

The rebuild recreates the following objects. The migration test snapshots them
before and after and asserts equality:

### Columns

All existing columns keep their name, type, primary-key flag and nullability,
except:

- `category` intentionally changes from `NOT NULL` to nullable.
- `request_type VARCHAR(32) NULL` is intentionally added.

### Indexes

| Index | Definition | Status |
| --- | --- | --- |
| `ix_portal_requests_user_id` | non-unique index on `user_id` | recreated explicitly |
| SQLite autoindex for `reference_id` | unique index on `reference_id` | recreated by the `UNIQUE` constraints |

The original SQLAlchemy model declares both a named `UniqueConstraint` and
`unique=True` on the `reference_id` column. Both declarations are intentionally
recreated to keep the rebuilt table equivalent to the original. SQLite enforces
the duplicate `UNIQUE (reference_id)` declarations with a single autoindex.
SQLite assigns the autoindex name; the test compares the complete index
snapshot, including name, uniqueness, origin and columns.

### Constraints

| Constraint | Definition | Status |
| --- | --- | --- |
| `PRIMARY KEY (id)` | integer primary key | recreated |
| `uq_portal_requests_reference_id` | `UNIQUE (reference_id)` | recreated |
| unnamed `UNIQUE (reference_id)` | duplicate unique constraint from the original DDL | intentionally recreated |
| `ck_portal_requests_status` | `status IN ('SUBMITTED', 'UNDER_REVIEW', 'REPLY_SENT', 'RESOLVED')` | recreated unchanged |
| `ck_portal_requests_category` | `category IS NULL OR category IN (...seven values...)` | intentionally widened from `category IN (...)` plus `NOT NULL` |
| `ck_portal_requests_request_type` | `request_type IS NULL OR request_type IN (...seven values...)` | intentionally added |
| foreign key on `user_id` | `REFERENCES portal_users (id) ON DELETE SET NULL` | recreated unchanged |

The seven category values and seven request-type values are generated from
`portal.categories.CATEGORY_VALUES` and
`portal.request_types.REQUEST_TYPE_VALUES`; they are not duplicated by hand.

### Child tables

`portal_status_events` and `portal_replies` are not dropped, altered or
recopied. Their `request_id` values remain valid because the parent `id`
values are copied unchanged. Their foreign keys reference the table name
`portal_requests`, which the rename restores.

## Failure behaviour

`PRAGMA foreign_key_check` runs before `COMMIT`. If it returns any rows, the
migration raises `RuntimeError`, executes `ROLLBACK`, and re-raises. The
original table, all rows and all child records remain intact, and the
temporary `portal_requests_migrated` table is removed by the rollback.
Enforcement is restored to `ON` in `finally`.

The test `test_migration_rolls_back_when_foreign_key_check_fails` inserts a
deliberate orphan status event, forces the check to fail, and verifies:

- the original `portal_requests` schema is unchanged;
- `request_type` was not added and `category` is still `NOT NULL`;
- the original request, status events and replies are still present;
- the temporary table does not survive;
- `PRAGMA foreign_keys` is back to `1` on the same pooled connection.

## Idempotency

Sequential startup is safe. `migrate_portal_requests()` re-inspects the live
schema and returns `False` once `request_type` exists and `category` is
nullable. `test_migration_preserves_existing_rows_and_children` asserts the
first call returns `True` and the second returns `False`.

## Concurrency limitation - single-process assumption

The current startup path assumes **one backend process**. `BEGIN IMMEDIATE`
serialises writers, but the column snapshot is taken before the write lock is
acquired. If two worker processes both inspect the old schema and then run in
sequence, the second process still holds its stale snapshot and can rebuild
again using the old column list. That would discard `request_type` values
written by the first process.

For the demo, run a single process. Before enabling multiple workers, move the
schema re-check inside the `BEGIN IMMEDIATE` transaction (or add a migration
lock/version row) so only the lock holder decides whether to rebuild.

## Verification

- `tests/test_request_types.py::test_migration_preserves_existing_rows_and_children`
- `tests/test_request_types.py::test_migration_preserves_all_indexes_and_constraints`
- `tests/test_request_types.py::test_migration_rolls_back_when_foreign_key_check_fails`
