(() => {
  "use strict";
  if (isPresenterOutputRoute()) return;
  const trigger = document.getElementById("monitorPanelBtn");
  if (!trigger) return;
  const modules = { home: "홈", presenter: "예배", service: "예배", scripture: "말씀", praise: "찬양", calendar: "교회력", references: "참고자료" };
  const eventNames = { open: "접속", view: "화면 이동", service: "예배 선택", edit: "입력 편집", save_start: "예배 저장 시작", save_ok: "예배 저장 완료", save_failed: "예배 저장 흐름 오류", output_on: "송출창 응답 시작", output_off: "송출창 응답 끊김" };
  const events = [];
  let remoteRows = [];
  let reporter = null, admin = null, uploading = false, reading = false, previous = null;
  let lastEdit = 0, loginSerial = 0, viewSerial = 0, shareSerial = 0, retryAt = 0, failures = 0;
  let enabled = false, name = "";
  try { enabled = localStorage.getItem("mindex.monitor.share") === "true"; name = localStorage.getItem("mindex.monitor.name") || ""; } catch {}
  const ua = navigator.userAgent;
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac/.test(ua) ? "macOS" : "Other";
  const browser = /Whale\//.test(ua) ? "Whale" : /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const version = document.querySelector('script[src*="/app.js?"]')?.src.split("?v=")[1] || "unknown";
  const panel = document.createElement("dialog");
  panel.className = "monitor-panel"; panel.setAttribute("aria-labelledby", "monitorTitle");
  panel.innerHTML = `<header><h2 id="monitorTitle">제어판</h2><span>읽기 전용</span><button class="icon-btn" data-close title="닫기" aria-label="닫기"><i data-lucide="x"></i></button></header>
    <div class="monitor-toolbar"><label for="monitorName">기기 이름</label><input id="monitorName" maxlength="60" autocomplete="off"></div>
    <div class="monitor-toolbar"><label><input type="checkbox" data-share>이 기기 상태 공유</label><button class="icon-btn" data-refresh title="새로고침" aria-label="새로고침"><i data-lucide="refresh-cw"></i></button><button class="btn secondary" data-lock hidden>잠금</button></div>
    <p class="monitor-message" role="status"></p><h3>현재 기기</h3><div data-local></div>
    <h3>접속 기기</h3><form><label for="monitorPassword">관리자 비밀번호</label><input id="monitorPassword" type="password" autocomplete="current-password" required maxlength="128"><button class="btn secondary" type="submit">확인</button></form><div data-devices></div>`;
  document.body.append(panel);
  const $ = (selector) => panel.querySelector(selector);
  $("[data-share]").checked = enabled; $("#monitorName").value = name || `${os} ${browser}`;
  function message(text) { $(".monitor-message").textContent = text; }
  function record(kind) {
    if (!enabled || !eventNames[kind]) return;
    events.push({ kind, at: new Date().toISOString() });
    if (events.length > 20) events.shift();
  }
  function snapshot() {
    const p = state.presenter;
    const service = state.services.find((s) => s.id === state.selectedServiceId);
    const output = Boolean(p.outputConnectedAt && Date.now() - p.outputConnectedAt < 5000);
    const current = { module: state.module, serviceId: service?.id || "", output };
    if (previous) {
      if (previous.module !== current.module) record("view");
      if (previous.serviceId !== current.serviceId) record("service");
      if (previous.output !== output) record(output ? "output_on" : "output_off");
    }
    previous = current;
    return { name: $("#monitorName").value.trim().slice(0, 60), os, browser, version,
      module: String(state.module || ""), serviceId: service?.id || "", serviceDate: service?.date || "", serviceType: service?.type_id || "", output,
      outputServiceId: p.serviceId || "", slide: output ? Number(p.index) + 1 : 0, count: output ? p.slides?.length || 0 : 0,
      dirty: Boolean(state.dirty?.service), saving: Boolean(state.saving),
      video: output && p.videoHealth && Date.now() - p.videoHealth.receivedAt < 5000 ? p.videoHealth.status : "",
      events: events.map((event) => ({ ...event })) };
  }
  function serviceName(id, date = "", typeId = "") {
    const service = state.services.find((s) => s.id === id);
    const type = state.serviceTypes.find((s) => s.id === (service?.type_id || typeId));
    return id ? `${service?.date || date} ${type?.name || service?.type_id || typeId || id}`.trim() : "미선택";
  }
  function renderDevice(root, data, lastSeen, id = "local") {
    const stale = lastSeen && Date.now() - Date.parse(lastSeen) > 45000;
    const row = document.createElement("section"); row.className = "monitor-device";
    const heading = document.createElement("strong"); heading.textContent = String(data.name || `${data.os} ${data.browser}`).slice(0, 80); row.append(heading);
    const lines = [`${data.os} · ${data.browser} · ${data.version}`, `${modules[data.module] || data.module || ""} · 편집 예배: ${serviceName(data.serviceId, data.serviceDate, data.serviceType)}`,
      stale ? "응답 없음 · 아래는 마지막 보고 상태" : "",
      `송출 예배: ${serviceName(data.outputServiceId)} · ${data.output ? `송출창 연결 · ${data.slide} / ${data.count}` : "송출창 미연결"}${data.video ? ` · 영상 ${data.video}` : ""}`,
      data.saving ? "저장 처리 중" : data.dirty ? "미저장 예배 변경 있음" : "미저장 예배 변경 없음",
      lastSeen ? `마지막 응답 ${new Date(lastSeen).toLocaleTimeString()}` : "현재 상태"];
    for (const text of lines.filter(Boolean)) { const p = document.createElement("p"); p.textContent = String(text).slice(0, 300); row.append(p); }
    const details = document.createElement("details"); details.dataset.device = id;
    const summary = document.createElement("summary"); summary.textContent = "최근 작업"; details.append(summary);
    const list = document.createElement("ul");
    for (const event of (Array.isArray(data.events) ? data.events : []).slice(-20).reverse()) {
      if (!eventNames[event.kind]) continue;
      const li = document.createElement("li"); li.textContent = `${new Date(event.at).toLocaleTimeString()} ${eventNames[event.kind]}`; list.append(li);
    }
    details.append(list); row.append(details); root.append(row);
  }
  function renderRows(root, rows) {
    const expanded = new Set([...root.querySelectorAll("details[open]")].map((d) => d.dataset.device));
    root.replaceChildren();
    for (const row of rows) renderDevice(root, row.status, row.last_seen, row.id);
    root.querySelectorAll("details").forEach((d) => { d.open = expanded.has(d.dataset.device); });
  }
  async function rpc(name, args) {
    if (!state.client?.rpc) throw Error("서버 연결을 확인해 주세요.");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const { data, error } = await state.client.rpc(name, args).abortSignal(controller.signal);
      if (error) throw Error(error.code === "PGRST202" || error.code === "42883" ? "원격 조회 서버 설정이 필요합니다." : "서버 요청에 실패했습니다.");
      return data;
    } finally { clearTimeout(timeout); }
  }
  async function leave(token) { if (token) { try { await rpc("mindex_monitor_leave", { p_token: token }); } catch {} } }
  async function upload() {
    if (!enabled || uploading || Date.now() < retryAt || !state.client) return;
    const serial = shareSerial; uploading = true;
    try {
      const token = reporter || await rpc("mindex_monitor_register", {});
      if (serial !== shareSerial || !enabled) { void leave(token); return; }
      if (!token) throw Error("상태 공유 서버 설정 또는 접속 상한을 확인해 주세요.");
      reporter = token;
      if (!await rpc("mindex_monitor_heartbeat", { p_token: token, p_status: snapshot() })) { reporter = null; throw Error("상태 공유 세션이 종료되었습니다."); }
      failures = 0; retryAt = 0;
    } catch (e) {
      retryAt = Date.now() + Math.min(300000, 15000 * 2 ** Math.min(++failures, 5));
      if (panel.open) message(e.message);
    } finally { uploading = false; }
  }
  function lock() {
    loginSerial++; viewSerial++; const old = admin; admin = null; void leave(old);
    $("form").hidden = false; $("[data-lock]").hidden = true; $("[data-devices]").replaceChildren();
    remoteRows = [];
  }
  async function refresh() {
    if (!panel.open) return;
    renderRows($("[data-local]"), [{ id: "local", status: snapshot() }]);
    if (!admin || reading) return;
    renderRows($("[data-devices]"), remoteRows);
    const serial = viewSerial; reading = true;
    try {
      const rows = await rpc("mindex_monitor_read", { p_token: admin });
      if (serial !== viewSerial || !panel.open) return;
      if (!Array.isArray(rows)) { lock(); message("인증이 만료되었습니다."); return; }
      remoteRows = rows.slice(0, 100);
      renderRows($("[data-devices]"), remoteRows);
      if (!rows.length) $("[data-devices]").textContent = "공유 중인 기기 없음";
      message("최근 24시간 · 기기 보고 상태");
    } catch (e) { if (serial === viewSerial) message(`${e.message} 이전 조회 결과입니다.`); }
    finally { reading = false; }
  }
  trigger.onclick = () => { panel.showModal(); void refresh(); window.lucide?.createIcons({ root: panel }); };
  $("[data-close]").onclick = () => panel.close(); panel.addEventListener("close", lock);
  $("[data-lock]").onclick = lock;
  $("[data-refresh]").onclick = () => { void refresh(); };
  $("#monitorName").onchange = () => { try { localStorage.setItem("mindex.monitor.name", $("#monitorName").value.slice(0, 60)); } catch {} };
  $("[data-share]").onchange = () => {
    enabled = $("[data-share]").checked; shareSerial++; events.length = 0; previous = null;
    try { localStorage.setItem("mindex.monitor.share", String(enabled)); } catch {}
    if (enabled) { retryAt = 0; record("open"); void upload(); }
    else { const old = reporter; reporter = null; void leave(old); message("상태 공유 중지"); }
  };
  $("form").onsubmit = async (event) => {
    event.preventDefault(); const serial = ++loginSerial; const submit = $("button[type=submit]"); submit.disabled = true;
    const password = $("#monitorPassword").value; $("#monitorPassword").value = "";
    try {
      const token = await rpc("mindex_monitor_login", { p_password: password });
      if (serial !== loginSerial || !panel.open) { void leave(token); return; }
      if (!token) { message("비밀번호·서버 설정 또는 시도 제한을 확인해 주세요."); return; }
      admin = token; $("form").hidden = true; $("[data-lock]").hidden = false; await refresh();
    } catch (e) { if (serial === loginSerial) message(e.message); }
    finally { submit.disabled = false; }
  };
  document.addEventListener("input", (e) => {
    if (!enabled || panel.contains(e.target) || !e.target.closest?.("#detailPane, #mindexRightSidebar") || Date.now() - lastEdit < 15000) return;
    lastEdit = Date.now(); record("edit");
  }, true);
  window.addEventListener("mindex:save-result", (e) => record(e.detail));
  window.addEventListener("pagehide", () => { shareSerial++; enabled = false; lock(); reporter = null; });
  window.addEventListener("pageshow", (e) => {
    if (!e.persisted) return;
    try { enabled = localStorage.getItem("mindex.monitor.share") === "true"; } catch { enabled = false; }
    $("[data-share]").checked = enabled;
  });
  record("open");
  // Telemetry never awaits, rebuilds, or publishes the presenter state.
  setInterval(() => { if (enabled) { snapshot(); void upload(); } if (panel.open) void refresh(); }, 15000);
})();
