const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const service = {id:'fixture'};
let draft = '';
let writes = 0;
const toasts = [];
const context = {
  state: {services:[service], serviceItems:{fixture:[]}, dirty:{},
    presenterPreparationApplyingServiceIds:new Set(), presenterPreparationDrafts:{fixture:'draft'}},
  compactSearchValue: value => String(value || '').replace(/\s+/g, ''),
  presenterPreparationDraftForService: () => draft,
  renderServiceList: () => {}, showToast: text => toasts.push(text),
  getServiceItems: () => [],
  parseServiceItemMemo: () => ({}),
  isSongServiceLabel: label => label.startsWith('찬양'), isSpecialSongServiceItem: () => false,
  serviceItemRequiresSongSelection: () => false,
  servicePraiseInputMode: () => 'manual_praise', serviceMemoInputMode: () => 'scripture',
  isScriptureBodyServiceItem: item => item.label === '성경봉독',
  normalizeServiceScriptureReferenceList: text => text ? [text] : [],
  parseBibleReference: text => text === '요 3:16' ? {} : null,
  markServiceItemSharedContentDirty: () => {}, serializeServiceItemMemo: JSON.stringify,
  projectWorshipServiceItemsFromTemplate: (_, items) => items,
  normalizeServiceItemsInCurrentOrder: items => items,
  refreshPresenterForService: () => {}, updateSaveState: () => {},
  renderCurrentServiceModuleDetail: () => {},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'mindex.worship-input.js'),'utf8'), context);
context.presenterPreparationTargetLabel = label => label;
context.findPresenterPreparationProjectedItem = (_, label) => {
  const key = label.replace(/\s/g,'');
  return /^(찬양\d+|성경봉독)$/.test(key) ? {id:key,label:key} : null;
};
context.materializePresenterPreparationItem = (_, items, projected) => {
  writes++;
  items.push({...projected});
  return items.length-1;
};
const app = fs.readFileSync(path.join(root,'app.js'),'utf8');
const start = app.indexOf('async function applyPresenterPreparationInput(');
assert.ok(start >= 0);
vm.runInContext(app.slice(start,app.indexOf('\n}\n',start)+2),context);
(async () => {
  for (const invalid of ['찬양1 새 곡\n성경봉독 잘못된 주소', '찬양1 새 곡\n없는항목: 내용', '찬양1 새 곡\n인용구절 오류']) {
    draft = invalid;
    await context.applyPresenterPreparationInput('fixture');
    assert.equal(writes, 0, invalid);
    assert.equal(context.state.serviceItems.fixture.length, 0);
    assert.equal(context.state.presenterPreparationDrafts.fixture, 'draft');
    assert.equal(context.state.presenterPreparationApplyingServiceIds.size, 0);
  }
  assert.equal(toasts.length, 3);
  draft = '9월 13일 주일예배\n찬양1\n새 곡\n찬양2 두 번째 곡';
  await context.applyPresenterPreparationInput('fixture');
  assert.equal(writes, 2);
  assert.deepEqual(context.state.serviceItems.fixture.map(item=>item.raw_title), ['새 곡','두 번째 곡']);
  assert.equal(context.state.dirty.service, true);
  assert.equal(context.state.presenterPreparationDrafts.fixture, undefined);
  console.log('PASS apply: invalid target/scripture/citation blocked before materialization; valid multiline applied');
})().catch(error => { console.error(error); process.exitCode = 1; });
