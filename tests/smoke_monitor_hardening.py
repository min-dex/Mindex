"""Monitor fault handling and lock races; all remote calls use synthetic fixtures."""
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
                    page.add_init_script('''const interval=window.setInterval;
                      window.setInterval=(fn,ms,...args)=>{if(ms===2000&&String(fn).includes('viewerExpiresAt'))window.auditTick=fn;return interval(fn,ms,...args)};''')
                    page.goto(url, wait_until='domcontentloaded')
                    page.wait_for_function("typeof auditTick==='function'")
                    page.evaluate('''() => {
                      window.calls=[];window.mode='ok';
                      const now=Date.now();
                      window.rows=[null,{id:'bad',status:null},
                        {id:'fresh',last_seen:new Date(now).toISOString(),status:{name:'Fresh',events:[{kind:'save_failed',at:new Date(now-2000).toISOString()},{kind:'save_ok',at:new Date(now).toISOString()}]}},
                        {id:'stale',last_seen:new Date(now-60000).toISOString(),status:{name:'Stale',output:true,slide:1,count:2,video:'blocked',events:[null,{kind:'save_failed',at:new Date(now).toISOString()}]}},
                        {id:'invalid',last_seen:'invalid',status:{name:'Unknown',events:[]}}];
                      state.client={rpc:(name,args)=>({abortSignal:signal=>{
                        calls.push({name,args});
                        if(name==='mindex_monitor_read'&&mode==='pending')return new Promise((resolve,reject)=>{
                          window.releaseRead=resolve;signal.addEventListener('abort',()=>reject(Error('private-error-detail')),{once:true});
                        });
                        if((name==='mindex_monitor_read'&&mode==='read-error')||(name==='mindex_monitor_heartbeat'&&mode==='write-error'))return Promise.reject(Error('private-error-detail'));
                        return Promise.resolve({data:name==='mindex_monitor_login'?'viewer':name==='mindex_monitor_register'?'reporter':name==='mindex_monitor_read'?rows:true,error:null});
                      }})};
                      state.presenter.outputConnectedAt=now-4000;
                    }''')
                    page.locator('#monitorPanelBtn').click()
                    assert '송출창 미연결' in page.locator('[data-local]').inner_text()
                    page.evaluate("mode='write-error'")
                    page.locator('[data-share]').check()
                    page.wait_for_function("document.querySelector('.monitor-share-status').textContent.includes('자동 재시도')")
                    page.evaluate("mode='ok'")

                    def login():
                        page.locator('#monitorPassword').fill('test-only')
                        page.locator('.monitor-panel button[type=submit]').click()
                        page.wait_for_function("!document.querySelector('[data-filters]').hidden")
                        page.wait_for_function("document.querySelectorAll('[data-devices] .monitor-device').length>0")

                    login()
                    assert '자동 재시도' in page.locator('.monitor-share-status').inner_text()
                    assert page.locator('[data-devices] .monitor-device').count() == 3
                    assert '시각 확인 불가' in page.locator('[data-devices]').inner_text()
                    assert '마지막 보고: 송출 예배' in page.locator('[data-devices]').inner_text()
                    page.locator('[data-device-filter]').select_option('fresh')
                    assert page.locator('[data-devices] .monitor-device').count() == 1
                    page.locator('[data-device-filter]').select_option('stale')
                    assert page.locator('[data-devices] .monitor-device').count() == 2
                    page.locator('[data-device-filter]').select_option('error')
                    assert page.locator('[data-devices] .monitor-device').count() == 1
                    page.locator('[data-event-filter]').select_option('error')
                    page.locator('[data-devices] summary').click()
                    assert '예배 저장 흐름 오류' in page.locator('[data-devices]').inner_text()
                    page.locator('[data-device-filter]').select_option('all')
                    page.evaluate("mode='read-error'")
                    page.locator('[data-refresh]').click()
                    page.wait_for_function("document.querySelector('.monitor-message').textContent.includes('이전 조회')")
                    assert page.locator('[data-devices] [data-health=stale]').count() == 3
                    assert 'private-error-detail' not in page.locator('.monitor-panel').inner_text()
                    page.evaluate("mode='ok'")
                    page.locator('[data-refresh]').click()
                    page.wait_for_function("document.querySelector('[data-devices] [data-health=fresh]')")
                    page.evaluate("window.stableRow=document.querySelector('[data-devices] .monitor-device');auditTick();auditTick()")
                    assert page.evaluate("stableRow===document.querySelector('[data-devices] .monitor-device')")

                    page.evaluate("mode='pending'")
                    page.locator('[data-refresh]').click()
                    page.wait_for_function("typeof releaseRead==='function'")
                    page.evaluate('''() => {
                      Object.defineProperty(document,'hidden',{configurable:true,value:true});
                      document.dispatchEvent(new Event('visibilitychange'));
                      releaseRead({data:rows,error:null});
                    }''')
                    page.wait_for_function("document.querySelector('[data-filters]').hidden")
                    assert page.locator('[data-devices]').inner_text() == ''
                    assert page.locator('#monitorPassword').input_value() == ''
                    assert page.evaluate("calls.some(c=>c.name==='mindex_monitor_leave'&&c.args.p_token==='viewer')")
                    page.evaluate("delete document.hidden;mode='ok'")
                    login()
                    page.evaluate('''() => { const now=Date.now;Date.now=()=>now()+6*60*1000;try{auditTick()}finally{Date.now=now} }''')
                    assert page.locator('[data-filters]').is_hidden()
                    assert '자동 잠금' in page.locator('.monitor-message').inner_text()
                    page.locator('#monitorPassword').fill('unsent-password')
                    page.locator('[data-close]').click()
                    page.wait_for_function("document.querySelector('#monitorPassword').value===''")
                    assert page.locator('#monitorPassword').input_value() == ''
                    print(engine, 'PASS heartbeat TTL, stale/invalid reports, filters, error separation, redaction, stable DOM, late read cancellation, idle lock, password clearing')
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
