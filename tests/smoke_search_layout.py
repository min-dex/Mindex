from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderGlobalSearchSections === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              songCatalogLoaded=true;state.search='많은 사람들';
              const results={praise:[{id:'song',title:'난 예수가 좋다오',versions:[]}],scripture:[{kind:'text',query:state.search}],service:[]};
              for(const module of ['calendar','home','scripture','praise','service','presenter','manuals']) {
                state.module=module;document.body.dataset.module=module;
                refs.songCount.textContent='1개 표시';refs.songList.innerHTML=renderGlobalSearchSections(results);
                const sections=refs.songList.querySelectorAll('.global-search-section');
                check(sections.length===1 && sections[0].textContent.includes('찬양'),'action mixed into scripture results '+module);
                check(refs.songList.lastElementChild.classList.contains('global-search-actions'),'action not last '+module);
                check(!refs.songList.querySelector('.global-search-result--primary'),'action overemphasized');
                if(['calendar','home'].includes(module)) check(getComputedStyle(refs.songCount.parentElement).display==='none','empty count space '+module);
              }
              state.module='manuals';document.body.dataset.module='manuals';
              state.search='많은 사람들';
              const originalGlobalList=renderGlobalSearchList;
              renderGlobalSearchList=()=>{refs.songList.innerHTML=renderGlobalSearchSections(results)};
              state.auth.session={user:{id:'search-fixture'}};
              renderModuleSwitcher();renderSongList();renderDetail();
              check(!refs.searchInput.disabled && refs.searchInput.placeholder==='검색...','manual search chrome changed');
              check(refs.songList.querySelector('.global-search-section'),'manual global search list missing');
              check(refs.detailPane.querySelector('.home-search-screen'),'manual global search detail missing');
              state.module='calendar';document.body.dataset.module='calendar';
              refs.detailPane.innerHTML='';renderSearchResultsForCurrentModule();
              check(refs.detailPane.querySelector('.home-search-screen'),'calendar global search detail missing');
              renderGlobalSearchList=originalGlobalList;
              state.module='scripture';
              check(getGlobalSearchSectionOrder()[0].id==='scripture','current tab priority changed');
              state.module='calendar';document.body.dataset.module='calendar';document.body.dataset.theme='dark';
              refs.searchInput.value=state.search;
              refs.songList.innerHTML=renderGlobalSearchSections(results);
              return 'PASS hidden count space, real results first, separate action and tab priority';
            }'''), flush=True)
            page.locator('.sidebar').screenshot(path='/tmp/mindex-search-layout-'+engine+'.png')
            browser.close()
finally:
    server.shutdown()
