const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const context = { state: { worshipSetlistArchiveView: 'date', worshipSetlistArchiveMonth: '09' } };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, 'mindex.worship-week.js'), 'utf8'), context);
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const start = app.indexOf('function filterWorshipSetlistArchivePeriod(');
vm.runInContext(app.slice(start, app.indexOf('\nfunction ', start + 1)), context);
const services = [{id:'monthly',service_date:'2026-09-04',service_type_id:'monthly',service_alias:'온세대 월삭예배'}];
const entries = context.MindexWorshipWeek.build([], services).flatMap(group => group.entries);
const monthly = entries.find(entry => entry.source.service_date === '2026-09-04');
assert.equal(monthly.source.service_type_id, 'monthly');
assert.equal(monthly.slotName, '월삭예배');
assert.equal(monthly.weeklyStatus, '콘티 미등록');
const filtered = context.filterWorshipSetlistArchivePeriod(entries);
assert(filtered.every(entry => entry.source.service_date.startsWith('2026-09')));
assert(filtered.includes(monthly));
context.state.worshipSetlistArchiveView = 'service';
assert.equal(context.filterWorshipSetlistArchivePeriod(entries), entries);
console.log('PASS monthly identity and calendar-month boundaries');

const boundary = context.MindexWorshipWeek.build([
 {source:{service_date:'2025-12-28',service_type_id:'youth'},candidates:[{raw_title:'실제 콘티'}]},
 {source:{service_date:'2026-01-02',service_type_id:'monthly'},candidates:[]}
], [], {statusStartDate:'2026-01-01'}).flatMap(group=>group.entries);
assert.equal(boundary.filter(entry=>entry.source.service_date.startsWith('2025')).length,1);
assert.equal(boundary.find(entry=>entry.source.service_date==='2025-12-28').candidates.length,1);
assert(!app.includes('data-setlist-period="year"'));
assert(!app.includes('worshipSetlistArchiveYear'));
console.log('PASS month-only navigation, real 2025 setlist retained without generated empty cards');
