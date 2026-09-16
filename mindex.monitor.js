(() => {
  "use strict";
  if (isPresenterOutputRoute()) return;
  const trigger = document.getElementById("monitorPanelBtn");
  if (!trigger) return;
  const modules = { home: "홈", presenter: "예배", service: "예배", scripture: "말씀", praise: "찬양", calendar: "교회력", references: "참고자료" };
  const eventNames = { open: "접속", view: "화면 이동", service: "예배 선택", edit: "입력 편집", save_start: "예배 저장 시작", save_ok: "예배 저장 완료", save_failed: "예배 저장 흐름 오류", output_on: "송출창 응답 시작", output_off: "송출창 응답 끊김" };
  const events = [];
  const videoNames = { playing: "재생 중", loading: "로딩 중", paused: "일시정지", blocked: "자동 재생 차단", error: "재생 오류", ended: "재생 종료" };
  const requests = new Map();
  const renderKeys = new WeakMap();
  let remoteRows = [];
  let remoteVerified = false, lastReportAt = 0, lastActivityAt = 0;
  let loginPending = false, viewerExpiresAt = 0;
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
    <p class="monitor-share-status" role="status"></p><p class="monitor-message" role="status"></p><h3>현재 기기</h3><div data-local></div>
    <h3>접속 기기</h3><form><label for="monitorPassword">관리자 비밀번호</label><input id="monitorPassword" type="password" autocomplete="current-password" required maxlength="128"><button class="btn secondary" type="submit">확인</button></form>
    <div class="monitor-toolbar" data-filters hidden><label>기기<select data-device-filter><option value="all">전체</option><option value="fresh">응답 있음</option><option value="stale">응답 끊김</option><option value="error">오류 보고</option></select></label><label>작업<select data-event-filter><option value="all">전체</option><option value="save">저장</option><option value="error">저장 오류</option></select></label><span data-count></span></div><div data-devices></div>`;
  document.body.append(panel);
  const $ = (selector) => panel.querySelector(selector);
  $("[data-share]").checked = enabled; $("#monitorName").value = name || `${os} ${browser}`;
  function message(text) { $(".monitor-message").textContent = text; }
  function shareMessage(text) { $(".monitor-share-status").textContent = text; }
  function timestamp(value) {
    const time = Date.parse(value);
    return Number.isFinite(time) && time <= Date.now() + 5000 ? time : 0;
  }
  function isStale(row) { const time = timestamp(row.last_seen); return !time || Date.now() - time > 45000; }
  function dateLabel(value) { return timestamp(value) ? new Date(value).toLocaleString() : "시각 확인 불가"; }
  function hasError(data) {
    const save = (Array.isArray(data.events) ? data.events : []).slice().reverse().find((e) => e?.kind === "save_ok" || e?.kind === "save_failed");
    return save?.kind === "save_failed" || ["blocked", "error"].includes(data.video);
  }
  function record(kind) {
    if (!enabled || !eventNames[kind]) return;
    events.push({ kind, at: new Date().toISOString() });
    if (events.length > 20) events.shift();
  }
  function snapshot() {
    const p = state.presenter;
    const service = state.services.find((s) => s.id === state.selectedServiceId);
    const output = Boolean(p.outputConnectedAt && Date.now() >= p.outputConnectedAt && Date.now() - p.outputConnectedAt <= PRESENTER_OUTPUT_HEARTBEAT_TTL_MS);
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
    const local = id === "local";
    const stale = !local && isStale({ last_seen: lastSeen });
    const unverified = !local && !remoteVerified;
    const row = document.createElement("section"); row.className = "monitor-device";
    row.dataset.health = stale || unverified ? "stale" : hasError(data) ? "error" : "fresh";
    const heading = document.createElement("strong"); heading.textContent = String(data.name || `${data.os} ${data.browser}`).slice(0, 80); row.append(heading);
    const lines = [`${data.os} · ${data.browser} · ${data.version}`, `${modules[data.module] || data.module || ""} · 편집 예배: ${serviceName(data.serviceId, data.serviceDate, data.serviceType)}`,
      stale ? "응답 없음 · 아래는 마지막 보고 상태" : unverified ? "최신 상태 확인 실패 · 아래는 이전 조회 결과" : "",
      `${stale || unverified ? "마지막 보고: " : ""}송출 예배: ${serviceName(data.outputServiceId)} · ${data.output ? `송출창 연결 · 선택 슬라이드 ${data.slide} / ${data.count}` : "송출창 미연결"}${videoNames[data.video] ? ` · 영상 ${videoNames[data.video]}` : ""}`,
      data.saving ? "저장 처리 중" : data.dirty ? "미저장 예배 변경 있음" : "미저장 예배 변경 없음",
      local ? "현재 상태" : `마지막 응답 ${dateLabel(lastSeen)} · 접속 ${id.slice(0, 8)}`];
    for (const text of lines.filter(Boolean)) { const p = document.createElement("p"); p.textContent = String(text).slice(0, 300); row.append(p); }
    const details = document.createElement("details"); details.dataset.device = id;
    const summary = document.createElement("summary"); summary.textContent = "최근 작업"; details.append(summary);
    const list = document.createElement("ul");
    for (const event of (Array.isArray(data.events) ? data.events : []).slice(-20).reverse()) {
      if (!eventNames[event?.kind]) continue;
      const filter = $("[data-event-filter]").value;
      if (filter === "save" && !event.kind.startsWith("save_")) continue;
      if (filter === "error" && event.kind !== "save_failed") continue;
      const li = document.createElement("li"); li.textContent = `${dateLabel(event.at)} ${eventNames[event.kind]}`; list.append(li);
    }
    if (!list.children.length) { const li = document.createElement("li"); li.textContent = "기록 없음"; list.append(li); }
    details.append(list); row.append(details); root.append(row);
  }
  function renderRows(root, rows) {
    const key = JSON.stringify([rows, $("[data-event-filter]").value, remoteVerified, rows.map((row) => isStale(row))]);
    if (renderKeys.get(root) === key) return;
    renderKeys.set(root, key);
    const expanded = new Set([...root.querySelectorAll("details[open]")].map((d) => d.dataset.device));
    root.replaceChildren();
    for (const row of rows) renderDevice(root, row.status, row.last_seen, row.id);
    root.querySelectorAll("details").forEach((d) => { d.open = expanded.has(d.dataset.device); });
  }
  function renderRemote() {
    const filter = $("[data-device-filter]").value;
    const rows = remoteRows.filter((row) => filter === "all" || (filter === "fresh" ? !isStale(row) && remoteVerified : filter === "stale" ? isStale(row) : hasError(row.status)));
    $("[data-count]").textContent = `${rows.length} / ${remoteRows.length}`;
    renderRows($("[data-devices]"), rows);
    if (!rows.length) $("[data-devices]").textContent = "해당 기기 없음";
  }
  async function rpc(name, args) {
    if (!state.client?.rpc) throw Error("원격 조회에 필요한 DB 클라이언트가 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.");
    if (!navigator.onLine) throw Error("네트워크 연결이 끊겼습니다.");
    const controller = new AbortController();
    requests.set(controller, ["mindex_monitor_login", "mindex_monitor_read"].includes(name) ? "viewer" : "reporter");
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const { data, error } = await state.client.rpc(name, args).abortSignal(controller.signal);
      if (controller.signal.aborted) throw Error("서버 응답 시간이 초과되었습니다.");
      if (error) throw Error(error.code === "PGRST202" || error.code === "42883" ? "원격 조회 서버 설정이 필요합니다." : "서버 요청에 실패했습니다.");
      return data;
    } catch (error) {
      if (controller.signal.aborted) throw Error("서버 응답 시간이 초과되었습니다.");
      throw Error(["원격 조회 서버 설정이 필요합니다.", "서버 요청에 실패했습니다."].includes(error?.message) ? error.message : "서버에 연결하지 못했습니다.");
    } finally { clearTimeout(timeout); requests.delete(controller); }
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
      if (serial !== shareSerial || !enabled) return;
      failures = 0; retryAt = 0; lastReportAt = Date.now();
      shareMessage(`상태 공유 중 · 마지막 전송 ${new Date(lastReportAt).toLocaleTimeString()}`);
    } catch (e) {
      if (serial !== shareSerial || !enabled) return;
      retryAt = Date.now() + Math.min(300000, 15000 * 2 ** Math.min(++failures, 5));
      shareMessage(`${e.message} 자동 재시도 예정 · 마지막 전송 ${lastReportAt ? new Date(lastReportAt).toLocaleTimeString() : "없음"}`);
    } finally { uploading = false; }
  }
  function lock() {
    loginSerial++; viewSerial++; const old = admin; admin = null; void leave(old);
    for (const [controller, scope] of requests) if (scope === "viewer") controller.abort();
    viewerExpiresAt = 0; $("#monitorPassword").value = "";
    $("form").hidden = false; $("[data-lock]").hidden = true; $("[data-devices]").replaceChildren();
    $("[data-filters]").hidden = true; remoteRows = []; remoteVerified = false;
    renderKeys.delete($("[data-devices]"));
    message("");
  }
  async function refresh() {
    if (!panel.open) return;
    renderRows($("[data-local]"), [{ id: "local", status: snapshot() }]);
    if (!admin || reading) return;
    renderRemote();
    const serial = viewSerial; reading = true;
    try {
      const rows = await rpc("mindex_monitor_read", { p_token: admin });
      if (serial !== viewSerial || !panel.open) return;
      if (!Array.isArray(rows)) { lock(); message("인증이 만료되었습니다."); return; }
      remoteRows = rows.filter((row) => row && typeof row.id === "string" && row.status && typeof row.status === "object" && !Array.isArray(row.status)).slice(0, 100);
      remoteVerified = true; renderRemote();
      if (!rows.length) $("[data-devices]").textContent = "공유 중인 기기 없음";
      message("최근 24시간 · 기기 보고 상태");
    } catch (e) { if (serial === viewSerial) { remoteVerified = false; renderRemote(); message(`${e.message} 이전 조회 결과입니다.`); } }
    finally { reading = false; }
  }
  trigger.onclick = () => { if (!panel.open) panel.showModal(); lastActivityAt = Date.now(); void refresh(); window.lucide?.createIcons({ root: panel }); };
  $("[data-close]").onclick = () => panel.close(); panel.addEventListener("close", lock);
  $("[data-lock]").onclick = lock;
  $("[data-refresh]").onclick = () => { void refresh(); if (enabled && Date.now() - lastReportAt >= 10000) { retryAt = 0; void upload(); } };
  $("[data-device-filter]").onchange = renderRemote;
  $("[data-event-filter]").onchange = () => { renderRemote(); renderRows($("[data-local]"), [{ id: "local", status: snapshot() }]); };
  $("#monitorName").onchange = () => { try { localStorage.setItem("mindex.monitor.name", $("#monitorName").value.slice(0, 60)); } catch {} };
  $("[data-share]").onchange = () => {
    enabled = $("[data-share]").checked; shareSerial++; events.length = 0; previous = null;
    try { localStorage.setItem("mindex.monitor.share", String(enabled)); } catch {}
    if (enabled) { retryAt = 0; record("open"); shareMessage("상태 공유 연결 중"); void upload(); }
    else { const old = reporter; reporter = null; void leave(old); shareMessage("상태 공유 중지"); }
  };
  $("form").onsubmit = async (event) => {
    event.preventDefault();
    if (loginPending || !panel.open || document.hidden) return;
    loginPending = true;
    const serial = ++loginSerial; const submit = $("button[type=submit]"); submit.disabled = true;
    const password = $("#monitorPassword").value; $("#monitorPassword").value = "";
    try {
      const token = await rpc("mindex_monitor_login", { p_password: password });
      if (serial !== loginSerial || !panel.open) { void leave(token); return; }
      if (!token) { message("비밀번호·서버 설정 또는 시도 제한을 확인해 주세요."); return; }
      admin = token; viewerExpiresAt = Date.now() + 30 * 60 * 1000; lastActivityAt = Date.now();
      $("form").hidden = true; $("[data-lock]").hidden = false; $("[data-filters]").hidden = false; await refresh();
    } catch (e) { if (serial === loginSerial) message(e.message); }
    finally { submit.disabled = false; loginPending = false; }
  };
  document.addEventListener("input", (e) => {
    if (!enabled || panel.contains(e.target) || !e.target.closest?.("#detailPane, #mindexRightSidebar") || Date.now() - lastEdit < 15000) return;
    lastEdit = Date.now(); record("edit");
  }, true);
  window.addEventListener("mindex:save-result", (e) => record(e.detail));
  for (const name of ["pointerdown", "keydown", "input"]) panel.addEventListener(name, () => { lastActivityAt = Date.now(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { lock(); }
    else { if (enabled) { retryAt = 0; void upload(); } void refresh(); }
  });
  window.addEventListener("offline", () => { remoteVerified = false; if (panel.open && admin) renderRemote(); if (enabled) shareMessage("네트워크 연결 끊김 · 전송 대기"); });
  window.addEventListener("online", () => { if (enabled) { retryAt = 0; void upload(); } void refresh(); });
  window.addEventListener("pagehide", () => { shareSerial++; enabled = false; lock(); reporter = null; });
  window.addEventListener("pageshow", (e) => {
    if (!e.persisted) return;
    try { enabled = localStorage.getItem("mindex.monitor.share") === "true"; } catch { enabled = false; }
    $("[data-share]").checked = enabled;
  });
  record("open");
  shareMessage(enabled ? "상태 공유 연결 대기" : "상태 공유 꺼짐");
  // Sample small state only; network writes retain the existing 15-second cadence.
  setInterval(() => {
    if (enabled) snapshot();
    if (admin && (Date.now() >= viewerExpiresAt || Date.now() - lastActivityAt >= 5 * 60 * 1000)) { lock(); message("자동 잠금되었습니다."); }
    if (panel.open) {
      renderRows($("[data-local]"), [{ id: "local", status: snapshot() }]);
      if (admin) renderRemote();
    }
  }, 2000);
  // Telemetry never awaits, rebuilds, or publishes the presenter state.
  setInterval(() => { if (enabled) { snapshot(); void upload(); } if (panel.open) void refresh(); }, 15000);
})();
