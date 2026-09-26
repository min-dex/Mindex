const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "mindex.db-refresh.js"), "utf8");
const serviceSnapshot = source.match(/if \(\["home", "service", "presenter"\]\.includes\(module\)\) \{([\s\S]*?)\n    \}/);

assert.ok(serviceSnapshot, "service refresh snapshot branch should exist");
assert.match(serviceSnapshot[1], /await fetchWorshipServiceListRows\(\)/,
  "manual refresh should use the compact service-list loader");
assert.doesNotMatch(serviceSnapshot[1], /state\.serviceAliasSupported \? WORSHIP_SERVICE_LIST_SELECT/,
  "manual refresh must not build its own full service-list request");

console.log("DB refresh service-list path is compact");
