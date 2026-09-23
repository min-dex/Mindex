-- One bulletin per worship service: content + layout, with optimistic saves.
-- Matches the existing shared Worship client roles; no service-role key in the app.
begin;
create table public.mindex_bulletins (
  service_id uuid primary key references public.mindex_worship_services(id) on delete cascade,
  content jsonb not null default '{}' check (jsonb_typeof(content) = 'object'),
  layout jsonb not null default '{}' check (jsonb_typeof(layout) = 'object'),
  revision integer not null default 1 check (revision > 0),
  updated_at timestamptz not null default now()
);
create function public.mindex_bulletin_revision() returns trigger
language plpgsql set search_path=pg_catalog,pg_temp as $$
begin
  if TG_OP='INSERT' then new.revision:=1;
  else
    if new.service_id<>old.service_id then raise exception 'BULLETIN_SERVICE_IMMUTABLE'; end if;
    new.revision:=old.revision+1;
  end if;
  new.updated_at:=now();
  return new;
end;
$$;
create trigger mindex_bulletin_revision before insert or update on public.mindex_bulletins
for each row execute function public.mindex_bulletin_revision();
alter table public.mindex_bulletins enable row level security;
create policy bulletin_shared_read on public.mindex_bulletins for select to anon,authenticated using (true);
create policy bulletin_shared_insert on public.mindex_bulletins for insert to anon,authenticated with check (
  exists(select 1 from public.mindex_worship_services s where s.id=service_id)
);
create policy bulletin_shared_update on public.mindex_bulletins for update to anon,authenticated using (true) with check (
  exists(select 1 from public.mindex_worship_services s where s.id=service_id)
);
grant select,insert,update on public.mindex_bulletins to anon,authenticated;
notify pgrst, 'reload schema';
commit;
