const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const lifetime = source.match(/const PRESENTER_MEDIA_CACHE_CONTROL = "(\d+)";/);
assert.ok(lifetime, "shared upload cache lifetime exists");
assert.equal(Number(lifetime[1]), 30 * 24 * 60 * 60);
const uploads = [...source.matchAll(/\.upload\(path, file, \{([^}]+)\}\)/g)];
assert.equal(uploads.length, 2, "reference media and audio upload paths covered");
for (const [, options] of uploads) {
  assert.match(options, /cacheControl: PRESENTER_MEDIA_CACHE_CONTROL/);
  assert.match(options, /upsert: false/);
}

const uploadPath = source.match(/function presenterReferenceMediaUploadPath\([^]*?\n\}/);
assert.ok(uploadPath);
let now = 1000;
const context = vm.createContext({ Date: { now: () => now } });
vm.runInContext(uploadPath[0], context);
const first = context.presenterReferenceMediaUploadPath("service", { id: "item" }, { name: "photo.png" });
now += 1;
const replacement = context.presenterReferenceMediaUploadPath("service", { id: "item" }, { name: "photo.png" });
assert.notEqual(first, replacement, "replacement gets a fresh URL");
assert.equal(first, "services/service/item/1000-photo.png");
console.log("PASS media cache lifetime and non-overwriting upload paths");
