-- DISPOSABLE TEST ONLY. Depends on worship-atomic-update-prototype.sql.
-- This models the privilege boundary, not a reviewed production migration.
create role mindex_atomic_writer nologin noinherit nosuperuser nobypassrls;
grant usage on schema public, mindex_atomic_lab to mindex_atomic_writer;
grant select, insert, update, delete on all tables in schema mindex_atomic_lab to mindex_atomic_writer;
grant execute on all functions in schema mindex_atomic_lab to mindex_atomic_writer;
grant select on public.mindex_song_versions to mindex_atomic_writer;
-- patch_row locks the referenced version with FOR SHARE.
grant update(id) on public.mindex_song_versions to mindex_atomic_writer;
-- Canonical tables also use RLS in production; table grants alone are not enough.
alter table public.mindex_song_versions enable row level security;
create policy atomic_version_reference on public.mindex_song_versions
  for select to mindex_atomic_writer using (true);
-- FOR SHARE also applies UPDATE USING under RLS. No row mutation is needed.
create policy atomic_version_lock on public.mindex_song_versions
  for update to mindex_atomic_writer using (true) with check (false);

do $$
declare tab text;
begin
  foreach tab in array array['mindex_worship_services','mindex_worship_sections',
    'mindex_worship_elements','mindex_worship_slides'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('revoke all on public.%I from public, anon, authenticated',tab);
    execute format('grant select on public.%I to anon, authenticated',tab);
    execute format('grant select, insert, update, delete on public.%I to mindex_atomic_writer',tab);
    execute format('create policy atomic_read on public.%I for select to anon, authenticated using (true)',tab);
    execute format('create policy atomic_write on public.%I to mindex_atomic_writer using (true) with check (true)',tab);
  end loop;
end $$;

create function public.get_worship_service_v1(service_id uuid) returns jsonb
language sql stable security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic_lab.read_service(service_id) $$;
create function public.save_worship_service_v1(request jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic_lab.save_existing(request) $$;
create function public.create_worship_service_v1(request jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic_lab.create_service(request) $$;
create function public.delete_worship_service_v1(request jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic_lab.delete_service(request) $$;

alter function public.get_worship_service_v1(uuid) owner to mindex_atomic_writer;
alter function public.save_worship_service_v1(jsonb) owner to mindex_atomic_writer;
alter function public.create_worship_service_v1(jsonb) owner to mindex_atomic_writer;
alter function public.delete_worship_service_v1(jsonb) owner to mindex_atomic_writer;
revoke all on function public.get_worship_service_v1(uuid), public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb), public.delete_worship_service_v1(jsonb) from public;
grant execute on function public.get_worship_service_v1(uuid), public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb), public.delete_worship_service_v1(jsonb) to anon, authenticated;
