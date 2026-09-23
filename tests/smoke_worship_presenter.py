from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from smoke_app import (
    PLAYWRIGHT_IMPORT_ERROR,
    PlaywrightTimeoutError,
    build_raw_connection_link,
    extract_supa_config,
    launch_chromium,
    select_service_with_slides,
    start_local_app_server,
    sync_playwright,
    wait_for_service_data,
    wait_for_supabase_client,
)


def presenter_output_url(app_url: str) -> str:
    return f"{app_url}?mindexSmokeRaw=1&output=presenter"


def rgb_at(image_bytes: bytes, x_ratio: float, y_ratio: float) -> tuple[int, int, int]:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    x = max(0, min(image.width - 1, round((image.width - 1) * x_ratio)))
    y = max(0, min(image.height - 1, round((image.height - 1) * y_ratio)))
    return image.getpixel((x, y))


def is_chromakey_green(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return green >= 220 and red <= 35 and blue <= 35


def is_dark_bar(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return red <= 25 and green <= 35 and 35 <= blue <= 95


def is_empty_output_background(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return red <= 8 and green <= 8 and blue <= 8


def screenshot_with_retry(page, locator, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return locator.screenshot()
        except Exception as error:
            last_error = error
            page.wait_for_timeout(250)
    assert last_error is not None
    raise last_error


def main() -> int:
    results: list[tuple[str, str, str]] = []
    console_messages: list[str] = []
    page_errors: list[str] = []

    def record_response(response, prefix: str = "") -> None:
        if response.status >= 400:
            # The deployed database may briefly remain on the previous schema
            # while the app probes the additive service_alias migration.
            if (
                response.status == 400
                and "/rest/v1/mindex_worship_services" in response.url
                and "select=service_alias" in response.url
            ):
                return
            label = f"{prefix} " if prefix else ""
            console_messages.append(f"{label}response {response.status}: {response.url}")

    def pass_(name: str, detail: str = "") -> None:
        results.append(("PASS", name, detail))

    def fail(name: str, detail: str = "") -> None:
        results.append(("FAIL", name, detail))

    def skip(name: str, detail: str = "") -> None:
        results.append(("SKIP", name, detail))

    app_source = (Path(__file__).resolve().parents[1] / "app.js").read_text(encoding="utf-8")
    click_start = app_source.find("function handleServiceOutlineSlideClick(serviceOutlineItem)")
    dblclick_start = app_source.find("function handleServiceOutlineSlideDoubleClick(event)")
    selection_start = app_source.find("function syncServiceOutlineSelection(serviceOutlineItem)")
    click_body = app_source[click_start:dblclick_start] if click_start >= 0 and dblclick_start > click_start else ""
    dblclick_body = app_source[dblclick_start:selection_start] if dblclick_start >= 0 and selection_start > dblclick_start else ""
    if (
        "selectPresenterBoardSlide(target.serviceId, target.slideIndex)" in click_body
        and "setPresenterPendingSlide(target.serviceId, target.slideIndex" not in click_body
        and "runPresenterAction(\"jump\", target.serviceId" not in click_body
        and "startPresenterAtSlide(target.serviceId, target.slideIndex)" in dblclick_body
        and "runPresenterAction(\"jump\", target.serviceId" in dblclick_body
        and "presenterSelectedLaunchIndex(serviceId)" in app_source
    ):
        pass_("presenter-outline-click-requires-doubleclick-output")
    else:
        fail("presenter-outline-click-requires-doubleclick-output")

    citation_start = app_source.find("async function appendPresenterCitationReference(input)")
    citation_end = app_source.find("function presenterSlideMatchesScriptureReference", citation_start)
    citation_body = app_source[citation_start:citation_end] if citation_start >= 0 and citation_end > citation_start else ""
    # 2026-09-18: `추가 즉시 송출` (autoOutput) jumps output to the first added verse
    # without forcing a controller scroll; off only adds/saves.
    if (
        "if (autoOutput && state.selectedServiceId === serviceId)" in citation_body
        and "const shouldOpenOutput = !presenterControllerIsLive(serviceId)" in citation_body
        and "runPresenterAction(\"jump\", serviceId, { index: targetIndex, scroll: false })" in citation_body
        and "if (shouldOpenOutput) await openPresenterOutput(serviceId)" in citation_body
    ):
        pass_("presenter-citation-auto-output-toggle")
    else:
        fail("presenter-citation-auto-output-toggle")

    if sync_playwright is None:
        skip("playwright-dependency", f"{PLAYWRIGHT_IMPORT_ERROR}. Install the Python playwright package to run UI smoke checks.")
        for status, name, detail in results:
            print(f"{status} {name}" + (f" :: {detail}" if detail else ""))
        return 0

    if not all(extract_supa_config()):
        skip("supabase-config", "No Supabase config found.")
        for status, name, detail in results:
            print(f"{status} {name}" + (f" :: {detail}" if detail else ""))
        return 0

    server, app_url = start_local_app_server()
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 980})
            page = context.new_page()
            page.add_init_script("localStorage.clear(); sessionStorage.clear();")
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("response", record_response)
            page.on(
                "console",
                lambda msg: console_messages.append(f"{msg.type}: {msg.text}")
                if msg.type in ("error", "warning")
                else None,
            )

            page.goto(build_raw_connection_link(app_url, "presenter"), wait_until="load")
            page.wait_for_selector(".app-shell", timeout=5000)
            wait_for_supabase_client(page)

            loading_right_rail_state = page.evaluate(
                """
                (() => {
                  const sidebar = document.querySelector('#mindexRightSidebar');
                  const shell = document.querySelector('.app-shell');
                  const topbar = document.querySelector('.topbar');
                  const topbarActions = document.querySelector('.topbar-actions');
                  const saveButton = document.querySelector('#saveAllBtn');
                  const themeButton = document.querySelector('#themeBtn');
                  const sidebarStyle = sidebar ? getComputedStyle(sidebar) : null;
                  const shellTopFillStyle = shell ? getComputedStyle(shell, '::after') : null;
                  const topbarStyle = topbar ? getComputedStyle(topbar) : null;
                  const sidebarRect = sidebar?.getBoundingClientRect();
                  const topbarRect = topbar?.getBoundingClientRect();
                  const topbarActionsRect = topbarActions?.getBoundingClientRect();
                  const saveStyle = saveButton ? getComputedStyle(saveButton) : null;
                  const themeStyle = themeButton ? getComputedStyle(themeButton) : null;
                  const hasContent = sidebar?.dataset.hasContent === 'true';
                  return {
                    module: document.body.dataset.module || '',
                    hidden: Boolean(sidebar?.hidden),
                    hasContent,
                    bodyOpen: document.body.classList.contains('right-sidebar-open'),
                    sidebarTop: sidebarRect ? Math.round(sidebarRect.top) : 0,
                    topbarBottom: topbarRect ? Math.round(topbarRect.bottom) : 0,
                    sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
                    topbarActionsLeft: topbarActionsRect ? Math.round(topbarActionsRect.left) : 0,
                    topbarActionsWidth: topbarActionsRect ? Math.round(topbarActionsRect.width) : 0,
                    sidebarLeft: sidebarRect ? Math.round(sidebarRect.left) : 0,
                    rightRailWidth: Math.round(parseFloat(getComputedStyle(document.body).getPropertyValue('--right-rail-w')) || 0),
                    sidebarBackground: sidebarStyle?.backgroundColor || '',
                    topFillBackground: shellTopFillStyle?.backgroundColor || '',
                    topbarBackground: topbarStyle?.backgroundColor || '',
                    saveOpacity: saveStyle?.opacity || '',
                    themeOpacity: themeStyle?.opacity || '',
                    saveColor: saveStyle?.color || '',
                    themeColor: themeStyle?.color || '',
                  };
                })()
                """
            )
            loading_right_rail_ok = (
                loading_right_rail_state["module"] == "presenter"
                and loading_right_rail_state["sidebarTop"] >= loading_right_rail_state["topbarBottom"]
                and not loading_right_rail_state["hidden"]
                and loading_right_rail_state["bodyOpen"]
                and loading_right_rail_state["sidebarWidth"] >= 180
                and abs(loading_right_rail_state["topbarActionsLeft"] - loading_right_rail_state["sidebarLeft"]) <= 1
                and abs(loading_right_rail_state["topbarActionsWidth"] - loading_right_rail_state["sidebarWidth"]) <= 1
                and loading_right_rail_state["sidebarBackground"] == loading_right_rail_state["topbarBackground"]
                and loading_right_rail_state["topFillBackground"] == loading_right_rail_state["sidebarBackground"]
                and float(loading_right_rail_state["saveOpacity"]) > 0
                and loading_right_rail_state["themeOpacity"] == "1"
            )
            if loading_right_rail_ok:
                pass_("presenter-loading-right-rail", json.dumps(loading_right_rail_state, ensure_ascii=False))
            else:
                fail("presenter-loading-right-rail", json.dumps(loading_right_rail_state, ensure_ascii=False))

            wait_for_service_data(page)

            service = select_service_with_slides(page)
            if not service:
                skip("presenter-slides", "No service with generated slides.")
            else:
                page.wait_for_function(
                    "() => document.querySelector('#servicePresenterControls') && document.querySelector('.svc-slide-thumb')",
                    timeout=10000,
                )
                board_slide_state = page.evaluate(
                    """
                    (serviceId) => {
                      const slides = presenterSlidesForService(serviceId);
                      const domIndexes = [...document.querySelectorAll('.svc-slide-thumb[data-presenter-index][data-service-id]')]
                        .filter((thumb) => thumb.dataset.serviceId === serviceId)
                        .map((thumb) => Number(thumb.dataset.presenterIndex))
                        .filter(Number.isFinite)
                        .sort((a, b) => a - b);
                      const missing = slides.map((_, index) => index).filter((index) => !domIndexes.includes(index));
                      return {
                        stateSlides: slides.length,
                        domSlides: domIndexes.length,
                        missing,
                      };
                    }
                    """,
                    service["id"],
                )
                if (
                    board_slide_state["stateSlides"] > 0
                    and board_slide_state["domSlides"] == board_slide_state["stateSlides"]
                    and not board_slide_state["missing"]
                ):
                    pass_("presenter-slides", json.dumps({**service, **board_slide_state}, ensure_ascii=False))
                else:
                    fail("presenter-slides", json.dumps({**service, **board_slide_state}, ensure_ascii=False))

                session_navigation_state = page.evaluate(
                    """
                    (serviceId) => {
                      const service = state.services.find((item) => item.id === serviceId) || {};
                      const previousPresenter = {
                        viewServiceId: state.presenter.viewServiceId,
                        serviceId: state.presenter.serviceId,
                        slides: state.presenter.slides,
                        sourceItems: state.presenter.sourceItems,
                        sourceSignature: state.presenter.sourceSignature,
                        index: state.presenter.index,
                        safetyBlank: state.presenter.safetyBlank,
                        jumpDraft: state.presenter.jumpDraft,
                        liveScripture: state.presenter.liveScripture,
                        livePraise: state.presenter.livePraise,
                      };
                      const previousSelectedServiceId = state.selectedServiceId;
                      const previousSelectedServiceItemIndex = state.selectedServiceItemIndex;
                      preparePresenterService(serviceId);
                      state.module = 'presenter';
                      state.selectedServiceId = null;
                      state.selectedServiceItemIndex = null;
                      renderPresenterDetail();
                      const controls = document.querySelector('#servicePresenterControls');
                      const title = document.querySelector('.service-sidebar-presenter-title')?.textContent?.trim() || '';
                      const controllerTitleRemoved = !document.querySelector('.presenter-viewer .svc-service-title')
                        && !document.querySelector('.presenter-viewer .svc-date-text');
                      const thumbs = [...document.querySelectorAll('.svc-slide-thumb[data-service-id]')]
                        .filter((thumb) => thumb.dataset.serviceId === serviceId)
                        .length;
                      const selectedWasCleared = !state.selectedServiceId;
                      Object.assign(state.presenter, previousPresenter);
                      state.selectedServiceId = previousSelectedServiceId;
                      state.selectedServiceItemIndex = previousSelectedServiceItemIndex;
                      renderPresenterDetail();
                      return {
                        sessionServiceId: serviceId,
                        selectedWasCleared,
                        title,
                        expectedTitle: serviceDisplayTypeName(service),
                        controllerTitleRemoved,
                        hasControls: Boolean(controls),
                        thumbs,
                      };
                    }
                    """,
                    service["id"],
                )
                if (
                    session_navigation_state["sessionServiceId"] == service["id"]
                    and session_navigation_state["selectedWasCleared"]
                    and session_navigation_state["title"] == session_navigation_state["expectedTitle"]
                    and session_navigation_state["controllerTitleRemoved"]
                    and session_navigation_state["hasControls"]
                    and session_navigation_state["thumbs"] > 0
                ):
                    pass_("presenter-session-survives-navigation-selection-clear", json.dumps(session_navigation_state, ensure_ascii=False))
                else:
                    fail("presenter-session-survives-navigation-selection-clear", json.dumps(session_navigation_state, ensure_ascii=False))

                tab_selection_state = page.evaluate(
                    """
                    (serviceId) => {
                      const service = state.services.find((item) => item.id === serviceId) || {};
                      const other = state.services.find((item) => item.id && item.id !== serviceId) || null;
                      if (!other) return { skipped: true, reason: 'No second service fixture.' };
                      const previousModule = state.module;
                      const previousPresenter = {
                        viewServiceId: state.presenter.viewServiceId,
                        serviceId: state.presenter.serviceId,
                        slides: state.presenter.slides,
                        sourceItems: state.presenter.sourceItems,
                        sourceSignature: state.presenter.sourceSignature,
                        index: state.presenter.index,
                        safetyBlank: state.presenter.safetyBlank,
                        jumpDraft: state.presenter.jumpDraft,
                        liveScripture: state.presenter.liveScripture,
                        livePraise: state.presenter.livePraise,
                      };
                      const previousSelectedServiceId = state.selectedServiceId;
                      const previousSelectedServiceItemIndex = state.selectedServiceItemIndex;
                      preparePresenterService(serviceId);
                      state.module = 'presenter';
                      state.selectedServiceId = other.id;
                      state.selectedServiceItemIndex = null;
                      const snapshot = currentBrowserHistorySnapshot();
                      renderPresenterDetail();
                      const title = document.querySelector('.service-sidebar-presenter-title')?.textContent?.trim() || '';
                      const controllerTitleRemoved = !document.querySelector('.presenter-viewer .svc-service-title')
                        && !document.querySelector('.presenter-viewer .svc-date-text');
                      const viewedServiceId = presenterViewServiceId();
                      Object.assign(state.presenter, previousPresenter);
                      state.module = previousModule;
                      state.selectedServiceId = previousSelectedServiceId;
                      state.selectedServiceItemIndex = previousSelectedServiceItemIndex;
                      render();
                      return {
                        skipped: false,
                        expectedServiceId: serviceId,
                        selectedServiceId: other.id,
                        viewedServiceId,
                        snapshotServiceId: snapshot.selectedServiceId,
                        title,
                        expectedTitle: serviceDisplayTypeName(service),
                        controllerTitleRemoved,
                      };
                    }
                    """,
                    service["id"],
                )
                if tab_selection_state.get("skipped"):
                    skip("presenter-tab-keeps-pinned-service", json.dumps(tab_selection_state, ensure_ascii=False))
                elif (
                    tab_selection_state["viewedServiceId"] == service["id"]
                    and tab_selection_state["snapshotServiceId"] == service["id"]
                    and tab_selection_state["title"] == tab_selection_state["expectedTitle"]
                    and tab_selection_state["controllerTitleRemoved"]
                ):
                    pass_("presenter-tab-keeps-pinned-service", json.dumps(tab_selection_state, ensure_ascii=False))
                else:
                    fail("presenter-tab-keeps-pinned-service", json.dumps(tab_selection_state, ensure_ascii=False))

                section_edit_buttons = page.locator("[data-presenter-section-edit]")
                section_editor_rows = []
                for section_index in range(section_edit_buttons.count()):
                    button = page.locator("[data-presenter-section-edit]").nth(section_index)
                    label = button.get_attribute("aria-label") or ""
                    button.click()
                    page.wait_for_timeout(60)
                    dialog = page.locator("[data-presenter-section-editor]")
                    opened = dialog.count() > 0
                    title = dialog.locator("h3").inner_text().strip() if opened else ""
                    section_editor_rows.append({"label": label, "opened": opened, "title": title})
                    if opened:
                        dialog.locator("[data-presenter-section-editor-close]").click()
                        page.wait_for_timeout(60)
                section_editor_state = {
                    "count": len(section_editor_rows),
                    "opened": section_editor_rows,
                    "allOpened": bool(section_editor_rows) and all(
                        item["opened"] and item["title"] for item in section_editor_rows
                    ),
                }
                # Section pencil controls were deliberately removed from the
                # board; element selection now opens the compact editor.
                if not section_editor_rows:
                    pass_("presenter-section-edit-buttons", json.dumps(section_editor_state, ensure_ascii=False))
                else:
                    fail("presenter-section-edit-buttons", json.dumps(section_editor_state, ensure_ascii=False))

                thumb_metrics = page.evaluate(
                    """
                    (() => [...document.querySelectorAll('.svc-slide-thumb-frame')]
                      .slice(0, 12)
                      .map((node) => {
                        const rect = node.getBoundingClientRect();
                        return {
                          width: Math.round(rect.width),
                          height: Math.round(rect.height),
                          ratio: rect.height ? Number((rect.width / rect.height).toFixed(3)) : 0
                        };
                      }))()
                    """
                )
                if thumb_metrics:
                    widths = [item["width"] for item in thumb_metrics]
                    heights = [item["height"] for item in thumb_metrics]
                    ratios = [item["ratio"] for item in thumb_metrics]
                    uniform = (
                        max(widths) - min(widths) <= 2
                        and max(heights) - min(heights) <= 2
                        and all(1.75 <= ratio <= 1.79 for ratio in ratios)
                    )
                    if uniform:
                        pass_("presenter-thumbnail-grid", json.dumps(thumb_metrics[:4], ensure_ascii=False))
                    else:
                        fail("presenter-thumbnail-grid", json.dumps(thumb_metrics[:8], ensure_ascii=False))

                initial_status = page.evaluate(
                    """
                    (() => ({
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                    }))()
                    """
                )
                if initial_status["status"] == "준비" and initial_status["mode"] == "":
                    pass_("presenter-status-ready", json.dumps(initial_status, ensure_ascii=False))
                else:
                    fail("presenter-status-ready", json.dumps(initial_status, ensure_ascii=False))

                live_panel_state = page.evaluate(
                    """
                    (() => {
                      const panel = document.querySelector('.svc-presenter-live-panel');
                      const actions = document.querySelector('.svc-presenter-actions');
                      const outputGroup = document.querySelector('.svc-presenter-side-panel .svc-presenter-output-group');
                      const mainGroup = document.querySelector('.svc-presenter-side-panel .svc-presenter-main');
                      const utilityGroup = document.querySelector('.svc-presenter-side-panel .svc-presenter-utility-actions');
                      const preview = panel?.querySelector('.svc-presenter-live-preview');
                      const previewRect = preview?.getBoundingClientRect();
                      const topRect = document.querySelector('.svc-presenter-top')?.getBoundingClientRect();
                      const rightSidebar = document.querySelector('#mindexRightSidebar');
                      const sidePanel = rightSidebar?.querySelector('.svc-presenter-side-panel');
                      const visualOrder = {
                        actions: actions ? getComputedStyle(actions).display : '',
                        live: panel ? Number(getComputedStyle(panel).order || 0) : 0,
                        output: outputGroup ? Number(getComputedStyle(outputGroup).order || 0) : 0,
                        main: mainGroup ? Number(getComputedStyle(mainGroup).order || 0) : 0,
                        utility: utilityGroup ? Number(getComputedStyle(utilityGroup).order || 0) : 0,
                      };
                      return {
                        exists: Boolean(panel),
                        inActions: Boolean(panel && actions?.contains(panel)),
                        inSidePanel: Boolean(panel && sidePanel?.contains(panel)),
                        inRightSidebar: Boolean(panel && rightSidebar?.contains(panel)),
                        visualOrder,
                        status: panel?.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                        title: panel?.querySelector('.svc-presenter-live-copy strong')?.textContent.trim() || '',
                        hasPreview: Boolean(preview),
                        hasEmptyPreview: Boolean(panel?.querySelector('.svc-presenter-live-preview-empty')),
                        emptyPreviewBackground: panel?.querySelector('.svc-presenter-live-preview-empty')
                          ? getComputedStyle(panel.querySelector('.svc-presenter-live-preview-empty')).backgroundColor
                          : '',
                        previewRatio: previewRect?.height ? Number((previewRect.width / previewRect.height).toFixed(2)) : 0,
                        topHeight: Math.round(topRect?.height || 0),
                        mediaCount: panel?.querySelectorAll('audio, video').length || 0,
                        overflowX: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
                      };
                    })()
                    """
                )
                live_panel_ok = (
                    live_panel_state["exists"]
                    and live_panel_state["inActions"]
                    and live_panel_state["inSidePanel"]
                    and live_panel_state["inRightSidebar"]
                    and live_panel_state["visualOrder"]["actions"] == "contents"
                    and live_panel_state["visualOrder"]["live"] < live_panel_state["visualOrder"]["main"]
                    and live_panel_state["visualOrder"]["main"] < live_panel_state["visualOrder"]["output"]
                    and live_panel_state["visualOrder"]["output"] < live_panel_state["visualOrder"]["utility"]
                    and live_panel_state["status"] == "준비"
                    and live_panel_state["title"] == "송출 대기"
                    and live_panel_state["hasPreview"]
                    and live_panel_state["hasEmptyPreview"]
                    and live_panel_state["emptyPreviewBackground"] == "rgb(0, 0, 0)"
                    and 1.72 <= live_panel_state["previewRatio"] <= 1.82
                    and 300 <= live_panel_state["topHeight"] <= 430
                    and live_panel_state["mediaCount"] == 0
                    and live_panel_state["overflowX"] == 0
                )
                if live_panel_ok:
                    pass_("presenter-live-status-panel", json.dumps(live_panel_state, ensure_ascii=False))
                else:
                    fail("presenter-live-status-panel", json.dumps(live_panel_state, ensure_ascii=False))

                right_sidebar_toggle_state = page.evaluate(
                    """
                    (() => {
                      const button = document.querySelector('#presenterRightSidebarBtn');
                      const saveButton = document.querySelector('#saveAllBtn');
                      const themeButton = document.querySelector('#themeBtn');
                      const sidebar = document.querySelector('#mindexRightSidebar');
                      const sidePanel = sidebar?.querySelector('.svc-presenter-side-panel');
                      const rightSidebarHead = sidebar?.querySelector('.right-sidebar-head');
                      const presenterTop = sidebar?.querySelector('.svc-presenter-top');
                      const inputRail = sidebar?.querySelector('.svc-presenter-input-rail');
                      const inputRailHead = sidebar?.querySelector('.svc-presenter-input-rail-head');
                      const leftSidebar = document.querySelector('#mindexSidebarPanel');
                      const headerToggle = document.querySelector('.svc-header-actions [data-presenter-right-sidebar-toggle]');
                      const presenterHeader = document.querySelector('.presenter-viewer .svc-header');
                      const topbar = document.querySelector('.topbar');
                      const topbarActions = document.querySelector('.topbar-actions');
                      const resolveCssColor = (value) => {
                        const sample = document.createElement('span');
                        sample.style.color = value;
                        document.body.appendChild(sample);
                        const color = getComputedStyle(sample).color;
                        sample.remove();
                        return color;
                      };
                      const sidebarIsVisible = () => {
                        if (!sidebar || sidebar.hidden || !document.body.classList.contains('right-sidebar-open')) return false;
                        const style = getComputedStyle(sidebar);
                        return style.visibility !== 'hidden' && Number(style.opacity) > 0.5;
                      };
                      const buttonStyle = button ? getComputedStyle(button) : null;
                      const buttonRect = button?.getBoundingClientRect();
                      const saveRect = saveButton?.getBoundingClientRect();
                      const themeRect = themeButton?.getBoundingClientRect();
                      const topbarRectForTheme = topbar?.getBoundingClientRect();
                      const presenterTopStyle = presenterTop ? getComputedStyle(presenterTop) : null;
                      const inputRailStyle = inputRail ? getComputedStyle(inputRail) : null;
                      const inputRailHeadStyle = inputRailHead ? getComputedStyle(inputRailHead) : null;
                      const saveStyle = saveButton ? getComputedStyle(saveButton) : null;
                      const themeStyle = themeButton ? getComputedStyle(themeButton) : null;
                      const sidebarRect = sidebar?.getBoundingClientRect();
                      const topbarRect = topbar?.getBoundingClientRect();
                      const topbarActionsRect = topbarActions?.getBoundingClientRect();
                      const before = {
                        buttonVisible: Boolean(button && !button.hidden),
                        saveHidden: Boolean(document.querySelector('#saveAllBtn')?.hidden),
                        saveVisible: Boolean(saveButton && !saveButton.hidden),
                        themeVisible: Boolean(themeButton && !themeButton.hidden),
                        saveInTopbar: Boolean(saveRect && topbarRectForTheme)
                          && saveRect.top >= topbarRectForTheme.top
                          && saveRect.bottom <= topbarRectForTheme.bottom,
                        saveTracksRightInfoBar: Boolean(saveRect && sidebarRect && topbarActionsRect)
                          && saveRect.left >= sidebarRect.left
                          && saveRect.right <= sidebarRect.right + 1
                          && Math.abs(Math.round(topbarActionsRect.left) - Math.round(sidebarRect.left)) <= 1,
                        saveInRightSidebar: Boolean(saveButton && sidebar?.contains(saveButton)),
                        themeInTopbar: Boolean(themeRect && topbarRectForTheme)
                          && themeRect.top >= topbarRectForTheme.top
                          && themeRect.bottom <= topbarRectForTheme.bottom,
                        themeTracksRightInfoBar: Boolean(themeRect && sidebarRect && topbarActionsRect)
                          && themeRect.left >= sidebarRect.left
                          && themeRect.right <= sidebarRect.right + 1
                          && Math.abs(Math.round(topbarActionsRect.width) - Math.round(sidebarRect.width)) <= 1,
                        themeInRightSidebar: Boolean(themeButton && sidebar?.contains(themeButton)),
                        headerToggleRemoved: !headerToggle,
                        presenterHeaderRemoved: !presenterHeader,
                        rightSidebarHeaderRemoved: !rightSidebarHead,
                        sidebarVisible: sidebarIsVisible(),
                        bodyOpen: document.body.classList.contains('right-sidebar-open'),
                        bodyTransition: getComputedStyle(document.body).transitionProperty,
                        sidebarTransition: sidebar ? getComputedStyle(sidebar).transitionProperty : '',
                        sidebarBorderLeft: sidebar ? getComputedStyle(sidebar).borderLeftWidth : '',
                        sidebarTop: sidebarRect ? Math.round(sidebarRect.top) : 0,
                        topbarBottom: topbarRect ? Math.round(topbarRect.bottom) : 0,
                        sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
                        sidePanelWidth: sidePanel ? Math.round(sidePanel.getBoundingClientRect().width) : 0,
                        leftSidebarWidth: leftSidebar ? Math.round(leftSidebar.getBoundingClientRect().width) : 0,
                        topbarActionsWidth: topbarActionsRect ? Math.round(topbarActionsRect.width) : 0,
                        rightRailWidth: Math.round(parseFloat(getComputedStyle(document.body).getPropertyValue('--right-rail-w')) || 0),
                        saveOpacity: saveStyle?.opacity || '',
                        themeOpacity: themeStyle?.opacity || '',
                        saveColor: saveStyle?.color || '',
                        themeColor: themeStyle?.color || '',
                        accentColor: resolveCssColor('var(--accent)'),
                        presenterTopBorderWidth: presenterTopStyle?.borderTopWidth || '',
                        inputRailBorderWidth: inputRailStyle?.borderTopWidth || '',
                        inputRailHeadBorderBottomWidth: inputRailHeadStyle?.borderBottomWidth || '',
                      };
                      saveButton?.click();
                      const afterSaveClick = {
                        sidebarVisible: sidebarIsVisible(),
                        sidebarMounted: Boolean(sidebar && !sidebar.hidden),
                        sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
                        bodyOpen: document.body.classList.contains('right-sidebar-open'),
                      };
                      themeButton?.click();
                      const afterThemeClick = {
                        sidebarVisible: sidebarIsVisible(),
                        sidebarMounted: Boolean(sidebar && !sidebar.hidden),
                        sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
                        bodyOpen: document.body.classList.contains('right-sidebar-open'),
                      };
                      return { before, afterSaveClick, afterThemeClick };
                    })()
                    """
                )
                right_sidebar_toggle_ok = (
                    not right_sidebar_toggle_state["before"]["buttonVisible"]
                    and not right_sidebar_toggle_state["before"]["saveHidden"]
                    and right_sidebar_toggle_state["before"]["saveVisible"]
                    and right_sidebar_toggle_state["before"]["themeVisible"]
                    and right_sidebar_toggle_state["before"]["saveInTopbar"]
                    and right_sidebar_toggle_state["before"]["saveTracksRightInfoBar"]
                    and not right_sidebar_toggle_state["before"]["saveInRightSidebar"]
                    and right_sidebar_toggle_state["before"]["themeInTopbar"]
                    and right_sidebar_toggle_state["before"]["themeTracksRightInfoBar"]
                    and not right_sidebar_toggle_state["before"]["themeInRightSidebar"]
                    and right_sidebar_toggle_state["before"]["headerToggleRemoved"]
                    and right_sidebar_toggle_state["before"]["presenterHeaderRemoved"]
                    and right_sidebar_toggle_state["before"]["rightSidebarHeaderRemoved"]
                    and right_sidebar_toggle_state["before"]["sidebarVisible"]
                    and right_sidebar_toggle_state["before"]["bodyOpen"]
                    and "--shell-right-w" in right_sidebar_toggle_state["before"]["bodyTransition"]
                    and "opacity" in right_sidebar_toggle_state["before"]["sidebarTransition"]
                    and right_sidebar_toggle_state["before"]["sidebarBorderLeft"] == "0px"
                    and right_sidebar_toggle_state["before"]["sidebarTop"] >= right_sidebar_toggle_state["before"]["topbarBottom"]
                    and right_sidebar_toggle_state["before"]["sidePanelWidth"] == right_sidebar_toggle_state["before"]["leftSidebarWidth"] + right_sidebar_toggle_state["before"]["rightRailWidth"]
                    and right_sidebar_toggle_state["before"]["sidebarWidth"] == right_sidebar_toggle_state["before"]["sidePanelWidth"]
                    and right_sidebar_toggle_state["before"]["topbarActionsWidth"] == right_sidebar_toggle_state["before"]["sidebarWidth"]
                    and float(right_sidebar_toggle_state["before"]["saveOpacity"]) > 0
                    and right_sidebar_toggle_state["before"]["themeOpacity"] == "1"
                    and right_sidebar_toggle_state["before"]["presenterTopBorderWidth"] == "0px"
                    and right_sidebar_toggle_state["before"]["inputRailBorderWidth"] == "0px"
                    and right_sidebar_toggle_state["before"]["inputRailHeadBorderBottomWidth"] == "0px"
                    and right_sidebar_toggle_state["afterSaveClick"]["sidebarVisible"]
                    and right_sidebar_toggle_state["afterSaveClick"]["sidebarMounted"]
                    and right_sidebar_toggle_state["afterSaveClick"]["sidebarWidth"] == right_sidebar_toggle_state["before"]["sidebarWidth"]
                    and right_sidebar_toggle_state["afterSaveClick"]["bodyOpen"]
                    and right_sidebar_toggle_state["afterThemeClick"]["sidebarVisible"]
                    and right_sidebar_toggle_state["afterThemeClick"]["sidebarMounted"]
                    and right_sidebar_toggle_state["afterThemeClick"]["sidebarWidth"] == right_sidebar_toggle_state["before"]["sidebarWidth"]
                    and right_sidebar_toggle_state["afterThemeClick"]["bodyOpen"]
                )
                if right_sidebar_toggle_ok:
                    pass_("presenter-right-sidebar-toggle", json.dumps(right_sidebar_toggle_state, ensure_ascii=False))
                else:
                    fail("presenter-right-sidebar-toggle", json.dumps(right_sidebar_toggle_state, ensure_ascii=False))

                web_output_controls_state = page.evaluate(
                    """
                    (serviceId) => {
                      const previousElectron = window.mindexElectron;
                      const previousAlwaysOnTop = state.presenter.alwaysOnTop;
                      const previousShowToast = showToast;
                      const toastMessages = [];
                      try {
                        delete window.mindexElectron;
                        state.presenter.alwaysOnTop = false;
                        showToast = (message, type) => {
                          toastMessages.push({ message, type });
                        };
                        renderPresenterControlState(serviceId);
                        const detectButton = document.querySelector('[data-presenter-action="detect-screens"]');
                        const toggle = document.querySelector('[data-presenter-always-on-top]');
                        if (toggle) {
                          toggle.checked = true;
                          toggle.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return {
                          detectVisible: Boolean(detectButton),
                          toggleVisible: Boolean(toggle),
                          unavailableClass: Boolean(toggle?.closest('.svc-presenter-pin-toggle')?.classList.contains('is-unavailable')),
                          alwaysOnTop: state.presenter.alwaysOnTop,
                          toastMessages,
                        };
                      } finally {
                        if (previousElectron === undefined) delete window.mindexElectron;
                        else window.mindexElectron = previousElectron;
                        state.presenter.alwaysOnTop = previousAlwaysOnTop;
                        showToast = previousShowToast;
                        renderPresenterControlState(serviceId);
                      }
                    }
                    """,
                    service["id"],
                )
                web_output_controls_ok = (
                    web_output_controls_state["detectVisible"]
                    and web_output_controls_state["toggleVisible"]
                    and web_output_controls_state["unavailableClass"]
                    and not web_output_controls_state["alwaysOnTop"]
                    and web_output_controls_state["toastMessages"] == [{
                        "message": "웹 버전에서는 항상 위 표시를 지원하지 않습니다.",
                        "type": "info",
                    }]
                )
                if web_output_controls_ok:
                    pass_("presenter-web-output-controls-fallback", json.dumps(web_output_controls_state, ensure_ascii=False))
                else:
                    fail("presenter-web-output-controls-fallback", json.dumps(web_output_controls_state, ensure_ascii=False))

                announcement_center_state = page.evaluate(
                    """
                    (() => {
                      const host = document.createElement('div');
                      host.style.cssText = 'position:fixed;left:-10000px;top:0;width:800px;height:450px;';
                      host.innerHTML = `
                        <section class="presenter-slide presenter-slide--liturgical-body" style="width:100%;height:100%;">
                          <div class="presenter-liturgical-body">
                            <div class="presenter-announcement-items">
                              <div class="presenter-announcement-item">
                                <span class="presenter-announcement-marker">①</span>
                                <span class="presenter-announcement-copy"><span>첫 번째 광고</span></span>
                              </div>
                              <div class="presenter-announcement-item">
                                <span class="presenter-announcement-marker">②</span>
                                <span class="presenter-announcement-copy"><span>두 번째 광고</span></span>
                              </div>
                            </div>
                          </div>
                        </section>`;
                      document.body.appendChild(host);
                      const bodyRect = host.querySelector('.presenter-liturgical-body').getBoundingClientRect();
                      const listRect = host.querySelector('.presenter-announcement-items').getBoundingClientRect();
                      const items = [...host.querySelectorAll('.presenter-announcement-item')];
                      const firstRect = items[0].getBoundingClientRect();
                      const lastRect = items[items.length - 1].getBoundingClientRect();
                      const state = {
                        bodyHeight: Math.round(bodyRect.height),
                        listHeight: Math.round(listRect.height),
                        centerDelta: Math.round(((firstRect.top + lastRect.bottom) / 2) - ((bodyRect.top + bodyRect.bottom) / 2)),
                      };
                      host.remove();
                      return state;
                    })()
                    """
                )
                if (
                    announcement_center_state["bodyHeight"] == announcement_center_state["listHeight"]
                    and abs(announcement_center_state["centerDelta"]) <= 2
                ):
                    pass_("presenter-department-announcement-vertical-center", json.dumps(announcement_center_state, ensure_ascii=False))
                else:
                    fail("presenter-department-announcement-vertical-center", json.dumps(announcement_center_state, ensure_ascii=False))

                ccm_form_order_state = page.evaluate(
                    """
                    (() => {
                      const forms = [
                        { id: 'v1', part_type: 'Verse', part_number: 1, lyrics: '첫 절' },
                        { id: 'c', part_type: 'Chorus', lyrics: '후렴' },
                        { id: 'v2', part_type: 'Verse', part_number: 2, lyrics: '둘째 절' },
                      ];
                      const song = { metadata: { presenter_form: { forms: ['V1', 'C', 'V2', 'C'] } } };
                      const suggestedItem = { memo: JSON.stringify({ formPreset: { forms: ['V1', 'C'], strength: 'suggested' } }) };
                      const forcedItem = { memo: JSON.stringify({ formPreset: { forms: ['V1', 'C', 'V1'], strength: 'default' } }) };
                      const disabledItem = { memo: JSON.stringify({ formPresetDisabled: true }) };
                      const groupedItem = { memo: JSON.stringify({ formPreset: { forms: ['V1A', 'V1B'], strength: 'default' } }) };
                      const groupedForms = [
                        { id: 'gv1', part_type: 'Verse', part_number: 1, lyrics: '1행\\n2행\\n3행\\n4행\\n5행\\n6행\\n7행\\n8행' },
                      ];
                      const groupedPlan = presenterFormPlanForServiceItem({ forms: groupedForms }, groupedItem, song);
                      const specialHymnForms = [
                        { id: 'sv1', part_type: 'Verse', part_number: 1, lyrics: '특송 1절' },
                        { id: 'sc', part_type: 'Chorus', lyrics: '특송 후렴' },
                        { id: 'sv2', part_type: 'Verse', part_number: 2, lyrics: '특송 2절' },
                        { id: 'si', part_type: 'Interlude', lyrics: '특송 간주' },
                        { id: 'sv4', part_type: 'Verse', part_number: 4, lyrics: '특송 4절' },
                      ];
                      const specialHymnItem = {
                        label: '특송',
                        _worshipSectionKey: 'special_song',
                        _worshipSectionTitle: '특송',
                        memo: JSON.stringify({ elementType: 'praise' }),
                      };
                      const specialHymnSong = { hymn_no: '430', versions: [{ id: 'special-hymn-version', forms: specialHymnForms }] };
                      const specialHymnWithoutChorusForms = specialHymnForms.filter((form) => form.part_type !== 'Chorus');
                      const specialHymnWithoutChorusPlan = presenterFormPlanForServiceItem(
                        { forms: specialHymnWithoutChorusForms },
                        specialHymnItem,
                        { hymn_no: '323', versions: [{ id: 'special-hymn-no-chorus-version', forms: specialHymnWithoutChorusForms }] },
                      );
                      return {
                        metadataOrder: presenterFormPlanForServiceItem({ forms }, suggestedItem, song).forms.map((form) => form.id),
                        disabledOrder: presenterFormPlanForServiceItem({ forms }, disabledItem, song).forms.map((form) => form.id),
                        inferredOrder: presenterFormPlanForServiceItem({ forms }, { memo: '' }, {}).forms.map((form) => form.id),
                        forcedOrder: presenterFormPlanForServiceItem({ forms }, forcedItem, song).forms.map((form) => form.id),
                        groupedLabels: groupedPlan.forms.map((form) => presenterFormDisplayLabel(form)),
                        groupedLyrics: groupedPlan.forms.map((form) => form.lyrics),
                        specialHymnOrder: presenterFormPlanForServiceItem(
                          { forms: specialHymnForms },
                          specialHymnItem,
                          specialHymnSong,
                        ).forms.map((form) => form.id),
                        specialHymnLabels: presenterFormPlanForServiceItem(
                          { forms: specialHymnForms },
                          specialHymnItem,
                          specialHymnSong,
                        ).forms.map((form) => presenterResolvedFormMarker(form)),
                        specialHymnWithoutChorusWarnings: specialHymnWithoutChorusPlan.warnings,
                      };
                    })()
                    """
                )
                if ccm_form_order_state == {
                    "metadataOrder": ["v1", "c", "v2", "c"],
                    "disabledOrder": ["v1", "c", "v2"],
                    "inferredOrder": ["v1", "c", "v2", "c"],
                    "forcedOrder": ["v1", "c", "v1"],
                    "groupedLabels": ["V1A", "V1B"],
                    "groupedLyrics": ["1행\n2행\n3행\n4행", "5행\n6행\n7행\n8행"],
                    "specialHymnOrder": ["sv1", "sc", "sv2", "sc", "preset-blank:instrumental", "sv4", "sc"],
                    "specialHymnLabels": ["1절", "Chorus", "2절", "Chorus", "Instrumental", "마지막 절", "Chorus"],
                    "specialHymnWithoutChorusWarnings": [],
                }:
                    pass_("presenter-ccm-repeats-chorus", json.dumps(ccm_form_order_state, ensure_ascii=False))
                else:
                    fail("presenter-ccm-repeats-chorus", json.dumps(ccm_form_order_state, ensure_ascii=False))

                praise_exact_title_priority_state = page.evaluate(
                    """
                    (() => {
                      const previousSongs = state.songs;
                      const makeSong = (id, title, praiseTypes, hymnNo = '') => ({
                        id,
                        title,
                        hymn_no: hymnNo,
                        praise_types: praiseTypes,
                        versions: [{
                          id: `${id}:v1`,
                          name: '기본',
                          is_primary: true,
                          praise_types: praiseTypes,
                          forms: [{ id: `${id}:f1`, lyrics: '가사' }],
                        }],
                      });
                      try {
                        state.songs = [
                          makeSong('__smoke_dup_children__', '완전 같은 제목', ['children']),
                          makeSong('__smoke_dup_ccm__', '완전 같은 제목', ['ccm']),
                          makeSong('__smoke_dup_hymn__', '완전 같은 제목', ['hymn'], '321'),
                          makeSong('__smoke_dup_children_only__', '찬송가 없는 제목', ['children']),
                          makeSong('__smoke_dup_ccm_only__', '찬송가 없는 제목', ['ccm']),
                        ];
                        return {
                          withHymn: findServicePraiseSong('완전 같은 제목')?.id || '',
                          withoutHymn: findServicePraiseSong('찬송가 없는 제목')?.id || '',
                        };
                      } finally {
                        state.songs = previousSongs;
                        state.songLookupSource = null;
                      }
                    })()
                    """
                )
                if praise_exact_title_priority_state == {
                    "withHymn": "__smoke_dup_hymn__",
                    "withoutHymn": "__smoke_dup_ccm_only__",
                }:
                    pass_("presenter-praise-exact-title-priority", json.dumps(praise_exact_title_priority_state, ensure_ascii=False))
                else:
                    fail("presenter-praise-exact-title-priority", json.dumps(praise_exact_title_priority_state, ensure_ascii=False))

                sticky_title_state: dict[str, Any] = page.evaluate(
                    """
                    async () => {
                      const pane = document.querySelector('.detail-pane');
                      const header = document.querySelector('.svc-header');
                      const presenterHeader = document.querySelector('.presenter-viewer .svc-header');
                      const board = document.querySelector('#servicePresenterControls');
                      const rightSidebar = document.querySelector('#mindexRightSidebar');
                      const top = rightSidebar?.querySelector('.svc-presenter-top');
                      const sidebarContext = document.querySelector('.service-sidebar-presenter-context');
                      const title = sidebarContext?.querySelector('.service-sidebar-presenter-title');
                      const date = sidebarContext?.querySelector('.service-sidebar-presenter-date');
                      const beforeHeader = header?.getBoundingClientRect();
                      const beforeBoard = board?.getBoundingClientRect();
                      const beforeTop = top?.getBoundingClientRect();
                      if (pane) pane.scrollTop = 260;
                      document.scrollingElement.scrollTop = 260;
                      await new Promise((resolve) => requestAnimationFrame(resolve));
                      const currentHeader = document.querySelector('.svc-header');
                      const currentPresenterHeader = document.querySelector('.presenter-viewer .svc-header');
                      const currentBoard = document.querySelector('#servicePresenterControls');
                      const currentRightSidebar = document.querySelector('#mindexRightSidebar');
                      const currentTop = currentRightSidebar?.querySelector('.svc-presenter-top');
                      const currentSidePanel = currentRightSidebar?.querySelector('.svc-presenter-side-panel');
                      const currentSidebarContext = document.querySelector('.service-sidebar-presenter-context');
                      const sidebarSearch = document.querySelector('.sidebar-search-wrap');
                      const currentTitle = currentSidebarContext?.querySelector('.service-sidebar-presenter-title');
                      const currentDate = currentSidebarContext?.querySelector('.service-sidebar-presenter-date');
                      const sidebarLaunch = currentSidebarContext?.querySelector('.svc-presenter-launch--sidebar');
                      const contextRect = currentSidebarContext?.getBoundingClientRect();
                      const searchRect = sidebarSearch?.getBoundingClientRect();
                      const pageTabs = document.querySelector('.page-tabs');
                      const titleStyle = currentTitle ? getComputedStyle(currentTitle) : null;
                      const dateStyle = currentDate ? getComputedStyle(currentDate) : null;
                      const controllerTitle = document.querySelector('.presenter-viewer .svc-service-title');
                      const controllerDate = document.querySelector('.presenter-viewer .svc-date-text');
                      const afterHeader = currentHeader?.getBoundingClientRect();
                      const afterBoard = currentBoard?.getBoundingClientRect();
                      const afterTop = currentTop?.getBoundingClientRect();
                      const beforeHeaderTop = Math.round(beforeHeader?.top || 0);
                      const afterHeaderTop = Math.round(afterHeader?.top || 0);
                      const beforeBoardTop = Math.round(beforeBoard?.top || 0);
                      const afterBoardTop = Math.round(afterBoard?.top || 0);
                      const beforeControlsTop = Math.round(beforeTop?.top || 0);
                      const afterControlsTop = Math.round(afterTop?.top || 0);
                      return {
                        title: currentTitle?.textContent.trim() || title?.textContent.trim() || '',
                        date: currentDate?.textContent.trim() || date?.textContent.trim() || '',
                        titleFontSize: parseFloat(titleStyle?.fontSize || '0'),
                        titleFontWeight: titleStyle?.fontWeight || '',
                        dateFontSize: parseFloat(dateStyle?.fontSize || '0'),
                        dateFontWeight: dateStyle?.fontWeight || '',
                        contextBackground: currentSidebarContext ? getComputedStyle(currentSidebarContext).backgroundColor : '',
                        contextLeft: Math.round(contextRect?.left || 0),
                        searchLeft: Math.round(searchRect?.left || 0),
                        contextWidth: Math.round(contextRect?.width || 0),
                        searchWidth: Math.round(searchRect?.width || 0),
                        sidebarLaunch: {
                          exists: Boolean(sidebarLaunch),
                          action: sidebarLaunch?.dataset.presenterAction || '',
                          label: sidebarLaunch?.querySelector('span')?.textContent.trim() || '',
                          icon: sidebarLaunch?.querySelector('svg')?.getAttribute('data-lucide') || '',
                          width: Math.round(sidebarLaunch?.getBoundingClientRect().width || 0),
                        },
                        pageTabsVisible: pageTabs ? getComputedStyle(pageTabs).visibility !== 'hidden' && getComputedStyle(pageTabs).opacity !== '0' : false,
                        rightSidebarTopGap: currentRightSidebar
                          ? Math.round((currentTop?.getBoundingClientRect().top || 0) - currentRightSidebar.getBoundingClientRect().top)
                          : 0,
                        topbarButtonSize: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--topbar-btn-size')) || 0,
                        usesSidebarTitle: Boolean((currentTitle || title)?.closest('.service-sidebar-presenter-context') && !document.querySelector('.svc-presenter-title-row')),
                        controllerTitleRemoved: !controllerTitle && !controllerDate,
                        presenterHeaderRemoved: !presenterHeader && !currentPresenterHeader,
                        headerPosition: currentHeader ? getComputedStyle(currentHeader).position : '',
                        controlsPosition: currentTop ? getComputedStyle(currentTop).position : '',
                        sidePanelPosition: currentSidePanel ? getComputedStyle(currentSidePanel).position : '',
                        sidePanelDisplay: currentSidePanel ? getComputedStyle(currentSidePanel).display : '',
                        rightSidebarVisible: Boolean(currentRightSidebar && !currentRightSidebar.hidden),
                        beforeHeaderTop,
                        afterHeaderTop,
                        headerShift: Math.abs(afterHeaderTop - beforeHeaderTop),
                        beforeBoardTop,
                        afterBoardTop,
                        beforeControlsTop,
                        afterControlsTop,
                        controlsShift: Math.abs(afterControlsTop - beforeControlsTop),
                        overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth)
                      };
                    }
                    """
                )
                if (
                    sticky_title_state["title"]
                    and sticky_title_state["date"]
                    and re.match(r"^\d{4}-\d{2}-\d{2} \((주일|월|화|수|목|금|토)\)", sticky_title_state["date"])
                    and sticky_title_state["usesSidebarTitle"]
                    and sticky_title_state["controllerTitleRemoved"]
                    and sticky_title_state["presenterHeaderRemoved"]
                    and sticky_title_state["titleFontSize"] >= 18
                    and int(sticky_title_state["titleFontWeight"]) >= 800
                    and sticky_title_state["dateFontSize"] >= 13
                    and int(sticky_title_state["dateFontWeight"]) >= 700
                    and sticky_title_state["contextBackground"] != "rgba(0, 0, 0, 0)"
                    and abs(sticky_title_state["contextLeft"] - sticky_title_state["searchLeft"]) <= 1
                    and abs(sticky_title_state["contextWidth"] - sticky_title_state["searchWidth"]) <= 1
                    and sticky_title_state["sidebarLaunch"]["exists"]
                    and sticky_title_state["sidebarLaunch"]["action"] in ("open", "stop")
                    and sticky_title_state["sidebarLaunch"]["label"] in ("송출 시작", "송출 종료")
                    and sticky_title_state["sidebarLaunch"]["icon"] in ("screen-share", "screen-share-off")
                    and sticky_title_state["sidebarLaunch"]["width"] >= 90
                    and sticky_title_state["pageTabsVisible"]
                    and 8 <= sticky_title_state["rightSidebarTopGap"] <= 28
                    and sticky_title_state["rightSidebarVisible"]
                    and sticky_title_state["controlsPosition"] == "static"
                    and sticky_title_state["sidePanelPosition"] == "static"
                    and sticky_title_state["sidePanelDisplay"] == "grid"
                    and sticky_title_state["headerShift"] <= 2
                    and sticky_title_state["beforeBoardTop"] <= 96
                    and sticky_title_state["controlsShift"] <= 2
                    and sticky_title_state["overflow"] <= 2
                ):
                    pass_("presenter-sticky-service-title", json.dumps(sticky_title_state, ensure_ascii=False))
                else:
                    fail("presenter-sticky-service-title", json.dumps(sticky_title_state, ensure_ascii=False))

                sidebar_launch_click_state = page.evaluate(
                    """
                    async () => {
                      const serviceId = state.selectedServiceId;
                      let openCall = null;
                      const originalOpen = window.open;
                      const originalHydrate = hydratePresenterOutputInBackground;
                      window.open = (url, name, features) => {
                        openCall = { url, name, features };
                        return {
                          closed: false,
                          focus() {},
                          addEventListener() {},
                        };
                      };
                      hydratePresenterOutputInBackground = () => {};
                      state.presenter.outputWindow = null;
                      state.presenter.outputConnectedAt = 0;
                      renderPresenterSidebar();
                      const button = document.querySelector('.service-sidebar-presenter-context [data-presenter-action="open"]');
                      button?.click();
                      await new Promise((resolve) => setTimeout(resolve, 40));
                      const stopButton = document.querySelector('.service-sidebar-presenter-context .svc-presenter-launch--sidebar');
                      const stopState = {
                        action: stopButton?.dataset.presenterAction || '',
                        label: stopButton?.querySelector('span')?.textContent.trim() || '',
                        icon: stopButton?.querySelector('svg')?.getAttribute('data-lucide') || '',
                      };
                      stopButton?.click();
                      await new Promise((resolve) => setTimeout(resolve, 40));
                      const restartButton = document.querySelector('.service-sidebar-presenter-context .svc-presenter-launch--sidebar');
                      const restartState = {
                        action: restartButton?.dataset.presenterAction || '',
                        label: restartButton?.querySelector('span')?.textContent.trim() || '',
                        icon: restartButton?.querySelector('svg')?.getAttribute('data-lucide') || '',
                      };
                      window.open = originalOpen;
                      hydratePresenterOutputInBackground = originalHydrate;
                      const presenterServiceId = state.presenter.serviceId || '';
                      state.presenter.outputWindow = null;
                      state.presenter.outputPendingAt = 0;
                      state.presenter.outputConnectedAt = 0;
                      state.presenter.outputStopAt = 0;
                      state.presenter.outputStoppingClientId = '';
                      state.presenter.outputClientId = '';
                      return {
                        hasButton: Boolean(button),
                        serviceId,
                        action: button?.dataset.presenterAction || '',
                        openCalled: Boolean(openCall),
                        url: openCall?.url || '',
                        presenterServiceId,
                        stopState,
                        restartState,
                      };
                    }
                    """
                )
                if (
                    sidebar_launch_click_state["hasButton"]
                    and sidebar_launch_click_state["action"] == "open"
                    and sidebar_launch_click_state["openCalled"]
                    and sidebar_launch_click_state["presenterServiceId"] == sidebar_launch_click_state["serviceId"]
                    and "output=presenter" in sidebar_launch_click_state["url"]
                    and sidebar_launch_click_state["stopState"]["action"] == "stop"
                    and sidebar_launch_click_state["stopState"]["label"] == "송출 종료"
                    and sidebar_launch_click_state["stopState"]["icon"] == "screen-share-off"
                    and sidebar_launch_click_state["restartState"]["action"] == "open"
                    and sidebar_launch_click_state["restartState"]["label"] == "송출 시작"
                    and sidebar_launch_click_state["restartState"]["icon"] == "screen-share"
                ):
                    pass_("presenter-sidebar-launch-click", json.dumps(sidebar_launch_click_state, ensure_ascii=False))
                else:
                    fail("presenter-sidebar-launch-click", json.dumps(sidebar_launch_click_state, ensure_ascii=False))

                pending_click_state = page.evaluate(
                    """
                    async () => {
                      const serviceId = state.selectedServiceId;
                      state.presenter.outputWindow = null;
                      state.presenter.outputPendingAt = 0;
                      state.presenter.outputConnectedAt = 0;
                      state.presenter.outputBlockedAt = 0;
                      state.presenter.outputStopAt = 0;
                      state.presenter.outputStoppingClientId = '';
                      state.presenter.outputClientId = '';
                      state.presenter.serviceId = null;
                      state.presenter.index = 0;
                      state.presenter.jumpDraft = "";
                      renderPresenterDetail();
                      await new Promise((resolve) => requestAnimationFrame(resolve));
                      const thumb = document.querySelector(`.svc-slide-thumb[data-service-id="${serviceId}"][data-presenter-index="2"]`);
                      thumb?.click();
                      await new Promise((resolve) => requestAnimationFrame(resolve));
                      const input = document.querySelector(`.svc-slide-jump-input[data-service-id="${serviceId}"]`);
                      const selectedThumb = document.querySelector('.svc-slide-thumb.selected');
                      return {
                        hasThumb: Boolean(thumb),
                        serviceId,
                        presenterServiceId: state.presenter.serviceId || '',
                        presenterIndex: state.presenter.index,
                        jumpDraft: state.presenter.jumpDraft || '',
                        inputValue: input?.value || '',
                        selectedIndex: Number(selectedThumb?.dataset.presenterIndex ?? -1),
                        outputOpen: Boolean(state.presenter.outputWindow),
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      };
                    }
                    """
                )
                if (
                    pending_click_state["hasThumb"]
                    and pending_click_state["presenterServiceId"] == pending_click_state["serviceId"]
                    and pending_click_state["presenterIndex"] == 2
                    and pending_click_state["inputValue"] == "3"
                    and pending_click_state["selectedIndex"] == 2
                    and not pending_click_state["outputOpen"]
                    and pending_click_state["status"] == "준비"
                ):
                    pass_("presenter-pending-slide-click", json.dumps(pending_click_state, ensure_ascii=False))
                else:
                    fail("presenter-pending-slide-click", json.dumps(pending_click_state, ensure_ascii=False))

                page.evaluate(
                    """
	                    (serviceId) => {
	                      preparePresenterService(serviceId);
	                      state.presenter.outputConnectedAt = Date.now();
	                      renderPresenterControlState(serviceId);
	                    }
                    """,
                    service["id"],
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

                fast_jump_state = page.evaluate(
                    """
	                    async (serviceId) => {
	                      preparePresenterService(serviceId);
	                      state.presenter.outputWindow = null;
	                      state.presenter.outputConnectedAt = 0;
	                      renderPresenterControlState(serviceId);
                      const detail = refs.detailPane || document.getElementById('detailPane');
                      const targetIndex = Math.min(18, Math.max(state.presenter.slides.length - 1, 0));
                      detail.scrollTop = 320;
                      const scrollBefore = detail.scrollTop;
	                      const boardBefore = document.querySelector('.svc-slide-board');
	                      const thumb = document.querySelector(`.svc-slide-thumb[data-service-id="${serviceId}"][data-presenter-index="${targetIndex}"]`);
	                      const originalScrollIntoView = Element.prototype.scrollIntoView;
	                      let scrolledIndex = -1;
	                      Element.prototype.scrollIntoView = function scrollIntoView() {
	                        scrolledIndex = Number(this.dataset?.presenterIndex ?? -1);
	                      };
	                      const startedAt = performance.now();
	                      thumb?.click();
	                      const immediateIndex = state.presenter.index;
	                      await new Promise((resolve) => requestAnimationFrame(resolve));
	                      Element.prototype.scrollIntoView = originalScrollIntoView;
                      const boardAfter = document.querySelector('.svc-slide-board');
                      const selectedThumb = document.querySelector('.svc-slide-thumb.selected');
                      const input = document.querySelector(`.svc-slide-jump-input[data-service-id="${serviceId}"]`);
                      const result = {
                        targetIndex,
                        immediateIndex,
                        inputValue: input?.value || '',
                        elapsedMs: Number((performance.now() - startedAt).toFixed(2)),
                        sameBoard: boardBefore === boardAfter,
                        scrollBefore,
                        scrollAfter: detail.scrollTop,
	                        selectedIndex: Number(selectedThumb?.dataset.presenterIndex ?? -1),
	                        scrolledIndex,
                      };
                      state.presenter.index = 0;
                      state.presenter.safetyBlank = false;
                      renderPresenterControlState(serviceId);
                      return result;
                    }
                    """,
                    service["id"],
                )
                if (
                    fast_jump_state["immediateIndex"] == fast_jump_state["targetIndex"]
                    and fast_jump_state["inputValue"] == str(fast_jump_state["targetIndex"] + 1)
                    and fast_jump_state["selectedIndex"] == fast_jump_state["targetIndex"]
                    and fast_jump_state["scrolledIndex"] in (-1, fast_jump_state["targetIndex"])
                    and fast_jump_state["sameBoard"]
                    and fast_jump_state["elapsedMs"] < 120
                ):
                    pass_("presenter-thumb-click-updates-pending", json.dumps(fast_jump_state, ensure_ascii=False))
                else:
                    fail("presenter-thumb-click-updates-pending", json.dumps(fast_jump_state, ensure_ascii=False))

                outline_follow_state = page.evaluate(
                    """
                    async (serviceId) => {
                      const targetIndex = Math.min(24, Math.max(state.presenter.slides.length - 1, 0));
                      const originalScrollIntoView = Element.prototype.scrollIntoView;
                      const previousConnectedAt = state.presenter.outputConnectedAt;
                      const previousStopAt = state.presenter.outputStopAt;
                      state.presenter.outputConnectedAt = Date.now();
                      state.presenter.outputStopAt = 0;
                      const calls = [];
                      Element.prototype.scrollIntoView = function scrollIntoView(options) {
                        if (this.classList?.contains('service-outline-row')) {
                          calls.push({
                            classes: this.className,
                            slide: Number(this.dataset.serviceOutlineSlide ?? -1),
                            block: options?.block || '',
                          });
                        }
                      };
                      runPresenterAction('jump', serviceId, { index: targetIndex });
                      await new Promise((resolve) => setTimeout(resolve, 950));
                      Element.prototype.scrollIntoView = originalScrollIntoView;
                      const result = {
                        targetIndex,
                        presenterIndex: state.presenter.index,
                        calls,
                        activeRows: document.querySelectorAll('.service-outline-row.active').length,
                      };
                      state.presenter.outputConnectedAt = previousConnectedAt;
                      state.presenter.outputStopAt = previousStopAt;
                      state.presenter.index = 0;
                      state.presenter.safetyBlank = false;
                      renderPresenterControlState(serviceId);
                      return result;
                    }
                    """,
                    service["id"],
                )
                if (
                    outline_follow_state["presenterIndex"] == outline_follow_state["targetIndex"]
                    and outline_follow_state["activeRows"] >= 1
                ):
                    pass_("presenter-outline-follows-live-transition", json.dumps(outline_follow_state, ensure_ascii=False))
                else:
                    fail("presenter-outline-follows-live-transition", json.dumps(outline_follow_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      document
                        .querySelector(`.svc-slide-thumb[data-service-id="${serviceId}"][data-presenter-index="1"] .svc-slide-thumb-frame`)
                        ?.scrollIntoView({ block: 'center', inline: 'nearest' });
                    }
                    """,
                    service["id"],
                )
                page.wait_for_timeout(80)
                hover_frame = page.locator(f'.svc-slide-thumb[data-service-id="{service["id"]}"][data-presenter-index="1"] .svc-slide-thumb-frame').first
                hover_frame.hover()
                page.wait_for_timeout(120)
                hover_state = page.evaluate(
                    """
                    (serviceId) => {
                      const frame = document.querySelector(`.svc-slide-thumb[data-service-id="${serviceId}"][data-presenter-index="1"] .svc-slide-thumb-frame`);
                      return {
                        exists: Boolean(frame),
                        hovered: Boolean(frame?.matches(':hover')),
                        filter: frame ? getComputedStyle(frame).filter : '',
                        shadow: frame ? getComputedStyle(frame).boxShadow : '',
                        outline: frame ? getComputedStyle(frame).outlineStyle : '',
                        outlineWidth: frame ? getComputedStyle(frame).outlineWidth : '',
                      };
                    }
                    """,
                    service["id"],
                )
                hover_has_no_ring = hover_state["outline"] == "none" or hover_state["outlineWidth"] == "0px"
                if hover_state["exists"] and hover_state["hovered"] and hover_has_no_ring and "brightness" in hover_state["filter"]:
                    pass_("presenter-thumb-hover-brightness", json.dumps(hover_state, ensure_ascii=False))
                else:
                    fail("presenter-thumb-hover-brightness", json.dumps(hover_state, ensure_ascii=False))
                page.mouse.move(0, 0)

                page.evaluate(
                    """
                    (serviceId) => {
                      state.presenter.outputWindow = null;
                      state.presenter.outputConnectedAt = 0;
                      renderPresenterControlState(serviceId);
                    }
                    """,
                    service["id"],
                )
                ready_status = page.evaluate(
                    """
                    (() => ({
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                    }))()
                    """
                )
                if ready_status["status"] == "준비" and ready_status["mode"].endswith("번"):
                    pass_("presenter-status-ready", json.dumps(ready_status, ensure_ascii=False))
                else:
                    fail("presenter-status-ready", json.dumps(ready_status, ensure_ascii=False))

                warmup_chip_state = page.evaluate(
                    """
                    (serviceId) => {
                      const previousConnectedAt = state.presenter.outputConnectedAt;
                      const previousWarmup = state.presenter.outputWarmup;
                      const previousClientId = state.presenter.outputClientId;
                      const previousStopAt = state.presenter.outputStopAt;
                      const previousServiceId = state.presenter.serviceId;
                      state.presenter.serviceId = serviceId;
                      state.presenter.outputStopAt = 0;
                      state.presenter.outputConnectedAt = Date.now();
                      state.presenter.outputClientId = '__smoke_output__';
                      state.presenter.outputWarmup = {
                        serviceId,
                        total: 12,
                        ready: 7,
                        queued: 5,
                        complete: false,
                        updatedAt: Date.now(),
                      };
                      const service = state.services.find((entry) => entry.id === serviceId);
                      const slides = presenterSlidesForService(serviceId);
                      const root = document.querySelector('#mindexRightSidebar [data-presenter-right-sidebar]');
                      patchPresenterControlsTop(root, service, slides, true, state.presenter.index);
                      const warming = document.querySelector('.svc-presenter-warmup');
                      const warmingState = {
                        text: warming?.textContent.trim() || '',
                        className: warming?.className || '',
                        aria: warming?.getAttribute('aria-label') || '',
                      };
                      state.presenter.outputWarmup = {
                        serviceId,
                        total: 12,
                        ready: 12,
                        queued: 0,
                        complete: true,
                        updatedAt: Date.now(),
                      };
                      patchPresenterControlsTop(root, service, slides, true, state.presenter.index);
                      const ready = document.querySelector('.svc-presenter-warmup');
                      const readyState = {
                        text: ready?.textContent.trim() || '',
                        className: ready?.className || '',
                        aria: ready?.getAttribute('aria-label') || '',
                      };
                      state.presenter.outputConnectedAt = previousConnectedAt;
                      state.presenter.outputWarmup = previousWarmup;
                      state.presenter.outputClientId = previousClientId;
                      state.presenter.outputStopAt = previousStopAt;
                      state.presenter.serviceId = previousServiceId;
                      renderPresenterControlState(serviceId);
                      return { warming: warmingState, ready: readyState };
                    }
                    """,
                    service["id"],
                )
                if (
                    warmup_chip_state["warming"]["text"] == "이미지 준비 7/12"
                    and "svc-presenter-warmup--warming" in warmup_chip_state["warming"]["className"]
                    and "7 / 12" in warmup_chip_state["warming"]["aria"]
                    and warmup_chip_state["ready"]["text"] == "이미지 준비 완료"
                    and "svc-presenter-warmup--ready" in warmup_chip_state["ready"]["className"]
                    and warmup_chip_state["ready"]["aria"] == "출력 이미지 준비 완료"
                ):
                    pass_("presenter-output-warmup-chip", json.dumps(warmup_chip_state, ensure_ascii=False))
                else:
                    fail("presenter-output-warmup-chip", json.dumps(warmup_chip_state, ensure_ascii=False))

                ready_thumb_state = page.evaluate(
                    """
                    (() => {
	                      const first = document.querySelector('.svc-slide-thumb[data-presenter-index="0"]');
	                      const second = document.querySelector('.svc-slide-thumb[data-presenter-index="1"]');
	                      const firstWrap = first?.closest('.svc-slide-thumb-wrap');
	                      const firstNumber = firstWrap?.querySelector('.svc-slide-thumb-no');
	                      const firstFrame = first?.querySelector('.svc-slide-thumb-frame');
	                      const numberRect = firstNumber?.getBoundingClientRect();
	                      const frameRect = firstFrame?.getBoundingClientRect();
	                      return {
	                        firstPreparationMedia: Boolean(first?.querySelector('.svc-slide-thumb-frame--video[data-element-type="video"][data-slide-layout="media"]')),
	                        firstPreviewVideo: Boolean(first?.querySelector('.svc-slide-mini-output video.presenter-video')),
	                        firstPreviewText: first?.querySelector('.svc-slide-mini-output')?.innerText.trim() || '',
	                        firstGeneratedWaitingLoop: Boolean(first?.querySelector('.presenter-waiting-loop')),
	                        numberBadges: document.querySelectorAll('.svc-slide-thumb-no').length,
	                        firstNumber: firstNumber?.textContent.trim() || '',
	                        secondNumber: second?.closest('.svc-slide-thumb-wrap')?.querySelector('.svc-slide-thumb-no')?.textContent.trim() || '',
	                        firstLabel: first?.getAttribute('aria-label') || '',
	                        secondLabel: second?.getAttribute('aria-label') || '',
	                        numberOutsidePreview: Boolean(numberRect && frameRect && numberRect.bottom <= frameRect.top),
	                      };
	                    })()
                    """
                )
                if (
                    ready_thumb_state["firstPreparationMedia"]
                    and ready_thumb_state["firstPreviewVideo"]
                    and ready_thumb_state["firstPreviewText"] == ""
                    and ready_thumb_state["numberBadges"] >= 2
	                    and ready_thumb_state["firstNumber"] == "1"
	                    and ready_thumb_state["secondNumber"] == "2"
	                    and any(
	                        ready_thumb_state["firstLabel"].startswith(prefix)
	                        for prefix in ("1번 슬라이드 선택:", "1번 슬라이드 선택 · 더블클릭해 송출:")
	                    )
	                    and any(
	                        ready_thumb_state["secondLabel"].startswith(prefix)
	                        for prefix in ("2번 슬라이드 선택:", "2번 슬라이드 선택 · 더블클릭해 송출:")
	                    )
	                    and ready_thumb_state["numberOutsidePreview"]
	                ):
                    pass_("presenter-ready-thumb-chrome", json.dumps(ready_thumb_state, ensure_ascii=False))
                else:
                    fail("presenter-ready-thumb-chrome", json.dumps(ready_thumb_state, ensure_ascii=False))

                intro_auto_advance_state = page.evaluate(
                    """
                    async () => {
                      const existingRoot = document.getElementById('presenterOutputRoot');
                      existingRoot?.remove();
                      const root = document.createElement('main');
                      root.id = 'presenterOutputRoot';
                      root.className = 'presenter-output-root no-chromakey';
                      document.body.appendChild(root);
                      const hits = [];
                      const makePayload = (role, playback = {}) => ({
                        serviceId: '__smoke_intro_service__',
                        serviceType: 'friday',
                        serviceDate: '2026-07-12',
                        chromakey: false,
                        backgroundImages: [],
                        index: 0,
                        slides: [
                          {
                            id: `__smoke_${role}_slide__`,
                            elementType: 'video',
                            layout: 'media',
                            type: 'video',
                            presenterRole: role,
                            title: role,
                            videoSrc: '/',
                            playback,
                          },
                          {
                            id: '__smoke_after_intro__',
                            elementType: 'title_assignee',
                            layout: 'lower_bar_text',
                            type: 'title-assignee',
                            title: '예배',
                            assignee: '',
                            text: '예배',
                          },
                        ],
                      });
                      const fireEnded = (payload) => {
                        renderPresenterOutput(payload, { onAutoAdvance: (detail) => hits.push(detail) });
                        const video = root.querySelector('.presenter-output-layer.is-active video.presenter-video');
                        video?.dispatchEvent(new Event('ended'));
                        return {
                          hitCount: hits.length,
                          videoRole: video?.dataset.presenterRole || '',
                          autoplay: video?.hasAttribute('autoplay') || false,
                          muted: video?.hasAttribute('muted') || false,
                          loop: video?.hasAttribute('loop') || false,
                          detail: hits[hits.length - 1] || null,
                        };
                      };
                      const introSlide = makePayload('intro').slides[0];
                      const waitingSlide = makePayload('waiting_loop', { loop: true }).slides[0];
                      const introLoopSlide = makePayload('intro', { loop: true }).slides[0];
                      const intro = fireEnded(makePayload('intro'));
                      hits.length = 0;
                      const waiting = fireEnded(makePayload('waiting_loop', { loop: true }));
                      hits.length = 0;
                      const introLoop = fireEnded(makePayload('intro', { loop: true }));
                      hits.length = 0;
                      const scheduledPastPayload = makePayload('waiting_loop', {
                        loop: true,
                        autoAdvanceAt: new Date(Date.now() - 1000).toISOString(),
                      });
                      renderPresenterOutput(scheduledPastPayload, { onAutoAdvance: (detail) => hits.push(detail) });
                      await new Promise((resolve) => setTimeout(resolve, 30));
                      const scheduledPast = {
                        hitCount: hits.length,
                        detail: hits[hits.length - 1] || null,
                      };
                      hits.length = 0;
                      const scheduledFuturePayload = makePayload('waiting_loop', {
                        loop: true,
                        autoAdvanceAt: new Date(Date.now() + 60000).toISOString(),
                      });
                      renderPresenterOutput(scheduledFuturePayload, { onAutoAdvance: (detail) => hits.push(detail) });
                      await new Promise((resolve) => setTimeout(resolve, 30));
                      const scheduledFuture = {
                        hitCount: hits.length,
                        timerArmed: Boolean(presenterOutputRenderState.autoAdvanceTimer),
                      };
                      const parsedClock = parsePresenterAutoAdvanceAt('10:40', '2026-07-12');
                      const timelinePayload = {
                        serviceId: '__smoke_timeline_service__',
                        serviceType: 'friday',
                        serviceDate: '2026-07-12',
                        chromakey: false,
                        index: 1,
                        slides: [
                          {
                            id: '__smoke_waiting_timeline__',
                            elementType: 'video',
                            layout: 'media',
                            presenterRole: 'waiting_loop',
                            playback: { autoAdvanceAt: '10:40' },
                          },
                          {
                            id: '__smoke_intro_timeline__',
                            elementType: 'video',
                            layout: 'media',
                            presenterRole: 'intro',
                            playback: { durationSeconds: 600 },
                          },
                          {
                            id: '__smoke_first_screen__',
                            elementType: 'title_assignee',
                            layout: 'lower_bar_text',
                            title: '예배 시작',
                            text: '예배 시작',
                          },
                        ],
                      };
                      const timelineIntro = timelinePayload.slides[1];
                      const catchUpMid = presenterVideoTimelineCatchUp(timelineIntro, timelinePayload, {
                        now: new Date('2026-07-12T10:44:00').getTime(),
                        durationSeconds: 600,
                      });
                      const catchUpDone = presenterVideoTimelineCatchUp(timelineIntro, timelinePayload, {
                        now: new Date('2026-07-12T10:54:00').getTime(),
                        durationSeconds: 600,
                      });
                      const endAtPayload = {
                        ...timelinePayload,
                        slides: [
                          timelinePayload.slides[0],
                          {
                            ...timelineIntro,
                            playback: { autoAdvanceAt: '10:50', durationSeconds: 600 },
                          },
                        ],
                      };
                      const catchUpFromEndAt = presenterVideoTimelineCatchUp(endAtPayload.slides[1], endAtPayload, {
                        now: new Date('2026-07-12T10:45:00').getTime(),
                        durationSeconds: 600,
                      });
                      clearPresenterOutputAutoAdvanceTimer();
                      root.remove();
                      if (existingRoot) document.body.appendChild(existingRoot);
                      return {
                        intro,
                        waiting,
                        introLoop,
                        scheduledPast,
                        scheduledFuture,
                        parsedClock: parsedClock ? {
                          year: parsedClock.getFullYear(),
                          month: parsedClock.getMonth() + 1,
                          day: parsedClock.getDate(),
                          hour: parsedClock.getHours(),
                          minute: parsedClock.getMinutes(),
                        } : null,
                        catchUpMid: catchUpMid ? {
                          offsetSeconds: Math.round(catchUpMid.offsetSeconds),
                          shouldAdvance: catchUpMid.shouldAdvance,
                          startHour: catchUpMid.startAt.getHours(),
                          startMinute: catchUpMid.startAt.getMinutes(),
                        } : null,
                        catchUpDone: catchUpDone ? {
                          offsetSeconds: Math.round(catchUpDone.offsetSeconds),
                          shouldAdvance: catchUpDone.shouldAdvance,
                        } : null,
                        catchUpFromEndAt: catchUpFromEndAt ? {
                          offsetSeconds: Math.round(catchUpFromEndAt.offsetSeconds),
                          shouldAdvance: catchUpFromEndAt.shouldAdvance,
                          startHour: catchUpFromEndAt.startAt.getHours(),
                          startMinute: catchUpFromEndAt.startAt.getMinutes(),
                        } : null,
                        shouldAdvanceIntro: presenterSlideShouldAutoAdvanceOnEnd(introSlide),
                        shouldAdvanceWaiting: presenterSlideShouldAutoAdvanceOnEnd(waitingSlide),
                        shouldAdvanceIntroLoop: presenterSlideShouldAutoAdvanceOnEnd(introLoopSlide),
                        introDefaults: presenterPlaybackConfig(null, 'intro-video'),
                        readyDefaults: presenterPlaybackConfig(null, 'ready-video'),
                      };
                    }
                    """
                )
                if (
                    intro_auto_advance_state["intro"]["hitCount"] == 1
                    and intro_auto_advance_state["intro"]["videoRole"] == "intro"
                    and intro_auto_advance_state["intro"]["autoplay"]
                    and not intro_auto_advance_state["intro"]["muted"]
                    and not intro_auto_advance_state["intro"]["loop"]
                    and intro_auto_advance_state["intro"]["detail"]["slideId"] == "__smoke_intro_slide__"
                    and intro_auto_advance_state["waiting"]["hitCount"] == 0
                    and intro_auto_advance_state["waiting"]["videoRole"] == "waiting_loop"
                    and intro_auto_advance_state["waiting"]["loop"]
                    and intro_auto_advance_state["introLoop"]["hitCount"] == 0
                    and intro_auto_advance_state["scheduledPast"]["hitCount"] == 1
                    and intro_auto_advance_state["scheduledPast"]["detail"]["slideId"] == "__smoke_waiting_loop_slide__"
                    and intro_auto_advance_state["scheduledFuture"]["hitCount"] == 0
                    and intro_auto_advance_state["scheduledFuture"]["timerArmed"]
                    and intro_auto_advance_state["catchUpMid"] == {
                        "offsetSeconds": 240,
                        "shouldAdvance": False,
                        "startHour": 10,
                        "startMinute": 40,
                    }
                    and intro_auto_advance_state["catchUpDone"]["shouldAdvance"]
                    and intro_auto_advance_state["catchUpDone"]["offsetSeconds"] == 600
                    and intro_auto_advance_state["catchUpFromEndAt"] == {
                        "offsetSeconds": 300,
                        "shouldAdvance": False,
                        "startHour": 10,
                        "startMinute": 40,
                    }
                    and intro_auto_advance_state["parsedClock"] == {
                        "year": 2026,
                        "month": 7,
                        "day": 12,
                        "hour": 10,
                        "minute": 40,
                    }
                    and intro_auto_advance_state["shouldAdvanceIntro"]
                    and not intro_auto_advance_state["shouldAdvanceWaiting"]
                    and not intro_auto_advance_state["shouldAdvanceIntroLoop"]
                    and intro_auto_advance_state["introDefaults"]["autoAdvanceOnEnd"]
                    and not intro_auto_advance_state["introDefaults"]["loop"]
                    and intro_auto_advance_state["readyDefaults"]["loop"]
                ):
                    pass_("presenter-intro-video-auto-advance", json.dumps(intro_auto_advance_state, ensure_ascii=False))
                else:
                    fail("presenter-intro-video-auto-advance", json.dumps(intro_auto_advance_state, ensure_ascii=False))

                fallback_state = page.evaluate(
                    """
                    (serviceId) => {
                      const modelServiceId = '__smoke_presenter_section_model_service__';
                      const modelService = {
                        id: modelServiceId,
                        type_id: 'monthly',
                        date: '2026-07-03',
                        title: '월삭예배',
                        leader: '',
                        alias: '',
                      };
                      if (!state.serviceTypes.some((item) => item.id === 'monthly')) {
                        state.serviceTypes.push({ id: 'monthly', name: '월삭예배', sort_order: 1 });
                      }
                      const scaffold = buildWorshipServiceScaffold(modelServiceId, 'monthly', { service: modelService });
                      const modelItems = normalizeServiceItemsForTemplateHierarchy(
                        modelService,
                        groupWorshipElements(scaffold.sections, scaffold.elements)[modelServiceId] || [],
                      );
                      state.services = [modelService].concat(state.services.filter((item) => item.id !== modelServiceId));
                      state.serviceItems[modelServiceId] = modelItems;
                      const slides = buildServicePresenterSlides(modelServiceId);
                      return {
                        centerFallbacks: slides.filter((slide) =>
                          !isPresenterPraiseSectionMarkerSlide(slide)
                          && (
                            slide.layout === 'center_text'
                            || slide.type === 'component'
                            || slide.elementType === 'plain_text'
                            || slide.elementType === 'freeform'
                          )
                        ).map((slide, index) => ({
                          index,
                          sectionLabel: slide.sectionLabel || '',
                          elementLabel: slide.elementLabel || '',
                          title: slide.title || ''
                        })),
                        ready: {
                          elementType: slides[0]?.elementType || '',
                          layout: slides[0]?.layout || '',
                          type: slides[0]?.type || ''
                        },
                        corporatePrayerGroups: groupPresenterSlidesBySection(slides, modelServiceId)
                          .filter((group) => group.label === '공동기도')
                          .map((group) => ({
                            title: group.title,
                            subgroups: group.subgroups.map((subgroup) => ({
                              label: subgroup.label,
                              title: subgroup.title,
                              slides: subgroup.slides.length,
                              ...(subgroup.label.includes('공동기도') ? {
                                slideTitles: subgroup.slides.map(({ slide }) =>
                                  slide.title || String(slide.text || '').split(/\\r?\\n/)[0] || (slide.type === 'blank' ? '빈 화면' : ''))
                              } : {})
                            }))
                          })),
                        corporatePrayerEditor: (() => {
                          const service = state.services.find((item) => item.id === modelServiceId);
                          const items = state.serviceItems[modelServiceId] || [];
                          const index = items.findIndex((item) => item.label === '공동기도 1·2');
                          const item = items[index];
                          const memo = parseServiceItemMemo(item?.memo);
                          const host = document.createElement('div');
                          host.innerHTML = item ? presenterServiceInputControls(item, index, service) : '';
                          const fields = [...host.querySelectorAll('[data-service-item-field]')];
                          const first = fields[0];
                          if (first) {
                            first.value = "'새 기도 제목'";
                            updateServiceItemField(first, { deferPresenterRefresh: true });
                          }
                          const updatedItem = state.serviceItems[modelServiceId]?.[index] || {};
                          const updatedMemo = parseServiceItemMemo(updatedItem.memo);
                          const updatedSlides = normalizePresenterSlidesForServiceOutput(
                            buildPresenterSlidesForServiceItem(updatedItem, service, index),
                            service
                          );
                          return {
                            index,
                            fields: fields.map((field) => ({
                              key: field.dataset.serviceItemField || '',
                              topicIndex: field.dataset.corporatePrayerTopicIndex || '',
                              label: field.closest('label')?.querySelector('span')?.textContent.trim() || '',
                              value: field.value || '',
                            })),
                            rawTitle: updatedItem.raw_title || '',
                            assignee: updatedItem.assignee || '',
                            memoSlides: updatedMemo.slides || [],
                            slideTitles: updatedSlides.map((slide) => slide.title || ''),
                            slideAssignees: updatedSlides.map((slide) => slide.assignee || ''),
                          };
                        })(),
                        mainPraiseGroups: groupPresenterSlidesBySection(slides, modelServiceId)
                          .filter((group) => group.kind === 'main-praise')
                          .map((group) => ({
                            label: group.label,
                            meta: group.meta,
                            subgroups: group.subgroups.length
                          })),
                        praiseSectionAssigneeBoardMeta: (() => {
                          const service = state.services.find((item) => item.id === modelServiceId);
                          if (!service) return [];
                          const praiseItems = (state.serviceItems[modelServiceId] || []).filter((item) => isMainPraiseServiceItem(item, service));
                          const previousAssignees = praiseItems.map((item) => item.assignee || '');
                          const previousLeader = service.leader || '';
                          praiseItems.forEach((item) => { item.assignee = '헤세드 찬양단'; });
                          service.leader = '김남영 목사';
                          const teamSlides = buildServicePresenterSlides(modelServiceId);
                          const groups = groupPresenterSlidesBySection(teamSlides, modelServiceId)
                            .filter((group) => group.kind === 'main-praise')
                            .map((group) => group.meta);
                          praiseItems.forEach((item, index) => { item.assignee = previousAssignees[index]; });
                          service.leader = previousLeader;
                          return groups;
                        })(),
                        praiseLeaderNameBoardMeta: (() => {
                          const service = state.services.find((item) => item.id === modelServiceId);
                          if (!service) return [];
                          const previousLeader = service.leader || '';
                          service.leader = '헤세드 찬양단';
                          const teamSlides = buildServicePresenterSlides(modelServiceId);
                          const groups = groupPresenterSlidesBySection(teamSlides, modelServiceId)
                            .filter((group) => group.kind === 'main-praise')
                            .map((group) => group.meta);
                          service.leader = previousLeader;
                          return groups;
                        })(),
                        praiseAutoAssigneeFallback: (() => ({
                          group: servicePraiseAssignee({ type_id: 'monthly', leader: '' }, [{ label: '찬양' }]),
                          board: servicePraiseBoardMetaCandidate({ type_id: 'monthly', leader: '' }, [{ label: '찬양' }]),
                        }))(),
                        mainPraiseElementTitleMeta: (() => {
                          const service = state.services.find((item) => item.id === serviceId) || { id: serviceId, type_id: 'monthly' };
                          const song = {
                            id: '__smoke_main_praise_meta_song__',
                            title: '가서 제자 삼으라',
                            subtitle: '갈릴리 마을 그 숲속에서',
                            original_title: 'Go Make Disciples',
                            versions: [{
                              id: '__smoke_main_praise_meta_version__',
                              name: 'Default',
                              is_primary: true,
                              forms: [
                                { id: 'meta-v1', part_type: 'Verse', part_number: 1, lyrics: '가서 제자 삼으라\\n세상 모든 사람들을', sort_order: 1 }
                              ]
                            }]
                          };
                          const previousSongs = state.songs;
                          state.songs = state.songs.filter((item) => item.id !== song.id).concat([song]);
                          const slides = buildPresenterSlidesForServiceItem({
                            id: '__smoke_main_praise_meta_item__',
                            label: '찬양',
                            raw_title: '가서 제자 삼으라',
                            song_id: song.id,
                            version_id: '__smoke_main_praise_meta_version__',
                          }, service, 0);
                          const group = groupPresenterSlidesBySection(slides, modelServiceId).find((item) => item.kind === 'main-praise');
                          const subgroup = group?.subgroups.find((item) =>
                            item.slides?.some(({ slide }) => slide.type === 'song-title')
                          ) || {};
                          const titleSlide = slides.find((slide) => slide.type === 'song-title') || {};
                          state.songs = previousSongs;
                          return {
                            groupTitle: group?.title || '',
                            subgroupTitle: subgroup.title || '',
                            outputTitle: titleSlide.title || '',
                            outputText: titleSlide.text || '',
                          };
                        })(),
                        connectedPraiseMedleyBoard: (() => {
                          const makeVersion = (id, lyrics) => ({
                            id,
                            name: 'Default',
                            is_primary: true,
                            forms: [{ id: `${id}-v`, part_type: 'Verse', part_number: 1, lyrics, sort_order: 1 }],
                          });
                          const songs = [
                            { id: '__smoke_medley_a__', title: '함께 지어져 가네', versions: [makeVersion('__smoke_medley_a_v__', '함께 지어져 가네\\n주 안에서')] },
                            { id: '__smoke_medley_b__', title: '성도의 노래', versions: [makeVersion('__smoke_medley_b_v__', '성도의 노래\\n주께 드리네')] },
                          ];
                          const previousSongs = state.songs;
                          state.songs = state.songs.filter((song) => !songs.some((fixture) => fixture.id === song.id)).concat(songs);
                          const connected = {
                            groupId: '__smoke_medley_6_7__',
                            title: '함께 지어져 가네 + 성도의 노래',
                            orderTitle: '찬양 6–7',
                            inputText: '함께 지어져 가네\\n성도의 노래',
                          };
                          const baseMemo = { elementType: 'praise', outputMode: 'lyrics', inputMode: 'lyrics_db' };
                          const medleyService = { id: '__smoke_medley_service__', type_id: 'sunday-main', date: '2026-08-23' };
                          const items = [
                            { id: '__smoke_medley_6__', service_id: medleyService.id, label: '찬양 6', raw_title: '함께 지어져 가네', song_id: '__smoke_medley_a__', song_version_id: '__smoke_medley_a_v__', memo: JSON.stringify({ ...baseMemo, connectedPraise: { ...connected, role: 'primary', primaryItemId: '__smoke_medley_6__', secondaryItemIds: ['__smoke_medley_7__'], itemIds: ['__smoke_medley_6__', '__smoke_medley_7__'] } }), _worshipSectionKey: 'praise', _worshipSectionTitle: '찬양', _worshipSectionId: '__smoke_medley_praise_section__', _worshipSectionOrder: 2, _worshipElementOrder: 6 },
                            { id: '__smoke_medley_7__', service_id: medleyService.id, label: '찬양 7', raw_title: '성도의 노래', song_id: '__smoke_medley_b__', song_version_id: '__smoke_medley_b_v__', memo: JSON.stringify({ ...baseMemo, connectedPraise: { ...connected, role: 'secondary', primaryItemId: '__smoke_medley_6__', itemIds: ['__smoke_medley_6__', '__smoke_medley_7__'] } }), _worshipSectionKey: 'praise', _worshipSectionTitle: '찬양', _worshipSectionId: '__smoke_medley_praise_section__', _worshipSectionOrder: 2, _worshipElementOrder: 7 },
                          ];
                          state.services = [medleyService].concat(state.services.filter((item) => item.id !== medleyService.id));
                          state.serviceItems[medleyService.id] = items;
                          const medleySlides = buildServicePresenterSlidesUncached(medleyService.id);
                          const group = groupPresenterSlidesBySection(medleySlides, medleyService.id).find((item) => item.kind === 'main-praise') || {};
                          const subgroup = group.subgroups?.find((item) => item.id === 'connected-praise:__smoke_medley_6_7__') || {};
                          const controlsHost = document.createElement('div');
                          controlsHost.innerHTML = renderPresenterBoardSubgroupInputControls(medleyService.id, subgroup);
                          const primaryOnlySubgroup = {
                            ...subgroup,
                            slides: (subgroup.slides || []).filter(({ slide }) => slide.elementId === '__smoke_medley_6__'),
                          };
                          const primaryOnlyControlsHost = document.createElement('div');
                          primaryOnlyControlsHost.innerHTML = renderPresenterBoardSubgroupInputControls(medleyService.id, primaryOnlySubgroup);
                          const boardHost = document.createElement('div');
                          boardHost.innerHTML = renderPresenterBoardSubgroup(subgroup, -1, medleyService.id, { showHead: true });
                          state.songs = previousSongs;
                          return {
                            label: subgroup.label || '',
                            title: subgroup.title || '',
                            renderedLabel: boardHost.querySelector('.svc-board-subgroup-head span')?.textContent.trim() || '',
                            renderedTitle: boardHost.querySelector('.svc-board-subgroup-head strong')?.textContent.trim() || '',
                            titleSlides: (subgroup.slides || []).filter(({ slide }) => slide.type === 'song-title').map(({ slide }) => slide.title || ''),
                            elementIds: [...new Set((subgroup.slides || []).map(({ slide }) => slide.elementId || '').filter(Boolean))],
                            inputLabels: [...controlsHost.querySelectorAll('.svc-board-subgroup-control-label')].map((node) => node.textContent.trim()),
                            primaryOnlyInputLabels: [...primaryOnlyControlsHost.querySelectorAll('.svc-board-subgroup-control-label')].map((node) => node.textContent.trim()),
                            songFieldCount: controlsHost.querySelectorAll('.svc-presenter-input-field--song').length,
                            primaryOnlySongFieldCount: primaryOnlyControlsHost.querySelectorAll('.svc-presenter-input-field--song').length,
                            stacked: controlsHost.querySelector('.svc-board-subgroup-controls')?.classList.contains('svc-board-subgroup-controls--stacked') || false,
                            readonlyTextareas: controlsHost.querySelectorAll('textarea[readonly]').length,
                          };
                        })(),
                        announcementGenericLabelGuard: (() => {
                          const announcementService = { id: '__smoke_announcement_label_guard_service__', type_id: 'sunday-main', date: '2026-08-23' };
                          const announcementItem = {
                            id: '__smoke_announcement_label_guard_item__',
                            service_id: announcementService.id,
                            label: '광고',
                            raw_title: '교회소식',
                            memo: serializeServiceItemMemo({ elementType: 'title' }),
                            _worshipSectionKey: 'announcements',
                            _worshipSectionTitle: '광고',
                            _worshipSectionId: '__smoke_announcement_label_guard_section__',
                            _worshipSectionOrder: 6,
                            _worshipElementOrder: 1,
                          };
                          state.services = [announcementService].concat(state.services.filter((item) => item.id !== announcementService.id));
                          state.serviceItems[announcementService.id] = [announcementItem];
                          const announcementSlides = buildServicePresenterSlidesUncached(announcementService.id);
                          const group = groupPresenterSlidesBySection(announcementSlides, announcementService.id)
                            .find((item) => item.sectionKey === 'announcements') || {};
                          const subgroup = group.subgroups?.[0] || {};
                          const boardHost = document.createElement('div');
                          boardHost.innerHTML = renderPresenterBoardSubgroup(subgroup, -1, announcementService.id, { showHead: true });
                          return {
                            groupLabel: group.label || '',
                            subgroupLabel: subgroup.label || '',
                            subgroupTitle: subgroup.title || '',
                            renderedLabel: boardHost.querySelector('.svc-board-subgroup-head span')?.textContent.trim() || '',
                            renderedTitle: boardHost.querySelector('.svc-board-subgroup-head strong')?.textContent.trim() || '',
                            hasHead: Boolean(boardHost.querySelector('.svc-board-subgroup-head')),
                            collapsed: boardHost.querySelector('.svc-board-subgroup')?.classList.contains('collapsed-head') || false,
                            slideTitle: subgroup.slides?.[0]?.slide?.title || '',
                          };
                        })(),
                        praiseSectionAssigneeIntro: (() => {
                          const service = state.services.find((item) => item.id === modelServiceId);
                          if (!service) return null;
                          const praiseItems = (state.serviceItems[modelServiceId] || []).filter((item) => isMainPraiseServiceItem(item, service));
                          const previousAssignees = praiseItems.map((item) => item.assignee || '');
                          praiseItems.forEach((item) => { item.assignee = '글로리아 찬양단'; });
                          const teamSlides = buildServicePresenterSlides(modelServiceId);
                          praiseItems.forEach((item, index) => { item.assignee = previousAssignees[index]; });
                          const intro = teamSlides.find((slide) => isPresenterPraiseSectionMarkerSlide(slide)) || {};
                          const introGroup = groupPresenterSlidesBySection(teamSlides, modelServiceId)
                            .find((group) => group.kind === 'main-praise') || {};
                          const introSubgroup = introGroup.subgroups?.find((subgroup) =>
                            subgroup.slides?.some(({ slide }) => slide.id === intro.id)
                          ) || {};
                          return {
                            type: intro.type || '',
                            elementType: intro.elementType || '',
                            layout: intro.layout || '',
                            elementLabel: intro.elementLabel || '',
                            title: intro.title || '',
                            subtitle: intro.subtitle || '',
                            bodyText: intro.bodyText || '',
                            text: intro.text || '',
                            skipTrailingBlank: intro.skipTrailingBlank === true,
                            boardGroupLabel: introGroup.label || '',
                            boardSubgroupLabel: introSubgroup.label || '',
                            boardSubgroupTitle: introSubgroup.title || '',
                            alias: serviceAlias({ alias: '온세대 찬양예배' }),
                          };
                        })(),
                        specialPraiseLabelGuard: (() => {
                          const slides = [
                            {
                              id: '__smoke_special_title__',
                              sectionId: '__smoke_special_section__',
                              sectionKey: 'special_song',
                              sectionLabel: '특송',
                              sectionTitle: '특송',
                              elementType: 'title_assignee',
                              layout: 'lower_bar_text',
                              type: 'title-assignee',
                              title: '특송',
                              assignee: '청소년부 교사 일동',
                              text: '특송\\n청소년부 교사 일동',
                            },
                            {
                              id: '__smoke_special_song_title__',
                              sectionId: '__smoke_special_section__',
                              sectionLabel: '찬양',
                              sectionTitle: '특송',
                              elementLabel: '찬양',
                              elementType: 'praise',
                              layout: 'lower_bar_text',
                              type: 'song-title',
                              title: '청소년부 교사 일동',
                              text: '♪ 청소년부 교사 일동',
                            },
                          ];
                          return {
                            mainFlags: slides.map((slide) => isPresenterMainPraiseSlide(slide)),
                            praiseIntroCount: slides.filter((slide) => slide.type === 'praise-section-title').length,
                            types: slides.map((slide) => slide.type),
                          };
                        })(),
                        canonicalBoardSectionTitle: (() => {
                          const groups = groupPresenterSlidesBySection([{
                            id: '__smoke_response_prayer__',
                            elementId: '__smoke_response_prayer__',
                            sectionId: '__smoke_response__',
                            sectionKey: 'response_song',
                            sectionLabel: '결단기도',
                            sectionTitle: '결단기도',
                            elementLabel: '결단기도',
                            elementType: 'title_assignee',
                            layout: 'lower_bar_text',
                            type: 'title-assignee',
                            title: '결단기도',
                            text: '결단기도',
                          }], serviceId);
                          return {
                            label: groups[0]?.label || '',
                            title: groups[0]?.title || '',
                            subgroupLabel: groups[0]?.subgroups?.[0]?.label || '',
                          };
                        })(),
                        friday3355SectionOrder: publicFriday3355Template().map((step) => step.sectionKey || ''),
                        closingGroups: groupPresenterSlidesBySection(slides, modelServiceId)
                          .filter((group) => group.slides.some((entry) => entry.slide.sectionKey === 'closing_visual'))
                          .map((group) => ({
                            kind: group.kind,
                            label: group.label,
                            title: group.title,
                            subgroups: group.subgroups.length
                          })),
                        trailingBlankPolicy: (() => {
                          const readySlides = withPresenterElementTrailingBlanks([
                            {
                              id: '__smoke_ready_media__',
                              elementId: '__smoke_ready_media__',
                              sectionId: '__smoke_ready__',
                              sectionKey: 'ready',
                              sectionRole: 'ready',
                              sectionLabel: '준비',
                              elementType: 'video',
                              layout: 'media',
                              type: 'ready',
                              title: '준비',
                              text: '',
                            },
                            {
                              id: '__smoke_after_ready__',
                              elementId: '__smoke_after_ready__',
                              sectionId: '__smoke_praise__',
                              sectionKey: 'praise',
                              sectionLabel: '찬양',
                              elementType: 'title_assignee',
                              layout: 'lower_bar_text',
                              type: 'title-assignee',
                              title: '찬양',
                              text: '찬양',
                            },
                          ]);
                          const closingSlides = withPresenterElementTrailingBlanks([
                            {
                              id: '__smoke_closing_visual__',
                              elementId: '__smoke_closing_visual__',
                              sectionId: '__smoke_closing__',
                              sectionKey: 'closing_visual',
                              sectionLabel: '마무리',
                              elementType: 'image',
                              layout: 'media',
                              type: 'image',
                              title: '마무리',
                              text: '마무리',
                            },
                            {
                              id: '__smoke_after_closing__',
                              elementId: '__smoke_after_closing__',
                              sectionId: '__smoke_after__',
                              sectionKey: 'after',
                              sectionLabel: '다음',
                              elementType: 'title_assignee',
                              layout: 'lower_bar_text',
                              type: 'title-assignee',
                              title: '다음',
                              text: '다음',
                            },
                          ]);
                          const normalSlides = withPresenterElementTrailingBlanks([
                            {
                              id: '__smoke_prayer__',
                              elementId: '__smoke_prayer__',
                              sectionId: '__smoke_prayer_section__',
                              sectionKey: 'prayer',
                              sectionLabel: '대표기도',
                              elementType: 'title_assignee',
                              layout: 'lower_bar_text',
                              type: 'title-assignee',
                              title: '기도',
                              text: '기도',
                            },
                            {
                              id: '__smoke_scripture__',
                              elementId: '__smoke_scripture__',
                              sectionId: '__smoke_scripture_section__',
                              sectionKey: 'scripture_reading',
                              sectionLabel: '성경봉독',
                              elementType: 'title_assignee',
                              layout: 'lower_bar_text',
                              type: 'title-assignee',
                              title: '성경봉독',
                              text: '성경봉독',
                            },
                          ]);
                          const prayerPraiseSlides = withPresenterElementTrailingBlanks([
                            {
                              id: '__smoke_prayer_praise_1__',
                              elementId: '__smoke_prayer_praise_1__',
                              sectionId: '__smoke_prayer_meeting__',
                              sectionKey: 'prayer_meeting_praise',
                              sectionLabel: '기도회',
                              elementLabel: '준비',
                              label: '준비',
                              elementType: 'praise',
                              layout: 'lower_bar_text',
                              type: 'song-title',
                              title: '비 준비하시니',
                              text: '♪ 비 준비하시니',
                            },
                            {
                              id: '__smoke_prayer_praise_2__',
                              elementId: '__smoke_prayer_praise_2__',
                              sectionId: '__smoke_prayer_meeting__',
                              sectionKey: 'prayer_meeting_praise',
                              sectionLabel: '기도회',
                              elementLabel: '기도찬양 2',
                              elementType: 'praise',
                              layout: 'lower_bar_text',
                              type: 'song-title',
                              title: '나는 믿노라',
                              text: '♪ 나는 믿노라',
                            },
                          ]);
                          return {
                            readyHasBlankAfterReady: readySlides.some((slide) => slide.id === '__smoke_ready_media__:after-blank'),
                            closingHasBlankAfterClosing: closingSlides.some((slide) => slide.id === '__smoke_closing_visual__:after-blank'),
                            normalHasBlankAfterPrayer: normalSlides.some((slide) => slide.id === '__smoke_prayer__:after-blank'),
                            scriptureHasBlankAfterReading: normalSlides.some((slide) => slide.id === '__smoke_scripture__:after-blank'),
                            prayerPraiseHasBlankAfterFirst: prayerPraiseSlides.some((slide) => slide.id === '__smoke_prayer_praise_1__:after-blank'),
                            scriptureBlank: (() => {
                              const blank = normalSlides.find((slide) => slide.id === '__smoke_scripture__:after-blank') || {};
                              return {
                                outputContext: blank.outputContext || '',
                                sectionKey: blank.sectionKey || '',
                                sectionLabel: blank.sectionLabel || '',
                                label: blank.label || '',
                                scriptureContext: blank.scriptureContext || '',
                                scriptureReadingFinal: Boolean(blank.scriptureReadingFinal),
                              };
                            })(),
                          };
                        })()
                      };
                    }
                    """,
                    service["id"],
                )
                if (
                    not fallback_state["centerFallbacks"]
                    and fallback_state["ready"] == {"elementType": "video", "layout": "media", "type": "ready"}
                    and fallback_state["corporatePrayerGroups"] == [{
                        "title": "공동기도",
                        "subgroups": [
                            {"label": "공동기도 1·2", "title": "공동기도 1·2", "slides": 3, "slideTitles": ["'교회 부흥을 위해'", "'선교와 민족을 위해'", "빈 화면"]},
                            {"label": "기도찬양", "title": "기도찬양", "slides": 1},
                            {"label": "공동기도 3·4", "title": "공동기도 3·4", "slides": 3, "slideTitles": ["'치유와 회복을 위해'", "'교회학교를 위해'", "빈 화면"]},
                        ],
                    }]
                    and fallback_state["corporatePrayerEditor"] == {
                        "index": 14,
                        "fields": [
                            {"key": "corporate_prayer_topic", "topicIndex": "0", "label": "공동기도 1", "value": "'새 기도 제목'"},
                            {"key": "corporate_prayer_assignee", "topicIndex": "0", "label": "공동기도 1", "value": ""},
                            {"key": "corporate_prayer_topic", "topicIndex": "1", "label": "공동기도 2", "value": "선교와 민족을 위해"},
                            {"key": "corporate_prayer_assignee", "topicIndex": "1", "label": "공동기도 2", "value": ""},
                        ],
                        "rawTitle": "",
                        "assignee": "",
                        "memoSlides": ["'새 기도 제목'", "'선교와 민족을 위해'"],
                        "slideTitles": ["'새 기도 제목'", "'선교와 민족을 위해'"],
                        "slideAssignees": ["", ""],
                    }
                    and len(fallback_state["mainPraiseGroups"]) == 1
                    and fallback_state["mainPraiseGroups"][0]["label"] == "찬양"
                    and fallback_state["mainPraiseGroups"][0]["meta"] == "썸프레이즈"
                    and fallback_state["praiseSectionAssigneeBoardMeta"] == ["썸프레이즈"]
                    and fallback_state["praiseLeaderNameBoardMeta"] == ["썸프레이즈"]
                    and fallback_state["praiseAutoAssigneeFallback"] == {
                        "group": "",
                        "board": {"text": "썸프레이즈", "priority": 2.5},
                    }
                    and fallback_state["mainPraiseElementTitleMeta"] == {
                        "groupTitle": "찬양",
                        "subgroupTitle": "가서 제자 삼으라",
                        "outputTitle": "가서 제자 삼으라",
                        "outputText": "♬ 가서 제자 삼으라",
                    }
                    and fallback_state["connectedPraiseMedleyBoard"] == {
                        "label": "찬양 6–7",
                        "title": "함께 지어져 가네 + 성도의 노래",
                        "renderedLabel": "찬양 6–7",
                        "renderedTitle": "함께 지어져 가네 + 성도의 노래",
                        "titleSlides": ["함께 지어져 가네 + 성도의 노래"],
                        "elementIds": ["__smoke_medley_6__", "__smoke_medley_7__"],
                        "inputLabels": [],  # medley rows are song pickers; no per-row "찬양 n"
                        "primaryOnlyInputLabels": [],
                        "songFieldCount": 2,
                        "primaryOnlySongFieldCount": 2,
                        "stacked": True,
                        "readonlyTextareas": 0,
                    }
                    and fallback_state["announcementGenericLabelGuard"] == {
                        "groupLabel": "광고",
                        "subgroupLabel": "교회소식",
                        "subgroupTitle": "교회소식",
                        "renderedLabel": "교회소식",
                        "renderedTitle": "",  # a title equal to the label is not printed twice
                        "hasHead": True,
                        "collapsed": False,
                        "slideTitle": "교회소식",
                    }
                    and fallback_state["praiseSectionAssigneeIntro"] == {
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "elementLabel": "환영",
                        "title": "찬양",
                        "subtitle": "",
                        "bodyText": "썸프레이즈",
                        "text": "찬양\n썸프레이즈",
                        "skipTrailingBlank": False,
                        "boardGroupLabel": "찬양",
                        "boardSubgroupLabel": "환영",
                        "boardSubgroupTitle": "",
                        "alias": "온세대 찬양예배",
                    }
                    and fallback_state["specialPraiseLabelGuard"] == {
                        "mainFlags": [False, False],
                        "praiseIntroCount": 0,
                        "types": ["title-assignee", "song-title"],
                    }
                    and fallback_state["canonicalBoardSectionTitle"] == {
                        "label": "결단",
                        "title": "결단",
                        "subgroupLabel": "결단기도",
                    }
                    and fallback_state["friday3355SectionOrder"] == [
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
                    and len(fallback_state["closingGroups"]) == 1
                    and fallback_state["closingGroups"][0]["kind"] == "item"
                    and fallback_state["closingGroups"][0]["label"] == "폐회"
                    and fallback_state["closingGroups"][0]["title"] == "폐회"
                    and fallback_state["closingGroups"][0]["subgroups"] >= 1
                    and fallback_state["trailingBlankPolicy"] == {
                        "readyHasBlankAfterReady": True,
                        "closingHasBlankAfterClosing": True,
                        "normalHasBlankAfterPrayer": True,
                        "scriptureHasBlankAfterReading": True,
                        "prayerPraiseHasBlankAfterFirst": True,
                        "scriptureBlank": {
                            "outputContext": "clean",
                            "sectionKey": "",
                            "sectionLabel": "",
                            "label": "",
                            "scriptureContext": "",
                            "scriptureReadingFinal": False,
                        },
                    }
                ):
                    pass_("presenter-section-element-model", json.dumps(fallback_state, ensure_ascii=False))
                else:
                    fail("presenter-section-element-model", json.dumps(fallback_state, ensure_ascii=False))

                slide_model_contract_state = page.evaluate(
                    """
                    (serviceId) => {
                      const slides = buildServicePresenterSlides(serviceId);
                      const issues = presenterSlidesModelIssues(slides);
                      const validCombinations = {
                        lowerBarPraise: presenterSlideModelIssues({
                          id: '__smoke_contract_praise__',
                          elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          type: 'lyrics',
                          title: '찬양',
                          text: '가사',
                        }),
                        cleanImage: presenterSlideModelIssues({
                          id: '__smoke_contract_image__',
                          elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
                          layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                          type: 'image',
                          title: '이미지',
                        }),
                        blank: presenterSlideModelIssues({
                          id: '__smoke_contract_blank__',
                          elementType: PRESENTER_ELEMENT_TYPES.BLANK,
                          layout: PRESENTER_SLIDE_LAYOUTS.BLANK,
                          type: 'blank',
                          title: '빈 화면',
                          text: '',
                        }),
                      };
                      const invalidCombinations = {
                        mediaPraise: presenterSlideModelIssues({
                          id: '__smoke_contract_bad_media__',
                          elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                          layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                          type: 'lyrics',
                          title: '찬양',
                        }),
                        blankPayload: presenterSlideModelIssues({
                          id: '__smoke_contract_bad_blank__',
                          elementType: PRESENTER_ELEMENT_TYPES.BLANK,
                          layout: PRESENTER_SLIDE_LAYOUTS.BLANK,
                          type: 'blank',
                          title: '빈 화면',
                          text: '보이면 안 됨',
                        }),
                        missingNoInputMode: presenterSlideModelIssues({
                          id: '__smoke_contract_bad_missing__',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          type: 'title-assignee',
                          title: '입력 필요',
                          missingContent: true,
                        }),
                      };
                      return {
                        slideCount: slides.length,
                        issues,
                        validCombinations,
                        invalidCombinations,
                      };
                    }
                    """,
                    service["id"],
                )
                if (
                    slide_model_contract_state["slideCount"] > 0
                    and slide_model_contract_state["issues"] == []
                    and all(not value for value in slide_model_contract_state["validCombinations"].values())
                    and all(value for value in slide_model_contract_state["invalidCombinations"].values())
                ):
                    pass_("presenter-slide-model-contract", json.dumps(slide_model_contract_state, ensure_ascii=False))
                else:
                    fail("presenter-slide-model-contract", json.dumps(slide_model_contract_state, ensure_ascii=False))

                title_assignee_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_title_service__',
                        type_id: 'sunday-second',
                        date: '2026-07-04',
                        worshipLeader: '김남영 목사'
                      };
                      const items = [
                        {
                          id: '__smoke_prayer_title__',
                          label: '대표기도',
                          raw_title: '박귀서 장로',
                          memo: serializeServiceItemMemo({ elementType: 'title_person' }),
                        },
                        {
                          id: '__smoke_scripture_title__',
                          label: '성경봉독',
                          raw_title: '대하 15:8-15',
                          assignee: '김남영 목사',
                          memo: serializeServiceItemMemo({ elementType: 'scripture_reading' }),
                        },
                        {
                          id: '__smoke_sermon_title__',
                          label: '설교',
                          raw_title: '정함',
                          assignee: '김남영 목사',
                          memo: serializeServiceItemMemo({ elementType: 'title_person' }),
                        },
                        {
                          id: '__smoke_offering_prayer_title__',
                          label: '봉헌기도',
                          raw_title: '봉헌기도',
                          assignee: '인도자',
                          memo: serializeServiceItemMemo({ elementType: 'title_person' }),
                        },
                        {
                          id: '__smoke_fellowship_title__',
                          label: '교제',
                          raw_title: '박미루 집사',
                          memo: serializeServiceItemMemo({ elementType: 'title_person' }),
                        },
                      ];
                      const slides = items.map((item, index) => {
                        const slide = buildPresenterSlidesForServiceItem(item, service, index)[0] || {};
                        return {
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          type: slide.type || '',
                          renderClass: presenterSlideRenderClass(slide),
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          html: renderPresenterSlideFrame(slide),
                        };
                      });
                      const cleanService = { ...service, type_id: 'sunday-first' };
                      const cleanSlides = normalizePresenterSlidesForServiceOutput(
                        items.map((item, index) => buildPresenterSlidesForServiceItem(item, cleanService, index)[0] || {}),
                        cleanService,
                      ).map((slide) => ({
                        elementType: slide.elementType || '',
                        layout: slide.layout || '',
                        type: slide.type || '',
                        renderClass: presenterSlideRenderClass(slide),
                        title: slide.title || '',
                        bodyText: slide.bodyText || '',
                        text: slide.text || '',
                        outputContext: presenterSlideOutputContext(slide, false),
                        html: renderPresenterSlideFrame(slide),
                      }));
                      const offeringSlides = buildPresenterSlidesForServiceItem(items[3], service, 3);
                      const offeringGroup = groupPresenterSlidesBySection(offeringSlides, service.id)[0] || {};
                      const offeringSubgroup = offeringGroup.subgroups?.[0] || {};
                      const offeringHeadHtml = renderPresenterBoardSubgroup(offeringSubgroup, 0, service.id, { showHead: true });
                      const offeringHead = document.createElement('div');
                      offeringHead.innerHTML = offeringHeadHtml;
                      return {
                        slides,
                        fellowshipInputModel: (() => {
                          const model = serviceItemEditorModel(items[4], { service });
                          const spec = presenterServiceTextInputSpec(items[4], model, parseServiceItemMemo(items[4].memo));
                          return {
                            showTitle: Boolean(model.showTitle),
                            showAssignee: Boolean(model.showAssignee),
                            assigneeValue: model.assigneeValue || '',
                            spec,
                          };
                        })(),
                        sermonTitleQuote: presenterTitleAssigneePerson(
                          { assignee: '김남영 목사' },
                          '설교 제목',
                          '정함',
                          '설교',
                          service,
                        ),
                        offeringBoard: {
                          label: offeringSubgroup.label || '',
                          title: offeringSubgroup.title || '',
                          span: offeringHead.querySelector('.svc-board-subgroup-head span')?.textContent.trim() || '',
                          strong: offeringHead.querySelector('.svc-board-subgroup-head strong')?.textContent.trim() || '',
                        },
                        cleanSlides,
                      };
                    }
                    """
                )
                if (
                    title_assignee_state["slides"] == [
                        {
                            "elementType": "title_assignee",
                            "layout": "lower_bar_text",
                            "type": "title-assignee",
                            "renderClass": "title-assignee",
                            "title": "대표기도",
                            "assignee": "박귀서 장로",
                            "text": "대표기도\n박귀서 장로",
                            "html": title_assignee_state["slides"][0]["html"],
                        },
                        {
                            "elementType": "title_assignee",
                            "layout": "lower_bar_text",
                            "type": "title-assignee",
                            "renderClass": "title-assignee",
                            "title": "성경봉독",
                            "assignee": "역대하 15:8–15",
                            "text": "성경봉독\n역대하 15:8–15",
                            "html": title_assignee_state["slides"][1]["html"],
                        },
                        {
                            "elementType": "title_assignee",
                            "layout": "lower_bar_text",
                            "type": "title-assignee",
                            "renderClass": "title-assignee",
                            "title": "｢정함｣",
                            "assignee": "김남영 목사",
                            "text": "설교\n｢정함｣\n김남영 목사",
                            "html": title_assignee_state["slides"][2]["html"],
                        },
                        {
                            "elementType": "title_assignee",
                            "layout": "lower_bar_text",
                            "type": "title-assignee",
                            "renderClass": "title-assignee",
                            "title": "봉헌기도",
                            "assignee": "김남영 목사",
                            "text": "봉헌기도\n김남영 목사",
                            "html": title_assignee_state["slides"][3]["html"],
                        },
                        {
                            "elementType": "title_assignee",
                            "layout": "lower_bar_text",
                            "type": "title-assignee",
                            "renderClass": "title-assignee",
                            "title": "교제",
                            "assignee": "박미루 집사",
                            "text": "교제\n박미루 집사",
                            "html": title_assignee_state["slides"][4]["html"],
                        },
                    ]
                    and title_assignee_state["fellowshipInputModel"] == {
                        "showTitle": False,
                        "showAssignee": True,
                        "assigneeValue": "박미루 집사",
                        "spec": {
                            "needsTitle": False,
                            "needsAssignee": True,
                        },
                    }
                    and all("presenter-title-assignee" in item["html"] for item in title_assignee_state["slides"])
                    and "presenter-title-assignee--missing" not in title_assignee_state["slides"][0]["html"]
                    and "presenter-title-assignee-title" in title_assignee_state["slides"][0]["html"]
                    and "presenter-title-assignee-person" in title_assignee_state["slides"][0]["html"]
                    and title_assignee_state["sermonTitleQuote"] == "｢정함｣\n김남영 목사"
                    and title_assignee_state["offeringBoard"] == {
                        "label": "봉헌기도",
                        "title": "봉헌기도",
                        "span": "봉헌기도",
                        "strong": "",
                    }
                    and title_assignee_state["cleanSlides"] == [
                        {
                            "elementType": "title_content",
                            "layout": "center_text",
                            "type": "title-content",
                            "renderClass": "title-content",
                            "title": "대표기도",
                            "bodyText": "박귀서 장로",
                            "text": "대표기도\n박귀서 장로",
                            "outputContext": "clean",
                            "html": title_assignee_state["cleanSlides"][0]["html"],
                        },
                        {
                            "elementType": "title_content",
                            "layout": "center_text",
                            "type": "title-content",
                            "renderClass": "title-content",
                            "title": "성경봉독",
                            "bodyText": "역대하 15:8–15",
                            "text": "성경봉독\n역대하 15:8–15",
                            "outputContext": "clean",
                            "html": title_assignee_state["cleanSlides"][1]["html"],
                        },
                        {
                            "elementType": "title_content",
                            "layout": "center_text",
                            "type": "title-content",
                            "renderClass": "title-content",
                            "title": "｢정함｣",
                            "bodyText": "김남영 목사",
                            "text": "｢정함｣\n김남영 목사",
                            "outputContext": "clean",
                            "html": title_assignee_state["cleanSlides"][2]["html"],
                        },
                        {
                            "elementType": "title_content",
                            "layout": "center_text",
                            "type": "title-content",
                            "renderClass": "title-content",
                            "title": "봉헌기도",
                            "bodyText": "",
                            "text": "봉헌기도",
                            "outputContext": "clean",
                            "html": title_assignee_state["cleanSlides"][3]["html"],
                        },
                        {
                            "elementType": "title_content",
                            "layout": "center_text",
                            "type": "title-content",
                            "renderClass": "title-content",
                            "title": "교제",
                            "bodyText": "박미루 집사",
                            "text": "교제\n박미루 집사",
                            "outputContext": "clean",
                            "html": title_assignee_state["cleanSlides"][4]["html"],
                        },
                    ]
                    and all("presenter-title-content" in item["html"] for item in title_assignee_state["cleanSlides"])
                    and "presenter-title-assignee--sermon" not in title_assignee_state["cleanSlides"][2]["html"]
                ):
                    pass_("presenter-title-assignee-slides", json.dumps(title_assignee_state, ensure_ascii=False))
                else:
                    fail("presenter-title-assignee-slides", json.dumps(title_assignee_state, ensure_ascii=False))

                fullscreen_missing_layout_state = page.evaluate(
                    """
                    () => {
                      const originalSongs = state.songs;
                      const service = {
                        id: '__smoke_fullscreen_missing_layout_service__',
                        type_id: 'friday',
                        date: '2026-08-21',
                      };
                      const song = {
                        id: '__smoke_fullscreen_missing_layout_song__',
                        title: '꽃들도',
                        versions: [{
                          id: '__smoke_fullscreen_missing_layout_version__',
                          name: '기본',
                          is_primary: true,
                          forms: [
                            { id: '__smoke_fullscreen_missing_layout_form__', part_type: 'Lyrics', lyrics: '꽃들도 구름도\\n바람도 넓은 바다도', sort_order: 1 },
                          ],
                        }],
                      };
                      const baseItem = {
                        id: '__smoke_fullscreen_missing_layout_praise__',
                        service_id: service.id,
                        label: '찬양 1',
                        memo: serializeServiceItemMemo({ elementType: 'praise' }),
                        _worshipSectionKey: 'praise',
                        _worshipSectionTitle: '찬양',
                      };
                      try {
                        state.songs = [song, ...originalSongs];
                        const missingSlide = normalizePresenterSlidesForServiceOutput(
                          buildPresenterSlidesForServiceItem({ ...baseItem, raw_title: '' }, service, 0),
                          service,
                        )[0] || {};
                        const filledSlides = normalizePresenterSlidesForServiceOutput(
                          buildPresenterSlidesForServiceItem({
                            ...baseItem,
                            raw_title: '',
                            song_id: song.id,
                            version_id: song.versions[0].id,
                            song_version_id: song.versions[0].id,
                          }, service, 0),
                          service,
                        );
                        const filledSlide = filledSlides.find((slide) => presenterSlideElementType(slide) === PRESENTER_ELEMENT_TYPES.PRAISE) || {};
                        const outlineBadges = ['praise_db', 'score_db', 'lyrics_db', 'manual_praise', 'scripture', 'asset', '']
                          .map((inputMode) => {
                            const container = document.createElement('div');
                            container.innerHTML = renderServiceOutlineMissingBadge({
                              missingContent: true,
                              inputMode,
                            });
                            return container.textContent.trim();
                          });
                        return {
                          missing: {
                            elementType: missingSlide.elementType || '',
                            layout: missingSlide.layout || '',
                            type: missingSlide.type || '',
                            renderClass: presenterSlideRenderClass(missingSlide),
                            title: missingSlide.title || '',
                            text: missingSlide.text || '',
                            sectionHeading: missingSlide.sectionHeading || '',
                            outputContext: presenterSlideOutputContext(missingSlide, false),
                            missingContent: Boolean(missingSlide.missingContent),
                            html: renderPresenterSlideFrame(missingSlide),
                          },
                          filled: {
                            elementType: filledSlide.elementType || '',
                            layout: filledSlide.layout || '',
                            type: filledSlide.type || '',
                            renderClass: presenterSlideRenderClass(filledSlide),
                            title: filledSlide.title || '',
                            text: filledSlide.text || '',
                            sectionHeading: filledSlide.sectionHeading || '',
                            outputContext: presenterSlideOutputContext(filledSlide, false),
                            missingContent: Boolean(filledSlide.missingContent),
                            html: renderPresenterSlideFrame(filledSlide),
                          },
                          outlineBadges,
                        };
                      } finally {
                        state.songs = originalSongs;
                      }
                    }
                    """
                )
                if (
                    fullscreen_missing_layout_state["missing"]["elementType"] == "praise"
                    and fullscreen_missing_layout_state["missing"]["layout"] == "lower_bar_text"
                    and fullscreen_missing_layout_state["missing"]["type"] == "song-title"
                    and fullscreen_missing_layout_state["missing"]["renderClass"] == "song-title"
                    and fullscreen_missing_layout_state["missing"]["title"] == "입력 필요"
                    and fullscreen_missing_layout_state["missing"]["text"] == "입력 필요"
                    and fullscreen_missing_layout_state["missing"]["outputContext"] == "clean"
                    and fullscreen_missing_layout_state["missing"]["missingContent"] is True
                    and fullscreen_missing_layout_state["outlineBadges"] == ["입력 필요"] * 7
                    and fullscreen_missing_layout_state["filled"]["elementType"] == "praise"
                    and fullscreen_missing_layout_state["filled"]["layout"] == "lower_bar_text"
                    and fullscreen_missing_layout_state["filled"]["type"] in ["song-title", "lyrics"]
                    and fullscreen_missing_layout_state["filled"]["renderClass"] in ["song-title", "lyrics"]
                    and fullscreen_missing_layout_state["filled"]["outputContext"] == "clean"
                    and fullscreen_missing_layout_state["filled"]["missingContent"] is False
                    and "presenter-title-content" not in fullscreen_missing_layout_state["missing"]["html"]
                ):
                    pass_("presenter-fullscreen-missing-song-layout", json.dumps(fullscreen_missing_layout_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-missing-song-layout", json.dumps(fullscreen_missing_layout_state, ensure_ascii=False))

                db_title_assignee_state = page.evaluate(
                    """
                    () => {
                      const slide = normalizeWorshipPresenterSlide({
                        service_id: '__smoke_db_service__',
                        section_id: '__smoke_db_section__',
                        section_order: 4,
                        section_key: 'prayer',
                        section_title: '대표기도',
                        section_person: '',
                        element_id: '__smoke_db_element__',
                        element_order: 1,
                        element_type: 'title_person',
                        element_title: '기도',
                        element_person: '박귀서 장로',
                        slide_id: '__smoke_db_slide__',
                        slide_order: 1,
                        slide_type: 'title_person',
                        slide_title: '기도',
                        slide_body: ''
                      }, 0);
                      return {
                        elementType: slide.elementType || '',
                        layout: slide.layout || '',
                        type: slide.type || '',
                        renderClass: presenterSlideRenderClass(slide),
                        title: slide.title || '',
                        assignee: slide.assignee || '',
                        text: slide.text || '',
                        html: renderPresenterSlideFrame(slide),
                      };
                    }
                    """
                )
                if (
                    db_title_assignee_state["elementType"] == "title_assignee"
                    and db_title_assignee_state["layout"] == "lower_bar_text"
                    and db_title_assignee_state["type"] == "title-assignee"
                    and db_title_assignee_state["renderClass"] == "title-assignee"
                    and db_title_assignee_state["title"] == "대표기도"
                    and db_title_assignee_state["assignee"] == "박귀서 장로"
                    and db_title_assignee_state["text"] == "대표기도\n박귀서 장로"
                    and "presenter-title-assignee" in db_title_assignee_state["html"]
                ):
                    pass_("presenter-db-title-assignee-slide", json.dumps(db_title_assignee_state, ensure_ascii=False))
                else:
                    fail("presenter-db-title-assignee-slide", json.dumps(db_title_assignee_state, ensure_ascii=False))

                title_content_state = page.evaluate(
                    """
                    () => {
                      const dbSlide = normalizePresenterSlidesForServiceOutput([normalizeWorshipPresenterSlide({
                        service_id: '__smoke_title_content_service__',
                        section_id: '__smoke_title_content_section__',
                        section_order: 5,
                        section_key: 'notice',
                        section_title: '교회소식',
                        section_person: '',
                        element_id: '__smoke_title_content_element__',
                        element_order: 1,
                        element_type: 'body',
                        element_title: '교회소식',
                        element_person: '',
                        slide_id: '__smoke_title_content_slide__',
                        slide_order: 1,
                        slide_type: 'body',
                        slide_title: '교회소식',
                        slide_body: '다음 주 공동의회가 있습니다\\n예배 후 본당에 남아 주세요'
                      }, 0)], { id: '__smoke_title_content_service__', type_id: 'monthly', date: '2026-07-04' })[0] || {};
                      const fallbackSlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem({
                        id: '__smoke_plain_text_body__',
                        label: '교회소식',
                        raw_title: '교회소식',
                        memo: serializeServiceItemMemo({
                          elementType: 'body',
                          slides: ['다음 주 공동의회가 있습니다\\n예배 후 본당에 남아 주세요']
                        }),
                      }, { id: '__smoke_title_content_fallback_service__', type_id: 'monthly', date: '2026-07-04' }, 0), { id: '__smoke_title_content_fallback_service__', type_id: 'monthly', date: '2026-07-04' });
                      const fallbackSlide = fallbackSlides[0] || {};
                      return {
                        db: {
                          elementType: dbSlide.elementType || '',
                          layout: dbSlide.layout || '',
                          type: dbSlide.type || '',
                          chromakeyContext: presenterSlideOutputContext(dbSlide, true),
                          chromakey: presenterSlideUsesChromakey(dbSlide, true),
                          cleanContext: presenterSlideOutputContext(dbSlide, false),
                          cleanChromakey: presenterSlideUsesChromakey(dbSlide, false),
                          renderClass: presenterSlideRenderClass(dbSlide),
                          title: dbSlide.title || '',
                          assignee: dbSlide.assignee || '',
                          text: dbSlide.text || '',
                          body: renderPresenterSlideBody(dbSlide).trim(),
                          html: renderPresenterSlideFrame(dbSlide),
                        },
                        fallback: {
                          elementType: fallbackSlide.elementType || '',
                          layout: fallbackSlide.layout || '',
                          type: fallbackSlide.type || '',
                          chromakeyContext: presenterSlideOutputContext(fallbackSlide, true),
                          chromakey: presenterSlideUsesChromakey(fallbackSlide, true),
                          cleanContext: presenterSlideOutputContext(fallbackSlide, false),
                          cleanChromakey: presenterSlideUsesChromakey(fallbackSlide, false),
                          renderClass: presenterSlideRenderClass(fallbackSlide),
                          title: fallbackSlide.title || '',
                          assignee: fallbackSlide.assignee || '',
                          text: fallbackSlide.text || '',
                          body: renderPresenterSlideBody(fallbackSlide).trim(),
                          html: renderPresenterSlideFrame(fallbackSlide),
                        }
                      };
                    }
                    """
                )
                if (
                    title_content_state["db"]["elementType"] == "title_assignee"
                    and title_content_state["db"]["layout"] == "lower_bar_text"
                    and title_content_state["db"]["type"] == "title-assignee"
                    and title_content_state["db"]["chromakeyContext"] == "chromakey"
                    and title_content_state["db"]["chromakey"] is True
                    and title_content_state["db"]["renderClass"] == "title-assignee"
                    and title_content_state["db"]["title"] == "교회소식"
                    and title_content_state["db"]["assignee"] == "다음 주 공동의회가 있습니다\n예배 후 본당에 남아 주세요"
                    and "presenter-title-assignee" in title_content_state["db"]["html"]
                    and "presenter-title-content" not in title_content_state["db"]["html"]
                    and "다음 주 공동의회가 있습니다" in title_content_state["db"]["body"]
                    and title_content_state["fallback"]["elementType"] == "title_assignee"
                    and title_content_state["fallback"]["layout"] == "lower_bar_text"
                    and title_content_state["fallback"]["chromakeyContext"] == "chromakey"
                    and title_content_state["fallback"]["chromakey"] is True
                    and title_content_state["fallback"]["renderClass"] == "title-assignee"
                    and title_content_state["fallback"]["title"] == "교회소식"
                    and title_content_state["fallback"]["assignee"] == "다음 주 공동의회가 있습니다\n예배 후 본당에 남아 주세요"
                    and "presenter-title-assignee" in title_content_state["fallback"]["html"]
                    and "presenter-title-content" not in title_content_state["fallback"]["html"]
                ):
                    pass_("presenter-title-content-slides", json.dumps(title_content_state, ensure_ascii=False))
                else:
                    fail("presenter-title-content-slides", json.dumps(title_content_state, ensure_ascii=False))

                title_and_liturgical_state = page.evaluate(
                    """
                    () => {
                      const confessionSlide = buildPresenterSlidesForServiceItem({
                        id: '__smoke_confession_title__',
                        label: '참회기도',
                        raw_title: '',
                        memo: serializeServiceItemMemo({ elementType: 'title' }),
                        _worshipSectionKey: 'confession',
                      }, { id: '__smoke_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' }, 0)[0] || {};
                      const creedItem = {
                        id: '__smoke_creed_body__',
                        label: '사도신경',
                        raw_title: '사도신경',
	                        memo: serializeServiceItemMemo({
	                          elementType: 'body',
	                          introSlide: { title: '신앙고백', body: '사도신경' },
	                          slides: ['전능하사 천지를 만드신 하나님 아버지를 내가 믿사오며\\n그 외아들 우리 주 예수 그리스도를 믿사오니\\n이는 성령으로 잉태하사 동정녀 마리아에게 나시고\\n본디오 빌라도에게 고난을 받으사 십자가에 못 박혀 죽으시고\\n장사한 지 사흘 만에 죽은 자 가운데서 다시 살아나시며\\n하늘에 오르사 전능하신 하나님 우편에 앉아 계시다가\\n저리로서 산 자와 죽은 자를 심판하러 오시리라\\n성령을 믿사오며 거룩한 공회와 성도가 서로 교통하는 것과\\n죄를 사하여 주시는 것과 몸이 다시 사는 것과\\n영원히 사는 것을 믿사옵나이다. 아멘']
	                        }),
                        _worshipSectionKey: 'creed',
                      };
                      const chromakeySlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem(
                        creedItem,
                        { id: '__smoke_creed_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' },
                        1
                      ), { id: '__smoke_creed_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' });
                      const fullscreenSlides = buildPresenterSlidesForServiceItem(
                        creedItem,
                        { id: '__smoke_creed_fullscreen_service__', type_id: 'friday', date: '2026-07-03' },
                        1
                      );
                      const previousServices = state.services.slice();
                      const previousServiceItems = JSON.parse(JSON.stringify(state.serviceItems || {}));
                      const scaffoldService = { id: '__smoke_public_creed_scaffold__', type_id: 'sunday-second', date: '2026-07-05', service_date: '2026-07-05' };
                      state.services = state.services.filter((service) => service.id !== scaffoldService.id);
                      state.services.push(scaffoldService);
                      const scaffold = buildWorshipServiceScaffold(scaffoldService.id, scaffoldService.type_id);
                      state.serviceItems[scaffoldService.id] = groupWorshipElements(scaffold.sections, scaffold.elements)[scaffoldService.id] || [];
                      const scaffoldAllSlides = buildServicePresenterSlides(scaffoldService.id);
                      const lordsPrayerService = { id: '__smoke_public_lords_prayer_scaffold__', type_id: 'sunday-first', date: '2026-08-23', service_date: '2026-08-23' };
                      state.services = state.services.filter((service) => service.id !== lordsPrayerService.id);
                      state.services.push(lordsPrayerService);
                      const lordsPrayerScaffold = buildWorshipServiceScaffold(lordsPrayerService.id, lordsPrayerService.type_id);
                      state.serviceItems[lordsPrayerService.id] = groupWorshipElements(lordsPrayerScaffold.sections, lordsPrayerScaffold.elements)[lordsPrayerService.id] || [];
                      const lordsPrayerItem = (state.serviceItems[lordsPrayerService.id] || [])
                        .find((item) => item.label === '주기도문') || {
                          id: '__smoke_lords_prayer_body__',
                          label: '주기도문',
                          raw_title: '주기도문',
                          memo: serializeServiceItemMemo({ elementType: 'body', introSlide: { title: '주기도문' } }),
                          _worshipSectionKey: 'sending',
                        };
                      const creedTemplatePlaceholder = {
                        id: '__smoke_creed_template_placeholder__',
                        label: '사도신경',
                        raw_title: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'body',
                          introSlide: { title: '신앙고백', body: '사도신경' },
                        }),
                        _worshipSectionKey: 'creed',
                        _worshipTemplateProjected: true,
                        _worshipTemplatePlaceholder: true,
                      };
                      const creedTemplatePlaceholderState = resolvePresenterServiceItemContentState(
                        creedTemplatePlaceholder,
                        parseServiceItemMemo(creedTemplatePlaceholder.memo),
                        lordsPrayerService
                      );
                      const closingTemplatePlaceholder = {
                        id: '__smoke_closing_template_placeholder__',
                        label: '마무리',
                        raw_title: '',
                        memo: serializeServiceItemMemo({ elementType: 'image' }),
                        _worshipSectionKey: 'closing_visual',
                        _worshipTemplateProjected: true,
                        _worshipTemplatePlaceholder: true,
                      };
                      const closingTemplatePlaceholderState = resolvePresenterServiceItemContentState(
                        closingTemplatePlaceholder,
                        parseServiceItemMemo(closingTemplatePlaceholder.memo),
                        null,
                        lordsPrayerService
                      );
                      const closingTemplatePlaceholderSlides = buildPresenterSlidesForServiceItem(
                        closingTemplatePlaceholder,
                        lordsPrayerService,
                        99
                      );
                      const doxologyTemplatePlaceholder = {
                        id: '__smoke_doxology_template_placeholder__',
                        label: '송영',
                        raw_title: '',
                        memo: serializeServiceItemMemo({ elementType: 'praise', outputMode: 'score' }),
                        _worshipSectionKey: 'sending',
                        _worshipTemplateProjected: true,
                        _worshipTemplatePlaceholder: true,
                      };
                      state.hymnScoreManifest = {
                        ...(state.hymnScoreManifest || {}),
                        '1': {
                          title: '만복의 근원 하나님',
                          slides: [
                            { src: 'assets/hymn-scores/1/slide-01.webp', sourceSlide: 1 },
                            { src: 'assets/hymn-scores/1/slide-02.webp', sourceSlide: 2 },
                          ],
                        },
                        '5': {
                          title: '이 천지간 만물들아',
                          slides: [
                            { src: 'assets/hymn-scores/5/slide-01.webp', sourceSlide: 1 },
                            { src: 'assets/hymn-scores/5/slide-02.webp', sourceSlide: 2 },
                          ],
                        },
                      };
                      const doxologyTemplatePlaceholderState = resolvePresenterServiceItemContentState(
                        doxologyTemplatePlaceholder,
                        parseServiceItemMemo(doxologyTemplatePlaceholder.memo),
                        null,
                        lordsPrayerService
                      );
                      const doxologyTemplatePlaceholderSlides = buildPresenterSlidesForServiceItem(
                        doxologyTemplatePlaceholder,
                        lordsPrayerService,
                        100
                      );
                      const afternoonDoxologyService = {
                        id: '__smoke_afternoon_doxology_service__',
                        type_id: 'sunday-afternoon',
                        date: '2026-07-05',
                      };
                      const afternoonDoxologyTemplatePlaceholderState = resolvePresenterServiceItemContentState(
                        doxologyTemplatePlaceholder,
                        parseServiceItemMemo(doxologyTemplatePlaceholder.memo),
                        null,
                        afternoonDoxologyService
                      );
                      const afternoonDoxologyTemplatePlaceholderSlides = buildPresenterSlidesForServiceItem(
                        doxologyTemplatePlaceholder,
                        afternoonDoxologyService,
                        101
                      );
	                      const sharedScriptureService = {
	                        id: '__smoke_shared_scripture_service__',
	                        type_id: 'friday',
	                        date: '2026-07-17',
	                      };
	                      const smokeTranslation = {
	                        id: '__smoke_placeholder_ko__',
	                        translationKey: 'SMOKE',
	                        name: '스모크역',
	                        abbreviation: '스모크',
	                      };
	                      if (!state.bibleTranslations.some((translation) => translation.id === smokeTranslation.id)) {
	                        state.bibleTranslations.push(smokeTranslation);
	                      }
	                      cacheServiceScriptureVerses(parseBibleReference('출 23:14–19'), [
	                        { book_code: 'EXO', chapter: 23, verse: 14, text: '너는 매년 세 번 내게 절기를 지킬지니라' },
	                      ], smokeTranslation);
	                      const sharedScriptureReadingItem = {
	                        id: '__smoke_shared_scripture_reading__',
	                        service_id: sharedScriptureService.id,
	                        label: '성경봉독',
	                        raw_title: '출 23:14–19',
	                        memo: serializeServiceItemMemo({
	                          elementType: 'scripture_body',
	                          inputMode: 'scripture',
	                          scriptureReference: '출 23:14–19',
	                          scriptureTranslationId: smokeTranslation.id,
	                        }),
	                        _worshipSectionKey: 'scripture_reading',
	                        _worshipTemplatePlaceholder: false,
	                      };
	                      const sharedSermonBodyItem = {
	                        id: '__smoke_shared_sermon_body__',
	                        service_id: sharedScriptureService.id,
	                        label: '설교 본문',
	                        raw_title: '출 23:14–19',
	                        memo: serializeServiceItemMemo({
	                          elementType: 'scripture_body',
	                          inputMode: 'scripture',
	                          scriptureReference: '출 23:14–19',
	                          scriptureTranslationId: smokeTranslation.id,
	                        }),
	                        _worshipSectionKey: 'sermon',
	                      };
	                      const placeholderScriptureItem = {
	                        id: '__smoke_placeholder_scripture_body__',
	                        service_id: sharedScriptureService.id,
	                        label: '성경봉독',
	                        raw_title: '',
	                        memo: serializeServiceItemMemo({
	                          elementType: 'scripture_body',
	                          inputMode: 'scripture',
	                          scriptureReference: '출 23:14–19',
	                          scriptureTranslationId: smokeTranslation.id,
	                        }),
	                        _worshipSectionKey: 'scripture_reading',
	                        _worshipSectionTitle: '성경봉독',
	                        _worshipTemplatePlaceholder: true,
	                      };
	                      const optionalCitationItem = {
	                        id: '__smoke_optional_citation__',
	                        service_id: sharedScriptureService.id,
	                        label: '인용 구절',
	                        raw_title: '',
	                        memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' }),
	                        _worshipSectionKey: 'sermon',
	                      };
	                      state.services = state.services.filter((service) => service.id !== sharedScriptureService.id);
	                      state.services.push(sharedScriptureService);
	                      state.serviceItems[sharedScriptureService.id] = [
	                        sharedScriptureReadingItem,
	                        sharedSermonBodyItem,
	                        optionalCitationItem,
	                      ];
	                      const sharedScriptureReadingState = resolvePresenterServiceItemContentState(
	                        sharedScriptureReadingItem,
	                        parseServiceItemMemo(sharedScriptureReadingItem.memo),
	                        null,
	                        sharedScriptureService
	                      );
	                      const optionalCitationState = resolvePresenterServiceItemContentState(
	                        optionalCitationItem,
	                        parseServiceItemMemo(optionalCitationItem.memo),
	                        null,
	                        sharedScriptureService
	                      );
	                      const sharedScriptureReadingSlides = buildPresenterSlidesForServiceItem(
	                        sharedScriptureReadingItem,
	                        sharedScriptureService,
	                        102
	                      );
	                      const placeholderScriptureState = resolvePresenterServiceItemContentState(
	                        placeholderScriptureItem,
	                        parseServiceItemMemo(placeholderScriptureItem.memo),
	                        null,
	                        sharedScriptureService
	                      );
	                      const placeholderScriptureSlides = buildPresenterSlidesForServiceItem(
	                        placeholderScriptureItem,
	                        sharedScriptureService,
	                        102.5
	                      );
	                      const optionalCitationSlides = buildPresenterSlidesForServiceItem(
	                        optionalCitationItem,
	                        sharedScriptureService,
	                        103
	                      );
	                      const sharedScriptureReadingReferences = serviceItemScriptureReferences(
	                        sharedScriptureReadingItem,
	                        parseServiceItemMemo(sharedScriptureReadingItem.memo),
	                        sharedScriptureService
	                      );
                      const sharedSundaySecondService = {
                        id: '__smoke_shared_sunday_second__',
                        type_id: 'sunday-second',
                        date: '2126-07-26',
                        service_date: '2126-07-26',
                      };
                      const sharedSundayThirdService = {
                        id: '__smoke_shared_sunday_third__',
                        type_id: 'sunday-main',
                        date: '2126-07-26',
                        service_date: '2126-07-26',
                      };
                      const sharedSundaySecondSermonBody = {
                        id: '__smoke_shared_sunday_second_sermon_body__',
                        service_id: sharedSundaySecondService.id,
                        label: '설교 본문',
                        raw_title: '마 13:31–33, 44–50',
                        memo: serializeServiceItemMemo({
                          elementType: 'scripture_body',
                          inputMode: 'scripture',
                          scriptureReference: '마 13:31–33',
                          scriptureReferences: ['마 13:31–33'],
                        }),
                        _worshipSectionKey: 'sermon',
                      };
                      const sharedSundayThirdSermonBody = {
                        id: '__smoke_shared_sunday_third_sermon_body__',
                        service_id: sharedSundayThirdService.id,
                        label: '설교 본문',
	                        raw_title: '',
	                        memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' }),
                        _worshipSectionKey: 'sermon',
                      };
                      const sharedSundaySecondCitation = {
                        id: '__smoke_shared_sunday_second_citation__',
                        service_id: sharedSundaySecondService.id,
                        label: '인용 구절',
                        raw_title: '요 15:9; 롬 5:7–8',
                        memo: serializeServiceItemMemo({
                          elementType: 'scripture_body',
                          inputMode: 'scripture',
                          scriptureReference: '요 15:9',
                          scriptureReferences: ['요 15:9', '롬 5:7–8'],
                        }),
                        _worshipSectionKey: 'sermon',
                      };
                      const sharedSundayThirdCitation = {
                        id: '__smoke_shared_sunday_third_citation__',
                        service_id: sharedSundayThirdService.id,
                        label: '인용 구절',
                        raw_title: '',
                        memo: serializeServiceItemMemo({ elementType: 'scripture_body', inputMode: 'scripture' }),
                        _worshipSectionKey: 'sermon',
                      };
                      state.services = state.services.filter((service) =>
                        ![sharedSundaySecondService.id, sharedSundayThirdService.id].includes(service.id)
                      );
                      state.services.push(sharedSundaySecondService, sharedSundayThirdService);
                      state.serviceItems[sharedSundaySecondService.id] = [
                        sharedSundaySecondSermonBody,
                        sharedSundaySecondCitation,
                      ];
                      // These target records represent a completed edit synchronization, not a read fallback.
                      Object.assign(sharedSundayThirdSermonBody, applySundayEditSync(sharedSundayThirdSermonBody, sharedSundaySecondSermonBody));
                      Object.assign(sharedSundayThirdCitation, applySundayEditSync(sharedSundayThirdCitation, sharedSundaySecondCitation));
                      state.serviceItems[sharedSundayThirdService.id] = [
                        sharedSundayThirdSermonBody,
                        sharedSundayThirdCitation,
                      ];
                      const sharedSundayThirdSermonBodyEffective = serviceItemWithSharedSundayContent(
                        sharedSundayThirdSermonBody,
                        sharedSundayThirdService
                      );
                      const sharedSundayThirdCitationEffective = serviceItemWithSharedSundayContent(
                        sharedSundayThirdCitation,
                        sharedSundayThirdService
                      );
                      const sharedSundayThirdSermonBodyEffectiveMemo = parseServiceItemMemo(sharedSundayThirdSermonBodyEffective.memo);
                      const sharedSundayThirdCitationEffectiveMemo = parseServiceItemMemo(sharedSundayThirdCitationEffective.memo);
                      const sharedSundayThirdSermonBodySlides = buildPresenterSlidesForServiceItem(
                        sharedSundayThirdSermonBody,
                        sharedSundayThirdService,
                        104
                      );
                      const sharedSundayThirdCitationSlides = buildPresenterSlidesForServiceItem(
                        sharedSundayThirdCitation,
                        sharedSundayThirdService,
                        105
                      );
	                      const lordsPrayerSlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem(
	                        lordsPrayerItem,
	                        { id: '__smoke_lords_prayer_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' },
	                        1
	                      ), { id: '__smoke_lords_prayer_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' })
                        .map((slide) => ({
                          layout: slide.layout || '',
                          type: slide.type || '',
                          text: slide.text || '',
                          lineCount: String(slide.text || '').split('\\n').length,
	                          outputContext: presenterSlideOutputContext(slide, true),
	                        }));
	                      const lordsPrayerFullscreenSlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem(
	                        lordsPrayerItem,
	                        { id: '__smoke_lords_prayer_fullscreen_service__', type_id: 'sunday-first', date: '2026-08-23' },
	                        1
	                      ), { id: '__smoke_lords_prayer_fullscreen_service__', type_id: 'sunday-first', date: '2026-08-23' })
	                        .map((slide) => ({
	                          layout: slide.layout || '',
	                          type: slide.type || '',
	                          text: slide.text || '',
	                          lineCount: String(slide.text || '').split('\\n').length,
	                          outputContext: presenterSlideOutputContext(slide, false),
	                        }));
                      const communityService = { id: '__smoke_public_community_scaffold__', type_id: 'sunday-main', date: '2026-07-05', service_date: '2026-07-05' };
                      state.services = state.services.filter((service) => service.id !== communityService.id);
                      state.services.push(communityService);
                      const communityScaffold = buildWorshipServiceScaffold(communityService.id, communityService.type_id);
                      state.serviceItems[communityService.id] = groupWorshipElements(communityScaffold.sections, communityScaffold.elements)[communityService.id] || [];
                      const communityItem = (state.serviceItems[communityService.id] || [])
                        .find((item) => item._worshipSectionKey === 'sending' && item.label === '공동체고백') || {};
                      const communitySlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem(
                        communityItem,
                        { id: '__smoke_community_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' },
                        1
                      ), { id: '__smoke_community_chromakey_service__', type_id: 'sunday-main', date: '2026-07-05' })
                        .map((slide) => ({
                          layout: slide.layout || '',
                          type: slide.type || '',
                          title: slide.title || '',
                          text: slide.text || '',
                          lineCount: String(slide.text || '').split('\\n').length,
                          outputContext: presenterSlideOutputContext(slide, true),
                          html: renderPresenterSlideFrame(slide),
                          textHighlights: slide.textHighlights || [],
                        }));
                      const communityFullscreenSlides = normalizePresenterSlidesForServiceOutput(buildPresenterSlidesForServiceItem(
                        communityItem,
                        { id: '__smoke_community_fullscreen_service__', type_id: 'sunday-first', date: '2026-07-05' },
                        1
                      ), { id: '__smoke_community_fullscreen_service__', type_id: 'sunday-first', date: '2026-07-05' })
                        .map((slide) => ({
                          layout: slide.layout || '',
                          type: slide.type || '',
                          title: slide.title || '',
                          text: slide.text || '',
                          lineCount: String(slide.text || '').split('\\n').length,
                          outputContext: presenterSlideOutputContext(slide, false),
                          html: renderPresenterSlideFrame(slide),
                          textHighlights: slide.textHighlights || [],
                        }));
                      const scaffoldSlides = scaffoldAllSlides
                        .filter((slide) => slide.sectionKey === 'creed')
                        .map((slide) => ({
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          type: slide.type || '',
                          title: slide.title || '',
                          text: slide.text || '',
                          lineCount: String(slide.text || '').split('\\n').length,
                          chromakey: presenterSlideUsesChromakey(slide, true),
                          outputContext: presenterSlideOutputContext(slide, true),
                          renderClass: presenterSlideRenderClass(slide),
                        }));
                      const scaffoldClosingSlides = scaffoldAllSlides
                        .filter((slide) => slide.sectionKey === 'closing_visual')
                        .map((slide) => ({
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          type: slide.type || '',
                          title: slide.title || '',
                          imageSrc: slide.imageSrc || '',
                          chromakey: presenterSlideUsesChromakey(slide, true),
                          outputContext: presenterSlideOutputContext(slide, true),
                        }));
                      const scaffoldOutputContexts = scaffoldAllSlides.reduce((contexts, slide) => {
                        const context = presenterSlideOutputContext(slide, true);
                        contexts[context] = (contexts[context] || 0) + 1;
                        return contexts;
                      }, {});
                      state.services = previousServices;
                      state.serviceItems = previousServiceItems;
                      return {
                        confession: {
                          elementType: confessionSlide.elementType || '',
                          layout: confessionSlide.layout || '',
                          type: confessionSlide.type || '',
                          renderClass: presenterSlideRenderClass(confessionSlide),
                          title: confessionSlide.title || '',
                          text: confessionSlide.text || '',
                          html: renderPresenterSlideFrame(confessionSlide),
                        },
                        chromakey: chromakeySlides.map((slide) => ({
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          type: slide.type || '',
                          chromakey: presenterSlideUsesChromakey(slide, true),
                          outputContext: presenterSlideOutputContext(slide, true),
                          renderClass: presenterSlideRenderClass(slide),
                          title: slide.title || '',
                          marker: slide.marker || '',
                          text: slide.text || '',
                        })),
                        fullscreen: fullscreenSlides.map((slide) => ({
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          type: slide.type || '',
                          chromakey: presenterSlideUsesChromakey(slide, false),
                          outputContext: presenterSlideOutputContext(slide, false),
                          renderClass: presenterSlideRenderClass(slide),
                          title: slide.title || '',
                          text: slide.text || '',
                          html: renderPresenterSlideFrame(slide),
                        })),
	                        scaffold: scaffoldSlides,
	                        lordsPrayerScaffold: lordsPrayerSlides,
	                        lordsPrayerFullscreen: lordsPrayerFullscreenSlides,
	                        creedTemplatePlaceholderState,
	                        closingTemplatePlaceholderState,
	                        closingTemplatePlaceholderSlides: closingTemplatePlaceholderSlides.map((slide) => ({
	                          type: slide.type || '',
	                          imageSrc: slide.imageSrc || '',
	                        })),
	                        doxologyTemplatePlaceholderState,
	                        doxologyTemplatePlaceholderSlides: doxologyTemplatePlaceholderSlides.map((slide) => ({
	                          type: slide.type || '',
	                          title: slide.title || '',
	                          imageSrc: slide.imageSrc || '',
	                        })),
	                        afternoonDoxologyTemplatePlaceholderState,
	                        afternoonDoxologyTemplatePlaceholderSlides: afternoonDoxologyTemplatePlaceholderSlides.map((slide) => ({
	                          type: slide.type || '',
	                          title: slide.title || '',
	                          imageSrc: slide.imageSrc || '',
	                        })),
	                        sharedScripture: {
	                          readingReferences: sharedScriptureReadingReferences,
	                          readingState: sharedScriptureReadingState,
	                          readingInput: presenterServiceInputItem(sharedScriptureReadingItem, sharedScriptureService),
	                          readingSlideCount: sharedScriptureReadingSlides.length,
	                          placeholderState: placeholderScriptureState,
	                          placeholderSlideTypes: placeholderScriptureSlides.map((slide) => slide.type || ''),
	                          placeholderSlideTexts: placeholderScriptureSlides.map((slide) => slide.text || ''),
	                          citationState: optionalCitationState,
	                          citationInputMode: presenterServiceInputItem(optionalCitationItem, sharedScriptureService)?.mode || '',
	                          citationSlides: optionalCitationSlides.map((slide) => ({
	                            type: slide.type || '',
	                            elementType: slide.elementType || '',
	                            liveScriptureControl: Boolean(slide.liveScriptureControl),
	                            isLiveScriptureElement: presenterSlideIsLiveScriptureElement(slide),
	                          })),
	                          targetLabel: presenterPreparationTargetLabel('성경봉독'),
	                        },
                        sharedSundaySermon: {
                          sermonBodyInputReferences: normalizeServiceScriptureReferenceList('마 13:31–33, 44–50'),
                          sermonBodySecondReferences: serviceItemScriptureReferences(
                            sharedSundaySecondSermonBody,
                            parseServiceItemMemo(sharedSundaySecondSermonBody.memo),
                            sharedSundaySecondService
                          ),
                          sermonBodyThirdReferences: serviceItemScriptureReferences(
                            sharedSundayThirdSermonBody,
                            parseServiceItemMemo(sharedSundayThirdSermonBody.memo),
                            sharedSundayThirdService
                          ),
                          sermonBodyThirdEffectiveReferences: serviceItemDirectScriptureReferences(
                            sharedSundayThirdSermonBodyEffective,
                            sharedSundayThirdSermonBodyEffectiveMemo
                          ),
                          sermonBodyThirdRaw: sharedSundayThirdSermonBodyEffective.raw_title || '',
                          sermonBodyThirdMemo: sharedSundayThirdSermonBodyEffectiveMemo,
                          sermonBodyThirdSlideCount: sharedSundayThirdSermonBodySlides.length,
                          citationInputReferences: normalizeServiceScriptureReferenceList('요 15:9; 롬 5:7–8'),
                          citationSecondReferences: serviceItemScriptureReferences(
                            sharedSundaySecondCitation,
                            parseServiceItemMemo(sharedSundaySecondCitation.memo),
                            sharedSundaySecondService
                          ),
                          citationThirdReferences: serviceItemScriptureReferences(
                            sharedSundayThirdCitation,
                            parseServiceItemMemo(sharedSundayThirdCitation.memo),
                            sharedSundayThirdService
                          ),
                          citationThirdEffectiveReferences: serviceItemDirectScriptureReferences(
                            sharedSundayThirdCitationEffective,
                            sharedSundayThirdCitationEffectiveMemo
                          ),
                          citationThirdRaw: sharedSundayThirdCitationEffective.raw_title || '',
                          citationThirdMemo: sharedSundayThirdCitationEffectiveMemo,
                          citationThirdSlideCount: sharedSundayThirdCitationSlides.length,
                          sermonBodyThirdState: resolvePresenterServiceItemContentState(
                            sharedSundayThirdSermonBodyEffective,
                            sharedSundayThirdSermonBodyEffectiveMemo,
                            null,
                            sharedSundayThirdService
                          ),
                          citationThirdState: resolvePresenterServiceItemContentState(
                            sharedSundayThirdCitationEffective,
                            sharedSundayThirdCitationEffectiveMemo,
                            null,
                            sharedSundayThirdService
                          ),
                        },
	                        communityScaffold: communitySlides,
	                        communityFullscreen: communityFullscreenSlides,
	                        scaffoldClosing: scaffoldClosingSlides,
                        scaffoldOutputContexts,
                        chromakeyCenterTextSlides: scaffoldAllSlides
                          .filter((slide) =>
                            presenterSlideOutputContext(slide, true) === 'chromakey'
                            && slide.layout === 'center_text'
                          )
                          .map((slide) => ({
                            id: slide.id || '',
                            type: slide.type || '',
                            title: slide.title || '',
                            sectionKey: slide.sectionKey || '',
                          })),
                      };
                    }
                    """
                )
                if (
                    title_and_liturgical_state["confession"]["elementType"] == "title_assignee"
                    and title_and_liturgical_state["confession"]["layout"] == "lower_bar_text"
                    and title_and_liturgical_state["confession"]["type"] == "title-assignee"
                    and title_and_liturgical_state["confession"]["renderClass"] == "title-assignee"
                    and title_and_liturgical_state["confession"]["title"] == "참회기도"
	                    and title_and_liturgical_state["creedTemplatePlaceholderState"]["state"] == "filled"
	                    and title_and_liturgical_state["creedTemplatePlaceholderState"]["hasOutputContent"] is True
	                    and title_and_liturgical_state["creedTemplatePlaceholderState"]["reason"] == "liturgical_body"
	                    and title_and_liturgical_state["closingTemplatePlaceholderState"]["state"] == "filled"
	                    and title_and_liturgical_state["closingTemplatePlaceholderState"]["hasOutputContent"] is True
	                    and title_and_liturgical_state["closingTemplatePlaceholderState"]["reason"] == "closing_visual_asset"
	                    and title_and_liturgical_state["closingTemplatePlaceholderSlides"] == [{
	                        "type": "image",
	                        "imageSrc": "assets/worship-templates/public-closing.png",
	                    }]
	                    and title_and_liturgical_state["doxologyTemplatePlaceholderState"]["state"] == "filled"
	                    and title_and_liturgical_state["doxologyTemplatePlaceholderState"]["hasOutputContent"] is True
	                    and title_and_liturgical_state["doxologyTemplatePlaceholderState"]["reason"] == "fixed_doxology"
	                    and title_and_liturgical_state["doxologyTemplatePlaceholderSlides"][0] == {
	                        "type": "title-assignee",
	                        "title": "송영",
	                        "imageSrc": "",
	                    }
	                    and title_and_liturgical_state["doxologyTemplatePlaceholderSlides"][1:] == [{
	                        "type": "image",
	                        "title": "5 이 천지간 만물들아",
	                        "imageSrc": "assets/hymn-scores/5/slide-01.webp",
	                    }, {
	                        "type": "image",
	                        "title": "5 이 천지간 만물들아",
	                        "imageSrc": "assets/hymn-scores/5/slide-02.webp",
	                    }]
	                    and title_and_liturgical_state["afternoonDoxologyTemplatePlaceholderState"]["state"] == "filled"
	                    and title_and_liturgical_state["afternoonDoxologyTemplatePlaceholderState"]["hasOutputContent"] is True
	                    and title_and_liturgical_state["afternoonDoxologyTemplatePlaceholderState"]["reason"] == "fixed_doxology"
	                    and title_and_liturgical_state["afternoonDoxologyTemplatePlaceholderSlides"][0] == {
	                        "type": "title-assignee",
	                        "title": "송영",
	                        "imageSrc": "",
	                    }
	                    and title_and_liturgical_state["afternoonDoxologyTemplatePlaceholderSlides"][1:] == [{
	                        "type": "image",
	                        "title": "1 만복의 근원 하나님",
	                        "imageSrc": "assets/hymn-scores/1/slide-01.webp",
	                    }, {
	                        "type": "image",
	                        "title": "1 만복의 근원 하나님",
	                        "imageSrc": "assets/hymn-scores/1/slide-02.webp",
	                    }]
	                    and title_and_liturgical_state["sharedScripture"]["readingReferences"] == ["출애굽기 23:14–19"]
	                    and title_and_liturgical_state["sharedScripture"]["readingState"]["state"] == "filled"
		                    and title_and_liturgical_state["sharedScripture"]["readingState"]["reason"] == "scripture_body"
                    and title_and_liturgical_state["sharedScripture"]["readingInput"] is not None
                    and title_and_liturgical_state["sharedScripture"]["readingSlideCount"] == 2
                    and title_and_liturgical_state["sharedScripture"]["placeholderState"]["state"] == "filled"
                    and title_and_liturgical_state["sharedScripture"]["placeholderState"]["reason"] == "scripture_body"
                    and title_and_liturgical_state["sharedScripture"]["placeholderSlideTypes"][:2] == ["title-assignee", "scripture"]
                    and "너는 매년 세 번 내게 절기를 지킬지니라" in "\n".join(title_and_liturgical_state["sharedScripture"]["placeholderSlideTexts"])
                    and title_and_liturgical_state["sharedScripture"]["citationState"]["state"] == "filled"
                    and title_and_liturgical_state["sharedScripture"]["citationState"]["reason"] == "optional_citation_empty"
                    and title_and_liturgical_state["sharedScripture"]["citationInputMode"] == "scripture"
                    and title_and_liturgical_state["sharedScripture"]["citationSlides"] == [{
                        "type": "blank",
                        "elementType": "blank",
                        "liveScriptureControl": True,
                        "isLiveScriptureElement": True,
                    }]
                    and title_and_liturgical_state["sharedScripture"]["targetLabel"] == "성경봉독"
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodyInputReferences"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodySecondReferences"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodyThirdEffectiveReferences"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodyThirdRaw"] == "마 13:31–33, 44–50"
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodyThirdMemo"]["scriptureReferences"] == ["마태복음 13:31–33", "마태복음 13:44–50"]
                    and title_and_liturgical_state["sharedSundaySermon"]["citationInputReferences"] == ["요한복음 15:9", "로마서 5:7–8"]
                    and title_and_liturgical_state["sharedSundaySermon"]["citationSecondReferences"] == ["요한복음 15:9", "로마서 5:7–8"]
                    and title_and_liturgical_state["sharedSundaySermon"]["citationThirdEffectiveReferences"] == ["요한복음 15:9", "로마서 5:7–8"]
                    and title_and_liturgical_state["sharedSundaySermon"]["citationThirdRaw"] == "요 15:9; 롬 5:7–8"
                    and title_and_liturgical_state["sharedSundaySermon"]["citationThirdMemo"]["scriptureReferences"] == ["요한복음 15:9", "로마서 5:7–8"]
                    and title_and_liturgical_state["sharedSundaySermon"]["sermonBodyThirdState"]["state"] == "filled"
                    and title_and_liturgical_state["sharedSundaySermon"]["citationThirdState"]["state"] == "filled"
                    and "presenter-title-assignee" in title_and_liturgical_state["confession"]["html"]
                    and 'presenter-slide--title"' not in title_and_liturgical_state["confession"]["html"]
                    and len(title_and_liturgical_state["chromakey"]) >= 3
                    and title_and_liturgical_state["chromakey"][0]["elementType"] == "title_assignee"
                    and title_and_liturgical_state["chromakey"][0]["layout"] == "lower_bar_text"
                    and title_and_liturgical_state["chromakey"][0]["type"] == "title-assignee"
                    and title_and_liturgical_state["chromakey"][0]["renderClass"] == "title-assignee"
                    and title_and_liturgical_state["chromakey"][0]["title"] == "신앙고백"
                    and title_and_liturgical_state["chromakey"][0]["text"] == "신앙고백\n사도신경"
                    and all(slide["chromakey"] is True for slide in title_and_liturgical_state["chromakey"])
                    and all(slide["outputContext"] == "chromakey" for slide in title_and_liturgical_state["chromakey"])
                    and all(slide["elementType"] == "body_text" for slide in title_and_liturgical_state["chromakey"][1:])
                    and all(slide["layout"] == "lower_bar_text" for slide in title_and_liturgical_state["chromakey"][1:])
                    and all(slide["type"] == "lyrics" for slide in title_and_liturgical_state["chromakey"][1:])
                    and all(slide["renderClass"] == "lyrics" for slide in title_and_liturgical_state["chromakey"][1:])
                    and title_and_liturgical_state["chromakey"][1]["marker"] == "사도신경"
                    and len(title_and_liturgical_state["fullscreen"]) == 2
                    and title_and_liturgical_state["fullscreen"][0]["elementType"] == "title_content"
                    and title_and_liturgical_state["fullscreen"][0]["layout"] == "center_text"
                    and title_and_liturgical_state["fullscreen"][0]["type"] == "title-content"
                    and title_and_liturgical_state["fullscreen"][0]["renderClass"] == "title-content"
                    and title_and_liturgical_state["fullscreen"][0]["title"] == "신앙고백"
                    and title_and_liturgical_state["fullscreen"][0]["text"] == "신앙고백\n사도신경"
                    and all(slide["chromakey"] is False for slide in title_and_liturgical_state["fullscreen"])
                    and all(slide["outputContext"] == "clean" for slide in title_and_liturgical_state["fullscreen"])
                    and title_and_liturgical_state["fullscreen"][1]["elementType"] == "body_text"
                    and title_and_liturgical_state["fullscreen"][1]["layout"] == "center_text"
                    and title_and_liturgical_state["fullscreen"][1]["type"] == "liturgical-body"
                    and title_and_liturgical_state["fullscreen"][1]["renderClass"] == "liturgical-body"
                    and "presenter-slide--liturgical-body" in title_and_liturgical_state["fullscreen"][1]["html"]
                    and "<i aria-hidden" not in title_and_liturgical_state["fullscreen"][1]["html"]
                    and title_and_liturgical_state["fullscreen"][1]["text"] == (
                        "나는 전능하신 아버지 하나님, 천지의 창조주를 믿습니다.\n"
                        "나는 그의 유일하신 아들, 우리 주 예수 그리스도를 믿습니다.\n"
                        "그는 성령으로 잉태되어 동정녀 마리아에게서 나시고,\n"
                        "본디오 빌라도에게 고난을 받아 십자가에 못 박혀 죽으시고,\n"
                        "장사된 지 사흘 만에 죽은 자 가운데서 다시 살아나셨으며,\n"
                        "하늘에 오르시어 전능하신 아버지 하나님 우편에 앉아 계시다가,\n"
                        "거기로부터 살아 있는 자와 죽은 자를 심판하러 오십니다.\n"
                        "나는 성령을 믿으며, 거룩한 공교회와 성도의 교제와\n"
                        "죄를 용서받는 것과 몸의 부활과 영생을 믿습니다. 아멘."
                    )
                    and len(title_and_liturgical_state["scaffold"]) >= 3
                    and title_and_liturgical_state["scaffold"][0]["type"] == "title-assignee"
                    and title_and_liturgical_state["scaffold"][0]["layout"] == "lower_bar_text"
                    and title_and_liturgical_state["scaffold"][0]["title"] == "신앙고백"
                    and title_and_liturgical_state["scaffold"][0]["text"] == "신앙고백\n사도신경"
                    and all(slide["chromakey"] is True for slide in title_and_liturgical_state["scaffold"])
                    and all(slide["outputContext"] == "chromakey" for slide in title_and_liturgical_state["scaffold"])
                    and title_and_liturgical_state["chromakeyCenterTextSlides"] == []
                    and title_and_liturgical_state["scaffoldOutputContexts"].get("clean", 0) >= 1
                    and title_and_liturgical_state["scaffoldOutputContexts"].get("chromakey", 0) > 0
                    and [slide["text"] for slide in title_and_liturgical_state["scaffold"] if slide["type"] == "lyrics"] == [
                        "나는 전능하신 아버지 하나님,\n천지의 창조주를 믿습니다.",
                        "나는 그의 유일하신 아들,\n우리 주 예수 그리스도를 믿습니다.",
                        "그는 성령으로 잉태되어\n동정녀 마리아에게서 나시고,",
                        "본디오 빌라도에게 고난을 받아\n십자가에 못 박혀 죽으시고,",
                        "장사된 지 사흘 만에\n죽은 자 가운데서 다시 살아나셨으며,",
                        "하늘에 오르시어 전능하신 아버지\n하나님 우편에 앉아 계시다가,",
                        "거기로부터 살아 있는 자와\n죽은 자를 심판하러 오십니다.",
                        "나는 성령을 믿으며,\n거룩한 공교회와 성도의 교제와",
                        "죄를 용서받는 것과\n몸의 부활과 영생을 믿습니다. 아멘.",
                    ]
                    and [slide["text"] for slide in title_and_liturgical_state["lordsPrayerScaffold"] if slide["type"] == "lyrics"] == [
                        "하늘에 계신 우리 아버지,\n아버지의 이름을 거룩하게 하시며",
                        "아버지의 나라가 오게 하시며,\n아버지의 뜻이 하늘에서와 같이 땅에서도 이루어지게 하소서.",
                        "오늘 우리에게 일용할 양식을 주시고,\n우리가 우리에게 잘못한 사람을 용서하여 준 것같이,",
                        "우리 죄를 용서하여 주시고,\n우리를 시험에 빠지지 않게 하시고, 악에서 구하소서.",
                        "나라와 권능과 영광이\n영원히 아버지의 것입니다. 아멘.",
                    ]
                    and [slide["text"] for slide in title_and_liturgical_state["lordsPrayerFullscreen"] if slide["type"] == "liturgical-body"] == [
                        "하늘에 계신 우리 아버지,\n"
                        "아버지의 이름을 거룩하게 하시며\n"
                        "아버지의 나라가 오게 하시며,\n"
                        "아버지의 뜻이 하늘에서와 같이 땅에서도 이루어지게 하소서.\n"
                        "오늘 우리에게 일용할 양식을 주시고,\n"
                        "우리가 우리에게 잘못한 사람을 용서하여 준 것같이,\n"
                        "우리 죄를 용서하여 주시고,\n"
                        "우리를 시험에 빠지지 않게 하시고, 악에서 구하소서.\n"
                        "나라와 권능과 영광이\n"
                        "영원히 아버지의 것입니다. 아멘."
                    ]
                    and all(slide["outputContext"] == "chromakey" for slide in title_and_liturgical_state["lordsPrayerScaffold"])
                    and all(slide["outputContext"] == "clean" for slide in title_and_liturgical_state["lordsPrayerFullscreen"])
                    and len([slide for slide in title_and_liturgical_state["lordsPrayerFullscreen"] if slide["type"] == "liturgical-body"]) == 1
                    and [slide["text"] for slide in title_and_liturgical_state["communityScaffold"] if slide["type"] == "lyrics"] == [
                        "우리는 세상으로부터 부름 받은\n하나님의 거룩한 백성입니다.",
                        "또한 세상으로 보냄 받은\n그리스도의 제자입니다.",
                        "하나님을 기쁘게 찬양하는\n성령 충만한 예배자가 되겠습니다.",
                        "진리를 배우고 수호하는\n은혜에 빚진 훈련자가 되겠습니다.",
                        "땅 끝까지 복음을 전파하는\n전도자가 되겠습니다.",
                        "이웃의 아픔을 함께하는\n치유자가 되겠습니다.",
                        "온 성도가 하나 되는\n화해자가 되겠습니다.",
                        "사회적 책임을 다하는\n소명자가 되겠습니다.",
                        "그리하여 우리 모두 하나님을 영화롭게 하는\n검단우리교회 공동체가 되겠습니다.",
                    ]
                    and [slide["text"] for slide in title_and_liturgical_state["communityFullscreen"] if slide["type"] == "liturgical-body"] == [
                        "우리는 세상으로부터 부름 받은 하나님의 거룩한 백성입니다.\n"
                        "또한 세상으로 보냄 받은 그리스도의 제자입니다.\n"
                        "하나님을 기쁘게 찬양하는 성령 충만한 예배자가 되겠습니다.\n"
                        "진리를 배우고 수호하는 은혜에 빚진 훈련자가 되겠습니다.\n"
                        "땅 끝까지 복음을 전파하는 전도자가 되겠습니다.\n"
                        "이웃의 아픔을 함께하는 치유자가 되겠습니다.\n"
                        "온 성도가 하나 되는 화해자가 되겠습니다.\n"
                        "사회적 책임을 다하는 소명자가 되겠습니다.\n"
                        "그리하여 우리 모두 하나님을 영화롭게 하는\n"
                        "검단우리교회 공동체가 되겠습니다."
                    ]
                    and any("#FFC832" in slide["html"] for slide in title_and_liturgical_state["communityScaffold"])
                    and any("#C8FF32" in slide["html"] for slide in title_and_liturgical_state["communityScaffold"])
                    and any("검단우리교회 공동체" in slide["text"] for slide in title_and_liturgical_state["communityFullscreen"])
                    and all("**" not in slide["html"] for slide in title_and_liturgical_state["communityScaffold"])
                    and all(slide["outputContext"] == "chromakey" for slide in title_and_liturgical_state["communityScaffold"])
                    and all(slide["outputContext"] == "clean" for slide in title_and_liturgical_state["communityFullscreen"])
                    and len([slide for slide in title_and_liturgical_state["communityFullscreen"] if slide["type"] == "liturgical-body"]) == 1
                    and all(
                        slide["lineCount"] <= 2
                        for slide in title_and_liturgical_state["lordsPrayerScaffold"]
                        if slide["type"] == "lyrics"
                    )
                    and all(
                        slide["lineCount"] <= 2
                        for slide in title_and_liturgical_state["communityScaffold"]
                        if slide["type"] == "lyrics"
                    )
                    and title_and_liturgical_state["scaffoldClosing"] == [{
                        "elementType": "image",
                        "layout": "media",
                        "type": "image",
                        "title": "2026 표어 이미지",
                        "imageSrc": "assets/worship-templates/public-closing.png",
                        "chromakey": False,
                        "outputContext": "clean",
                    }]
                    and all(
                        slide["lineCount"] <= 2
                        for slide in title_and_liturgical_state["scaffold"]
                        if slide["type"] == "lyrics"
                    )
                ):
                    pass_("presenter-title-and-liturgical-body-contract", json.dumps(title_and_liturgical_state, ensure_ascii=False))
                else:
                    fail("presenter-title-and-liturgical-body-contract", json.dumps(title_and_liturgical_state, ensure_ascii=False))

                form_preset_state = page.evaluate(
                    """
                    () => {
                      const hymnSong = {
                        id: '__smoke_hymn_song__',
                        title: '특송 테스트',
                        hymn_no: '999',
                        versions: [{
                          id: '__smoke_hymn_version__',
                          name: 'Default',
                          is_primary: true,
                          forms: [
                            { id: 'h-v1', part_type: 'Verse', part_number: 1, lyrics: '1절 첫 줄\\n1절 둘째 줄', sort_order: 1 },
                            { id: 'h-c', part_type: 'Chorus', part_number: null, lyrics: '후렴 첫 줄\\n후렴 둘째 줄', sort_order: 2 },
                            { id: 'h-v2', part_type: 'Verse', part_number: 2, lyrics: '2절 첫 줄\\n2절 둘째 줄', sort_order: 3 },
                            { id: 'h-v3', part_type: 'Verse', part_number: 3, lyrics: '3절 첫 줄\\n3절 둘째 줄', sort_order: 4 },
                            { id: 'h-v4', part_type: 'Verse', part_number: 4, lyrics: '마지막 절 첫 줄\\n마지막 절 둘째 줄', sort_order: 5 },
                            { id: 'h-coda', part_type: 'Coda', part_number: null, lyrics: '아멘', sort_order: 6 }
                          ]
                        }]
                      };
                      const ccmSong = {
                        id: '__smoke_ccm_song__',
                        title: '반복 테스트',
                        versions: [{
                          id: '__smoke_ccm_version__',
                          name: 'Default',
                          is_primary: true,
                          forms: [
                            { id: 'c-v1', part_type: 'Verse', part_number: 1, lyrics: 'V1 첫 줄\\nV1 둘째 줄', sort_order: 1 },
                            { id: 'c-c', part_type: 'Chorus', part_number: null, lyrics: 'C 첫 줄\\nC 둘째 줄', sort_order: 2 },
                            { id: 'c-v2', part_type: 'Verse', part_number: 2, lyrics: 'V2 첫 줄\\nV2 둘째 줄', sort_order: 3 }
                          ]
                        }]
                      };
                      const explicitTagSong = {
                        id: '__smoke_explicit_tag_song__',
                        title: '태그 명시 테스트',
                        versions: [{
                          id: '__smoke_explicit_tag_version__',
                          name: 'Default',
                          is_primary: true,
                          forms: [
                            { id: 'et-v1', part_type: 'Verse', part_number: 1, lyrics: 'V1 첫 줄\\nV1 둘째 줄', sort_order: 1 },
                            { id: 'et-c1', part_type: 'Chorus', part_number: null, lyrics: 'C 첫 줄\\nC 둘째 줄', sort_order: 2 },
                            { id: 'et-v2', part_type: 'Verse', part_number: 2, lyrics: 'V2 첫 줄\\nV2 둘째 줄', sort_order: 3 },
                            { id: 'et-b', part_type: 'Bridge', part_number: null, lyrics: 'B 첫 줄\\nB 둘째 줄', sort_order: 4 },
                            { id: 'et-c2', part_type: 'Chorus', part_number: 2, lyrics: 'C2 첫 줄\\nC2 둘째 줄', sort_order: 5 },
                          ]
                        }]
                      };
                      const defaultFormSong = {
                        id: '__smoke_default_form_song__',
                        title: '감사',
                        metadata: {
                          presenter_form: { forms: ['V1', 'V2', 'C', 'V3', 'Coda'], hint: 'V1-V2-C-V3-Coda', strength: 'song-default' }
                        },
                        versions: [{
                          id: '__smoke_default_form_version__',
                          name: 'Default',
                          is_primary: true,
                          forms: [
                            {
                              id: 'df-lyrics',
                              part_type: 'Lyrics',
                              part_number: null,
                              lyrics: '감사 1절 첫 줄\\n감사 1절 둘째 줄\\n\\n감사 2절 첫 줄\\n감사 2절 둘째 줄\\n\\n감사 후렴 첫 줄\\n감사 후렴 둘째 줄\\n\\n감사 3절 첫 줄\\n감사 3절 둘째 줄\\n\\n감사 코다 첫 줄\\n감사 코다 둘째 줄',
                              sort_order: 1
                            }
                          ]
                        }]
                      };
                      const fallbackSong = {
                        id: '__smoke_presenter_fallback_song__',
                        title: '하나님은 너를 지키시는 자 스모크',
                        versions: [
                          {
                            id: '__smoke_presenter_empty_version__',
                            name: '빈 버전',
                            is_primary: true,
                            forms: []
                          },
                          {
                            id: '__smoke_presenter_lyrics_version__',
                            name: '가사 버전',
                            forms: [
                              { id: 'fb-lyrics', part_type: 'Lyrics', part_number: null, lyrics: '하나님은 너를 지키시는 자\\n너의 우편에 그늘 되시니', sort_order: 1 }
                            ]
                          }
                        ]
                      };
                      const hymnScoreSong = {
                        ...hymnSong,
                        id: '__smoke_hymn_score_song__',
                        title: '이 천지간 만물들아',
                        hymn_no: '5',
                      };
                      const hymnScoreSequenceSong = {
                        ...hymnSong,
                        id: '__smoke_hymn_score_sequence_song__',
                        title: '천성을 향해 가는 성도들아',
                        hymn_no: '359',
                        versions: [{
                          id: '__smoke_hymn_score_sequence_version__',
                          name: '새찬송가 악보',
                          is_primary: true,
                          forms: []
                        }],
                      };
                      const offeringSong = {
                        ...hymnSong,
                        id: '__smoke_offering_song__',
                        title: '하나님의 크신 사랑',
                      };
                      state.hymnScoreManifest = {
                        '5': {
                          title: '이 천지간 만물들아',
                          slides: [
                            { src: 'assets/hymn-scores/5/slide-01.webp', sourceSlide: 1 },
                            { src: 'assets/hymn-scores/5/slide-02.webp', sourceSlide: 2 },
                          ],
                        },
                        '359': {
                          title: '천성을 향해 가는 성도들아',
                          slides: [
                            { src: 'assets/hymn-scores/359/slide-01.webp', scoreFormLabel: 'Verse 1' },
                            { src: 'assets/hymn-scores/359/slide-02.webp' },
                            { src: 'assets/hymn-scores/359/slide-03.webp', scoreFormLabel: 'Chorus' },
                            { src: 'assets/hymn-scores/359/slide-04.webp' },
                            { src: 'assets/hymn-scores/359/slide-05.webp', scoreFormLabel: 'Verse 2' },
                            { src: 'assets/hymn-scores/359/slide-06.webp' },
                            { src: 'assets/hymn-scores/359/slide-07.webp', scoreFormLabel: 'Chorus' },
                            { src: 'assets/hymn-scores/359/slide-08.webp' },
                            { src: 'assets/hymn-scores/359/slide-09.webp', scoreFormLabel: 'Verse 3' },
                            { src: 'assets/hymn-scores/359/slide-10.webp' },
                            { src: 'assets/hymn-scores/359/slide-11.webp', scoreFormLabel: 'Chorus' },
                            { src: 'assets/hymn-scores/359/slide-12.webp' },
                          ],
                        },
                      };
                      state.songs = state.songs.filter((song) => !String(song.id || '').startsWith('__smoke_')).concat([hymnSong, hymnScoreSong, hymnScoreSequenceSong, offeringSong, ccmSong, explicitTagSong, defaultFormSong, fallbackSong]);
                      const service = { id: '__smoke_form_service__', type_id: 'sunday-main', date: '2026-07-04' };
                      const hymnItem = {
                        id: '__smoke_hymn_item__',
                        label: '특송',
                        raw_title: '특송 테스트',
                        song_id: hymnSong.id,
                        version_id: '__smoke_hymn_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPresetRules: [{
                            when: { songType: 'hymn' },
                            formPreset: {
                              forms: ['1절', '2절', '간주', '마지막 절'],
                              hint: '1절-2절-간주-마지막 절',
                              strength: 'default'
                            }
                          }]
                        })
                      };
                      const ccmItem = {
                        id: '__smoke_ccm_item__',
                        label: '찬양',
                        raw_title: '반복 테스트',
                        song_id: ccmSong.id,
                        version_id: '__smoke_ccm_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['V1', 'C', 'C'], hint: 'V1-C-C', strength: 'default' }
                        })
                      };
                      const missingItem = {
                        id: '__smoke_missing_item__',
                        label: '찬양',
                        raw_title: '반복 테스트',
                        song_id: ccmSong.id,
                        version_id: '__smoke_ccm_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['V1', 'C', 'B'], hint: 'V1-C-B', strength: 'manual' }
                        })
                      };
                      const explicitTagItem = {
                        id: '__smoke_explicit_tag_item__',
                        label: '찬양',
                        raw_title: '태그 명시 테스트',
                        song_id: explicitTagSong.id,
                        version_id: '__smoke_explicit_tag_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['V', 'C', 'V', 'C', 'Tags'], hint: 'V-C-V-C-Tags', strength: 'manual' }
                        })
                      };
                      const explicitGenericItem = {
                        id: '__smoke_explicit_generic_item__',
                        label: '찬양',
                        raw_title: '태그 명시 테스트',
                        song_id: explicitTagSong.id,
                        version_id: '__smoke_explicit_tag_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['V', 'C', 'V', 'C'], hint: 'V-C-V-C', strength: 'manual' }
                        })
                      };
                      const defaultFormItem = {
                        id: '__smoke_default_form_item__',
                        label: '찬양',
                        raw_title: '감사',
                        song_id: defaultFormSong.id,
                        version_id: '__smoke_default_form_version__',
                        memo: serializeServiceItemMemo({ elementType: 'praise' })
                      };
                      const fallbackVersionItem = {
                        id: '__smoke_presenter_fallback_version_item__',
                        label: '결단',
                        raw_title: '하나님은 너를 지키시는 자 스모크',
                        song_id: fallbackSong.id,
                        version_id: '__smoke_presenter_empty_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['Lyrics'], hint: 'Lyrics', strength: 'manual' }
                        })
                      };
                      const fallbackTitleItem = {
                        id: '__smoke_presenter_fallback_title_item__',
                        label: '결단',
                        raw_title: '하나님은 너를 지키시는 자 스모크',
                        song_id: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          formPreset: { forms: ['Lyrics'], hint: 'Lyrics', strength: 'manual' }
                        })
                      };
                      const hymnAutoItem = {
                        id: '__smoke_hymn_auto_item__',
                        label: '찬양',
                        raw_title: '특송 테스트',
                        song_id: hymnSong.id,
                        version_id: '__smoke_hymn_version__',
                        memo: serializeServiceItemMemo({ elementType: 'praise' })
                      };
                      const scoreItem = {
                        id: '__smoke_score_item__',
                        label: '찬송',
                        raw_title: '특송 테스트',
                        song_id: hymnSong.id,
                        version_id: '__smoke_hymn_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const scoreImageItem = {
                        id: '__smoke_score_image_item__',
                        label: '찬송',
                        raw_title: '악보 이미지 테스트',
                        song_id: hymnSong.id,
                        version_id: '__smoke_hymn_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score',
                          asset: {
                            kind: 'score',
                            name: '찬양 PPT',
                            slides: [
                              { url: 'assets/worship-backgrounds/26-A1.png', name: '1', scoreFormLabel: 'Verse 1' },
                              { url: 'assets/worship-backgrounds/26-A2.png', name: '2', scoreFormLabel: 'Chorus' },
                            ]
                          }
                        })
                      };
                      const scoreManifestItem = {
                        id: '__smoke_score_manifest_item__',
                        label: '찬송',
                        raw_title: '5 이 천지간 만물들아',
                        song_id: hymnScoreSong.id,
                        version_id: '__smoke_hymn_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const scoreSequenceItem = {
                        id: '__smoke_score_sequence_item__',
                        label: '파송찬송',
                        raw_title: '359 천성을 향해 가는 성도들아',
                        song_id: hymnScoreSequenceSong.id,
                        version_id: '__smoke_hymn_score_sequence_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score',
                          formPreset: { forms: ['V1', 'V2', 'C', '간주', 'V3', 'C', 'C'], hint: 'V1-V2-C-간주-V3-C-C', strength: 'manual' }
                        })
                      };
                      const scoreRawTitleItem = {
                        id: '__smoke_score_raw_title_item__',
                        label: '찬송',
                        raw_title: '5 이 천지간 만물들아',
                        song_id: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const offeringScoreItem = {
                        id: '__smoke_offering_score_item__',
                        label: '봉헌찬송',
                        raw_title: '하나님의 크신 사랑',
                        song_id: offeringSong.id,
                        version_id: '__smoke_hymn_version__',
                        _worshipSectionId: '__smoke_offering_section__',
                        _worshipSectionKey: 'offering',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const flexibleOfferingScoreItem = {
                        id: '__smoke_flexible_offering_score_item__',
                        label: '봉헌찬송',
                        raw_title: '봉헌특송',
                        song_id: hymnScoreSong.id,
                        version_id: '__smoke_hymn_version__',
                        _worshipSectionId: '__smoke_flexible_offering_section__',
                        _worshipSectionKey: 'offering',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          inputMode: 'score_db',
                          outputMode: 'score'
                        })
                      };
                      const flexibleOfferingLegacyScoreItem = {
                        id: '__smoke_flexible_offering_legacy_score_item__',
                        label: '봉헌찬송',
                        raw_title: '',
                        song_id: hymnScoreSong.id,
                        version_id: '__smoke_hymn_version__',
                        _worshipSectionId: '__smoke_flexible_offering_section__',
                        _worshipSectionKey: 'offering',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          inputMode: 'praise_db',
                          outputMode: 'score'
                        })
                      };
                      const specialScoreItem = {
                        id: '__smoke_special_score_item__',
                        label: '특송',
                        raw_title: '특송 테스트',
                        song_id: '',
                        _worshipSectionId: '__smoke_special_section__',
                        _worshipSectionKey: 'special_song',
                        assignee: '할렐루야 찬양대',
                        _worshipSectionTitle: '특송',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const specialLinkedScoreItem = {
                        id: '__smoke_special_linked_score_item__',
                        label: '특송',
                        raw_title: '특송 테스트',
                        song_id: hymnSong.id,
                        version_id: '__smoke_hymn_version__',
                        _worshipSectionId: '__smoke_special_linked_section__',
                        _worshipSectionKey: 'special_song',
                        assignee: '할렐루야 찬양대',
                        _worshipSectionTitle: '특송',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const doxologyScoreItem = {
                        id: '__smoke_doxology_score_item__',
                        label: '송영',
                        raw_title: '5 이 천지간 만물들아',
                        song_id: hymnScoreSong.id,
                        version_id: '__smoke_hymn_version__',
                        _worshipSectionId: '__smoke_doxology_section__',
                        _worshipSectionKey: 'doxology',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          outputMode: 'score'
                        })
                      };
                      const audioMemo = serializeServiceItemMemo({
                        elementType: 'audio',
                        asset: { kind: 'audio', name: '성가대 MR', url: 'assets/audio/choir.m4a' }
                      });
                      const audioItem = {
                        id: '__smoke_audio_item__',
                        label: '특송 음원',
                        raw_title: '성가대 MR',
                        song_id: '',
                        memo: audioMemo
                      };
                      const syncedLyricsItem = {
                        id: '__smoke_synced_lyrics_item__',
                        label: '찬양',
                        raw_title: '반복 테스트',
                        song_id: ccmSong.id,
                        version_id: '__smoke_ccm_version__',
                        memo: serializeServiceItemMemo({
                          elementType: 'praise',
                          asset: {
                            kind: 'synced_lyrics',
                            name: '반복 테스트 자동 넘김',
                            audio: { name: '반복 테스트 음원', url: 'assets/audio/children-praise.mp3' },
                            timing: {
                              duration: 52,
                              cross: 46.5,
                              pages: [
                                { page: 1, start: 12.3 },
                                { page: 2, start: 24.6 },
                                { page: 3, start: 36.9 },
                              ],
                            },
                          },
                        }),
                      };
                      const importedDeckItem = {
                        id: '__smoke_imported_deck_item__',
                        label: '설교 자료',
                        raw_title: '요셉 이야기',
                        song_id: '',
                        _worshipSectionKey: 'sermon_media',
                        _worshipSectionTitle: '설교 자료',
                        memo: serializeServiceItemMemo({
                          elementType: 'image',
                          asset: {
                            kind: 'imported_deck',
                            name: '요셉 이야기',
                            manifestUrl: 'cache/keynote/joseph/manifest.json',
                            fingerprint: 'deck-v1-smoke',
                            slides: [
                              { url: 'cache/keynote/joseph/stage-001.png', name: 'Stage 1' },
                              { url: 'cache/keynote/joseph/stage-002.png', name: 'Stage 2' },
                            ],
                          },
                        }),
                      };
                      const hymnAllSlides = buildPresenterSlidesForServiceItem(hymnItem, service, 0);
                      const hymnSlides = hymnAllSlides.filter((slide) => slide.type === 'lyrics');
                      const hymnBlankSlides = hymnAllSlides.filter((slide) => slide.type === 'blank');
                      const ccmSlides = buildPresenterSlidesForServiceItem(ccmItem, service, 1).filter((slide) => slide.type === 'lyrics');
                      const missingSlides = buildPresenterSlidesForServiceItem(missingItem, service, 2);
                      const explicitTagSlides = buildPresenterSlidesForServiceItem(explicitTagItem, service, 2.1).filter((slide) => slide.type === 'lyrics');
                      const explicitGenericSlides = buildPresenterSlidesForServiceItem(explicitGenericItem, service, 2.15).filter((slide) => slide.type === 'lyrics');
                      const defaultFormSlides = buildPresenterSlidesForServiceItem(defaultFormItem, service, 2.2).filter((slide) => slide.type === 'lyrics');
                      const fallbackVersionSlides = buildPresenterSlidesForServiceItem(fallbackVersionItem, service, 2.25);
                      const fallbackTitleSlides = buildPresenterSlidesForServiceItem(fallbackTitleItem, service, 2.3);
                      const hymnAutoSlides = buildPresenterSlidesForServiceItem(hymnAutoItem, service, 2.4).filter((slide) => slide.type === 'lyrics');
                      const scoreAllSlides = buildPresenterSlidesForServiceItem(scoreItem, service, 3);
                      const scoreSlides = scoreAllSlides.filter((slide) => slide.sourceType === 'score');
                      const scoreImageAllSlides = buildPresenterSlidesForServiceItem(scoreImageItem, service, 4);
                      const scoreImageSlides = scoreImageAllSlides.filter((slide) => slide.sourceType === 'score');
                      const longScoreSlides = Array.from({ length: 12 }, (_, slideIndex) => ({
                        id: `__smoke_long_score__:${slideIndex}`,
                        sectionId: '__smoke_long_score_section__',
                        elementId: '__smoke_long_score_element__',
                        type: 'image',
                        elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
                        layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                        sourceType: 'score',
                        componentType: 'score',
                        scoreBackground: true,
                        imageSrc: `assets/hymn-scores/999/slide-${String(slideIndex + 1).padStart(2, '0')}.webp`,
                      }));
                      const longScoreWarmupSourcesStart = presenterOutputWarmupSourcesForPayload({
                        serviceId: '__smoke_long_score_service__',
                        slides: longScoreSlides,
                        index: 0,
                        chromakey: false
                      }, longScoreSlides[0]);
                      const longScoreWarmupSourcesMiddle = presenterOutputWarmupSourcesForPayload({
                        serviceId: '__smoke_long_score_service__',
                        slides: longScoreSlides,
                        index: 6,
                        chromakey: false
                      }, longScoreSlides[6]);
                      const longScoreWarmupKeys = [
                        presenterOutputWarmupKey({ serviceId: '__smoke_long_score_service__' }, longScoreWarmupSourcesStart),
                        presenterOutputWarmupKey({ serviceId: '__smoke_long_score_service__' }, longScoreWarmupSourcesMiddle),
                      ];
                      const scoreManifestAllSlides = buildPresenterSlidesForServiceItem(scoreManifestItem, service, 5);
                      const scoreManifestSlides = scoreManifestAllSlides.filter((slide) => slide.sourceType === 'score');
                      const scoreSequenceSlides = buildPresenterSlidesForServiceItem(scoreSequenceItem, service, 5.5)
                        .filter((slide) => slide.sourceType === 'score');
                      const scoreRawTitleAllSlides = buildPresenterSlidesForServiceItem(scoreRawTitleItem, service, 6);
                      const scoreRawTitleSlides = scoreRawTitleAllSlides.filter((slide) => slide.sourceType === 'score');
                      const offeringScoreSlides = buildPresenterSlidesForServiceItem(offeringScoreItem, service, 7);
                      const flexibleOfferingScoreSlides = buildPresenterSlidesForServiceItem(flexibleOfferingScoreItem, service, 7.1);
                      const flexibleOfferingLegacyScoreSlides = buildPresenterSlidesForServiceItem(flexibleOfferingLegacyScoreItem, service, 7.2);
                      const specialScoreSlides = buildPresenterSlidesForServiceItem(specialScoreItem, service, 8);
                      const specialLinkedScoreSlides = buildPresenterSlidesForServiceItem(specialLinkedScoreItem, service, 8.1);
                      const allGenerationSpecialSlides = buildPresenterSlidesForServiceItem({
                        ...specialLinkedScoreItem,
                        id: '__smoke_all_generation_special_item__',
                        raw_title: '한 사람',
                        assignee: '카다로스 중창단',
                      }, {
                        ...service,
                        type_id: 'sunday-main',
                        alias: '온세대 찬양예배',
                        _worshipSourceRef: { sunday_main_variant: 'all_generations' },
                      }, 8.2);
                      const doxologyScoreSlides = buildPresenterSlidesForServiceItem(doxologyScoreItem, service, 9);
                      const sundayFirstMainScoreSlides = buildPresenterSlidesForServiceItem({
                        ...scoreItem,
                        id: '__smoke_sunday_first_main_score__',
                        label: '찬양 1',
                        _worshipSectionKey: 'praise'
                      }, { ...service, type_id: 'sunday-first' }, 10);
                      const sectionSongTitleSlides = {
                        offering: offeringScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          type: slide.type,
                          title: slide.title,
                          text: slide.text,
                          sectionHeading: slide.sectionHeading || '',
                          sectionKey: slide.sectionKey,
                          layout: slide.layout,
                          body: renderPresenterSlideBody(slide).trim(),
                        })),
                        special: specialScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          type: slide.type,
                          title: slide.title,
                          text: slide.text,
                          sectionHeading: slide.sectionHeading || '',
                          sectionKey: slide.sectionKey,
                          layout: slide.layout,
                          body: renderPresenterSlideBody(slide).trim(),
                        })),
                        doxology: doxologyScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          type: slide.type,
                          title: slide.title,
                          text: slide.text,
                          sectionHeading: slide.sectionHeading || '',
                          sectionKey: slide.sectionKey,
                          layout: slide.layout,
                          body: renderPresenterSlideBody(slide).trim(),
                        })),
                      };
                      const specialSectionTitleSlides = specialScoreSlides.filter((slide) => slide.type === 'title-assignee').map((slide) => ({
                        type: slide.type,
                        elementType: slide.elementType || '',
                        layout: slide.layout || '',
                        title: slide.title || '',
                        assignee: slide.assignee || '',
                        text: slide.text || '',
                        sectionKey: slide.sectionKey || '',
                        body: renderPresenterSlideBody(slide).trim(),
                      }));
                      const specialLinkedIntroSlides = specialLinkedScoreSlides
                        .filter((slide) => slide.type === 'title-assignee' || slide.type === 'song-title')
                        .map((slide) => ({
                          type: slide.type,
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                        }));
                      const specialLinkedLyricsSlides = specialLinkedScoreSlides
                        .filter((slide) => slide.type === 'lyrics' || slide.type === 'blank')
                        .map((slide) => ({
                          type: slide.type,
                          marker: slide.marker || '',
                          text: slide.text || '',
                          formKey: slide.formKey || '',
                          sectionKey: slide.sectionKey || '',
                        }));
                      const thirdManualSpecialTitleSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_third_manual_special_item__',
                        label: '특송',
                        raw_title: '',
                        song_id: '',
                        assignee: '할렐루야 찬양대',
                        _worshipSectionId: '__smoke_third_special_section__',
                        _worshipSectionKey: 'special_song',
                        _worshipSectionTitle: '특송',
                        memo: serializeServiceItemMemo({ elementType: 'praise' })
                      }, { ...service, type_id: 'sunday-main' }, 8.5)
                        .filter((slide) => slide.type === 'title-assignee')
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                        }));
                      const thirdEmptySpecialMissingSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_third_empty_special_item__',
                        label: '특송',
                        raw_title: '',
                        song_id: '',
                        assignee: '',
                        _worshipSectionId: '__smoke_third_special_section__',
                        _worshipSectionKey: 'special_song',
                        _worshipSectionTitle: '특송',
                        memo: serializeServiceItemMemo({ elementType: 'praise' })
                      }, { ...service, type_id: 'sunday-main' }, 8.6)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                          missingContent: Boolean(slide.missingContent),
                          missingReason: slide.missingReason || '',
                          inputMode: slide.inputMode || '',
                          contentState: slide.contentState || '',
                          warnings: slide.warnings || [],
                        }));
                      const thirdTitlePersonSpecialSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_third_title_person_special_item__',
                        label: '특송',
                        raw_title: '청년부 특송',
                        song_id: '',
                        assignee: '청년부',
                        _worshipSectionId: '__smoke_third_special_section__',
                        _worshipSectionKey: 'special_song',
                        _worshipSectionTitle: '특송',
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      }, { ...service, type_id: 'sunday-main' }, 8.7)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                        }));
                      const specialInputModes = {
                        sundayMain: (() => {
                          const item = {
                            id: '__smoke_special_mode_sunday_main__',
                            label: '특송',
                            raw_title: '',
                            song_id: '',
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            memo: serializeServiceItemMemo({ elementType: 'praise' })
                          };
                          const targetService = { ...service, type_id: 'sunday-main' };
                          return {
                            mode: servicePraiseInputMode(item, parseServiceItemMemo(item.memo), targetService),
                            requiresSong: serviceItemRequiresSongSelection(item, targetService),
                          };
                        })(),
                        sundaySecond: (() => {
                          const item = {
                            id: '__smoke_special_mode_sunday_second__',
                            label: '특송',
                            raw_title: '',
                            song_id: '',
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            memo: serializeServiceItemMemo({ elementType: 'praise' })
                          };
                          const targetService = { ...service, type_id: 'sunday-second' };
                          return {
                            mode: servicePraiseInputMode(item, parseServiceItemMemo(item.memo), targetService),
                            requiresSong: serviceItemRequiresSongSelection(item, targetService),
                          };
                        })(),
                        monthlyYesterday: (() => {
                          const item = {
                            id: '__smoke_special_mode_monthly_yesterday__',
                            label: '특송',
                            raw_title: '430 주와 같이 길 가는 것',
                            song_id: '',
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            memo: serializeServiceItemMemo({ elementType: 'praise' })
                          };
                          const targetService = { ...service, type_id: 'monthly', date: '2026-08-07', service_date: '2026-08-07' };
                          return {
                            mode: servicePraiseInputMode(item, parseServiceItemMemo(item.memo), targetService),
                            requiresSong: serviceItemRequiresSongSelection(item, targetService),
                          };
                        })(),
                        manualSlidesOutsideSundayMain: (() => {
                          const item = {
                            id: '__smoke_special_mode_manual_slides__',
                            label: '특송',
                            raw_title: '',
                            song_id: '',
                            _worshipSectionKey: 'special_song',
                            _worshipSectionTitle: '특송',
                            memo: serializeServiceItemMemo({ elementType: 'praise', slides: ['기관 특송'] })
                          };
                          const targetService = { ...service, type_id: 'sunday-second' };
                          return {
                            mode: servicePraiseInputMode(item, parseServiceItemMemo(item.memo), targetService),
                            requiresSong: serviceItemRequiresSongSelection(item, targetService),
                          };
                        })(),
                      };
                      const emptyTemplateInputSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_empty_template_input_item__',
                        label: '대표기도',
                        raw_title: '',
                        song_id: '',
                        assignee: '',
                        _worshipSectionId: '__smoke_empty_template_input_section__',
                        _worshipSectionKey: 'prayer',
                        _worshipSectionTitle: '대표기도',
                        _worshipTemplateProjected: true,
                        _worshipTemplatePlaceholder: true,
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      }, { ...service, type_id: 'sunday-main' }, 8.7)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                          missingContent: Boolean(slide.missingContent),
                          missingReason: slide.missingReason || '',
                          inputMode: slide.inputMode || '',
                          contentState: slide.contentState || '',
                          warnings: slide.warnings || [],
                        }));
                      const missingSermonBodySlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_missing_sermon_body_item__',
                        label: '설교 본문',
                        raw_title: '',
                        song_id: '',
                        assignee: '',
                        _worshipSectionId: '__smoke_missing_sermon_section__',
                        _worshipSectionKey: 'sermon',
                        _worshipSectionTitle: '설교',
                        memo: serializeServiceItemMemo({ elementType: 'scripture_body' })
                      }, { ...service, type_id: 'sunday-main' }, 8.75)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                          missingContent: Boolean(slide.missingContent),
                          missingReason: slide.missingReason || '',
                          inputMode: slide.inputMode || '',
                          contentState: slide.contentState || '',
                          warnings: slide.warnings || [],
                        }));
                      const missingSermonTitleSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_missing_sermon_title_item__',
                        label: '설교 제목',
                        raw_title: '',
                        song_id: '',
                        assignee: '김남영 목사',
                        _worshipSectionId: '__smoke_missing_sermon_section__',
                        _worshipSectionKey: 'sermon',
                        _worshipSectionTitle: '설교',
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      }, { ...service, type_id: 'sunday-main' }, 8.76)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                          missingContent: Boolean(slide.missingContent),
                          missingReason: slide.missingReason || '',
                          inputMode: slide.inputMode || '',
                          contentState: slide.contentState || '',
                          warnings: slide.warnings || [],
                        }));
                      const sermonSubgroupHeaderService = { id: '__smoke_sermon_subgroup_header_service__', type_id: 'sunday-main', date: '2026-07-04' };
                      const sermonSubgroupHeaderItem = normalizeServiceItem({
                        id: '__smoke_sermon_subgroup_header_item__',
                        service_id: sermonSubgroupHeaderService.id,
                        label: '설교 제목',
                        raw_title: '',
                        song_id: '',
                        assignee: '',
                        _worshipSectionId: '__smoke_sermon_subgroup_header_section__',
                        _worshipSectionKey: 'sermon',
                        _worshipSectionTitle: '설교',
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      });
                      state.services = state.services
                        .filter((item) => item.id !== sermonSubgroupHeaderService.id)
                        .concat([sermonSubgroupHeaderService]);
                      state.serviceItems[sermonSubgroupHeaderService.id] = [sermonSubgroupHeaderItem];
                      const sermonSubgroupHeaderHtml = renderPresenterBoardSubgroup({
                        id: sermonSubgroupHeaderItem.id,
                        label: '설교',
                        title: '',
                        name: '설교',
                        slides: [{
                          slide: {
                            id: '__smoke_sermon_subgroup_header_slide__',
                            elementId: sermonSubgroupHeaderItem.id,
                            type: 'title-assignee',
                            elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                            sectionKey: 'sermon',
                            sectionLabel: '설교',
                            sectionTitle: '설교',
                            elementLabel: '',
                            title: '설교',
                            warnings: ['입력 필요'],
                          },
                          slideIndex: 11,
                        }],
                      }, -1, sermonSubgroupHeaderService.id, { showHead: true });
                      const sermonSubgroupHeaderNode = document.createElement('div');
                      sermonSubgroupHeaderNode.innerHTML = sermonSubgroupHeaderHtml;
                      const sermonSubgroupHeaderLabels = [...sermonSubgroupHeaderNode.querySelectorAll('.svc-board-subgroup-head > span:not(.svc-presenter-warnings)')]
                        .map((node) => node.textContent.trim());
                      const sermonSubgroupControlLabels = [...sermonSubgroupHeaderNode.querySelectorAll('.svc-board-subgroup-control-label')]
                        .map((node) => node.textContent.trim());
                      const missingTitlePersonAssigneeSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_missing_title_person_assignee_item__',
                        label: '공동기도',
                        raw_title: '공동기도 제목',
                        song_id: '',
                        assignee: '',
                        _worshipSectionId: '__smoke_missing_corporate_prayer_section__',
                        _worshipSectionKey: 'corporate_prayer',
                        _worshipSectionTitle: '공동기도',
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      }, { ...service, type_id: 'sunday-main' }, 8.77)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          sectionKey: slide.sectionKey || '',
                          missingContent: Boolean(slide.missingContent),
                          missingReason: slide.missingReason || '',
                          inputMode: slide.inputMode || '',
                          contentState: slide.contentState || '',
                          warnings: slide.warnings || [],
                        }));
                      const defaultTemplateInputSlides = buildPresenterSlidesForServiceItem({
                        id: '__smoke_default_template_input_item__',
                        label: '대표기도',
                        raw_title: '',
                        song_id: '',
                        assignee: '김남영 목사',
                        _worshipSectionId: '__smoke_default_template_input_section__',
                        _worshipSectionKey: 'prayer',
                        _worshipSectionTitle: '대표기도',
                        _worshipTemplateProjected: true,
                        _worshipTemplatePlaceholder: true,
                        memo: serializeServiceItemMemo({ elementType: 'title_person' })
                      }, { ...service, type_id: 'sunday-main' }, 8.8)
                        .map((slide) => ({
                          type: slide.type,
                          elementType: slide.elementType || '',
                          layout: slide.layout || '',
                          title: slide.title || '',
                          assignee: slide.assignee || '',
                          text: slide.text || '',
                          missingContent: Boolean(slide.missingContent),
                          warnings: slide.warnings || [],
                        }));
                      const audioSlides = buildPresenterSlidesForServiceItem(audioItem, service, 9);
                      const syncedLyricsSlides = buildPresenterSlidesForServiceItem(syncedLyricsItem, service, 9.1);
                      const importedDeckSlides = buildPresenterSlidesForServiceItem(importedDeckItem, service, 9.2);
                      const warningHtml = renderPresenterBoardSubgroup({
                        id: '__smoke_warning_group__',
                        label: '찬양',
                        title: '반복 테스트',
                        name: '찬양 / 반복 테스트',
                        slides: missingSlides.map((slide, slideIndex) => ({ slide, slideIndex }))
                      }, 0, service.id, { showHead: true });
                      const warningNode = document.createElement('div');
                      warningNode.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;';
                      warningNode.innerHTML = warningHtml;
                      document.body.appendChild(warningNode);
                      const warningHead = warningNode.querySelector('.svc-board-subgroup-head');
                      const warningTitle = warningNode.querySelector('.svc-board-subgroup-head strong');
                      const warningChip = warningNode.querySelector('.svc-presenter-warning');
                      const warningHeadRect = warningHead?.getBoundingClientRect();
                      const warningTitleRect = warningTitle?.getBoundingClientRect();
                      const warningChipRect = warningChip?.getBoundingClientRect();
                      const warningLayout = {
                        headDisplay: warningHead ? getComputedStyle(warningHead).display : '',
                        headWidth: warningHeadRect?.width || 0,
                        chipGap: warningChipRect && warningTitleRect ? Math.round(warningChipRect.left - warningTitleRect.right) : null,
                      };
                      warningNode.remove();
                      const scoreBadgeHtml = renderPresenterBoardSubgroup({
                        id: '__smoke_score_badge_group__',
                        label: '찬송',
                        title: '악보 이미지 테스트',
                        name: '찬송 / 악보 이미지 테스트',
                        slides: scoreImageSlides.map((slide, slideIndex) => ({ slide, slideIndex }))
                      }, 0, service.id, { showHead: true });
                      const scoreBadgeNode = document.createElement('div');
                      scoreBadgeNode.innerHTML = scoreBadgeHtml;
                      const scoreSafeArea = (() => {
                        const host = document.createElement('div');
                        host.className = 'svc-slide-mini-output no-chromakey';
                        host.style.cssText = 'position:fixed;left:-2000px;top:0;width:1152px;height:648px;';
                        host.innerHTML = `<span class="svc-slide-mini-canvas" style="width:1152px;height:648px;transform:none">${renderPresenterSlideFrame(scoreManifestSlides[0], { preview: true })}</span>`;
                        document.body.appendChild(host);
                        const slideEl = host.querySelector('.presenter-slide');
                        const imageEl = host.querySelector('.presenter-image');
                        const slideRect = slideEl?.getBoundingClientRect();
                        const imageRect = imageEl?.getBoundingClientRect();
                        const metrics = slideRect && imageRect ? {
                          className: slideEl.className,
                          slideBackground: getComputedStyle(slideEl).backgroundColor,
                          imageBackground: getComputedStyle(imageEl).backgroundImage,
                          imageBackgroundColor: getComputedStyle(imageEl).backgroundColor,
                          top: Math.round(imageRect.top - slideRect.top),
                          right: Math.round(slideRect.right - imageRect.right),
                          bottom: Math.round(slideRect.bottom - imageRect.bottom),
                          left: Math.round(imageRect.left - slideRect.left),
                        } : null;
                        host.remove();
                        return metrics;
                      })();
                      // A linked song must resolve in the catalog before save rows are built
                      // (unresolved links now block the save instead of persisting blindly).
                      state.songs = state.songs.concat([{ id: '__smoke_missing_song_object__', title: '카탈로그 곡', versions: [] }]);
                      const persistenceStateRows = buildWorshipPersistenceRows({ ...service, id: '__smoke_content_state_service__' }, [
                        {
                          id: '__smoke_persist_empty_special_item__',
                          service_id: '__smoke_content_state_service__',
                          label: '특송',
                          raw_title: '',
                          song_id: '',
                          assignee: '',
                          _worshipSectionKey: 'special_song',
                          _worshipSectionTitle: '특송',
                          memo: serializeServiceItemMemo({ elementType: 'praise' })
                        },
                        {
                          id: '__smoke_persist_default_prayer_item__',
                          service_id: '__smoke_content_state_service__',
                          label: '대표기도',
                          raw_title: '',
                          song_id: '',
                          assignee: '김남영 목사',
                          _worshipSectionKey: 'prayer',
                          _worshipSectionTitle: '대표기도',
                          memo: serializeServiceItemMemo({ elementType: 'title_person' })
                        },
                        {
                          id: '__smoke_persist_song_id_item__',
                          service_id: '__smoke_content_state_service__',
                          label: '찬양',
                          raw_title: '',
                          song_id: '__smoke_missing_song_object__',
                          assignee: '',
                          _worshipSectionKey: 'praise',
                          _worshipSectionTitle: '찬양',
                          memo: serializeServiceItemMemo({ elementType: 'praise' })
                        }
                      ], {}, {}, {
                        elementTypedStateColumns: { inputMode: true, contentState: true }
                      }).elements.map((element) => ({
                        label: element.source_ref?.label || '',
                        songId: element.song_id || '',
                        inputMode: element.config?.inputMode || '',
                        typedInputMode: element.input_mode || '',
                        contentState: element.config?.contentState || null,
                        typedContentState: element.content_state || null,
                      }));
                      return {
                        hymnTypes: hymnAllSlides.map((slide) => slide.type),
                        hymnTitleTexts: hymnAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.text),
                        hymnMarkers: hymnSlides.map((slide) => slide.marker),
                        hymnTexts: hymnSlides.map((slide) => slide.text),
                        hymnWarnings: [...new Set(hymnAllSlides.flatMap((slide) => slide.warnings || []))],
                        hymnBlankCount: hymnBlankSlides.length,
                        hymnBlankText: hymnBlankSlides.map((slide) => slide.text).join(''),
                        hymnBlankLayout: hymnBlankSlides[0]?.layout || '',
                        ccmMarkers: ccmSlides.map((slide) => slide.marker),
                        ccmTexts: ccmSlides.map((slide) => slide.text),
                        ccmFormKeys: ccmSlides.map((slide) => slide.formKey),
                        explicitTagMarkers: explicitTagSlides.map((slide) => slide.marker),
                        explicitTagTexts: explicitTagSlides.map((slide) => slide.text),
                        explicitGenericMarkers: explicitGenericSlides.map((slide) => slide.marker),
                        explicitGenericTexts: explicitGenericSlides.map((slide) => slide.text),
                        groupedLetterMarkers: [
                          presenterFormMarker({ part_type: 'Chorus', part_number: null, label: 'CB' }),
                          presenterFormMarker({ part_type: 'Chorus', part_number: null, label: 'Chorus B' }),
                          normalizePresenterScoreFormLabel('C B'),
                        ],
                        defaultFormMetadataSummary: serviceFormPresetSummary(normalizeSongMetadata(defaultFormSong.metadata).presenter_form),
                        defaultFormMarkers: defaultFormSlides.map((slide) => slide.marker),
                        defaultFormTexts: defaultFormSlides.map((slide) => slide.text),
                        unifiedHymnTitleText: formatPresenterSongTitleText(presenterSongTitleDisplayTitle(
                          { title: '만복의 근원 하나님', hymn_no: '1' },
                          { hymn_no: '통 1', name: '통일 1' },
                          '',
                          ''
                        )),
                        fallbackVersionTexts: fallbackVersionSlides.filter((slide) => slide.type === 'lyrics').map((slide) => slide.text),
                        fallbackVersionWarnings: [...new Set(fallbackVersionSlides.flatMap((slide) => slide.warnings || []))],
                        fallbackTitleTexts: fallbackTitleSlides.filter((slide) => slide.type === 'lyrics').map((slide) => slide.text),
                        fallbackTitleWarnings: [...new Set(fallbackTitleSlides.flatMap((slide) => slide.warnings || []))],
                        hymnAutoMarkers: hymnAutoSlides.map((slide) => slide.marker),
                        hymnAutoTexts: hymnAutoSlides.map((slide) => slide.text),
                        scoreTitleSlides: scoreAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          type: slide.type,
                          title: slide.title,
                          text: slide.text
                        })),
                        scoreTitleTexts: scoreAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.text),
                        scoreManifestTitleTexts: scoreManifestAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.text),
                        scoreRawTitleTexts: scoreRawTitleAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.text),
                        scoreImageTitleSlides: scoreImageAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.title),
                        scoreManifestTitleSlides: scoreManifestAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.title),
                        scoreRawTitleTitleSlides: scoreRawTitleAllSlides.filter((slide) => slide.type === 'song-title').map((slide) => slide.title),
                        offeringScoreTitleSlides: offeringScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          title: slide.title,
                          sectionTitle: slide.sectionTitle,
                          label: slide.label
                        })),
                        flexibleOfferingScoreMode: serviceItemOutputMode(
                          flexibleOfferingScoreItem,
                          parseServiceItemMemo(flexibleOfferingScoreItem.memo)
                        ),
                        flexibleOfferingScoreSlides: flexibleOfferingScoreSlides.filter((slide) => slide.sourceType === 'score').map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          imageSrc: slide.imageSrc
                        })),
                        flexibleOfferingLegacyScoreMode: serviceItemOutputMode(
                          flexibleOfferingLegacyScoreItem,
                          parseServiceItemMemo(flexibleOfferingLegacyScoreItem.memo)
                        ),
                        flexibleOfferingLegacyScoreSlides: flexibleOfferingLegacyScoreSlides.filter((slide) => slide.sourceType === 'score').map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          imageSrc: slide.imageSrc
                        })),
                        specialScoreTitleSlides: specialScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          title: slide.title,
                          sectionTitle: slide.sectionTitle,
                          label: slide.label
                        })),
                        specialScoreSourceCount: specialScoreSlides.filter((slide) =>
                          slide.sourceType === 'score' || slide.componentType === 'score' || slide.scoreBackground
                        ).length,
                        specialLinkedScoreSourceCount: specialLinkedScoreSlides.filter((slide) =>
                          slide.sourceType === 'score' || slide.componentType === 'score' || slide.scoreBackground
                        ).length,
                        specialLinkedIntroSlides,
                        allGenerationSpecialOutputContexts: allGenerationSpecialSlides.map((slide) => slide.outputContext || ''),
                        specialLinkedLyricsSlides,
                        sundayFirstMainScoreTitleSlides: sundayFirstMainScoreSlides.filter((slide) => slide.type === 'song-title').map((slide) => ({
                          title: slide.title,
                          sectionTitle: slide.sectionTitle,
                          label: slide.label
                        })),
                        specialSectionTitleSlides,
                        thirdManualSpecialTitleSlides,
                        thirdEmptySpecialMissingSlides,
                        thirdTitlePersonSpecialSlides,
                        specialInputModes,
                        emptyTemplateInputSlides,
                        missingSermonBodySlides,
                        missingSermonTitleSlides,
                        sermonSubgroupHeaderLabels,
                        sermonSubgroupControlLabels,
                        missingTitlePersonAssigneeSlides,
                        defaultTemplateInputSlides,
                        persistenceStateRows,
                        sectionSongTitleSlides,
                        scoreSlides: scoreSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          title: slide.title
                        })),
                        scoreImageSlides: scoreImageSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          imageSrc: slide.imageSrc
                        })),
                        scoreManifestSlides: scoreManifestSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          imageSrc: slide.imageSrc
                        })),
                        scoreSequenceImages: scoreSequenceSlides.map((slide) => slide.imageSrc),
                        scoreSequenceBadges: scoreSequenceSlides.map((slide) => slide.formLabel || ''),
                        scoreRawTitleSlides: scoreRawTitleSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          marker: slide.marker,
                          imageSrc: slide.imageSrc
                        })),
                        scorePreloadSources: presenterOutputImageSourcesForPreload({
                          slides: scoreImageSlides,
                          index: 0,
                          chromakey: false
                        }, scoreImageSlides[0]),
                        longScorePreloadSources: presenterOutputImageSourcesForPreload({
                          slides: longScoreSlides,
                          index: 0,
                          chromakey: false
                        }, longScoreSlides[0]),
                        longScoreWarmupSourcesStart,
                        longScoreWarmupSourcesMiddle,
                        longScoreWarmupKeys,
                        scoreSafeArea,
                        audioMemo: parseServiceItemMemo(audioMemo),
                        audioDbType: worshipDbElementTypeForSave('audio'),
                        audioConfig: serviceElementConfigForSave({}, parseServiceItemMemo(audioMemo)),
                        audioSlides: audioSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          audioSrc: slide.audioSrc,
                          body: renderPresenterSlideBody(slide).trim(),
                          preview: renderPresenterSlideBody(slide),
                        })),
                        syncedLyricsAllSlides: syncedLyricsSlides.map((slide) => ({
                          type: slide.type,
                          sourceType: slide.sourceType,
                          audioSource: presenterSlideAudioSource(slide),
                          syncTimeline: slide.syncTimeline || null,
                        })),
                        syncedLyricsSlides: syncedLyricsSlides.filter((slide) => slide.type === 'lyrics').map((slide) => ({
                          type: slide.type,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          text: slide.text,
                          syncTimeline: slide.syncTimeline || null,
                        })),
                        importedDeckSlides: importedDeckSlides.map((slide) => ({
                          type: slide.type,
                          layout: slide.layout,
                          elementType: slide.elementType,
                          sourceType: slide.sourceType,
                          componentType: slide.componentType,
                          imageSrc: slide.imageSrc,
                          importedDeck: slide.importedDeck || null,
                        })),
                        scoreFormBadges: [...scoreBadgeNode.querySelectorAll('.svc-slide-form-badge')].map((node) => node.textContent.trim()),
                        missingWarnings: [...new Set(missingSlides.flatMap((slide) => slide.warnings || []))],
                        missingPreviewText: missingSlides.map((slide) => renderPresenterSlideMiniPreview(slide, service.id)).join(' '),
                        warningChipText: warningChip?.textContent.trim() || '',
                        warningLayout
                      };
                    }
                    """
                )
                if (
                    form_preset_state["hymnTypes"] == ["title-assignee", "song-title", "lyrics", "lyrics", "lyrics", "lyrics", "blank", "lyrics", "lyrics", "lyrics"]
                    and form_preset_state["hymnTitleTexts"] == ["♬ 999 특송 테스트"]
                    and form_preset_state["hymnMarkers"] == ["Verse 1", "Chorus", "Verse 2", "Chorus", "Verse 4", "Chorus", "Coda"]
                    and form_preset_state["hymnTexts"] == [
                        "1절 첫 줄\n1절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "2절 첫 줄\n2절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "마지막 절 첫 줄\n마지막 절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "아멘",
                    ]
                    and "3절 첫 줄" not in "\n".join(form_preset_state["hymnTexts"])
                    and form_preset_state["hymnWarnings"] == []
                    and form_preset_state["hymnBlankCount"] == 1
                    and form_preset_state["hymnBlankText"] == ""
                    and form_preset_state["hymnBlankLayout"] == "blank"
                    and form_preset_state["ccmMarkers"] == ["Verse 1", "Chorus", "Chorus"]
                    and form_preset_state["ccmTexts"] == ["V1 첫 줄\nV1 둘째 줄", "C 첫 줄\nC 둘째 줄", "C 첫 줄\nC 둘째 줄"]
                    and len(set(form_preset_state["ccmFormKeys"])) == 3
                    and form_preset_state["explicitTagMarkers"] == ["Verse 1", "Chorus 1", "Verse 2", "Chorus 2", "Tags"]
                    and "B 첫 줄" not in "\n".join(form_preset_state["explicitTagTexts"])
                    and form_preset_state["explicitTagTexts"][3] == "C2 첫 줄\nC2 둘째 줄"
                    and form_preset_state["explicitTagTexts"][-1] == "C 둘째 줄\nC 둘째 줄"
                    and form_preset_state["explicitGenericMarkers"] == ["Verse 1", "Chorus 1", "Verse 2", "Chorus 2"]
                    and "B 첫 줄" not in "\n".join(form_preset_state["explicitGenericTexts"])
                    and form_preset_state["groupedLetterMarkers"] == ["Chorus B", "Chorus B", "Chorus B"]
                    and form_preset_state["defaultFormMetadataSummary"] == "V1-V2-C-V3-Coda"
                    and form_preset_state["defaultFormMarkers"] == ["Verse 1", "Verse 2", "Chorus", "Verse 3", "Coda"]
                    and form_preset_state["defaultFormTexts"] == [
                        "감사 1절 첫 줄\n감사 1절 둘째 줄",
                        "감사 2절 첫 줄\n감사 2절 둘째 줄",
                        "감사 후렴 첫 줄\n감사 후렴 둘째 줄",
                        "감사 3절 첫 줄\n감사 3절 둘째 줄",
                        "감사 코다 첫 줄\n감사 코다 둘째 줄",
                    ]
                    and form_preset_state["unifiedHymnTitleText"] == "♬ 통 1 만복의 근원 하나님"
                    and form_preset_state["fallbackVersionTexts"] == ["하나님은 너를 지키시는 자\n너의 우편에 그늘 되시니"]
                    and form_preset_state["fallbackVersionWarnings"] == []
                    and form_preset_state["fallbackTitleTexts"] == ["하나님은 너를 지키시는 자\n너의 우편에 그늘 되시니"]
                    and form_preset_state["fallbackTitleWarnings"] == []
                    and form_preset_state["hymnAutoMarkers"] == ["Verse 1", "Chorus", "Verse 2", "Chorus", "Verse 3", "Chorus", "Verse 4", "Chorus", "Coda"]
                    and form_preset_state["hymnAutoTexts"] == [
                        "1절 첫 줄\n1절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "2절 첫 줄\n2절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "3절 첫 줄\n3절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "마지막 절 첫 줄\n마지막 절 둘째 줄",
                        "후렴 첫 줄\n후렴 둘째 줄",
                        "아멘",
                    ]
                    and len(form_preset_state["scoreTitleSlides"]) == 1
                    and form_preset_state["scoreTitleTexts"] == ["♬ 999 특송 테스트"]
                    and form_preset_state["scoreManifestTitleTexts"] == ["♬ 5 이 천지간 만물들아"]
                    and form_preset_state["scoreRawTitleTexts"] == ["♬ 5 이 천지간 만물들아"]
                    and form_preset_state["scoreImageTitleSlides"]
                    and form_preset_state["scoreManifestTitleSlides"]
                    and form_preset_state["scoreRawTitleTitleSlides"] == ["5 이 천지간 만물들아"]
                    and len(form_preset_state["offeringScoreTitleSlides"]) == 0
                    and form_preset_state["flexibleOfferingScoreMode"] == "score"
                    and form_preset_state["flexibleOfferingScoreSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-01.webp",
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-02.webp",
                        },
                    ]
                    and form_preset_state["flexibleOfferingLegacyScoreMode"] == "score"
                    and form_preset_state["flexibleOfferingLegacyScoreSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-01.webp",
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-02.webp",
                        },
                    ]
                    and form_preset_state["specialScoreTitleSlides"] == []
                    and form_preset_state["specialScoreSourceCount"] == 0
                    and form_preset_state["specialLinkedScoreSourceCount"] == 0
                    and form_preset_state["specialLinkedIntroSlides"][:2] == [
                        {
                            "type": "title-assignee",
                            "title": "특송",
                            "assignee": "할렐루야 찬양대",
                            "text": "특송\n할렐루야 찬양대",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "song-title",
                            "title": "999 특송 테스트",
                            "assignee": "",
                            "text": "♬ 999 특송 테스트",
                            "sectionKey": "special_song",
                        },
                    ]
                    and "clean" not in form_preset_state["allGenerationSpecialOutputContexts"]
                    and form_preset_state["specialLinkedLyricsSlides"] == [
                        {
                            "type": "lyrics",
                            "marker": "Verse 1",
                            "text": "1절 첫 줄\n1절 둘째 줄",
                            "formKey": "h-v1:0",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Chorus",
                            "text": "후렴 첫 줄\n후렴 둘째 줄",
                            "formKey": "h-c:1",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Verse 2",
                            "text": "2절 첫 줄\n2절 둘째 줄",
                            "formKey": "h-v2:2",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Chorus",
                            "text": "후렴 첫 줄\n후렴 둘째 줄",
                            "formKey": "h-c:3",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "blank",
                            "marker": "",
                            "text": "",
                            "formKey": "blank:instrumental:4",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Verse 4",
                            "text": "마지막 절 첫 줄\n마지막 절 둘째 줄",
                            "formKey": "h-v4:5",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Chorus",
                            "text": "후렴 첫 줄\n후렴 둘째 줄",
                            "formKey": "h-c:6",
                            "sectionKey": "special_song",
                        },
                        {
                            "type": "lyrics",
                            "marker": "Coda",
                            "text": "아멘",
                            "formKey": "h-coda:7",
                            "sectionKey": "special_song",
                        },
                    ]
                    and form_preset_state["sundayFirstMainScoreTitleSlides"] == []
                    and form_preset_state["specialSectionTitleSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "특송",
                        "assignee": "",
                        "text": "특송",
                        "sectionKey": "special_song",
                        "body": form_preset_state["specialSectionTitleSlides"][0]["body"],
                    }]
                    and "presenter-title-assignee" in form_preset_state["specialSectionTitleSlides"][0]["body"]
                    and form_preset_state["thirdManualSpecialTitleSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "특송",
                        "assignee": "",
                        "text": "특송",
                        "sectionKey": "special_song",
                    }]
                    and form_preset_state["thirdEmptySpecialMissingSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "특송",
                        "assignee": "",
                        "text": "특송",
                        "sectionKey": "special_song",
                        "missingContent": True,
                        "missingReason": "manual_praise_empty",
                        "inputMode": "manual_praise",
                        "contentState": "missing",
                        "warnings": ["입력 필요"],
                    }]
                    and form_preset_state["thirdTitlePersonSpecialSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "특송",
                        "assignee": "청년부",
                        "text": "특송\n청년부",
                        "sectionKey": "special_song",
                    }]
                    and form_preset_state["specialInputModes"] == {
                        "sundayMain": {
                            "mode": "manual_praise",
                            "requiresSong": False,
                        },
                        "sundaySecond": {
                            "mode": "lyrics_db",
                            "requiresSong": True,
                        },
                        "monthlyYesterday": {
                            "mode": "lyrics_db",
                            "requiresSong": True,
                        },
                        "manualSlidesOutsideSundayMain": {
                            "mode": "manual_praise",
                            "requiresSong": False,
                        },
                    }
                    and form_preset_state["emptyTemplateInputSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "대표기도",
                        "assignee": "불러오는 중",
                        "text": "대표기도\n불러오는 중",
                        "sectionKey": "prayer",
                        "missingContent": False,
                        "missingReason": "service_items_hydrating",
                        "inputMode": "text",
                        "contentState": "loading",
                        "warnings": ["불러오는 중"],
                    }]
                    and form_preset_state["missingSermonBodySlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "설교 본문",
                        "assignee": "",
                        "text": "설교 본문",
                        "sectionKey": "sermon",
                        "missingContent": True,
                        "missingReason": "scripture_body_empty",
                        "inputMode": "scripture",
                        "contentState": "missing",
                        "warnings": ["입력 필요"],
                    }]
                    and form_preset_state["missingSermonTitleSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "설교",
                        "assignee": "",
                        "text": "설교",
                        "sectionKey": "sermon",
                        "missingContent": True,
                        "missingReason": "title_empty",
                        "inputMode": "text",
                        "contentState": "missing",
                        "warnings": ["입력 필요"],
                    }]
                    and form_preset_state["sermonSubgroupHeaderLabels"] == ["설교"]
                    and form_preset_state["sermonSubgroupControlLabels"] == []  # single-item subgroups reuse the header label
                    and form_preset_state["missingTitlePersonAssigneeSlides"] == [{
                        "type": "title-assignee",
                        "elementType": "title_assignee",
                        "layout": "lower_bar_text",
                        "title": "공동기도",
                        "assignee": "",
                        "text": "공동기도",
                        "sectionKey": "corporate_prayer",
                        "missingContent": True,
                        "missingReason": "assignee_empty",
                        "inputMode": "text",
                        "contentState": "missing",
                        "warnings": ["입력 필요"],
                    }]
	                    and form_preset_state["defaultTemplateInputSlides"] == [{
	                        "type": "title-assignee",
	                        "elementType": "title_assignee",
	                        "layout": "lower_bar_text",
	                        "title": "대표기도",
                        "assignee": "김남영 목사",
	                        "text": "대표기도\n김남영 목사",
	                        "missingContent": False,
	                        "warnings": [],
	                    }]
	                    and form_preset_state["persistenceStateRows"] == [
	                        {
	                            "label": "특송",
	                            "songId": "",
	                            "inputMode": "manual_praise",
	                            "typedInputMode": "praise_db",
	                            "contentState": {
	                                "state": "missing",
	                                "reason": "manual_praise_empty",
	                                "inputMode": "manual_praise",
	                                "elementType": "praise",
	                                "required": True,
	                            },
	                            "typedContentState": {
	                                "state": "missing",
	                                "reason": "manual_praise_empty",
	                                "inputMode": "manual_praise",
	                                "elementType": "praise",
	                                "required": True,
	                            },
	                        },
	                        {
	                            "label": "대표기도",
	                            "songId": "",
	                            "inputMode": "text",
	                            "typedInputMode": "text",
	                            "contentState": {
	                                "state": "filled",
	                                "reason": "title_person",
	                                "inputMode": "text",
	                                "elementType": "title_person",
	                                "required": False,
	                            },
	                            "typedContentState": {
	                                "state": "filled",
	                                "reason": "title_person",
	                                "inputMode": "text",
	                                "elementType": "title_person",
	                                "required": False,
	                            },
	                        },
	                        {
	                            "label": "찬양",
	                            "songId": "__smoke_missing_song_object__",
	                            "inputMode": "lyrics_db",
	                            "typedInputMode": "praise_db",
	                            "contentState": {
	                                "state": "filled",
	                                "reason": "song",
	                                "inputMode": "lyrics_db",
	                                "elementType": "praise",
	                                "required": False,
	                            },
	                            "typedContentState": {
	                                "state": "filled",
	                                "reason": "song",
	                                "inputMode": "lyrics_db",
	                                "elementType": "praise",
	                                "required": False,
	                            },
	                        },
	                    ]
                    and len(form_preset_state["sectionSongTitleSlides"]["offering"]) == 0
                    and len(form_preset_state["sectionSongTitleSlides"]["special"]) == 0
                    and len(form_preset_state["sectionSongTitleSlides"]["doxology"]) == 0
                    and form_preset_state["scoreSlides"] == []
                    and form_preset_state["scoreImageSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/worship-backgrounds/26-A1.png",
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/worship-backgrounds/26-A2.png",
                        },
                    ]
                    and form_preset_state["scoreFormBadges"] == ["Verse 1", "Chorus"]
                    and form_preset_state["scoreManifestSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-01.webp",
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-02.webp",
                        },
                    ]
                    and form_preset_state["scoreSequenceImages"] == [
                        "assets/hymn-scores/359/slide-01.webp",
                        "assets/hymn-scores/359/slide-02.webp",
                        "assets/hymn-scores/359/slide-05.webp",
                        "assets/hymn-scores/359/slide-06.webp",
                        "assets/hymn-scores/359/slide-07.webp",
                        "assets/hymn-scores/359/slide-08.webp",
                        "assets/hymn-scores/359/slide-09.webp",
                        "assets/hymn-scores/359/slide-10.webp",
                        "assets/hymn-scores/359/slide-11.webp",
                        "assets/hymn-scores/359/slide-12.webp",
                        "assets/hymn-scores/359/slide-11.webp",
                        "assets/hymn-scores/359/slide-12.webp",
                    ]
                    and form_preset_state["scoreSequenceBadges"] == [
                        "Verse 1",
                        "",
                        "Verse 2",
                        "",
                        "Chorus",
                        "",
                        "Verse 3",
                        "",
                        "Chorus",
                        "",
                        "Chorus",
                        "",
                    ]
                    and form_preset_state["scoreRawTitleSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-01.webp",
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "score",
                            "componentType": "score",
                            "marker": "",
                            "imageSrc": "assets/hymn-scores/5/slide-02.webp",
                        },
                    ]
                    and form_preset_state["scorePreloadSources"] == [
                        "assets/worship-backgrounds/26-A1.png",
                        "assets/worship-backgrounds/26-A2.png",
                    ]
                    and len(form_preset_state["longScorePreloadSources"]) == 12
                    and form_preset_state["longScorePreloadSources"][0].endswith("slide-01.webp")
                    and form_preset_state["longScorePreloadSources"][-1].endswith("slide-12.webp")
                    and len(form_preset_state["longScoreWarmupSourcesStart"]) == 12
                    and len(form_preset_state["longScoreWarmupSourcesMiddle"]) == 12
                    and form_preset_state["longScoreWarmupSourcesStart"][0].endswith("slide-01.webp")
                    and form_preset_state["longScoreWarmupSourcesMiddle"][0].endswith("slide-07.webp")
                    and form_preset_state["longScoreWarmupKeys"][0] == form_preset_state["longScoreWarmupKeys"][1]
                    and "presenter-slide--score" in form_preset_state["scoreSafeArea"]["className"]
                    and abs(form_preset_state["scoreSafeArea"]["top"]) <= 1
                    and abs(form_preset_state["scoreSafeArea"]["right"]) <= 1
                    and abs(form_preset_state["scoreSafeArea"]["bottom"]) <= 1
                    and abs(form_preset_state["scoreSafeArea"]["left"]) <= 1
                    and form_preset_state["scoreSafeArea"]["slideBackground"] == "rgb(255, 255, 255)"
                    and form_preset_state["scoreSafeArea"]["imageBackground"] == "none"
                    and form_preset_state["scoreSafeArea"]["imageBackgroundColor"] == "rgb(255, 255, 255)"
                    and form_preset_state["audioMemo"]["elementType"] == "audio"
                    and form_preset_state["audioMemo"]["asset"] == {
                        "kind": "audio",
                        "name": "성가대 MR",
                        "url": "assets/audio/choir.m4a",
                    }
                    and form_preset_state["audioDbType"] == "plain_text"
                    and form_preset_state["audioConfig"]["elementType"] == "audio"
                    and form_preset_state["audioConfig"]["asset"]["kind"] == "audio"
                    and form_preset_state["audioSlides"] == [{
                        "type": "audio",
                        "layout": "file",
                        "elementType": "audio",
                        "sourceType": "audio",
                        "componentType": "audio",
                        "audioSrc": "assets/audio/choir.m4a",
                        "body": "",
                        "preview": "",
                    }]
                    and [slide["syncTimeline"]["start"] for slide in form_preset_state["syncedLyricsSlides"]] == [12.3, 24.6, 36.9, None]
                    and form_preset_state["syncedLyricsAllSlides"][0]["type"] == "song-title"
                    and form_preset_state["syncedLyricsAllSlides"][0]["audioSource"] == "assets/audio/children-praise.mp3"
                    and form_preset_state["syncedLyricsAllSlides"][0]["syncTimeline"]["intro"]
                    and form_preset_state["syncedLyricsAllSlides"][0]["syncTimeline"]["start"] is None
                    and all(slide["sourceType"] == "synced_lyrics" for slide in form_preset_state["syncedLyricsSlides"])
                    and all(slide["syncTimeline"]["audioSrc"] == "assets/audio/children-praise.mp3" for slide in form_preset_state["syncedLyricsSlides"])
                    and form_preset_state["syncedLyricsSlides"][0]["syncTimeline"]["groupId"] == "__smoke_synced_lyrics_item__:synced-lyrics"
                    and form_preset_state["syncedLyricsSlides"][-1]["syncTimeline"]["cross"] == 46.5
                    and form_preset_state["importedDeckSlides"] == [
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "imported_deck",
                            "componentType": "imported_deck",
                            "imageSrc": "cache/keynote/joseph/stage-001.png",
                            "importedDeck": {
                                "manifestUrl": "cache/keynote/joseph/manifest.json",
                                "fingerprint": "deck-v1-smoke",
                                "stage": 1,
                            },
                        },
                        {
                            "type": "image",
                            "layout": "media",
                            "elementType": "image",
                            "sourceType": "imported_deck",
                            "componentType": "imported_deck",
                            "imageSrc": "cache/keynote/joseph/stage-002.png",
                            "importedDeck": {
                                "manifestUrl": "cache/keynote/joseph/manifest.json",
                                "fingerprint": "deck-v1-smoke",
                                "stage": 2,
                            },
                        },
                    ]
                    and form_preset_state["missingWarnings"] == ["Bridge 없음"]
                    and "Bridge 없음" not in form_preset_state["missingPreviewText"]
                    and form_preset_state["warningChipText"] == "Bridge 없음"
                    and form_preset_state["warningLayout"]["headDisplay"] in ("flex", "inline-flex")
                    and 0 <= form_preset_state["warningLayout"]["chipGap"] <= 16
                ):
                    pass_("presenter-form-preset-sequence", json.dumps(form_preset_state, ensure_ascii=False))
                else:
                    fail("presenter-form-preset-sequence", json.dumps(form_preset_state, ensure_ascii=False))

                synced_lyrics_runtime_state = page.evaluate(
                    """
                    () => {
                      const previousPresenter = { ...state.presenter };
                      const previousMusic = { ...state.serviceMusic };
                      const previousModule = state.module;
                      const previousSelected = state.selectedServiceId;
                      let publishCalls = 0;
                      const previousPublish = window.publishPresenterState;
                      window.publishPresenterState = () => { publishCalls += 1; };
                      state.module = 'presenter';
                      state.selectedServiceId = '__smoke_synced_runtime_service__';
                      state.presenter.serviceId = '__smoke_synced_runtime_service__';
                      state.presenter.safetyBlank = false;
                      state.presenter.liveScripture = { active: false, slide: null, reference: '', draft: '' };
                      state.presenter.slides = [
                        {
                          id: 'sync-title',
                          type: 'song-title',
                          syncTimeline: {
                            groupId: 'runtime-group',
                            audioSrc: 'assets/audio/children-praise.mp3',
                            audioTitle: '어린이 찬양',
                            page: 0,
                            start: null,
                            intro: true,
                          },
                        },
                        {
                          id: 'sync-1',
                          type: 'lyrics',
                          syncTimeline: {
                            groupId: 'runtime-group',
                            audioSrc: 'assets/audio/children-praise.mp3',
                            page: 1,
                            start: 12.3,
                          },
                        },
                        {
                          id: 'sync-2',
                          type: 'lyrics',
                          syncTimeline: {
                            groupId: 'runtime-group',
                            audioSrc: 'assets/audio/children-praise.mp3',
                            page: 2,
                            start: 24.6,
                          },
                        },
                        {
                          id: 'other-audio',
                          type: 'lyrics',
                          syncTimeline: {
                            groupId: 'runtime-group',
                            audioSrc: 'assets/audio/other.mp3',
                            page: 3,
                            start: 36.9,
                          },
                        },
                      ];
                      state.presenter.index = 0;
                      state.serviceMusic = {
                        ...state.serviceMusic,
                        audio: { currentTime: 24.4, currentSrc: '', src: '', paused: false, ended: false },
                        mode: 'presenter-audio',
                        sourceKey: 'assets/audio/children-praise.mp3',
                        sourceLabel: '어린이 찬양',
                        playing: true,
                      };
                      const titleSource = presenterSlideAudioSource(state.presenter.slides[0]);
                      const moved = syncServiceMusicSyncedLyricsWithCurrentTime({ publish: false, render: false, scroll: false });
                      const movedIndex = state.presenter.index;
                      const movedSlide = state.presenter.slides[movedIndex].id;
                      state.serviceMusic.audio.currentTime = 36.9;
                      const blockedDifferentAudio = syncServiceMusicSyncedLyricsWithCurrentTime({ publish: false, render: false, scroll: false });
                      const finalIndex = state.presenter.index;
                      window.publishPresenterState = previousPublish;
                      state.presenter = previousPresenter;
                      state.serviceMusic = previousMusic;
                      state.module = previousModule;
                      state.selectedServiceId = previousSelected;
                      return { titleSource, moved, movedIndex, movedSlide, blockedDifferentAudio, finalIndex, publishCalls };
                    }
                    """
                )
                if (
                    synced_lyrics_runtime_state["titleSource"] == "assets/audio/children-praise.mp3"
                    and synced_lyrics_runtime_state["moved"]
                    and synced_lyrics_runtime_state["movedIndex"] == 2
                    and synced_lyrics_runtime_state["movedSlide"] == "sync-2"
                    and not synced_lyrics_runtime_state["blockedDifferentAudio"]
                    and synced_lyrics_runtime_state["finalIndex"] == 2
                    and synced_lyrics_runtime_state["publishCalls"] == 0
                ):
                    pass_("presenter-synced-lyrics-runtime-advance", json.dumps(synced_lyrics_runtime_state, ensure_ascii=False))
                else:
                    fail("presenter-synced-lyrics-runtime-advance", json.dumps(synced_lyrics_runtime_state, ensure_ascii=False))

                section_song_title_fit_state = page.evaluate(
                    """
                    () => {
                      const serviceId = '__smoke_section_song_title_fit_service__';
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      state.services.push({
                        id: serviceId,
                        type_id: 'sunday-first',
                        date: '2026-07-05',
                        service_date: '2026-07-05',
                      });
                      const slide = presenterOrderContentTitleSlide(
                        { id: '__smoke_section_song_title_fit_slide__', label: '송영' },
                        { sectionKey: 'doxology', sectionLabel: '송영', sectionTitle: '송영' },
                        0,
                        '송영',
                        '♪ 5 이 천지간 만물들아',
                      );
                      const mount = document.createElement('div');
                      mount.style.cssText = 'position:fixed;left:16px;top:16px;width:368px;height:207px;z-index:99999;pointer-events:none';
                      mount.innerHTML = renderPresenterSlideMiniPreview(slide, serviceId);
                      document.body.appendChild(mount);
                      const host = mount.querySelector('.svc-slide-mini-output');
                      const bar = mount.querySelector('.presenter-slide-text');
                      const songLayout = mount.querySelector('.presenter-section-song-title');
                      const orderContent = mount.querySelector('.presenter-title-assignee--order-content');
                      const titleContent = mount.querySelector('.presenter-title-content');
                      const heading = mount.querySelector('.presenter-title-assignee-order');
                      const name = mount.querySelector('.presenter-title-assignee-content');
                      const title = mount.querySelector('.presenter-title-content-title');
                      const result = {
                        noChromakey: Boolean(host?.classList.contains('no-chromakey')),
                        hasBackground: Boolean(host?.classList.contains('has-background')),
                        hasSongLayout: Boolean(songLayout),
                        hasOrderContent: Boolean(orderContent),
                        hasTitleContent: Boolean(titleContent),
                        titleText: title?.textContent?.trim() || '',
                        display: '',
                        columns: '',
                        headingInsideBar: false,
                        nameInsideBar: false,
                        barWidth: 0,
                        headingWidth: 0,
                        nameWidth: 0,
                      };
                      if (bar && orderContent && heading && name) {
                        const barRect = bar.getBoundingClientRect();
                        const headingRect = heading.getBoundingClientRect();
                        const nameRect = name.getBoundingClientRect();
                        const style = getComputedStyle(orderContent);
                        result.display = style.display;
                        result.columns = style.gridTemplateColumns;
                        result.headingInsideBar = headingRect.left >= barRect.left - 1 && headingRect.right <= barRect.right + 1;
                        result.nameInsideBar = nameRect.left >= barRect.left - 1 && nameRect.right <= barRect.right + 1;
                        result.barWidth = Math.round(barRect.width);
                        result.headingWidth = Math.round(headingRect.width);
                        result.nameWidth = Math.round(nameRect.width);
                      }
                      mount.remove();
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      return result;
                    }
                    """
                )
                if (
	                    section_song_title_fit_state["noChromakey"]
	                    and section_song_title_fit_state["hasBackground"]
	                    and not section_song_title_fit_state["hasSongLayout"]
	                    and not section_song_title_fit_state["hasOrderContent"]
	                    and section_song_title_fit_state["hasTitleContent"]
	                    and "이 천지간 만물들아" in section_song_title_fit_state["titleText"]
	                ):
                    pass_("presenter-section-song-title-fit", json.dumps(section_song_title_fit_state, ensure_ascii=False))
                else:
                    fail("presenter-section-song-title-fit", json.dumps(section_song_title_fit_state, ensure_ascii=False))

                plain_song_title_mini_preview_state = page.evaluate(
                    """
                    () => {
                      const serviceId = '__smoke_plain_song_title_mini_preview_service__';
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      state.services.push({
                        id: serviceId,
                        type_id: 'sunday-first',
                        date: '2026-07-05',
                        service_date: '2026-07-05',
                      });
                      const slide = {
                        id: '__smoke_plain_song_title_mini_preview_slide__',
                        elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'song-title',
                        title: '405 주의 친절한 팔에 안기세',
                        text: '♪ 405 주의 친절한 팔에 안기세',
                        sectionKey: 'praise',
                      };
                      const mount = document.createElement('div');
                      mount.style.cssText = 'position:fixed;left:16px;top:16px;width:368px;height:207px;z-index:99999;pointer-events:none';
                      mount.innerHTML = renderPresenterSlideMiniPreview(slide, serviceId);
                      document.body.appendChild(mount);
                      const host = mount.querySelector('.svc-slide-mini-output');
                      const titleContent = mount.querySelector('.presenter-title-content');
                      const title = mount.querySelector('.presenter-title-content-title');
                      const songTitle = mount.querySelector('.presenter-slide--song-title');
                      const result = {
                        noChromakey: Boolean(host?.classList.contains('no-chromakey')),
                        hasBackground: Boolean(host?.classList.contains('has-background')),
                        hasTitleContent: Boolean(titleContent),
                        hasSongTitle: Boolean(songTitle),
                        titleText: title?.textContent?.trim() || '',
                      };
                      mount.remove();
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      return result;
                    }
                    """
                )
                if (
                    plain_song_title_mini_preview_state["noChromakey"]
                    and plain_song_title_mini_preview_state["hasBackground"]
                    and plain_song_title_mini_preview_state["hasTitleContent"]
                    and not plain_song_title_mini_preview_state["hasSongTitle"]
                    and "405 주의 친절한 팔에 안기세" in plain_song_title_mini_preview_state["titleText"]
                ):
                    pass_("presenter-plain-song-title-mini-preview", json.dumps(plain_song_title_mini_preview_state, ensure_ascii=False))
                else:
                    fail("presenter-plain-song-title-mini-preview", json.dumps(plain_song_title_mini_preview_state, ensure_ascii=False))

                section_song_title_output_font_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root';
                      document.body.appendChild(outputRoot);
                      renderPresenterOutput({
                        serviceId: '__smoke_section_song_title_output_font__',
                        serviceType: 'sunday2',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_section_song_title_output_font_slide__',
                          elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          type: 'song-title',
                          title: '주 내 아버지',
                          text: '♪ 주 내 아버지',
                          sectionHeading: '찬양',
                          sectionKey: 'praise',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const heading = root?.querySelector('.presenter-section-song-title-heading');
                      const name = root?.querySelector('.presenter-section-song-title-name');
                      const size = (node) => node ? Number.parseFloat(getComputedStyle(node).fontSize) : 0;
                      const weight = (node) => node ? getComputedStyle(node).fontWeight : '';
                      const result = {
                        hasRoot: Boolean(root),
                        hasHeading: Boolean(heading),
                        hasName: Boolean(name),
                        text: root?.innerText || '',
                        headingFontSize: size(heading),
                        nameFontSize: size(name),
                        nameFontWeight: weight(name),
                      };
                      root?.remove();
                      return result;
                    }
                    """
                )
                if (
                    "주 내 아버지" in section_song_title_output_font_state["text"]
                    and section_song_title_output_font_state["headingFontSize"] < section_song_title_output_font_state["nameFontSize"]
                    and 65 <= section_song_title_output_font_state["headingFontSize"] <= 70
                    and 73 <= section_song_title_output_font_state["nameFontSize"] <= 76
                    and section_song_title_output_font_state["nameFontWeight"] == "800"
                ):
                    pass_("presenter-section-song-title-output-font", json.dumps(section_song_title_output_font_state, ensure_ascii=False))
                else:
                    fail("presenter-section-song-title-output-font", json.dumps(section_song_title_output_font_state, ensure_ascii=False))

                plain_song_title_output_font_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root';
                      document.body.appendChild(outputRoot);
                      renderPresenterOutput({
                        serviceId: '__smoke_plain_song_title_output_font__',
                        serviceType: 'sunday2',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_plain_song_title_output_font_slide__',
                          elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          type: 'song-title',
                          title: '주 찬양합니다',
                          text: '♪ 주 찬양합니다',
                          sectionKey: 'praise',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const text = root?.querySelector('.presenter-slide--song-title > .presenter-slide-text');
                      const textRect = text?.getBoundingClientRect();
                      const style = text ? getComputedStyle(text) : null;
                      const result = {
                        hasRoot: Boolean(root),
                        hasText: Boolean(text),
                        text: root?.innerText || '',
                        fontSize: style ? Number.parseFloat(style.fontSize) : 0,
                        fontWeight: style?.fontWeight || '',
                        lineHeight: style ? Number.parseFloat(style.lineHeight) : 0,
                        boxHeight: textRect ? Math.round(textRect.height) : 0,
                      };
                      root?.remove();
                      return result;
                    }
                    """
                )
                if (
                    "주 찬양합니다" in plain_song_title_output_font_state["text"]
                    and 73 <= plain_song_title_output_font_state["fontSize"] <= 76
                    and plain_song_title_output_font_state["fontWeight"] == "800"
                    and plain_song_title_output_font_state["lineHeight"] >= plain_song_title_output_font_state["fontSize"]
                ):
                    pass_("presenter-plain-song-title-output-font", json.dumps(plain_song_title_output_font_state, ensure_ascii=False))
                else:
                    fail("presenter-plain-song-title-output-font", json.dumps(plain_song_title_output_font_state, ensure_ascii=False))

                fullscreen_song_title_output_font_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root no-chromakey';
                      document.body.appendChild(outputRoot);
                      const result = ['praise', 'pre_scripture_praise', 'entrance_praise', 'response_song', 'prayer_meeting_praise'].map((sectionKey) => {
                        renderPresenterOutput({
                          serviceId: '__smoke_fullscreen_song_title_output_font__',
                          serviceType: 'sunday2', chromakey: false, outputTheme: 'formal', backgroundImage: '',
                          slides: [{ id: `__smoke_fullscreen_song_title_output_font_${sectionKey}__`, elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                            layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT, type: 'song-title', title: '주 찬양합니다',
                            text: '♪ 주 찬양합니다', sectionKey }], index: 0, safetyBlank: false,
                        });
                        const name = outputRoot.querySelector('.presenter-slide--fullscreen-song-title .presenter-title-content-title');
                        const style = name ? getComputedStyle(name) : null;
                        return { sectionKey, text: outputRoot.innerText || '', fontSize: style ? Number.parseFloat(style.fontSize) : 0, fontWeight: style?.fontWeight || '' };
                      });
                      outputRoot.remove();
                      return result;
                    }
                    """
                )
                if (
                    all("주 찬양합니다" in item["text"] for item in fullscreen_song_title_output_font_state)
                    and all(110 <= item["fontSize"] <= 114 for item in fullscreen_song_title_output_font_state)
                    and all(item["fontWeight"] == "800" for item in fullscreen_song_title_output_font_state)
                ):
                    pass_("presenter-fullscreen-song-title-output-font", json.dumps(fullscreen_song_title_output_font_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-song-title-output-font", json.dumps(fullscreen_song_title_output_font_state, ensure_ascii=False))

                fullscreen_sermon_title_center_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root no-chromakey';
                      document.body.appendChild(outputRoot);
                      renderPresenterOutput({
                        serviceId: '__smoke_fullscreen_sermon_title_center__',
                        serviceType: 'sunday1', chromakey: false, outputTheme: 'formal', backgroundImage: '',
                        slides: [{ id: '__smoke_fullscreen_sermon_title_center_slide__',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT, type: 'title-assignee',
                          titlePresentation: 'sermon', contentTitle: '하나님의 나라를 함께 살아내는 믿음',
                          assignee: '김석범 목사' }], index: 0, safetyBlank: false,
                      });
                      const layout = outputRoot.querySelector('.presenter-title-assignee--sermon');
                      const title = outputRoot.querySelector('.presenter-title-assignee-content');
                      const person = outputRoot.querySelector('.presenter-title-assignee-person');
                      const rootRect = outputRoot.getBoundingClientRect();
                      const centerOffset = (element) => {
                        const rect = element?.getBoundingClientRect();
                        return rect ? Math.round(Math.abs((rect.left + rect.right) / 2 - (rootRect.left + rootRect.right) / 2)) : -1;
                      };
                      const style = layout ? getComputedStyle(layout) : null;
                      const result = {
                        display: style?.display || '',
                        titleCentered: centerOffset(title),
                        personCentered: centerOffset(person),
                      };
                      outputRoot.remove();
                      return result;
                    }
                    """
                )
                if (
                    fullscreen_sermon_title_center_state["display"] == "grid"
                    and fullscreen_sermon_title_center_state["titleCentered"] > 1
                    and fullscreen_sermon_title_center_state["personCentered"] > 1
                ):
                    pass_("presenter-fullscreen-sermon-title-center", json.dumps(fullscreen_sermon_title_center_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-sermon-title-center", json.dumps(fullscreen_sermon_title_center_state, ensure_ascii=False))

                preview_long_sermon_title_fit_state = page.evaluate(
                    """
                    () => {
                      const serviceId = '__smoke_preview_long_sermon_title__';
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      state.services.push({ id: serviceId, type_id: 'sunday-first', date: '2026-07-05', service_date: '2026-07-05' });
                      const mount = document.createElement('div');
                      mount.style.cssText = 'position:fixed;left:16px;top:16px;width:423px;height:238px;z-index:99999;pointer-events:none';
                      mount.innerHTML = renderPresenterSlideMiniPreview({
                        id: '__smoke_preview_long_sermon_title_slide__',
                        elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'title-assignee', titlePresentation: 'sermon',
                        contentTitle: '｢하나님의 나라를 함께 살아내는 믿음의 길 ②｣', assignee: '김석범 목사',
                      }, serviceId);
                      document.body.appendChild(mount);
                      const host = mount.querySelector('.svc-slide-mini-output');
                      fitPresenterSermonTitleText(host);
                      const title = mount.querySelector('.presenter-title-content-title');
                      const slide = mount.querySelector('.presenter-slide');
                      const hostRect = host?.getBoundingClientRect();
                      const titleRect = title?.getBoundingClientRect();
                      const result = {
                        slideLayout: slide?.dataset.slideLayout || '',
                        renderClass: slide?.classList.contains('presenter-slide--title-content') ? 'title-content' : '',
                        hasLowerBar: Boolean(mount.querySelector('.presenter-title-assignee')),
                        fontSize: title ? Number.parseFloat(getComputedStyle(title).fontSize) : 0,
                        scrollWidth: title?.scrollWidth || 0,
                        clientWidth: title?.clientWidth || 0,
                        centerOffset: hostRect && titleRect ? Math.round(Math.abs((titleRect.left + titleRect.right - hostRect.left - hostRect.right) / 2)) : -1,
                      };
                      mount.remove();
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      return result;
                    }
                    """
                )
                if (
                    preview_long_sermon_title_fit_state["slideLayout"] == "center_text"
                    and preview_long_sermon_title_fit_state["renderClass"] == "title-content"
                    and preview_long_sermon_title_fit_state["hasLowerBar"] is False
                    and preview_long_sermon_title_fit_state["fontSize"] >= 18
                    and preview_long_sermon_title_fit_state["scrollWidth"] <= preview_long_sermon_title_fit_state["clientWidth"]
                    and preview_long_sermon_title_fit_state["centerOffset"] <= 1
                ):
                    pass_("presenter-preview-long-sermon-title-fit", json.dumps(preview_long_sermon_title_fit_state, ensure_ascii=False))
                else:
                    fail("presenter-preview-long-sermon-title-fit", json.dumps(preview_long_sermon_title_fit_state, ensure_ascii=False))

                fullscreen_long_song_title_fit_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root no-chromakey';
                      document.body.appendChild(outputRoot);
                      renderPresenterOutput({
                        serviceId: '__smoke_fullscreen_long_song_title__',
                        serviceType: 'friday', chromakey: false, outputTheme: 'formal', backgroundImage: '',
                        slides: [{ id: '__smoke_fullscreen_long_song_title_slide__', elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT, type: 'song-title',
                          title: '주 내 소망은 주 더 알기 원합니다',
                          text: '♪ 주 내 소망은 주 더 알기 원합니다', sectionHeading: '찬양', sectionKey: 'praise' }],
                        index: 0, safetyBlank: false,
                      });
                      const name = outputRoot.querySelector('.presenter-slide--fullscreen-song-title .presenter-title-content-title');
                      const style = name ? getComputedStyle(name) : null;
                      const result = {
                        fontSize: style ? Number.parseFloat(style.fontSize) : 0,
                        scrollWidth: name?.scrollWidth || 0,
                        clientWidth: name?.clientWidth || 0,
                        textAlign: style?.textAlign || '',
                      };
                      outputRoot.remove();
                      return result;
                    }
                    """
                )
                if (
                    72 <= fullscreen_long_song_title_fit_state["fontSize"] < 152
                    and fullscreen_long_song_title_fit_state["scrollWidth"] <= fullscreen_long_song_title_fit_state["clientWidth"]
                    and fullscreen_long_song_title_fit_state["textAlign"] == "center"
                ):
                    pass_("presenter-fullscreen-long-song-title-fit", json.dumps(fullscreen_long_song_title_fit_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-long-song-title-fit", json.dumps(fullscreen_long_song_title_fit_state, ensure_ascii=False))

                offering_song_title_output_font_state = page.evaluate(
                    """
                    () => {
                      document.getElementById('presenterOutputRoot')?.remove();
                      const outputRoot = document.createElement('main');
                      outputRoot.id = 'presenterOutputRoot';
                      outputRoot.className = 'presenter-output-root no-chromakey';
                      document.body.appendChild(outputRoot);
                      renderPresenterOutput({
                        serviceId: '__smoke_offering_song_title_output_font__',
                        serviceType: 'sunday2',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: '',
                        slides: [presenterOrderContentTitleSlide(
                          { id: '__smoke_offering_song_title_output_font_slide__', label: '봉헌찬송' },
                          { sectionKey: 'offering', sectionLabel: '봉헌', sectionTitle: '봉헌' },
                          0,
                          '봉헌찬송',
                          '♪ 내 주 되신 주를 참 사랑하고',
                        )],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const slide = root?.querySelector('.presenter-slide--title-assignee');
	                      const songLayout = root?.querySelector('.presenter-section-song-title');
	                      const orderContent = root?.querySelector('.presenter-title-assignee--order-content');
	                      const heading = root?.querySelector('.presenter-title-assignee-order');
	                      const name = root?.querySelector('.presenter-title-assignee-content');
	                      const size = (node) => node ? Number.parseFloat(getComputedStyle(node).fontSize) : 0;
	                      const result = {
	                        hasRoot: Boolean(root),
	                        hasSongLayout: Boolean(songLayout),
	                        hasOrderContent: Boolean(orderContent),
	                        sectionKey: slide?.dataset.sectionKey || '',
	                        text: root?.innerText || '',
	                        headingFontSize: size(heading),
                        headingFontWeight: heading ? getComputedStyle(heading).fontWeight : '',
                        nameFontSize: size(name),
                        nameFontWeight: name ? getComputedStyle(name).fontWeight : '',
                      };
                      root?.remove();
                      return result;
                    }
                    """
                )
                if (
	                    offering_song_title_output_font_state["sectionKey"] == "offering"
	                    and not offering_song_title_output_font_state["hasSongLayout"]
	                    and offering_song_title_output_font_state["hasOrderContent"]
	                    and "내 주 되신 주를 참 사랑하고" in offering_song_title_output_font_state["text"]
	                    and offering_song_title_output_font_state["headingFontSize"] >= 65
	                    and offering_song_title_output_font_state["headingFontWeight"] == "800"
	                    and 50 <= offering_song_title_output_font_state["nameFontSize"] <= 55
	                    and offering_song_title_output_font_state["nameFontWeight"] == "800"
	                ):
                    pass_("presenter-offering-song-title-output-font", json.dumps(offering_song_title_output_font_state, ensure_ascii=False))
                else:
                    fail("presenter-offering-song-title-output-font", json.dumps(offering_song_title_output_font_state, ensure_ascii=False))

                scripture_fit_state = page.evaluate(
                    """
                    () => {
                      const serviceId = '__smoke_scripture_fit_service__';
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      state.services.push({
                        id: serviceId,
                        type_id: 'sunday-first',
                        date: '2026-07-05',
                        service_date: '2026-07-05',
                      });
                      const verseText = '요 20:30–31  30 예수께서 제자들 앞에서 이 책에 기록되지 아니한 다른 표적도 많이 행하셨으나';
                      const slide = {
                        id: '__smoke_scripture_fit_slide__',
                        elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'scripture',
                        title: '본문',
                        text: verseText,
                      };
                      const mount = document.createElement('div');
                      mount.style.cssText = 'position:fixed;left:16px;top:16px;width:368px;height:207px;z-index:99999;pointer-events:none';
                      mount.innerHTML = renderPresenterSlideMiniPreview(slide, serviceId);
                      document.body.appendChild(mount);
                      const bar = mount.querySelector('.presenter-slide-text');
                      const line = mount.querySelector('.presenter-slide-text span');
                      const head = document.createElement('button');
                      head.className = 'svc-board-subgroup-head';
                      head.style.cssText = 'position:fixed;left:16px;top:240px;width:850px';
                      head.innerHTML = `<span>본문</span><strong>${escapeHtml(verseText)}</strong>`;
                      document.body.appendChild(head);
                      const strong = head.querySelector('strong');
                      const barRect = bar.getBoundingClientRect();
                      const lineRect = line.getBoundingClientRect();
                      const headRect = head.getBoundingClientRect();
                      const strongRect = strong.getBoundingClientRect();
                      const lineStyle = getComputedStyle(line);
                      const strongStyle = getComputedStyle(strong);
                      const result = {
                        lineChars: line.style.getPropertyValue('--line-chars'),
                        lineDisplay: lineStyle.display,
                        lineFontSize: lineStyle.fontSize,
                        lineFits: line.scrollWidth <= line.clientWidth + 1,
                        lineInsideTextBox: lineRect.left >= barRect.left - 1 && lineRect.right <= barRect.right + 1,
                        lineScrollWidth: line.scrollWidth,
                        lineClientWidth: line.clientWidth,
                        subgroupTitleMaxWidth: strongStyle.maxWidth,
                        subgroupTitleUsesHeadWidth: strongRect.right <= headRect.right + 1,
                        subgroupTitleScrollWidth: strong.scrollWidth,
                        subgroupTitleClientWidth: strong.clientWidth,
                      };
                      mount.remove();
                      head.remove();
                      state.services = state.services.filter((item) => item.id !== serviceId);
                      return result;
                    }
                    """
                )
                if (
                    scripture_fit_state["lineDisplay"] == "block"
                    and scripture_fit_state["lineFits"]
                    and scripture_fit_state["lineInsideTextBox"]
                    and scripture_fit_state["subgroupTitleMaxWidth"] == "100%"
                    and scripture_fit_state["subgroupTitleUsesHeadWidth"]
                ):
                    pass_("presenter-scripture-line-fit", json.dumps(scripture_fit_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-line-fit", json.dumps(scripture_fit_state, ensure_ascii=False))

                scripture_context_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_scripture_context_service__',
                        type_id: 'sunday-main',
                        date: '2026-07-05',
                        service_date: '2026-07-05',
                      };
                      state.services = state.services.filter((item) => item.id !== service.id);
                      state.services.push(service);
                      if (!state.bibleTranslations.some((translation) => translation.id === '__smoke_ko__')) {
                        state.bibleTranslations.push({
                          id: '__smoke_ko__',
                          translationKey: 'RKB',
                          name: '개역개정',
                          language: 'ko',
                          abbreviation: '개역개정',
                        });
                      }
                      if (!state.bibleTranslations.some((translation) => translation.id === '__smoke_en__')) {
                        state.bibleTranslations.push({
                          id: '__smoke_en__',
                          translationKey: 'WEB',
                          name: 'World English Bible',
                          language: 'en',
                          abbreviation: 'WEB',
                        });
                      }
                      state.selectedBibleTranslationId = '__smoke_en__';
                      const smokeKoTranslation = state.bibleTranslations.find((translation) => translation.id === '__smoke_ko__');
                      cacheServiceScriptureVerses(parseBibleReference('출 23:14–19'), [
                        { book_code: 'EXO', chapter: 23, verse: 14, text: '너는 매년 세 번 내게 절기를 지킬지니라' },
                      ], smokeKoTranslation);
                      cacheServiceScriptureVerses(parseBibleReference('출 24:1–2'), [
                        { book_code: 'EXO', chapter: 24, verse: 1, text: '또 모세에게 이르시되' },
                        { book_code: 'EXO', chapter: 24, verse: 2, text: '너 모세만 여호와께 가까이 나아오고' },
                      ], smokeKoTranslation);
                      const readingItem = {
                        id: '__smoke_scripture_reading_body__',
                        label: '성경봉독',
                        raw_title: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'scripture_body',
                          scriptureReference: '출 23:14–19',
                        }),
                        _worshipSectionKey: 'scripture_reading',
                        _worshipSectionTitle: '성경봉독',
                      };
                      const sermonItem = {
                        id: '__smoke_scripture_sermon_body__',
                        label: '본문',
                        raw_title: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'scripture_body',
                          scriptureReference: '출 23:14–19',
                        }),
                        _worshipSectionKey: 'sermon',
                        _worshipSectionTitle: '설교',
                      };
                      const citationItem = {
                        id: '__smoke_scripture_citation_body__',
                        label: '인용 구절',
                        raw_title: '',
                        memo: serializeServiceItemMemo({
                          elementType: 'scripture_body',
                          scriptureReference: '출 24:1–2',
                        }),
                        _worshipSectionKey: 'sermon',
                        _worshipSectionTitle: '설교',
                      };
                      const readingSlides = normalizePresenterSlidesForServiceOutput(
                        buildPresenterSlidesForServiceItem(readingItem, service, 0),
                        service
                      );
                      const readingTitleSlide = readingSlides[0] || {};
                      const readingSlide = readingSlides[1] || {};
                      const sermonSlide = normalizePresenterSlidesForServiceOutput(
                        buildPresenterSlidesForServiceItem(sermonItem, service, 1),
                        service
                      )[0] || {};
	                      const citationSlides = normalizePresenterSlidesForServiceOutput(
	                        buildPresenterSlidesForServiceItem(citationItem, service, 2),
	                        service
	                      );
	                      const pendingItem = {
	                        id: '__smoke_scripture_pending_body__',
	                        label: '인용 구절',
	                        raw_title: '',
	                        memo: serializeServiceItemMemo({
	                          elementType: 'scripture_body',
	                          scriptureReference: '마 24:3–14',
	                        }),
	                        _worshipSectionKey: 'sermon',
	                        _worshipSectionTitle: '설교',
	                      };
	                      const pendingSlides = normalizePresenterSlidesForServiceOutput(
	                        buildPresenterSlidesForServiceItem(pendingItem, service, 4),
	                        service
	                      );
	                      const fullscreenCitationService = {
	                        ...service,
	                        id: '__smoke_fullscreen_citation_context__',
                        type_id: 'sunday-first',
                      };
                      const fullscreenCitationSlides = normalizePresenterSlidesForServiceOutput(
                        buildPresenterSlidesForServiceItem(citationItem, fullscreenCitationService, 3),
                        fullscreenCitationService
                      );
                      const mount = document.createElement('div');
                      mount.style.cssText = 'position:fixed;left:16px;top:16px;width:368px;height:207px;z-index:99999;pointer-events:none';
                      mount.innerHTML = [
                        renderPresenterSlideMiniPreview(readingSlide, service.id),
                        renderPresenterSlideMiniPreview(sermonSlide, service.id),
                      ].join('');
                      document.body.appendChild(mount);
                      const outputs = [...mount.querySelectorAll('.svc-slide-mini-output')];
                      const slides = [...mount.querySelectorAll('.presenter-slide')];
                      const readingHead = mount.querySelector('.presenter-scripture-reading-head');
                      const readingRef = mount.querySelector('.presenter-scripture-reading-ref');
                      const readingVersion = mount.querySelector('.presenter-scripture-reading-version');
                      const readingNo = mount.querySelector('.presenter-scripture-reading-no');
                      const readingText = mount.querySelector('.presenter-scripture-reading-text');
                      const readingFin = mount.querySelector('.presenter-scripture-reading-fin');
                      const sermonText = slides[1]?.querySelector('.presenter-slide-text');
                      const readingHeadRect = readingHead?.getBoundingClientRect();
                      const readingRefRect = readingRef?.getBoundingClientRect();
                      const readingVersionRect = readingVersion?.getBoundingClientRect();
                      const readingTextRect = readingText?.getBoundingClientRect();
                      const readingTextStyle = readingText ? getComputedStyle(readingText) : null;
                      const readingRefStyle = readingRef ? getComputedStyle(readingRef) : null;
                      const readingVersionStyle = readingVersion ? getComputedStyle(readingVersion) : null;
                      const readingNoStyle = readingNo ? getComputedStyle(readingNo) : null;
                      const readingFinStyle = readingFin ? getComputedStyle(readingFin) : null;
                      const readingSlideStyle = slides[0] ? getComputedStyle(slides[0]) : null;
                      const sermonTextStyle = sermonText ? getComputedStyle(sermonText) : null;
                      const citationMount = document.createElement('div');
                      citationMount.style.cssText = 'position:fixed;left:16px;top:240px;width:368px;height:207px;z-index:99999;pointer-events:none';
                      citationMount.innerHTML = renderPresenterSlideMiniPreview(fullscreenCitationSlides[0], fullscreenCitationService.id);
                      document.body.appendChild(citationMount);
                      const fullscreenCitationOutput = citationMount.querySelector('.svc-slide-mini-output');
                      const fullscreenCitationSlide = citationMount.querySelector('.presenter-slide');
                      const fullscreenCitationReference = citationMount.querySelector('.presenter-scripture-reading-ref');
                      const fullscreenCitationText = citationMount.querySelector('.presenter-scripture-reading-text');
                      const result = {
                        readingTypes: readingSlides.map((slide) => slide.type),
                        readingTitleText: readingTitleSlide.text || '',
                        readingTitle: readingTitleSlide.title || '',
                        readingTitleAssignee: readingTitleSlide.assignee || '',
                        readingContext: readingSlide.scriptureContext || '',
                        readingElementTitle: readingSlide.elementTitle || '',
                        readingReferenceBook: readingSlide.referenceBook || '',
                        readingReferenceRange: readingSlide.referenceRange || '',
                        readingFinal: readingSlide.scriptureReadingFinal || false,
                        readingSuppressBackground: Boolean(readingSlide.suppressBackgroundImage),
                        readingTranslationLabel: readingSlide.translationLabel || '',
                        readerSelectedTranslationId: state.selectedBibleTranslationId || '',
                        presenterFallbackTranslationId: selectedPresenterBibleTranslation()?.id || '',
                        readingOutputContext: presenterSlideOutputContext(readingSlide, true),
                        readingNoChromakey: outputs[0]?.classList.contains('no-chromakey') || false,
                        readingHasClass: slides[0]?.classList.contains('presenter-slide--scripture-reading') || false,
                        readingSlideBackground: slides[0]?.style.getPropertyValue('--presenter-slide-bg-image') || '',
                        readingRequiredImage: presenterSlideImageSource(readingSlide),
                        readingShowsServiceBackground: presenterOutputFrameStateForSlide(readingSlide, {
                          chromakey: false,
                          backgroundImages: ['assets/worship-backgrounds/monthly-fullscreen-a.png'],
                        }).showBackground,
                        readingHasLowerBarText: Boolean(slides[0]?.querySelector('.presenter-slide-text')),
                        readingReference: readingRef?.textContent?.trim() || '',
                        hebrewsChapterReference: presenterScriptureReadingHeaderReference({
                          referenceBook: '히브리서',
                          referenceRange: '10:38–39',
                        }),
                        readingVersion: readingVersion?.textContent?.trim() || '',
                        readingHeaderSplit: Boolean(readingHead && readingRef && readingVersion && readingRefRect && readingVersionRect && readingRefRect.left < readingVersionRect.left),
                        readingBodyBelowHeader: Boolean(readingHeadRect && readingTextRect && readingTextRect.top > readingHeadRect.bottom),
                        readingNumber: readingNo?.textContent?.trim() || '',
                        readingText: readingText?.textContent?.trim() || '',
                        readingFin: readingFin?.textContent?.trim() || '',
                        readingFinFontStyle: readingFinStyle?.fontStyle || '',
                        readingSidePadding: parseFloat(readingSlideStyle?.paddingLeft || '0'),
                        readingFontFamily: readingTextStyle?.fontFamily || '',
                        readingFontWeight: readingTextStyle?.fontWeight || '',
                        readingFontSynthesis: readingTextStyle?.fontSynthesis || '',
                        readingLetterSpacing: readingTextStyle?.letterSpacing || '',
                        readingLineBreak: readingTextStyle?.lineBreak || '',
                        readingTextShadow: readingTextStyle?.textShadow || '',
                        readingTextStroke: readingTextStyle?.webkitTextStrokeWidth || '',
                        readingWordBreak: readingTextStyle?.wordBreak || '',
                        readingLineHeight: readingTextStyle?.lineHeight || '',
                        readingRefFontFamily: readingRefStyle?.fontFamily || '',
                        readingRefFontWeight: readingRefStyle?.fontWeight || '',
                        readingVersionFontFamily: readingVersionStyle?.fontFamily || '',
                        readingVersionFontSize: readingVersionStyle?.fontSize || '',
                        readingVersionFontWeight: readingVersionStyle?.fontWeight || '',
                        readingVersionOpacity: readingVersionStyle?.opacity || '',
                        readingNumberFontFamily: readingNoStyle?.fontFamily || '',
                        readingNumberFontWeight: readingNoStyle?.fontWeight || '',
                        readingFinFontFamily: readingFinStyle?.fontFamily || '',
                        readingFinFontWeight: readingFinStyle?.fontWeight || '',
                        sermonContext: sermonSlide.scriptureContext || '',
                        sermonElementTitle: sermonSlide.elementTitle || '',
                        sermonOutputContext: presenterSlideOutputContext(sermonSlide, true),
                        sermonNoChromakey: outputs[1]?.classList.contains('no-chromakey') || false,
                        sermonHasClass: slides[1]?.classList.contains('presenter-slide--scripture-sermon') || false,
                        sermonHasLowerBarText: Boolean(slides[1]?.querySelector('.presenter-slide-text')),
                        sermonFontFamily: sermonTextStyle?.fontFamily || '',
                        sermonFontSize: Number.parseFloat(sermonTextStyle?.fontSize || '0'),
                        sermonFontWeight: sermonTextStyle?.fontWeight || '',
                        sermonLineHeight: sermonTextStyle?.lineHeight || '',
                        lyricsFontSizeToken: (() => {
                          const probe = document.createElement('span');
                          probe.style.cssText = 'position:fixed;visibility:hidden;font-size:var(--presenter-size-lyrics)';
                          (slides[1]?.closest('.presenter-output-root') || mount.querySelector('.presenter-output-root') || mount).appendChild(probe);
                          const value = Number.parseFloat(getComputedStyle(probe).fontSize || '0');
                          probe.remove();
                          return value;
                        })(),
	                        citationTexts: citationSlides.map((slide) => slide.text || ''),
	                        fullscreenCitationContext: fullscreenCitationSlides[0]?.scriptureContext || '',
	                        fullscreenCitationOutputContext: presenterSlideOutputContext(fullscreenCitationSlides[0], true),
	                        fullscreenCitationNoChromakey: fullscreenCitationOutput?.classList.contains('no-chromakey') || false,
	                        fullscreenCitationHasReadingClass: fullscreenCitationSlide?.classList.contains('presenter-slide--scripture-reading') || false,
	                        fullscreenCitationHasReadingBody: Boolean(citationMount.querySelector('.presenter-scripture-reading')),
	                        fullscreenCitationReference: fullscreenCitationReference?.textContent?.trim() || '',
	                        fullscreenCitationText: fullscreenCitationText?.textContent?.trim() || '',
	                        citationBadge: presenterSlideScriptureReferenceBadge(citationSlides[0]),
                        citationNoNumberBadge: presenterSlideScriptureReferenceBadge({
                          ...citationSlides[0],
                          text: '또 모세에게 이르시되',
                          referenceBook: '출애굽기',
	                          referenceRange: '24:1–2',
	                          title: '출애굽기 24:1–2',
	                        }),
	                        pendingType: pendingSlides[0]?.type || '',
	                        pendingElementType: pendingSlides[0]?.elementType || '',
	                        pendingLayout: pendingSlides[0]?.layout || '',
	                        pendingText: pendingSlides[0]?.text || '',
	                        pendingMarker: pendingSlides[0]?.marker || '',
	                        pendingSkipTrailingBlank: Boolean(pendingSlides[0]?.skipTrailingBlank),
	                      };
                      citationMount.remove();
                      mount.remove();
                      state.services = state.services.filter((item) => item.id !== service.id);
                      return result;
                    }
                    """
                )
                if (
                    scripture_context_state["readingTypes"][:2] == ["title-assignee", "scripture"]
                    and scripture_context_state["readingTitle"] == "성경봉독"
                    and scripture_context_state["readingTitleAssignee"] == "출애굽기 23:14–19"
                    and scripture_context_state["readingTitleText"] == "성경봉독\n출애굽기 23:14–19"
                    and
                    scripture_context_state["readingContext"] == "reading"
                    and scripture_context_state["readingElementTitle"] == "출애굽기 23:14–19"
                    and scripture_context_state["readingOutputContext"] == "clean"
                    and scripture_context_state["readingNoChromakey"]
                    and scripture_context_state["readingHasClass"]
                    and scripture_context_state["readingSlideBackground"] != ""
                    and scripture_context_state["readingRequiredImage"].endswith("scripture-reading-cross.png")
                    and not scripture_context_state["readingShowsServiceBackground"]
                    and not scripture_context_state["readingHasLowerBarText"]
                    and scripture_context_state["readingReference"] == "출애굽기 23:14"
                    and scripture_context_state["hebrewsChapterReference"] == "히브리서 10장"
                    and scripture_context_state["readingReferenceBook"] == "출애굽기"
                    and scripture_context_state["readingReferenceRange"] == "23:14–19"
                    and scripture_context_state["readingFinal"]
                    and not scripture_context_state["readingSuppressBackground"]
                    and scripture_context_state["readingTranslationLabel"] == "개역개정"
                    and scripture_context_state["readingVersion"] == "개역개정"
                    and scripture_context_state["readerSelectedTranslationId"] == "__smoke_en__"
                    and scripture_context_state["presenterFallbackTranslationId"] == "__smoke_ko__"
                    and scripture_context_state["readingFin"] == "Fin."
                    and scripture_context_state["readingFinFontStyle"] == "italic"
                    and scripture_context_state["readingSidePadding"] >= 75
                    and scripture_context_state["readingHeaderSplit"]
                    and scripture_context_state["readingBodyBelowHeader"]
                    and scripture_context_state["readingNumber"] == ""
                    and "너는 매년 세 번" in scripture_context_state["readingText"]
                    and "Eulyoo1945" in scripture_context_state["readingFontFamily"]
                    and "Eulyoo1945" not in scripture_context_state["readingRefFontFamily"]
                    and "Eulyoo1945" not in scripture_context_state["readingVersionFontFamily"]
                    and "Eulyoo1945" in scripture_context_state["readingFinFontFamily"]
                    and scripture_context_state["readingFontWeight"] == "700"
                    and scripture_context_state["readingFontSynthesis"] in ["weight", "auto"]
                    and scripture_context_state["readingRefFontWeight"] == "700"
                    and scripture_context_state["readingVersionFontWeight"] == "600"
                    and scripture_context_state["readingVersionOpacity"] == "1"
                    and float(scripture_context_state["readingVersionFontSize"].replace("px", "")) >= 35
                    and scripture_context_state["readingFinFontWeight"] == "600"
                    and -6 <= float(scripture_context_state["readingLetterSpacing"].replace("px", "") or "0") <= -5
                    and scripture_context_state["readingLineBreak"] == "anywhere"
                    and scripture_context_state["readingTextShadow"] == "none"
                    and float(scripture_context_state["readingTextStroke"].replace("px", "") or "0") > 0
                    and scripture_context_state["readingWordBreak"] == "break-all"
                    and float(scripture_context_state["readingLineHeight"].replace("px", "") or "0") >= 75
                    and scripture_context_state["sermonContext"] == "sermon-chromakey"
                    and scripture_context_state["sermonElementTitle"] == "출애굽기 23:14–19"
                    and scripture_context_state["sermonOutputContext"] == "chromakey"
                    and not scripture_context_state["sermonNoChromakey"]
                    and not scripture_context_state["sermonHasClass"]
                    and scripture_context_state["sermonHasLowerBarText"]
                    and scripture_context_state["sermonFontSize"] == scripture_context_state["lyricsFontSizeToken"]
                    and scripture_context_state["citationTexts"] == [
                        "출 24:1   또 모세에게 이르시되",
                        "출 24:2   너 모세만 여호와께 가까이 나아오고",
                    ]
	                    and scripture_context_state["citationBadge"] == "출애굽기 24:1"
                    and scripture_context_state["citationNoNumberBadge"] == "출애굽기 24:1–2"
	                    and scripture_context_state["pendingType"] == "scripture-pending"
	                    and scripture_context_state["pendingElementType"] == "blank"
	                    and scripture_context_state["pendingLayout"] == "blank"
	                    and scripture_context_state["pendingText"] == ""
	                    and scripture_context_state["pendingMarker"] == ""
	                    and scripture_context_state["pendingSkipTrailingBlank"]
	                    and scripture_context_state["fullscreenCitationContext"] == "citation"
                    and scripture_context_state["fullscreenCitationOutputContext"] == "clean"
                    and scripture_context_state["fullscreenCitationNoChromakey"]
                    and scripture_context_state["fullscreenCitationHasReadingClass"]
                    and scripture_context_state["fullscreenCitationHasReadingBody"]
                    and scripture_context_state["fullscreenCitationReference"] == "출애굽기 24:1"
                    and scripture_context_state["fullscreenCitationText"].startswith("또 모세에게")
                ):
                    pass_("presenter-scripture-context-layouts", json.dumps(scripture_context_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-context-layouts", json.dumps(scripture_context_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      state.presenter.serviceId = serviceId;
                      state.presenter.liveScripture = {
                        reference: "",
                        draft: "",
                        active: true,
                        slide: {
                          id: "__smoke_live_scripture_input_scope__",
                          elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          type: "scripture",
                          title: "",
                          text: "",
                          live: true,
                        },
                      };
                      state.presenter.safetyBlank = false;
                      const service = state.services.find((entry) => entry.id === serviceId);
                      const slides = presenterSlidesForService(serviceId);
                      const root = document.querySelector('#mindexRightSidebar [data-presenter-right-sidebar]');
                      patchPresenterControlsTop(root, service, slides, true, state.presenter.index);
                    }
                    """,
                    service["id"],
                )
                live_scripture_slide_index = page.evaluate(
                    """
                    (serviceId) => {
                      const target = state.presenter.slides.findIndex((slide) =>
                        `${slide.sectionLabel || ''} ${slide.title || ''} ${slide.text || ''}`.replace(/\\s+/g, '').includes('실시간성구송출')
                      );
                      state.presenter.index = Math.max(target, 0);
                      const service = state.services.find((entry) => entry.id === serviceId);
                      const slides = presenterSlidesForService(serviceId);
                      const root = document.querySelector('#mindexRightSidebar [data-presenter-right-sidebar]');
                      patchPresenterControlsTop(root, service, slides, true, state.presenter.index);
                      return target;
                    }
                    """,
                    service["id"],
                )
                live_input = page.locator(f'[data-live-scripture-input][data-service-id="{service["id"]}"]')
                live_input.fill("요")
                live_input.focus()
                live_input.evaluate("(node) => node.setSelectionRange(node.value.length, node.value.length)")
                page.keyboard.press("Space")
                page.keyboard.press("5")
                page.keyboard.press("ArrowRight")
                focused_input_state = page.evaluate(
                    """
                    (serviceId) => ({
                      index: state.presenter.index,
                      draft: state.presenter.jumpDraft,
                      inputValue: document.querySelector(`[data-live-scripture-input][data-service-id="${serviceId}"]`)?.value || '',
                    })
                    """,
                    service["id"],
                )
                if (
                    focused_input_state["index"] == max(live_scripture_slide_index, 0)
                    and focused_input_state["draft"] == ""
                    and focused_input_state["inputValue"] == "요 5"
                ):
                    pass_("presenter-keyboard-input-scope", json.dumps(focused_input_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-input-scope", json.dumps(focused_input_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      state.presenter.liveScripture = { reference: "", draft: "", active: false, slide: null };
                      renderPresenterControlState(serviceId);
                    }
                    """,
                    service["id"],
                )
                jump_scope_input = page.locator(f'[data-presenter-jump-input][data-service-id="{service["id"]}"]')
                jump_scope_index_before = page.evaluate("() => state.presenter.index")
                jump_scope_input.fill("1")
                jump_scope_input.focus()
                page.wait_for_function(
                    """
                    (serviceId) => document.activeElement?.matches(`[data-presenter-jump-input][data-service-id="${serviceId}"]`)
                    """,
                    arg=service["id"],
                    timeout=1000,
                )
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(250)
                jump_scope_state = page.evaluate(
                    """
                    (serviceId) => ({
                      index: state.presenter.index,
                      maxIndex: Math.max(0, state.presenter.slides.length - 1),
                      draft: state.presenter.jumpDraft,
                      inputValue: document.querySelector(`[data-presenter-jump-input][data-service-id="${serviceId}"]`)?.value || '',
                      focused: document.activeElement?.matches(`[data-presenter-jump-input][data-service-id="${serviceId}"]`) || false,
                    })
                    """,
                    service["id"],
                )
                if (
                    jump_scope_state["index"] == min(jump_scope_index_before + 1, jump_scope_state["maxIndex"])
                    and jump_scope_state["draft"] == ""
                    and jump_scope_state["inputValue"] == str(jump_scope_state["index"] + 1)
                ):
                    pass_("presenter-keyboard-jump-input-arrows-advance", json.dumps(jump_scope_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-jump-input-arrows-advance", json.dumps(jump_scope_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      preparePresenterService(serviceId);
                      state.presenter.index = 0;
                      state.presenter.safetyBlank = false;
                      state.presenter.jumpDraft = "";
                      renderPresenterControlState(serviceId);
                    }
                    """,
                    service["id"],
                )
                jump_scope_input = page.locator(f'[data-presenter-jump-input][data-service-id="{service["id"]}"]')
                jump_scope_input.fill("9")
                jump_scope_input.focus()
                page.wait_for_function(
                    """
                    (serviceId) => document.activeElement?.matches(`[data-presenter-jump-input][data-service-id="${serviceId}"]`)
                    """,
                    arg=service["id"],
                    timeout=1000,
                )
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
                jump_escape_state = page.evaluate(
                    """
                    (serviceId) => ({
                      index: state.presenter.index,
                      draft: state.presenter.jumpDraft,
                      inputValue: document.querySelector(`[data-presenter-jump-input][data-service-id="${serviceId}"]`)?.value || '',
                    })
                    """,
                    service["id"],
                )
                if (
                    jump_escape_state["index"] == 0
                    and jump_escape_state["draft"] == ""
                    and jump_escape_state["inputValue"] == "1"
                ):
                    pass_("presenter-keyboard-jump-input-escape-cancel", json.dumps(jump_escape_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-jump-input-escape-cancel", json.dumps(jump_escape_state, ensure_ascii=False))

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
                    service["id"],
                )
                if (
                    form_label_state["heads"] == 0
                    and form_label_state["dividers"] == 0
                    and not form_label_state["continuationBadges"]
                ):
                    pass_("presenter-form-labels", json.dumps(form_label_state, ensure_ascii=False))
                else:
                    fail("presenter-form-labels", json.dumps(form_label_state, ensure_ascii=False))

                scripture_badge_state = page.evaluate(
                    """
                    (() => ({
                      fromSlideBook: presenterSlideScriptureReferenceBadge({
                        elementType: 'scripture_text',
                        layout: 'lower_bar_text',
                        referenceBook: '출',
                        referenceRange: '3:1–3',
                        text: '1 모세가 장인 이드로의 양 떼를 치더니',
                      }),
                      fromFullBook: presenterSlideScriptureReferenceBadge({
                        elementType: 'scripture_text',
                        layout: 'lower_bar_text',
                        referenceBook: '출',
                        referenceBookFull: '출애굽기',
                        referenceRange: '3:1–3',
                        text: '2 여호와의 사자가 떨기나무 가운데로부터',
                      }),
                      fromInline: presenterSlideScriptureReferenceBadge({
                        elementType: 'scripture_text',
                        layout: 'lower_bar_text',
                        referenceBook: '',
                        referenceRange: '',
                        text: '출 3:1 모세가 장인 이드로의 양 떼를 치더니',
                      }),
                    }))()
                    """
                )
                if scripture_badge_state == {
                    "fromSlideBook": "출애굽기 3:1–3",
                    "fromFullBook": "출애굽기 3:1–3",
                    "fromInline": "출애굽기 3:1",
                }:
                    pass_("presenter-scripture-thumb-badge-full-book", json.dumps(scripture_badge_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-thumb-badge-full-book", json.dumps(scripture_badge_state, ensure_ascii=False))

                legacy_artifact_state = page.evaluate(
                    """
                    (() => ({
                      visible: /\\b(?:Elem|Element|Section|Slide)_/i.test(document.body.innerText),
                      presentationTerms: /\\bPPTX?\\b|PowerPoint/i.test(document.body.innerText),
                      labels: [...document.querySelectorAll('[aria-label]')]
                        .map((node) => node.getAttribute('aria-label') || '')
                        .filter((label) => /\\b(?:Elem|Element|Section|Slide)_/i.test(label)),
                    }))()
                    """
                )
                if not legacy_artifact_state["visible"] and not legacy_artifact_state["presentationTerms"] and not legacy_artifact_state["labels"]:
                    pass_("presenter-legacy-artifact-hidden", json.dumps(legacy_artifact_state, ensure_ascii=False))
                else:
                    fail("presenter-legacy-artifact-hidden", json.dumps(legacy_artifact_state, ensure_ascii=False))

                if service["slides"] > 1:
                    page.click(f'[data-presenter-action="next"][data-service-id="{service["id"]}"]')
                    next_state = page.evaluate(
                        """
                        (() => ({
                          serviceId: state.presenter.serviceId,
                          index: state.presenter.index,
                          slides: state.presenter.slides.length
                        }))()
                        """
                    )
                    if next_state["serviceId"] == service["id"] and next_state["index"] == 1:
                        pass_("presenter-next-control", json.dumps(next_state, ensure_ascii=False))
                    else:
                        fail("presenter-next-control", json.dumps(next_state, ensure_ascii=False))

                    jump_target = min(service["slides"], 3)
                    jump_input = page.locator(f'[data-presenter-jump-input][data-service-id="{service["id"]}"]')
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
                    if jump_state["serviceId"] == service["id"] and jump_state["index"] == jump_target - 1 and not jump_state["draft"]:
                        pass_("presenter-jump-control", json.dumps(jump_state, ensure_ascii=False))
                    else:
                        fail("presenter-jump-control", json.dumps(jump_state, ensure_ascii=False))

                    page.evaluate(
                        """
	                        (() => {
	                          state.presenter.outputWindow = null;
	                          state.presenter.outputConnectedAt = 0;
	                          const primary = {
                            isPrimary: true,
                            left: 0,
                            top: 0,
                            availLeft: 0,
                            availTop: 0,
                            width: 1440,
                            height: 900,
                            availWidth: 1440,
                            availHeight: 900,
                          };
                          const secondary = {
                            isPrimary: false,
                            left: 1440,
                            top: 0,
                            availLeft: 1440,
                            availTop: 0,
                            width: 1920,
                            height: 1080,
                            availWidth: 1920,
                            availHeight: 1080,
                          };
                          window.__mindexScreenDetailsCalls = 0;
                          window.getScreenDetails = async () => {
                            window.__mindexScreenDetailsCalls += 1;
                            return {
                              currentScreen: primary,
                              screens: [primary, secondary],
                              addEventListener() {},
                            };
                          };
                          window.__mindexPresenterOpenArgs = null;
                          window.__mindexPresenterFullscreenCalls = 0;
                          window.__mindexPresenterFocusCalls = 0;
                          window.__mindexPresenterCloseCalls = 0;
                          window.open = (url, name, features) => {
                            window.__mindexPresenterOpenArgs = { url, name, features };
                            window.__mindexPresenterOpenCalls = (window.__mindexPresenterOpenCalls || 0) + 1;
                            return {
                              closed: false,
                              focus() { window.__mindexPresenterFocusCalls += 1; },
                              close() {
                                this.closed = true;
                                window.__mindexPresenterCloseCalls += 1;
                              },
                              addEventListener() {},
                              moveTo() {},
                              resizeTo() {},
                              document: {
                                documentElement: {
                                  requestFullscreen() {
                                    window.__mindexPresenterFullscreenCalls += 1;
                                    return Promise.resolve();
                                  }
                                }
                              }
                            };
                          };
                        })()
                        """
                    )
                    page.evaluate("() => requestPresenterScreens()")
                    page.wait_for_function("() => state.presenter.screens.length === 2", timeout=5000)
                    page.click(f'.svc-presenter-side-panel .svc-presenter-launch[data-service-id="{service["id"]}"]')
                    page.wait_for_function("() => Boolean(window.__mindexPresenterOpenArgs)", timeout=5000)
                    target_state = page.evaluate(
                        """
                        (() => ({
                          args: window.__mindexPresenterOpenArgs,
                          fullscreenCalls: window.__mindexPresenterFullscreenCalls || 0,
                          focusCalls: window.__mindexPresenterFocusCalls || 0,
                          openCalls: window.__mindexPresenterOpenCalls || 0,
                          screenDetailsCalls: window.__mindexScreenDetailsCalls || 0,
                          action: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch')?.dataset.presenterAction || '',
                          label: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch span')?.textContent.trim() || '',
                          icon: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch svg')?.getAttribute('data-lucide') || '',
                        }))()
                        """
                    )
                    target_features = target_state["args"]["features"] or ""
                    if (
                        "fullscreen=1" not in target_state["args"]["url"]
                        and "left=1440" in target_features
                        and "top=0" in target_features
                        and "width=1920" in target_features
                        and "height=1080" in target_features
                        and "fullscreen=yes" not in target_features
                        and target_state["fullscreenCalls"] == 0
                        and target_state["focusCalls"] == 1
                        and target_state["openCalls"] == 1
                        and target_state["screenDetailsCalls"] == 1
                        and target_state["action"] == "stop"
                        and target_state["label"] == "송출 종료"
                        and target_state["icon"] == "screen-share-off"
                    ):
                        pass_("presenter-secondary-fullscreen-launch", json.dumps(target_state, ensure_ascii=False))
                    else:
                        fail("presenter-secondary-fullscreen-launch", json.dumps(target_state, ensure_ascii=False))

                    page.click(f'.svc-presenter-side-panel .svc-presenter-launch[data-service-id="{service["id"]}"]')
                    page.wait_for_function("() => (window.__mindexPresenterCloseCalls || 0) === 1", timeout=5000)
                    stop_state = page.evaluate(
                        """
                        (() => ({
                          openCalls: window.__mindexPresenterOpenCalls || 0,
                          closeCalls: window.__mindexPresenterCloseCalls || 0,
                          hasWindowRef: Boolean(state.presenter.outputWindow),
                          action: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch')?.dataset.presenterAction || '',
                          label: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch span')?.textContent.trim() || '',
                        }))()
                        """
                    )
                    if (
                        stop_state["openCalls"] == 1
                        and stop_state["closeCalls"] == 1
                        and not stop_state["hasWindowRef"]
                        and stop_state["action"] == "open"
                        and stop_state["label"] == "송출 시작"
                    ):
                        pass_("presenter-show-stop-toggle", json.dumps(stop_state, ensure_ascii=False))
                    else:
                        fail("presenter-show-stop-toggle", json.dumps(stop_state, ensure_ascii=False))

                    music_flow_state = page.evaluate(
                        f"""
                        (() => {{
                          const serviceId = {json.dumps(service["id"])};
                          preparePresenterService(serviceId);
                          const previousMusic = {{ ...state.serviceMusic }};
                          let pauseCalls = 0;
                          let removeSourceCalls = 0;
                          state.serviceMusic = {{
                            ...state.serviceMusic,
                            audio: {{
                              paused: false,
                              ended: false,
                              pause() {{ pauseCalls += 1; }},
                              removeAttribute(name) {{
                                if (name === 'src') removeSourceCalls += 1;
                              }},
                            }},
                            objectUrl: '',
                            fileName: '',
                            mode: 'presenter-audio',
                            sourceKey: 'assets/audio/keep-playing.mp3',
                            sourceLabel: '계속 재생',
                            playing: true,
                            volumeLevel: 3,
                          }};
                          state.presenter.index = 0;
                          movePresenterSlide(1);
                          refreshPresenterForService(serviceId, {{ publish: false, renderControls: false }});
                          stopPresenterOutput(serviceId);
                          const result = {{
                            pauseCalls,
                            removeSourceCalls,
                            playing: state.serviceMusic.playing,
                            mode: state.serviceMusic.mode,
                            sourceKey: state.serviceMusic.sourceKey,
                            sourceLabel: state.serviceMusic.sourceLabel,
                          }};
                          state.serviceMusic = previousMusic;
                          return result;
                        }})()
                        """
                    )
                    if (
                        music_flow_state["pauseCalls"] == 0
                        and music_flow_state["removeSourceCalls"] == 0
                        and music_flow_state["playing"]
                        and music_flow_state["mode"] == "presenter-audio"
                        and music_flow_state["sourceKey"] == "assets/audio/keep-playing.mp3"
                        and music_flow_state["sourceLabel"] == "계속 재생"
                    ):
                        pass_("presenter-controller-music-survives-presenter-flow", json.dumps(music_flow_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-survives-presenter-flow", json.dumps(music_flow_state, ensure_ascii=False))

                    music_open_nav_state = page.evaluate(
                        f"""
                        (() => {{
                          const serviceId = {json.dumps(service["id"])};
                          const previousMusic = {{ ...state.serviceMusic }};
                          const previousOpen = window.open;
                          const previousChannel = state.presenter.channel;
                          let pauseCalls = 0;
                          let removeSourceCalls = 0;
                          window.open = () => ({{
                            closed: false,
                            focus() {{}},
                            addEventListener() {{}},
                            postMessage() {{}},
                          }});
                          state.presenter.channel = {{
                            postMessage() {{}},
                          }};
                          state.serviceMusic = {{
                            ...state.serviceMusic,
                            audio: {{
                              paused: false,
                              ended: false,
                              pause() {{ pauseCalls += 1; }},
                              removeAttribute(name) {{
                                if (name === 'src') removeSourceCalls += 1;
                              }},
                            }},
                            objectUrl: '',
                            fileName: '',
                            mode: 'presenter-audio',
                            sourceKey: 'assets/audio/open-nav.mp3',
                            sourceLabel: '송출 중 음악',
                            playing: false,
                            volumeLevel: 3,
                          }};
                          runPresenterAction('open', serviceId);
                          runPresenterAction('next', serviceId);
                          refreshPresenterForService(serviceId, {{ publish: false, renderControls: false }});
                          const result = {{
                            pauseCalls,
                            removeSourceCalls,
                            playing: state.serviceMusic.playing,
                            mode: state.serviceMusic.mode,
                            sourceKey: state.serviceMusic.sourceKey,
                            sourceLabel: state.serviceMusic.sourceLabel,
                          }};
                          window.open = previousOpen;
                          state.presenter.channel = previousChannel;
                          state.serviceMusic = previousMusic;
                          state.presenter.outputWindow = null;
                          state.presenter.outputConnectedAt = 0;
                          state.presenter.outputPendingAt = 0;
                          stopPresenterOutputWindowMonitor();
                          return result;
                        }})()
                        """
                    )
                    if (
                        music_open_nav_state["pauseCalls"] == 0
                        and music_open_nav_state["removeSourceCalls"] == 0
                        and music_open_nav_state["playing"]
                        and music_open_nav_state["mode"] == "presenter-audio"
                        and music_open_nav_state["sourceKey"] == "assets/audio/open-nav.mp3"
                        and music_open_nav_state["sourceLabel"] == "송출 중 음악"
                    ):
                        pass_("presenter-controller-music-survives-output-open-navigation", json.dumps(music_open_nav_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-survives-output-open-navigation", json.dumps(music_open_nav_state, ensure_ascii=False))

                    music_source_resume_state = page.evaluate(
                        """
                        (async () => {
                          const previousMusic = { ...state.serviceMusic };
                          let pauseCalls = 0;
                          let playCalls = 0;
                          const audio = {
                            paused: true,
                            ended: false,
                            currentSrc: '',
                            src: '',
                            loop: false,
                            volume: 0,
                            play() {
                              playCalls += 1;
                              this.paused = false;
                              return Promise.resolve();
                            },
                            pause() {
                              pauseCalls += 1;
                              this.paused = true;
                            },
                            removeAttribute(name) {
                              if (name === 'src') this.src = '';
                            },
                          };
                          state.serviceMusic = {
                            ...state.serviceMusic,
                            audio,
                            objectUrl: '',
                            fileName: '',
                            mode: 'presenter-audio',
                            sourceKey: 'assets/audio/resume-preserved.mp3',
                            sourceLabel: '다시 재생 음악',
                            playing: false,
                            volumeLevel: 3,
                          };
                          runServiceMusicAction('toggle');
                          await new Promise((resolve) => setTimeout(resolve, 20));
                          const result = {
                            pauseCalls,
                            playCalls,
                            src: audio.src,
                            playing: state.serviceMusic.playing,
                            mode: state.serviceMusic.mode,
                            sourceKey: state.serviceMusic.sourceKey,
                            sourceLabel: state.serviceMusic.sourceLabel,
                          };
                          state.serviceMusic = previousMusic;
                          return result;
                        })()
                        """
                    )
                    if (
                        music_source_resume_state["pauseCalls"] == 0
                        and music_source_resume_state["playCalls"] == 1
                        and music_source_resume_state["src"] == "assets/audio/resume-preserved.mp3"
                        and music_source_resume_state["playing"]
                        and music_source_resume_state["mode"] == "presenter-audio"
                        and music_source_resume_state["sourceKey"] == "assets/audio/resume-preserved.mp3"
                        and music_source_resume_state["sourceLabel"] == "다시 재생 음악"
                    ):
                        pass_("presenter-controller-music-resumes-preserved-source", json.dumps(music_source_resume_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-resumes-preserved-source", json.dumps(music_source_resume_state, ensure_ascii=False))

                    music_pause_guard_state = page.evaluate(
                        """
                        (async () => {
                          const previousMusic = { ...state.serviceMusic };
                          const audio = getServiceMusicAudio();
                          const previousPlay = audio.play;
                          let playCalls = 0;
                          audio.play = () => {
                            playCalls += 1;
                            return Promise.resolve();
                          };
                          state.serviceMusic.sourceKey = 'assets/audio/click-survive.mp3';
                          state.serviceMusic.sourceLabel = '클릭 보호 음악';
                          state.serviceMusic.mode = 'presenter-audio';
                          state.serviceMusic.playing = true;
                          state.serviceMusic.intentionalPauseUntil = 0;
                          state.serviceMusic.resumeAttempts = 0;
                          audio.dispatchEvent(new Event('pause'));
                          await new Promise((resolve) => setTimeout(resolve, 20));
                          const accidental = {
                            playCalls,
                            playing: state.serviceMusic.playing,
                            resumeAttempts: state.serviceMusic.resumeAttempts,
                            sourceKey: state.serviceMusic.sourceKey,
                          };
                          allowIntentionalServiceMusicPause(1000);
                          audio.dispatchEvent(new Event('pause'));
                          await new Promise((resolve) => setTimeout(resolve, 20));
                          const intentional = {
                            playCalls,
                            playing: state.serviceMusic.playing,
                            resumeAttempts: state.serviceMusic.resumeAttempts,
                            sourceKey: state.serviceMusic.sourceKey,
                          };
                          audio.play = previousPlay;
                          clearServiceMusicResumeTimer();
                          state.serviceMusic = previousMusic;
                          return { accidental, intentional };
                        })()
                        """
                    )
                    if (
                        music_pause_guard_state["accidental"]["playCalls"] == 1
                        and music_pause_guard_state["accidental"]["playing"]
                        and music_pause_guard_state["accidental"]["resumeAttempts"] == 0
                        and music_pause_guard_state["accidental"]["sourceKey"] == "assets/audio/click-survive.mp3"
                        and music_pause_guard_state["intentional"]["playCalls"] == 1
                    ):
                        pass_("presenter-controller-music-resumes-accidental-pause", json.dumps(music_pause_guard_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-resumes-accidental-pause", json.dumps(music_pause_guard_state, ensure_ascii=False))

                    music_pause_retry_state = page.evaluate(
                        """
                        (async () => {
                          const previousMusic = { ...state.serviceMusic };
                          const audio = getServiceMusicAudio();
                          const previousPlay = audio.play;
                          let playCalls = 0;
                          audio.play = () => {
                            playCalls += 1;
                            if (playCalls === 1) return Promise.reject(new Error('temporary interruption'));
                            return Promise.resolve();
                          };
                          state.serviceMusic.sourceKey = 'assets/audio/retry-survive.mp3';
                          state.serviceMusic.sourceLabel = '재시도 보호 음악';
                          state.serviceMusic.mode = 'presenter-audio';
                          state.serviceMusic.playing = true;
                          state.serviceMusic.intentionalPauseUntil = 0;
                          state.serviceMusic.resumeAttempts = 0;
                          audio.dispatchEvent(new Event('pause'));
                          await new Promise((resolve) => setTimeout(resolve, 420));
                          const result = {
                            playCalls,
                            playing: state.serviceMusic.playing,
                            resumeAttempts: state.serviceMusic.resumeAttempts,
                            sourceKey: state.serviceMusic.sourceKey,
                          };
                          audio.play = previousPlay;
                          clearServiceMusicResumeTimer();
                          state.serviceMusic = previousMusic;
                          return result;
                        })()
                        """
                    )
                    if (
                        music_pause_retry_state["playCalls"] >= 2
                        and music_pause_retry_state["playing"]
                        and music_pause_retry_state["resumeAttempts"] == 0
                        and music_pause_retry_state["sourceKey"] == "assets/audio/retry-survive.mp3"
                    ):
                        pass_("presenter-controller-music-retries-accidental-pause", json.dumps(music_pause_retry_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-retries-accidental-pause", json.dumps(music_pause_retry_state, ensure_ascii=False))

                    page.evaluate(
                        f"""
                        (() => {{
                          const serviceId = {json.dumps(service["id"])};
                          preparePresenterService(serviceId);
                          window.__mindexPreviousMusic = {{ ...state.serviceMusic }};
                          window.__mindexMusicPauseCalls = 0;
                          state.serviceMusic = {{
                            ...state.serviceMusic,
                            audio: {{
                              pause() {{ window.__mindexMusicPauseCalls += 1; }},
                              removeAttribute() {{}},
                            }},
                            objectUrl: '',
                            fileName: '',
                            mode: 'presenter-audio',
                            sourceKey: 'assets/audio/focused-button.mp3',
                            sourceLabel: '포커스 음악',
                            playing: true,
                            volumeLevel: 3,
                          }};
                          state.presenter.index = 0;
                          renderPresenterControlState(serviceId);
                        }})()
                        """
                    )
                    blocked_music_keys = ["Enter", "Space", "ArrowRight", "PageDown", "ArrowLeft", "Home", "End"]
                    for key_name in blocked_music_keys:
                        page.locator(".svc-music-toggle").focus()
                        page.keyboard.press(key_name)
                    page.wait_for_timeout(100)
                    music_key_state = page.evaluate(
                        """
                        (() => {
                          const result = {
                            pauseCalls: window.__mindexMusicPauseCalls || 0,
                            playing: state.serviceMusic.playing,
                            index: state.presenter.index,
                            activeElement: document.activeElement?.className || '',
                          };
                          state.serviceMusic = window.__mindexPreviousMusic;
                          delete window.__mindexPreviousMusic;
                          delete window.__mindexMusicPauseCalls;
                          renderPresenterControlState(state.presenter.serviceId);
                          return result;
                        })()
                        """
                    )
                    if (
                        music_key_state["pauseCalls"] == 0
                        and music_key_state["playing"]
                        and music_key_state["index"] == 0
                    ):
                        pass_("presenter-controller-music-nav-keys-do-not-stop", json.dumps(music_key_state, ensure_ascii=False))
                    else:
                        fail("presenter-controller-music-nav-keys-do-not-stop", json.dumps(music_key_state, ensure_ascii=False))

                    page.click(f'.svc-presenter-side-panel .svc-presenter-launch[data-service-id="{service["id"]}"]')
                    page.wait_for_function("() => (window.__mindexPresenterOpenCalls || 0) === 2", timeout=5000)

                    dbl_target = min(service["slides"] - 1, 4)
                    page.evaluate(
                        """
                        (() => {
                          window.__mindexPresenterOpenCalls = 0;
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
                        f'.svc-slide-thumb[data-service-id="{service["id"]}"][data-presenter-index="{dbl_target}"]'
                    ).dblclick()
                    dbl_state = page.evaluate(
                        """
                        (() => ({
                          serviceId: state.presenter.serviceId,
                          index: state.presenter.index,
                          openCalls: window.__mindexPresenterOpenCalls || 0,
                          hasWindowRef: Boolean(state.presenter.outputWindow)
                        }))()
                        """
                    )
                    if (
                        dbl_state["serviceId"] == service["id"]
                        and dbl_state["index"] == dbl_target
                        and dbl_state["openCalls"] == 0
                        and dbl_state["hasWindowRef"]
                    ):
                        pass_("presenter-doubleclick-live-jumps", json.dumps(dbl_state, ensure_ascii=False))
                    else:
                        fail("presenter-doubleclick-live-jumps", json.dumps(dbl_state, ensure_ascii=False))
                    page.wait_for_timeout(120)
                    sidebar_preview_scale_state = page.evaluate(
                        """
                        (() => {
                          const preview = document.querySelector('.svc-presenter-side-panel .svc-presenter-live-preview');
                          const output = preview?.querySelector('.svc-slide-mini-output');
                          const canvas = preview?.querySelector('.svc-slide-mini-canvas.presenter-output-root');
                          const previewRect = preview?.getBoundingClientRect();
                          const outputRect = output?.getBoundingClientRect();
                          const canvasRect = canvas?.getBoundingClientRect();
                          const scale = Number(canvas?.style.getPropertyValue('--presenter-preview-scale')) || 0;
                          return {
                            hasPreview: Boolean(preview),
                            hasOutput: Boolean(output),
                            hasCanvas: Boolean(canvas),
                            outputWidth: Math.round(outputRect?.width || 0),
                            outputHeight: Math.round(outputRect?.height || 0),
                            canvasCssWidth: Math.round(Number.parseFloat(getComputedStyle(canvas || document.body).width) || 0),
                            canvasCssHeight: Math.round(Number.parseFloat(getComputedStyle(canvas || document.body).height) || 0),
                            visualWidth: Math.round(canvasRect?.width || 0),
                            visualHeight: Math.round(canvasRect?.height || 0),
                            previewRatio: previewRect?.height ? Number((previewRect.width / previewRect.height).toFixed(3)) : 0,
                            visualRatio: canvasRect?.height ? Number((canvasRect.width / canvasRect.height).toFixed(3)) : 0,
                            scale,
                          };
                        })()
                        """
                    )
                    if (
                        sidebar_preview_scale_state["hasPreview"]
                        and sidebar_preview_scale_state["hasOutput"]
                        and sidebar_preview_scale_state["hasCanvas"]
                        and sidebar_preview_scale_state["canvasCssWidth"] == 1920
                        and sidebar_preview_scale_state["canvasCssHeight"] == 1080
                        and 0 <= sidebar_preview_scale_state["outputWidth"] - sidebar_preview_scale_state["visualWidth"] <= 5
                        and 0 <= sidebar_preview_scale_state["outputHeight"] - sidebar_preview_scale_state["visualHeight"] <= 5
                        and 1.75 <= sidebar_preview_scale_state["previewRatio"] <= 1.79
                        and 1.75 <= sidebar_preview_scale_state["visualRatio"] <= 1.79
                        and sidebar_preview_scale_state["scale"] > 0
                    ):
                        pass_("presenter-sidebar-live-preview-scale", json.dumps(sidebar_preview_scale_state, ensure_ascii=False))
                    else:
                        fail("presenter-sidebar-live-preview-scale", json.dumps(sidebar_preview_scale_state, ensure_ascii=False))
                    page.evaluate(
                        """
                        (serviceId) => {
                          state.presenter.outputWindow = null;
                          state.presenter.outputConnectedAt = 0;
                          state.presenter.outputClientId = "";
                          stopPresenterOutputWindowMonitor();
                          preparePresenterService(serviceId);
                          state.presenter.index = 0;
                          renderPresenterControlState(serviceId);
                          publishPresenterState({ force: true });
                        }
                        """,
                        service["id"],
                    )

                overflow_state: dict[str, Any] = page.evaluate(
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
                overflow = max(
                    overflow_state["documentScrollWidth"] - overflow_state["viewport"],
                    overflow_state["bodyScrollWidth"] - overflow_state["viewport"],
                    overflow_state["boardScrollWidth"] - overflow_state["boardClientWidth"],
                )
                if overflow <= 2:
                    pass_("presenter-horizontal-overflow", json.dumps(overflow_state, ensure_ascii=False))
                else:
                    fail("presenter-horizontal-overflow", json.dumps(overflow_state, ensure_ascii=False))

                responsive_control_states = []
                for width in [1180, 900, 760, 620, 520, 390]:
                    page.set_viewport_size({"width": width, "height": 820})
                    page.wait_for_timeout(80)
                    responsive_control_states.append(page.evaluate(
                        """
                        () => {
                          const rect = (node) => {
                            const r = node?.getBoundingClientRect();
                            return r ? {
                              x: Math.round(r.x),
                              y: Math.round(r.y),
                              right: Math.round(r.right),
                              bottom: Math.round(r.bottom),
                              width: Math.round(r.width),
                              height: Math.round(r.height),
                            } : null;
                          };
                          const top = document.querySelector('.svc-presenter-top');
                          const boxes = [...(top?.children || [])].map(rect).filter(Boolean);
                          let overlaps = 0;
                          for (let i = 0; i < boxes.length; i += 1) {
                            for (let j = i + 1; j < boxes.length; j += 1) {
                              const a = boxes[i];
                              const b = boxes[j];
                              if (!(a.right <= b.x || b.right <= a.x || a.bottom <= b.y || b.bottom <= a.y)) overlaps += 1;
                            }
                          }
                          return {
                            width: window.innerWidth,
                            top: rect(top),
                            overlaps,
                            overflow: Math.max(document.documentElement.scrollWidth - window.innerWidth, document.body.scrollWidth - window.innerWidth),
                          };
                        }
                        """
                    ))
                page.set_viewport_size({"width": 1440, "height": 980})
                page.wait_for_timeout(80)
                if all(item["overlaps"] == 0 and item["overflow"] <= 2 for item in responsive_control_states):
                    pass_("presenter-responsive-controls", json.dumps(responsive_control_states, ensure_ascii=False))
                else:
                    fail("presenter-responsive-controls", json.dumps(responsive_control_states, ensure_ascii=False))

                payload = page.evaluate(
                    """
                    (serviceId) => {
                      preparePresenterService(serviceId);
                      state.presenter.index = Math.min(1, Math.max(state.presenter.slides.length - 1, 0));
                      state.presenter.liveScripture = { reference: "", draft: "", active: false, slide: null };
                      state.presenter.livePraise = { query: "", draft: "", active: false, slides: [], index: 0, songId: "", versionId: "" };
                      state.presenter.outputWindow = null;
                      state.presenter.outputConnectedAt = 0;
                      state.presenter.outputClientId = "";
                      stopPresenterOutputWindowMonitor();
                      renderPresenterControlState(serviceId);
                      publishPresenterState({ force: true });
                      return presenterStatePayload(serviceId);
                    }
                    """,
                    service["id"],
                )
                output_page = context.new_page()
                output_page.set_viewport_size({"width": 1280, "height": 800})
                output_page.on("pageerror", lambda error: page_errors.append(f"output: {error}"))
                output_page.on("response", lambda response: record_response(response, "output"))
                output_page.on(
                    "console",
                    lambda msg: console_messages.append(f"output {msg.type}: {msg.text}")
                    if msg.type in ("error", "warning")
                    else None,
                )
                output_page.goto(presenter_output_url(app_url), wait_until="load")
                output_page.wait_for_selector("#presenterOutputRoot", timeout=5000)
                output_page.wait_for_function(
                    "(serviceId) => (readPresenterStoredPayload() || {}).serviceId === serviceId",
                    arg=service["id"],
                    timeout=5000,
                )
                fixed_stage_state = []
                for viewport in ({"width": 1920, "height": 1080}, {"width": 2560, "height": 1440}, {"width": 1280, "height": 800}):
                    output_page.set_viewport_size(viewport)
                    output_page.wait_for_timeout(80)
                    fixed_stage_state.append(output_page.evaluate(
                        """
                        (viewport) => {
                          renderPresenterOutput({
                            serviceId: '__smoke_fixed_stage__',
                            serviceType: 'friday',
                            chromakey: true,
                            outputTheme: 'chromakey',
                            backgroundImage: '',
                            slides: [{
                              id: '__smoke_fixed_stage_slide__',
                              type: 'lyrics',
                              elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
                              layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                              text: '내가 보는 화면 그대로\\n예배에서도 보이게',
                            }],
                            index: 0,
                            safetyBlank: false,
                          });
                          const root = document.getElementById('presenterOutputRoot');
                          const text = root.querySelector('.presenter-slide-text');
                          const rootRect = root.getBoundingClientRect();
                          const textRect = text.getBoundingClientRect();
                          const style = getComputedStyle(text);
                          return {
                            viewport,
                            offsetWidth: root.offsetWidth,
                            offsetHeight: root.offsetHeight,
                            visualWidth: Math.round(rootRect.width),
                            visualHeight: Math.round(rootRect.height),
                            fontSize: style.fontSize,
                            lineHeight: style.lineHeight,
                            textVisualHeight: Math.round(textRect.height),
                          };
                        }
                        """,
                        viewport,
                    ))
                if (
	                    [item["offsetWidth"] for item in fixed_stage_state] == [1920, 2560, 1280]
	                    and [item["offsetHeight"] for item in fixed_stage_state] == [1080, 1440, 720]
	                    and [item["visualWidth"] for item in fixed_stage_state] == [1920, 2560, 1280]
	                    and [item["visualHeight"] for item in fixed_stage_state] == [1080, 1440, 720]
                    and max(float(item["fontSize"].replace("px", "")) / item["visualWidth"] for item in fixed_stage_state)
                        - min(float(item["fontSize"].replace("px", "")) / item["visualWidth"] for item in fixed_stage_state) < 0.0001
                    and max(float(item["lineHeight"].replace("px", "")) / item["visualWidth"] for item in fixed_stage_state)
                        - min(float(item["lineHeight"].replace("px", "")) / item["visualWidth"] for item in fixed_stage_state) < 0.0001
                ):
                    pass_("presenter-output-design-stage-contain-font-size", json.dumps(fixed_stage_state, ensure_ascii=False))
                else:
                    fail("presenter-output-design-stage-contain-font-size", json.dumps(fixed_stage_state, ensure_ascii=False))
                output_page.set_viewport_size({"width": 1920, "height": 1080})
                output_page.wait_for_timeout(80)
                page.wait_for_function(
                    "() => state.presenter.outputConnectedAt > 0 && isPresenterOutputWindowOpen()",
                    timeout=10000,
                )
                page.mouse.move(0, 0)
                page.evaluate("(serviceId) => renderPresenterControlState(serviceId)", service["id"])
                page.wait_for_function(
                    "() => document.querySelector('.svc-presenter-status')?.textContent.trim() === '송출 중'",
                    timeout=5000,
                )
                heartbeat_state = page.evaluate(
                    """
                    (() => ({
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                      connected: state.presenter.outputConnectedAt > 0,
                      open: isPresenterOutputWindowOpen(),
                      hasWindowRef: Boolean(state.presenter.outputWindow),
                    }))()
                    """
                )
                if (
                    heartbeat_state["status"] == "송출 중"
                    and heartbeat_state["mode"] == "2번"
                    and heartbeat_state["connected"]
                    and heartbeat_state["open"]
                    and not heartbeat_state["hasWindowRef"]
                ):
                    pass_("presenter-output-heartbeat-direct-route", json.dumps(heartbeat_state, ensure_ascii=False))
                else:
                    fail("presenter-output-heartbeat-direct-route", json.dumps(heartbeat_state, ensure_ascii=False))

                output_fullscreen_key_state = output_page.evaluate(
                    """
                    async () => {
                      let requestCalls = 0;
                      const originalRequestFullscreen = document.documentElement.requestFullscreen;
                      document.documentElement.requestFullscreen = () => {
                        requestCalls += 1;
                        return Promise.resolve();
                      };
                      const before = (readPresenterStoredPayload() || {}).index;
                      const fEvent = new KeyboardEvent('keydown', { key: 'f', bubbles: true, cancelable: true });
                      const fDispatched = window.dispatchEvent(fEvent);
                      await new Promise((resolve) => setTimeout(resolve, 80));
                      window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }));
                      await new Promise((resolve) => setTimeout(resolve, 80));
                      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                      await new Promise((resolve) => setTimeout(resolve, 80));
                      const after = (readPresenterStoredPayload() || {}).index;
                      document.documentElement.requestFullscreen = originalRequestFullscreen;
                      return { requestCalls, before, after, fPrevented: !fDispatched || fEvent.defaultPrevented };
                    }
                    """
                )
                if (
                    output_fullscreen_key_state["requestCalls"] == 0
                    and output_fullscreen_key_state["fPrevented"]
                    and output_fullscreen_key_state["after"] > output_fullscreen_key_state["before"]
                ):
                    pass_("presenter-output-enter-space-fullscreen", json.dumps(output_fullscreen_key_state, ensure_ascii=False))
                else:
                    fail("presenter-output-enter-space-fullscreen", json.dumps(output_fullscreen_key_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (() => {
                      window.__mindexPresenterOpenCalls = 0;
                      window.open = () => {
                        window.__mindexPresenterOpenCalls += 1;
                        return null;
                      };
                    })()
                    """
                )
                heartbeat_stop_state = page.evaluate(
                    """
                    (() => ({
                      openCalls: window.__mindexPresenterOpenCalls || 0,
                      connected: state.presenter.outputConnectedAt > 0,
                      open: isPresenterOutputWindowOpen(),
                      hasWindowRef: Boolean(state.presenter.outputWindow),
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      action: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch')?.dataset.presenterAction || '',
                      label: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch span')?.textContent.trim() || '',
                      icon: document.querySelector('.svc-presenter-side-panel .svc-presenter-launch svg')?.getAttribute('data-lucide') || '',
                    }))()
                    """
                )
                if (
                    heartbeat_stop_state["openCalls"] == 0
                    and heartbeat_stop_state["connected"]
                    and heartbeat_stop_state["open"]
                    and not heartbeat_stop_state["hasWindowRef"]
                    and heartbeat_stop_state["status"] == "송출 중"
                    and heartbeat_stop_state["action"] == "stop"
                    and heartbeat_stop_state["label"] == "송출 종료"
                    and heartbeat_stop_state["icon"] == "screen-share-off"
                ):
                    pass_("presenter-heartbeat-output-stop-affordance", json.dumps(heartbeat_stop_state, ensure_ascii=False))
                else:
                    fail("presenter-heartbeat-output-stop-affordance", json.dumps(heartbeat_stop_state, ensure_ascii=False))

                blocked_popup_state = page.evaluate(
                    """
                    async (serviceId) => {
                      const originalOpen = window.open;
                      const originalHydrate = hydratePresenterServiceData;
                      window.__mindexPresenterOpenCalls = 0;
                      let hydrateCalls = 0;
                      state.presenter.outputWindow = null;
                      state.presenter.outputConnectedAt = 0;
                      state.presenter.outputClientId = "";
                      state.presenter.outputStopAt = 0;
                      stopPresenterOutputWindowMonitor();
                      window.open = () => {
                        window.__mindexPresenterOpenCalls += 1;
                        return null;
                      };
                      hydratePresenterServiceData = async (...args) => {
                        hydrateCalls += 1;
                        return originalHydrate(...args);
                      };
                      await openPresenterOutput(serviceId);
                      window.open = originalOpen;
                      hydratePresenterServiceData = originalHydrate;
                      return {
                        openCalls: window.__mindexPresenterOpenCalls || 0,
                        hydrateCalls,
                        connected: state.presenter.outputConnectedAt > 0,
                        pending: state.presenter.outputPendingAt > 0,
                        blocked: state.presenter.outputBlockedAt > 0,
                        attemptServiceId: state.presenter.outputAttemptServiceId,
                        open: isPresenterOutputWindowOpen(),
                        hasWindowRef: Boolean(state.presenter.outputWindow),
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      };
                    }
                    """,
                    service["id"],
                )
                if (
                    blocked_popup_state["openCalls"] == 1
                    and blocked_popup_state["hydrateCalls"] == 0
                    and not blocked_popup_state["connected"]
                    and not blocked_popup_state["pending"]
                    and blocked_popup_state["blocked"]
                    and blocked_popup_state["attemptServiceId"] == service["id"]
                    and not blocked_popup_state["open"]
                    and not blocked_popup_state["hasWindowRef"]
                    and blocked_popup_state["status"] == "창 열기 실패"
                ):
                    pass_("presenter-popup-block-skips-hydrate", json.dumps(blocked_popup_state, ensure_ascii=False))
                else:
                    fail("presenter-popup-block-skips-hydrate", json.dumps(blocked_popup_state, ensure_ascii=False))

                payload = page.evaluate(
                    """
                    (serviceId) => {
                      const songTitleIndex = state.presenter.slides.findIndex((slide) => slide.type === 'song-title');
                      state.presenter.index = songTitleIndex >= 0
                        ? songTitleIndex
                        : Math.min(2, Math.max(state.presenter.slides.length - 1, 0));
                      state.presenter.safetyBlank = false;
                      renderPresenterControlState(serviceId);
                      publishPresenterState({ force: true });
                      return presenterStatePayload(serviceId);
                    }
                    """,
                    service["id"],
                )
                output_page.wait_for_function(
                    "(expectedIndex) => (readPresenterStoredPayload() || {}).index === expectedIndex",
                    arg=payload["index"],
                    timeout=5000,
                )

                output_state = output_page.evaluate(
                    """
                    (() => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slide = root?.querySelector('.presenter-slide');
                      const text = slide?.innerText.trim() || '';
                      const styles = root ? getComputedStyle(root) : null;
                      const rect = root?.getBoundingClientRect();
                      const textRect = slide?.querySelector('.presenter-slide-text')?.getBoundingClientRect();
                      return {
                        serviceType: root?.dataset.serviceType || '',
                        outputTheme: root?.dataset.outputTheme || '',
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        hasBackground: root?.classList.contains('has-background') || false,
                        slideClass: slide ? [...slide.classList].find((name) => name.startsWith('presenter-slide--') && name !== 'presenter-slide') : '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        backgroundColor: styles?.backgroundColor || '',
                        documentTitle: document.title,
                        text,
                        viewport: { width: window.innerWidth, height: window.innerHeight },
                        frame: rect ? {
                          width: Math.round(rect.width),
                          height: Math.round(rect.height),
                          ratio: rect.height ? Number((rect.width / rect.height).toFixed(3)) : 0,
                        } : null,
                        lowerBarRatio: rect && textRect ? Number((textRect.height / rect.height).toFixed(3)) : 0,
                        overflow: Math.max(
                          document.documentElement.scrollWidth - window.innerWidth,
                          document.documentElement.scrollHeight - window.innerHeight,
                          document.body.scrollWidth - window.innerWidth,
                          document.body.scrollHeight - window.innerHeight
                        ),
                      };
                    })()
                    """
                )
                if (
                    output_state["serviceType"] == payload["serviceType"]
                    and output_state["outputTheme"] == payload["outputTheme"]
                    and output_state["noChromakey"] is False
                    and output_state["slideClass"]
                    and output_state["elementType"]
                    and output_state["layout"]
                    and "송출" not in output_state["documentTitle"]
                    and output_state["documentTitle"]
                    and (
                        output_state["slideClass"] != "presenter-slide--song-title"
                        or output_state["text"].startswith("♬ ")
                        or output_state["text"].endswith("입력 필요")
                    )
                    and output_state["frame"]["width"] == 1920
                    and output_state["frame"]["height"] == 1080
                    and abs(output_state["frame"]["ratio"] - (16 / 9)) <= 0.01
                    and abs(output_state["lowerBarRatio"] - 0.18) <= 0.01
                    and output_state["overflow"] <= 2
                ):
                    pass_("presenter-output-route", json.dumps(output_state, ensure_ascii=False))
                else:
                    fail("presenter-output-route", json.dumps({"payload": payload, "output": output_state}, ensure_ascii=False))

                preview_state = page.evaluate(
                    """
                    (() => {
                      const thumb = document.querySelector('.svc-slide-thumb.active .svc-slide-mini-output')
                        || document.querySelector(`.svc-slide-thumb[data-presenter-index="${state.presenter.index}"] .svc-slide-mini-output`);
                      const slide = thumb?.querySelector('.presenter-slide');
                      const canvas = thumb?.querySelector('.svc-slide-mini-canvas.presenter-output-root');
                      const boardColumnChildren = [...document.querySelectorAll('.svc-presenter-board-column > *')]
                        .map((node) => [...node.classList].join(' '));
                      const slideText = canvas?.querySelector('.presenter-slide-text');
                      const textStyle = slideText ? getComputedStyle(slideText) : null;
                      const text = thumb?.innerText.trim() || '';
                      return {
                        hasSharedFrame: Boolean(slide && canvas),
                        boardColumnChildren,
                        slideClass: slide ? [...slide.classList].find((name) => name.startsWith('presenter-slide--') && name !== 'presenter-slide') : '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        designFrame: canvas ? {
                          width: canvas.offsetWidth,
                          height: canvas.offsetHeight,
                        } : null,
                        fontSize: textStyle?.fontSize || '',
                        text,
                      };
                    })()
                    """
                )
                if (
                    preview_state["hasSharedFrame"]
                    and preview_state["boardColumnChildren"] == ["svc-slide-board svc-slide-board--chromakey"]
                    and preview_state["slideClass"] == output_state["slideClass"]
                    and preview_state["elementType"] == output_state["elementType"]
                    and preview_state["layout"] == output_state["layout"]
                    and preview_state.get("designFrame", {}).get("width") == 1920
                    and preview_state.get("designFrame", {}).get("height") == 1080
                    and preview_state["fontSize"].endswith("px")
                    and (output_state["text"] in preview_state["text"] or preview_state["text"] in output_state["text"])
                ):
                    pass_("presenter-controller-preview-shared-frame", json.dumps(preview_state, ensure_ascii=False))
                else:
                    fail("presenter-controller-preview-shared-frame", json.dumps({"output": output_state, "preview": preview_state}, ensure_ascii=False))

                preview_renderer_state = page.evaluate(
                    """
                    (() => {
                      const video = {
                        id: '__smoke_preview_video__',
                        elementType: PRESENTER_ELEMENT_TYPES.VIDEO,
                        layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                        type: 'video',
                        title: '영상',
                        videoSrc: 'assets/presenter/chromakey-ready-loop-fast.mp4',
                        outputContext: 'clean',
                      };
                      const audio = {
                        id: '__smoke_preview_audio__',
                        elementType: PRESENTER_ELEMENT_TYPES.AUDIO,
                        layout: PRESENTER_SLIDE_LAYOUTS.FILE,
                        type: 'audio',
                        title: '오디오',
                        audioSrc: 'assets/audio/choir.m4a',
                        outputContext: 'clean',
                      };
                      const videoPreview = renderPresenterSlideMiniPreview(video);
                      const audioPreview = renderPresenterSlideMiniPreview(audio);
                      const waitingLoop = {
                        id: '__smoke_preview_waiting_loop__',
                        elementType: PRESENTER_ELEMENT_TYPES.VIDEO,
                        layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                        type: 'ready',
                        title: '예배 전 영상',
                        videoSrc: 'assets/presenter/chromakey-ready-loop-fast.mp4',
                        presenterRole: 'waiting_loop',
                        outputContext: 'chromakey',
                      };
                      const waitingPreview = renderPresenterSlideMiniPreview(waitingLoop);
                      const waitingMount = document.createElement('div');
                      waitingMount.innerHTML = waitingPreview;
                      document.body.appendChild(waitingMount);
                      const waitingVideo = waitingMount.querySelector('video.presenter-video');
                      const videoMount = document.createElement('div');
                      videoMount.innerHTML = videoPreview;
                      const videoOutput = videoMount.querySelector('video.presenter-video');
                      const waitingObjectFit = waitingVideo ? getComputedStyle(waitingVideo).objectFit : '';
                      waitingMount.remove();
                      return {
                        videoUsesOutputElement: videoPreview.includes('<video'),
                        videoUsesMetadataPreload: videoPreview.includes('preload="metadata"'),
                        videoUsesFirstFrameOffset: videoPreview.includes('#t=0.001'),
                        videoMuted: videoPreview.includes('muted'),
                        videoAutoplay: Boolean(videoOutput?.autoplay),
                        videoLoop: Boolean(videoOutput?.loop),
                        videoUsesPlaceholder: videoPreview.includes('presenter-slide-file'),
                        videoUsesStaticPreview: videoPreview.includes('presenter-static-media-preview'),
                        videoElementCount: videoMount.querySelectorAll('video').length,
                        waitingUsesOutputElement: Boolean(waitingVideo),
                        waitingUsesStaticPreview: waitingPreview.includes('presenter-static-media-preview'),
                        waitingUsesMetadataPreload: waitingPreview.includes('preload="metadata"'),
                        waitingUsesFirstFrameOffset: waitingPreview.includes('#t=0.001'),
                        waitingAutoplay: Boolean(waitingVideo?.autoplay),
                        waitingMuted: Boolean(waitingVideo?.muted),
                        waitingLoop: Boolean(waitingVideo?.loop),
                        waitingObjectFit,
                        audioUsesPlaceholder: audioPreview.includes('presenter-slide-file'),
                      };
                    })()
                    """
                )
                if (
                    preview_renderer_state["videoUsesOutputElement"]
                    and preview_renderer_state["videoUsesMetadataPreload"]
                    and preview_renderer_state["videoUsesFirstFrameOffset"]
                    and preview_renderer_state["videoMuted"]
                    and not preview_renderer_state["videoAutoplay"]
                    and not preview_renderer_state["videoLoop"]
                    and not preview_renderer_state["videoUsesPlaceholder"]
                    and not preview_renderer_state["videoUsesStaticPreview"]
                    and preview_renderer_state["videoElementCount"] == 1
                    and preview_renderer_state["waitingUsesOutputElement"]
                    and not preview_renderer_state["waitingUsesStaticPreview"]
                    and preview_renderer_state["waitingUsesMetadataPreload"]
                    and preview_renderer_state["waitingUsesFirstFrameOffset"]
                    and not preview_renderer_state["waitingAutoplay"]
                    and preview_renderer_state["waitingMuted"]
                    and not preview_renderer_state["waitingLoop"]
                    and preview_renderer_state["waitingObjectFit"] == "contain"
                    and not preview_renderer_state["audioUsesPlaceholder"]
                ):
                    pass_("presenter-preview-uses-video-first-frame", json.dumps(preview_renderer_state, ensure_ascii=False))
                else:
                    fail("presenter-preview-uses-video-first-frame", json.dumps(preview_renderer_state, ensure_ascii=False))

                video_paint_guard_state = page.evaluate(
                    """
                    (() => {
                      const source = [
                        String(preparePresenterOutputFrameForPaint),
                        String(preparePresenterOutputVideoForPaint),
                      ].join('\\n');
                      return {
                        frameWaitsForVideo: source.includes('video.presenter-video')
                          && source.includes('preparePresenterOutputVideoForPaint'),
                        waitsForFirstFrame: source.includes('HAVE_CURRENT_DATA')
                          && source.includes('loadeddata')
                          && source.includes('canplay'),
                        retriesAutoplay: source.includes('video.play')
                          && source.includes('playPromise.catch'),
                        preservesAudibleAutoplay: source.includes('!video.muted && !video.defaultMuted && !video.hasAttribute("muted")'),
                        forcesSafariMutedInline: source.includes('video.defaultMuted = true')
                          && source.includes('video.muted = true')
                          && source.includes('webkit-playsinline'),
                        hasTimeoutFallback: source.includes('setTimeout')
                          && source.includes('1500'),
                      };
                    })()
                    """
                )
                if (
                    video_paint_guard_state["frameWaitsForVideo"]
                    and video_paint_guard_state["waitsForFirstFrame"]
                    and video_paint_guard_state["retriesAutoplay"]
                    and video_paint_guard_state["preservesAudibleAutoplay"]
                    and video_paint_guard_state["forcesSafariMutedInline"]
                    and video_paint_guard_state["hasTimeoutFallback"]
                ):
                    pass_("presenter-output-video-paint-guard", json.dumps(video_paint_guard_state, ensure_ascii=False))
                else:
                    fail("presenter-output-video-paint-guard", json.dumps(video_paint_guard_state, ensure_ascii=False))

                output_viewport_shot = output_page.screenshot()
                fixed_viewport_pixels = {
                    "top": rgb_at(output_viewport_shot, 0.5, 0.01),
                    "bottom": rgb_at(output_viewport_shot, 0.5, 0.99),
                }
                if (
                    is_chromakey_green(fixed_viewport_pixels["top"])
                    and is_dark_bar(fixed_viewport_pixels["bottom"])
                ):
                    pass_("presenter-output-fixed-viewport-fill", json.dumps(fixed_viewport_pixels, ensure_ascii=False))
                else:
                    fail("presenter-output-fixed-viewport-fill", json.dumps(fixed_viewport_pixels, ensure_ascii=False))

                current_presenter_index = page.evaluate("state.presenter.index")
                page.wait_for_function(
                    "(index) => Boolean(document.querySelector(`.svc-slide-thumb[data-presenter-index=\"${index}\"] .svc-slide-mini-output`))",
                    arg=current_presenter_index,
                    timeout=5000,
                )
                page.wait_for_timeout(250)
                thumb_shot = screenshot_with_retry(page, page.locator(f'.svc-slide-thumb[data-presenter-index="{current_presenter_index}"] .svc-slide-mini-output').first)
                thumb_frame_shot = screenshot_with_retry(page, page.locator(f'.svc-slide-thumb[data-presenter-index="{current_presenter_index}"] .svc-slide-thumb-frame').first)
                output_shot = output_page.locator("#presenterOutputRoot").screenshot()
                thumb_host_state = page.evaluate(
                    """
                    (index) => {
                      const host = document.querySelector(`.svc-slide-thumb[data-presenter-index="${index}"] .svc-slide-mini-output`);
                      const frame = document.querySelector(`.svc-slide-thumb[data-presenter-index="${index}"] .svc-slide-thumb-frame`);
                      return {
                        hostBackground: host ? getComputedStyle(host).backgroundColor : "",
                        frameBackground: frame ? getComputedStyle(frame).backgroundColor : "",
                      };
                    }
                    """,
                    current_presenter_index,
                )
                chromakey_pixels = {
                    "thumbTop": rgb_at(thumb_shot, 0.5, 0.2),
                    "thumbBar": rgb_at(thumb_shot, 0.02, 0.92),
                    "thumbFrameBottomLeft": rgb_at(thumb_frame_shot, 0.025, 0.96),
                    "thumbFrameBottomRight": rgb_at(thumb_frame_shot, 0.975, 0.96),
                    "thumbHostBackground": thumb_host_state["hostBackground"],
                    "thumbFrameBackground": thumb_host_state["frameBackground"],
                    "outputTop": rgb_at(output_shot, 0.5, 0.2),
                    "outputBar": rgb_at(output_shot, 0.02, 0.92),
                }
                if (
                    is_chromakey_green(chromakey_pixels["thumbTop"])
                    and is_chromakey_green(chromakey_pixels["outputTop"])
                    and chromakey_pixels["thumbHostBackground"] == "rgba(0, 0, 0, 0)"
                    and is_dark_bar(chromakey_pixels["thumbBar"])
                    and is_dark_bar(chromakey_pixels["thumbFrameBottomLeft"])
                    and is_dark_bar(chromakey_pixels["thumbFrameBottomRight"])
                    and is_dark_bar(chromakey_pixels["outputBar"])
                ):
                    pass_("presenter-output-pixel-match-chromakey", json.dumps(chromakey_pixels, ensure_ascii=False))
                else:
                    fail("presenter-output-pixel-match-chromakey", json.dumps(chromakey_pixels, ensure_ascii=False))

                image_swap_state = output_page.evaluate(
                    """
                    async () => {
                      const root = document.getElementById('presenterOutputRoot');
                      const src = normalizePresenterMediaSource('assets/worship-backgrounds/26-A1.png');
                      let resolveReady;
                      const pending = new Promise((resolve) => { resolveReady = resolve; });
                      presenterOutputImagePreloadCache.clear();
                      presenterOutputImagePreloadCache.set(src, {
                        image: { complete: false, naturalWidth: 0 },
                        promise: pending,
                        lastUsed: Date.now(),
                        ready: false,
                      });
                      root.innerHTML = '<section class="presenter-slide presenter-slide--lyrics" data-element-type="praise" data-slide-layout="lower_bar_text"><div class="presenter-slide-text"><span>OLD FRAME</span></div></section>';
                      renderPresenterOutput({
                        serviceId: '__smoke_image_wait__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_image_slide__',
                          type: 'image',
                          elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
                          layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
                          imageSrc: src,
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const before = {
                        busy: root.getAttribute('aria-busy'),
                        oldVisible: root.querySelector('.presenter-output-layer.is-active')?.innerText.includes('OLD FRAME') || root.innerText.includes('OLD FRAME'),
                        activeHasImage: Boolean(root.querySelector('.presenter-output-layer.is-active img.presenter-image')),
                        nextHasImage: Boolean(root.querySelector('.presenter-output-layer:not(.is-active) img.presenter-image')),
                      };
                      const record = presenterOutputImagePreloadCache.get(src);
                      record.ready = true;
                      resolveReady();
                      await new Promise((resolve) => {
                        const start = Date.now();
                        const tick = () => {
                          const imageReady = !root.getAttribute('aria-busy')
                            && root.querySelector('.presenter-output-layer.is-active img.presenter-image');
                          if (imageReady || Date.now() - start > 3000) resolve();
                          else requestAnimationFrame(tick);
                        };
                        tick();
                      });
                      const after = {
                        busy: root.getAttribute('aria-busy'),
                        oldVisible: root.querySelector('.presenter-output-layer.is-active')?.innerText.includes('OLD FRAME') || false,
                        activeHasImage: Boolean(root.querySelector('.presenter-output-layer.is-active img.presenter-image')),
                        source: root.querySelector('.presenter-output-layer.is-active img.presenter-image')?.getAttribute('src') || '',
                      };
                      return { before, after };
                    }
                    """
                )
                if (
                    image_swap_state["before"]["busy"] == "true"
                    and image_swap_state["before"]["oldVisible"]
                    and not image_swap_state["before"]["activeHasImage"]
                    and image_swap_state["after"]["busy"] is None
                    and not image_swap_state["after"]["oldVisible"]
                    and image_swap_state["after"]["activeHasImage"]
                    and "26-A1.png" in image_swap_state["after"]["source"]
                ):
                    pass_("presenter-output-image-ready-swap", json.dumps(image_swap_state, ensure_ascii=False))
                else:
                    fail("presenter-output-image-ready-swap", json.dumps(image_swap_state, ensure_ascii=False))

                title_assignee_bounds = output_page.evaluate(
                    """
                    () => {
                      renderPresenterOutput({
                        serviceId: '__smoke_title_assignee_bounds__',
                        serviceType: 'friday',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_long_title_assignee__',
                          type: 'title-assignee',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          title: '성경봉독과 공동기도를 위한 안내',
                          assignee: '김남영 담임목사 외 공동집례자',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const bar = root.querySelector('.presenter-title-assignee');
                      const title = root.querySelector('.presenter-title-assignee-title');
                      const person = root.querySelector('.presenter-title-assignee-person');
                      const rect = (node) => {
                        const r = node.getBoundingClientRect();
                        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
                      };
                      const rootRect = rect(root);
                      const barRect = rect(bar);
                      const titleRect = rect(title);
                      const personRect = rect(person);
                      const titleStyle = getComputedStyle(title);
                      const personStyle = getComputedStyle(person);
                      const twoPart = {
                        text: root.innerText,
                        titleOverflow: titleStyle.textOverflow,
                        personOverflow: personStyle.textOverflow,
                        titleFontSize: Number.parseFloat(titleStyle.fontSize),
                        titleFontWeight: titleStyle.fontWeight,
                        personFontSize: Number.parseFloat(personStyle.fontSize),
                        personFontWeight: personStyle.fontWeight,
                        titleInside: titleRect.left >= rootRect.left - 1 && titleRect.right <= rootRect.right + 1,
                        personInside: personRect.left >= rootRect.left - 1 && personRect.right <= rootRect.right + 1,
                        noOverlap: titleRect.bottom <= personRect.top + 1 || personRect.bottom <= titleRect.top + 1,
                        titleCentered: Math.abs(((rootRect.left + rootRect.right) / 2) - ((titleRect.left + titleRect.right) / 2)) < 2,
                      };
                      renderPresenterOutput({
                        serviceId: '__smoke_title_assignee_three_part__',
                        serviceType: 'friday',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_three_part_title_assignee__',
                          type: 'title-assignee',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          orderTitle: '순서',
                          contentTitle: '모든 것 되신 예수',
                          assignee: '김광한 전도사',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const order = root.querySelector('.presenter-title-assignee-order');
                      const content = root.querySelector('.presenter-title-assignee-content');
                      const threePerson = root.querySelector('.presenter-title-assignee-person');
                      return {
                        text: twoPart.text,
                        titleOverflow: twoPart.titleOverflow,
                        personOverflow: twoPart.personOverflow,
                        titleFontSize: twoPart.titleFontSize,
                        titleFontWeight: twoPart.titleFontWeight,
                        personFontSize: twoPart.personFontSize,
                        personFontWeight: twoPart.personFontWeight,
                        orderFontSize: Number.parseFloat(getComputedStyle(order).fontSize),
                        orderFontWeight: getComputedStyle(order).fontWeight,
                        contentFontSize: Number.parseFloat(getComputedStyle(content).fontSize),
                        contentFontWeight: getComputedStyle(content).fontWeight,
                        threePartPersonFontSize: Number.parseFloat(getComputedStyle(threePerson).fontSize),
                        threePartPersonFontWeight: getComputedStyle(threePerson).fontWeight,
                        titleInside: twoPart.titleInside,
                        personInside: twoPart.personInside,
                        noOverlap: twoPart.noOverlap,
                        titleCentered: twoPart.titleCentered,
                      };
                    }
                    """
                )
                if (
                    "성경봉독과 공동기도를 위한 안내" in title_assignee_bounds["text"]
                    and "김남영 담임목사 외 공동집례자" in title_assignee_bounds["text"]
                    and title_assignee_bounds["titleOverflow"] == "clip"
                    and title_assignee_bounds["personOverflow"] == "clip"
                    and title_assignee_bounds["titleFontSize"] == 90
                    and title_assignee_bounds["titleFontWeight"] == "800"
                    and title_assignee_bounds["personFontSize"] == 70
                    and title_assignee_bounds["personFontWeight"] == "600"
                    and title_assignee_bounds["orderFontSize"] == 90
                    and title_assignee_bounds["orderFontWeight"] == "800"
                    and title_assignee_bounds["contentFontSize"] == 70
                    and title_assignee_bounds["contentFontWeight"] == "600"
                    and title_assignee_bounds["threePartPersonFontSize"] == 70
                    and title_assignee_bounds["threePartPersonFontWeight"] == "600"
                    and title_assignee_bounds["titleInside"]
                    and title_assignee_bounds["personInside"]
                    and not title_assignee_bounds["titleCentered"]
                ):
                    pass_("presenter-title-assignee-long-fit", json.dumps(title_assignee_bounds, ensure_ascii=False))
                else:
                    fail("presenter-title-assignee-long-fit", json.dumps(title_assignee_bounds, ensure_ascii=False))

                sermon_title_font_state = output_page.evaluate(
                    """
                    () => {
                      renderPresenterOutput({
                        serviceId: '__smoke_sermon_title_font__',
                        serviceType: 'sunday2',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_sermon_title_font_slide__',
                          type: 'title-assignee',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          title: '베드로의 고백',
                          orderTitle: '설교',
                          contentTitle: '베드로의 고백',
                          assignee: '김남영 목사',
                          text: '설교\\n베드로의 고백\\n김남영 목사',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const order = root.querySelector('.presenter-title-assignee-order');
                      const content = root.querySelector('.presenter-title-assignee-content');
                      const person = root.querySelector('.presenter-title-assignee-person');
                      const rootRect = root.getBoundingClientRect();
                      const contentRect = content.getBoundingClientRect();
                      const personRect = person.getBoundingClientRect();
                      const size = (node) => Number.parseFloat(getComputedStyle(node).fontSize);
                      return {
                        text: root.innerText,
                        hasSermonClass: Boolean(root.querySelector('.presenter-title-assignee--sermon')),
                        hasOrder: Boolean(order),
                        contentLeft: Math.round(contentRect.left - rootRect.left),
                        contentBeforePerson: contentRect.left < personRect.left,
                        personRight: Math.round(rootRect.right - personRect.right),
                        contentFontSize: size(content),
                        personFontSize: size(person),
                      };
                    }
                    """
                )
                if (
                    "베드로의 고백" in sermon_title_font_state["text"]
                    and "설교" not in sermon_title_font_state["text"]
                    and sermon_title_font_state["hasSermonClass"]
                    and not sermon_title_font_state["hasOrder"]
                    and sermon_title_font_state["contentBeforePerson"]
                    and sermon_title_font_state["contentFontSize"] == 90
                    and sermon_title_font_state["personFontSize"] == 70
                ):
                    pass_("presenter-sermon-title-content-font", json.dumps(sermon_title_font_state, ensure_ascii=False))
                else:
                    fail("presenter-sermon-title-content-font", json.dumps(sermon_title_font_state, ensure_ascii=False))

                title_assignee_solo = output_page.evaluate(
                    """
                    () => {
                      renderPresenterOutput({
                        serviceId: '__smoke_title_assignee_solo__',
                        serviceType: 'friday',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        backgroundImage: '',
                        slides: [{
                          id: '__smoke_long_title_solo__',
                          type: 'title-assignee',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                          layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                          title: '공동체를 위한 길고 긴 안내 제목',
                          assignee: '',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const root = document.getElementById('presenterOutputRoot');
                      const bar = root.querySelector('.presenter-title-assignee');
                      const title = root.querySelector('.presenter-title-assignee-title');
                      const rootRect = root.getBoundingClientRect();
                      const titleRect = title.getBoundingClientRect();
                      return {
                        text: root.innerText,
                        hasSoloClass: bar.classList.contains('presenter-title-assignee--solo'),
                        columnCount: getComputedStyle(bar).gridTemplateColumns.split(' ').filter(Boolean).length,
                        titleInside: titleRect.left >= rootRect.left - 1 && titleRect.right <= rootRect.right + 1,
                        hasPerson: Boolean(root.querySelector('.presenter-title-assignee-person')),
                      };
                    }
                    """
                )
                if (
                    "공동체를 위한 길고 긴 안내 제목" in title_assignee_solo["text"]
                    and title_assignee_solo["hasSoloClass"]
                    and not title_assignee_solo["hasPerson"]
                    and title_assignee_solo["titleInside"]
                    and title_assignee_solo["columnCount"] == 1
                ):
                    pass_("presenter-title-assignee-solo-fit", json.dumps(title_assignee_solo, ensure_ascii=False))
                else:
                    fail("presenter-title-assignee-solo-fit", json.dumps(title_assignee_solo, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      const slide = {
                        id: '__smoke_live_scripture__',
                        elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'scripture',
                        label: '성구',
                        title: '요 3:16',
                        marker: '요 3:16',
                        text: '요 3:16   하나님이 세상을 이처럼 사랑하사',
                        live: true,
                      };
                      state.presenter.liveScripture = {
                        reference: slide.title,
                        draft: slide.title,
                        active: true,
                        slide,
                      };
                      state.presenter.safetyBlank = false;
                      publishPresenterState({ force: true });
                      renderPresenterControlState(serviceId);
                      return presenterStatePayload(serviceId);
                    }
                    """,
                    service["id"],
                )
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).liveScripture?.active === true",
                    timeout=5000,
                )
                output_page.wait_for_function(
                    "() => document.querySelector('.presenter-slide')?.classList.contains('presenter-slide--scripture')",
                    timeout=5000,
                )
                live_scripture_state = output_page.evaluate(
                    """
                    (() => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slide = root?.querySelector('.presenter-slide');
                      const textEl = slide?.querySelector('.presenter-slide-text');
                      const firstLine = textEl?.querySelector('span');
                      const rootRect = root?.getBoundingClientRect();
                      const textRect = textEl?.getBoundingClientRect();
                      const firstRect = firstLine?.getBoundingClientRect();
                      const style = textEl ? getComputedStyle(textEl) : null;
                      const lineStyle = firstLine ? getComputedStyle(firstLine) : null;
                      const probe = document.createElement('span');
                      probe.style.cssText = 'position:fixed;visibility:hidden;font-size:var(--presenter-size-lyrics)';
                      root.appendChild(probe);
                      const lyricsFontSize = Number.parseFloat(getComputedStyle(probe).fontSize || '0');
                      probe.remove();
                      return {
                        slideClass: slide?.className || '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        text: slide?.innerText.trim() || '',
                        html: firstLine?.innerHTML || '',
                        textAlign: style?.textAlign || '',
                        alignItems: style?.alignItems || '',
                        fontSize: Number.parseFloat(style?.fontSize || '0'),
                        lyricsFontSize,
                        barRatio: rootRect && textRect ? Number((textRect.height / rootRect.height).toFixed(3)) : 0,
                        lineDisplay: lineStyle?.display || '',
                        lineFits: firstLine ? firstLine.scrollWidth <= firstLine.clientWidth + 1 : false,
                        lineInsideTextBox: textRect && firstRect ? firstRect.left >= textRect.left - 1 && firstRect.right <= textRect.right + 1 : false,
                        lineLeftInset: rootRect && firstRect ? Math.round(firstRect.left - rootRect.left) : -1,
                        lineRightInset: rootRect && firstRect ? Math.round(rootRect.right - firstRect.right) : -1,
                      };
                    })()
                    """
                )
                if (
                    "presenter-slide--scripture" in live_scripture_state["slideClass"]
                    and live_scripture_state["elementType"] == "scripture_text"
                    and live_scripture_state["layout"] == "lower_bar_text"
                    and "요 3:16" in live_scripture_state["text"]
                    and "하나님이 세상을" in live_scripture_state["text"]
                    and "요 3:16&nbsp;&nbsp;&nbsp;하나님이" in live_scripture_state["html"]
                    and live_scripture_state["textAlign"] == "left"
                    and live_scripture_state["alignItems"] == "flex-start"
                    and live_scripture_state["fontSize"] <= live_scripture_state["lyricsFontSize"]
                    and abs(live_scripture_state["barRatio"] - (7 / 40)) <= 0.01
                    and live_scripture_state["lineDisplay"] == "block"
                    and live_scripture_state["lineFits"]
                    and live_scripture_state["lineInsideTextBox"]
                    and 32 <= live_scripture_state["lineLeftInset"] <= 90
                    and 24 <= live_scripture_state["lineRightInset"] <= 60
                ):
                    pass_("presenter-live-scripture-lower-bar", json.dumps(live_scripture_state, ensure_ascii=False))
                else:
                    fail("presenter-live-scripture-lower-bar", json.dumps(live_scripture_state, ensure_ascii=False))

                long_live_scripture_state = output_page.evaluate(
                    """
                    (() => {
                      const slide = {
                        id: '__smoke_long_live_scripture__',
                        elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'scripture',
                        title: '로마서 8:17',
                        text: '17 자녀이면 또한 상속자 곧 하나님의 상속자요 그리스도와 함께 한 상속자니 우리가 그와 함께 영광을 받기 위하여 고난도 함께 받아야 할 것이니라',
                        live: true,
                        outputContext: 'chromakey',
                      };
                      renderPresenterOutput({
                        serviceId: '__smoke_long_live_scripture_service__',
                        serviceType: 'sunday-main',
                        chromakey: true,
                        slides: [slide],
                        index: 0,
                        safetyBlank: false,
                      }, {});
                      const root = document.getElementById('presenterOutputRoot');
                      const textEl = root?.querySelector('.presenter-slide--scripture .presenter-slide-text');
                      const style = textEl ? getComputedStyle(textEl) : null;
                      return {
                        fontSize: Number.parseFloat(style?.fontSize || '0'),
                        fitsHeight: textEl ? textEl.scrollHeight <= textEl.clientHeight + 1 : false,
                        fitsWidth: textEl ? textEl.scrollWidth <= textEl.clientWidth + 1 : false,
                      };
                    })()
                    """
                )
                if (
                    long_live_scripture_state["fontSize"] < 72
                    and long_live_scripture_state["fitsHeight"]
                    and long_live_scripture_state["fitsWidth"]
                ):
                    pass_("presenter-long-live-scripture-fits-lower-bar", json.dumps(long_live_scripture_state, ensure_ascii=False))
                else:
                    fail("presenter-long-live-scripture-fits-lower-bar", json.dumps(long_live_scripture_state, ensure_ascii=False))

                extra_long_live_scripture_state = output_page.evaluate(
                    """
                    (() => {
                      const slide = {
                        id: '__smoke_extra_long_live_scripture__',
                        elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'scripture',
                        title: '창세기 45:11',
                        text: '11 흉년이 아직 다섯 해가 있으니 내가 거기서 아버지를 봉양하리이다 아버지와 아버지의 가족과 아버지께 속한 모든 사람에게 부족함이 없도록 하겠습니다',
                        live: true,
                        outputContext: 'chromakey',
                      };
                      renderPresenterOutput({
                        serviceId: '__smoke_extra_long_live_scripture_service__',
                        serviceType: 'sunday-main',
                        chromakey: true,
                        slides: [slide],
                        index: 0,
                        safetyBlank: false,
                      }, {});
                      const root = document.getElementById('presenterOutputRoot');
                      const textEl = root?.querySelector('.presenter-slide--scripture .presenter-slide-text');
                      const firstLine = textEl?.querySelector('span');
                      const textRect = textEl?.getBoundingClientRect();
                      const firstRect = firstLine?.getBoundingClientRect();
                      const style = textEl ? getComputedStyle(textEl) : null;
                      return {
                        fontSize: Number.parseFloat(style?.fontSize || '0'),
                        fitsHeight: textEl ? textEl.scrollHeight <= textEl.clientHeight + 1 : false,
                        fitsWidth: textEl ? textEl.scrollWidth <= textEl.clientWidth + 1 : false,
                        textInsideBox: textRect && firstRect ? firstRect.top >= textRect.top - 1 && firstRect.bottom <= textRect.bottom + 1 : false,
                        clipsOverflow: style?.overflow === 'hidden',
                      };
                    })()
                    """
                )
                if (
                    extra_long_live_scripture_state["fontSize"] <= 72
                    and extra_long_live_scripture_state["fitsHeight"]
                    and extra_long_live_scripture_state["fitsWidth"]
                    and extra_long_live_scripture_state["textInsideBox"]
                    and extra_long_live_scripture_state["clipsOverflow"]
                ):
                    pass_("presenter-extra-long-live-scripture-fits-lower-bar", json.dumps(extra_long_live_scripture_state, ensure_ascii=False))
                else:
                    fail("presenter-extra-long-live-scripture-fits-lower-bar", json.dumps(extra_long_live_scripture_state, ensure_ascii=False))

                long_live_scripture_preview_state = page.evaluate(
                    """
                    (() => {
                      const slide = {
                        id: '__smoke_long_live_scripture_preview__',
                        elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
                        type: 'scripture',
                        title: '로마서 8:17',
                        text: '17 자녀이면 또한 상속자 곧 하나님의 상속자요 그리스도와 함께 한 상속자니 우리가 그와 함께 영광을 받기 위하여 고난도 함께 받아야 할 것이니라',
                        live: true,
                        outputContext: 'chromakey',
                      };
                      const mount = document.createElement('div');
                      mount.innerHTML = renderPresenterSlideMiniPreview(slide);
                      document.body.append(mount);
                      fitPresenterChromakeyScripturePreviews(mount);
                      const textEl = mount.querySelector('.presenter-slide--scripture .presenter-slide-text');
                      const style = textEl ? getComputedStyle(textEl) : null;
                      const result = {
                        fontSize: Number.parseFloat(style?.fontSize || '0'),
                        fitsHeight: textEl ? textEl.scrollHeight <= textEl.clientHeight + 1 : false,
                        fitsWidth: textEl ? textEl.scrollWidth <= textEl.clientWidth + 1 : false,
                      };
                      mount.remove();
                      return result;
                    })()
                    """
                )
                if (
                    abs(long_live_scripture_preview_state["fontSize"] - long_live_scripture_state["fontSize"]) <= 0.1
                    and long_live_scripture_preview_state["fitsHeight"]
                    and long_live_scripture_preview_state["fitsWidth"]
                ):
                    pass_("presenter-long-live-scripture-preview-parity", json.dumps(long_live_scripture_preview_state, ensure_ascii=False))
                else:
                    fail("presenter-long-live-scripture-preview-parity", json.dumps(long_live_scripture_preview_state, ensure_ascii=False))

                live_scripture_controller_state = page.evaluate(
                    """
                    (() => ({
                      activeThumbs: document.querySelectorAll('.svc-slide-thumb.active').length,
                      activeWraps: document.querySelectorAll('.svc-slide-thumb-wrap.active').length,
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                    }))()
                    """
                )
                if (
                    live_scripture_controller_state["activeThumbs"] == 0
                    and live_scripture_controller_state["activeWraps"] == 0
                    and live_scripture_controller_state["status"] == "송출 중"
                    and live_scripture_controller_state["mode"] == "성구"
                ):
                    pass_("presenter-live-scripture-controller-preview", json.dumps(live_scripture_controller_state, ensure_ascii=False))
                else:
                    fail("presenter-live-scripture-controller-preview", json.dumps(live_scripture_controller_state, ensure_ascii=False))

                jump_input = page.locator(f'[data-presenter-jump-input][data-service-id="{service["id"]}"]')
                jump_input.fill("1")
                jump_input.press("Enter")
                output_page.wait_for_function(
                    "() => { const payload = (readPresenterStoredPayload() || {}); return payload.index === 0 && payload.safetyBlank !== true; }",
                    timeout=5000,
                )
                output_page.wait_for_function(
                    "() => document.querySelector('.presenter-slide--video .presenter-video')",
                    timeout=5000,
                )
                ready_output_shot = output_page.locator("#presenterOutputRoot").screenshot()
                ready_output_state = output_page.evaluate(
                    """
                    (() => {
                      const slide = document.querySelector('.presenter-slide');
                      const video = slide?.querySelector('.presenter-video');
                      const copy = slide?.querySelector('.presenter-waiting-loop-copy');
                      const logo = slide?.querySelector('.presenter-waiting-loop-logo');
                      return {
                        slideClass: slide?.className || '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        slidePresenterRole: slide?.dataset.presenterRole || '',
                        slideBackground: slide ? getComputedStyle(slide).backgroundColor : '',
                        text: slide?.innerText.trim() || '',
                        videoSrc: video?.getAttribute('src') || '',
                        autoplay: Boolean(video?.autoplay),
                        muted: Boolean(video?.muted),
                        loop: Boolean(video?.loop),
                        controls: Boolean(video?.controls),
                        presenterRole: video?.dataset.presenterRole || '',
                        hasOverlay: Boolean(copy && logo),
                      };
                    })()
                    """
                )
                ready_output_state["centerPixel"] = rgb_at(ready_output_shot, 0.5, 0.5)
                if (
                    "presenter-slide--video" in ready_output_state["slideClass"]
                    and ready_output_state["elementType"] == "video"
                    and ready_output_state["layout"] == "media"
                    and ready_output_state["slidePresenterRole"] == "waiting_loop"
                    and ready_output_state["slideBackground"] == "rgb(0, 0, 0)"
                    and ready_output_state["videoSrc"].split("?")[0].endswith("assets/presenter/chromakey-ready-loop-fast.mp4")
                    and ready_output_state["autoplay"]
                    and ready_output_state["muted"]
                    and ready_output_state["loop"]
                    and not ready_output_state["controls"]
                    and ready_output_state["presenterRole"] == "waiting_loop"
                    and not ready_output_state["hasOverlay"]
                    and ready_output_state["text"] == ""
                    and not is_chromakey_green(tuple(ready_output_state["centerPixel"]))
                ):
                    pass_("presenter-ready-output-chromakey-video-loop", json.dumps(ready_output_state, ensure_ascii=False))
                else:
                    fail("presenter-ready-output-chromakey-video-loop", json.dumps(ready_output_state, ensure_ascii=False))

                jump_input.fill("0")
                jump_input.press("Enter")
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).safetyBlank === true",
                    timeout=5000,
                )
                output_page.wait_for_function(
                    "() => document.querySelector('.presenter-slide')?.classList.contains('presenter-slide--blank')",
                    timeout=5000,
                )
                safety_blank_state = output_page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      const slide = document.querySelector('.presenter-slide');
                      return {
                        index: payload.index,
                        safetyBlank: Boolean(payload.safetyBlank),
                        slideClass: slide?.className || '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        text: slide?.innerText.trim() || '',
                      };
                    })()
                    """
                )
                if (
                    safety_blank_state["safetyBlank"]
                    and "presenter-slide--blank" in safety_blank_state["slideClass"]
                    and safety_blank_state["elementType"] == "blank"
                    and safety_blank_state["layout"] == "blank"
                    and safety_blank_state["text"] == ""
                ):
                    pass_("presenter-invalid-jump-blank", json.dumps(safety_blank_state, ensure_ascii=False))
                else:
                    fail("presenter-invalid-jump-blank", json.dumps(safety_blank_state, ensure_ascii=False))

                blank_cross_animation = output_page.evaluate(
                    """
                    (() => {
                      renderPresenterOutput({
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        slides: [],
                        index: 0,
                        safetyBlank: true,
                      });
                      const slide = document.querySelector('.presenter-slide--blank');
                      const vertical = getComputedStyle(slide, '::before');
                      const horizontal = getComputedStyle(slide, '::after');
                      const verticalAnimation = vertical.animationName;
                      const verticalDelay = vertical.animationDelay;
                      const verticalOrigin = vertical.transformOrigin;
                      const horizontalAnimation = horizontal.animationName;
                      const horizontalDelay = horizontal.animationDelay;
                      const horizontalOrigin = horizontal.transformOrigin;
                      const repeatPayload = {
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        slides: [],
                        index: 0,
                        safetyBlank: true,
                      };
                      renderPresenterOutput(repeatPayload);
                      const repeatActiveBefore = document.querySelector('#presenterOutputRoot > .presenter-output-layer.is-active');
                      renderPresenterOutput(repeatPayload);
                      const repeatActiveAfter = document.querySelector('#presenterOutputRoot > .presenter-output-layer.is-active');
                      const inactiveBlank = document.querySelector('#presenterOutputRoot > .presenter-output-layer:not(.is-active) .presenter-slide--blank');
                      const inactiveVertical = inactiveBlank ? getComputedStyle(inactiveBlank, '::before') : null;
                      const inactiveHorizontal = inactiveBlank ? getComputedStyle(inactiveBlank, '::after') : null;
                      const mini = document.createElement('span');
                      mini.className = 'svc-slide-mini-canvas presenter-output-root no-chromakey is-blank';
                      mini.innerHTML = renderPresenterSlideFrame({
                        id: '__smoke_blank_thumb_cross__',
                        elementType: 'blank',
                        layout: 'blank',
                        type: 'blank',
                        title: '빈 화면',
                        text: '',
                      }, { noChromakey: true, previewStage: true });
                      document.body.appendChild(mini);
                      const miniSlide = mini.querySelector('.presenter-slide--blank');
                      const miniVertical = getComputedStyle(miniSlide, '::before');
                      const miniHorizontal = getComputedStyle(miniSlide, '::after');
                      renderPresenterOutput({
                        serviceType: 'sunday-second',
                        chromakey: true,
                        outputTheme: 'chromakey',
                        slides: [{
                          id: '__smoke_chromakey_blank_has_no_cross__',
                          elementType: 'blank',
                          layout: 'blank',
                          type: 'blank',
                          title: '빈 화면',
                          text: '',
                          outputContext: 'chromakey',
                        }],
                        index: 0,
                        safetyBlank: false,
                      });
                      const chromakeySlide = document.querySelector('.presenter-slide--blank');
                      const chromakeyVertical = getComputedStyle(chromakeySlide, '::before');
                      const chromakeyHorizontal = getComputedStyle(chromakeySlide, '::after');
                      const verseRange = presenterScriptureVerseNumber({ number: '18', verseEnd: 19 });
                      const verseParts = presenterScriptureVerseParts(`${verseRange}   함께 저장된 본문`);
                      return {
                        verticalAnimation,
                        verticalDelay,
                        verticalOrigin,
                        horizontalAnimation,
                        horizontalDelay,
                        horizontalOrigin,
                        repeatActivePreserved: Boolean(repeatActiveBefore && repeatActiveBefore === repeatActiveAfter),
                        inactiveVerticalDisplay: inactiveVertical?.display || '',
                        inactiveHorizontalDisplay: inactiveHorizontal?.display || '',
                        miniVerticalWidth: miniVertical.width,
                        miniVerticalTransform: miniVertical.transform,
                        miniHorizontalHeight: miniHorizontal.height,
                        miniHorizontalTransform: miniHorizontal.transform,
                        chromakeyVerticalAnimation: chromakeyVertical.animationName,
                        chromakeyHorizontalAnimation: chromakeyHorizontal.animationName,
                        verseRange,
                        verseParts,
                      };
                    })()
                    """
                )
                if (
                    blank_cross_animation["verticalAnimation"] == "presenter-blank-cross-vertical"
                    and blank_cross_animation["verticalDelay"] == "0s"
                    and blank_cross_animation["verticalOrigin"].endswith(" 0px")
                    and blank_cross_animation["horizontalAnimation"] == "presenter-blank-cross-horizontal"
                    and blank_cross_animation["horizontalDelay"] == "0.55s"
                    and blank_cross_animation["horizontalOrigin"].startswith("0px ")
                    and blank_cross_animation["repeatActivePreserved"]
                    and blank_cross_animation["inactiveVerticalDisplay"] in ["", "none"]
                    and blank_cross_animation["inactiveHorizontalDisplay"] in ["", "none"]
                    and blank_cross_animation["miniVerticalWidth"] == "12px"
                    and blank_cross_animation["miniVerticalTransform"] != "none"
                    and blank_cross_animation["miniHorizontalHeight"] == "12px"
                    and blank_cross_animation["miniHorizontalTransform"] != "none"
                    and blank_cross_animation["chromakeyVerticalAnimation"] not in ["presenter-blank-cross-vertical"]
                    and blank_cross_animation["chromakeyHorizontalAnimation"] not in ["presenter-blank-cross-horizontal"]
                    and blank_cross_animation["verseRange"] == "18–19"
                    and blank_cross_animation["verseParts"] == {"number": "18–19", "text": "함께 저장된 본문"}
                ):
                    pass_("presenter-blank-cross-draw-order", json.dumps(blank_cross_animation, ensure_ascii=False))
                else:
                    fail("presenter-blank-cross-draw-order", json.dumps(blank_cross_animation, ensure_ascii=False))

                safety_blank_controller_state = page.evaluate(
                    """
                    (() => ({
                      inputValue: document.querySelector('[data-presenter-jump-input]')?.value || '',
                      activeThumbs: document.querySelectorAll('.svc-slide-thumb.active').length,
                      activeWraps: document.querySelectorAll('.svc-slide-thumb-wrap.active').length,
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                    }))()
                    """
                )
                if (
                    safety_blank_controller_state["inputValue"] == "0"
                    and safety_blank_controller_state["activeThumbs"] == 0
                    and safety_blank_controller_state["activeWraps"] == 0
                    and safety_blank_controller_state["status"] == "송출 중"
                    and safety_blank_controller_state["mode"] == "빈 화면"
                ):
                    pass_("presenter-safety-blank-controller-preview", json.dumps(safety_blank_controller_state, ensure_ascii=False))
                else:
                    fail("presenter-safety-blank-controller-preview", json.dumps(safety_blank_controller_state, ensure_ascii=False))

                jump_input.fill("2")
                jump_input.press("Enter")
                output_page.wait_for_function(
                    "() => { const payload = (readPresenterStoredPayload() || {}); return payload.index === 1 && payload.safetyBlank !== true; }",
                    timeout=10000,
                )

                invalid_slide_number = page.evaluate("() => state.presenter.slides.length + 100")
                jump_input.fill(str(invalid_slide_number))
                jump_input.press("Enter")
                page.wait_for_timeout(150)
                invalid_jump_state = page.evaluate(
                    """
                    (() => ({
                      index: state.presenter.index,
                      safetyBlank: Boolean(state.presenter.safetyBlank),
                      inputValue: document.querySelector('[data-presenter-jump-input]')?.value || '',
                    }))()
                    """
                )
                if (
                    invalid_jump_state["index"] == 1
                    and not invalid_jump_state["safetyBlank"]
                    # The output must not move and the field returns to the current slide number.
                    and invalid_jump_state["inputValue"] == "2"
                ):
                    pass_("presenter-invalid-jump-noop", json.dumps(invalid_jump_state, ensure_ascii=False))
                else:
                    fail("presenter-invalid-jump-noop", json.dumps(invalid_jump_state, ensure_ascii=False))

                output_page.keyboard.press("ArrowRight")
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).index === 2",
                    timeout=10000,
                )
                channel_state = output_page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      const text = document.querySelector('.presenter-slide')?.innerText.trim() || '';
                      return {
                        index: payload.index,
                        slideClass: document.querySelector('.presenter-slide')?.className || '',
                        text,
                      };
                    })()
                    """
                )
                controller_state = page.evaluate(
                    """
                    (() => ({
                      index: state.presenter.index,
                      serviceId: state.presenter.serviceId,
                    }))()
                    """
                )
                if channel_state["index"] == 2 and controller_state["index"] == 2:
                    pass_("presenter-output-key-sync", json.dumps({"output": channel_state, "controller": controller_state}, ensure_ascii=False))
                else:
                    fail("presenter-output-key-sync", json.dumps({"output": channel_state, "controller": controller_state}, ensure_ascii=False))

                controller_restore_after_hydration = page.evaluate(
                    """
                    (() => {
                      const previous = {
                        services: state.services,
                        serviceTypes: state.serviceTypes,
                        serviceItems: state.serviceItems,
                        selectedServiceId: state.selectedServiceId,
                        selectedServiceTypeId: state.selectedServiceTypeId,
                        module: state.module,
                        presenter: { ...state.presenter },
                        storedPayload: localStorage.getItem(PRESENTER_STORAGE_KEY),
                      };
                      const service = {
                        id: '__smoke_presenter_restore_hydration__',
                        type_id: 'monthly',
                        date: '2026-07-04',
                        title: 'Restore Hydration Smoke',
                        leader: '테스트',
                        alias: '',
                      };
                      try {
                        if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                          state.serviceTypes = [
                            ...state.serviceTypes,
                            { id: service.type_id, name: '월삭예배', sort_order: 1 },
                          ];
                        }
                        state.services = [
                          service,
                          ...state.services.filter((item) => item.id !== service.id),
                        ];
                        const hydratedItems = normalizeServiceItems([
                          {
                            id: '__smoke_presenter_restore_item_1__',
                            service_id: service.id,
                            sort_order: 1,
                            label: '준비',
                            raw_title: '복원 첫 항목',
                            memo: JSON.stringify({ slides: ['복원 첫 슬라이드'] }),
                          },
                          {
                            id: '__smoke_presenter_restore_item_2__',
                            service_id: service.id,
                            sort_order: 2,
                            label: '찬양',
                            raw_title: '복원 둘째 항목',
                            memo: JSON.stringify({ slides: ['복원 둘째 슬라이드'] }),
                          },
                        ]);
                        state.serviceItems = {
                          ...state.serviceItems,
                          [service.id]: hydratedItems,
                        };
                        const slides = buildServicePresenterSlides(service.id);
                        const targetIndex = Math.min(1, Math.max(slides.length - 1, 0));
                        const restorePayload = normalizePresenterPayload({
                          serviceId: service.id,
                          serviceType: service.type_id,
                          serviceTitle: '월삭예배 · 2026-07-04',
                          serviceDate: service.date,
                          slides,
                          index: targetIndex,
                          slideAnchor: presenterSlideAnchor(slides[targetIndex]),
                          safetyBlank: false,
                          liveScripture: null,
                          updatedAt: Date.now(),
                        });
                        localStorage.setItem(PRESENTER_STORAGE_KEY, JSON.stringify(restorePayload));

                        delete state.serviceItems[service.id];
                        state.module = 'presenter';
                        state.selectedServiceId = '';
                        state.selectedServiceTypeId = '';
                        state.presenter = {
                          ...state.presenter,
                          serviceId: '',
                          slides: [],
                          index: 0,
                          safetyBlank: false,
                          liveScripture: { reference: '', draft: '', active: false, slide: null },
                          livePraise: emptyLivePraiseState(),
                          restorePayload,
                          outputConnectedAt: Date.now(),
                          outputStopAt: 0,
                        };
                        const before = restorePresenterControllerSession();
                        state.serviceItems[service.id] = hydratedItems;
                        const after = restorePresenterControllerSession();
                        return {
                          before,
                          after,
                          serviceId: state.presenter.serviceId,
                          selectedServiceId: state.selectedServiceId,
                          selectedServiceTypeId: state.selectedServiceTypeId,
                          index: state.presenter.index,
                          expectedIndex: targetIndex,
                          slideTitle: state.presenter.slides[state.presenter.index]?.title || '',
                          payloadIndex: JSON.parse(localStorage.getItem(PRESENTER_STORAGE_KEY) || '{}').index,
                        };
                      } finally {
                        state.services = previous.services;
                        state.serviceTypes = previous.serviceTypes;
                        state.serviceItems = previous.serviceItems;
                        state.selectedServiceId = previous.selectedServiceId;
                        state.selectedServiceTypeId = previous.selectedServiceTypeId;
                        state.module = previous.module;
                        state.presenter = previous.presenter;
                        if (previous.storedPayload === null) localStorage.removeItem(PRESENTER_STORAGE_KEY);
                        else localStorage.setItem(PRESENTER_STORAGE_KEY, previous.storedPayload);
                      }
                    })()
                    """
                )
                if (
                    controller_restore_after_hydration["before"] == "pending"
                    and controller_restore_after_hydration["after"] == "restored"
                    and controller_restore_after_hydration["serviceId"] == "__smoke_presenter_restore_hydration__"
                    and controller_restore_after_hydration["selectedServiceId"] == "__smoke_presenter_restore_hydration__"
                    and controller_restore_after_hydration["selectedServiceTypeId"] == "monthly"
                    and controller_restore_after_hydration["index"] == controller_restore_after_hydration["expectedIndex"]
                    and controller_restore_after_hydration["payloadIndex"] == controller_restore_after_hydration["expectedIndex"]
                ):
                    pass_("presenter-controller-restore-after-hydration", json.dumps(controller_restore_after_hydration, ensure_ascii=False))
                else:
                    fail("presenter-controller-restore-after-hydration", json.dumps(controller_restore_after_hydration, ensure_ascii=False))

                selection_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_presenter_switch_service__',
                        type_id: 'monthly',
                        date: '2026-07-04',
                        title: 'Switch Smoke',
                        leader: '테스트',
                        alias: '',
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({ id: service.type_id, name: '월삭예배', sort_order: 1 });
                      }
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_presenter_switch_item_1__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '안내',
                          raw_title: '전환 테스트',
                          memo: JSON.stringify({
                            slides: ['전환 후 첫 슬라이드', '전환 후 둘째 슬라이드'],
                          }),
                        },
                      ]);
                      state.module = 'presenter';
                      state.selectedServiceTypeId = service.type_id;
                      state.selectedServiceId = service.id;
                      state.presenter.viewServiceId = service.id;
                      renderPresenterDetail();
                      renderServiceList();
                      const payload = (readPresenterStoredPayload() || {});
                      return {
                        switchId: service.id,
                        selectedServiceId: state.selectedServiceId,
                        presenterServiceId: state.presenter.serviceId,
                        outputServiceId: payload.serviceId || '',
                        selectedThumbs: document.querySelectorAll('.svc-slide-thumb').length,
                        selectedActiveThumbs: document.querySelectorAll('.svc-slide-thumb.active').length,
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                        mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                      };
                    }
                    """
                )
                if (
                    selection_state["switchId"] == selection_state["selectedServiceId"]
                    and selection_state["presenterServiceId"] == service["id"]
                    and selection_state["outputServiceId"] == service["id"]
                    and selection_state["selectedThumbs"] >= 2
                    and selection_state["selectedActiveThumbs"] == 0
                    and selection_state["status"] == "다른 예배 송출"
                    and selection_state["mode"] == "다른 예배"
                ):
                    pass_("presenter-service-selection-is-passive", json.dumps(selection_state, ensure_ascii=False))
                else:
                    fail("presenter-service-selection-is-passive", json.dumps(selection_state, ensure_ascii=False))

                page.keyboard.press("Space")
                page.locator(
                    f'.svc-slide-thumb[data-service-id="{selection_state["switchId"]}"][data-presenter-index="1"]'
                ).click()
                page.wait_for_timeout(500)
                other_live_keyboard_state = page.evaluate(
                    """
                    () => {
                      const payload = (readPresenterStoredPayload() || {});
                      return {
                        presenterServiceId: state.presenter.serviceId,
                        presenterIndex: state.presenter.index,
                        outputServiceId: payload.serviceId || '',
                        outputIndex: payload.index,
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                        mode: document.querySelector('.svc-presenter-mode')?.textContent.trim() || '',
                      };
                    }
                    """
                )
                if (
                    other_live_keyboard_state["presenterServiceId"] == service["id"]
                    and other_live_keyboard_state["presenterIndex"] == 2
                    and other_live_keyboard_state["outputServiceId"] == service["id"]
                    and other_live_keyboard_state["outputIndex"] == 2
                    and other_live_keyboard_state["status"] == "다른 예배 송출"
                    and other_live_keyboard_state["mode"] == "다른 예배"
                ):
                    pass_("presenter-keyboard-other-live-ignored", json.dumps(other_live_keyboard_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-other-live-ignored", json.dumps(other_live_keyboard_state, ensure_ascii=False))

                controller_esc_state = page.evaluate(
                    """
                    () => {
                      const previousModule = state.module;
                      const previousSelectedServiceId = state.selectedServiceId;
                      const previousPresenterServiceId = state.presenter.serviceId;
                      const previousExitArmedAt = state.presenter.exitArmedAt;
                      const originalStopPresenterOutput = stopPresenterOutput;
                      let stoppedServiceId = '';
                      let preventCount = 0;
                      stopPresenterOutput = (serviceId) => {
                        stoppedServiceId = serviceId || '';
                      };
                      state.module = 'presenter';
                      state.selectedServiceId = '__smoke_other_selected__';
                      state.presenter.serviceId = previousPresenterServiceId || '__smoke_active_presenter__';
                      state.presenter.exitArmedAt = 0;
                      const makeEvent = () => ({
                        key: 'Escape',
                        target: document.body,
                        metaKey: false,
                        ctrlKey: false,
                        altKey: false,
                        preventDefault() { preventCount += 1; },
                      });
                      const firstHandled = handlePresenterShortcut(makeEvent());
                      const armedAfterFirst = state.presenter.exitArmedAt > 0;
                      const secondHandled = handlePresenterShortcut(makeEvent());
                      const armedAfterSecond = state.presenter.exitArmedAt > 0;
                      stopPresenterOutput = originalStopPresenterOutput;
                      state.module = previousModule;
                      state.selectedServiceId = previousSelectedServiceId;
                      state.presenter.serviceId = previousPresenterServiceId;
                      state.presenter.exitArmedAt = previousExitArmedAt || 0;
                      return {
                        firstHandled,
                        secondHandled,
                        armedAfterFirst,
                        armedAfterSecond,
                        stoppedServiceId,
                        expectedServiceId: previousPresenterServiceId,
                        preventCount,
                      };
                    }
                    """
                )
                if (
                    controller_esc_state["firstHandled"]
                    and controller_esc_state["secondHandled"]
                    and controller_esc_state["armedAfterFirst"]
                    and controller_esc_state["armedAfterSecond"]
                    and controller_esc_state["stoppedServiceId"] == controller_esc_state["expectedServiceId"]
                    and controller_esc_state["preventCount"] == 2
                ):
                    pass_("presenter-controller-escape-stop-other-service", json.dumps(controller_esc_state, ensure_ascii=False))
                else:
                    fail("presenter-controller-escape-stop-other-service", json.dumps(controller_esc_state, ensure_ascii=False))

                controller_f11_state = page.evaluate(
                    """
                    () => {
                      const previousModule = state.module;
                      const previousSelectedServiceId = state.selectedServiceId;
                      const previousPresenterServiceId = state.presenter.serviceId;
                      const previousOutputWindow = state.presenter.outputWindow;
                      const previousOutputConnectedAt = state.presenter.outputConnectedAt;
                      const previousChannel = state.presenter.channel;
                      const previousElectron = window.mindexElectron;
                      let preventCount = 0;
                      let stopCount = 0;
                      let directFullscreenCalls = 0;
                      let electronFullscreenCalls = 0;
                      let outputFocusCalls = 0;
                      const messages = [];
                      state.module = 'presenter';
                      state.selectedServiceId = '__smoke_active_presenter__';
                      state.presenter.serviceId = '__smoke_active_presenter__';
                      state.presenter.outputConnectedAt = Date.now();
                      state.presenter.outputWindow = {
                        closed: false,
                        focus() {
                          outputFocusCalls += 1;
                        },
                        document: {
                          documentElement: {
                            requestFullscreen() {
                              directFullscreenCalls += 1;
                              return Promise.resolve();
                            },
                          },
                        },
                      };
                      state.presenter.channel = {
                        postMessage(message) {
                          messages.push(message);
                        },
                      };
                      window.mindexElectron = {
                        fullscreenPresenterOutput() {
                          electronFullscreenCalls += 1;
                          return Promise.resolve();
                        },
                      };
                      const input = document.createElement('input');
                      document.body.appendChild(input);
                      const handled = handlePresenterShortcut({
                        key: 'F11',
                        target: input,
                        metaKey: false,
                        ctrlKey: false,
                        altKey: false,
                        preventDefault() { preventCount += 1; },
                        stopPropagation() { stopCount += 1; },
                      });
                      const signal = JSON.parse(localStorage.getItem(PRESENTER_SIGNAL_KEY) || '{}');
                      input.remove();
                      state.module = previousModule;
                      state.selectedServiceId = previousSelectedServiceId;
                      state.presenter.serviceId = previousPresenterServiceId;
                      state.presenter.outputWindow = previousOutputWindow;
                      state.presenter.outputConnectedAt = previousOutputConnectedAt;
                      state.presenter.channel = previousChannel;
                      if (previousElectron === undefined) delete window.mindexElectron;
                      else window.mindexElectron = previousElectron;
                      return {
                        handled,
                        preventCount,
                        stopCount,
                        directFullscreenCalls,
                        electronFullscreenCalls,
                        outputFocusCalls,
                        messageTypes: messages.map((message) => message.type),
                        signalType: signal.type || '',
                      };
                    }
                    """
                )
                if (
                    controller_f11_state["handled"]
                    and controller_f11_state["preventCount"] == 1
                    and controller_f11_state["stopCount"] == 1
                    and controller_f11_state["directFullscreenCalls"] == 0
                    and controller_f11_state["electronFullscreenCalls"] == 1
                    and controller_f11_state["outputFocusCalls"] == 0  # Electron main owns output focus (e9d05ec3)
                    and controller_f11_state["messageTypes"] == []
                    and controller_f11_state["signalType"] == ""
                ):
                    pass_("presenter-controller-f11-output-fullscreen", json.dumps(controller_f11_state, ensure_ascii=False))
                else:
                    fail("presenter-controller-f11-output-fullscreen", json.dumps(controller_f11_state, ensure_ascii=False))

                presenter_desktop_output_controls = page.evaluate(
                    """
                    async (serviceId) => {
                      const previousElectron = window.mindexElectron;
                      const previousScreens = state.presenter.screens;
                      const previousSelectedScreenId = state.presenter.selectedScreenId;
                      const previousAlwaysOnTop = state.presenter.alwaysOnTop;
                      const previousOutputWindow = state.presenter.outputWindow;
                      const previousOutputConnectedAt = state.presenter.outputConnectedAt;
                      const previousOutputPendingAt = state.presenter.outputPendingAt;
                      const previousOutputBlockedAt = state.presenter.outputBlockedAt;
                      const previousOutputAttemptServiceId = state.presenter.outputAttemptServiceId;
                      const previousOutputStopAt = state.presenter.outputStopAt;
                      const previousOpen = window.open;
                      const previousAlwaysStorage = localStorage.getItem(PRESENTER_ALWAYS_ON_TOP_STORAGE_KEY);
                      const openedPayloads = [];
                      const alwaysUpdates = [];
                      try {
                        window.mindexElectron = {
                          getPresenterDisplays: async () => ({
                            ok: true,
                            displays: [
                              { id: '1', label: '기본 화면', isPrimary: true, left: 0, top: 0, width: 1440, height: 900 },
                              { id: '2', label: '출력 화면', isPrimary: false, left: 1440, top: 0, width: 1920, height: 1080 },
                            ],
                          }),
                          openPresenterOutput: async (payload) => {
                            openedPayloads.push(payload);
                            state.presenter.outputConnectedAt = Date.now();
                            return { ok: true };
                          },
                          setPresenterAlwaysOnTop: async (payload) => {
                            alwaysUpdates.push(payload);
                            return { ok: true };
                          },
                        };
                        window.open = () => null;
                        state.presenter.screens = [];
                        state.presenter.selectedScreenId = null;
                        state.presenter.alwaysOnTop = false;
                        state.presenter.outputWindow = null;
                        state.presenter.outputConnectedAt = 0;
                        state.presenter.outputPendingAt = 0;
                        state.presenter.outputBlockedAt = 0;
                        state.presenter.outputAttemptServiceId = '';
                        state.presenter.outputStopAt = 0;
                        stopPresenterOutputWindowMonitor();
                        await requestPresenterScreens();
                        renderPresenterControlState(serviceId);
                        const screenLabel = document.querySelector('[data-presenter-screen-select] option:checked')?.textContent.trim() || '';
                        const toggle = document.querySelector('[data-presenter-always-on-top]');
                        if (toggle) {
                          toggle.checked = true;
                          toggle.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        await openPresenterOutput(serviceId);
                        return {
                          screenCount: state.presenter.screens.length,
                          selectedScreenId: state.presenter.selectedScreenId || '',
                          screenLabel,
                          toggleRendered: Boolean(toggle),
                          alwaysOnTop: state.presenter.alwaysOnTop,
                          alwaysUpdates,
                          openedPayloads: openedPayloads.map((payload) => ({
                            hasUrl: Boolean(payload.url),
                            alwaysOnTop: Boolean(payload.alwaysOnTop),
                            targetRect: payload.targetRect || null,
                          })),
                        };
                      } finally {
                        if (previousElectron === undefined) delete window.mindexElectron;
                        else window.mindexElectron = previousElectron;
                        window.open = previousOpen;
                        state.presenter.screens = previousScreens;
                        state.presenter.selectedScreenId = previousSelectedScreenId;
                        state.presenter.alwaysOnTop = previousAlwaysOnTop;
                        state.presenter.outputWindow = previousOutputWindow;
                        state.presenter.outputConnectedAt = previousOutputConnectedAt;
                        state.presenter.outputPendingAt = previousOutputPendingAt;
                        state.presenter.outputBlockedAt = previousOutputBlockedAt;
                        state.presenter.outputAttemptServiceId = previousOutputAttemptServiceId;
                        state.presenter.outputStopAt = previousOutputStopAt;
                        if (previousAlwaysStorage === null) localStorage.removeItem(PRESENTER_ALWAYS_ON_TOP_STORAGE_KEY);
                        else localStorage.setItem(PRESENTER_ALWAYS_ON_TOP_STORAGE_KEY, previousAlwaysStorage);
                        renderPresenterControlState(serviceId);
                      }
                    }
                    """,
                    service["id"],
                )
                desktop_controls_ok = (
                    presenter_desktop_output_controls["screenCount"] == 2
                    and "1920x1080" in presenter_desktop_output_controls["screenLabel"]
                    and presenter_desktop_output_controls["toggleRendered"]
                    and presenter_desktop_output_controls["alwaysOnTop"]
                    and presenter_desktop_output_controls["alwaysUpdates"] == [{"enabled": True}]
                    and len(presenter_desktop_output_controls["openedPayloads"]) == 1
                    and presenter_desktop_output_controls["openedPayloads"][0]["hasUrl"]
                    and presenter_desktop_output_controls["openedPayloads"][0]["alwaysOnTop"]
                    and presenter_desktop_output_controls["openedPayloads"][0]["targetRect"] == {
                        "left": 1440,
                        "top": 0,
                        "width": 1920,
                        "height": 1080,
                    }
                )
                if desktop_controls_ok:
                    pass_("presenter-desktop-output-controls", json.dumps(presenter_desktop_output_controls, ensure_ascii=False))
                else:
                    fail("presenter-desktop-output-controls", json.dumps(presenter_desktop_output_controls, ensure_ascii=False))

                switch_state = page.evaluate(
                    """
                    (switchId) => {
                      state.presenter.index = 99;
                      state.presenter.liveScripture = {
                        reference: '요 3:16',
                        draft: '요 3:16',
                        active: true,
                        slide: { text: '테스트 본문' },
                      };
                      preparePresenterService(switchId);
                      publishPresenterState({ force: true });
                      renderPresenterControlState(switchId);
                      const payload = presenterStatePayload(switchId);
                      return {
                        serviceId: state.presenter.serviceId,
                        index: state.presenter.index,
                        liveScriptureActive: Boolean(state.presenter.liveScripture.active),
                        slides: state.presenter.slides.length,
                        payloadIndex: payload.index,
                        activeThumbs: document.querySelectorAll('.svc-slide-thumb.active').length,
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      };
                    }
                    """,
                    selection_state["switchId"],
                )
                output_page.wait_for_function(
                    "(serviceId) => (readPresenterStoredPayload() || {}).serviceId === serviceId",
                    arg=selection_state["switchId"],
                    timeout=5000,
                )
                switch_output_state = output_page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      const root = document.getElementById('presenterOutputRoot');
                      return {
                        serviceId: payload.serviceId || '',
                        index: payload.index,
                        hasSlide: Boolean(root?.querySelector('.presenter-slide')),
                      };
                    })()
                    """
                )
                if (
                    switch_state["serviceId"] == selection_state["switchId"]
                    and switch_state["index"] == 0
                    and not switch_state["liveScriptureActive"]
                    and switch_state["slides"] >= 2
                    and switch_state["payloadIndex"] == 0
                    and switch_state["activeThumbs"] in (0, 1)
                    and switch_state["status"] == "송출 중"
                    and switch_output_state["serviceId"] == selection_state["switchId"]
                    and switch_output_state["index"] == 0
                    and switch_output_state["hasSlide"]
                ):
                    pass_(
                        "presenter-service-switch-reset",
                        json.dumps({"controller": switch_state, "output": switch_output_state}, ensure_ascii=False),
                    )
                else:
                    fail(
                        "presenter-service-switch-reset",
                        json.dumps({"controller": switch_state, "output": switch_output_state}, ensure_ascii=False),
                    )

                page.keyboard.press("Space")
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).index === 1",
                    timeout=5000,
                )
                active_keyboard_state = page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      return {
                        presenterServiceId: state.presenter.serviceId,
                        presenterIndex: state.presenter.index,
                        outputServiceId: payload.serviceId || '',
                        outputIndex: payload.index,
                        status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                      };
                    })()
                    """
                )
                if (
                    active_keyboard_state["presenterServiceId"] == selection_state["switchId"]
                    and active_keyboard_state["presenterIndex"] == 1
                    and active_keyboard_state["outputServiceId"] == selection_state["switchId"]
                    and active_keyboard_state["outputIndex"] == 1
                    and active_keyboard_state["status"] == "송출 중"
                ):
                    pass_("presenter-keyboard-active-service", json.dumps(active_keyboard_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-active-service", json.dumps(active_keyboard_state, ensure_ascii=False))

                page.evaluate(
                    """
                    () => {
                      const thumb = document.querySelector('.svc-slide-thumb[data-presenter-index="1"][data-service-id]');
                      thumb?.focus();
                    }
                    """
                )
                page.keyboard.press("ArrowRight")
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).index === 2",
                    timeout=5000,
                )
                thumb_focus_keyboard_state = page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      return {
                        presenterIndex: state.presenter.index,
                        outputIndex: payload.index,
                        focusedThumb: document.activeElement?.matches('.svc-slide-thumb[data-presenter-index][data-service-id]') || false,
                      };
                    })()
                    """
                )
                if (
                    thumb_focus_keyboard_state["presenterIndex"] == 2
                    and thumb_focus_keyboard_state["outputIndex"] == 2
                    and thumb_focus_keyboard_state["focusedThumb"]
                ):
                    pass_("presenter-keyboard-thumb-focus-advances", json.dumps(thumb_focus_keyboard_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-thumb-focus-advances", json.dumps(thumb_focus_keyboard_state, ensure_ascii=False))

                page.evaluate(
                    """
                    (serviceId) => {
                      state.presenter.serviceId = serviceId;
                      state.presenter.index = 1;
                      state.selectedServiceId = serviceId;
                      publishPresenterState({ force: true });
                      renderPresenterControlState(serviceId);
                      const thumb = document.querySelector('.svc-slide-thumb[data-presenter-index="1"][data-service-id]');
                      thumb?.focus();
                    }
                    """,
                    selection_state["switchId"],
                )
                page.keyboard.press("Space")
                output_page.wait_for_function(
                    "() => (readPresenterStoredPayload() || {}).index === 2",
                    timeout=5000,
                )
                page.wait_for_timeout(200)
                thumb_space_keyboard_state = page.evaluate(
                    """
                    (() => {
                      const payload = (readPresenterStoredPayload() || {});
                      return {
                        presenterIndex: state.presenter.index,
                        outputIndex: payload.index,
                        focusedThumb: document.activeElement?.matches('.svc-slide-thumb[data-presenter-index][data-service-id]') || false,
                      };
                    })()
                    """
                )
                if (
                    thumb_space_keyboard_state["presenterIndex"] == 2
                    and thumb_space_keyboard_state["outputIndex"] == 2
                    and thumb_space_keyboard_state["focusedThumb"]
                ):
                    pass_("presenter-keyboard-thumb-space-no-bounce", json.dumps(thumb_space_keyboard_state, ensure_ascii=False))
                else:
                    fail("presenter-keyboard-thumb-space-no-bounce", json.dumps(thumb_space_keyboard_state, ensure_ascii=False))

                outline_click_scroll_state = page.evaluate(
                    """
                    (serviceId) => {
                      preparePresenterService(serviceId);
                      renderServiceList();
                      renderPresenterControlState(serviceId);
                      const rows = [...document.querySelectorAll('.service-outline-row--child[data-service-outline-slide][data-service-outline-item-index]')]
                        .filter((node) => Number(node.dataset.serviceOutlineItemIndex) >= 0 && Number(node.dataset.serviceOutlineSlide) >= 0);
                      const row = rows.find((node) => node.textContent.includes('찬양') && Number(node.dataset.serviceOutlineItemIndex) > 1)
                        || rows.find((node) => Number(node.dataset.serviceOutlineItemIndex) > 1)
                        || rows[0];
                      if (!row) return { hasRow: false };
                      const previousStable = scrollPresenterBoardToIndexStable;
                      const previousItem = scrollPresenterBoardToServiceItem;
                      const previousIndex = scrollPresenterBoardToIndex;
                      const stableCalls = [];
                      const itemCalls = [];
                      const indexCalls = [];
                      scrollPresenterBoardToIndexStable = (...args) => {
                        stableCalls.push(args.map((value) => typeof value === 'object' ? { ...value } : value));
                        return true;
                      };
                      scrollPresenterBoardToServiceItem = (...args) => {
                        itemCalls.push(args.map((value) => typeof value === 'object' ? { ...value } : value));
                        return true;
                      };
                      scrollPresenterBoardToIndex = (...args) => {
                        indexCalls.push(args.map((value) => typeof value === 'object' ? { ...value } : value));
                        return true;
                      };
                      const target = {
                        text: row.textContent.trim(),
                        itemIndex: Number(row.dataset.serviceOutlineItemIndex),
                        slideIndex: Number(row.dataset.serviceOutlineSlide),
                      };
                      const beforeIndex = state.presenter.index;
                      const controllerLive = presenterControllerIsLive(serviceId);
                      row.click();
                      scrollPresenterBoardToIndexStable = previousStable;
                      scrollPresenterBoardToServiceItem = previousItem;
                      scrollPresenterBoardToIndex = previousIndex;
                      return {
                        hasRow: true,
                        target,
                        beforeIndex,
                        controllerLive,
                        presenterIndex: state.presenter.index,
                        selectedItemIndex: state.selectedServiceItemIndex,
                        stableCalls,
                        itemCalls,
                        indexCalls,
                      };
                    }
                    """,
                    selection_state["switchId"],
                )
                if (
                    outline_click_scroll_state["hasRow"]
                    and (
                        (
                            outline_click_scroll_state["controllerLive"]
                            and outline_click_scroll_state["presenterIndex"] == outline_click_scroll_state["beforeIndex"]
                        )
                        or (
                            not outline_click_scroll_state["controllerLive"]
                            and outline_click_scroll_state["presenterIndex"] == outline_click_scroll_state["target"]["slideIndex"]
                        )
                    )
                    and outline_click_scroll_state["selectedItemIndex"] == outline_click_scroll_state["target"]["itemIndex"]
                    and outline_click_scroll_state["stableCalls"] == []
                    and len(outline_click_scroll_state["itemCalls"]) == 1
                    and outline_click_scroll_state["itemCalls"][0][1] == outline_click_scroll_state["target"]["itemIndex"]
                    and outline_click_scroll_state["itemCalls"][0][2].get("block") == "start"
                    and outline_click_scroll_state["indexCalls"] == []
                ):
                    pass_("presenter-outline-click-prefers-item-scroll", json.dumps(outline_click_scroll_state, ensure_ascii=False))
                else:
                    fail("presenter-outline-click-prefers-item-scroll", json.dumps(outline_click_scroll_state, ensure_ascii=False))

                outline_stale_index_state = page.evaluate(
                    """
                    (serviceId) => {
                      preparePresenterService(serviceId);
                      renderServiceList();
                      renderPresenterControlState(serviceId);
                      const slides = presenterSlidesForService(serviceId);
                      const rows = [...document.querySelectorAll('.service-outline-row--child[data-service-outline-slide][data-service-outline-item-index][data-service-outline-item-id]')]
                        .filter((node) => Number(node.dataset.serviceOutlineItemIndex) >= 0 && Number(node.dataset.serviceOutlineSlide) >= 0);
                      if (rows.length < 2) return { hasRows: false, rowCount: rows.length };
                      const beforeIndex = state.presenter.index;
                      const targetRow = rows.find((node) => {
                        const item = serviceOutlineItemForIndex(serviceId, Number(node.dataset.serviceOutlineItemIndex));
                        const expected = item ? firstPresenterSlideIndexForServiceItem(item, slides) : -1;
                        return expected >= 0
                          && expected !== beforeIndex
                          && rows.some((other) => Number(other.dataset.serviceOutlineSlide) !== expected);
                      }) || rows[0];
                      const item = serviceOutlineItemForIndex(serviceId, Number(targetRow.dataset.serviceOutlineItemIndex));
                      const expectedSlide = item ? firstPresenterSlideIndexForServiceItem(item, slides) : -1;
                      const staleSlide = rows
                        .map((node) => Number(node.dataset.serviceOutlineSlide))
                        .find((index) => Number.isFinite(index) && index >= 0 && index !== expectedSlide);
                      if (!item || expectedSlide < 0 || staleSlide === undefined) {
                        return { hasRows: true, canTest: false, expectedSlide, staleSlide };
                      }
                      targetRow.dataset.serviceOutlineSlide = String(staleSlide);
                      targetRow.click();
                      const afterClickIndex = state.presenter.index;
                      targetRow.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
                      return {
                        hasRows: true,
                        canTest: true,
                        expectedSlide,
                        staleSlide,
                        beforeIndex,
                        afterClickIndex,
                        afterDoubleClickIndex: state.presenter.index,
                        presenterIndex: state.presenter.index,
                        selectedItemIndex: state.selectedServiceItemIndex,
                        expectedItemIndex: Number(targetRow.dataset.serviceOutlineItemIndex),
                      };
                    }
                    """,
                    selection_state["switchId"],
                )
                if (
                    outline_stale_index_state["hasRows"]
                    and outline_stale_index_state["canTest"]
                    and outline_stale_index_state["staleSlide"] != outline_stale_index_state["expectedSlide"]
                    and outline_stale_index_state["beforeIndex"] != outline_stale_index_state["expectedSlide"]
                    and outline_stale_index_state["afterClickIndex"] == outline_stale_index_state["beforeIndex"]
                    and outline_stale_index_state["afterDoubleClickIndex"] == outline_stale_index_state["expectedSlide"]
                    and outline_stale_index_state["presenterIndex"] == outline_stale_index_state["expectedSlide"]
                    and outline_stale_index_state["selectedItemIndex"] == outline_stale_index_state["expectedItemIndex"]
                ):
                    pass_("presenter-outline-click-ignores-stale-slide-index", json.dumps(outline_stale_index_state, ensure_ascii=False))
                else:
                    fail("presenter-outline-click-ignores-stale-slide-index", json.dumps(outline_stale_index_state, ensure_ascii=False))

                next_prep_state = page.evaluate(
                    """
                    (() => {
                      const previous = {
                        services: state.services,
                        serviceItems: state.serviceItems,
                        selectedServiceId: state.selectedServiceId,
                        selectedServiceTypeId: state.selectedServiceTypeId,
                        presenter: { ...state.presenter },
                      };
                      const services = [
                        { id: '__smoke_next_first__', type_id: 'sunday-first', date: '2099-07-05', title: '' },
                        { id: '__smoke_next_youth__', type_id: 'youth', date: '2099-07-05', title: '' },
                        { id: '__smoke_next_young__', type_id: 'young-adult', date: '2099-07-05', title: '' },
                        { id: '__smoke_next_second__', type_id: 'sunday-second', date: '2099-07-05', title: '' },
                        { id: '__smoke_next_third__', type_id: 'sunday-main', date: '2099-07-05', title: '' },
                        { id: '__smoke_next_afternoon__', type_id: 'sunday-afternoon', date: '2099-07-05', title: '' },
                      ];
                      try {
                        state.services = previous.services
                          .filter((service) => !service.id.startsWith('__smoke_next_'))
                          .concat(services);
                        state.serviceItems = { ...previous.serviceItems };
                        services.forEach((service) => { state.serviceItems[service.id] = []; });
                        state.selectedServiceId = '__smoke_next_first__';
                        state.selectedServiceTypeId = 'sunday-first';
                        state.presenter = {
                          ...state.presenter,
                          serviceId: '',
                          slides: [],
                          index: 0,
                          safetyBlank: false,
                          outputWindow: null,
                          outputConnectedAt: 0,
                        };
                        preparePresenterService('__smoke_next_first__');
                        renderPresenterDetail();
                        const button = document.querySelector('[data-presenter-action="prepare-next-service"]');
                        const before = {
                          text: button?.textContent.replace(/\\s+/g, ' ').trim() || '',
                          nextServiceId: button?.dataset.nextServiceId || '',
                          isBoardFooter: button?.parentElement?.parentElement?.classList.contains('svc-slide-board') || false,
                          isInsideSection: Boolean(button?.closest('.svc-board-section')),
                          nextFromFirst: nextPreparationService(state.services.find((service) => service.id === '__smoke_next_first__'))?.id || '',
                          nextFromSecond: nextPreparationService(state.services.find((service) => service.id === '__smoke_next_second__'))?.id || '',
                          nextFromThird: nextPreparationService(state.services.find((service) => service.id === '__smoke_next_third__'))?.id || '',
                        };
                        button?.click();
                        const after = {
                          selectedServiceId: state.selectedServiceId,
                          selectedServiceTypeId: state.selectedServiceTypeId,
                          presenterServiceId: state.presenter.serviceId,
                          presenterIndex: state.presenter.index,
                          nextFromYouth: nextPreparationService(state.services.find((service) => service.id === '__smoke_next_youth__'))?.id || '',
                        };
                        state.selectedServiceId = '__smoke_next_third__';
                        state.selectedServiceTypeId = 'sunday-main';
                        preparePresenterService('__smoke_next_third__');
                        renderPresenterDetail();
                        const thirdButton = document.querySelector('[data-presenter-action="prepare-next-service"]');
                        const third = {
                          text: thirdButton?.textContent.replace(/\\s+/g, ' ').trim() || '',
                          nextServiceId: thirdButton?.dataset.nextServiceId || '',
                        };
                        const legacyServices = [
                          { id: '__smoke_next_legacy_third__', type_id: '주일예배', date: '2099-07-12', title: '' },
                          { id: '__smoke_next_legacy_afternoon__', type_id: '주일오후예배', date: '2099-07-12', title: '' },
                        ];
                        state.services = state.services
                          .filter((service) => !service.id.startsWith('__smoke_next_legacy_'))
                          .concat(legacyServices);
                        const legacy = {
                          nextFromThird: nextPreparationService(state.services.find((service) => service.id === '__smoke_next_legacy_third__'))?.id || '',
                          thirdDisplay: serviceDisplayTypeName(state.services.find((service) => service.id === '__smoke_next_legacy_third__')),
                          afternoonDisplay: serviceDisplayTypeName(state.services.find((service) => service.id === '__smoke_next_legacy_afternoon__')),
                        };
                        return { before, after, third, legacy };
                      } finally {
                        state.services = previous.services;
                        state.serviceItems = previous.serviceItems;
                        state.selectedServiceId = previous.selectedServiceId;
                        state.selectedServiceTypeId = previous.selectedServiceTypeId;
                        state.presenter = previous.presenter;
                        renderPresenterDetail();
                      }
                    })()
                    """
                )
                if (
                    next_prep_state["before"]["text"] == "다음 예배 준비 청소년부 예배"
                    and next_prep_state["before"]["nextServiceId"] == "__smoke_next_youth__"
                    and next_prep_state["before"]["isBoardFooter"]
                    and not next_prep_state["before"]["isInsideSection"]
                    and next_prep_state["before"]["nextFromFirst"] == "__smoke_next_youth__"
                    and next_prep_state["before"]["nextFromSecond"] == "__smoke_next_third__"
                    and next_prep_state["before"]["nextFromThird"] == "__smoke_next_afternoon__"
                    and next_prep_state["after"]["selectedServiceId"] == "__smoke_next_youth__"
                    and next_prep_state["after"]["selectedServiceTypeId"] == "youth"
                    and next_prep_state["after"]["presenterServiceId"] == "__smoke_next_youth__"
                    and next_prep_state["after"]["presenterIndex"] == 0
                    and next_prep_state["after"]["nextFromYouth"] == "__smoke_next_young__"
                    and next_prep_state["third"]["text"] == "다음 예배 준비 주일오후예배"
                    and next_prep_state["third"]["nextServiceId"] == "__smoke_next_afternoon__"
                    and next_prep_state["legacy"]["nextFromThird"] == "__smoke_next_legacy_afternoon__"
                    and next_prep_state["legacy"]["thirdDisplay"] == "주일예배 [3부]"
                    and next_prep_state["legacy"]["afternoonDisplay"] == "주일오후예배"
                ):
                    pass_("presenter-next-service-prep", json.dumps(next_prep_state, ensure_ascii=False))
                else:
                    fail("presenter-next-service-prep", json.dumps(next_prep_state, ensure_ascii=False))

                fullscreen_ready_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_fullscreen_ready_image_service__',
                        type_id: 'friday',
                        date: '2026-07-03',
                        title: 'Fullscreen Ready Image',
                        leader: '테스트',
                        alias: '',
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({ id: service.type_id, name: '금요기도회', sort_order: 2 });
                      }
                      const smokeSong = state.songs[0] || null;
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_fullscreen_ready_image_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '준비',
                          raw_title: '준비',
                          memo: JSON.stringify({
                            elementType: 'image',
                            asset: {
                              kind: 'image',
                              name: '첫 슬라이드',
                              url: 'assets/worship-backgrounds/26-A1.png',
                            },
                          }),
                        },
                        {
                          id: '__smoke_fullscreen_ready_image_song__',
                          service_id: service.id,
                          sort_order: 2,
                          label: '찬양',
                          raw_title: '금요기도회 찬양',
                          song_id: smokeSong?.id || '',
                          version_id: smokeSong ? getDefaultVersionId(smokeSong) : '',
                          memo: JSON.stringify({
                            slides: ['[Verse 1]\\n보이지 않아도\\n주님만 의지해'],
                          }),
                        },
                      ]);
                      preparePresenterService(service.id);
                      const first = state.presenter.slides[0] || {};
                      const normalizedReadyItem = state.serviceItems[service.id]?.find((item) => item.id === '__smoke_fullscreen_ready_image_item__') || {};
                      const host = document.createElement('div');
                      host.className = 'presenter-output-root no-chromakey';
                      host.innerHTML = renderPresenterFullscreenReadySlide(first);
                      document.body.appendChild(host);
                      const ready = host.querySelector('.presenter-ready-screen');
                      const kicker = host.querySelector('.presenter-ready-screen-kicker');
                      const message = host.querySelector('.presenter-ready-screen-message');
                      const strong = message?.querySelector('strong');
                      const readyStyle = ready ? getComputedStyle(ready) : null;
                      const kickerStyle = kicker ? getComputedStyle(kicker) : null;
                      const messageStyle = message ? getComputedStyle(message) : null;
                      const strongStyle = strong ? getComputedStyle(strong) : null;
                      const field = host.querySelector('.presenter-ready-screen-field');
                      const fieldStyle = field ? getComputedStyle(field) : null;
                      const logo = host.querySelector('.presenter-ready-screen-logo');
                      const kickerRect = kicker?.getBoundingClientRect();
                      const messageRect = message?.getBoundingClientRect();
                      const logoRect = logo?.getBoundingClientRect();
                      const readyMessage = {
                        kickerText: kicker?.textContent || '',
                        kickerWeight: kickerStyle?.fontWeight || '',
                        kickerFontSize: parseFloat(kickerStyle?.fontSize || '0') || 0,
                        kickerHeight: kickerRect?.height || 0,
                        text: message?.textContent || '',
                        messageFontSize: parseFloat(messageStyle?.fontSize || '0') || 0,
                        strongText: strong?.textContent || '',
                        messageWeight: messageStyle?.fontWeight || '',
                        strongWeight: strongStyle?.fontWeight || '',
                        backgroundImage: readyStyle?.backgroundImage || '',
                        backgroundColor: readyStyle?.backgroundColor || '',
                        fieldDisplay: fieldStyle?.display || '',
                        logoHeight: logoRect?.height || 0,
                        gapAboveMessage: messageRect && kickerRect ? messageRect.top - kickerRect.bottom : 0,
                        gapBelowMessage: logoRect && messageRect ? logoRect.top - messageRect.bottom : 0,
                      };
                      host.remove();
                      return {
                        chromakey: presenterServiceUsesChromakey(service),
                        slideCount: state.presenter.slides.length,
                        type: first.type || '',
                        elementType: first.elementType || '',
                        layout: first.layout || '',
                        imageSrc: first.imageSrc || '',
                        title: first.title || '',
                        readyServiceName: first.readyServiceName || '',
                        text: first.text || '',
                        readyMessage,
                        normalizedRawTitle: normalizedReadyItem.raw_title || '',
                      };
                    }
                    """
                )
                if (
                    fullscreen_ready_state["chromakey"] is False
                    and fullscreen_ready_state["slideCount"] >= 2
                    and fullscreen_ready_state["type"] == "ready"
                    and fullscreen_ready_state["elementType"] == "image"
                    and fullscreen_ready_state["layout"] == "media"
                    and fullscreen_ready_state["imageSrc"] == ""
                    and fullscreen_ready_state["readyServiceName"] == "금요기도회"
                    and fullscreen_ready_state["text"] == "잠시 후\n금요기도회\n가 시작됩니다"
                    and fullscreen_ready_state["readyMessage"]["kickerText"] == "지금은 기도로 예배를 준비하는 시간입니다"
                    and "url(" not in fullscreen_ready_state["readyMessage"]["backgroundImage"]
                    and fullscreen_ready_state["readyMessage"]["backgroundColor"] == "rgb(0, 0, 0)"
                    and fullscreen_ready_state["readyMessage"]["fieldDisplay"] == "none"
                    and fullscreen_ready_state["readyMessage"]["kickerFontSize"] < fullscreen_ready_state["readyMessage"]["messageFontSize"]
                    and 36 <= fullscreen_ready_state["readyMessage"]["kickerHeight"] <= 52
                    and 40 <= fullscreen_ready_state["readyMessage"]["logoHeight"] <= 58
                    and 18 <= fullscreen_ready_state["readyMessage"]["gapAboveMessage"] <= 32
                    and fullscreen_ready_state["readyMessage"]["gapBelowMessage"] >= 180
                    and 72 <= fullscreen_ready_state["readyMessage"]["messageFontSize"] <= 78
                    and fullscreen_ready_state["readyMessage"]["text"] == "잠시 후 금요기도회가 시작됩니다"
                    and fullscreen_ready_state["readyMessage"]["strongText"] == "금요기도회"
                    and int(fullscreen_ready_state["readyMessage"]["strongWeight"]) > int(fullscreen_ready_state["readyMessage"]["messageWeight"])
                    and fullscreen_ready_state["normalizedRawTitle"] == ""
                ):
                    pass_("presenter-fullscreen-ready-image", json.dumps(fullscreen_ready_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-ready-image", json.dumps(fullscreen_ready_state, ensure_ascii=False))

                friday_ready_default_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_friday_ready_default_image_service__',
                        type_id: 'friday',
                        date: '2026-07-10',
                        title: 'Friday Ready Default Image',
                        leader: '테스트',
                        alias: '',
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({ id: service.type_id, name: '금요기도회', sort_order: 2 });
                      }
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_friday_ready_default_image_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '준비',
                          raw_title: '준비',
                          memo: '',
                        },
                      ]);
                      preparePresenterService(service.id);
                      const first = state.presenter.slides[0] || {};
                      return {
                        chromakey: presenterServiceUsesChromakey(service),
                        type: first.type || '',
                        elementType: first.elementType || '',
                        layout: first.layout || '',
                        imageSrc: first.imageSrc || '',
                        title: first.title || '',
                        elementLabel: first.elementLabel || '',
                        readyServiceName: first.readyServiceName || '',
                        videoSrc: first.videoSrc || '',
                      };
                    }
                    """
                )
                if (
                    friday_ready_default_state["chromakey"] is False
                    and friday_ready_default_state["type"] == "ready"
                    and friday_ready_default_state["elementType"] == "image"
                    and friday_ready_default_state["layout"] == "media"
                    and friday_ready_default_state["imageSrc"] == ""
                    and friday_ready_default_state["videoSrc"] == ""
                    and friday_ready_default_state["elementLabel"] == "대기 화면"
                    and friday_ready_default_state["readyServiceName"] == "금요기도회"
                ):
                    pass_("presenter-friday-ready-default-image", json.dumps(friday_ready_default_state, ensure_ascii=False))
                else:
                    fail("presenter-friday-ready-default-image", json.dumps(friday_ready_default_state, ensure_ascii=False))

                friday_legacy_waiting_loop_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_friday_legacy_waiting_loop_service__',
                        type_id: 'friday',
                        date: '2026-07-17',
                        title: 'Friday Legacy Waiting Loop',
                        leader: '테스트',
                        alias: '',
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({ id: service.type_id, name: '금요기도회', sort_order: 2 });
                      }
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_friday_legacy_waiting_loop_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '대기 화면',
                          raw_title: '대기 화면',
                          memo: JSON.stringify({ presenterRole: 'waiting_loop' }),
                        },
                      ]);
                      preparePresenterService(service.id);
                      const first = state.presenter.slides[0] || {};
                      return {
                        chromakey: presenterServiceUsesChromakey(service),
                        type: first.type || '',
                        elementType: first.elementType || '',
                        layout: first.layout || '',
                        imageSrc: first.imageSrc || '',
                        videoSrc: first.videoSrc || '',
                        presenterRole: first.presenterRole || '',
                        outputContext: first.outputContext || '',
                      };
                    }
                    """
                )
                if (
                    friday_legacy_waiting_loop_state["chromakey"] is False
                    and friday_legacy_waiting_loop_state["type"] == "ready"
                    and friday_legacy_waiting_loop_state["elementType"] == "image"
                    and friday_legacy_waiting_loop_state["layout"] == "media"
                    and friday_legacy_waiting_loop_state["imageSrc"] == ""
                    and friday_legacy_waiting_loop_state["videoSrc"] == ""
                    and friday_legacy_waiting_loop_state["presenterRole"] == "ready"
                    and friday_legacy_waiting_loop_state["outputContext"] == "clean"
                ):
                    pass_("presenter-friday-legacy-waiting-loop-normalized", json.dumps(friday_legacy_waiting_loop_state, ensure_ascii=False))
                else:
                    fail("presenter-friday-legacy-waiting-loop-normalized", json.dumps(friday_legacy_waiting_loop_state, ensure_ascii=False))

                chromakey_explicit_ready_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_chromakey_explicit_ready_service__',
                        type_id: '__smoke_chromakey_explicit_ready_type__',
                        date: '2026-09-01',
                        title: 'Chromakey Explicit Ready',
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({
                          id: service.type_id,
                          name: 'Chromakey Smoke',
                          sort_order: 999,
                          _worship: true,
                          _worshipChromakey: true,
                          _worshipOutputContext: 'chromakey',
                          fixed_items: [],
                        });
                      }
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_chromakey_explicit_ready_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '대기 화면',
                          raw_title: '',
                          memo: JSON.stringify({ presenterRole: 'ready' }),
                        },
                      ]);
                      preparePresenterService(service.id);
                      const first = state.presenter.slides.find((slide) => slide.elementId === '__smoke_chromakey_explicit_ready_item__') || {};
                      return {
                        chromakey: presenterServiceUsesChromakey(service),
                        type: first.type || '',
                        elementType: first.elementType || '',
                        presenterRole: first.presenterRole || '',
                        imageSrc: first.imageSrc || '',
                        videoSrc: first.videoSrc || '',
                      };
                    }
                    """
                )
                if (
                    chromakey_explicit_ready_state["chromakey"] is True
                    and chromakey_explicit_ready_state["type"] == "ready"
                    and chromakey_explicit_ready_state["elementType"] == "image"
                    and chromakey_explicit_ready_state["presenterRole"] == "ready"
                    and chromakey_explicit_ready_state["videoSrc"] == ""
                ):
                    pass_("presenter-chromakey-explicit-ready-screen", json.dumps(chromakey_explicit_ready_state, ensure_ascii=False))
                else:
                    fail("presenter-chromakey-explicit-ready-screen", json.dumps(chromakey_explicit_ready_state, ensure_ascii=False))

                friday_ready_background_guard = page.evaluate(
                    """
                    () => {
                      const directService = {
                        id: '__smoke_friday_ready_background_guard_direct__',
                        type_id: 'friday',
                        date: '2026-07-10',
                        presenter_background: 'assets/presenter/friday-prayer-ready.png',
                      };
                      const legacyService = {
                        id: '__smoke_friday_ready_background_guard_legacy__',
                        type_id: 'friday',
                        date: '2026-07-10',
                        presenter_background: 'assets/worship-backgrounds/friday-prayer-ready.png',
                      };
                      const normalService = {
                        id: '__smoke_friday_ready_background_guard_normal__',
                        type_id: 'friday',
                        date: '2026-07-10',
                      };
                      return {
                        direct: presenterBackgroundSourcesForService(directService),
                        legacy: presenterBackgroundSourcesForService(legacyService),
                        normal: presenterBackgroundSourcesForService(normalService),
                      };
                    }
                    """
                )
                if (
                    any("26-B4.png" in source for source in friday_ready_background_guard["direct"])
                    and any("26-B4.png" in source for source in friday_ready_background_guard["legacy"])
                    and all("friday-prayer-ready" not in source for source in friday_ready_background_guard["normal"])
                    and all("friday-prayer-ready" not in source for source in friday_ready_background_guard["direct"])
                    and all("friday-prayer-ready" not in source for source in friday_ready_background_guard["legacy"])
                ):
                    pass_("presenter-friday-ready-background-guard", json.dumps(friday_ready_background_guard, ensure_ascii=False))
                else:
                    fail("presenter-friday-ready-background-guard", json.dumps(friday_ready_background_guard, ensure_ascii=False))

                default_background_state = page.evaluate(
                    """
                    () => {
                      const cases = [
                        { type_id: 'sunday-first', date: '2026-07-05', expected: '26-A4.png', defaultFile: '26-A4.png', seasonFile: '26-SH.png', chromakey: false },
                        { type_id: 'young-adult', date: '2026-01-04', expected: '26-A1.png', defaultFile: '26-A1.png', seasonFile: '', chromakey: false },
                        { type_id: 'friday', date: '2026-03-06', expected: '26-B2.png', defaultFile: '26-B2.png', seasonFile: '', chromakey: false },
                        { type_id: 'friday', date: '2026-07-24', expected: '26-B4.png', defaultFile: '26-B4.png', seasonFile: '', chromakey: false },
                        { type_id: 'friday', date: '2026-08-21', alias: '삼삼오오예배', sourceRef: { friday_variant: '3355', friday_variant_name: '삼삼오오예배' }, expected: '26-B4.png', defaultFile: '26-B4.png', seasonFile: '', chromakey: false },
                        { type_id: 'friday', date: '2026-08-28', alias: '구역연합예배', sourceRef: { friday_variant: 'district-union', friday_variant_name: '구역연합예배' }, expected: '', defaultFile: '26-B4.png', seasonFile: '', chromakey: true },
                        { type_id: 'youth', date: '2026-01-04', expected: '26-B1.png', defaultFile: '26-B1.png', seasonFile: '', chromakey: false },
                        { type_id: 'children', date: '2026-01-04', expected: '26-C1.png', defaultFile: '26-C1.png', seasonFile: '', chromakey: false },
                        { type_id: 'sunday-first', date: '2026-03-29', calendarNote: '종려주일', expected: '26-S4.png', defaultFile: '26-A2.png', seasonFile: '26-S4.png', chromakey: false },
                        { type_id: 'sunday-first', date: '2026-04-05', calendarNote: '부활주일', expected: '26-S5.png', defaultFile: '26-A2.png', seasonFile: '26-S5.png', chromakey: false },
                        { type_id: 'sunday-first', date: '2026-05-24', calendarNote: '성령강림주일', expected: '26-S6.png', defaultFile: '26-A3.png', seasonFile: '26-S6.png', chromakey: false },
                        { type_id: 'sunday-first', date: '2026-07-05', calendarNote: '맥추감사주일', expected: '26-A4.png', defaultFile: '26-A4.png', seasonFile: '26-SH.png', chromakey: false },
                        { type_id: 'sunday-first', date: '2026-11-15', calendarNote: '추수감사주일', expected: '', defaultFile: '26-A6.png', seasonFile: '26-ST.png', chromakey: false },
                        { type_id: 'sunday-first', date: '2027-01-03', expected: '', defaultFile: '27-A1.png', seasonFile: '', chromakey: false },
                        { type_id: 'sunday-second', date: '2026-07-05', expected: '', defaultFile: '26-A4.png', seasonFile: '26-SH.png', chromakey: true },
                        { type_id: 'sunday-main', date: '2026-07-05', expected: '', defaultFile: '26-A4.png', seasonFile: '26-SH.png', chromakey: true },
                        { type_id: 'sunday-main', date: '2026-08-23', alias: '온세대 찬양예배', sourceRef: { sunday_main_variant: 'all_generations' }, expected: '', defaultFile: '26-A4.png', seasonFile: '', chromakey: true },
                        { type_id: 'wednesday', date: '2026-07-08', expected: '', defaultFile: '', seasonFile: '', chromakey: true },
                        { type_id: 'monthly', date: '2026-07-03', expected: '', defaultFile: '', seasonFile: '', chromakey: true },
                      ];
                      const previousCalendarData = state.calendarData;
                      state.calendarData = cases.filter((entry) => entry.calendarNote).map((entry) => ({ date: entry.date, note: entry.calendarNote }));
                      const result = cases.map((entry) => {
                        const service = {
                          id: `__smoke_default_bg_${entry.type_id}__`,
                          type_id: entry.type_id,
                          date: entry.date,
                          title: '',
                          alias: entry.alias || '',
                          _worshipSourceRef: entry.sourceRef || {},
                        };
                        return {
                          ...entry,
                          actualChromakey: presenterServiceUsesChromakey(service),
                          actualDefaultFile: presenterDefaultBackgroundFileNameForService(service),
                          actualSeasonFile: presenterSeasonBackgroundFileNameForService(service),
                          sources: presenterBackgroundSourcesForService(service),
                        };
                      });
                      state.calendarData = previousCalendarData;
                      return result;
                    }
                    """
                )
                default_background_ok = all(
                    item["actualChromakey"] == item["chromakey"]
                    and item["actualDefaultFile"] == item["defaultFile"]
                    and item["actualSeasonFile"] == item["seasonFile"]
                    and ((item["expected"] and any(item["expected"] in source for source in item["sources"])) or (not item["expected"] and item["sources"] == []))
                    for item in default_background_state
                )
                if default_background_ok:
                    pass_("presenter-default-background-groups", json.dumps(default_background_state, ensure_ascii=False))
                else:
                    fail("presenter-default-background-groups", json.dumps(default_background_state, ensure_ascii=False))

                all_generations_preview_state = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_all_generations_chromakey_preview__',
                        type_id: 'sunday-main',
                        date: '2026-08-23',
                        title: '온세대 찬양예배',
                        alias: '온세대 찬양예배',
                        _worshipSourceRef: { sunday_main_variant: 'all_generations' },
                      };
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      const slide = {
                        id: '__smoke_all_generations_bongheon_song_title__',
                        type: 'song-title',
                        elementType: 'praise',
                        layout: 'lower_bar_text',
                        sectionKey: 'offering',
                        sectionLabel: '봉헌',
                        title: '말할 수 없는 영광스러운 즐거움으로',
                        text: '말할 수 없는 영광스러운 즐거움으로',
                      };
                      const mount = document.createElement('div');
                      mount.innerHTML = renderPresenterSlideMiniPreview(slide, service.id);
                      document.body.append(mount);
                      const frame = mount.querySelector('.svc-slide-mini-output');
                      const root = mount.querySelector('.presenter-output-root');
                      const title = mount.querySelector('.presenter-slide--song-title');
                      const beforeContent = title ? getComputedStyle(title, '::before').content : '';
                      const result = {
                        chromakey: presenterServiceUsesChromakey(service),
                        frameNoChromakey: frame?.classList.contains('no-chromakey') || false,
                        rootNoChromakey: root?.classList.contains('no-chromakey') || false,
                        hasBackground: frame?.classList.contains('has-background') || false,
                        beforeContent,
                      };
                      mount.remove();
                      return result;
                    }
                    """
                )
                if (
                    all_generations_preview_state["chromakey"] is True
                    and all_generations_preview_state["frameNoChromakey"] is False
                    and all_generations_preview_state["rootNoChromakey"] is False
                    and all_generations_preview_state["hasBackground"] is False
                    and all_generations_preview_state["beforeContent"] in ["none", '""']
                ):
                    pass_("presenter-all-generations-chromakey-preview", json.dumps(all_generations_preview_state, ensure_ascii=False))
                else:
                    fail("presenter-all-generations-chromakey-preview", json.dumps(all_generations_preview_state, ensure_ascii=False))

                friday_legacy_background_state = page.evaluate(
                    """
                    () => presenterBackgroundSourcesForService({
                      id: '__smoke_friday_legacy_background__',
                      type_id: 'friday',
                      date: '2026-07-24',
                      _worshipSourceRef: { presenter_background: '26-B4.png' },
                    })
                    """
                )
                if any("26-B4.png" in source for source in friday_legacy_background_state):
                    pass_("presenter-friday-legacy-background-migration", json.dumps(friday_legacy_background_state, ensure_ascii=False))
                else:
                    fail("presenter-friday-legacy-background-migration", json.dumps(friday_legacy_background_state, ensure_ascii=False))

                no_chromakey_payload = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_presenter_background_service__',
                        type_id: 'friday',
                        date: '2026-03-06',
                        title: 'No Chroma Smoke',
                        leader: '테스트',
                        alias: '',
                      };
                      const missingBackgroundFile = presenterDefaultBackgroundFileNameForService(service);
                      WORSHIP_BACKGROUND_STATIC_FILES.delete(missingBackgroundFile);
                      delete state.worshipBackgroundRegistry[missingBackgroundFile];
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({ id: service.type_id, name: '금요기도회', sort_order: 2 });
                      }
                      const smokeSong = state.songs[0] || null;
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_presenter_background_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '찬양',
                          raw_title: '금요기도회 찬양',
                          song_id: smokeSong?.id || '',
                          version_id: smokeSong ? getDefaultVersionId(smokeSong) : '',
                          memo: JSON.stringify({
                            slides: ['[Verse 1]\\n보이지 않아도\\n주님만 의지해'],
                          }),
                        },
                      ]);
                      preparePresenterService(service.id);
                      const lyricsIndex = state.presenter.slides.findIndex((slide) => slide.type === 'lyrics');
                      state.presenter.index = lyricsIndex >= 0
                        ? lyricsIndex
                        : Math.min(2, Math.max(state.presenter.slides.length - 1, 0));
                      state.presenter.liveScripture = { reference: "", draft: "", active: false, slide: null };
                      state.presenter.livePraise = { query: "", draft: "", active: false, slides: [], index: 0, songId: "", versionId: "" };
                      state.module = 'presenter';
                      state.selectedServiceTypeId = service.type_id;
                      state.selectedServiceId = service.id;
                      renderPresenterDetail();
                      publishPresenterState({ force: true });
                      const payload = presenterStatePayload(service.id);
                      WORSHIP_BACKGROUND_STATIC_FILES.add(missingBackgroundFile);
                      return payload;
                    }
                    """
                )
                output_page.wait_for_function(
                    "(serviceId) => (readPresenterStoredPayload() || {}).serviceId === serviceId",
                    arg=no_chromakey_payload["serviceId"],
                    timeout=5000,
                )
                no_chromakey_state = output_page.evaluate(
                    """
                    (() => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slide = root?.querySelector('.presenter-slide');
                      const styles = root ? getComputedStyle(root) : null;
                      return {
                        serviceType: root?.dataset.serviceType || '',
                        outputTheme: root?.dataset.outputTheme || '',
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        hasBackground: root?.classList.contains('has-background') || false,
                        slideClass: slide ? [...slide.classList].find((name) => name.startsWith('presenter-slide--') && name !== 'presenter-slide') : '',
                        elementType: slide?.dataset.elementType || '',
                        layout: slide?.dataset.slideLayout || '',
                        inlineBackground: root?.style.getPropertyValue('--presenter-bg-image') || '',
                        computedBackground: styles?.backgroundImage || '',
                        backgroundColor: styles?.backgroundColor || '',
                        text: slide?.innerText.trim() || '',
                        overflow: Math.max(
                          document.documentElement.scrollWidth - window.innerWidth,
                          document.documentElement.scrollHeight - window.innerHeight,
                          document.body.scrollWidth - window.innerWidth,
                          document.body.scrollHeight - window.innerHeight
                        ),
                      };
                    })()
                    """
                )
                if (
                    no_chromakey_payload["chromakey"] is False
                    and no_chromakey_payload["backgroundImage"] == ""
                    and no_chromakey_state["serviceType"] == no_chromakey_payload["serviceType"]
                    and no_chromakey_state["noChromakey"]
                    and no_chromakey_state["hasBackground"]
                    and "url(" in no_chromakey_state["inlineBackground"]
                    and "url(" in no_chromakey_state["computedBackground"]
                    and no_chromakey_state["slideClass"] == "presenter-slide--lyrics"
                    and no_chromakey_state["elementType"] == "praise"
                    and no_chromakey_state["layout"] == "lower_bar_text"
                    and no_chromakey_state["overflow"] <= 2
                ):
                    pass_("presenter-output-no-chromakey", json.dumps(no_chromakey_state, ensure_ascii=False))
                else:
                    fail(
                        "presenter-output-no-chromakey",
                        json.dumps({"payload": no_chromakey_payload, "output": no_chromakey_state}, ensure_ascii=False),
                    )

                current_presenter_index = page.evaluate("state.presenter.index")
                page.wait_for_function(
                    "(index) => Boolean(document.querySelector(`.svc-slide-thumb[data-presenter-index=\"${index}\"] .svc-slide-mini-output`))",
                    arg=current_presenter_index,
                    timeout=5000,
                )
                page.wait_for_timeout(250)
                no_chromakey_thumb_shot = screenshot_with_retry(page, page.locator(f'.svc-slide-thumb[data-presenter-index="{current_presenter_index}"] .svc-slide-mini-output').first)
                no_chromakey_output_shot = output_page.locator("#presenterOutputRoot").screenshot()
                no_chromakey_pixels = {
                    "thumbTop": rgb_at(no_chromakey_thumb_shot, 0.5, 0.16),
                    "thumbBottom": rgb_at(no_chromakey_thumb_shot, 0.5, 0.92),
                    "outputTop": rgb_at(no_chromakey_output_shot, 0.5, 0.16),
                    "outputBottom": rgb_at(no_chromakey_output_shot, 0.5, 0.92),
                }
                if not any(is_chromakey_green(rgb) for rgb in no_chromakey_pixels.values()):
                    pass_("presenter-output-pixel-match-no-chromakey", json.dumps(no_chromakey_pixels, ensure_ascii=False))
                else:
                    fail("presenter-output-pixel-match-no-chromakey", json.dumps(no_chromakey_pixels, ensure_ascii=False))

                fullscreen_transition_state = output_page.evaluate(
                    """
                    async () => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slides = [
                        {
                          id: '__smoke_transition_old__',
                          type: 'title-content',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '이전 화면',
                          text: '이전 화면',
                          outputContext: 'clean',
                        },
                        {
                          id: '__smoke_transition_next__',
                          type: 'title-content',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '다음 화면',
                          text: '다음 화면',
                          outputContext: 'clean',
                        },
                      ];
                      await preloadPresenterOutputImage(PRESENTER_SCRIPTURE_READING_BACKGROUND);
                      renderPresenterOutput({
                        serviceId: '__smoke_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: '',
                        slides,
                        index: 0,
                        safetyBlank: false,
                      });
                      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                      renderPresenterOutput({
                        serviceId: '__smoke_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: '',
                        slides,
                        index: 1,
                        safetyBlank: false,
                      });
                      for (let attempt = 0; attempt < 40; attempt += 1) {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        if (root.querySelector('.presenter-output-layer.is-active .presenter-slide--scripture-reading')) break;
                      }
                      const active = root.querySelector('.presenter-output-layer.is-active');
                      const entering = root.querySelector('.presenter-output-layer.is-entering');
                      const exiting = root.querySelector('.presenter-output-layer.is-exiting');
                      return {
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        activeText: active?.innerText.trim() || '',
                        enteringCount: entering ? 1 : 0,
                        exitingCount: exiting ? 1 : 0,
                      };
                    }
                    """
                )
                if (
                    fullscreen_transition_state["noChromakey"]
                    and "다음 화면" in fullscreen_transition_state["activeText"]
                    and fullscreen_transition_state["enteringCount"] == 0
                    and fullscreen_transition_state["exitingCount"] == 0
                ):
                    pass_("presenter-fullscreen-no-fade-transition", json.dumps(fullscreen_transition_state, ensure_ascii=False))
                else:
                    fail("presenter-fullscreen-no-fade-transition", json.dumps(fullscreen_transition_state, ensure_ascii=False))

                scripture_reading_transition_state = output_page.evaluate(
                    """
                    async () => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slides = [
                        {
                          id: '__smoke_scripture_reading_transition_old__',
                          type: 'scripture',
                          elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '성경봉독',
                          text: '이전 본문',
                          outputContext: 'clean',
                          scriptureContext: 'reading',
                        },
                        {
                          id: '__smoke_scripture_reading_transition_next__',
                          type: 'scripture',
                          elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '성경봉독',
                          text: '다음 본문',
                          outputContext: 'clean',
                          scriptureContext: 'reading',
                        },
                      ];
                      renderPresenterOutput({
                        serviceId: '__smoke_scripture_reading_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: 'assets/worship-backgrounds/26-B2.png',
                        slides,
                        index: 0,
                        safetyBlank: false,
                      });
                      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                      renderPresenterOutput({
                        serviceId: '__smoke_scripture_reading_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: 'assets/worship-backgrounds/26-B2.png',
                        slides,
                        index: 1,
                        safetyBlank: false,
                      });
                      for (let attempt = 0; attempt < 40; attempt += 1) {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        if (root.querySelector('.presenter-output-layer.is-active .presenter-slide--scripture-reading')) break;
                      }
                      const active = root.querySelector('.presenter-output-layer.is-active');
                      return {
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        activeText: active?.innerText.trim() || '',
                        activeIsReading: Boolean(active?.querySelector('.presenter-slide--scripture-reading')),
                        enteringCount: root.querySelectorAll('.presenter-output-layer.is-entering').length,
                        exitingCount: root.querySelectorAll('.presenter-output-layer.is-exiting').length,
                      };
                    }
                    """
                )
                if (
                    scripture_reading_transition_state["noChromakey"]
                    and "다음 본문" in scripture_reading_transition_state["activeText"]
                    and scripture_reading_transition_state["activeIsReading"]
                    and scripture_reading_transition_state["enteringCount"] == 0
                    and scripture_reading_transition_state["exitingCount"] == 0
                ):
                    pass_("presenter-scripture-reading-no-fade-transition", json.dumps(scripture_reading_transition_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-reading-no-fade-transition", json.dumps(scripture_reading_transition_state, ensure_ascii=False))

                score_transition_state = output_page.evaluate(
                    """
                    async () => {
                      const root = document.getElementById('presenterOutputRoot');
                      const slides = [
                        {
                          id: '__smoke_score_transition_old__',
                          type: 'title-content',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '이전 악보',
                          text: '이전 악보',
                          outputContext: 'clean',
                          sourceType: 'score',
                          componentType: 'score',
                        },
                        {
                          id: '__smoke_score_transition_next__',
                          type: 'title-content',
                          elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
                          layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
                          title: '다음 악보',
                          text: '다음 악보',
                          outputContext: 'clean',
                          sourceType: 'score',
                          componentType: 'score',
                        },
                      ];
                      renderPresenterOutput({
                        serviceId: '__smoke_score_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: '',
                        slides,
                        index: 0,
                        safetyBlank: false,
                      });
                      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                      renderPresenterOutput({
                        serviceId: '__smoke_score_transition_service__',
                        serviceType: 'friday',
                        chromakey: false,
                        outputTheme: 'formal',
                        backgroundImage: '',
                        slides,
                        index: 1,
                        safetyBlank: false,
                      });
                      await new Promise((resolve) => setTimeout(resolve, 120));
                      const active = root.querySelector('.presenter-output-layer.is-active');
                      return {
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        activeText: active?.innerText.trim() || '',
                        activeIsScore: Boolean(active?.querySelector('.presenter-slide--score')),
                        enteringCount: root.querySelectorAll('.presenter-output-layer.is-entering').length,
                        exitingCount: root.querySelectorAll('.presenter-output-layer.is-exiting').length,
                      };
                    }
                    """
                )
                if (
                    score_transition_state["noChromakey"]
                    and "다음 악보" in score_transition_state["activeText"]
                    and score_transition_state["activeIsScore"]
                    and score_transition_state["enteringCount"] == 0
                    and score_transition_state["exitingCount"] == 0
                ):
                    pass_("presenter-score-no-fade-transition", json.dumps(score_transition_state, ensure_ascii=False))
                else:
                    fail("presenter-score-no-fade-transition", json.dumps(score_transition_state, ensure_ascii=False))

                explicit_background_payload = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_presenter_explicit_background_service__',
                        type_id: 'youth',
                        date: '2026-07-05',
                        title: 'Explicit Background Smoke',
                        leader: '테스트',
                        alias: '',
                        _worshipSourceRef: { presenter_background: '26-B2.png' },
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({
                          id: service.type_id,
                          name: '청소년부 예배',
                          sort_order: 5,
                          _worship: true,
                          _worshipOutputContext: 'clean',
                          _worshipChromakey: false,
                        });
                      }
                      const smokeSong = state.songs[0] || null;
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_presenter_explicit_background_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '찬양',
                          raw_title: '청소년부 찬양',
                          song_id: smokeSong?.id || '',
                          version_id: smokeSong ? getDefaultVersionId(smokeSong) : '',
                          memo: JSON.stringify({
                            slides: ['[Verse 1]\\n주님만 바라봅니다'],
                          }),
                        },
                      ]);
                      preparePresenterService(service.id);
                      return presenterStatePayload(service.id);
                    }
                    """
                )
                if (
                    explicit_background_payload["chromakey"] is False
                    and explicit_background_payload["backgroundImage"].endswith("assets/worship-backgrounds/26-B2.png")
                    and all("26-B4" not in source for source in explicit_background_payload["backgroundImages"])
                ):
                    pass_("presenter-output-explicit-background", json.dumps(explicit_background_payload, ensure_ascii=False))
                else:
                    fail("presenter-output-explicit-background", json.dumps(explicit_background_payload, ensure_ascii=False))

                clean_blank_background_state = output_page.evaluate(
                    """
                    (payload) => {
                      const blankIndex = payload.slides.findIndex((slide) => slide?.layout === 'blank' && slide?.autoTrailingBlank);
                      renderPresenterOutput({ ...payload, index: blankIndex, safetyBlank: false }, {});
                      const root = document.getElementById('presenterOutputRoot');
                      const slide = root?.querySelector('.presenter-slide');
                      const cleanBlank = {
                        blankIndex,
                        hasBackground: root?.classList.contains('has-background') || false,
                        isBlank: root?.classList.contains('is-blank') || false,
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        inlineBackground: root?.style.getPropertyValue('--presenter-bg-image') || '',
                        slideClass: slide?.className || '',
                        text: slide?.innerText.trim() || '',
                      };
                      renderPresenterOutput({ ...payload, index: blankIndex, safetyBlank: true }, {});
                      const safetyRoot = document.getElementById('presenterOutputRoot');
                      const safetySlide = safetyRoot?.querySelector('.presenter-slide');
                      return {
                        cleanBlank,
                        safetyBlank: {
                          hasBackground: safetyRoot?.classList.contains('has-background') || false,
                          isBlank: safetyRoot?.classList.contains('is-blank') || false,
                          noChromakey: safetyRoot?.classList.contains('no-chromakey') || false,
                          inlineBackground: safetyRoot?.style.getPropertyValue('--presenter-bg-image') || '',
                          slideClass: safetySlide?.className || '',
                          text: safetySlide?.innerText.trim() || '',
                        },
                      };
                    }
                    """,
                    explicit_background_payload,
                )
                if (
                    clean_blank_background_state["cleanBlank"]["blankIndex"] >= 0
                    and clean_blank_background_state["cleanBlank"]["hasBackground"]
                    and clean_blank_background_state["cleanBlank"]["isBlank"]
                    and clean_blank_background_state["cleanBlank"]["noChromakey"]
                    and "26-B2.png" in clean_blank_background_state["cleanBlank"]["inlineBackground"]
                    and "presenter-slide--blank" in clean_blank_background_state["cleanBlank"]["slideClass"]
                    and clean_blank_background_state["cleanBlank"]["text"] == ""
                    and clean_blank_background_state["safetyBlank"]["hasBackground"]
                    and clean_blank_background_state["safetyBlank"]["isBlank"]
                    and "26-B2.png" in clean_blank_background_state["safetyBlank"]["inlineBackground"]
                    and "presenter-slide--blank" in clean_blank_background_state["safetyBlank"]["slideClass"]
                    and clean_blank_background_state["safetyBlank"]["text"] == ""
                ):
                    pass_("presenter-clean-blank-keeps-background", json.dumps(clean_blank_background_state, ensure_ascii=False))
                else:
                    fail("presenter-clean-blank-keeps-background", json.dumps(clean_blank_background_state, ensure_ascii=False))

                scripture_blank_background_payload = page.evaluate(
                    """
                    () => {
                      const service = {
                        id: '__smoke_scripture_blank_background_service__',
                        type_id: 'sunday-second',
                        date: '2026-07-05',
                        title: 'Scripture Blank Background Smoke',
                        leader: '테스트',
                        alias: '',
                        _worshipSourceRef: { presenter_background: '26-B2.png' },
                      };
                      if (!state.serviceTypes.some((item) => item.id === service.type_id)) {
                        state.serviceTypes.push({
                          id: service.type_id,
                          name: '주일예배 [2부]',
                          sort_order: 5,
                          _worship: true,
                          _worshipOutputContext: 'chromakey',
                          _worshipChromakey: true,
                        });
                      }
                      if (!state.bibleTranslations.some((translation) => translation.id === '__smoke_ko__')) {
                        state.bibleTranslations.push({
                          id: '__smoke_ko__',
                          translationKey: 'RKB',
                          name: '개역개정',
                          language: 'ko',
                          abbreviation: '개역개정',
                        });
                      }
                      state.selectedBibleTranslationId = '__smoke_ko__';
                      cacheServiceScriptureVerses(parseBibleReference('출 23:14'), [
                        { book_code: 'EXO', chapter: 23, verse: 14, text: '너는 매년 세 번 내게 절기를 지킬지니라' },
                      ]);
                      state.services = [
                        service,
                        ...state.services.filter((item) => item.id !== service.id),
                      ];
                      state.serviceItems[service.id] = normalizeServiceItems([
                        {
                          id: '__smoke_scripture_blank_background_item__',
                          service_id: service.id,
                          sort_order: 1,
                          label: '성경봉독',
                          raw_title: '',
                          memo: JSON.stringify({
                            elementType: 'scripture_body',
                            scriptureReference: '출 23:14',
                          }),
                          _worshipSectionKey: 'scripture_reading',
                          _worshipSectionTitle: '성경봉독',
                        },
                      ]);
                      preparePresenterService(service.id);
                      return presenterStatePayload(service.id);
                    }
                    """
                )
                scripture_blank_background_state = output_page.evaluate(
                    """
                    async (payload) => {
                      const finalIndex = payload.slides.findIndex((slide) =>
                        slide?.type === 'scripture'
                        && slide?.sectionKey === 'scripture_reading'
                        && slide?.scriptureReadingFinal
                      );
                      const blankIndex = finalIndex + 1;
                      const blankModel = payload.slides[blankIndex] || {};
                      renderPresenterOutput({ ...payload, index: finalIndex, safetyBlank: false }, {});
                      const root = document.getElementById('presenterOutputRoot');
                      for (let attempt = 0; attempt < 40; attempt += 1) {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        if (root.querySelector('.presenter-output-layer.is-active .presenter-slide--scripture-reading')) break;
                      }
                      const finalSlide = root?.querySelector('.presenter-slide');
                      const finalState = {
                        hasBackground: root?.classList.contains('has-background') || false,
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        inlineBackground: root?.style.getPropertyValue('--presenter-bg-image') || '',
                        slideClass: finalSlide?.className || '',
                        renderedReference: finalSlide?.querySelector('.presenter-scripture-reading-ref')?.textContent?.trim() || '',
                        fin: finalSlide?.querySelector('.presenter-scripture-reading-fin')?.textContent?.trim() || '',
                      };
                      renderPresenterOutput({ ...payload, index: blankIndex, safetyBlank: false }, {});
                      for (let attempt = 0; attempt < 20; attempt += 1) {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        if (root.querySelector('.presenter-output-layer.is-active .presenter-slide--blank')) break;
                      }
                      const blankSlide = root?.querySelector('.presenter-slide');
                      return {
                        blankIndex,
                        finalIndex,
                        ...finalState,
                        blankIsBlank: blankModel?.layout === 'blank' && Boolean(blankModel?.autoTrailingBlank),
                        blankModelSectionKey: blankModel?.sectionKey || '',
                        blankModelSectionLabel: blankModel?.sectionLabel || '',
                        blankModelLabel: blankModel?.label || '',
                        blankModelScriptureContext: blankModel?.scriptureContext || '',
                        blankModelScriptureReadingFinal: Boolean(blankModel?.scriptureReadingFinal),
                        blankModelOutputContext: blankModel?.outputContext || '',
                        blankHasBackground: root?.classList.contains('has-background') || false,
                        blankNoChromakey: root?.classList.contains('no-chromakey') || false,
                        blankInlineBackground: root?.style.getPropertyValue('--presenter-bg-image') || '',
                        blankSlideClass: blankSlide?.className || '',
                        blankSlideBackground: blankSlide?.style.getPropertyValue('--presenter-slide-bg-image') || '',
                        blankText: blankSlide?.innerText.trim() || '',
                      };
                    }
                    """,
                    scripture_blank_background_payload,
                )
                if (
                    scripture_blank_background_state["blankIndex"] == scripture_blank_background_state["finalIndex"] + 1
                    and scripture_blank_background_state["finalIndex"] >= 0
                    and scripture_blank_background_state["noChromakey"]
                    and not scripture_blank_background_state["hasBackground"]
                    and scripture_blank_background_state["inlineBackground"] == ""
                    and "presenter-slide--scripture-reading" in scripture_blank_background_state["slideClass"]
                    and scripture_blank_background_state["renderedReference"] == "출애굽기 23:14"
                    and scripture_blank_background_state["fin"] == "Fin."
                    and scripture_blank_background_state["blankIsBlank"]
                    and scripture_blank_background_state["blankModelSectionKey"] == ""
                    and scripture_blank_background_state["blankModelSectionLabel"] == ""
                    and scripture_blank_background_state["blankModelLabel"] == ""
                    and scripture_blank_background_state["blankModelScriptureContext"] == ""
                    and not scripture_blank_background_state["blankModelScriptureReadingFinal"]
                    and scripture_blank_background_state["blankModelOutputContext"] == "chromakey"
                    and not scripture_blank_background_state["blankHasBackground"]
                    and not scripture_blank_background_state["blankNoChromakey"]
                    and scripture_blank_background_state["blankInlineBackground"] == ""
                    and "presenter-slide--blank" in scripture_blank_background_state["blankSlideClass"]
                    and "presenter-slide--scripture-reading" not in scripture_blank_background_state["blankSlideClass"]
                    and scripture_blank_background_state["blankSlideBackground"] == ""
                    and scripture_blank_background_state["blankText"] == ""
                ):
                    pass_("presenter-scripture-reading-generic-trailing-blank", json.dumps(scripture_blank_background_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-reading-generic-trailing-blank", json.dumps(scripture_blank_background_state, ensure_ascii=False))

                scripture_final_background_state = output_page.evaluate(
                    """
                    async (payload) => {
                      const finalIndex = payload.slides.findIndex((slide) =>
                        slide?.type === 'scripture'
                        && slide?.sectionKey === 'scripture_reading'
                        && slide?.scriptureReadingFinal
                      );
                      const finalSlide = payload.slides[finalIndex] || {};
                      renderPresenterOutput({ ...payload, index: finalIndex, safetyBlank: false }, {});
                      const root = document.getElementById('presenterOutputRoot');
                      for (let attempt = 0; attempt < 40; attempt += 1) {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        if (root.querySelector('.presenter-output-layer.is-active .presenter-slide--scripture-reading')) break;
                      }
                      const slide = root?.querySelector('.presenter-slide');
                      return {
                        finalIndex,
                        title: finalSlide.title || '',
                        referenceBook: finalSlide.referenceBook || '',
                        referenceRange: finalSlide.referenceRange || '',
                        suppressBackgroundImage: Boolean(finalSlide.suppressBackgroundImage),
                        hasBackground: root?.classList.contains('has-background') || false,
                        noChromakey: root?.classList.contains('no-chromakey') || false,
                        inlineBackground: root?.style.getPropertyValue('--presenter-bg-image') || '',
                        slideBackground: slide?.style.getPropertyValue('--presenter-slide-bg-image') || '',
                        renderedReference: slide?.querySelector('.presenter-scripture-reading-ref')?.textContent?.trim() || '',
                        fin: slide?.querySelector('.presenter-scripture-reading-fin')?.textContent?.trim() || '',
                      };
                    }
                    """,
                    scripture_blank_background_payload,
                )
                if (
                    scripture_final_background_state["finalIndex"] >= 0
                    and not scripture_final_background_state["suppressBackgroundImage"]
                    and scripture_final_background_state["noChromakey"]
                    and not scripture_final_background_state["hasBackground"]
                    and scripture_final_background_state["inlineBackground"] == ""
                    and scripture_final_background_state["slideBackground"] != ""
                    and scripture_final_background_state["renderedReference"] == "출애굽기 23:14"
                    and scripture_final_background_state["fin"] == "Fin."
                ):
                    pass_("presenter-scripture-final-has-background", json.dumps(scripture_final_background_state, ensure_ascii=False))
                else:
                    fail("presenter-scripture-final-has-background", json.dumps(scripture_final_background_state, ensure_ascii=False))
                page.evaluate(
                    """
                    (serviceId) => {
                      state.module = "presenter";
                      state.selectedServiceId = serviceId;
                      preparePresenterService(serviceId);
                      state.presenter.outputConnectedAt = Date.now();
                      renderPresenterDetail();
                      publishPresenterState({ force: true });
                    }
                    """,
                    service["id"],
                )

                theme_preview_state = page.evaluate(
                    """
                    (() => {
                      const host = document.createElement('div');
                      host.style.cssText = 'position:fixed;left:-10000px;top:0;width:184px;height:104px;';
                      host.innerHTML = `
                        <span id="miniFormal" class="svc-slide-mini-output" data-output-theme="formal"></span>
                        <span id="miniChildren" class="svc-slide-mini-output" data-output-theme="children">
                          <span class="svc-slide-mini-canvas presenter-output-root" data-output-theme="children">
                            <section class="presenter-slide presenter-slide--song-title" data-element-type="praise" data-slide-layout="lower_bar_text">
                              <div class="presenter-slide-text"><span>♪ 어린이 찬양</span></div>
                            </section>
                          </span>
                        </span>
                        <span id="miniYouth" class="svc-slide-mini-output" data-output-theme="youth"></span>
                        <span id="miniYoungAdult" class="svc-slide-mini-output" data-output-theme="young-adult"></span>
                        <span id="miniChildrenBg" class="svc-slide-mini-output no-chromakey has-background" data-output-theme="children" style="--presenter-bg-image: url('assets/worship-backgrounds/26-C1.png')"></span>
                      `;
                      document.body.appendChild(host);
                      const css = (id) => getComputedStyle(host.querySelector(`#${id}`));
                      const childrenText = getComputedStyle(host.querySelector('#miniChildren .presenter-slide-text'));
                      const result = {
                        formalBg: css('miniFormal').backgroundColor,
                        childrenBgImage: css('miniChildren').backgroundImage,
                        childrenTextColor: childrenText.color,
                        youthBgImage: css('miniYouth').backgroundImage,
                        youngAdultBgImage: css('miniYoungAdult').backgroundImage,
                        childrenHasBackgroundImage: css('miniChildrenBg').backgroundImage,
                      };
                      host.remove();
                      return result;
                    })()
                    """
                )
                if (
                    theme_preview_state["formalBg"] == "rgb(16, 18, 15)"
                    and theme_preview_state["childrenBgImage"] == "none"
                    and theme_preview_state["childrenTextColor"] == "rgb(255, 255, 255)"
                    and theme_preview_state["youthBgImage"] == "none"
                    and theme_preview_state["youngAdultBgImage"] == "none"
                    and "26-C1.png" in theme_preview_state["childrenHasBackgroundImage"]
                ):
                    pass_("presenter-controller-preview-theme-parity", json.dumps(theme_preview_state, ensure_ascii=False))
                else:
                    fail("presenter-controller-preview-theme-parity", json.dumps(theme_preview_state, ensure_ascii=False))

                output_page.keyboard.press("Escape")
                output_page.wait_for_timeout(120)
                output_page.keyboard.press("Escape")
                page.wait_for_function(
                    "() => state.presenter.outputConnectedAt === 0 && !isPresenterOutputWindowOpen()",
                    timeout=5000,
                )
                esc_stop_state = page.evaluate(
                    """
                    (() => ({
                      outputConnectedAt: state.presenter.outputConnectedAt,
                      outputWindowCleared: state.presenter.outputWindow === null,
                      monitorCleared: state.presenter.outputWindowMonitor === null,
                      open: isPresenterOutputWindowOpen(),
                      status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                    }))()
                    """
                )
                if (
                    esc_stop_state["outputConnectedAt"] == 0
                    and esc_stop_state["outputWindowCleared"]
                    and esc_stop_state["monitorCleared"]
                    and not esc_stop_state["open"]
                    and esc_stop_state["status"] == "준비"
                ):
                    pass_("presenter-output-escape-stop", json.dumps(esc_stop_state, ensure_ascii=False))
                else:
                    fail("presenter-output-escape-stop", json.dumps(esc_stop_state, ensure_ascii=False))
                if not output_page.is_closed():
                    output_page.close()
                page.evaluate(
                    """
                    (serviceId) => {
                      state.module = "presenter";
                      state.selectedServiceId = serviceId;
                      preparePresenterService(serviceId);
                      state.presenter.outputWindow = null;
                      state.presenter.outputConnectedAt = 0;
                      state.presenter.outputClientId = "";
                      stopPresenterOutputWindowMonitor();
                      publishPresenterState({ force: true });
                      renderPresenterDetail();
                      renderPresenterControlState(serviceId);
                    }
                    """,
                    service["id"],
                )
                disconnect_page = context.new_page()
                disconnect_page.set_viewport_size({"width": 1280, "height": 720})
                disconnect_page.on("pageerror", lambda error: page_errors.append(f"disconnect output: {error}"))
                disconnect_page.on("response", lambda response: record_response(response, "disconnect output"))
                disconnect_page.on(
                    "console",
                    lambda msg: console_messages.append(f"disconnect output {msg.type}: {msg.text}")
                    if msg.type in ("error", "warning")
                    else None,
                )
                disconnect_page.goto(presenter_output_url(app_url), wait_until="load")
                disconnect_page.wait_for_selector("#presenterOutputRoot", timeout=5000)
                page.wait_for_function(
                    "() => state.presenter.outputConnectedAt > 0 && isPresenterOutputWindowOpen()",
                    timeout=5000,
                )
                disconnect_page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
                page.wait_for_function(
                    "() => state.presenter.outputConnectedAt === 0 && !isPresenterOutputWindowOpen()",
                    timeout=5000,
                )
                disconnect_state = page.evaluate(
                    """
                    (() => ({
                      outputConnectedAt: state.presenter.outputConnectedAt,
                      outputWindowCleared: state.presenter.outputWindow === null,
                      monitorCleared: state.presenter.outputWindowMonitor === null,
                      open: isPresenterOutputWindowOpen(),
                    }))()
                    """
                )
                if (
                    disconnect_state["outputConnectedAt"] == 0
                    and disconnect_state["outputWindowCleared"]
                    and disconnect_state["monitorCleared"]
                    and not disconnect_state["open"]
                ):
                    pass_("presenter-output-pagehide-disconnect", json.dumps(disconnect_state, ensure_ascii=False))
                else:
                    fail("presenter-output-pagehide-disconnect", json.dumps(disconnect_state, ensure_ascii=False))
                if not disconnect_page.is_closed():
                    disconnect_page.close()
                monitor_state = page.evaluate(
                    """
                    () => new Promise((resolve) => {
                      const fakeWindow = { closed: true };
                      state.presenter.outputWindow = fakeWindow;
                      startPresenterOutputWindowMonitor(state.presenter.serviceId);
                      window.setTimeout(() => {
                        resolve({
                          outputWindowCleared: state.presenter.outputWindow === null,
                          monitorCleared: state.presenter.outputWindowMonitor === null,
                          connectedAt: state.presenter.outputConnectedAt,
                          open: isPresenterOutputWindowOpen(),
                          status: document.querySelector('.svc-presenter-status')?.textContent.trim() || '',
                        });
                      }, 4300);
                    })
                    """
                )
                if (
                    monitor_state["outputWindowCleared"]
                    and monitor_state["monitorCleared"]
                    and monitor_state["connectedAt"] == 0
                    and not monitor_state["open"]
                    and monitor_state["status"] == "준비"
                ):
                    pass_("presenter-output-window-monitor", json.dumps(monitor_state, ensure_ascii=False))
                else:
                    fail("presenter-output-window-monitor", json.dumps(monitor_state, ensure_ascii=False))

            if page_errors:
                fail("page-errors", "\n".join(page_errors[:5]))
            else:
                pass_("page-errors")

            relevant_console = [
                item for item in console_messages
                if "favicon" not in item.lower()
                and "source map" not in item.lower()
                and "the server responded with a status of 400" not in item.lower()
                and "scripts may close only the windows that were opened by them" not in item.lower()
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
