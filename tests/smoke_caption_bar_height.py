from pathlib import Path
from smoke_app import launch_chromium, sync_playwright

root = Path(__file__).resolve().parents[1]
css = (root / "styles.presenter-output.css").read_text()
preview_css = (root / "styles.css").read_text()
assert "--presenter-output-bar-height: 18%;" in css
assert "--presenter-output-bar-height: 18%;" in preview_css
with sync_playwright() as p:
    browser = launch_chromium(p)
    for width, height in ((1920, 1080), (960, 540), (320, 180)):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content('''<meta charset="utf-8"><body class="presenter-output-body"><div class="presenter-output-root">
          <div class="presenter-slide presenter-slide--lyrics">
            <div class="presenter-slide-text">내 죄를 씻으신 주 이름<br>찬송합시다</div>
          </div></div></body>''')
        style = page.add_style_tag(content=css.replace("--presenter-output-bar-height: 18%;", "--presenter-output-bar-height: 20%;"))
        read = '''() => {
          const stage=document.querySelector('.presenter-output-root');
          const text=document.querySelector('.presenter-slide-text');
          const s=getComputedStyle(text);
          return {height:text.getBoundingClientRect().height, stage:stage.getBoundingClientRect().height,
            font:s.fontSize, weight:s.fontWeight, padding:s.paddingLeft};
        }'''
        before = page.evaluate(read)
        style.evaluate("(el, css) => el.textContent = css", css)
        after = page.evaluate(read)
        assert abs(after["height"] / after["stage"] - 0.18) < 0.002, after
        for key in ("font", "weight", "padding"):
            assert before[key] == after[key], (key, before, after)
        if width == 960:
            page.screenshot(path="/tmp/mindex-caption-18.png")
        page.close()
    browser.close()
print("PASS 18% caption bar at 1920/960/320; font, weight and horizontal padding unchanged")
