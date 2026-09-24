const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
require('../mindex.setlist-links.js');
const snapshot = {services:[{id:'s',service_date:'2026-09-20',service_type_id:'sun_3rd'}],sections:[{id:'sec',service_id:'s'}]};
for (const flags of [{template_suppressed:true},{legacy_template_suppressed:true},{config:{templateSuppressed:true}},{config:{template_suppressed:true}}]) {
 const result = MindexSetlistLinks.fromServices({...snapshot,elements:[
  {id:'deleted',section_id:'sec',element_type:'praise',title:'삭제',label:'찬양',...flags},
  {id:'kept',section_id:'sec',element_type:'praise',title:'유지',label:'찬양',config:{hiddenInPresentation:true}}
 ]});
 assert.equal(result.candidates.length,1);assert.equal(result.candidates[0].id,'kept');assert.equal(result.candidates[0].raw_label,'찬양 1');
}
const source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('async function loadWorshipSetlistSongCatalog(');
let calls=0,fail=true;
const context=vm.createContext({state:{client:{},config:{url:'test'},worshipSetlistSongCatalog:{status:'idle'}},window:{MindexSetlistLinks},console:{warn(){}},fetchSupabasePaged:async()=>{calls++;if(fail)throw new Error('offline');return []}});
vm.runInContext(source.slice(start,source.indexOf('\n}\n',start)+2),context);
(async()=>{
 await context.loadWorshipSetlistSongCatalog();assert.equal(context.state.worshipSetlistSongCatalog.status,'failed');
 fail=false;await Promise.all([context.loadWorshipSetlistSongCatalog(),context.loadWorshipSetlistSongCatalog()]);
 assert.equal(context.state.worshipSetlistSongCatalog.status,'loaded');assert.equal(calls,4);
 await context.loadWorshipSetlistSongCatalog();assert.equal(calls,4);
 await context.loadWorshipSetlistSongCatalog({force:true});assert.equal(calls,6);
 console.log('PASS suppressed-item exclusion, stable numbering, presentation visibility, retry and deduplication');
})().catch(e=>{console.error(e);process.exitCode=1});
