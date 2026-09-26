const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('app.js', 'utf8');
const context = {
  compactSearchValue: value => String(value || '').replace(/\s+/g, ''),
  parseServiceItemMemo: value => value || {},
  serviceMemoElementType: memo => memo.elementType || '',
  isMonthlyCorporatePrayerGroupItem: () => false,
  serviceTitlePersonRawTitleAssignee: () => '',
  presenterTitleAssigneeTitleIsGeneric: () => false,
  looksLikePersonOrGroup: () => false,
};
vm.createContext(context);
for (const name of ['serviceTitlePersonDisallowsTitleInput', 'serviceTitlePersonNeedsTitleInput']) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf('\n}\n', start) + 2;
  vm.runInContext(source.slice(start, end), context);
}

const offering = { label: '봉헌기도', raw_title: '별도 제목', memo: { elementType: 'title_person' } };
assert.equal(context.serviceTitlePersonDisallowsTitleInput(offering, offering.memo), true);
assert.equal(context.serviceTitlePersonNeedsTitleInput(offering, offering.memo), false);

const sermon = { label: '설교', memo: { elementType: 'title_person' } };
assert.equal(context.serviceTitlePersonDisallowsTitleInput(sermon, sermon.memo), false);
assert.equal(context.serviceTitlePersonNeedsTitleInput(sermon, sermon.memo), true);

console.log('PASS offering prayer accepts an assignee without a title input');
