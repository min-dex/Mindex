const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const app = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const monitor = fs.readFileSync(path.join(__dirname, "../mindex.monitor.js"), "utf8");

function between(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from);
  return source.slice(from, to);
}

const context = vm.createContext({});
vm.runInContext(between(app, "function isUnavailableRelationError(", "function isUnavailableRpcError("), context);
vm.runInContext(between(app, "function referenceTableErrorMessage(", "async function saveScripture("), context);
vm.runInContext(between(app, "function serviceSaveErrorMessage(", "let worshipConflictReview"), context);
const message = context.referenceTableErrorMessage;
for (const error of [{ code: "42501" }, { message: "permission denied for table links" },
  { details: "new row violates row-level security policy" }]) {
  assert.match(message(error), /접근할 권한이 없습니다/);
  assert.doesNotMatch(message(error), /테이블이 없습니다/);
}
assert.equal(message({ code: "42P01" }), "링크 테이블이 없습니다.");
for (const error of [{ code: "PGRST205" }, { message: "schema cache is stale" }]) {
  assert.match(message(error), /테이블 정보를 확인할 수 없습니다/);
}
assert.equal(message({ message: "Network request failed" }), "Network request failed");
assert.equal(message(null), "링크를 업데이트하지 못했습니다.");

const serviceMessage = context.serviceSaveErrorMessage;
for (const [code, expected] of [
  ["PENDING_REQUEST_REQUIRES_RESOLUTION", /이전 저장 결과.*입력은 유지/],
  ["SERVICE_DELETED", /예배를 찾을 수 없습니다.*입력은 유지/],
  ["DOCUMENT_ELEMENT_OWNERSHIP", /예배 원문과 저장 항목.*입력은 유지/],
  ["DOCUMENT_PARENT_MISMATCH", /예배 원문과 저장 항목.*입력은 유지/],
  ["SONG_VERSION_MISMATCH", /찬양과 선택한 버전.*입력은 유지/],
  ["DUPLICATE_DOCUMENT_RECORD", /예배 항목이 겹쳐.*입력은 유지/],
]) {
  assert.match(serviceMessage({ message: code }), expected);
  assert.doesNotMatch(serviceMessage({ message: code }), new RegExp(`^${code}$`));
}
assert.equal(serviceMessage({ message: "Network request failed" }), "Network request failed");

for (const staleEnglish of ["Could not load calendar.", "File read failed.",
  "Image is too large for local storage.", "Background update failed.",
  "No background to download.", "File downloaded.", "Copy failed.",
  "Lyrics are required for XML.", "Lyrics are required for FreeShow .show."]) {
  assert.ok(!app.includes(`\"${staleEnglish}\"`), `stale English feedback: ${staleEnglish}`);
}
for (const koreanFeedback of ["교회력을 불러오지 못했습니다.", "파일을 내려받았습니다.", "복사하지 못했습니다."]) {
  assert.ok(app.includes(koreanFeedback), `missing Korean feedback: ${koreanFeedback}`);
}

const notices = [];
let rendered = 0;
const popup = vm.createContext({
  window: { open: () => null },
  state: { presenter: {} },
  browserUrl: new URL("https://example.test/?output=presenter"), features: "", serviceId: "service",
  showToast: text => notices.push(text),
  renderPresenterControlState: () => rendered++,
});
vm.runInContext(`(function () { ${between(app,
  '  const outputWindow = window.open(browserUrl.toString(), "mindexPresenterOutput", features);',
  '  state.presenter.outputWindow = outputWindow;')} })()`, popup);
assert.match(notices[0], /출력 창을 열지 못했습니다/);
assert.doesNotMatch(notices[0], /차단했습니다/);
assert.equal(rendered, 1);
assert.ok(popup.state.presenter.outputBlockedAt > 0);
assert.equal(popup.state.presenter.outputPendingAt, 0);

const remote = vm.createContext({
  state: { client: null }, navigator: { onLine: true },
  AbortController, setTimeout, clearTimeout, requests: new Map(),
});
vm.runInContext(between(monitor, "  async function rpc(", "  async function leave("), remote);
(async () => {
  await assert.rejects(remote.rpc("test", {}), /DB 클라이언트가 준비되지 않았습니다/);
  remote.state.client = { rpc: () => ({ abortSignal: async () => ({ data: "ok" }) }) };
  assert.equal(await remote.rpc("test", {}), "ok");
  remote.navigator.onLine = false;
  await assert.rejects(remote.rpc("test", {}), /네트워크 연결이 끊겼습니다/);
  assert.equal(remote.requests.size, 0);
  console.log("PASS link errors, popup failure, and remote initialization feedback");
})().catch(error => { console.error(error); process.exitCode = 1; });
