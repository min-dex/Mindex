from smoke_app import launch_chromium, start_local_app_server, sync_playwright


server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ("chrome", "webkit"):
            browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("typeof renderManualsDetail === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(value,message)=>{if(!value)throw Error(message)};
              state.module='manuals';state.search='';render();
              const sections=[...refs.detailPane.querySelectorAll('.manual-section')];
              const links=[...refs.detailPane.querySelectorAll('.manuals-index a')];
              const quickLinks=[...refs.detailPane.querySelectorAll('.manuals-quickstart a')];
              check(sections.length>8,'manual sections missing');
              check(links.length===sections.length,'manual index count');
              check(quickLinks.length===4,'manual quick start count');
              check(refs.detailPane.querySelector('.manuals-notice'),'manual source notice missing');
              check(refs.detailPane.querySelectorAll('.manual-checklist-group').length>=4,'manual paragraph groups missing');
              check(refs.detailPane.querySelector('.manuals-head p'),'manual summary missing');
              check(sections.every((section,index)=>section.id && links[index].getAttribute('href')===`#${section.id}`),'manual index targets');
              check(quickLinks.every(link=>refs.detailPane.querySelector(link.getAttribute('href'))),'manual quick start targets');
              check(sections.every(section=>section.querySelector('.manual-section-head') && section.querySelector('.manual-section-content')),'manual section hierarchy');
              return 'PASS manual summary, quick start targets and section hierarchy';
            }'''))
            page.locator('#detailPane').screenshot(path=f'/tmp/mindex-manuals-{engine}-desktop.png')
            page.set_viewport_size({"width": 640, "height": 1000})
            page.locator('#detailPane').screenshot(path=f'/tmp/mindex-manuals-{engine}-mobile.png')
            browser.close()
finally:
    server.shutdown()
