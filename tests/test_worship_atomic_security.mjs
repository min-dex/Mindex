// Disposable role/RLS integration test. Never accepts production credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { openWorshipTestDb } from './helpers/worship-test-db.mjs';

const db = await openWorshipTestDb();
const scalar = async (sql, args = []) => Object.values((await db.query(sql, args)).rows[0])[0];
const fixture = name => fs.readFile(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
try {
  await db.exec(`
    create role anon; create role authenticated; create role unrelated;
    create table public.mindex_worship_service_types(id text primary key);
    create table public.mindex_worship_templates(id uuid primary key);
    create table public.mindex_songs(id uuid primary key);
    create table public.mindex_song_versions(id uuid primary key, source_song_id uuid references public.mindex_songs(id), canonical_song_id uuid);
    create table public.mindex_scriptures(id uuid primary key);
    create function public.mindex_touch_updated_at() returns trigger language plpgsql as $$
      begin new.updated_at=now(); return new; end $$;
  `);
  const schema = await fs.readFile(new URL('../scripts/worship-schema.sql', import.meta.url), 'utf8');
  await db.exec(schema.slice(schema.indexOf('create table if not exists public.mindex_worship_services ('),
    schema.indexOf('-- ── Import review pipeline')));
  await db.exec(await fixture('worship-atomic-update-prototype.sql'));
  await db.exec(await fixture('worship-atomic-security.sql'));
  await db.exec("insert into public.mindex_worship_service_types values ('fixture')");
  const serviceId = randomUUID(), sectionId = randomUUID(), elementId = randomUUID();
  const songId = randomUUID(), versionId = randomUUID();
  await db.query('insert into public.mindex_songs values ($1)', [songId]);
  await db.query('insert into public.mindex_song_versions values ($1,$2,null)', [versionId, songId]);
  const request = {
    protocolVersion: 1, serviceId, requestId: randomUUID(), serviceTypeId: 'fixture', serviceDate: '2026-09-19',
    metadataPatch: {}, sections: [{id: sectionId, patch: {title: 'section'}}],
    elements: [{id: elementId, sectionId, patch: {element_type: 'praise', song_id: songId, song_version_id: versionId}}],
    document: {sourceText: 'fixture'},
  };
  const read = () => scalar('select public.get_worship_service_v1($1)', [serviceId]);
  const save = req => scalar('select public.save_worship_service_v1($1)', [req]);
  await db.exec('set session authorization anon');
  const created = await scalar('select public.create_worship_service_v1($1)', [request]);
  assert.equal(created.committedRevision, '1');
  assert.equal((await read()).elements[0].song_version_id, versionId);
  console.log('PASS anonymous create/read including canonical pair lock under least-privileged owner');

  for (const role of ['anon', 'authenticated']) {
    await db.exec(`reset session authorization; set session authorization ${role}`);
    for (const table of ['services', 'sections', 'elements', 'slides']) {
      const name = `public.mindex_worship_${table}`;
      await db.query(`select * from ${name} limit 1`);
      await assert.rejects(db.exec(`update ${name} set id=id where false`), /permission denied/);
      await assert.rejects(db.exec(`delete from ${name} where false`), /permission denied/);
      await assert.rejects(db.exec(`insert into ${name} (id) values (gen_random_uuid())`), /permission denied/);
    }
    await assert.rejects(db.exec('select * from mindex_atomic_lab.receipts'), /permission denied/);
    await assert.rejects(db.exec("select mindex_atomic_lab.patch_row('service', gen_random_uuid(), '{}')"), /permission denied/);
    await assert.rejects(db.exec('set role mindex_atomic_writer'), /permission denied/);
    console.log(`PASS ${role}: presenter reads retained, direct writes/private helpers/role escalation denied`);
  }
  const change = {protocolVersion: 1, serviceId, requestId: randomUUID(), expectedRevision: '1',
    metadataPatch: {title: 'saved'}, sectionPatches: [], elementPatches: [], document: {sourceText: 'saved'}};
  const saved = await save(change);
  assert.equal(saved.committedRevision, '2');
  assert.equal((await save(change)).replayed, true);
  const baseline = await read();
  await assert.rejects(save({...change, requestId: randomUUID()}), /REVISION_CONFLICT/);
  assert.deepEqual(await read(), baseline);
  console.log('PASS authenticated save, exact retry, stale rejection under RLS');

  await db.exec('create temporary table mindex_worship_services(id uuid, title text)');
  assert.deepEqual(await read(), baseline);
  await db.exec('reset session authorization');
  await db.exec(`create function mindex_atomic_lab.fail_receipt() returns trigger language plpgsql as $$
    begin raise exception 'INJECTED_RECEIPT_FAILURE'; end $$;
    create trigger injected_failure before insert on mindex_atomic_lab.receipts
    for each row execute function mindex_atomic_lab.fail_receipt();`);
  const checkpoint = await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1', [serviceId]);
  await db.exec('set session authorization anon');
  await assert.rejects(save({...change, requestId: randomUUID(), expectedRevision: '2',
    metadataPatch: {title: 'must rollback'}, document: {sourceText: 'must rollback'}}), /INJECTED_RECEIPT_FAILURE/);
  assert.deepEqual(await read(), baseline);
  await db.exec('reset session authorization');
  assert.deepEqual(await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1', [serviceId]), checkpoint);
  await db.exec('drop trigger injected_failure on mindex_atomic_lab.receipts; drop function mindex_atomic_lab.fail_receipt()');
  console.log('PASS temporary table shadow cannot redirect read; definer save rolls back rows, document and checkpoint');

  const owner = (await db.query("select rolcanlogin, rolsuper, rolbypassrls from pg_roles where rolname='mindex_atomic_writer'")).rows[0];
  assert.deepEqual(owner, {rolcanlogin: false, rolsuper: false, rolbypassrls: false});
  const wrappers = (await db.query("select p.prosecdef, p.proconfig, pg_get_userbyid(p.proowner) as owner from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('get_worship_service_v1','save_worship_service_v1','create_worship_service_v1','delete_worship_service_v1')")).rows;
  assert.equal(wrappers.length, 4);
  for (const fn of wrappers) {
    assert.equal(fn.prosecdef, true);
    assert.equal(fn.owner, 'mindex_atomic_writer');
    assert.deepEqual(fn.proconfig, ['search_path=pg_catalog, pg_temp']);
  }
  await db.exec('set session authorization unrelated');
  await assert.rejects(read(), /permission denied/);
  await db.exec('reset session authorization; set session authorization anon');
  const deleted = await scalar('select public.delete_worship_service_v1($1)', [{
    protocolVersion: 1, serviceId, requestId: randomUUID(), expectedRevision: '2', confirmDelete: true,
  }]);
  assert.equal(deleted.deleted, true);
  assert.equal(await read(), null);
  await db.exec('reset session authorization');
  assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.checkpoints'), 1);
  console.log('PASS fixed definer ownership/search_path, PUBLIC denial, delete and private recovery retained');
  console.log('NOT PRODUCTION: canonical invalidation, retention/recovery UI, operational cutover remain separate gates');
} finally {
  await db.close();
}
