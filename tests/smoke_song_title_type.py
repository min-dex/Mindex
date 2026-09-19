"""Check lower-bar title roles in output and scaled previews."""

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
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url + '?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterOutput === 'function'")
            page.evaluate('document.fonts.ready')
            for chromakey in [True, False]:
                for key in ['praise', 'pre_scripture_praise', 'entrance_praise',
                            'response_song', 'prayer_meeting_praise', 'special_song', 'offering',
                            'hymn_praise', 'doxology', 'sending', 'closing_song', 'closing_hymn', 'closing_visual']:
                    for title in ['임재', '한라에서 백두까지 백두에서 땅끝까지',
                                  '한라에서 백두까지 백두에서 땅끝까지 주님의 사랑을 전하리',
                                  '주의 자녀로 산다는 것은']:
                        result = page.evaluate("""({chromakey, key, title}) => {
                          let slide = {id:'title-test', type:'song-title', elementType:'praise',
                            layout:'lower_bar_text', sectionKey:key, title, text:'♬ ' + title,
                            sectionHeading:'찬양 1', label:'찬양 1',
                            outputContext:chromakey ? 'chromakey' : 'fullscreen', live:true};
                          if (chromakey) delete slide.sectionHeading;
                          else {
                            slide = {...presenterSongTitleSlide(
                              {id:'title-test',label:'찬양 1'}, {sectionKey:key}, null, null, title, 0),
                              outputContext:'fullscreen',live:true};
                          }
                          renderPresenterOutput({serviceId:'title-test', serviceType:'sunday-main',
                            chromakey, slides:[slide], index:0, safetyBlank:false}, {});
                          const measure = root => {
                            const box = root.querySelector(chromakey
                              ? '.presenter-slide--song-title > .presenter-slide-text'
                              : '.presenter-slide--fullscreen-song-title .presenter-title-content-title');
                            const range = document.createRange();
                            range.selectNodeContents(box);
                            const bounds = box.getBoundingClientRect();
                            const style = getComputedStyle(box);
                            const stage = root.matches('.presenter-output-root') ? root : root.querySelector('.presenter-output-root');
                            const stageBounds = stage.getBoundingClientRect();
                            const clip = chromakey ? bounds : stageBounds;
                            const textBounds = range.getBoundingClientRect();
                            return {size:parseFloat(style.fontSize), weight:style.fontWeight,
                              clean:chromakey || (!root.querySelector('.presenter-title-content-body')
                                && !root.textContent.includes('찬양 1') && box.textContent.includes('♬')
                                && box.scrollWidth <= box.clientWidth + 1
                                && Math.abs((textBounds.left + textBounds.right - stageBounds.left - stageBounds.right) / 2) < 2
                                // Order headings are restored above the title (dc5cf02b), so the title box
                                // sits below the heading rather than at the stage's vertical center.
                                && bounds.top >= stageBounds.top && bounds.bottom <= stageBounds.bottom),
                              inside:[...range.getClientRects()].every(r => r.left >= clip.left - 1
                                && r.right <= clip.right + 1 && r.top >= clip.top - 1
                                && r.bottom <= clip.bottom + 1)};
                          };
                          const output = measure(document.getElementById('presenterOutputRoot'));
                          const mount = document.createElement('div');
                          mount.className = 'svc-slide-thumb-frame';
                          mount.style.cssText='position:fixed;top:0;left:0;width:406px;height:228.375px';
                          mount.innerHTML = renderPresenterSlideMiniPreview(slide);
                          document.body.append(mount);
                          applyPresenterPreviewScales(mount);
                          fitPresenterSongTitlePreviews(mount);
                          fitPresenterSermonTitlePreviews(mount);
                          const preview = measure(mount);
                          mount.remove();
                          return {output, preview};
                        }""", {'chromakey': chromakey, 'key': key, 'title': title})
                        assert result['output'] == result['preview'], result
                        page.screenshot(path=f'/tmp/mindex-song-title-{chromakey}.png')
                        for value in result.values():
                            assert value['weight'] == '800' and value['inside'] and value['clean'], result
                            assert (56 if chromakey else 48) <= value['size'] <= (100.01 if chromakey else 150.01), result
                            if title == '임재':
                                assert abs(value['size'] - (100 if chromakey else 150)) < 0.1, result
                        print('PASS', chromakey, key, title, result, flush=True)
                page.screenshot(path=f'/tmp/mindex-song-title-{chromakey}.png')
            browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
