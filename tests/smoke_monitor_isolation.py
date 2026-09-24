from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    context = browser.new_context()
                    context.route('**/*supabase*/**', lambda r: r.abort())
                    context.add_init_script('''const originalInterval=window.setInterval;
                      window.setInterval=(fn,ms,...args)=>{if(ms===15000&&String(fn).includes('snapshot()'))window.monitorTick=fn;return originalInterval(fn,ms,...args)};''')
                    controller = context.new_page()
                    controller.goto(url, wait_until='domcontentloaded')
                    controller.wait_for_function("typeof monitorTick==='function'")
                    print(engine, controller.evaluate('''async () => {
                      const check=(v,m)=>{if(!v)throw Error(m)};
                      const slides=Array.from({length:300},(_,i)=>({id:'s'+i,type:'title-assignee',text:'Slide '+i,layout:'lower-bar-text'}));
                      const payload={serviceId:'monitor-perf',chromakey:true,slides,index:0};
                      state.services=[{id:'monitor-perf',date:'2026-09-13',type_id:'sunday-main'}];
                      state.presenter.serviceId='monitor-perf';state.presenter.slides=slides;state.presenter.index=0;
                      window.requests=0;
                      state.client={rpc:()=>({abortSignal:signal=>{requests++;return new Promise((resolve,reject)=>{
                        signal.addEventListener('abort',()=>reject(Error('offline')),{once:true});window.releaseMonitor=resolve;
                      });}})};
                      const measure=()=>{
                        const times=[];
                        for(let i=0;i<60;i++){
                          const start=performance.now();monitorTick();publishPresenterPayload({...payload,index:i});times.push(performance.now()-start);
                        }
                        return times.sort((a,b)=>a-b)[Math.floor(times.length*.95)];
                      };
                      measure();const off=measure();check(requests===0,'disabled telemetry made requests');
                      const toggle=document.querySelector('[data-share]');toggle.checked=true;toggle.dispatchEvent(new Event('change'));
                      await Promise.resolve();const on=measure();
                      check(requests===1,'slow network created overlapping telemetry requests');
                      check(state.presenter.index===0&&state.presenter.slides===slides,'monitor mutated presenter');
                      check(on<Math.max(20,off+15),'monitor caused large synchronous latency regression');
                      toggle.checked=false;toggle.dispatchEvent(new Event('change'));
                      releaseMonitor({data:null,error:null});await Promise.resolve();
                      return {offP95ms:off,onWithStalledNetworkP95ms:on,requests};
                    }'''))
                    # Isolate the video fixture from the controller's persisted slide payload.
                    output = browser.new_page()
                    output.route('**/*supabase*/**', lambda r: r.abort())
                    output.goto(url+'?output=presenter', wait_until='domcontentloaded')
                    output.wait_for_selector('#presenterOutputRoot', state='attached')
                    assert output.locator('.monitor-panel').count() == 0
                    assert output.evaluate("typeof monitorTick==='undefined'")
                    output.evaluate('''() => { window.fixture={serviceId:'video-isolation',index:0,chromakey:true,slides:[{id:'video',type:'video',elementType:'video',layout:'media',videoSrc:'assets/presenter/chromakey-ready-loop-pingpong.mp4',playback:{autoplay:true,muted:true}}]};renderPresenterOutput(fixture);window.firstVideo=document.querySelector('.is-active video'); }''')
                    output.wait_for_function('firstVideo.currentTime>.15')
                    output.evaluate('renderPresenterOutput(fixture)')
                    assert output.evaluate("firstVideo===document.querySelector('.is-active video')&&!firstVideo.paused")
                    print(engine, 'PASS output route has no monitor timer/UI, video playing without replacement')
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
