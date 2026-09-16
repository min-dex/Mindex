from pathlib import Path
from smoke_app import launch_chromium, sync_playwright

source = (Path(__file__).resolve().parents[1] / "mindex.presenter.js").read_text()
helper = source[source.index("function setupPresenterStartupFullscreen()"):
                source.index("function initPresenterOutputCore()")]

with sync_playwright() as p:
    browser = launch_chromium(p)
    for mode in ("allowed", "blocked", "escape", "unsupported", "no-request"):
        page = browser.new_page()
        page.route("https://fullscreen.test/**", lambda route: route.fulfill(
            content_type="text/html", body="<main style='height:100vh'>Output</main>"))
        page.goto("https://fullscreen.test/" + ("" if mode == "no-request" else "?fullscreen=start"))
        page.evaluate("""mode => {
          window.calls = 0;
          window.actualFullscreen = null;
          Object.defineProperty(document, 'fullscreenElement', {get: () => actualFullscreen});
          Object.defineProperty(document, 'fullscreenEnabled', {value: mode !== 'unsupported'});
          document.documentElement.requestFullscreen = async () => {
            calls++;
            if (mode !== 'allowed' && calls === 1) throw new DOMException('Blocked', 'NotAllowedError');
            actualFullscreen = document.documentElement;
            document.dispatchEvent(new Event('fullscreenchange'));
          };
        }""", mode)
        page.add_script_tag(content=helper + "\nsetupPresenterStartupFullscreen();")
        assert page.evaluate("calls") == (0 if mode in ("unsupported", "no-request") else 1), mode
        if mode == "escape":
            page.keyboard.press("Escape")
        page.mouse.click(100, 100)
        expected = 2 if mode == "blocked" else 0 if mode in ("unsupported", "no-request") else 1
        assert page.evaluate("calls") == expected, mode
        # ESC/fullscreen exit and subsequent output activity must never re-enter.
        page.evaluate("actualFullscreen = null; document.dispatchEvent(new Event('fullscreenchange'));")
        page.keyboard.press("ArrowRight")
        page.mouse.click(100, 100)
        page.evaluate("setupPresenterStartupFullscreen()")
        assert page.evaluate("calls") == expected, mode
        assert page.evaluate("new URL(location.href).searchParams.has('fullscreen')") is False
        page.close()
    page = browser.new_page()
    page.route("https://fullscreen.test/**", lambda route: route.fulfill(
        content_type="text/html", body="<main style='height:100vh'>Output</main>"))
    page.goto("https://fullscreen.test/?fullscreen=start")
    page.add_script_tag(content=helper + "\nsetupPresenterStartupFullscreen();")
    page.mouse.click(100, 100)
    page.wait_for_function("Boolean(document.fullscreenElement)")
    page.evaluate("document.exitFullscreen()")
    page.mouse.click(100, 100)
    assert page.evaluate("document.fullscreenElement === null")
    page.close()
    browser.close()
print("PASS startup attempt, trusted-click fallback, ESC, unsupported, and no re-entry (mocked API)")
print("PASS native Chrome fullscreen click and no re-entry after exit (headless, one display)")
