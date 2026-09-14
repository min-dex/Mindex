# Current Worship Persistence Contract

## Save receipt hardening (2026-09-11)

Full and element saves now request an exact affected-row count for the service
update and reject zero or missing counts without clearing the local draft.
Full saves advance the local source document baseline only after all row writes
succeed. Recovery-history equality compares the complete compact document,
excluding only its timestamp, so linked-source, layout and exception changes
are retained even when text/slide signatures are unchanged.

This is not transactional saving or cross-client revision checking. Partial
writes and concurrent ID-only replacements remain possible. No production
data, authentication, grants or RLS changes are included.

Offline verification: `tests/test_worship_save_receipts.cjs` exercises the
bundled SDK and history comparison; `tests/smoke_service_save_safety.py`
exercises draft retention and save queues in Chromium and WebKit.

Reviewed 2026-09-10 against the shared checkout of `app.js`,
`scripts/worship-schema.sql` and the existing save-safety tests. The checkout
contains concurrent work. This is a code/schema-source audit, not a production
catalog inspection or evidence of a specific lost production record. No data,
constraints or migrations were changed by this audit.

## Current representation

### Full-save failure boundary coverage (2026-09-14, offline verification)

`python3 tests/smoke_full_save_failure_boundaries.py` adds six synthetic cases in
each of Chromium and WebKit: failure before a write and response loss after a
committed write, at the service update, section upsert and element upsert stages.
The test runs the current browser save lifecycle and row conversion against a
stateful in-memory API double; all Supabase browser traffic is blocked.

Assertions cover immediate stop at the injected boundary, retained item content
and dirty IDs, unchanged local committed rows/source_ref, captured recovery draft,
released save lock, and a subsequent explicit successful retry with fake-server
state comparison without
duplicate stable IDs. Earlier fake-server writes remain committed: this deliberately
characterizes partial persistence, not transaction rollback. An all-written but
unacknowledged save must still retain the local draft.

Learning sources: FINDEX's
[`config-atomic-write-smoke.mjs`](../../Findex/scripts/config-atomic-write-smoke.mjs)
injects persistence failures and checks memory separately from disk; STUDEX's
`dbSaveEntry` checks its `updated_at` conditional-write receipt before finalization;
VITEX's [`Store.save`](../../Vitex/tools/local_store.py) preserves a recovery copy
on a revision/save error. MINDEX reuses the failure-boundary testing principle,
not those storage implementations or a second atomic-save protocol.

Not covered by this matrix: structural deletes, sibling synchronization, service
type defaults, concurrent clients, PostgreSQL rollback/locks, durable recovery,
and idempotent exactly-once retries. These remain separate acceptance work in
[the existing atomic-save design](worship-atomic-save-design.md). No runtime code,
production records, migration, permission or deployment changes accompany this test.

| Surface | Current implementation | Limit |
| --- | --- | --- |
| Service identity | `mindex_worship_services.id`, section and element UUIDs | Display labels and sort order are not stable IDs. |
| Instance data | Service row, section rows, element rows | Saved through separate API requests, not one transaction. |
| Content | `input_mode`, `content_state`, `asset`, `config`, `source_ref` and typed links | Optional column detection retains compatibility; JSON references are not foreign keys. |
| Behavioral slot | Optional `slot_key`, plus `source_ref.slotKey` / `config.slotKey`; runtime `_worshipSlotKey` | Current validator detects duplicate slots in its input only; no service-wide SQL uniqueness guarantee established by this audit. |
| Service document | `source_ref.mindexServiceDocument`: sourceText, sourceRecords, slides, exceptions, signatures | Coexists with normalized rows; not yet a single authoritative transactional aggregate. |
| Canonical content | `song_id`, `song_version_id`, `scripture_id`; resolved Scripture references and asset URLs | Canonical ownership stays outside Worship; persisted source/slides may also contain copied content. |
| Recovery | Browser-local snapshots and bounded `mindexServiceDocumentHistory` in source_ref | Best effort / bounded, not an independent durable audit log or rollback transaction. |

`buildServiceDocumentSnapshot` derives source text from an explicit draft or
current items, and slides from the presenter builder. Source records link text
records back to item/section/slot identities. These are coordinated projections,
not a completed source-text-only storage model. Do not remove compatibility
fields or the normalized rows on the assumption that the migration is complete.

The checked SQL declares foreign keys for service -> section -> element -> slide
with cascading child deletion, and nullable canonical references with SET NULL.
It does not declare JSON-to-record foreign keys, or a composite constraint proving
that a song version belongs to the linked song. Deployed constraints/triggers
must be inspected separately before asserting production integrity.

## Write paths

- `runServiceSave`: serializes saves in the current JS runtime; saves dirty
  service-type defaults first. It does not coordinate another tab/computer.
- `saveWorshipServiceInstance`: validates rows; updates service metadata/document;
  upserts sections; upserts elements; deletes removed elements; deletes removed
  sections; then updates local state. Earlier requests remain committed if a
  later one fails. The in-memory source_ref advances only after these instance row
  writes complete; retaining it on failure does not roll back earlier remote writes.
- `saveWorshipServiceElementPatch`: validates all current items; upserts the
  target section and element; updates the service document built from all items;
  then acknowledges only the target item's local dirty state. Other local drafts
  can therefore appear in the document although their element rows were not saved.
- Both paths use ID-only predicates for service updates, not an expected revision
  or updated_at comparison. Local signatures protect edits made during this
  runtime's request; they do not prevent overwriting a newer remote document.
- `saveDirtyServiceTypes` updates defaults independently. Success there followed
  by instance failure is not rolled back. Treat defaults as a separate operation.
- `syncSharedSundayContentAfterSave` runs after a successful source save, only
  for explicitly edited content whose persisted before/after values differ.
  Read-time sibling projection is disabled. Each service displays its own values.
  Existing same-date standard elements synchronize only when their content matches
  the source's previous value (or a retry value). Different values, local drafts,
  live output, duplicate slots, replacements, and absent rows are not overwritten.
  Targets use updated_at CAS with exact row receipts. Target document writes
  separately compare the previous source_ref. These writes are not transactional;
  a failed document write is reported and retried with the durable local job.
  A subsequent source save retries pending jobs; merely loading a service does not.

## Verified gaps and existing protections

1. **High: partial commits.** Failure of the document update after an element
   upsert leaves a new element with an old document. Full saves have the opposite
   write order and can leave a new document with old rows. UI error handling is
   not DB rollback.
2. **High: cross-client lost updates.** ID-only document replacement accepts a
   stale client's source_ref. A same-tab save queue is not compare-and-swap.
3. **Medium: scope validation.** `validateWorshipPersistenceRows` checks IDs,
   timestamps, modes and duplicate slot keys, but currently does not reject a
   section belonging to another service or an element whose section is absent
   from the submitted set. Ordinary FK existence alone does not establish ownership.
4. **Recovery is limited.** Local snapshot failure warns but does not prevent
   save. Remote history shares the same overwrite path. The history size constant
   is measured with JS string length, and trimming retains one entry even above
   that limit; it is not a hard UTF-8 byte cap.

Existing protections remain valuable: loading rows before first persistence,
typed-state normalization, pre-write validation, retained content/suppression
markers, local dirty-state signatures, and same-runtime save serialization.
Do not remove them when adding server-side protection.

## Reproduction and next acceptance criteria

Run `node tests/audit_worship_persistence_contract.cjs`. It uses extracted current
functions with an in-memory API double; no browser, credentials or network. It
characterizes known gaps rather than proving safety. If a gap is fixed, replace
the corresponding characterization with the required safety assertion.

Next implementation should be separately scoped and reviewed:

The proposed protocol and rollout are in
[Atomic Worship Save Design](worship-atomic-save-design.md); this is design only,
not an implemented guarantee.

1. Define an expected aggregate revision and an atomic server operation for
   service document + sections + elements, including deletes. All instance write
   paths must participate; adding CAS only to the last document write is not enough.
2. Validate service ownership, canonical pair consistency and slot identity inside
   that operation. Reject stale/mismatched input without any committed row changes.
3. Define whether saving one element excludes other unsaved drafts from the
   authoritative document or intentionally saves the whole aggregate. Align the UI
   acknowledgement with that choice; do not silently change existing behavior.
4. Retain a recoverable previous revision and introduce idempotent request IDs.
   Test retries after uncertain network outcomes, failure at each write stage,
   stale clients, concurrent structure edits and fresh-client readback.
5. Confirm live schema/RLS and client rollout compatibility before any migration.
   A new client guard cannot constrain old clients still writing directly.

No broad JSON cleanup, curated-record normalization, table deletion or production
migration is authorized by this audit document.

## Read-only audit lookup cost (2026-09-14, offline verification)

`scripts/audit_mindex_content.py` now indexes song versions once instead of
linearly searching every version for each linked worship element. The first
matching duplicate ID is retained, matching the old lookup behavior; missing
references and warning order/content are unchanged. This adds an in-memory map
of references, not copies of version payloads. Fetch calls and selected columns
are unchanged; no production bandwidth or latency improvement is claimed.

`python3 tests/test_audit_version_lookup_cost.py` replaces fetches with synthetic
rows and counts version-row visits (not elapsed time):

| Versions / elements | Before | After |
| --- | ---: | ---: |
| 100 / 200 | 20,300 | 300 |
| 200 / 400 | 80,600 | 600 |

Both fixtures assert the complete expected warnings and counts. A separate case
protects first-duplicate and missing-reference semantics. The existing
`tests/test_audit_mindex_content.py` structural-warning test remains enabled.
This tool-only optimization is separate from the full-save failure matrix above;
it does not modify app runtime, Storage metadata, production DB or permissions.

Focused timing check on Python 3.9.6 / Darwin arm64, using the same 200-version /
400-element fixture: three warmups followed by 20 timed calls per variant in
alternating before/after order. Median was 18.641 ms before and 5.227 ms after;
nearest-rank p95 was 35.479 ms before and 11.527 ms after. Both variants produced
identical complete counts/issues/warnings on every call. The before variant
restored only the prior lookup in an in-memory module; no runtime file was reverted.
Timing includes the complete mocked audit invocation, excludes fixture creation,
imports and compilation, and makes no live network requests. These local samples
are not a production database, UI latency, or guaranteed speedup measurement.
