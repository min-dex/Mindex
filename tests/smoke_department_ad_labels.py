from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda r: r.abort())
            page.goto(url+'?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof serviceElementDisplayLabel === 'function'")
            print(page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              for(const label of ['청소년부 광고','청년부 광고']) {
                const item={id:'fixture',label,raw_title:'1. 이번 주 모임 안내',_worshipSectionKey:'announcements',memo:serializeServiceItemMemo({elementType:'body'})};
                const before=JSON.stringify(item);
                check(serviceElementDisplayLabel(label)==='광고','display label');
                check(liturgicalBodyTitle(item)==='광고','output title');
                check(serviceSidebarChildItemDisplayParts(item).meta==='광고','outline label');
                check(presenterBoardSubgroupDisplay('fixture',{label,title:'',slides:[]}).label==='광고','editor heading');
                check(isLiturgicalBodyServiceItem(item),'body recognition changed');
                check(JSON.stringify(item)===before,'data changed');
                const normalized=normalizeServiceItem({...item,service_id:'11111111-1111-4111-8111-111111111111'});
                check(normalized.label==='광고' && normalized.raw_title===item.raw_title,'canonical label/body');
                check(isAnnouncementTextInputItem(normalized) && liturgicalBodyTitle(normalized)==='광고','renamed body recognition');
                check(liturgicalBodyText(normalized).includes('이번 주 모임 안내'),'body lost');
                const service={id:normalized.service_id,type_id:label==='청소년부 광고'?'youth':'young-adult',date:'2026-09-13'};
                const projected=projectWorshipServiceItemsFromTemplate(service,[normalized]);
                const ads=projected.filter(x=>isAnnouncementTextInputItem(x));
                check(ads.length===1 && ads[0].raw_title===item.raw_title,'duplicate or overwritten announcement');
                const rows=buildWorshipPersistenceRows(service,ads);
                check(rows.elements.length===1 && rows.elements[0].source_ref.label==='광고','saved label');
                const reloaded=groupWorshipElements(rows.sections,rows.elements)[service.id][0];
                check(reloaded.label==='광고' && liturgicalBodyText(reloaded).includes('이번 주 모임 안내'),'reload loses body');
              }
              check(serviceElementDisplayLabel('교회소식')==='교회소식','unrelated label changed');
              check(youthWorshipAnnouncementsStep().elements[0].label==='광고','youth template');
              check(youngAdultWorshipAnnouncementsStep().elements[0].label==='광고','young adult template');
              check(serviceElementDisplayLabel('청년부 광고 특별 안내')==='청년부 광고 특별 안내','custom title changed');
              const prior={id:'10000000-0000-4000-8000-000000000001',type_id:'young-adult',date:'2026-09-13'};
              const created={id:'10000000-0000-4000-8000-000000000002',type_id:'young-adult',date:'2026-09-20'};
              const priorSection={id:'20000000-0000-4000-8000-000000000001',service_id:prior.id,section_key:'announcements',sort_order:9,title:'광고'};
              const priorElement={id:'30000000-0000-4000-8000-000000000001',section_id:priorSection.id,sort_order:1,element_type:'body',title:'',body:'이번 주 청년부 광고',source_ref:{label:'광고',slotKey:'announcements.department'},config:{slides:['이번 주 청년부 광고'],outputMode:'custom'},input_mode:'text',content_state:{state:'filled'}};
              const oldServices=state.services,oldSections=state.worshipSections,oldElements=state.worshipElements,oldLoaded=state.loadedWorshipServiceIds;
              state.services=[prior,created];state.worshipSections=[priorSection];state.worshipElements=[priorElement];state.loadedWorshipServiceIds=new Set([prior.id]);
              const copied=await calendarAssigneeRowsForNewService(created);
              const copiedSection=copied.sections.find(section=>section.section_key==='announcements');
              const copiedElements=copied.elements.filter(element=>element.section_id===copiedSection?.id);
              check(copiedElements.length===1,'department ad count not copied');
              check(copiedElements[0].id!==priorElement.id&&copiedElements[0].body===priorElement.body,'department ad body not copied safely');
              check(!copiedElements[0].config.slides&&!copiedElements[0].config.outputMode&&copiedElements[0].template_modified,'prior layout copied');
              check(copiedSection.source_ref.copied_from_service_id===prior.id,'department ad origin missing');
              const copiedItems=groupWorshipElements(copied.sections,copied.elements)[created.id]||[];
              const copiedRows=buildWorshipPersistenceRows(created,copiedItems,
                Object.fromEntries(copied.sections.map(section=>[section.id,section])),
                Object.fromEntries(copied.elements.map(element=>[element.id,element])));
              validateWorshipPersistenceRows(copiedRows,{serviceId:created.id});
              state.services=oldServices;state.worshipSections=oldSections;state.worshipElements=oldElements;state.loadedWorshipServiceIds=oldLoaded;
              return 'PASS outline, editor and output labels; data and custom names preserved';
            }'''))
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
