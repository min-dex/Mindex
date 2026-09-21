const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
require("../mindex.setlist-links.js");
const context = {
  window: {MindexSetlistLinks:globalThis.MindexSetlistLinks},
  worshipSetlistCandidateLinks: candidate => [{text:candidate.raw_title}],
  normalizeTitle: value => value.trim(),
  worshipAppServiceTypeId: value => value === 'fri' ? 'friday' : value,
};
vm.createContext(context);
for (const name of ['worshipSetlistArchiveTypeName', 'worshipSetlistArchiveTypeOrder', 'worshipSetlistArchiveAliases']) {
  const start = source.indexOf(`function ${name}(`);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}

for (const name of ['setlistCandidateDisplayOrder', 'compareSetlistCandidatesForDisplay', 'worshipSetlistArchiveDisplayLabel', 'prepareWorshipSetlistArchiveCandidates']) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, name);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}
const prepare = context.prepareWorshipSetlistArchiveCandidates;
const friday = { service_type_id: 'fri', source_kind: 'setlist' };
const song = (raw_label, raw_title, sort_order) => ({ raw_label, raw_title, sort_order });
const opening = ['밤이나 낮이나', '예수 열방의 소망', '새 힘 얻으리', '하나님은 우리의 피난처가 되시며', '보라 너희는 두려워 말고']
  .map((title, index) => song('찬양', title, index + 1));
const rows = [...opening, song('찬양', '272 고통의 멍에 벗으려고', 6),
  song('특송', '365 마음속에 근심 있는 사람', 7), song('결단', '말씀하시면', 8),
  song('기도 1', '주님과 담대히 나아가', 9), song('기도 2', '주께서 전진해 온다', 10), song('기도 3', '기도의 능력', 11)];
const original = JSON.stringify(rows);
const result = prepare(rows, friday);
assert.equal(result.map(row => row.archive_display_label || row.raw_label).join('|'),
  '찬양 1|찬양 2|찬양 3|찬양 4|찬양 5|특송|입례찬양|결단찬양|기도찬양 1|기도찬양 2|기도찬양 3');
assert.equal(result[6].raw_title, '272 고통의 멍에 벗으려고');
assert.equal(JSON.stringify(rows), original, 'source data must stay unchanged');
assert.equal(prepare(opening, friday).at(-1).archive_display_label, '찬양 5');
assert.equal(prepare(rows.filter(row => row.raw_label !== '특송'), friday)[5].archive_display_label, '입례찬양');
assert.equal(prepare([...opening, song('예배찬양', '별도 예배찬양', 6)], friday).at(-1).archive_display_label, '입례찬양');
assert.ok(prepare(rows, { ...friday, service_type_id: 'wednesday' }).filter(row => row.raw_label === '찬양').every((row, index) => row.archive_display_label === `찬양 ${index + 1}`));
assert.ok(prepare(rows, { ...friday, source_kind: 'pptx' }).every(row => row.archive_display_label !== '입례찬양'));
assert.ok(prepare([...rows, song('찬양', '추가 메인 찬양', 12)], friday).every(row => row.archive_display_label !== '입례찬양'));
console.log('PASS: Friday archive ordering, numbering, missing worship praise, explicit role, scope and source preservation');

for (const [raw, expected] of [['예배찬양','입례찬양'], ['봉헌','봉헌찬양'], ['결단','결단찬양'], ['기도 1','기도찬양 1'], ['기도찬양 2','기도찬양 2'], ['파송','파송찬양'], ['폐회','폐회찬양'], ['특송','특송'], ['3부 특송','3부 특송']]) {
  assert.equal(context.worshipSetlistArchiveDisplayLabel(raw), expected);
}
assert.equal(prepare([song('봉헌','곡',1)], {service_type_id:'youth'})[0].archive_display_label, '봉헌찬양');
console.log('PASS: Archive role labels across services and no duplicated suffix');

context.state = { search: '이재희', worshipSetlistArchiveView: 'date' };
context.worshipSetlistLeaderDrafts = new Map();
context.normalizeSearchValue = value => String(value || '').trim().toLowerCase();
context.serviceTypeDisplayName = () => '금요기도회';
context.escapeHtml = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
context.escapeAttr = value => context.escapeHtml(value).replaceAll('"', '&quot;');
for (const name of ['worshipSetlistArchiveServiceId', 'worshipSetlistLeaderInputWidth', 'renderWorshipSetlistLeaderEditor', 'filterWorshipSetlistArchiveEntries', 'renderWorshipSetlistArchiveEntry', 'renderWorshipSetlistCandidate']) {
  const start = source.indexOf(`function ${name}(`);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}
const entry = {source: {service_date: '2026-01-16', service_type_id: 'fri', leader: '이재희 청년'}, candidates: result};
assert.equal(context.filterWorshipSetlistArchiveEntries([entry]).length, 1);
context.state.search = '다른 인도자';
assert.equal(context.filterWorshipSetlistArchiveEntries([entry]).length, 0);
assert.ok(context.renderWorshipSetlistArchiveEntry(entry).includes('이재희 청년'));
assert.ok(context.renderWorshipSetlistArchiveEntry(entry).includes('<strong>금요기도회</strong>'));
context.state.worshipSetlistArchiveView = 'service';
assert.ok(context.renderWorshipSetlistArchiveEntry(entry).includes('<strong>2026-01-16</strong>'));
assert.ok(context.renderWorshipSetlistArchiveEntry({...entry, source:{}}).includes('placeholder="—" value=""'));
assert.ok(context.renderWorshipSetlistArchiveEntry({...entry, source:{leader:'<이름>'}}).includes('&lt;이름&gt;'));
console.log('PASS: Leader search, absent leader, HTML escaping and contextual card titles');

context.serviceTypeSortOrder = value => ({fri:2,youth:3})[value] || 1;
for (const name of ['parseLocalDate', 'toLocalDateStr', 'worshipSetlistArchiveWeek', 'groupWorshipSetlistArchiveEntries']) {
  const start = source.indexOf(`function ${name}(`);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}
const week = context.worshipSetlistArchiveWeek;
assert.equal(week('2026-07-12').key, '2026-07-12');
assert.equal(week('2026-07-18').key, '2026-07-12');
assert.equal(week('2026-07-19').key, '2026-07-19');
assert.equal(week('2026-07-15').title, '7월 12–18일');
assert.equal(week('2026-09-02').title, '8월 30일–9월 5일');
assert.equal(week('2026-01-01').title, '2025년 12월 28일–2026년 1월 3일');
assert.equal(week('2026-02-31').key, '');
assert.equal(week('').title, '날짜 없음');
const weeklyEntries = ['2026-07-17','2026-07-12','2026-07-19','2026-07-15'].map(service_date => ({source:{service_date,service_type_id:'fri'}}));
const weekly = context.groupWorshipSetlistArchiveEntries(weeklyEntries,'date');
assert.equal(weekly.length,2);
assert.equal(weekly[0].key,'2026-07-19');
assert.equal(weekly[1].entries.map(e=>e.source.service_date).join(','),'2026-07-12,2026-07-15,2026-07-17');
const byService = context.groupWorshipSetlistArchiveEntries(weeklyEntries,'service');
assert.equal(byService[0].entries[0].source.service_date,'2026-07-19');
context.state.worshipSetlistArchiveView = 'date';
assert.ok(context.renderWorshipSetlistArchiveEntry(entry).includes('2026-01-16'));
console.log('PASS: Sunday/Saturday boundaries, year boundary, invalid dates, week ordering and card dates');

// A source can contain multiple Sunday services; preserve explicitly labeled songs.
assert.ok(!source.slice(source.indexOf('function worshipSetlistArchiveEntries()'), source.indexOf('function filterWorshipSetlistArchiveEntries')).includes('.filter((candidate) => setlistCandidateBelongsToSource'));
const shared = prepare([song('찬양', '첫 곡', 1), song('찬양', '둘째 곡', 2), song('2부 특송', '2부 곡', 3), song('3부 특송', '3부 곡', 4)], { service_type_id: 'sun_3rd' });
assert.equal(shared.map(row => row.archive_display_label).join('|'), '찬양 1|찬양 2|2부 특송|3부 특송');
console.log('PASS: all-service numbering and shared-source 2nd/3rd service special songs');
assert.equal(context.worshipSetlistArchiveTypeName('sunday-main'), '주일예배');
assert.ok(context.worshipSetlistArchiveTypeOrder('sunday-main') < context.worshipSetlistArchiveTypeOrder('youth'));
const sundayGroups = context.groupWorshipSetlistArchiveEntries([
  {source:{service_type_id:'youth',service_date:'2026-06-21'}},
  {source:{service_type_id:'sunday-main',service_date:'2026-06-21'}},
], 'service');
assert.equal(sundayGroups[0].title, '주일예배');
assert.equal(context.groupWorshipSetlistArchiveEntries(sundayGroups.flatMap(g=>g.entries), 'date')[0].entries[0].source.service_type_id, 'sunday-main');
console.log('PASS: archive Sunday name and priority in service/week views');

const medleyRows=prepare([song("찬양","A + B",1),song("찬양","C + D + E",2),song("찬양","F",3)],{service_type_id:"sun_3rd"});
assert.equal(medleyRows.map(c=>c.archive_display_label).join("|"),"찬양 1–2|찬양 3–5|찬양 6");
assert.equal(context.worshipSetlistArchiveAliases({service_type_id:"sun_3rd",aliases:["온세대 찬양예배","온세대 찬양예배"]}),"온세대 찬양예배");
console.log("PASS: medley numbering ranges and unique service aliases");
