from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={'width': 800, 'height': 950})
        page.route('**/*supabase*/**', lambda route: route.abort())
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("typeof renderPresenterControlsTop==='function'")
        print(page.evaluate("""() => {
          document.body.dataset.module='presenter';document.body.dataset.theme='dark';
          document.body.classList.remove('ui-booting');document.body.classList.add('right-sidebar-open');
          const service={id:'bottom-fixture',type_id:'sunday-second',date:'2026-09-20'};
          state.services=[service];state.serviceItems[service.id]=[];
          isPresenterOutputWindowOpen=()=>false;
          document.body.innerHTML='<aside class="right-sidebar" id="fixture"><div class="svc-presenter-side-panel"></div></aside>';
          const sidebar=document.querySelector('#fixture'), panel=sidebar.firstElementChild;
          sidebar.style.cssText='position:fixed;top:10px;left:10px;width:320px;height:850px;box-sizing:border-box';
          panel.innerHTML=renderPresenterControlsTop(service,[],false,0)+renderPresenterServiceInputRail(service);
          bindDetailInteractionRoot(panel);refreshIcons(panel);
          const input=panel.querySelector('textarea'),rail=panel.querySelector('.svc-presenter-input-rail');
          input.value='찬양1: 초안 유지';input.dispatchEvent(new Event('input',{bubbles:true}));
          input.focus();input.setSelectionRange(3,3);
          const inputHeight=input.getBoundingClientRect().height;
          for(const width of [254,320,390]) for(const height of [850,400]){
            sidebar.style.width=width+'px';sidebar.style.height=height+'px';sidebar.scrollTop=0;
            const r=rail.getBoundingClientRect(),s=sidebar.getBoundingClientRect();
            const top=panel.querySelector('.svc-presenter-top').getBoundingClientRect();
            const padding=parseFloat(getComputedStyle(sidebar).paddingBottom);
            if(height===850 && Math.abs(r.bottom-(s.bottom-padding))>1) throw Error('Input not at bottom');
            if(r.top<top.bottom) throw Error('Controls overlap');
            if(height===400 && sidebar.scrollHeight<=sidebar.clientHeight) throw Error('Short panel cannot scroll');
            if(getComputedStyle(rail).borderTopWidth!=='0px') throw Error('Divider remains');
            if(input.getBoundingClientRect().height!==inputHeight || input.value!=='찬양1: 초안 유지'
              || document.activeElement!==input || input.selectionStart!==3) throw Error('Input changed');
          }
          sidebar.style.width='320px';sidebar.style.height='850px';
          return 'PASS bottom alignment, short-panel scroll, no overlap, unchanged input/focus at 3 widths';
        }"""))
        page.screenshot(path='/tmp/mindex-panel-input-bottom.png')
        browser.close()
finally:
    server.shutdown()
