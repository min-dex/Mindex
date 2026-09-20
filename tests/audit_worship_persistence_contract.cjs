// Offline characterization of current gaps, not a claim that persistence is safe.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
function extract(name, async = false) {
  const start = source.indexOf(`${async ? 'async ' : ''}function ${name}(`);
  assert.ok(start >= 0, `Missing function ${name}`);
  const end = source.indexOf('\n}\n', start);
  assert.ok(end > start);
  return source.slice(start, end + 2);
}
function fixture(failDocument) {
  const items = [{id: 'item', raw_title: 'stale edit'}, {id: 'other', raw_title: 'unsaved draft'}];
  const section = {id: 'section', service_id: 'service'};
  const element = {id: 'item', section_id: 'section', title: 'stale edit'};
  const db = {element: {title: 'remote edit'}, document: {revision: 'remote'}};
  const filters = [];
  const state = {
    worshipSections: [section], worshipElements: [element, {id: 'other', section_id: 'section', title: 'committed sibling'}],
    serviceItems: {service: items},
    client: {from(table) {
      return {
        async upsert(rows) {
          if (table === 'mindex_worship_elements') db.element = clone(rows[0]);
          return {error: null};
        },
        update(payload) {
          return {async eq(key, value) {
            filters.push([key, value]);
            if (failDocument) return {error: new Error('document write failed')};
            db.document = clone(payload.source_ref);
            return {error: null, count: 1};
          }};
        },
      };
    }},
  };
  const context = {
    state, structuredClone, getServiceItems: () => items,
    serviceDocumentSnapshotFromRef: () => null,
    worshipAtomicClient: async () => null,
    ensureWorshipServiceRowsLoadedForPersistence: async () => {},
    requireFullServiceSourceRef: async () => {},
    normalizeServiceItemsInCurrentOrder: x => x,
    normalizeServiceItemsForTemplateHierarchy: (_s, x) => x,
    ensureUniqueServiceItemPersistenceIds: x => x,
    isUnmodifiedTemplatePlaceholder: () => false,
    worshipElementTypedStateColumns: async () => ({}),
    buildWorshipPersistenceRows: () => ({sections: [section], elements: [element]}),
    sanitizeWorshipPersistenceRows: () => {}, compactWorshipPersistenceRows: () => {},
    validateWorshipPersistenceRows: () => {}, captureWorshipRecoverySnapshot: () => {},
    withServiceDocumentSnapshot: (_s, all) => ({items: clone(all)}),
    groupWorshipElements: (_sections, elements) => ({service: elements.map(row => ({id: row.id, raw_title: row.title}))}),
    syncSharedSundayContentAfterSave: async () => {},
    refreshPresenterForService: () => {}, serviceHasPendingTextEdits: () => false,
  };
  vm.createContext(context);
  vm.runInContext(extract('saveWorshipServiceElementPatch', true), context);
  return {context, db, filters};
}
(async () => {
  let {context, db} = fixture(true);
  await assert.rejects(context.saveWorshipServiceElementPatch({id: 'service'}, 'item'), /document write failed/);
  assert.equal(db.element.title, 'stale edit');
  assert.equal(db.document.revision, 'remote');
  console.log('REPRODUCED: element committed while document write failed');

  const ok = fixture(false);
  await ok.context.saveWorshipServiceElementPatch({id: 'service'}, 'item');
  assert.deepEqual(ok.filters, [['id', 'service']]);
  assert.equal(ok.db.document.revision, undefined);
  assert.equal(ok.db.document.items.find(item => item.id === 'other').raw_title, 'committed sibling');
  assert.equal(ok.context.state.serviceItems.service.find(item => item.id === 'other').raw_title, 'unsaved draft');
  console.log('REPRODUCED: ID-only document replacement');
  console.log('PASS: single-element snapshot excludes sibling drafts');

  const validation = {
    WORSHIP_DB_ELEMENT_TYPES: new Set(['plain_text']),
    WORSHIP_DB_ELEMENT_INPUT_MODES: new Set(['']),
    normalizeServiceInputMode: x => x || '',
    normalizeServiceAsset: x => x || {}, hasServiceAsset: () => false,
    normalizeWorshipSlotKey: x => x || '',
  };
  vm.createContext(validation);
  vm.runInContext(extract('validateWorshipPersistenceRows'), validation);
  assert.throws(() => validation.validateWorshipPersistenceRows({
    sections: [{id: 'section', service_id: 'different-service', created_at: 'now', updated_at: 'now'}],
    elements: [{id: 'item', section_id: 'unsubmitted-section', element_type: 'plain_text', created_at: 'now', updated_at: 'now'}],
  }, {serviceId: 'service'}), /service ownership mismatch/);
  const validRows = {
    sections: [{id: 'section', service_id: 'service', created_at: 'now', updated_at: 'now'}],
    elements: [{id: 'item', section_id: 'section', element_type: 'plain_text', created_at: 'now', updated_at: 'now'}],
  };
  assert.doesNotThrow(() => validation.validateWorshipPersistenceRows(validRows, {serviceId: 'service'}));
  assert.doesNotThrow(() => validation.validateWorshipPersistenceRows({sections: [], elements: []}, {serviceId: 'service'}));
  assert.throws(() => validation.validateWorshipPersistenceRows({
    ...validRows, elements: [{...validRows.elements[0], section_id: 'foreign-section'}],
  }, {serviceId: 'service'}), /section is not in this save/);
  assert.throws(() => validation.validateWorshipPersistenceRows({
    ...validRows, sections: [...validRows.sections, ...validRows.sections],
  }, {serviceId: 'service'}), /duplicate id/);
  assert.throws(() => validation.validateWorshipPersistenceRows({
    ...validRows, elements: [...validRows.elements, ...validRows.elements],
  }, {serviceId: 'service'}), /duplicate id/);
  console.log('PASS: payload service/section membership and duplicate IDs are checked');
})().catch(error => { console.error(error); process.exitCode = 1; });
