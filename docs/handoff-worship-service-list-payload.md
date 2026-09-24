# Handoff: worship service list payload (UX -> Data)

Status: requirement recorded by the UX thread (2026-09-20). No schema change was made.

## Problem (measured on https://min-dex.github.io, Chrome, emulated slow 4G)

The first data request of every cold load is the worship service list:

```
mindex_worship_services?select=id,service_type_id,service_date,service_date_end,title,
  worship_leader,praise_leader,notes,created_at,status,source_ref,service_alias
  &order=service_date.asc,service_type_id.asc
```

For 93 services it returns **1.0 MB on the wire (gzip), 7.7 MB decoded**. Almost all of it
is two keys inside `source_ref`:

| key | decoded size | share |
| --- | --- | --- |
| `mindexServiceDocumentHistory` | 5.3 MB | 71 % |
| `mindexServiceDocument` | 2.1 MB | 28.5 % |
| everything else (all other columns and keys) | ~0.03 MB | 0.4 % |

Effect: on slow 4G this one request takes ~17 s (11.3 s -> 28.1 s) and every later request
(elements, sections, templates, songs) waits behind it, so data appears after ~30 s. On
broadband it still costs ~1 s plus parsing/normalizing 7.7 MB of JSON on the main thread.
The Home screen only needs the light fields; the document and its history are used only
when a service is opened (presenter fallback slides, source-text history, save).

## Requirement

A list read that returns `source_ref` **without** `mindexServiceDocument` and
`mindexServiceDocumentHistory`, plus enough to know whether they exist, for example:

- a view or RPC `mindex_worship_services_list` with the same columns as above where
  `source_ref` is `source_ref - 'mindexServiceDocument' - 'mindexServiceDocumentHistory'`,
  and an extra boolean such as `has_service_document`;
- anon read access with the same RLS behavior as `mindex_worship_services`;
- unchanged ordering and the same column names, so the client only swaps the table name.

The full row stays available through the existing `select("*").eq("id", ...)` reads.

## UX-side plan once the read exists

1. `fetchWorshipServiceListRows()` reads the lightweight list.
2. Opening a service (presenter/service detail) fetches its full `source_ref`
   (document + history) **before** any code path can save it. A save that merges
   `mindexServiceDocumentHistory` from a list-only `source_ref` would drop the history, so this
   ordering is a hard requirement, not an optimization.
3. Add a smoke test that a save never runs with a list-only `source_ref`.

## Not done / out of scope for the UX thread

- No schema, view, RPC or data rewrite was made.
- Compressing or trimming the stored history itself (5.3 MB for 93 services) is a data
  question for the Data thread; the list read fix above removes it from the startup path
  either way.

## Other startup costs measured (UX-owned, not changed)

- `PretendardVariable.woff2` 2.0 MB is the UI font and is preloaded (a subset/dynamic-subset
  build would cut it; needs a font toolchain).
- `chromakey-ready-loop-pingpong.mp4` 26 MB is prefetched only when a presenter view is opened.
- Three Freesentation weights ~1.4 MB are preloaded; lowering their priority with
  `fetchpriority="low"` was tried and showed no effect on the deployed site.

## Data thread response (2026-09-20)

Status: migration written and verified on a local PGlite engine. **Not applied to production yet.**
It needs the Supabase SQL Editor (or a service-role/database connection); the browser anon key cannot
create views or triggers.

### 1) List read: `public.mindex_worship_services_list` (view)

`migrations/2026-09-20-worship-service-list-view.sql`

- Columns: `id, service_type_id, service_date, service_date_end, title, service_alias, worship_leader,
  praise_leader, notes, status, created_at, updated_at, source_ref, has_service_document,
  has_service_document_history`. Every column of the current list select keeps its name; the client
  swaps only the table name. `updated_at` is extra, for cache checks.
- `source_ref` = `source_ref - 'mindexServiceDocument' - 'mindexServiceDocumentHistory'`. Other keys
  (`no_gathering`, `sunday_main_variant`, `created_from`, ...) are intact, so
  `source_ref->no_gathering` style selects also work against the view.
- `security_invoker = true`: the caller's role and RLS apply as on `mindex_worship_services`
  (anon keeps the shared-access policy). `select` only is granted; insert/update/delete are denied.
- Ordering is the caller's `.order("service_date").order("service_type_id")`; it uses the existing
  `mindex_worship_services_date_type_idx`. Paged reads (`range`) work like on the table.
- Expected payload: `source_ref` leftovers total ~13 KB across the 93 rows measured today, so the
  response is tens of KB decoded (was 7.7 MB) and a few KB on the wire (was 1.0 MB).
- Full reads are unchanged: `mindex_worship_services?select=*&id=eq.<id>` still returns both keys.
- Never write a `source_ref` read from the view back to the table (see guard below).

### 2) Server-side guard for a list-only save

Same migration: `BEFORE UPDATE OF source_ref` trigger
`mindex_worship_services_preserve_source_documents` on `mindex_worship_services`.

| new `source_ref` | result |
| --- | --- |
| key absent (list-only or stale copy) while the row has it | stored value is kept |
| key present | stored as sent (normal save, history rotation) |
| key present with JSON `null` | key is removed (explicit delete) |

Consequences for the client:

- A list-only `source_ref` can no longer erase the document or history, but the UX rule
  "save only after the full `source_ref` was fetched" should stay: the guard is a safety net, and a list-only
  save also cannot record a new document/history entry.
- The compare-and-set update (`.eq("source_ref", JSON.stringify(previous))`) is unaffected.
- To delete the document or history on purpose, send the key as `null`. The current client never
  deletes them intentionally; `normalizeServiceSourceRef` drops a key only when the stored value
  fails normalization, and the guard now keeps the old value in that case.
- The undeployed atomic save protocol already strips both keys from `metadataPatch.source_ref`
  (`mindex.worship-atomic-client.mjs`), so it is consistent with the guard.

Verification: `PGLITE_ROOT=<dir> node tests/test_worship_service_list_view.mjs` (real `services`
DDL and RLS policy; view columns, stripped keys, flags, read-only, no-privilege role, guard cases,
idempotent re-run). PGlite is PostgreSQL 18; the view needs `security_invoker` (PostgreSQL 15+), and
the migration is transactional, so an older engine fails without changing anything.

### 3) Size of the stored history (measured 2026-09-20, read-only)

- 93 services: `mindexServiceDocument` on 24 (2.5 MB), `mindexServiceDocumentHistory` on 22 (6.2 MB).
  71 services have no history; all 22 with history are from 2026-08-01 or later.
- Each history entry is a full document snapshot, ~102 KB on average. The client keeps at most 3
  entries and ~450 KB (`MINDEX_SERVICE_DOCUMENT_HISTORY_LIMIT/MAX_BYTES`); the largest row holds
  558 KB of history (the byte cap always keeps one entry).
- After the list read is switched, history is fetched only when a service is opened: ~100-560 KB for
  services that have it, nothing for the rest. That is acceptable, so no data was trimmed.
- Options if it still matters (none applied; each rewrites curated production records and needs an
  explicit decision): keep 1 entry instead of 3 for services older than N days (only 1 service is
  older than two weeks today, ~139 KB, so the gain is small now); store diffs instead of full
  snapshots (client change); move history to its own table and load it on demand (schema change).
  Growth is bounded by the 3-entry cap, so revisit when the service count grows.

### Apply / rollback

1. Run `migrations/2026-09-20-worship-service-list-view.sql` in the Supabase SQL Editor (idempotent).
2. Check with the anon key: `GET /rest/v1/mindex_worship_services_list?select=id,source_ref,has_service_document&limit=1`
   returns a `source_ref` without the two keys, and the full list request is tens of KB.
3. Rollback statements are at the bottom of the migration file.

## UX thread status (2026-09-20)

The client is switched and safe to deploy **before** the migration is applied:

- `fetchWorshipServiceListRows()` reads `mindex_worship_services_list` first
  (`WORSHIP_SERVICE_LIST_VIEW`). If the view is missing (404 / `PGRST205` / `42P01` / `42703` /
  `42501`) it reads `mindex_worship_services` exactly as before and remembers the miss for one hour
  (`mindex.serviceListView.missingUntil` in localStorage) so users do not see a 404 on every load.
  Network failures are **not** treated as "missing"; they follow the existing cache fallback.
- A row with `has_service_document` or `has_service_document_history` is marked
  `_worshipSourceRefPartial`. Opening a service (`loadServiceItems`, `hydratePresenterServiceData`)
  fetches `select=source_ref&id=eq.<id>` once and merges it, keeping local edits of the light keys.
- Saving is refused until the full `source_ref` is present: `requireFullServiceSourceRef()` in
  `saveWorshipServiceInstance` and `saveWorshipServiceElementPatch`, plus a hard invariant in
  `withServiceDocumentSnapshot()` (throws for a partial service). The server guard stays a safety net.
- Tests: `tests/smoke_service_list_view.py` (view read, fallback, outage, merge, save refusal).

End-to-end check with live data, read-only, view simulated in the browser from the real table:
list response **51 KB decoded** (was 7.7 MB), 24 of 93 services marked partial, opening one fetched
its full `source_ref` (document + 3 history entries restored), an unopened partial service refused to
build an outgoing `source_ref`.

Applied to production on 2026-09-20 (`Success. No rows returned`). Verified with the anon key: 93 rows,
7 KB on the wire / 48 KB decoded (was 1.0 MB / 7.7 MB), 24 with a document, 22 with history, no stripped
key in `source_ref`. On the deployed site (emulated slow 4G, cold) the list request dropped from ~17 s to
0.44 s and data appeared at ~13 s instead of ~30-35 s (broadband 1.2 s). The temporary 404 allowance in the
smoke suites was removed.
