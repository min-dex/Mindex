// Private recovery exercise in a disposable database. Never accepts live credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { openWorshipTestDb } from './helpers/worship-test-db.mjs';

const db = await openWorshipTestDb({ requirePostgres: true });
const scalar = async (sql, args = [], client = db) => Object.values((await client.query(sql, args)).rows[0])[0];
const load = file => fs.readFile(new URL(file, import.meta.url), 'utf8');
const sid = randomUUID(), section = randomUUID(), element = randomUUID(), slide = randomUUID();
const song = randomUUID(), version = randomUUID();
const read = () => scalar('select mindex_atomic_lab.read_service($1)', [sid]);
const restore = req => scalar('select mindex_atomic_lab.restore_checkpoint($1)', [req]);
const request = (revision, checkpointRevision) => ({protocolVersion: 1, serviceId: sid, requestId: randomUUID(),
  expectedRevision: revision, checkpointRevision, confirmRestore: true});
const checkpoint = () => scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1', [sid]);
const metadata = {title: 'original', source_ref: {extension: {keep: true}}};
try {
  await db.exec(`create role anon; create role authenticated;
    create table public.mindex_worship_service_types(id text primary key);
    create table public.mindex_worship_templates(id uuid primary key);
    create table public.mindex_songs(id uuid primary key);
    create table public.mindex_song_versions(id uuid primary key, source_song_id uuid references public.mindex_songs(id), canonical_song_id uuid);
    create table public.mindex_scriptures(id uuid primary key);
    create function public.mindex_touch_updated_at() returns trigger language plpgsql as $$
      begin new.updated_at=now(); return new; end $$;`);
  const schema = await load('../scripts/worship-schema.sql');
  await db.exec(schema.slice(schema.indexOf('create table if not exists public.mindex_worship_services ('),
    schema.indexOf('-- ── Import review pipeline')));
  await db.exec(await load('./fixtures/worship-atomic-update-prototype.sql'));
  await db.exec(await load('./fixtures/worship-atomic-security.sql'));
  await db.exec(await load('./fixtures/worship-atomic-restore.sql'));
  await db.exec("insert into public.mindex_worship_service_types values ('fixture')");
  await db.query('insert into public.mindex_songs values ($1)', [song]);
  await db.query('insert into public.mindex_song_versions values ($1,$2,null)', [version, song]);
  await scalar('select mindex_atomic_lab.create_service($1)', [{protocolVersion: 1, serviceId: sid,
    requestId: randomUUID(), serviceTypeId: 'fixture', serviceDate: '2026-09-19', metadataPatch: metadata,
    sections: [{id: section, patch: {title: 'section'}}], elements: [{id: element, sectionId: section,
      patch: {element_type: 'praise', song_id: song, song_version_id: version, body: 'saved lyric',
        config: {exception: 'preserved'}, asset: {url: 'https://example.invalid/image.png'}}}],
    document: {sourceText: 'saved source', custom: {keep: true}},
  }]);
  await db.query('insert into public.mindex_worship_slides(id,element_id,slide_type,body) values($1,$2,$3,$4)',
    [slide, element, 'plain_text', 'saved slide']);
  const original = await read();
  await scalar('select mindex_atomic_lab.save_existing($1)', [{protocolVersion: 1, serviceId: sid,
    requestId: randomUUID(), expectedRevision: '1', metadataPatch: {title: 'changed'},
    deleteElementIds: [element], document: {sourceText: 'changed source'}}]);
  const changed = await read();
  assert.equal(changed.elements.length, 0);
  assert.deepEqual(await checkpoint(), original);
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`set session authorization ${role}`);
    await assert.rejects(restore(request('2', '1')), /permission denied/);
    await db.exec('reset session authorization');
  }
  console.log('PASS recovery is not exposed to browser roles');

  await assert.rejects(restore({...request('2', '1'), confirmRestore: 'true'}), /RESTORE_INTENT_REQUIRED/);
  await assert.rejects(restore(request('1', '1')), /REVISION_CONFLICT/);
  await assert.rejects(restore(request('2', '0')), /CHECKPOINT_CHANGED/);
  await assert.rejects(restore({...request('2', '1'), aggregate: original}), /UNKNOWN_REQUEST_FIELD/);
  assert.deepEqual(await read(), changed);
  const receipts = await scalar('select count(*)::int from mindex_atomic_lab.receipts');
  for (const [stage, table, operation] of [
    ['root', 'public.mindex_worship_services', 'update'],
    ['section', 'public.mindex_worship_sections', 'insert'],
    ['element', 'public.mindex_worship_elements', 'insert'],
    ['slide', 'public.mindex_worship_slides', 'insert'],
    ['checkpoint', 'mindex_atomic_lab.checkpoints', 'update'],
    ['receipt', 'mindex_atomic_lab.receipts', 'insert'],
  ]) {
    await db.exec(`create function mindex_atomic_lab.fail_restore() returns trigger language plpgsql as $$
      begin raise exception 'RESTORE_FAILURE'; end $$;
      create trigger restore_failure before ${operation} on ${table}
      for each row execute function mindex_atomic_lab.fail_restore();`);
    await assert.rejects(restore(request('2', '1')), /RESTORE_FAILURE/);
    assert.deepEqual(await read(), changed);
    assert.deepEqual(await checkpoint(), original);
    assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.receipts'), receipts);
    await db.exec(`drop trigger restore_failure on ${table}; drop function mindex_atomic_lab.fail_restore()`);
    console.log('PASS recovery rollback at', stage);
  }
  const recover = request('2', '1');
  const recovered = await restore(recover);
  assert.equal(recovered.committedRevision, '3');
  assert.equal(recovered.aggregate.service.title, original.service.title);
  assert.deepEqual(recovered.aggregate.service.source_ref, original.service.source_ref);
  for (const key of ['id', 'section_id', 'song_id', 'song_version_id', 'body', 'config', 'asset']) {
    assert.deepEqual(recovered.aggregate.elements[0][key], original.elements[0][key]);
  }
  assert.deepEqual(recovered.aggregate.slides, original.slides);
  assert.deepEqual(await checkpoint(), changed);
  assert.equal((await restore(recover)).replayed, true);
  assert.equal((await read()).revision, '3');
  await assert.rejects(restore({...recover, checkpointRevision: '2'}), /REQUEST_ID_REUSED/);
  console.log('PASS content, stable IDs, links, assets and stored slides restored at a new revision; exact retry writes once');

  await scalar('select mindex_atomic_lab.delete_service($1)', [{protocolVersion: 1, serviceId: sid,
    requestId: randomUUID(), expectedRevision: '3', confirmDelete: true}]);
  assert.equal(await read(), null);
  const deletedCheckpoint = await checkpoint();
  // A removed source cannot be silently detached during recovery.
  await db.query('delete from public.mindex_song_versions where id=$1', [version]);
  await assert.rejects(restore(request('4', '3')), /foreign key/);
  assert.equal(await read(), null);
  assert.deepEqual(await checkpoint(), deletedCheckpoint);
  assert.equal(await scalar('select revision::text from mindex_atomic_lab.tombstones where service_id=$1', [sid]), '4');
  await db.query('insert into public.mindex_song_versions values ($1,$2,null)', [version, song]);
  const otherSong = randomUUID();
  await db.query('insert into public.mindex_songs values ($1)', [otherSong]);
  await db.query('update public.mindex_song_versions set source_song_id=$1 where id=$2', [otherSong, version]);
  await assert.rejects(restore(request('4', '3')), /SONG_VERSION_MISMATCH/);
  assert.equal(await read(), null);
  assert.deepEqual(await checkpoint(), deletedCheckpoint);
  await db.query('update public.mindex_song_versions set source_song_id=$1 where id=$2', [song, version]);
  const competitor = randomUUID();
  await scalar('select mindex_atomic_lab.create_service($1)', [{protocolVersion: 1, serviceId: competitor,
    requestId: randomUUID(), serviceTypeId: 'fixture', serviceDate: '2026-09-19', metadataPatch: metadata,
    sections: [], elements: [], document: {sourceText: 'another service'}}]);
  await assert.rejects(restore(request('4', '3')), /duplicate key/);
  assert.equal(await read(), null);
  await scalar('select mindex_atomic_lab.delete_service($1)', [{protocolVersion: 1, serviceId: competitor,
    requestId: randomUUID(), expectedRevision: '1', confirmDelete: true}]);
  const foreign = randomUUID();
  await scalar('select mindex_atomic_lab.create_service($1)', [{protocolVersion: 1, serviceId: foreign,
    requestId: randomUUID(), serviceTypeId: 'fixture', serviceDate: '2026-09-20', metadataPatch: {},
    sections: [{id: section, patch: {title: 'foreign section'}}], elements: [], document: {sourceText: 'foreign'}}]);
  const foreignState = await scalar('select mindex_atomic_lab.read_service($1)', [foreign]);
  await assert.rejects(restore(request('4', '3')), /duplicate key/);
  assert.deepEqual(await scalar('select mindex_atomic_lab.read_service($1)', [foreign]), foreignState);
  assert.equal(await read(), null);
  await scalar('select mindex_atomic_lab.delete_service($1)', [{protocolVersion: 1, serviceId: foreign,
    requestId: randomUUID(), expectedRevision: '1', confirmDelete: true}]);
  const undelete = request('4', '3');
  assert.equal((await restore(undelete)).committedRevision, '5');
  assert.equal((await restore(undelete)).replayed, true);
  assert.equal((await read()).elements[0].song_version_id, version);
  assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.tombstones where service_id=$1', [sid]), 0);
  console.log('PASS deleted-service restore: monotonic revisions; missing/reassigned references and foreign UUID/identity collisions roll back');

  if (db.connect) {
    const a = await db.connect(), b = await db.connect();
    const results = await Promise.allSettled([a, b].map(client => scalar(
      'select mindex_atomic_lab.restore_checkpoint($1)', [request('5', '3')], client)));
    assert.equal(results.filter(result => result.status === 'fulfilled').length, 1);
    assert.match(results.find(result => result.status === 'rejected').reason.message, /REVISION_CONFLICT/);
    assert.equal((await read()).revision, '6');
    console.log('PASS two competing recovery sessions commit once; the other conflicts');
  }
  console.log('NOT PRODUCTION: private checkpoint recovery only; operational backup restore and approval UI are not covered');
} finally {
  await db.close();
}
