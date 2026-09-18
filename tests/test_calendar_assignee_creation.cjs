const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={console,document:{addEventListener(){}},localStorage:{getItem(){return null}},setTimeout,clearTimeout,URL,URLSearchParams,crypto:require('node:crypto').webcrypto};c.window=c;c.location={search:'',hash:'',pathname:'/'};vm.createContext(c);
for(const f of ['mindex.constants.js','mindex.presenter.js','mindex.worship-input.js','mindex.setlist-links.js','app.js'])vm.runInContext(fs.readFileSync(f,'utf8'),c,{filename:f});
c.assert=assert;
(async()=>{try{await vm.runInContext(`(async()=>{
 state.calendarLoaded=true;state.calendarData=[{date:'2026-09-13',nursery_prayer:'유치부 담당',children_prayer:'어린이 담당',youth_prayer:'청소년 담당',young_adult_prayer:'청년 담당',youth_offering_prayer:'봉헌 담당'}];
 const stored={mindex_worship_services:[],mindex_worship_sections:[],mindex_worship_elements:[]};let fail=false;let writes=0;
 state.client={from(table){return {insert(rows){writes++;if(fail&&table==='mindex_worship_elements')return Promise.resolve({error:new Error('fixture write failure')});stored[table].push(...JSON.parse(JSON.stringify(rows)));return table==='mindex_worship_services'?{select:async()=>({data:rows,error:null})}:Promise.resolve({error:null})},delete(){return {in:async(_,ids)=>{stored.mindex_worship_services=stored.mindex_worship_services.filter(x=>!ids.includes(x.id));const sections=stored.mindex_worship_sections.filter(x=>ids.includes(x.service_id));stored.mindex_worship_sections=stored.mindex_worship_sections.filter(x=>!ids.includes(x.service_id));stored.mindex_worship_elements=stored.mindex_worship_elements.filter(x=>!sections.some(s=>s.id===x.section_id));return {error:null}}}}}}};
 assert.equal(calendarAssigneeRowsForNewService({id:'child-original',type_id:'children',date:'2026-09-13'}).elements.length,0,'Do not invent a prayer slot absent from the template');
 SERVICE_ORDER_TEMPLATE_FALLBACKS.nursery=[...SERVICE_ORDER_TEMPLATE_FALLBACKS.nursery,publicWorshipPrayerStep()];
 SERVICE_ORDER_TEMPLATE_FALLBACKS.children=[...SERVICE_ORDER_TEMPLATE_FALLBACKS.children,publicWorshipPrayerStep()];
 const payloads=['nursery','children','youth','young-adult'].map(type=>autoWorshipServicePayload({typeId:type,date:'2026-09-13'}));
 const created=await insertWorshipServicesWithCalendarAssignees(payloads);assert.equal(created.length,4);assert.equal(writes,3,'Batch writes should not multiply per service');assert.equal(stored.mindex_worship_elements.length,5);
 state.services=created.map(normalizeWorshipService);
 state.calendarData[0].young_adult_prayer='바뀐 교회력';
 for(const service of state.services){const rows=groupWorshipElements(stored.mindex_worship_sections,stored.mindex_worship_elements)[service.id];const prayer=rows.find(x=>x.label==='대표기도');const expected=service.type_id==='nursery'?'유치부 담당':service.type_id==='children'?'어린이 담당':service.type_id==='youth'?'청소년 담당':'청년 담당';assert.equal(prayer.assignee,expected);assert.equal(serviceItemEditableAssigneeValue(prayer,service),expected);assert.equal(serviceItemEditableAssigneeValue({...prayer,assignee:''},service),'','Explicit clear must not refill');}
 const before=stored.mindex_worship_services.length;fail=true;await assert.rejects(insertWorshipServicesWithCalendarAssignees([autoWorshipServicePayload({typeId:'young-adult',date:'2026-09-13'})]),/fixture write failure/);assert.equal(stored.mindex_worship_services.length,before,'Partial creation rollback');assert.equal(state.services.length,4);
 const oldLoad=loadCalendarData;loadCalendarData=async()=>{};state.calendarLoaded=false;const beforeWrites=writes;await assert.rejects(insertWorshipServicesWithCalendarAssignees([autoWorshipServicePayload({typeId:'youth',date:'2026-09-13'})]),/교회력/);assert.equal(writes,beforeWrites,'Calendar failure must precede writes');loadCalendarData=oldLoad;
 fail=false;state.calendarLoaded=true;
 const wed=await insertWorshipServicesWithCalendarAssignees([{id:'wed-leader',service_type_id:'wed',service_date:'2026-08-12',worship_leader:'unused',praise_leader:''}]);
 assert.equal(wed[0].worship_leader,'');assert.equal(wed[0].praise_leader,'');
 assert.equal(serviceWorshipLeaderLabel({worshipLeader:'unused'}),'');
 assert.equal(servicePraiseLeaderLabel({type_id:'sunday-first',praiseLeader:'김석범 목사'}),'김석범 목사');
 console.log('PASS all departments: persisted prayer/offering, no live overwrite, explicit clear, bounded batch writes, failure rollback');
})()`,c);}catch(e){console.error(e);process.exitCode=1}})();
