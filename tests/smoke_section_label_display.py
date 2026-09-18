from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterSectionEditorItem === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              const service={id:'label-fixture',type_id:'friday',date:'2026-09-18'};
              state.services=[service];state.selectedServiceId=service.id;
              const items=[{id:'prayer-song',service_id:service.id,label:'기도찬양 1',_origIndex:0,_worshipSectionKey:'prayer',memo:''}];
              state.serviceItems[service.id]=items;
              serviceTemplateHierarchyIndex=()=>({sections:[{key:'prayer',elements:[{label:'기도찬양 1'},{label:'기도찬양 2'}]}]});
              getServiceItems=()=>items;
              const context={service,sectionItems:items};
              const mount=document.createElement('div');
              const before=JSON.stringify(items);
              mount.innerHTML=renderPresenterSectionEditorItem(items[0],0,context);
              const field=mount.querySelector('[data-service-item-field="label"]');
              check(field.value==='기도찬양','single ordinal leaked');
              updateServiceItemField(field,{deferPresenterRefresh:true});
              check(JSON.stringify(items)===before,'untouched display mutated source');
              items.push({...items[0],id:'prayer-song-2',label:'기도찬양 2',_origIndex:1});
              mount.innerHTML=items.map((item,i)=>renderPresenterSectionEditorItem(item,i,context)).join('');
              check([...mount.querySelectorAll('[data-service-item-field="label"]')].map(f=>f.value).join('|')==='기도찬양 1|기도찬양 2','peer numbering mismatch');
              items[0].label='기념 2026';
              mount.innerHTML=renderPresenterSectionEditorItem(items[0],0,context);
              check(mount.querySelector('[data-service-item-field="label"]').value==='기념 2026','custom number removed');
              return 'PASS single/peer/custom labels and no-op source preservation';
            }'''), flush=True)
            browser.close()
finally:
    server.shutdown()
