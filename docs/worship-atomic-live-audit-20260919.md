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
The comparison is not a complete field diff or an automatic merge.
Background/silent conflicts still do not open a modal. No force-save or automatic
baseline adoption was introduced.

Explicit recovery now offers "archive draft and open latest". It re-reads and
requires the exact reviewed aggregate, no uncertain pending write, and an
unchanged local draft. Before replacing local editable rows it verifies durable
local storage of the full draft (including raw items and source text). A unique
conflict archive is kept separately from the rolling latest recovery pointer.
The existing source recovery picker exposes "pre-conflict input" for deliberate
reapplication; it does not automatically merge fields, attachments or structure.
The local JSON export remains available. Storage failure, a dismissed review or
intervening local/server changes prevent adoption. Reopening performs no DB write
and does not publish presenter output. The next normal save uses the reviewed
revision and can conflict again if another editor has saved meanwhile.

Client tests cover these guards and subsequent revision CAS. Browser tests cover
the real recovery action, quota failure, editing during the read, archived raw
items, unrelated service drafts/dirty flags and absence of DB writes/publishing.
These are local fixtures, not an operational cutover or real backup restore test.

Chromium/WebKit desktop/mobile tests cover visibility, bounded layout, literal
text rendering, frozen export, failed/deleted server reads, duplicate opens,
late responses after close, save-lock release, and absence of save/audio actions.
Screenshots were inspected at 1440x900 and 390x844. Runtime full/element/sibling
atomic-save regression tests also passed. Production remains on the legacy path.
