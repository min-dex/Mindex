const assert = require('node:assert/strict');
require('../mindex.setlist-links.js');
const {buildIndex,resolve,split} = globalThis.MindexSetlistLinks;
const songs = [
 {id:'a', title:'곡 A', subtitle:'별명'}, {id:'b',title:'곡 B'},
 {id:'hymn',title:'동명곡',hymn_no:'38'}, {id:'ccm',title:'동명곡'},
 {id:'number',title:'찬송 제목',hymn_no:'259'},
 {id:'s1',title:'성령의 불로',subtitle:'예수님 목마릅니다'},
 {id:'s2',title:'성령의 불로',subtitle:'주의 도를 버리고'},
];
const versions=[{id:'v',source_song_id:'number',version_label:'통일 100 찬송 제목'}, {id:'a-v',source_song_id:'a',curated_version_name:'버전 별명'}];
const before=JSON.stringify({songs,versions});const index=buildIndex(songs,versions);
assert.deepEqual(split('메들리 (곡 A + 곡 B)'),['곡 A','곡 B']);
assert.deepEqual(split('곡 A + 모르는 곡'),['곡 A','모르는 곡']);
assert.equal(resolve(' 곡 A ',index).song.id,'a');
assert.equal(resolve('별명',index).text,'곡 A');
assert.equal(resolve('버전 별명',index).song.id,'a');
assert.equal(resolve('곡 A (별명)',index).song.id,'a');
assert.equal(resolve('동명곡',index).status,'ambiguous');
assert.equal(resolve('38 동명곡',index).song.id,'hymn');
assert.equal(resolve('256 찬송 제목',index).status,'hymn-number');
assert.equal(resolve('259 찬송 제목 ⑴',index).text,'259 찬송 제목 ⑴');
assert.equal(resolve('통 100 찬송 제목',index).text,'259 찬송 제목');
assert.equal(resolve('통 259 찬송 제목',index).status,'hymn-number');
assert.equal(resolve('성령의 불로 (예수님 목마릅니다)',index).song.id,'s1');
assert.equal(resolve('동명곡',index,'ccm').song.id,'ccm');
assert.equal(resolve('곡 A',index,'deleted').status,'broken-link');
assert.equal(resolve('새 곡',index).status,'unmatched');
assert.equal(resolve('곡 A',null).status,'pending');
assert.equal(JSON.stringify({songs,versions}),before);
console.log('PASS: unique/ambiguous titles, explicit links, aliases, medleys, hymn numbers/editions/verses and immutable source');

assert.equal(MindexSetlistLinks.isExcluded({raw_label:'3부 특송'}),true);
assert.equal(MindexSetlistLinks.isExcluded({raw_label:'3 부 특송'}),true);
assert.equal(MindexSetlistLinks.isExcluded({raw_label:'특송'},'sun_3rd'),true);
assert.equal(MindexSetlistLinks.isExcluded({raw_label:'2부 특송'},'sun_3rd'),false);
assert.equal(MindexSetlistLinks.isExcluded({raw_label:'특송'},'fri'),false);
assert.equal(MindexSetlistLinks.isExcluded({raw_label:'찬양'},'sun_3rd'),false);
const reviewed=buildIndex([{id:'569',title:'선한 목자 되신 우리 주',hymn_no:'569'},{id:'jesus',title:'예수 예수'}]);
assert.equal(resolve('569 선한 목자 되신 주',reviewed).status,'unmatched');
assert.equal(resolve('569 선한 목자 되신 우리 주',reviewed).song.id,'569');
assert.equal(resolve('능력의 이름 예수',reviewed).status,'unmatched');
const distinct=buildIndex([{id:'jesus',title:'예수 예수'},{id:'power',title:'능력의 이름 예수'}]);
assert.equal(resolve('능력의 이름 예수',distinct).song.id,'power');
assert.equal(resolve('568 선한 목자 되신 우리 주',reviewed).status,'hymn-number');
console.log('PASS: third-service special exclusions and removal of legacy aliases');

const services=[{id:'s',service_date:'2026-07-12',service_type_id:'sun_3rd',praise_leader:'인도자'},
 {id:'other',service_date:'2026-07-12',service_type_id:'sun_2nd'},
 {id:'empty',service_date:'2026-07-19',service_type_id:'sun_3rd'}];
const sections=[{id:'section',service_id:'s',sort_order:1,title:'찬양',section_key:'praise'},
 {id:'second',service_id:'other',sort_order:1,title:'찬양'}];
const elements=[{id:'b',section_id:'section',sort_order:2,element_type:'praise',song_id:'b',label:'찬양 2'},
 {id:'a',section_id:'section',sort_order:1,element_type:'praise',song_id:'a',label:'찬양 1'},
 {id:'empty-slot',section_id:'section',sort_order:3,element_type:'praise',title:''},
 {id:'manual',section_id:'section',sort_order:4,element_type:'praise',title:'특송 제목',label:'특송'},
 {id:'text',section_id:'section',sort_order:5,element_type:'body',title:'본문'},
 {id:'other-song',section_id:'second',sort_order:1,element_type:'praise',song_id:'a'}];
const live=MindexSetlistLinks.fromServices({services,sections,elements});
assert.equal(live.sources.length,2);assert.equal(live.candidates.length,4);
assert.equal(live.sources[0].leader,'인도자');
assert.deepEqual(live.candidates.filter(c=>c.import_source_id==='worship:s').map(c=>c.id),['a','b','manual']);
assert.equal(live.candidates.find(c=>c.id==='manual').archive_manual_song,true);
const merged=MindexSetlistLinks.fromServices({services,sections,elements},[{service_date:'2026-07-12',service_type_id:'sun_3rd'}]);
assert.equal(merged.sources.length,1);assert.equal(merged.sources[0].service_type_id,'sun_2nd');
assert.equal(MindexSetlistLinks.fromServices({services,sections,elements:[]}).sources.length,0);
console.log('PASS: live service cards, exact service-type deduplication, ordered songs, empty slots, manual praise and leaders');

const namedLive=MindexSetlistLinks.fromServices({services,sections,elements},[],index);
assert.equal(namedLive.candidates.find(c=>c.id==="a").raw_title,"곡 A");
const medleyLive=MindexSetlistLinks.fromServices({services:[{id:'m',service_date:'2026-08-21',service_type_id:'fri',service_alias:'삼삼오오예배'}],sections:[{id:'ms',service_id:'m',sort_order:1,title:'찬양'}],elements:[{id:'m1',section_id:'ms',sort_order:1,element_type:'praise',title:'A + B',label:'찬양 1'},{id:'m2',section_id:'ms',sort_order:2,element_type:'praise',title:'C + D + E',label:'찬양 2'},{id:'m3',section_id:'ms',sort_order:3,element_type:'praise',song_id:'a',label:'찬양 3'}]});
assert.equal(medleyLive.sources[0].aliases,'삼삼오오예배');
assert.deepEqual(medleyLive.candidates.map(c=>c.raw_label),['찬양 1–2','찬양 3–5','찬양 6']);
console.log('PASS: live service aliases and medley ranges');

const sundayEntry = (type, rows, date='2026-09-06') => ({source:{service_type_id:type,service_date:date,leader:type},candidates:rows});
const sundayRows = [{raw_label:'찬양 1',raw_title:'A'},{raw_label:'특송',raw_title:'Third'},{raw_label:'파송찬양',raw_title:'End'}];
const sundayInput = [sundayEntry('sun_1st',[{raw_label:'찬양 1'}]),sundayEntry('sun_2nd',[{raw_label:'찬양 1'},{raw_label:'특송',raw_title:'Second',suggested_song_id:'b'}]),sundayEntry('sun_3rd',sundayRows),sundayEntry('fri',[])];
const sundayBefore=JSON.stringify(sundayInput);
const combined=MindexSetlistLinks.mergeSundayEntries(sundayInput);
assert.equal(combined.length,2);
assert.equal(combined[0].source.leader,'sun_3rd');
assert.deepEqual(combined[0].candidates.map(c=>c.raw_label),['2부 특송','찬양 1','3부 특송','파송찬양']);
assert.equal(combined[0].candidates[0].suggested_song_id,'b');
assert.equal(MindexSetlistLinks.isExcluded(combined[0].candidates[2],'sun_3rd'),true);
assert.equal(MindexSetlistLinks.isExcluded(combined[0].candidates[0],'sun_3rd'),false);
assert.equal(JSON.stringify(sundayInput),sundayBefore);
assert.equal(MindexSetlistLinks.mergeSundayEntries([...sundayInput.slice(0,2),combined[0]])[0].candidates.length,4);
assert.equal(MindexSetlistLinks.mergeSundayEntries([sundayInput[1],sundayEntry('sun_3rd',sundayRows,'2026-08-30')])[0].candidates.length,3);
console.log('PASS: Sunday third-service card, second-service special only, no duplicate/date crossover, immutable records');
const archivedRows = [{raw_label:'찬양 1'}, {raw_label:'2부 특송',raw_title:'First'}, {raw_label:'파송찬양'}, {raw_label:'2부 특송',raw_title:'Second'}];
const archivedBefore = JSON.stringify(archivedRows);
const reordered = MindexSetlistLinks.mergeSundayEntries([sundayEntry('sunday-main',archivedRows)])[0];
assert.deepEqual(reordered.candidates.map(c=>c.raw_label), ['2부 특송','2부 특송','찬양 1','파송찬양']);
assert.deepEqual(reordered.candidates.slice(0,2).map(c=>c.raw_title), ['First','Second']);
assert.equal(JSON.stringify(archivedRows), archivedBefore);
assert.deepEqual(MindexSetlistLinks.mergeSundayEntries([reordered])[0].candidates, reordered.candidates);
console.log('PASS: archived second-service specials lead, stable order and idempotent projection');

assert.equal(resolve('찬송 제목', index, 'number').text, '259 찬송 제목');
assert.equal(resolve('256 예전 제목', index, 'number').text, '259 찬송 제목');
assert.equal(resolve('38 동명곡', index, 'ccm').text, '동명곡');
assert.equal(resolve('동명곡', index, 'hymn').text, '38 동명곡');
console.log('PASS DB hymn number and title override source text for linked songs');
