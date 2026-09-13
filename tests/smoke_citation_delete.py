from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page()
                    page.route('**/*supabase*/**', lambda r:r.abort())
                    page.goto(url+'?output=presenter', wait_until='domcontentloaded')
                    page.wait_for_function("typeof buildWorshipPersistenceRows === 'function'")
                    print(engine, page.evaluate('''async () => {
                      const check=(v,m)=>{if(!v)throw Error(m)};
                      const service={id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',type_id:'audit-fixture',date:'2026-09-13'};
                      const columns={inputMode:true,contentState:true};
                      const initial=normalizeServiceItem({label:'인용 구절',raw_title:'요한복음 3:16; 로마서 8:1',_worshipSectionKey:'sermon',_worshipSectionTitle:'설교',_worshipSlotKey:'sermon.citations',
                        memo:serializeServiceItemMemo({elementType:'scripture_body',scriptureReferences:['요한복음 3:16','로마서 8:1'],scriptureReference:'요한복음 3:16',scriptureReferencePayloads:[{reference:'요한복음 3:16',scriptureTranslationId:'translation-a'}]})},0);
                      const base=buildWorshipPersistenceRows(service,[initial],{},{},{elementTypedStateColumns:columns});
                      const old=base.elements[0];
                      old.config.scriptureReference='요한복음 3:16';
                      old.source_ref.scriptureReferences=['요한복음 3:16','로마서 8:1'];
                      old.source_ref.customNote='keep';
                      const sectionMap=Object.fromEntries(base.sections.map(s=>[s.id,s]));
                      const elementMap={[old.id]:old};
                      const fresh=()=>groupWorshipElements(base.sections,base.elements)[service.id][0];
                      state.services=[service];state.selectedServiceId=service.id;state.client=null;
                      schedulePresenterRefreshForService=()=>{};refreshPresenterForService=()=>{};updateSaveState=()=>{};
                      const edit=value=>{
                        const field=document.createElement('input');field.dataset.serviceId=service.id;
                        field.dataset.serviceItemField='raw_title';field.dataset.serviceItemIndex='0';field.value=value;
                        updateServiceItemField(field,{deferPresenterRefresh:true,resolveSongSelection:false});
                      };
                      for(const value of ['로마서 8:1','']) {
                        state.serviceItems={[service.id]:[fresh()]};edit(value);
                        const edited=state.serviceItems[service.id][0];
                        const rows=buildWorshipPersistenceRows(service,[edited],sectionMap,elementMap,{elementTypedStateColumns:columns});
                        const restored=groupWorshipElements(rows.sections,rows.elements)[service.id][0];
                        const refs=serviceItemScriptureReferences(restored);
                        check(JSON.stringify(refs)===JSON.stringify(value?[value]:[]),'deleted citation restored: '+JSON.stringify({refs,edited,element:rows.elements[0]}));
                        check(rows.elements[0].source_ref.customNote==='keep','unrelated metadata removed');
                        check(parseServiceItemMemo(edited.memo).scriptureReferencePayloads.length===0,'removed reference payload retained');
                      }
                      state.serviceItems={[service.id]:[fresh()]};
                      let release;fetchServiceScriptureVerses=()=>new Promise(r=>{release=r});
                      const oldItem=state.serviceItems[service.id][0];
                      oldItem.raw_title='요한복음 3:16';oldItem.memo=serializeServiceItemMemo({elementType:'scripture_body',scriptureReference:'요한복음 3:16',scriptureReferences:['요한복음 3:16']});
                      const pending=resolveServiceScriptureBodyReference(service.id,0,{renderDetail:false});
                      state.serviceItems[service.id]=JSON.parse(JSON.stringify(state.serviceItems[service.id]));
                      edit('');release([{verse:16,text:'test'}]);await pending;
                      check(serviceItemScriptureReferences(state.serviceItems[service.id][0]).length===0,'late lookup restored deleted citation');
                      return 'PASS partial/full deletion roundtrip, metadata preservation, removed payloads, late lookup after cloned items';
                    }'''))
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
