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
- `chromakey-ready-loop-fast.mp4` 3.9 MB is `rel=prefetch` (idle priority) on every page.
- Three Freesentation weights ~1.4 MB are preloaded; lowering their priority with
  `fetchpriority="low"` was tried and showed no effect on the deployed site.
