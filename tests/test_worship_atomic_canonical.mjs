// Disposable PostgreSQL only; canonical edits never contact the live database.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { openWorshipTestDb } from './helpers/worship-test-db.mjs';

const db = await openWorshipTestDb();
const scalar = async (sql, args = [], client = db) => Object.values((await client.query(sql, args)).rows[0])[0];
const load = file => fs.readFile(new URL(file, import.meta.url), 'utf8');
const sid = randomUUID(), other = randomUUID(), song = randomUUID(), canonical = randomUUID();
const version = randomUUID(), unit1 = randomUUID(), unit2 = randomUUID();
const read = id => scalar('select public.get_worship_service_v1($1)', [id]);
const saveRequest = revision => ({protocolVersion: 1, serviceId: sid, requestId: randomUUID(), expectedRevision: revision,
  metadataPatch: {title: 'edited'}, sectionPatches: [], elementPatches: [], document: {sourceText: 'saved instance'}});
try {
  await db.exec(`
    create role anon; create role authenticated;
    create table public.mindex_worship_service_types(id text primary key);
    create table public.mindex_worship_templates(id uuid primary key, title text);
    create table public.mindex_songs(id uuid primary key, title text);
    create table public.mindex_canonical_songs(id uuid primary key, title text);
    create table public.mindex_song_versions(id uuid primary key,
      source_song_id uuid references public.mindex_songs(id) on delete cascade,
      canonical_song_id uuid references public.mindex_canonical_songs(id) on delete cascade, version_label text);
    create table public.mindex_version_units(id uuid primary key,
      version_id uuid references public.mindex_song_versions(id) on delete cascade,
      canonical_song_id uuid references public.mindex_canonical_songs(id) on delete cascade, text text);
    create table public.mindex_scriptures(id uuid primary key, body text);
    create function public.mindex_touch_updated_at() returns trigger language plpgsql as $$
      begin new.updated_at=now(); return new; end $$;
  `);
  const schema = await load('../scripts/worship-schema.sql');
  await db.exec(schema.slice(schema.indexOf('create table if not exists public.mindex_worship_services ('),
    schema.indexOf('-- ── Import review pipeline')));
  await db.exec(await load('./fixtures/worship-atomic-update-prototype.sql'));
  await db.exec(await load('./fixtures/worship-atomic-security.sql'));
  await db.exec(await load('./fixtures/worship-atomic-canonical.sql'));
  for (const table of ['mindex_songs', 'mindex_canonical_songs', 'mindex_song_versions',
    'mindex_version_units', 'mindex_scriptures', 'mindex_worship_templates']) {
    await db.exec(`grant select,insert,update,delete on public.${table} to anon, authenticated;
      create policy collaborative_editor on public.${table} to anon, authenticated using (true) with check (true)`);
  }
  await db.exec("insert into public.mindex_worship_service_types values ('fixture')");
  await db.query('insert into public.mindex_songs values ($1,$2)', [song, 'original']);
  await db.query('insert into public.mindex_canonical_songs values ($1,$2)', [canonical, 'canonical']);
  await db.query('insert into public.mindex_song_versions values ($1,$2,$3,$4)', [version, song, canonical, 'version']);
  await db.query('insert into public.mindex_version_units values ($1,$2,$3,$4),($5,$2,$3,$6)',
    [unit1, version, canonical, 'line one', unit2, 'line two']);
  await db.exec('set session authorization anon');
  for (const [serviceId, date, linked] of [[sid, '2026-09-19', true], [other, '2026-09-20', false]]) {
    const sectionId = randomUUID(), elementId = randomUUID();
    await scalar('select public.create_worship_service_v1($1)', [{protocolVersion: 1, serviceId,
      requestId: randomUUID(), serviceTypeId: 'fixture', serviceDate: date, metadataPatch: {},
      sections: [{id: sectionId, patch: {title: 'section'}}], elements: [{id: elementId, sectionId,
        patch: {element_type: 'praise', body: 'saved lyric', ...(linked ? {song_id: song, song_version_id: version} : {})}}],
      document: {sourceText: 'saved instance', extension: {preserve: true}},
    }]);
  }
  const initial = await read(sid), unrelated = await read(other);
  await db.query('update public.mindex_songs set title=$1 where id=$2', ['renamed', song]);
  const changed = await read(sid);
  assert.equal(changed.revision, '2');
  assert.deepEqual(changed.elements, initial.elements);
  assert.deepEqual(changed.service.source_ref, initial.service.source_ref);
  assert.deepEqual(await read(other), unrelated);
  await assert.rejects(scalar('select public.save_worship_service_v1($1)', [saveRequest('1')]), /REVISION_CONFLICT/);
  await db.query('update public.mindex_songs set title=title where id=$1', [song]);
  assert.equal((await read(sid)).revision, '2');
  console.log('PASS linked metadata invalidates only affected service; saved text/document untouched; stale save and no-op handled');

  await db.exec('begin');
  await db.query('update public.mindex_version_units set text=text || $1 where version_id=$2', [' revised', version]);
  await db.query('update public.mindex_song_versions set version_label=$1 where id=$2', ['new version', version]);
  await db.exec('commit');
  assert.equal((await read(sid)).revision, '3');
  await db.exec('reset session authorization');
  assert.deepEqual(await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1', [sid]), changed);
  await db.exec('set session authorization anon');
  console.log('PASS multiple lyric rows and version edit advance once per transaction; prior aggregate checkpoint retained');

  const beforeDelete = await read(sid);
  for (const [table, id] of [['mindex_songs', song], ['mindex_song_versions', version], ['mindex_canonical_songs', canonical]]) {
    await assert.rejects(db.query(`delete from public.${table} where id=$1`, [id]), /CANONICAL_IN_USE/);
    assert.deepEqual(await read(sid), beforeDelete);
  }
  const replacement = randomUUID();
  await db.query('insert into public.mindex_songs values ($1,$2)', [replacement, 'other song']);
  await assert.rejects(db.query('update public.mindex_song_versions set source_song_id=$1 where id=$2', [replacement, version]), /LINKED_VERSION_REASSIGNMENT/);
  assert.deepEqual(await read(sid), beforeDelete);
  await db.query('delete from public.mindex_songs where id=$1', [replacement]);
  assert.deepEqual(await read(sid), beforeDelete);
  console.log('PASS referenced source/version/canonical delete and reassignment rejected; unused delete allowed');

  await db.exec('begin');
  await db.query('delete from public.mindex_version_units where id=$1', [unit2]);
  await db.exec('rollback');
  assert.deepEqual(await read(sid), beforeDelete);
  assert.equal(await scalar('select count(*)::int from public.mindex_version_units where id=$1', [unit2]), 1);
  console.log('PASS rolled-back canonical edit also rolls back revision/checkpoint invalidation');

  await db.exec('reset session authorization');
  if (db.connect) {
    const writer = await db.connect(), editor = await db.connect();
    await writer.query('set session authorization anon');
    await editor.query('set session authorization anon');
    // Canonical writer owns the dependency gate first: a stale editor waits,
    // then observes the committed revision instead of committing old content.
    await writer.query('begin');
    await writer.query('update public.mindex_version_units set text=$1 where id=$2', ['concurrent lyric', unit1]);
    const waiting = scalar('select public.save_worship_service_v1($1)', [saveRequest('3')], editor)
      .then(value => ({value}), error => ({error}));
    await writer.query('commit');
    assert.match((await waiting).error?.message || '', /REVISION_CONFLICT/);
    assert.equal((await read(sid)).revision, '4');
    console.log('PASS two backends: canonical writer wins, old editor rejects without stale overwrite');

    // Reversed order: a saved service commits first; canonical invalidation
    // runs afterward, with no cyclic service/canonical-row wait.
    await editor.query('begin');
    const committed = await scalar('select public.save_worship_service_v1($1)', [saveRequest('4')], editor);
    assert.equal(committed.committedRevision, '5');
    const canonicalWaiting = writer.query('update public.mindex_songs set title=$1 where id=$2', ['after save', song]);
    await editor.query('commit');
    await canonicalWaiting;
    assert.equal((await read(sid)).revision, '6');
    assert.deepEqual(await read(other), unrelated);
    console.log('PASS reverse lock order: save then canonical edit, monotonic revision and no deadlock');

    await editor.query('begin');
    await scalar('select public.save_worship_service_v1($1)', [saveRequest('6')], editor);
    await writer.query("set lock_timeout='100ms'");
    await assert.rejects(writer.query('update public.mindex_songs set title=$1 where id=$2', ['timeout', song]), /lock timeout/);
    await editor.query('rollback');
    assert.equal((await read(sid)).revision, '6');
    assert.equal(await scalar('select title from public.mindex_songs where id=$1', [song]), 'after save');
    console.log('PASS lock timeout preserves canonical data and rolled-back service draft');
  }
  const scriptureId = randomUUID(), templateId = randomUUID();
  await db.query('insert into public.mindex_scriptures values ($1,$2)', [scriptureId, 'scripture']);
  await db.query('insert into public.mindex_worship_templates values ($1,$2)', [templateId, 'template']);
  // Seed saved dependencies as the fixture owner, before checking public edits.
  const targetElement = (await read(other)).elements[0].id;
  await db.query('update public.mindex_worship_elements set scripture_id=$1 where id=$2', [scriptureId, targetElement]);
  await db.query('update public.mindex_worship_services set template_id=$1 where id=$2', [templateId, other]);
  const dependencyBefore = await read(other);
  await db.exec('set session authorization anon');
  await db.query('update public.mindex_scriptures set body=$1 where id=$2', ['revised scripture', scriptureId]);
  assert.equal((await read(other)).revision, '2');
  await db.query('update public.mindex_worship_templates set title=$1 where id=$2', ['revised template', templateId]);
  const dependencyAfter = await read(other);
  assert.equal(dependencyAfter.revision, '3');
  assert.deepEqual(dependencyAfter.elements, dependencyBefore.elements);
  assert.deepEqual(dependencyAfter.service.source_ref, dependencyBefore.service.source_ref);
  await assert.rejects(db.query('delete from public.mindex_scriptures where id=$1', [scriptureId]), /CANONICAL_IN_USE/);
  await assert.rejects(db.query('delete from public.mindex_worship_templates where id=$1', [templateId]), /CANONICAL_IN_USE/);
  await assert.rejects(db.exec('select * from mindex_atomic_lab.canonical_invalidations'), /permission denied/);
  console.log('PASS scripture/template revisions and FK deletion guards under canonical RLS; private markers inaccessible');
  console.log('NOT PRODUCTION: private prototype, conservative deletion policy, no live migration or activation');
} finally {
  await db.close();
}
