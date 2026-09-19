"""Manual praise lyrics must reserve space before assignee and slides."""

import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    server, url = start_local_app_server() if not args.url else (None, args.url)
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof presenterServiceInputControls === 'function'")
            page.evaluate("""() => {
              const service = {id:'layout-test', type_id:'sunday-main'};
              const item = {id:'special', label:'특송', raw_title:'', assignee:'할렐루야 찬양대',
                _worshipSectionKey:'special_song', memo:JSON.stringify({inputMode:'manual_praise'})};
              const fixture = document.createElement('main');
              fixture.id = 'layoutFixture';
              fixture.style.cssText = 'position:absolute;inset:0;padding:24px;background:#191919;z-index:99999';
              fixture.innerHTML = `<div class="svc-board-subgroup-controls"><div class="svc-board-subgroup-control-item">
                <span class="svc-board-subgroup-control-label">특송</span>
                ${presenterServiceInputControls(item, 0, service)}
                ${renderPresenterBoardItemAudioControls(service.id, {item,index:0})}
                </div></div><div id="followingSlide" style="height:150px;background:#000">특송</div>`;
              document.body.append(fixture);
            }""")
            for width in (1400, 800, 390):
                page.set_viewport_size({'width': width, 'height': 900})
                for height in (180, 360):
                    result = page.evaluate("""height => {
                      const root = document.getElementById('layoutFixture');
                      const textarea = root.querySelector('.svc-presenter-input-field--lyrics textarea');
                      textarea.style.height = `${height}px`;
                      const lyrics = textarea.getBoundingClientRect();
                      const assignee = root.querySelector('[data-service-item-field="assignee"]').getBoundingClientRect();
                      const controls = root.querySelector('.svc-board-subgroup-controls').getBoundingClientRect();
                      const next = root.querySelector('#followingSlide').getBoundingClientRect();
                      // Wide viewports lay the assignee beside the lyrics (d3c607b9): only overlap is a failure.
                      const noOverlap = assignee.top >= lyrics.bottom || assignee.left >= lyrics.right - 1 || assignee.right <= lyrics.left + 1;
                      return {reserved:noOverlap, contained:controls.bottom >= lyrics.bottom,
                        nextBelow:next.top >= controls.bottom, fitsWidth:lyrics.right <= innerWidth};
                    }""", height)
                    assert all(result.values()), (width, height, result)
                print('PASS multiline editor at viewport', width, flush=True)
            page.screenshot(path='/tmp/mindex-multiline-mobile.png')
            page.set_viewport_size({'width':1400,'height':900})
            page.screenshot(path='/tmp/mindex-multiline-desktop.png')
            browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
