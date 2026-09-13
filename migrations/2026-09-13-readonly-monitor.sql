-- Isolated operational telemetry. No worship tables, policies or data are changed.
begin;
create schema if not exists mindex_monitor_private;
revoke all on schema mindex_monitor_private from public, anon, authenticated;
create extension if not exists pgcrypto with schema extensions;

create table if not exists mindex_monitor_private.settings (
  singleton boolean primary key default true check (singleton),
  password_hash text,
  attempts integer not null default 0,
  window_start timestamptz not null default now()
);
insert into mindex_monitor_private.settings(singleton) values (true) on conflict do nothing;
create table if not exists mindex_monitor_private.sessions (
  id uuid primary key default gen_random_uuid(),
  token_hash text unique not null,
  kind text not null check (kind in ('reporter', 'viewer')),
  expires_at timestamptz not null,
  last_seen timestamptz not null default now(),
  status jsonb not null default '{}'
);
alter table mindex_monitor_private.settings enable row level security;
alter table mindex_monitor_private.sessions enable row level security;
revoke all on all tables in schema mindex_monitor_private from public, anon, authenticated;

-- Deliberately unavailable to browser roles; run from the trusted SQL editor.
create or replace function mindex_monitor_private.set_password(p_password text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if length(p_password) < 4 or length(p_password) > 128 then raise exception 'Invalid password length'; end if;
  update mindex_monitor_private.settings set password_hash = extensions.crypt(p_password, extensions.gen_salt('bf', 10)), attempts = 0, window_start = now();
  delete from mindex_monitor_private.sessions where kind = 'viewer';
end $$;
revoke all on function mindex_monitor_private.set_password(text) from public, anon, authenticated;

create or replace function public.mindex_monitor_login(p_password text)
returns text language plpgsql security definer set search_path = '' as $$
declare cfg mindex_monitor_private.settings; token text;
begin
  select * into cfg from mindex_monitor_private.settings where singleton for update;
  if cfg.password_hash is null then return null; end if;
  if now() - cfg.window_start >= interval '10 minutes' then
    update mindex_monitor_private.settings set attempts = 0, window_start = now() where singleton;
    cfg.attempts := 0;
  end if;
  if cfg.attempts >= 5 then return null; end if;
  update mindex_monitor_private.settings set attempts = attempts + 1 where singleton;
  if p_password is null or length(p_password) > 128 or extensions.crypt(p_password, cfg.password_hash) <> cfg.password_hash then return null; end if;
  update mindex_monitor_private.settings set attempts = 0 where singleton;
  delete from mindex_monitor_private.sessions where expires_at < now();
  if (select count(*) from mindex_monitor_private.sessions where kind = 'viewer') >= 10 then return null; end if;
  token := encode(extensions.gen_random_bytes(32), 'hex');
  insert into mindex_monitor_private.sessions(token_hash, kind, expires_at)
    values (encode(extensions.digest(token, 'sha256'), 'hex'), 'viewer', now() + interval '30 minutes');
  return token;
end $$;

create or replace function public.mindex_monitor_register()
returns text language plpgsql security definer set search_path = '' as $$
declare token text;
begin
  -- One lock also bounds anonymous registration under concurrent requests.
  perform 1 from mindex_monitor_private.settings where singleton for update;
  if not exists (select 1 from mindex_monitor_private.settings where password_hash is not null) then return null; end if;
  delete from mindex_monitor_private.sessions where expires_at < now();
  if (select count(*) from mindex_monitor_private.sessions where kind = 'reporter') >= 100 then return null; end if;
  token := encode(extensions.gen_random_bytes(32), 'hex');
  insert into mindex_monitor_private.sessions(token_hash, kind, expires_at)
    values (encode(extensions.digest(token, 'sha256'), 'hex'), 'reporter', now() + interval '24 hours');
  return token;
end $$;

create or replace function public.mindex_monitor_heartbeat(p_token text, p_status jsonb)
returns boolean language plpgsql security definer set search_path = '' as $$
declare sid uuid; clean jsonb; events jsonb;
begin
  if p_token is null or length(p_token) <> 64 or p_status is null or jsonb_typeof(p_status) <> 'object' or octet_length(p_status::text) > 12000 then return false; end if;
  select id into sid from mindex_monitor_private.sessions
    where token_hash = encode(extensions.digest(p_token, 'sha256'), 'hex') and kind = 'reporter' and expires_at > now() for update;
  if sid is null then return false; end if;
  if exists(select 1 from mindex_monitor_private.sessions where id = sid and status <> '{}' and last_seen > now() - interval '10 seconds') then return true; end if;
  select coalesce(jsonb_object_agg(k, left(p_status->>k, 120)), '{}') into clean
    from unnest(array['name','os','browser','version','module','serviceId','serviceDate','serviceType','outputServiceId']) k;
  clean := clean || jsonb_build_object(
    'output', p_status->'output' = 'true'::jsonb,
    'dirty', p_status->'dirty' = 'true'::jsonb,
    'saving', p_status->'saving' = 'true'::jsonb,
    'slide', case when p_status->>'slide' ~ '^[0-9]{1,5}$' then (p_status->>'slide')::int else 0 end,
    'count', case when p_status->>'count' ~ '^[0-9]{1,5}$' then (p_status->>'count')::int else 0 end,
    'video', case when p_status->>'video' in ('playing','loading','paused','blocked','error','ended') then p_status->>'video' else '' end);
  select coalesce(jsonb_agg(jsonb_build_object('kind', e->>'kind', 'at', left(e->>'at', 30))), '[]') into events
    from (select value e from jsonb_array_elements(case when jsonb_typeof(p_status->'events') = 'array' then p_status->'events' else '[]' end) limit 20) q
    where e->>'kind' in ('open','view','service','edit','save_start','save_ok','save_failed','output_on','output_off');
  update mindex_monitor_private.sessions set status = clean || jsonb_build_object('events', events), last_seen = now() where id = sid;
  return true;
end $$;

create or replace function public.mindex_monitor_read(p_token text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare result jsonb;
begin
  if p_token is null or length(p_token) <> 64 or not exists (
    select 1 from mindex_monitor_private.sessions where token_hash = encode(extensions.digest(p_token, 'sha256'), 'hex') and kind = 'viewer' and expires_at > now()
  ) then return null; end if;
  select coalesce(jsonb_agg(jsonb_build_object('id', id, 'last_seen', last_seen, 'status', status) order by last_seen desc), '[]') into result
    from mindex_monitor_private.sessions where kind = 'reporter' and expires_at > now() and status <> '{}';
  return result;
end $$;

create or replace function public.mindex_monitor_leave(p_token text)
returns void language sql security definer set search_path = '' as $$
  delete from mindex_monitor_private.sessions where token_hash = encode(extensions.digest(p_token, 'sha256'), 'hex');
$$;

revoke all on function public.mindex_monitor_login(text), public.mindex_monitor_register(), public.mindex_monitor_heartbeat(text,jsonb), public.mindex_monitor_read(text), public.mindex_monitor_leave(text) from public;
grant execute on function public.mindex_monitor_login(text), public.mindex_monitor_register(), public.mindex_monitor_heartbeat(text,jsonb), public.mindex_monitor_read(text), public.mindex_monitor_leave(text) to anon, authenticated;
commit;
