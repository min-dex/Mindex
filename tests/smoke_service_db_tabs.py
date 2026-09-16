from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof openServiceDbTab === 'function'")
            result = page.evaluate("""async () => {
              let allowed=true, opened=[];
              confirmSaveBeforeLeaving=async()=>allowed;
              applyPageTabSnapshot=async(index)=>{
                const snapshot=state.pageTabs[index].snapshot;
                opened.push(snapshot.module);state.module=snapshot.module;
                state.selectedSongId=snapshot.selectedSongId;
                state.selectedServiceId=snapshot.selectedServiceId;
              };
              state.module='service';state.selectedServiceId='fixture-service';
              state.pageTabs=[newPageTab(currentBrowserHistorySnapshot()),newPageTab({module:'calendar'})];state.pageTabIndex=0;
              const originalId=state.pageTabs[0].id;
              const song=document.createElement('button');song.dataset.serviceDbSong='fixture-song';
              await Promise.all([openServiceDbTab(song),openServiceDbTab(song)]);
              if(state.pageTabs.length!==3 || state.pageTabs[0].id!==originalId
                || state.pageTabs[0].snapshot.selectedServiceId!=='fixture-service'
                || opened.join()!=='praise' || song.disabled
                || state.pageTabs[1].snapshot.selectedSongId!=='fixture-song') throw Error('Song tab/preservation failed');
              if(sanitizePageTab(state.pageTabs[1]).openerTabId!==originalId) throw Error('Opener persistence lost');
              allowed=false;
              await openServiceDbTab(song);
              if(state.pageTabs.length!==3 || song.disabled) throw Error('Cancel created tab');
              await closePageTab(1);
              if(state.pageTabs.length!==3 || state.pageTabIndex!==1) throw Error('Close cancellation lost tab');
              allowed=true;
              await Promise.all([closePageTab(1),closePageTab(1)]);
              if(state.pageTabs.length!==2 || state.pageTabs[state.pageTabIndex].id!==originalId) throw Error('Did not return to opener');
              const bible=document.createElement('button');bible.dataset.serviceDbReference='요한복음 3:16-18';
              await openServiceDbTab(bible);
              const bibleSnapshot=state.pageTabs[1].snapshot;
              if(state.pageTabs.length!==3 || opened.at(-1)!=='scripture'
                || bibleSnapshot.selectedBibleChapter!==3 || bibleSnapshot.selectedBibleVerse!==16
                || bibleSnapshot.selectedBibleVerseEnd!==18) throw Error('Bible target lost');
              await closePageTab(0);
              if(state.module!=='scripture' || state.pageTabIndex!==0) throw Error('Background close changed active tab');
              await closePageTab(0);
              if(state.pageTabs.length!==1 || state.module!=='calendar') throw Error('Missing opener fallback');
              if(opened.includes('home')) throw Error('Unnecessary home render');
              const markup=renderServicePraiseLinkControl({label:'찬양',song_id:'fixture-song'},0);
              if(!markup.includes('data-service-db-song') || !markup.includes('새 탭')) throw Error('Button contract');
              return {tabs:state.pageTabs.length,opened};
            }""")
            print('PASS direct DB tabs, cancel/duplicate close, opener return/fallback, scripture range', result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
