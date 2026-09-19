# Atomic Recovery Check

2026-09-19. Disposable PostgreSQL 17.6 only. No production changes or activation.

`tests/fixtures/worship-atomic-restore.sql` adds a private operator-only recovery
prototype. It accepts a service ID, expected current revision, expected checkpoint
revision, a stable request ID and explicit confirmation. It reads the checkpoint
from the server; callers cannot submit replacement recovery rows.

Verified by `tests/test_worship_atomic_restore.mjs`:

- Live and deleted services restore at a new monotonic revision, not a rewind.
- Stable child IDs, saved lyrics, source document, JSON exceptions, asset URLs
  and persisted slide rows survive restoration.
- Repeated requests commit once. Reused request IDs with changed contents fail.
- Stale current/checkpoint revisions and absent confirmation reject before writes.
- Injected root, section, element, slide, checkpoint and receipt errors roll back
  the entire operation, preserving the previous checkpoint.
- Missing or reassigned song references reject instead of silently unlinking.
- Business identity and foreign child UUID collisions reject without modifying
  another service. The prototype does not reparent or overwrite foreign rows.
- Two PostgreSQL sessions competing at one revision yield one commit/one conflict.
- Browser roles cannot execute recovery; there is no public restore RPC or UI.

The same dependency-first lock order as other aggregate operations is used.
Restoring a live service swaps its previous aggregate into the bounded checkpoint.
Restoring a deleted service retains the prior checkpoint, removes its tombstone,
and keeps lightweight request receipts so old requests cannot be reexecuted.

Run:

```sh
WORSHIP_TEST_ENGINE=postgres WORSHIP_TEST_PG_VERSION=17.6 PGLITE_ROOT=/private/tmp/mindex-atomic-deps node tests/test_worship_atomic_restore.mjs
```

## Still Required

This is not a production migration, a full database backup restoration, or media
backup verification. It assumes the synthetic aggregate schema and private server
checkpoints. Production schema/trigger audit, restore authorization/preview UI,
missing-source policy, checkpoint/receipt capacity and retention, live backup
restoration, conflict UI and coordinated old-client denial remain rollout gates.
The atomic protocol flag stays disabled; legacy partial-save risks remain live.

## Database Backup Rehearsal

2026-09-19: `tests/test_worship_atomic_security.mjs` now optionally runs real
`pg_dump --format=custom` and `pg_restore --exit-on-error --single-transaction`.
This is a logical database archive, not a PostgreSQL physical/base backup.
The helper creates a second empty database inside its disposable loopback-only
PostgreSQL 17.6 cluster. It cannot accept a production URL or a caller-supplied
backup. The archive and both databases are removed when the test ends.

Verified using PostgreSQL 17.6 dump/restore binaries:

- Every fixture table matches after restore, including linked song/version IDs,
  source documents, JSON exceptions, media URLs, persisted slides, checkpoints,
  tombstones and request receipts.
- RPC owners, SECURITY DEFINER/search_path settings, function ACLs and RLS
  policies match. Anonymous/authenticated reads work; direct writes/private
  receipt reads still fail.
- Replaying the pre-backup create request adds no rows or receipts.
- Stale revisions still fail; a normal save after restore advances revision.
- The source database remains unchanged by the restored database's saves.

Run the security test with `WORSHIP_TEST_ENGINE=postgres`,
`WORSHIP_TEST_PG_VERSION=17.6`, `PGLITE_ROOT` pointing to test dependencies and
`WORSHIP_TEST_PG_BIN` pointing to a directory containing `pg_dump`/`pg_restore`.
An uninstalled macOS source build also requires `DYLD_LIBRARY_PATH` pointing to
its `src/interfaces/libpq` directory. Only the temporary tools were built; no
system PostgreSQL installation was changed.

This does not verify production data or a separate cluster's global roles.
The two test databases share roles. Supabase auth/storage schemas, extensions,
role provisioning and external media bytes are not covered. A real operational
backup plus isolated full restore remains required before activation. As of this
check the local project contains only Supabase URL/anon credentials, not a direct
PostgreSQL connection or an operational DB backup.
