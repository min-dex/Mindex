from __future__ import annotations

import html
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as error:
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = error
else:
    PLAYWRIGHT_IMPORT_ERROR = None


APP_DIR = Path(__file__).resolve().parents[1]
INDEX_PATH = APP_DIR / "index.html"
LOCAL_CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ENV_PATHS = (
    APP_DIR / ".env.supabase.local",
    APP_DIR / ".env.supabase",
)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def extract_supa_config() -> tuple[str, str]:
    values: dict[str, str] = {}
    for path in ENV_PATHS:
        values.update(read_env_file(path))
    values.update(os.environ)
    url = values.get("MINDEX_SUPABASE_URL") or values.get("SUPABASE_URL") or ""
    key = (
        values.get("MINDEX_SUPABASE_ANON_KEY")
        or values.get("SUPABASE_ANON_KEY")
        or values.get("SUPABASE_KEY")
        or ""
    )
    return url, key


def injected_index_html() -> str:
    markup = INDEX_PATH.read_text(encoding="utf-8")
    supa_url, supa_key = extract_supa_config()
    if not supa_url or not supa_key or "window.MINDEX_SUPABASE" in markup:
        return markup
    config = json.dumps({"url": supa_url, "anonKey": supa_key})
    script = f"<script>window.MINDEX_SUPABASE={html.escape(config, quote=False)};</script>"
    return markup.replace("</head>", f"    {script}\n  </head>", 1)


class MindexSmokeHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        route = parsed.path
        if route in ("", "/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            query = parse_qs(parsed.query)
            markup = INDEX_PATH.read_text(encoding="utf-8") if query.get("mindexSmokeRaw") else injected_index_html()
            self.wfile.write(markup.encode("utf-8"))
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *_: Any) -> None:
        return


class MindexSmokeServer(ThreadingHTTPServer):
    # The default listen backlog (5) resets connections when a page fires many
    # parallel asset requests, which intermittently dropped app.js mid-load.
    request_queue_size = 128


def start_local_app_server() -> tuple[ThreadingHTTPServer, str]:
    handler = partial(MindexSmokeHandler, directory=str(APP_DIR))
    server = MindexSmokeServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/index.html"


def build_raw_connection_link(app_url: str, module: str = "praise") -> str:
    supa_url, supa_key = extract_supa_config()
    params = (
        f"supabaseUrl={quote(supa_url, safe='')}"
        f"&supabaseAnonKey={quote(supa_key, safe='')}"
        f"&module={quote(module, safe='')}"
    )
    return f"{app_url}?mindexSmokeRaw=1#{params}"


def launch_chromium(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception:
        if LOCAL_CHROME_PATH.exists():
            return playwright.chromium.launch(headless=True, executable_path=str(LOCAL_CHROME_PATH))
        raise


def wait_for_module_data(page, module: str) -> None:
    if module == "service" or module == "presenter":
        expected_module = module
        page.wait_for_function(
            """
            (expectedModule) => document.body.dataset.module === expectedModule
              && (
                document.querySelector('.service-dashboard')
                || document.querySelector('.presenter-dashboard')
                || document.querySelector('#servicePresenterControls')
                || document.querySelector('.service-sidebar')
                || document.querySelector('.empty-detail')
                || document.body.textContent.includes('Psalm 27:14')
              )
            """,
            arg=expected_module,
            timeout=30000,
        )
        return
    if module == "scripture":
        page.wait_for_function(
            """
            () => document.body.dataset.module === 'scripture'
              && (
                document.querySelector('[data-book-code]')
                || document.querySelector('[data-scripture-id]')
                || document.querySelector('.scripture-editor')
                || document.querySelector('.empty-detail')
              )
            """,
            timeout=30000,
        )
        return
    if module == "praise":
        page.wait_for_function(
            """
            () => document.body.dataset.module === 'praise'
              && (
                document.querySelector('[data-song-id]')
                || document.querySelector('.empty-detail')
                || document.querySelector('.song-list-empty')
                || (typeof state !== 'undefined' && state.songs.length > 0)
              )
            """,
            timeout=30000,
        )


def wait_for_supabase_client(page) -> None:
    page.wait_for_function(
        "() => typeof state !== 'undefined' && Boolean(state.client || state.connectionError)",
        timeout=10000,
    )


def wait_for_service_data(page) -> None:
    page.wait_for_function(
        """
        () => typeof state !== 'undefined'
          && (
            (
              state.serviceTypes.length > 0
              && Array.isArray(state.services)
              && state.serviceItems
            )
            || state.serviceError
            || state.connectionError
          )
        """,
        timeout=30000,
    )


def wait_for_praise_data(page) -> None:
    page.wait_for_function(
        """
        () => typeof state !== 'undefined'
          && (state.songs.length > 0 || state.connectionError)
        """,
        timeout=30000,
    )


def wait_for_scripture_data(page) -> None:
    page.wait_for_function(
        """
        () => typeof state !== 'undefined'
          && (state.scriptureBooks.length > 0 || state.scriptureError || state.connectionError)
        """,
        timeout=30000,
    )


def get_app_snapshot(page) -> dict[str, Any]:
    return page.evaluate(
        """
        (() => {
          if (typeof state === 'undefined') return { stateAvailable: false };
          return {
            stateAvailable: true,
            module: state.module,
            songs: state.songs.length,
            scriptures: state.scriptures.length,
            scriptureBooks: state.scriptureBooks.length,
            serviceTypes: state.serviceTypes.length,
            services: state.services.length,
            serviceItemGroups: Object.keys(state.serviceItems || {}).length,
            connectionError: state.connectionError,
            serviceError: state.serviceError,
            scriptureError: state.scriptureError
          };
        })()
        """
    )


def shell_layout_snapshot(page) -> dict[str, Any]:
    return page.evaluate(
        """
        (() => {
          const detail = document.querySelector('.detail-pane');
          const topbar = document.querySelector('.topbar');
          const sidebar = document.querySelector('.sidebar');
          const search = document.querySelector('.sidebar-search-wrap');
          const searchInput = document.querySelector('.sidebar-search-wrap input');
          const firstSectionLabel = document.querySelector('.service-sidebar-head');
          const toggle = document.querySelector('#sidebarToggleBtn');
          const styles = detail ? getComputedStyle(detail) : null;
          const searchInputStyles = searchInput ? getComputedStyle(searchInput) : null;
          const topbarRect = topbar?.getBoundingClientRect();
          const toggleRect = toggle?.getBoundingClientRect();
          const sidebarRect = sidebar?.getBoundingClientRect();
          const searchRect = search?.getBoundingClientRect();
          const firstSectionLabelRect = firstSectionLabel?.getBoundingClientRect();
          return {
            module: document.body.dataset.module,
            viewport: window.innerWidth,
            documentScrollWidth: document.documentElement.scrollWidth,
            bodyScrollWidth: document.body.scrollWidth,
            detailPaddingLeft: styles ? Math.round(parseFloat(styles.paddingLeft)) : 0,
            detailPaddingTop: styles ? Math.round(parseFloat(styles.paddingTop)) : 0,
            sidebarSearchTop: searchRect && topbarRect ? Math.round(searchRect.top - topbarRect.bottom) : 0,
            sidebarSearchSectionGap: searchRect && firstSectionLabelRect ? Math.round(firstSectionLabelRect.top - searchRect.bottom) : 0,
            sidebarSearchInputLineHeight: searchInputStyles ? Math.round(parseFloat(searchInputStyles.lineHeight)) : 0,
            topbarHeight: topbarRect ? Math.round(topbarRect.height) : 0,
            sidebarWidth: sidebarRect ? Math.round(sidebarRect.width) : 0,
            toggleLeft: toggleRect ? Math.round(toggleRect.left) : 0,
            toggleTop: toggleRect ? Math.round(toggleRect.top) : 0,
            toggleWidth: toggleRect ? Math.round(toggleRect.width) : 0,
            toggleHeight: toggleRect ? Math.round(toggleRect.height) : 0
          };
        })()
        """
    )


def select_service_with_slides(page) -> dict[str, Any] | None:
    return page.evaluate(
        """
        (() => {
          if (typeof state === 'undefined') return null;
          let fixture = false;
          let service = state.services
            .filter((item) => (state.serviceItems[item.id] || []).length > 0)
            .find((item) => buildServicePresenterSlides(item.id).length > 0);
          if (!service) {
            fixture = true;
            const typeId = 'monthly';
            service = {
              id: '__smoke_presenter_service__',
              type_id: typeId,
              date: '2026-07-02',
              title: 'Presenter Smoke',
              leader: '테스트',
              alias: '',
            };
            if (!state.serviceTypes.some((item) => item.id === typeId)) {
              state.serviceTypes.push({ id: typeId, name: '월삭예배', sort_order: 1 });
            }
            state.services = [
              service,
              ...state.services.filter((item) => item.id !== service.id),
            ];
            state.__smokePresenterFixtureServiceId = service.id;
            state.serviceItems[service.id] = normalizeServiceItems([
              {
                id: '__smoke_presenter_item_1__',
                service_id: service.id,
                sort_order: 1,
                label: '찬양',
                assignee: '테스트',
                raw_title: '주만 의지해',
                memo: JSON.stringify({
                  slides: [
                    '[Verse 1]\\n주만 의지해\\n주만 바라봐',
                    '[Chorus]\\n주 예수 앞에 다 아뢰어라',
                  ],
                }),
              },
              {
                id: '__smoke_presenter_item_2__',
                service_id: service.id,
                sort_order: 2,
                label: '말씀',
                raw_title: '요 3:16',
                memo: JSON.stringify({
                  elementType: 'scripture',
                  slides: ['하나님이 세상을 이처럼 사랑하사'],
                }),
              },
              {
                id: '__smoke_presenter_item_3__',
                service_id: service.id,
                sort_order: 3,
                label: '빈 화면',
                raw_title: '',
                memo: JSON.stringify({ elementType: 'blank' }),
              },
              {
                id: '__smoke_presenter_item_4__',
                service_id: service.id,
                sort_order: 4,
                label: '파일',
                raw_title: '',
                memo: JSON.stringify({
                  elementType: 'file',
                  asset: {
                    kind: 'file',
                    name: '예배 자료',
                    url: 'archive/service-file',
                  },
                }),
              },
            ]);
          }
          if (!service) return null;
          const slides = buildServicePresenterSlides(service.id);
          state.module = 'presenter';
          state.search = '';
          if (typeof refs !== 'undefined' && refs.searchInput) refs.searchInput.value = '';
          state.selectedServiceTypeId = service.type_id;
          state.selectedServiceId = service.id;
          state.presenter.viewServiceId = service.id;
          render();
          const renderedSlides = presenterSlidesForService(service.id);
          const visibleThumbs = document.querySelectorAll('.svc-slide-thumb[data-presenter-index][data-service-id]').length;
          return { id: service.id, typeId: service.type_id, date: service.date, slides: visibleThumbs || renderedSlides.length, fixture };
        })()
        """
    )


def cleanup_presenter_fixture(page) -> None:
    page.evaluate(
        """
        (() => {
          if (typeof state === 'undefined') return;
          const serviceId = state.__smokePresenterFixtureServiceId;
          if (!serviceId) return;
          state.services = state.services.filter((service) => service.id !== serviceId);
          delete state.serviceItems[serviceId];
          delete state.worshipPresenterSlides[serviceId];
          if (state.selectedServiceId === serviceId) state.selectedServiceId = null;
          if (state.presenter?.viewServiceId === serviceId) state.presenter.viewServiceId = "";
          if (state.presenter?.serviceId === serviceId) {
            state.presenter.serviceId = null;
            state.presenter.slides = [];
            state.presenter.index = 0;
            state.presenter.jumpDraft = "";
            state.presenter.liveScripture = { reference: "", draft: "", active: false, slide: null };
            state.presenter.livePraise = { query: "", draft: "", active: false, slides: [], index: 0, songId: "", versionId: "" };
          }
          if (state.dirty) {
            state.dirty.song = false;
            state.dirty.forms = false;
            state.dirty.scripture = false;
            state.dirty.service = false;
            state.dirty.references = false;
          }
          if (state.dirtyServiceTypeIds?.clear) state.dirtyServiceTypeIds.clear();
          if (typeof clearDirtyState === 'function') clearDirtyState();
          delete state.__smokePresenterFixtureServiceId;
          if (typeof render === 'function') render();
        })()
        """
    )


def main() -> int:
    results: list[tuple[str, str, str]] = []
    console_messages: list[str] = []
    page_errors: list[str] = []
    has_config = all(extract_supa_config())

    def pass_(name: str, detail: str = "") -> None:
        results.append(("PASS", name, detail))

    def fail(name: str, detail: str = "") -> None:
        results.append(("FAIL", name, detail))

    def skip(name: str, detail: str = "") -> None:
        results.append(("SKIP", name, detail))

    app_source = (APP_DIR / "app.js").read_text(encoding="utf-8")
    full_save_start = app_source.find("async function saveWorshipServiceInstance(service)")
    hydrate_call = app_source.find("await ensureWorshipServiceRowsLoadedForPersistence(serviceId);", full_save_start)
    existing_sections = app_source.find("const existingSections = state.worshipSections", full_save_start)
    if full_save_start >= 0 and hydrate_call >= 0 and existing_sections >= 0 and hydrate_call < existing_sections:
        pass_("worship-full-save-loads-rows-before-persist")
    else:
        fail("worship-full-save-loads-rows-before-persist")

    save_service_start = app_source.find("async function saveService(")
    save_service_end = app_source.find("async function saveDirtyServiceTypes", save_service_start)
    save_service_body = app_source[save_service_start:save_service_end]
    commit_input_index = save_service_body.find("commitActiveDeferredServiceTextInput(serviceId);")
    source_apply_index = save_service_body.find("applyPendingServiceSourceTextBeforeSave(serviceId);")
    source_pending_index = save_service_body.find("const sourceTextHadPendingChanges")
    source_block_index = save_service_body.find("예배 원문에서 반영할 항목을 찾지 못해 저장하지 않았습니다.")
    input_problem_index = save_service_body.find("const inputProblem = service ? serviceInputSaveProblem(service) : null;")
    if (
        save_service_start >= 0
        and commit_input_index >= 0
        and source_pending_index >= 0
        and source_apply_index >= 0
        and source_block_index >= 0
        and input_problem_index >= 0
        and commit_input_index < source_pending_index < source_apply_index < source_block_index < input_problem_index
        and "function serviceSourceTextHasPendingChanges" in app_source
    ):
        pass_("worship-save-applies-pending-source-text")
    else:
        fail("worship-save-applies-pending-source-text")

    recovery_helpers = [
        "WORSHIP_RECOVERY_SNAPSHOTS_STORAGE_KEY",
        "WORSHIP_RECOVERY_LATEST_STORAGE_PREFIX",
        "readWorshipRecoverySnapshots",
        "cloneRecoveryRecord",
        "writeWorshipRecoverySnapshots",
        "scheduleWorshipRecoverySnapshotHistoryWrite",
        "buildWorshipRecoverySnapshot",
        "captureWorshipRecoverySnapshot",
    ]
    if all(helper in app_source for helper in recovery_helpers):
        pass_("worship-recovery-snapshot-helpers")
    else:
        fail("worship-recovery-snapshot-helpers")

    capture_start = app_source.find("function captureWorshipRecoverySnapshot")
    capture_end = app_source.find("function uiText", capture_start)
    capture_body = app_source[capture_start:capture_end]
    if (
        "worshipRecoveryLatestSnapshotKey(snapshot.serviceId)" in capture_body
        and "scheduleWorshipRecoverySnapshotHistoryWrite(snapshotJson)" in capture_body
        and "readWorshipRecoverySnapshots()" not in capture_body
    ):
        pass_("worship-recovery-latest-write-before-idle-history")
    else:
        fail("worship-recovery-latest-write-before-idle-history")

    recovery_start = app_source.find("function readWorshipRecoverySnapshots")
    recovery_end = app_source.find("function uiText", recovery_start)
    recovery_body = app_source[recovery_start:recovery_end]
    if (
        "function cloneRecoveryRecord" in recovery_body
        and "serviceDocument" in recovery_body
        and "buildWorshipRecoveryServiceDocument(service)" in recovery_body
        and "!rows.sections.length && !rows.elements.length && !serviceDocument" in recovery_body
        and "JSON.parse(JSON.stringify" not in recovery_body
    ):
        pass_("worship-recovery-shallow-clone-and-service-document")
    else:
        fail("worship-recovery-shallow-clone-and-service-document")

    full_save_end = app_source.find("async function saveServiceItemPatch", full_save_start)
    full_save_body = app_source[full_save_start:full_save_end]
    service_update_index = full_save_body.find('.from("mindex_worship_services")')
    full_save_snapshot_index = full_save_body.find('captureWorshipRecoverySnapshot(service, "before-full-save")')
    full_save_validate_index = full_save_body.find("validateWorshipPersistenceRows(rows, { serviceId });")
    if (
        full_save_snapshot_index >= 0
        and service_update_index >= 0
        and full_save_validate_index >= 0
        and full_save_snapshot_index < full_save_validate_index < service_update_index
    ):
        pass_("worship-full-save-captures-recovery-snapshot")
    else:
        fail("worship-full-save-captures-recovery-snapshot")

    element_patch_start = app_source.find("async function saveWorshipServiceElementPatch")
    element_patch_end = app_source.find("async function syncSharedSundayContentAfterSave", element_patch_start)
    element_patch_body = app_source[element_patch_start:element_patch_end]
    element_upsert_index = element_patch_body.find('.from("mindex_worship_sections")')
    element_service_update_index = element_patch_body.find('.from("mindex_worship_services")')
    element_snapshot_index = element_patch_body.find('captureWorshipRecoverySnapshot(service, "before-element-patch")')
    if (
        element_snapshot_index >= 0
        and element_upsert_index >= 0
        and element_service_update_index >= 0
        and element_snapshot_index < element_upsert_index < element_service_update_index
    ):
        pass_("worship-element-patch-captures-recovery-snapshot")
    else:
        fail("worship-element-patch-captures-recovery-snapshot")

    delete_start = app_source.find("async function deleteService(serviceId)")
    delete_end = app_source.find("function renderServiceTypeFilters", delete_start)
    delete_body = app_source[delete_start:delete_end]
    delete_index = delete_body.find('.delete()')
    delete_snapshot_index = delete_body.find('captureWorshipRecoverySnapshot(service, "before-service-delete")')
    if delete_snapshot_index >= 0 and delete_index >= 0 and delete_snapshot_index < delete_index:
        pass_("worship-delete-captures-recovery-snapshot")
    else:
        fail("worship-delete-captures-recovery-snapshot")

    if sync_playwright is None:
        skip("playwright-dependency", f"{PLAYWRIGHT_IMPORT_ERROR}. Install the Python playwright package to run UI smoke checks.")
        for status, name, detail in results:
            print(f"{status} {name}" + (f" :: {detail}" if detail else ""))
        return 0

    server, app_url = start_local_app_server()
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1440, "height": 980})
            page.add_init_script(
                """
                (() => {
                  if (sessionStorage.getItem('__mindexSmokeStorageInitialized')) return;
                  localStorage.clear();
                  sessionStorage.clear();
                  sessionStorage.setItem('__mindexSmokeStorageInitialized', 'true');
                })();
                """
            )
            def capture_page_error(error) -> None:
                detail = {
                    "name": getattr(error, "name", ""),
                    "message": getattr(error, "message", str(error)),
                    "stack": getattr(error, "stack", ""),
                }
                if detail["name"] or detail["stack"] or detail["message"] != "Object":
                    page_errors.append(json.dumps(detail, ensure_ascii=False, default=str))

            page.on("pageerror", capture_page_error)
            page.on(
                "console",
                lambda msg: console_messages.append(f"{msg.type}: {msg.text}")
                if msg.type in ("error", "warning")
                else None,
            )

            page.goto(app_url, wait_until="load")
            page.wait_for_selector(".app-shell", timeout=5000)

            pass_("document-title", page.title())
            if page.title() != "MINDEX":
                fail("document-title-uppercase", page.title())
            else:
                pass_("document-title-uppercase")

            viewport_restore_state = page.evaluate(
                """
                (async () => {
                  const originalPane = refs.detailPane;
                  const originalState = {
                    module: state.module,
                    selectedSongId: state.selectedSongId,
                    selectedVersionId: state.selectedVersionId,
                    selectedServiceId: state.selectedServiceId,
                  };
                  const pane = document.createElement('div');
                  pane.style.cssText = 'position:fixed;left:-9999px;top:0;width:320px;height:120px;overflow:auto';
                  pane.innerHTML = '<div style="height:2400px"></div>';
                  document.body.appendChild(pane);
                  refs.detailPane = pane;
                  try {
                    state.module = 'praise';
                    state.selectedSongId = 'scroll-song';
                    state.selectedVersionId = 'scroll-version';
                    pane.scrollTop = 420;
                    const detailSnapshot = captureDetailViewportSnapshot();
                    pane.scrollTop = 0;
                    restoreDetailViewportSnapshot(detailSnapshot);
                    const detailImmediate = pane.scrollTop;
                    await new Promise((resolve) => requestAnimationFrame(resolve));
                    const detailAfterFrame = pane.scrollTop;

                    state.module = 'presenter';
                    state.selectedServiceId = 'scroll-service';
                    pane.scrollTop = 0;
                    restorePresenterViewportSnapshot({
                      serviceId: 'scroll-service',
                      scrollTop: 520,
                      selector: '',
                      offsetTop: 0,
                    });
                    const presenterImmediate = pane.scrollTop;
                    restorePresenterViewportSnapshot({
                      serviceId: 'scroll-service',
                      scrollTop: 620,
                      selector: '',
                      offsetTop: 0,
                    });
                    await new Promise((resolve) => requestAnimationFrame(resolve));
                    return {
                      detailImmediate,
                      detailAfterFrame,
                      presenterImmediate,
                      presenterLatest: pane.scrollTop,
                    };
                  } finally {
                    refs.detailPane = originalPane;
                    Object.assign(state, originalState);
                    pane.remove();
                  }
                })()
                """
            )
            if viewport_restore_state == {
                "detailImmediate": 420,
                "detailAfterFrame": 420,
                "presenterImmediate": 520,
                "presenterLatest": 620,
            }:
                pass_("detail-viewport-survives-rerender", json.dumps(viewport_restore_state, ensure_ascii=False))
            else:
                fail("detail-viewport-survives-rerender", json.dumps(viewport_restore_state, ensure_ascii=False))

            unsaved_leave_dialog = page.evaluate(
                """
                (async () => {
                  if (typeof state === 'undefined' || typeof confirmSaveBeforeLeaving !== 'function') {
                    return { ready: false };
                  }
                  const originalReloadDiscardedChanges = reloadDiscardedChanges;
                  let reloadedModules = null;
                  reloadDiscardedChanges = async (dirtyModules) => {
                    reloadedModules = dirtyModules;
                  };
                  if (typeof clearDirtyState === 'function') clearDirtyState();
                  state.cleanFingerprints.praise = '';
                  state.dirty.song = true;
                  if (typeof updateSaveState === 'function') updateSaveState();
                  const pending = confirmSaveBeforeLeaving();
                  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                  const buttons = [...document.querySelectorAll('.unsaved-dialog [data-unsaved-action]')]
                    .map((button) => button.dataset.unsavedAction);
                  document.querySelector('[data-unsaved-action="discard"]')?.click();
                  const result = await pending;
                  const dialogGone = !document.querySelector('.unsaved-dialog-backdrop');
                  const dirtyAfter = typeof hasDirtyChanges === 'function' ? hasDirtyChanges() : null;
                  reloadDiscardedChanges = originalReloadDiscardedChanges;
                  if (typeof clearDirtyState === 'function') clearDirtyState();
                  if (typeof updateSaveState === 'function') updateSaveState();
                  return { ready: true, buttons, result, reloadedModules, dialogGone, dirtyAfter };
                })()
                """
            )
            if (
                unsaved_leave_dialog.get("ready")
                and unsaved_leave_dialog.get("buttons") == ["cancel", "discard", "save"]
                and unsaved_leave_dialog.get("result") is True
                and unsaved_leave_dialog.get("reloadedModules", {}).get("praise") is True
                and unsaved_leave_dialog.get("dialogGone") is True
                and unsaved_leave_dialog.get("dirtyAfter") is False
            ):
                pass_("unsaved-leave-dialog-discard", json.dumps(unsaved_leave_dialog, ensure_ascii=False))
            else:
                fail("unsaved-leave-dialog-discard", json.dumps(unsaved_leave_dialog, ensure_ascii=False))

            actual_dirty_diff = page.evaluate(
                """
                (() => {
                  if (
                    typeof state === 'undefined'
                    || typeof captureCleanFingerprint !== 'function'
                    || typeof hasDirtyChanges !== 'function'
                  ) return { ready: false };
                  const originalLinks = state.referenceLinks;
                  const originalDirty = { ...state.dirty };
                  const originalFingerprints = { ...state.cleanFingerprints };
                  try {
                    state.referenceLinks = [{
                      id: 'dirty-smoke-reference',
                      title: '기준 제목',
                      url: 'https://example.com',
                      sort_order: 10,
                      is_active: true,
                    }];
                    captureCleanFingerprint('references');
                    state.dirty.references = true;
                    const unchanged = hasDirtyChanges({ reconcile: true });
                    state.referenceLinks[0].title = '변경 제목';
                    state.dirty.references = true;
                    const changed = hasDirtyChanges({ reconcile: true });
                    state.referenceLinks[0].title = '기준 제목';
                    const restored = hasDirtyChanges({ reconcile: true });
                    return { ready: true, unchanged, changed, restored };
                  } finally {
                    state.referenceLinks = originalLinks;
                    Object.assign(state.dirty, originalDirty);
                    Object.assign(state.cleanFingerprints, originalFingerprints);
                  }
                })()
                """
            )
            if actual_dirty_diff == {
                "ready": True,
                "unchanged": False,
                "changed": True,
                "restored": False,
            }:
                pass_("unsaved-warning-uses-actual-diff", json.dumps(actual_dirty_diff, ensure_ascii=False))
            else:
                fail("unsaved-warning-uses-actual-diff", json.dumps(actual_dirty_diff, ensure_ascii=False))

            reversed_scripture_reference = page.evaluate(
                """
                (() => {
                  if (typeof parseBibleReference !== 'function') return { ready: false };
                  const references = ['23:1마', '23:1 마', '23:1-3마', '23:1ak']
                    .map((input) => {
                      const parsed = parseBibleReference(input);
                      return {
                        input,
                        book: parsed?.book?.code || '',
                        chapter: parsed?.chapter || 0,
                        verse: parsed?.verse || 0,
                        verseEnd: parsed?.verseEnd || 0,
                      };
                    });
                  return { ready: true, references };
                })()
                """
            )
            if (
                reversed_scripture_reference.get("ready")
                and reversed_scripture_reference.get("references") == [
                    {"input": "23:1마", "book": "MAT", "chapter": 23, "verse": 1, "verseEnd": 0},
                    {"input": "23:1 마", "book": "MAT", "chapter": 23, "verse": 1, "verseEnd": 0},
                    {"input": "23:1-3마", "book": "MAT", "chapter": 23, "verse": 1, "verseEnd": 3},
                    {"input": "23:1ak", "book": "MAT", "chapter": 23, "verse": 1, "verseEnd": 0},
                ]
            ):
                pass_("reversed-scripture-reference", json.dumps(reversed_scripture_reference, ensure_ascii=False))
            else:
                fail("reversed-scripture-reference", json.dumps(reversed_scripture_reference, ensure_ascii=False))

            preparation_role_semantics = page.evaluate(
                """
                (() => {
                  if (
                    typeof normalizeServicePresenterRole !== 'function'
                    || typeof presenterPreparationRole !== 'function'
                    || typeof servicePreparationElementLabel !== 'function'
                    || typeof servicePreparationDefaultRoleForType !== 'function'
                  ) return { ready: false };
                  return {
                    ready: true,
                    readyScreenAlias: normalizeServicePresenterRole('대기 화면'),
                    waitingVideoAlias: normalizeServicePresenterRole('대기 영상'),
                    readyScreenRole: presenterPreparationRole({ label: '대기 화면', raw_title: '' }, {}),
                    waitingVideoRole: presenterPreparationRole({ label: '대기 영상', raw_title: '' }, {}),
                    chromakeyDefaultRole: servicePreparationDefaultRoleForType('', 'monthly'),
                    chromakeyReadyRole: servicePreparationDefaultRoleForType('대기 화면', 'monthly'),
                    chromakeyWaitingRole: servicePreparationDefaultRoleForType('대기 영상', 'monthly'),
                    readyScreenLabel: servicePreparationElementLabel('ready'),
                    waitingVideoLabel: servicePreparationElementLabel('waiting_loop'),
                  };
                })()
                """
            )
            if preparation_role_semantics == {
                "ready": True,
                "readyScreenAlias": "ready",
                "waitingVideoAlias": "waiting_loop",
                "readyScreenRole": "ready",
                "waitingVideoRole": "waiting_loop",
                "chromakeyDefaultRole": "waiting_loop",
                "chromakeyReadyRole": "ready",
                "chromakeyWaitingRole": "waiting_loop",
                "readyScreenLabel": "대기 화면",
                "waitingVideoLabel": "대기 영상",
            }:
                pass_("preparation-role-semantics", json.dumps(preparation_role_semantics, ensure_ascii=False))
            else:
                fail("preparation-role-semantics", json.dumps(preparation_role_semantics, ensure_ascii=False))

            passive_service_scripture_dirty = page.evaluate(
                """
                (async () => {
                  if (
                    typeof state === 'undefined'
                    || typeof normalizeServiceItem !== 'function'
                    || typeof serializeServiceItemMemo !== 'function'
                    || typeof parseBibleReference !== 'function'
                    || typeof cacheServiceScriptureVerses !== 'function'
                    || typeof resolveServiceScriptureBodyReference !== 'function'
                    || typeof captureCleanFingerprint !== 'function'
                    || typeof hasDirtyChanges !== 'function'
                  ) return { ready: false };
                  const original = {
                    services: state.services,
                    serviceItems: state.serviceItems,
                    selectedServiceId: state.selectedServiceId,
                    selectedServiceTypeId: state.selectedServiceTypeId,
                    dirty: { ...state.dirty },
                    cleanFingerprints: { ...state.cleanFingerprints },
                    client: state.client,
                    bibleTranslations: state.bibleTranslations,
                    selectedBibleTranslationId: state.selectedBibleTranslationId,
                    bibleVerseCache: state.bibleVerseCache,
                  };
                  const service = { id: '__smoke_passive_scripture_service__', type_id: 'wednesday', date: '2099-01-01', title: '' };
                  const makeScriptureItem = () => normalizeServiceItem({
                    id: '__smoke_passive_scripture_item__',
                    service_id: service.id,
                    label: '성경봉독',
                    raw_title: '요 3:16',
                    memo: serializeServiceItemMemo({
                      elementType: 'scripture_body',
                      inputMode: 'scripture',
                      scriptureReference: '요 3:16',
                      scriptureReferences: ['요 3:16'],
                      slides: [],
                    }),
                  }, 0);
                  try {
                    const reference = parseBibleReference('요 3:16');
                    if (!reference) return { ready: false, reason: 'reference' };
                    const translation = { id: '__smoke_passive_translation__', name: '개역개정', translationKey: 'KRV' };
                    state.services = [service];
                    state.serviceItems = { [service.id]: [makeScriptureItem()] };
                    state.selectedServiceId = service.id;
                    state.selectedServiceTypeId = service.type_id;
                    state.client = {};
                    state.bibleTranslations = [translation];
                    state.selectedBibleTranslationId = translation.id;
                    state.bibleVerseCache = new Map();
                    cacheServiceScriptureVerses(reference, [{
                      book_code: reference.book.code,
                      chapter: 3,
                      verse: 16,
                      text: '하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니',
                    }], translation);

                    captureCleanFingerprint('service');
                    state.dirty.service = false;
                    await resolveServiceScriptureBodyReference(service.id, 0, {
                      itemId: '__smoke_passive_scripture_item__',
                      markDirty: false,
                      renderControls: false,
                      renderDetail: false,
                    });
                    const passiveDirty = state.dirty.service;
                    const passiveHasDirty = hasDirtyChanges({ reconcile: true });

                    state.serviceItems = { [service.id]: [makeScriptureItem()] };
                    captureCleanFingerprint('service');
                    state.dirty.service = false;
                    await resolveServiceScriptureBodyReference(service.id, 0, {
                      itemId: '__smoke_passive_scripture_item__',
                      renderControls: false,
                      renderDetail: false,
                    });
                    const explicitDirty = state.dirty.service;

                    if (typeof scheduledPresenterRefreshes !== 'undefined') {
                      scheduledPresenterRefreshes.forEach((entry) => {
                        if (entry?.timer) window.clearTimeout(entry.timer);
                      });
                      scheduledPresenterRefreshes.clear();
                    }
                    return { ready: true, passiveDirty, passiveHasDirty, explicitDirty };
                  } finally {
                    if (typeof scheduledPresenterRefreshes !== 'undefined') {
                      scheduledPresenterRefreshes.forEach((entry) => {
                        if (entry?.timer) window.clearTimeout(entry.timer);
                      });
                      scheduledPresenterRefreshes.clear();
                    }
                    state.services = original.services;
                    state.serviceItems = original.serviceItems;
                    state.selectedServiceId = original.selectedServiceId;
                    state.selectedServiceTypeId = original.selectedServiceTypeId;
                    Object.assign(state.dirty, original.dirty);
                    state.cleanFingerprints = original.cleanFingerprints;
                    state.client = original.client;
                    state.bibleTranslations = original.bibleTranslations;
                    state.selectedBibleTranslationId = original.selectedBibleTranslationId;
                    state.bibleVerseCache = original.bibleVerseCache;
                  }
                })()
                """
            )
            if passive_service_scripture_dirty == {
                "ready": True,
                "passiveDirty": False,
                "passiveHasDirty": False,
                "explicitDirty": True,
            }:
                pass_("passive-service-scripture-resolve-keeps-clean", json.dumps(passive_service_scripture_dirty, ensure_ascii=False))
            else:
                fail("passive-service-scripture-resolve-keeps-clean", json.dumps(passive_service_scripture_dirty, ensure_ascii=False))

            icon_metrics = page.evaluate(
                """
                [...document.querySelectorAll('#sidebarToggleBtn,#themeBtn,#saveAllBtn')]
                  .filter((node) => node.offsetParent !== null)
                  .map((node) => {
                    const rect = node.getBoundingClientRect();
                    return { id: node.id, width: Math.round(rect.width), height: Math.round(rect.height) };
                  })
                """
            )
            bad_icons = [
                item for item in icon_metrics
                if abs(item["width"] - item["height"]) > 2 or item["width"] < 28 or item["height"] < 28
            ]
            if bad_icons:
                fail("topbar-icon-grid", json.dumps(bad_icons, ensure_ascii=False))
            else:
                pass_("topbar-icon-grid", json.dumps(icon_metrics, ensure_ascii=False))

            save_state_scope = page.evaluate(
                """
                async () => {
                  const original = {
                    module: state.module,
                    dirty: { ...state.dirty },
                    selectedSongId: state.selectedSongId,
                    selectedScriptureId: state.selectedScriptureId,
                    songs: state.songs,
                    scriptures: state.scriptures,
                    saving: state.saving,
                    loading: state.loading,
                  };
                  const snap = () => ({
                    label: refs.saveAllBtn.getAttribute('aria-label'),
                    title: refs.saveAllBtn.getAttribute('title'),
                    disabled: refs.saveAllBtn.disabled,
                  });
                  try {
                    state.songs = [{ id: '__save_scope_song__', title: '저장 범위 확인', versions: [] }];
                    state.scriptures = [{ id: '__save_scope_scripture__', title: '저장 범위 확인' }];
                    state.selectedSongId = '__save_scope_song__';
                    state.selectedScriptureId = '__save_scope_scripture__';
                    state.loading = false;
                    state.saving = false;

                    state.dirty = { song: false, forms: false, scripture: false, service: false, references: true };
                    state.module = 'praise';
                    updateSaveState();
                    const praiseOtherDirty = snap();
                    const praiseNoop = await saveAll();

                    state.dirty = { song: false, forms: true, scripture: false, service: false, references: false };
                    updateSaveState();
                    const praiseOwnDirty = snap();

                    state.dirty = { song: true, forms: false, scripture: false, service: false, references: false };
                    state.module = 'scripture';
                    updateSaveState();
                    const scriptureOtherDirty = snap();

                    state.dirty = { song: false, forms: false, scripture: true, service: false, references: false };
                    updateSaveState();
                    const scriptureOwnDirty = snap();

                    state.module = 'calendar';
                    state.dirty = { song: false, forms: false, scripture: false, service: false, references: true };
                    updateSaveState();
                    const calendar = snap();

                    state.module = 'references';
                    state.saving = true;
                    updateSaveState();
                    const saving = snap();

                    return { praiseOtherDirty, praiseNoop, praiseOwnDirty, scriptureOtherDirty, scriptureOwnDirty, calendar, saving };
                  } finally {
                    state.module = original.module;
                    state.dirty = original.dirty;
                    state.selectedSongId = original.selectedSongId;
                    state.selectedScriptureId = original.selectedScriptureId;
                    state.songs = original.songs;
                    state.scriptures = original.scriptures;
                    state.saving = original.saving;
                    state.loading = original.loading;
                    updateSaveState();
                  }
                }
                """
            )
            if (
                save_state_scope["praiseOtherDirty"] == {"label": "찬양 저장", "title": "찬양 저장", "disabled": True}
                and save_state_scope["praiseNoop"] is True
                and save_state_scope["praiseOwnDirty"] == {"label": "찬양 저장", "title": "찬양 저장", "disabled": False}
                and save_state_scope["scriptureOtherDirty"] == {"label": "말씀 저장", "title": "말씀 저장", "disabled": True}
                and save_state_scope["scriptureOwnDirty"] == {"label": "말씀 저장", "title": "말씀 저장", "disabled": False}
                and save_state_scope["calendar"] == {"label": "교회력은 여기서 읽기 전용입니다", "title": "교회력은 여기서 읽기 전용입니다", "disabled": True}
                and save_state_scope["saving"] == {"label": "저장 중", "title": "저장 중", "disabled": True}
            ):
                pass_("save-state-current-module-scope", json.dumps(save_state_scope, ensure_ascii=False))
            else:
                fail("save-state-current-module-scope", json.dumps(save_state_scope, ensure_ascii=False))

            topbar_offsets = page.evaluate(
                """
                (() => {
                  const leftRail = document.querySelector('.nav-sidebar')?.getBoundingClientRect();
                  const rightRail = document.querySelector('.topbar-actions')?.getBoundingClientRect();
                  const leftFirst = document.querySelector('#sidebarToggleBtn')?.getBoundingClientRect();
                  const rightFirst = document.querySelector('#themeBtn')?.getBoundingClientRect();
                  const rightLast = [...(document.querySelector('.topbar-actions')?.children || [])]
                    .filter(child => getComputedStyle(child).display !== 'none')
                    .pop()?.getBoundingClientRect();
                  return {
                    leftFirst: Math.round((leftFirst?.left || 0) - (leftRail?.left || 0)),
                    rightFirst: Math.round((rightFirst?.left || 0) - (rightRail?.left || 0)),
                    rightLastInset: Math.round((rightRail?.right || 0) - (rightLast?.right || 0))
                  };
                })()
                """
            )
            if topbar_offsets["leftFirst"] == 5 and topbar_offsets["rightLastInset"] == 5:
                pass_("topbar-action-offset", json.dumps(topbar_offsets, ensure_ascii=False))
            else:
                fail("topbar-action-offset", json.dumps(topbar_offsets, ensure_ascii=False))

            page.click("#sidebarToggleBtn")
            collapsed = page.evaluate("document.body.classList.contains('sidebar-collapsed')")
            page.click("#sidebarToggleBtn")
            expanded = page.evaluate("!document.body.classList.contains('sidebar-collapsed')")
            page.wait_for_timeout(180)
            if collapsed and expanded:
                pass_("sidebar-toggle")
            else:
                fail("sidebar-toggle", f"collapsed={collapsed} expanded={expanded}")

            page.click("#sidebarToggleBtn")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#sidebarToggleBtn")
            page.wait_for_function("() => typeof state !== 'undefined'")
            collapsed_after_reload = page.evaluate("document.body.classList.contains('sidebar-collapsed')")
            page.click("#sidebarToggleBtn")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#sidebarToggleBtn")
            page.wait_for_function("() => typeof state !== 'undefined'")
            expanded_after_reload = page.evaluate("!document.body.classList.contains('sidebar-collapsed')")
            if collapsed_after_reload and expanded_after_reload:
                pass_("sidebar-state-persistence")
            else:
                fail(
                    "sidebar-state-persistence",
                    f"collapsed={collapsed_after_reload} expanded={expanded_after_reload}",
                )

            desktop_shell = shell_layout_snapshot(page)
            desktop_overflow = max(
                desktop_shell["documentScrollWidth"] - desktop_shell["viewport"],
                desktop_shell["bodyScrollWidth"] - desktop_shell["viewport"],
            )
            if (
                desktop_shell["detailPaddingLeft"] == 25
                and desktop_shell["detailPaddingTop"] == 25
                and desktop_shell["sidebarSearchTop"] == 0
                and desktop_shell["sidebarSearchInputLineHeight"] == 30
                and desktop_shell["topbarHeight"] == 50
                and desktop_shell["toggleWidth"] == desktop_shell["toggleHeight"] == 40
                and desktop_overflow <= 2
            ):
                pass_("shell-desktop-geometry", json.dumps(desktop_shell, ensure_ascii=False))
            else:
                fail("shell-desktop-geometry", json.dumps(desktop_shell, ensure_ascii=False))

            home_gutter = page.evaluate(
                """
                (() => {
                  const detail = document.querySelector('.detail-pane')?.getBoundingClientRect();
                  const home = document.querySelector('.service-dashboard, .loading-detail')?.getBoundingClientRect();
                  return {
                    ready: Boolean(home),
                    left: Math.round((home?.left || 0) - (detail?.left || 0)),
                    top: Math.round((home?.top || 0) - (detail?.top || 0)),
                    width: Math.round(home?.width || 0),
                    overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                  };
                })()
                """
            )
            if (
                not home_gutter["ready"]
                or (
                    home_gutter["left"] in {24, 25}
                    and home_gutter["top"] in {24, 25}
                    and home_gutter["overflow"] <= 2
                )
            ):
                pass_("home-screen-gutter", json.dumps(home_gutter, ensure_ascii=False))
            else:
                fail("home-screen-gutter", json.dumps(home_gutter, ensure_ascii=False))

            page.click("#sidebarToggleBtn")
            page.wait_for_timeout(180)
            collapsed_shell = shell_layout_snapshot(page)
            page.click("#sidebarToggleBtn")
            page.wait_for_timeout(180)
            if collapsed_shell["detailPaddingLeft"] == desktop_shell["detailPaddingLeft"]:
                pass_("sidebar-collapse-keeps-gutter", json.dumps(collapsed_shell, ensure_ascii=False))
            else:
                fail("sidebar-collapse-keeps-gutter", json.dumps(collapsed_shell, ensure_ascii=False))

            page.set_viewport_size({"width": 390, "height": 780})
            page.wait_for_timeout(180)
            mobile_shell = shell_layout_snapshot(page)
            mobile_overflow = max(
                mobile_shell["documentScrollWidth"] - mobile_shell["viewport"],
                mobile_shell["bodyScrollWidth"] - mobile_shell["viewport"],
            )
            if (
                mobile_shell["detailPaddingLeft"] == 25
                and mobile_shell["detailPaddingTop"] == 25
                and mobile_shell["sidebarSearchTop"] == 0
                and mobile_shell["sidebarSearchInputLineHeight"] == 30
                and mobile_shell["topbarHeight"] == 50
                and mobile_overflow <= 2
            ):
                pass_("shell-mobile-geometry", json.dumps(mobile_shell, ensure_ascii=False))
            else:
                fail("shell-mobile-geometry", json.dumps(mobile_shell, ensure_ascii=False))
            page.set_viewport_size({"width": 1440, "height": 980})

            responsive_shells = []
            for width in (1180, 900, 760, 520, 390):
                page.set_viewport_size({"width": width, "height": 780})
                page.wait_for_timeout(180)
                responsive_shells.append(
                    page.evaluate(
                        """
                        (width) => {
                          const rect = (selector) => {
                            const node = document.querySelector(selector);
                            const box = node?.getBoundingClientRect();
                            return box ? {
                              left: Math.round(box.left),
                              right: Math.round(box.right),
                              width: Math.round(box.width),
                              height: Math.round(box.height)
                            } : null;
                          };
                          const topbar = rect('.topbar');
                          const navSidebar = rect('.nav-sidebar');
                          const sidebar = rect('.sidebar');
                          const search = rect('.sidebar-search-wrap');
                          const detail = rect('.detail-pane');
                          const switcher = document.querySelector('.primary-switcher');
                          return {
                            width,
                            topbarHeight: topbar?.height || 0,
                            railWidth: navSidebar?.width || 0,
                            sidebarWidth: sidebar?.width || 0,
                            sidebarHeight: sidebar?.height || 0,
                            sidebarLeftRail: Boolean(sidebar && detail && detail.left >= sidebar.right),
                            searchWithinSidebar: Boolean(search && sidebar && search.left >= sidebar.left && search.right <= sidebar.right),
                            switcherClientWidth: Math.round(switcher?.clientWidth || 0),
                            switcherScrollWidth: Math.round(switcher?.scrollWidth || 0),
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                          };
                        }
                        """,
                        width,
                    )
                )
            if all(
                item["topbarHeight"] == 50
                and item["sidebarWidth"] <= item["railWidth"] <= item["width"]
                and item["railWidth"] - item["sidebarWidth"] == 50
                and item["sidebarLeftRail"]
                and (item["width"] > 860 or item["sidebarHeight"] > 300)
                and item["searchWithinSidebar"]
                and item["switcherClientWidth"] > 0
                and item["overflow"] <= 2
                for item in responsive_shells
            ):
                pass_("shell-responsive-geometry", json.dumps(responsive_shells, ensure_ascii=False))
            else:
                fail("shell-responsive-geometry", json.dumps(responsive_shells, ensure_ascii=False))
            page.set_viewport_size({"width": 1440, "height": 980})

            reference_page = browser.new_page(viewport={"width": 1100, "height": 760})
            reference_page.add_init_script("localStorage.clear(); sessionStorage.clear();")
            reference_page.goto(f"{app_url}?mindexSmokeRaw=1", wait_until="load")
            reference_page.wait_for_selector(".app-shell", timeout=5000)
            reference_page.wait_for_function("() => typeof state !== 'undefined'", timeout=10000)
            reference_page.evaluate(
                """
                (() => {
                  state.module = 'references';
                  state.referenceError = '';
                  state.referenceLinksLoaded = true;
                  state.referenceGroupSupported = true;
                  state.referenceLinks = [
                    { id: 'a1', title: 'Alpha Link', url: 'https://alpha.example', group_name: 'Alpha', sort_order: 10, is_active: true },
                    { id: 'b1', title: 'Beta One', url: 'https://beta-one.example', group_name: 'Beta', sort_order: 20, is_active: true },
                    { id: 'b2', title: 'Beta Two', url: 'https://beta-two.example', group_name: 'Beta', sort_order: 30, is_active: true }
                  ];
                  render();
                })();
                """
            )
            reference_page.evaluate(
                """
                (() => {
                  moveReferenceGroup('Alpha', 1);
                  moveReferenceLink('b1', 1);
                })();
                """
            )
            reference_order = reference_page.evaluate(
                """
                (() => ({
                  groups: [...document.querySelectorAll('.reference-group-head h3')].map((node) => node.textContent.trim()),
                  links: state.referenceLinks.map((link) => link.id),
                  dirty: state.dirty.references
                }))()
                """
            )
            if reference_order["groups"] == ["Beta", "Alpha"] and reference_order["links"] == ["b2", "b1", "a1"] and reference_order["dirty"]:
                pass_("reference-group-reorder", json.dumps(reference_order, ensure_ascii=False))
            else:
                fail("reference-group-reorder", json.dumps(reference_order, ensure_ascii=False))
            reference_guards = reference_page.evaluate(
                """
                async () => {
                  const originalClient = state.client;
                  const originalToast = window.showToast;
                  window.showToast = () => {};

                  state.module = 'calendar';
                  state.calendarData = [{ id: 'cal1', date: '2026-01-04', note: '이전 기념' }];
                  state.client = {
                    from: () => ({
                      update: () => ({
                        eq: async () => ({ error: new Error('save failed') })
                      })
                    })
                  };
                  const cell = document.createElement('td');
                  cell.className = 'cal-cell';
                  cell.dataset.initialValue = '이전 기념';
                  cell.textContent = '새 기념';
                  const calendarSaved = await saveCalendarCell('cal1', 'note', '새 기념', { cell, previousValue: '이전 기념' });

                  state.module = 'references';
                  state.referenceLinksLoaded = true;
                  state.referenceGroupSupported = false;
                  state.referenceError = '';
                  state.referenceLinks = [
                    { id: 'safe', title: 'Safe', url: 'example.com/path', group_name: '', sort_order: 10, is_active: true },
                    { id: 'bad', title: 'Bad', url: 'javascript:alert(1)', group_name: 'Hidden', sort_order: 20, is_active: true }
                  ];
                  renderReferencesDetail();
                  const rendered = {
                    newGroupButtons: document.querySelectorAll('[data-reference-action="new-group"]').length,
                    groupFields: document.querySelectorAll('[data-reference-field="group_name"]').length,
                    disabledLinks: document.querySelectorAll('.reference-card-link.disabled').length,
                    safeUrl: normalizeReferenceUrl('example.com/path'),
                    unsafeUrl: normalizeReferenceUrl('javascript:alert(1)')
                  };

                  let savedPayload = null;
                  let orderCount = 0;
                  state.referenceLinks = [{ id: 'save-safe', title: 'Docs', url: 'docs.example.com', group_name: 'Ignored', sort_order: 10, is_active: true }];
                  state.client = {
                    from: () => ({
                      upsert: (payload) => {
                        savedPayload = payload;
                        const query = {
                          select: () => query,
                          order: () => {
                            orderCount += 1;
                            return orderCount >= 2 ? { data: payload, error: null } : query;
                          }
                        };
                        return query;
                      }
                    })
                  };
                  await saveReferenceLinks();

                  state.client = originalClient;
                  window.showToast = originalToast;
                  return {
                    calendarSaved,
                    calendarText: cell.textContent,
                    calendarRow: state.calendarData[0].note,
                    calendarErrorClass: cell.classList.contains('is-save-error'),
                    rendered,
                    savedPayload
                  };
                }
                """
            )
            if (
                reference_guards["calendarSaved"] is False
                and reference_guards["calendarText"] == "이전 기념"
                and reference_guards["calendarRow"] == "이전 기념"
                and reference_guards["calendarErrorClass"]
                and reference_guards["rendered"]["newGroupButtons"] == 0
                and reference_guards["rendered"]["groupFields"] == 0
                and reference_guards["rendered"]["disabledLinks"] == 1
                and reference_guards["rendered"]["safeUrl"] == "https://example.com/path"
                and reference_guards["rendered"]["unsafeUrl"] == ""
                and reference_guards["savedPayload"][0]["url"] == "https://docs.example.com/"
                and "group_name" not in reference_guards["savedPayload"][0]
            ):
                pass_("calendar-reference-guards", json.dumps(reference_guards, ensure_ascii=False))
            else:
                fail("calendar-reference-guards", json.dumps(reference_guards, ensure_ascii=False))
            reference_page.close()

            if not has_config:
                skip("supabase-backed-flows", "No Supabase config found.")
            else:
                raw_page = browser.new_page(viewport={"width": 1280, "height": 820})
                raw_page.add_init_script(
                    """
                    (() => {
                      localStorage.clear();
                      sessionStorage.clear();
                    })();
                    """
                )
                raw_page.on("pageerror", lambda error: page_errors.append(f"raw-link: {error}"))
                raw_page.on(
                    "console",
                    lambda msg: console_messages.append(f"raw-link {msg.type}: {msg.text}")
                    if msg.type in ("error", "warning")
                    else None,
                )
                raw_page.goto(build_raw_connection_link(app_url, "praise"), wait_until="load")
                raw_page.wait_for_selector(".app-shell", timeout=5000)
                wait_for_supabase_client(raw_page)
                wait_for_praise_data(raw_page)
                raw_link_state = raw_page.evaluate(
                    """
                    (() => ({
                      module: state.module,
                      songs: state.songs.length,
                      connectionError: state.connectionError,
                      injectedConfig: Boolean(window.MINDEX_SUPABASE),
                      hasUrl: Boolean(state.config.url),
                      hasAnonKey: Boolean(state.config.anonKey)
                    }))()
                    """
                )
                if (
                    raw_link_state["module"] == "praise"
                    and raw_link_state["songs"] > 0
                    and not raw_link_state["connectionError"]
                    and raw_link_state["hasUrl"]
                    and raw_link_state["hasAnonKey"]
                ):
                    pass_("share-link-connection", json.dumps(raw_link_state, ensure_ascii=False))
                else:
                    fail("share-link-connection", json.dumps(raw_link_state, ensure_ascii=False))

                explicit_past_service_link = raw_page.evaluate(
                    """
                    (() => {
                      const serviceId = '44444444-4444-4444-8444-444444444444';
                      const originalServices = state.services;
                      const originalSelectedServiceId = state.selectedServiceId;
                      const originalModule = state.module;
                      try {
                        explicitlyRequestedWorshipServiceIds.delete(serviceId);
                        state.services = [{ id: serviceId, type_id: 'wednesday', date: '2000-01-01' }];
                        const deferredBefore = shouldDeferPastWorshipServiceLoad(serviceId);
                        applyLinkState(new URLSearchParams(`module=presenter&service=${serviceId}`));
                        return {
                          deferredBefore,
                          deferredAfter: shouldDeferPastWorshipServiceLoad(serviceId),
                          selectedServiceId: state.selectedServiceId,
                        };
                      } finally {
                        explicitlyRequestedWorshipServiceIds.delete(serviceId);
                        state.services = originalServices;
                        state.selectedServiceId = originalSelectedServiceId;
                        state.module = originalModule;
                      }
                    })()
                    """
                )
                if (
                    explicit_past_service_link["deferredBefore"]
                    and not explicit_past_service_link["deferredAfter"]
                    and explicit_past_service_link["selectedServiceId"] == "44444444-4444-4444-8444-444444444444"
                ):
                    pass_("explicit-past-service-link-loads", json.dumps(explicit_past_service_link, ensure_ascii=False))
                else:
                    fail("explicit-past-service-link-loads", json.dumps(explicit_past_service_link, ensure_ascii=False))
                raw_page.close()

                wait_for_supabase_client(page)
                page.evaluate("goHome()")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)
                home_order = page.evaluate(
                    """
                    [...document.querySelectorAll('.service-sidebar-head span, .service-type-row span')]
                      .map((node) => node.textContent.trim())
                    """
                )
                home_visibility_state = page.evaluate(
                    """
                    (() => {
                      const first = document.querySelector('.service-type-row');
                      const firstStyle = first ? getComputedStyle(first) : null;
                      const probe = document.createElement('span');
                      probe.style.position = 'absolute';
                      probe.style.background = 'var(--sidebar-active-bg)';
                      document.body.appendChild(probe);
                      const activeBackground = getComputedStyle(probe).backgroundColor;
                      probe.remove();
                      return {
                        hasActivities: Boolean(document.querySelector('.home-sidebar-card.activities')),
                        disabledSections: document.querySelectorAll('.home-sidebar-section--disabled').length,
                        activeCards: document.querySelectorAll('.service-type-row.active').length,
                        firstBackground: firstStyle?.backgroundColor || '',
                        activeBackground,
                        firstLooksActive: Boolean(firstStyle && firstStyle.backgroundColor === activeBackground)
                      };
                    })()
                    """
                )
                expected_home_order = ["예배", "최근 예배", "전체 예배", "역대 콘티", "다가오는 예배"]
                if (
                    home_order == expected_home_order
                    and not home_visibility_state["hasActivities"]
                    and home_visibility_state["disabledSections"] == 0
                    and home_visibility_state["activeCards"] <= 1
                    and not home_visibility_state["firstLooksActive"]
                ):
                    pass_("home-sidebar-hierarchy", json.dumps({"order": home_order, "visibility": home_visibility_state}, ensure_ascii=False))
                else:
                    fail("home-sidebar-hierarchy", json.dumps({"order": home_order, "visibility": home_visibility_state}, ensure_ascii=False))

                home_design_state = page.evaluate(
                    """
                    (() => {
                      const dashboard = document.querySelector('.service-dashboard');
                      const weekBoard = document.querySelector('.service-week-board');
                      const recentCards = [...document.querySelectorAll('.service-dashboard .service-week-card')];
                      return {
                        hasDashboard: Boolean(dashboard),
                        weekDays: weekBoard?.children.length || 0,
                        recentCards: recentCards.length,
                        text: dashboard?.innerText || '',
                        overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                      };
                    })()
                    """
                )
                if (
                    home_design_state["hasDashboard"]
                    and home_design_state["weekDays"] == 7
                    and home_design_state["recentCards"] > 0
                    and "최근 예배" in home_design_state["text"]
                    and "이번 주" in home_design_state["text"]
                    and home_design_state["overflow"] <= 2
                ):
                    pass_("home-design-shell", json.dumps(home_design_state, ensure_ascii=False))
                else:
                    fail("home-design-shell", json.dumps(home_design_state, ensure_ascii=False))

                page.evaluate("switchModule('service')")
                page.wait_for_function("() => document.body.dataset.module === 'service'", timeout=5000)
                page.locator('[data-service-setlist-archive]').first.click()
                page.wait_for_function("() => document.querySelector('.page-tab.active > span')?.textContent === '역대 콘티'", timeout=5000)
                archive_tab = page.evaluate("() => state.pageTabs[state.pageTabIndex]")
                if archive_tab["label"] == "역대 콘티" and archive_tab["snapshot"]["selectedServiceTypeId"] == "__setlist_archive":
                    pass_("setlist-archive-tab-title", archive_tab["label"])
                else:
                    fail("setlist-archive-tab-title", json.dumps(archive_tab, ensure_ascii=False))
                page.locator('[data-service-setlist-view="service"]').click()
                page.wait_for_function("() => document.querySelector('[data-service-setlist-view=service]')?.getAttribute('aria-pressed') === 'true'", timeout=5000)
                archive_groups = page.evaluate("""() => {
                  const entries = worshipSetlistArchiveEntries();
                  return ['date', 'service'].every(view => {
                    const groups = groupWorshipSetlistArchiveEntries(entries, view);
                    return groups.reduce((count, group) => count + group.entries.length, 0) === entries.length
                      && groups.every(group => group.entries.every(entry => group.key === (view === 'date'
                        ? worshipSetlistArchiveWeek(entry.source.service_date).key
                        : worshipAppServiceTypeId(entry.source.service_type_id) || '')));
                  });
                }""")
                if archive_groups:
                    pass_("setlist-archive-view-groups", "week/service grouping preserves all entries")
                else:
                    fail("setlist-archive-view-groups", "group membership or count mismatch")
                page.locator('[data-service-setlist-view="date"]').click()
                page.wait_for_function("() => document.querySelector('[data-service-setlist-view=date]')?.getAttribute('aria-pressed') === 'true'", timeout=5000)
                page.locator('[data-service-week]').first.click()
                page.wait_for_function("() => document.querySelector('.page-tab.active > span')?.textContent === '최근 예배'", timeout=5000)
                service_default_state = page.evaluate(
                    """
                    (() => ({
                    selectedTypeId: state.selectedServiceTypeId || '',
                    hasDashboard: Boolean(document.querySelector('.service-dashboard')),
                    hasAllList: Boolean(document.querySelector('.service-date-list--all')),
                    title: document.querySelector('.service-date-list-title')?.textContent.trim() || '',
                      activeWeekRows: document.querySelectorAll('[data-service-week].active').length,
                      activeListRows: document.querySelectorAll('[data-service-list].active').length,
                    }))()
                    """
                )
                if (
                    service_default_state["selectedTypeId"] == "__week"
                    and service_default_state["hasDashboard"]
                    and not service_default_state["hasAllList"]
                    and service_default_state["title"] == "최근 예배"
                    and service_default_state["activeWeekRows"] == 1
                    and service_default_state["activeListRows"] == 0
                ):
                    pass_("service-default-opens-week-board", json.dumps(service_default_state, ensure_ascii=False))
                else:
                    fail("service-default-opens-week-board", json.dumps(service_default_state, ensure_ascii=False))

                page.click("[data-service-list]")
                page.wait_for_function("() => state.selectedServiceTypeId === '__list'", timeout=5000)
                page.click('.nav-rail [data-home-module="service"]')
                page.wait_for_function("() => state.selectedServiceTypeId === '__week'", timeout=5000)
                service_rail_state = page.evaluate(
                    """
                    (() => ({
                      module: document.body.dataset.module,
                      selectedTypeId: state.selectedServiceTypeId || '',
                      selectedServiceId: state.selectedServiceId || '',
                      hasDashboard: Boolean(document.querySelector('.service-dashboard')),
                      activeWeekRows: document.querySelectorAll('[data-service-week].active').length,
                      activeListRows: document.querySelectorAll('[data-service-list].active').length,
                    }))()
                    """
                )
                if (
                    service_rail_state["module"] == "service"
                    and service_rail_state["selectedTypeId"] == "__week"
                    and service_rail_state["selectedServiceId"] == ""
                    and service_rail_state["hasDashboard"]
                    and service_rail_state["activeWeekRows"] == 1
                    and service_rail_state["activeListRows"] == 0
                ):
                    pass_("service-rail-click-opens-week-board", json.dumps(service_rail_state, ensure_ascii=False))
                else:
                    fail("service-rail-click-opens-week-board", json.dumps(service_rail_state, ensure_ascii=False))
                calendar_alternative_service_skip_state = page.evaluate(
                    """
                    (() => {
                      const previousCalendarData = state.calendarData;
                      try {
                        state.calendarData = [
                          { date: '2099-09-06', church_schedule: '청년부 야외예배' },
                          { date: '2099-09-13', church_schedule: '청소년부 문화예배' },
                          { date: '2099-09-20', church_schedule: '청년부 예배' },
                        ];
                        return {
                          youngAdultOutdoor: [...calendarSkippedServiceTypesForDate('2099-09-06')],
                          youthCulture: [...calendarSkippedServiceTypesForDate('2099-09-13')],
                          regularYoungAdult: [...calendarSkippedServiceTypesForDate('2099-09-20')],
                        };
                      } finally {
                        state.calendarData = previousCalendarData;
                      }
                    })()
                    """
                )
                if (
                    calendar_alternative_service_skip_state["youngAdultOutdoor"] == ["young-adult"]
                    and calendar_alternative_service_skip_state["youthCulture"] == ["youth"]
                    and calendar_alternative_service_skip_state["regularYoungAdult"] == []
                ):
                    pass_("calendar-alternative-service-skip", json.dumps(calendar_alternative_service_skip_state, ensure_ascii=False))
                else:
                    fail("calendar-alternative-service-skip", json.dumps(calendar_alternative_service_skip_state, ensure_ascii=False))
                page.evaluate("() => { resetHomeState(); render(); }")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)

                spacing_modules = ["home", "service", "presenter", "scripture", "praise", "calendar", "references"]
                module_spacing = []
                for module_id in spacing_modules:
                    page.evaluate("(moduleId) => switchModule(moduleId)", module_id)
                    page.wait_for_function("(moduleId) => document.body.dataset.module === moduleId", arg=module_id, timeout=5000)
                    page.wait_for_timeout(120)
                    module_spacing.append(
                        page.evaluate(
                            """
                            (moduleId) => {
                              const topbar = document.querySelector('.topbar')?.getBoundingClientRect();
                              const search = document.querySelector('.sidebar-search-wrap')?.getBoundingClientRect();
                              const first = document.querySelector('.detail-pane > *')?.getBoundingClientRect();
                              return {
                                module: moduleId,
                                searchTop: Math.round((search?.top || 0) - (topbar?.bottom || 0)),
                                firstTop: Math.round((first?.top || 0) - (topbar?.bottom || 0)),
                                overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                              };
                            }
                            """,
                            module_id,
                        )
                    )
                if all(item["searchTop"] == 0 and item["firstTop"] in {24, 25} and item["overflow"] <= 2 for item in module_spacing):
                    pass_("module-start-gutters", json.dumps(module_spacing, ensure_ascii=False))
                else:
                    fail("module-start-gutters", json.dumps(module_spacing, ensure_ascii=False))

                page.click('[data-home-module="scripture"]')
                page.wait_for_function("() => document.body.dataset.module === 'scripture'", timeout=5000)
                page.mouse.move(12, 200)
                topbar_state = page.evaluate(
                    """
                    (() => {
                      const tabs = [...document.querySelectorAll('.nav-rail .nav-rail-tab')];
                      const active = document.querySelector('.nav-rail .nav-rail-tab.active');
                      const activeIcon = active?.querySelector('svg');
                      const activeStyles = active ? getComputedStyle(active) : null;
                      const activeIconStyles = activeIcon ? getComputedStyle(activeIcon) : null;
                      const activeIconRect = activeIcon?.getBoundingClientRect();
                      const probe = document.createElement('span');
                      probe.style.position = 'absolute';
                      probe.style.color = 'var(--accent)';
                      document.body.appendChild(probe);
                      const expected = getComputedStyle(probe);
                      const expectedColor = expected.color;
                      const output = {
                        order: tabs.map((tab) => tab.getAttribute('aria-label') || ''),
                        active: active?.dataset.homeModule || '',
                        activeColor: activeStyles?.color || '',
                        expectedColor,
                        activeIconColor: activeIconStyles?.color || '',
                        activeIconWidth: Math.round(activeIconRect?.width || 0),
                        activeIconHeight: Math.round(activeIconRect?.height || 0),
                        activeIconStroke: activeIconStyles?.strokeWidth || '',
                        referencesIconRotation: (() => {
                          const icon = document.querySelector('.nav-rail [data-home-module="references"] svg');
                          if (!icon) return null;
                          const matrix = new DOMMatrixReadOnly(getComputedStyle(icon).transform);
                          const angle = Math.round(Math.atan2(matrix.b, matrix.a) * 180 / Math.PI);
                          return angle < 0 ? angle + 360 : angle;
                        })()
                      };
                      probe.remove();
                      return output;
                    })()
                    """
                )
                expected_topbar_order = ["예배", "말씀", "찬양", "교회력", "참고자료"]
                if (
                    topbar_state["order"] == expected_topbar_order
                    and topbar_state["active"] == "scripture"
                    and topbar_state["activeColor"] == topbar_state["expectedColor"]
                    and topbar_state["activeIconColor"] == topbar_state["expectedColor"]
                    and topbar_state["activeIconWidth"] == 16
                    and topbar_state["activeIconHeight"] == 16
                    and topbar_state["activeIconStroke"] == "1.5px"
                    and topbar_state["referencesIconRotation"] == 45
                ):
                    pass_("navigation-rail-order-active-style", json.dumps(topbar_state, ensure_ascii=False))
                else:
                    fail("navigation-rail-order-active-style", json.dumps(topbar_state, ensure_ascii=False))

                page.click('.nav-rail [data-home-module="scripture"]')
                nav_repeat_state = page.evaluate(
                    """() => ({
                      module: document.body.dataset.module,
                      collapsed: document.body.classList.contains('sidebar-collapsed')
                    })"""
                )
                if nav_repeat_state == {"module": "scripture", "collapsed": False}:
                    pass_("navigation-rail-does-not-toggle", json.dumps(nav_repeat_state, ensure_ascii=False))
                else:
                    fail("navigation-rail-does-not-toggle", json.dumps(nav_repeat_state, ensure_ascii=False))

                page.click("#brandNameHome")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)
                home_rail_state = page.evaluate(
                    """() => ({
                      module: document.body.dataset.module,
                      collapsed: document.body.classList.contains('sidebar-collapsed'),
                      active: document.querySelector('.nav-rail .nav-rail-tab.active')?.dataset.homeModule || '',
                      homeRailButton: Boolean(document.querySelector('.nav-rail [data-home-module="home"]'))
                    })"""
                )
                if home_rail_state == {"module": "home", "collapsed": False, "active": "", "homeRailButton": False}:
                    pass_("navigation-rail-home", json.dumps(home_rail_state, ensure_ascii=False))
                else:
                    fail("navigation-rail-home", json.dumps(home_rail_state, ensure_ascii=False))

                page.click('.nav-rail [data-home-module="scripture"]')
                page.wait_for_function("() => document.body.dataset.module === 'scripture'", timeout=5000)
                page.click("#brandNameHome")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)
                wordmark_state = page.evaluate(
                    """() => ({
                      module: document.body.dataset.module,
                      collapsed: document.body.classList.contains('sidebar-collapsed')
                    })"""
                )
                if wordmark_state == {"module": "home", "collapsed": False}:
                    pass_("wordmark-goes-home", json.dumps(wordmark_state, ensure_ascii=False))
                else:
                    fail("wordmark-goes-home", json.dumps(wordmark_state, ensure_ascii=False))

                page.evaluate("switchModule('scripture')")
                page.wait_for_function("() => document.body.dataset.module === 'scripture'", timeout=5000)
                page.hover(".page-tab")
                single_tab_close_before = page.locator(".page-tab-close").count()
                page.click(".page-tab-close")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)
                single_tab_close_state = page.evaluate(
                    """() => ({
                      module: document.body.dataset.module,
                      tabs: document.querySelectorAll('.page-tab').length,
                      closeButtons: document.querySelectorAll('.page-tab-close').length
                    })"""
                )
                if single_tab_close_before == 1 and single_tab_close_state == {"module": "home", "tabs": 1, "closeButtons": 0}:
                    pass_("single-nonhome-tab-close-goes-home", json.dumps(single_tab_close_state, ensure_ascii=False))
                else:
                    fail(
                        "single-nonhome-tab-close-goes-home",
                        json.dumps({"before": single_tab_close_before, "after": single_tab_close_state}, ensure_ascii=False),
                    )

                page_tab_style = page.evaluate(
                    """() => {
                      const tab = document.querySelector('.page-tab.active');
                      const add = document.querySelector('#pageTabAddBtn');
                      const icon = add?.querySelector('svg');
                      const tabStyle = tab ? getComputedStyle(tab) : null;
                      const addRect = add?.getBoundingClientRect();
                      const iconRect = icon?.getBoundingClientRect();
                      return {
                        tabWeight: Number(tabStyle?.fontWeight || 0),
                        addWidth: Math.round(addRect?.width || 0),
                        addHeight: Math.round(addRect?.height || 0),
                        iconWidth: Math.round(iconRect?.width || 0),
                        iconHeight: Math.round(iconRect?.height || 0)
                      };
                    }"""
                )
                if page_tab_style == {
                    "tabWeight": 700,
                    "addWidth": 40,
                    "addHeight": 40,
                    "iconWidth": 16,
                    "iconHeight": 16,
                }:
                    pass_("page-tab-visual-contract", json.dumps(page_tab_style, ensure_ascii=False))
                else:
                    fail("page-tab-visual-contract", json.dumps(page_tab_style, ensure_ascii=False))

                tab_reorder_state = page.evaluate(
                    """
                    (() => {
                      const probeTabs = [
                        newPageTab(homePageTabSnapshot()),
                        newPageTab({...homePageTabSnapshot(), module: 'scripture'}),
                        newPageTab({...homePageTabSnapshot(), module: 'calendar'})
                      ];
                      normalizePageTabsState(probeTabs, 1);
                      renderPageTabs();
                      refreshIcons();
                      const activeId = state.pageTabs[state.pageTabIndex].id;
                      const before = state.pageTabs.map(tab => tab.id);
                      const draggableTabs = document.querySelectorAll('.page-tab[draggable="true"]').length;
                      const addDraggable = document.querySelector('#pageTabAddBtn')?.draggable === true;
                      const moved = reorderPageTab(0, 3);
                      const after = state.pageTabs.map(tab => tab.id);
                      const persisted = JSON.parse(sessionStorage.getItem(MINDEX_TAB_STATE_STORAGE_KEY) || '{}');
                      const result = {
                        moved,
                        before,
                        after,
                        activePreserved: state.pageTabs[state.pageTabIndex]?.id === activeId,
                        persisted: (persisted.tabs || []).map(tab => tab.id),
                        draggableTabs,
                        addDraggable
                      };
                      normalizePageTabsState([], 0);
                      persistPageTabsState();
                      renderPageTabs();
                      refreshIcons();
                      return result;
                    })()
                    """
                )
                if (
                    tab_reorder_state["moved"]
                    and tab_reorder_state["after"] == tab_reorder_state["before"][1:] + tab_reorder_state["before"][:1]
                    and tab_reorder_state["activePreserved"]
                    and tab_reorder_state["persisted"] == tab_reorder_state["after"]
                    and tab_reorder_state["draggableTabs"] == 3
                    and not tab_reorder_state["addDraggable"]
                ):
                    pass_("page-tab-drag-reorder", json.dumps(tab_reorder_state, ensure_ascii=False))
                else:
                    fail("page-tab-drag-reorder", json.dumps(tab_reorder_state, ensure_ascii=False))

                page.evaluate("switchModule('calendar')")
                page.wait_for_function("() => document.body.dataset.module === 'calendar'", timeout=5000)
                page.wait_for_selector(".cal-tab.active", timeout=15000)
                calendar_state = page.evaluate(
                    """
                    (() => ({
                      placeholder: document.querySelector('#searchInput')?.placeholder || '',
                      hasCalendar: Boolean(document.querySelector('.cal-view') || document.querySelector('.empty-detail')),
                      title: document.querySelector('.cal-title')?.textContent.trim() || '',
                      activeTab: document.querySelector('.cal-tab.active')?.textContent.trim() || '',
                      headerBorder: getComputedStyle(document.querySelector('.cal-header')).borderBottomWidth,
                      headerMinHeight: Math.round(document.querySelector('.cal-header')?.getBoundingClientRect().height || 0),
                      titleFontSize: getComputedStyle(document.querySelector('.cal-title')).fontSize,
                      subtitleFontSize: getComputedStyle(document.querySelector('.cal-subtitle')).fontSize,
                      tabHeight: Math.round(document.querySelector('.cal-tab.active')?.getBoundingClientRect().height || 0),
                      departmentHeaders: [...document.querySelectorAll('.cal-table thead th')]
                        .map((node) => node.textContent.replace(/\\s+/g, ' ').trim())
                        .map((text) => text.normalize('NFC'))
                        .filter((text) => text.includes('부')),
                      widths: [...document.querySelectorAll('.cal-table thead th')]
                        .map((node) => Math.round(node.getBoundingClientRect().width)),
                      wrapperWidth: Math.round(document.querySelector('.cal-table-wrap')?.clientWidth || 0),
                      tableClass: document.querySelector('.cal-table')?.className || '',
                      tableScrollWidth: Math.round(document.querySelector('.cal-table')?.scrollWidth || 0),
                      hasYearEndRow: document.body.textContent.includes('송구영신예배'),
                      hasFootnote: document.querySelector('.cal-footnote')?.textContent.includes('부활절 기간 동안 사도행전을 읽는 것으로') || false,
                      footnoteHasBreak: Boolean(document.querySelector('.cal-footnote br')),
                      overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                    }))()
                    """
                )
                expected_department_headers = [
                    "유치부 기도자",
                    "어린이부 기도자",
                    "청소년부 기도자",
                    "청소년부 봉헌기도자",
                    "청소년부 설교자",
                    "청년부 기도자",
                ]
                if (
                    calendar_state["placeholder"] == "검색..."
                    and calendar_state["hasCalendar"]
                    and calendar_state["title"] == "교회력"
                    and calendar_state["activeTab"] == "부서 일과"
                    and calendar_state["headerBorder"] == "1px"
                    and 44 <= calendar_state["headerMinHeight"] <= 60
                    and calendar_state["titleFontSize"] == "20px"
                    and calendar_state["subtitleFontSize"] == "12px"
                    and calendar_state["tabHeight"] == 28
                    and calendar_state["departmentHeaders"] == expected_department_headers
                    and "cal-table--departments" in calendar_state["tableClass"]
                    and 0 <= calendar_state["tableScrollWidth"] - calendar_state["wrapperWidth"] <= 32
                    and calendar_state["widths"][4] >= 90
                    and min(calendar_state["widths"][3:]) >= 90
                    and calendar_state["hasYearEndRow"]
                    and calendar_state["hasFootnote"]
                    and not calendar_state["footnoteHasBreak"]
                    and calendar_state["overflow"] <= 2
                ):
                    pass_("calendar-utility-shell", json.dumps(calendar_state, ensure_ascii=False))
                else:
                    fail("calendar-utility-shell", json.dumps(calendar_state, ensure_ascii=False))

                page.click('[data-calendar-detail-tab="lectionary"]')
                calendar_lectionary_state = page.evaluate(
                    """
                    (() => ({
                      activeTab: document.querySelector('.cal-tab.active')?.textContent.trim() || '',
                      headers: [...document.querySelectorAll('.cal-table thead th')]
                        .map((node) => node.textContent.replace(/\\s+/g, ' ').trim())
                        .slice(-5),
                      widths: [...document.querySelectorAll('.cal-table thead th')]
                        .map((node) => Math.round(node.getBoundingClientRect().width)),
                      wrapperWidth: Math.round(document.querySelector('.cal-table-wrap')?.clientWidth || 0),
                      tableClass: document.querySelector('.cal-table')?.className || '',
                      tableScrollWidth: Math.round(document.querySelector('.cal-table')?.scrollWidth || 0),
                      overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                    }))()
                    """
                )
                expected_lectionary_headers = ["색깔", "첫째 읽기", "시편", "둘째 읽기", "복음서"]
                if (
                    calendar_lectionary_state["activeTab"] == "성서일과"
                    and calendar_lectionary_state["headers"] == expected_lectionary_headers
                    and "cal-table--lectionary" in calendar_lectionary_state["tableClass"]
                    and abs(calendar_lectionary_state["tableScrollWidth"] - calendar_lectionary_state["wrapperWidth"]) <= 2
                    and min(calendar_lectionary_state["widths"][3:]) >= 118
                    and calendar_lectionary_state["overflow"] <= 2
                ):
                    pass_("calendar-lectionary-tab", json.dumps(calendar_lectionary_state, ensure_ascii=False))
                else:
                    fail("calendar-lectionary-tab", json.dumps(calendar_lectionary_state, ensure_ascii=False))

                page.evaluate("switchModule('references')")
                page.wait_for_function("() => document.body.dataset.module === 'references'", timeout=5000)
                references_state = page.evaluate(
                    """
                    (() => ({
                      placeholder: document.querySelector('#searchInput')?.placeholder || '',
                      hasReferences: Boolean(document.querySelector('.references-shell') || document.querySelector('.empty-detail')),
                      title: document.querySelector('.references-shell .editor-title h2')?.textContent.trim() || '',
                      summary: document.querySelector('.references-shell .utility-summary')?.textContent.trim() || '',
                      headerBorder: getComputedStyle(document.querySelector('.references-shell .editor-head')).borderBottomWidth,
                      headerMinHeight: Math.round(document.querySelector('.references-shell .editor-head')?.getBoundingClientRect().height || 0),
                      titleFontSize: getComputedStyle(document.querySelector('.references-shell .editor-title h2')).fontSize,
                      summaryFontSize: getComputedStyle(document.querySelector('.references-shell .utility-summary')).fontSize,
                      groupToolGap: (() => {
                        const title = document.querySelector('.reference-group-head h3');
                        const tools = document.querySelector('.reference-group-tools');
                        if (!title || !tools) return null;
                        return Math.round(tools.getBoundingClientRect().left - title.getBoundingClientRect().right);
                      })(),
                      firstCardWidth: Math.round(document.querySelector('.reference-card')?.getBoundingClientRect().width || 0),
                      groupWithinGrid: (() => {
                        const group = document.querySelector('.reference-group');
                        const grid = document.querySelector('.reference-link-grid');
                        if (!group || !grid) return true;
                        return group.getBoundingClientRect().right <= grid.getBoundingClientRect().right + 2;
                      })(),
                      overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                    }))()
                    """
                )
                if (
                    references_state["placeholder"] == "검색..."
                    and references_state["hasReferences"]
                    and references_state["title"] == "참고자료"
                    and "링크" in references_state["summary"]
                    and references_state["headerBorder"] == "1px"
                    and 44 <= references_state["headerMinHeight"] <= 60
                    and references_state["titleFontSize"] == "20px"
                    and references_state["summaryFontSize"] == "12px"
                    and references_state["groupToolGap"] is not None
                    and 6 <= references_state["groupToolGap"] <= 16
                    and 0 < references_state["firstCardWidth"] <= 370
                    and references_state["groupWithinGrid"]
                    and references_state["overflow"] <= 2
                ):
                    pass_("references-utility-shell", json.dumps(references_state, ensure_ascii=False))
                else:
                    fail("references-utility-shell", json.dumps(references_state, ensure_ascii=False))

                reference_search_state = page.evaluate(
                    """
                    (() => ({
                      title: document.querySelector('.reference-card strong')?.textContent.trim() || '',
                      before: document.querySelectorAll('.reference-card').length
                    }))()
                    """
                )
                if reference_search_state["title"]:
                    page.fill("#searchInput", reference_search_state["title"])
                    page.wait_for_function(
                        """
                        () => !document.querySelector('.global-search-section')
                          && document.querySelector('.references-shell')
                          && document.querySelectorAll('.reference-card').length > 0
                        """,
                        timeout=5000,
                    )
                    reference_search_state.update(page.evaluate(
                        """
                        () => ({
                          after: document.querySelectorAll('.reference-card').length,
                          globalSections: document.querySelectorAll('.global-search-section').length
                        })
                        """
                    ))
                    if 0 < reference_search_state["after"] <= reference_search_state["before"] and reference_search_state["globalSections"] == 0:
                        pass_("references-local-search", json.dumps(reference_search_state, ensure_ascii=False))
                    else:
                        fail("references-local-search", json.dumps(reference_search_state, ensure_ascii=False))
                    page.press("#searchInput", "Enter")
                    reference_search_state["moduleAfterEnter"] = page.evaluate("() => document.body.dataset.module || ''")
                    if reference_search_state["moduleAfterEnter"] != "references":
                        fail("references-search-enter", json.dumps(reference_search_state, ensure_ascii=False))
                    else:
                        pass_("references-search-enter", json.dumps(reference_search_state, ensure_ascii=False))
                    page.fill("#searchInput", "")

                page.click('[data-home-module="service"]')
                wait_for_service_data(page)
                wait_for_module_data(page, "service")
                snapshot = get_app_snapshot(page)
                if snapshot.get("serviceError") or snapshot.get("connectionError"):
                    fail("service-data-load", json.dumps(snapshot, ensure_ascii=False))
                elif snapshot.get("serviceTypes", 0) > 0 and snapshot.get("services", 0) >= 0:
                    pass_("service-data-load", json.dumps(snapshot, ensure_ascii=False))
                else:
                    fail("service-data-load", json.dumps(snapshot, ensure_ascii=False))

                service_save_reentry = page.evaluate(
                    """
                    async () => {
                      const originalClient = state.client;
                      const originalServices = state.services;
                      const originalSaving = state.saving;
                      const originalDirtyService = state.dirty.service;
                      const originalActivePromise = activeServiceSavePromise;
                      const service = { id: '__smoke_service_save_reentry__', type_id: 'sunday-main', date: '2026-08-23', _isExpected: true };
                      const startedAt = performance.now();
                      try {
                        state.client = state.client || {};
                        state.services = [service, ...state.services.filter((item) => item.id !== service.id)];
                        state.saving = true;
                        state.dirty.service = true;
                        activeServiceSavePromise = new Promise((resolve) => {
                          window.setTimeout(() => {
                            state.saving = false;
                            resolve(true);
                          }, 24);
                        });
                        const saved = await saveService(service.id, { silent: true, renderAfterSave: false });
                        return {
                          saved,
                          waitedMs: Math.round(performance.now() - startedAt),
                          saving: state.saving,
                          activeCleared: activeServiceSavePromise === null,
                        };
                      } finally {
                        state.client = originalClient;
                        state.services = originalServices;
                        state.saving = originalSaving;
                        state.dirty.service = originalDirtyService;
                        activeServiceSavePromise = originalActivePromise;
                        updateSaveState();
                      }
                    }
                    """
                )
                if (
                    service_save_reentry["saved"]
                    and service_save_reentry["waitedMs"] >= 16
                    and service_save_reentry["saving"] is False
                    and service_save_reentry["activeCleared"]
                ):
                    pass_("service-save-reentry-waits", json.dumps(service_save_reentry, ensure_ascii=False))
                else:
                    fail("service-save-reentry-waits", json.dumps(service_save_reentry, ensure_ascii=False))

                page.fill("#searchInput", "창세기")
                page.wait_for_selector(".global-search-section", timeout=5000)
                global_search_state = page.evaluate(
                    """
                    (() => ({
                      module: document.body.dataset.module || '',
                      headings: [...document.querySelectorAll('.global-search-heading')]
                        .map((node) => node.textContent.trim()),
                      scriptureResults: document.querySelectorAll('[data-global-book-code], [data-global-bible-text]').length,
                      serviceLocalRows: document.querySelectorAll('.service-type-row, .service-sidebar-card').length,
                      overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                    }))()
                    """
                )
                if (
                    global_search_state["module"] == "service"
                    and "말씀" in global_search_state["headings"]
                    and global_search_state["scriptureResults"] > 0
                    and global_search_state["serviceLocalRows"] == 0
                    and global_search_state["overflow"] <= 2
                ):
                    pass_("global-search-cross-module", json.dumps(global_search_state, ensure_ascii=False))
                else:
                    fail("global-search-cross-module", json.dumps(global_search_state, ensure_ascii=False))

                global_search_deep_state = page.evaluate(
                    """
                    (() => {
                      const originalSongs = state.songs;
                      const originalSearch = state.search;
                      const originalInputValue = refs.searchInput?.value || "";
                      const syntheticSong = {
                        id: "__smoke_global_search_song__",
                        title: "통합검색 대표 제목",
                        hymn_no: "",
                        subtitle: "숨은 부제 검색어",
                        original_title: "Original Integrated Search",
                        scripture: ["요 3:16"],
                        metadata: { artist: "검색 아티스트" },
                        versions: [{
                          id: "__smoke_global_search_version__",
                          version_label: "대표 버전",
                          raw_section_name: "원제 섹션",
                          metadata: { album: "검색 앨범" },
                          forms: [{ part_type: "Verse", lyrics: "첫 가사 통합검색 문장" }]
                        }]
                      };
                      const syntheticHymn = {
                        id: "__smoke_hymn_430__",
                        title: "주와 같이 길 가는 것",
                        hymn_no: "430",
                        subtitle: "",
                        original_title: "",
                        versions: []
                      };
                      const directMatches = {
                        subtitle: Boolean(getSongSearchMatch(syntheticSong, getSearchTokens("숨은 부제"))),
                        originalTitle: Boolean(getSongSearchMatch(syntheticSong, getSearchTokens("Original Integrated"))),
                        firstLyrics: Boolean(getSongSearchMatch(syntheticSong, getSearchTokens("첫 가사 통합검색"))),
                        initials: Boolean(getSongSearchMatch(syntheticSong, getSearchTokens("ㅌㅎㄱㅅ"))),
                      };
                      state.songs = [syntheticSong, syntheticHymn, ...originalSongs];
                      clearSearchCaches();
                      state.search = "숨은 부제";
                      if (refs.searchInput) refs.searchInput.value = state.search;
                      renderSongList();
                      const rendered = {
                        headings: [...document.querySelectorAll(".global-search-heading")].map((node) => node.textContent.trim()),
                        songResult: Boolean(document.querySelector('[data-global-song-id="__smoke_global_search_song__"]')),
                        songMeta: document.querySelector('[data-global-song-id="__smoke_global_search_song__"] .song-meta-line')?.textContent.trim() || '',
                      };
                      const scriptureReferences = normalizeServiceScriptureReferenceList("요3:16~17, 18");
                      const complexScriptureReferences = {
                        sameChapterComma: normalizeServiceScriptureReferenceList("마 13:31–33, 44–50"),
                        consecutiveComma: normalizeServiceScriptureReferenceList("롬 8:22,23"),
                        consecutiveCommaFormatted: formatServiceScriptureReferenceList("롬 8:22,23"),
                        crossBookSemicolon: normalizeServiceScriptureReferenceList("요 15:9; 롬 5:7–8"),
                        sameBookSemicolon: normalizeServiceScriptureReferenceList("느 6:15-19; 7:1-5"),
                        sameBookSemicolonFormatted: formatServiceScriptureReferenceList("느 6:15-19; 7:1-5"),
                        longDash: normalizeServiceScriptureReferenceList("마 13:31—33, 44—50"),
                        formatted: formatServiceScriptureReferenceList("마 13:31–33, 44–50"),
                        displayTitle: worshipElementDisplayTitle(
                          { element_type: "scripture_body", title: "요 15:9, 롬 5:7–8", scripture_reference: "요 15:9" },
                          { section_key: "sermon", title: "설교" },
                          { label: "설교 본문" },
                          { scriptureReferences: ["요 15:9", "롬 5:7–8"] },
                        ),
                      };
                      const hymnPreparation = {
                        bareLeading: parsePresenterPreparationHymnHint("430장 주와 같이 길 가는 것"),
                        bareTrailing: parsePresenterPreparationHymnHint("주와 같이 길 가는 것 430장"),
                        prefixedOnly: parsePresenterPreparationHymnHint("찬 430"),
                        splitBareLeading: stripHymnNo("430장 주와 같이 길 가는 것"),
                        splitPrefixedOnly: stripHymnNo("찬 430"),
                        resolvedId: resolvePresenterPreparationSong(
                          "430장 주와 같이 길 가는 것",
                          { label: "찬양 1" },
                          { type_id: "sunday-first" },
                        )?.id || "",
                        fallbackTitle: stripHymnNo(presenterPreparationSongContent("430장 없는 찬송 제목")).title.trim(),
                      };
                      state.songs = originalSongs;
                      clearSearchCaches();
                      state.search = originalSearch;
                      if (refs.searchInput) refs.searchInput.value = originalInputValue;
                      renderSongList();
                      return { directMatches, rendered, scriptureReferences, complexScriptureReferences, hymnPreparation };
                    })()
                    """
                )
                if (
                    all(global_search_deep_state["directMatches"].values())
                    and "찬양" in global_search_deep_state["rendered"]["headings"]
                    and global_search_deep_state["rendered"]["songResult"]
                    and "부제 일치" in global_search_deep_state["rendered"]["songMeta"]
                    and global_search_deep_state["scriptureReferences"] == ["요한복음 3:16–18"]
                    and global_search_deep_state["complexScriptureReferences"] == {
                        "sameChapterComma": ["마태복음 13:31–33", "마태복음 13:44–50"],
                        "consecutiveComma": ["로마서 8:22–23"],
                        "consecutiveCommaFormatted": "로마서 8:22–23",
                        "crossBookSemicolon": ["요한복음 15:9", "로마서 5:7–8"],
                        "sameBookSemicolon": ["느헤미야 6:15–19", "느헤미야 7:1–5"],
                        "sameBookSemicolonFormatted": "느헤미야 6:15–19; 7:1–5",
                        "longDash": ["마태복음 13:31–33", "마태복음 13:44–50"],
                        "formatted": "마태복음 13:31–33, 44–50",
                        "displayTitle": "요한복음 15:9; 로마서 5:7–8",
                    }
                    and global_search_deep_state["hymnPreparation"] == {
                        "bareLeading": {"title": "주와 같이 길 가는 것", "hymnNo": "430"},
                        "bareTrailing": {"title": "주와 같이 길 가는 것", "hymnNo": "430"},
                        "prefixedOnly": {"title": "", "hymnNo": "430"},
                        "splitBareLeading": {"no": "430", "title": "주와 같이 길 가는 것"},
                        "splitPrefixedOnly": {"no": "430", "title": ""},
                        "resolvedId": "__smoke_hymn_430__",
                        "fallbackTitle": "없는 찬송 제목",
                    }
                ):
                    pass_("global-search-deep-matching", json.dumps(global_search_deep_state, ensure_ascii=False))
                else:
                    fail("global-search-deep-matching", json.dumps(global_search_deep_state, ensure_ascii=False))

                page.evaluate(
                    """
                    async () => {
                      await switchModule('service');
                      state.search = '';
                      refs.searchInput.value = '';
                      renderServiceList();
                    }
                    """
                )
                page.wait_for_function("() => document.body.dataset.module === 'service'", timeout=5000)
                page.wait_for_selector(".service-sidebar-head", timeout=5000)

                service_sidebar_gap = page.evaluate(
                    """
                    (() => {
                      const search = document.querySelector('.sidebar-search-wrap')?.getBoundingClientRect();
                      const headNode = document.querySelector('.service-sidebar-head');
                      const head = headNode?.getBoundingClientRect();
                      const label = headNode?.querySelector('span')?.getBoundingClientRect();
                      const headStyles = headNode ? getComputedStyle(headNode) : null;
                      const sidebar = document.querySelector('.sidebar')?.getBoundingClientRect();
                      return {
                        gap: search && head ? Math.round(head.top - search.bottom) : 0,
                        headHeight: Math.round(head?.height || 0),
                        headLineHeight: headStyles?.lineHeight || '',
                        headLeft: sidebar && head ? Math.round(head.left - sidebar.left) : 0,
                        labelLeft: sidebar && label ? Math.round(label.left - sidebar.left) : 0
                      };
                    })()
                    """
                )
                if (
                    service_sidebar_gap["gap"] == 20
                    and service_sidebar_gap["headHeight"] < 18
                    and service_sidebar_gap["headLeft"] == 5
                    and service_sidebar_gap["labelLeft"] == 15
                ):
                    pass_("service-sidebar-section-label-gap", json.dumps(service_sidebar_gap, ensure_ascii=False))
                else:
                    fail("service-sidebar-section-label-gap", json.dumps(service_sidebar_gap, ensure_ascii=False))

                page.evaluate("switchModule('service')")
                page.wait_for_function("() => document.body.dataset.module === 'service'", timeout=5000)
                upcoming_service_sidebar = page.evaluate(
                    """
                    (() => {
                      const today = new Date();
                      today.setHours(0, 0, 0, 0);
                      const cards = [...document.querySelectorAll('.service-sidebar-section--recent [data-service-id]')];
                      const services = cards
                        .map((card) => state.services.find((service) => service.id === card.dataset.serviceId))
                        .filter(Boolean);
                      const dates = services.map((service) => {
                        const value = parseLocalDate(service.date);
                        value.setHours(0, 0, 0, 0);
                        return value.getTime();
                      });
                      return {
                        heading: document.querySelector('.service-sidebar-section--recent .service-sidebar-head span')?.textContent.trim() || '',
                        count: services.length,
                        dates,
                        isAscending: dates.every((date, index) => index === 0 || dates[index - 1] <= date),
                        includesOnlyTodayOrLater: dates.every((date) => date >= today.getTime()),
                      };
                    })()
                    """
                )
                if (
                    upcoming_service_sidebar["heading"] == "다가오는 예배"
                    and upcoming_service_sidebar["count"] > 0
                    and upcoming_service_sidebar["isAscending"]
                    and upcoming_service_sidebar["includesOnlyTodayOrLater"]
                ):
                    pass_("upcoming-service-sidebar-order", json.dumps(upcoming_service_sidebar, ensure_ascii=False))
                else:
                    fail("upcoming-service-sidebar-order", json.dumps(upcoming_service_sidebar, ensure_ascii=False))

                service_time_sort_order = page.evaluate(
                    """
                    (() => sortServicesByDate([
                      { id: 'afternoon', type_id: 'sunday-afternoon', date: '2099-08-16' },
                      { id: 'youth', type_id: 'youth', date: '2099-08-16' },
                      { id: 'first', type_id: 'sunday-first', date: '2099-08-16' },
                      { id: 'children', type_id: 'children', date: '2099-08-16' },
                      { id: 'main', type_id: 'sunday-main', date: '2099-08-16' },
                      { id: 'second', type_id: 'sunday-second', date: '2099-08-16' },
                      { id: 'young-adult', type_id: 'young-adult', date: '2099-08-16' },
                    ]).map((service) => service.id))()
                    """
                )
                if service_time_sort_order == ["first", "second", "main", "children", "youth", "young-adult", "afternoon"]:
                    pass_("service-time-sort-order", json.dumps(service_time_sort_order, ensure_ascii=False))
                else:
                    fail("service-time-sort-order", json.dumps(service_time_sort_order, ensure_ascii=False))

                sunday_auto_targets = page.evaluate(
                    """
                    (() => {
                      const defaultTargets = autoUpcomingPublicServiceTargets(new Date('2099-08-16T12:00:00'))
                        .map((target) => `${target.typeId}:${target.date}`);
                      const sundayEveningTargets = autoUpcomingPublicServiceTargets(new Date('2099-08-16T16:00:00'))
                        .map((target) => `${target.typeId}:${target.date}`);
                      const childrenType = serviceTypeById('children');
                      const originalConfig = { ...(childrenType?._worshipConfig || {}) };
                      if (childrenType) childrenType._worshipConfig = { ...originalConfig, autoScheduleEnabled: true };
                      const enabledTargets = autoUpcomingPublicServiceTargets(new Date('2099-08-16T12:00:00'))
                        .map((target) => `${target.typeId}:${target.date}`);
                      if (childrenType) childrenType._worshipConfig = originalConfig;
                      return { defaultTargets, sundayEveningTargets, enabledTargets };
                    })()
                    """
                )
                if (
                    "children:2099-08-16" not in sunday_auto_targets["defaultTargets"]
                    and "children:2099-08-16" in sunday_auto_targets["enabledTargets"]
                    and "sunday-first:2099-08-16" in sunday_auto_targets["defaultTargets"]
                    and "sunday-first:2099-08-16" not in sunday_auto_targets["sundayEveningTargets"]
                    and "sunday-first:2099-08-23" in sunday_auto_targets["sundayEveningTargets"]
                    and "wednesday:2099-08-19" in sunday_auto_targets["sundayEveningTargets"]
                    and "friday:2099-08-21" in sunday_auto_targets["sundayEveningTargets"]
                ):
                    pass_("children-auto-targets-config-opt-in", json.dumps(sunday_auto_targets, ensure_ascii=False))
                else:
                    fail("children-auto-targets-config-opt-in", json.dumps(sunday_auto_targets, ensure_ascii=False))

                page.evaluate("goHome()")
                page.wait_for_function("() => document.body.dataset.module === 'home'", timeout=5000)
                home_recent_service_sidebar = page.evaluate(
                    """
                    (() => {
                      const today = new Date();
                      today.setHours(0, 0, 0, 0);
                      const end = new Date(today);
                      end.setDate(today.getDate() + 6);
                      const cards = [...document.querySelectorAll('.service-sidebar-section--recent [data-service-id]')];
                      const services = cards
                        .map((card) => state.services.find((service) => service.id === card.dataset.serviceId))
                        .filter(Boolean);
                      const dates = services.map((service) => {
                        const value = parseLocalDate(service.date);
                        value.setHours(0, 0, 0, 0);
                        return value.getTime();
                      });
                      return {
                        heading: document.querySelector('.service-sidebar-section--recent .service-sidebar-head span')?.textContent.trim() || '',
                        count: services.length,
                        dates,
                        isAscending: dates.every((date, index) => index === 0 || dates[index - 1] <= date),
                        staysWithinUpcomingWeek: dates.every((date) => date >= today.getTime() && date <= end.getTime()),
                      };
                    })()
                    """
                )
                if (
                    home_recent_service_sidebar["heading"] == "다가오는 예배"
                    and home_recent_service_sidebar["count"] > 0
                    and home_recent_service_sidebar["isAscending"]
                    and home_recent_service_sidebar["staysWithinUpcomingWeek"]
                ):
                    pass_("home-sidebar-upcoming-week-services", json.dumps(home_recent_service_sidebar, ensure_ascii=False))
                else:
                    fail("home-sidebar-upcoming-week-services", json.dumps(home_recent_service_sidebar, ensure_ascii=False))

                home_visible_service_previews = page.evaluate(
                    """
                    (() => {
                      const visibleIds = [...document.querySelectorAll('.service-week-card[data-service-id], .service-date-card[data-service-id]')]
                        .map((card) => card.dataset.serviceId)
                        .filter(Boolean);
                      const uniqueIds = [...new Set(visibleIds)];
                      const previewable = uniqueIds
                        .map((id) => {
                          const service = state.services.find((item) => item.id === id) || {};
                          const items = state.serviceItems[id] || [];
                          const sermonTitle = items.find((item) => isPresenterPreparationSermonTitleItem(item));
                          return {
                            id,
                            type: worshipAppServiceTypeId(service.type_id),
                            hasSermonTitle: Boolean(String(sermonTitle?.raw_title || '').trim()),
                            preview: serviceItemPreview(id),
                            loaded: state.loadedWorshipServiceIds?.has(id) || false,
                          };
                        })
                        .filter((entry) => entry.hasSermonTitle);
                      return {
                        visibleCount: uniqueIds.length,
                        previewable,
                        previewableCount: previewable.length,
                        structuredPreviews: [...document.querySelectorAll('.service-card-sermon-preview')]
                          .filter((node) => node.querySelector('.service-card-sermon-title') && node.querySelector('.service-card-sermon-reference'))
                          .length,
                        allPreviewableShown: previewable.every((entry) => entry.loaded && Boolean(entry.preview)),
                      };
                    })()
                    """
                )
                if (
                    home_visible_service_previews["visibleCount"] > 0
                    and (
                        home_visible_service_previews["previewableCount"] == 0
                        or home_visible_service_previews["structuredPreviews"] > 0
                    )
                    and home_visible_service_previews["allPreviewableShown"]
                ):
                    pass_("home-visible-service-previews-loaded", json.dumps(home_visible_service_previews, ensure_ascii=False))
                else:
                    fail("home-visible-service-previews-loaded", json.dumps(home_visible_service_previews, ensure_ascii=False))

                page.locator("[data-service-list]").first.click()
                page.wait_for_selector(".service-date-list", timeout=5000)
                service_gutter = page.evaluate(
                    """
                    (() => {
                      const detail = document.querySelector('.detail-pane')?.getBoundingClientRect();
                      const list = document.querySelector('.service-date-list')?.getBoundingClientRect();
                      const title = document.querySelector('.service-date-list-title')?.getBoundingClientRect();
                      const styles = getComputedStyle(document.querySelector('.service-date-list'));
                      return {
                        listLeft: Math.round((list?.left || 0) - (detail?.left || 0)),
                        titleLeft: Math.round((title?.left || 0) - (detail?.left || 0)),
                        paddingLeft: Math.round(parseFloat(styles.paddingLeft)),
                        hasGroups: Boolean(document.querySelector('.service-list-groups')),
                        overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                      };
                    })()
                    """
                )
                if (
                    service_gutter["listLeft"] in {24, 25}
                    and service_gutter["titleLeft"] in {24, 25}
                    and service_gutter["paddingLeft"] == 0
                    and service_gutter["hasGroups"]
                    and service_gutter["overflow"] <= 2
                ):
                    pass_("service-date-list-gutter", json.dumps(service_gutter, ensure_ascii=False))
                else:
                    fail("service-date-list-gutter", json.dumps(service_gutter, ensure_ascii=False))

                friday_family_grouping = page.evaluate(
                    """
                    (() => {
                      const blocks = [...document.querySelectorAll('.service-list-type-block')].map((block) => ({
                        title: block.querySelector('.service-list-type-open strong')?.textContent.trim() || '',
                        cardTypes: [...block.querySelectorAll('.service-date-card-type')].map((node) => node.textContent.trim()),
                        notes: [...block.querySelectorAll('.service-date-card-note')].map((node) => node.textContent.trim()).filter(Boolean),
                      }));
                      const friday = blocks.find((block) => block.title === '금요예배') || {};
                      return {
                        titles: blocks.map((block) => block.title),
                        fridayCardTypes: friday.cardTypes || [],
                        fridayNotes: friday.notes || [],
                        hasFridayFamily: Boolean(friday.title),
                        splitFridayTitles: blocks
                          .map((block) => block.title)
                          .filter((title) => ['금요기도회', '월삭예배', '삼삼오오예배'].includes(title)),
                      };
                    })()
                    """
                )
                if (
                    friday_family_grouping["hasFridayFamily"]
                    and friday_family_grouping["splitFridayTitles"] == []
                    and "금요기도회" in friday_family_grouping["fridayCardTypes"]
                    and "월삭예배" in friday_family_grouping["fridayCardTypes"]
                    and "삼삼오오예배" in friday_family_grouping["fridayCardTypes"]
                ):
                    pass_("service-list-friday-family-grouping", json.dumps(friday_family_grouping, ensure_ascii=False))
                else:
                    fail("service-list-friday-family-grouping", json.dumps(friday_family_grouping, ensure_ascii=False))

                page.evaluate(
                    """
                    (() => {
                      renderServiceTemplatesDetail();
                    })()
                    """
                )
                page.wait_for_selector(".svc-template-card, .svc-template-level-card", timeout=5000)
                template_gutter = page.evaluate(
                    """
                    (() => {
                      const detail = document.querySelector('.detail-pane')?.getBoundingClientRect();
                      const root = document.querySelector('.service-templates')?.getBoundingClientRect();
                      const title = document.querySelector('.service-templates .service-date-list-title')?.getBoundingClientRect();
                      const grid = document.querySelector('.svc-template-level-grid, .svc-template-draft-grid')?.getBoundingClientRect();
                      const styles = getComputedStyle(document.querySelector('.service-templates'));
                      return {
                        rootLeft: Math.round((root?.left || 0) - (detail?.left || 0)),
                        titleLeft: Math.round((title?.left || 0) - (detail?.left || 0)),
                        gridLeft: Math.round((grid?.left || 0) - (detail?.left || 0)),
                        paddingLeft: Math.round(parseFloat(styles.paddingLeft)),
                        overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                      };
                    })()
                    """
                )
                if (
                    template_gutter["rootLeft"] in {24, 25}
                    and template_gutter["titleLeft"] in {24, 25}
                    and template_gutter["gridLeft"] in {24, 25}
                    and template_gutter["paddingLeft"] == 0
                    and template_gutter["overflow"] <= 2
                ):
                    pass_("service-template-gutter", json.dumps(template_gutter, ensure_ascii=False))
                else:
                    fail("service-template-gutter", json.dumps(template_gutter, ensure_ascii=False))

                template_mode = page.evaluate(
                    """
                    () => document.querySelector('.svc-template-card') ? 'classic' : 'worship'
                    """
                )
                if template_mode == "classic":
                    page.evaluate(
                        """
                        (() => {
                          const card = [...document.querySelectorAll('.svc-template-card')]
                            .find((item) => item.querySelector('.svc-template-step-row'));
                          if (card) card.open = true;
                        })()
                        """
                    )
                    page.wait_for_function("() => document.querySelector('.svc-template-card[open] .svc-template-step-row')", timeout=5000)
                    template_terms = page.evaluate(
                        """
                        (() => {
                          const root = [...document.querySelectorAll('.svc-template-card[open]')]
                            .find((item) => item.querySelector('.svc-template-step-row')) || document;
                          const row = root.querySelector('.svc-template-step-row') || root;
                          const fieldLabels = [...row.querySelectorAll('.svc-template-step-field small')];
                          const headerLabels = [...root.querySelectorAll('.svc-template-step-header span')].slice(1, 7);
                          return {
                            mode: 'classic',
                            labels: (fieldLabels.length ? fieldLabels : headerLabels)
                              .slice(0, 6)
                              .map((node) => node.textContent.trim()),
                            toggles: [...row.querySelectorAll('.svc-template-step-toggle span')]
                              .slice(0, 3)
                              .map((node) => node.textContent.trim()),
                            addText: root.querySelector('.svc-template-add')?.textContent.trim() || '',
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                          };
                        })()
                        """
                    )
                    expected_labels = ["섹션", "기본 항목", "흐름", "타입", "템플릿", "출력"]
                    expected_toggles = ["필수", "유동", "반복"]
                    if (
                        template_terms["labels"] == expected_labels
                        and template_terms["toggles"] == expected_toggles
                        and template_terms["addText"] == "+ 섹션"
                        and template_terms["overflow"] <= 2
                    ):
                        pass_("service-template-terminology", json.dumps(template_terms, ensure_ascii=False))
                    else:
                        fail("service-template-terminology", json.dumps(template_terms, ensure_ascii=False))
                else:
                    template_terms = page.evaluate(
                        """
                        (() => ({
                          mode: 'worship',
                          templateVersionBaseline: {
                            version: PUBLIC_WORSHIP_TEMPLATE_VERSION,
                            effectiveFrom: PUBLIC_WORSHIP_TEMPLATE_EFFECTIVE_FROM,
                            versions: ['sunday-first', 'sunday-second', 'sunday-main', 'sunday-afternoon', 'monthly', 'wednesday']
                              .map((typeId) => resolvePublicWorshipTemplateVersion(typeId, { service: { type_id: typeId, date: '2026-07-05' } })?.version || ''),
                          },
                          autoScheduleTargets: (() => {
                            const previousCalendarData = state.calendarData;
                            const regularMonday = autoUpcomingPublicServiceTargets('2026-07-20').map((item) => `${item.typeId}:${item.date}`);
                            try {
                              state.calendarData = [
                                ...(previousCalendarData || []),
                                {
                                  id: '__smoke_all_generations__',
                                  date: '2026-07-26',
                                  church_schedule: '온세대 찬양예배'
                                }
                              ];
                              return {
                                monday: regularMonday,
                                allGenerationsMonday: autoUpcomingPublicServiceTargets('2026-07-20').map((item) => `${item.typeId}:${item.date}`),
                                saturday: autoUpcomingPublicServiceTargets('2026-07-18').map((item) => `${item.typeId}:${item.date}`),
                                sunday: autoUpcomingPublicServiceTargets('2026-07-19').map((item) => `${item.typeId}:${item.date}`),
                              };
                            } finally {
                              state.calendarData = previousCalendarData;
                            }
                          })(),
                          allGenerationDateGuards: (() => {
                            const previousCalendarData = state.calendarData;
                            try {
                              state.calendarData = [
                                { id: '__smoke_regular_blank__', date: '2026-08-02', note: '', church_schedule: '' },
                                { id: '__smoke_regular_note__', date: '2026-08-09', note: '온세대 찬양예배', church_schedule: '청소년부 제자헌신예배' },
                                { id: '__smoke_regular_alias__', date: '2026-08-16', note: '', church_schedule: '' },
                                { id: '__smoke_all_generation_schedule__', date: '2026-08-23', note: '', church_schedule: '온세대 찬양예배' },
                              ];
                              return {
                                blankDate: isAllGenerationsWorshipDate('2026-08-02'),
                                noteOnlyDate: isAllGenerationsWorshipDate('2026-08-09'),
                                aliasOnlyService: isAllGenerationsWorshipService({
                                  id: '__smoke_alias_only__',
                                  type_id: 'sunday-main',
                                  date: '2026-08-16',
                                  alias: '온세대 찬양예배',
                                }),
                                sourceRefOnlyService: isAllGenerationsWorshipService({
                                  id: '__smoke_source_ref_only__',
                                  type_id: 'sunday-main',
                                  date: '2026-08-16',
                                  _worshipSourceRef: { sunday_main_variant: 'all_generations' },
                                }),
                                scheduledDate: isAllGenerationsWorshipDate('2026-08-23'),
                                scheduledThirdService: isAllGenerationsWorshipService({
                                  id: '__smoke_scheduled_third__',
                                  type_id: 'sunday-main',
                                  date: '2026-08-23',
                                }),
                                scheduledYouthService: isAllGenerationsWorshipService({
                                  id: '__smoke_scheduled_youth__',
                                  type_id: 'youth',
                                  date: '2026-08-23',
                                }),
                              };
                            } finally {
                              state.calendarData = previousCalendarData;
                            }
                          })(),
                          levels: [...document.querySelectorAll('.svc-template-level-card strong')]
                            .map((node) => node.textContent.trim()),
                          monthlyFirst: (() => {
                            const step = serviceOrderTemplate('monthly')[0] || {};
                            const thirdService = { id: '__smoke_sunday_third_creed__', type_id: 'sunday-main' };
                            const thirdScaffold = buildWorshipServiceScaffold(thirdService.id, thirdService.type_id, { service: thirdService });
                            const thirdCreed = (groupWorshipElements(thirdScaffold.sections, thirdScaffold.elements)[thirdService.id] || [])
                              .find((item) => item._worshipSectionKey === 'creed');
                            const thirdCreedSlides = buildPresenterSlidesForServiceItem(thirdCreed, thirdService, 0)
                              .slice(0, 2)
                              .map((slide) => ({ type: slide.type || '', title: slide.title || '', text: slide.text || '' }));
                            return {
                              label: step.label || step.name || '',
                              elementType: step.elementType || step.element_type || step.componentType || step.component_type || ''
                            };
                          })(),
                          fridayScaffold: (() => {
                            const scaffold = buildWorshipServiceScaffold('__smoke_friday__', 'friday');
                            return {
                              sections: scaffold.sections.map((section) => section.title || ''),
                              labels: scaffold.elements.map((element) => element.source_ref?.label || ''),
                              rawTitles: projectWorshipServiceItemsFromTemplate({
                                id: '__smoke_friday__',
                                type_id: 'friday',
                                date: '2026-07-17',
                              }, []).map((item) => ({
                                label: item.label || '',
                                rawTitle: item.raw_title || '',
                                sectionKey: item._worshipSectionKey || '',
                              })),
                            };
                          })(),
                          friday3355Scaffold: (() => {
                            const service = {
                              id: '__smoke_friday_3355__',
                              type_id: 'friday',
                              date: '2026-08-21',
                              alias: '삼삼오오예배',
                              _worshipSourceRef: { friday_variant: '3355', friday_variant_name: '삼삼오오예배' },
                            };
                            const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                            const projectedWithLegacyPrayer = projectWorshipServiceItemsFromTemplate(service, [{
                              id: '__smoke_friday_3355_legacy_ready__',
                              service_id: service.id,
                              label: '대기 화면',
                              raw_title: '대기 화면',
                              _worshipSectionKey: 'ready',
                              _worshipSectionTitle: '준비',
                              _worshipElementTemplateModified: true,
                            }, {
                              id: '__smoke_friday_3355_legacy_entrance__',
                              service_id: service.id,
                              label: '입례찬양',
                              raw_title: '입례찬양 곡',
                              _worshipSectionKey: 'entrance_praise',
                              _worshipSectionTitle: '입례찬양',
                              _worshipElementTemplateModified: true,
                            }, {
                              id: '__smoke_friday_3355_legacy_prayer_song__',
                              service_id: service.id,
                              label: '기도찬양 1',
                              raw_title: '주여 이 시간',
                              _worshipSectionKey: 'prayer_meeting_praise',
                              _worshipSectionTitle: '기도회',
                              _worshipElementTemplateModified: true,
                            }, {
                              id: '__smoke_friday_3355_legacy_free_prayer__',
                              service_id: service.id,
                              label: '자율기도',
                              raw_title: '자율기도',
                              _worshipSectionKey: 'prayer_meeting_praise',
                              _worshipSectionTitle: '기도회',
                              _worshipElementTemplateModified: true,
                            }]);
                            return {
                              sections: scaffold.sections.map((section) => section.section_key || ''),
                              titles: scaffold.sections.map((section) => section.title || ''),
                              labels: scaffold.elements.map((element) => element.source_ref?.label || ''),
                              elementTypes: scaffold.elements.map((element) => ({
                                label: element.source_ref?.label || '',
                                type: element.element_type || '',
                                section: scaffold.sections.find((section) => section.id === element.section_id)?.section_key || '',
                              })),
                              projectedSections: [...new Set(projectedWithLegacyPrayer.map((item) => item._worshipSectionTitle || ''))],
                              projectedLabels: projectedWithLegacyPrayer.map((item) => item.label || ''),
                              firstProjectedLabel: projectedWithLegacyPrayer[0]?.label || '',
                              fellowshipEditor: (() => {
                                const fellowship = projectedWithLegacyPrayer.find((item) => item._worshipSectionKey === 'fellowship');
                                const model = serviceItemEditorModel(fellowship || {}, { service });
                                const spec = presenterServiceTextInputSpec(fellowship || {}, model, parseServiceItemMemo(fellowship?.memo));
                                const host = document.createElement('div');
                                host.innerHTML = renderPresenterServiceTextInputs(
                                  fellowship || {},
                                  projectedWithLegacyPrayer.findIndex((item) => item === fellowship),
                                  model,
                                  parseServiceItemMemo(fellowship?.memo),
                                );
                                const fieldLabels = [...host.querySelectorAll('.svc-presenter-input-field > span')]
                                  .map((node) => node.textContent.trim());
                                const placeholders = [...host.querySelectorAll('input')]
                                  .map((node) => node.getAttribute('placeholder') || '');
                                const legacyPersonInTitle = {
                                  ...(fellowship || {}),
                                  raw_title: '박미루 집사',
                                  assignee: '',
                                };
                                const legacyMemo = parseServiceItemMemo(legacyPersonInTitle.memo);
                                const legacyModel = serviceItemEditorModel(legacyPersonInTitle, { service });
                                const legacyState = resolvePresenterServiceItemContentState(
                                  legacyPersonInTitle,
                                  legacyMemo,
                                  null,
                                  service,
                                );
                                const legacySlide = buildPresenterSlidesForServiceItem(legacyPersonInTitle, service, 0)[0] || {};
                                return {
                                  label: fellowship?.label || '',
                                  showTitle: Boolean(model.showTitle),
                                  showAssignee: Boolean(model.showAssignee),
                                  needsTitle: Boolean(spec.needsTitle),
                                  needsAssignee: Boolean(spec.needsAssignee),
                                  titlePlaceholder: model.titlePlaceholder || '',
                                  presenterFieldLabels: fieldLabels,
                                  presenterPlaceholders: placeholders,
                                  legacyPersonInTitle: {
                                    state: legacyState.state,
                                    reason: legacyState.reason,
                                    hasOutputContent: Boolean(legacyState.hasOutputContent),
                                    displayText: serviceItemDisplayText(legacyPersonInTitle),
                                    titleValue: legacyModel.titleValueOverride ?? legacyModel.titleValue ?? '',
                                    assigneeValue: legacyModel.assigneeValue || '',
                                    slideTitle: legacySlide.title || '',
                                    slideAssignee: legacySlide.assignee || '',
                                    slideText: legacySlide.text || '',
                                    missingContent: Boolean(legacySlide.missingContent),
                                  },
                                };
                              })(),
                              praiseLabels: scaffold.elements
                                .filter((element) => scaffold.sections.find((section) => section.id === element.section_id)?.section_key === 'praise')
                                .map((element) => element.source_ref?.label || ''),
                              sending: scaffold.elements
                                .filter((element) => scaffold.sections.find((section) => section.id === element.section_id)?.section_key === 'sending')
                                .map((element) => ({
                                  label: element.source_ref?.label || '',
                                  person: element.person || '',
                                })),
                            };
                          })(),
                          fridayDistrictUnionScaffold: (() => {
                            const service = {
                              id: '__smoke_friday_district_union__',
                              type_id: 'friday',
                              date: '2026-08-28',
                              alias: '구역연합예배',
                              _worshipSourceRef: { friday_variant: 'district-union', friday_variant_name: '구역연합예배' },
                            };
                            const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                            const readySection = scaffold.sections.find((section) => section.section_key === 'ready') || {};
                            const readyElement = scaffold.elements.find((element) => element.section_id === readySection.id) || {};
                            return {
                              chromakey: presenterServiceUsesChromakey(service),
                              firstElementType: readyElement.element_type || '',
                              firstElementLabel: readyElement.source_ref?.label || '',
                              firstElementRole: readyElement.config?.presenterRole || '',
                            };
                          })(),
                          monthlyScaffold: (() => {
                            const scaffold = buildWorshipServiceScaffold('__smoke_service__', 'monthly');
                            const sections = scaffold.sections.map((section) => ({
                              key: section.section_key || '',
                              title: section.title || '',
                              elements: scaffold.elements
                                .filter((element) => element.section_id === section.id)
                                .map((element) => ({
                                  type: element.element_type || '',
                                  label: element.source_ref?.label || ''
                                }))
                            }));
                            const defaultsFor = (sectionKey) => {
                              const section = scaffold.sections.find((item) => item.section_key === sectionKey);
                              return scaffold.elements
                                .filter((element) => element.section_id === section?.id)
                                .map((element) => ({
                                  label: element.source_ref?.label || '',
                                  title: element.title || '',
                                  formHint: element.config?.formHint || '',
                                  forms: element.config?.formPreset?.forms || [],
                                  strength: element.config?.defaultStrength || element.config?.formPreset?.strength || ''
                                }));
                            };
                            return {
                              sections: scaffold.sections.length,
                              elements: scaffold.elements.length,
                              firstSection: scaffold.sections[0]?.title || '',
                              firstElementType: scaffold.elements[0]?.element_type || '',
                              firstElementLabel: scaffold.elements[0]?.source_ref?.label || '',
                              firstElementTitle: scaffold.elements[0]?.title || '',
                              sectionKeys: sections.map((section) => section.key),
                              praiseElements: sections.find((section) => section.key === 'praise')?.elements || [],
                              corporatePrayerElements: sections.find((section) => section.key === 'corporate_prayer')?.elements || [],
                              prayerSection: (() => {
                                const prayer = sections.find((section) => section.key === 'prayer');
                                return {
                                  title: prayer?.title || '',
                                  elements: prayer?.elements || [],
                                  defaults: defaultsFor('prayer')
                                };
                              })(),
                              sermonSection: (() => {
                                const sermon = sections.find((section) => section.key === 'sermon');
                                return {
                                  title: sermon?.title || '',
                                  elements: sermon?.elements || []
                                };
                              })(),
                              responseSection: (() => {
                                const response = sections.find((section) => section.key === 'response_song');
                                return {
                                  title: response?.title || '',
                                  elements: response?.elements || []
                                };
                              })(),
                              offeringElements: sections.find((section) => section.key === 'offering')?.elements || [],
                              offeringDefaults: defaultsFor('offering'),
                              closingSection: (() => {
                                const closing = sections.find((section) => section.key === 'closing_visual');
                                return {
                                  title: closing?.title || '',
                                  elements: closing?.elements || []
                                };
                              })(),
                              closingVisualSection: (() => {
                                const closing = scaffold.sections.find((section) => section.section_key === 'closing_visual');
                                return {
                                  title: closing?.title || '',
                                  elements: scaffold.elements
                                    .filter((element) => element.section_id === closing?.id)
                                    .map((element) => ({
                                      type: element.element_type || '',
                                      label: element.source_ref?.label || '',
                                      assetUrl: element.config?.asset?.url || ''
                                    }))
                                };
                              })(),
                              closingDefaults: defaultsFor('closing_visual')
                            };
                          })(),
                          youthScaffold: (() => {
                            const scaffold = buildWorshipServiceScaffold('__smoke_youth__', 'youth');
                            const offering = scaffold.sections.find((section) => section.section_key === 'offering');
                            const praise = scaffold.elements.find((element) =>
                              element.section_id === offering?.id && element.source_ref?.label === '봉헌찬양');
                            return {
                              songLinked: Boolean(praise?.song_id && praise?.song_version_id),
                              formHint: praise?.config?.formHint || '',
                              forms: praise?.config?.formPreset?.forms || [],
                              strength: praise?.config?.defaultStrength || praise?.config?.formPreset?.strength || '',
                            };
                          })(),
                          publicSpecialRule: (() => {
                            const scaffold = buildWorshipServiceScaffold('__smoke_public__', 'sunday-main');
                            const section = scaffold.sections.find((item) => item.section_key === 'special_song');
                            const element = scaffold.elements.find((item) => item.section_id === section?.id);
                            const rule = element?.config?.formPresetRules?.[0] || null;
                            return {
                              sectionTitle: section?.title || '',
                              elementLabel: element?.source_ref?.label || '',
                              when: rule?.when || {},
                              forms: rule?.formPreset?.forms || [],
                              hint: rule?.formPreset?.hint || '',
                              strength: rule?.formPreset?.strength || ''
                            };
                          })(),
                          sundayPublicScaffold: (() => {
                            const compact = (value) => String(value || '').replace(/\\s+/g, '');
                            const summarize = (typeId, service = null) => {
                              const serviceId = service?.id || `__smoke_${typeId}__`;
                              const serviceForSummary = service || { id: serviceId, type_id: typeId };
                              const scaffold = buildWorshipServiceScaffold(serviceId, typeId, service ? { service } : {});
                              const sections = scaffold.sections.map((section) => ({
                                id: section.id || '',
                                key: section.section_key || '',
                                title: section.title || '',
                                elements: scaffold.elements
                                  .filter((element) => element.section_id === section.id)
                                  .map((element) => ({
                                    type: element.element_type || '',
                                    label: element.source_ref?.label || '',
                                    ...(element.person ? { person: element.person } : {}),
                                    ...(element.config?.introSlide?.title ? { introTitle: element.config.introSlide.title } : {}),
                                    ...(element.config?.introSlide?.body ? { introBody: element.config.introSlide.body } : {}),
                                    ...(element.config?.textHighlights?.length ? { textHighlights: element.config.textHighlights } : {}),
                                    ...(element.config?.formHint ? { formHint: element.config.formHint } : {}),
                                    ...(element.config?.formPreset?.forms ? { forms: element.config.formPreset.forms } : {}),
                                    ...(element.config?.defaultStrength || element.config?.formPreset?.strength ? { strength: element.config.defaultStrength || element.config.formPreset.strength } : {}),
                                    outputMode: element.config?.outputMode || '',
                                    ...(element.config?.hiddenInPresentation ? { hidden: true } : {}),
                                  }))
                              }));
                              const groupedItems = groupWorshipElements(scaffold.sections, scaffold.elements)[serviceId] || [];
                              return {
                                sections: sections.length,
                                elements: scaffold.elements.length,
                                titles: sections.map((section) => section.title),
                                keys: sections.map((section) => section.key),
                                compactTitles: sections.map((section) => compact(section.title)),
                                praiseElements: sections.find((section) => section.key === 'praise')?.elements || [],
                                silentPrayerElements: sections.find((section) => section.key === 'silent_prayer')?.elements || [],
                                hymnElements: sections.find((section) => section.key === 'hymn_praise')?.elements || [],
                                creedElements: sections.find((section) => section.key === 'creed')?.elements || [],
                                prayerElements: sections.find((section) => section.key === 'prayer')?.elements || [],
                                scriptureElements: sections.find((section) => section.key === 'scripture_reading')?.elements || [],
                                communityElements: (sections.find((section) => section.key === 'sending')?.elements || [])
                                  .filter((element) => element.label === '공동체고백'),
                                sermonElements: sections.find((section) => section.key === 'sermon')?.elements || [],
                                offeringElements: sections.find((section) => section.key === 'offering')?.elements || [],
                                announcementsElements: sections.find((section) => section.key === 'announcements')?.elements || [],
                                sendingElements: sections.find((section) => section.key === 'sending')?.elements || [],
                                closingElements: sections.find((section) => section.key === 'closing_visual')?.elements || [],
                                hiddenContentStates: groupedItems
                                  .filter((item) => ['special_song', 'offering'].includes(item._worshipSectionKey || ''))
                                  .map((item) => {
                                    const memo = parseServiceItemMemo(item.memo);
                                    const state = resolvePresenterServiceItemContentState(item, memo, serviceItemLinkedSong(item), serviceForSummary);
                                    return {
                                      sectionKey: item._worshipSectionKey || '',
                                      label: item.label || '',
                                      hidden: Boolean(memo.hiddenInPresentation),
                                      state: state.state || '',
                                      reason: state.reason || '',
                                      required: Boolean(state.required),
                                    };
                                  }),
                                closingHymnDefaults: scaffold.elements
                                  .filter((element) =>
                                    element.section_id === sections.find((section) => section.key === 'closing_visual')?.id
                                    && element.source_ref?.label === '폐회찬송'
                                  )
                                  .map((element) => ({
                                    type: element.element_type || '',
                                    label: element.source_ref?.label || '',
                                    title: element.title || '',
                                    formHint: element.config?.formHint || '',
                                    forms: element.config?.formPreset?.forms || [],
                                    strength: element.config?.defaultStrength || element.config?.formPreset?.strength || ''
                                  })),
                                scoreSlots: sections.flatMap((section) =>
                                  section.elements
                                    .filter((element) => element.outputMode === 'score')
                                    .map((element) => `${section.key}:${element.label}`)
                                ),
                                doxologyDefaults: scaffold.elements
                                  .filter((element) => element.source_ref?.label === '송영')
                                  .map((element) => ({
                                    sectionKey: scaffold.sections.find((section) => section.id === element.section_id)?.section_key || '',
                                    title: element.title || ''
                                  }))
                              };
                            };
                            const thirdService = { id: '__smoke_sunday_third_creed__', type_id: 'sunday-main' };
                            const thirdScaffold = buildWorshipServiceScaffold(thirdService.id, thirdService.type_id, { service: thirdService });
                            const thirdCreed = (groupWorshipElements(thirdScaffold.sections, thirdScaffold.elements)[thirdService.id] || [])
                              .find((item) => item._worshipSectionKey === 'creed');
                            const thirdCreedSlides = buildPresenterSlidesForServiceItem(thirdCreed, thirdService, 0)
                              .slice(0, 2)
                              .map((slide) => ({ type: slide.type || '', title: slide.title || '', text: slide.text || '' }));
                            return {
                              first: summarize('sunday-first'),
                              firstLayRotation: summarize('sunday-first', { id: '__smoke_sunday_first_lay_rotation__', type_id: 'sunday-first', date: '2026-08-23' }),
                              firstPastorRotation: summarize('sunday-first', { id: '__smoke_sunday_first_pastor_rotation__', type_id: 'sunday-first', date: '2026-08-30' }),
                              firstPastor: summarize('sunday-first', { id: '__smoke_sunday_first_pastor__', type_id: 'sunday-first', worshipLeader: '김남영 목사' }),
                              second: summarize('sunday-second'),
                              third: summarize('sunday-main'),
                              allGeneration: (() => {
                                const previousCalendarData = state.calendarData;
                                const service = {
                                  id: '__smoke_sunday_third_all_generation__',
                                  type_id: 'sunday-main',
                                  date: '2026-07-19',
                                  alias: '온세대 찬양예배',
                                  _worshipSourceRef: { sunday_main_variant: 'all_generations' },
                                };
                                try {
                                  state.calendarData = [
                                    ...(previousCalendarData || []),
                                    { id: '__smoke_all_generation_scaffold__', date: '2026-07-19', church_schedule: '온세대 찬양예배' },
                                  ];
                                  const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                                  const praiseSection = scaffold.sections.find((section) => section.section_key === 'praise');
                                  const specialSection = scaffold.sections.find((section) => section.section_key === 'special_song');
                                  const offeringSection = scaffold.sections.find((section) => section.section_key === 'offering');
                                  const closingSection = scaffold.sections.find((section) => section.section_key === 'closing_visual');
                                  return {
                                    sectionKeys: scaffold.sections.map((section) => section.section_key || ''),
                                    sectionTitles: scaffold.sections.map((section) => section.title || ''),
                                    specialSong: scaffold.elements.find((element) => element.section_id === specialSection?.id) || null,
                                    offeringElements: scaffold.elements
                                      .filter((element) => element.section_id === offeringSection?.id)
                                      .map((element) => ({
                                        type: element.element_type || '',
                                        label: element.source_ref?.label || '',
                                        outputMode: element.config?.outputMode || '',
                                        assetUrl: element.config?.asset?.url || '',
                                      })),
                                    praiseElements: scaffold.elements
                                      .filter((element) => element.section_id === praiseSection?.id)
                                      .map((element) => ({
                                        label: element.source_ref?.label || '',
                                        title: element.title || state.songs.find((song) => song.id === element.song_id)?.title || '',
                                      })),
                                    closingElements: scaffold.elements
                                      .filter((element) => element.section_id === closingSection?.id)
                                      .map((element) => ({
                                        type: element.element_type || '',
                                        label: element.source_ref?.label || '',
                                        outputMode: element.config?.outputMode || '',
                                        assetUrl: element.config?.asset?.url || '',
                                      })),
                                    closingHymnDefaults: scaffold.elements
                                      .filter((element) =>
                                        element.section_id === closingSection?.id
                                        && element.source_ref?.label === '폐회찬송'
                                      )
                                      .map((element) => ({
                                        type: element.element_type || '',
                                        label: element.source_ref?.label || '',
                                        title: element.title || '',
                                        formHint: element.config?.formHint || '',
                                        forms: element.config?.formPreset?.forms || [],
                                        strength: element.config?.defaultStrength || element.config?.formPreset?.strength || ''
                                      })),
                                  };
                                } finally {
                                  state.calendarData = previousCalendarData;
                                }
                              })(),
                              allGenerationRegular: (() => {
                                const previousCalendarData = state.calendarData;
                                const service = {
                                  id: '__smoke_sunday_third_all_generation_regular__',
                                  type_id: 'sunday-main',
                                  date: '2026-08-23',
                                  alias: '온세대 찬양예배',
                                };
                                try {
                                  state.calendarData = [
                                    ...(previousCalendarData || []),
                                    { id: '__smoke_all_generation_regular_scaffold__', date: '2026-08-23', church_schedule: '온세대 찬양예배' },
                                  ];
                                  const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                                  const offeringSection = scaffold.sections.find((section) => section.section_key === 'offering');
                                  return scaffold.elements
                                    .filter((element) => element.section_id === offeringSection?.id)
                                    .map((element) => ({
                                      type: element.element_type || '',
                                      label: element.source_ref?.label || '',
                                      outputMode: element.config?.outputMode || '',
                                      assetUrl: element.config?.asset?.url || '',
                                    }));
                                } finally {
                                  state.calendarData = previousCalendarData;
                                }
                              })(),
                              afternoon: summarize('sunday-afternoon'),
                              thirdDefaults: {
                                entrancePraise: publicSundayThirdEntrancePraiseElement().defaultSong || null,
                                sendingPraise: publicSundayThirdSendingPraiseElement().defaultSong || null,
                                closingPraise: publicWorshipClosingHymnElement().defaultSong || null,
                              },
                              thirdCreedSlides,
                            };
                          })(),
                          commonClosingTemplates: (() => {
                            const summarize = (typeId) => {
                              const template = serviceOrderTemplate(typeId);
                              const last = template[template.length - 1] || {};
                              const scaffold = buildWorshipServiceScaffold(`__smoke_common_${typeId}__`, typeId);
                              const lastSection = scaffold.sections[scaffold.sections.length - 1] || {};
                              return {
                                typeId,
                                lastLabel: last.label || last.name || '',
                                lastSectionKey: last.sectionKey || last.section_key || '',
                                lastScaffoldTitle: lastSection.title || '',
                                lastScaffoldKey: lastSection.section_key || '',
                              };
                            };
                            return ['holy-week-dawn', 'omer', 'special'].map(summarize);
                          })(),
                          scoreModeMemo: (() => {
                            const memo = serializeServiceItemMemo({ elementType: 'praise', outputMode: 'score' });
                            const parsed = parseServiceItemMemo(memo);
                            return {
                              memo,
                              outputMode: parsed.outputMode || '',
                              serializedKeepsMode: memo.includes('"outputMode":"score"')
                            };
                          })(),
                          formPresetUi: (() => {
                            const memo = serializeServiceItemMemo({
                              formHint: 'V2-C',
                              formPreset: normalizeServiceFormPreset('V2-C', 'V2-C', 'manual'),
                              formPresetRules: [{
                                when: { songType: 'hymn' },
                                formPreset: { forms: ['1절', '2절', '간주', '마지막 절'], hint: '1절-2절-간주-마지막 절' }
                              }]
                            });
                            const parsed = parseServiceItemMemo(memo);
                            const badgeHtml = renderServiceEditorFormControls({ memo }, 0, { song: null, parsed }, { compact: true, placeholder: '송폼' });
                            const previousSongs = state.songs;
                            const song = {
                              id: '__form_meta_song__',
                              title: '송폼 메타 찬양',
                              metadata: { presenter_form: { forms: ['V1', 'V2', 'C', 'B', 'Coda'], hint: 'V1-V2-C-B-Coda' } },
                              versions: [{ id: '__form_meta_version__', forms: [] }]
                            };
                            const hymnSong = {
                              id: '__form_hymn_song__',
                              title: '1 만복의 근원 하나님',
                              hymn_no: '1',
                              praise_types: ['hymn'],
                              versions: [{ id: '__form_hymn_version__', forms: [], praise_types: ['hymn'] }]
                            };
                            const explicitSequence = normalizeSongMetadata({
                              presenter_form: 'V-C-V-C-B-C-Coda',
                            }).presenter_form || {};
                            const legacyAugmentedSequence = normalizeSongMetadata({
                              presenter_form: {
                                forms: ['V', 'C', 'B', 'Coda'],
                                hint: 'V-C-B-Coda',
                                sourceForms: ['V', 'C', 'V', 'C', 'B', 'C', 'Coda'],
                              },
                            }).presenter_form || {};
                            const item = normalizeServiceItem({
                              id: '__form_meta_item__',
                              service_id: '__form_meta_service__',
                              label: '찬양 1',
                              song_id: song.id,
                              version_id: '__form_meta_version__',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' })
                            });
                            const hymnItem = normalizeServiceItem({
                              id: '__form_hymn_item__',
                              service_id: '__form_meta_service__',
                              label: '특송',
                              song_id: hymnSong.id,
                              version_id: '__form_hymn_version__',
                              memo: serializeServiceItemMemo({
                                formPresetRules: [{
                                  when: { songType: 'hymn' },
                                  formPreset: { forms: ['1절', '2절', '간주', '마지막 절'], hint: '1절-2절-간주-마지막 절' }
                                }]
                              })
                            });
                            state.songs = [song, hymnSong];
                            const metadataValue = serviceItemEffectiveFormHint(item);
                            const inputHtml = renderServiceFormHintInput(item, 0, { compact: true, placeholder: '송폼' });
                            const hymnInputHtml = renderServiceFormHintInput(hymnItem, 0, { compact: true, placeholder: '송폼' });
                            const disabledMemo = serializeServiceItemMemo({ ...parseServiceItemMemo(item.memo), formHint: '', formPreset: null, formPresetDisabled: true });
                            const disabledParsed = parseServiceItemMemo(disabledMemo);
                            const disabledValue = serviceItemEffectiveFormHint({ ...item, memo: disabledMemo });
                            const previousServiceItems = state.serviceItems;
                            const previousSelectedServiceId = state.selectedServiceId;
                            const editableItem = { ...item, memo: item.memo };
                            state.serviceItems = {
                              ...previousServiceItems,
                              __form_meta_service__: [editableItem],
                              __other_selected_service__: [normalizeServiceItem({ id: '__other_item__', service_id: '__other_selected_service__', label: '찬양 1' })],
                            };
                            state.selectedServiceId = '__other_selected_service__';
                            const inputNode = document.createElement('div');
                            inputNode.innerHTML = renderServiceFormHintInput(editableItem, 0, { compact: true, placeholder: '송폼' });
                            const formInput = inputNode.querySelector('input');
                            formInput.value = '';
                            updateServiceItemField(formInput);
                            const savedOverride = parseServiceItemMemo(state.serviceItems.__form_meta_service__[0].memo).formPresetDisabled === true;
                            const otherUntouched = parseServiceItemMemo(state.serviceItems.__other_selected_service__[0].memo).formPresetDisabled === false;
                            const savedConfig = serviceElementConfigForSave({}, disabledParsed, { item, service: { id: '__form_meta_service__' } });
                            const configKeepsOverride = savedConfig.formPresetDisabled === true
                              && !savedConfig.formHint
                              && !savedConfig.formPreset
                              && !savedConfig.formPresetRules;
                            const configHintDisabled = serviceFormHintFromConfig(savedConfig) === '';
                            const staleConfig = serviceElementConfigForSave(
                              {
                                formHint: 'V1-C',
                                form_hint: 'V1-C',
                                formPreset: { forms: ['V1', 'C'], hint: 'V1-C' },
                                form_preset: { forms: ['V1', 'C'], hint: 'V1-C' },
                                formPresetRules: [{ when: { songType: 'ccm' }, formPreset: { forms: ['V1'] } }],
                                form_preset_rules: [{ when: { songType: 'ccm' }, formPreset: { forms: ['V1'] } }],
                              },
                              { ...disabledParsed, formPreset: { forms: ['V1', 'C'], hint: 'V1-C' } },
                              { item, service: { id: '__form_meta_service__' } },
                            );
                            const staleConfigCleaned = staleConfig.formPresetDisabled === true
                              && !staleConfig.formHint
                              && !staleConfig.form_hint
                              && !staleConfig.formPreset
                              && !staleConfig.form_preset
                              && !staleConfig.formPresetRules
                              && !staleConfig.form_preset_rules;
                            const mergedDisabledMemo = mergeTemplateProjectionMemo(
                              serializeServiceItemMemo({ formHint: 'V1-C-V2-C', formPreset: normalizeServiceFormPreset('V1-C-V2-C', 'V1-C-V2-C', 'metadata') }),
                              disabledMemo,
                            );
                            const mergedParsed = parseServiceItemMemo(mergedDisabledMemo);
                            const mergeKeepsOverride = mergedParsed.formPresetDisabled === true
                              && !mergedParsed.formHint
                              && !mergedParsed.formPreset
                              && !mergedParsed.formPresetRules.length;
                            state.selectedServiceId = previousSelectedServiceId;
                            state.serviceItems = previousServiceItems;
                            state.songs = previousSongs;
                            return {
                              formHint: parsed.formHint || '',
                              forms: parsed.formPreset?.forms || [],
                              strength: parsed.formPreset?.strength || '',
                              metadataValue,
                              explicitSequenceValue: serviceFormPresetSummary(explicitSequence),
                              explicitSequenceForms: explicitSequence.forms || [],
                              legacyAugmentedSequenceValue: serviceFormPresetSummary(legacyAugmentedSequence),
                              legacyAugmentedSequenceForms: legacyAugmentedSequence.forms || [],
                              inputValue: (() => {
                                const node = document.createElement('div');
                                node.innerHTML = inputHtml;
                                return node.querySelector('input')?.value || '';
                              })(),
                              hymnInputValue: (() => {
                                const node = document.createElement('div');
                                node.innerHTML = hymnInputHtml;
                                return node.querySelector('input')?.value || '';
                              })(),
                              disabledMemoKeepsOverride: disabledParsed.formPresetDisabled === true,
                              disabledValue,
                              savedOverride,
                              otherUntouched,
                              configKeepsOverride,
                              configHintDisabled,
                              staleConfigCleaned,
                              mergeKeepsOverride,
                              badgeText: (() => {
                                const node = document.createElement('div');
                                node.innerHTML = badgeHtml;
                                return node.textContent.trim().replace(/\\s+/g, ' ');
                              })()
                            };
                          })(),
                          fridayNewServiceLeader: (() => {
                            const previousSelectedTypeId = state.selectedServiceTypeId;
                            const previousSelectedServiceId = state.selectedServiceId;
                            const previousForm = state.newServiceForm ? { ...state.newServiceForm } : null;
                            startNewServiceForm('friday');
                            const inputValue = document.querySelector('[data-new-service-field="leader"]')?.value || '';
                            const formLeader = state.newServiceForm?.leader || '';
                            state.selectedServiceTypeId = previousSelectedTypeId;
                            state.selectedServiceId = previousSelectedServiceId;
                            state.newServiceForm = previousForm;
                            renderServiceTemplatesDetail();
                            return {
                              formLeader,
                              inputValue,
                              defaultLeader: defaultServicePraiseLeader('friday'),
                              monthlyDefaultLeader: defaultServicePraiseLeader('monthly')
                            };
                          })(),
                          serviceInstanceOverride: (() => {
                            const serviceId = '__smoke_instance_override__';
                            const previousServices = state.services;
                            const previousItems = state.serviceItems[serviceId];
                            const previousSelectedServiceId = state.selectedServiceId;
                            const previousDirty = state.dirty.service;
                            const scaffold = buildWorshipServiceScaffold(serviceId, 'sunday-main');
                            state.services = previousServices.filter((service) => service.id !== serviceId).concat([{
                              id: serviceId,
                              type_id: 'sunday-main',
                              date: '2026-07-05',
                              alias: ''
                            }]);
                            state.serviceItems[serviceId] = groupWorshipElements(scaffold.sections, scaffold.elements)[serviceId] || [];
                            state.selectedServiceId = serviceId;
                            const items = state.serviceItems[serviceId];
                            const index = items.findIndex((item) => item._worshipSectionKey === 'offering' && item.label === '봉헌찬송');
                            const beforeTitle = items[index]?.raw_title || '';
                            const input = document.createElement('input');
                            input.dataset.serviceItemField = 'raw_title';
                            input.dataset.serviceItemIndex = String(index);
                            input.value = '봉헌특송';
                            updateServiceItemField(input);
                            const afterItem = state.serviceItems[serviceId][index] || {};
                            const afterMemo = parseServiceItemMemo(afterItem.memo);
                            const legacyMemo = parseServiceItemMemo(JSON.stringify({ outputMode: 'score' }));
                            const templateOffering = serviceOrderTemplate('sunday-main')
                              .find((step) => (step.sectionKey || step.section_key) === 'offering')
                              ?.elements?.find((element) => element.label === '봉헌찬송') || {};
                            state.services = previousServices;
                            if (previousItems === undefined) delete state.serviceItems[serviceId];
                            else state.serviceItems[serviceId] = previousItems;
                            state.selectedServiceId = previousSelectedServiceId;
                            state.dirty.service = previousDirty;
                            return {
                              label: afterItem.label || '',
                              sectionKey: afterItem._worshipSectionKey || '',
                              beforeTitle,
                              afterTitle: afterItem.raw_title || '',
                              outputMode: afterMemo.outputMode || '',
                              effectiveOutputMode: serviceItemOutputMode(afterItem, afterMemo),
                              legacyEffectiveOutputMode: serviceItemOutputMode({ ...afterItem, memo: JSON.stringify({ outputMode: 'score' }) }, legacyMemo),
                              templateTitle: templateOffering.default_text || '',
                              templateLabel: templateOffering.label || ''
                            };
                          })(),
                          legacyHierarchyCleanup: (() => {
                            const service = {
                              id: '__smoke_legacy_hierarchy__',
                              type_id: 'sunday-main',
                              date: '2026-07-05'
                            };
                            const sectionIds = {
                              sending: '11111111-1111-4111-8111-111111111111',
                              closing: '22222222-2222-4222-8222-222222222222',
                              oldBenediction: '33333333-3333-4333-8333-333333333333',
                              oldLordsPrayer: '44444444-4444-4444-8444-444444444444',
                              oldClosingHymn: '55555555-5555-4555-8555-555555555555'
                            };
                            const item = (id, label, key, sectionId, order) => normalizeServiceItem({
                              id,
                              service_id: service.id,
                              sort_order: order,
                              label,
                              raw_title: label,
                              _worshipSectionId: sectionId,
                              _worshipSectionKey: key,
                              _worshipSectionTitle: label,
                              _worshipSectionOrder: order,
                              _worshipElementOrder: 1,
                              memo: serializeServiceItemMemo({ elementType: label === '폐회찬송' ? 'praise' : 'title_person' })
                            });
                            const items = [
                              item('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '축도', 'benediction', sectionIds.oldBenediction, 3),
                              item('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '주기도문', 'lords_prayer', sectionIds.oldLordsPrayer, 4),
                              item('cccccccc-cccc-4ccc-8ccc-cccccccccccc', '마무리', 'closing_visual', sectionIds.closing, 5),
                              item('dddddddd-dddd-4ddd-8ddd-dddddddddddd', '폐회찬송', 'closing_hymn', sectionIds.oldClosingHymn, 2),
                            ];
                            const normalized = normalizeServiceItemsForTemplateHierarchy(service, items);
                            const sections = [
                              { id: sectionIds.sending, service_id: service.id, sort_order: 14, section_key: 'sending', title: '파송', source_ref: {}, config: {} },
                              { id: sectionIds.closing, service_id: service.id, sort_order: 15, section_key: 'closing_visual', title: '폐회', source_ref: {}, config: {} },
                              { id: sectionIds.oldBenediction, service_id: service.id, sort_order: 9, section_key: 'benediction', title: '축도', source_ref: {}, config: {} },
                              { id: sectionIds.oldLordsPrayer, service_id: service.id, sort_order: 10, section_key: 'lords_prayer', title: '주기도문', source_ref: {}, config: {} },
                              { id: sectionIds.oldClosingHymn, service_id: service.id, sort_order: 11, section_key: 'closing_hymn', title: '폐회찬송', source_ref: {}, config: {} },
                            ];
                            const existingSectionById = Object.fromEntries(sections.map((section) => [section.id, section]));
                            const existingElementById = Object.fromEntries(items.map((row) => [row.id, { id: row.id, section_id: row._worshipSectionId, source_ref: {}, config: {} }]));
                            const rows = buildWorshipPersistenceRows(service, normalized, existingSectionById, existingElementById);
                            return {
                              normalized: normalized.map((row) => ({
                                label: row.label,
                                key: row._worshipSectionKey,
                                title: row._worshipSectionTitle,
                                sectionId: row._worshipSectionId
                              })),
                              persistedSections: rows.sections.map((section) => ({
                                id: section.id,
                                key: section.section_key,
                                title: section.title
                              })),
                              persistedElementSections: rows.elements.map((element) => ({
                                id: element.id,
                                sectionId: element.section_id
                              }))
                            };
                          })(),
                          generatedSectionPersistence: (() => {
                            const service = { id: '__smoke_generated_section__', type_id: 'monthly', date: '2026-07-03' };
                            const sectionId = '99999999-9999-4999-8999-999999999999';
                            const items = ['첫 항목', '둘째 항목'].map((label, index) => normalizeServiceItem({
                              id: `eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee${index + 1}`,
                              service_id: service.id,
                              sort_order: index + 1,
                              label,
                              raw_title: '',
                              _worshipSectionId: sectionId,
                              _worshipSectionKey: 'generated_section',
                              _worshipSectionTitle: '새 섹션',
                              _worshipSectionOrder: 1,
                              _worshipElementOrder: index + 1,
                              memo: serializeServiceItemMemo({ elementType: 'title' })
                            }));
                            const rows = buildWorshipPersistenceRows(service, items, {}, {});
                            return {
                              sectionCount: rows.sections.length,
                              elementCount: rows.elements.length,
                              sortOrders: rows.sections.map((section) => section.sort_order),
                              sharedSection: new Set(rows.elements.map((element) => element.section_id)).size === 1,
                              sectionTimestamps: rows.sections.every((section) => Boolean(section.created_at && section.updated_at)),
                              elementTimestamps: rows.elements.every((element) => Boolean(element.created_at && element.updated_at)),
                            };
                          })(),
                          concurrentTemplateProjectionDeduplication: (() => {
                            const service = { id: '__smoke_concurrent_template__', type_id: 'sunday-main', date: '2026-08-16' };
                            const first = projectWorshipServiceItemsFromTemplate(service, []);
                            const second = projectWorshipServiceItemsFromTemplate(service, []).map((item) => (
                              item.label === '설교 제목'
                                ? { ...item, raw_title: '동시 저장 보존 제목', _worshipElementTemplateModified: true }
                                : item
                            ));
                            const collapsed = projectWorshipServiceItemsFromTemplate(service, [...first, ...second]);
                            const firstRows = buildWorshipPersistenceRows(service, first, {}, {});
                            const secondRows = buildWorshipPersistenceRows(service, projectWorshipServiceItemsFromTemplate(service, []), {}, {});
                            const ids = (rows) => ({
                              sections: rows.sections.map((row) => row.id).sort(),
                              elements: rows.elements.map((row) => row.id).sort(),
                            });
                            return {
                              praiseCount: collapsed.filter((item) => item.label === '찬송').length,
                              specialSongCount: collapsed.filter((item) => item.label === '특송').length,
                              sermonTitleCount: collapsed.filter((item) => item.label === '설교 제목').length,
                              sermonTitle: collapsed.find((item) => item.label === '설교 제목')?.raw_title || '',
                              deterministicIds: JSON.stringify(ids(firstRows)) === JSON.stringify(ids(secondRows)),
                            };
                          })(),
                          duplicatePersistenceIds: (() => {
                            const service = { id: '__smoke_duplicate_persistence__', type_id: 'sunday-main', date: '2026-08-23' };
                            const duplicateId = 'aaaaaaaa-1111-4111-8111-aaaaaaaa1111';
                            const sectionId = 'bbbbbbbb-2222-4222-8222-bbbbbbbb2222';
                            const items = ['특송', '특송'].map((label, index) => normalizeServiceItem({
                              id: duplicateId,
                              service_id: service.id,
                              sort_order: index + 1,
                              label,
                              raw_title: index === 0 ? '첫 번째 특송' : '두 번째 특송',
                              _worshipSectionId: sectionId,
                              _worshipSectionKey: 'special_song',
                              _worshipSectionTitle: '특송',
                              _worshipSectionOrder: 5,
                              _worshipElementOrder: index + 1,
                              _worshipElementTemplateModified: true,
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'manual_praise' })
                            }));
                            const uniqueItems = ensureUniqueServiceItemPersistenceIds(items);
                            const rows = buildWorshipPersistenceRows(service, uniqueItems, {
                              [sectionId]: {
                                id: sectionId,
                                service_id: service.id,
                                created_at: '2026-08-23T00:00:00.000Z',
                                updated_at: '2026-08-23T00:00:00.000Z',
                                section_key: 'special_song',
                                title: '특송',
                                source_ref: {},
                                config: {},
                              },
                            }, {
                              [duplicateId]: {
                                id: duplicateId,
                                section_id: sectionId,
                                created_at: '2026-08-23T00:00:00.000Z',
                                updated_at: '2026-08-23T00:00:00.000Z',
                                element_type: 'praise',
                                title: '첫 번째 특송',
                                source_ref: {},
                                config: {},
                              },
                            });
                            return {
                              itemIds: uniqueItems.map((item) => item.id),
                              elementIds: rows.elements.map((element) => element.id),
                              uniqueItemIds: new Set(uniqueItems.map((item) => item.id)).size,
                              uniqueElementIds: new Set(rows.elements.map((element) => element.id)).size,
                              elementCount: rows.elements.length,
                            };
                          })(),
                          persistenceRowCompaction: (() => {
                            const sectionId = 'cccccccc-3333-4333-8333-cccccccc3333';
                            const elementId = 'dddddddd-4444-4444-8444-dddddddd4444';
                            const rows = compactWorshipPersistenceRows({
                              sections: [
                                { id: sectionId, title: '특송', sort_order: 1 },
                                { id: sectionId, title: '특송', sort_order: 2, config: { templateSuppressed: true } },
                              ],
                              elements: [
                                { id: elementId, title: '이전 특송', sort_order: 1 },
                                { id: elementId, title: '온세대 특송', sort_order: 2, config: { audioAsset: { kind: 'audio' } } },
                              ],
                            });
                            return {
                              sectionCount: rows.sections.length,
                              elementCount: rows.elements.length,
                              sectionSort: rows.sections[0]?.sort_order,
                              elementTitle: rows.elements[0]?.title || '',
                              audioKind: rows.elements[0]?.config?.audioAsset?.kind || '',
                            };
                          })(),
                          templateSuppressionProjection: (() => {
                            const service = { id: '__smoke_template_suppression__', type_id: 'friday', date: '2026-07-24' };
                            const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                            const items = groupWorshipElements(scaffold.sections, scaffold.elements)[service.id] || [];
                            const target = items.find((item) => item.label === '특송') || {};
                            const source = items.map((item) => ({
                              ...item,
                              raw_title: `입력:${item.label}`,
                              _worshipElementTemplateModified: true,
                              memo: item.id === target.id
                                ? serializeServiceItemMemo({ ...parseServiceItemMemo(item.memo), templateSuppressed: true })
                                : item.memo,
                            }));
                            const suppressed = source.find((item) => item.id === target.id) || {};
                            const projected = projectWorshipServiceItemsFromTemplate(service, source);
                            const itemFor = (label) => projected.find((item) => item.label === label) || {};
                            return {
                              sourceFound: Boolean(target.id),
                              suppressed: isTemplateSuppressedServiceItem(suppressed),
                              projected: projected.some((item) => item.label === '특송'),
                              preservedSlots: ['교회소식', '성경봉독', '입례찬양', '결단찬양', '기도찬양 1', '자율기도']
                                .map((label) => ({
                                  label,
                                  sectionKey: itemFor(label)._worshipSectionKey || '',
                                  title: itemFor(label).raw_title || '',
                                })),
                            };
                          })(),
                          templateSuppressionSurvivesRepeatedProjection: (() => {
                            const service = { id: '__smoke_template_suppression_repeat__', type_id: 'sunday-main', date: '2026-08-23' };
                            const scaffold = buildWorshipServiceScaffold(service.id, service.type_id, { service });
                            const items = groupWorshipElements(scaffold.sections, scaffold.elements)[service.id] || [];
                            const scaffoldMarker = items.find((item) =>
                              item._worshipSectionKey === 'offering' && item.label === '봉헌찬송'
                            );
                            const marker = scaffoldMarker || normalizeServiceItem({
                              id: 'legacy-offering-hymn',
                              service_id: service.id,
                              label: '봉헌찬송',
                              raw_title: '',
                              memo: serializeServiceItemMemo({ elementType: 'praise', outputMode: 'score' }),
                              _worshipSectionKey: 'offering',
                              _worshipSectionTitle: '봉헌',
                              _worshipElementOrder: 1,
                            });
                            const source = [
                              ...items.filter((item) => !(item._worshipSectionKey === 'offering' && item.label === '봉헌찬송')),
                              {
                                ...marker,
                                id: 'suppressed-offering-hymn',
                                service_id: service.id,
                                memo: serializeServiceItemMemo({
                                  ...parseServiceItemMemo(marker.memo),
                                  templateSuppressed: true,
                                }),
                                _worshipElementTemplateModified: true,
                              },
                              normalizeServiceItem({
                                id: 'offering-video',
                                service_id: service.id,
                                label: '봉헌 영상',
                                raw_title: '',
                                memo: serializeServiceItemMemo({ elementType: 'video', inputMode: 'asset' }),
                                _worshipSectionKey: 'offering',
                                _worshipSectionTitle: '봉헌',
                                _worshipElementOrder: 1,
                                _worshipElementTemplateModified: true,
                              }),
                            ];
                            const first = projectWorshipServiceItemsFromTemplate(service, source);
                            const second = projectWorshipServiceItemsFromTemplate(service, first);
                            state.templateElementSuppressions.delete('suppressed-offering-hymn');
                            return {
                              scaffoldHasOfferingHymn: Boolean(scaffoldMarker?.id),
                              firstHasOfferingHymn: first.some((item) => item.label === '봉헌찬송'),
                              secondHasOfferingHymn: second.some((item) => item.label === '봉헌찬송'),
                              firstHasVideo: first.some((item) => item.label === '봉헌 영상'),
                              secondHasVideo: second.some((item) => item.label === '봉헌 영상'),
                            };
                          })(),
                          sundayFirstSendingPrune: (() => {
                            const sectionId = '66666666-6666-4666-8666-666666666666';
                            const item = (id, label, key, order, assignee = '') => normalizeServiceItem({
                              id,
                              service_id: '__smoke_sunday_first_sending__',
                              sort_order: order,
                              label,
                              raw_title: label,
                              assignee,
                              _worshipSectionId: sectionId,
                              _worshipSectionKey: key,
                              _worshipSectionTitle: label,
                              _worshipSectionOrder: order,
                              _worshipElementOrder: order,
                              memo: serializeServiceItemMemo({ elementType: label === '주기도문' ? 'body' : 'title_person' })
                            });
                            const items = [
                              item('77777777-7777-4777-8777-777777777777', '축도', 'benediction', 1),
                              item('88888888-8888-4888-8888-888888888888', '주기도문', 'lords_prayer', 2),
                              item('99999999-9999-4999-8999-999999999999', '설교 제목', 'sermon', 3, '김남영 목사'),
                            ];
                            const pastorPreacher = normalizeServiceItemsForTemplateHierarchy(
                              { id: '__smoke_sunday_first_lay__', type_id: 'sunday-first', worshipLeader: '인도자' },
                              items,
                            ).map((row) => row.label);
                            const layPreacher = normalizeServiceItemsForTemplateHierarchy(
                              { id: '__smoke_sunday_first_pastor_existing__', type_id: 'sunday-first', worshipLeader: '김남영 목사' },
                              items.map((row) => row.label === '설교 제목' ? { ...row, assignee: '이준철 전도사' } : row),
                            ).map((row) => row.label);
                            return { pastorPreacher, layPreacher };
                          })(),
                          liturgicalSidebarSummaries: (() => {
                            const item = (label, key, text) => normalizeServiceItem({
                              id: `__smoke_liturgical_sidebar_${key}__`,
                              service_id: '__smoke_liturgical_sidebar__',
                              label,
                              raw_title: text,
                              _worshipSectionKey: key,
                              memo: serializeServiceItemMemo({ elementType: 'body' }),
                            });
                            return {
                              creedBody: serviceSidebarChildItemDisplayParts(item('사도신경', 'creed', '전능하사 천지를 만드신 하나님 아버지를 내가 믿사오며,')),
                              creedTitle: serviceSidebarChildItemDisplayParts(item('신앙고백', 'creed', '사도신경')),
                              communityBody: serviceSidebarChildItemDisplayParts(item('공동체고백', 'community_confession', PUBLIC_COMMUNITY_CONFESSION_TEXT)),
                              lordsBody: serviceSidebarChildItemDisplayParts(item('주기도문', 'lords_prayer', PUBLIC_LORDS_PRAYER_TEXT)),
                            };
                          })(),
                          sundayFirstDoxologyProjectionRecovery: (() => {
                            const previousServices = state.services.slice();
                            const previousItems = state.serviceItems;
                            const service = { id: '__smoke_sunday_first_doxology_recovery__', type_id: 'sunday-first', date: '2026-07-19', title: '주일예배 [1부]' };
                            state.services = [...previousServices, service];
                            state.serviceItems = {
                              ...previousItems,
                              [service.id]: [normalizeServiceItem({
                                id: '__smoke_sunday_first_lords_only__',
                                service_id: service.id,
                                sort_order: 1,
                                label: '주기도문',
                                raw_title: '',
                                _worshipSectionId: '__smoke_sunday_first_lords_only_section__',
                                _worshipSectionKey: 'sending',
                                _worshipSectionTitle: '파송',
                                _worshipSectionOrder: 10,
                                _worshipElementOrder: 2,
                                memo: serializeServiceItemMemo({ elementType: 'body' })
                              })],
                            };
                            const projected = getServiceItems(service.id);
                            const result = {
                              labels: projected
                                .filter((row) => row._worshipSectionKey === 'sending')
                                .map((row) => row.label),
                              doxology: projected.some((row) =>
                                row._worshipSectionKey === 'sending'
                                && compactSearchValue(row.label) === '송영'
                              ),
                              stored: (state.serviceItems[service.id] || []).some((row) =>
                                row._worshipSectionKey === 'sending'
                                && compactSearchValue(row.label) === '송영'
                              ),
                            };
                            state.services = previousServices;
                            state.serviceItems = previousItems;
                            return result;
                          })(),
                          duplicateBenedictionProjection: (() => {
                            const service = { id: '__smoke_duplicate_benediction__', type_id: 'sunday-main', date: '2026-07-05' };
                            const item = (id, label, key, order, assignee = '') => normalizeServiceItem({
                              id,
                              service_id: service.id,
                              sort_order: order,
                              label,
                              raw_title: label,
                              assignee,
                              _worshipSectionId: key === 'sending'
                                ? '11111111-1111-4111-8111-111111111111'
                                : '33333333-3333-4333-8333-333333333333',
                              _worshipSectionKey: key,
                              _worshipSectionTitle: key === 'sending' ? '파송' : label,
                              _worshipSectionOrder: order,
                              _worshipElementOrder: order,
                              memo: serializeServiceItemMemo({ elementType: 'title_person' })
                            });
                            const projected = projectWorshipServiceItemsFromTemplate(service, [
                              item('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '축도', 'benediction', 1, ''),
                              item('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '축도', 'sending', 2, '김남영 목사'),
                            ]);
                            const presenterItems = adaptServiceItemsForPresenterView(service, [
                              item('cccccccc-cccc-4ccc-8ccc-cccccccccccc', '축도', 'benediction', 1, ''),
                              item('dddddddd-dddd-4ddd-8ddd-dddddddddddd', '축도', 'sending', 2, '김남영 목사'),
                            ]);
                            const benedictions = projected.filter((row) => compactSearchValue(row.label) === '축도');
                            const presenterBenedictions = presenterItems.filter((row) => compactSearchValue(row.label) === '축도');
                            return {
                              count: benedictions.length,
                              people: benedictions.map((row) => row.assignee || ''),
                              sectionKeys: benedictions.map((row) => row._worshipSectionKey || ''),
                              presenterCount: presenterBenedictions.length,
                              presenterPeople: presenterBenedictions.map((row) => row.assignee || ''),
                            };
                          })(),
                          sharedSundayContentProjection: (() => {
                            const previousServices = state.services.slice();
                            const previousItems = state.serviceItems;
                            const services = [
                              { id: '__smoke_share_first__', type_id: 'sunday-first', date: '2099-01-04', title: '주일예배 [1부]' },
                              { id: '__smoke_share_second__', type_id: 'sunday-second', date: '2099-01-04', title: '주일예배 [2부]' },
                              { id: '__smoke_share_third__', type_id: 'sunday-main', date: '2099-01-04', title: '주일예배 [3부]' },
                            ];
                            state.services = [...previousServices, ...services];
                            const makeItem = (serviceId, label, key, order, values = {}) => normalizeServiceItem({
                              id: `${serviceId}:${key}:${label}`,
                              service_id: serviceId,
                              sort_order: order,
                              label,
                              raw_title: values.rawTitle || '',
                              assignee: values.assignee || '',
                              song_id: values.songId || null,
                              version_id: values.versionId || null,
                              _worshipSectionId: `${serviceId}:${key}`,
                              _worshipSectionKey: key,
                              _worshipSectionTitle: values.sectionTitle || label,
                              _worshipSectionOrder: order,
                              _worshipElementOrder: order,
                              memo: serializeServiceItemMemo({
                                elementType: values.elementType || (key === 'sermon' || key === 'scripture_reading' ? 'scripture_body' : 'praise'),
                                inputMode: values.inputMode || (key === 'sermon' || key === 'scripture_reading' ? 'scripture' : 'praise_db'),
                                ...(values.scriptureReference ? { scriptureReference: values.scriptureReference } : {}),
                                ...(values.scriptureReferences ? { scriptureReferences: values.scriptureReferences } : {}),
                                ...(values.formPreset ? { formPreset: values.formPreset } : {}),
                              }),
                            });
                            const praiseSong = state.songs.find((song) => song.title === '평화 하나님의 평강이') || state.songs[0];
                            const praiseVersion = praiseSong?.versions?.[0] || null;
                            const offeringSong = state.songs.find((song) => compactSearchValue(song.title).includes('공중나는새를보라')) || state.songs[1] || praiseSong;
                            const offeringVersion = offeringSong?.versions?.[0] || null;
                            state.serviceItems = {
                              ...previousItems,
                              __smoke_share_first__: [
                                makeItem('__smoke_share_first__', '찬양 1', 'praise', 1, { songId: praiseSong?.id, versionId: praiseVersion?.id }),
                                makeItem('__smoke_share_first__', '봉헌찬송', 'offering', 2, { songId: offeringSong?.id, versionId: offeringVersion?.id }),
                              ],
                              __smoke_share_second__: [
                                makeItem('__smoke_share_second__', '찬양 1', 'praise', 1, { songId: praiseSong?.id, versionId: praiseVersion?.id }),
                                makeItem('__smoke_share_second__', '성경봉독', 'scripture_reading', 2, { rawTitle: '마 13:31–33, 44–50', scriptureReferences: ['마 13:31–33', '마 13:44–50'] }),
                                makeItem('__smoke_share_second__', '설교 제목', 'sermon', 3, { elementType: 'title_person', inputMode: 'text', rawTitle: '믿음으로 사는 사람', assignee: '김남영 목사' }),
                                makeItem('__smoke_share_second__', '인용 구절', 'sermon', 4, { rawTitle: '고전 13:4-7', scriptureReference: '고전 13:4-7' }),
                                makeItem('__smoke_share_second__', '봉헌찬송', 'offering', 5),
                              ],
                              __smoke_share_third__: [
                                makeItem('__smoke_share_third__', '성경봉독', 'scripture_reading', 1),
                                makeItem('__smoke_share_third__', '설교 제목', 'sermon', 2, { elementType: 'title_person', inputMode: 'text' }),
                                makeItem('__smoke_share_third__', '설교 본문', 'sermon', 3),
                                makeItem('__smoke_share_third__', '인용 구절', 'sermon', 4),
                                makeItem('__smoke_share_third__', '봉헌찬송', 'offering', 5),
                              ],
                            };
                            const secondPraise = getServiceOutputItems('__smoke_share_second__').find((item) => item.label === '찬양 1');
                            const secondOffering = getServiceOutputItems('__smoke_share_second__').find((item) => item.label === '봉헌찬송');
                            const thirdReading = getServiceOutputItems('__smoke_share_third__').find((item) => item.label === '성경봉독');
                            const thirdSermonTitle = getServiceOutputItems('__smoke_share_third__').find((item) => item.label === '설교 제목');
                            const thirdSermonBody = getServiceOutputItems('__smoke_share_third__').find((item) => item.label === '설교 본문');
                            const thirdCitation = getServiceOutputItems('__smoke_share_third__').find((item) => item.label === '인용 구절');
                            const thirdOffering = getServiceOutputItems('__smoke_share_third__').find((item) => item.label === '봉헌찬송');
                            const syncedPraise = applySharedSundayContentToItem(
                              makeItem('__smoke_share_second__', '찬양 1', 'praise', 1),
                              makeItem('__smoke_share_first__', '찬양 1', 'praise', 1, { songId: praiseSong?.id, versionId: praiseVersion?.id })
                            );
                            const clearedPraise = applySharedSundayContentToItem(
                              syncedPraise,
                              makeItem('__smoke_share_first__', '찬양 1', 'praise', 1)
                            );
                            const syncedScripture = applySharedSundayContentToItem(
                              makeItem('__smoke_share_third__', '설교 본문', 'sermon', 3),
                              makeItem('__smoke_share_second__', '설교 본문', 'sermon', 3, { rawTitle: '마 13:31–33, 44–50', scriptureReferences: ['마 13:31–33', '마 13:44–50'] })
                            );
                            const clearedScripture = applySharedSundayContentToItem(
                              syncedScripture,
                              makeItem('__smoke_share_second__', '설교 본문', 'sermon', 3)
                            );
                            const materializedSecondItems = materializeSharedSundayContentForPersistence(
                              services[1],
                              state.serviceItems.__smoke_share_second__
                            );
                            const materializedSecondPraise = materializedSecondItems.find((item) => item.label === '찬양 1');
                            const materializedEmptySecondPraise = materializeSharedSundayContentForPersistence(
                              services[1],
                              [makeItem('__smoke_share_second__', '찬양 1', 'praise', 1)]
                            )[0];
                            const result = {
                              secondPraiseText: serviceItemDisplayText(secondPraise),
                              secondPraiseSongId: serviceItemWithSharedSundayContent(secondPraise, services[1]).song_id || '',
                              secondPraiseMaterializedSongId: materializedSecondPraise?.song_id || '',
                              secondPraiseMaterializedVersionId: materializedSecondPraise?.version_id || materializedSecondPraise?.song_version_id || '',
                              emptySecondPraiseMaterializedSongId: materializedEmptySecondPraise?.song_id || '',
                              mainPraiseSharedTypes: services.map((service) =>
                                sundaySharedContentTypesForItem(
                                  makeItem(service.id, '찬양 1', 'praise', 1),
                                  service
                                )
                              ),
                              secondPraiseStatic: presenterServiceInputIsStatic(secondPraise),
                              secondPraiseMissing: resolvePresenterServiceItemContentState(secondPraise, parseServiceItemMemo(secondPraise.memo), null, services[1]).state,
                              secondOfferingText: serviceItemDisplayText(secondOffering),
                              thirdReadingRefs: serviceItemScriptureReferences(thirdReading, parseServiceItemMemo(thirdReading.memo), services[2]),
                              thirdReadingMissing: resolvePresenterServiceItemContentState(thirdReading, parseServiceItemMemo(thirdReading.memo), null, services[2]).state,
                              thirdSermonTitleText: serviceItemDisplayText(thirdSermonTitle),
                              thirdSermonTitleAssignee: serviceItemWithSharedSundayContent(thirdSermonTitle, services[2]).assignee || '',
                              thirdSermonTitleStatic: presenterServiceInputIsStatic(thirdSermonTitle),
                              thirdSermonBodyRefs: serviceItemScriptureReferences(thirdSermonBody, parseServiceItemMemo(thirdSermonBody.memo), services[2]),
                              thirdSermonBodyPayloadReference: serviceScriptureTextPayload(thirdSermonBody, parseServiceItemMemo(thirdSermonBody.memo), services[2]).reference,
                              thirdCitationRefs: serviceItemScriptureReferences(thirdCitation, parseServiceItemMemo(thirdCitation.memo), services[2]),
                              thirdOfferingText: serviceItemDisplayText(thirdOffering),
                              thirdOfferingStatic: presenterServiceInputIsStatic(thirdOffering),
                              thirdMissingSlides: buildServicePresenterSlides('__smoke_share_third__').filter((slide) => slide.missingContent).map((slide) => slide.label),
                              syncedPraiseSongId: syncedPraise.song_id || '',
                              clearedPraiseSongId: clearedPraise.song_id || '',
                              syncedScriptureRefs: serviceItemScriptureReferences(syncedScripture, parseServiceItemMemo(syncedScripture.memo), services[2]),
                              clearedScriptureRefs: parseServiceItemMemo(clearedScripture.memo).scriptureReferences || [],
                            };
                            state.services = previousServices;
                            state.serviceItems = previousItems;
                            return result;
                          })(),
                          fullscreenSermonBodyCompatibility: (() => {
                            const service = { id: '__smoke_fullscreen_sermon_body__', type_id: 'sunday-first', date: '2026-07-05' };
                            const previousServices = state.services.slice();
                            const previousItems = state.serviceItems;
                            state.services.push(service);
                            const readingItem = normalizeServiceItem({
                              id: '__smoke_fullscreen_reading_body_item__',
                              service_id: service.id,
                              label: '성경봉독',
                              raw_title: '요 21:15-25',
                              _worshipSectionId: '__smoke_fullscreen_reading_section__',
                              _worshipSectionKey: 'scripture_reading',
                              _worshipSectionTitle: '성경봉독',
                              memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture', scriptureReferences: ['요 21:15–25'] })
                            });
                            const item = normalizeServiceItem({
                              id: '__smoke_fullscreen_sermon_body_item__',
                              service_id: service.id,
                              label: '설교 본문',
                              raw_title: '',
                              _worshipSectionId: '__smoke_fullscreen_sermon_section__',
                              _worshipSectionKey: 'sermon',
                              _worshipSectionTitle: '설교',
                              memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' })
                            });
                            state.serviceItems = {
                              ...state.serviceItems,
                              [service.id]: [readingItem, item],
                            };
                            const memo = parseServiceItemMemo(item.memo);
                            const content = resolvePresenterServiceItemContentState(item, memo, null, service);
                            const slides = buildPresenterSlidesForServiceItem(item, service, 0);
                            const staticInput = presenterServiceInputIsStatic(item, memo);
                            const rows = buildWorshipPersistenceRows(service, [readingItem, item], {}, {}).elements;
                            const sermonRow = rows[1] || null;
                            state.services = previousServices;
                            state.serviceItems = previousItems;
                            return {
                              staticInput,
                              contentState: content.state || '',
                              reason: content.reason || '',
                              slideCount: slides.length,
                              savedTitle: sermonRow?.title || '',
                              savedReference: sermonRow?.scripture_reference || '',
                            };
                          })(),
                          worshipSongVersionFkGuard: (() => {
                            const previousSongs = state.songs;
                            const service = { id: '__smoke_fk_service__', type_id: 'sunday-second', date: '2026-07-26' };
                            const persistedSong = {
                              id: '__smoke_song_persisted__',
                              title: '저장 가능 곡',
                              versions: [{ id: '__smoke_version_persisted__', name: '기본', is_primary: true, _worshipVersionPersisted: true }],
                            };
                            const otherSong = {
                              id: '__smoke_song_other__',
                              title: '다른 곡',
                              versions: [{ id: '__smoke_version_other__', name: '기본', is_primary: true, _worshipVersionPersisted: true }],
                            };
                            const memoOnlySong = {
                              id: '__smoke_song_memo__',
                              title: '메모 버전 곡',
                              versions: [{ id: '__smoke_version_memo__', name: '기본', is_primary: true }],
                            };
                            const makeItem = (song, versionId) => normalizeServiceItem({
                              id: `__smoke_fk_item_${song.id}__`,
                              service_id: service.id,
                              label: '찬양 1',
                              song_id: song.id,
                              version_id: versionId,
                              _worshipSectionId: '__smoke_fk_section__',
                              _worshipSectionKey: 'praise',
                              _worshipSectionTitle: '찬양',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' }),
                            });
                            try {
                              state.songs = [persistedSong, otherSong, memoOnlySong];
                              const staleItem = makeItem(persistedSong, otherSong.versions[0].id);
                              const validItem = makeItem(persistedSong, persistedSong.versions[0].id);
                              const memoOnlyItem = makeItem(memoOnlySong, memoOnlySong.versions[0].id);
                              const staleRows = buildWorshipPersistenceRows(service, [staleItem], {}, {}).elements;
                              const validRows = buildWorshipPersistenceRows(service, [validItem], {}, {}).elements;
                              const memoOnlyRows = buildWorshipPersistenceRows(service, [memoOnlyItem], {}, {}).elements;
                              return {
                                staleInvalid: serviceItemVersionSelectionInvalid(staleItem, service),
                                staleSavedVersion: staleRows[0]?.song_version_id || null,
                                validSavedVersion: validRows[0]?.song_version_id || null,
                                memoOnlySavedVersion: memoOnlyRows[0]?.song_version_id || null,
                              };
                            } finally {
                              state.songs = previousSongs;
                              state.songLookupSource = null;
                            }
                          })(),
                          scriptureRangeInference: inferBibleVerseEndRanges([
                            { book_code: 'DEU', chapter: 6, verse: 18, text: '18-19가 함께 저장된 본문' },
                            { book_code: 'DEU', chapter: 6, verse: 20, text: '다음 절' },
                          ]).map((verse) => ({ verse: verse.verse, verseEnd: verse.verse_end })),
                          cards: document.querySelectorAll('.svc-template-draft-card, .svc-template-inventory-card').length,
                          overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                        }))()
                        """
                    )
                    if (
                        template_terms["levels"] == ["Service", "Section", "Element", "Slide"]
                        and template_terms["autoScheduleTargets"] == {
                            "monday": [
                                "wednesday:2026-07-22",
                                "friday:2026-07-24",
                                "sunday-first:2026-07-26",
                                "sunday-second:2026-07-26",
                                "sunday-main:2026-07-26",
                                "youth:2026-07-26",
                                "young-adult:2026-07-26",
                                "sunday-afternoon:2026-07-26",
                            ],
                            "allGenerationsMonday": [
                                "wednesday:2026-07-22",
                                "friday:2026-07-24",
                                "sunday-first:2026-07-26",
                                "sunday-second:2026-07-26",
                                "sunday-main:2026-07-26",
                                "young-adult:2026-07-26",
                                "sunday-afternoon:2026-07-26",
                            ],
                            "saturday": [
                                "wednesday:2026-07-22",
                                "friday:2026-07-24",
                                "sunday-first:2026-07-19",
                                "sunday-second:2026-07-19",
                                "sunday-main:2026-07-19",
                                "young-adult:2026-07-19",
                                "sunday-afternoon:2026-07-19",
                            ],
                            "sunday": [
                                "wednesday:2026-07-22",
                                "friday:2026-07-24",
                                "sunday-first:2026-07-19",
                                "sunday-second:2026-07-19",
                                "sunday-main:2026-07-19",
                                "young-adult:2026-07-19",
                                "sunday-afternoon:2026-07-19",
                            ],
                        }
                        and template_terms["allGenerationDateGuards"] == {
                            "blankDate": False,
                            "noteOnlyDate": False,
                            "aliasOnlyService": False,
                            "sourceRefOnlyService": False,
                            "scheduledDate": True,
                            "scheduledThirdService": True,
                            "scheduledYouthService": False,
                        }
                        and template_terms["monthlyFirst"] == {"label": "준비", "elementType": "video"}
                        and template_terms["friday3355Scaffold"]["sections"] == [
                            "ready",
                            "praise",
                            "prayer",
                            "scripture_reading",
                            "sermon",
                            "response_song",
                            "announcements",
                            "sending",
                            "closing_visual",
                            "fellowship",
                        ]
                        and template_terms["friday3355Scaffold"]["praiseLabels"] == ["찬양 1", "찬양 2", "찬양 3"]
                        and "특송" not in template_terms["friday3355Scaffold"]["titles"]
                        and "입례찬양" not in template_terms["friday3355Scaffold"]["titles"]
                        and "기도회" not in template_terms["friday3355Scaffold"]["titles"]
                        and template_terms["friday3355Scaffold"]["titles"][-2:] == ["폐회", "교제"]
                        and {"label": "교제", "type": "title_person", "section": "fellowship"} in template_terms["friday3355Scaffold"]["elementTypes"]
                        and template_terms["friday3355Scaffold"]["firstProjectedLabel"] == "대기 화면"
                        and template_terms["friday3355Scaffold"]["fellowshipEditor"] == {
                            "label": "교제",
                            "showTitle": False,
                            "showAssignee": True,
                            "needsTitle": False,
                            "needsAssignee": True,
                            "titlePlaceholder": "내용",
                            "presenterFieldLabels": ["담당"],
                            "presenterPlaceholders": ["담당"],
                            "legacyPersonInTitle": {
                                "state": "filled",
                                "reason": "title_person",
                                "hasOutputContent": True,
                                "displayText": "교제 · 박미루 집사",
                                "titleValue": "",
                                "assigneeValue": "박미루 집사",
                                "slideTitle": "교제",
                                "slideAssignee": "박미루 집사",
                                "slideText": "교제\n박미루 집사",
                                "missingContent": False,
                            },
                        }
                        and "입례찬양" not in template_terms["friday3355Scaffold"]["projectedSections"]
                        and "입례찬양" not in template_terms["friday3355Scaffold"]["projectedLabels"]
                        and "기도회" not in template_terms["friday3355Scaffold"]["projectedSections"]
                        and "기도찬양 1" not in template_terms["friday3355Scaffold"]["projectedLabels"]
                        and "자율기도" not in template_terms["friday3355Scaffold"]["projectedLabels"]
                        and template_terms["friday3355Scaffold"]["sending"] == [
                            {"label": "축도", "person": "김남영 목사"},
                        ]
                        and template_terms["fridayDistrictUnionScaffold"] == {
                            "chromakey": True,
                            "firstElementType": "video",
                            "firstElementLabel": "대기 영상",
                            "firstElementRole": "waiting_loop",
                        }
                        and template_terms["monthlyScaffold"]["sections"] == 12
                        and template_terms["monthlyScaffold"]["elements"] == 24
                        and template_terms["monthlyScaffold"]["firstSection"] == "준비"
                        and template_terms["monthlyScaffold"]["firstElementType"] == "video"
                        and template_terms["monthlyScaffold"]["firstElementLabel"] == "대기 영상"
                        and template_terms["monthlyScaffold"]["firstElementTitle"] == ""
                        and "corporate_prayer" in template_terms["monthlyScaffold"]["sectionKeys"]
                        and "sending" in template_terms["monthlyScaffold"]["sectionKeys"]
                        and "closing_visual" in template_terms["monthlyScaffold"]["sectionKeys"]
                        and template_terms["monthlyScaffold"]["praiseElements"][:2] == [
                            {"type": "title_content", "label": "환영"},
                            {"type": "praise", "label": "찬양 1"},
                        ]
                        and template_terms["monthlyScaffold"]["prayerSection"] == {
                            "title": "대표기도",
                            "elements": [{"type": "title_person", "label": "대표기도"}],
                            "defaults": [{"label": "대표기도", "title": "", "formHint": "", "forms": [], "strength": ""}],
                        }
                        and template_terms["monthlyScaffold"]["sermonSection"] == {
                            "title": "설교",
                            "elements": [
                                {"type": "title_person", "label": "설교 제목"},
                                {"type": "scripture_body", "label": "설교 본문"},
                                {"type": "scripture_body", "label": "인용 구절"},
                            ],
                        }
                        and template_terms["monthlyScaffold"]["responseSection"] == {
                            "title": "결단",
                            "elements": [
                                {"type": "praise", "label": "결단찬양"},
                                {"type": "title_person", "label": "결단기도"},
                            ],
                        }
                        and template_terms["monthlyScaffold"]["closingSection"]["title"] == "폐회"
                        and template_terms["monthlyScaffold"]["closingSection"]["elements"] == [
                            {"type": "image", "label": "마무리"},
                        ]
                        and template_terms["monthlyScaffold"]["closingVisualSection"]["title"] == "폐회"
                        and template_terms["monthlyScaffold"]["closingVisualSection"]["elements"] == [
                            {
                                "type": "image",
                                "label": "마무리",
                                "assetUrl": "assets/worship-templates/public-closing.png",
                            },
                        ]
                        and template_terms["monthlyScaffold"]["offeringDefaults"][0] == {
                            "label": "봉헌찬양",
                            "title": "",
                            "formHint": "V-C",
                            "forms": ["V", "C"],
                            "strength": "suggested",
                        }
                        and template_terms["youthScaffold"] == {
                            "songLinked": True,
                            "formHint": "V1-C",
                            "forms": ["V1", "C"],
                            "strength": "default",
                        }
                        and template_terms["monthlyScaffold"]["corporatePrayerElements"] == [
                            {"type": "title_person", "label": "공동기도 1·2"},
                            {"type": "praise", "label": "기도찬양"},
                            {"type": "title_person", "label": "공동기도 3·4"},
                        ]
                        and template_terms["publicSpecialRule"] == {
                            "sectionTitle": "특송",
                            "elementLabel": "특송",
                            "when": {"songType": "hymn"},
                            "forms": ["V1", "C", "V2", "C", "Int", "VL", "C", "Coda"],
                            "hint": "V1-C-V2-C-Int-VL-C-Coda",
                            "strength": "default",
                        }
                        and template_terms["sundayPublicScaffold"]["first"]["titles"][:4] == ["준비", "신앙고백", "찬양", "참회기도"]
                        and "환영" not in template_terms["sundayPublicScaffold"]["first"]["titles"]
                        and all(element["label"] != "환영" for element in template_terms["sundayPublicScaffold"]["first"]["praiseElements"])
                        and all(element["label"] != "환영" for element in template_terms["sundayPublicScaffold"]["second"]["praiseElements"])
                        and template_terms["sundayPublicScaffold"]["first"]["creedElements"] == [
                            {"type": "body", "label": "사도신경", "introTitle": "신앙고백", "introBody": "사도신경", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["second"]["creedElements"] == [
                            {"type": "body", "label": "사도신경", "introTitle": "신앙고백", "introBody": "사도신경", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["third"]["creedElements"] == [
                            {"type": "body", "label": "사도신경", "introTitle": "신앙고백", "introBody": "사도신경", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["thirdCreedSlides"][0] == {
                            "type": "title-content", "title": "신앙고백", "text": "신앙고백\n사도신경"
                        }
                        and template_terms["sundayPublicScaffold"]["thirdCreedSlides"][1]["type"] == "lyrics"
                        and template_terms["sundayPublicScaffold"]["first"]["offeringElements"] == [
                            {"type": "praise", "label": "봉헌찬송", "outputMode": "score"},
                            {"type": "title_person", "label": "봉헌기도", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["first"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김석범 목사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["second"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김남영 목사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["second"]["prayerElements"] == [
                            {"type": "title_person", "label": "대표기도", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["first"]["announcementsElements"] == [
                            {"type": "title", "label": "교회소식", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["second"]["announcementsElements"] == [
                            {"type": "title", "label": "교회소식", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["first"]["sendingElements"] == [
                            {"type": "praise", "label": "송영", "outputMode": "score"},
                            {"type": "body", "label": "주기도문", "introTitle": "주기도문", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["firstLayRotation"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김광한 전도사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["firstLayRotation"]["sendingElements"] == [
                            {"type": "praise", "label": "송영", "outputMode": "score"},
                            {"type": "body", "label": "주기도문", "introTitle": "주기도문", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["firstPastorRotation"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김석범 목사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["firstPastorRotation"]["sendingElements"] == [
                            {"type": "praise", "label": "송영", "outputMode": "score"},
                            {"type": "title_person", "label": "축도", "person": "김석범 목사", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["firstPastor"]["sendingElements"] == [
                            {"type": "praise", "label": "송영", "outputMode": "score"},
                            {"type": "title_person", "label": "축도", "person": "김석범 목사", "outputMode": ""},
                        ]
                        and set(template_terms["sundayPublicScaffold"]["first"]["scoreSlots"]) == {
                            "praise:찬양 1",
                            "praise:찬양 2",
                            "praise:찬양 3",
                            "offering:봉헌찬송",
                            "sending:송영",
                        }
                        and set(template_terms["sundayPublicScaffold"]["second"]["scoreSlots"]) == {
                            "praise:찬양 1",
                            "praise:찬양 2",
                            "praise:찬양 3",
                            "offering:봉헌찬송",
                            "sending:송영",
                        }
                        and template_terms["sundayPublicScaffold"]["afternoon"]["titles"] == [
                            "준비",
                            "찬양",
                            "묵도",
                            "찬송",
                            "대표기도",
                            "성경봉독",
                            "특송",
                            "설교",
                            "결단",
                            "봉헌",
                            "광고",
                            "파송",
                            "폐회",
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["praiseElements"] == [
                            {"type": "praise", "label": "찬양 1", "outputMode": ""},
                            {"type": "praise", "label": "찬양 2", "outputMode": ""},
                            {"type": "praise", "label": "찬양 3", "outputMode": ""},
                            {"type": "praise", "label": "찬양 4", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["silentPrayerElements"] == [
                            {"type": "title", "label": "묵도", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["hymnElements"] == [
                            {"type": "praise", "label": "찬송", "outputMode": "score"}
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["prayerElements"] == [
                            {"type": "title_person", "label": "대표기도", "outputMode": ""}
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["scriptureElements"] == [
                            {"type": "scripture_body", "label": "성경봉독", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김남영 목사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["offeringElements"] == [
                            {"type": "praise", "label": "봉헌찬송", "outputMode": "score", "hidden": True},
                            {"type": "title_person", "label": "봉헌기도", "outputMode": "", "hidden": True},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["hiddenContentStates"] == [
                            {"sectionKey": "special_song", "label": "특송", "hidden": True, "state": "filled", "reason": "hidden_in_presentation", "required": False},
                            {"sectionKey": "offering", "label": "봉헌찬송", "hidden": True, "state": "filled", "reason": "hidden_in_presentation", "required": False},
                            {"sectionKey": "offering", "label": "봉헌기도", "hidden": True, "state": "filled", "reason": "hidden_in_presentation", "required": False},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["sendingElements"] == [
                            {"type": "praise", "label": "송영", "outputMode": "score"},
                            {"type": "title_person", "label": "축도", "person": "김남영 목사", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["afternoon"]["doxologyDefaults"] == [
                            {"sectionKey": "sending", "title": ""}
                        ]
                        and set(template_terms["sundayPublicScaffold"]["afternoon"]["scoreSlots"]) == {
                            "hymn_praise:찬송",
                            "offering:봉헌찬송",
                            "sending:송영",
                        }
                        and "사죄의선언" not in template_terms["sundayPublicScaffold"]["third"]["titles"]
                        and "새가족환영" not in template_terms["sundayPublicScaffold"]["third"]["titles"]
                        and "공동체고백" not in template_terms["sundayPublicScaffold"]["third"]["titles"]
                        and template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["type"] == "body"
                        and template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["label"] == "공동체고백"
                        and template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["introTitle"] == "공동체고백"
                        and template_terms["sundayPublicScaffold"]["third"]["sendingElements"][0]["label"] == "공동체고백"
                        and any(
                            item.get("text") == "예배자" and item.get("color") == "#FFC832"
                            for item in template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["textHighlights"]
                        )
                        and any(
                            item.get("text") == "검단우리교회 공동체" and item.get("bold") is True
                            for item in template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["textHighlights"]
                        )
                        and "아멘송" not in template_terms["sundayPublicScaffold"]["third"]["titles"]
                        and "폐회" in template_terms["sundayPublicScaffold"]["third"]["titles"]
                        and template_terms["sundayPublicScaffold"]["third"]["praiseElements"][:2] == [
                            {"type": "title_content", "label": "환영", "outputMode": ""},
                            {"type": "praise", "label": "찬양 1", "outputMode": ""},
                        ]
                        and [
                            item["label"]
                            for item in template_terms["sundayPublicScaffold"]["third"]["praiseElements"]
                        ] == ["환영", "찬양 1", "찬양 2", "찬양 3", "찬양 4", "입례찬양"]
                        and template_terms["sundayPublicScaffold"]["allGeneration"]["sectionKeys"] == [
                            "ready",
                            "praise",
                            "prayer",
                            "scripture_reading",
                            "special_song",
                            "sermon",
                            "response_song",
                            "offering",
                            "announcements",
                            "sending",
                            "closing_visual",
                        ]
                        and "special_song" in template_terms["sundayPublicScaffold"]["allGeneration"]["sectionKeys"]
                        and not (template_terms["sundayPublicScaffold"]["allGeneration"]["specialSong"].get("person") or "").strip()
                        and not (template_terms["sundayPublicScaffold"]["allGeneration"]["specialSong"].get("title") or "").strip()
                        and template_terms["sundayPublicScaffold"]["allGeneration"]["offeringElements"] == [
                            {"type": "praise", "label": "봉헌특송", "outputMode": "", "assetUrl": ""},
                            {
                                "type": "image",
                                "label": "감사 이미지",
                                "outputMode": "",
                                "assetUrl": "assets/worship-templates/all-generations-2026-07-19-offering-thanks.png",
                            },
                            {"type": "title_person", "label": "봉헌기도", "outputMode": "", "assetUrl": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["allGenerationRegular"] == [
                            {"type": "video", "label": "봉헌 영상", "outputMode": "", "assetUrl": ""},
                            {"type": "title_person", "label": "봉헌기도", "outputMode": "", "assetUrl": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["allGeneration"]["praiseElements"] == [
                            {"label": "환영", "title": "환영\n테힐라 찬양단"},
                            {"label": "찬양 1", "title": ""},
                            {"label": "찬양 2", "title": ""},
                            {"label": "찬양 3", "title": ""},
                            {"label": "찬양 4", "title": ""},
                            {"label": "찬양 5", "title": ""},
                            {"label": "찬양 6", "title": ""},
                            {"label": "찬양 7", "title": ""},
                        ]
                        and [
                            item["label"]
                            for item in template_terms["sundayPublicScaffold"]["allGeneration"]["closingElements"]
                        ] == ["마무리"]
                        and template_terms["sundayPublicScaffold"]["allGeneration"]["closingHymnDefaults"] == []
                        and template_terms["sundayPublicScaffold"]["third"]["praiseElements"][-1] == {
                            "type": "praise",
                            "label": "입례찬양",
                            "formHint": "V-V-C-V-V-C",
                            "forms": ["V", "V", "C", "V", "V", "C"],
                            "strength": "default",
                            "outputMode": "",
                        }
                        and template_terms["sundayPublicScaffold"]["third"]["sermonElements"] == [
                            {"type": "title_person", "label": "설교 제목", "person": "김남영 목사", "outputMode": ""},
                            {"type": "scripture_body", "label": "설교 본문", "outputMode": ""},
                            {"type": "scripture_body", "label": "인용 구절", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["third"]["sendingElements"] == [
                            {
                                "type": "body",
                                "label": "공동체고백",
                                "introTitle": "공동체고백",
                                "textHighlights": template_terms["sundayPublicScaffold"]["third"]["communityElements"][0]["textHighlights"],
                                "outputMode": "",
                            },
                            {
                                "type": "praise",
                                "label": "파송찬송",
                                "formHint": "V1-V2-C-간주-V3-C-C",
                                "forms": ["V1", "V2", "C", "Int", "V3", "C", "C"],
                                "strength": "default",
                                "outputMode": "",
                            },
                            {"type": "title_person", "label": "축도", "person": "김남영 목사", "outputMode": ""},
                        ]
                        and template_terms["sundayPublicScaffold"]["thirdDefaults"] == {
                            "entrancePraise": {"title": "내 한 가지 소원"},
                            "sendingPraise": {"title": "천성을 향해 가는 성도들아", "hymnNo": "359"},
                            "closingPraise": {"title": "십자가 군병들아", "hymnNo": "352"},
                        }
                        and template_terms["sundayPublicScaffold"]["third"]["closingHymnDefaults"] == [{
                            "type": "praise",
                            "label": "폐회찬송",
                            "title": "",
                            "formHint": "V1A-간주-V1-V2-간주-V4-V1B",
                            "forms": ["V1A", "Int", "V1", "V2", "Int", "V4", "V1B"],
                            "strength": "default",
                        }]
                        and [
                            item["label"]
                            for item in template_terms["sundayPublicScaffold"]["third"]["closingElements"]
                        ] == ["마무리", "폐회찬송"]
                        and template_terms["sundayPublicScaffold"]["third"]["keys"].count("praise") == 1
                        and "hymn_praise" in template_terms["sundayPublicScaffold"]["third"]["keys"]
                        and set(template_terms["sundayPublicScaffold"]["third"]["scoreSlots"]) == {
	                            "hymn_praise:찬송",
	                            "offering:봉헌찬송",
                        }
                        and template_terms["sundayPublicScaffold"]["afternoon"]["titles"][:4] == ["준비", "찬양", "묵도", "찬송"]
                        and "hymn_praise" in template_terms["sundayPublicScaffold"]["afternoon"]["keys"]
                        and set(template_terms["sundayPublicScaffold"]["afternoon"]["scoreSlots"]) == {
                            "hymn_praise:찬송",
                            "offering:봉헌찬송",
                            "sending:송영",
                        }
                        and all(item["lastLabel"] == "마무리" for item in template_terms["commonClosingTemplates"])
                        and all(item["lastSectionKey"] == "closing_visual" for item in template_terms["commonClosingTemplates"])
                        and all(item["lastScaffoldTitle"] == "마무리" for item in template_terms["commonClosingTemplates"])
                        and all(item["lastScaffoldKey"] == "closing_visual" for item in template_terms["commonClosingTemplates"])
                        and template_terms["scoreModeMemo"] == {
                            "memo": '{"note":"","elementType":"praise","outputMode":"score"}',
                            "outputMode": "score",
                            "serializedKeepsMode": True,
                        }
                        and template_terms["formPresetUi"] == {
                            "formHint": "V2-C",
                            "forms": ["V2", "C"],
                            "strength": "manual",
                            "metadataValue": "V1-V2-C-B-Coda",
                            "explicitSequenceValue": "V-C-V-C-B-C-Coda",
                            "explicitSequenceForms": ["V", "C", "V", "C", "B", "C", "Coda"],
                            "legacyAugmentedSequenceValue": "V-C-V-C-B-C-Coda",
                            "legacyAugmentedSequenceForms": ["V", "C", "V", "C", "B", "C", "Coda"],
                            "inputValue": "V1-V2-C-B-Coda",
                            "hymnInputValue": "V1-C-V2-C-Int-VL-C-Coda",
                            "disabledMemoKeepsOverride": True,
                            "disabledValue": "",
                            "savedOverride": True,
                            "otherUntouched": True,
                            "configKeepsOverride": True,
                            "configHintDisabled": True,
                            "staleConfigCleaned": True,
                            "mergeKeepsOverride": True,
                            "badgeText": "",
                        }
                        and template_terms["fridayNewServiceLeader"] == {
                            "formLeader": "이재희 청년",
                            "inputValue": "이재희 청년",
                            "defaultLeader": "이재희 청년",
                            "monthlyDefaultLeader": "",
                        }
                        and template_terms["fridayScaffold"]["sections"][-2:] == ["결단", "기도회"]
                        and template_terms["fridayScaffold"]["sections"].index("성경봉독")
                            < template_terms["fridayScaffold"]["sections"].index("입례찬양")
                            < template_terms["fridayScaffold"]["sections"].index("설교")
                        and any(
                            item["label"] == "입례찬양"
                            and item["sectionKey"] == "entrance_praise"
                            for item in template_terms["fridayScaffold"]["rawTitles"]
                        )
                        and [item for item in template_terms["fridayScaffold"]["labels"] if item.startswith("찬양 ")] == [
                            "찬양 1", "찬양 2", "찬양 3", "찬양 4", "찬양 5"
                        ]
                        and any(
                            item["label"] == "기도찬양 1"
                            and item["sectionKey"] == "prayer_meeting_praise"
                            for item in template_terms["fridayScaffold"]["rawTitles"]
                        )
                        and any(
                            item["label"] == "자율기도"
                            and item["sectionKey"] == "prayer_meeting_praise"
                            for item in template_terms["fridayScaffold"]["rawTitles"]
                        )
                        and any(
                            item["label"] == "인용 구절"
                            and item["sectionKey"] == "sermon"
                            for item in template_terms["fridayScaffold"]["rawTitles"]
                        )
                        and "통성기도" not in template_terms["fridayScaffold"]["sections"]
                        and template_terms["fridayScaffold"]["sections"].count("기도회") == 1
                        and "폐회" not in template_terms["fridayScaffold"]["sections"]
                        and "마무리" not in template_terms["fridayScaffold"]["labels"]
                        and next(item["rawTitle"] for item in template_terms["fridayScaffold"]["rawTitles"] if item["label"] == "교회소식") == ""
                        and not any(item["label"] == "통성기도" for item in template_terms["fridayScaffold"]["rawTitles"])
                        and template_terms["serviceInstanceOverride"] == {
                            "label": "봉헌찬송",
                            "sectionKey": "offering",
                            "beforeTitle": "",
                            "afterTitle": "봉헌특송",
                            "outputMode": "score",
                            "effectiveOutputMode": "score",
                            "legacyEffectiveOutputMode": "score",
                            "templateTitle": "",
                            "templateLabel": "봉헌찬송",
                        }
                        and template_terms["generatedSectionPersistence"] == {
                            "sectionCount": 1,
                            "elementCount": 2,
                            "sortOrders": [1],
                            "sharedSection": True,
                            "sectionTimestamps": True,
                            "elementTimestamps": True,
                        }
                        and template_terms["concurrentTemplateProjectionDeduplication"] == {
                            "praiseCount": 1,
                            "specialSongCount": 1,
                            "sermonTitleCount": 1,
                            "sermonTitle": "동시 저장 보존 제목",
                            "deterministicIds": True,
                        }
	                        and template_terms["templateSuppressionProjection"] == {
	                            "sourceFound": True,
	                            "suppressed": True,
	                            "projected": False,
	                            "preservedSlots": [
	                                {"label": "교회소식", "sectionKey": "announcements", "title": "입력:교회소식"},
	                                {"label": "성경봉독", "sectionKey": "scripture_reading", "title": "입력:성경봉독"},
	                                {"label": "입례찬양", "sectionKey": "entrance_praise", "title": "입력:입례찬양"},
	                                {"label": "결단찬양", "sectionKey": "response_song", "title": "입력:결단찬양"},
	                                {"label": "기도찬양 1", "sectionKey": "prayer_meeting_praise", "title": "입력:기도찬양 1"},
	                                {"label": "자율기도", "sectionKey": "prayer_meeting_praise", "title": "입력:자율기도"},
	                            ],
	                        }
	                        and template_terms["templateSuppressionSurvivesRepeatedProjection"] == {
	                            "scaffoldHasOfferingHymn": False,
	                            "firstHasOfferingHymn": False,
	                            "secondHasOfferingHymn": False,
	                            "firstHasVideo": True,
	                            "secondHasVideo": True,
	                        }
	                        and template_terms["templateVersionBaseline"] == {
	                            "version": "2026-q3",
	                            "effectiveFrom": "2026-07-01",
	                            "versions": ["2026-q3", "2026-q3", "2026-q3-07-26", "2026-q3", "2026-q3", "2026-q3"],
	                        }
	                        and template_terms["legacyHierarchyCleanup"]["normalized"] == [
                            {
                                "label": "축도",
                                "key": "sending",
                                "title": "파송",
                                "sectionId": "33333333-3333-4333-8333-333333333333",
                            },
                            {
                                "label": "마무리",
                                "key": "closing_visual",
                                "title": "폐회",
                                "sectionId": "22222222-2222-4222-8222-222222222222",
                            },
                            {
                                "label": "폐회찬송",
                                "key": "closing_visual",
                                "title": "폐회",
                                "sectionId": "22222222-2222-4222-8222-222222222222",
                            },
                        ]
                        and template_terms["legacyHierarchyCleanup"]["persistedSections"] == [
                            {
                                "id": "33333333-3333-4333-8333-333333333333",
                                "key": "sending",
                                "title": "파송",
                            },
                            {
                                "id": "22222222-2222-4222-8222-222222222222",
                                "key": "closing_visual",
                                "title": "폐회",
                            },
                        ]
                        and template_terms["sundayFirstSendingPrune"] == {
                            "pastorPreacher": ["설교 제목", "축도"],
                            "layPreacher": ["설교 제목", "주기도문"],
                        }
                        and template_terms["liturgicalSidebarSummaries"] == {
                            "creedBody": {"meta": "사도신경", "title": ""},
                            "creedTitle": {"meta": "신앙고백", "title": "사도신경"},
                            "communityBody": {"meta": "공동체고백", "title": ""},
                            "lordsBody": {"meta": "주기도문", "title": ""},
                        }
                        and template_terms["sundayFirstDoxologyProjectionRecovery"] == {
                            "labels": ["송영", "축도"],
                            "doxology": True,
                            "stored": True,
                        }
                        and template_terms["duplicateBenedictionProjection"] == {
                            "count": 1,
                            "people": ["김남영 목사"],
                            "sectionKeys": ["sending"],
                            "presenterCount": 1,
                            "presenterPeople": ["김남영 목사"],
                        }
                        and template_terms["duplicatePersistenceIds"]["elementCount"] == 2
                        and template_terms["duplicatePersistenceIds"]["uniqueItemIds"] == 2
                        and template_terms["duplicatePersistenceIds"]["uniqueElementIds"] == 2
                        and template_terms["persistenceRowCompaction"] == {
                            "sectionCount": 1,
                            "elementCount": 1,
                            "sectionSort": 2,
                            "elementTitle": "온세대 특송",
                            "audioKind": "audio",
                        }
                        and template_terms["sharedSundayContentProjection"]["secondPraiseStatic"] is False
                        and template_terms["sharedSundayContentProjection"]["secondPraiseMissing"] == "missing"
                        and template_terms["sharedSundayContentProjection"]["secondPraiseText"]
                        and template_terms["sharedSundayContentProjection"]["secondPraiseSongId"]
                        and template_terms["sharedSundayContentProjection"]["secondPraiseMaterializedSongId"]
                        and template_terms["sharedSundayContentProjection"]["secondPraiseMaterializedVersionId"]
                        and template_terms["sharedSundayContentProjection"]["emptySecondPraiseMaterializedSongId"] == ""
                        and template_terms["sharedSundayContentProjection"]["mainPraiseSharedTypes"] == [
                            ["sunday-first", "sunday-second"],
                            ["sunday-first", "sunday-second"],
                            [],
                        ]
                        and template_terms["sharedSundayContentProjection"]["secondOfferingText"]
                        and template_terms["sharedSundayContentProjection"]["thirdReadingRefs"] == []
                        and template_terms["sharedSundayContentProjection"]["thirdReadingMissing"] == "missing"
                        and template_terms["sharedSundayContentProjection"]["thirdSermonTitleText"] == "설교 제목"
                        and template_terms["sharedSundayContentProjection"]["thirdSermonTitleAssignee"] == "김남영 목사"
                        and template_terms["sharedSundayContentProjection"]["thirdSermonTitleStatic"] is False
                        and template_terms["sharedSundayContentProjection"]["thirdSermonBodyRefs"] == []
                        and template_terms["sharedSundayContentProjection"]["thirdSermonBodyPayloadReference"] == ""
                        and template_terms["sharedSundayContentProjection"]["thirdCitationRefs"] == []
                        and template_terms["sharedSundayContentProjection"]["thirdOfferingText"]
                        and template_terms["sharedSundayContentProjection"]["thirdOfferingStatic"] is False
                        and template_terms["sharedSundayContentProjection"]["syncedPraiseSongId"]
                        and template_terms["sharedSundayContentProjection"]["clearedPraiseSongId"] == template_terms["sharedSundayContentProjection"]["syncedPraiseSongId"]
                        and template_terms["sharedSundayContentProjection"]["syncedScriptureRefs"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                        and template_terms["sharedSundayContentProjection"]["clearedScriptureRefs"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                        and set(template_terms["sharedSundayContentProjection"]["thirdMissingSlides"]).issuperset([
                            "찬양 1", "찬양 2", "찬양 3", "찬양 4", "찬송", "대표기도", "특송",
                        ])
                        and template_terms["fullscreenSermonBodyCompatibility"] == {
                            "staticInput": False,
                            "contentState": "filled",
                            "reason": "scripture_body",
                            "slideCount": 1,
                            "savedTitle": "요한복음 21:15–25",
                            "savedReference": "요한복음 21:15–25",
                        }
                        and template_terms["worshipSongVersionFkGuard"] == {
                            "staleInvalid": True,
                            "staleSavedVersion": None,
                            "validSavedVersion": "__smoke_version_persisted__",
                            "memoOnlySavedVersion": None,
                        }
                        and template_terms["scriptureRangeInference"] == [
                            {"verse": 18, "verseEnd": 19},
                            {"verse": 20, "verseEnd": None},
                        ]
                        and len(template_terms["monthlyScaffold"]["corporatePrayerElements"]) == 3
                        and len(template_terms["monthlyScaffold"]["offeringElements"]) == 2
                        and template_terms["overflow"] <= 2
                    ):
                        pass_("service-template-terminology", json.dumps(template_terms, ensure_ascii=False))
                    else:
                        fail("service-template-terminology", json.dumps(template_terms, ensure_ascii=False))

                    youth_template = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_youth_template__', type_id: 'youth', date: '2026-07-26' };
                          const youngAdultService = { id: '__smoke_young_adult_template__', type_id: 'young-adult', date: '2026-07-26' };
                          const childrenService = { id: '__smoke_children_template__', type_id: 'children', date: '2026-07-26' };
                          const previousCalendarData = state.calendarData;
                          try {
                            // Calendar assignees are persisted at service creation, so projecting the
                            // template must not fill them live (see test_calendar_assignee_creation.cjs).
                            state.calendarData = [
                              {
                                id: '__smoke_youth_integrated__',
                                date: '2026-07-26',
                                church_schedule: '온세대 찬양예배',
                                youth_prayer: '김윤민 청년',
                                youth_offering_prayer: '박지훈 교사',
                                young_adult_prayer: '정선분 권사',
                              },
                              ...(previousCalendarData || []).filter((row) => row.date !== '2026-07-26'),
                            ];
                            const template = serviceOrderTemplate('youth', { service });
                            const projected = projectWorshipServiceItemsFromTemplate(service, []);
                            const youngAdultTemplate = serviceOrderTemplate('young-adult', { service: youngAdultService });
                            const youngAdultProjected = projectWorshipServiceItemsFromTemplate(youngAdultService, []);
                            const offering = projected.find((item) => item.label === '봉헌찬양');
                            const prayer = projected.find((item) => item.label === '대표기도');
                            const offeringPrayer = projected.find((item) => item.label === '봉헌기도');
                            const fellowship = projected.find((item) => item.label === '반별 모임');
                            const announcement = projected.find((item) => item.label === '광고');
                            const youngAdultPrayer = youngAdultProjected.find((item) => item.label === '대표기도');
                            const youngAdultAnnouncement = youngAdultProjected.find((item) => item.label === '광고');
                            const youngAdultBenediction = youngAdultProjected.find((item) => item.label === '축도');
                            const offeringSong = presenterSongForServiceItem(
                              offering,
                              serviceItemDisplayText(offering),
                              offering?.label || '',
                              service,
                            );
                            const offeringContent = resolvePresenterServiceItemContentState(
                              offering,
                              parseServiceItemMemo(offering?.memo),
                              offeringSong,
                              service,
                            );
                            const fellowshipContent = resolvePresenterServiceItemContentState(
                              { ...fellowship, raw_title: '' },
                              parseServiceItemMemo(fellowship?.memo),
                              null,
                              service,
                            );
                            return {
                              sections: template.map((step) => step.sectionKey || step.label),
                              labels: projected.map((item) => item.label || ''),
                              offeringTitle: offering?.raw_title || '',
                              offeringLinked: Boolean(
                                offering?.song_id
                                && offering?.version_id
                              ),
                              prayerAssignee: serviceItemEditableAssigneeValue(prayer, service),
                              prayerSidebarTitle: serviceSidebarChildItemTitle(prayer, service),
                              offeringPrayerAssignee: serviceItemEditableAssigneeValue(offeringPrayer, service),
                              offeringReady: offeringContent.state === 'filled' && offeringContent.reason === 'song',
                              fellowshipStatic: presenterServiceInputItem({ ...fellowship, raw_title: '' }, service) === null,
                              fellowshipContent: fellowshipContent.reason,
                              youngAdultPrayerAssignee: serviceItemEditableAssigneeValue(youngAdultPrayer, youngAdultService),
                              youngAdultPrayerSidebarTitle: serviceSidebarChildItemTitle(youngAdultPrayer, youngAdultService),
                              youngAdultBenedictionAssignee: serviceItemEditableAssigneeValue(youngAdultBenediction, youngAdultService),
                              announcementEditable: presenterServiceInputItem(announcement, service)?.mode === 'text',
                              youngAdultAnnouncementEditable: presenterServiceInputItem(youngAdultAnnouncement, youngAdultService)?.mode === 'text',
                              youngAdultSections: youngAdultTemplate.map((step) => step.sectionKey || step.label),
                              youngAdultLabels: youngAdultProjected.map((item) => item.label || ''),
                              childrenLastSection: serviceOrderTemplate('children', { service: childrenService }).at(-1)?.label || '',
                              scheduledOnIntegratedSunday: autoUpcomingPublicServiceTargets('2026-07-20')
                                .some((item) => item.typeId === 'youth' && item.date === '2026-07-26'),
                              youngAdultScheduledOnIntegratedSunday: autoUpcomingPublicServiceTargets('2026-07-20')
                                .some((item) => item.typeId === 'young-adult' && item.date === '2026-07-26'),
                            };
                          } finally {
                            state.calendarData = previousCalendarData;
                          }
                        })()
                        """
                    )
                    if youth_template == {
                        "sections": [
                            "ready", "creed", "praise", "prayer", "offering", "scripture_reading",
                            "sermon", "response_song", "announcements", "lords_prayer", "fellowship",
                        ],
                        "labels": [
                            "대기 화면", "사도신경", "찬양 1", "찬양 2", "찬양 3", "대표기도", "봉헌찬양", "봉헌기도",
                            "성경봉독", "설교 제목", "설교 본문", "인용 구절", "결단기도", "광고", "주기도문", "반별 모임",
                        ],
                        "offeringTitle": "",
                        "offeringLinked": True,
                        "prayerAssignee": "",
                        "prayerSidebarTitle": "대표기도",
                        "offeringPrayerAssignee": "",
                        "offeringReady": True,
                        "fellowshipStatic": True,
                        "fellowshipContent": "fixed_title",
                        "youngAdultPrayerAssignee": "",
                        "youngAdultPrayerSidebarTitle": "대표기도",
                        "youngAdultBenedictionAssignee": "김석범 목사",
                        "announcementEditable": True,
                        "youngAdultAnnouncementEditable": True,
                        "youngAdultSections": [
                            "ready", "creed", "prayer", "praise", "scripture_reading",
                            "sermon", "response_song", "offering", "announcements", "sending", "fellowship",
                        ],
                        "youngAdultLabels": [
                            "대기 화면", "사도신경", "대표기도", "찬양 1", "찬양 2", "찬양 3", "찬양 4",
                            "성경봉독", "설교 제목", "설교 본문", "인용 구절", "결단찬양", "결단기도",
                            "봉헌찬양", "봉헌기도", "광고", "파송찬양", "축도", "셀 모임",
                        ],
                        "childrenLastSection": "교제",
                        "scheduledOnIntegratedSunday": False,
                        "youngAdultScheduledOnIntegratedSunday": True,
                    }:
                        pass_("youth-service-template", json.dumps(youth_template, ensure_ascii=False))
                    else:
                        fail("youth-service-template", json.dumps(youth_template, ensure_ascii=False))

                    strict_song_picker = page.evaluate(
                        """
                        (() => {
                          const previous = {
                            songs: state.songs,
                            services: state.services,
                            serviceItems: state.serviceItems,
                            selectedServiceId: state.selectedServiceId,
                            selectedServiceTypeId: state.selectedServiceTypeId,
                            dirtyService: state.dirty.service,
                            showToast,
                          };
                          const service = { id: '__smoke_strict_song_service__', type_id: 'sunday-first', date: '2099-07-05', title: '' };
                          const hymn = {
                            id: '__smoke_hymn_song__',
                            title: '만복의 근원 하나님',
                            hymn_no: '1',
                            subtitle: 'Doxology',
                            metadata: {},
                            praise_types: ['hymn'],
                          };
                          hymn.versions = normalizeSongVersions(hymn, [
                            { id: '__smoke_hymn_new__', name: '새찬송가', praise_types: ['hymn'], forms: [] },
                            { id: '__smoke_hymn_unified__', name: '통일 1', hymn_no: '통 1', praise_types: ['hymn'], forms: [] },
                          ]);
                          const ccm = {
                            id: '__smoke_ccm_song__',
                            title: '은혜',
                            subtitle: '내가 누려왔던 모든 것들이',
                            metadata: { artist: '손경민' },
                            praise_types: ['ccm'],
                          };
                          ccm.versions = normalizeSongVersions(ccm, [
                            { id: '__smoke_ccm_v1__', name: 'Original', praise_types: ['ccm'], forms: [] },
                            { id: '__smoke_ccm_v2__', name: 'Female Key', praise_types: ['ccm'], forms: [] },
                          ]);
                          try {
                            state.songs = [hymn, ccm];
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.selectedServiceTypeId = service.type_id;
                            const strictItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '찬양 1',
                              raw_title: '',
                              memo: serializeServiceItemMemo({ elementType: 'praise' }),
                            }, 0);
                            const scoreItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '봉헌찬송',
                              raw_title: '',
                              memo: serializeServiceItemMemo({ elementType: 'praise', outputMode: 'score' }),
                            }, 1);
                            const hymnPraiseItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '찬양 2',
                              raw_title: '',
                              memo: serializeServiceItemMemo({ elementType: 'praise' }),
                            }, 2);
                            state.serviceItems = { [service.id]: [strictItem, scoreItem, hymnPraiseItem] };
                            updateServiceItemField({
                              dataset: { serviceItemIndex: '0', serviceItemField: 'raw_title' },
                              value: '은혜',
                            });
                            const typed = state.serviceItems[service.id][0];
                            const typedSongId = typed.song_id || '';
                            const typedVersionId = typed.version_id || '';
                            const strictResults = serviceSongPickerResults('은혜', strictItem, service).map((song) => song.id);
                            const scoreCcmResults = serviceSongPickerResults('은혜', scoreItem, service).map((song) => song.id);
                            const scoreHymnResults = serviceSongPickerResults('만복', scoreItem, service).map((song) => song.id);
                            updateServiceItemField({
                              dataset: { serviceItemIndex: '1', serviceItemField: 'raw_title' },
                              value: '1 만복의 근원 하나님',
                            });
                            const typedScore = state.serviceItems[service.id][1];
                            const typedScoreSongId = typedScore.song_id || '';
                            const typedScoreVersionId = typedScore.version_id || '';
                            const typedScoreRawTitle = typedScore.raw_title || '';
                            const versionToasts = [];
                            showToast = (message, type = 'info') => {
                              versionToasts.push({ message, type });
                            };
                            selectServiceSongForItem(0, ccm.id);
                            showToast = previous.showToast;
                            const selected = state.serviceItems[service.id][0];
                            const selectedVersionImmediately = selected.version_id || '';
                            const invalidAfterSong = serviceItemSongSelectionInvalid(selected, service);
                            updateServiceItemField({
                              dataset: { serviceItemIndex: '0', serviceItemField: 'version_id' },
                              value: '__smoke_ccm_v2__',
                            });
                            const withVersion = state.serviceItems[service.id][0];
                            const selectedVersionAfterPick = withVersion.version_id || '';
                            const invalidAfterVersion = serviceItemSongSelectionInvalid(withVersion, service);
                            selectServiceSongForItem(2, hymn.id);
                            const hymnDefaultVersion = state.serviceItems[service.id][2].version_id || '';
                            const deferredField = document.createElement('input');
                            deferredField.type = 'text';
                            deferredField.dataset.serviceItemIndex = '0';
                            deferredField.dataset.serviceItemField = 'raw_title';
                            deferredField.value = '입력 대기';
                            document.body.append(deferredField);
                            handleDetailInput({ target: deferredField });
                            const deferredBeforeEnter = state.serviceItems[service.id][0].raw_title || '';
                            let deferredPrevented = false;
                            handleDetailKeydown({
                              target: deferredField,
                              key: 'Enter',
                              preventDefault() { deferredPrevented = true; },
                            });
                            const deferredAfterEnter = state.serviceItems[service.id][0].raw_title || '';
                            deferredField.remove();
                            const strictSearchField = document.createElement('input');
                            strictSearchField.type = 'text';
                            strictSearchField.dataset.serviceItemIndex = '0';
                            strictSearchField.dataset.serviceItemField = 'raw_title';
                            strictSearchField.dataset.initialValue = '';
                            strictSearchField.dataset.presenterPreviewValue = '';
                            strictSearchField.setAttribute('data-service-song-required', 'true');
                            strictSearchField.value = '은혜 검색';
                            document.body.append(strictSearchField);
                            const strictSearchDeferred = isDeferredServiceTextInput(strictSearchField);
                            handleDetailInput({ target: strictSearchField });
                            const strictSearchAfterInput = state.serviceItems[service.id][0].raw_title || '';
                            strictSearchField.remove();
                            const oneOffThirdSpecial = normalizeServiceItem({
                              service_id: service.id,
                              label: '특송',
                              raw_title: '청년부 특송',
                              memo: serializeServiceItemMemo({ elementType: 'praise' }),
                            }, 2);
                            return {
                              strictRequires: serviceItemRequiresSongSelection(strictItem, service),
                              typedSongId,
                              typedVersionId,
                              typedScoreSongId,
                              typedScoreVersionId,
                              typedScoreRawTitle,
                              strictResults,
                              scoreCcmResults,
                              scoreHymnResults,
                              selectedSongId: selected.song_id || '',
                              selectedRawTitle: selected.raw_title || '',
                              selectedDisplayText: serviceItemDisplayText(selected),
                              selectedTitleForSave: serviceElementTitleForSave(selected, 'praise'),
                              selectedVersionId: selectedVersionImmediately,
                              versionToasts,
                              invalidAfterSong,
                              selectedVersionAfterPick,
                              invalidAfterVersion,
                              hymnDefaultVersion,
                              deferredBeforeEnter,
                              deferredAfterEnter,
                              deferredPrevented,
                              strictSearchDeferred,
                              strictSearchAfterInput,
                              renderedHasPicker: renderServiceEditorTitleControl(strictItem, 0, { service }, serviceItemEditorModel(strictItem, { service })).includes('svc-song-picker'),
                              renderedSongControlHasNativeDatalist: renderServiceEditorTitleControl(oneOffThirdSpecial, 2, { service }, serviceItemEditorModel(oneOffThirdSpecial, { service })).includes('servicePraiseOptions'),
                              thirdSpecialManual: serviceItemAllowsManualSongText(oneOffThirdSpecial, { ...service, type_id: 'sunday-main' }),
                              pickerNullMeta: renderServiceSongPickerResult({
                                id: '__smoke_null_meta__',
                                title: '메타 없는 찬양',
                                subtitle: null,
                                original_title: null,
                                praise_types: ['ccm'],
                              }, 0),
                            };
                          } finally {
                            state.songs = previous.songs;
                            state.services = previous.services;
                            state.serviceItems = previous.serviceItems;
                            state.selectedServiceId = previous.selectedServiceId;
                            state.selectedServiceTypeId = previous.selectedServiceTypeId;
                            state.dirty.service = previous.dirtyService;
                            showToast = previous.showToast || showToast;
                            renderCurrentServiceModuleDetail();
                          }
                        })()
                        """
                    )
                    if (
                        strict_song_picker["strictRequires"]
                        and strict_song_picker["typedSongId"] == ""
                        and strict_song_picker["typedVersionId"] == ""
                        and strict_song_picker["typedScoreSongId"] == ""
                        and strict_song_picker["typedScoreVersionId"] == ""
                        and strict_song_picker["typedScoreRawTitle"] == "1 만복의 근원 하나님"
                        and strict_song_picker["strictResults"] == ["__smoke_ccm_song__"]
                        and strict_song_picker["scoreCcmResults"] == ["__smoke_hymn_song__"]
                        and strict_song_picker["scoreHymnResults"] == ["__smoke_hymn_song__"]
                        and strict_song_picker["selectedSongId"] == "__smoke_ccm_song__"
                        and strict_song_picker["selectedRawTitle"] == ""
                        and strict_song_picker["selectedDisplayText"] == "은혜"
                        and strict_song_picker["selectedTitleForSave"] == ""
                        and strict_song_picker["selectedVersionId"] == "__smoke_ccm_v1__"
                        and strict_song_picker["versionToasts"] == [{
                            "message": "은혜에 여러 버전이 있어 첫 번째 버전을 우선 선택했습니다. 필요하면 버전을 골라 주세요.",
                            "type": "info",
                        }]
                        and not strict_song_picker["invalidAfterSong"]
                        and strict_song_picker["selectedVersionAfterPick"] == "__smoke_ccm_v2__"
                        and not strict_song_picker["invalidAfterVersion"]
                        and strict_song_picker["hymnDefaultVersion"] == "__smoke_hymn_new__"
                        and strict_song_picker["deferredBeforeEnter"] == ""
                        and strict_song_picker["deferredAfterEnter"] in ("", "입력 대기")
                        and strict_song_picker["deferredPrevented"]
                        and strict_song_picker["strictSearchDeferred"]
                        and strict_song_picker["strictSearchAfterInput"] == ""
                        and strict_song_picker["renderedHasPicker"]
                        and not strict_song_picker["renderedSongControlHasNativeDatalist"]
                        and strict_song_picker["thirdSpecialManual"]
                        and "null ·" not in strict_song_picker["pickerNullMeta"]
                    ):
                        pass_("service-strict-song-picker", json.dumps(strict_song_picker, ensure_ascii=False))
                    else:
                        fail("service-strict-song-picker", json.dumps(strict_song_picker, ensure_ascii=False))

                    service_title_normalization = page.evaluate(
                        """
                        () => ({
                          monthly: serviceDisplayTypeName({
                            type_id: 'monthly',
                            title: '7월 월삭예배',
                            date: '2026-07-03',
                          }),
                          otherMonth: serviceDisplayTypeName({
                            type_id: 'monthly',
                            title: '8월 월삭예배',
                            date: '2026-07-03',
                          }),
                          monthlyCustomTitle: serviceDisplayTypeName({
                            type_id: 'monthly',
                            title: '청년 연합 월삭예배',
                            date: '2026-07-03',
                          }),
                          specialCustomTitle: serviceDisplayTypeName({
                            type_id: 'special',
                            title: '청년 연합 월삭예배',
                            date: '2026-07-03',
                          }),
                          allGenerationsAlias: serviceDisplayTypeName({
                            type_id: 'sunday-main',
                            title: '주일예배 [3부]',
                            alias: '온세대 찬양예배',
                            date: '2026-07-05',
                          }),
                          youthDedicationAlias: serviceDisplayTypeName({
                            type_id: 'youth',
                            title: '청소년부 예배',
                            alias: '청소년부 제자헌신예배',
                            date: '2026-07-05',
                          }),
                          fridayFamily: serviceFamilyDisplayName({
                            type_id: 'friday',
                            date: '2026-08-21',
                            alias: '삼삼오오예배',
                            _worshipSourceRef: { friday_variant: '3355', friday_variant_name: '삼삼오오예배' },
                          }),
                          fridayVariant: serviceVariantDisplayName({
                            type_id: 'friday',
                            date: '2026-08-21',
                            alias: '삼삼오오예배',
                            _worshipSourceRef: { friday_variant: '3355', friday_variant_name: '삼삼오오예배' },
                          }),
                          fridayDetailTitle: serviceDisplayTypeName({
                            type_id: 'friday',
                            date: '2026-08-21',
                            alias: '삼삼오오예배',
                            _worshipSourceRef: { friday_variant: '3355', friday_variant_name: '삼삼오오예배' },
                          }),
                          monthlyFamily: serviceFamilyDisplayName({
                            type_id: 'monthly',
                            title: '8월 월삭예배',
                            date: '2026-08-07',
                          }),
                          monthlyVariant: serviceVariantDisplayName({
                            type_id: 'monthly',
                            title: '8월 월삭예배',
                            date: '2026-08-07',
                          }),
                          normalizedRowTitle: normalizeWorshipService({
                            id: '__title_normalization__',
                            service_type_id: 'monthly',
                            service_date: '2026-07-03',
                            title: '7월 월삭예배',
                          }).title,
                          normalizedOtherMonthRowTitle: normalizeWorshipService({
                            id: '__title_normalization_other__',
                            service_type_id: 'monthly',
                            service_date: '2026-07-03',
                            title: '8월 월삭예배',
                          }).title,
                          normalizedSundayRowTitle: normalizeWorshipService({
                            id: '__title_normalization_sunday__',
                            service_type_id: 'sunday-first',
                            service_date: '2026-07-05',
                            title: '7월 주일예배 [1부]',
                          }).title,
                        })
                        """
                    )
                    if service_title_normalization == {
                        "monthly": "월삭예배",
                        "otherMonth": "월삭예배",
                        "monthlyCustomTitle": "월삭예배",
                        "specialCustomTitle": "청년 연합 월삭예배",
                        "allGenerationsAlias": "온세대 찬양예배",
                        "youthDedicationAlias": "청소년부 제자헌신예배",
                        "fridayFamily": "금요예배",
                        "fridayVariant": "삼삼오오예배",
                        "fridayDetailTitle": "삼삼오오예배",
                        "monthlyFamily": "금요예배",
                        "monthlyVariant": "월삭예배",
                        "normalizedRowTitle": "월삭예배",
                        "normalizedOtherMonthRowTitle": "월삭예배",
                        "normalizedSundayRowTitle": "주일예배 [1부]",
                    }:
                        pass_("service-title-normalization", json.dumps(service_title_normalization, ensure_ascii=False))
                    else:
                        fail("service-title-normalization", json.dumps(service_title_normalization, ensure_ascii=False))

                service_for_slides = select_service_with_slides(page)
                if not service_for_slides:
                    skip("presenter-slides", "No service with generated slides.")
                else:
                    page.wait_for_selector("#servicePresenterControls", timeout=5000)
                    slide_count = page.locator(".svc-slide-thumb").count()
                    if slide_count == service_for_slides["slides"]:
                        pass_("presenter-slides", json.dumps(service_for_slides, ensure_ascii=False))
                    else:
                        fail("presenter-slides", f"dom={slide_count} state={service_for_slides}")
                    presenter_terms = page.evaluate(
                        """
                        (() => ({
                          sidebarHeadings: [...document.querySelectorAll('.service-sidebar-head span')]
                            .map((node) => node.textContent.trim()),
                          outlineHeaderTail: document.querySelector('.service-sidebar-section--current > .service-sidebar-head > small')?.textContent.trim() || '',
                          outlineRows: document.querySelectorAll('.service-outline-row').length,
                          outlineGroups: document.querySelectorAll('.service-outline-group').length,
                          multiOutlineGroups: document.querySelectorAll('.service-outline-group .service-outline-children .service-outline-row--child:nth-child(2)').length,
                          childPraiseMarkers: [...document.querySelectorAll('.service-outline-group')]
                            .filter((group) => group.querySelector('.service-outline-row--section strong')?.textContent.trim() === '찬양')
                            .flatMap((group) => [...group.querySelectorAll('.service-outline-row--child strong')].map((node) => node.textContent.trim()))
                            .filter((text) => text === '찬양').length,
                          praiseChildTargetContract: [...document.querySelectorAll('.service-outline-group')]
                            .filter((group) => group.querySelector('.service-outline-row--section strong')?.textContent.trim() === '찬양')
                            .flatMap((group) => [...group.querySelectorAll('.service-outline-row--child[data-service-outline-slide]')]
                              .map((row) => {
                                const target = serviceOutlineSlideTarget(row) || {};
                                return {
                                  label: row.querySelector('.service-outline-kind')?.textContent.trim() || '',
                                  dataSlide: Number(row.dataset.serviceOutlineSlide),
                                  targetSlide: Number(target.slideIndex ?? -1),
                                };
                              })),
                          outlineCountText: [...document.querySelectorAll('.service-outline-row small')]
                            .map((node) => node.textContent.replace(/\\s+/g, ' ').trim())
                            .filter((text) => /슬라이드|항목|곡/.test(text)),
                          outlineStartNumbers: [...document.querySelectorAll('.service-outline-row[data-service-outline-slide]:not([disabled])')]
                            .slice(0, 12)
                            .map((row) => ({
                              slide: Number(row.dataset.serviceOutlineSlide),
                              start: row.querySelector('.service-outline-start')?.textContent.trim() || '',
                              align: getComputedStyle(row.querySelector('.service-outline-start')).textAlign,
                              child: row.classList.contains('service-outline-row--child')
                            })),
                          outlineChildMetrics: (() => {
                            const row = [...document.querySelectorAll('.service-outline-row--child')]
                              .find((candidate) => candidate.querySelector('strong'));
                            const title = row?.querySelector('strong');
                            if (!row || !title) return null;
                            const rowStyle = getComputedStyle(row);
                            const titleStyle = getComputedStyle(title);
                            return {
                              rowHeight: Number(row.getBoundingClientRect().height.toFixed(2)),
                              rowMinHeight: rowStyle.minHeight,
                              titleFontSize: titleStyle.fontSize,
                              titleLineHeight: titleStyle.lineHeight,
                            };
                          })(),
                          outlineHierarchyAlignment: (() => {
                            const group = [...document.querySelectorAll('.service-outline-group')]
                              .find((candidate) => candidate.querySelector('.service-outline-row--section strong')
                                && candidate.querySelector('.service-outline-row--child .service-outline-kind'));
                            const sectionTitle = group?.querySelector('.service-outline-row--section strong');
                            const childLabel = group?.querySelector('.service-outline-row--child .service-outline-kind');
                            const guide = group?.querySelector('.service-outline-children');
                            if (!group || !sectionTitle || !childLabel || !guide) return null;
                            const sectionLeft = sectionTitle.getBoundingClientRect().left;
                            const childLeft = childLabel.getBoundingClientRect().left;
                            return {
                              sectionLeft: Number(sectionLeft.toFixed(2)),
                              childLeft: Number(childLeft.toFixed(2)),
                              guideLeft: Number(guide.getBoundingClientRect().left.toFixed(2)),
                              guideBorderLeftWidth: getComputedStyle(guide).borderLeftWidth,
                              sectionMinusChild: Number((sectionLeft - childLeft).toFixed(2)),
                              childMinusGuide: Number((childLeft - guide.getBoundingClientRect().left).toFixed(2)),
                            };
                          })(),
                          outlineMissingBadgeContract: (() => {
                            const service = selectedServiceForEditor();
                            const titledItem = {
                              id: '__smoke_outline_titled_missing__',
                              service_id: service?.id || '__service__',
                              label: '찬양 1',
                              raw_title: '10 전능왕 오셔서',
                            };
                            const emptyItem = {
                              id: '__smoke_outline_empty_missing__',
                              service_id: service?.id || '__service__',
                              label: '찬양 2',
                              raw_title: '',
                            };
                            const titledHtml = renderServiceOutlineChildRow(service || { id: '__service__' }, titledItem, 0, -1, [{
                              id: '__smoke_outline_titled_missing__:missing',
                              elementId: '__smoke_outline_titled_missing__',
                              missingContent: true,
                            }]);
                            const emptyHtml = renderServiceOutlineChildRow(service || { id: '__service__' }, emptyItem, 1, -1, [{
                              id: '__smoke_outline_empty_missing__:missing',
                              elementId: '__smoke_outline_empty_missing__',
                              missingContent: true,
                            }]);
                            const titledHost = document.createElement('div');
                            const emptyHost = document.createElement('div');
                            titledHost.innerHTML = titledHtml;
                            emptyHost.innerHTML = emptyHtml;
                            return {
                              titledText: titledHost.textContent.replace(/\\s+/g, ' ').trim(),
                              titledBadges: titledHost.querySelectorAll('.service-outline-badge').length,
                              emptyText: emptyHost.textContent.replace(/\\s+/g, ' ').trim(),
                              emptyBadges: emptyHost.querySelectorAll('.service-outline-badge').length,
                            };
                          })(),
                          collapsedBoardSubgroups: document.querySelectorAll('.svc-board-subgroup.collapsed-head').length,
                          mainPraiseSubgroupLabels: (() => {
                            const group = { kind: 'main-praise', label: '찬양', subgroups: [] };
                            addPresenterSlideToSubgroup(group, {
                              slideIndex: 0,
                              slide: { type: 'praise-section-title', sectionLabel: '찬양', elementId: 'marker' }
                            });
                            addPresenterSlideToSubgroup(group, {
                              slideIndex: 1,
                              slide: { type: 'image', sectionLabel: '찬양 2', elementTitle: '하나님의 크신 사랑', elementId: 'song-1' }
                            });
                            return group.subgroups.map((subgroup) => subgroup.label);
                          })(),
                          formBadgeLabelContract: [
                            presenterFormGroupLabel({ marker: 'CB' }),
                            presenterFormGroupLabel({ formLabel: 'Chorus B' }),
                            presenterFormGroupLabel({ marker: 'C B' }),
                          ],
                          formBadgeRenderContract: (() => {
                            const html = renderPresenterSlideThumb({ type: 'image', formKey: 'cb' }, 108, -1, '__service__', 'CB');
                            return {
                              hasDisplay: html.includes('Chorus B'),
                              hasRaw: html.includes('>CB<'),
                              aria: html.includes('aria-label="Chorus B"'),
                            };
                          })(),
                          elementNameTitleContract: (() => {
                            const welcomeItem = {
                              label: '환영',
                              raw_title: '환영\\n헤세드 찬양단',
                              memo: serializeServiceItemMemo({ elementType: 'title_content' }),
                            };
                            const multilineCreedItem = {
                              label: '사도신경',
                              raw_title: '나는 전능하신 아버지 하나님, 천지의 창조주를 믿습니다.\\n나는 그의 유일하신 아들, 우리 주 예수 그리스도를 믿습니다.',
                              memo: serializeServiceItemMemo({ elementType: 'body_text' }),
                            };
                            const mainPraiseTitle = presenterBoardSubgroupContentTitle({
                              sectionKey: 'praise',
                              sectionLabel: '찬양',
                              elementLabel: '환영',
                              elementTitle: '환영',
                              type: 'title-assignee',
                              missingContent: true,
                            }, '찬양 1');
                            const entranceTitle = presenterBoardSubgroupContentTitle({
                              sectionKey: 'praise',
                              sectionLabel: '찬양',
                              elementLabel: '입례찬양',
                              elementTitle: '입례찬양',
                              type: 'lyrics',
                            }, '찬양 5');
                            const corruptedConnectedPraise = {
                              groupId: '__smoke_sidebar_medley_three__',
                              role: 'primary',
                              title: '온 맘 다해 + 주님 마음 내게 주소서 + 주께 가까이',
                              orderTitle: '온 맘 다해 – 주님 마음 내게 주소서 – 주께 가까이',
                              itemIds: ['__smoke_medley_3__', '__smoke_medley_4__', '__smoke_medley_5__'],
                            };
                            return {
                              welcomeSidebar: serviceSidebarChildItemTitle(welcomeItem),
                              welcomeSidebarParts: serviceSidebarChildItemDisplayParts(welcomeItem),
                              multilineSidebar: serviceSidebarChildItemTitle(multilineCreedItem),
                              multilineSidebarParts: serviceSidebarChildItemDisplayParts(multilineCreedItem),
                              praiseSidebarParts: serviceSidebarChildItemDisplayParts({
                                label: '찬양 1',
                                raw_title: '은혜 은혜',
                                memo: serializeServiceItemMemo({ elementType: 'praise' }),
                              }),
                              connectedPraiseSidebarParts: serviceSidebarChildItemDisplayParts({
                                label: '찬양 6',
                                raw_title: '함께 지어져 가네',
                                memo: serializeServiceItemMemo({
                                  elementType: 'praise',
                                  connectedPraise: {
                                    groupId: '__smoke_sidebar_medley__',
                                    role: 'primary',
                                    title: '함께 지어져 가네 + 성도의 노래',
                                    orderTitle: '찬양 6–7',
                                  },
                                }),
                              }),
                              connectedPraiseSidebar: serviceSidebarChildItemTitle({
                                label: '찬양 6',
                                raw_title: '함께 지어져 가네',
                                memo: serializeServiceItemMemo({
                                  elementType: 'praise',
                                  connectedPraise: {
                                    groupId: '__smoke_sidebar_medley__',
                                    role: 'primary',
                                    title: '함께 지어져 가네 + 성도의 노래',
                                    orderTitle: '찬양 6–7',
                                  },
                                }),
                              }),
                              connectedThreePraiseSidebarParts: serviceSidebarChildItemDisplayParts({
                                label: '찬양 3',
                                raw_title: '온 맘 다해',
                                memo: serializeServiceItemMemo({
                                  elementType: 'praise',
                                  connectedPraise: corruptedConnectedPraise,
                                }),
                              }),
                              connectedThreePraiseBoardTitle: presenterBoardSubgroupContentTitle({
                                sectionKey: 'praise',
                                sectionLabel: '찬양',
                                elementLabel: '찬양 3',
                                connectedPraise: corruptedConnectedPraise,
                              }, '3–5'),
                              connectedThreePraiseBoardLabel: connectedPraiseSubgroupRangeLabel(corruptedConnectedPraise, { label: '찬양 3' }),
                              mainPraiseTitle,
                              entranceTitle,
                            };
                          })(),
                          doxologyScoreSectionTitle: (() => {
                            const section = presenterSectionForServiceItem({
                              id: 'smoke-doxology',
                              label: '찬양',
                              _worshipSectionKey: 'doxology',
                              raw_title: '이 천지간 만물들아'
                            }, 0, '이 천지간 만물들아');
                            return presenterScoreImageSlidesFromAsset(
                              { slides: [{ url: '/assets/smoke-score.png' }] },
                              { id: 'smoke-doxology', label: '찬양' },
                              section,
                              0,
                              '이 천지간 만물들아',
                              '찬양'
                            )[0]?.sectionTitle || '';
                          })(),
                          readyShortcutRows: document.querySelectorAll('.service-outline-row--ready').length,
                          announcementTitleContract: (() => {
                            const group = {
                              sectionKey: 'announcements',
                              sectionTitle: '광고'
                            };
                            const items = [
                              { label: '교회소식', raw_title: '교회소식', _worshipSectionKey: 'announcements' },
                              { label: '새가족환영', raw_title: '새가족환영', _worshipSectionKey: 'announcements' },
                            ];
                            return {
                              section: serviceSidebarSectionTitle(group, items[0]),
                              children: items.map((item) => serviceSidebarChildItemTitle(item))
                            };
                          })(),
                          sectionDisplayTitleAudit: [
                            ['sending', '주기도문'],
                            ['sending', '축도'],
                            ['sending', '파송찬송'],
                            ['closing_visual', '마무리'],
                            ['closing_visual', '폐회찬송'],
                            ['creed', '사도신경'],
                            ['offering', '봉헌찬양'],
                            ['response_song', '결단찬양'],
                            ['announcements', '새가족환영'],
                            ['sermon', '설교 본문'],
                            ['scripture_reading', '겔 8:14'],
                            ['custom_section', '특별 순서'],
                          ].map(([sectionKey, title]) => ({
                            sectionKey,
                            title,
                            sidebar: serviceSidebarSectionTitle(
                              { sectionKey, sectionTitle: title },
                              { label: title, _worshipSectionKey: sectionKey },
                            ),
                            board: createPresenterSlideGroup(
                              { sectionKey, sectionTitle: title, sectionId: `${sectionKey}:${title}` },
                              0,
                            ).title,
                          })),
                          editorFields: [...document.querySelectorAll('.service-sidebar-editor label > span')]
                            .map((node) => node.textContent.trim()),
                          hasLegacyDrawer: Boolean(document.querySelector('.svc-edit-drawer')),
                          status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                          modeTabLabels: [...document.querySelectorAll('.svc-header .svc-mode-tab span')]
                            .map((node) => node.textContent.trim()),
                          jumpLabel: document.querySelector('[data-presenter-jump-button]')?.getAttribute('aria-label') || '',
	                          controlLabels: [...document.querySelectorAll('.svc-presenter-mini-label')]
	                            .map((node) => node.textContent.trim()),
	                          pageTabLabel: currentPageTabTitle(),
	                          actionButtonTexts: [...document.querySelectorAll('.svc-action-text-btn')]
	                            .map((node) => node.textContent.trim()),
                          actionGroups: document.querySelectorAll('.svc-presenter-action-group').length,
                          helpLabel: document.querySelector('[data-presenter-help] > summary')?.getAttribute('aria-label') || '',
                          helpText: document.querySelector('.svc-presenter-help-panel')?.textContent.replace(/\\s+/g, ' ').trim() || '',
                          firstThumbLabel: document.querySelector('.svc-slide-thumb')?.getAttribute('aria-label') || '',
                          firstOutlineLabel: document.querySelector('.service-outline-row[data-service-outline-slide]')?.getAttribute('aria-label') || '',
                          selectedSectionRows: document.querySelectorAll('.service-outline-row--section.selected').length,
                          sidebarWidth: Math.round(document.querySelector('.sidebar')?.getBoundingClientRect().width || 0),
                          actionLabels: [...document.querySelectorAll('.service-sidebar-editor-actions [aria-label]')]
                            .slice(0, 4)
                            .map((node) => node.getAttribute('aria-label')),
                          elementTypes: [...document.querySelectorAll('[data-service-item-field="element_type"] option')]
                            .map((node) => node.textContent.trim())
                            .slice(0, 12),
                          visibleBadTerms: /컴포넌트|\\bcomponents\\b|\\bComponent\\b|\\bItem\\b|\\bElement\\b|\\bElem_/.test(document.body.innerText),
                          visiblePresentationTerms: /\\bPPTX?\\b|PowerPoint/i.test(document.body.innerText),
                          legacyArtifactLabels: [...document.querySelectorAll('[aria-label]')]
                            .map((node) => node.getAttribute('aria-label') || '')
                            .filter((label) => /\\b(?:Elem|Element|Section|Slide)_/i.test(label)),
                          overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                        }))()
                        """
                    )
                    if (
                        "순서" not in presenter_terms["sidebarHeadings"]
                        and presenter_terms["outlineHeaderTail"] == ""
                        and "편집" not in presenter_terms["sidebarHeadings"]
                        and "최근 예배" not in presenter_terms["sidebarHeadings"]
                        and presenter_terms["outlineRows"] >= 2
                        and presenter_terms["outlineGroups"] >= 1
                        and presenter_terms["multiOutlineGroups"] >= 1
                        and presenter_terms["childPraiseMarkers"] == 0
                        and presenter_terms["praiseChildTargetContract"]
                        and all(
                            item["label"].startswith("찬양")
                            and item["dataSlide"] == item["targetSlide"]
                            for item in presenter_terms["praiseChildTargetContract"]
                        )
                        and presenter_terms["outlineCountText"] == []
                        and presenter_terms["outlineChildMetrics"] is not None
                        and presenter_terms["outlineChildMetrics"]["rowHeight"] <= 40
                        and presenter_terms["outlineChildMetrics"]["rowMinHeight"] == "36px"
                        and presenter_terms["outlineChildMetrics"]["titleFontSize"] == "12px"
                        and presenter_terms["outlineChildMetrics"]["titleLineHeight"] == "16px"
                        and presenter_terms["outlineHierarchyAlignment"] is not None
                        and abs(presenter_terms["outlineHierarchyAlignment"]["sectionMinusChild"]) <= 0.5
                        and presenter_terms["outlineHierarchyAlignment"]["childMinusGuide"] >= 6
                        and presenter_terms["outlineHierarchyAlignment"]["guideBorderLeftWidth"] == "0px"
                        and presenter_terms["outlineMissingBadgeContract"] == {
                            "titledText": "찬양 1 10 전능왕 오셔서",
                            "titledBadges": 0,
                            "emptyText": "찬양 2 입력 필요",
                            "emptyBadges": 1,
                        }
                        and all(
                            (
                                item["start"] == ""
                                if item["child"]
                                else item["start"] in ("", str(item["slide"] + 1)) and item["align"] == "right"
                            )
                            for item in presenter_terms["outlineStartNumbers"]
                        )
                        and presenter_terms["collapsedBoardSubgroups"] == 0
                        and presenter_terms["mainPraiseSubgroupLabels"] == ["환영", "찬양 1"]
                        and presenter_terms["formBadgeLabelContract"] == ["Chorus B", "Chorus B", "Chorus B"]
                        and presenter_terms["formBadgeRenderContract"] == {"hasDisplay": True, "hasRaw": False, "aria": True}
                        and presenter_terms["elementNameTitleContract"] == {
                            "welcomeSidebar": "환영 · 헤세드 찬양단",
                            "welcomeSidebarParts": {"meta": "환영", "title": "헤세드 찬양단"},
                            "multilineSidebar": "사도신경",
                            "multilineSidebarParts": {"meta": "사도신경", "title": ""},
                            "praiseSidebarParts": {"meta": "찬양 1", "title": "은혜 은혜"},
                            "connectedPraiseSidebarParts": {"meta": "찬양 6–7", "title": "함께 지어져 가네 + 성도의 노래"},
                            "connectedPraiseSidebar": "찬양 6–7 · 함께 지어져 가네 + 성도의 노래",
                            "connectedThreePraiseSidebarParts": {"meta": "찬양 3–5", "title": "온 맘 다해 + 주님 마음 내게 주소서 + 주께 가까이"},
                            "connectedThreePraiseBoardTitle": "온 맘 다해 + 주님 마음 내게 주소서 + 주께 가까이",
                            "connectedThreePraiseBoardLabel": "찬양 3–5",
                            "mainPraiseTitle": "환영",
                            "entranceTitle": "입례찬양",
                        }
                        and presenter_terms["doxologyScoreSectionTitle"] == "송영"
                        and presenter_terms["readyShortcutRows"] <= 1
                        and presenter_terms["announcementTitleContract"] == {
                            "section": "광고",
                            "children": ["교회소식", "새가족환영"],
                        }
                        and presenter_terms["sectionDisplayTitleAudit"] == [
                            {"sectionKey": "sending", "title": "주기도문", "sidebar": "파송", "board": "파송"},
                            {"sectionKey": "sending", "title": "축도", "sidebar": "파송", "board": "파송"},
                            {"sectionKey": "sending", "title": "파송찬송", "sidebar": "파송", "board": "파송"},
                            {"sectionKey": "closing_visual", "title": "마무리", "sidebar": "폐회", "board": "폐회"},
                            {"sectionKey": "closing_visual", "title": "폐회찬송", "sidebar": "폐회", "board": "폐회"},
                            {"sectionKey": "creed", "title": "사도신경", "sidebar": "신앙고백", "board": "신앙고백"},
                            {"sectionKey": "offering", "title": "봉헌찬양", "sidebar": "봉헌", "board": "봉헌"},
                            {"sectionKey": "response_song", "title": "결단찬양", "sidebar": "결단", "board": "결단"},
                            {"sectionKey": "announcements", "title": "새가족환영", "sidebar": "광고", "board": "광고"},
                            {"sectionKey": "sermon", "title": "설교 본문", "sidebar": "설교", "board": "설교"},
                            {"sectionKey": "scripture_reading", "title": "겔 8:14", "sidebar": "성경봉독", "board": "성경봉독"},
                            {"sectionKey": "custom_section", "title": "특별 순서", "sidebar": "특별 순서", "board": "특별 순서"},
                        ]
                        and presenter_terms["editorFields"] == []
                        and not presenter_terms["hasLegacyDrawer"]
                        and presenter_terms["actionLabels"] == []
                        and presenter_terms["elementTypes"] == []
                        and presenter_terms["status"] == "준비"
                        and presenter_terms["modeTabLabels"] == []
	                        and presenter_terms["jumpLabel"] == "슬라이드로 이동"
	                        and presenter_terms["controlLabels"] == ["슬라이드"]
	                        and "송출" not in presenter_terms["pageTabLabel"]
	                        and presenter_terms["pageTabLabel"]
	                        and presenter_terms["actionButtonTexts"] == ["송출", "숨김"]
                        and presenter_terms["actionGroups"] == 3
                        and presenter_terms["helpLabel"] == "도움말"
                        and "Esc 2번 송출 종료" in presenter_terms["helpText"]
                        and "브라우저 전체화면" not in presenter_terms["helpText"]
                        and "출력 창에서 F" not in presenter_terms["helpText"]
                        and "번호 + Enter" in presenter_terms["helpText"]
                        and "0 + Enter" in presenter_terms["helpText"]
                        and "0 또는 없는 번호" not in presenter_terms["helpText"]
                        and "1번 슬라이드 선택" in presenter_terms["firstThumbLabel"]
                        and "준비 선택" in presenter_terms["firstOutlineLabel"]
                        and presenter_terms["selectedSectionRows"] == 0
                        and presenter_terms["sidebarWidth"] >= 228
                        and not presenter_terms["visibleBadTerms"]
                        and not presenter_terms["visiblePresentationTerms"]
                        and not presenter_terms["legacyArtifactLabels"]
                        and presenter_terms["overflow"] <= 2
                    ):
                        pass_("presenter-terminology", json.dumps(presenter_terms, ensure_ascii=False))
                    else:
                        fail("presenter-terminology", json.dumps(presenter_terms, ensure_ascii=False))

                    presenter_font_contract = page.evaluate(
                        """
                        (() => {
                          const createHost = (className) => {
                            const host = document.createElement('div');
                            host.className = className;
                            host.style.cssText = 'position:absolute;left:-10000px;top:0;';
                            host.innerHTML = `
                            <span id="fontDisplay" style="font-size: var(--presenter-size-display)"></span>
                            <span id="fontSection" style="font-size: var(--presenter-size-section)"></span>
                            <span id="fontBody" style="font-size: var(--presenter-size-body)"></span>
                            <span id="fontLyrics" style="font-size: var(--presenter-size-lyrics)"></span>
                            <span id="fontMeta" style="font-size: var(--presenter-size-meta)"></span>
                            <span id="fontScriptureBar" style="font-size: var(--presenter-scripture-bar-size)"></span>
                            <span id="fontScriptureClean" style="font-size: var(--presenter-scripture-clean-size)"></span>
                            <span id="fontScriptureReadingText" style="font-size: var(--presenter-scripture-reading-text-size)"></span>
                          `;
                            document.body.appendChild(host);
                            return host;
                          };
                          const readContract = (host) => {
                            const hostStyles = getComputedStyle(host);
                            const font = (id) => getComputedStyle(host.querySelector(`#${id}`)).fontSize;
                            return {
                              unit: hostStyles.getPropertyValue('--presenter-stage-unit').trim(),
                              barHeight: hostStyles.getPropertyValue('--presenter-output-bar-height').trim(),
                              outputBg: hostStyles.getPropertyValue('--presenter-output-bg').trim(),
                              tokenDisplay: hostStyles.getPropertyValue('--presenter-size-display').trim(),
                              tokenBody: hostStyles.getPropertyValue('--presenter-size-body').trim(),
                              display: font('fontDisplay'),
                              section: font('fontSection'),
                              body: font('fontBody'),
                              lyrics: font('fontLyrics'),
                              meta: font('fontMeta'),
                              scriptureBar: font('fontScriptureBar'),
                              scriptureClean: font('fontScriptureClean'),
                              scriptureReadingText: font('fontScriptureReadingText'),
                            };
                          };
                          const chromakeyHost = createHost('presenter-output-root');
                          const cleanHost = createHost('presenter-output-root no-chromakey');
                          const result = {
                            chromakey: readContract(chromakeyHost),
                            clean: readContract(cleanHost),
                          };
                          chromakeyHost.remove();
                          cleanHost.remove();
                          return result;
                        })()
                        """
                    )
                    if (
                        presenter_font_contract["chromakey"]["unit"] == "0.0520833333cqw"
                        and presenter_font_contract["chromakey"]["barHeight"] == "18%"
                        and presenter_font_contract["chromakey"]["outputBg"] == "#00ff00"
                        and presenter_font_contract["chromakey"]["display"] == "67.5px"
                        and presenter_font_contract["chromakey"]["section"] == "52.5px"
                        and presenter_font_contract["chromakey"]["body"] == "52.5px"
                        and presenter_font_contract["chromakey"]["lyrics"] == "52.5px"
                        and presenter_font_contract["chromakey"]["meta"] == "37.5px"
                        and presenter_font_contract["chromakey"]["scriptureBar"] == "52.5px"
                        and presenter_font_contract["chromakey"]["scriptureClean"] == "52.5px"
                        and presenter_font_contract["chromakey"]["scriptureReadingText"] == "67.5px"
                        and presenter_font_contract["clean"]["display"] == "127.5px"
                        and presenter_font_contract["clean"]["outputBg"] == "#000"
                        and presenter_font_contract["clean"]["section"] == "105px"
                        and presenter_font_contract["clean"]["body"] == "75px"
                        and presenter_font_contract["clean"]["lyrics"] == "78.75px"
                        and presenter_font_contract["clean"]["meta"] == "75px"
                        and presenter_font_contract["clean"]["scriptureBar"] == "52.5px"
                        and presenter_font_contract["clean"]["scriptureClean"] == "52.5px"
                        and presenter_font_contract["clean"]["scriptureReadingText"] == "67.5px"
                    ):
                        pass_("presenter-font-contract", json.dumps(presenter_font_contract, ensure_ascii=False))
                    else:
                        fail("presenter-font-contract", json.dumps(presenter_font_contract, ensure_ascii=False))

                    sorter_state = page.evaluate(
                        """
                        (serviceId) => {
                          state.presenter.outputWindow = null;
                          state.presenter.outputConnectedAt = 0;
                          state.presenter.serviceId = null;
                          state.presenterBoardSelection = {
                            serviceId: null,
                            elementKey: '',
                            indexes: [],
                            anchorIndex: null,
                            drag: null,
                            clipboard: null
                          };
                          renderPresenterDetail();
                          const first = document.querySelector('.svc-slide-thumb[data-presenter-index][data-service-id]');
                          first?.click();
                          const selectedAfterClick = document.querySelectorAll('.svc-slide-thumb.selected').length;
                          const activeAfterClick = document.querySelectorAll('.svc-slide-thumb.active').length;
                          openPresenterSectionEditorForSlide(serviceId, Number(first?.dataset.presenterIndex || 0));
                          const editor = document.querySelector('[data-presenter-section-editor]');
                          const reference = parseBibleReference('ckd 1:1');
                          const beforeItems = JSON.parse(JSON.stringify(state.serviceItems[serviceId] || []));
                          const editableSectionKey = (() => {
                            const counts = {};
                            for (const item of state.serviceItems[serviceId] || []) {
                              const key = item._worshipSectionKey || '';
                              if (!key) continue;
                              counts[key] = (counts[key] || 0) + 1;
                            }
                            return Object.entries(counts).find(([, count]) => count > 1)?.[0] || '';
                          })();
                          let editorContract = {};
                          if (editableSectionKey) {
                            state.presenterSectionEditor = { serviceId, itemId: '', sectionKey: `section-key:${editableSectionKey}` };
                            renderPresenterDetail();
                            const sectionInput = document.querySelector('[data-presenter-section-field="label"]');
                            const contextBefore = presenterSectionEditorContext(state.services.find((svc) => svc.id === serviceId));
                            const labelsBefore = (contextBefore?.sectionItems || []).map((item) => item.label);
                            if (sectionInput) {
                              sectionInput.value = '편집 섹션';
                              updatePresenterSectionField(sectionInput);
                            }
                            const addRoot = document.querySelector('[data-presenter-section-editor]');
                            const typeSelect = addRoot?.querySelector('[data-presenter-section-new-type]');
                            const nameInput = addRoot?.querySelector('[data-presenter-section-new-name]');
                            if (typeSelect && nameInput) {
                              typeSelect.value = 'title';
                              nameInput.value = '새 엘리멘트';
                              runPresenterSectionItemAction('add', -1);
                            }
                            const contextAfter = presenterSectionEditorContext(state.services.find((svc) => svc.id === serviceId));
                            editorContract = {
                              sectionTitle: contextAfter?.sectionTitle || '',
                              labelsPreserved: labelsBefore.every((label, index) => (contextAfter?.sectionItems || [])[index]?.label === label),
                              addedElementLabel: (contextAfter?.sectionItems || []).some((item) => item.label === '새 엘리멘트'),
                            };
                          }
                          const result = {
                            selectedAfterClick,
                            activeAfterClick,
                            selectionService: state.presenterBoardSelection.serviceId || '',
                            editorOpen: Boolean(editor),
                            editorItems: editor ? editor.querySelectorAll('.presenter-section-editor-item').length : 0,
                            editorHasAdd: Boolean(editor?.querySelector('[data-presenter-section-add]')),
                            restoredReference: reference ? `${reference.book.code} ${reference.chapter}:${reference.verse}` : '',
                            editorContract,
                          };
                          state.serviceItems[serviceId] = beforeItems;
                          state.dirty.service = false;
                          state.presenterSectionEditor = null;
                          renderPresenterDetail();
                          return result;
                        }
                        """,
                        service_for_slides["id"],
                    )
                    if (
                        sorter_state["selectedAfterClick"] == 1
                        and sorter_state["activeAfterClick"] == 0
                        and sorter_state["selectionService"] == service_for_slides["id"]
                        and sorter_state["editorOpen"]
                        and sorter_state["editorItems"] >= 1
                        and sorter_state["editorHasAdd"]
                        and sorter_state["restoredReference"] == "GEN 1:1"
                        and sorter_state["editorContract"].get("sectionTitle") == "편집 섹션"
                        and sorter_state["editorContract"].get("labelsPreserved")
                        and sorter_state["editorContract"].get("addedElementLabel")
                    ):
                        pass_("presenter-sorter-and-editor", json.dumps(sorter_state, ensure_ascii=False))
                    else:
                        fail("presenter-sorter-and-editor", json.dumps(sorter_state, ensure_ascii=False))

                    context_menu_state = page.evaluate(
                        """
                        async (serviceId) => {
                          state.presenter.outputWindow = null;
                          state.presenter.outputConnectedAt = 0;
                          state.presenter.serviceId = null;
                          state.presenterSectionEditor = null;
                          state.presenterBoardSelection = {
                            serviceId: null,
                            elementKey: '',
                            indexes: [],
                            anchorIndex: null,
                            drag: null,
                            clipboard: null
                          };
                          renderPresenterDetail();
                          const thumbs = [...document.querySelectorAll('.svc-slide-thumb[data-presenter-index][data-service-id]')];
                          const target = thumbs.find((thumb) => Number(thumb.dataset.presenterIndex) > 0) || thumbs[0] || null;
                          target?.dispatchEvent(new MouseEvent('contextmenu', {
                            bubbles: true,
                            cancelable: true,
                            button: 2,
                            clientX: 80,
                            clientY: 80,
                          }));
                          const selectedImmediately = [...document.querySelectorAll('.svc-slide-thumb.selected')]
                            .map((thumb) => Number(thumb.dataset.presenterIndex));
                          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                          const editor = document.querySelector('[data-presenter-section-editor]');
                          const result = {
                            targetIndex: Number(target?.dataset.presenterIndex ?? -1),
                            selectedImmediately,
                            selectedAfterOpen: [...document.querySelectorAll('.svc-slide-thumb.selected')]
                              .map((thumb) => Number(thumb.dataset.presenterIndex)),
                            activeAfterOpen: document.querySelectorAll('.svc-slide-thumb.active').length,
                            editorOpen: Boolean(editor),
                            editorTitle: editor?.querySelector('.presenter-section-editor-head h3')?.textContent.trim() || '',
                            transition: getComputedStyle(editor?.querySelector('.presenter-section-editor') || document.body).animationName || '',
                          };
                          state.presenterSectionEditor = null;
                          renderPresenterDetail();
                          return result;
                        }
                        """,
                        service_for_slides["id"],
                    )
                    if (
                        context_menu_state["targetIndex"] >= 0
                        and context_menu_state["selectedImmediately"] == [context_menu_state["targetIndex"]]
                        and context_menu_state["selectedAfterOpen"] == [context_menu_state["targetIndex"]]
                        and context_menu_state["activeAfterOpen"] == 0
                        and context_menu_state["editorOpen"]
                        and context_menu_state["editorTitle"]
                        and context_menu_state["transition"] == "presenter-section-editor-in"
                    ):
                        pass_("presenter-context-menu-flow", json.dumps(context_menu_state, ensure_ascii=False))
                    else:
                        fail("presenter-context-menu-flow", json.dumps(context_menu_state, ensure_ascii=False))

                    outline_scroll_seed = page.evaluate(
                        """
                        () => {
                          delete window.__mindexOutlineScrollTarget;
                          delete window.__mindexOutlineScrollTo;
                          if (!window.__mindexOriginalScrollIntoView) {
                            window.__mindexOriginalScrollIntoView = Element.prototype.scrollIntoView;
                          }
                          if (!window.__mindexOriginalDetailScrollTo) {
                            window.__mindexOriginalDetailScrollTo = Element.prototype.scrollTo;
                          }
                          Element.prototype.scrollIntoView = function(options) {
                            if (this.matches?.('.svc-board-subgroup, .svc-slide-thumb')) {
                              const thumb = this.matches('.svc-slide-thumb')
                                ? this
                                : this.querySelector('.svc-slide-thumb[data-presenter-index][data-service-id]');
                              window.__mindexOutlineScrollTarget = {
                                className: this.className || '',
                                itemIndex: Number(this.dataset.serviceItemIndex ?? -1),
                                serviceId: thumb?.dataset.serviceId || '',
                                index: Number(thumb?.dataset.presenterIndex ?? -1),
                                block: options?.block || '',
                                behavior: options?.behavior || ''
                              };
                            }
                            return window.__mindexOriginalScrollIntoView.call(this, options);
                          };
                          Element.prototype.scrollTo = function(options) {
                            if (this.matches?.('.detail-pane')) {
                              window.__mindexOutlineScrollTo = {
                                top: Number(options?.top ?? -1),
                                behavior: options?.behavior || ''
                              };
                            }
                            return window.__mindexOriginalDetailScrollTo.call(this, options);
                          };
                          const rows = [...document.querySelectorAll('.service-outline-row[data-service-outline-slide]:not([disabled])')]
                            .filter((row) => Number(row.dataset.serviceOutlineSlide) > 0);
                          const praiseChild = rows.find((candidate) => (
                            candidate.classList.contains('service-outline-row--child')
                            && candidate.closest('.service-outline-group')
                              ?.querySelector('.service-outline-row--section strong')
                              ?.textContent.trim() === '찬양'
                          ));
                          const row = praiseChild || rows[rows.length - 1] || null;
                          if (!row) return null;
                          row.dataset.smokeOutlineScroll = '1';
                          const target = serviceOutlineSlideTarget(row) || {};
                          return {
                            serviceId: row.dataset.serviceOutlineService || '',
                            itemIndex: Number(row.dataset.serviceOutlineItemIndex ?? -1),
                            index: Number(target.slideIndex ?? row.dataset.serviceOutlineSlide),
                            text: row.textContent.replace(/\\s+/g, ' ').trim()
                          };
                        }
                        """,
                    )
                    if outline_scroll_seed:
                        page.evaluate(
                            "() => document.querySelector('[data-smoke-outline-scroll=\"1\"]')?.click()"
                        )
                        page.wait_for_timeout(350)
                        outline_scroll_state = page.evaluate(
                            """
                            (expected) => {
                              const target = window.__mindexOutlineScrollTarget || {};
                              const activeThumb = document.querySelector(`.svc-slide-thumb.active[data-presenter-index="${expected.index}"]`);
                              const targetThumb = document.querySelector(`.svc-slide-thumb[data-service-id="${expected.serviceId}"][data-presenter-index="${expected.index}"]`);
                              const activeTarget = activeThumb?.closest('.svc-board-subgroup')
                                || targetThumb?.closest('.svc-board-subgroup')
                                || activeThumb
                                || targetThumb;
                              const pane = document.querySelector('.detail-pane');
                              const targetRect = activeTarget?.getBoundingClientRect();
                              const paneRect = pane?.getBoundingClientRect();
                              const visible = Boolean(targetRect && paneRect
                                && targetRect.top < paneRect.bottom
                                && targetRect.bottom > paneRect.top
                                && targetRect.left < paneRect.right
                                && targetRect.right > paneRect.left);
                              Element.prototype.scrollIntoView = window.__mindexOriginalScrollIntoView;
                              Element.prototype.scrollTo = window.__mindexOriginalDetailScrollTo;
                              const activeSubgroup = activeTarget?.closest?.('.svc-board-subgroup') || activeTarget;
                              const sticky = document.querySelector('.detail-pane .svc-presenter-top');
                              const stickyRect = sticky?.getBoundingClientRect();
                              const activeRect = activeSubgroup?.getBoundingClientRect();
                              return {
                                expected,
                                target,
                                scrollTo: window.__mindexOutlineScrollTo || {},
                                activeTarget: {
                                  className: activeSubgroup?.className || '',
                                  itemIndex: Number(activeSubgroup?.dataset?.serviceItemIndex ?? -1),
                                  top: activeRect ? Math.round(activeRect.top) : null,
                                },
                                stickyBottom: stickyRect ? Math.round(stickyRect.bottom) : null,
                                belowSticky: Boolean(activeRect && (!stickyRect || activeRect.top >= stickyRect.bottom - 2)),
                                presenterIndex: state.presenter.index,
                                activeThumbs: document.querySelectorAll(`.svc-slide-thumb.active[data-presenter-index="${expected.index}"]`).length,
                                targetThumbs: document.querySelectorAll(`.svc-slide-thumb[data-service-id="${expected.serviceId}"][data-presenter-index="${expected.index}"]`).length,
                                selectedThumbs: document.querySelectorAll(`.svc-slide-thumb.selected[data-presenter-index="${expected.index}"]`).length,
                                visible
                              };
                            }
                            """,
                            outline_scroll_seed,
                        )
                        scroll_target = outline_scroll_state["target"]
                        active_target = outline_scroll_state["activeTarget"]
                        scroll_to = outline_scroll_state["scrollTo"]
                        scroll_ok = (
                            (
                                not scroll_target
                                and scroll_to.get("behavior") in ("auto", "smooth")
                                and "svc-board-subgroup" in active_target["className"]
                                and (
                                    outline_scroll_seed["itemIndex"] < 0
                                    or active_target.get("itemIndex") == outline_scroll_seed["itemIndex"]
                                )
                            )
                            or (
                                scroll_target["serviceId"] == outline_scroll_seed["serviceId"]
                                and scroll_target["index"] == outline_scroll_state["presenterIndex"]
                                and (
                                    outline_scroll_seed["itemIndex"] < 0
                                    or scroll_target.get("itemIndex") == outline_scroll_seed["itemIndex"]
                                )
                                and "svc-board-subgroup" in scroll_target["className"]
                                and scroll_target["block"] == "start"
                                and scroll_target["behavior"] in ("auto", "smooth")
                            )
                        )
                        if (
                            scroll_ok
                            and outline_scroll_state["visible"]
                            and outline_scroll_state["belowSticky"]
                            and (
                                outline_scroll_state["presenterIndex"] >= 0
                                or outline_scroll_state["selectedThumbs"] >= 1
                            )
                        ):
                            pass_("presenter-outline-scroll", json.dumps(outline_scroll_state, ensure_ascii=False))
                        else:
                            fail("presenter-outline-scroll", json.dumps(outline_scroll_state, ensure_ascii=False))
                    else:
                        skip("presenter-outline-scroll", "No outline row with slide target.")

                    page.evaluate(
                        """
                        (serviceId) => {
                          if (state.presenter.serviceId === serviceId) {
                            state.presenter.index = 0;
                            state.presenter.safetyBlank = false;
                            state.presenter.liveScripture = { ...state.presenter.liveScripture, active: false, slide: null };
                            state.presenter.livePraise = emptyLivePraiseState(state.presenter.livePraise?.draft || state.presenter.livePraise?.query || "");
                            renderPresenterControlState(serviceId);
                          }
                        }
                        """,
                        service_for_slides["id"],
                    )

                    page.evaluate(
                        """
                        (serviceId) => {
                          state.module = 'service';
                          state.selectedServiceId = serviceId;
                          const service = state.services.find((item) => item.id === serviceId);
                          state.selectedServiceTypeId = service?.type_id || state.selectedServiceTypeId;
                          render();
                        }
                        """,
                        service_for_slides["id"],
                    )
                    page.wait_for_selector("#servicePresenterControls", timeout=5000)
                    authoring_state = page.evaluate(
                        """
                        (() => {
                          const root = document.querySelector('.presenter-viewer');
                          const rect = root?.getBoundingClientRect();
                          const board = document.querySelector('#servicePresenterControls');
                          const boardRect = board?.getBoundingClientRect();
                          return {
                            mounted: Boolean(root),
                            controllerTitleRemoved: !document.querySelector('.presenter-viewer .svc-service-title')
                              && !document.querySelector('.presenter-viewer .svc-date-text'),
                            presenterHeaderRemoved: !document.querySelector('.presenter-viewer .svc-header'),
                            boardTop: Math.round(boardRect?.top || 0),
                            rootTop: Math.round(rect?.top || 0),
                            topGap: Math.round((boardRect?.top || 0) - (rect?.top || 0)),
                            hasReadonly: Boolean(document.querySelector('.service-readonly-view')),
                            hasPresenterControls: Boolean(document.querySelector('#servicePresenterControls')),
                            module: state.module,
                            openState: state.servicePrepEditorOpenId || '',
                            width: Math.round(rect?.width || 0),
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                          };
                        })()
                        """
                    )
                    if (
                        authoring_state["mounted"]
                        and authoring_state["controllerTitleRemoved"]
                        and authoring_state["presenterHeaderRemoved"]
                        and 0 <= authoring_state["topGap"] <= 8
                        and not authoring_state["hasReadonly"]
                        and authoring_state["hasPresenterControls"]
                        and authoring_state["module"] in ("service", "presenter")
                        and not authoring_state["openState"]
                        and authoring_state["width"] >= 900
                        and authoring_state["overflow"] <= 2
                    ):
                        pass_("service-opens-presenter", json.dumps(authoring_state, ensure_ascii=False))
                    else:
                        fail("service-opens-presenter", json.dumps(authoring_state, ensure_ascii=False))

                    presenter_header_input = page.evaluate(
                        """
                        (() => {
                          const service = state.services.find((item) => item.id === state.selectedServiceId);
                          state.module = 'presenter';
                          state.presenter.viewServiceId = service?.id || state.selectedServiceId;
                          renderModuleSwitcher();
                          const target = servicePrepEditorItems(service?.id || '')
                            .find((item) => presenterServiceInputItem(item, service));
                          state.selectedServiceItemIndex = Number.isInteger(target?._origIndex) ? target._origIndex : null;
                          renderServiceList();
                          renderPresenterDetail();
                          const legacyContext = document.querySelector('.service-sidebar-input-context');
                          const rightSidebar = document.querySelector('#mindexRightSidebar');
                          const bulkInput = rightSidebar?.querySelector('.svc-presenter-side-panel [data-presenter-preparation-input]');
                          const bulkButton = rightSidebar?.querySelector('.svc-presenter-side-panel [data-presenter-preparation-apply]');
                          const sidePanel = rightSidebar?.querySelector('.svc-presenter-side-panel');
                          const topbarToggle = document.querySelector('#presenterRightSidebarBtn');
                          const headerToggle = document.querySelector('.svc-header-actions [data-presenter-right-sidebar-toggle]');
                          const sidebarContext = document.querySelector('.service-sidebar-presenter-context');
                          const bulkTemplate = document.createElement('template');
                          bulkTemplate.innerHTML = renderPresenterSidebarPreparationInput(service).trim();
                          const bulkStatus = bulkTemplate.content.querySelector('.service-sidebar-head small')?.textContent.trim() || '';
                          if (bulkInput) {
                            bulkInput.value = '찬양 1: 평화 하나님의 평강이';
                            bulkInput.dispatchEvent(new Event('input', { bubbles: true }));
                          }
                          const topbarActionButtons = ['themeBtn', 'saveAllBtn']
                            .map((id) => {
                              const node = document.getElementById(id);
                              const rect = node?.getBoundingClientRect();
                              const style = node ? getComputedStyle(node) : null;
                              return rect ? {
                                id,
                                top: Math.round(rect.top),
                                bottom: Math.round(rect.bottom),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                opacity: Number(style?.opacity || 0),
                              } : null;
                            })
                            .filter(Boolean);
                          const topbarRect = document.querySelector('.topbar-actions')?.getBoundingClientRect();
                          const bulkInputRect = bulkInput?.getBoundingClientRect();
                          const bulkButtonRect = bulkButton?.getBoundingClientRect();
                          const bulkActionsRect = bulkButton?.closest('.svc-presenter-preparation-actions')?.getBoundingClientRect();
                          const bulkExamples = rightSidebar?.querySelector('.svc-presenter-preparation-examples');
                          const controlGroups = [...document.querySelectorAll('.svc-board-subgroup-controls')];
                          const controls = [...document.querySelectorAll('.svc-board-subgroup-controls [data-service-item-field]')];
                          const firstControlStyle = controlGroups[0] ? getComputedStyle(controlGroups[0]) : null;
                          const firstHead = controlGroups[0]?.closest('.svc-board-subgroup')?.querySelector('.svc-board-subgroup-head');
                          const firstHeadRowStyle = controlGroups[0]?.parentElement ? getComputedStyle(controlGroups[0].parentElement) : null;
                          const firstControlRect = controlGroups[0]?.getBoundingClientRect();
                          const firstHeadRect = firstHead?.getBoundingClientRect();
                          const headerLabels = controlGroups.map((node) => {
                            const header = node.closest('.svc-board-subgroup')?.querySelector('.svc-board-subgroup-head');
                            return header?.textContent?.replace(/\\s+/g, ' ').trim() || '';
                          });
                          const songFields = controls.filter((node) => node.getAttribute('data-service-item-field') === 'raw_title');
                          const editableLabels = servicePrepEditorItems(service?.id || '')
                            .filter((item) => presenterServiceInputHasEditableField(item, service))
                            .map((item) => item.label || '');
                          return {
                            module: state.module,
                            legacyContextRemoved: !legacyContext,
                            rightSidebarMounted: Boolean(rightSidebar && !rightSidebar.hidden),
                            topbarToggleVisible: Boolean(topbarToggle && !topbarToggle.hidden),
                            saveHidden: Boolean(document.querySelector('#saveAllBtn')?.hidden),
                            saveVisible: Boolean(document.querySelector('#saveAllBtn:not([hidden])')),
                            headerToggleRemoved: !headerToggle,
                            railMounted: Boolean(rightSidebar?.querySelector('.svc-presenter-input-rail')),
                            sidePanelMounted: Boolean(sidePanel),
                            sidebarContext: sidebarContext?.textContent?.replace(/\\s+/g, ' ').trim() || '',
                            controlGroupCount: controlGroups.length,
                            headRowDisplay: firstHeadRowStyle?.display || '',
                            controlGroupJustify: firstControlStyle?.justifyContent || '',
                            controlGroupMaxWidth: firstControlStyle?.maxWidth || '',
                            controlBelowHead: firstControlRect && firstHeadRect
                              ? Math.round(firstControlRect.top - firstHeadRect.bottom)
                              : null,
                            controlAlignedLeft: firstControlRect && firstHeadRect
                              ? Math.round(firstControlRect.left - firstHeadRect.left)
                              : null,
                            fieldCount: controls.length,
                            songFieldCount: songFields.length,
                            headerLabels,
                            editableLabels,
                            bulkInput: Boolean(bulkInput),
                            bulkButton: Boolean(bulkButton),
                            bulkExamples: Boolean(bulkExamples),
                            bulkPlaceholder: bulkInput?.getAttribute('placeholder') || '',
                            bulkButtonLabel: bulkButton?.textContent?.replace(/\s+/g, ' ').trim() || '',
                            bulkButtonTitle: bulkButton?.getAttribute('title') || '',
                            bulkButtonWidth: Math.round(bulkButtonRect?.width || 0),
                            bulkActionsWidth: Math.round(bulkActionsRect?.width || 0),
                            bulkInputWidth: Math.round(bulkInputRect?.width || 0),
                            bulkStatus,
                            bulkDraft: state.presenterPreparationDrafts[service?.id || ''] || '',
                            rightRailDesktop: document.body.dataset.module === 'presenter' && window.innerWidth > 900,
                            topbarActionButtons,
                            actionsInTopbar: topbarActionButtons.every((button) =>
                              topbarRect
                              && button.top >= Math.round(topbarRect.top)
                              && button.bottom <= Math.round(topbarRect.bottom)
                            ),
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                          };
                        })()
                        """
                    )
                    if (
                        presenter_header_input["legacyContextRemoved"]
                        and presenter_header_input["rightSidebarMounted"]
                        and not presenter_header_input["topbarToggleVisible"]
                        and not presenter_header_input["saveHidden"]
                        and presenter_header_input["saveVisible"]
                        and presenter_header_input["headerToggleRemoved"]
                        and presenter_header_input["railMounted"]
                        and presenter_header_input["sidePanelMounted"]
                        and (
                            presenter_header_input["module"] != "presenter"
                            or presenter_header_input["sidebarContext"]
                        )
                        and presenter_header_input["controlGroupCount"] >= 8
                        and presenter_header_input["headRowDisplay"] == "grid"
                        and presenter_header_input["controlGroupJustify"] in ("flex-start", "normal")
                        and presenter_header_input["controlGroupMaxWidth"] in ("100%", "760px")
                        and presenter_header_input["controlBelowHead"] is not None
                        and 0 <= presenter_header_input["controlBelowHead"] <= 12
                        and abs(presenter_header_input["controlAlignedLeft"] or 0) <= 2
                        and presenter_header_input["fieldCount"] >= 12
                        and presenter_header_input["songFieldCount"] >= 5
                        and presenter_header_input["bulkInput"] == presenter_header_input["bulkButton"]
                        and not presenter_header_input["bulkExamples"]
                        and presenter_header_input["bulkPlaceholder"].startswith("찬양1:")
                        and presenter_header_input["bulkButtonLabel"] == "반영"
                        and presenter_header_input["bulkButtonTitle"] == "입력창에서 Enter 두 번 또는 ⌘/Ctrl+Enter"
                        and presenter_header_input["bulkButtonWidth"] >= presenter_header_input["bulkActionsWidth"] - 2
                        and presenter_header_input["bulkButtonWidth"] >= presenter_header_input["bulkInputWidth"] - 2
                        and (
                            presenter_header_input["bulkStatus"] == ""
                            or presenter_header_input["bulkStatus"] in ("불러오는 중", "입력 완료", "입력 없음")
                            or presenter_header_input["bulkStatus"].endswith("개 입력 필요")
                        )
                        and presenter_header_input["bulkDraft"] in ("", "찬양 1: 평화 하나님의 평강이")
                        and (
                            not presenter_header_input["rightRailDesktop"]
                            or (
                                [button["id"] for button in presenter_header_input["topbarActionButtons"]] == ["themeBtn", "saveAllBtn"]
                                and presenter_header_input["actionsInTopbar"]
                                and all(button["width"] == button["height"] and button["width"] >= 32 for button in presenter_header_input["topbarActionButtons"])
                            )
                        )
                        and any("찬양" in label for label in presenter_header_input["headerLabels"])
                        and any("성경봉독" in label for label in presenter_header_input["headerLabels"])
                        and any("설교 제목" in label for label in presenter_header_input["headerLabels"])
                        and "결단기도" not in presenter_header_input["editableLabels"]
                        and presenter_header_input["overflow"] <= 2
                    ):
                        pass_("presenter-header-input-controls", json.dumps(presenter_header_input, ensure_ascii=False))
                    else:
                        fail("presenter-header-input-controls", json.dumps(presenter_header_input, ensure_ascii=False))

                    presenter_preparation_apply_click = page.evaluate(
                        """
                        (async () => {
                          const input = document.querySelector('#mindexRightSidebar [data-presenter-preparation-input]');
                          const button = document.querySelector('#mindexRightSidebar [data-presenter-preparation-apply]');
                          if (!input || !button) return { ready: false, reason: 'control' };
                          const serviceId = input.dataset.serviceId || state.selectedServiceId;
                          const normalizeLabel = (value) => String(value || '').replace(/\\s+/g, '');
                          const target = findPresenterPreparationProjectedItem(
                            state.services.find((service) => service.id === serviceId),
                            '대표기도'
                          );
                          if (!target) return { ready: false, reason: 'target' };
                          const index = getServiceItems(serviceId).findIndex((item) => item.id === target.id);
                          if (index < 0) return { ready: false, reason: 'index' };
                          const item = getServiceItems(serviceId)[index];
                          const original = {
                            draft: state.presenterPreparationDrafts[serviceId],
                            items: getServiceItems(serviceId).map((entry) => ({ ...entry })),
                            rawTitle: item.raw_title,
                            assignee: item.assignee,
                            dirty: state.dirty.service,
                          };
                          const toasts = [];
                          const originalToast = showToast;
                          try {
                            showToast = (message, type = 'info') => toasts.push({ message, type });
                            delete state.presenterPreparationDrafts[serviceId];
                            state.dirty.service = false;
                            input.value = '대표기도: 테스트 권사';
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            await applyPresenterPreparationInput(serviceId, { draft: input.value });
                            await new Promise((resolve) => window.setTimeout(resolve, 80));
                            return {
                              ready: true,
                              assignee: getServiceItems(serviceId)[index]?.assignee || '',
                              assignees: getServiceItems(serviceId)
                                .filter((entry) => normalizeLabel(entry.label || '') === normalizeLabel('대표기도'))
                                .map((entry) => entry.assignee || ''),
                              draftCleared: !(serviceId in state.presenterPreparationDrafts),
                              dirty: state.dirty.service,
                              toasts,
                            };
                          } finally {
                            showToast = originalToast;
                            state.serviceItems[serviceId] = original.items;
                            if (original.draft == null) delete state.presenterPreparationDrafts[serviceId];
                            else state.presenterPreparationDrafts[serviceId] = original.draft;
                            state.dirty.service = original.dirty;
                            render();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_apply_click.get("ready")
                        and "테스트 권사" in presenter_preparation_apply_click["assignees"]
                        and presenter_preparation_apply_click["draftCleared"]
                        and presenter_preparation_apply_click["dirty"]
                        and presenter_preparation_apply_click["toasts"]
                        and presenter_preparation_apply_click["toasts"][-1]["type"] == "info"
                    ):
                        pass_("presenter-preparation-apply-click", json.dumps(presenter_preparation_apply_click, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-apply-click", json.dumps(presenter_preparation_apply_click, ensure_ascii=False))

                    presenter_input_enter_commit_guard = page.evaluate(
                        """
                        (async () => {
                          if (
                            typeof handleDetailInput !== 'function'
                            || typeof handleDetailChange !== 'function'
                            || typeof handleDetailKeydown !== 'function'
                            || typeof saveCommittedServiceItem !== 'function'
                          ) return { ready: false };
                          const fields = [
                            ...document.querySelectorAll('.svc-board-subgroup-controls input[data-service-item-field="raw_title"]')
                          ];
                          const field = fields.find((candidate) => {
                            const candidateServiceId = candidate.dataset.serviceId || state.selectedServiceId;
                            const candidateIndex = Number(candidate.dataset.serviceItemIndex);
                            const candidateItem = (state.serviceItems[candidateServiceId] || [])[candidateIndex];
                            const candidateService = state.services.find((service) => service.id === candidateServiceId);
                            const rect = candidate.getBoundingClientRect();
                            return candidate.isConnected
                              && refs.detailPane?.contains(candidate)
                              && rect.width > 0
                              && rect.height > 0
                              && !candidate.disabled
                              && !candidate.readOnly
                              && candidateItem
                              && !serviceItemRequiresSongSelection(candidateItem, candidateService)
                              && !isScriptureBodyServiceItem(candidateItem);
                          });
                          if (!field) return { ready: false, reason: 'field' };
                          const serviceId = field.dataset.serviceId || state.selectedServiceId;
                          const index = Number(field.dataset.serviceItemIndex);
                          const item = () => (state.serviceItems[serviceId] || [])[index] || {};
                          const previousSaveCommittedServiceItem = saveCommittedServiceItem;
                          const originalValue = item().raw_title || '';
                          const originalDirty = state.dirty.service;
                          const saves = [];
                          const documentEvents = [];
                          const rememberDocumentEvent = (event) => documentEvents.push(event.type);
                          try {
                            saveCommittedServiceItem = (itemIndex, savedServiceId, options = {}) => {
                              saves.push({ itemIndex: Number(itemIndex), serviceId: savedServiceId, silent: Boolean(options.silent) });
                            };
                            document.addEventListener('input', rememberDocumentEvent);
                            document.addEventListener('change', rememberDocumentEvent);
                            document.addEventListener('focusout', rememberDocumentEvent);
                            document.addEventListener('keydown', rememberDocumentEvent);
                            state.dirty.service = false;
                            field.dataset.initialValue = field.value;
                            field.dataset.presenterPreviewValue = field.value;
                            field.value = '마 23:1';
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            await new Promise((resolve) => window.setTimeout(resolve, 650));
                            const afterInput = item().raw_title || '';
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            const afterChange = item().raw_title || '';
                            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
                            const enterDispatched = field.dispatchEvent(enterEvent);
                            const afterEnter = item().raw_title || '';
                            field.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: document.body }));
                            const afterFocusout = item().raw_title || '';
                            return {
                              ready: true,
                              serviceId,
                              index,
                              afterInput,
                              afterChange,
                              afterEnter,
                              afterFocusout,
                              saves,
                              prevented: !enterDispatched || enterEvent.defaultPrevented,
                              documentEvents,
                              dirty: state.dirty.service,
                            };
                          } finally {
                            document.removeEventListener('input', rememberDocumentEvent);
                            document.removeEventListener('change', rememberDocumentEvent);
                            document.removeEventListener('focusout', rememberDocumentEvent);
                            document.removeEventListener('keydown', rememberDocumentEvent);
                            saveCommittedServiceItem = previousSaveCommittedServiceItem;
                            if (item()) item().raw_title = originalValue;
                            state.dirty.service = originalDirty;
                            if (typeof renderPresenterDetail === 'function') renderPresenterDetail();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_input_enter_commit_guard.get("ready")
                        and presenter_input_enter_commit_guard["afterInput"] != "마 23:1"
                        and presenter_input_enter_commit_guard["afterChange"] != "마 23:1"
                        and presenter_input_enter_commit_guard["afterEnter"] == "마 23:1"
                        and presenter_input_enter_commit_guard["afterFocusout"] == "마 23:1"
                        and len(presenter_input_enter_commit_guard["saves"]) == 1
                        and presenter_input_enter_commit_guard["saves"][0]["itemIndex"] == presenter_input_enter_commit_guard["index"]
                        and presenter_input_enter_commit_guard["saves"][0]["serviceId"] == presenter_input_enter_commit_guard["serviceId"]
                        and presenter_input_enter_commit_guard["saves"][0]["silent"] is True
                        and presenter_input_enter_commit_guard["prevented"]
                        and presenter_input_enter_commit_guard["documentEvents"] == []
                    ):
                        pass_("presenter-input-enter-commit-guard", json.dumps(presenter_input_enter_commit_guard, ensure_ascii=False))
                    else:
                        fail("presenter-input-enter-commit-guard", json.dumps(presenter_input_enter_commit_guard, ensure_ascii=False))

                    presenter_item_apply_flow = page.evaluate(
                        """
                        (async () => {
                          if (
                            typeof commitServiceItemInputs !== 'function'
                            || typeof renderPresenterBoardSubgroupInputControls !== 'function'
                          ) return { ready: false, reason: 'functions' };
                          const service = { id: '__smoke_item_apply_flow__', type_id: 'special', date: '2026-08-02' };
                          const item = normalizeServiceItem({
                            id: '__smoke_item_apply_flow_item__',
                            service_id: service.id,
                            label: '특송',
                            raw_title: '이전 제목',
                            assignee: '이전 담당',
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'manual_praise',
                              outputMode: 'lyrics',
                              slides: ['이전 가사'],
                            }),
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const originalServices = state.services;
                          const originalItems = state.serviceItems[service.id];
                          const originalSelectedServiceId = state.selectedServiceId;
                          const originalResolveAndSave = resolveAndSaveCommittedServiceItem;
                          const originalDirty = state.dirty.service;
                          const host = document.createElement('div');
                          const saves = [];
                          try {
                            state.services = [service, ...originalServices.filter((candidate) => candidate.id !== service.id)];
                            state.serviceItems[service.id] = [item];
                            state.selectedServiceId = service.id;
                            state.dirty.service = false;
                            const html = renderPresenterBoardSubgroupInputControls(service.id, {
                              id: item.id,
                              label: '특송',
                              title: '이전 제목',
                              slides: [{ slide: { elementId: item.id } }],
                            });
                            refs.detailPane.appendChild(host);
                            host.innerHTML = html;
                            const title = host.querySelector('[data-service-item-field="raw_title"]');
                            const lyrics = host.querySelector('[data-service-item-field="manual_praise_lyrics"]');
                            const assignee = host.querySelector('[data-service-item-field="assignee"]');
                            const button = host.querySelector('[data-service-item-commit]');
                            if (!title || !lyrics || !assignee || !button) {
                              return { ready: false, reason: 'controls', html };
                            }
                            title.value = '새 특송 제목';
                            lyrics.value = '첫 줄\\n\\n후렴';
                            assignee.value = '새 담당';
                            resolveAndSaveCommittedServiceItem = async (serviceId, index, options = {}) => {
                              saves.push({ serviceId, index: Number(index), renderAfterSave: options.renderAfterSave, resolveScriptureBeforeSave: options.resolveScriptureBeforeSave });
                              return true;
                            };
                            await commitServiceItemInputs(button.dataset.serviceId, Number(button.dataset.serviceItemIndex));
                            const updated = state.serviceItems[service.id][0] || {};
                            const memo = parseServiceItemMemo(updated.memo);
                            return {
                              ready: true,
                              buttonLabel: button.textContent.replace(/\\s+/g, ' ').trim(),
                              rawTitle: updated.raw_title || '',
                              assignee: updated.assignee || '',
                              inputMode: memo.inputMode || '',
                              slides: memo.slides || [],
                              saves,
                              dirty: state.dirty.service,
                            };
                          } finally {
                            resolveAndSaveCommittedServiceItem = originalResolveAndSave;
                            state.services = originalServices;
                            if (originalItems === undefined) delete state.serviceItems[service.id];
                            else state.serviceItems[service.id] = originalItems;
                            state.selectedServiceId = originalSelectedServiceId;
                            state.dirty.service = originalDirty;
                            host.remove();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_item_apply_flow.get("ready")
                        and presenter_item_apply_flow["buttonLabel"] == "저장"
                        and presenter_item_apply_flow["rawTitle"] == "새 특송 제목"
                        and presenter_item_apply_flow["assignee"] == "새 담당"
                        and presenter_item_apply_flow["inputMode"] == "manual_praise"
                        and presenter_item_apply_flow["slides"] == ["첫 줄", "후렴"]
                        and presenter_item_apply_flow["saves"] == [{
                            "serviceId": "__smoke_item_apply_flow__",
                            "index": 0,
                            "renderAfterSave": False,
                            "resolveScriptureBeforeSave": False,
                        }]
                    ):
                        pass_("presenter-item-apply-flow", json.dumps(presenter_item_apply_flow, ensure_ascii=False))
                    else:
                        fail("presenter-item-apply-flow", json.dumps(presenter_item_apply_flow, ensure_ascii=False))

                    service_source_view = page.evaluate(
                        """
                        (() => {
                          if (
                            typeof buildServiceSourceText !== 'function'
                            || typeof renderServicePresenterControls !== 'function'
                          ) return { ready: false, reason: 'functions' };
                          const service = { id: '__smoke_source_view__', type_id: 'special', date: '2026-08-02', alias: '찬양예배' };
                          const items = [
                            normalizeServiceItem({
                              id: '__smoke_source_creed__',
                              service_id: service.id,
                              label: '사도신경',
                              raw_title: '사도신경',
                              memo: serializeServiceItemMemo({
                                elementType: 'title',
                                inputMode: 'none',
                              }),
                              _worshipSectionKey: 'creed',
                              _worshipSectionTitle: '신앙고백',
                            }, 0),
                            normalizeServiceItem({
                              id: '__smoke_source_reading__',
                              service_id: service.id,
                              label: '성경봉독',
                              raw_title: '느 6:15-19; 느 7:1-4',
                              memo: serializeServiceItemMemo({
                                elementType: 'scripture_body',
                                inputMode: 'scripture',
                                scriptureReferences: ['느 6:15-19', '느 7:1-4'],
                              }),
                              _worshipSectionKey: 'scripture_reading',
                              _worshipSectionTitle: '성경봉독',
                            }, 1),
                            normalizeServiceItem({
                              id: '__smoke_source_special__',
                              service_id: service.id,
                              label: '특송',
                              raw_title: '하나님의 나팔 소리',
                              assignee: '할렐루야 찬양대',
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'manual_praise',
                                outputMode: 'lyrics',
                                slides: ['누가 나와 함께 가려오', '주가 예비하신 그곳'],
                              }),
                              _worshipSectionKey: 'special_song',
                              _worshipSectionTitle: '특송',
                            }, 2),
                            normalizeServiceItem({
                              id: '__smoke_source_video__',
                              service_id: service.id,
                              label: '교회소식',
                              memo: serializeServiceItemMemo({
                                elementType: 'video',
                                inputMode: 'asset',
                                asset: { kind: 'video', name: '광고.mp4', url: 'https://example.com/ad.mp4' },
                              }),
                              _worshipSectionKey: 'announcements',
                              _worshipSectionTitle: '광고',
                            }, 3),
                          ];
                          const originalServices = state.services;
                          const originalItems = state.serviceItems[service.id];
                          try {
                            state.services = [service, ...originalServices.filter((candidate) => candidate.id !== service.id)];
                            state.serviceItems[service.id] = items;
                            const source = buildServiceSourceText(service);
                            const html = renderServicePresenterControls(service, [], false, 0);
                            return {
                              ready: true,
                              source,
                              hasRoot: html.includes('id="servicePresenterControls"'),
                              hasSourcePanel: html.includes('svc-source-panel'),
                              hasEditableText: html.includes('data-service-source-text="__smoke_source_view__"') && !html.includes('readonly'),
                              hasSignature: html.includes('data-service-source-signature='),
                              hasApply: html.includes('data-service-source-apply="__smoke_source_view__"'),
                              hasCopy: html.includes('data-service-source-copy="__smoke_source_view__"'),
                            };
                          } finally {
                            state.services = originalServices;
                            if (originalItems === undefined) delete state.serviceItems[service.id];
                            else state.serviceItems[service.id] = originalItems;
                          }
                        })()
                        """
                    )
                    if (
                        service_source_view.get("ready")
                        and service_source_view.get("hasRoot")
                        and service_source_view.get("hasSourcePanel")
                        and service_source_view.get("hasEditableText")
                        and service_source_view.get("hasSignature")
                        and service_source_view.get("hasApply")
                        and service_source_view.get("hasCopy")
                        and "# " not in service_source_view["source"]
                        and "date:" not in service_source_view["source"]
                        and "[신앙고백]" not in service_source_view["source"]
                        and "사도신경" not in service_source_view["source"]
                        and "[성경봉독]" in service_source_view["source"]
                        and "성경봉독: 느헤미야 6:15–19; 7:1–4" in service_source_view["source"]
                        and "특송: 하나님의 나팔 소리" in service_source_view["source"]
                        and "  담당: 할렐루야 찬양대" in service_source_view["source"]
                        and "  가사:" in service_source_view["source"]
                        and "    누가 나와 함께 가려오" in service_source_view["source"]
                        and "  파일: 광고.mp4" in service_source_view["source"]
                        and "  링크: https://example.com/ad.mp4" in service_source_view["source"]
                    ):
                        pass_("service-source-view-export", json.dumps(service_source_view, ensure_ascii=False))
                    else:
                        fail("service-source-view-export", json.dumps(service_source_view, ensure_ascii=False))

                    service_source_view_apply = page.evaluate(
                        """
                        (() => {
                          if (
                            typeof applyServiceSourceText !== 'function'
                            || typeof renderServiceSourcePanel !== 'function'
                          ) return { ready: false, reason: 'functions' };
                          const service = { id: '__smoke_source_apply__', type_id: 'special', date: '2026-08-02', alias: '찬양예배' };
                          const items = [
                            normalizeServiceItem({
                              id: '__smoke_source_apply_reading__',
                              service_id: service.id,
                              label: '성경봉독',
                              raw_title: '느 6:15-19',
                              memo: serializeServiceItemMemo({
                                elementType: 'scripture_body',
                                inputMode: 'scripture',
                                scriptureReferences: ['느 6:15-19'],
                              }),
                              _worshipSectionKey: 'scripture_reading',
                              _worshipSectionTitle: '성경봉독',
                            }, 0),
                            normalizeServiceItem({
                              id: '__smoke_source_apply_special__',
                              service_id: service.id,
                              label: '특송',
                              raw_title: '이전 특송',
                              assignee: '이전 담당',
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'manual_praise',
                                outputMode: 'lyrics',
                                slides: ['이전 가사'],
                              }),
                              _worshipSectionKey: 'special_song',
                              _worshipSectionTitle: '특송',
                            }, 1),
                            normalizeServiceItem({
                              id: '__smoke_source_apply_video__',
                              service_id: service.id,
                              label: '교회소식',
                              memo: serializeServiceItemMemo({
                                elementType: 'video',
                                inputMode: 'asset',
                                asset: { kind: 'video', name: '이전광고.mp4', url: 'https://example.com/old.mp4' },
                              }),
                              _worshipSectionKey: 'announcements',
                              _worshipSectionTitle: '광고',
                            }, 2),
                          ];
                          const originalServices = state.services;
                          const originalItems = state.serviceItems[service.id];
                          const originalSelectedServiceId = state.selectedServiceId;
                          const originalModule = state.module;
                          const originalDetailHtml = refs.detailPane.innerHTML;
                          const originalRenderCurrent = renderCurrentServiceModuleDetail;
                          const originalRenderServiceList = renderServiceList;
                          const originalRefreshPresenter = refreshPresenterForService;
                          const originalDirty = state.dirty.service;
                          const recoveryKey = worshipRecoveryLatestSnapshotKey(service.id);
                          const originalRecovery = localStorage.getItem(recoveryKey);
                          const refreshes = [];
                          let rendered = false;
                          try {
                            state.services = [service, ...originalServices.filter((candidate) => candidate.id !== service.id)];
                            state.serviceItems[service.id] = items;
                            state.selectedServiceId = service.id;
                            state.module = 'presenter';
                            state.dirty.service = false;
                            refs.detailPane.innerHTML = renderServiceSourcePanel(service);
                            const textarea = refs.detailPane.querySelector('[data-service-source-text="__smoke_source_apply__"]');
                            if (!textarea) return { ready: false, reason: 'textarea' };
                            const pendingBefore = serviceSourceTextHasPendingChanges(textarea);
                            textarea.value = [
                              '[성경봉독]',
                              '성경봉독: 막 1:1-3',
                              '',
                              '[특송]',
                              '특송: 새 특송',
                              '  담당: 새 담당',
                              '  가사:',
                              '    첫 줄',
                              '    ',
                              '    후렴',
                              '',
                              '[광고]',
                              '교회소식: 새광고.mp4',
                              '  파일: 새광고.mp4',
                              '  링크: https://example.com/new.mp4',
                            ].join('\\n');
                            textarea.dispatchEvent(new Event('input', { bubbles: true }));
                            const pendingAfterEdit = serviceSourceTextHasPendingChanges(textarea);
                            const draftAfterInput = service._worshipSourceTextDraft || '';
                            const saveDirtyAfterInput = currentSaveButtonState().dirty;
                            const rerenderedSource = renderServiceSourcePanel(service);
                            renderCurrentServiceModuleDetail = () => { rendered = true; };
                            renderServiceList = () => {};
                            refreshPresenterForService = (serviceId, options = {}) => refreshes.push({ serviceId, publish: options.publish });
                            const applied = applyServiceSourceText(service.id);
                            const pendingAfterApply = serviceSourceTextHasPendingChanges(textarea);
                            const reading = state.serviceItems[service.id][0];
                            const special = state.serviceItems[service.id][1];
                            const video = state.serviceItems[service.id][2];
                            const readingMemo = parseServiceItemMemo(reading.memo);
                            const specialMemo = parseServiceItemMemo(special.memo);
                            const videoMemo = parseServiceItemMemo(video.memo);
                            const recovery = JSON.parse(localStorage.getItem(recoveryKey) || '{}');
                            refs.detailPane.innerHTML = renderServiceSourcePanel(service);
                            const recoveryButton = refs.detailPane.querySelector('[data-service-source-recovery]');
                            const recoveryRestored = restoreServiceSourceRecovery(service.id);
                            const recoveryTextarea = refs.detailPane.querySelector('[data-service-source-text="__smoke_source_apply__"]');
                            return {
                              ready: true,
                              applied,
                              readingTitle: reading.raw_title || '',
                              readingReferences: readingMemo.scriptureReferences || [],
                              specialTitle: special.raw_title || '',
                              specialAssignee: special.assignee || '',
                              specialInputMode: specialMemo.inputMode || '',
                              specialSlides: specialMemo.slides || [],
                              asset: videoMemo.asset || {},
                              sourceDraft: service._worshipSourceTextDraft || '',
                              recoveryReason: recovery.reason || '',
                              recoverySourceText: recovery.serviceDocument?.sourceText || '',
                              pendingBefore,
                              pendingAfterEdit,
                              draftAfterInput,
                              saveDirtyAfterInput,
                              rerenderPreservedDraft: rerenderedSource.includes('새 특송'),
                              pendingAfterApply,
                              recoveryButton: Boolean(recoveryButton),
                              recoveryRestored,
                              recoveryRestoredText: recoveryTextarea?.value || '',
                              dirty: state.dirty.service,
                              rendered,
                              refreshes,
                            };
                          } finally {
                            renderCurrentServiceModuleDetail = originalRenderCurrent;
                            renderServiceList = originalRenderServiceList;
                            refreshPresenterForService = originalRefreshPresenter;
                            refs.detailPane.innerHTML = originalDetailHtml;
                            state.services = originalServices;
                            if (originalItems === undefined) delete state.serviceItems[service.id];
                            else state.serviceItems[service.id] = originalItems;
                            state.selectedServiceId = originalSelectedServiceId;
                            state.module = originalModule;
                            state.dirty.service = originalDirty;
                            if (originalRecovery === null) localStorage.removeItem(recoveryKey);
                            else localStorage.setItem(recoveryKey, originalRecovery);
                          }
                        })()
                        """
                    )
                    if (
                        service_source_view_apply.get("ready")
                        and service_source_view_apply.get("applied")
                        and service_source_view_apply["readingTitle"] == "마가복음 1:1–3"
                        and service_source_view_apply["readingReferences"] == ["마가복음 1:1–3"]
                        and service_source_view_apply["specialTitle"] == "새 특송"
                        and service_source_view_apply["specialAssignee"] == "새 담당"
                        and service_source_view_apply["specialInputMode"] == "manual_praise"
                        and service_source_view_apply["specialSlides"] == ["첫 줄", "후렴"]
                        and service_source_view_apply["asset"].get("name") == "새광고.mp4"
                        and service_source_view_apply["asset"].get("url") == "https://example.com/new.mp4"
                        and "특송: 새 특송" in service_source_view_apply["sourceDraft"]
                        and service_source_view_apply["recoveryReason"] == "after-source-text-apply"
                        and service_source_view_apply["recoverySourceText"] == service_source_view_apply["sourceDraft"]
                        and not service_source_view_apply["pendingBefore"]
                        and service_source_view_apply["pendingAfterEdit"]
                        and "특송: 새 특송" in service_source_view_apply["draftAfterInput"]
                        and service_source_view_apply["saveDirtyAfterInput"]
                        and service_source_view_apply["rerenderPreservedDraft"]
                        and not service_source_view_apply["pendingAfterApply"]
                        and service_source_view_apply["recoveryButton"]
                        and service_source_view_apply["recoveryRestored"]
                        and service_source_view_apply["recoveryRestoredText"] == service_source_view_apply["sourceDraft"]
                        and service_source_view_apply.get("dirty")
                        and service_source_view_apply.get("rendered")
                        and service_source_view_apply["refreshes"] == [{"serviceId": "__smoke_source_apply__", "publish": False}]
                    ):
                        pass_("service-source-view-apply", json.dumps(service_source_view_apply, ensure_ascii=False))
                    else:
                        fail("service-source-view-apply", json.dumps(service_source_view_apply, ensure_ascii=False))

                    service_document_snapshot = page.evaluate(
                        """
                        (() => {
                          if (
                            typeof buildServiceDocumentSnapshot !== 'function'
                            || typeof serviceDocumentSnapshotFromRef !== 'function'
                            || typeof withServiceDocumentSnapshot !== 'function'
                          ) return { ready: false, reason: 'functions' };
                          const previousDocument = {
                            kind: MINDEX_SERVICE_DOCUMENT_KIND,
                            version: MINDEX_SERVICE_DOCUMENT_VERSION,
                            serviceId: '__smoke_service_document__',
                            serviceTypeId: 'special',
                            serviceDate: '2026-07-18',
                            updatedAt: '2026-07-18T00:00:00.000Z',
                            sourceSignature: 'old-source',
                            slideSignature: 'old-slides',
                            sourceText: '[봉헌]\\n이미지: 이전 안내 이미지',
                            sourceRecords: [{ index: 1, recordKey: 'offering.media|old', slotKey: 'offering.media', label: '이미지', value: '이전 안내 이미지' }],
                            slides: [{ index: 1, slideKey: 'offering.media|old-slide', slotKey: 'offering.media', type: 'image', title: '이전 안내 이미지' }],
                          };
                          const service = {
                            id: '__smoke_service_document__',
                            type_id: 'special',
                            date: '2026-07-19',
                            alias: '온세대예배',
                            _worshipSourceRef: { [MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY]: previousDocument },
                          };
                          const item = normalizeServiceItem({
                            id: '__smoke_service_document_asset__',
                            service_id: service.id,
                            label: '이미지',
                            _worshipSlotKey: 'offering.media',
                            source_ref: { slotKey: 'offering.media' },
                            memo: serializeServiceItemMemo({
                              elementType: 'image',
                              inputMode: 'asset',
                              asset: { kind: 'image', name: '꿈꾸는 어린이부 여름성경학교 안내', url: 'assets/worship-templates/all-generations-2026-07-19-offering-thanks.png' },
                            }),
                            _worshipSectionKey: 'offering',
                            _worshipSectionTitle: '봉헌',
                          }, 0);
                          const originalServices = state.services;
                          const originalItems = state.serviceItems[service.id];
                          const originalCache = presenterSlideBuildCache.get(service.id);
                          const originalDetailHtml = refs.detailPane.innerHTML;
                          const originalDirty = state.dirty.service;
                          try {
                            state.services = [service, ...originalServices.filter((candidate) => candidate.id !== service.id)];
                            state.serviceItems[service.id] = [item];
                            presenterSlideBuildCache.delete(service.id);
                            service._worshipSourceTextDraft = '[봉헌]\\n이미지: 사용자가 남긴 안내 이미지';
                            const document = buildServiceDocumentSnapshot(service, [item]);
                            const sourceRef = withServiceDocumentSnapshot(service, [item]);
                            const fromRef = serviceDocumentSnapshotFromRef({ _worshipSourceRef: sourceRef }) || {};
                            const history = sourceRef[MINDEX_SERVICE_DOCUMENT_HISTORY_SOURCE_REF_KEY] || [];
                            service._worshipSourceRef = sourceRef;
                            const placeholder = normalizeServiceItem({
                              id: '__smoke_service_document_placeholder__',
                              service_id: service.id,
                              label: '이미지',
                              raw_title: '',
                              _worshipSectionKey: 'offering',
                              _worshipSectionTitle: '봉헌',
                              _worshipTemplateProjected: true,
                              _worshipTemplatePlaceholder: true,
                            }, 0);
                            state.serviceItems[service.id] = [placeholder];
                            presenterSlideBuildCache.delete(service.id);
                            const fallbackSlides = buildServicePresenterSlides(service.id);
                            const pendingReference = normalizeServiceItem({
                              id: '__smoke_service_document_pending_reference__',
                              service_id: service.id,
                              label: '참고 화면',
                              raw_title: '',
                              memo: serializeServiceItemMemo({
                                elementType: 'image',
                                componentType: 'image',
                                inputMode: 'asset',
                                asset: { kind: 'image', name: '', url: '' },
                              }),
                              _worshipSectionKey: 'announcements',
                              _worshipSectionTitle: '광고',
                              _worshipElementTemplateModified: true,
                              _worshipTemplatePlaceholder: false,
                            }, 1);
                            state.serviceItems[service.id] = [placeholder, pendingReference];
                            presenterSlideBuildCache.delete(service.id);
                            const pendingSlides = buildServicePresenterSlides(service.id);
                            refs.detailPane.innerHTML = renderServiceSourcePanel(service);
                            const historyButton = refs.detailPane.querySelector('[data-service-source-history]');
                            const restored = restoreServiceSourceHistory(service.id, 0);
                            const textarea = refs.detailPane.querySelector('[data-service-source-text="__smoke_service_document__"]');
                            return {
                              ready: true,
                              kind: document.kind || '',
                              version: document.version || '',
                              serviceId: document.serviceId || '',
                              serviceTypeId: document.serviceTypeId || '',
                              serviceDate: document.serviceDate || '',
                              sourceText: document.sourceText || '',
                              sourceSignature: document.sourceSignature || '',
                              sourceRecordCount: document.sourceRecords?.length || 0,
                              sourceRecord: document.sourceRecords?.[0] || {},
                              slideSignature: document.slideSignature || '',
                              slideCount: document.slides.length,
                              slideSlotKey: document.slides.find((slide) => slide.elementId === item.id)?.slotKey || '',
                              slideKey: document.slides.find((slide) => slide.elementId === item.id)?.slideKey || '',
                              slideAsset: document.slides.find((slide) => slide.asset)?.asset || {},
                              fallbackCount: fallbackSlides.length,
                              fallbackRestoredCount: fallbackSlides.filter((slide) => slide.serviceDocumentFallback).length,
                              fallbackAsset: fallbackSlides.find((slide) => slide.serviceDocumentFallback && slide.asset)?.asset || {},
                              pendingFallbackCount: pendingSlides.filter((slide) => slide.serviceDocumentFallback).length,
                              pendingReferenceCount: pendingSlides.filter((slide) => slide.referenceMediaPending).length,
                              pendingReferenceElementId: pendingSlides.find((slide) => slide.referenceMediaPending)?.elementId || '',
                              exceptionReason: document.exceptions[0]?.reason || '',
                              historyCount: history.length,
                              historySourceText: history[0]?.sourceText || '',
                              historySlideCount: history[0]?.slideCount ?? history[0]?.slides?.length ?? 0, // history entries are stored slim: a count, not the slides
                              historyButton: Boolean(historyButton),
                              restored,
                              restoredText: textarea?.value || '',
                              restoredPending: serviceSourceTextHasPendingChanges(textarea),
                              roundTripVersion: fromRef.version || '',
                              roundTripSourceSignature: fromRef.sourceSignature || '',
                            };
                          } finally {
                            refs.detailPane.innerHTML = originalDetailHtml;
                            state.dirty.service = originalDirty;
                            state.services = originalServices;
                            if (originalItems === undefined) delete state.serviceItems[service.id];
                            else state.serviceItems[service.id] = originalItems;
                            if (originalCache) presenterSlideBuildCache.set(service.id, originalCache);
                            else presenterSlideBuildCache.delete(service.id);
                          }
                        })()
                        """
                    )
                    if (
                        service_document_snapshot.get("ready")
                        and service_document_snapshot["kind"] == "worship-service-document"
                        and service_document_snapshot["version"] == "service-document-v1"
                        and service_document_snapshot["serviceId"] == "__smoke_service_document__"
                        and service_document_snapshot["serviceTypeId"] == "special"
                        and service_document_snapshot["serviceDate"] == "2026-07-19"
                        and service_document_snapshot["sourceText"] == "[봉헌]\n이미지: 사용자가 남긴 안내 이미지"
                        and ":" in service_document_snapshot["sourceSignature"]
                        and service_document_snapshot["sourceRecordCount"] == 1
                        and service_document_snapshot["sourceRecord"].get("recordKey") == "offering.media|__smoke_service_document_asset__|offering|이미지"
                        and service_document_snapshot["sourceRecord"].get("sectionTitle") == "봉헌"
                        and service_document_snapshot["sourceRecord"].get("label") == "이미지"
                        and service_document_snapshot["sourceRecord"].get("value") == "사용자가 남긴 안내 이미지"
                        and service_document_snapshot["sourceRecord"].get("elementId") == "__smoke_service_document_asset__"
                        and service_document_snapshot["sourceRecord"].get("sectionKey") == "offering"
                        and service_document_snapshot["sourceRecord"].get("slotKey") == "offering.media"
                        and service_document_snapshot["sourceRecord"].get("linkedSource", {}).get("asset", {}).get("name") == "꿈꾸는 어린이부 여름성경학교 안내"
                        and ":" in service_document_snapshot["slideSignature"]
                        and service_document_snapshot["slideCount"] >= 1
                        and service_document_snapshot["slideSlotKey"] == "offering.media"
                        and service_document_snapshot["slideKey"]
                        and service_document_snapshot["slideAsset"].get("name") == "꿈꾸는 어린이부 여름성경학교 안내"
                        and service_document_snapshot["fallbackCount"] >= service_document_snapshot["slideCount"]
                        and service_document_snapshot["fallbackRestoredCount"] >= 1
                        and service_document_snapshot["fallbackAsset"].get("name") == "꿈꾸는 어린이부 여름성경학교 안내"
                        and service_document_snapshot["pendingFallbackCount"] == 0
                        and service_document_snapshot["pendingReferenceCount"] == 1
                        and service_document_snapshot["pendingReferenceElementId"] == "__smoke_service_document_pending_reference__"
                        and "봉헌 섹션의 이미지 항목" in service_document_snapshot["exceptionReason"]
                        and service_document_snapshot["historyCount"] == 1
                        and service_document_snapshot["historySourceText"] == "[봉헌]\n이미지: 이전 안내 이미지"
                        and service_document_snapshot["historySlideCount"] == 1
                        and service_document_snapshot["historyButton"]
                        and service_document_snapshot["restored"]
                        and service_document_snapshot["restoredText"] == "[봉헌]\n이미지: 이전 안내 이미지"
                        and service_document_snapshot["restoredPending"]
                        and service_document_snapshot["roundTripVersion"] == "service-document-v1"
                        and service_document_snapshot["roundTripSourceSignature"] == service_document_snapshot["sourceSignature"]
                    ):
                        pass_("service-document-snapshot", json.dumps(service_document_snapshot, ensure_ascii=False))
                    else:
                        fail("service-document-snapshot", json.dumps(service_document_snapshot, ensure_ascii=False))

                    presenter_preparation_double_enter = page.evaluate(
                        """
                        (() => {
                          if (
                            typeof handleDetailKeydown !== 'function'
                            || typeof presenterPreparationDoubleEnterShouldApply !== 'function'
                          ) return { ready: false };
                          const input = document.querySelector('#mindexRightSidebar [data-presenter-preparation-input]');
                          if (!input) return { ready: false, reason: 'input' };
                          const originalApply = applyPresenterPreparationInput;
                          const originalValue = input.value;
                          const calls = [];
                          try {
                            applyPresenterPreparationInput = (serviceId, options = {}) => {
                              calls.push({ serviceId, draft: options.draft || '' });
                            };
                            input.value = '대표기도: 더블엔터 권사';
                            input.selectionStart = input.selectionEnd = input.value.length;
                            let firstPrevented = false;
                            handleDetailKeydown({
                              target: input,
                              key: 'Enter',
                              preventDefault() { firstPrevented = true; },
                              stopPropagation() {},
                            });
                            const firstCalls = calls.length;
                            input.value = '대표기도: 더블엔터 권사\\n';
                            input.selectionStart = input.selectionEnd = input.value.length;
                            let secondPrevented = false;
                            let secondStopped = false;
                            handleDetailKeydown({
                              target: input,
                              key: 'Enter',
                              preventDefault() { secondPrevented = true; },
                              stopPropagation() { secondStopped = true; },
                            });
                            return {
                              ready: true,
                              firstPrevented,
                              firstCalls,
                              secondPrevented,
                              secondStopped,
                              calls,
                            };
                          } finally {
                            applyPresenterPreparationInput = originalApply;
                            input.value = originalValue;
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_double_enter.get("ready")
                        and not presenter_preparation_double_enter["firstPrevented"]
                        and presenter_preparation_double_enter["firstCalls"] == 0
                        and presenter_preparation_double_enter["secondPrevented"]
                        and presenter_preparation_double_enter["secondStopped"]
                        and len(presenter_preparation_double_enter["calls"]) == 1
                        and presenter_preparation_double_enter["calls"][0]["draft"] == "대표기도: 더블엔터 권사\n"
                    ):
                        pass_("presenter-preparation-double-enter", json.dumps(presenter_preparation_double_enter, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-double-enter", json.dumps(presenter_preparation_double_enter, ensure_ascii=False))

                    presenter_input_label_vocabulary = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_presenter_input_labels__', type_id: 'friday', date: '2026-08-21' };
                          const makeItem = (label, memo, extra = {}) => normalizeServiceItem({
                            id: `__smoke_presenter_input_labels_${label}__`,
                            service_id: service.id,
                            label,
                            raw_title: '',
                            memo: serializeServiceItemMemo(memo),
                            ...extra,
                          });
                          const collectLabels = (html) => {
                            const host = document.createElement('div');
                            host.innerHTML = html;
                            return [...host.querySelectorAll('.svc-presenter-input-field > span')]
                              .map((node) => node.textContent.trim())
                              .filter(Boolean);
                          };
                          const hasFieldClass = (html, className) => {
                            const host = document.createElement('div');
                            host.innerHTML = html;
                            return Boolean(host.querySelector(`.${className}`));
                          };
                          const measureAnnouncementInput = (html) => {
                            const host = document.createElement('div');
                            host.className = 'svc-board-subgroup-controls';
                            host.style.cssText = 'position:absolute;left:-9999px;top:0;width:960px;';
                            const row = document.createElement('div');
                            row.className = 'svc-board-subgroup-control-item';
                            row.innerHTML = html;
                            host.appendChild(row);
                            document.body.appendChild(host);
                            const field = host.querySelector('.svc-presenter-input-field--announcement');
                            const textarea = host.querySelector('textarea.svc-presenter-input-control--multiline');
                            const fieldRect = field?.getBoundingClientRect();
                            const textareaRect = textarea?.getBoundingClientRect();
                            const result = {
                              fieldWidth: Math.round(fieldRect?.width || 0),
                              textareaWidth: Math.round(textareaRect?.width || 0),
                              leftGap: Math.round((textareaRect?.left || 0) - (fieldRect?.left || 0)),
                            };
                            host.remove();
                            return result;
                          };
                          const praise = makeItem('찬양 1', { elementType: 'praise', inputMode: 'lyrics_db' });
                          const praiseModel = serviceItemEditorModel(praise, { service });
                          const scripture = makeItem('성경봉독', { elementType: 'scripture_body', scriptureReference: '요 3:16' }, { raw_title: '요 3:16' });
                          const scriptureMemo = parseServiceItemMemo(scripture.memo);
                          const title = makeItem('설교 제목', { elementType: 'title_person' }, { raw_title: '선택 가이드', assignee: '김남영 목사' });
                          const titleMemo = parseServiceItemMemo(title.memo);
                          const titleModel = serviceItemEditorModel(title, { service });
                          const special = makeItem('특송', { elementType: 'praise', inputMode: 'manual_praise', slides: ['특송 가사'] }, { raw_title: '은혜', assignee: '청년부' });
                          const specialMemo = parseServiceItemMemo(special.memo);
                          const specialModel = serviceItemEditorModel(special, { service });
                          const announcement = makeItem('광고', { elementType: 'body' }, { raw_title: '1. 광고 내용', _worshipSectionKey: 'announcements' });
                          const announcementMemo = parseServiceItemMemo(announcement.memo);
                          const announcementModel = serviceItemEditorModel(announcement, { service });
                          const announcementHtml = renderPresenterServiceTextInputs(announcement, 4, announcementModel, announcementMemo);
                          const labels = {
                            praise: collectLabels(renderPresenterServicePraiseInput(praise, 0, praiseModel)),
                            scripture: collectLabels(renderPresenterServiceScriptureInput(scripture, 1, scriptureMemo)),
                            title: collectLabels(renderPresenterServiceTextInputs(title, 2, titleModel, titleMemo)),
                            special: collectLabels(renderPresenterServiceTextInputs(special, 3, specialModel, specialMemo)),
                            announcement: collectLabels(announcementHtml),
                          };
                          const titleLabelVisibility = {
                            genericTitle: presenterServiceTitleFieldShowsLabel('제목'),
                            content: presenterServiceTitleFieldShowsLabel('내용'),
                            scripture: presenterServiceTitleFieldShowsLabel('말씀'),
                            praise: presenterServiceTitleFieldShowsLabel('찬양'),
                          };
                          return {
                            ...labels,
                            titleLabelVisibility,
                            genericAssigneeFallbacks: ['성경봉독', '교회소식', '광고', '예배기도', '축복기도', '봉헌기도', '축도']
                              .map((label) => ({
                                label,
                                placeholder: inferServiceItemAssignee({ label, raw_title: '' }),
                              })),
                            all: Object.values(labels).flat(),
                            announcementFullWidth: hasFieldClass(announcementHtml, 'svc-presenter-input-field--announcement'),
                            announcementLayout: measureAnnouncementInput(announcementHtml),
                          };
                        })()
                        """
                    )
                    if (
                        presenter_input_label_vocabulary["praise"] == ["찬양"]
                        and presenter_input_label_vocabulary["scripture"] == ["말씀"]
                        and presenter_input_label_vocabulary["title"] == ["담당"]
                        and presenter_input_label_vocabulary["special"] == ["찬양", "가사", "담당"]
                        and presenter_input_label_vocabulary["announcement"] == []
                        and presenter_input_label_vocabulary["titleLabelVisibility"] == {
                            "genericTitle": False,
                            "content": False,
                            "scripture": True,
                            "praise": True,
                        }
                        and presenter_input_label_vocabulary["announcementFullWidth"] is True
                        and presenter_input_label_vocabulary["announcementLayout"]["fieldWidth"] >= 900
                        and presenter_input_label_vocabulary["announcementLayout"]["textareaWidth"] >= 880
                        and presenter_input_label_vocabulary["announcementLayout"]["leftGap"] <= 2
                        and all(not item["placeholder"] for item in presenter_input_label_vocabulary["genericAssigneeFallbacks"])
                        and all(label in ["찬양", "말씀", "제목", "가사", "담당"] for label in presenter_input_label_vocabulary["all"])
                    ):
                        pass_("presenter-input-label-vocabulary", json.dumps(presenter_input_label_vocabulary, ensure_ascii=False))
                    else:
                        fail("presenter-input-label-vocabulary", json.dumps(presenter_input_label_vocabulary, ensure_ascii=False))

                    presenter_input_completion_guard = page.evaluate(
                        """
                        (() => {
                          const service = state.services.find((item) => item.id === state.selectedServiceId);
                          const strictSongItem = servicePrepEditorItems(service?.id || '')
                            .find((item) => serviceItemRequiresSongSelection(item, service));
                          if (!strictSongItem) return { skipped: true };
                          const typedOnly = {
                            ...strictSongItem,
                            raw_title: '가',
                            song_id: null,
                            version_id: null,
                            song_version_id: null
                          };
                          const typedMemo = parseServiceItemMemo(typedOnly.memo);
                          const typedState = resolvePresenterServiceItemContentState(typedOnly, typedMemo, null, service);
                          return {
                            skipped: false,
                            label: strictSongItem.label || '',
                            state: typedState.state,
                            hasOutputContent: typedState.hasOutputContent,
                            reason: typedState.reason,
                            inputMode: typedState.inputMode
                          };
                        })()
                        """
                    )
                    if presenter_input_completion_guard.get("skipped"):
                        skip("presenter-input-completion-guard", "No strict song input item.")
                    elif (
                        presenter_input_completion_guard["state"] == "missing"
                        and not presenter_input_completion_guard["hasOutputContent"]
                        and presenter_input_completion_guard["reason"] == "song_selection_required"
                    ):
                        pass_("presenter-input-completion-guard", json.dumps(presenter_input_completion_guard, ensure_ascii=False))
                    else:
                        fail("presenter-input-completion-guard", json.dumps(presenter_input_completion_guard, ensure_ascii=False))

                    presenter_linked_song_loading_guard = page.evaluate(
                        """
                        (() => {
                          const originalSongs = state.songs;
                          const service = { id: '__smoke_linked_song_loading__', type_id: 'sunday-first', date: '2026-08-02' };
                          const item = normalizeServiceItem({
                            id: '__smoke_linked_song_loading_item__',
                            service_id: service.id,
                            label: '찬양 1',
                            raw_title: '이미 선택된 찬양',
                            song_id: '11111111-2222-4333-8444-555555555555',
                            song_version_id: '22222222-3333-4444-8555-666666666666',
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'lyrics_db',
                              outputMode: 'lyrics',
                            }),
                            _worshipSectionKey: 'praise',
                            _worshipSectionTitle: '찬양',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          try {
                            state.songs = [];
                            clearSearchCaches();
                            const memo = parseServiceItemMemo(item.memo);
                            const content = resolvePresenterServiceItemContentState(item, memo, null, service);
                            const slide = presenterMissingContentSlide(item, {}, 0, content, service);
                            return {
                              state: content.state,
                              reason: content.reason,
                              hasOutputContent: content.hasOutputContent,
                              loadingContent: Boolean(slide.loadingContent),
                              missingContent: Boolean(slide.missingContent),
                              warning: slide.warnings?.[0] || '',
                            };
                          } finally {
                            state.songs = originalSongs;
                            clearSearchCaches();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_linked_song_loading_guard["state"] == "loading"
                        and presenter_linked_song_loading_guard["reason"] == "song_hydrating"
                        and not presenter_linked_song_loading_guard["hasOutputContent"]
                        and presenter_linked_song_loading_guard["loadingContent"]
                        and not presenter_linked_song_loading_guard["missingContent"]
                        and presenter_linked_song_loading_guard["warning"] == "불러오는 중"
                    ):
                        pass_("presenter-linked-song-loading-guard", json.dumps(presenter_linked_song_loading_guard, ensure_ascii=False))
                    else:
                        fail("presenter-linked-song-loading-guard", json.dumps(presenter_linked_song_loading_guard, ensure_ascii=False))

                    presenter_linked_song_hydration = page.evaluate(
                        """
                        (() => {
                          const originalSongs = state.songs;
                          const originalServices = state.services;
                          const originalServiceItems = state.serviceItems;
                          const originalSelectedServiceId = state.selectedServiceId;
                          const service = { id: '__smoke_linked_song_hydration__', type_id: 'special', date: '2026-08-19' };
                          const songId = '11111111-1111-4111-8111-111111111111';
                          const versionId = '22222222-2222-4222-8222-222222222222';
                          try {
                            state.songs = [normalizeServerSong({ id: songId, title: '연결 찬양', praise_types: ['ccm'], memo: null })];
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.serviceItems = { [service.id]: [normalizeServiceItem({
                              id: '__smoke_linked_item__',
                              service_id: service.id,
                              label: '찬양 1',
                              raw_title: '',
                              song_id: songId,
                              song_version_id: versionId,
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'lyrics_db',
                                outputMode: 'lyrics',
                              }),
                              _worshipSectionKey: 'praise',
                              _worshipSectionTitle: '찬양',
                              _worshipElementTemplateModified: true,
                              _worshipTemplatePlaceholder: false,
                            }, 0)] };
                            clearSearchCaches();
                            const beforeSignature = presenterSlideBuildSourceSignature(service.id);
                            const beforeNeedsHydration = songNeedsRelationalHydration(songId);
                            attachRelationalSongVersionRows([{
                              id: versionId,
                              source_song_id: songId,
                              canonical_song_id: songId,
                              version_order: 1,
                              curated_version_name: 'Default',
                              version_label: 'Default',
                              is_primary: true,
                              praise_types: ['ccm'],
                            }], [{
                              id: '33333333-3333-4333-8333-333333333333',
                              version_id: versionId,
                              unit_order: 1,
                              unit_label: 'Verse 1',
                              unit_kind: 'Verse',
                              curated_order: 1,
                              curated_unit_label: 'Verse 1',
                              curated_unit_type: 'Verse',
                              text: '연결된 가사',
                            }], [songId]);
                            clearSearchCaches();
                            const afterSignature = presenterSlideBuildSourceSignature(service.id);
                            const progress = presenterServiceInputProgress(service);
                            const slides = buildServicePresenterSlidesUncached(service.id);
                            const hydratedSong = songById(songId);
                            const hydratedVersion = hydratedSong?.versions?.find((version) => version.id === versionId);
                            hydratedVersion.forms[0].lyrics = '수정된 연결 가사';
                            const lyricsSignature = presenterSlideBuildSourceSignature(service.id);
                            return {
                              beforeNeedsHydration,
                              afterNeedsHydration: songNeedsRelationalHydration(songId),
                              versionId: hydratedVersion?.id || '',
                              missing: progress.missing,
                              slideText: slides.map((slide) => slide.text || '').join(' '),
                              hasMissingSlide: slides.some((slide) => slide.missingContent),
                              signatureChangedOnHydration: beforeSignature !== afterSignature,
                              signatureChangedOnLyrics: afterSignature !== lyricsSignature,
                            };
                          } finally {
                            presenterSlideBuildCache.delete(service.id);
                            state.songs = originalSongs;
                            state.services = originalServices;
                            state.serviceItems = originalServiceItems;
                            state.selectedServiceId = originalSelectedServiceId;
                            clearSearchCaches();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_linked_song_hydration["beforeNeedsHydration"]
                        and not presenter_linked_song_hydration["afterNeedsHydration"]
                        and presenter_linked_song_hydration["versionId"] == "22222222-2222-4222-8222-222222222222"
                        and presenter_linked_song_hydration["missing"] == 0
                        and "연결된 가사" in presenter_linked_song_hydration["slideText"]
                        and not presenter_linked_song_hydration["hasMissingSlide"]
                        and presenter_linked_song_hydration["signatureChangedOnHydration"]
                        and presenter_linked_song_hydration["signatureChangedOnLyrics"]
                    ):
                        pass_("presenter-linked-song-hydration", json.dumps(presenter_linked_song_hydration, ensure_ascii=False))
                    else:
                        fail("presenter-linked-song-hydration", json.dumps(presenter_linked_song_hydration, ensure_ascii=False))

                    selected_service_song_hydration_order = page.evaluate(
                        """
                        async () => {
                          const originalFetchRows = fetchWorshipRowsForServiceIds;
                          const originalLoadSongsForIds = loadSongsForIds;
                          const originalRenderDetail = renderCurrentServiceModuleDetail;
                          const originalWarmWorship = warmWorshipScriptureReferencesForService;
                          const originalWarmItems = warmServiceItemScriptureReferencesForService;
                          const originalServices = state.services;
                          const originalServiceItems = state.serviceItems;
                          const originalSections = state.worshipSections;
                          const originalElements = state.worshipElements;
                          const originalLoadedIds = state.loadedWorshipServiceIds;
                          const originalSelectedServiceId = state.selectedServiceId;
                          const originalModule = state.module;
                          const originalDirty = { ...state.dirty };
                          const serviceId = '__smoke_selected_song_hydration_order__';
                          const sectionId = '__smoke_selected_song_hydration_section__';
                          const songId = '33333333-3333-4333-8333-333333333333';
                          const events = [];
                          try {
                            state.services = [{ id: serviceId, type_id: 'sunday-first', title: 'Hydration Order', date: '2099-08-30' }];
                            state.serviceItems = {};
                            state.worshipSections = [];
                            state.worshipElements = [];
                            state.loadedWorshipServiceIds = new Set();
                            state.selectedServiceId = serviceId;
                            state.module = 'presenter';
                            state.dirty = { ...state.dirty, service: false };
                            fetchWorshipRowsForServiceIds = async () => ({
                              sections: [{
                                id: sectionId,
                                service_id: serviceId,
                                section_key: 'praise',
                                label: '찬양',
                                sort_order: 1,
                              }],
                              elements: [{
                                id: '__smoke_selected_song_hydration_item__',
                                section_id: sectionId,
                                label: '찬양 1',
                                raw_title: '',
                                song_id: songId,
                                song_version_id: '44444444-4444-4444-8444-444444444444',
                                element_type: 'praise',
                                input_mode: 'lyrics_db',
                                output_mode: 'lyrics',
                                sort_order: 1,
                              }],
                            });
                            loadSongsForIds = async (ids) => {
                              events.push(`songs:start:${ids.includes(songId)}`);
                              await new Promise((resolve) => setTimeout(resolve, 0));
                              events.push('songs:done');
                            };
                            renderCurrentServiceModuleDetail = () => {
                              events.push('render');
                            };
                            warmWorshipScriptureReferencesForService = () => Promise.resolve(false);
                            warmServiceItemScriptureReferencesForService = () => Promise.resolve(false);
                            await loadServiceItems(serviceId);
                            return {
                              events,
                              renderAfterSongs: events.indexOf('render') > events.indexOf('songs:done'),
                              backgroundHydrationSkipped: events.filter((event) => event.startsWith('songs:start')).length === 1,
                            };
                          } finally {
                            fetchWorshipRowsForServiceIds = originalFetchRows;
                            loadSongsForIds = originalLoadSongsForIds;
                            renderCurrentServiceModuleDetail = originalRenderDetail;
                            warmWorshipScriptureReferencesForService = originalWarmWorship;
                            warmServiceItemScriptureReferencesForService = originalWarmItems;
                            state.services = originalServices;
                            state.serviceItems = originalServiceItems;
                            state.worshipSections = originalSections;
                            state.worshipElements = originalElements;
                            state.loadedWorshipServiceIds = originalLoadedIds;
                            state.selectedServiceId = originalSelectedServiceId;
                            state.module = originalModule;
                            state.dirty = originalDirty;
                          }
                        }
                        """
                    )
                    if (
                        selected_service_song_hydration_order["renderAfterSongs"]
                        and selected_service_song_hydration_order["backgroundHydrationSkipped"]
                    ):
                        pass_("selected-service-song-hydration-before-render", json.dumps(selected_service_song_hydration_order, ensure_ascii=False))
                    else:
                        fail("selected-service-song-hydration-before-render", json.dumps(selected_service_song_hydration_order, ensure_ascii=False))

                    presenter_praise_input_mode_persistence = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_praise_input_modes__', type_id: 'sunday-first', date: '2026-08-02' };
                          const makeItem = (label, inputMode, index, sectionKey = 'praise', sectionTitle = '찬양') => normalizeServiceItem({
                            service_id: service.id,
                            label,
                            raw_title: inputMode === 'manual_praise' ? `${label} 직접 입력` : '',
                            song_id: inputMode === 'manual_praise' ? null : `__smoke_song_${index}__`,
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode,
                              outputMode: servicePraiseInputModeOutputMode(inputMode),
                              slides: inputMode === 'manual_praise' ? ['가사 한 줄'] : [],
                            }),
                            _worshipSectionKey: sectionKey,
                            _worshipSectionTitle: sectionTitle,
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, index);
                          const previousSongs = state.songs;
                          try {
                            // Linked songs must resolve in the catalog before a save row is built.
                            state.songs = [0, 1].map((index) => ({ id: `__smoke_song_${index}__`, title: `스모크 곡 ${index}`, versions: [] }));
                            const rows = buildWorshipPersistenceRows(service, [
                              makeItem('찬양 1', 'score_db', 0),
                              makeItem('찬양 2', 'lyrics_db', 1),
                              makeItem('찬양 3', 'manual_praise', 2),
                              makeItem('특송', 'manual_praise', 3, 'special_song', '특송'),
                            ], {}, {}, { elementTypedStateColumns: { inputMode: true, contentState: true } });
                            return rows.elements.map((row) => ({
                              label: row.source_ref?.label || '',
                              inputMode: row.input_mode || '',
                              contentInputMode: row.content_state?.inputMode || '',
                              configInputMode: row.config?.inputMode || '',
                              songId: row.song_id || '',
                              body: row.body || '',
                            }));
                          } finally {
                            state.songs = previousSongs;
                          }
                        })()
                        """
                    )
                    if presenter_praise_input_mode_persistence == [
                        {"label": "찬양 1", "inputMode": "praise_db", "contentInputMode": "score_db", "configInputMode": "score_db", "songId": "__smoke_song_0__", "body": ""},
                        {"label": "찬양 2", "inputMode": "praise_db", "contentInputMode": "lyrics_db", "configInputMode": "lyrics_db", "songId": "__smoke_song_1__", "body": ""},
                        {"label": "찬양 3", "inputMode": "praise_db", "contentInputMode": "manual_praise", "configInputMode": "manual_praise", "songId": "", "body": "가사 한 줄"},
                        {"label": "특송", "inputMode": "praise_db", "contentInputMode": "manual_praise", "configInputMode": "manual_praise", "songId": "", "body": "가사 한 줄"},
                    ]:
                        pass_("presenter-praise-input-mode-persistence", json.dumps(presenter_praise_input_mode_persistence, ensure_ascii=False))
                    else:
                        fail("presenter-praise-input-mode-persistence", json.dumps(presenter_praise_input_mode_persistence, ensure_ascii=False))

                    presenter_manual_praise_body_roundtrip = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_manual_roundtrip__', type_id: 'sunday-first', date: '2026-08-02' };
                          const item = normalizeServiceItem({
                            service_id: service.id,
                            label: '찬양 1',
                            raw_title: '직접 입력 찬양',
                            song_id: null,
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'manual_praise',
                              outputMode: 'lyrics',
                              slides: ['첫 줄\\n둘째 줄', '후렴'],
                            }),
                            _worshipSectionKey: 'praise',
                            _worshipSectionTitle: '찬양',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const rows = buildWorshipPersistenceRows(service, [item], {}, {}, { elementTypedStateColumns: { inputMode: true, contentState: true } });
                          const hydrated = groupWorshipElements(rows.sections, rows.elements)[service.id]?.[0] || {};
                          const memo = parseServiceItemMemo(hydrated.memo);
                          return {
                            inputMode: rows.elements[0]?.input_mode || '',
                            contentInputMode: rows.elements[0]?.content_state?.inputMode || '',
                            body: rows.elements[0]?.body || '',
                            hydratedInputMode: memo.inputMode || '',
                            hydratedSlides: memo.slides || [],
                          };
                        })()
                        """
                    )
                    if presenter_manual_praise_body_roundtrip == {
                        "inputMode": "praise_db",
                        "contentInputMode": "manual_praise",
                        "body": "첫 줄\n둘째 줄\n\n후렴",
                        "hydratedInputMode": "manual_praise",
                        "hydratedSlides": ["첫 줄\n둘째 줄", "후렴"],
                    }:
                        pass_("presenter-manual-praise-body-roundtrip", json.dumps(presenter_manual_praise_body_roundtrip, ensure_ascii=False))
                    else:
                        fail("presenter-manual-praise-body-roundtrip", json.dumps(presenter_manual_praise_body_roundtrip, ensure_ascii=False))

                    worship_slot_key_column_adapter = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_slot_key_service__', type_id: 'sunday-main', date: '2026-08-30' };
                          const item = normalizeServiceItem({
                            service_id: service.id,
                            label: '설교 본문',
                            raw_title: '마 16:13–20',
                            memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' }),
                            _worshipSectionKey: 'sermon',
                            _worshipSectionTitle: '설교',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const withoutColumn = buildWorshipPersistenceRows(service, [item], {}, {}).elements[0];
                          const withColumnRows = buildWorshipPersistenceRows(service, [item], {}, {}, {
                            elementTypedStateColumns: { inputMode: true, contentState: true, slotKey: true }
                          });
                          sanitizeWorshipPersistenceRows(withColumnRows, {
                            elementTypedStateColumns: { inputMode: true, contentState: true, slotKey: true }
                          });
                          const withColumn = withColumnRows.elements[0];
                          const hydrated = groupWorshipElements([
                            { id: '__smoke_slot_section__', service_id: service.id, section_key: 'sermon', title: '설교', sort_order: 1 }
                          ], [{
                            id: '__smoke_slot_element__',
                            section_id: '__smoke_slot_section__',
                            sort_order: 1,
                            element_type: 'title_person',
                            title: '설교 제목처럼 보이는 기존 제목',
                            source_ref: { label: '설교 제목' },
                            config: {},
                            slot_key: 'sermon.scripture',
                          }])[service.id]?.[0];
                          return {
                            omittedWithoutColumn: !Object.prototype.hasOwnProperty.call(withoutColumn, 'slot_key'),
                            columnSlotKey: withColumn.slot_key || '',
                            sourceSlotKey: withColumn.source_ref?.slotKey || '',
                            hydratedSlotKey: hydrated?._worshipSlotKey || '',
                            hydratedLabel: hydrated?.label || '',
                          };
                        })()
                        """
                    )
                    if worship_slot_key_column_adapter == {
                        "omittedWithoutColumn": True,
                        "columnSlotKey": "sermon.scripture",
                        "sourceSlotKey": "sermon.scripture",
                        "hydratedSlotKey": "sermon.scripture",
                        "hydratedLabel": "설교 제목",
                    }:
                        pass_("worship-slot-key-column-adapter", json.dumps(worship_slot_key_column_adapter, ensure_ascii=False))
                    else:
                        fail("worship-slot-key-column-adapter", json.dumps(worship_slot_key_column_adapter, ensure_ascii=False))

                    worship_announcement_media_video_guard = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_announcement_media_video__', type_id: 'sun_2nd', date: '2026-08-30' };
                          const items = groupWorshipElements([
                            { id: '__smoke_announcement_media_section__', service_id: service.id, section_key: 'announcements', title: '광고', sort_order: 11 }
                          ], [{
                            id: '__smoke_announcement_media_element__',
                            section_id: '__smoke_announcement_media_section__',
                            sort_order: 2,
                            element_type: 'video',
                            title: '문고리 전도 홍보 영상',
                            body: '',
                            asset: { kind: 'video', name: '문고리 전도 홍보 영상.mp4', url: 'https://example.test/mungori.mp4' },
                            input_mode: 'asset',
                            content_state: { state: 'filled', reason: 'asset', inputMode: 'asset', elementType: 'video' },
                            source_ref: { label: '참고화면', slotKey: 'announcements.media' },
                            config: {
                              inputMode: 'asset',
                              elementType: 'video',
                              componentType: 'video',
                              asset: { kind: 'video', name: '문고리 전도 홍보 영상.mp4', url: 'https://example.test/mungori.mp4' },
                            },
                            template_modified: true,
                          }])[service.id] || [];
                          const item = items[0] || {};
                          const memo = parseServiceItemMemo(item.memo);
                          const slides = buildPresenterSlidesForServiceItem(item, service, 0);
                          const slide = slides[0] || {};
                          return {
                            itemCount: items.length,
                            label: item.label || '',
                            slotKey: item._worshipSlotKey || '',
                            memoElementType: memo.elementType || '',
                            memoInputMode: memo.inputMode || '',
                            memoAssetKind: memo.asset?.kind || '',
                            slideType: slide.type || '',
                            slideElementType: slide.elementType || '',
                            slideLayout: slide.layout || '',
                            videoSrc: slide.videoSrc || '',
                          };
                        })()
                        """
                    )
                    if worship_announcement_media_video_guard == {
                        "itemCount": 1,
                        "label": "참고화면",
                        "slotKey": "announcements.media",
                        "memoElementType": "video",
                        "memoInputMode": "asset",
                        "memoAssetKind": "video",
                        "slideType": "video",
                        "slideElementType": "video",
                        "slideLayout": "media",
                        "videoSrc": "https://example.test/mungori.mp4",
                    }:
                        pass_("worship-announcement-media-video-guard", json.dumps(worship_announcement_media_video_guard, ensure_ascii=False))
                    else:
                        fail("worship-announcement-media-video-guard", json.dumps(worship_announcement_media_video_guard, ensure_ascii=False))

                    presenter_manual_title_match_guard = page.evaluate(
                        """
                        (async () => {
                          const originalSongs = state.songs;
                          const originalServices = state.services;
                          const originalServiceItems = state.serviceItems;
                          const originalSelectedServiceId = state.selectedServiceId;
                          const service = { id: '__smoke_manual_title_match__', type_id: 'special', date: '2026-08-02' };
                          try {
                            state.songs = [
                              normalizeServerSong({
                                id: '__smoke_manual_match_song__',
                                title: '은혜',
                                memo: serializeSongMemo({ versions: [{
                                  id: '__smoke_manual_match_version__',
                                  name: '기본',
                                  is_primary: true,
                                  forms: [{ id: '__smoke_manual_match_form__', label: 'Verse 1', lyrics: 'DB 가사' }],
                                }] }),
                              }),
                              ...originalSongs,
                            ];
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            const item = normalizeServiceItem({
                              service_id: service.id,
                              label: '특송',
                              raw_title: '',
                              song_id: null,
                              version_id: null,
                              song_version_id: null,
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'manual_praise',
                                outputMode: 'lyrics',
                                slides: ['직접 입력한 가사'],
                              }),
                              _worshipSectionKey: 'special_song',
                              _worshipSectionTitle: '특송',
                              _worshipElementTemplateModified: true,
                              _worshipTemplatePlaceholder: false,
                            }, 0);
                            state.serviceItems = { [service.id]: [item] };
                            item.raw_title = '은혜';
                            applyServiceSongSelectionWithService(item, service);
                            await resolveServiceSongSelectionBeforeSave(service.id, 0);
                            const updated = getServiceItems(service.id)[0] || {};
                            const memo = parseServiceItemMemo(updated.memo);
                            return {
                              rawTitle: updated.raw_title || '',
                              songId: updated.song_id || '',
                              versionId: updated.version_id || updated.song_version_id || '',
                              inputMode: memo.inputMode || '',
                              outputMode: memo.outputMode || '',
                              slides: memo.slides || [],
                            };
                          } finally {
                            state.songs = originalSongs;
                            state.services = originalServices;
                            state.serviceItems = originalServiceItems;
                            state.selectedServiceId = originalSelectedServiceId;
                          }
                        })()
                        """
                    )
                    if presenter_manual_title_match_guard == {
                        "rawTitle": "은혜",
                        "songId": "",
                        "versionId": "",
                        "inputMode": "manual_praise",
                        "outputMode": "lyrics",
                        "slides": ["직접 입력한 가사"],
                    }:
                        pass_("presenter-manual-title-match-guard", json.dumps(presenter_manual_title_match_guard, ensure_ascii=False))
                    else:
                        fail("presenter-manual-title-match-guard", json.dumps(presenter_manual_title_match_guard, ensure_ascii=False))

                    presenter_lyrics_db_version_resolution = page.evaluate(
                        """
                        (() => {
                          const originalSongs = state.songs;
                          const service = { id: '__smoke_lyrics_db_service__', type_id: 'sunday-third', date: '2026-08-02' };
                          const song = {
                            id: '__smoke_lyrics_song__',
                            title: '가사 불러오기 테스트',
                            versions: [
                              {
                                id: '__smoke_lyrics_score__',
                                name: '악보',
                                is_primary: true,
                                _worshipVersionPersisted: true,
                                praise_types: ['hymn'],
                                forms: [],
                              },
                              {
                                id: '__smoke_lyrics_text__',
                                name: '가사',
                                _worshipVersionPersisted: true,
                                praise_types: ['ccm'],
                                forms: [
                                  { id: '__smoke_lyrics_text_f1__', part_type: 'Verse', lyrics: '가사 A\\n가사 B', sort_order: 1 },
                                ],
                              },
                            ],
                          };
                          try {
                            state.songs = [song, ...originalSongs];
                            const item = normalizeServiceItem({
                              service_id: service.id,
                              label: '찬양 1',
                              raw_title: '',
                              song_id: song.id,
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'lyrics_db',
                                outputMode: 'lyrics',
                              }),
                              _worshipSectionKey: 'praise',
                              _worshipSectionTitle: '찬양',
                              _worshipElementTemplateModified: true,
                              _worshipTemplatePlaceholder: false,
                            }, 0);
                            const model = serviceItemEditorModel(item, { service });
                            const pickerHtml = renderServiceSongVersionPicker(item, 0, model);
                            const rows = buildWorshipPersistenceRows(service, [item], {}, {}, { elementTypedStateColumns: { inputMode: true, contentState: true } });
                            const slides = buildPresenterSlidesForServiceItem(item, service, 0);
                            const switchedItem = normalizeServiceItem({
                              ...item,
                              version_id: '__smoke_lyrics_score__',
                              song_version_id: '__smoke_lyrics_score__',
                              raw_title: '',
                              memo: serializeServiceItemMemo({
                                elementType: 'praise',
                                inputMode: 'lyrics_db',
                                outputMode: 'lyrics',
                              }),
                            }, 1);
                            applyServiceSongSelectionWithService(switchedItem, service);
                            return {
                              invalid: serviceItemSongSelectionInvalid(item, service),
                              preferredVersionId: preferredServiceSongVersion(song, item, service)?.id || '',
                              persistedVersionId: rows.elements[0]?.song_version_id || '',
                              pickerInvalid: pickerHtml.includes('is-invalid') || pickerHtml.includes('aria-invalid="true"'),
                              lyricTexts: slides.filter((slide) => slide.type === 'lyrics').map((slide) => slide.text),
                              switchedSongId: switchedItem.song_id || '',
                              switchedVersionId: switchedItem.version_id || '',
                            };
                          } finally {
                            state.songs = originalSongs;
                          }
                        })()
                        """
                    )
                    if presenter_lyrics_db_version_resolution == {
                        "invalid": False,
                        "preferredVersionId": "__smoke_lyrics_text__",
                        "persistedVersionId": "__smoke_lyrics_text__",
                        "pickerInvalid": False,
                        "lyricTexts": ["가사 A\n가사 B"],
                        "switchedSongId": "__smoke_lyrics_song__",
                        "switchedVersionId": "__smoke_lyrics_score__",
                    }:
                        pass_("presenter-lyrics-db-version-resolution", json.dumps(presenter_lyrics_db_version_resolution, ensure_ascii=False))
                    else:
                        fail("presenter-lyrics-db-version-resolution", json.dumps(presenter_lyrics_db_version_resolution, ensure_ascii=False))

                    presenter_media_persistence_guard = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_media_guard__', type_id: 'sunday-first', date: '2026-08-02' };
                          const item = normalizeServiceItem({
                            service_id: service.id,
                            label: '참고 화면',
                            raw_title: '',
                            memo: serializeServiceItemMemo({
                              elementType: 'audio',
                              componentType: 'audio',
                              inputMode: 'asset',
                              asset: { kind: 'audio', name: '성가대 MR', url: 'https://example.test/choir.m4a' },
                            }),
                            _worshipSectionKey: 'sermon',
                            _worshipSectionTitle: '설교',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const rows = buildWorshipPersistenceRows(service, [item], {}, {}, { elementTypedStateColumns: { inputMode: true, contentState: true } });
                          let validationError = '';
                          try {
                            validateWorshipPersistenceRows(rows, { serviceId: service.id });
                          } catch (error) {
                            validationError = error?.message || String(error);
                          }
                          let invalidModeError = '';
                          try {
                            validateWorshipPersistenceRows({
                              sections: [{
                                id: 'section',
                                service_id: service.id,
                                created_at: new Date().toISOString(),
                                updated_at: new Date().toISOString(),
                              }],
                              elements: [{
                                id: 'element',
                                section_id: 'section',
                                created_at: new Date().toISOString(),
                                updated_at: new Date().toISOString(),
                                element_type: 'plain_text',
                                input_mode: 'future_mode',
                                source_ref: { label: '미래 모드' },
                                config: {},
                                asset: {},
                              }],
                            }, { serviceId: service.id });
                          } catch (error) {
                            invalidModeError = error?.message || String(error);
                          }
                          const row = rows.elements[0] || {};
                          return {
                            validationError,
                            invalidModeBlocked: invalidModeError.includes('future_mode'),
                            elementType: row.element_type || '',
                            inputMode: row.input_mode || '',
                            contentInputMode: row.content_state?.inputMode || '',
                            configElementType: row.config?.elementType || '',
                            configInputMode: row.config?.inputMode || '',
                            asset: row.asset || {},
                          };
                        })()
                        """
                    )
                    if (
                        presenter_media_persistence_guard["validationError"] == ""
                        and presenter_media_persistence_guard["invalidModeBlocked"]
                        and presenter_media_persistence_guard["elementType"] == "plain_text"
                        and presenter_media_persistence_guard["inputMode"] == "asset"
                        and presenter_media_persistence_guard["contentInputMode"] == "asset"
                        and presenter_media_persistence_guard["configElementType"] == "audio"
                        and presenter_media_persistence_guard["configInputMode"] == "asset"
                        and presenter_media_persistence_guard["asset"] == {
                            "kind": "audio",
                            "name": "성가대 MR",
                            "url": "https://example.test/choir.m4a",
                        }
                    ):
                        pass_("presenter-media-persistence-guard", json.dumps(presenter_media_persistence_guard, ensure_ascii=False))
                    else:
                        fail("presenter-media-persistence-guard", json.dumps(presenter_media_persistence_guard, ensure_ascii=False))

                    worship_duplicate_slot_key_guard = page.evaluate(
                        """
                        (() => {
                          const now = new Date().toISOString();
                          let validationError = '';
                          try {
                            validateWorshipPersistenceRows({
                              sections: [{
                                id: '__smoke_duplicate_slot_section__',
                                service_id: '__smoke_duplicate_slot_service__',
                                created_at: now,
                                updated_at: now,
                              }],
                              elements: [{
                                id: '__smoke_duplicate_slot_first__',
                                section_id: '__smoke_duplicate_slot_section__',
                                created_at: now,
                                updated_at: now,
                                element_type: 'praise',
                                source_ref: { label: '찬양 1', slotKey: 'praise.song.1' },
                                config: {},
                                asset: {},
                              }, {
                                id: '__smoke_duplicate_slot_second__',
                                section_id: '__smoke_duplicate_slot_section__',
                                created_at: now,
                                updated_at: now,
                                element_type: 'praise',
                                source_ref: { label: '찬양 중복', slotKey: 'praise.song.1' },
                                config: {},
                                asset: {},
                              }],
                            }, { serviceId: '__smoke_duplicate_slot_service__' });
                          } catch (error) {
                            validationError = error?.message || String(error);
                          }
                          return {
                            blocked: validationError.includes('저장 위치가') && validationError.includes('praise.song.1'),
                            message: validationError,
                          };
                        })()
                        """
                    )
                    if worship_duplicate_slot_key_guard["blocked"]:
                        pass_("worship-duplicate-slot-key-guard", json.dumps(worship_duplicate_slot_key_guard, ensure_ascii=False))
                    else:
                        fail("worship-duplicate-slot-key-guard", json.dumps(worship_duplicate_slot_key_guard, ensure_ascii=False))

                    presenter_generic_asset_upload_guard = page.evaluate(
                        """
                        async () => {
                          const serviceId = '__smoke_generic_video_asset_upload__';
                          const item = normalizeServiceItem({
                            id: '__smoke_generic_video_asset_item__',
                            service_id: serviceId,
                            label: '봉헌 영상',
                            raw_title: '',
                            memo: serializeServiceItemMemo({
                              elementType: 'video',
                              componentType: 'video',
                              inputMode: 'asset',
                              asset: { kind: 'video', name: '봉헌 영상', url: '' },
                            }),
                          }, 0);
                          const originalItems = state.serviceItems[serviceId];
                          const originalClient = state.client;
                          const originalSaveService = saveService;
                          const originalRenderCurrentServiceModuleDetail = renderCurrentServiceModuleDetail;
                          const originalRenderServiceList = renderServiceList;
                          const uploads = [];
                          let saved = false;
                          let rendered = false;
                          try {
                            state.serviceItems[serviceId] = [item];
                            state.client = {
                              storage: {
                                from(bucket) {
                                  return {
                                    upload: async (path, file, options) => {
                                      uploads.push({ bucket, path, fileName: file.name, contentType: options?.contentType || '' });
                                      return { error: null };
                                    },
                                    getPublicUrl: (path) => ({ data: { publicUrl: `https://cdn.example.test/${path}` } }),
                                    remove: async () => ({ error: null }),
                                  };
                                },
                              },
                            };
                            saveService = async () => { saved = true; return true; };
                            renderCurrentServiceModuleDetail = () => { rendered = true; };
                            renderServiceList = () => {};
                            const html = renderPresenterServiceAssetInput(item, 0, parseServiceItemMemo(item.memo));
                            const uploaded = await uploadPresenterReferenceMediaAsset({
                              file: new File(['video-data'], 'offering.mp4', { type: 'video/mp4' }),
                              serviceId,
                              item,
                            });
                            const memo = parseServiceItemMemo(item.memo);
                            const uploadedHtml = renderPresenterServiceAssetInput(item, 0, memo);
                            return {
                              hasFileInput: html.includes('data-service-item-asset-file'),
                              acceptVideoOnly: html.includes('accept="video/*"'),
                              compactVideoStatus: uploadedHtml.includes('svc-reference-media-preview--file') && uploadedHtml.includes('영상 연결됨'),
                              noVideoPreviewElement: !uploadedHtml.includes('<video'),
                              uploaded,
                              saved,
                              rendered,
                              uploads,
                              elementType: memo.elementType || '',
                              inputMode: memo.inputMode || '',
                              asset: memo.asset || {},
                              modified: Boolean(item._worshipElementTemplateModified),
                              videoLimitLarger: presenterMediaMaxBytesForKind('video') > presenterMediaMaxBytesForKind('image'),
                              videoLimitLabel: presenterMediaMaxSizeLabel('video'),
                            };
                          } finally {
                            if (originalItems === undefined) delete state.serviceItems[serviceId];
                            else state.serviceItems[serviceId] = originalItems;
                            state.client = originalClient;
                            saveService = originalSaveService;
                            renderCurrentServiceModuleDetail = originalRenderCurrentServiceModuleDetail;
                            renderServiceList = originalRenderServiceList;
                          }
                        }
                        """
                    )
                    if (
                        presenter_generic_asset_upload_guard["hasFileInput"]
                        and presenter_generic_asset_upload_guard["acceptVideoOnly"]
                        and presenter_generic_asset_upload_guard["compactVideoStatus"]
                        and presenter_generic_asset_upload_guard["noVideoPreviewElement"]
                        and presenter_generic_asset_upload_guard["uploaded"]
                        and presenter_generic_asset_upload_guard["saved"]
                        and presenter_generic_asset_upload_guard["rendered"]
                        and len(presenter_generic_asset_upload_guard["uploads"]) == 1
                        and presenter_generic_asset_upload_guard["uploads"][0]["fileName"] == "offering.mp4"
                        and presenter_generic_asset_upload_guard["uploads"][0]["contentType"] == "video/mp4"
                        and presenter_generic_asset_upload_guard["elementType"] == "video"
                        and presenter_generic_asset_upload_guard["inputMode"] == "asset"
                        and presenter_generic_asset_upload_guard["asset"].get("kind") == "video"
                        and presenter_generic_asset_upload_guard["asset"].get("name") == "offering.mp4"
                        and presenter_generic_asset_upload_guard["asset"].get("url", "").startswith("https://cdn.example.test/services/")
                        and presenter_generic_asset_upload_guard["modified"]
                        and presenter_generic_asset_upload_guard["videoLimitLarger"]
                        and presenter_generic_asset_upload_guard["videoLimitLabel"] == "500MB"
                    ):
                        pass_("presenter-generic-asset-upload-guard", json.dumps(presenter_generic_asset_upload_guard, ensure_ascii=False))
                    else:
                        fail("presenter-generic-asset-upload-guard", json.dumps(presenter_generic_asset_upload_guard, ensure_ascii=False))

                    presenter_imported_deck_asset_guard = page.evaluate(
                        """
                        async () => {
                          const serviceId = '__smoke_imported_deck_asset_upload__';
                          const item = normalizeServiceItem({
                            id: '__smoke_imported_deck_asset_item__',
                            service_id: serviceId,
                            label: '설교 자료',
                            raw_title: '',
                            memo: serializeServiceItemMemo({
                              elementType: 'image',
                              componentType: 'image',
                              inputMode: 'asset',
                              asset: { kind: 'imported_deck', name: '', url: '' },
                            }),
                          }, 0);
                          const originalItems = state.serviceItems[serviceId];
                          const originalElectron = window.mindexElectron;
                          const originalSaveService = saveService;
                          const originalRenderCurrentServiceModuleDetail = renderCurrentServiceModuleDetail;
                          const originalRenderServiceList = renderServiceList;
                          const calls = [];
                          let saved = false;
                          let rendered = false;
                          try {
                            state.serviceItems[serviceId] = [item];
                            window.mindexElectron = {
                              filePathForFile: (file) => `/tmp/${file.name}`,
                              importKeynoteDeck: async (payload) => {
                                calls.push(payload);
                                return {
                                  ok: true,
                                  cached: false,
                                  manifestPath: '/tmp/cache/sermon/manifest.json',
                                  manifest: {
                                    name: '어린이 설교',
                                    manifestUrl: 'file:///tmp/cache/sermon/manifest.json',
                                    fingerprint: 'deck-smoke-v1',
                                    slides: [
                                      { order: 1, name: 'Stage 1', url: 'file:///tmp/cache/sermon/stage-001.png' },
                                      { order: 2, name: 'Stage 2', url: 'file:///tmp/cache/sermon/stage-002.png' },
                                    ],
                                  },
                                };
                              },
                            };
                            saveService = async () => { saved = true; return true; };
                            renderCurrentServiceModuleDetail = () => { rendered = true; };
                            renderServiceList = () => {};
                            const html = renderPresenterServiceAssetInput(item, 0, parseServiceItemMemo(item.memo));
                            const input = {
                              files: [new File(['deck-data'], 'sermon.key', { type: 'application/vnd.apple.keynote' })],
                              dataset: { serviceId, serviceItemIndex: '0' },
                              disabled: false,
                              value: 'sermon.key',
                            };
                            const imported = await uploadServiceItemAssetFile(input);
                            const memo = parseServiceItemMemo(item.memo);
                            const uploadedHtml = renderPresenterServiceAssetInput(item, 0, memo);
                            return {
                              acceptDeck: html.includes('.key,.keynote,.ppt,.pptx'),
                              imported,
                              saved,
                              rendered,
                              calls,
                              inputCleared: input.value === '',
                              elementType: memo.elementType || '',
                              inputMode: memo.inputMode || '',
                              rawTitle: item.raw_title || '',
                              asset: memo.asset || {},
                              compactDeckStatus: uploadedHtml.includes('슬라이드 2장 연결됨'),
                              modified: Boolean(item._worshipElementTemplateModified),
                            };
                          } finally {
                            if (originalItems === undefined) delete state.serviceItems[serviceId];
                            else state.serviceItems[serviceId] = originalItems;
                            if (originalElectron === undefined) delete window.mindexElectron;
                            else window.mindexElectron = originalElectron;
                            saveService = originalSaveService;
                            renderCurrentServiceModuleDetail = originalRenderCurrentServiceModuleDetail;
                            renderServiceList = originalRenderServiceList;
                          }
                        }
                        """
                    )
                    if (
                        presenter_imported_deck_asset_guard["acceptDeck"]
                        and presenter_imported_deck_asset_guard["imported"]
                        and presenter_imported_deck_asset_guard["saved"]
                        and presenter_imported_deck_asset_guard["rendered"]
                        and presenter_imported_deck_asset_guard["inputCleared"]
                        and len(presenter_imported_deck_asset_guard["calls"]) == 1
                        and presenter_imported_deck_asset_guard["calls"][0]["inputPath"] == "/tmp/sermon.key"
                        and presenter_imported_deck_asset_guard["elementType"] == "image"
                        and presenter_imported_deck_asset_guard["inputMode"] == "asset"
                        and presenter_imported_deck_asset_guard["rawTitle"] == "어린이 설교"
                        and presenter_imported_deck_asset_guard["asset"].get("kind") == "imported_deck"
                        and presenter_imported_deck_asset_guard["asset"].get("name") == "어린이 설교"
                        and presenter_imported_deck_asset_guard["asset"].get("manifestUrl") == "file:///tmp/cache/sermon/manifest.json"
                        and presenter_imported_deck_asset_guard["asset"].get("fingerprint") == "deck-smoke-v1"
                        and len(presenter_imported_deck_asset_guard["asset"].get("slides", [])) == 2
                        and presenter_imported_deck_asset_guard["compactDeckStatus"]
                        and presenter_imported_deck_asset_guard["modified"]
                    ):
                        pass_("presenter-imported-deck-asset-guard", json.dumps(presenter_imported_deck_asset_guard, ensure_ascii=False))
                    else:
                        fail("presenter-imported-deck-asset-guard", json.dumps(presenter_imported_deck_asset_guard, ensure_ascii=False))

                    presenter_praise_header_audio_guard = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_praise_header_audio__', type_id: 'sunday-second', date: '2026-08-02' };
                          const item = normalizeServiceItem({
                            service_id: service.id,
                            label: '특송',
                            raw_title: '어린이부 특송',
                            assignee: '어린이부',
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'manual_praise',
                              slides: ['자막 1', '자막 2'],
                              audioAsset: { kind: 'audio', name: '특송 MR', url: 'https://example.test/special.mp3' },
                            }),
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const parsed = parseServiceItemMemo(item.memo);
                          const rows = buildWorshipPersistenceRows(service, [item], {}, {}, { elementTypedStateColumns: { inputMode: true, contentState: true } });
                          const row = rows.elements[0] || {};
                          return {
                            parsedAudio: parsed.audioAsset || {},
                            dbElementType: row.element_type || '',
                            dbInputMode: row.input_mode || '',
                            configElementType: row.config?.elementType || '',
                            configInputMode: row.config?.inputMode || '',
                            configAudio: row.config?.audioAsset || {},
                            configAsset: row.config?.asset || {},
                            body: row.body || '',
                          };
                        })()
                        """
                    )
                    if (
                        presenter_praise_header_audio_guard["parsedAudio"] == {"kind": "audio", "name": "특송 MR", "url": "https://example.test/special.mp3"}
                        and presenter_praise_header_audio_guard["dbElementType"] == "praise"
                        and presenter_praise_header_audio_guard["dbInputMode"] == "praise_db"
                        and presenter_praise_header_audio_guard["configElementType"] == "praise"
                        and presenter_praise_header_audio_guard["configInputMode"] == "manual_praise"
                        and presenter_praise_header_audio_guard["configAudio"] == {"kind": "audio", "name": "특송 MR", "url": "https://example.test/special.mp3"}
                        and presenter_praise_header_audio_guard["configAsset"] in ({}, {"kind": "", "name": "", "url": ""})
                        and presenter_praise_header_audio_guard["body"] == "자막 1\n\n자막 2"
                    ):
                        pass_("presenter-praise-header-audio-guard", json.dumps(presenter_praise_header_audio_guard, ensure_ascii=False))
                    else:
                        fail("presenter-praise-header-audio-guard", json.dumps(presenter_praise_header_audio_guard, ensure_ascii=False))

                    presenter_praise_header_audio_upload_limit = page.evaluate(
                        """
                        async () => {
                          const serviceId = '__smoke_praise_header_audio_upload__';
                          const originalClient = state.client;
                          const originalItems = state.serviceItems[serviceId];
                          const originalSaveService = saveService;
                          const originalRenderCurrentServiceModuleDetail = renderCurrentServiceModuleDetail;
                          const originalRenderServiceList = renderServiceList;
                          const uploads = [];
                          let saved = false;
                          let rendered = false;
                          const item = normalizeServiceItem({
                            service_id: serviceId,
                            label: '특송',
                            raw_title: '온세대 특송',
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'manual_praise',
                              slides: ['특송 자막'],
                            }),
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          const file = {
                            name: 'special-large.mp3',
                            type: 'audio/mpeg',
                            size: 75 * 1024 * 1024,
                          };
                          const input = {
                            files: [file],
                            dataset: { serviceId, serviceItemIndex: '0' },
                            disabled: false,
                            value: 'special-large.mp3',
                          };
                          try {
                            state.serviceItems[serviceId] = [item];
                            state.client = {
                              storage: {
                                from(bucket) {
                                  return {
                                    upload: async (path, uploadedFile, options) => {
                                      uploads.push({ bucket, path, fileName: uploadedFile.name, size: uploadedFile.size, contentType: options?.contentType || '' });
                                      return { error: null };
                                    },
                                    getPublicUrl: (path) => ({ data: { publicUrl: `https://cdn.example.test/${path}` } }),
                                    remove: async () => ({ error: null }),
                                  };
                                },
                              },
                            };
                            saveService = async () => { saved = true; return true; };
                            renderCurrentServiceModuleDetail = () => { rendered = true; };
                            renderServiceList = () => {};
                            const uploaded = await uploadServiceItemAudioAsset(input);
                            const memo = parseServiceItemMemo(item.memo);
                            return {
                              uploaded,
                              saved,
                              rendered,
                              uploads,
                              inputDisabled: input.disabled,
                              inputValue: input.value,
                              audioLimitLabel: presenterMediaMaxSizeLabel('audio'),
                              audioLimitLargerThanImage: presenterMediaMaxBytesForKind('audio') > presenterMediaMaxBytesForKind('image'),
                              audioAsset: memo.audioAsset || {},
                            };
                          } finally {
                            if (originalItems === undefined) delete state.serviceItems[serviceId];
                            else state.serviceItems[serviceId] = originalItems;
                            state.client = originalClient;
                            saveService = originalSaveService;
                            renderCurrentServiceModuleDetail = originalRenderCurrentServiceModuleDetail;
                            renderServiceList = originalRenderServiceList;
                          }
                        }
                        """
                    )
                    if (
                        presenter_praise_header_audio_upload_limit["uploaded"]
                        and presenter_praise_header_audio_upload_limit["saved"]
                        and presenter_praise_header_audio_upload_limit["rendered"]
                        and len(presenter_praise_header_audio_upload_limit["uploads"]) == 1
                        and presenter_praise_header_audio_upload_limit["uploads"][0]["fileName"] == "special-large.mp3"
                        and presenter_praise_header_audio_upload_limit["uploads"][0]["size"] == 75 * 1024 * 1024
                        and presenter_praise_header_audio_upload_limit["uploads"][0]["contentType"] == "audio/mpeg"
                        and presenter_praise_header_audio_upload_limit["inputDisabled"] is False
                        and presenter_praise_header_audio_upload_limit["inputValue"] == ""
                        and presenter_praise_header_audio_upload_limit["audioLimitLabel"] == "500MB"
                        and presenter_praise_header_audio_upload_limit["audioLimitLargerThanImage"]
                        and presenter_praise_header_audio_upload_limit["audioAsset"].get("kind") == "audio"
                        and presenter_praise_header_audio_upload_limit["audioAsset"].get("name") == "special-large.mp3"
                        and presenter_praise_header_audio_upload_limit["audioAsset"].get("url", "").startswith("https://cdn.example.test/services/")
                    ):
                        pass_("presenter-praise-header-audio-upload-limit", json.dumps(presenter_praise_header_audio_upload_limit, ensure_ascii=False))
                    else:
                        fail("presenter-praise-header-audio-upload-limit", json.dumps(presenter_praise_header_audio_upload_limit, ensure_ascii=False))

                    presenter_praise_header_audio_clear_confirm = page.evaluate(
                        """
                        async () => {
                          const serviceId = '__smoke_praise_header_audio_clear__';
                          const originalItems = state.serviceItems[serviceId];
                          const originalConfirm = window.confirm;
                          const originalSaveService = saveService;
                          const originalRefreshPresenterForService = refreshPresenterForService;
                          const originalRenderCurrentServiceModuleDetail = renderCurrentServiceModuleDetail;
                          const originalRenderServiceList = renderServiceList;
                          const originalShowToast = showToast;
                          const prompts = [];
                          const saves = [];
                          let refreshCount = 0;
                          let detailRenderCount = 0;
                          let listRenderCount = 0;
                          const toasts = [];
                          const makeItem = () => normalizeServiceItem({
                            service_id: serviceId,
                            label: '특송',
                            raw_title: '온세대 특송',
                            memo: serializeServiceItemMemo({
                              elementType: 'praise',
                              inputMode: 'manual_praise',
                              slides: ['특송 자막'],
                              audioAsset: { kind: 'audio', name: '특송 MR.mp3', url: 'https://example.test/special.mp3' },
                            }),
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            _worshipElementTemplateModified: true,
                            _worshipTemplatePlaceholder: false,
                          }, 0);
                          try {
                            saveService = async (savedServiceId) => { saves.push(savedServiceId); return true; };
                            refreshPresenterForService = () => { refreshCount += 1; };
                            renderCurrentServiceModuleDetail = () => { detailRenderCount += 1; };
                            renderServiceList = () => { listRenderCount += 1; };
                            showToast = (message) => { toasts.push(message); };

                            state.serviceItems[serviceId] = [makeItem()];
                            window.confirm = (message) => {
                              prompts.push({ message, response: false });
                              return false;
                            };
                            await clearServiceItemAudioAsset(serviceId, 0);
                            const afterCancel = parseServiceItemMemo(state.serviceItems[serviceId][0].memo).audioAsset || {};

                            state.serviceItems[serviceId] = [makeItem()];
                            window.confirm = (message) => {
                              prompts.push({ message, response: true });
                              return true;
                            };
                            await clearServiceItemAudioAsset(serviceId, 0);
                            const afterConfirm = parseServiceItemMemo(state.serviceItems[serviceId][0].memo).audioAsset || {};

                            return {
                              prompts,
                              afterCancel,
                              afterConfirm,
                              saves,
                              refreshCount,
                              detailRenderCount,
                              listRenderCount,
                              toasts,
                            };
                          } finally {
                            if (originalItems === undefined) delete state.serviceItems[serviceId];
                            else state.serviceItems[serviceId] = originalItems;
                            window.confirm = originalConfirm;
                            saveService = originalSaveService;
                            refreshPresenterForService = originalRefreshPresenterForService;
                            renderCurrentServiceModuleDetail = originalRenderCurrentServiceModuleDetail;
                            renderServiceList = originalRenderServiceList;
                            showToast = originalShowToast;
                          }
                        }
                        """
                    )
                    if (
                        len(presenter_praise_header_audio_clear_confirm["prompts"]) == 2
                        and "특송 MR.mp3" in presenter_praise_header_audio_clear_confirm["prompts"][0]["message"]
                        and presenter_praise_header_audio_clear_confirm["afterCancel"].get("kind") == "audio"
                        and presenter_praise_header_audio_clear_confirm["afterCancel"].get("name") == "특송 MR.mp3"
                        and presenter_praise_header_audio_clear_confirm["afterConfirm"] == {"kind": "", "name": "", "url": ""}
                        and presenter_praise_header_audio_clear_confirm["saves"] == ["__smoke_praise_header_audio_clear__"]
                        and presenter_praise_header_audio_clear_confirm["refreshCount"] == 1
                        and presenter_praise_header_audio_clear_confirm["detailRenderCount"] == 1
                        and presenter_praise_header_audio_clear_confirm["listRenderCount"] == 1
                    ):
                        pass_("presenter-praise-header-audio-clear-confirm", json.dumps(presenter_praise_header_audio_clear_confirm, ensure_ascii=False))
                    else:
                        fail("presenter-praise-header-audio-clear-confirm", json.dumps(presenter_praise_header_audio_clear_confirm, ensure_ascii=False))

                    presenter_response_prayer_input_guard = page.evaluate(
                        """
                        (() => {
                          const service = state.services.find((item) => item.id === state.selectedServiceId);
                          const responsePrayer = servicePrepEditorItems(service?.id || '')
                            .find((item) => item._worshipSectionKey === 'response_song' && compactSearchValue(item.label || '') === '결단기도');
                          if (!responsePrayer) return { skipped: true };
                          const memo = parseServiceItemMemo(responsePrayer.memo);
                          const contentState = resolvePresenterServiceItemContentState(responsePrayer, memo, null, service);
                          const slides = buildPresenterSlidesForServiceItem(responsePrayer, service, 0);
                          return {
                            skipped: false,
                            inputItem: Boolean(presenterServiceInputItem(responsePrayer, service)),
                            state: contentState.state,
                            hasOutputContent: contentState.hasOutputContent,
                            reason: contentState.reason,
                            missingSlides: slides.filter((slide) => slide?.missingContent).length,
                            titles: slides.map((slide) => slide.title || slide.text || ''),
                          };
                        })()
                        """
                    )
                    if presenter_response_prayer_input_guard.get("skipped"):
                        skip("presenter-response-prayer-input-guard", "No response prayer item.")
                    elif (
                        not presenter_response_prayer_input_guard["inputItem"]
                        and presenter_response_prayer_input_guard["state"] == "filled"
                        and presenter_response_prayer_input_guard["reason"] == "fixed_title"
                        and presenter_response_prayer_input_guard["missingSlides"] == 0
                        and presenter_response_prayer_input_guard["titles"] == ["결단기도"]
                    ):
                        pass_("presenter-response-prayer-input-guard", json.dumps(presenter_response_prayer_input_guard, ensure_ascii=False))
                    else:
                        fail("presenter-response-prayer-input-guard", json.dumps(presenter_response_prayer_input_guard, ensure_ascii=False))

                    youth_missing_input_guard = page.evaluate(
                        """
                        (() => {
                          const service = { id: '__smoke_youth_missing__', type_id: 'youth', date: '2026-07-26' };
                          const previousServices = state.services;
                          const previousItems = state.serviceItems;
                          const previousTranslations = state.bibleTranslations;
                          const previousSelectedTranslationId = state.selectedBibleTranslationId;
                          try {
                            state.bibleTranslations = [{ id: '__smoke_krv__', name: '개역개정', abbreviation: '개역개정', code: 'KRV' }];
                            state.selectedBibleTranslationId = '__smoke_krv__';
                            state.services = [...previousServices, service];
                            const items = projectWorshipServiceItemsFromTemplate(service, []);
                            state.serviceItems = { ...previousItems, [service.id]: items };
                            state.loadedWorshipServiceIds.add(service.id);
                            const states = ['대표기도', '성경봉독', '설교 제목', '봉헌기도'].map((label) => {
                              const item = items.find((entry) => entry.label === label);
                              const content = resolvePresenterServiceItemContentState(item, parseServiceItemMemo(item?.memo), null, service);
                              return { label, state: content.state, reason: content.reason };
                            });
                            const missingSlides = buildServicePresenterSlides(service.id).filter((slide) => slide?.missingContent).length;
                            const reading = items.find((entry) => entry.label === '성경봉독');
                            const readingIndex = items.indexOf(reading);
                            updateServiceItemField({
                              dataset: { serviceId: service.id, serviceItemIndex: String(readingIndex), serviceItemField: 'raw_title' },
                              value: '요 3:16',
                            });
                            cacheServiceScriptureVerses(parseBibleReference('요 3:16'), [
                              { book_code: 'JHN', chapter: 3, verse: 16, text: '하나님이 세상을 이처럼 사랑하사' },
                            ]);
                            const announcement = items.find((entry) => entry.label === '광고');
                            const announcementIndex = items.indexOf(announcement);
                            updateServiceItemField({
                              dataset: { serviceId: service.id, serviceItemIndex: String(announcementIndex), serviceItemField: 'raw_title' },
                              value: '1. 다음 주 토요일 여름수련회 준비 모임\\n준비물은 개인 물병입니다\\n2. 반별 사진 제출',
                            });
                            const preparedSlides = buildServicePresenterSlides(service.id);
                            const preparedReading = state.serviceItems[service.id].find((entry) => entry.label === '성경봉독');
                            const preparedAnnouncement = state.serviceItems[service.id].find((entry) => entry.label === '광고');
                            return {
                              states,
                              missingSlides,
                              readingMemo: parseServiceItemMemo(preparedReading?.memo),
                              announcementMemo: parseServiceItemMemo(preparedAnnouncement?.memo),
                              announcementRawTitle: preparedAnnouncement?.raw_title || '',
                              announcementInputHtml: renderPresenterServiceTextInputs(preparedAnnouncement, announcementIndex, serviceItemEditorModel(preparedAnnouncement, { service }), parseServiceItemMemo(preparedAnnouncement?.memo)),
                              readingSlides: preparedSlides.filter((slide) => slide?.sectionKey === 'scripture_reading').map((slide) => slide.type),
                              announcement: preparedSlides.find((slide) => slide?.elementLabel === '광고') || {},
                            };
                          } finally {
                            state.loadedWorshipServiceIds.delete(service.id);
                            state.services = previousServices;
                            state.serviceItems = previousItems;
                            state.bibleTranslations = previousTranslations;
                            state.selectedBibleTranslationId = previousSelectedTranslationId;
                          }
                        })()
                        """
                    )
                    if (
                        [entry["label"] for entry in youth_missing_input_guard["states"]]
                        == ["대표기도", "성경봉독", "설교 제목", "봉헌기도"]
                        and [entry["state"] for entry in youth_missing_input_guard["states"]]
                        == ["missing", "missing", "missing", "missing"]
                        and youth_missing_input_guard["missingSlides"] >= 3
                        and youth_missing_input_guard["readingSlides"] == ["title-content", "scripture"]
                        and youth_missing_input_guard["announcement"].get("type") == "liturgical-body"
                        and youth_missing_input_guard["announcement"].get("title") == "광고"
                        and youth_missing_input_guard["announcement"].get("text", "") == "① 다음 주 토요일 여름수련회 준비 모임\n준비물은 개인 물병입니다\n② 반별 사진 제출"
                        and youth_missing_input_guard["announcement"].get("announcementItems") == [
                            {"marker": "①", "lines": ["다음 주 토요일 여름수련회 준비 모임", "준비물은 개인 물병입니다"]},
                            {"marker": "②", "lines": ["반별 사진 제출"]},
                        ]
                        and "<textarea" in youth_missing_input_guard["announcementInputHtml"]
                        and "svc-presenter-input-field--announcement" in youth_missing_input_guard["announcementInputHtml"]
                        and "<span>내용</span>" not in youth_missing_input_guard["announcementInputHtml"]
                        and "줄 맨 앞의 1., 2.마다 새 항목" in youth_missing_input_guard["announcementInputHtml"]
                        and "번호 없는 다음 줄은 같은 항목" in youth_missing_input_guard["announcementInputHtml"]
                    ):
                        pass_("youth-missing-input-guard", json.dumps(youth_missing_input_guard, ensure_ascii=False))
                    else:
                        fail("youth-missing-input-guard", json.dumps(youth_missing_input_guard, ensure_ascii=False))

                    live_scripture_translation_hint = page.evaluate(
                        """
                        async () => {
                          const previousClient = state.client;
                          const previousTranslations = state.bibleTranslations;
                          const previousSelectedTranslationId = state.selectedBibleTranslationId;
                          const requests = [];
                          try {
                            state.bibleTranslations = [
                              { id: '__live_ko__', translationKey: 'KRV', name: '개역한글', abbreviation: '개역한글', language: 'ko' },
                              { id: '__live_new_ko__', translationKey: 'NKSB', name: '새한글성경', abbreviation: '새한글', language: 'ko' },
                              { id: '__live_niv__', translationKey: 'NIV', name: 'New International Version', abbreviation: 'NIV', language: 'en' },
                            ];
                            state.selectedBibleTranslationId = '__live_ko__';
                            state.client = {
                              from(table) {
                                const filters = [];
                                const builder = {
                                  select() { return builder; },
                                  eq(field, value) { filters.push([field, value]); return builder; },
                                  gte(field, value) { filters.push([field, value]); return builder; },
                                  lte(field, value) { filters.push([field, value]); return builder; },
                                  order() { return builder; },
                                  then(resolve) {
                                    const translationId = filters.find(([field]) => field === 'translation_id')?.[1] || '';
                                    requests.push({ table, filters });
                                    resolve({
                                      data: [{
                                        book_code: 'GEN',
                                        chapter: 1,
                                        verse: 1,
                                        text: translationId === '__live_niv__'
                                          ? 'In the beginning God created the heavens and the earth.'
                                          : translationId === '__live_new_ko__'
                                            ? '처음에 하나님이 하늘과 땅을 창조하셨다.'
                                            : '태초에 하나님이 천지를 창조하시니라',
                                      }],
                                      error: null,
                                    });
                                  },
                                };
                                return builder;
                              },
                            };
                            const korean = await buildLiveScriptureSlide('창 1 1 개역한글');
                            const newKorean = await buildLiveScriptureSlide('창 1 1 새한글성경');
                            const english = await buildLiveScriptureSlide('창 1 1 NIV');
                            return {
                              koreanTitle: korean?.title || '',
                              koreanText: korean?.text || '',
                              koreanTranslation: korean?.translationLabel || '',
                              newKoreanTitle: newKorean?.title || '',
                              newKoreanText: newKorean?.text || '',
                              newKoreanTranslation: newKorean?.translationLabel || '',
                              englishTitle: english?.title || '',
                              englishText: english?.text || '',
                              englishTranslation: english?.translationLabel || '',
                              requestedTranslationIds: requests.map((request) => request.filters.find(([field]) => field === 'translation_id')?.[1] || ''),
                            };
                          } finally {
                            state.client = previousClient;
                            state.bibleTranslations = previousTranslations;
                            state.selectedBibleTranslationId = previousSelectedTranslationId;
                          }
                        }
                        """
                    )
                    if (
                        live_scripture_translation_hint["koreanTitle"] == "창 1:1"
                        and live_scripture_translation_hint["koreanText"].startswith("창 1:1   태초에")
                        and live_scripture_translation_hint["koreanTranslation"] == "개역한글"
                        and live_scripture_translation_hint["newKoreanTitle"] == "창 1:1"
                        and live_scripture_translation_hint["newKoreanText"].startswith("창 1:1   처음에")
                        and live_scripture_translation_hint["newKoreanTranslation"] == "새한글"
                        and live_scripture_translation_hint["englishTitle"] == "Gen 1:1"
                        and live_scripture_translation_hint["englishText"].startswith("Gen 1:1   In the beginning")
                        and live_scripture_translation_hint["englishTranslation"] == "NIV"
                        and live_scripture_translation_hint["requestedTranslationIds"] == ["__live_ko__", "__live_new_ko__", "__live_niv__"]
                    ):
                        pass_("live-scripture-translation-hint", json.dumps(live_scripture_translation_hint, ensure_ascii=False))
                    else:
                        fail("live-scripture-translation-hint", json.dumps(live_scripture_translation_hint, ensure_ascii=False))

                    presenter_preparation_real_song_match = page.evaluate(
                        """
                        (() => {
                          const service = state.services.find((entry) => entry.type_id === 'wednesday') || state.services[0];
                          const item = normalizeServiceItem({
                            service_id: service?.id || '',
                            label: '찬양 1',
                            memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' }),
                          });
                          return ['평화 하나님의 평강이', '이 세상은 내 집 아니네', '슬픈 마음 있는 사람', '충만', '나는 믿네']
                            .map((query) => {
                              const song = resolvePresenterPreparationSong(query, item, service);
                              return { query, id: song?.id || '', title: songServiceOptionLabel(song) || song?.title || '', versions: song?.versions?.length || 0 };
                            });
                        })()
                        """
                    )
                    if all(match["id"] for match in presenter_preparation_real_song_match):
                        pass_("presenter-preparation-real-song-match", json.dumps(presenter_preparation_real_song_match, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-real-song-match", json.dumps(presenter_preparation_real_song_match, ensure_ascii=False))

                    presenter_preparation_song_index = page.evaluate(
                        """
                        (() => {
                          clearSearchCaches();
                          const first = presenterPreparationSongExactIndex();
                          const second = presenterPreparationSongExactIndex();
                          const sampleSong = state.songs.find((song) => song.title === '충만') || state.songs[0];
                          const sampleKey = compactSearchValue(sampleSong?.title || '');
                          const sampleMatches = first.labels.get(sampleKey) || [];
                          clearSearchCaches();
                          const third = presenterPreparationSongExactIndex();
                          return {
                            reused: first === second,
                            invalidated: first !== third,
                            sampleFound: sampleMatches.some((song) => song.id === sampleSong?.id),
                            hymn430Count: (third.hymnNos.get('430') || []).length,
                          };
                        })()
                        """
                    )
                    if (
                        presenter_preparation_song_index.get("reused") is True
                        and presenter_preparation_song_index.get("invalidated") is True
                        and presenter_preparation_song_index.get("sampleFound") is True
                        and presenter_preparation_song_index.get("hymn430Count", 0) >= 1
                    ):
                        pass_("presenter-preparation-song-index", json.dumps(presenter_preparation_song_index, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-song-index", json.dumps(presenter_preparation_song_index, ensure_ascii=False))

                    presenter_preparation_middle_dot_separator = page.evaluate(
                        """
                        (() => {
                          const parsed = parsePresenterPreparationInput(`찬양 1 · 목마른 사슴 시냇물
찬양 2 · 지금은 엘리야때처럼
찬양 3 · 꽃들도`);
                          return {
                            errors: parsed.errors,
                            entries: parsed.entries.map((entry) => ({
                              label: entry.label,
                              content: entry.content,
                            })),
                          };
                        })()
                        """
                    )
                    if (
                        presenter_preparation_middle_dot_separator.get("errors") == []
                        and presenter_preparation_middle_dot_separator.get("entries") == [
                            {"label": "찬양 1", "content": "목마른 사슴 시냇물"},
                            {"label": "찬양 2", "content": "지금은 엘리야때처럼"},
                            {"label": "찬양 3", "content": "꽃들도"},
                        ]
                    ):
                        pass_("presenter-preparation-middle-dot-separator", json.dumps(presenter_preparation_middle_dot_separator, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-middle-dot-separator", json.dumps(presenter_preparation_middle_dot_separator, ensure_ascii=False))

                    presenter_preparation_hymn_slot_numbering = page.evaluate(
                        """
                        (() => {
                          const parsed = parsePresenterPreparationInput(`찬양 1 찬 1장
찬양 2. 1
찬양 3. 찬송가 2장
찬양4:2장`);
                          return {
                            errors: parsed.errors,
                            entries: parsed.entries.map((entry) => ({
                              label: entry.label,
                              content: entry.content,
                            })),
                          };
                        })()
                        """
                    )
                    if (
                        presenter_preparation_hymn_slot_numbering.get("errors") == []
                        and presenter_preparation_hymn_slot_numbering.get("entries") == [
                            {"label": "찬양 1", "content": "찬 1장"},
                            {"label": "찬양 2", "content": "찬 1장"},
                            {"label": "찬양 3", "content": "찬 2장"},
                            {"label": "찬양 4", "content": "찬 2장"},
                        ]
                    ):
                        pass_("presenter-preparation-hymn-slot-numbering", json.dumps(presenter_preparation_hymn_slot_numbering, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-hymn-slot-numbering", json.dumps(presenter_preparation_hymn_slot_numbering, ensure_ascii=False))

                    presenter_preparation_hymn_apply_flow = page.evaluate(
                        """
                        (async () => {
                          const original = {
                            songs: state.songs,
                            services: state.services,
                            serviceItems: state.serviceItems,
                            selectedServiceId: state.selectedServiceId,
                            selectedServiceTypeId: state.selectedServiceTypeId,
                            drafts: state.presenterPreparationDrafts,
                            dirty: state.dirty.service,
                            showToast,
                          };
                          const service = { id: '__smoke_hymn_apply_flow__', type_id: 'special', date: '2099-08-30' };
                          const hymnOne = {
                            id: '__smoke_apply_hymn_1__',
                            title: '만복의 근원 하나님',
                            hymn_no: '1',
                            praise_types: ['hymn'],
                          };
                          hymnOne.versions = normalizeSongVersions(hymnOne, [
                            { id: '__smoke_apply_hymn_1_new__', name: '새찬송가', praise_types: ['hymn'], forms: [] },
                            { id: '__smoke_apply_hymn_1_alt__', name: '다른 버전', praise_types: ['hymn'], forms: [] },
                          ]);
                          const hymnTwo = {
                            id: '__smoke_apply_hymn_2__',
                            title: '찬양 성부 성자 성령',
                            hymn_no: '2',
                            praise_types: ['hymn'],
                          };
                          hymnTwo.versions = normalizeSongVersions(hymnTwo, [
                            { id: '__smoke_apply_hymn_2_new__', name: '새찬송가', praise_types: ['hymn'], forms: [] },
                          ]);
                          const ccmTen = {
                            id: '__smoke_apply_ccm_10__',
                            title: '10 전능왕 오셔서',
                            praise_types: ['ccm'],
                          };
                          ccmTen.versions = normalizeSongVersions(ccmTen, [
                            { id: '__smoke_apply_ccm_10_v1__', name: '기본', praise_types: ['ccm'], forms: [] },
                          ]);
                          const toasts = [];
                          try {
                            state.songs = [hymnOne, hymnTwo, ccmTen];
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.selectedServiceTypeId = service.type_id;
                            state.serviceItems = {
                              [service.id]: ['찬양 1', '찬양 2', '찬양 3', '찬양 4', '찬양 5'].map((label, index) => normalizeServiceItem({
                                id: `__smoke_apply_item_${index + 1}__`,
                                service_id: service.id,
                                label,
                                memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' }),
                                _worshipSectionKey: 'praise',
                                _worshipSectionTitle: '찬양',
                              }, index)),
                            };
                            state.presenterPreparationDrafts = {
                              [service.id]: `찬양 1 찬 1장
찬양 2. 1
찬양 3. 찬송가 2장
찬양4:2장
찬양 5: 10 전능왕 오셔서`,
                            };
                            showToast = (message, type = 'info') => {
                              toasts.push({ message, type });
                            };
                            await applyPresenterPreparationInput(service.id);
                            const targetLabels = ['찬양 1', '찬양 2', '찬양 3', '찬양 4', '찬양 5'];
                            const items = targetLabels.map((label) =>
                              (state.serviceItems[service.id] || []).find((item) => item.label === label) || {});
                            return {
                              songs: items.map((item) => item.song_id || ''),
                              versions: items.map((item) => item.version_id || item.song_version_id || ''),
                              rawTitles: items.map((item) => item.raw_title || ''),
                              saveProblem: serviceInputSaveProblem(service),
                              draftCleared: !state.presenterPreparationDrafts[service.id],
                              toasts,
                            };
                          } finally {
                            state.songs = original.songs;
                            state.services = original.services;
                            state.serviceItems = original.serviceItems;
                            state.selectedServiceId = original.selectedServiceId;
                            state.selectedServiceTypeId = original.selectedServiceTypeId;
                            state.presenterPreparationDrafts = original.drafts;
                            state.dirty.service = original.dirty;
                            showToast = original.showToast;
                            renderPresenterDetail();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_hymn_apply_flow["songs"] == [
                            "__smoke_apply_hymn_1__",
                            "__smoke_apply_hymn_1__",
                            "__smoke_apply_hymn_2__",
                            "__smoke_apply_hymn_2__",
                            "__smoke_apply_ccm_10__",
                        ]
                        and presenter_preparation_hymn_apply_flow["versions"] == [
                            "__smoke_apply_hymn_1_new__",
                            "__smoke_apply_hymn_1_new__",
                            "__smoke_apply_hymn_2_new__",
                            "__smoke_apply_hymn_2_new__",
                            "__smoke_apply_ccm_10_v1__",
                        ]
                        and presenter_preparation_hymn_apply_flow["rawTitles"] == ["", "", "", "", ""]
                        and presenter_preparation_hymn_apply_flow["saveProblem"] == ""
                        and presenter_preparation_hymn_apply_flow["draftCleared"] is True
                        and presenter_preparation_hymn_apply_flow["toasts"]
                        and presenter_preparation_hymn_apply_flow["toasts"][-1]["type"] == "info"
                        and "찬양 1" in presenter_preparation_hymn_apply_flow["toasts"][-1]["message"]
                    ):
                        pass_("presenter-preparation-hymn-apply-flow", json.dumps(presenter_preparation_hymn_apply_flow, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-hymn-apply-flow", json.dumps(presenter_preparation_hymn_apply_flow, ensure_ascii=False))

                    presenter_preparation_label_priority = page.evaluate(
                        """
                        (() => {
                          const parsed = parsePresenterPreparationInput(`기도찬양 나의 반석이신 하나님
기도찬양2 부흥
대표기도 문병자 권사
특송 찬 430
말씀 “신유란 무엇인가요?”
설교 김남영 목사
성경봉독 요 15:9; 롬 5:7-8
봉헌찬양 임재
파송찬송 찬 359
폐회찬송 찬 352
송영 찬 5`);
                          return {
                            errors: parsed.errors,
                            entries: parsed.entries.map((entry) => ({
                              rawLabel: entry.rawLabel,
                              label: entry.label,
                              key: entry.key,
                              rawKey: entry.rawKey,
                              content: entry.content,
                            })),
                          };
                        })()
                        """
                    )
                    if (
                        presenter_preparation_label_priority.get("errors") == []
                        and presenter_preparation_label_priority.get("entries") == [
                            {"rawLabel": "기도찬양", "label": "기도찬양", "key": "기도찬양", "rawKey": "기도찬양", "content": "나의 반석이신 하나님"},
                            {"rawLabel": "기도찬양 2", "label": "기도찬양 2", "key": "기도찬양2", "rawKey": "기도찬양2", "content": "부흥"},
                            {"rawLabel": "대표기도", "label": "대표기도", "key": "대표기도", "rawKey": "대표기도", "content": "문병자 권사"},
                            {"rawLabel": "특송", "label": "특송", "key": "특송", "rawKey": "특송", "content": "찬 430"},
                            {"rawLabel": "말씀", "label": "설교 본문", "key": "설교본문", "rawKey": "말씀", "content": "신유란 무엇인가요?"},
                            {"rawLabel": "설교", "label": "설교 제목", "key": "설교제목", "rawKey": "설교", "content": "김남영 목사"},
                            {"rawLabel": "성경봉독", "label": "성경봉독", "key": "성경봉독", "rawKey": "성경봉독", "content": "요 15:9; 롬 5:7-8"},
                            {"rawLabel": "봉헌찬양", "label": "봉헌찬양", "key": "봉헌찬양", "rawKey": "봉헌찬양", "content": "임재"},
                            {"rawLabel": "파송찬송", "label": "파송찬송", "key": "파송찬송", "rawKey": "파송찬송", "content": "찬 359장"},
                            {"rawLabel": "폐회찬송", "label": "폐회찬송", "key": "폐회찬송", "rawKey": "폐회찬송", "content": "찬 352장"},
                            {"rawLabel": "송영", "label": "송영", "key": "송영", "rawKey": "송영", "content": "찬 5장"},
                        ]
                    ):
                        pass_("presenter-preparation-label-priority", json.dumps(presenter_preparation_label_priority, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-label-priority", json.dumps(presenter_preparation_label_priority, ensure_ascii=False))

                    presenter_preparation_existing_song_guard = page.evaluate(
                        """
                        (async () => {
                          const originalSongs = state.songs;
                          const originalClient = state.client;
                          const originalServices = state.services;
                          const originalServiceItems = state.serviceItems;
                          const originalSelectedServiceId = state.selectedServiceId;
                          const service = { id: '__smoke_existing_song_service__', type_id: 'special', date: '2026-07-31' };
                          const item = normalizeServiceItem({
                            service_id: service.id,
                            label: '찬양 1',
                            memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'lyrics_db' }),
                          });
                          let insertCalled = false;
                          try {
                            state.songs = [
                              normalizeServerSong({
                                id: '__smoke_existing_song__',
                                title: '주 내 소망은 주 더 알기 원합니다',
                                original_title: 'To Know You More',
                                memo: serializeSongMemo({ versions: [{
                                  id: '__smoke_existing_song_version__',
                                  name: '기본',
                                  is_primary: true,
                                  forms: [{ id: '__smoke_existing_song_form__', label: 'Verse 1', lyrics: '오 주님 채우소서\\n나의 마음 깊은 곳' }],
                                }] }),
                              }),
                              normalizeServerSong({
                                id: '__smoke_other_song__',
                                title: '주님 내 소망',
                                memo: serializeSongMemo({ versions: [{
                                  id: '__smoke_other_song_version__',
                                  name: '기본',
                                  forms: [{ id: '__smoke_other_song_form__', label: 'Verse 1', lyrics: '다른 가사' }],
                                }] }),
                              }),
                              normalizeServerSong({
                                id: '__smoke_hymn_430_existing__',
                                title: '주와 같이 길 가는 것',
                                hymn_no: '430',
                                praise_types: ['hymn'],
                                memo: serializeSongMemo({ versions: [{
                                  id: '__smoke_hymn_430_existing_version__',
                                  name: '기본',
                                  is_primary: true,
                                  forms: [],
                                }] }),
                              }),
                            ];
                            state.client = {
                              from(table) {
                                if (table !== 'mindex_songs') return originalClient.from(table);
                                return {
                                  insert() {
                                    insertCalled = true;
                                    return {
                                      select() {
                                        return {
                                          single: async () => ({ data: null, error: new Error('insert should not run') }),
                                        };
                                      },
                                    };
                                  },
                                };
                              },
                            };
                            const byTitleWithKey = resolvePresenterPreparationSong('주 내 소망은 주 더 알기 원합니다 G', item, service)?.id || '';
                            const byOriginalTitle = resolvePresenterPreparationSong('To Know You More', item, service)?.id || '';
                            const byLyric = resolvePresenterPreparationSong('오 주님 채우소서', item, service)?.id || '';
                            const viaBlankFallback = await createBlankPraiseSongForServiceInput('주 내 소망은 주 더 알기 원합니다 G', service);
                            const hymnViaBlankFallback = await createBlankPraiseSongForServiceInput('430장 주와 같이 길 가는 것', service);
                            const specialHymnViaBlankFallback = await createBlankPraiseSongForServiceInput('찬 430', service);
                            const specialSongWithRoleViaBlankFallback = await createBlankPraiseSongForServiceInput('특송 찬 430', service);
                            const bareHymnWithTitleViaBlankFallback = await createBlankPraiseSongForServiceInput('430 주와 같이 길 가는 것', service);
                            const connectedSongResolve = resolvePresenterPreparationSong('모든 열방 주 볼 때까지 + 물이 바다 덮음같이', item, service)?.id || '';
                            const connectedViaBlankFallback = await createBlankPraiseSongForServiceInput('모든 열방 주 볼 때까지 + 물이 바다 덮음같이', service, item);
                            const serviceItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '찬양 1',
                              raw_title: '주 내 소망은 주 더 알기 원합니다 G',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'lyrics_db' }),
                            });
                            const pickerBareHymn = serviceSongPickerResults('430 주와 같이 길 가는 것', serviceItem, service).map((song) => song.id);
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.serviceItems = { [service.id]: [serviceItem] };
                            await createPraiseSongFromServiceItem(0);
                            const linkedFromInput = getServiceItems(service.id)[0]?.song_id || '';
                            const connectedServiceItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '찬양 2',
                              raw_title: '모든 열방 주 볼 때까지 + 물이 바다 덮음같이',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'lyrics_db' }),
                            });
                            state.serviceItems = { [service.id]: [connectedServiceItem] };
                            await createPraiseSongFromServiceItem(0);
                            const connectedCreateButtonSongId = getServiceItems(service.id)[0]?.song_id || '';
                            const specialManualItem = normalizeServiceItem({
                              service_id: service.id,
                              label: '특송',
                              raw_title: '특송 찬 430',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'manual_praise', outputMode: 'lyrics' }),
                            });
                            state.serviceItems = { [service.id]: [specialManualItem] };
                            await resolveServiceSongSelectionBeforeSave(service.id, 0);
                            const resolvedSpecial = getServiceItems(service.id)[0] || {};
                            const resolvedSpecialMemo = parseServiceItemMemo(resolvedSpecial.memo);
                            return {
                              byTitleWithKey,
                              byOriginalTitle,
                              byLyric,
                              viaBlankFallback: viaBlankFallback?.id || '',
                              hymnViaBlankFallback: hymnViaBlankFallback?.id || '',
                              specialHymnViaBlankFallback: specialHymnViaBlankFallback?.id || '',
                              specialSongWithRoleViaBlankFallback: specialSongWithRoleViaBlankFallback?.id || '',
                              bareHymnWithTitleViaBlankFallback: bareHymnWithTitleViaBlankFallback?.id || '',
                              connectedSongResolve,
                              connectedViaBlankFallback: connectedViaBlankFallback?.id || '',
                              connectedCreateButtonSongId,
                              pickerBareHymn,
                              linkedFromInput,
                              resolvedSpecialSongId: resolvedSpecial.song_id || '',
                              resolvedSpecialRawTitle: resolvedSpecial.raw_title || '',
                              resolvedSpecialInputMode: resolvedSpecialMemo.inputMode || '',
                              resolvedSpecialVersionId: resolvedSpecial.version_id || resolvedSpecial.song_version_id || '',
                              insertCalled,
                            };
                          } finally {
                            state.songs = originalSongs;
                            state.client = originalClient;
                            state.services = originalServices;
                            state.serviceItems = originalServiceItems;
                            state.selectedServiceId = originalSelectedServiceId;
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_existing_song_guard.get("byTitleWithKey") == "__smoke_existing_song__"
                        and presenter_preparation_existing_song_guard.get("byOriginalTitle") == "__smoke_existing_song__"
                        and presenter_preparation_existing_song_guard.get("byLyric") == "__smoke_existing_song__"
                        and presenter_preparation_existing_song_guard.get("viaBlankFallback") == "__smoke_existing_song__"
                        and presenter_preparation_existing_song_guard.get("hymnViaBlankFallback") == "__smoke_hymn_430_existing__"
                        and presenter_preparation_existing_song_guard.get("specialHymnViaBlankFallback") == "__smoke_hymn_430_existing__"
                        and presenter_preparation_existing_song_guard.get("specialSongWithRoleViaBlankFallback") == "__smoke_hymn_430_existing__"
                        and presenter_preparation_existing_song_guard.get("bareHymnWithTitleViaBlankFallback") == "__smoke_hymn_430_existing__"
                        and presenter_preparation_existing_song_guard.get("connectedSongResolve") == ""
                        and presenter_preparation_existing_song_guard.get("connectedViaBlankFallback") == ""
                        and presenter_preparation_existing_song_guard.get("connectedCreateButtonSongId") == ""
                        and presenter_preparation_existing_song_guard.get("pickerBareHymn", [None])[0] == "__smoke_hymn_430_existing__"
                        and presenter_preparation_existing_song_guard.get("linkedFromInput") == "__smoke_existing_song__"
                        and presenter_preparation_existing_song_guard.get("resolvedSpecialSongId") == ""
                        and presenter_preparation_existing_song_guard.get("resolvedSpecialRawTitle") == "특송 찬 430"
                        and presenter_preparation_existing_song_guard.get("resolvedSpecialInputMode") == "manual_praise"
                        and presenter_preparation_existing_song_guard.get("resolvedSpecialVersionId") == ""
                        and presenter_preparation_existing_song_guard.get("insertCalled") is False
                    ):
                        pass_("presenter-preparation-existing-song-guard", json.dumps(presenter_preparation_existing_song_guard, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-existing-song-guard", json.dumps(presenter_preparation_existing_song_guard, ensure_ascii=False))

                    presenter_preparation_paste = page.evaluate(
                        """
                        (async () => {
                          const original = {
                            module: state.module,
                            songs: state.songs,
                            services: state.services,
                            serviceItems: state.serviceItems,
                            client: state.client,
                            songVersionTablesSupported: state.songVersionTablesSupported,
                            selectedServiceId: state.selectedServiceId,
                            selectedServiceTypeId: state.selectedServiceTypeId,
                            presenterViewServiceId: state.presenter.viewServiceId,
                            calendarData: state.calendarData,
                            drafts: state.presenterPreparationDrafts,
                            dirty: state.dirty.service,
                          };
                          const service = { id: '__smoke_preparation_input__', type_id: 'wednesday', date: '2026-07-15', alias: '' };
                          const item = (label, elementType, sectionKey, order) => normalizeServiceItem({
                            id: `__smoke_${label}__`,
                            service_id: service.id,
                            label,
                            memo: serializeServiceItemMemo({ elementType, inputMode: serviceInputModeForElementType(elementType) }),
                            _worshipSectionId: `__smoke_section_${sectionKey}__`,
                            _worshipSectionKey: sectionKey,
                            _worshipSectionTitle: sectionKey === 'sermon' ? '설교' : sectionKey === 'prayer' ? '대표기도' : sectionKey === 'scripture_reading' ? '성경봉독' : sectionKey === 'response_song' ? '결단' : '찬양',
                            _worshipSectionOrder: order,
                            _worshipElementOrder: 1,
                          });
                          try {
                            state.module = 'home';
                            state.songs = [
                              { id: '__batch_praise_1__', title: '평화', subtitle: '하나님의 평강이', versions: [{ id: '__batch_praise_1_v__', name: '기본' }] },
                              { id: '__batch_praise_2__', title: '이 세상은 내 집 아니네', versions: [{ id: '__batch_praise_2_v__', name: '기본' }] },
                              { id: '__batch_praise_3__', title: '슬픈 마음 있는 사람', versions: [{ id: '__batch_praise_3_v__', name: '기본' }] },
                              { id: '__batch_praise_4__', title: '충만', versions: [{ id: '__batch_praise_4_v__', name: '기본' }] },
                              { id: '__batch_response__', title: '나는 믿네', versions: [{ id: '__batch_response_v__', name: '기본' }] },
                              { id: '__batch_hymn_9__', title: '하늘에 가득 찬 영광의', hymn_no: '9', versions: [{ id: '__batch_hymn_9_v__', name: '새찬송가' }, { id: '__batch_hymn_9_unified__', name: '통일 9' }] },
                              { id: '__batch_hymn_288__', title: '예수를 나의 구주 삼고', hymn_no: '288', versions: [{ id: '__batch_hymn_288_v__', name: '새찬송가' }, { id: '__batch_hymn_288_unified__', name: '통일 204' }] },
                              { id: '__batch_hymn_182__', title: '강물같이 흐르는 기쁨', hymn_no: '182', versions: [{ id: '__batch_hymn_182_v__', name: '새찬송가' }, { id: '__batch_hymn_182_unified__', name: '통일 169' }] },
                              { id: '__batch_hymn_187__', title: '비둘기같이 온유한', hymn_no: '187', versions: [{ id: '__batch_hymn_187_v__', name: '새찬송가' }] },
                            ];
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.selectedServiceTypeId = service.type_id;
                            state.serviceItems = {
                              [service.id]: [
                                item('찬양 1', 'praise', 'praise', 2),
                                item('찬양 2', 'praise', 'praise', 2),
                                item('찬양 3', 'praise', 'praise', 2),
                                item('찬양 4', 'praise', 'praise', 2),
                                item('기도', 'title_person', 'prayer', 3),
                                item('성경봉독', 'scripture_body', 'scripture_reading', 5),
                                item('설교 제목', 'title_person', 'sermon', 6),
                                item('설교 본문', 'scripture_body', 'sermon', 6),
                                item('결단찬양', 'praise', 'response_song', 7),
                              ],
                            };
                            state.presenterPreparationDrafts = {
                              [service.id]: `찬양 1: 평화 하나님의 평강이\n찬양 2: 이 세상은 내 집 아니네\n찬양 3: 슬픈 마음 있는 사람\n찬양 4: 충만\n\n대표기도: 정선분 권사\n성경봉독: 히 10:38–39\n설교 제목: 믿음을 잃어버릴 수도 있어요?\n인용 구절: 렘 3:22; 마 3:11; 눅 24:49; 행 2:4; 고후 10:4; 롬 8:35-37; 살전 4:3; 벧전 1:14–15; 히 4:12; 엡 5:26; 요일 1:7; 행 15:8–9; 눅 11:13; 롬 8:30; 마 5:48; 롬 13:10\n결단찬양: 나는 믿네`,
                            };
                            await applyPresenterPreparationInput(service.id);
                            const items = state.serviceItems[service.id];
                            const byLabel = (label) => items.find((entry) => entry.label === label) || {};
                            const hymnService = { id: '__smoke_preparation_hymn_versions__', type_id: 'sunday-second', date: '2026-07-19', alias: '' };
                            state.services = [service, hymnService];
                            state.serviceItems[hymnService.id] = ['찬양 1', '찬양 2', '찬양 3'].map((label, index) => normalizeServiceItem({
                              id: `__smoke_hymn_${index + 1}__`,
                              service_id: hymnService.id,
                              label,
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db', outputMode: 'score' }),
                              _worshipSectionId: '__smoke_hymn_praise__',
                              _worshipSectionKey: 'praise',
                              _worshipSectionTitle: '찬양',
                              _worshipSectionOrder: 2,
                              _worshipElementOrder: index + 1,
                            }, index));
                            state.presenterPreparationDrafts[hymnService.id] = `찬양 1: 하늘에 가득 찬 영광의(9장)\n찬양 2: 예수를 나의 구주 삼고(288장)\n찬양 3: 강물같이 흐르는 기쁨(182장)`;
                            await applyPresenterPreparationInput(hymnService.id);
                            const hymnItems = (state.serviceItems[hymnService.id] || [])
                              .filter((entry) => ['찬양 1', '찬양 2', '찬양 3'].includes(entry.label || ''));
                            const rawTitleScoreItem = normalizeServiceItem({
                              id: '__smoke_raw_title_score_praise__',
                              service_id: hymnService.id,
                              label: '찬양 1',
                              raw_title: '9 하늘에 가득 찬 영광의',
                              song_id: '',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db', outputMode: 'score' }),
                              _worshipSectionId: '__smoke_hymn_praise__',
                              _worshipSectionKey: 'praise',
                              _worshipSectionTitle: '찬양',
                              _worshipSectionOrder: 2,
                              _worshipElementOrder: 1,
                            }, 0);
                            const rawTitleScoreSong = presenterSongForServiceItem(
                              rawTitleScoreItem,
                              serviceItemDisplayText(rawTitleScoreItem),
                              rawTitleScoreItem.label,
                              hymnService,
                            );
                            state.hymnScoreManifest = {
                              9: {
                                title: '하늘에 가득 찬 영광의',
                                slides: [{ src: 'assets/hymn-scores/9/slide-01.webp', scoreFormLabel: 'Verse 1' }],
                              },
                            };
                            state.hymnScoreManifestLoaded = true;
                            const rawTitleScoreState = resolvePresenterServiceItemContentState(
                              rawTitleScoreItem,
                              parseServiceItemMemo(rawTitleScoreItem.memo),
                              rawTitleScoreSong,
                              hymnService,
                            );
                            const rawTitleScoreSlides = buildPresenterSlidesForServiceItem(rawTitleScoreItem, hymnService, 10);
                            const citations = items.filter(isPresenterPreparationCitationItem);
                            const citation = citations[0] || {};
                            const citationReferences = parseServiceItemMemo(citation.memo).scriptureReferences || [];
                            if (!state.bibleTranslations.length) {
                              state.bibleTranslations = [{ id: '__smoke_krv__', name: '개역개정', abbreviation: '개역개정', code: 'KRV' }];
                              state.selectedBibleTranslationId = '__smoke_krv__';
                            }
                            const translation = selectedPresenterBibleTranslation();
                            citationReferences.forEach((referenceText) => {
                              const reference = parseBibleReference(referenceText);
                              if (!reference || !translation?.id) return;
                              const start = reference.verse || 1;
                              const end = reference.verseEnd || reference.verse || start;
                              cacheServiceScriptureVerses(reference, Array.from({ length: end - start + 1 }, (_, offset) => ({
                                book_code: reference.book.code,
                                chapter: reference.chapter,
                                verse: start + offset,
                                text: `${referenceText} ${start + offset}`,
                              })));
                            });
                            const citationSlides = buildPresenterScriptureTextSlides(citation, {
                              sectionKey: 'sermon', sectionLabel: '설교', sectionTitle: '설교',
                            }, 0);
                            const citationMemoRoundTrip = parseServiceItemMemo(serializeServiceItemMemo(parseServiceItemMemo(citation.memo)));
                            const citationConfig = serviceElementConfigForSave({}, citationMemoRoundTrip, { item: citation, service });
                            const shorthandDraft = `하늘에 가득 찬 영광의(9장)\n예수를 나의 구주 삼고(288장)\n강물같이 흐르는 기쁨(182장)\n성경봉독 요 21:15~25\n설교 제목  베드로의 고백\n봉헌찬송 찬 187장`;
                            const shorthand = parsePresenterPreparationInput(shorthandDraft);
                            const mixedNumbering = parsePresenterPreparationInput(`찬양 1: 평화 하나님의 평강이\n찬양 3: 슬픈 마음 있는 사람\n충만`);
                            const shorthandSongIds = shorthand.entries
                              .filter((entry) => /^찬양\\d+$|^봉헌찬송$/.test(entry.key))
                              .map((entry) => resolvePresenterPreparationSong(entry.content, {}, service)?.id || '');
                            const fullscreenService = { id: '__smoke_preparation_fullscreen__', type_id: 'sunday-second', date: '2026-07-19', alias: '' };
                            state.services = [service, fullscreenService];
                            state.serviceItems[fullscreenService.id] = [
                              normalizeServiceItem({
                                id: '__smoke_fullscreen_reading__',
                                service_id: fullscreenService.id,
                                label: '성경봉독',
                                memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' }),
                                _worshipSectionId: '__smoke_fullscreen_scripture__',
                                _worshipSectionKey: 'scripture_reading',
                                _worshipSectionTitle: '성경봉독',
                                _worshipSectionOrder: 5,
                                _worshipElementOrder: 1,
                              }, 0),
                              normalizeServiceItem({
                                id: '__smoke_fullscreen_sermon_title__',
                                service_id: fullscreenService.id,
                                label: '설교 제목',
                                memo: serializeServiceItemMemo({ elementType: 'title_person', inputMode: 'text' }),
                                _worshipSectionId: '__smoke_fullscreen_sermon__',
                                _worshipSectionKey: 'sermon',
                                _worshipSectionTitle: '설교',
                                _worshipSectionOrder: 6,
                                _worshipElementOrder: 1,
                              }, 1),
                            ];
                            state.presenterPreparationDrafts[fullscreenService.id] = `본문 요 21:15~25\n인용 구절: 렘 3:22, 마 3:11, 눅 24:49`;
                            await applyPresenterPreparationInput(fullscreenService.id);
                            const fullscreenItems = state.serviceItems[fullscreenService.id] || [];
                            const fullscreenReading = fullscreenItems.find((entry) => entry.label === '성경봉독') || {};
                            const fullscreenCitation = fullscreenItems.find(isPresenterPreparationCitationItem) || {};
                            const fullscreenCitationMemo = parseServiceItemMemo(fullscreenCitation.memo);
                            const looseService = { id: '__smoke_preparation_loose__', type_id: 'sunday-afternoon', date: '2026-07-19', alias: '' };
                            const createdSongs = [];
                            state.client = {
                              from(table) {
                                if (table !== 'mindex_songs') return original.client.from(table);
                                return {
                                  insert(payload) {
                                    const row = {
                                      id: `__created_song_${createdSongs.length + 1}__`,
                                      title: payload.title,
                                      praise_types: payload.praise_types || [],
                                      memo: payload.memo || null,
                                    };
                                    createdSongs.push(row);
                                    return {
                                      select() {
                                        return {
                                          single: async () => ({ data: row, error: null }),
                                        };
                                      },
                                    };
                                  },
                                  update() {
                                    return {
                                      eq: async () => ({ data: null, error: null }),
                                    };
                                  },
                                };
                              },
                            };
                            state.songVersionTablesSupported = false;
                            state.services = [looseService];
                            state.serviceItems[looseService.id] = [
                              item('찬양 1', 'praise', 'praise', 2),
                              item('찬양 2', 'praise', 'praise', 2),
                              item('찬양 3', 'praise', 'praise', 2),
                              item('찬양 4', 'praise', 'praise', 2),
                              item('기도', 'title_person', 'prayer', 3),
                              item('설교 제목', 'title_person', 'sermon', 6),
                            ];
                            const loosePlaceholder = presenterPreparationPlaceholderForService(looseService);
                            state.presenterPreparationDrafts[looseService.id] = `찬양1 주 찬양합니다\n찬양2 변찮는 주님의 사랑과\n찬양3 승리는 내 것일세\n찬양4 꽃들도\n대표기도 문병자 권사\n말씀 “신유란 무엇인가요?”\n설교 김남영 목사`;
                            await applyPresenterPreparationInput(looseService.id);
                            const looseItems = state.serviceItems[looseService.id] || [];
                            const looseByLabel = (label) => looseItems.find((entry) => entry.label === label) || {};
                            const fridayService = { id: '__smoke_preparation_friday__', type_id: 'friday', date: '2026-07-24', alias: '' };
                            state.services = [fridayService];
                            state.serviceItems[fridayService.id] = projectWorshipServiceItemsFromTemplate(fridayService, []);
                            const fridayLegacyItems = projectWorshipServiceItemsFromTemplate(fridayService, [{
                              id: '__smoke_friday_legacy_entrance__',
                              service_id: fridayService.id,
                              label: '성경봉독 전 찬양',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' }),
                              _worshipSectionKey: 'pre_scripture_praise',
                              _worshipSectionTitle: '찬양',
                              _worshipElementTemplateModified: true,
                            }, {
                              id: '__smoke_friday_legacy_prayer_praise__',
                              service_id: fridayService.id,
                              label: '기도찬양 1',
                              memo: serializeServiceItemMemo({ elementType: 'praise', inputMode: 'praise_db' }),
                              _worshipSectionKey: 'prayer_meeting_praise',
                              _worshipSectionTitle: '기도찬양',
                              _worshipElementTemplateModified: true,
                            }]);
                            const freePrayer = state.serviceItems[fridayService.id].find((entry) => entry.label === '자율기도') || {};
                            const freePrayerSlides = buildPresenterSlidesForServiceItem(freePrayer, fridayService, 0);
                            const fridayPlaceholder = presenterPreparationPlaceholderForService(fridayService);
                            state.presenterPreparationDrafts[fridayService.id] = `[썸프레이즈.07.24]

1. 주 내 소망은 주 더 알기 원합니다 G
2. 왕의 왕 주의 주 G
3. 기뻐하며 왕께 노래부르리 G
4. 오직 주의 사랑에 매여 D
5. 내 삶의 이유라 D

금요기도회입니다!
입례찬양 주 예수 나의 산 소망 G
기도찬양 마지막 날에 D
기도찬양2 부흥 G`;
                            await applyPresenterPreparationInput(fridayService.id);
                            const fridayItems = state.serviceItems[fridayService.id] || [];
                            const fridayByLabel = (label) => fridayItems.find((entry) => entry.label === label) || {};
                            const allGenerationService = {
                              id: '__smoke_all_generation_dynamic_praise__',
                              type_id: 'sunday-main',
                              date: '2026-07-26',
                              alias: '온세대 찬양예배',
                              _worshipSourceRef: { sunday_main_variant: 'all_generations' },
                            };
                            state.calendarData = [
                              ...(state.calendarData || []),
                              { id: '__smoke_all_generation_dynamic_calendar__', date: '2026-07-26', church_schedule: '온세대 찬양예배' },
                            ];
                            state.services = [allGenerationService];
                            state.serviceItems[allGenerationService.id] = projectWorshipServiceItemsFromTemplate(allGenerationService, []);
                            state.presenterPreparationDrafts[allGenerationService.id] = Array.from(
                              { length: 12 },
                              (_, index) => `찬양 ${index + 1}: 온세대 테스트곡 ${index + 1}`
                            ).join('\\n');
                            await applyPresenterPreparationInput(allGenerationService.id);
                            const allGenerationItems = state.serviceItems[allGenerationService.id] || [];
                            const allGenerationPraiseItems = allGenerationItems.filter((entry) => /^찬양\\s*\\d+$/.test(entry.label || ''));
                            const connectedService = { id: '__smoke_connected_song_input__', type_id: 'friday', date: '2026-07-31' };
                            state.services = [connectedService];
                            state.serviceItems[connectedService.id] = projectWorshipServiceItemsFromTemplate(connectedService, []);
                            const createdBeforeConnected = createdSongs.length;
                            state.presenterPreparationDrafts[connectedService.id] = '찬양 1: 모든 열방 주 볼 때까지 + 물이 바다 덮음같이';
                            await applyPresenterPreparationInput(connectedService.id);
                            const connectedInputItem = (state.serviceItems[connectedService.id] || [])
                              .find((entry) => entry.label === '찬양 1') || {};
                            const connectedInputMemo = parseServiceItemMemo(connectedInputItem.memo);
                            const regularThirdService = {
                              id: '__smoke_regular_third_leftovers__',
                              type_id: 'sunday-main',
                              date: '2026-08-02',
                            };
                            const regularThirdScaffold = buildWorshipServiceScaffold(
                              regularThirdService.id,
                              regularThirdService.type_id,
                              { service: regularThirdService }
                            );
                            const regularThirdItems = groupWorshipElements(
                              regularThirdScaffold.sections,
                              regularThirdScaffold.elements
                            )[regularThirdService.id] || [];
                            const allGenerationProjectedFromRegular = projectWorshipServiceItemsFromTemplate(
                              allGenerationService,
                              regularThirdItems
                            );
                            const allGenerationProjectedLabels = allGenerationProjectedFromRegular.map((entry) => entry.label || '');
                            const allGenerationProjectedSections = [...new Set(allGenerationProjectedFromRegular.map((entry) => entry._worshipSectionKey || ''))];
                            const allGenerationSharedMainPraiseIndex = sundaySharedContentItemIndex(
                              allGenerationItems,
                              'main-praise:3',
                              allGenerationService
                            );
                            return {
                              songIds: ['찬양 1', '찬양 2', '찬양 3', '찬양 4', '결단찬양'].map((label) => byLabel(label).song_id || ''),
                              versionIds: ['찬양 1', '찬양 2', '찬양 3'].map((label) => byLabel(label).version_id || byLabel(label).song_version_id || ''),
                              hymnVersionIds: hymnItems.map((entry) => entry.version_id || entry.song_version_id || ''),
                              hymnMissingReasons: hymnItems.map((entry) => {
                                const memo = parseServiceItemMemo(entry.memo);
                                const song = serviceItemLinkedSong(entry);
                                return resolvePresenterServiceItemContentState(entry, memo, song, hymnService).reason;
                              }),
                              rawTitleScore: {
                                songId: rawTitleScoreSong?.id || '',
                                reason: rawTitleScoreState.reason || '',
                                missingCount: rawTitleScoreSlides.filter((slide) => slide.missingContent).length,
                                slideTypes: rawTitleScoreSlides.map((slide) => slide.type || ''),
                              },
                              prayer: (byLabel('기도').assignee || byLabel('대표기도').assignee || ''),
                              reading: byLabel('성경봉독').raw_title || '',
                              sermonTitle: byLabel('설교 제목').raw_title || '',
                              shorthand: {
                                errors: shorthand.errors,
                                labels: shorthand.entries.map((entry) => entry.label),
                                contents: shorthand.entries.map((entry) => entry.content),
                                songIds: shorthandSongIds,
                              },
                              mixedNumbering: {
                                errors: mixedNumbering.errors,
                                labels: mixedNumbering.entries.map((entry) => entry.label),
                              },
                              fullscreenFallback: {
                                reading: fullscreenReading.raw_title || '',
                                sermonBodyCount: fullscreenItems.filter((entry) => entry.label === '설교 본문').length,
                                citationCount: fullscreenItems.filter(isPresenterPreparationCitationItem).length,
                                citationReferences: fullscreenCitationMemo.scriptureReferences || [],
                                citationSection: fullscreenCitation._worshipSectionKey || '',
                              },
                              looseInput: {
                                placeholder: loosePlaceholder,
                                createdTitles: createdSongs.slice(0, 4).map((song) => song.title),
                                praiseSongIds: ['찬양 1', '찬양 2', '찬양 3', '찬양 4'].map((label) => looseByLabel(label).song_id || ''),
                                prayer: (looseByLabel('기도').assignee || looseByLabel('대표기도').assignee || ''),
                                sermonTitle: looseByLabel('설교 제목').raw_title || '',
                                sermonAssignee: looseByLabel('설교 제목').assignee || '',
                                draftCleared: !state.presenterPreparationDrafts[looseService.id],
                              },
                              fridayInput: {
                                placeholder: fridayPlaceholder,
                                labels: ['찬양 1', '찬양 2', '찬양 3', '찬양 4', '찬양 5'].map((label) => fridayByLabel(label).label || ''),
                                praiseSongIds: ['찬양 1', '찬양 2', '찬양 3', '찬양 4', '찬양 5'].map((label) => fridayByLabel(label).song_id || ''),
                                entryPraiseSongIds: ['입례찬양', '기도찬양 1', '기도찬양 2'].map((label) => fridayByLabel(label).song_id || ''),
                                prayerPraiseOneRawTitle: fridayByLabel('기도찬양 1').raw_title || '',
                                prayerAssignee: fridayByLabel('대표기도').assignee || fridayByLabel('기도').assignee || '',
                                songInputs: ['주 내 소망은 주 더 알기 원합니다 G', '오직 주의 사랑에 매여 D', '내 삶의 이유라 D'].map(presenterPreparationSongContent),
                                legacyEntranceLabel: fridayLegacyItems.find((entry) => entry.label === '입례찬양')?.label || '',
                                legacyEntranceSection: fridayLegacyItems.find((entry) => entry.label === '입례찬양')?._worshipSectionKey || '',
                                legacyPrayerMeetingTitle: fridayLegacyItems.find((entry) => entry._worshipSectionKey === 'prayer_meeting_praise')?._worshipSectionTitle || '',
                                freePrayerSection: freePrayer._worshipSectionKey || '',
                                freePrayerEditable: presenterServiceInputHasEditableField(freePrayer, fridayService),
                                freePrayerMissing: freePrayerSlides.some((slide) => slide.missingContent),
                                draftCleared: !state.presenterPreparationDrafts[fridayService.id],
                              },
                              allGenerationInput: {
                                labels: allGenerationPraiseItems.map((entry) => entry.label),
                                songCount: allGenerationPraiseItems.filter((entry) => entry.song_id).length,
                                maxElementOrder: Math.max(...allGenerationPraiseItems.map((entry) => Number(entry._worshipElementOrder) || 0)),
                                projectedFromRegularSections: allGenerationProjectedSections,
                                projectedFromRegularBlockedLabels: ["입례찬양", "찬송", "사도신경", "공동체고백", "폐회찬송"]
                                  .filter((label) => allGenerationProjectedLabels.includes(label)),
                                projectedFromRegularClosingLabels: allGenerationProjectedFromRegular
                                  .filter((entry) => (entry._worshipSectionKey || '') === 'closing_visual')
                                  .map((entry) => entry.label || ''),
                                sharedMainPraiseIndex: allGenerationSharedMainPraiseIndex,
                                draftCleared: !state.presenterPreparationDrafts[allGenerationService.id],
                              },
                              connectedSongInput: {
                                rawTitle: connectedInputItem.raw_title || '',
                                songId: connectedInputItem.song_id || '',
                                versionId: connectedInputItem.version_id || connectedInputItem.song_version_id || '',
                                inputMode: connectedInputMemo.inputMode || '',
                                outputMode: connectedInputMemo.outputMode || '',
                                groupTitle: connectedInputMemo.connectedPraise?.title || '',
                                groupItemCount: (connectedInputMemo.connectedPraise?.itemIds || []).length,
                                createdDelta: createdSongs.length - createdBeforeConnected,
                                draftCleared: !state.presenterPreparationDrafts[connectedService.id],
                              },
                              citationCount: citations.length,
                              citationReferences,
                              citationRawTitle: citation.raw_title || '',
                              citationSlideCount: citationSlides.length,
                              citationSlideReferences: [...new Set(citationSlides.map((slide) => slide.title))],
                              citationQuickInsert: citationSlides.every((slide) => slide.citationQuickInsert === true),
                              citationMemoRoundTrip: citationMemoRoundTrip.scriptureReferences || [],
                              citationConfigReferences: citationConfig.scriptureReferences || [],
                              draftCleared: !state.presenterPreparationDrafts[service.id],
                            };
                          } finally {
                            state.module = original.module;
                            state.songs = original.songs;
                            state.services = original.services;
                            state.serviceItems = original.serviceItems;
                            state.client = original.client;
                            state.songVersionTablesSupported = original.songVersionTablesSupported;
                            state.selectedServiceId = original.selectedServiceId;
                            state.selectedServiceTypeId = original.selectedServiceTypeId;
                            state.presenter.viewServiceId = original.presenterViewServiceId;
                            state.calendarData = original.calendarData;
                            state.presenterPreparationDrafts = original.drafts;
                            state.dirty.service = original.dirty;
                            renderPresenterDetail();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_paste["songIds"] == [
                            "__batch_praise_1__", "__batch_praise_2__", "__batch_praise_3__", "__batch_praise_4__", "__batch_response__"
                        ]
                        and presenter_preparation_paste["versionIds"] == [
                            "__batch_praise_1_v__", "__batch_praise_2_v__", "__batch_praise_3_v__"
                        ]
                        and presenter_preparation_paste["hymnVersionIds"] == [
                            "__batch_hymn_9_v__", "__batch_hymn_288_v__", "__batch_hymn_182_v__"
                        ]
                        and presenter_preparation_paste["hymnMissingReasons"] == ["song", "song", "song"]
                        and presenter_preparation_paste["rawTitleScore"]["songId"] == "__batch_hymn_9__"
                        and presenter_preparation_paste["rawTitleScore"]["reason"] == "song"
                        and presenter_preparation_paste["rawTitleScore"]["missingCount"] == 0
                        and presenter_preparation_paste["rawTitleScore"]["slideTypes"] == ["image"]
                        and presenter_preparation_paste["prayer"] == "정선분 권사"
                        and presenter_preparation_paste["reading"] == "히브리서 10:38–39"
                        and presenter_preparation_paste["sermonTitle"] == "믿음을 잃어버릴 수도 있어요?"
                        and presenter_preparation_paste["shorthand"] == {
                            "errors": [],
                            "labels": ["찬양 1", "찬양 2", "찬양 3", "성경봉독", "설교 제목", "봉헌찬송"],
                            "contents": [
                                "하늘에 가득 찬 영광의(9장)",
                                "예수를 나의 구주 삼고(288장)",
                                "강물같이 흐르는 기쁨(182장)",
                                "요 21:15~25",
                                "베드로의 고백",
                                "찬 187장",
                            ],
                            "songIds": ["__batch_hymn_9__", "__batch_hymn_288__", "__batch_hymn_182__", "__batch_hymn_187__"],
                        }
                        and presenter_preparation_paste["mixedNumbering"] == {
                            "errors": [],
                            "labels": ["찬양 1", "찬양 3", "찬양 4"],
                        }
                        and presenter_preparation_paste["fullscreenFallback"] == {
                            "reading": "",
                            "sermonBodyCount": 1,
                            "citationCount": 1,
                            "citationReferences": ["예레미야 3:22", "마태복음 3:11", "누가복음 24:49"],
                            "citationSection": "sermon",
                        }
                        and [line.split(":")[0] for line in presenter_preparation_paste["looseInput"]["placeholder"].split("\n")] == [
                            "찬양1", "찬양2", "찬양3", "찬양4", "찬송", "대표기도", "성경봉독", "특송",
                            "설교 제목", "설교 본문", "인용구절", "봉헌찬송", "봉헌기도", "축도",
                        ]
                        and {key: value for key, value in presenter_preparation_paste["looseInput"].items() if key != "placeholder"} == {
                            "createdTitles": ["주 찬양합니다", "변찮는 주님의 사랑과", "승리는 내 것일세", "꽃들도"],
                            "praiseSongIds": ["__created_song_1__", "__created_song_2__", "__created_song_3__", "__created_song_4__"],
                            "prayer": "문병자 권사",
                            "sermonTitle": "신유란 무엇인가요?",
                            "sermonAssignee": "김남영 목사",
                            "draftCleared": True,
                        }
                        and [line.split(":")[0] for line in presenter_preparation_paste["fridayInput"]["placeholder"].split("\n")[:5]] == [
                            "찬양1", "찬양2", "찬양3", "찬양4", "찬양5"
                        ]
                        and presenter_preparation_paste["fridayInput"]["labels"] == [
                            "찬양 1", "찬양 2", "찬양 3", "찬양 4", "찬양 5"
                        ]
                        and all(presenter_preparation_paste["fridayInput"]["praiseSongIds"])
                        and all(presenter_preparation_paste["fridayInput"]["entryPraiseSongIds"])
                        and presenter_preparation_paste["fridayInput"]["prayerPraiseOneRawTitle"] == ""
                        and presenter_preparation_paste["fridayInput"]["prayerAssignee"] == ""
                        and presenter_preparation_paste["fridayInput"]["songInputs"] == [
                            "주 내 소망은 주 더 알기 원합니다", "오직 주의 사랑에 매여", "내 삶의 이유라"
                        ]
                        and presenter_preparation_paste["fridayInput"]["legacyEntranceLabel"] == "입례찬양"
                        and presenter_preparation_paste["fridayInput"]["legacyEntranceSection"] == "entrance_praise"
                        and presenter_preparation_paste["fridayInput"]["legacyPrayerMeetingTitle"] == "기도회"
                        and presenter_preparation_paste["fridayInput"]["freePrayerSection"] == "prayer_meeting_praise"
                        and presenter_preparation_paste["fridayInput"]["freePrayerEditable"] is False
                        and presenter_preparation_paste["fridayInput"]["freePrayerMissing"] is False
                        and presenter_preparation_paste["fridayInput"]["draftCleared"] is True
                        and presenter_preparation_paste["allGenerationInput"] == {
                            "labels": [f"찬양 {index}" for index in range(1, 13)],
                            "songCount": 12,
                            "maxElementOrder": 120,
                            "projectedFromRegularSections": [
                                "ready",
                                "praise",
                                "prayer",
                                "scripture_reading",
                                "special_song",
                                "sermon",
                                "response_song",
                                "offering",
                                "announcements",
                                "sending",
                                "closing_visual",
                            ],
                            "projectedFromRegularBlockedLabels": [],
                            "projectedFromRegularClosingLabels": ["마무리"],
                            "sharedMainPraiseIndex": -1,
                            "draftCleared": True,
                        }
                        and {
                            **presenter_preparation_paste["connectedSongInput"],
                            "songId": bool(presenter_preparation_paste["connectedSongInput"]["songId"]),
                            "versionId": bool(presenter_preparation_paste["connectedSongInput"]["versionId"]),
                        } == {
                            "rawTitle": "",
                            "songId": True,
                            "versionId": True,
                            "inputMode": "",
                            "outputMode": "",
                            "groupTitle": "모든 열방 주 볼 때까지 + 물이 바다 덮음같이",
                            "groupItemCount": 2,
                            "createdDelta": 2,
                            "draftCleared": True,
                        }
                        and presenter_preparation_paste["citationCount"] == 1
                        and presenter_preparation_paste["citationReferences"] == [
                            "예레미야 3:22", "마태복음 3:11", "누가복음 24:49", "사도행전 2:4", "고린도후서 10:4", "로마서 8:35–37", "데살로니가전서 4:3", "베드로전서 1:14–15",
                            "히브리서 4:12", "에베소서 5:26", "요한일서 1:7", "사도행전 15:8–9", "누가복음 11:13", "로마서 8:30", "마태복음 5:48", "로마서 13:10"
                        ]
                        and presenter_preparation_paste["citationRawTitle"] == "예레미야 3:22; 마태복음 3:11; 누가복음 24:49; 사도행전 2:4; 고린도후서 10:4; 로마서 8:35–37; 데살로니가전서 4:3; 베드로전서 1:14–15; 히브리서 4:12; 에베소서 5:26; 요한일서 1:7; 사도행전 15:8–9; 누가복음 11:13; 로마서 8:30; 마태복음 5:48; 로마서 13:10"
                        and presenter_preparation_paste["citationSlideCount"] == 20
                        and presenter_preparation_paste["citationQuickInsert"] is True
                        and len(presenter_preparation_paste["citationSlideReferences"]) == 16
                        and presenter_preparation_paste["citationSlideReferences"][:4] == [
                            "예레미야 3:22", "마태복음 3:11", "누가복음 24:49", "사도행전 2:4"
                        ]
                        and presenter_preparation_paste["citationMemoRoundTrip"] == presenter_preparation_paste["citationReferences"]
                        and presenter_preparation_paste["citationConfigReferences"] == presenter_preparation_paste["citationReferences"]
                        and presenter_preparation_paste["draftCleared"]
                    ):
                        pass_("presenter-preparation-paste", json.dumps(presenter_preparation_paste, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-paste", json.dumps(presenter_preparation_paste, ensure_ascii=False))

                    presenter_preparation_sermon_slot = page.evaluate(
                        """
                        (() => {
                          const original = {
                            module: state.module,
                            services: state.services,
                            serviceItems: state.serviceItems,
                            selectedServiceId: state.selectedServiceId,
                            selectedServiceTypeId: state.selectedServiceTypeId,
                            drafts: state.presenterPreparationDrafts,
                            dirty: state.dirty.service,
                            presenter: {
                              viewServiceId: state.presenter.viewServiceId,
                              serviceId: state.presenter.serviceId,
                              slides: state.presenter.slides,
                              index: state.presenter.index,
                              safetyBlank: state.presenter.safetyBlank,
                              jumpDraft: state.presenter.jumpDraft,
                              liveScripture: state.presenter.liveScripture,
                              livePraise: state.presenter.livePraise,
                            },
                            presenterBoardSelection: state.presenterBoardSelection,
                            presenterSectionEditor: state.presenterSectionEditor,
                          };
                          const service = { id: '__smoke_preparation_sermon_slot__', type_id: 'wednesday', date: '2026-07-15', alias: '' };
                          const sermonTitle = normalizeServiceItem({
                            id: '__smoke_sermon_title_only__',
                            service_id: service.id,
                            sort_order: 1,
                            label: '설교 제목',
                            memo: serializeServiceItemMemo({ elementType: 'title_person', inputMode: 'text' }),
                            _worshipSectionId: '__smoke_section_sermon__',
                            _worshipSectionKey: 'sermon',
                            _worshipSectionTitle: '설교',
                            _worshipSectionOrder: 6,
                            _worshipElementOrder: 1,
                          });
                          try {
                            state.module = 'home';
                            state.services = [service];
                            state.selectedServiceId = service.id;
                            state.selectedServiceTypeId = service.type_id;
                            state.serviceItems = { [service.id]: [sermonTitle] };
                            state.presenterPreparationDrafts = {
                              [service.id]: '설교 제목: 믿음을 잃어버릴 수도 있어요?',
                            };
                            applyPresenterPreparationInput(service.id);
                            const sermonItems = (state.serviceItems[service.id] || [])
                              .filter((item) => item._worshipSectionKey === 'sermon')
                              .map((item) => ({
                                label: item.label,
                                type: serviceMemoElementType(parseServiceItemMemo(item.memo)),
                                title: item.raw_title || '',
                                placeholder: Boolean(item._worshipTemplatePlaceholder),
                              }));
                            return {
                              sermonItems,
                              labels: sermonItems.map((item) => item.label),
                            };
                          } finally {
                            state.module = original.module;
                            state.services = original.services;
                            state.serviceItems = original.serviceItems;
                            state.selectedServiceId = original.selectedServiceId;
                            state.selectedServiceTypeId = original.selectedServiceTypeId;
                            state.presenterPreparationDrafts = original.drafts;
                            state.dirty.service = original.dirty;
                            state.presenter.serviceId = original.presenter.serviceId;
                            state.presenter.viewServiceId = original.presenter.viewServiceId;
                            state.presenter.slides = original.presenter.slides;
                            state.presenter.index = original.presenter.index;
                            state.presenter.safetyBlank = original.presenter.safetyBlank;
                            state.presenter.jumpDraft = original.presenter.jumpDraft;
                            state.presenter.liveScripture = original.presenter.liveScripture;
                            state.presenter.livePraise = original.presenter.livePraise;
                            state.presenterBoardSelection = original.presenterBoardSelection;
                            state.presenterSectionEditor = original.presenterSectionEditor;
                            renderPresenterDetail();
                          }
                        })()
                        """
                    )
                    if (
                        presenter_preparation_sermon_slot["labels"] == ["설교 제목", "설교 본문", "인용 구절"]
                        and presenter_preparation_sermon_slot["sermonItems"][0]["title"] == "믿음을 잃어버릴 수도 있어요?"
                    ):
                        pass_("presenter-preparation-sermon-slot", json.dumps(presenter_preparation_sermon_slot, ensure_ascii=False))
                    else:
                        fail("presenter-preparation-sermon-slot", json.dumps(presenter_preparation_sermon_slot, ensure_ascii=False))

                    page.set_viewport_size({"width": 520, "height": 760})
                    page.evaluate(
                        """
                        (serviceId) => {
                          state.module = 'presenter';
                          state.selectedServiceId = serviceId;
                          const service = state.services.find((item) => item.id === serviceId);
                          state.selectedServiceTypeId = service?.type_id || state.selectedServiceTypeId;
                          state.presenter.viewServiceId = serviceId;
                          renderPresenterDetail();
                        }
                        """,
                        service_for_slides["id"],
                    )
                    page.wait_for_selector("#servicePresenterControls", timeout=5000)
                    authoring_narrow = page.evaluate(
                        """
                        (() => {
                          const editor = document.querySelector('.presenter-viewer')?.getBoundingClientRect();
                          const editorLeft = editor?.left || 0;
                          const editorRight = editor?.right || window.innerWidth;
                          return {
                            viewport: window.innerWidth,
                            editorWidth: Math.round(editor?.width || 0),
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth),
                            editorScrollOverflow: Math.max(0, Math.round((editor?.scrollWidth || 0) - (editor?.clientWidth || 0))),
                            hasReadonly: Boolean(document.querySelector('.service-readonly-view')),
                            hasControls: Boolean(document.querySelector('#servicePresenterControls')),
                            legacyInputContextRemoved: !document.querySelector('.service-sidebar-input-context'),
                            headerControls: document.querySelectorAll('.svc-board-subgroup-controls [data-service-item-field]').length,
                            railMounted: Boolean(document.querySelector('#mindexRightSidebar .svc-presenter-input-rail')),
                            sidePanelMounted: Boolean(document.querySelector('#mindexRightSidebar .svc-presenter-side-panel')),
                            rightSidebarMounted: Boolean(document.querySelector('#mindexRightSidebar:not([hidden])')),
                            topbarToggleVisible: Boolean(document.querySelector('#presenterRightSidebarBtn:not([hidden])')),
                            saveHidden: Boolean(document.querySelector('#saveAllBtn')?.hidden),
                            saveVisible: Boolean(document.querySelector('#saveAllBtn:not([hidden])'))
                          };
                        })()
                        """
                    )
                    page.set_viewport_size({"width": 1440, "height": 980})
                    if (
                        authoring_narrow["viewport"] == 520
                        and 160 <= authoring_narrow["editorWidth"] <= authoring_narrow["viewport"]
                        and authoring_narrow["overflow"] <= 2
                        and authoring_narrow["editorScrollOverflow"] <= 2
                        and authoring_narrow["hasControls"]
                        and authoring_narrow["legacyInputContextRemoved"]
                        and authoring_narrow["headerControls"] >= 0
                        and authoring_narrow["railMounted"]
                        and authoring_narrow["sidePanelMounted"]
                        and authoring_narrow["rightSidebarMounted"]
                        and not authoring_narrow["topbarToggleVisible"]
                        and not authoring_narrow["saveHidden"]
                        and authoring_narrow["saveVisible"]
                        and not authoring_narrow["hasReadonly"]
                    ):
                        pass_("presenter-narrow", json.dumps(authoring_narrow, ensure_ascii=False))
                    else:
                        fail("presenter-narrow", json.dumps(authoring_narrow, ensure_ascii=False))

                    page.evaluate(
                        """
                        (serviceId) => {
                          state.module = 'presenter';
                          state.selectedServiceId = serviceId;
                          renderPresenterDetail();
                          renderServiceList();
                        }
                        """,
                        service_for_slides["id"],
                    )

                    thumb_metrics = page.evaluate(
                        """
                        (() => {
                          const frameMetric = (node) => {
                            const rect = node.getBoundingClientRect();
                            return {
                              left: Math.round(rect.left),
                              top: Math.round(rect.top),
                              width: Math.round(rect.width),
                              height: Math.round(rect.height),
                              ratio: rect.height ? Number((rect.width / rect.height).toFixed(3)) : 0
                            };
                          };
                          const frames = [...document.querySelectorAll('.svc-slide-thumb-frame')].map(frameMetric);
                          const grids = [...document.querySelectorAll('.svc-board-grid')].map((grid) => {
                            const gridRect = grid.getBoundingClientRect();
                            const gridFrames = [...grid.querySelectorAll('.svc-slide-thumb-frame')].map(frameMetric);
                            const rows = Object.values(gridFrames.reduce((acc, item) => {
                              const key = Object.keys(acc).find((top) => Math.abs(Number(top) - item.top) <= 2) || String(item.top);
                              acc[key] = acc[key] || [];
                              acc[key].push(item);
                              return acc;
                            }, {})).map((row) => row.sort((a, b) => a.left - b.left));
                            const row = rows.find((candidate) => candidate.length > 1) || [];
                            const horizontalGaps = row.slice(0, -1).map((item, index) => row[index + 1].left - (item.left + item.width));
                            const first = row[0] || null;
                            const last = row[row.length - 1] || null;
                            return {
                              count: gridFrames.length,
                              row,
                              horizontalGaps,
                              leftInset: first ? Math.round(first.left - gridRect.left) : 0,
                              rightInset: last ? Math.round(gridRect.right - (last.left + last.width)) : 0
                            };
                          });
                          const grid = grids
                            .filter((candidate) => candidate.horizontalGaps.length)
                            .sort((a, b) => b.row.length - a.row.length)[0] || { row: [], horizontalGaps: [], leftInset: 0, rightInset: 0 };
                          return { frames: frames.slice(0, 12), row: grid.row, horizontalGaps: grid.horizontalGaps, leftInset: grid.leftInset, rightInset: grid.rightInset };
                        })()
                        """
                    )
                    if thumb_metrics["frames"]:
                        widths = [item["width"] for item in thumb_metrics["frames"]]
                        heights = [item["height"] for item in thumb_metrics["frames"]]
                        ratios = [item["ratio"] for item in thumb_metrics["frames"]]
                        horizontal_gaps = thumb_metrics["horizontalGaps"]
                        uniform = (
                            max(widths) - min(widths) <= 2
                            and max(heights) - min(heights) <= 2
                            and all(1.75 <= ratio <= 1.79 for ratio in ratios)
                            and horizontal_gaps
                            and max(horizontal_gaps) - min(horizontal_gaps) <= 2
                            and 18 <= horizontal_gaps[0] <= 24
                            and thumb_metrics["leftInset"] <= 6
                        )
                        if uniform:
                            pass_("presenter-thumbnail-grid", json.dumps(thumb_metrics, ensure_ascii=False))
                        else:
                            fail("presenter-thumbnail-grid", json.dumps(thumb_metrics, ensure_ascii=False))

                    thumb_scripture_fit_state = page.evaluate(
                        """
                        () => {
                          const host = document.createElement('span');
                          host.className = 'svc-slide-mini-canvas presenter-output-root';
                          host.style.cssText = 'position:absolute;left:-10000px;top:0;width:1920px;height:1080px;display:grid;place-items:center;';
                          host.innerHTML = renderPresenterSlideFrame({
                            id: '__smoke_thumb_scripture_fit__',
                            type: 'scripture',
                            layout: 'lower_bar_text',
                            elementType: 'scripture_text',
                            label: '성경봉독',
                            title: '느헤미야 6:15–19; 느헤미야 7:1–5',
                            text: '느헤미야 6:15–19; 느헤미야 7:1–5',
                          }, { previewStage: true });
                          document.body.appendChild(host);
                          applyPresenterPreviewScales(document);
                          fitPresenterChromakeyScriptureText(host);
                          const box = host.querySelector('.presenter-slide--scripture > .presenter-slide-text');
                          const line = box?.querySelector('span');
                          const naturalWidth = line ? presenterTextNaturalWidth(line) : 0;
                          const limit = box ? box.clientWidth : 0;
                          const fontSize = box ? Number.parseFloat(getComputedStyle(box).fontSize || '0') : 0;
                          const fittedSize = box?.style.getPropertyValue('--presenter-scripture-fitted-size') || '';
                          host.remove();
                          return { naturalWidth, limit, fontSize, fittedSize };
                        }
                        """
                    )
                    if (
                        thumb_scripture_fit_state["naturalWidth"] > 0
                        and thumb_scripture_fit_state["limit"] > 0
                        and thumb_scripture_fit_state["naturalWidth"] <= thumb_scripture_fit_state["limit"] + 1
                        and thumb_scripture_fit_state["fontSize"] >= 28
                        and thumb_scripture_fit_state["fittedSize"]
                    ):
                        pass_("presenter-thumbnail-scripture-fit", json.dumps(thumb_scripture_fit_state, ensure_ascii=False))
                    else:
                        fail("presenter-thumbnail-scripture-fit", json.dumps(thumb_scripture_fit_state, ensure_ascii=False))

                    thumb_zoom_state = page.evaluate(
                        """
                        async () => {
                          const sample = () => {
                            const frames = [...document.querySelectorAll('.svc-slide-thumb-frame')].slice(0, 10);
                            return frames.map((frame) => {
                              const rect = frame.getBoundingClientRect();
                              const canvas = frame.querySelector('.svc-slide-mini-canvas');
                              const canvasStyle = canvas ? getComputedStyle(canvas) : null;
                              return {
                                width: Number(rect.width.toFixed(2)),
                                height: Number(rect.height.toFixed(2)),
                                transform: canvasStyle?.transform || '',
                              };
                            });
                          };
                          const before = sample();
                          document.documentElement.style.zoom = '125%';
                          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                          const zoomed = sample();
                          await new Promise((resolve) => setTimeout(resolve, 80));
                          const zoomedLater = sample();
                          document.documentElement.style.zoom = '';
                          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                          const restored = sample();
                          return { before, zoomed, zoomedLater, restored };
                        }
                        """
                    )
                    if thumb_zoom_state["before"]:
                        zoom_width_drift = max(
                            abs(item["width"] - thumb_zoom_state["zoomed"][index]["width"])
                            for index, item in enumerate(thumb_zoom_state["zoomedLater"])
                        )
                        restore_width_drift = max(
                            abs(item["width"] - thumb_zoom_state["restored"][index]["width"])
                            for index, item in enumerate(thumb_zoom_state["before"])
                        )
                        transforms_stable = all(
                            item["transform"] == thumb_zoom_state["zoomedLater"][index]["transform"]
                            for index, item in enumerate(thumb_zoom_state["zoomed"])
                        )
                        if zoom_width_drift <= 1 and restore_width_drift <= 1 and transforms_stable:
                            pass_("presenter-thumbnail-zoom-stability", json.dumps(thumb_zoom_state, ensure_ascii=False))
                        else:
                            fail("presenter-thumbnail-zoom-stability", json.dumps(thumb_zoom_state, ensure_ascii=False))

                    thumb_hover_state = page.evaluate(
                        """
                        () => {
                          const frame = document.querySelector('.svc-slide-thumb-frame');
                          const number = frame?.closest('.svc-slide-thumb-wrap')?.querySelector('.svc-slide-thumb-no');
                          const canvas = frame?.querySelector('.svc-slide-mini-canvas');
                          if (!frame || !canvas) return null;
                          const rect = frame.getBoundingClientRect();
                          const numberStyle = number ? getComputedStyle(number) : null;
                          const hoverOverlayStyle = getComputedStyle(frame, '::after');
                          return {
                            width: Number(rect.width.toFixed(2)),
                            height: Number(rect.height.toFixed(2)),
                            transform: getComputedStyle(canvas).transform || '',
                            numberColor: numberStyle?.color || '',
                            numberWeight: numberStyle?.fontWeight || '',
                            hoverOverlayOpacity: Number.parseFloat(hoverOverlayStyle.opacity || '0') || 0,
                          };
                        }
                        """
                    )
                    if thumb_hover_state:
                        page.evaluate(
                            """
                            () => document.querySelector('[data-unsaved-action="discard"]')?.click()
                            """
                        )
                        page.hover(".svc-slide-thumb[data-presenter-index][data-service-id]")
                        page.wait_for_timeout(80)
                        thumb_hover_later = page.evaluate(
                            """
                            () => {
                              const frame = document.querySelector('.svc-slide-thumb-frame');
                              const number = frame?.closest('.svc-slide-thumb-wrap')?.querySelector('.svc-slide-thumb-no');
                              const canvas = frame?.querySelector('.svc-slide-mini-canvas');
                              if (!frame || !canvas) return null;
                              const rect = frame.getBoundingClientRect();
                              const numberStyle = number ? getComputedStyle(number) : null;
                              const hoverOverlayStyle = getComputedStyle(frame, '::after');
                              return {
                                width: Number(rect.width.toFixed(2)),
                                height: Number(rect.height.toFixed(2)),
                                transform: getComputedStyle(canvas).transform || '',
                                outline: getComputedStyle(frame).outlineStyle,
                                numberColor: numberStyle?.color || '',
                                numberWeight: numberStyle?.fontWeight || '',
                                hoverOverlayOpacity: Number.parseFloat(hoverOverlayStyle.opacity || '0') || 0,
                              };
                            }
                            """
                        )
                        hover_stable = (
                            thumb_hover_later
                            and abs(thumb_hover_state["width"] - thumb_hover_later["width"]) <= 1
                            and abs(thumb_hover_state["height"] - thumb_hover_later["height"]) <= 1
                            and thumb_hover_state["transform"] == thumb_hover_later["transform"]
                            and thumb_hover_state["numberColor"] == thumb_hover_later["numberColor"]
                            and thumb_hover_state["numberWeight"] == thumb_hover_later["numberWeight"]
                            and thumb_hover_state["hoverOverlayOpacity"] <= 0.01
                            and thumb_hover_later["hoverOverlayOpacity"] >= 0.5
                        )
                        if hover_stable:
                            pass_("presenter-thumbnail-hover-stability", json.dumps({
                                "before": thumb_hover_state,
                                "after": thumb_hover_later,
                            }, ensure_ascii=False))
                        else:
                            fail("presenter-thumbnail-hover-stability", json.dumps({
                                "before": thumb_hover_state,
                                "after": thumb_hover_later,
                            }, ensure_ascii=False))
                    page.mouse.move(1430, 10)
                    page.evaluate(
                        """
                        (serviceId) => {
                          preparePresenterService(serviceId);
                          state.presenter.outputConnectedAt = Date.now();
                          renderPresenterControlState(serviceId);
                        }
                        """,
                        service_for_slides["id"],
                    )
                    page.wait_for_function(
                        "() => document.querySelectorAll('.svc-slide-thumb-wrap.active').length === 1",
                        timeout=5000,
                    )
                    active_ring_state = page.evaluate(
                        """
                        (() => {
                          const wrap = document.querySelector('.svc-slide-thumb-wrap.active');
                          const thumb = wrap?.querySelector('.svc-slide-thumb');
                          const frame = wrap?.querySelector('.svc-slide-thumb-frame');
                          if (!wrap || !thumb || !frame) return { hasActiveWrap: false };
                          const wrapRect = wrap.getBoundingClientRect();
                          const thumbRect = thumb.getBoundingClientRect();
                          const frameRect = frame.getBoundingClientRect();
                          const ring = Number.parseFloat(getComputedStyle(wrap).getPropertyValue('--svc-thumb-ring-space')) || 0;
                          const activeRing = getComputedStyle(thumb, '::after');
                          return {
                            hasActiveWrap: true,
                            ring,
                            leftInset: Number((frameRect.left - wrapRect.left).toFixed(2)),
                            topInset: Number((frameRect.top - wrapRect.top).toFixed(2)),
                            rightInset: Number((wrapRect.right - frameRect.right).toFixed(2)),
                            bottomInset: Number((wrapRect.bottom - frameRect.bottom).toFixed(2)),
                            wrapWidth: Math.round(wrapRect.width),
                            wrapHeight: Math.round(wrapRect.height),
                            thumbHeight: Math.round(thumbRect.height),
                            frameWidth: Math.round(frameRect.width),
                            frameHeight: Math.round(frameRect.height),
                            activeRingBorder: activeRing.borderTopStyle,
                            activeRingBorderWidth: Number.parseFloat(activeRing.borderTopWidth) || 0,
                            activeFrameShadow: getComputedStyle(frame).boxShadow,
                            activeFrameOutline: getComputedStyle(frame).outlineStyle,
                          };
                        })()
                        """
                    )
                    if (
                        active_ring_state.get("hasActiveWrap")
                        and active_ring_state.get("ring", 0) >= 3
                        and min(
                            active_ring_state.get("leftInset", 0),
                            active_ring_state.get("topInset", 0),
                            active_ring_state.get("rightInset", 0),
                            active_ring_state.get("bottomInset", 0),
                        ) >= active_ring_state.get("ring", 0) - 1
                        and active_ring_state.get("activeRingBorder") == "solid"
                        and active_ring_state.get("activeRingBorderWidth", 0) >= 1
                        and active_ring_state.get("activeFrameOutline") in ("none", "")
                        and active_ring_state.get("thumbHeight", 0) <= active_ring_state.get("frameHeight", 0) + 1
                        and active_ring_state.get("wrapHeight", 0) > active_ring_state.get("thumbHeight", 0) + 12
                    ):
                        pass_("presenter-active-ring-box", json.dumps(active_ring_state, ensure_ascii=False))
                    else:
                        fail("presenter-active-ring-box", json.dumps(active_ring_state, ensure_ascii=False))
                    form_label_state = page.evaluate(
                        """
                        (serviceId) => {
                          const slides = buildServicePresenterSlides(serviceId);
                          const badges = [...document.querySelectorAll('.svc-slide-form-badge')]
                            .map((node) => {
                              const thumb = node.closest('.svc-slide-thumb-wrap')?.querySelector('.svc-slide-thumb');
                              return {
                                index: Number(thumb?.dataset.presenterIndex),
                                label: node.textContent.trim()
                              };
                            })
                            .filter((item) => Number.isFinite(item.index));
                          const continuationBadges = badges.filter((item) => {
                            const slide = slides[item.index];
                            const previous = slides[item.index - 1];
                            return slide
                              && previous
                              && slide.elementType === 'praise'
                              && previous.elementType === 'praise'
                              && slide.formKey
                              && slide.formKey === previous.formKey;
                          });
                          return {
                            heads: badges.length,
                            dividers: document.querySelectorAll('.svc-slide-form-divider').length,
                            labels: badges.slice(0, 6).map((item) => item.label),
                            continuationBadges
                          };
                        }
                        """,
                        service_for_slides["id"],
                    )
                    if (
                        all(form_label_state["labels"])
                        and form_label_state["dividers"] == 0
                        and not form_label_state["continuationBadges"]
                    ):
                        pass_("presenter-form-labels", json.dumps(form_label_state, ensure_ascii=False))
                    else:
                        fail("presenter-form-labels", json.dumps(form_label_state, ensure_ascii=False))
                    if service_for_slides["slides"] > 1:
                        page.click(f'[data-presenter-action="next"][data-service-id="{service_for_slides["id"]}"]')
                        next_state = page.evaluate(
                            """
                            (() => ({
                              serviceId: state.presenter.serviceId,
                              index: state.presenter.index,
                              slides: state.presenter.slides.length
                            }))()
                            """
                        )
                        if next_state["serviceId"] == service_for_slides["id"] and next_state["index"] == 1:
                            pass_("presenter-next-control", json.dumps(next_state, ensure_ascii=False))
                        else:
                            fail("presenter-next-control", json.dumps(next_state, ensure_ascii=False))

                        jump_target = min(service_for_slides["slides"], 3)
                        jump_input = page.locator(f'[data-presenter-jump-input][data-service-id="{service_for_slides["id"]}"]')
                        jump_input.fill(str(jump_target))
                        jump_input.press("Enter")
                        page.wait_for_function("(target) => state.presenter.index === target", arg=jump_target - 1, timeout=5000)
                        jump_state = page.evaluate(
                            """
                            (() => ({
                              serviceId: state.presenter.serviceId,
                              index: state.presenter.index,
                              draft: state.presenter.jumpDraft
                            }))()
                            """
                        )
                        if jump_state["serviceId"] == service_for_slides["id"] and jump_state["index"] == jump_target - 1 and not jump_state["draft"]:
                            pass_("presenter-jump-control", json.dumps(jump_state, ensure_ascii=False))
                        else:
                            fail("presenter-jump-control", json.dumps(jump_state, ensure_ascii=False))

                        dbl_target = min(service_for_slides["slides"] - 1, 4)
                        page.evaluate(
	                        """
	                        (() => {
	                          window.__mindexPresenterOpenCalls = 0;
                              state.presenter.outputWindow = null;
                              state.presenter.outputConnectedAt = 0;
	                          window.open = () => {
                                window.__mindexPresenterOpenCalls += 1;
                                return {
                                  closed: false,
                                  focus() {},
                                  addEventListener() {},
                                  moveTo() {},
                                  resizeTo() {},
                                  document: {
                                    documentElement: {
                                      requestFullscreen() { return Promise.resolve(); }
                                    }
                                  }
                                };
                              };
                            })()
                            """
                        )
                        page.locator(
                            f'.svc-slide-thumb[data-service-id="{service_for_slides["id"]}"][data-presenter-index="{dbl_target}"]'
                        ).dblclick()
                        page.wait_for_function("() => (window.__mindexPresenterOpenCalls || 0) === 1", timeout=5000)
                        dbl_state = page.evaluate(
                            """
                            (() => ({
                              serviceId: state.presenter.serviceId,
                              index: state.presenter.index,
                              openCalls: window.__mindexPresenterOpenCalls || 0,
                              selected: document.querySelectorAll('.svc-slide-thumb.selected').length,
                            }))()
                            """
                        )
                        if (
                            dbl_state["serviceId"] == service_for_slides["id"]
                            and dbl_state["index"] == dbl_target
                            and dbl_state["openCalls"] == 1
                        ):
                            pass_("presenter-doubleclick-starts-output", json.dumps(dbl_state, ensure_ascii=False))
                        else:
                            fail("presenter-doubleclick-starts-output", json.dumps(dbl_state, ensure_ascii=False))

                        hierarchy_state = page.evaluate(
                            """
                            (() => {
                              const groups = [...document.querySelectorAll('.service-outline-list > .service-outline-group')];
                              return {
                                standaloneRows: document.querySelectorAll('.service-outline-list > .service-outline-row:not(.service-outline-row--ready)').length,
                                sections: groups.map((group) => group.querySelector('.service-outline-row--section strong')?.textContent.trim() || ''),
                                elements: groups.map((group) => [...group.querySelectorAll('.service-outline-row--child .service-outline-kind')]
                                  .map((node) => node.textContent.trim())),
                                visibleOrderNumbers: [...document.querySelectorAll('.service-outline-no')]
                                  .map((node) => node.textContent.trim())
                                  .filter(Boolean),
                                labelOnlyBodyTexts: [...document.querySelectorAll('.service-outline-row--child')]
                                  .filter((row) => row.querySelector('.service-outline-kind') && !row.querySelector('strong'))
                                  .map((row) => row.querySelector('.service-outline-kind')?.textContent.trim() || ''),
                                emptySections: groups.filter((group) => !group.querySelector('.service-outline-row--section strong')?.textContent.trim()).length,
                              };
                            })()
                            """
                        )
                        if (
                            hierarchy_state["standaloneRows"] == 0
                            and hierarchy_state["sections"]
                            and not hierarchy_state["emptySections"]
                            and not hierarchy_state["visibleOrderNumbers"]
                            and all(elements for elements in hierarchy_state["elements"])
                            and hierarchy_state["labelOnlyBodyTexts"]
                        ):
                            pass_("presenter-sidebar-section-element-hierarchy", json.dumps(hierarchy_state, ensure_ascii=False))
                        else:
                            fail("presenter-sidebar-section-element-hierarchy", json.dumps(hierarchy_state, ensure_ascii=False))

                        page.evaluate(
                            """
                            (serviceId) => {
                              preparePresenterService(serviceId);
                              state.presenter.outputWindow = { closed: false, focus() {}, close() {} };
                              state.presenter.outputConnectedAt = Date.now();
                            }
                            """,
                            service_for_slides["id"],
                        )
                        passive_target = 0 if dbl_target != 0 else 1
                        page.locator(
                            f'.svc-slide-thumb[data-service-id="{service_for_slides["id"]}"][data-presenter-index="{passive_target}"]'
                        ).click()
                        passive_board_state = page.evaluate(
                            """
                            (selectedIndex) => ({
                              index: state.presenter.index,
                              selectedIndex,
                              outputIndex: (readPresenterStoredPayload() || {}).index,
                              selectedThumbs: [...document.querySelectorAll('.svc-slide-thumb.selected')]
                                .map((node) => Number(node.dataset.presenterIndex)),
                            })
                            """,
                            passive_target,
                        )
                        outline_target = page.locator(
                            f'.service-outline-row[data-service-outline-slide="{passive_target}"]:not([disabled])'
                        ).first
                        if outline_target.count():
                            outline_target.click()
                            passive_sidebar_state = page.evaluate(
                                """
                                (selectedIndex) => ({
                                  index: state.presenter.index,
                                  selectedIndex,
                                  outputIndex: (readPresenterStoredPayload() || {}).index,
                                  selectedRows: document.querySelectorAll('.service-outline-row.selected').length,
                                  selectedThumbs: [...document.querySelectorAll('.svc-slide-thumb.selected')]
                                    .map((node) => Number(node.dataset.presenterIndex)),
                                })
                                """,
                                passive_target,
                            )
                        else:
                            passive_sidebar_state = {"index": -1, "outputIndex": -1, "selectedRows": 0}
                        if (
                            passive_board_state["index"] == passive_target
                            and passive_board_state["outputIndex"] == passive_target
                            and passive_sidebar_state["index"] == passive_target
                            and passive_sidebar_state["outputIndex"] == passive_target
                            and passive_sidebar_state["selectedRows"] >= 1
                        ):
                            pass_("presenter-live-click-transitions-output", json.dumps({
                                "board": passive_board_state,
                                "sidebar": passive_sidebar_state,
                                "selectedIndex": passive_target,
                            }, ensure_ascii=False))
                        else:
                            fail("presenter-live-click-transitions-output", json.dumps({
                                "board": passive_board_state,
                                "sidebar": passive_sidebar_state,
                            }, ensure_ascii=False))

                    overflow_state = page.evaluate(
                        """
                        (() => {
                          const root = document.documentElement;
                          const body = document.body;
                          const board = document.querySelector('.svc-slide-board');
                          return {
                            viewport: window.innerWidth,
                            documentScrollWidth: root.scrollWidth,
                            bodyScrollWidth: body.scrollWidth,
                            boardScrollWidth: board?.scrollWidth || 0,
                            boardClientWidth: board?.clientWidth || 0
                          };
                        })()
                        """
                    )
                    const_overflow = max(
                        overflow_state["documentScrollWidth"] - overflow_state["viewport"],
                        overflow_state["bodyScrollWidth"] - overflow_state["viewport"],
                        overflow_state["boardScrollWidth"] - overflow_state["boardClientWidth"],
                    )
                    if const_overflow <= 2:
                        pass_("presenter-horizontal-overflow", json.dumps(overflow_state, ensure_ascii=False))
                    else:
                        fail("presenter-horizontal-overflow", json.dumps(overflow_state, ensure_ascii=False))

                cleanup_presenter_fixture(page)

                page.evaluate(
                    """
                    async () => {
                      if (typeof clearDirtyState === 'function') clearDirtyState();
                      if (document.body.dataset.module === 'praise') return;
                      if (typeof switchModule === 'function') await switchModule('praise', { syncHistory: false });
                    }
                    """
                )
                page.wait_for_function("() => document.body.dataset.module === 'praise'", timeout=5000)
                wait_for_praise_data(page)
                wait_for_module_data(page, "praise")
                praise_placeholder = page.input_value("#searchInput")
                placeholder = page.get_attribute("#searchInput", "placeholder") or ""
                if placeholder == "검색...":
                    pass_("praise-module-placeholder", placeholder)
                else:
                    fail("praise-module-placeholder", placeholder or praise_placeholder)
                page.wait_for_selector("[data-song-id]", state="attached", timeout=5000)
                praise_filter_state = page.evaluate(
                    """
                    (() => {
                      const originalSongs = state.songs;
                      const originalFilter = state.praiseFilter;
                      const originalSearch = state.search;
                      const originalSelectedSongId = state.selectedSongId;
                      const originalSelectedVersionId = state.selectedVersionId;
                      const originalSongList = refs.songList.innerHTML;
                      const fixtures = [
                        {
                          id: '__filter_empty__',
                          title: '빈곡 테스트',
                          versions: [{ id: '__filter_empty_v__', name: 'Default', forms: [] }]
                        },
                        {
                          id: '__filter_pink__',
                          title: '분홍 검토 테스트',
                          versions: [
                            {
                              id: '__filter_pink_v1__',
                              name: 'Default',
                              forms: [{ id: '__filter_pink_f1__', part_type: 'Verse', lyrics: '가사', review_status: 'needs_review' }]
                            },
                            {
                              id: '__filter_pink_v2__',
                              name: 'Alt',
                              forms: [{ id: '__filter_pink_f2__', part_type: 'Verse', lyrics: '가사', review_status: 'needs_review' }]
                            }
                          ]
                        },
                        {
                          id: '__filter_blue__',
                          title: '파랑 검토 테스트',
                          versions: [{
                            id: '__filter_blue_v__',
                            name: 'Default',
                            forms: [{ id: '__filter_blue_f__', part_type: 'Verse', lyrics: '가사', review_status: 'needs_review' }]
                          }]
                        },
                        {
                          id: '__filter_yellow_empty__',
                          title: '노랑 일부 빈곡 테스트',
                          versions: [
                            { id: '__filter_yellow_v1__', name: 'Default', forms: [{ id: '__filter_yellow_f1__', part_type: 'Verse', lyrics: '가사' }] },
                            { id: '__filter_yellow_v2__', name: 'Alt', forms: [] }
                          ]
                        },
                        {
                          id: '__filter_clean__',
                          title: '정상 테스트',
                          versions: [{ id: '__filter_clean_v__', name: 'Default', forms: [{ id: '__filter_clean_f__', part_type: 'Verse', lyrics: '가사' }] }]
                        }
                      ];
                      state.songs = fixtures;
                      state.search = '';
                      state.selectedSongId = null;
                      state.selectedVersionId = null;
                      const results = {};
                      for (const filter of ['empty', 'review']) {
                        state.praiseFilter = filter;
                        results[filter] = getSongsForPraiseFilter().map((song) => song.id);
                      }
                      const aliases = {
                        allReview: normalizePraiseListFilterKey('all-review'),
                        pink: normalizePraiseListFilterKey('attention-pink'),
                        blue: normalizePraiseListFilterKey('attention-blue'),
                        yellow: normalizePraiseListFilterKey('attention-yellow'),
                      };
                      renderListFilter();
                      const filterButtons = [...document.querySelectorAll('[data-list-filter]:not([hidden])')]
                        .map((button) => ({ key: button.dataset.listFilter, label: button.textContent.trim() }));
                      state.songs = originalSongs;
                      state.praiseFilter = originalFilter;
                      state.search = originalSearch;
                      state.selectedSongId = originalSelectedSongId;
                      state.selectedVersionId = originalSelectedVersionId;
                      refs.songList.innerHTML = originalSongList;
                      renderListFilter();
                      return { results, aliases, filterButtons };
                    })()
                    """
                )
                if (
                    praise_filter_state["results"]["empty"] == ["__filter_empty__"]
                    and praise_filter_state["results"]["review"] == ["__filter_pink__", "__filter_blue__", "__filter_yellow_empty__"]
                    and praise_filter_state["aliases"] == {
                        "allReview": "review",
                        "pink": "review",
                        "blue": "review",
                        "yellow": "review",
                    }
                    and [item["key"] for item in praise_filter_state["filterButtons"]] == [
                        "all",
                        "empty",
                        "review",
                        "hymns",
                        "ccm",
                        "children",
                    ]
                    and [item["label"] for item in praise_filter_state["filterButtons"]] == [
                        "전체",
                        "빈 곡",
                        "검토 필요",
                        "찬송가",
                        "CCM",
                        "어린이",
                    ]
                ):
                    pass_("praise-status-filters", json.dumps(praise_filter_state, ensure_ascii=False))
                else:
                    fail("praise-status-filters", json.dumps(praise_filter_state, ensure_ascii=False))
                page.evaluate(
                    """
                    () => document.querySelector('[data-song-id]')?.click()
                    """
                )
                page.wait_for_selector(".version-compare-title", state="attached", timeout=5000)
                praise_actions = page.evaluate(
                    """
                    (() => {
                      const heads = [...document.querySelectorAll('.version-compare-title:not(.linked-version-title)')];
                      const linkedHeads = [...document.querySelectorAll('.version-compare-title.linked-version-title')];
                      const versionCopyButtons = [...document.querySelectorAll('.version-copy-btn[data-copy-action="plain"][data-version-id]')];
                      const versionDuplicateButtons = [...document.querySelectorAll('.version-add-btn[data-add-version]')];
                      const draft = buildNewPraiseSongDraft({ title: '테스트 새 찬양', praiseTypes: ['ccm'] });
                      const emptyNewDraft = buildNewPraiseSongDraft({ title: '새 찬양', praiseTypes: ['ccm'] });
                      const nonEmptyNewDraft = {
                        ...emptyNewDraft,
                        versions: [{
                          ...emptyNewDraft.versions[0],
                          forms: [{ part_type: 'Lyrics', lyrics: '이미 입력된 가사', sort_order: 1 }]
                        }]
                      };
                      const renamedEmptyShell = buildNewPraiseSongDraft({ title: '날 구원하신 주 감사', praiseTypes: ['ccm'] });
                      const originalSongs = state.songs;
                      const originalSelectedSongId = state.selectedSongId;
                      const originalSelectedVersionId = state.selectedVersionId;
                      const originalForms = state.forms;
                      const originalDirty = { ...state.dirty };
                      const originalLoading = state.loading;
                      const primary = {
                        id: '__smoke_link_primary__',
                        title: '링크 원곡',
                        metadata: {
                          artist: '길고 긴 아티스트 이름과 예배팀 이름',
                          lyricist: '아주 긴 작사자 이름과 공동 작사자 목록',
                          composer: '아주 긴 작곡자 이름과 공동 작곡자 목록',
                          album: '잘리지 않아야 하는 긴 앨범 메타데이터',
                        },
                        related_song_ids: ['__smoke_link_related__'],
                        versions: [{
                          id: '__smoke_link_primary_v1__',
                          name: 'Default',
                          is_primary: true,
                          forms: [{ id: '__smoke_link_primary_f1__', part_type: 'Lyrics', lyrics: '원곡 가사', sort_order: 1 }]
                        }]
                      };
                      const related = {
                        id: '__smoke_link_related__',
                        title: '링크된 곡',
                        related_song_ids: [],
                        versions: [{
                          id: '__smoke_link_related_v1__',
                          name: 'Default',
                          is_primary: true,
                          forms: [{ id: '__smoke_link_related_f1__', part_type: 'Lyrics', lyrics: '링크 가사', sort_order: 1 }]
                        }]
                      };
                      state.songs = [primary, related, ...originalSongs];
                      state.selectedSongId = primary.id;
                      state.selectedVersionId = primary.versions[0].id;
                      state.forms = normalizeForms(primary.versions[0].forms.map((form) => ({ ...form, song_id: primary.versions[0].id })));
                      renderDetail();
                      const metaStrong = document.querySelector('.song-description-meta--head .meta-attribute strong');
                      const metaWrapStyle = metaStrong ? getComputedStyle(metaStrong) : null;
                      const metaHead = document.querySelector('.song-description-meta--head');
                      const metaHeadStyle = metaHead ? getComputedStyle(metaHead) : null;
                      const metaItems = [...document.querySelectorAll('.song-description-meta--head .meta-attribute')].map((node) => ({
                        label: node.querySelector('.meta-attribute-label')?.textContent.trim() || '',
                        value: node.querySelector('strong')?.textContent.trim() || '',
                      }));
                      const metaSeparator = metaStrong
                        ? getComputedStyle(metaStrong.closest('.meta-attribute'), '::after').content
                        : '';
                      const linkedEntries = linkedSongVersionEntries(primary);
                      const linkedHtml = renderFormsTab(primary);
                      const titleHtml = renderVersionTitleContent(primary, primary.versions[0], primary.versions[0].forms, { active: true });
                      updateVersionNameField({
                        dataset: { versionNameField: primary.versions[0].id },
                        value: '수정 버전'
                      });
                      const editedVersion = { ...primary.versions[0] };
                      state.loading = true;
                      syncPraiseCreateControls();
                      const loadingCreateState = {
                        canCreate: canCreatePraiseSong(),
                        topbarHidden: refs.newSongBtn.hidden,
                        topbarDisabled: refs.newSongBtn.disabled,
                        sidebarExists: Boolean(document.querySelector('.sidebar-create-song-btn[data-create-song]')),
                        detailButtonsHidden: [...document.querySelectorAll('.praise-create-btn[data-create-song], .praise-empty-create-btn[data-create-song]')]
                          .every((button) => button.hidden && button.disabled)
                      };
                      state.songs = originalSongs;
                      state.selectedSongId = originalSelectedSongId;
                      state.selectedVersionId = originalSelectedVersionId;
                      state.forms = originalForms;
                      state.dirty = originalDirty;
                      state.loading = originalLoading;
                      syncPraiseCreateControls();
                      updateSaveState();
                      return {
                        heads: heads.length,
                        linkedHeads: linkedHeads.length,
                        versionCopyButtons: versionCopyButtons.length,
                        versionDuplicateButtons: versionDuplicateButtons.length,
                        createButtons: document.querySelectorAll('[data-create-song]').length,
                        deleteButtons: document.querySelectorAll('[data-delete-song]').length,
                        deleteInMetaRow: Boolean(document.querySelector('.song-header-meta-row [data-delete-song]')),
                        deleteInHeadActions: Boolean(document.querySelector('.head-actions [data-delete-song]')),
                        deleteButtonText: document.querySelector('[data-delete-song]')?.textContent.trim() || '',
                        deleteButtonWidth: Math.round(document.querySelector('[data-delete-song]')?.getBoundingClientRect().width || 0),
                        createButtonText: document.querySelector('.praise-create-btn[data-create-song]')?.textContent.trim() || '',
                        createButtonAria: document.querySelector('.praise-create-btn[data-create-song]')?.getAttribute('aria-label') || '',
                        createButtonWidth: Math.round(document.querySelector('.praise-create-btn[data-create-song]')?.getBoundingClientRect().width || 0),
                        createButtonBg: getComputedStyle(document.querySelector('.praise-create-btn[data-create-song]')).backgroundColor,
                        createButtonColor: getComputedStyle(document.querySelector('.praise-create-btn[data-create-song]')).color,
                        sidebarCreateButtonExists: Boolean(document.querySelector('.sidebar-create-song-btn[data-create-song]')),
                        addVersionAria: document.querySelector('.version-add-btn[data-add-version]')?.getAttribute('aria-label') || '',
                        copyVersionAria: document.querySelector('.version-copy-btn[data-copy-action="plain"]')?.getAttribute('aria-label') || '',
                        versionNameInputs: document.querySelectorAll('[data-version-name-field]').length,
                        versionTitleHasInput: titleHtml.includes('data-version-name-field="__smoke_link_primary_v1__"'),
                        editedVersionName: editedVersion.name,
                        editedVersionRawName: editedVersion.raw_section_name,
                        loadingCreateState,
                        metadataWrap: {
                          exists: Boolean(metaStrong),
                          labels: metaItems.map((item) => item.label),
                          values: metaItems.map((item) => item.value),
                          whiteSpace: metaWrapStyle?.whiteSpace || '',
                          overflow: metaWrapStyle?.overflow || '',
                          textOverflow: metaWrapStyle?.textOverflow || '',
                          headFlexWrap: metaHeadStyle?.flexWrap || '',
                          headOverflow: metaHeadStyle?.overflow || '',
                          separator: metaSeparator,
                        },
                        draftTitle: draft.title,
                        draftVersions: draft.versions.length,
                        draftPraiseType: draft.versions[0]?.praise_types?.[0] || '',
                        emptyNewDraftDeletable: canDeletePraiseSong(emptyNewDraft),
                        nonEmptyNewDraftDeletable: canDeletePraiseSong(nonEmptyNewDraft),
                        renamedEmptyShellDeletable: canDeletePraiseSong(renamedEmptyShell),
                        linkedEntries: linkedEntries.length,
                        linkedReadonly: linkedHtml.includes('linked-version-column')
                          && linkedHtml.includes('data-open-song="__smoke_link_related__"')
                          && linkedHtml.includes('링크 가사'),
                        linkedEditableLeak: linkedHtml.includes('data-version-id="__smoke_link_related_v1__"')
                          || linkedHtml.includes('data-source-version-id="__smoke_link_related_v1__"'),
                        downloadShowButtons: document.querySelectorAll('[data-copy-action="download-freeshow"]').length,
                        downloadXmlButtons: document.querySelectorAll('[data-copy-action="download-xml"]').length,
                        toolbarCopyStack: document.querySelectorAll('.form-toolbar .copy-actions').length,
                        firstHeadActions: [...(heads[0]?.querySelectorAll('.version-title-actions button') || [])]
                          .map((button) => button.className)
                      };
                    })()
                    """
                )
                if (
                    praise_actions["heads"] > 0
                    and praise_actions["versionCopyButtons"] == praise_actions["heads"]
                    and praise_actions["versionDuplicateButtons"] == praise_actions["heads"]
                    and praise_actions["createButtons"] >= 1
                    and praise_actions["deleteButtons"] >= 1
                    and praise_actions["deleteInMetaRow"]
                    and not praise_actions["deleteInHeadActions"]
                    and praise_actions["deleteButtonText"] == "삭제"
                    and praise_actions["deleteButtonWidth"] >= 50
                    and praise_actions["createButtonText"] == ""
                    and praise_actions["createButtonAria"] == "곡 추가"
                    and praise_actions["createButtonWidth"] <= 32
                    and praise_actions["createButtonBg"] == "rgba(0, 0, 0, 0)"
                    and praise_actions["createButtonColor"] != "rgb(255, 126, 193)"
                    and not praise_actions["sidebarCreateButtonExists"]
                    and praise_actions["addVersionAria"] == "이 버전으로 새 버전 추가"
                    and praise_actions["copyVersionAria"] == "이 버전 가사 복사"
                    and praise_actions["versionNameInputs"] >= 1
                    and praise_actions["versionTitleHasInput"]
                    and praise_actions["editedVersionName"] == "수정 버전"
                    and praise_actions["editedVersionRawName"] == "수정 버전"
                    and not praise_actions["loadingCreateState"]["canCreate"]
                    and praise_actions["loadingCreateState"]["topbarHidden"]
                    and praise_actions["loadingCreateState"]["topbarDisabled"]
                    and not praise_actions["loadingCreateState"]["sidebarExists"]
                    and praise_actions["loadingCreateState"]["detailButtonsHidden"]
                    and praise_actions["metadataWrap"]["exists"]
                    and praise_actions["metadataWrap"]["labels"][:2] == ["아티스트", "앨범"]
                    and "아티스트" in praise_actions["metadataWrap"]["labels"]
                    and "앨범" in praise_actions["metadataWrap"]["labels"]
                    and "길고 긴 아티스트 이름과 예배팀 이름" in praise_actions["metadataWrap"]["values"]
                    and "잘리지 않아야 하는 긴 앨범 메타데이터" in praise_actions["metadataWrap"]["values"]
                    and praise_actions["metadataWrap"]["whiteSpace"] != "nowrap"
                    and praise_actions["metadataWrap"]["overflow"] == "visible"
                    and praise_actions["metadataWrap"]["textOverflow"] == "clip"
                    and praise_actions["metadataWrap"]["headFlexWrap"] == "wrap"
                    and praise_actions["metadataWrap"]["headOverflow"] == "visible"
                    and praise_actions["metadataWrap"]["separator"] in ("none", "normal", "")
                    and praise_actions["draftTitle"] == "테스트 새 찬양"
                    and praise_actions["draftVersions"] == 1
                    and praise_actions["draftPraiseType"] == "ccm"
                    and praise_actions["emptyNewDraftDeletable"]
                    and not praise_actions["nonEmptyNewDraftDeletable"]
                    and praise_actions["renamedEmptyShellDeletable"]
                    and praise_actions["linkedEntries"] == 1
                    and praise_actions["linkedReadonly"]
                    and not praise_actions["linkedEditableLeak"]
                    and praise_actions["downloadShowButtons"] == 0
                    and praise_actions["downloadXmlButtons"] == 0
                    and praise_actions["toolbarCopyStack"] == 0
                ):
                    pass_("praise-version-copy-actions", json.dumps(praise_actions, ensure_ascii=False))
                else:
                    fail("praise-version-copy-actions", json.dumps(praise_actions, ensure_ascii=False))
                signature_state = page.evaluate(
                    """
                    (() => {
                      const rows = [
                        { id: '11111111-1111-4111-8111-111111111111', canonical_song_id: 'song', source_song_id: 'song', lyric_signature: 'mindex-same' },
                        { id: '22222222-2222-4222-8222-222222222222', canonical_song_id: 'song', source_song_id: 'song', lyric_signature: 'mindex-same' },
                        { id: '33333333-3333-4333-8333-333333333333', canonical_song_id: 'song', source_song_id: 'song', lyric_signature: 'mindex-other' },
                      ];
                      assignUniqueVersionLyricSignatures(rows, [
                        { id: '99999999-9999-4999-8999-999999999999', lyric_signature: 'mindex-other' },
                      ]);
                      const versionOrderRows = [
                        { id: '44444444-4444-4444-8444-444444444444', version_order: 1 },
                        { id: '55555555-5555-4555-8555-555555555555', version_order: 2 },
                      ];
                      const orders = assignStableVersionOrders([
                        { id: '66666666-6666-4666-8666-666666666666' },
                        { id: '77777777-7777-4777-8777-777777777777' },
                      ], versionOrderRows, 'other-song');
                      return {
                        signatures: rows.map((row) => row.lyric_signature),
                        unique: new Set(rows.map((row) => row.lyric_signature)).size === rows.length,
                        secondSuffixed: rows[1].lyric_signature.startsWith('mindex-same:'),
                        existingConflictSuffixed: rows[2].lyric_signature.startsWith('mindex-other:'),
                        orders: [...orders.values()],
                      };
                    })()
                    """
                )
                if (
                    signature_state["unique"]
                    and signature_state["signatures"][0] == "mindex-same"
                    and signature_state["secondSuffixed"]
                    and signature_state["existingConflictSuffixed"]
                    and signature_state["orders"] == [3, 4]
                ):
                    pass_("praise-version-lyric-signature-unique", json.dumps(signature_state, ensure_ascii=False))
                else:
                    fail("praise-version-lyric-signature-unique", json.dumps(signature_state, ensure_ascii=False))
                canonical_state = page.evaluate(
                    """
                    async () => {
                      const originalClient = state.client;
                      const existingId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
                      let directUpsertCalled = false;
                      let raceMaybeCalls = 0;
                      let raceUpsertCalled = false;
                      try {
                        state.client = {
                          from() {
                            return {
                              select() { return this; },
                              eq() { return this; },
                              maybeSingle() {
                                return Promise.resolve({
                                  data: { id: existingId, title: '같은 제목', normalized_title: '같은제목' },
                                  error: null,
                                });
                              },
                              upsert() {
                                directUpsertCalled = true;
                                return this;
                              },
                              single() {
                                return Promise.resolve({ data: { id: 'unexpected' }, error: null });
                              },
                            };
                          },
                        };
                        const directSong = {
                          id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
                          title: '같은 제목',
                        };
                        const directId = await ensureCanonicalSongRow(directSong);

                        state.client = {
                          from() {
                            return {
                              select() { return this; },
                              eq() { return this; },
                              maybeSingle() {
                                raceMaybeCalls += 1;
                                return Promise.resolve({
                                  data: raceMaybeCalls === 1
                                    ? null
                                    : { id: existingId, title: '같은 제목', normalized_title: '같은제목' },
                                  error: null,
                                });
                              },
                              upsert() {
                                raceUpsertCalled = true;
                                return this;
                              },
                              single() {
                                return Promise.resolve({
                                  data: null,
                                  error: {
                                    code: '23505',
                                    message: 'duplicate key value violates unique constraint "mindex_canonical_songs_normalized_title_key"',
                                  },
                                });
                              },
                            };
                          },
                        };
                        const raceSong = {
                          id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                          title: '같은 제목',
                        };
                        const raceId = await ensureCanonicalSongRow(raceSong);
                        return {
                          directId,
                          directCached: directSong._canonicalSongId,
                          directUpsertCalled,
                          raceId,
                          raceCached: raceSong._canonicalSongId,
                          raceMaybeCalls,
                          raceUpsertCalled,
                        };
                      } finally {
                        state.client = originalClient;
                      }
                    }
                    """
                )
                if (
                    canonical_state["directId"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
                    and canonical_state["directCached"] == canonical_state["directId"]
                    and not canonical_state["directUpsertCalled"]
                    and canonical_state["raceId"] == canonical_state["directId"]
                    and canonical_state["raceCached"] == canonical_state["raceId"]
                    and canonical_state["raceMaybeCalls"] == 2
                    and not canonical_state["raceUpsertCalled"]
                ):
                    pass_("praise-canonical-normalized-title-reuse", json.dumps(canonical_state, ensure_ascii=False))
                else:
                    fail("praise-canonical-normalized-title-reuse", json.dumps(canonical_state, ensure_ascii=False))
                form_reorder_save = page.evaluate(
                    """
                    async () => {
                      const originalClient = state.client;
                      const originalPraiseTypesSupported = state.songVersionPraiseTypesSupported;
                      const versionId = '11111111-2222-4333-8444-555555555555';
                      const firstUnitId = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';
                      const secondUnitId = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb';
                      const operations = [];
                      try {
                        state.songVersionPraiseTypesSupported = true;
                        state.selectedVersionId = versionId;
                        state.forms = [];
                        state.client = {
                          from(table) {
                            let pendingUpdate = false;
                            const query = {
                              select() { return this; },
                              eq(column, value) {
                                operations.push({ op: 'eq', table, column, value });
                                if (pendingUpdate) {
                                  pendingUpdate = false;
                                  return Promise.resolve({ data: null, error: null });
                                }
                                return this;
                              },
                              in(column, values) {
                                operations.push({ op: 'in', table, column, values });
                                if (table === 'mindex_version_units') {
                                  return Promise.resolve({
                                    data: [
                                      { id: firstUnitId, version_id: versionId, unit_order: 1, curated_order: 1 },
                                      { id: secondUnitId, version_id: versionId, unit_order: 2, curated_order: 2 },
                                    ],
                                    error: null,
                                  });
                                }
                                return Promise.resolve({ data: [], error: null });
                              },
                              maybeSingle() {
                                return Promise.resolve({
                                  data: { id: '99999999-9999-4999-8999-999999999999', title: '순서 테스트', normalized_title: '순서테스트' },
                                  error: null,
                                });
                              },
                              update(payload) {
                                operations.push({ op: 'update', table, payload });
                                pendingUpdate = true;
                                return this;
                              },
                              upsert(payload) {
                                operations.push({ op: 'upsert', table, payload });
                                if (table === 'mindex_version_units') {
                                  const unitUpsertIndex = operations.length - 1;
                                  const reservedBeforeUpsert = operations
                                    .slice(0, unitUpsertIndex)
                                    .filter((entry) => entry.op === 'update' && entry.table === 'mindex_version_units')
                                    .length;
                                  if (reservedBeforeUpsert < 2) {
                                    return Promise.resolve({
                                      data: null,
                                      error: { message: 'duplicate key value violates unique unit order' },
                                    });
                                  }
                                }
                                return Promise.resolve({ data: payload, error: null });
                              },
                              delete() {
                                operations.push({ op: 'delete', table });
                                return this;
                              },
                            };
                            return query;
                          },
                        };
                        const song = {
                          id: '99999999-9999-4999-8999-999999999999',
                          title: '순서 테스트',
                          versions: [{
                            id: versionId,
                            name: 'Default',
                            is_primary: true,
                            praise_types: ['ccm'],
                            forms: [
                              { id: secondUnitId, part_type: 'Chorus', lyrics: '후렴', sort_order: 1 },
                              { id: firstUnitId, part_type: 'Verse', lyrics: '절', sort_order: 2 },
                            ],
                          }],
                        };
                        await saveSongVersions(song);
                        const unitUpdates = operations
                          .filter((entry) => entry.op === 'update' && entry.table === 'mindex_version_units')
                          .map((entry) => entry.payload);
                        const unitUpsert = operations.find((entry) => entry.op === 'upsert' && entry.table === 'mindex_version_units');
                        return {
                          unitUpdates,
                          upsertOrders: (unitUpsert?.payload || []).map((row) => ({
                            id: row.id,
                            unit_order: row.unit_order,
                            curated_order: row.curated_order,
                            label: row.curated_unit_label,
                          })),
                          updateBeforeUpsert: operations.findIndex((entry) => entry.op === 'update' && entry.table === 'mindex_version_units')
                            < operations.findIndex((entry) => entry.op === 'upsert' && entry.table === 'mindex_version_units'),
                        };
                      } finally {
                        state.client = originalClient;
                        state.songVersionPraiseTypesSupported = originalPraiseTypesSupported;
                      }
                    }
                    """
                )
                if (
                    len(form_reorder_save["unitUpdates"]) == 2
                    and form_reorder_save["updateBeforeUpsert"]
                    and all(item["unit_order"] >= 10000 and item["curated_order"] >= 10000 for item in form_reorder_save["unitUpdates"])
                    and [item["id"] for item in form_reorder_save["upsertOrders"]] == [
                        "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
                        "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
                    ]
                    and [item["unit_order"] for item in form_reorder_save["upsertOrders"]] == [1, 2]
                    and [item["curated_order"] for item in form_reorder_save["upsertOrders"]] == [1, 2]
                ):
                    pass_("praise-form-reorder-save-reserves-orders", json.dumps(form_reorder_save, ensure_ascii=False))
                else:
                    fail("praise-form-reorder-save-reserves-orders", json.dumps(form_reorder_save, ensure_ascii=False))

                page.click('[data-home-module="scripture"]')
                wait_for_scripture_data(page)
                wait_for_module_data(page, "scripture")
                snapshot = get_app_snapshot(page)
                if snapshot.get("scriptureError"):
                    fail("scripture-data-load", json.dumps(snapshot, ensure_ascii=False))
                elif snapshot.get("scriptureBooks", 0) > 0:
                    pass_("scripture-data-load", json.dumps(snapshot, ensure_ascii=False))
                else:
                    fail("scripture-data-load", json.dumps(snapshot, ensure_ascii=False))

            if page_errors:
                fail("page-errors", "\n".join(page_errors[:5]))
            else:
                pass_("page-errors")

            relevant_console = [
                item for item in console_messages
                if "favicon" not in item.lower()
                and "source map" not in item.lower()
                and "the server responded with a status of 400" not in item.lower()
                and "could not load song versions" not in item.lower()
            ]
            if relevant_console:
                fail("console-errors", "\n".join(relevant_console[:8]))
            else:
                pass_("console-errors")

            browser.close()
    except PlaywrightTimeoutError as error:
        fail("playwright-timeout", str(error))
    finally:
        server.shutdown()
        server.server_close()

    for status, name, detail in results:
        print(f"{status} {name}" + (f" :: {detail}" if detail else ""))

    return 1 if any(status == "FAIL" for status, _, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
