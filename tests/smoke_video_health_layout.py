from pathlib import Path
from smoke_app import launch_chromium, sync_playwright

with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (254, 320, 390):
        page = browser.new_page(viewport={"width": width, "height": 300})
        page.set_content('<main style="display:grid;gap:10px"><div class="svc-presenter-video-health"></div><button id="next">송출 시작</button></main>')
        page.add_style_tag(path=str(Path(__file__).resolve().parents[1] / "styles.css"))
        page.add_style_tag(content="body { min-width: 0; }")
        baseline = page.locator("#next").bounding_box()["y"]
        for label in ("영상 불러오는 중", "영상 재생 실패", "영상 일시정지 · 송출 창 확인", "자동재생 차단", ""):
            page.locator('.svc-presenter-video-health').evaluate('''(el, label) => {
              el.innerHTML = label ? '<span role="status"></span><button class="icon-btn">↻</button>' : '';
              if (label) el.querySelector('span').textContent = label;
            }''', label)
            assert page.locator("#next").bounding_box()["y"] == baseline
            assert page.locator('.svc-presenter-video-health').evaluate('(el) => el.scrollHeight <= el.clientHeight')
        page.close()
    browser.close()
print("PASS loading/error/paused/blocked/empty: no vertical shift at 254/320/390px")
