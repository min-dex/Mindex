from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url + '?output=presenter', wait_until='domcontentloaded')
                page.wait_for_function("typeof renderPresenterCitationTabSlide === 'function'")
                for width in [1920, 400]:
                    page.set_viewport_size({'width': width, 'height': round(width * 9 / 16)})
                    widths = []
                    for book in ['요한복음', '데살로니가전서']:
                        result = page.evaluate('''async ({book}) => {
                          const slide={elementType:PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                            layout:PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT, type:'scripture',
                            scriptureContext:'citation-chromakey', referenceBook:book,
                            referenceRange:'1:1', scriptureVerse:1, title:book+' 1:1',
                            text:'살전 1:1   귀 있는 자는 들으라 하시니라',
                            citationBodyText:'귀 있는 자는 들으라 하시니라'};
                          document.body.innerHTML='<div class="presenter-output-root" id="fixture">'+renderPresenterSlideFrame(slide)+'</div>';
                          await document.fonts.ready;
                          const root=document.querySelector('#fixture');
                          fitPresenterChromakeyScriptureText(root);
                          const tab=root.querySelector('.presenter-citation-tab');
                          const body=root.querySelector('.presenter-slide-text');
                          const t=tab.getBoundingClientRect(), b=body.getBoundingClientRect();
                          return {label:tab.textContent, text:body.textContent, width:t.width, weight:getComputedStyle(tab).fontWeight,
                            overlap:t.bottom>b.top+1, fits:tab.scrollWidth<=tab.clientWidth+1 && body.scrollHeight<=body.clientHeight+1};
                        }''', {'book': book})
                        assert result['label'] == book+' 1:1', result
                        assert result['weight'] == '700', result
                        assert result['text'] == '귀 있는 자는 들으라 하시니라', result
                        assert result['fits'] and not result['overlap'], result
                        widths.append(result['width'])
                    assert widths[1] > widths[0], widths
                    if engine == 'chromium' and width == 1920:
                        page.screenshot(path='/private/tmp/mindex-citation-tab.png')
                print('PASS', engine, 'full-size/thumbnail content-width tab and separate body')
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
