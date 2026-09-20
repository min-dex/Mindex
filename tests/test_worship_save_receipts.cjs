const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
// Run the browser bundle with a stubbed fetch; no live database requests.
const sdk = {fetch, Headers, Request, Response, URL, URLSearchParams, AbortController,
  TextEncoder, TextDecoder, WebSocket, setTimeout, clearTimeout, console};
vm.createContext(sdk);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../vendor/supabase-js.min.js'), 'utf8'), sdk);
const {createClient} = sdk.supabase;
const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
const context = {
  MINDEX_SERVICE_DOCUMENT_KIND: 'worship-service',
  MINDEX_SERVICE_DOCUMENT_VERSION: 1,
  MINDEX_SERVICE_DOCUMENT_HISTORY_LIMIT: 3,
  MINDEX_SERVICE_DOCUMENT_HISTORY_MAX_BYTES: 450000,
  cleanList: x => x.filter(Boolean), limitServiceDocumentText: x => x,
  normalizeServiceAsset: x => x || {},
  hasServiceAsset: x => Boolean(x.url),
  normalizeWorshipSlotKey: x => x || '',
  normalizeServiceItemReferenceSpacing: x => x,
  compactSearchValue: x => x,
  // Same as app.js: length plus a 32-bit hash, so signatures stay short like in production.
  compactTextSignature: (value = '') => {
    const text = String(value || '');
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
    return `${text.length}:${hash >>> 0}`;
  },
};
vm.createContext(context);
for (const name of ['serviceDocumentHistoryWithPrevious', 'compactServiceDocumentHistoryEntry',
  'serviceDocumentHistoryContentSignature', 'serviceSourceHistoryMeta',
  'serviceDocumentHistoryEntryKey', 'trimServiceDocumentHistory',
  'normalizeServiceDocumentSnapshot', 'normalizeServiceDocumentSourceRecords',
  'normalizeServiceDocumentSlides', 'normalizeServiceDocumentExceptions',
  'serviceDocumentRecordKey', 'serviceDocumentSlideKey'].filter(name => source.includes('function ' + name + '('))) {
  const start = source.indexOf('function ' + name + '(');
  assert.ok(start >= 0);
  vm.runInContext(source.slice(start, source.indexOf('\n}\n', start) + 2), context);
}
const original = {
  version: 1, updatedAt: 'before', sourceSignature: 'same-text', slideSignature: 'same-slides',
  sourceText: 'Original', sourceRecords: [{elementId: 'a', linkedSource: {songVersionId: 'v1'}}],
  slides: [{id: 's1', layout: 'title'}], exceptions: [{reason: 'Original exception'}],
};
for (const change of [
  {sourceRecords: [{elementId: 'a', linkedSource: {songVersionId: 'v2'}}]},
  {exceptions: [{reason: 'Changed exception'}]},
  {slides: [{id: 's1', layout: 'lyrics'}]},
  {sourceText: 'Different text despite an unchanged signature'},
]) {
  const result = context.serviceDocumentHistoryWithPrevious(original, [], {...original, ...change});
  assert.equal(result.length, 1);
  assert.equal(JSON.stringify(result[0]), JSON.stringify(context.compactServiceDocumentHistoryEntry(original)));
}
assert.equal(context.serviceDocumentHistoryWithPrevious(original, [], {...original, updatedAt: 'later'}).length, 0);
assert.equal(context.serviceDocumentHistoryWithPrevious(original, [original], {...original, sourceText: 'Next'}).length, 1);
assert.equal(context.trimServiceDocumentHistory([original, original, original, original]).length, 3);
console.log('PASS history preserves recoverable changes, deduplicates timestamps and stays bounded');

// Slim history entries: only text, counts and a content signature are stored.
const big = {...original, slides: Array.from({length: 40}, (_, i) => ({id: 's' + i, layout: 'lyrics', text: 'x'.repeat(200)})),
  sourceRecords: Array.from({length: 5}, (_, i) => ({elementId: 'r' + i}))};
const slim = context.compactServiceDocumentHistoryEntry(big);
assert.ok(!('slides' in slim) && !('sourceRecords' in slim) && !('exceptions' in slim), 'arrays are not stored');
assert.equal(slim.slideCount, 40);
assert.equal(slim.sourceRecordCount, 5);
assert.equal(slim.sourceText, 'Original');
assert.ok(slim.contentSignature, 'content signature kept');
assert.ok(JSON.stringify(slim).length * 20 < JSON.stringify(big).length, 'entry is much smaller than the document');
// The current document snapshot is unchanged: no slim-only fields leak into it.
const snapshot = context.normalizeServiceDocumentSnapshot(big);
assert.ok(snapshot.slides.length === 40 && !('slideCount' in snapshot) && !('contentSignature' in snapshot), 'document keeps its arrays only');
// Normalizing a stored slim entry keeps counts and the signature.
const roundTrip = context.normalizeServiceDocumentSnapshot(JSON.parse(JSON.stringify(slim)));
assert.equal(roundTrip.slideCount, 40);
assert.equal(roundTrip.contentSignature, slim.contentSignature);
assert.equal(JSON.stringify(context.compactServiceDocumentHistoryEntry(roundTrip)), JSON.stringify(slim), 'slimming is idempotent');
// De-duplication still works between a slim history entry and the full current document.
const changed = {...big, sourceText: 'Changed'};
assert.equal(context.serviceDocumentHistoryWithPrevious(changed, [slim], big).length, 1, 'entry equal to the current document is dropped');
assert.equal(context.serviceDocumentHistoryWithPrevious(changed, [slim], {...big, sourceText: 'Third'}).length, 2, 'distinct entries are both kept');
assert.equal(context.serviceDocumentHistoryWithPrevious(big, [slim], {...big, sourceText: 'Third'}).length, 1, 'identical previous and history entry collapse');
// Real content changes with identical signatures are still recorded against a slim entry.
const sameSignatureOtherSlides = {...big, slides: [{id: 'other'}]};
assert.equal(context.serviceDocumentHistoryWithPrevious(big, [], sameSignatureOtherSlides).length, 1);
assert.notEqual(context.compactServiceDocumentHistoryEntry(big).contentSignature, context.compactServiceDocumentHistoryEntry(sameSignatureOtherSlides).contentSignature);
// A legacy entry (arrays) is rewritten slim the next time the history is rebuilt.
const rebuilt = context.serviceDocumentHistoryWithPrevious(changed, [big], {...big, sourceText: 'Fourth'});
assert.ok(rebuilt.every((entry) => !('slides' in entry) && !('sourceRecords' in entry)), 'rebuilt history is slim');
// An entry slimmed by the data rewrite (counts, no content signature) is still keyed and shown.
const rewritten = {kind: 'worship-service', version: 1, updatedAt: 'old', sourceSignature: 'a', slideSignature: 'b', sourceText: 'Old text', slideCount: 7, sourceRecordCount: 2};
const kept = context.serviceDocumentHistoryWithPrevious(original, [rewritten], {...original, sourceText: 'Next'});
assert.equal(kept.length, 2);
assert.equal(kept[1].slideCount, 7);
assert.equal(context.serviceDocumentHistoryWithPrevious(original, [rewritten, rewritten], {...original, sourceText: 'Next'}).length, 2, 'duplicate rewritten entries collapse');
// The list meta shows counts for slim, rewritten and legacy entries.
assert.equal(context.serviceSourceHistoryMeta(slim), '항목 5 · 슬라이드 40');
assert.equal(context.serviceSourceHistoryMeta(rewritten), '항목 2 · 슬라이드 7');
assert.equal(context.serviceSourceHistoryMeta(big), '항목 5 · 슬라이드 40');
console.log('PASS history entries are stored slim, keep restorable text and counts, and still deduplicate');
(async () => {
  for (const count of [0, 1, null]) {
    const client = createClient('https://example.invalid', 'offline-test-key', {
      auth: {persistSession: false, autoRefreshToken: false},
      global: {fetch: async (_url, options) => {
        assert.equal(options.method, 'PATCH');
        assert.match(new Headers(options.headers).get('Prefer'), /count=exact/);
        return new Response(null, {status: 204,
          headers: count === null ? {} : {'content-range': '*/' + count}});
      }},
    });
    const result = await client.from('mindex_worship_services')
      .update({title: 'Offline fixture'}, {count: 'exact'}).eq('id', 'fixture');
    assert.equal(result.error, null);
    assert.equal(result.count, count);
  }
  console.log('PASS bundled Supabase SDK sends exact-count preference and parses receipts');
})().catch(error => { console.error(error); process.exitCode = 1; });
