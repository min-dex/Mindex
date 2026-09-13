const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = {
  compactSearchValue: x => String(x || '').replace(/\s/g, ''),
  cleanPresenterAssignee: x => String(x || '').trim(),
  cleanList: x => x.filter(Boolean),
  isCreedPresenterItem: () => false,
  isPresenterScriptureReadingSource: () => false,
  serviceItemDefaultAssignee: () => '',
  serviceWorshipLeaderLabel: () => { throw Error('Output must not resolve worship leader'); },
  PRESENTER_ELEMENT_TYPES: { TITLE_ASSIGNEE: 'title-assignee' },
};
vm.createContext(context);
for (const [file, name] of [['mindex.presenter.js', 'presenterTitleAssigneePerson'], ['app.js', 'presenterSlideWithServiceAssigneeFallback']]) {
  const source = fs.readFileSync(file, 'utf8');
  const start = source.indexOf(`function ${name}(`);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}
for (const label of ['교회소식', '예배의 부름', '사죄의 선언', '묵도', '봉헌기도']) {
  assert.equal(context.presenterTitleAssigneePerson({}, label, '', label, {}), '');
  const result = context.presenterSlideWithServiceAssigneeFallback({ title: label, elementType: 'title-assignee', assignee: '', sectionAssignee: '' }, {});
  assert.equal(result.assignee, '');
}
assert.equal(context.presenterTitleAssigneePerson({ assignee: '김석범 목사' }, '봉헌기도', '', '봉헌기도', {}), '김석범 목사');
assert.equal(context.presenterSlideWithServiceAssigneeFallback({ title: '대표기도', elementType: 'title-assignee', assignee: '이재희 청년' }, {}).assignee, '이재희 청년');
console.log('PASS output omits automatic worship leader and retains order assignees');
