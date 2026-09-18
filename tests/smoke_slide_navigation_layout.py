from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={'width': 600, 'height': 300})
        page.route('**/*supabase*/**', lambda route: route.abort())
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("typeof renderPresenterControlsTop==='function'")
        for theme in ['light', 'dark']:
            for width in [230, 296, 366]:
                for count in [0, 93, 1120]:
                    result = page.evaluate("""({theme,width,count})=>{
                      document.body.dataset.theme=theme;document.body.classList.remove('ui-booting');
                      const service={id:'nav-fixture',type_id:'sunday-second',date:'2026-09-20'};
                      isPresenterOutputWindowOpen=()=>false;
                      const template=document.createElement('div');
                      template.innerHTML=renderPresenterControlsTop(service,Array.from({length:count},()=>({})),false,0);
                      document.body.innerHTML='<div class="svc-presenter-side-panel" id="fixture"></div>';
                      const host=document.querySelector('#fixture');
                      host.style.cssText='margin:20px;width:'+width+'px;background:var(--sidebar-bg)';
                      host.append(template.querySelector('.svc-presenter-main'));refreshIcons(host);
                      const row=host.firstElementChild;
                      const els=[...row.querySelectorAll('input,button')];
                      const bounds=els.map(el=>el.getBoundingClientRect());
                      if(bounds.some(r=>r.height!==34 || Math.abs(r.top-bounds[0].top)>1)) throw Error('Misaligned control');
                      for(let i=1;i<bounds.length;i++) if(bounds[i].left<bounds[i-1].right) throw Error('Overlap');
                      if(row.scrollWidth>row.clientWidth || host.scrollWidth>host.clientWidth) throw Error('Overflow');
                      const jump=row.querySelector('[data-presenter-jump-button]');
                      if(!jump.title || jump.disabled!==(count===0)) throw Error('Tooltip/disabled state');
                      const counter=row.querySelector('.svc-slide-counter');
                      const total=counter.querySelector('span:not(.svc-presenter-mini-label)').getBoundingClientRect();
                      if(Math.abs(jump.getBoundingClientRect().left-total.right-5)>1) throw Error('Jump not grouped with number');
                      return true;
                    }""", {'theme': theme, 'width': width, 'count': count})
                    assert result
            page.locator('#fixture').screenshot(path=f'/tmp/mindex-slide-navigation-{theme}.png')
        browser.close()
        print('PASS navigation grouping, 34px alignment, 0/93/1120 counts, 3 widths, both themes')
finally:
    server.shutdown()
