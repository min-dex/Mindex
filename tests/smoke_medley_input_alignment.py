from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chromium", "webkit"):
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url, wait_until="domcontentloaded")
                page.evaluate(
                    r'''() => {
                      const row = (title, selected, longest) => `
                        <div class="svc-board-subgroup-control-item">
                          <label class="svc-presenter-input-field svc-presenter-input-field--song">
                            <span>찬양</span>
                            <div class="svc-edit-title-wrap svc-edit-title-wrap--song">
                              <select class="svc-presenter-input-control"><option>가사 불러오기</option></select>
                              <input class="svc-edit-title" value="${title}">
                              <div class="svc-song-picker svc-song-picker--linked">
                                <select class="svc-song-version-select">
                                  <option selected>${selected}</option>
                                  <option>${longest}</option>
                                </select>
                                <button class="svc-song-clear" type="button">×</button>
                              </div>
                              <input class="svc-form-hint compact" value="V1-V2">
                            </div>
                          </label>
                        </div>`;
                      document.body.innerHTML = `
                        <main id="fixture" style="margin:24px;width:1200px">
                          <div class="svc-board-subgroup-controls svc-board-subgroup-controls--stacked">
                            ${row("예수 예수", "후렴 반복", "후렴 반복")}
                            ${row("91 슬픈 마음 있는 사람", "새찬송가", "새찬송가 91장 슬픈 마음 있는 사람")}
                          </div>
                        </main>`;
                    }'''
                )

                for width in (1200, 840, 560):
                    page.evaluate("width => document.getElementById('fixture').style.width = width + 'px'", width)
                    page.wait_for_timeout(50)
                    result = page.evaluate(
                        r'''() => {
                          const rects = selector => [...document.querySelectorAll(selector)].map(node => node.getBoundingClientRect());
                          const titles = rects('.svc-edit-title');
                          const pickers = rects('.svc-song-picker--linked');
                          const rows = rects('.svc-board-subgroup-control-item');
                          return {
                            titleDelta: Math.abs(titles[0].width - titles[1].width),
                            pickerDelta: Math.abs(pickers[0].width - pickers[1].width),
                            pickerWidths: pickers.map(rect => rect.width),
                            overflow: rows.some((row, index) => pickers[index].right > row.right + 1),
                          };
                        }'''
                    )
                    assert result["titleDelta"] <= 1, (engine, width, result)
                    assert result["pickerDelta"] <= 1, (engine, width, result)
                    assert not result["overflow"], (engine, width, result)
                print("PASS", engine, "medley title and version alignment")
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
