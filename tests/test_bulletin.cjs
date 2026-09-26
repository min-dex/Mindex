const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const c=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync('mindex.bulletin.js','utf8'),c);
const fixture={service:{id:'service',service_date:'2026-09-20',worship_leader:'인도자'},
  sections:[{id:'s',service_id:'service',title:'찬양',section_key:'praise',sort_order:1},
    {id:'p',service_id:'service',title:'대표기도',section_key:'prayer',sort_order:2},
    {id:'w',service_id:'service',title:'설교',section_key:'sermon',sort_order:3}],
  elements:[{id:'a',section_id:'s',sort_order:1,element_type:'praise',song_id:'song',title:'stale song'},
    {id:'b',section_id:'p',sort_order:1,element_type:'title_person',person:'예배 담당자'},
    {id:'c',section_id:'w',sort_order:1,element_type:'title_person',title:'저장된 설교',source_ref:{slotKey:'sermon.title'}},
    {id:'d',section_id:'w',sort_order:2,element_type:'video',title:'송출 영상'}],
  songs:[{id:'song',title:'DB 찬양',hymn_no:309}],calendar:[{date:'2026-09-20',young_adult_prayer:'교회력 담당자'},
    {date:'2026-09-27',young_adult_prayer:'다음 담당자'}]};
const before=JSON.stringify(fixture);
const result=c.window.MindexBulletin.resolveSource(fixture);
assert.equal(result.order[0].content,'309 DB 찬양');
assert.equal(result.order[1].person,'교회력 담당자');
assert.equal(result.sermon,'저장된 설교');
assert.equal(result.order.length,3);
assert.equal(result.prayers.find(r=>r.date==="2026-09-27").next,true);
assert.equal(JSON.stringify(fixture),before,'Resolver must not mutate saved aggregates');
fixture.calendar[0].young_adult_prayer='';
assert.equal(c.window.MindexBulletin.resolveSource(fixture).order[1].person,'예배 담당자');
fixture.elements.push({id:'creed',section_id:'s',sort_order:9,element_type:'body',title:'사도신경',body:'송출용 신앙고백 전문',source_ref:{label:'사도신경',slotKey:'faith.creed'}},
  {id:'citation',section_id:'w',sort_order:9,element_type:'scripture_body',scripture_reference:'요한복음 1:1',source_ref:{label:'인용 구절',slotKey:'sermon.citation'}});
const fullCopy=c.window.MindexBulletin.resolveSource({...fixture,settings:{compactOrder:false}});
assert.equal(fullCopy.order.find(r=>r.label==='사도신경').content,'송출용 신앙고백 전문');
assert.ok(fullCopy.order.some(r=>r.id==='citation'));
const printOnly=c.window.MindexBulletin.resolveSource({...fixture,settings:{compactOrder:true}});
assert.equal(printOnly.order.find(r=>r.label==='사도신경').content,'');
assert.ok(!printOnly.order.some(r=>r.id==='citation'),'Sermon citations are not separate worship-order readings');
for(const f of c.window.MindexBulletin.defaultFrames()) {
  assert.ok(c.window.MindexBulletin.TOKENS.fontSizes.includes(f.size));
  assert.ok(f.x>=0&&f.y>=0&&f.x+f.w<=297&&f.y+f.h<=210,'Frame stays on paper');
}
console.log('PASS bulletin saved-source resolver, prayer authority, media filtering, numeric frame bounds');

const {monthlyView,profileForDate}=c.window.MindexBulletin;
const view=monthlyView([{date:'2026-09-27',young_adult_prayer:''},{date:'2026-10-04',young_adult_prayer:'담당자'}], '2026-09-20', {}, [{date:'2026-09-27',noGathering:true,label:'연합예배'}]);
assert.equal(view.prayers.length,5);
assert.equal(view.prayers.find(r=>r.next).date,'2026-09-27');
assert.equal(view.prayers.find(r=>r.next).person,'(연합예배)');
assert.equal(view.prayers[0].person,'미정');
assert.equal(monthlyView([], '2026-08-23').prayers.length,6);
const separate=monthlyView([{date:'2026-10-02',church_schedule:'월삭'}], '2026-09-20', {eventsMonth:'2026-10',rosterMonth:'2026-08'});
assert.match(separate.events,/월삭/);assert.equal(separate.prayers[0].date,'2026-08-02');
const currentWeek=monthlyView([{date:'2026-09-20',church_schedule:'지난 주 일정'},{date:'2026-09-27',church_schedule:'이번 주 일정'}], '2026-09-27');
assert.equal(currentWeek.events,'9월 20일  지난 주 일정\n9월 27일  이번 주 일정','Printed monthly panels retain the whole month');
const monthReview=monthlyView([{date:'2026-09-20',church_schedule:'지난 주 일정'},{date:'2026-09-27',church_schedule:'이번 주 일정'}], '2026-09-27',{eventsMonth:'2026-09'});
assert.match(monthReview.events,/지난 주 일정/,'An explicitly selected month may show its complete history');
assert.match(profileForDate('2026-06-28').address,/서구/);
assert.match(profileForDate('2026-07-05').address,/검단구/);
assert.match(profileForDate('2026-05-24').notices,/오전 11시/);
assert.match(profileForDate('2026-05-31').notices,/오후 3시/);
assert.match(profileForDate('2025-01-26').verse,/시편/);
assert.match(profileForDate('2025-02-02').verse,/이사야/);
console.log('PASS dated profiles, complete Sunday roster, exceptions, NEXT and independent months');
const adSource=c.window.MindexBulletin.resolveSource({service:{id:'ad-service',service_date:'2026-09-20'},sections:[{id:'ads',section_key:'announcements',title:'광고',sort_order:1,person:'section person'}],elements:[{id:'ad',section_id:'ads',element_type:'body',title:'광고 본문',person:'예배 담당자',sort_order:1}]});
assert.equal(adSource.order[0].person,'예배 담당자','Bulletin advertisement assignee comes from the worship record');
assert.equal(adSource.news,'광고 본문');
console.log('PASS announcement person and body come from worship records');

for (const person of ['', '   ']) {
  const source=c.window.MindexBulletin.resolveSource({service:{id:'s',service_date:'2026-09-20'},
    sections:[{id:'a',section_key:'announcements',title:'광고',sort_order:1,person:'unused section person'}],
    elements:[{id:'e',section_id:'a',element_type:'body',title:'본문',person,sort_order:1}]});
  assert.equal(source.order[0].person,'','Empty individual assignee must not inherit section metadata');
}
console.log('PASS section assignees are never inherited');

const split=c.window.MindexBulletin.resolveSource({service:{id:'copy',service_date:'2026-09-20'},sections:[{id:'ann',section_key:'announcements'}],elements:[{id:'ann1',section_id:'ann',element_type:'body',body:'오늘도 청년부 예배에 오신 여러분을 환영하고 축복합니다 :)\n1. 오늘 셀 모임입니다.\n2. 청년부 기도 모임(매주 토요일 오후 3시)에 참여 바랍니다.\n3. 검단우리교회는 신천지 출입을 금지합니다.'}]});
assert.equal(split.news,'1. 오늘 셀 모임입니다.');
assert.match(split.notices,/◈ 청년부 기도 모임/);
assert.match(split.notices,/◈ 검단우리교회/);
assert.match(split.welcome,/^오늘도.*환영/);
assert.match(split.announcements,/2\. 청년부 기도 모임/);
console.log('PASS raw announcements and optional print-order compaction');
const doc={fields:{news:'① 그대로'},settings:{theme:'aurora',eventsMonth:'2026-09',compactOrder:true},frames:c.window.MindexBulletin.defaultFrames()};
const stored=c.window.MindexBulletin.storedValue(doc);
assert.equal(stored.layout.background,'26-A1.png');
assert.equal(stored.content.fields.news,'① 그대로');
const restored={};c.window.MindexBulletin.applyStored(restored,{...stored,revision:2});
assert.equal(restored.settings.theme,'26-A1.png');assert.equal(restored.revision,2);
assert.equal(restored.fields.news,'① 그대로');
assert.equal(restored.settings.compactOrder,true);
assert.equal(restored.frames.length,doc.frames.length);
console.log('PASS content/layout serialization and legacy background identity');

const sanitized=c.window.MindexBulletin.normalizeSnapshot({fields:{news:'문구',unexpected:'ignored'},frames:[null,{id:'news',x:999,y:-1,size:Infinity}],settings:{theme:'26-A1.png'},revision:999,id:'wrong'});
assert.equal(sanitized.fields.news,'문구');assert.equal(sanitized.fields.unexpected,undefined);assert.equal(sanitized.revision,undefined);
assert.equal(sanitized.frames.find(f=>f.id==='news').x,10);
assert.doesNotThrow(()=>c.window.MindexBulletin.normalizeSnapshot({frames:{}}));
assert.throws(()=>c.window.MindexBulletin.applyStored({}, {revision:1,content:[],layout:{}}));
assert.throws(()=>c.window.MindexBulletin.applyStored({}, {revision:1,content:{},layout:{frames:{}}}));
fixture.elements.find(e=>e.id==='citation').source_ref.slotKey='sermon.citation.1';
assert.ok(!c.window.MindexBulletin.resolveSource({...fixture,settings:{compactOrder:true}}).order.some(r=>r.id==='citation'));
console.log('PASS safe snapshots, invalid DB layout and canonical citation slot');

const autoValue=c.window.MindexBulletin.storedValue({fields:{},settings:{},frames:[]});
assert.equal(autoValue.layout.background,'auto');
const autoRestored={};c.window.MindexBulletin.applyStored(autoRestored,{...autoValue,revision:1});
assert.equal(autoRestored.settings.theme,'auto');
const noBackground=c.window.MindexBulletin.storedValue({fields:{},settings:{theme:''},frames:[]});
assert.equal(noBackground.layout.background,'');
console.log('PASS automatic background selection and explicit no-background persistence');

const actual=require('./fixtures/bulletin-20260920.json');
const actualBefore=JSON.stringify(actual);
const reference=c.window.MindexBulletin.resolveSource(actual);
assert.equal(reference.scripture,'사무엘상 22:1–5');
assert.match(reference.liturgical,/순교자기념주일/);
assert.equal(reference.order.length,13,'The verified print template includes communal prayer without mutating stored elements');
assert.equal(reference.order.filter(r=>r.label==='성경봉독').length,1);
assert.equal(reference.order.find(r=>r.label==='찬양').content.split('\n').length,4);
assert.equal(reference.order.find(r=>r.label==='사도신경').content,'');
assert.equal(reference.order.find(r=>r.label==='광고').person,'');
assert.equal(reference.news.split('\n').length,2);
assert.equal(reference.notices.split('\n').length,2);
assert.equal(JSON.stringify(actual),actualBefore);
assert.equal(c.window.MindexBulletin.normalizeSnapshot({}).settings.compactOrder,true);
assert.equal(c.window.MindexBulletin.normalizeSnapshot({settings:{compactOrder:false}}).settings.compactOrder,false);
console.log('PASS actual September 20 source: print grouping, array references, calendar note and separate copy');

const B=c.window.MindexBulletin;
const baseDoc=source=>({...B.normalizeSnapshot({}),source});
const commonDoc=baseDoc(B.resolveSource(actual));
assert.equal(B.fieldValue(commonDoc,'church'),'기독교대한성결교회 검단우리교회');
assert.match(B.fieldValue(commonDoc,'eventsText'),/4일 \(금\) 오후 8:00/);
assert.match(B.fieldValue(commonDoc,'notices'),/토요일 오후 3시/);
assert.match(B.fieldValue(commonDoc,'outline'),/길을 잃다/);
const history=[
 {date:'2026-09-06',content:{reuse:{common:{meeting:'새 예배 장소',notices:''},months:{'2026-09':'9월 확인 일정'}},fields:{news:'이전 주 소식',leader:'이전 인도자',outline:'이전 설교'}}},
 {date:'2026-10-04',content:{reuse:{common:{meeting:'미래 장소'},months:{'2026-10':'미래 일정'}}}}
];
const reused=B.resolveSource({...actual,history});
assert.equal(B.fieldValue(baseDoc(reused),'meeting'),'새 예배 장소');
assert.equal(reused.events,'9월 확인 일정');
assert.equal(B.fieldValue(baseDoc(reused),'notices'),'','Explicitly shared blanks override older recurring text in announcements');
assert.ok(!reused.news.includes('이전 주 소식'));
assert.equal(reused.leader,'이재희 청년');
assert.equal(B.reusableContent('2026-09-20','2026-09',history).common.notices,'');
const nextMonth=B.resolveSource({...actual,service:{...actual.service,service_date:'2026-10-01'},history});
assert.equal(nextMonth.events,'','September content must not leak across the month boundary');
assert.equal(nextMonth.common.meeting,'새 예배 장소','Future-dated changes must not apply early');
for(const month of ['01','02','03','04','05','06','07','08','09'])assert.ok(B.reusableContent(`2026-${month}-28`,`2026-${month}`).events,'Every reviewed month has its own original panel');
const edited=baseDoc(reused);edited.fields.meeting='수정한 장소';edited.fields.news='이번 주만';
edited.months={'2026-09':'이번 달 확정 일정','2026-10':'다음 달 확정 일정'};
const saved=B.storedValue(edited);
assert.equal(saved.content.reuse.common.meeting,'수정한 장소');
assert.equal(saved.content.reuse.common.news,undefined);
assert.equal(saved.content.reuse.common.leader,undefined);
assert.equal(saved.content.reuse.months['2026-09'],'이번 달 확정 일정');
const reload=baseDoc(nextMonth);B.applyStored(reload,{...saved,revision:1});
reload.source=B.resolveSource({...actual,history:[{date:'2026-09-13',content:{reuse:{common:{church:'나중에 수정된 교회명'}}}}]});
assert.equal(B.fieldValue(reload,'church'),'기독교대한성결교회 검단우리교회','Saved inherited copy is stable until an explicit source refresh');
assert.equal(B.fieldValue(reload,'eventsText'),'이번 달 확정 일정');
reload.settings.eventsMonth='2026-10';assert.equal(B.fieldValue(reload,'eventsText'),'다음 달 확정 일정');
reload.settings.eventsMonth='2026-09';assert.equal(B.fieldValue(reload,'eventsText'),'이번 달 확정 일정');
reload.fields.church='';assert.equal(B.fieldValue(reload,'church'),'','An intentional blank remains blank');
assert.equal(B.normalizeSnapshot({months:{bad:'discard','2026-09':'keep'},inherited:{common:{news:'discard'},months:{bad:'discard'}}}).months.bad,undefined);
console.log('PASS monthly reuse, dated common copy, week/month isolation, explicit blanks and saved inherited values');

const legacy=B.reusableContent('2026-09-20','2026-09',[{date:'2026-09-06',content:{fields:{church:'기존에 수정한 교회명',eventsText:'기존 월간 일정',news:'복사하면 안 되는 소식'}}}]);
assert.equal(legacy.common.church,'기존에 수정한 교회명');assert.equal(legacy.events,'기존 월간 일정');assert.equal(legacy.common.news,undefined);


const frozenSource=B.resolveSource(actual);
const frozenDoc=baseDoc(frozenSource);
frozenDoc.fields.announcer='';
frozenDoc.settings.outlineColumns=2;
const publication=B.storedValue(frozenDoc);
assert.equal(publication.layout.outlineColumns,2);
assert.equal(publication.content.outlineColumns,undefined,'Column layout belongs to layout data');
const publicationDoc={};B.applyStored(publicationDoc,{...publication,revision:1});
const changedSource={...frozenSource,sermon:'changed sermon',news:'changed news',leader:'changed leader',order:[],prayers:[]};
const frozenAgain=B.applySourceSnapshot(changedSource,publicationDoc.sourceSnapshot);
assert.equal(frozenAgain.sermon,frozenSource.sermon);
assert.equal(frozenAgain.news,frozenSource.news);
assert.equal(JSON.stringify(frozenAgain.prayers),JSON.stringify(frozenSource.prayers));
assert.equal(B.applySourceSnapshot(changedSource,null).sermon,'changed sermon');
assert.equal(B.applySourceSnapshot({...changedSource,id:'different'},publicationDoc.sourceSnapshot).sermon,'changed sermon');
const anotherMonth=B.applySourceSnapshot({...changedSource,rosterMonth:'2026-10'},publicationDoc.sourceSnapshot);
assert.equal(anotherMonth.prayers.length,0,'An unrecorded month must use newly loaded calendar data');
const live=B.resolveSource({...actual,settings:{archiveReference:false}});
assert.equal(live.leader,'');
assert.equal(live.outline,undefined);
const future=B.resolveSource({...actual,service:{...actual.service,service_date:'2026-10-04'}});
assert.equal(future.hasArchiveReference,false);
assert.equal(future.leader,'');
assert.equal(future.outline,undefined);
assert.equal(future.order.filter(r=>r.label==='기도').length,1,'The printed prayer belongs to the youth template, not individual issue exceptions');
console.log('PASS published source freezing, explicit refresh, month isolation, layout storage and no historical weekly-copy leakage');
