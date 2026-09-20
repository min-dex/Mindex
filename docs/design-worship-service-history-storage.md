# Design: worship service document history storage

Status: option S (slim entries) is implemented in the client (2026-09-20, reads old and new entries). The data rewrite of
existing rows and option T are not applied.
Related: `handoff-worship-service-list-payload.md` (Data thread response, section 3),
`worship-persistence-current.md` (Recovery row), `worship-data-contract.md`.

## Decision summary

1. **The list read is already fixed** (light view `mindex_worship_services_list`); history no longer
   affects startup. What remains is the cost of opening a service that has history (100-560 KB) and
   the size of `source_ref` in general.
2. **Recommended first step: slim history entries, no schema change.** 91 % of the stored history is
   `slides` snapshots that the "이전 저장본" restore never uses. Keeping only `sourceText` plus counts
   shrinks the measured 4.9 MB of history to ~57 KB (-99 %).
3. **A separate history table is the right shape only if history must grow or be queried on its own.**
   Design below, not recommended yet: it needs a schema change, a client change and a cutover for a
   gain the slim entries already deliver.

## Measurements (read-only, 2026-09-20, 93 services)

| what | value |
| --- | --- |
| services with history | 22 (all dated 2026-08-01 or later); 71 have none |
| history entries | 60 (cap: 3 per service, ~450 KB per service) |
| history total | 4.9 MB of entries (6.2 MB counting JSON structure per service) |
| largest service history | 558 KB |

Where the bytes are, summed over all 60 entries:

| entry field | KB | share |
| --- | ---: | ---: |
| `slides` | 4501 | 91.0 % |
| `sourceRecords` | 365 | 7.4 % |
| `exceptions` | 36 | 0.7 % |
| `sourceText` | 35 | 0.7 % |
| everything else (signatures, ids, dates) | ~10 | 0.2 % |

## How history is used today (client, `app.js`)

| where | use |
| --- | --- |
| `withServiceDocumentSnapshot`, element save path (`before-element-patch`) | build the new history: previous document pushed in front, `serviceDocumentHistoryWithPrevious` |
| `compactServiceDocumentHistoryEntry` | shape of one entry (fields above) |
| `serviceDocumentHistoryEntryKey` | de-duplicate consecutive identical entries (compares the compact content without `updatedAt`) |
| `trimServiceDocumentHistory` | at most `MINDEX_SERVICE_DOCUMENT_HISTORY_LIMIT` = 3 entries and `..._MAX_BYTES` = 450000 (the last entry is always kept) |
| `renderServiceSourceHistory` / `serviceSourceHistoryMeta` | the "이전 저장본" list: label = `updatedAt`, meta = **counts** of `sourceRecords` and `slides` |
| `restoreServiceSourceHistory` | restores **`sourceText` only** into the source textarea |

The stored `slides` of a history entry are never re-rendered or restored; only their count is shown.
The current document (`mindexServiceDocument`, presenter fallback slides) is a separate key and is
not part of this change. Server side: the `preserve_source_documents` trigger keeps both keys when a
save omits them; the atomic-save prototype strips both keys from client patches
(`mindex.worship-atomic-client.mjs`, `tests/fixtures/worship-atomic-update-prototype.sql`).

## Option S: slim entries (recommended)

Entry shape after the change:

```json
{ "kind": "worship-service-document", "version": 1, "serviceId": "...", "serviceTypeId": "...",
  "serviceDate": "...", "serviceTitle": "...", "serviceAlias": "...", "updatedAt": "...",
  "sourceSignature": "...", "slideSignature": "...",
  "sourceText": "...", "sourceRecordCount": 12, "slideCount": 48 }
```

Client (implemented, `app.js`):
- `compactServiceDocumentHistoryEntry` stops copying `slides`, `sourceRecords`, `exceptions` and writes
  `sourceRecordCount` / `slideCount` plus `contentSignature` instead.
- `contentSignature` is a signature of the full content (without `updatedAt`), computed while the arrays are
  still available. The existing rule "a change in slides, records or exceptions is recorded even when the text
  signatures are equal" is kept because the de-duplication key is `contentSignature` + `sourceText`.
- `normalizeServiceDocumentSnapshot` carries the counts and `contentSignature` only when the input has them, so
  the current document (`mindexServiceDocument`) is unchanged.
- `serviceSourceHistoryMeta` reads the counts and falls back to `array.length` for legacy entries.
- Legacy entries (with arrays) are rewritten slim the next time the history is rebuilt (any save); until then
  they are read as before. Entries slimmed by the SQL below have counts but no `contentSignature`; they are keyed by
  `sourceSignature`/`slideSignature` + `sourceText`, which is enough because restore only uses the text (worst case:
  one duplicate of an older text is kept once).
- `trimServiceDocumentHistory` keeps its 3-entry cap; the 450 KB byte cap becomes a safety net.
- Tests: `tests/test_worship_save_receipts.cjs` (shape, idempotence, de-dup against full and rewritten entries,
  counts), `tests/smoke_history_slim.py` (real save path, list, restore, bound), `smoke_app.py` (`historySlideCount`).

Existing rows (Data thread, needs an explicit go, not part of the client change):

```sql
-- 1) dry run: how much would shrink
select count(*) as services,
       sum(pg_column_size(source_ref->'mindexServiceDocumentHistory')) as bytes_now
from public.mindex_worship_services
where source_ref ? 'mindexServiceDocumentHistory';

-- 2) backup, then rewrite (run in a transaction, check row counts before commit)
create table if not exists public.mindex_worship_services_history_backup_20260920 as
  select id, source_ref->'mindexServiceDocumentHistory' as history
  from public.mindex_worship_services where source_ref ? 'mindexServiceDocumentHistory';

update public.mindex_worship_services svc
set source_ref = jsonb_set(svc.source_ref, '{mindexServiceDocumentHistory}', (
  select coalesce(jsonb_agg(
    (e - 'slides' - 'sourceRecords' - 'exceptions')
    || jsonb_build_object('slideCount', jsonb_array_length(coalesce(e->'slides', '[]')),
                          'sourceRecordCount', jsonb_array_length(coalesce(e->'sourceRecords', '[]')))
    order by ord), '[]'::jsonb)
  from jsonb_array_elements(svc.source_ref->'mindexServiceDocumentHistory') with ordinality as t(e, ord)))
where svc.source_ref ? 'mindexServiceDocumentHistory';
```

The guard trigger stores a present key as sent, so this rewrite is accepted. The statements above were run on a local
PostgreSQL (PGlite) copy of the real `mindex_worship_services` DDL and the list-view migration: order, `sourceText`,
the document key and unrelated keys were unchanged, rows without history were untouched, the counts were added, and the
rollback from the backup table restored the full entries (27 KB -> 0.6 KB on the fixture row). Not run on production. Entries keep their order and
`sourceText`, so restore behaves the same. Rollback: copy `history` back from the backup table.
Order of work: ship the client that reads both shapes first (done in the client change above), then run the data rewrite.
Without the rewrite the stored history also shrinks by itself: each service is rewritten slim on its next save.

Expected result: history 4.9 MB -> ~57 KB; opening a service with history costs the document only
(~25 KB) instead of up to ~590 KB.

## Option T: separate history table (design, not recommended yet)

Use only if history has to be kept longer than 3 entries, searched, or audited without loading the
service row.

```sql
create table public.mindex_worship_service_history (
  id uuid primary key default gen_random_uuid(),
  service_id uuid not null references public.mindex_worship_services(id) on delete cascade,
  captured_at timestamptz not null default now(),
  reason text not null default '',            -- before-element-patch, after-source-text-apply, ...
  source_signature text not null default '',
  source_text text not null default '',
  counts jsonb not null default '{}'::jsonb,  -- {"records": n, "slides": n}
  document jsonb                              -- optional full snapshot, null in the slim case
);
create index mindex_worship_service_history_service_idx
  on public.mindex_worship_service_history (service_id, captured_at desc);
```

- **Access:** RLS enabled; `anon` may `select` and `insert`, not `update`/`delete` (append-only, same
  shared-access spirit as the other worship tables, without letting a stray client rewrite history).
- **Retention:** `AFTER INSERT` trigger (security definer) deletes rows beyond the newest N per
  service (N = 3 today) and, if `document` is stored, beyond a byte budget.
- **Append path:** an RPC `append_worship_service_history(service_id, entry)` (insert + retention in one
  call) so the document save and the history append are two independent, best-effort requests. History
  is a recovery aid, not an audit log, so a failed append must not fail the save.
- **Views:** `has_service_document_history` in `mindex_worship_services_list` becomes
  `exists (select 1 from ... history where service_id = svc.id)`.
- **Client changes:** `withServiceDocumentSnapshot` and the element save path stop writing
  `mindexServiceDocumentHistory` into `source_ref` and call the append RPC; `serviceDocumentHistoryFromRef`
  becomes an on-demand read (`select ... where service_id = ... order by captured_at desc limit 3`) when
  the "이전 저장본" panel opens. The compare-and-set on `source_ref` no longer includes history, which removes
  a source of spurious conflicts.
- **Cutover (four steps, each shippable and reversible):**
  1. create the table, RPC and trigger; backfill from `source_ref` (slim shape);
  2. client reads the table first and falls back to `source_ref`; writes to both;
  3. client stops writing the key; `preserve_source_documents` keeps protecting `mindexServiceDocument` only;
  4. after a verification period, strip `mindexServiceDocumentHistory` from `source_ref`.
- **Contract impact:** `worship-data-contract.md` (new table), `worship-persistence-current.md` (Recovery row),
  the atomic-save design (history append must be inside or explicitly outside the atomic transaction),
  `supabase-rls-audit.sql` and the backup/restore scripts.
- **Risks:** two-request consistency, RLS on a new table, more moving parts than the gain justifies today.

## Comparison

| | S: slim entries | T: history table | do nothing |
| --- | --- | --- | --- |
| history size | ~57 KB total (-99 %) | rows outside `source_ref`; size per policy | 4.9 MB |
| open a service with history | ~25 KB | ~25 KB + on-demand history | up to ~590 KB |
| schema change | none | new table, RPC, trigger, RLS | none |
| client change | one file, small | save path, panel, cutover | none |
| production data rewrite | one `UPDATE` (backup + dry run) | backfill + later strip | none |
| history longer than 3 entries | no | yes | no |

## Proposed order and triggers

1. Do nothing more for startup: solved by the list view.
2. When the "open a service" cost matters, ship option S (client first, data rewrite second). Cost: small.
3. Move to option T only when one of these becomes true: history must be kept beyond 3 entries, history
   must be queried across services, or the document itself (`mindexServiceDocument`, 2.5 MB over 24
   services today) also has to leave `source_ref`.

## Open questions for the owner

- Is "이전 저장본" restore expected to bring back slide content, or only the source text as today?
  (Option S assumes only the source text, which matches the current behaviour.)
- Is 3 entries enough, or should recent services keep more once entries are ~1 KB each?
- Should the backup table from the rewrite be kept, and for how long?
