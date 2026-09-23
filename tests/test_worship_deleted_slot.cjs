const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app.js', 'utf8');
const context = vm.createContext({ console: {warn() {}}, normalizeWorshipSlotKey: v => String(v || '').trim(),
 normalizeServiceAsset: v => v || {}, hasServiceAsset: v => Boolean(v.url) });
for (const name of ['worshipElementPersistenceSlotKey','worshipElementHasPersistedContent','shouldPreserveExistingWorshipElement','preserveExistingWorshipContentRows']) {
 const start = source.indexOf(`function ${name}(`);
 vm.runInContext(source.slice(start, source.indexOf('\n}\n',start)+2), context);
}
const sections = [{id:'sermon'}];
const old = {id:'stored',section_id:'sermon',title:'히브리서 7:20–28',source_ref:{slotKey:'sermon.citation.1'}};
const other = {id:'other',section_id:'sermon',title:'설교',source_ref:{slotKey:'sermon.title'}};
for (const flag of ['templateSuppressed','template_suppressed']) {
 const marker={id:'projected-deletion',section_id:'sermon',source_ref:{slotKey:'sermon.citation.1'},config:{[flag]:true}};
 const rows={sections:[...sections],elements:[marker]};
 context.preserveExistingWorshipContentRows(rows,sections,[old,other]);
 assert.deepEqual(rows.elements.map(e=>e.id),['projected-deletion','other']);
 assert.equal(old.title,'히브리서 7:20–28');
}
const omitted={sections:[],elements:[]};
context.preserveExistingWorshipContentRows(omitted,sections,[old]);
assert.equal(omitted.elements[0],old,'Accidentally omitted content remains protected');
const active={sections:[...sections],elements:[{...old,id:'another-active'}]};
context.preserveExistingWorshipContentRows(active,sections,[old]);
assert.equal(active.elements.length,2,'Active collisions must still reach validation, not silently discard content');
console.log('PASS explicit slot deletion wins over preservation; unrelated and omitted content remain protected');
