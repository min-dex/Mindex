const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const escapeHtml = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const context = { escapeHtml, compactSearchValue: value => String(value || '').replace(/\s+/g, '').toLowerCase() };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../mindex.worship-input.js'), 'utf8'), context);
const j = value => JSON.parse(JSON.stringify(value));

// Form: labels only, taken from the per-service example lines.
const examples = '찬양1: 주 은혜임을\n설교: 은혜로 사는 삶 / 홍길동 목사\n설교 본문: 히브리서 10:38-39\n인용구절: 히브리서 10:38-39\n축도: 홍길동 목사';
assert.equal(context.presenterPreparationFormFromExamples(examples), '찬양1: \n설교: \n설교 본문: \n인용구절: \n축도: ');
assert.equal(context.presenterPreparationFormFromExamples('입력할 항목이 없습니다'), '');
assert.equal(context.presenterPreparationFormFromExamples(''), '');

// Blank labels are skipped only when asked to; the default stays strict.
const draft = '찬양1: 주 은혜임을\n설교: \n설교 본문: 히브리서 10:38-39\n인용구절: \n축도: ';
const strict = j(context.parsePresenterPreparationInput(draft));
assert.ok(strict.errors.length, 'default parse still rejects a blank label');
const lenient = j(context.parsePresenterPreparationInput(draft, { skipEmptyLabels: true }));
assert.deepEqual(lenient.errors, []);
assert.deepEqual(lenient.entries.map(entry => entry.key), ['찬양1', '설교본문']);
assert.equal(lenient.skipped.length, 3);
// "label:" followed by its content on the next line keeps working.
const nextLine = j(context.parsePresenterPreparationInput('설교:\n은혜로 사는 삶\n축도: ', { skipEmptyLabels: true }));
assert.deepEqual(nextLine.errors, []);
assert.deepEqual(nextLine.entries.map(entry => [entry.key, entry.content]), [['설교', '은혜로 사는 삶']]);
assert.equal(nextLine.skipped.length, 1);
// A bare label without a colon is still an error (existing rule).
assert.ok(j(context.parsePresenterPreparationInput('특송', { skipEmptyLabels: true })).errors.length);
// Nothing filled: no entries, only skipped.
const empty = j(context.parsePresenterPreparationInput('설교: \n축도: ', { skipEmptyLabels: true }));
assert.deepEqual([empty.errors, empty.entries.length, empty.skipped.length], [[], 0, 2]);

// A blank label the parser does not know (e.g. 광고) is skipped, never turned into a song title.
const unknownBlank = j(context.parsePresenterPreparationInput('광고: \n특송: ', { skipEmptyLabels: true }));
assert.deepEqual([unknownBlank.errors, unknownBlank.entries.length, unknownBlank.skipped.length], [[], 0, 2]);
const mixed = j(context.parsePresenterPreparationInput('찬양1: 주 은혜임을\n광고: \n광고2: 안내\n특송: ', { skipEmptyLabels: true }));
assert.ok(!mixed.entries.some(entry => /광고:/.test(entry.content)), 'blank label leaked into a song');
assert.deepEqual(mixed.errors, []);
assert.equal(mixed.skipped.length >= 2, true);
// A blank known label followed by a blank unknown label: the second line is not its content.
const chained = j(context.parsePresenterPreparationInput('봉헌기도: \n광고: \n축도: 홍길동 목사', { skipEmptyLabels: true }));
assert.deepEqual(chained.errors, []);
assert.deepEqual(chained.entries.map(entry => [entry.key, entry.content]), [['축도', '홍길동 목사']]);
// Default mode is untouched by the new branch.
assert.equal(j(context.parsePresenterPreparationInput('광고:')).entries[0]?.content, '광고:');

console.log('PASS worship input form: label parsing and blank-label skipping');
