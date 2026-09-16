from pathlib import Path
from smoke_app import launch_chromium, sync_playwright

root = Path(__file__).resolve().parents[1]
source = (root / "mindex.presenter.js").read_text()
controller = source[source.index("function requestPresenterOutputFullscreenFromController()"):
                    source.index("function shouldKeepPresenterShortcutInFocusedControl(")]
receiver = source[source.index("function setupPresenterDelegatedFullscreen()"):
                  source.index("function setupPresenterStartupFullscreen()")]
markup = '''<div class="svc-presenter-side-panel"><div class="svc-presenter-output-group">
<button class="svc-present-btn svc-presenter-launch" id="open">송출 시작</button>
<div class="svc-presenter-window-controls"><button class="icon-btn" id="screen">화면 감지</button>
<button class="icon-btn svc-presenter-fullscreen" id="full" title="송출 화면 전체화면" disabled>⛶</button>
<button class="svc-presenter-pin-toggle" id="pin">항상 위</button></div></div></div>'''

with sync_playwright() as p:
    browser = launch_chromium(p)
    context = browser.new_context()
    context.route("https://fullscreen.test/**", lambda r: r.fulfill(content_type="text/html; charset=utf-8", body=markup))
    page = context.new_page()
    page.goto("https://fullscreen.test/controller")
    page.add_style_tag(path=str(root / "styles.css"))
    # The isolated fixture represents a sidebar, not the full app viewport.
    page.add_style_tag(content="body { min-width: 0; }")
    page.add_script_tag(content=controller + '''
      window.notices = [];
      function showToast(message) { notices.push(message); }
      function presenterOutputWindowRef() { return window.output; }
      document.querySelector('#open').onclick = () => {
        window.output = window.open('/output', 'output', 'popup');
        document.querySelector('#full').disabled = false;
      };
      document.querySelector('#full').onclick = requestPresenterOutputFullscreenFromController;
    ''')
    assert page.locator("#full").is_disabled()
    with page.expect_popup() as opened:
        page.click("#open")
    output = opened.value
    output.wait_for_load_state()
    output.add_script_tag(content=receiver + "\nsetupPresenterDelegatedFullscreen();")
    # Same-origin but non-opener messages must not request fullscreen.
    output.evaluate("window.postMessage({type:'presenter-fullscreen-request',requestId:'fake'}, location.origin)")
    output.wait_for_timeout(100)
    assert output.evaluate("!document.fullscreenElement")
    page.bring_to_front()
    page.click("#full")
    output.wait_for_function("!!document.fullscreenElement")
    assert page.evaluate("!document.fullscreenElement")
    output.evaluate("document.exitFullscreen()")
    output.wait_for_function("!document.fullscreenElement")
    page.bring_to_front()
    page.click("#full")
    output.wait_for_function("!!document.fullscreenElement")
    assert page.evaluate("notices.length") == 0
    for _ in range(8):
        output.evaluate("document.exitFullscreen()")
        output.wait_for_function("!document.fullscreenElement")
        page.bring_to_front()
        page.click("#full")
        output.wait_for_function("!!document.fullscreenElement")
        assert page.evaluate("!document.fullscreenElement && notices.length === 0")
    output.close()
    page.click("#full")
    assert "연결된 송출 창이 없습니다" in page.evaluate("notices.at(-1)")
    for width in (254, 320, 390):
        page.set_viewport_size({"width": width, "height": 240})
        bounds = page.evaluate('''() => {
          const a = document.querySelector('#screen').getBoundingClientRect();
          const b = document.querySelector('#full').getBoundingClientRect();
          const c = document.querySelector('#pin').getBoundingClientRect();
          return {sameRow: Math.abs(a.top-b.top)<2 && Math.abs(b.top-c.top)<2,
            separate:a.right<=b.left && b.right<=c.left, fits:c.right<=innerWidth};
        }''')
        assert all(bounds.values()), (width, bounds)
    page.screenshot(path="/tmp/mindex-fullscreen-button.png")
    browser.close()
print("PASS real Chrome delegation, controller unchanged, repeat explicit request, closed output, sender validation, 254/320/390px layout")
