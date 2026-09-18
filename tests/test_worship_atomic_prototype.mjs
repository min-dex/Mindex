// Disposable PostgreSQL engine only. Never reads credentials or contacts Supabase.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { openWorshipTestDb } from './helpers/worship-test-db.mjs';
import { createWorshipStore } from '../mindex.worship-store.mjs';

const db = await openWorshipTestDb();
const scalar = async (sql, args=[]) => Object.values((await db.query(sql,args)).rows[0])[0];
const sid=randomUUID(), other=randomUUID(), section=randomUUID(), element=randomUUID(), foreign=randomUUID();
try {
  await db.exec(`
    create role anon;
    create table mindex_worship_service_types(id text primary key);
    create table mindex_worship_templates(id uuid primary key);
    create table mindex_songs(id uuid primary key);
    create table mindex_song_versions(id uuid primary key,source_song_id uuid references mindex_songs(id),canonical_song_id uuid);
    create table mindex_scriptures(id uuid primary key);
    create function mindex_touch_updated_at() returns trigger language plpgsql as $$
      begin new.updated_at=now(); return new; end $$;
  `);
  const schema=await fs.readFile(new URL('../scripts/worship-schema.sql',import.meta.url),'utf8');
  await db.exec(schema.slice(schema.indexOf('create table if not exists public.mindex_worship_services ('),
    schema.indexOf('-- ── Import review pipeline')));
  await db.exec(await fs.readFile(new URL('./fixtures/worship-atomic-update-prototype.sql',import.meta.url),'utf8'));
  await db.exec("insert into mindex_worship_service_types values('fixture')");
  for (const [id,date] of [[sid,'2026-09-17'],[other,'2026-09-18']]) {
    await db.query('insert into mindex_worship_services(id,service_type_id,service_date,source_ref) values($1,$2,$3,$4)',
      [id,'fixture',date,{custom:'keep',mindexServiceDocument:{sourceText:'before'}}]);
  }
  await db.query('insert into mindex_worship_sections(id,service_id,title) values($1,$2,$3),($4,$5,$6)',
    [section,sid,'section',foreign,other,'other']);
  await db.query('insert into mindex_worship_elements(id,section_id,element_type,title,config) values($1,$2,$3,$4,$5)',
    [element,section,'plain_text','before',{unknown:'keep'}]);
  await db.query('insert into mindex_worship_slides(element_id,slide_type,body) values($1,$2,$3)',[element,'plain_text','saved slide']);
  const read=()=>scalar('select mindex_atomic_lab.read_service($1)',[sid]);
  const save=req=>scalar('select mindex_atomic_lab.save_existing($1)',[req]);
  const remove=req=>scalar('select mindex_atomic_lab.delete_service($1)',[req]);
  const create=req=>scalar('select mindex_atomic_lab.create_service($1)',[req]);
  const request=(revision='0')=>({protocolVersion:1,serviceId:sid,requestId:randomUUID(),expectedRevision:revision,
    metadataPatch:{title:'changed'},sectionPatches:[{id:section,patch:{title:'changed section'}}],
    elementPatches:[{id:element,patch:{title:'changed element',config:{added:'yes'}}}],
    document:{sourceText:'changed'}});
  const baseline=await read();
  const good=request(); const receipt=await save(good);
  assert.equal(receipt.committedRevision,'1');
  assert.equal(receipt.aggregate.service.source_ref.custom,'keep');
  assert.equal(receipt.aggregate.elements[0].config.unknown,'keep');
  assert.equal(receipt.aggregate.slides[0].body,'saved slide');
  assert.deepEqual(await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1',[sid]),baseline);
  const replay=await save(good);
  assert.equal(replay.replayed,true); assert.equal((await read()).revision,'1');
  await assert.rejects(save({...good,document:{sourceText:'changed payload'}}),/REQUEST_ID_REUSED/);
  await assert.rejects(save(request('0')),/REVISION_CONFLICT/);
  const next=request('1'); await save(next);
  const oldReplay=await save(good);
  assert.equal(oldReplay.committedRevision,'1'); assert.equal(oldReplay.aggregate.revision,'2');
  console.log('PASS revision CAS, same-request retry, changed-request rejection, latest-state replay');

  const state=await read();
  const checkpoint=await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1',[sid]);
  const receiptCount=await scalar('select count(*)::int from mindex_atomic_lab.receipts');
  const unchanged=async()=>{
    assert.deepEqual(await read(),state);
    assert.deepEqual(await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1',[sid]),checkpoint);
    assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.receipts'),receiptCount);
  };
  for (const stage of ['service','section','element','document','receipt']) {
    const table={service:'public.mindex_worship_services',section:'public.mindex_worship_sections',
      element:'public.mindex_worship_elements',document:'public.mindex_worship_services',receipt:'mindex_atomic_lab.receipts'}[stage];
    const condition=stage==='service' ? 'new.save_revision=old.save_revision'
      : stage==='document' ? 'new.save_revision<>old.save_revision' : 'true';
    await db.exec(`create function mindex_atomic_lab.fail_stage() returns trigger language plpgsql as $$
      begin if ${condition} then raise exception 'INJECTED_FAILURE'; end if; return new; end $$;
      create trigger test_failure before ${stage==='receipt'?'insert':'update'} on ${table}
      for each row execute function mindex_atomic_lab.fail_stage();`);
    await assert.rejects(save(request('2')),/INJECTED_FAILURE/);
    await unchanged();
    await db.exec(`drop trigger test_failure on ${table}; drop function mindex_atomic_lab.fail_stage();`);
    console.log('PASS actual SQL rollback at',stage);
  }
  const invalid=request('2'); invalid.sectionPatches[0].id=foreign;
  await assert.rejects(save(invalid),/SECTION_OWNERSHIP/); await unchanged();
  const duplicated=request('2'); duplicated.elementPatches.push(duplicated.elementPatches[0]);
  await assert.rejects(save(duplicated),/DUPLICATE_ID/); await unchanged();
  const reserved=request('2'); reserved.metadataPatch.save_revision=100;
  await assert.rejects(save(reserved),/UNKNOWN_PATCH_FIELD/); await unchanged();
  const ownership=request('2'); ownership.elementPatches[0].patch.section_id=foreign;
  await assert.rejects(save(ownership),/UNKNOWN_PATCH_FIELD/); await unchanged();
  await db.exec('set role anon');
  await assert.rejects(read(),/permission denied/);
  await assert.rejects(save(request('2')),/permission denied/);
  await assert.rejects(remove({}),/permission denied/);
  await assert.rejects(create({}),/permission denied/);
  await db.exec('reset role');
  console.log('PASS ownership, duplicate IDs, reserved fields and unexposed prototype');

  const deletion={protocolVersion:1,serviceId:sid,requestId:randomUUID(),expectedRevision:'2',confirmDelete:true};
  await assert.rejects(remove({...deletion,confirmDelete:false}),/DELETE_INTENT_REQUIRED/);
  await assert.rejects(remove({...deletion,confirmDelete:'true'}),/DELETE_INTENT_REQUIRED/);
  await assert.rejects(remove({...deletion,expectedRevision:'1'}),/REVISION_CONFLICT/);
  await assert.rejects(remove({...deletion,requestId:good.requestId}),/REQUEST_ID_REUSED/);
  await unchanged();
  const otherState=await scalar('select mindex_atomic_lab.read_service($1)',[other]);
  for (const [stage,table,event] of [
    ['section cascade','public.mindex_worship_sections','delete'],
    ['element cascade','public.mindex_worship_elements','delete'],
    ['slide cascade','public.mindex_worship_slides','delete'],
    ['tombstone','mindex_atomic_lab.tombstones','insert'],
    ['delete receipt','mindex_atomic_lab.receipts','insert'],
  ]) {
    await db.exec(`create function mindex_atomic_lab.fail_delete() returns trigger language plpgsql as $$
      begin raise exception 'INJECTED_DELETE_FAILURE'; end $$;
      create trigger test_failure before ${event} on ${table}
      for each row execute function mindex_atomic_lab.fail_delete();`);
    await assert.rejects(remove(deletion),/INJECTED_DELETE_FAILURE/);
    await unchanged();
    assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.tombstones'),0);
    await db.exec(`drop trigger test_failure on ${table}; drop function mindex_atomic_lab.fail_delete();`);
    console.log('PASS deletion rollback at',stage);
  }
  const deleted=await remove(deletion);
  assert.equal(deleted.committedRevision,'3');
  assert.equal(deleted.deleted,true); assert.equal(deleted.aggregate,null);
  assert.equal(await read(),null);
  for (const table of ['sections','elements','slides']) {
    for (const row of state[table]) {
      assert.equal(await scalar(`select count(*)::int from public.mindex_worship_${table} where id=$1`,[row.id]),0);
    }
  }
  assert.deepEqual(await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1',[sid]),state);
  assert.deepEqual(await scalar('select mindex_atomic_lab.read_service($1)',[other]),otherState);
  assert.equal((await remove(deletion)).replayed,true);
  assert.equal(await scalar('select count(*)::int from mindex_atomic_lab.receipts'),receiptCount+1);
  const preDeleteRetry=await save(good);
  assert.equal(preDeleteRetry.replayed,true); assert.equal(preDeleteRetry.deleted,true);
  assert.equal(preDeleteRetry.aggregate,null);
  await assert.rejects(remove({...deletion,expectedRevision:'3'}),/REQUEST_ID_REUSED/);
  await assert.rejects(remove({...deletion,requestId:randomUUID()}),/SERVICE_NOT_FOUND/);
  await assert.rejects(save(request('2')),/SERVICE_NOT_FOUND/);
  console.log('PASS deletion intent, CAS, cascade, recovery checkpoint, retry and cross-operation request identity');
  const newId=randomUUID(), newSection=randomUUID(), newElement=randomUUID();
  const creation={protocolVersion:1,serviceId:newId,requestId:randomUUID(),serviceTypeId:'fixture',serviceDate:'2026-09-19',
    metadataPatch:{title:'new service'},sections:[{id:newSection,patch:{title:'new section'}}],
    elements:[{id:newElement,sectionId:newSection,patch:{element_type:'body',body:'new content',config:{custom:'kept'}}}],
    document:{sourceText:'new source'}};
  const snapshot=()=>scalar(`select jsonb_build_object(
    'services',(select jsonb_agg(to_jsonb(t) order by id) from mindex_worship_services t),
    'sections',(select jsonb_agg(to_jsonb(t) order by id) from mindex_worship_sections t),
    'elements',(select jsonb_agg(to_jsonb(t) order by id) from mindex_worship_elements t),
    'slides',(select jsonb_agg(to_jsonb(t) order by id) from mindex_worship_slides t),
    'receipts',(select jsonb_agg(to_jsonb(t) order by service_id,request_id) from mindex_atomic_lab.receipts t),
    'checkpoints',(select jsonb_agg(to_jsonb(t) order by service_id) from mindex_atomic_lab.checkpoints t),
    'tombstones',(select jsonb_agg(to_jsonb(t) order by service_id) from mindex_atomic_lab.tombstones t))`);
  const beforeCreate=await snapshot();
  for (const [stage,table,event,condition] of [
    ['root','public.mindex_worship_services','insert','true'],
    ['section','public.mindex_worship_sections','insert','true'],
    ['element','public.mindex_worship_elements','insert','true'],
    ['document','public.mindex_worship_services','update','new.save_revision<>old.save_revision'],
    ['receipt','mindex_atomic_lab.receipts','insert','true'],
  ]) {
    await db.exec(`create function mindex_atomic_lab.fail_create() returns trigger language plpgsql as $$
      begin if ${condition} then raise exception 'INJECTED_CREATE_FAILURE'; end if; return new; end $$;
      create trigger test_failure before ${event} on ${table}
      for each row execute function mindex_atomic_lab.fail_create();`);
    await assert.rejects(create(creation),/INJECTED_CREATE_FAILURE/);
    assert.deepEqual(await snapshot(),beforeCreate);
    await db.exec(`drop trigger test_failure on ${table}; drop function mindex_atomic_lab.fail_create();`);
    console.log('PASS creation rollback at',stage);
  }
  for (const [invalidCreate,error] of [
    [{...creation,elements:[{...creation.elements[0],sectionId:foreign}]},/SECTION_OWNERSHIP/],
    [{...creation,sections:[...creation.sections,...creation.sections]},/duplicate key/],
    [{...creation,sections:[{...creation.sections[0],id:foreign}]},/duplicate key/],
    [{...creation,metadataPatch:{save_revision:8}},/UNKNOWN_PATCH_FIELD/],
    [{...creation,serviceId:sid},/SERVICE_DELETED/],
    [{...creation,serviceTypeId:'nonexistent'},/foreign key/],
    [{...creation,serviceDate:'2026-02-30'},/out of range/],
  ]) {
    await assert.rejects(create(invalidCreate),error);
    assert.deepEqual(await snapshot(),beforeCreate);
  }
  const created=await create(creation);
  assert.equal(created.committedRevision,'1');
  assert.equal(created.aggregate.elements[0].body,'new content');
  assert.equal(created.aggregate.elements[0].config.custom,'kept');
  assert.equal(created.aggregate.service.source_ref.mindexServiceDocument.sourceText,'new source');
  assert.equal(created.aggregate.sections[0].service_id,newId);
  assert.equal((await create(creation)).replayed,true);
  await assert.rejects(create({...creation,document:{sourceText:'different'}}),/REQUEST_ID_REUSED/);
  await assert.rejects(create({...creation,requestId:randomUUID()}),/SERVICE_ALREADY_EXISTS/);
  await assert.rejects(create({...creation,serviceId:randomUUID(),requestId:randomUUID()}),/duplicate key/);
  await remove({protocolVersion:1,serviceId:newId,requestId:randomUUID(),expectedRevision:'1',confirmDelete:true});
  const createdReplay=await create(creation);
  assert.equal(createdReplay.deleted,true); assert.equal(createdReplay.aggregate,null);
  console.log('PASS creation ownership, identity constraints, retry, document storage and no resurrection');
  const structId=randomUUID(), sourceSection=randomUUID(), targetSection=randomUUID();
  const moving=randomUUID(), removing=randomUUID();
  await create({...creation,serviceId:structId,requestId:randomUUID(),metadataPatch:{title:'structure fixture'},
    sections:[{id:sourceSection,patch:{title:'source'}},{id:targetSection,patch:{title:'target'}}],
    elements:[moving,removing].map(id=>({id,sectionId:sourceSection,patch:{body:id}}))});
  for (const id of [moving,removing]) {
    await db.query('insert into mindex_worship_slides(element_id,slide_type,body) values($1,$2,$3)',[id,'plain_text',id]);
  }
  const structure={protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'1',
    elementMoves:[{id:moving,sectionId:targetSection}],deleteElementIds:[removing],deleteSectionIds:[sourceSection],
    elementPatches:[{id:moving,patch:{sort_order:3}}],document:{sourceText:'moved source'}};
  const structureBaseline=await snapshot();
  for (const [invalidStructure,error] of [
    [{...structure,deleteElementIds:[]},/CHILD_DELETE_INTENT_REQUIRED/],
    [{...structure,elementMoves:[]},/CHILD_DELETE_INTENT_REQUIRED/],
    [{...structure,elementMoves:[{id:moving,sectionId:foreign}]},/MOVE_OWNERSHIP/],
    [{...structure,elementMoves:[{id:moving,sectionId:sourceSection}]},/CONFLICTING_STRUCTURE/],
    [{...structure,deleteElementIds:[removing,moving]},/CONFLICTING_STRUCTURE/],
    [{...structure,deleteSectionIds:[foreign]},/DELETE_OWNERSHIP/],
    [{...structure,deleteElementIds:[removing,removing]},/DUPLICATE_ID/],
    [{...structure,elementMoves:[...structure.elementMoves,...structure.elementMoves]},/DUPLICATE_ID/],
    [{...structure,deleteElementIds:null},/INVALID_SHAPE/],
    [{...structure,elementPatches:[{id:removing,patch:{title:'conflict'}}]},/CONFLICTING_STRUCTURE/],
    [{...structure,sectionPatches:[{id:sourceSection,patch:{title:'conflict'}}]},/CONFLICTING_STRUCTURE/],
  ]) {
    await assert.rejects(save(invalidStructure),error);
    assert.deepEqual(await snapshot(),structureBaseline);
  }
  for (const [stage,table,event,condition] of [
    ['slide deletion','public.mindex_worship_slides','delete','true'],
    ['section deletion','public.mindex_worship_sections','delete','true'],
    ['document','public.mindex_worship_services','update','new.save_revision<>old.save_revision'],
    ['receipt','mindex_atomic_lab.receipts','insert','true'],
  ]) {
    await db.exec(`create function mindex_atomic_lab.fail_structure() returns trigger language plpgsql as $$
      begin if ${condition} then raise exception 'INJECTED_STRUCTURE_FAILURE'; end if; return new; end $$;
      create trigger test_failure before ${event} on ${table}
      for each row execute function mindex_atomic_lab.fail_structure();`);
    await assert.rejects(save(structure),/INJECTED_STRUCTURE_FAILURE/);
    assert.deepEqual(await snapshot(),structureBaseline);
    await db.exec(`drop trigger test_failure on ${table}; drop function mindex_atomic_lab.fail_structure();`);
    console.log('PASS structure rollback at',stage);
  }
  const structured=await save(structure);
  assert.equal(structured.committedRevision,'2');
  assert.deepEqual(structured.aggregate.sections.map(s=>s.id),[targetSection]);
  assert.deepEqual(structured.aggregate.elements.map(e=>e.id),[moving]);
  assert.equal(structured.aggregate.elements[0].section_id,targetSection);
  assert.equal(structured.aggregate.elements[0].sort_order,3);
  assert.equal(structured.aggregate.slides.length,1);
  assert.equal(structured.aggregate.slides[0].element_id,moving);
  assert.equal(structured.aggregate.slides[0].body,moving);
  assert.equal((await save(structure)).replayed,true);
  const omitted=await save({protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'2',document:{sourceText:'only text'}});
  assert.deepEqual(omitted.aggregate.elements,structured.aggregate.elements);
  assert.deepEqual(omitted.aggregate.slides,structured.aggregate.slides);
  console.log('PASS explicit structural intent, ownership, move preserving slide IDs, omission preservation and retry');
  const insertedSection=randomUUID(), insertedElement=randomUUID();
  const insertion={protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'3',
    newSections:[{id:insertedSection,patch:{title:'new section'}}],
    newElements:[{id:insertedElement,sectionId:insertedSection,patch:{body:'inserted'}}],
    document:{sourceText:'inserted'}};
  const beforeInsertion=await snapshot();
  await assert.rejects(save({...insertion,newElements:[{...insertion.newElements[0],sectionId:foreign}]}),/SECTION_OWNERSHIP/);
  assert.deepEqual(await snapshot(),beforeInsertion);
  await assert.rejects(save({...insertion,newSections:[{id:targetSection,patch:{title:'overwrite'}}]}),/duplicate key/);
  assert.deepEqual(await snapshot(),beforeInsertion);
  await assert.rejects(save({...insertion,metadataPatch:{save_revision:100}}),/UNKNOWN_PATCH_FIELD/);
  assert.deepEqual(await snapshot(),beforeInsertion);
  const inserted=await save(insertion);
  assert.equal(inserted.aggregate.elements.length,2);
  assert.equal(inserted.aggregate.slides[0].element_id,moving);
  const checkpointBeforeInsertion=await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1',[structId]);
  assert.equal(checkpointBeforeInsertion.elements.length,1);
  assert.equal(checkpointBeforeInsertion.sections.length,1);
  assert.equal((await save(insertion)).replayed,true);
  console.log('PASS structural insertion, stable existing rows, pre-insert checkpoint and late validation rollback');
  const songA=randomUUID(),songB=randomUUID(),versionA=randomUUID(),versionCanonical=randomUUID();
  await db.query('insert into mindex_songs values($1),($2)',[songA,songB]);
  await db.query('insert into mindex_song_versions values($1,$2,$3),($4,null,$2)',[versionA,songA,songB,versionCanonical]);
  const songRequest={protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'4',document:{sourceText:'linked'},
    elementPatches:[{id:insertedElement,patch:{song_id:songA,song_version_id:versionA}}]};
  const beforeBadPair=await snapshot();
  await assert.rejects(save({...songRequest,elementPatches:[{id:insertedElement,patch:{song_id:songB,song_version_id:versionA}}]}),/SONG_VERSION_MISMATCH/);
  assert.deepEqual(await snapshot(),beforeBadPair);
  const linked=await save(songRequest);
  assert.equal(linked.aggregate.elements.find(e=>e.id===insertedElement).song_id,songA);
  await save({...songRequest,requestId:randomUUID(),expectedRevision:'5',elementPatches:[{id:insertedElement,patch:{song_version_id:versionCanonical}}]});
  await assert.rejects(save({...songRequest,requestId:randomUUID(),expectedRevision:'6',elementPatches:[{id:insertedElement,patch:{song_id:null}}]}),/SONG_VERSION_MISMATCH/);
  await save({...songRequest,requestId:randomUUID(),expectedRevision:'6',elementPatches:[{id:insertedElement,patch:{song_id:null,song_version_id:null}}]});
  console.log('PASS source-song ownership, canonical fallback only without source, pair rejection and explicit unlink');
  const journalData=new Map();
  const journal={getItem:key=>journalData.get(key)||null,setItem:(key,value)=>journalData.set(key,value),removeItem:key=>journalData.delete(key)};
  let loseResponse=true;
  const transportOptions={journal,methods:{save:'save_existing'},makeId:randomUUID,rpc:async(method,{req})=>{
    assert.equal(method,'save_existing');
    const result=await save(req);
    if(loseResponse) { loseResponse=false; throw new Error('SIMULATED_RESPONSE_LOSS_AFTER_COMMIT'); }
    return {data:result};
  }};
  const transport=createWorshipStore(transportOptions);
  transport.acceptRead(structId,await scalar('select mindex_atomic_lab.read_service($1)',[structId]));
  const transportDraft={serviceId:structId,expectedRevision:'7',document:{sourceText:'captured text'}};
  await assert.rejects(transport.save('save',transportDraft),/SIMULATED_RESPONSE_LOSS_AFTER_COMMIT/);
  transportDraft.document.sourceText='new local edit';
  assert.equal((await scalar('select mindex_atomic_lab.read_service($1)',[structId])).revision,'8');
  const reloadedTransport=createWorshipStore(transportOptions);
  const transportReceipt=await reloadedTransport.retry(structId);
  assert.equal(transportReceipt.replayed,true);
  assert.equal(transportReceipt.aggregate.revision,'8');
  assert.equal(transportReceipt.aggregate.service.source_ref.mindexServiceDocument.sourceText,'captured text');
  assert.equal(transportDraft.document.sourceText,'new local edit');
  assert.equal(journalData.size,0);
  console.log('PASS real DB commit + simulated response loss + recreated client exact retry; newer draft preserved');
  await save({protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'8',document:{sourceText:'with reference'},
    elementPatches:[{id:insertedElement,patch:{source_ref:{scriptureReferences:['reference'],customException:'keep'}}}]});
  const removal={protocolVersion:1,serviceId:structId,requestId:randomUUID(),expectedRevision:'9',document:{sourceText:'cleared'},
    elementPatches:[{id:insertedElement,patch:{},removeKeys:{source_ref:['scriptureReferences']}}]};
  const beforeRemoval=await snapshot();
  for(const [change,error] of [
    [{patch:{source_ref:{scriptureReferences:[]}},removeKeys:{source_ref:['scriptureReferences']}},/CONFLICTING_REMOVAL/],
    [{patch:{},removeKeys:{title:['anything']}},/INVALID_REMOVAL/],
    [{patch:{},removeKeys:{source_ref:[null]}},/INVALID_REMOVAL/],
    [{patch:{},removeKeys:{source_ref:null}},/INVALID_REMOVAL/],
  ]) {
    await assert.rejects(save({...removal,elementPatches:[{id:insertedElement,...change}]}),error);
    assert.deepEqual(await snapshot(),beforeRemoval);
  }
  const removedKey=await save(removal);
  const ref=removedKey.aggregate.elements.find(e=>e.id===insertedElement).source_ref;
  assert.equal(Object.hasOwn(ref,'scriptureReferences'),false);
  assert.equal(ref.customException,'keep');
  assert.equal((await save(removal)).replayed,true);
  console.log('PASS explicit JSON-key removal preserves unrelated exception metadata; ambiguous intent rejected');

  const templateId=randomUUID(), scheduledId=randomUUID(), scheduledSection=randomUUID(), scheduledElement=randomUUID();
  await db.query('insert into mindex_worship_templates values($1)',[templateId]);
  const provenance={template_id:templateId,template_modified:true,source_kind:'import',source_ref:{externalKey:'retain'}};
  const scheduled={protocolVersion:1,serviceId:scheduledId,requestId:randomUUID(),serviceTypeId:'fixture',serviceDate:'2026-10-01',
    metadataPatch:{...provenance,title:'multi-day',service_date_end:'2026-10-03'},
    sections:[{id:scheduledSection,patch:{...provenance,title:'schedule section'}}],
    elements:[{id:scheduledElement,sectionId:scheduledSection,patch:{...provenance,element_type:'body',body:'schedule body'}}],
    document:{sourceText:'schedule document'}};
  const scheduleReceipt=await create(scheduled);
  for(const row of [scheduleReceipt.aggregate.service,...scheduleReceipt.aggregate.sections,...scheduleReceipt.aggregate.elements]) {
    assert.equal(row.template_id,templateId);
    assert.equal(row.template_modified,true);
    assert.equal(row.source_kind,'import');
    assert.equal(row.source_ref.externalKey,'retain');
  }
  assert.equal(scheduleReceipt.aggregate.service.service_date_end,'2026-10-03');
  assert.deepEqual(scheduleReceipt.aggregate.service.source_ref.mindexServiceDocument,scheduled.document);
  assert.equal((await create(scheduled)).replayed,true);
  await assert.rejects(create({...scheduled,serviceId:randomUUID(),requestId:randomUUID(),
    metadataPatch:{...scheduled.metadataPatch,service_date:'2026-10-06'}}),/DUPLICATE_CREATE_IDENTITY/);
  // Same start/title with a different end date is a distinct existing DB identity.
  await create({...scheduled,serviceId:randomUUID(),requestId:randomUUID(),sections:[],elements:[],
    metadataPatch:{...scheduled.metadataPatch,service_date_end:'2026-10-04'}});
  const scheduleBefore=await snapshot();
  const scheduleEdit={protocolVersion:1,serviceId:scheduledId,requestId:randomUUID(),expectedRevision:'1',document:{sourceText:'edited'}};
  for(const [patch,error] of [
    [{service_date_end:'2026-09-30'},/INVALID_DATE_RANGE/],
    [{service_date_end:'infinity'},/INVALID_END_DATE/],
    [{template_id:randomUUID()},/foreign key/],
    [{source_kind:'unsupported'},/check constraint/],
    [{source_ref:{mindexServiceDocument:{sourceText:'bypass'}}},/PROTECTED_DOCUMENT_FIELD/],
    [{source_ref:{mindexServiceDocumentHistory:[]}},/PROTECTED_DOCUMENT_FIELD/],
  ]) {
    await assert.rejects(save({...scheduleEdit,metadataPatch:patch}),error);
    assert.deepEqual(await snapshot(),scheduleBefore);
    await assert.rejects(create({...scheduled,serviceId:randomUUID(),requestId:randomUUID(),sections:[],elements:[],
      metadataPatch:{...scheduled.metadataPatch,title:'invalid schedule',...patch}}),error);
    assert.deepEqual(await snapshot(),scheduleBefore);
  }
  const scheduleUpdate=await save({...scheduleEdit,metadataPatch:{service_date_end:null,source_ref:{extra:'added'}}});
  assert.equal(scheduleUpdate.aggregate.service.service_date_end,null);
  assert.equal(scheduleUpdate.aggregate.service.source_ref.externalKey,'retain');
  assert.equal(scheduleUpdate.aggregate.service.source_ref.extra,'added');
  assert.equal(scheduleUpdate.aggregate.service.source_ref.mindexServiceDocument.sourceText,'edited');
  console.log('PASS scheduling/provenance create, edit, replay, date identity, protected document and rollback');

  await db.exec("insert into mindex_worship_service_types values('rescheduled')");
  const reschedule={protocolVersion:1,serviceId:scheduledId,requestId:randomUUID(),expectedRevision:'2',
    metadataPatch:{service_date:'2026-10-05',service_type_id:'rescheduled'},
    document:{sourceText:'rescheduled',serviceDate:'2026-10-05'}};
  const beforeReschedule=await scalar('select mindex_atomic_lab.read_service($1)',[scheduledId]);
  for(const [patch,error] of [[{service_date:null},/INVALID_SERVICE_DATE/],
    [{service_date:'infinity'},/INVALID_SERVICE_DATE/],[{service_type_id:'missing'},/foreign key/]]) {
    await assert.rejects(save({...reschedule,metadataPatch:{...reschedule.metadataPatch,...patch}}),error);
    assert.deepEqual(await scalar('select mindex_atomic_lab.read_service($1)',[scheduledId]),beforeReschedule);
  }
  await assert.rejects(save({...reschedule,document:{sourceText:'stale',serviceDate:'2026-10-01'}}),/DOCUMENT_DATE_MISMATCH/);
  assert.deepEqual(await scalar('select mindex_atomic_lab.read_service($1)',[scheduledId]),beforeReschedule);
  const rescheduled=await save(reschedule);
  assert.equal(rescheduled.aggregate.service.service_date,'2026-10-05');
  assert.equal(rescheduled.aggregate.service.service_type_id,'rescheduled');
  assert.deepEqual(rescheduled.aggregate.elements,beforeReschedule.elements);
  assert.equal((await save(reschedule)).replayed,true);
  console.log('PASS date/type edits are atomic with document date; invalid date/type and stale document roll back');

  const docId=randomUUID(), docSection=randomUUID(), docOtherSection=randomUUID(), docElement=randomUUID();
  const mixedDocument={sourceText:'manual source',serviceId:docId,serviceDate:'2026-10-02',
    sourceRecords:[{elementId:docElement,sectionId:docSection,slotKey:'praise.song.1',label:'custom label',value:'manual title'}],
    slides:[{id:'custom-title',elementId:docElement,sectionId:docSection,type:'title',text:'manual title'},
      {id:'custom-image',elementId:docElement,sectionId:docSection,type:'image',asset:{url:'https://example.invalid/fixture.png'}},
      {id:'custom-blank',elementId:docElement,sectionId:docSection,type:'blank'}],
    exceptions:[{type:'asset',target:{elementId:docElement},reason:'Explicit fixture image insertion'}],
    customExtension:{untouched:true}};
  const docCreate={...scheduled,serviceId:docId,requestId:randomUUID(),serviceDate:'2026-10-02',
    metadataPatch:{title:'document checks'},
    sections:[{id:docSection,patch:{title:'one'}},{id:docOtherSection,patch:{title:'two'}}],
    elements:[{id:docElement,sectionId:docSection,patch:{element_type:'praise',source_ref:{slotKey:'praise.song.1'}}}],
    document:mixedDocument};
  const badCreate={...docCreate,document:{...mixedDocument,serviceId:other}};
  const beforeBadCreate=await snapshot();
  await assert.rejects(create(badCreate),/DOCUMENT_SERVICE_MISMATCH/);
  assert.deepEqual(await snapshot(),beforeBadCreate);
  const docReceipt=await create(docCreate);
  assert.deepEqual(docReceipt.aggregate.service.source_ref.mindexServiceDocument,mixedDocument);
  const docBefore=await snapshot();
  const docEdit={protocolVersion:1,serviceId:docId,requestId:randomUUID(),expectedRevision:'1',
    metadataPatch:{title:'should roll back'},elementPatches:[{id:docElement,patch:{body:'should roll back'}}],document:mixedDocument};
  for(const [document,error] of [
    [{sourceText:null},/INVALID_DOCUMENT/],
    [{...mixedDocument,serviceId:other},/DOCUMENT_SERVICE_MISMATCH/],
    [{...mixedDocument,serviceDate:'2026-10-03'},/DOCUMENT_DATE_MISMATCH/],
    [{...mixedDocument,slides:null},/INVALID_DOCUMENT_LIST/],
    [{...mixedDocument,sourceRecords:[null]},/INVALID_DOCUMENT_ENTRY/],
    [{...mixedDocument,sourceRecords:[{elementId:docElement,sectionId:foreign}]},/DOCUMENT_SECTION_OWNERSHIP/],
    [{...mixedDocument,sourceRecords:[{elementId:scheduledElement}]},/DOCUMENT_ELEMENT_OWNERSHIP/],
    [{...mixedDocument,sourceRecords:[{elementId:docElement,sectionId:docOtherSection}]},/DOCUMENT_PARENT_MISMATCH/],
    [{...mixedDocument,sourceRecords:[{elementId:docElement,slotKey:'prayer.meeting.song.1'}]},/DOCUMENT_SLOT_MISMATCH/],
    [{...mixedDocument,sourceRecords:[{elementId:docElement,linkedSource:{songId:randomUUID()}}]},/DOCUMENT_SONG_MISMATCH/],
    [{...mixedDocument,sourceRecords:[{elementId:docElement,linkedSource:{songVersionId:randomUUID()}}]},/DOCUMENT_VERSION_MISMATCH/],
    [{...mixedDocument,sourceRecords:[...mixedDocument.sourceRecords,...mixedDocument.sourceRecords]},/DUPLICATE_DOCUMENT_RECORD/],
    [{...mixedDocument,slides:[{id:'dup'},{id:'dup'}]},/DUPLICATE_DOCUMENT_SLIDE/],
    [{...mixedDocument,slides:[{elementId:docElement}]},/INVALID_DOCUMENT_SLIDE_ID/],
    [{...mixedDocument,exceptions:[{target:{elementId:scheduledElement}}]},/DOCUMENT_ELEMENT_OWNERSHIP/],
  ]) {
    await assert.rejects(save({...docEdit,document}),error);
    assert.deepEqual(await snapshot(),docBefore);
  }
  // Validation uses the post-mutation tree, not the previous ownership snapshot.
  await assert.rejects(save({...docEdit,elementPatches:[],deleteElementIds:[docElement]}),/DOCUMENT_ELEMENT_OWNERSHIP/);
  assert.deepEqual(await snapshot(),docBefore);
  await assert.rejects(save({...docEdit,elementMoves:[{id:docElement,sectionId:docOtherSection}]}),/DOCUMENT_PARENT_MISMATCH/);
  assert.deepEqual(await snapshot(),docBefore);
  const movedDocument=structuredClone(mixedDocument);
  for(const entry of [...movedDocument.sourceRecords,...movedDocument.slides])entry.sectionId=docOtherSection;
  const docSaved=await save({...docEdit,elementMoves:[{id:docElement,sectionId:docOtherSection}],document:movedDocument});
  assert.deepEqual(docSaved.aggregate.service.source_ref.mindexServiceDocument,movedDocument);
  console.log('PASS final-tree document ownership, parent/slot/song consistency, mixed slides, create/update rollback');
  // Generated by the offline browser test, never a production DB export.
  if (process.env.WORSHIP_EDITOR_FIXTURES) {
    const fixtures=JSON.parse(await fs.readFile(process.env.WORSHIP_EDITOR_FIXTURES,'utf8'));
    for (const fixture of fixtures) {
      const {service,rows,document,before,engine}=fixture;
      const sections=rows.sections.map(({id,service_id,created_at,updated_at,...patch})=>({id,patch}));
      const elements=rows.elements.map(({id,section_id,created_at,updated_at,...patch})=>({id,sectionId:section_id,patch}));
      const req={protocolVersion:1,serviceId:service.id,requestId:randomUUID(),
        serviceTypeId:'fixture',serviceDate:service.date,metadataPatch:{title:engine},sections,elements,document};
      if (fixture.prepared) Object.assign(req,fixture.prepared.payload,{metadataPatch:{title:engine}});
      await assert.rejects(create({...req,document:before}),/DOCUMENT_(ELEMENT|SECTION)_OWNERSHIP/);
      assert.equal(await scalar('select count(*)::int from mindex_worship_services where id=$1',[service.id]),0);
      const created=await create(req);
      assert.deepEqual(created.aggregate.service.source_ref.mindexServiceDocument,document);
      assert.equal(created.aggregate.elements.length,rows.elements.length);
      for (const original of rows.elements) {
        const stored=created.aggregate.elements.find(x=>x.id===original.id);
        for (const key of ['title','body','asset','config','source_ref','input_mode','content_state'])
          if (key in original) assert.deepEqual(stored[key],original[key],`${engine}: ${key}`);
      }
      const updated=await save({protocolVersion:1,serviceId:service.id,requestId:randomUUID(),
        expectedRevision:'1',document,metadataPatch:{notes:'roundtrip'}});
      assert.deepEqual(updated.aggregate.service.source_ref.mindexServiceDocument,document);
      const ready=document.slides.find(x=>x.type==='ready' && !x.elementId);
      assert.ok(ready,'fixture must exercise synthetic ready group');
      for (const patch of [
        {sectionId:other+':ready',id:other+':ready'},
        {id:service.id+':unrecognized'},
        {type:'image'},
        {elementId:rows.elements[0].id},
      ]) {
        const invalidDoc=structuredClone(document);
        Object.assign(invalidDoc.slides.find(x=>x.id===ready.id),patch);
        await assert.rejects(save({protocolVersion:1,serviceId:service.id,requestId:randomUUID(),
          expectedRevision:'2',document:invalidDoc,metadataPatch:{notes:'must rollback'}}),/DOCUMENT_SECTION_OWNERSHIP/);
        assert.deepEqual(await scalar('select mindex_atomic_lab.read_service($1)',[service.id]),updated.aggregate);
      }
      console.log('PASS real editor document create/save, draft ID rejection and rollback:',engine);
      if (fixture.update) {
        const edited=await save({...fixture.update.payload,protocolVersion:1,requestId:randomUUID(),expectedRevision:'2'});
        assert.deepEqual(edited.aggregate.service.source_ref.mindexServiceDocument,fixture.update.payload.document);
        assert.ok(edited.aggregate.elements.some(row=>row.title==='Edited praise title'));
        assert.ok(edited.aggregate.elements.some(row=>row.config.integrationExtension?.keep));
        assert.deepEqual(edited.aggregate.elements.map(row=>row.id).sort(),rows.elements.map(row=>row.id).sort());
        console.log('PASS prepared editor payload: existing IDs, edited title and extension preservation:',engine);
        const mixed=await save({...fixture.mixed.payload,protocolVersion:1,requestId:randomUUID(),expectedRevision:'3'});
        assert.equal(mixed.aggregate.elements.length,rows.elements.length+1);
        assert.deepEqual(mixed.aggregate.service.source_ref.mindexServiceDocument,fixture.mixed.payload.document);
        const priorIds=new Set(mixed.aggregate.elements.map(row=>row.id));
        assert.ok(rows.elements.every(row=>priorIds.has(row.id)));
        console.log('PASS prepared mixed existing/new element save:',engine);
        for (const action of fixture.actions || []) {
          const request={...action.payload,protocolVersion:1,requestId:randomUUID()};
          const committed=await save(request);
          assert.deepEqual(committed.aggregate.service.source_ref.mindexServiceDocument,action.payload.document);
          assert.deepEqual(committed.aggregate.elements.map(row=>row.id).sort(),action.rows.elements.map(row=>row.id).sort());
          for (const row of action.rows.elements) {
            const actual=committed.aggregate.elements.find(saved=>saved.id===row.id);
            for (const key of ['title','body','asset','config','source_ref']) assert.deepEqual(actual[key],row[key]);
          }
          const replay=await save(request);
          assert.equal(replay.replayed,true);
          assert.deepEqual(replay.aggregate,committed.aggregate);
          await assert.rejects(save({...request,requestId:randomUUID()}),/REVISION_CONFLICT/);
        }
        console.log('PASS prepared deletion, suppression, explicit key removal and replay:',engine);
      }
    }
  }

  if (process.env.WORSHIP_RUNTIME_FIXTURES) {
    const fixtures = JSON.parse(await fs.readFile(process.env.WORSHIP_RUNTIME_FIXTURES, 'utf8'));
    for (const [engine, fixture] of fixtures.entries()) {
      const initial = {...fixture.initial, protocolVersion:1, requestId:randomUUID()};
      await db.query('insert into mindex_worship_service_types(id) values($1) on conflict do nothing', [initial.serviceTypeId]);
      // Separate fixture dates/titles avoid business identity collisions.
      initial.metadataPatch.title += ` runtime-${engine}`;
      await create(initial);
      for (const request of fixture.writes) {
        if (request.metadataPatch.title) request.metadataPatch.title += ` runtime-${engine}`;
        const committed = await save(request);
        assert.deepEqual(committed.aggregate.service.source_ref.mindexServiceDocument, request.document);
        const replay = await save(request);
        assert.equal(replay.replayed, true);
        assert.deepEqual(replay.aggregate, committed.aggregate);
        await assert.rejects(save({...request, requestId:randomUUID()}), /REVISION_CONFLICT/);
      }
      console.log('PASS actual app RPC payloads: element/full save, document references, retry and stale-write rejection:', engine);
    }
  }

  if (process.env.WORSHIP_LIFECYCLE_FIXTURES) {
    const fixtures = JSON.parse(await fs.readFile(process.env.WORSHIP_LIFECYCLE_FIXTURES, 'utf8'));
    for (const [engine, fixture] of fixtures.entries()) {
      for (const {name, req} of fixture.requests) {
        if (name === 'create_worship_service_v1') {
          await db.query('insert into mindex_worship_service_types(id) values($1) on conflict do nothing', [req.serviceTypeId]);
          req.metadataPatch.title = `${req.metadataPatch.title || ''} lifecycle-${engine}`;
          const receipt = await create(req);
          assert.equal(receipt.aggregate.elements.length, req.elements.length);
          assert.deepEqual(receipt.aggregate.service.source_ref.mindexServiceDocument, req.document);
        } else if (name === 'save_worship_service_v1') {
          const receipt = await save(req);
          assert.equal(receipt.aggregate.service.praise_leader, req.metadataPatch.praise_leader);
          assert.deepEqual(receipt.aggregate.service.source_ref.mindexServiceDocument, req.document);
        } else {
          assert.equal(name, 'delete_worship_service_v1');
          const receipt = await remove(req);
          assert.equal(receipt.deleted, true);
          assert.equal(receipt.aggregate, null);
          const checkpoint = await scalar('select aggregate from mindex_atomic_lab.checkpoints where service_id=$1', [req.serviceId]);
          assert.equal(checkpoint.service.id, req.serviceId);
        }
      }
      console.log('PASS actual lifecycle RPC payloads: assigned creation, exact retries, deletion checkpoint and automatic cleanup:', engine);
    }
  }

  if (db.connect) {
    const first=await db.connect(), second=await db.connect();
    const concurrentId=randomUUID();
    await create({...creation,serviceId:concurrentId,requestId:randomUUID(),metadataPatch:{title:'concurrency'},sections:[],elements:[]});
    const edit={protocolVersion:1,serviceId:concurrentId,requestId:randomUUID(),expectedRevision:'1',document:{sourceText:'first'}};
    await first.query('begin');
    await first.query('select mindex_atomic_lab.save_existing($1)',[edit]);
    // The second backend waits on the first transaction's service lock.
    const pending=second.query('select mindex_atomic_lab.save_existing($1)',[{...edit,requestId:randomUUID(),document:{sourceText:'second'}}])
      .then(value=>({value}),error=>({error}));
    const pid=(await first.query('select pid from pg_stat_activity where pid<>pg_backend_pid() and query like $1',
      ['select mindex_atomic_lab.save_existing%'])).rows;
    assert.ok(pid.length>0);
    let waiting=false;
    for(let i=0;i<100;i++) {
      waiting=await scalar("select exists(select from pg_stat_activity where wait_event_type='Lock' and query like 'select mindex_atomic_lab.save_existing%')");
      if(waiting) break;
      await new Promise(resolve=>setTimeout(resolve,10));
    }
    assert.equal(waiting,true,'second connection must actually contend for the lock');
    await first.query('commit');
    assert.match((await pending).error?.message || '',/REVISION_CONFLICT/);
    assert.equal((await scalar('select mindex_atomic_lab.read_service($1)',[concurrentId])).revision,'2');
    console.log('PASS two PostgreSQL backends: exactly one same-revision writer commits');

    const replayEdit={...edit,requestId:randomUUID(),expectedRevision:'2'};
    await first.query('begin');
    await first.query('select mindex_atomic_lab.save_existing($1)',[replayEdit]);
    const replayPending=second.query('select mindex_atomic_lab.save_existing($1)',[replayEdit]);
    await first.query('commit');
    assert.equal((await replayPending).rows[0].save_existing.replayed,true);
    assert.equal((await scalar('select mindex_atomic_lab.read_service($1)',[concurrentId])).revision,'3');
    console.log('PASS concurrent identical retry increments revision once');

    await first.query('begin');
    await first.query('select pg_advisory_xact_lock(hashtextextended($1,0))',[concurrentId]);
    await second.query("set lock_timeout='100ms'");
    await assert.rejects(second.query('select mindex_atomic_lab.save_existing($1)',[{...edit,requestId:randomUUID(),expectedRevision:'3'}]),/lock timeout/);
    await first.query('rollback');
    await second.query('reset lock_timeout');
    assert.equal((await scalar('select mindex_atomic_lab.read_service($1)',[concurrentId])).revision,'3');
    console.log('PASS lock timeout leaves the aggregate unchanged');
  } else console.log('NOT COVERED in PGlite mode: multi-connection locks');
  console.log('NOT COVERED: real network loss, production RLS/cutover, canonical external mutation invalidation, document semantics');
} finally { await db.close(); }
