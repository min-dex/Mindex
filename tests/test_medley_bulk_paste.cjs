const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const service = {id:'fixture'};
let draft = '';
const toasts = [];
const songs = {
  '곡A': {id:'song-a', title:'곡A'},
  '곡B': {id:'song-b', title:'곡B'},
};
let nextLocalId = 0;
const context = {
  state: {services:[service], serviceItems:{fixture:[]}, dirty:{},
    presenterPreparationApplyingServiceIds:new Set(), presenterPreparationDrafts:{fixture:'draft'}},
  compactSearchValue: value => String(value || '').replace(/\s+/g, ''),
  presenterPreparationDraftForService: () => draft,
  renderServiceList: () => {}, showToast: text => toasts.push(text),
  getServiceItems: () => [],
  parseServiceItemMemo: memo => (memo ? JSON.parse(memo) : {}),
  isSongServiceLabel: label => label.startsWith('찬양'), isSpecialSongServiceItem: () => false,
  serviceItemRequiresSongSelection: () => false,
  servicePraiseInputMode: () => 'lyrics_db', serviceMemoInputMode: () => 'scripture',
  isScriptureBodyServiceItem: () => false,
  normalizeServiceScriptureReferenceList: text => text ? [text] : [],
  parseBibleReference: () => null,
  markServiceItemSharedContentDirty: () => {}, serializeServiceItemMemo: value => JSON.stringify(value),
  projectWorshipServiceItemsFromTemplate: (_, items) => items,
  normalizeServiceItemsInCurrentOrder: items => items,
  refreshPresenterForService: () => {}, updateSaveState: () => {},
  renderCurrentServiceModuleDetail: () => {},
  serviceItemRequiresNewHymnalScoreSong: () => false,
  isNewHymnalScoreSong: () => true,
  defaultServiceSongVersion: () => ({id:'v1'}),
  serviceSongHasMultipleSelectableVersions: () => false,
  createLocalId: () => `local-${nextLocalId++}`,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'mindex.worship-input.js'),'utf8'), context);
context.presenterPreparationTargetLabel = label => label;
context.findPresenterPreparationProjectedItem = (_, label) => {
  const key = label.replace(/\s/g,'');
  return /^찬양\d+$/.test(key) ? {id:key,label:key} : null;
};
context.materializePresenterPreparationItem = (_, items, projected) => {
  items.push({...projected});
  return items.length-1;
};
context.materializeSecondaryConnectedPraiseItem = (_service, items, primaryItem, ordinal) => {
  items.push({id:`${primaryItem.id}:secondary:${ordinal}`, label: primaryItem.label, memo:''});
  return items.length-1;
};
// resolvePresenterPreparationSong is loaded for real from mindex.worship-input.js,
// but it depends on the full song-catalog index; stub it directly so this test
// exercises applyPresenterPreparationInput's segment-splitting logic, not song search.
context.resolvePresenterPreparationSong = (value) => songs[String(value || '').trim()] || null;
context.createBlankPraiseSongForServiceInput = async () => null;
const app = fs.readFileSync(path.join(root,'app.js'),'utf8');
const start = app.indexOf('async function applyPresenterPreparationInput(');
assert.ok(start >= 0);
vm.runInContext(app.slice(start,app.indexOf('\n}\n',start)+2),context);

(async () => {
  // Both segments resolve: two linked items sharing one connectedPraise group.
  draft = '찬양1 곡A + 곡B';
  await context.applyPresenterPreparationInput('fixture');
  const items = context.state.serviceItems.fixture;
  assert.equal(items.length, 2, 'creates primary + one secondary row');
  const [primary, secondary] = items;
  assert.equal(primary.song_id, 'song-a');
  assert.equal(secondary.song_id, 'song-b');
  const primaryMemo = JSON.parse(primary.memo);
  const secondaryMemo = JSON.parse(secondary.memo);
  assert.ok(primaryMemo.connectedPraise.groupId, 'primary has a groupId');
  assert.equal(primaryMemo.connectedPraise.groupId, secondaryMemo.connectedPraise.groupId, 'both rows share one groupId');
  assert.equal(primaryMemo.connectedPraise.role, 'primary');
  assert.equal(secondaryMemo.connectedPraise.role, 'secondary');
  assert.deepEqual(primaryMemo.connectedPraise.itemIds, [primary.id, secondary.id]);
  assert.deepEqual(secondaryMemo.connectedPraise.itemIds, [primary.id, secondary.id]);
  assert.equal(primaryMemo.connectedPraise.primaryItemId, primary.id);
  assert.equal(primaryMemo.connectedPraise.title, '곡A + 곡B', 'combined title is stored for the presenter output marker');

  // One segment fails to resolve: nothing is written for that line (matches the
  // existing all-or-nothing behavior for a single unresolved song).
  context.state.serviceItems.fixture = [];
  context.state.dirty.service = false;
  context.state.presenterPreparationDrafts.fixture = 'draft';
  toasts.length = 0;
  draft = '찬양1 곡A + 없는곡';
  await context.applyPresenterPreparationInput('fixture');
  assert.equal(context.state.serviceItems.fixture.length, 0, 'partial resolution writes nothing');
  assert.equal(context.state.presenterPreparationDrafts.fixture, 'draft', 'draft is preserved on failure');
  assert.equal(toasts.length, 1);
  assert.match(toasts[0], /없는곡.*찾지 못했습니다/);

  console.log('PASS medley bulk-paste: "+"-joined segments link to distinct DB songs sharing one connectedPraise group; partial failure writes nothing');
})().catch(error => { console.error(error); process.exitCode = 1; });
