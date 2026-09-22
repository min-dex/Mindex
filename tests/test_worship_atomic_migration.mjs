// Executes the production migration in a disposable PostgreSQL 17 cluster.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { openWorshipTestDb } from './helpers/worship-test-db.mjs';

const db = await openWorshipTestDb({ requirePostgres: true });
const scalar = async (sql, args = []) => Object.values((await db.query(sql, args)).rows[0])[0];
const load = path => fs.readFile(new URL(path, import.meta.url), 'utf8');

try {
  await db.exec(`
    create role anon;
    create role authenticated;
    create table public.mindex_worship_service_types(id text primary key);
    create table public.mindex_worship_templates(id uuid primary key);
    create table public.mindex_songs(id uuid primary key);
    create table public.mindex_canonical_songs(id uuid primary key);
    create table public.mindex_song_versions(
      id uuid primary key,
      source_song_id uuid references public.mindex_songs(id),
      canonical_song_id uuid references public.mindex_canonical_songs(id)
    );
    create table public.mindex_version_units(id uuid primary key, version_id uuid references public.mindex_song_versions(id));
    create table public.mindex_scriptures(id uuid primary key);
    create function public.mindex_touch_updated_at() returns trigger language plpgsql as $$
      begin new.updated_at=now(); return new; end $$;
  `);

  const schema = await load('../scripts/worship-schema.sql');
  await db.exec(schema.slice(
    schema.indexOf('create table if not exists public.mindex_worship_services ('),
    schema.indexOf('-- ── Import review pipeline'),
  ));
  await db.exec(`
    do $legacy$
    declare relation_name text;
    begin
      foreach relation_name in array array[
        'mindex_worship_services',
        'mindex_worship_sections',
        'mindex_worship_elements',
        'mindex_worship_slides'
      ] loop
        execute format('alter table public.%I enable row level security', relation_name);
        execute format('grant select, insert, update, delete on public.%I to anon, authenticated', relation_name);
        execute format('create policy legacy_shared_all on public.%I to anon, authenticated using (true) with check (true)', relation_name);
      end loop;
    end
    $legacy$;
  `);
  await db.exec("insert into public.mindex_worship_service_types values ('fixture')");

  await db.exec(await load('../migrations/2026-09-22-worship-atomic-additive.sql'));
  assert.equal(await scalar(`select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in ('get_worship_service_v1','save_worship_service_v1',
      'create_worship_service_v1','delete_worship_service_v1')`), 4);

  const serviceId = randomUUID();
  const createRequest = {
    protocolVersion: 1,
    serviceId,
    requestId: randomUUID(),
    serviceTypeId: 'fixture',
    serviceDate: '2026-09-22',
    metadataPatch: { title: 'atomic fixture' },
    sections: [],
    elements: [],
    document: { sourceText: '' },
  };

  await db.exec('set session authorization anon');
  const created = await scalar('select public.create_worship_service_v1($1)', [createRequest]);
  assert.equal(created.committedRevision, '1');
  await db.query('update public.mindex_worship_services set title=$1 where id=$2', ['legacy still works', serviceId]);
  assert.equal(await scalar('select title from public.mindex_worship_services where id=$1', [serviceId]), 'legacy still works');
  console.log('PASS additive install exposes RPCs without breaking the legacy writer');

  await db.exec('reset session authorization');
  await db.exec(await load('../migrations/2026-09-22-worship-atomic-cutover.sql'));
  await db.exec('set session authorization anon');
  await assert.rejects(
    db.query('update public.mindex_worship_services set title=$1 where id=$2', ['must fail', serviceId]),
    /permission denied/,
  );

  const saveRequest = {
    protocolVersion: 1,
    serviceId,
    requestId: randomUUID(),
    expectedRevision: '1',
    metadataPatch: { title: 'atomic only' },
    sectionPatches: [],
    elementPatches: [],
    document: { sourceText: '' },
  };
  const saved = await scalar('select public.save_worship_service_v1($1)', [saveRequest]);
  assert.equal(saved.committedRevision, '2');
  assert.equal(saved.aggregate.service.title, 'atomic only');
  assert.equal((await scalar('select public.save_worship_service_v1($1)', [saveRequest])).replayed, true);
  console.log('PASS cutover blocks direct writes while atomic save and exact retry remain available');

  await db.exec('reset session authorization');
  assert.equal(await scalar("select has_schema_privilege('anon','mindex_atomic','usage')"), false);
  assert.equal(await scalar("select has_schema_privilege('authenticated','mindex_atomic','usage')"), false);
  assert.equal(await scalar("select has_schema_privilege('mindex_atomic_writer','public','create')"), false);
  assert.equal(await scalar("select has_schema_privilege('mindex_atomic_writer','mindex_atomic','create')"), false);
  assert.equal(await scalar(`select exists(
    select 1 from pg_auth_members m
    join pg_roles member on member.oid=m.member
    join pg_roles granted on granted.oid=m.roleid
    where member.rolname='postgres' and granted.rolname='mindex_atomic_writer')`), false);
  console.log('PASS private journal and recovery schema remain unavailable to browser roles');
} finally {
  await db.close();
}
