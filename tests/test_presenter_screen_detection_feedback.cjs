const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const start = source.indexOf("async function requestPresenterScreens(");
const end = source.indexOf("\nfunction observePresenterScreenDetails(", start);
assert.ok(start >= 0 && end > start);

async function run({ error, silent = false, supported = true, permission = "granted" } = {}) {
  const messages = [];
  let calls = 0;
  const context = vm.createContext({
    window: {
      isSecureContext: true,
      ...(supported ? { getScreenDetails: async () => {
        calls++;
        if (error) throw error;
        return { screens: [{ rect: { width: 1920, height: 1080 } }] };
      } } : {}),
    },
    navigator: { permissions: { query: async () => ({ state: permission }) } },
    console: { warn() {} },
    normalizePresenterScreen: screen => screen,
    observePresenterScreenDetails() {},
    applyPresenterScreens() {},
    renderPresenterControlState() {},
    presenterViewServiceId: () => "service",
    showToast: (message, kind) => messages.push({ message, kind }),
  });
  vm.runInContext(source.slice(start, end), context);
  await context.requestPresenterScreens({ silent });
  return { messages, calls };
}

(async () => {
  const denied = await run({ error: { name: "NotAllowedError" } });
  assert.match(denied.messages[0].message, /창 관리/);
  assert.equal(denied.messages[0].kind, "error");
  for (const error of [new Error("disconnected"), { name: "SecurityError" }]) {
    const result = await run({ error });
    assert.match(result.messages[0].message, /감지하지 못했습니다/);
    assert.doesNotMatch(result.messages[0].message, /권한/);
  }
  assert.match((await run({ supported: false })).messages[0].message, /지원하지 않습니다/);
  assert.match((await run()).messages[0].message, /외부 화면이 없습니다/);
  assert.equal((await run({ silent: true, error: new Error("failed") })).messages.length, 0);
  const boot = await run({ silent: true, permission: "prompt" });
  assert.equal(boot.calls, 0);
  assert.equal(boot.messages.length, 0);
  console.log("PASS screen detection feedback and silent startup");
})().catch(error => { console.error(error); process.exitCode = 1; });
