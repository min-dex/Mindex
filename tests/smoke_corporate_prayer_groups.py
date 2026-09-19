from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda r: r.abort())
            page.goto(url+'?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof mergeMonthlyCorporatePrayerItems === 'function'")
            page.add_style_tag(path='styles.css')
            result = page.evaluate('''() => {
              const check=(value,message)=>{if(!value)throw new Error(message)};
              const service={id:'11111111-1111-4111-8111-111111111111',type_id:'monthly',date:'2026-08-07'};
              const sectionId='22222222-2222-4222-8222-222222222222';
              const topics=['교회 부흥을 위해','선교와 민족을 위해','치유와 회복을 위해','교회학교를 위해'];
              const prayers=topics.map((title,i)=>({id:`33333333-3333-4333-8333-33333333333${i}`,service_id:service.id,
                label:`공동기도 ${i+1}`,raw_title:title,assignee:`담당 ${i+1}`,song_id:null,
                _worshipSectionKey:'corporate_prayer',_worshipSectionId:sectionId,_worshipSectionOrder:8,
                _worshipSectionTitle:'공동기도',_worshipElementOrder:i<2?i+1:i+2,sort_order:8001+i,
                memo:serializeServiceItemMemo({elementType:'title_person',inputMode:'text'})}));
              const song={...prayers[0],id:'44444444-4444-4444-8444-444444444444',label:'기도찬양',
                raw_title:'나의 반석이신 하나님',assignee:'',song_id:'55555555-5555-4555-8555-555555555555',
                _worshipElementOrder:3,sort_order:8003,memo:serializeServiceItemMemo({elementType:'praise',inputMode:'lyrics_db'})};
              const original=[prayers[0],prayers[1],song,prayers[2],prayers[3]];
              const before=JSON.stringify(original);
              const merged=mergeMonthlyCorporatePrayerItems(original);
              check(JSON.stringify(original)===before,'input mutated');
              check(merged.map(x=>x.label).join('|')==='공동기도 1·2|기도찬양|공동기도 3·4','wrong grouping');
              check(merged[1]===song,'song changed');
              check(JSON.stringify(mergeMonthlyCorporatePrayerItems(merged))===JSON.stringify(merged),'not idempotent');
              check(mergeMonthlyCorporatePrayerItems([...merged,prayers[1],prayers[3]]).length===3,'saved legacy rows reappear');
              const slides=presenterMonthlyCorporatePrayerSlides(merged[2],{sectionKey:'corporate_prayer'},0,parseServiceItemMemo(merged[2].memo));
              check(slides[0].title===topics[2] && slides[0].assignee==='담당 3','output missing person');
              check(slides[1].title===topics[3] && slides[1].assignee==='담당 4','output missing second person');
              const html=renderPresenterMonthlyCorporatePrayerInputs(merged[2],2,parseServiceItemMemo(merged[2].memo),service.id);
              check((html.match(/data-service-item-field="corporate_prayer_assignee"/g)||[]).length===2,'missing assignee inputs');
              // Linked songs must resolve in the catalog before save rows are built.
              state.songs=[{id:song.song_id,title:song.raw_title,versions:[]}];
              const rows=buildWorshipPersistenceRows(service,merged);
              validateWorshipPersistenceRows(rows,{serviceId:service.id});
              check(rows.elements.length===3,'wrong persisted row count');
              const legacyConfig={inputMode:'text',elementType:'title_person'};
              const migratedConfig=serviceElementConfigForSave(legacyConfig,parseServiceItemMemo(merged[2].memo),{item:merged[2],service});
              check(migratedConfig.templateKey==='monthly_corporate_prayer_group','existing row loses group type');
              const loaded=groupWorshipElements(rows.sections,rows.elements)[service.id];
              const group=loaded.find(x=>x.label==='공동기도 3·4');
              check(parseServiceItemMemo(group.memo).corporatePrayers[1].assignee==='담당 4','save reload loses person');
              const projected=projectWorshipServiceItemsFromTemplate(service,loaded).filter(x=>templateProjectionSectionKey(x)==='corporate_prayer');
              check(projected.length===3,'template duplicates groups: '+projected.map(x=>x.label));
              check(projected.map(x=>x.label).join('|')==='공동기도 1·2|기도찬양|공동기도 3·4','projected order incorrect');
              const editedMemo=parseServiceItemMemo(group.memo);
              editedMemo.corporatePrayers[0].title='';
              editedMemo.corporatePrayers[0].assignee='변경 담당';
              const edited=parseServiceItemMemo(serializeServiceItemMemo(editedMemo));
              check(edited.corporatePrayers[0].title==='' && edited.corporatePrayers[1].title===topics[3],'blank title shifts second prayer');
              check(edited.corporatePrayers[0].assignee==='변경 담당','edited person lost');
              state.services=[service]; state.selectedServiceId=service.id; state.serviceItems[service.id]=merged;
              const oldRefresh=refreshPresenterForService,oldSave=updateSaveState;
              refreshPresenterForService=()=>{}; updateSaveState=()=>{};
              try {
                const groupIndex=getServiceItems(service.id).findIndex(x=>x.label==='공동기도 3·4');
                updateServiceItemField({dataset:{serviceId:service.id,serviceItemIndex:String(groupIndex),serviceItemField:'corporate_prayer_assignee',corporatePrayerTopicIndex:'1'},value:'새 담당'});
                const current=state.serviceItems[service.id].find(x=>x.label==='공동기도 3·4');
                check(parseServiceItemMemo(current.memo).corporatePrayers[1].assignee==='새 담당','input handler does not save assignee');
              } finally {refreshPresenterForService=oldRefresh;updateSaveState=oldSave;}
              const duplicate=[...original,{...prayers[0],id:'duplicate'}];
              check(mergeMonthlyCorporatePrayerItems(duplicate).some(x=>x.id==='duplicate'),'ambiguous duplicate lost');
              document.body.className='';
              document.body.innerHTML='<main style="padding:24px;width:100%;box-sizing:border-box">'+html+'</main>';
              return {labels:merged.map(x=>x.label),slots:rows.elements.map(x=>x.source_ref.slotKey),roundtrip:true};
            }''')
            print('PASS', result)
            page.screenshot(path='/private/tmp/mindex-corporate-prayer-editor.png')
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
