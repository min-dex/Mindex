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
