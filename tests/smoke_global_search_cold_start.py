from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof ensureGlobalPraiseSearchCatalog === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              canUseClientData=()=>true;finishListRender=()=>{};
              state.services=[];state.songs=[];state.search='갈 길을 밝히';state.module='calendar';
              songCatalogLoaded=false;globalPraiseSearchError='';globalPraiseSearchLoad=null;
              clearSearchCaches();
              let calls=0,resolveLoad;
              loadSongs=()=>{calls++;return new Promise(resolve=>{resolveLoad=()=>{
                state.songs=[{id:'hymn',title:'갈 길을 밝히 보이시니',hymn_no:524,versions:[]}];
                songCatalogLoaded=true;resolve();
              }})};
              renderGlobalSearchList();renderGlobalSearchList();await Promise.resolve();
              check(calls===1,'duplicate fetch');
              check(refs.songList.textContent.includes('찬양 검색 준비 중'),'missing loading state');
              state.search='524장';const pending=globalPraiseSearchLoad;resolveLoad();await pending;
              check(refs.songList.querySelector('[data-global-song-id="hymn"]'),'late load not displayed');
              check(state.search==='524장' && state.module==='calendar','search/module overwritten');
              renderGlobalSearchList();check(calls===1,'loaded catalog refetched');
              for(const module of ['service','presenter','calendar','scripture','praise','home']) {
                state.module=module;state.search='갈 길을 밝히';clearSearchCaches();renderGlobalSearchList();
                check(refs.songList.querySelector('[data-global-song-id="hymn"]'),'title missing '+module);
              }
              songCatalogLoaded=false;state.songs=[];clearSearchCaches();loadSongs=async()=>{calls++;throw Error('offline')};
              renderGlobalSearchList();await globalPraiseSearchLoad;
              const failedCalls=calls;renderGlobalSearchList();
              check(calls===failedCalls && refs.songList.querySelector('[data-global-praise-retry]'),'failure hidden or looping');
              loadSongs=async()=>{calls++;songCatalogLoaded=true;state.songs=[{id:'hymn',title:'갈 길을 밝히 보이시니',versions:[]}]};
              refs.songList.querySelector('[data-global-praise-retry]').click();await globalPraiseSearchLoad;
              check(refs.songList.querySelector('[data-global-song-id="hymn"]'),'retry failed');
              songCatalogLoaded=false;globalPraiseSearchError='';loadSongs=()=>new Promise(resolve=>{resolveLoad=resolve});
              renderGlobalSearchList();await Promise.resolve();const last=globalPraiseSearchLoad;
              state.search='';refs.songList.innerHTML='<p>normal sidebar</p>';songCatalogLoaded=true;resolveLoad();await last;
              check(refs.songList.textContent==='normal sidebar','closed search overwritten');
              return 'PASS cold calendar search, single fetch, latest query, all modules, failure/retry and cleared search';
            }'''), flush=True)
            browser.close()
finally:
    server.shutdown()
