from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof serviceSearchItemText === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              const tick=()=>new Promise(r=>setTimeout(r,0));
              const events=[];let release,fetches=0;
              requireClient=()=>true;canUseClientData=()=>true;
              fetchAllRows=async()=>{fetches++;return {data:[{id:'song',title:'갈 길을 밝히 보이시니',versions:[]}],error:null}};
              yieldToBrowser=async()=>{};
              attachRelationalSongVersions=()=>new Promise(r=>{release=()=>{state.songs[0].versions=[{id:'v',forms:[{lyrics:'새로운 가사'}]}];r()}});
              attachSongRelations=async()=>{};
              renderConnectionStatus=()=>{};renderLoadingStatus=()=>{};
              refreshPresenterForService=()=>events.push('presenter');
              render=()=>events.push('full-render');persistUiState=()=>events.push('persist');
              loadForms=async()=>events.push('forms');updateSaveState=()=>{};finishListRender=()=>{};
              state.services=[];state.songs=[];state.search='갈 길';state.module='calendar';
              state.presenter.serviceId='live';state.presenter.slides=[{id:'live-slide'}];
              state.selectedSongId='editing';state.selectedVersionId='draft-version';state.forms=[{lyrics:'unsaved'}];
              songCatalogLoaded=false;globalPraiseSearchError='';globalPraiseSearchLoad=null;
              const before=JSON.stringify([state.presenter,state.forms,state.selectedSongId,state.selectedVersionId]);
              ensureGlobalPraiseSearchCatalog();await tick();
              check(refs.songList.querySelector('[data-global-song-id="song"]'),'title waited for lyrics');
              const pending=globalPraiseSearchLoad;
              state.search='새로운 가사';release();await pending;
              check(refs.songList.querySelector('[data-global-song-id="song"]'),'lyric cache was stale');
              check(events.length===0,'search caused UI/output/editor side effects: '+events);
              check(JSON.stringify([state.presenter,state.forms,state.selectedSongId,state.selectedVersionId])===before,'live/draft changed');
              check(fetches===1,'duplicate catalog request');
              songCatalogLoaded=false;state.selectedSongId=null;state.search='';
              const search=loadSongs({searchOnly:true});await tick();
              const normal=loadSongs();release();await Promise.all([search,normal]);
              check(fetches===2 && events.includes('presenter') && events.includes('full-render'),'normal concurrent load behavior lost');
              events.length=0;
              fetchAllRows=async()=>({error:Error('offline')});state.connectionError='existing';
              await loadSongs({searchOnly:true}).then(()=>{throw Error('expected failure')},()=>{});
              check(state.connectionError==='existing' && events.length===0,'search failure changed global screen');
              const service={id:'svc',type_id:'friday',date:'2026-09-18'};
              state.services=[service];state.serviceTypes=[{id:'friday',name:'금요기도회',fixed_items:[{label:'기본 순서',raw_title:'기본 제목'}]}];
              state.serviceItems={svc:[{label:'설교',raw_title:'첫 제목'}]};
              getServiceItems=()=>{throw Error('search projected editor items')};
              const original=JSON.stringify(state.serviceItems);
              check(serviceMatchesSearch(service,'첫 제목'),'stored title missing');
              const cached=serviceSearchItemTextCache.get(service);
              check(serviceMatchesSearch(service,'기본 제목'),'default title missing');
              check(serviceSearchItemTextCache.get(service)===cached,'unchanged item index rebuilt');
              check(JSON.stringify(state.serviceItems)===original,'search mutated service');
              state.serviceItems.svc[0].raw_title='수정 제목';
              check(serviceMatchesSearch(service,'수정 제목') && !serviceMatchesSearch(service,'첫 제목'),'item cache stale');
              return 'PASS progressive results, live/draft isolation, concurrent normal load, failure isolation and read-only service index';
            }'''), flush=True)
            browser.close()
finally:
    server.shutdown()
