from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda r: r.abort())
            page.goto(url + '?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterReadingAssigneeTab === 'function'")
            for width in [1920, 400]:
                page.set_viewport_size({'width': width, 'height': round(width * 9 / 16)})
                for name in ['', '이예울 학생', '<이예울> 학생']:
                    result = page.evaluate('''async ({name}) => {
                      const slide = presenterScriptureReadingTitleSlide(
                        {id:'reading', assignee:name}, {sectionKey:'scripture_reading'}, 0, '로마서 8:12–17');
                      const prepared = presenterSlideWithServiceAssigneeFallback(slide);
                      document.body.innerHTML='<div class="presenter-output-root">'+renderPresenterSlideFrame(prepared)+'</div>';
                      await document.fonts.ready;
                      const tab=document.querySelector('.presenter-assignee-tab');
                      const bar=document.querySelector('.presenter-slide-text');
                      const b=bar.getBoundingClientRect(), t=tab?.getBoundingClientRect();
                      return {name:tab?.textContent || '', tabs:document.querySelectorAll('.presenter-assignee-tab').length,
                        fits:!t || (t.left>=0 && t.right<=innerWidth+1 && Math.abs(t.right-b.right)<2 && t.bottom<=b.top+1),
                        reference:bar.textContent,
                        unrelated:renderPresenterReadingAssigneeTab({label:'설교',scriptureReadingAssignee:name})};
                    }''', {'name':name})
                    assert result['name'] == name, result
                    assert result['tabs'] == bool(name) and result['fits'], result
                    assert '로마서' in result['reference'] and result['unrelated'] == '', result
            browser.close()
            print('PASS scripture assignee tab: explicit name, empty state, escaping, fallback and geometry')
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
