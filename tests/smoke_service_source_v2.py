"""Portable service source v2 keeps section/element structure parseable."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_function("typeof parseServiceSourceText === 'function' && typeof ensurePortableSourceItems === 'function'")
            result = page.evaluate("""() => {
              const service={id:'__source_v2__',type_id:'custom',date:'2026-09-23',alias:'테스트'};
              const originalServices=state.services, originalItems=state.serviceItems[service.id];
              try {
                state.services=[service,...originalServices];
                state.serviceItems[service.id]=[];
                const records=parseServiceSourceText(`[[특송]]\n\n[특송]\n- 제목: 예수 예수\n- 유형: praise\n- 입력: manual_praise\n- 송폼: V1-C\n- 담당: 홍길동\n- 가사: |\n  첫 줄\n\n  후렴\n\n[[광고]]\n\n[참고 화면]\n- 제목: 홍보 영상\n- 유형: video\n- 파일: promo.mp4\n- 링크: https://example.com/promo.mp4`);
                if(records.length!==2 || !records.every(record=>record.portable)) throw Error('v2 blocks not parsed');
                if(!records[0].lyrics.includes('첫 줄') || !records[0].lyrics.includes('후렴') || records[1].assetUrl!=='https://example.com/promo.mp4') throw Error('v2 metadata lost: '+JSON.stringify(records));
                const added=ensurePortableSourceItems(service,records);
                const items=getServiceItems(service.id);
                const special=items.find(item=>item.label==='특송');
                const media=items.find(item=>item.label==='참고 화면');
                if(added!==2 || !special || !media) throw Error('v2 elements not created');
                return {parsed:records.length,added,specialType:serviceMemoElementType(parseServiceItemMemo(special.memo)),mediaType:serviceMemoElementType(parseServiceItemMemo(media.memo))};
              } finally {
                state.services=originalServices;
                if(originalItems===undefined) delete state.serviceItems[service.id]; else state.serviceItems[service.id]=originalItems;
              }
            }""")
            if result != {"parsed": 2, "added": 2, "specialType": "praise", "mediaType": "video"}:
                raise RuntimeError(result)
            print("PASS service source v2", result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
