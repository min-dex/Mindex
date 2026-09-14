"""Read-only monitor UI, isolation and privacy checks; no live DB traffic."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    page.route('**/*supabase*/**', lambda r: r.abort())
                    page.goto(url, wait_until='domcontentloaded')
                    page.wait_for_function("!!document.querySelector('.monitor-panel')")
                    page.evaluate('''() => {
                      window.monitorCalls=[]; window.monitorMode='ok';
                      state.services=[{id:'editing',date:'2026-09-13',type_id:'sunday-second'}, {id:'output',date:'2026-09-13',type_id:'sunday-main'}];
                      state.selectedServiceId='editing'; state.module='presenter';
                      state.presenter.serviceId='output';state.presenter.index=2;state.presenter.slides=[{},{},{}];
                      state.presenter.outputConnectedAt=Date.now();
                      state.client={rpc:(name,args)=>({abortSignal:signal=>{
                        monitorCalls.push({name,args});
                        if(monitorMode==='pending')return new Promise(resolve=>window.monitorRelease=resolve);
                        if(monitorMode==='missing')return Promise.resolve({error:{code:'PGRST202'}});
                        const data=name==='mindex_monitor_register'?'report-token':name==='mindex_monitor_login'?(args.p_password==='test-secret'?'admin-token':null):name==='mindex_monitor_read'?[{
                          id:'remote',last_seen:new Date().toISOString(),status:{name:'<img src=x onerror=alert(1)>',os:'Windows',browser:'Whale',version:'test',module:'praise',serviceId:'editing',outputServiceId:'output',output:true,slide:3,count:3,events:[{kind:'save_ok',at:new Date().toISOString()}]}
                        }]:true;
                        return Promise.resolve({data,error:null});
                      }})};
                    }''')
                    page.locator('#monitorPanelBtn').click()
                    assert page.locator('.monitor-panel').is_visible()
                    assert page.evaluate('monitorCalls.length') == 0
                    assert 'sunday-second' in page.locator('[data-local]').inner_text()
                    assert 'sunday-main' in page.locator('[data-local]').inner_text()
                    page.locator('[data-share]').check()
                    page.wait_for_function("monitorCalls.some(c=>c.name==='mindex_monitor_heartbeat')")
                    page.evaluate("emitMonitorSaveEvent('save_start');emitMonitorSaveEvent('save_ok');emitMonitorSaveEvent('save_failed')")
                    page.locator('[data-refresh]').click()
                    page.locator('[data-local] summary').click()
                    assert '예배 저장 완료' in page.locator('[data-local]').inner_text()
                    assert '예배 저장 흐름 오류' in page.locator('[data-local]').inner_text()
                    assert not page.evaluate("monitorCalls.some(c=>c.name==='mindex_monitor_read')")
                    page.locator('#monitorPassword').fill('wrong')
                    page.locator('.monitor-panel button[type=submit]').click()
                    page.wait_for_function("document.querySelector('.monitor-message').textContent.includes('시도 제한')")
                    page.locator('#monitorPassword').fill('test-secret')
                    page.locator('.monitor-panel button[type=submit]').click()
                    page.wait_for_function("!!document.querySelector('[data-devices] strong')")
                    assert page.locator('[data-devices] img').count() == 0
                    assert page.locator('#monitorPassword').input_value() == ''
                    assert page.evaluate("Object.values(localStorage).every(v=>!v.includes('test-secret')&&!v.includes('admin-token'))")
                    for width in [1280, 390]:
                        page.set_viewport_size({'width': width, 'height': 900})
                        assert page.locator('.monitor-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                        page.screenshot(path=f'/tmp/mindex-monitor-{engine}-{width}.png')
                    page.locator('[data-share]').uncheck()
                    page.wait_for_function("monitorCalls.some(c=>c.name==='mindex_monitor_leave'&&c.args.p_token==='report-token')")
                    page.locator('[data-close]').click()
                    page.wait_for_function("monitorCalls.some(c=>c.name==='mindex_monitor_leave'&&c.args.p_token==='admin-token')")
                    assert page.locator('[data-devices]').inner_text() == ''
                    assert page.evaluate("state.presenter.index===2&&state.presenter.serviceId==='output'&&state.selectedServiceId==='editing'")
                    payload = page.evaluate("monitorCalls.find(c=>c.name==='mindex_monitor_heartbeat').args.p_status")
                    assert set(payload) <= set('name os browser version module serviceId serviceDate serviceType output outputServiceId slide count dirty saving video events'.split())
                    page.evaluate("monitorMode='missing'")
                    page.locator('#monitorPanelBtn').click()
                    page.locator('[data-share]').check()
                    page.wait_for_function("document.querySelector('.monitor-share-status').textContent.includes('서버 설정')")
                    assert page.evaluate('state.presenter.index') == 2
                    print(engine, 'PASS opt-in, authenticated read, save results, separate edit/output, privacy, XSS, responsive layout, revoke, missing server isolation')
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
