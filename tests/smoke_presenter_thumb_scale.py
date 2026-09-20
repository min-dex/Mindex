"""Controller slide size setting: applies to the board only, persists, and never reaches the output window."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
                page = ctx.new_page()
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof setPresenterThumbScale === 'function'")
                print(engine, page.evaluate('''() => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const host=document.createElement('div'); host.id='scale-host';
                  host.innerHTML=renderPresenterThumbScaleControl()+'<div class="svc-board-grid" id="g" style="display:block"><i id="probe" style="display:block;height:1px;width:var(--svc-thumb-width)"></i></div>';
                  document.body.append(host); bindDetailInteractionRoot(host);
                  const buttons=[...host.querySelectorAll('[data-presenter-thumb-scale]')];
                  check(buttons.length===4 && buttons[0].getAttribute('aria-pressed')==='true','default is 기본');
                  const width=()=>document.getElementById('probe').getBoundingClientRect().width;
                  check(width()===184,'base width '+width());
                  buttons[2].click();
                  check(document.documentElement.dataset.thumbScale==='1.6','click applies');
                  check(Math.abs(width()-184*1.6)<0.01,'scaled width '+width());
                  check(localStorage.getItem('mindex.ui.presenterThumbScale')==='1.6','persisted');
                  check(buttons.map(b=>b.getAttribute('aria-pressed')).join()==='false,false,true,false','pressed state follows');
                  check(readPresenterThumbScale()==='1.6','read back');
                  localStorage.setItem('mindex.ui.presenterThumbScale','9');
                  check(readPresenterThumbScale()==='1','invalid stored value falls back');
                  applyPresenterThumbScale('nope');
                  check(document.documentElement.dataset.thumbScale==='1','invalid key falls back');
                  return 'PASS';
                }'''), 'controls, scaling, persistence, fallback', flush=True)
                # narrow breakpoints keep the multiplier
                for w, base in [(1100, 168), (700, 148)]:
                    page.set_viewport_size({'width': w, 'height': 800})
                    got = page.evaluate('''() => { setPresenterThumbScale('1.3'); return document.getElementById('probe').getBoundingClientRect().width; }''')
                    assert abs(got - base * 1.3) < 0.01, (w, got)
                page.evaluate("setPresenterThumbScale('2')")
                # A fresh controller load restores it; the output window never applies it.
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function("typeof readPresenterThumbScale === 'function'")
                assert page.evaluate("document.documentElement.dataset.thumbScale") == '2', 'restored on reload'
                out = ctx.new_page()
                out.route('**/*supabase*/**', lambda r: r.abort())
                out.goto(url + '?output=presenter', wait_until='domcontentloaded')
                out.wait_for_function("typeof renderPresenterOutput === 'function'")
                out.wait_for_timeout(300)
                assert out.evaluate("document.documentElement.dataset.thumbScale || ''") == '', 'output window must not get the controller scale'
                assert out.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--svc-thumb-scale').trim()") == '', 'output scale var'
                print(engine, 'PASS restore on reload, breakpoints, output window untouched', flush=True)
                browser.close()
    finally:
        server.shutdown()


main()
