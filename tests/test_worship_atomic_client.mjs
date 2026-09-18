import assert from 'node:assert/strict';
import {createWorshipAtomicClient, prepareWorshipRowsCommit, prepareWorshipRowsCreate} from '../mindex.worship-atomic-client.mjs';

const baseline = {revision:'1', service:{id:'service', service_type_id:'fixture', service_date:'2026-10-12'},
  sections:[{id:'section', service_id:'service', title:'Section'}],
  elements:[{id:'element', section_id:'section', title:'Original',config:{keep:true,clear:true}},
    {id:'sibling', section_id:'section', title:'Sibling'}], slides:[]};
const input = {serviceId:'service',rows:{sections:[],elements:[{...baseline.elements[0],title:'Changed',config:{keep:true}}]},
  document:{sourceText:'Changed'}};
const prepared=prepareWorshipRowsCommit({...input,baseline});
assert.deepEqual(prepared.deleteElementIds,[]);
assert.equal(prepared.elementPatches.length,1);
assert.deepEqual(prepared.elementPatches[0].removeKeys,{config:['clear']});
assert.deepEqual(baseline.elements[0].config,{keep:true,clear:true});
assert.throws(()=>prepareWorshipRowsCommit({...input,baseline,deleteElementIds:['element']}),/INVALID_STRUCTURE/);
assert.equal(prepareWorshipRowsCommit({...input,baseline,metadata:{service_date:'2026-10-13'}}).metadataPatch.service_date,'2026-10-13');
assert.throws(()=>prepareWorshipRowsCommit({...input,baseline,rows:{sections:[],elements:[{id:'x',section_id:'foreign'}]}}),/OWNERSHIP/);
console.log('PASS partial row scope, explicit removals, ownership, date patch and immutable input');

const memory=new Map();
const journal={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
let mode='network',calls=[],db=structuredClone(baseline);
const client=createWorshipAtomicClient({journal,makeId:()=> 'request',rpc:async(name,args)=>{
  if(name==='get_worship_service_v1')return {data:structuredClone(db)};
  calls.push(structuredClone(args.req));
  if(mode==='network')throw Error('Network lost');
  if(mode==='conflict')return {error:{code:'P0001',message:'REVISION_CONFLICT'}};
  return {data:{replayed:true,committedRevision:'2',aggregate:{...db,revision:'2'}}};
}});
await client.read('service');
await assert.rejects(client.commit(input),/Network lost/);
const pending=client.pending('service');assert.ok(pending);
mode='ok';
await assert.rejects(client.commit({...input,document:{sourceText:'Newer draft'}}),/RETRY_COMMITTED/);
assert.deepEqual(calls[1],calls[0]);assert.equal(client.pending('service'),null);
await assert.rejects(client.commit(input),/RELOAD_REQUIRED/);
assert.equal(calls.length,2);
db={...db,revision:'2'};await client.read('service');
mode='conflict';await assert.rejects(client.commit(input),e=>e.message==='REVISION_CONFLICT');
assert.equal(client.pending('service'),null);
await assert.rejects(client.commit(input),/RELOAD_REQUIRED/);
console.log('PASS uncertain retry uses original request; newer draft not acknowledged; known rollback clears request');

await client.read('service');mode='network';await assert.rejects(client.commit(input),/Network lost/);
mode='conflict';await assert.rejects(client.commit(input),e=>e.message==='REVISION_CONFLICT');
assert.equal(client.pending('service'),null);
db={...db,revision:'10'};await client.read('service',{adopt:false});
assert.equal(client.baseline('service').revision,'2');
console.log('PASS conflict after uncertain retry and non-adopting background reads');

const creation = {service:{...baseline.service,created_at:'client time',source_ref:{custom:true}},
  rows:{sections:baseline.sections,elements:baseline.elements},document:{sourceText:'New',updatedAt:'one'}};
const createPayload=prepareWorshipRowsCreate(creation);
assert.equal(createPayload.metadataPatch.created_at,undefined);
assert.equal(createPayload.metadataPatch.service_type_id,undefined);
assert.equal(createPayload.elements.length,2);
let lost=true, replayCalls=[];
memory.clear();
const lifecycle=createWorshipAtomicClient({journal,makeId:()=> 'stable-id',rpc:async(name,{req})=>{
  replayCalls.push({name,req:structuredClone(req)});
  if(lost){lost=false;throw Error('Response lost')}
  return {data:name==='create_worship_service_v1'
    ? {aggregate:{...baseline,revision:'1'},committedRevision:'1',replayed:true}
    : {aggregate:null,deleted:true,currentRevision:'2',committedRevision:'2',replayed:true}};
}});
const identity=['fixture','2026-10-12'];
assert.equal(lifecycle.creationId(identity),lifecycle.creationId(identity));
await assert.rejects(lifecycle.create(creation),/Response lost/);
const recovered=await lifecycle.create({...creation,document:{...creation.document,updatedAt:'two'}});
assert.equal(recovered.service.id,'service');
assert.deepEqual(replayCalls[0],replayCalls[1]);
lost=true;await assert.rejects(lifecycle.remove('service'),/Response lost/);
assert.equal(await lifecycle.remove('service'),true);
assert.deepEqual(replayCalls[2],replayCalls[3]);
assert.equal(await lifecycle.remove('service'),true);
assert.equal(replayCalls.length,4);
lifecycle.finishCreation(identity,'stable-id');
assert.equal([...memory.keys()].length,0);
console.log('PASS creation identity, ignored client timestamps, exact create/delete retry and tombstone receipt');
