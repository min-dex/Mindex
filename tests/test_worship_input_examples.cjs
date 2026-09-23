const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const context = {
  compactSearchValue: value => String(value || '').replace(/\s+/g, ''),
  serviceItemRequiresSongSelection: () => false,
  isMonthlyCorporatePrayerGroupItem: () => false,
  isAnnouncementTextInputItem: () => false,
  servicePraiseInputMode: (_, memo) => memo?.inputMode,
  isSpecialSongServiceItem: item => item.label.includes('특송'),
  isScriptureBodyServiceItem: () => false,
  presenterServiceTextInputSpec: (_, spec) => spec,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'mindex.worship-input.js'),'utf8'),context);
const app = fs.readFileSync(path.join(root,'app.js'),'utf8');
const start = app.indexOf('function presenterPreparationPlaceholderLinesForItem(');
vm.runInContext(app.slice(start,app.indexOf('\n}\n',start)+2),context);
const fixtures = [
  ['찬양 1','lyrics_db'], ['찬양 2','lyrics_db'], ['특송','manual_praise'],
  ['봉헌특송','lyrics_db'], ['성경봉독','scripture'], ['봉헌찬송','score_db'],
  ['설교','text',{needsTitle:true,needsAssignee:true},'sermon'],
  ['대표기도','text',{needsAssignee:true}], ['축도','text',{needsAssignee:true}],
];
for (const [label,mode,model={},section=''] of fixtures) {
  const lines=context.presenterPreparationPlaceholderLinesForItem({label,_worshipSectionKey:section},{},{mode,model});
  assert.equal(lines.length,1,label);
  const parsed=context.parsePresenterPreparationInput(lines.join('\n'));
  assert.equal(parsed.errors.length,0,lines.join('\n'));
  assert.equal(parsed.entries.length,1,label);
  assert.ok(lines[0].includes(': '),label);
  if(label.includes('특송')) assert.ok(lines[0].endsWith(' / 찬양대'));
  if(label==='축도') assert.ok(lines[0].endsWith('목사'));
}
console.log('PASS examples: songs, manual special, scripture, hymn, sermon, assignee parse correctly');
