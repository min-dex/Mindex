const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const c = {
 state:{worshipSetlistArchive:{loaded:true,live:{services:[]}},worshipSetlistArchiveView:'date',worshipSetlistArchiveYear:'2025'},
 refs:{detailPane:{}},SERVICE_SETLIST_ARCHIVE_PANEL_TITLE:'역대 콘티',escapeHtml:x=>x,finishDetailRender(){},
 filterWorshipSetlistArchiveEntries:x=>x,filterWorshipSetlistArchivePeriod:x=>x,renderWorshipSetlistArchiveGroups:()=>'',
 worshipSetlistArchiveEntries:()=>[
  {source:{id:'adbda7ef-bea0-5751-857d-68d3adec7ed2',service_date:'2025-12-28',service_type_id:'youth'},candidates:[]},
  {source:{service_date:'2026-01-02',service_type_id:'monthly'},candidates:[]}
 ],
 renderWorshipSetlistArchiveNavigation(entries){c.years=[...new Set(entries.map(e=>e.source.service_date.slice(0,4)))];return '';}
};
c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(root,'mindex.worship-week.js'),'utf8'),c);
const s=fs.readFileSync(path.join(root,'app.js'),'utf8'),start=s.indexOf('function renderServiceSetlistArchiveDetail(');
vm.runInContext(s.slice(start,s.indexOf('\nfunction ',start+1)),c);
c.renderServiceSetlistArchiveDetail();
assert.deepEqual(c.years,['2026']);
assert.equal(c.state.worshipSetlistArchiveYear,'');
assert.equal(c.worshipSetlistArchiveEntries()[0].source.service_date,'2025-12-28');
console.log('PASS actual 2025 youth record excluded from year options, source retained');
