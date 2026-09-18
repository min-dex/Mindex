from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof mountDeferredPresenterBoardSections === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(value,label)=>{if(!value)throw Error(label)};
              const service={id:'rapid-scroll',type_id:'sunday'};
              const slides=Array.from({length:140},(_,index)=>({
                id:'slide-'+index,sectionId:'section-'+Math.floor(index/7),
                sectionTitle:'찬양 '+(Math.floor(index/7)+1), elementId:'element-'+Math.floor(index/7),
                type:'lyrics',elementType:'praise',layout:'center-text',title:'찬양',text:'가사 '+index,
              }));
              state.module='presenter';state.selectedServiceId=service.id;state.services=[service];
              state.presenter.serviceId=service.id;state.presenter.slides=slides;state.presenter.index=0;
              presenterSlidesForService=()=>slides;patchPresenterSidebarServiceSummary=()=>{};
              patchPresenterSidebarOutline=()=>{};patchServiceOutlineActiveState=()=>{};updateSaveState=()=>{};
              refs.detailPane.style.cssText='height:500px;overflow:auto';
              refs.detailPane.innerHTML=renderServicePresenterControls(service,slides,true,0);
              const root=document.getElementById('servicePresenterControls');
              mountDeferredPresenterBoardSections(root,service.id,slides);
              check(root.querySelector('[data-presenter-deferred-board-section]'),'fixture did not defer');
              refs.detailPane.scrollTop=refs.detailPane.scrollHeight;
              refs.detailPane.dispatchEvent(new Event('scroll'));
              const immediateVisible=[...root.querySelectorAll('[data-presenter-deferred-board-section]')].filter(node=>{
                const rect=node.getBoundingClientRect(), pane=refs.detailPane.getBoundingClientRect();
                return rect.bottom>pane.top && rect.top<pane.bottom;
              });
              check(!immediateVisible.length,'visible deferred board blank during scroll');
              await new Promise(resolve=>setTimeout(resolve,180));
              const visibleDeferred=[...root.querySelectorAll('[data-presenter-deferred-board-section]')].filter(node=>{
                const rect=node.getBoundingClientRect(), pane=refs.detailPane.getBoundingClientRect();
                return rect.bottom>pane.top && rect.top<pane.bottom;
              });
              check(!visibleDeferred.length,'visible deferred board left blank after rapid scroll');
              check(root.querySelectorAll('.svc-slide-thumb').length>10,'deferred slides were not hydrated');
              return 'PASS rapid scroll hydrates visible controller sections';
            }'''), flush=True)
            browser.close()
finally:
    server.shutdown()
