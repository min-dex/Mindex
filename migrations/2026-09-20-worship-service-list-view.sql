-- Worship service list read path (UX -> Data handoff, docs/handoff-worship-service-list-payload.md).
--
-- Why: the first screen reads every service row. On 93 rows that is ~1 MB gzip / 7.7 MB decoded,
-- and >99% of it is two source_ref keys (mindexServiceDocument, mindexServiceDocumentHistory)
-- that the list never renders. This adds a light read view and a server-side guard so a list-only
-- source_ref can never wipe the stored document/history.
--
-- Scope: one read-only view + one BEFORE UPDATE trigger. No table/column/data change; existing
-- select("*").eq("id", ...) reads and all current writes keep working.
-- Idempotent. Roll back with the statements at the bottom.
begin;

-- 1) Light list view -------------------------------------------------------------------------
-- security_invoker: the caller's role and RLS apply exactly as on mindex_worship_services
-- (anon keeps the existing shared-access policy). Column names match the list select so the
-- client only swaps the table name; ordering stays the caller's .order(...) (uses
-- mindex_worship_services_date_type_idx).
create or replace view public.mindex_worship_services_list
with (security_invoker = true) as
select
  svc.id,
  svc.service_type_id,
  svc.service_date,
  svc.service_date_end,
  svc.title,
  svc.service_alias,
  svc.worship_leader,
  svc.praise_leader,
  svc.notes,
  svc.status,
  svc.created_at,
  svc.updated_at,
  svc.source_ref - 'mindexServiceDocument' - 'mindexServiceDocumentHistory' as source_ref,
  (svc.source_ref ? 'mindexServiceDocument') as has_service_document,
  (svc.source_ref ? 'mindexServiceDocumentHistory') as has_service_document_history
from public.mindex_worship_services svc;

comment on view public.mindex_worship_services_list is
  'Read-only list of worship services. source_ref omits mindexServiceDocument and mindexServiceDocumentHistory; use has_service_document* to know they exist and read the full row from mindex_worship_services when a service is opened. Never write a source_ref read from this view back to mindex_worship_services.';

revoke all on public.mindex_worship_services_list from public, anon, authenticated;
grant select on public.mindex_worship_services_list to anon, authenticated;

-- 2) Server-side guard for the stored document + history ---------------------------------------
-- A source_ref written back from the light list (or any stale copy) has no document/history keys.
-- The client normally replaces the whole source_ref, which would silently erase them. Rule:
--   * key absent in the new source_ref while the row has it -> keep the stored value;
--   * key present -> the new value is stored as sent (normal save/replace);
--   * key present with JSON null -> explicit removal (the key is dropped).
create or replace function public.mindex_worship_services_preserve_source_documents()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  protected_key text;
begin
  if jsonb_typeof(new.source_ref) is distinct from 'object' or jsonb_typeof(old.source_ref) is distinct from 'object' then
    return new;
  end if;
  foreach protected_key in array array['mindexServiceDocument', 'mindexServiceDocumentHistory'] loop
    if new.source_ref -> protected_key = 'null'::jsonb then
      new.source_ref := new.source_ref - protected_key;
    elsif not (new.source_ref ? protected_key) and (old.source_ref ? protected_key) then
      new.source_ref := new.source_ref || jsonb_build_object(protected_key, old.source_ref -> protected_key);
    end if;
  end loop;
  return new;
end;
$$;

drop trigger if exists mindex_worship_services_preserve_source_documents on public.mindex_worship_services;
create trigger mindex_worship_services_preserve_source_documents
before update of source_ref on public.mindex_worship_services
for each row execute function public.mindex_worship_services_preserve_source_documents();

commit;

-- Rollback:
--   drop trigger if exists mindex_worship_services_preserve_source_documents on public.mindex_worship_services;
--   drop function if exists public.mindex_worship_services_preserve_source_documents();
--   drop view if exists public.mindex_worship_services_list;
