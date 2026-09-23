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
fixture.elements.push({id:'creed',section_id:'s',sort_order:9,element_type:'body',title:'송출용 신앙고백 전문',source_ref:{label:'사도신경',slotKey:'faith.creed'}},
  {id:'citation',section_id:'w',sort_order:9,element_type:'scripture_body',scripture_reference:'요한복음 1:1',source_ref:{label:'인용 구절',slotKey:'sermon.citation.1'}});
const printOnly=c.window.MindexBulletin.resolveSource(fixture);
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
assert.match(split.notices,/기도 모임/);assert.match(split.notices,/신천지/);
assert.match(split.welcome,/환영/);
console.log('PASS reference layout announcement regions preserve source copy');
