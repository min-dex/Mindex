# Atomic Worship Rollout

## Current State

- The production-ready additive and cutover migrations are versioned separately.
- The additive migration was verified in disposable PostgreSQL 17.6, including
  legacy compatibility before cutover and RPC-only writes after cutover.
- Production received the additive migration on 2026-09-22. Existing services
  retained their data and started at `save_revision = 0`.
- PostgREST exposes the new aggregate read RPC and its live result matches REST.
- The client flag is enabled for deployment. Legacy table permissions remain
  active only as a rollback path until a reviewed save is verified.
- The cutover migration has not been applied. Direct browser writes have not
  been revoked.

## Safe Sequence

1. Run `python3 tests/check_worship_atomic_live.py` until the aggregate read RPC
   matches an existing service and revision.
2. Deploy `window.MINDEX_WORSHIP_ATOMIC_PROTOCOL = 1` and run the full presenter,
   save, lifecycle and conflict-review browser suites.
3. Verify a reviewed low-risk live save and exact retry from the compatible app.
4. Confirm no worship editor is actively saving, then apply the cutover migration.
5. Verify RPC writes succeed while legacy direct writes are denied. Keep reads and
   presenter output available throughout.

Do not apply the cutover migration before step 2. Disabling the client flag is a
safe rollback only while legacy table writes remain available.
