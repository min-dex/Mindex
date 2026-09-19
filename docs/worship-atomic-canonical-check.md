# External Dependency Revision Check

2026-09-19. Implemented and tested only in disposable PostgreSQL 17.6.
No live rows, grants, triggers or client flags were changed.

## Scope

The canonical fixture models songs, canonical songs, versions, lyric units,
scripture records and worship template references. Changes invalidate only
persisted worship instances with matching references. It deliberately preserves
the saved instance rows, lyrics, document, manual slides and extension fields;
revision invalidation is not automatic lyric replacement.

Referenced source/version/canonical/scripture/template deletion and referenced
version ownership reassignment are rejected by this conservative prototype.
Unused records and individual lyric units may still be deleted. This deletion
behavior is **not a settled production policy**: ask whether to block or provide
an explicit detach-to-snapshot operation before rollout.

## Locking

Atomic create/save/delete takes a shared dependency advisory lock before its
per-service advisory/row lock. Canonical writes take the exclusive counterpart
in a BEFORE STATEMENT trigger, before acquiring canonical row locks. Read-only
presenter queries do not acquire this lock. Concurrent independent worship
saves can continue together; a canonical write temporarily serializes saves.
The latency of large canonical imports remains unmeasured and is a rollout gate.

A private service/transaction-ID marker increments each affected service once
per transaction, including multi-row lyric edits. The first invalidation stores
the previous instance aggregate in the existing bounded checkpoint. Markers
are neither client settings nor caller-owned temp objects, and are not exposed.
They roll back with the canonical mutation.

## Verified

- Original metadata/lyrics change rejects a stale instance save without changing
  stored instance lyrics/document or unrelated services.
- No-op updates do not increment revisions.
- Multi-row lyric edits and version metadata edits increment once per transaction.
- Prior instance checkpoint, version and source rows roll back on transaction abort.
- Referenced deletions/reassignment cannot silently null FKs or change song identity.
- Two independent PostgreSQL sessions exercise both canonical-first and save-first
  order; revisions remain monotonic. Lock timeout leaves data unchanged.
- Scripture/template changes invalidate the affected instance without rewriting it.
- Canonical tables use RLS. The writer role needs SELECT and UPDATE USING for
  FOR SHARE, plus the existing column privilege. UPDATE WITH CHECK false prevents
  actual version-row mutation; no BYPASSRLS or broad canonical write grant is used.
- The existing SQL prototype rollback/concurrency and definer security suites pass.

Run with the same disposable helper as the other atomic tests:

```sh
WORSHIP_TEST_ENGINE=postgres WORSHIP_TEST_PG_VERSION=17.6 PGLITE_ROOT=/private/tmp/mindex-atomic-deps node tests/test_worship_atomic_canonical.mjs
```

## Remaining Boundaries

This is not a live-schema migration. Real function owners, policies, role
membership, existing triggers and privileged import paths still need review.
Service-type default changes remain a separate operation. This also does not
make the current multi-request song editor transactional or implement detachment,
restore UI, retention, conflict reconciliation or operational backup restoration.
Keep the client protocol disabled until those activation gates are resolved.
