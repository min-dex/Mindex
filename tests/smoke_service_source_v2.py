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
              const originalSongs=state.songs, originalTranslations=state.bibleTranslations;
              try {
                state.services=[service,...originalServices];
                state.serviceItems[service.id]=[];
                state.songs=[{id:'song-v2',title:'예수 예수',versions:[{id:'version-v2',_worshipVersionPersisted:true}]}];
                state.songLookupSource=null;
                state.bibleTranslations=[{id:'bible-v2',abbreviation:'개역개정'}];
                const records=parseServiceSourceText(`[[특송]]\n\n[특송]\n- 제목: 예수 예수\n- 유형: praise\n- 입력: lyrics_db\n- 출력: lyrics\n- 송폼: V1-C\n- 곡: 예수 예수\n- 곡 ID: song-v2\n- 버전 ID: version-v2\n- 담당: 홍길동\n- 음원 파일: special.m4a\n- 음원 링크: https://example.com/special.m4a\n\n[[말씀]]\n\n[성경봉독]\n- 제목: 요한복음 3:16\n- 유형: scripture\n- 입력: scripture\n- 역본: 개역개정\n- 역본 ID: bible-v2\n- 수동 역본: 테스트역\n- 수동 본문: |\n  16 하나님이 세상을 이처럼 사랑하사\n\n[[광고]]\n\n[참고 화면]\n- 제목: 홍보 영상\n- 유형: video\n- 파일: promo.mp4\n- 링크: https://example.com/promo.mp4`);
                if(records.length!==3 || !records.every(record=>record.portable)) throw Error('v2 blocks not parsed');
                if(records[0].songId!=='song-v2' || records[0].versionId!=='version-v2' || records[1].translationId!=='bible-v2' || !records[1].manualScripture.includes('사랑하사') || records[2].assetUrl!=='https://example.com/promo.mp4') throw Error('v2 metadata lost: '+JSON.stringify(records));
                const added=ensurePortableSourceItems(service,records);
                const items=getServiceItems(service.id);
                const special=items.find(item=>item.label==='특송');
                const reading=items.find(item=>item.label==='성경봉독');
                const media=items.find(item=>item.label==='참고 화면');
                if(added!==3 || !special || !reading || !media) throw Error('v2 elements not created');
                applyServiceSourceRecord(service.id,items.indexOf(special),records[0]);
                applyServiceSourceRecord(service.id,items.indexOf(reading),records[1]);
                const appliedItems=getServiceItems(service.id);
                const appliedSpecial=appliedItems.find(item=>item.label==='특송');
                const appliedReading=appliedItems.find(item=>item.label==='성경봉독');
                const specialMemo=parseServiceItemMemo(appliedSpecial.memo), readingMemo=parseServiceItemMemo(appliedReading.memo);
                if(appliedSpecial.song_id!=='song-v2' || appliedSpecial.version_id!=='version-v2' || specialMemo.audioAsset?.url!=='https://example.com/special.m4a') throw Error('song/audio source fields not applied');
                if(readingMemo.scriptureTranslationId!=='bible-v2' || readingMemo.manualScripture?.translationLabel!=='테스트역' || readingMemo.manualScripture?.verses?.[0]?.text!=='하나님이 세상을 이처럼 사랑하사') throw Error('scripture source fields not applied: '+JSON.stringify(readingMemo));
                return {parsed:records.length,added,specialType:serviceMemoElementType(specialMemo),mediaType:serviceMemoElementType(parseServiceItemMemo(media.memo))};
              } finally {
                state.services=originalServices;
                if(originalItems===undefined) delete state.serviceItems[service.id]; else state.serviceItems[service.id]=originalItems;
                state.songs=originalSongs;
                state.bibleTranslations=originalTranslations;
                state.songLookupSource=null;
              }
            }""")
            if result != {"parsed": 3, "added": 3, "specialType": "praise", "mediaType": "video"}:
                raise RuntimeError(result)
            print("PASS service source v2", result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
