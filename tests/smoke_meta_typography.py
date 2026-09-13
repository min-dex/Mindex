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
                page.wait_for_function("typeof presenterReadySlide === 'function'")
                print(engine, page.evaluate('''() => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const root=document.createElement('div');root.className='presenter-output-root';
                  root.style.cssText='--presenter-stage-unit:1px;--presenter-stage-width:1920px;--presenter-stage-height:1080px';
                  document.body.replaceChildren(root);
                  const cases=['presenter-ready-screen-kicker','presenter-waiting-loop-script','presenter-citation-tab',
                    'presenter-slide-meta','presenter-title-content-body','presenter-fullscreen-song-heading',
                    'presenter-fullscreen-order-heading','presenter-fullscreen-song-detail',
                    'presenter-liturgical-body-lines','presenter-announcement-items',
                    'presenter-scripture-reading-version','presenter-scripture-reading-fin'];
                  root.innerHTML=cases.map(c=>`<div class="${c}">개역개정 Fin.</div>`).join('')+
                    '<div class="presenter-slide--liturgical-body"><div class="presenter-slide-text">본문</div><div class="presenter-title-content-body">본문</div></div>'+
                    '<div class="presenter-scripture-reading-text">하나님이 세상을 사랑하사</div>';
                  for(const clean of [false,true]) {
                    root.classList.toggle('no-chromakey',clean);
                    for(const node of root.querySelectorAll('div')) {
                      const css=getComputedStyle(node);
                      const weight=node.classList.contains('presenter-citation-tab')?'700':'600';
                      if(Math.abs(parseFloat(css.fontSize)-50)<0.01)check(css.fontWeight===weight,node.className+' '+css.fontWeight);
                    }
                    const fin=getComputedStyle(root.querySelector('.presenter-scripture-reading-fin'));
                    const text=getComputedStyle(root.querySelector('.presenter-scripture-reading-text'));
                    check(fin.fontFamily===text.fontFamily,'Fin family differs from reading');
                    check(fin.fontStyle==='italic'&&fin.fontWeight==='600','Fin style');
                    check(text.fontWeight==='700'&&parseFloat(text.fontSize)===90,'reading body changed');
                    if(clean)check(getComputedStyle(root.querySelector('.presenter-title-content-body')).fontWeight==='700','100px weight changed');
                  }
                  root.innerHTML='<div class="presenter-scripture-reading" style="position:absolute;inset:100px;width:auto;height:auto"><div class="presenter-scripture-reading-version">개역개정</div><div class="presenter-scripture-reading-text" style="margin-top:80px">하나님이 세상을 이처럼 사랑하사</div><div class="presenter-scripture-reading-fin">Fin.</div></div>';
                  return 'PASS citation tab = 700, other tested 50px roles = 600; Fin family/italic; body and support preserved';
                }'''))
                page.screenshot(path=f'/private/tmp/mindex-meta-{engine}.png')
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
