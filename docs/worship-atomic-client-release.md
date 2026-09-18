# Atomic Client Preparation

2026-09-19: client preparation only. This release does not enable atomic saving,
apply SQL, change production rows or revoke existing write permissions.
`MINDEX_WORSHIP_ATOMIC_PROTOCOL` is deliberately unset in index.html.

## Included

- Opt-in aggregate read and RPC adapters for full save, element Apply, sibling
  edit synchronization, creation, deletion, scheduling and live setlist leaders.
- Tab-scoped immutable pending requests, exact retries, revision checks and
  preservation of unrelated/in-flight local drafts.
- Stable creation identities and original child UUIDs/calendar seeds on retry.
- Independent service transactions in creation batches; confirmed services are
  retained when a later service fails.
- Atomic-mode automatic cleanup skips populated or locally edited services.
- Removal of the uncalled old shared-write helper pair. Active edit-time sync
  remains in place. Its legacy branch constructs the document before writes.
- Desktop packaging includes the two dynamically imported runtime modules.

The default/production path still uses the existing direct-write protocol.
Existing partial-commit and stale-write risks are not fixed by this preparation
release; the characterization test continues to document them.

## Verification

The actual deployed app functions are exercised offline by
`tests/smoke_atomic_save_runtime.py` and `tests/smoke_atomic_lifecycle.py` in
Chromium and WebKit. Their exported requests are replayed in disposable
PostgreSQL 17.6 with `tests/test_worship_atomic_prototype.mjs`, using optional
`WORSHIP_RUNTIME_FIXTURES` and `WORSHIP_LIFECYCLE_FIXTURES` paths.
The SQL under tests/fixtures is private test code, never a production migration.

Coverage includes rollback, same-revision competition, lost-response retries,
document ownership/date checks, source/target isolation and creation/deletion.
Existing default-path save, edit-sync and presenter regressions are also run.

## Activation Gates

Production SECURITY DEFINER ownership/grants and public RPCs, revision handling
for external canonical mutations, recovery/retention policy, pending/conflict UI,
coordinated old-client denial and live operational verification remain required.
Do not enable the switch or revoke DML merely because this client is deployed.
