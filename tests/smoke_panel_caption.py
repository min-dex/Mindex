from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={'width': 600, 'height': 900})
        page.route('**/*supabase*/**', lambda route: route.abort())
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("typeof renderPresenterControlsTop==='function'")
        for width in [254, 320, 390]:
            print(page.evaluate("""width => {
              document.body.dataset.theme='dark';document.body.dataset.module='presenter';
              document.body.classList.remove('ui-booting');
              const service={id:'panel-fixture',type_id:'sunday-second',date:'2026-09-20'};
              state.services=[service];state.serviceItems[service.id]=[];
              isPresenterOutputWindowOpen=()=>false;
              document.body.innerHTML='<div id="fixture" class="svc-presenter-side-panel"></div>';
              const host=document.querySelector('#fixture');
              host.style.cssText='position:absolute;top:20px;left:20px;width:'+width+'px;background:var(--sidebar-bg)';
              host.innerHTML=renderPresenterControlsTop(service,[],false,0)+renderPresenterServiceInputRail(service);
              bindDetailInteractionRoot(host);refreshIcons(host);
              state.presenter.serviceId=service.id;state.presenter.index=0;
              state.presenter.safetyBlank=false;state.presenter.liveScripture=null;
              const health=host.querySelector('[data-presenter-video-health]');
              const title=host.querySelector('.svc-presenter-preview-caption > strong');
              title.textContent='길이가 긴 슬라이드 제목도 제목 영역 안에 유지되는지 확인하는 테스트';
              const input=host.querySelector('textarea');
              input.value='찬양1: 입력 중';input.dispatchEvent(new Event('input',{bubbles:true}));
              input.focus();input.setSelectionRange(3,3);
              const tops=()=>['.svc-presenter-live-preview','.svc-presenter-launch','.svc-presenter-input-rail'].map(s=>host.querySelector(s).getBoundingClientRect().top);
              const baseline=tops();
              for(const status of ['loading','error','paused','blocked','playing']){
                state.presenter.videoHealth={serviceId:service.id,index:0,status,receivedAt:Date.now()};
                syncPresenterVideoHealthControl();
                if(JSON.stringify(tops())!==JSON.stringify(baseline)) throw Error('Layout shift '+status);
                if(health.scrollHeight>health.clientHeight+1 || health.scrollWidth>health.clientWidth+1) throw Error('Health overflow '+status);
                if((getComputedStyle(title).visibility==='hidden')!==(status!=='playing')) throw Error('Title overlap '+status);
                if(document.activeElement!==input || input.selectionStart!==3 || input.value!=='찬양1: 입력 중') throw Error('Draft focus changed');
                if(['error','paused','blocked'].includes(status) && health.querySelector('button')?.dataset.presenterAction!=='retry-video') throw Error('Retry lost');
              }
              const utility=host.querySelector('.svc-presenter-utility-actions').getBoundingClientRect();
              const help=host.querySelector('.svc-presenter-help > summary').getBoundingClientRect();
              if(help.height!==34 || help.width!==34 || help.top<utility.top || help.bottom>utility.bottom) throw Error('Help overflows utility row');
              if(host.scrollWidth>host.clientWidth+1) throw Error('Panel overflow');
              return {width,previewTop:baseline[0],utilityHeight:utility.height,helpHeight:help.height};
            }""", width))
            page.screenshot(path=f'/tmp/mindex-panel-spacing-{width}.png')
        browser.close()
finally:
    server.shutdown()
