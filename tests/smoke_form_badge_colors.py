from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page(viewport={'width': 900, 'height': 360})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterSlideThumb === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              refreshIcons();
              const door=document.querySelector('.nav-rail-tab[data-home-module="service"] svg path[d="M14 21v-3a2 2 0 0 0-4 0v3"]');
              check(door && getComputedStyle(door).display==='none','church detail not simplified');
              renderPresenterSlideMiniPreview=()=>'';
              const host=document.createElement('div');host.id='badge-test';
              host.style.cssText='padding:24px;display:flex;gap:12px;flex-wrap:wrap';
              for(const [i,label] of ['Verse 1','Verse 2','Chorus','Pre-Chorus','Bridge','Tag','Interlude','Coda','Custom'].entries()) {
                const holder=document.createElement('div');
                holder.innerHTML=renderPresenterSlideThumb({id:'s'+i,title:'Song',text:'Lyrics',type:'lyrics'},i,-1,'fixture',label);
                const badge=holder.querySelector('.svc-slide-form-badge');
                check(badge && badge.dataset.presenterAction==='jump' && badge.dataset.presenterIndex===String(i),'jump target changed');
                host.append(badge);
              }
              const neutral=document.createElement('button');neutral.className='svc-slide-form-badge svc-slide-scripture-reference';neutral.textContent='요한복음 3:16';host.append(neutral);
              document.body.replaceChildren(host);
              const badges=[...host.querySelectorAll('[data-form-type]')];
              check(badges[0].dataset.formType==='verse' && badges[1].dataset.formType==='verse','verse numbering affected type');
              for(const theme of ['light','dark']) {
                document.body.dataset.theme=theme;
                const colors=badges.map(b=>getComputedStyle(b).backgroundColor);
                check(colors[0]===colors[1] && new Set(colors.slice(1,8)).size===7,'type colors not distinct');
                check(badges.every(b=>b.getBoundingClientRect().height===18),'badge height changed');
                check(badges.every(b=>getComputedStyle(b).boxShadow==='none'),'form color rendered as border');
                check(!neutral.hasAttribute('data-form-type'),'scripture received song color');
              }
              return 'PASS simplified icon, type colors, verse consistency, dimensions and jump targets';
            }'''), flush=True)
            for theme in ('light', 'dark'):
                page.evaluate('(theme)=>document.body.dataset.theme=theme', theme)
                page.locator('#badge-test').screenshot(path='/tmp/mindex-form-colors-'+engine+'-'+theme+'.png')
            browser.close()
finally:
    server.shutdown()
