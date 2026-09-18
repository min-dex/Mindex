import assert from 'node:assert/strict';
import { createWorshipStore } from '../mindex.worship-store.mjs';
const memory = new Map();
const journal = {getItem:key=>memory.get(key) || null,setItem:(key,value)=>memory.set(key,value),removeItem:key=>memory.delete(key)};
const methods={create:'create',save:'save',delete:'delete'};
const aggregate = revision => ({revision,service:{id:'service'},sections:[],elements:[],slides:[]});
let rpcCalls=0, captured, respond;
const store=createWorshipStore({journal,methods,makeId:()=>`request-${rpcCalls}`,
  rpc:async(name,{req})=>{ rpcCalls++; captured=req; return new Promise(resolve=>{respond=resolve;}); }});
store.acceptRead('service',aggregate('1'));
const draft={serviceId:'service',expectedRevision:'1',document:{sourceText:'before'}};
const first=store.save('save',draft);
draft.document.sourceText='newer unsaved edit';
assert.equal(captured.document.sourceText,'before');
await assert.rejects(store.retry('service'),/SAVE_IN_PROGRESS/);
respond({error:new Error('network outcome unknown')});
await assert.rejects(first,/network outcome unknown/);
const pending=store.pending('service');
assert.equal(pending.request.document.sourceText,'before');
await assert.rejects(store.save('save',draft),/PENDING_REQUEST/);
assert.equal(rpcCalls,1);
const retried=store.retry('service');
assert.deepEqual(captured,pending.request);
respond({data:{replayed:true,committedRevision:'2',aggregate:aggregate('2')}});
await retried;
assert.equal(store.pending('service'),null);
assert.equal(draft.document.sourceText,'newer unsaved edit');
store.acceptRead('service',aggregate('5'));
store.acceptRead('service',aggregate('3'));
assert.equal(store.baseline('service').revision,'5');
console.log('PASS frozen retry, no replacement while uncertain, unchanged draft and monotonic baseline');

const second=store.save('save',{...draft,expectedRevision:'5'});
const older=store.pending('service');
const newer={...older,request:{...older.request,requestId:'other-tab'}};
journal.setItem('mindex.atomic.pending.v1:service',JSON.stringify(newer));
respond({data:{replayed:false,committedRevision:'6',aggregate:aggregate('6')}});
await second;
assert.equal(store.pending('service').request.requestId,'other-tab');
assert.throws(()=>store.resolvePending('service','wrong'),/REQUEST_ID_MISMATCH/);
store.resolvePending('service','other-tab');
console.log('PASS late response cannot clear another tab request');

let contacted=false;
const quota=createWorshipStore({journal:{...journal,setItem:()=>{throw new Error('quota');}},methods,
  rpc:async()=>{contacted=true;}});
quota.acceptRead('service',aggregate('1'));
await assert.rejects(quota.save('save',{serviceId:'service',expectedRevision:'1'}),/quota/);
assert.equal(contacted,false);
console.log('PASS journal quota failure prevents network write');

let sent;
const reload=createWorshipStore({journal,methods,rpc:async(name,{req})=>{
  sent=req; return {data:{replayed:true,committedRevision:'7',aggregate:aggregate('8')}};
}});
journal.setItem('mindex.atomic.pending.v1:service',JSON.stringify(older));
await reload.retry('service');
assert.deepEqual(sent,older.request);
assert.equal(reload.baseline('service').revision,'8');
console.log('PASS journal survives client recreation and accepts latest-state replay');
const deletedStore=createWorshipStore({journal,methods,rpc:async()=>({data:{
  replayed:true,committedRevision:'2',currentRevision:'10',aggregate:null,deleted:true,
}})});
deletedStore.acceptRead('service',aggregate('9'));
journal.setItem('mindex.atomic.pending.v1:service',JSON.stringify(older));
await deletedStore.retry('service');
assert.equal(deletedStore.baseline('service').deleted,true);
assert.equal(deletedStore.baseline('service').revision,'10');
deletedStore.acceptRead('service',aggregate('9'));
assert.equal(deletedStore.baseline('service').deleted,true);
console.log('PASS pre-deletion receipt observes the latest tombstone revision');
