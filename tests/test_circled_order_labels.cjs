const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const context = vm.createContext({document: {}});
vm.runInContext(fs.readFileSync(path.join(__dirname, "../mindex.presenter.js"), "utf8"), context);
const format = context.presenterOrderDisplayLabel;
for (const [input, output] of [
  ["찬양 1", "찬양"], ["찬양2", "찬양"],
  ["공동기도 3·4", "공동기도"], ["기도 20", "기도"],
  ["기도 21", "기도"], ["기도 36", "기도"], ["기도 50", "기도"],
  ["기도 51", "기도"], ["찬양 ①", "찬양"],
  ["찬양 6–7", "찬양"], ["공동기도 ③·④", "공동기도"],
  ["찬양", "찬양"], ["기도 ㊿", "기도"],
  ["요한복음 6:11", "요한복음 6:11"], ["새찬송가 436장", "새찬송가 436장"],
  ["436 나 이제 주님의 새 생명 얻은 몸", "436 나 이제 주님의 새 생명 얻은 몸"],
]) assert.equal(format(input), output);
context.escapeHtml = context.escapeAttr = String;
context.presenterLineCharEstimate = (text) => text.length;
context.presenterTitleContentLines = () => [];
context.renderPresenterSongText = String;
const slide = {fullscreenSongTitle: true, title: "Song 2",
  songTitleContent: {orderTitle: "찬양 2", detail: "Original 3", detailKind: "original"}};
const before = JSON.stringify(slide);
const html = context.renderPresenterTitleContentSlide(slide);
assert.match(html, />찬양</);
assert.doesNotMatch(html, /찬양 [②2]/);
assert.match(html, /Song 2/);
assert.match(html, /Original 3/);
assert.equal(JSON.stringify(slide), before);
console.log("PASS output order numbers hidden; content and source unchanged");
