const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app.js', 'utf8');
const start = source.indexOf('function applyServiceSongSelectionWithService(');
const code = source.slice(start, source.indexOf('\n}\n', start) + 2);
let catalogSong = null;
let mode = 'lyrics_db';
const c = {
  state: {services: [], selectedServiceId: ''},
  isSongServiceLabel: () => true, isSpecialSongServiceItem: () => false,
  parseServiceItemMemo: () => ({}), servicePraiseInputMode: () => mode,
  serviceItemLinkedSong: () => catalogSong,
  resolvePresenterPreparationSong: () => null, findServicePraiseSong: () => null,
  selectedServiceForEditor: () => null,
  linkServiceItemToPraiseSong: (item, song) => { item.song_id = song.id; },
};
vm.createContext(c); vm.runInContext(code, c);
const item = {label: '찬양 5', raw_title: '', song_id: 'saved-song', version_id: 'saved-version', song_version_id: 'saved-version'};
const before = JSON.stringify(item);
c.applyServiceSongSelectionWithService(item);
assert.equal(JSON.stringify(item), before, 'Pending/failed catalog hydration must preserve saved IDs');
catalogSong = {id: 'saved-song'};
c.applyServiceSongSelectionWithService(item);
assert.equal(JSON.stringify(item), before, 'Hydration resumes with the saved selection');
mode = 'manual_praise';
c.applyServiceSongSelectionWithService(item);
assert.equal(item.song_id, null, 'Explicit manual mode still unlinks');
assert.equal(item.version_id, null);
const presenter = vm.createContext({document: {}});
vm.runInContext(fs.readFileSync('mindex.presenter.js', 'utf8'), presenter);
for (const [input, expected] of [['찬양 6–7','찬양'],['찬양 3-5','찬양'],['찬양 1 ~ 2','찬양'],['기도 3·4','기도'],['찬양 51–52','찬양'],['요한복음 6:11','요한복음 6:11']]) assert.equal(presenter.presenterOrderDisplayLabel(input), expected);
console.log('PASS saved praise links survive catalog hydration; medley ranges use circled labels');

assert.ok(!source.includes("presenterOrderDisplayLabel("), "Controller labels must retain plain order numbers");
