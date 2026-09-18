# Live Read-Only Audit

2026-09-19, Mindex production, through the authenticated Supabase SQL Editor.
All queries ran inside `BEGIN TRANSACTION READ ONLY ... ROLLBACK`.
No schema, grants, worship content, storage objects or protocol flags were changed.

## Observed

- PostgreSQL 17.6; `pg_database_size` returned 353,627,283 bytes at inspection.
- `mindex_worship_services.save_revision` does not exist.
- The four intended public v1 atomic RPCs do not exist. A public function-name
  query matching `%worship%` returned no functions; this does not rule out
  differently named privileged writers or private-schema functions.
- All eight table/role pairs (services, sections, elements, slides times anon,
  authenticated) have SELECT/INSERT/UPDATE/DELETE table privileges. RLS is enabled.
- Each aggregate table has an ALL policy for anon, USING true, WITH CHECK true.
  Authenticated table grants alone do not prove effective RLS permission.
- The only observed non-internal triggers on the four tables update timestamps.
- Child FK deletion cascades are services -> sections -> elements -> slides.
- Song, version, scripture and template references use ON DELETE SET NULL.
- Elements include `input_mode`, `content_state`; no dedicated `slot_key` column.
- Song/version mismatches against `coalesce(source_song_id, canonical_song_id)`:
  **0**. Elements without a parent section: **0**. These are scoped counts, not
  evidence that every document, lyric, attachment or historical exception is valid.

## Consequences

Atomic protection is not active. Old/direct writers and external FK changes can
bypass a future revision protocol unless included in the coordinated cutover.
Do not enable the client flag based on local SQL tests. A reviewed production
migration, private recovery access, real backup restoration, receipt/checkpoint
capacity policy, conflict resolution and old-client denial remain prerequisites.

## Conflict Review Preparation

The disabled atomic client now supports non-adopting conflict inspection. It
freezes the local draft before the read, validates server identity/revision and
preserves both the committed baseline and any uncertain pending request.
The staged app opens a source-text comparison on non-silent atomic save conflicts,
allows a local JSON export (draft/baseline/latest/pending) and leaves editing intact.
The comparison is not a complete field diff or a merge/reapply implementation.
Background/silent conflicts still do not open a modal. No force-save or automatic
baseline adoption was introduced.

Chromium/WebKit desktop/mobile tests cover visibility, bounded layout, literal
text rendering, frozen export, failed/deleted server reads, duplicate opens,
late responses after close, save-lock release, and absence of save/audio actions.
Screenshots were inspected at 1440x900 and 390x844. Runtime full/element/sibling
atomic-save regression tests also passed. Production remains on the legacy path.
