const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync('app.js','utf8');const c={worshipAppServiceTypeId:x=>({wed:'wednesday',sun_3rd:'sunday-main'}[x]||x),serviceDateString:x=>typeof x==='string'?x:x?.date||x?.service_date||'',dateOnlyUtcTime:x=>Date.parse(x+'T00:00:00Z'),isAllGenerationsWorshipDate:x=>x==='2026-07-19',isAllGenerationsWorshipContext:x=>x==='온세대 찬양예배',serviceFridayVariantKey:x=>x.source_ref?.friday_variant||(x.alias==='삼삼오오예배'?'3355':'friday'),state:{},serviceUsesPraiseLeader:()=>true};vm.createContext(c);
for(const name of ['defaultServicePraiseLeader','updateNewServiceFormField']){const a=s.indexOf('function '+name+'(');vm.runInContext(s.slice(a,s.indexOf('\n}\n',a)+2),c);}
const f=c.defaultServicePraiseLeader;
for(const [type,name] of Object.entries({'sunday-main':'김석범 목사','sunday-afternoon':'박수경 집사',children:'서영윤 선생님',youth:'허호범 선생님','young-adult':'이재희 청년',friday:'이재희 청년'}))assert.equal(f(type),name);
assert.equal(f('sun_3rd','2026-07-19'),'이재희 청년');assert.equal(f('sunday-main',{alias:'온세대 찬양예배'}),'이재희 청년');
assert.equal(f('friday',{source_ref:{friday_variant:'3355'}}),'김덕열 집사');assert.equal(f('friday',{alias:'삼삼오오예배'}),'김덕열 집사');assert.equal(f('wed','2026-09-16'),'김석범 목사');
c.state.newServiceForm={type_id:'friday',leader:'이재희 청년'};const field=(key,value)=>({dataset:{newServiceField:key},value,closest:()=>null});c.updateNewServiceFormField(field('alias','삼삼오오예배'));assert.equal(c.state.newServiceForm.leader,'김덕열 집사');c.updateNewServiceFormField(field('leader',''));c.updateNewServiceFormField(field('date','2026-09-18'));assert.equal(c.state.newServiceForm.leader,'');
console.log('PASS defaults, variants, manual blank preserved');
