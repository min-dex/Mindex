const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('app.js', 'utf8');
const start = source.indexOf('function serviceAllowsDynamicMainPraiseCount(');
const end = source.indexOf('\nfunction servicePraiseAssignee(', start);
assert.ok(start >= 0 && end > start, 'dynamic main-praise helpers found');

const context = {
  isAllGenerationsWorshipService: (service) => service.allGenerations === true,
  worshipAppServiceTypeId: (typeId) => ({ fri: 'friday' }[typeId] || typeId),
  compactSearchValue: (value) => String(value || '').replace(/\s+/g, ''),
  servicePrepEditorItems: () => [{
    id: 'praise-1', label: '찬양 1', service_id: 'friday-20260710',
    _worshipSectionKey: 'praise', _worshipSectionTitle: '찬양', _worshipElementOrder: 10,
  }],
  isMainPraiseServiceItem: (item) => item._worshipSectionKey === 'praise',
  normalizeServiceItem: (item) => item,
  TEMPLATE_PROJECTED_SERVICE_TYPES: new Set(['friday', 'wednesday']),
  state: { templateElementSuppressions: new Map() },
  parseServiceItemMemo: () => ({}),
  serializeServiceItemMemo: JSON.stringify,
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const friday = { id: 'friday-20260710', type_id: 'fri' };
assert.equal(context.serviceAllowsDynamicMainPraiseCount(friday), true);
const sixth = context.createDynamicMainPraiseProjectedItem(friday, '찬양6');
assert.equal(sixth.label, '찬양 6');
assert.equal(sixth._worshipSectionKey, 'praise');
assert.equal(sixth._worshipTemplateProjected, true);
const wednesday = { id: 'wed-20260715', type_id: 'wednesday' };
assert.equal(context.serviceAllowsDynamicMainPraiseCount(wednesday), true);
assert.equal(context.createDynamicMainPraiseProjectedItem(wednesday, '찬양6').label, '찬양 6');
const original = [1, 2, 3, 4].map((ordinal) => ({
  id: `praise-${ordinal}`, label: `찬양 ${ordinal}`, _worshipSectionKey: 'praise', memo: '',
}));
const reduced = context.reconcileMainPraiseItemsFromPreparationEntries(wednesday, original, [
  { label: '찬양1' }, { label: '찬양2' },
]);
assert.deepEqual(reduced.map((item) => item.label), ['찬양 1', '찬양 2']);
assert.equal(context.state.templateElementSuppressions.size, 2);
const appended = context.reconcileMainPraiseItemsFromPreparationEntries(wednesday, original, [{ label: '찬양6' }]);
assert.equal(appended.length, 4, 'a partial append must not remove earlier songs');
console.log('PASS numbered main praise expands or shrinks across service types without deleting partial edits');
