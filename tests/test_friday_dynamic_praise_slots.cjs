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
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const friday = { id: 'friday-20260710', type_id: 'fri' };
assert.equal(context.serviceAllowsDynamicMainPraiseCount(friday), true);
const sixth = context.createDynamicMainPraiseProjectedItem(friday, '찬양6');
assert.equal(sixth.label, '찬양 6');
assert.equal(sixth._worshipSectionKey, 'praise');
assert.equal(sixth._worshipTemplateProjected, true);
assert.equal(context.createDynamicMainPraiseProjectedItem({ id: 'ordinary', type_id: 'wednesday' }, '찬양6'), null);
console.log('PASS Friday bulk input materializes a sixth main-praise slot without changing other services');
