-- Compact legacy worship source-history entries.
--
-- The current client stores only sourceText, signatures and counts in
-- mindexServiceDocumentHistory. Older entries also keep rendered slides and
-- source-record arrays, although restore only reads sourceText. This migration
-- removes those redundant arrays from history entries only. It intentionally
-- does not alter mindexServiceDocument, because that legacy current document
-- can still be a presenter fallback for services whose canonical rows are
-- unavailable.
--
-- Run the preflight query below in the Supabase SQL Editor first. The backup
-- table is retained for rollback; drop it only after the chosen retention
-- period. The migration is idempotent: the first captured value for each
-- service is never overwritten on subsequent runs.

-- Preflight (read-only):
-- select count(*) as services,
--        sum(pg_column_size(source_ref -> 'mindexServiceDocumentHistory')) as history_bytes,
--        sum(pg_column_size(source_ref -> 'mindexServiceDocument')) as current_document_bytes
-- from public.mindex_worship_services
-- where jsonb_typeof(source_ref -> 'mindexServiceDocumentHistory') = 'array';

begin;

create table if not exists public.mindex_worship_service_history_backup_20260926 (
  service_id uuid primary key references public.mindex_worship_services(id) on delete cascade,
  history jsonb not null,
  backed_up_at timestamptz not null default now()
);

comment on table public.mindex_worship_service_history_backup_20260926 is
  'Rollback backup for migrations/2026-09-26-worship-document-history-compaction.sql. Keep until the compacted history has been verified.';

-- Save each original history once, but only for rows that still contain legacy
-- rendering arrays. The INSERT precedes the UPDATE in the same transaction.
insert into public.mindex_worship_service_history_backup_20260926 (service_id, history)
select svc.id, svc.source_ref -> 'mindexServiceDocumentHistory'
from public.mindex_worship_services svc
where jsonb_typeof(svc.source_ref -> 'mindexServiceDocumentHistory') = 'array'
  and exists (
    select 1
    from jsonb_array_elements(svc.source_ref -> 'mindexServiceDocumentHistory') as entry(value)
    where jsonb_typeof(entry.value) = 'object'
      and entry.value ?| array['slides', 'sourceRecords', 'exceptions']
  )
on conflict (service_id) do nothing;

update public.mindex_worship_services svc
set source_ref = jsonb_set(svc.source_ref, '{mindexServiceDocumentHistory}', compacted.history, true)
from lateral (
  select coalesce(jsonb_agg(
    case
      when jsonb_typeof(entry.value) <> 'object' then entry.value
      else
        (entry.value - 'slides' - 'sourceRecords' - 'exceptions')
        || jsonb_build_object(
          'slideCount', case
            when jsonb_typeof(entry.value -> 'slides') = 'array' then jsonb_array_length(entry.value -> 'slides')
            when coalesce(entry.value ->> 'slideCount', '') ~ '^[0-9]+$' then (entry.value ->> 'slideCount')::integer
            else 0
          end,
          'sourceRecordCount', case
            when jsonb_typeof(entry.value -> 'sourceRecords') = 'array' then jsonb_array_length(entry.value -> 'sourceRecords')
            when coalesce(entry.value ->> 'sourceRecordCount', '') ~ '^[0-9]+$' then (entry.value ->> 'sourceRecordCount')::integer
            else 0
          end
        )
    end
    order by entry.ordinality
  ), '[]'::jsonb) as history
  from jsonb_array_elements(svc.source_ref -> 'mindexServiceDocumentHistory') with ordinality as entry(value, ordinality)
) compacted
where jsonb_typeof(svc.source_ref -> 'mindexServiceDocumentHistory') = 'array'
  and exists (
    select 1
    from jsonb_array_elements(svc.source_ref -> 'mindexServiceDocumentHistory') as entry(value)
    where jsonb_typeof(entry.value) = 'object'
      and entry.value ?| array['slides', 'sourceRecords', 'exceptions']
  );

commit;

-- Postflight (read-only):
-- select count(*) as services,
--        sum(pg_column_size(source_ref -> 'mindexServiceDocumentHistory')) as compacted_history_bytes,
--        count(*) filter (where exists (
--          select 1 from jsonb_array_elements(source_ref -> 'mindexServiceDocumentHistory') as entry(value)
--          where jsonb_typeof(entry.value) = 'object'
--            and entry.value ?| array['slides', 'sourceRecords', 'exceptions']
--        )) as legacy_entries_remaining
-- from public.mindex_worship_services
-- where jsonb_typeof(source_ref -> 'mindexServiceDocumentHistory') = 'array';
--
-- Rollback (only while the backup table is retained):
-- update public.mindex_worship_services svc
-- set source_ref = jsonb_set(svc.source_ref, '{mindexServiceDocumentHistory}', backup.history, true)
-- from public.mindex_worship_service_history_backup_20260926 backup
-- where backup.service_id = svc.id;
