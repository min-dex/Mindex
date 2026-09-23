"""The sermon source shows and edits the canonical scripture-reading reference."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_function("typeof buildServiceSourceText === 'function'")
            result = page.evaluate("""() => {
              const service={id:'sermon-source-fixture',type_id:'custom',date:'2026-09-23',alias:'테스트'};
              const oldServices=state.services, oldItems=state.serviceItems[service.id];
              try {
                state.services=[service,...oldServices];
                state.serviceItems[service.id]=[
                  normalizeServiceItem({service_id:service.id,label:'성경봉독',raw_title:'요한복음 3:16',_worshipSectionKey:'scripture_reading',memo:serializeServiceItemMemo({elementType:'scripture_body',inputMode:'scripture',scriptureReferences:['요한복음 3:16']})}),
                  normalizeServiceItem({service_id:service.id,label:'설교',raw_title:'하나님의 사랑',_worshipSectionKey:'sermon',_worshipSlotKey:'sermon.title',memo:serializeServiceItemMemo({elementType:'title_person'})}),
                ];
                const source=buildServiceSourceText(service);
                if(!source.includes('[설교]') || !source.includes('- 제목: 하나님의 사랑') || !source.includes('- 성경 본문: 요한복음 3:16')) throw Error('sermon reference missing: '+source);
                const sermonRecord=parseServiceSourceText(source).find(record=>record.label==='설교');
                if(!sermonRecord?.hasLinkedScripture) throw Error('sermon reference not parsed');
                sermonRecord.linkedScriptureValue='요한복음 3:17';
                applyServiceSourceRecord(service.id,1,sermonRecord);
                const reading=getServiceItems(service.id)[0];
                if(reading.raw_title!=='요한복음 3:17') throw Error('canonical reading not updated: '+reading.raw_title);
                return {source,reading:reading.raw_title};
              } finally {
                state.services=oldServices;
                if(oldItems===undefined) delete state.serviceItems[service.id]; else state.serviceItems[service.id]=oldItems;
              }
            }""")
            if result["reading"] != "요한복음 3:17":
                raise RuntimeError(result)
            print("PASS sermon source scripture reference", result["reading"])
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
