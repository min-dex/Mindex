from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof serviceNavigationBlocked === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              const absent={id:'absent',type_id:'friday',date:'2026-09-18',_worshipSourceRef:{no_gathering:true}};
              const regular={id:'regular',type_id:'friday',date:'2026-09-25'};
              state.services=[absent,regular];state.selectedServiceId='regular';
              state.serviceTypes=[{id:'friday',name:'금요기도회'}];state.calendarData=[];
              serviceItemPreviewParts=()=>({text:''});
              const before=JSON.stringify(state.services);
              for(const render of [renderServiceDateCard,renderServiceWeekCard]) {
                const host=document.createElement('div');host.innerHTML=render(absent);
                check(host.querySelector('button').disabled,'absent card enabled');
                check(!host.querySelector('[data-service-id]'),'absent navigation attribute');
                check(host.textContent.includes('집회 없음'),'missing status');
                host.innerHTML=render(regular);
                check(!host.querySelector('button').disabled,'regular card disabled');
                check(host.querySelector('[data-service-id]').dataset.serviceId==='regular','regular target missing');
              }
              let loads=0,confirms=0,prepares=0;
              showToast=()=>{};loadServiceItems=async()=>{loads++};
              confirmDiscardServiceChanges=()=>{confirms++;return true};
              preparePresenterService=()=>{prepares++};
              selectService(absent.id);
              await openServiceInPresenter(absent.id);
              await openHomeNextService('service',absent.id);
              await openPresenterOutput(absent.id);
              check(state.selectedServiceId==='regular' && !loads && !confirms && !prepares,'blocked path mutated state');
              check(!serviceNavigationBlocked(regular.id),'missing setlist blocked');
              check(getHomeNextService(new Date('2026-09-17T00:00:00')).id==='regular','home chose absent service');
              state.client={};state.serviceError='';state.selectedServiceId=absent.id;
              state.presenter.viewServiceId=absent.id;state.serviceItems={};
              renderPresenterDetail();
              check(refs.detailPane.textContent.includes('집회 없음') && !loads,'deep link loaded editor');
              check(!refs.detailPane.querySelector('input,textarea,[data-presenter-action]'),'deep link contains controls');
              check(JSON.stringify(state.services)===before,'service records mutated');
              renderCurrentServiceModuleDetail=()=>{};renderServiceList=()=>{};
              syncBrowserHistory=()=>{};captureCleanFingerprint=()=>{};
              selectService(regular.id);
              check(state.selectedServiceId===regular.id && loads===1,'normal navigation broken');
              return 'PASS disabled cards, navigation/output guards, deep link, home exclusion and normal service';
            }'''), flush=True)
            page.locator('#detailPane').screenshot(path='/tmp/mindex-no-gathering-'+engine+'.png')
            browser.close()
finally:
    server.shutdown()
