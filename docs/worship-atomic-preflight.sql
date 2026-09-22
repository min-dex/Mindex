-- Read-only checks to run immediately before the atomic cutover.
begin transaction read only;

select current_setting('server_version') as server_version,
  current_database() as database_name,
  pg_database_size(current_database()) as database_bytes;

select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'mindex_worship_services'
  and column_name = 'save_revision';

select n.nspname as schema_name,
  p.proname as function_name,
  pg_get_function_identity_arguments(p.oid) as arguments,
  p.prosecdef as security_definer,
  pg_get_userbyid(p.proowner) as owner,
  p.proconfig as settings,
  p.proacl::text as privileges
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in (
    'get_worship_service_v1',
    'save_worship_service_v1',
    'create_worship_service_v1',
    'delete_worship_service_v1'
  )
order by p.proname;

select c.relname as relation_name,
  c.relrowsecurity as rls_enabled,
  has_table_privilege('anon', c.oid, 'select') as anon_select,
  has_table_privilege('anon', c.oid, 'insert') as anon_insert,
  has_table_privilege('anon', c.oid, 'update') as anon_update,
  has_table_privilege('anon', c.oid, 'delete') as anon_delete,
  has_table_privilege('authenticated', c.oid, 'insert') as authenticated_insert,
  has_table_privilege('authenticated', c.oid, 'update') as authenticated_update,
  has_table_privilege('authenticated', c.oid, 'delete') as authenticated_delete
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in (
    'mindex_worship_services',
    'mindex_worship_sections',
    'mindex_worship_elements',
    'mindex_worship_slides'
  )
order by c.relname;

select count(*) as service_count,
  min(save_revision) as minimum_revision,
  max(save_revision) as maximum_revision,
  count(*) filter (where save_revision < 0) as invalid_revision_count
from public.mindex_worship_services;

select count(*) as orphan_section_count
from public.mindex_worship_sections s
left join public.mindex_worship_services w on w.id = s.service_id
where w.id is null;

select count(*) as orphan_element_count
from public.mindex_worship_elements e
left join public.mindex_worship_sections s on s.id = e.section_id
where s.id is null;

select count(*) as orphan_slide_count
from public.mindex_worship_slides v
left join public.mindex_worship_elements e on e.id = v.element_id
where e.id is null;

rollback;

