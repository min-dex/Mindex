-- DISPOSABLE TEST ONLY. No production installation is authorized by this file.
-- Linked deletion/reassignment is deliberately rejected pending a reviewed
-- detach-to-snapshot operation. Ordinary lyric and metadata edits remain allowed.
create table mindex_atomic_lab.canonical_invalidations (
  service_id uuid primary key references public.mindex_worship_services(id) on delete cascade,
  last_xid xid8 not null
);
revoke all on mindex_atomic_lab.canonical_invalidations from public, anon, authenticated;
grant select, insert, update, delete on mindex_atomic_lab.canonical_invalidations to mindex_atomic_writer;
grant select on public.mindex_songs, public.mindex_canonical_songs,
  public.mindex_version_units, public.mindex_scriptures, public.mindex_worship_templates to mindex_atomic_writer;

create function mindex_atomic_lab.canonical_write_gate() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
begin
  -- Before-statement ordering avoids holding a canonical row while waiting for
  -- a save that has already locked its service and needs that canonical row.
  perform pg_advisory_xact_lock(1296649816, 1);
  return null;
end $$;

create function mindex_atomic_lab.canonical_changed() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
declare prev jsonb; next jsonb; ids uuid[]; version_ids uuid[]; services uuid[];
  sid uuid; xid xid8 := pg_current_xact_id(); touched int;
begin
  if tg_op='UPDATE' and to_jsonb(old)=to_jsonb(new) then return new; end if;
  if tg_op<>'INSERT' then prev := to_jsonb(old); end if;
  if tg_op<>'DELETE' then next := to_jsonb(new); end if;
  ids := array_remove(array[(prev->>'id')::uuid,(next->>'id')::uuid],null);
  if tg_table_name='mindex_version_units' then
    version_ids := array_remove(array[(prev->>'version_id')::uuid,(next->>'version_id')::uuid],null);
  elsif tg_table_name='mindex_song_versions' then
    version_ids := ids;
  elsif tg_table_name='mindex_songs' then
    select array_agg(id) into version_ids from public.mindex_song_versions
      where source_song_id=any(ids);
  elsif tg_table_name='mindex_canonical_songs' then
    select array_agg(id) into version_ids from public.mindex_song_versions
      where canonical_song_id=any(ids);
  elsif tg_table_name in ('mindex_scriptures','mindex_worship_templates') then
    version_ids := '{}';
  else
    raise exception 'INVALID_CANONICAL_TABLE';
  end if;
  select array_agg(distinct affected.service_id order by affected.service_id) into services from (
    select s.service_id from public.mindex_worship_elements e
      join public.mindex_worship_sections s on s.id=e.section_id
      where e.song_version_id=any(coalesce(version_ids,'{}'))
        or (tg_table_name='mindex_songs' and e.song_id=any(ids))
        or (tg_table_name='mindex_scriptures' and e.scripture_id=any(ids))
        or (tg_table_name='mindex_worship_templates' and (e.template_id=any(ids) or s.template_id=any(ids)))
    union
    select s.id from public.mindex_worship_services s
      where tg_table_name='mindex_worship_templates' and s.template_id=any(ids)
    union
    select s.service_id from public.mindex_worship_sections s
      where tg_table_name='mindex_worship_templates' and s.template_id=any(ids)
    union
    select s.service_id from public.mindex_worship_slides v
      join public.mindex_worship_elements e on e.id=v.element_id
      join public.mindex_worship_sections s on s.id=e.section_id
      where tg_table_name='mindex_worship_templates' and v.template_id=any(ids)
  ) affected;
  if cardinality(services)>0 and tg_op='DELETE' and tg_table_name<>'mindex_version_units'
    then raise exception 'CANONICAL_IN_USE' using errcode='23503'; end if;
  if tg_table_name='mindex_song_versions' and tg_op='UPDATE' then
    if exists(select from public.mindex_worship_elements e where e.song_version_id=old.id
      and e.song_id is distinct from coalesce(new.source_song_id,new.canonical_song_id))
      then raise exception 'LINKED_VERSION_REASSIGNMENT' using errcode='23503'; end if;
  end if;
  foreach sid in array coalesce(services,'{}') loop
    perform pg_advisory_xact_lock(hashtextextended(sid::text,0));
    perform 1 from public.mindex_worship_services where id=sid for update;
    -- Once per transaction/service, even for multi-row unit edits and UPSERT.
    -- A private table is used instead of a caller-forgeable setting or temp table.
    insert into mindex_atomic_lab.canonical_invalidations values(sid,xid)
      on conflict(service_id) do update set last_xid=excluded.last_xid
      where mindex_atomic_lab.canonical_invalidations.last_xid<>excluded.last_xid;
    get diagnostics touched = row_count;
    if touched=1 then
      insert into mindex_atomic_lab.checkpoints values(sid,mindex_atomic_lab.read_service(sid))
        on conflict(service_id) do update set aggregate=excluded.aggregate;
      update public.mindex_worship_services set save_revision=save_revision+1 where id=sid;
    end if;
  end loop;
  if tg_op='DELETE' then return old; else return new; end if;
end $$;

alter function mindex_atomic_lab.canonical_write_gate() owner to mindex_atomic_writer;
alter function mindex_atomic_lab.canonical_changed() owner to mindex_atomic_writer;
revoke all on function mindex_atomic_lab.canonical_write_gate(), mindex_atomic_lab.canonical_changed() from public;
do $$
declare tab text;
begin
  foreach tab in array array['mindex_songs','mindex_canonical_songs','mindex_song_versions',
    'mindex_version_units','mindex_scriptures','mindex_worship_templates'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('create policy atomic_dependency_read on public.%I for select to mindex_atomic_writer using (true)',tab);
    execute format('create trigger atomic_canonical_gate before insert or update or delete on public.%I
      for each statement execute function mindex_atomic_lab.canonical_write_gate()',tab);
    execute format('create trigger atomic_canonical_change before insert or update or delete on public.%I
      for each row execute function mindex_atomic_lab.canonical_changed()',tab);
  end loop;
end $$;
