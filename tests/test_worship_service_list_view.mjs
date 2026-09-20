// Install @electric-sql/pglite in a temporary directory, then set PGLITE_ROOT.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(path.resolve(process.env.PGLITE_ROOT || '.', 'package.json'));
let pgliteEntry;
try { pgliteEntry = require.resolve('@electric-sql/pglite'); } catch {
  console.log('SKIP @electric-sql/pglite not found. Install it in a temporary directory and set PGLITE_ROOT to run this test.');
  process.exit(0);
}
const { PGlite } = await import(pathToFileURL(pgliteEntry));
const db = new PGlite();
const read = (rel) => fs.readFile(new URL(rel, import.meta.url), 'utf8');
const rows = async (sql, args = []) => (await db.query(sql, args)).rows;
const scalar = async (sql, args = []) => Object.values((await rows(sql, args))[0] || {})[0];
const LIST_COLUMNS = ['id', 'service_type_id', 'service_date', 'service_date_end', 'title', 'worship_leader', 'praise_leader', 'notes', 'created_at', 'status', 'source_ref', 'service_alias'];
const bigDoc = { kind: 'worship-service-document', slides: Array.from({ length: 50 }, (_, i) => ({ id: `s${i}`, text: 'x'.repeat(200) })) };
const history = [{ kind: 'worship-service-document', slides: [{ id: 'old' }] }];

try {
  await db.exec('create role anon; create role authenticated;');
  // Real services/sections/elements DDL, RLS policy included; only unrelated song/scripture tables are stubbed.
  await db.exec(`
    create table public.mindex_worship_service_types(id text primary key);
    create table public.mindex_worship_templates(id uuid primary key);
    create table public.mindex_songs(id uuid primary key);
    create table public.mindex_song_versions(id uuid primary key, source_song_id uuid references public.mindex_songs(id), canonical_song_id uuid);
    create table public.mindex_scriptures(id uuid primary key);
    create function public.mindex_touch_updated_at() returns trigger language plpgsql as $$ begin new.updated_at = now(); return new; end $$;
  `);
  const schema = await read('../scripts/worship-schema.sql');
  await db.exec(schema.slice(schema.indexOf('create table if not exists public.mindex_worship_services ('), schema.indexOf('-- ── Import review pipeline')));
  await db.exec(`
    alter table public.mindex_worship_services enable row level security;
    drop policy if exists "mindex_worship_services_shared_all" on public.mindex_worship_services;
    create policy "mindex_worship_services_shared_all" on public.mindex_worship_services for all to anon using (true) with check (true);
    grant all on public.mindex_worship_services to anon, authenticated;
    insert into public.mindex_worship_service_types values ('sunday-main');
  `);
  await db.exec(await read('../migrations/2026-09-20-worship-service-list-view.sql'));
  await db.exec(await read('../migrations/2026-09-20-worship-service-list-view.sql')); // idempotent

  const withDoc = await scalar(`insert into public.mindex_worship_services (service_type_id, service_date, title, service_alias, source_ref)
    values ('sunday-main', '2026-09-20', 'A', '온세대', $1::jsonb) returning id`, [JSON.stringify({ no_gathering: false, mindexServiceDocument: bigDoc, mindexServiceDocumentHistory: history })]);
  const plain = await scalar(`insert into public.mindex_worship_services (service_type_id, service_date, title, source_ref)
    values ('sunday-main', '2026-09-13', 'B', $1::jsonb) returning id`, [JSON.stringify({ created_from: 'mindex_auto_schedule' })]);

  // anon reads through the view: same columns, heavy keys gone, existence flags, order kept by caller.
  await db.exec('set role anon');
  const list = await rows('select * from public.mindex_worship_services_list order by service_date asc, service_type_id asc');
  assert.deepEqual(list.map((r) => r.title), ['B', 'A']);
  for (const column of LIST_COLUMNS) assert(column in list[0], `missing column ${column}`);
  const a = list.find((r) => r.title === 'A');
  assert.deepEqual(Object.keys(a.source_ref), ['no_gathering']);
  assert.equal(a.has_service_document, true);
  assert.equal(a.has_service_document_history, true);
  const b = list.find((r) => r.title === 'B');
  assert.equal(b.has_service_document, false);
  assert.deepEqual(b.source_ref, { created_from: 'mindex_auto_schedule' });
  assert.equal(await scalar("select source_ref->>'no_gathering' from public.mindex_worship_services_list where title = 'A'"), 'false');
  const listBytes = JSON.stringify(list).length;
  assert(listBytes < 2000, `list payload should be tiny, got ${listBytes}`);

  // Full row reads are unchanged.
  const full = await rows('select * from public.mindex_worship_services where id = $1', [withDoc]);
  assert.equal(full[0].source_ref.mindexServiceDocument.slides.length, 50);
  assert.equal(full[0].source_ref.mindexServiceDocumentHistory.length, 1);

  // The view is read-only for browser roles.
  await assert.rejects(db.exec("update public.mindex_worship_services_list set title = 'x'"), /permission denied/);
  await assert.rejects(db.exec("delete from public.mindex_worship_services_list"), /permission denied/);
  await db.exec('reset role');

  // security_invoker: a role without table access gets no rows/permission through the view either.
  await db.exec('create role nobody; grant select on public.mindex_worship_services_list to nobody; set role nobody');
  await assert.rejects(db.exec('select * from public.mindex_worship_services_list'), /permission denied/);
  await db.exec('reset role');

  // Guard: writing back a list-only source_ref keeps the stored document and history.
  await db.exec('set role anon');
  await db.query('update public.mindex_worship_services set source_ref = $1::jsonb where id = $2', [JSON.stringify({ ...a.source_ref, no_gathering: true }), withDoc]);
  let saved = (await rows('select source_ref from public.mindex_worship_services where id = $1', [withDoc]))[0].source_ref;
  assert.equal(saved.no_gathering, true, 'other source_ref keys still update');
  assert.deepEqual(saved.mindexServiceDocumentHistory, history, 'history preserved on list-only save');
  assert.equal(saved.mindexServiceDocument.slides.length, 50, 'document preserved on list-only save');

  // Normal save replaces the document and history as sent.
  const nextHistory = [{ kind: 'worship-service-document', slides: [{ id: 'newer' }] }, ...history];
  await db.query('update public.mindex_worship_services set source_ref = $1::jsonb where id = $2', [JSON.stringify({ no_gathering: true, mindexServiceDocument: { kind: 'worship-service-document', slides: [] }, mindexServiceDocumentHistory: nextHistory }), withDoc]);
  saved = (await rows('select source_ref from public.mindex_worship_services where id = $1', [withDoc]))[0].source_ref;
  assert.equal(saved.mindexServiceDocument.slides.length, 0);
  assert.equal(saved.mindexServiceDocumentHistory.length, 2);

  // Explicit JSON null removes a key; the key is dropped, not stored as null.
  await db.query(`update public.mindex_worship_services set source_ref = $1::jsonb where id = $2`, [JSON.stringify({ no_gathering: true, mindexServiceDocument: saved.mindexServiceDocument, mindexServiceDocumentHistory: null }), withDoc]);
  saved = (await rows('select source_ref from public.mindex_worship_services where id = $1', [withDoc]))[0].source_ref;
  assert(!('mindexServiceDocumentHistory' in saved), 'explicit null removes history');
  assert(saved.mindexServiceDocument, 'document kept when only history was cleared');

  // Rows without a document are unaffected; writing one in is allowed; updates that skip source_ref do not touch it.
  await db.query('update public.mindex_worship_services set source_ref = $1::jsonb where id = $2', [JSON.stringify({ created_from: 'x' }), plain]);
  assert.deepEqual((await rows('select source_ref from public.mindex_worship_services where id = $1', [plain]))[0].source_ref, { created_from: 'x' });
  await db.query('update public.mindex_worship_services set source_ref = $1::jsonb where id = $2', [JSON.stringify({ created_from: 'x', mindexServiceDocument: bigDoc }), plain]);
  assert.equal((await rows('select source_ref from public.mindex_worship_services where id = $1', [plain]))[0].source_ref.mindexServiceDocument.slides.length, 50);
  await db.query("update public.mindex_worship_services set praise_leader = 'Kim' where id = $1", [withDoc]);
  assert((await rows('select source_ref from public.mindex_worship_services where id = $1', [withDoc]))[0].source_ref.mindexServiceDocument, 'non-source_ref update leaves document');

  // Optimistic-lock style update (client compares the whole source_ref) still matches and applies.
  const current = (await rows('select source_ref from public.mindex_worship_services where id = $1', [withDoc]))[0].source_ref;
  const locked = await db.query('update public.mindex_worship_services set source_ref = $1::jsonb where id = $2 and source_ref = $3::jsonb', [JSON.stringify({ ...current, note: 1 }), withDoc, JSON.stringify(current)]);
  assert.equal(locked.affectedRows, 1);
  await db.exec('reset role');
  console.log('PASS service list view (columns, stripped keys, flags, RLS/permissions, read-only) and source document guard (preserve, replace, explicit null, lock)');
} finally { await db.close(); }
