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
              applyPageTabSnapshot=async(index)=>{state.module=state.pageTabs[index].snapshot.module;};
              openGlobalSongResult=async(id)=>{opened.push(['song',id]);state.module='praise';};
              openGlobalBibleReference=async(ref)=>{opened.push(['bible',ref]);state.module='scripture';};
              state.module='service';state.selectedServiceId='fixture-service';
              state.pageTabs=[newPageTab(currentBrowserHistorySnapshot())];state.pageTabIndex=0;
              const originalId=state.pageTabs[0].id;
              const song=document.createElement('button');song.dataset.serviceDbSong='fixture-song';
              await Promise.all([openServiceDbTab(song),openServiceDbTab(song)]);
              if(state.pageTabs.length!==2 || state.pageTabs[0].id!==originalId
                || state.pageTabs[0].snapshot.selectedServiceId!=='fixture-service'
                || opened.length!==1 || song.disabled) throw Error('Song tab/preservation failed');
              allowed=false;
              await openServiceDbTab(song);
              if(state.pageTabs.length!==2 || song.disabled) throw Error('Cancel created tab');
              allowed=true;
              const bible=document.createElement('button');bible.dataset.serviceDbReference='요한복음 3:16';
              await openServiceDbTab(bible);
              if(state.pageTabs.length!==3 || opened[1]?.[1]!=='요한복음 3:16') throw Error('Bible target lost');
              const markup=renderServicePraiseLinkControl({label:'찬양',song_id:'fixture-song'},0);
              if(!markup.includes('data-service-db-song') || !markup.includes('새 탭')) throw Error('Button contract');
              return {tabs:state.pageTabs.length,opened};
            }""")
            print('PASS new tabs, original service retained, cancel, rapid-click guard, DB targets', result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
