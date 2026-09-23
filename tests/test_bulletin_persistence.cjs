const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const app=fs.readFileSync('app.js','utf8');
const code=app.slice(app.indexOf('async function loadBulletinDraft('),app.indexOf('function mountServiceBulletinWorkbench('));
let result,calls;
const query=new Proxy({}, {get:(_,method)=>(...args)=>{
  calls.push([method,...args]);return method==='maybeSingle'?Promise.resolve(result):query;
}});
const ctx=vm.createContext({state:{client:{from(table){calls.push(['from',table]);return query;}}}});
vm.runInContext(code,ctx);
(async()=>{
  calls=[];result={data:null,error:null};assert.equal(await ctx.loadBulletinDraft('service'),null);
  assert.deepEqual(calls.find(c=>c[0]==='eq'),['eq','service_id','service']);
  const value={content:{fields:{news:'原文 ③'}},layout:{background:'26-A4.png',frames:[]}};
  calls=[];result={data:{...value,revision:1},error:null};await ctx.saveBulletinDraft('service',value,0);
  assert.equal(calls.find(c=>c[0]==='insert')[1].service_id,'service');
  calls=[];result={data:{...value,revision:3},error:null};await ctx.saveBulletinDraft('service',value,2);
  assert.deepEqual(calls.filter(c=>c[0]==='eq'),[['eq','service_id','service'],['eq','revision',2]]);
  assert.deepEqual(calls.find(c=>c[0]==='update')[1],value);
  for(const response of [{data:null,error:null},{data:null,error:{code:'23505'}}]){
    calls=[];result=response;await assert.rejects(()=>ctx.saveBulletinDraft('service',value,2),/다른 곳에서/);
  }
  calls=[];result={data:null,error:{code:'42501',message:'permission denied'}};
  await assert.rejects(()=>ctx.saveBulletinDraft('service',value,2),/DB 저장 실패/);
  calls=[];result={data:null,error:{code:'PGRST205',message:'missing table'}};
  await assert.rejects(()=>ctx.loadBulletinDraft('service'),/DB를 불러오지/);
  console.log('PASS bulletin DB adapter: content/layout writes, revision compare, conflicts, permission and missing schema');
})().catch(e=>{console.error(e);process.exitCode=1;});
