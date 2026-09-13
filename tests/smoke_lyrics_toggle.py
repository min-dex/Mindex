from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page(viewport={'width': 1200, 'height': 900})
                    page.route('**/*supabase*/**', lambda r: r.abort())
                    page.goto(url, wait_until='domcontentloaded')
                    page.wait_for_function("typeof renderPresenterManualLyricsField === 'function'")
                    page.evaluate('''() => {
                      window.item={id:'song',label:'특송',memo:JSON.stringify({inputMode:'manual_praise',slides:Array.from({length:12},()=> '성도는 믿음으로 산다\\n나의 모든 길 주님 인도하시리')})};
                      window.originalMemo=item.memo;
                      state.module='presenter';state.presenter.serviceId='service-a';
                      document.body.innerHTML='<main id="fixture" style="width:960px;margin:20px"><div class="svc-board-subgroup-controls"><div class="svc-board-subgroup-control-item">'+renderPresenterManualLyricsField(item,0,'service-a')+'</div></div></main>';
                      document.getElementById('fixture').addEventListener('click',handlePresenterDetailClick);
                      refreshIcons(document.body);
                      window.textarea=document.querySelector('textarea');
                      textarea.value+='\\n미저장 입력';textarea.setSelectionRange(2,6);
                      window.value=textarea.value;window.events=0;window.publishes=0;
                      textarea.addEventListener('input',()=>events++);textarea.addEventListener('change',()=>events++);
                      publishPresenterState=()=>{publishes++};
                    }''')
                    for width in [960, 320]:
                        page.evaluate("w=>document.getElementById('fixture').style.width=w+'px'", width)
                        collapsed = page.locator('textarea').bounding_box()['height']
                        page.get_by_role('button', name='가사 펼치기').click()
                        expanded = page.locator('textarea').bounding_box()['height']
                        assert expanded > collapsed + 60, (collapsed, expanded)
                        assert page.evaluate("renderPresenterManualLyricsField(item,0,'service-a').includes('aria-expanded=\"true\"')")
                        assert page.evaluate("renderPresenterManualLyricsField(item,0,'service-b').includes('aria-expanded=\"false\"')")
                        page.locator('#fixture').screenshot(path=f'/private/tmp/lyrics-toggle-{engine}-{width}.png')
                        page.get_by_role('button', name='가사 접기').click()
                        page.evaluate('''() => {
                          if(textarea!==document.querySelector('textarea') || textarea.value!==value)throw Error('draft lost');
                          if(textarea.selectionStart!==2 || textarea.selectionEnd!==6)throw Error('selection lost');
                          if(events || publishes || item.memo!==originalMemo)throw Error('toggle mutated data or output');
                          const host=document.getElementById('fixture').getBoundingClientRect();
                          for(const n of document.querySelectorAll('textarea,button'))if(n.getBoundingClientRect().right>host.right+1)throw Error('overflow');
                        }''')
                    page.get_by_role('button', name='가사 펼치기').focus()
                    page.keyboard.press('Enter')
                    assert page.get_by_role('button', name='가사 접기').get_attribute('aria-expanded') == 'true'
                    print('PASS', engine, 'collapse/expand, draft and selection, service scope, keyboard, no output/data mutation, 960/320px')
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
