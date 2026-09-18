from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page()
        page.route('**/*supabase*/**', lambda route: route.abort())
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("typeof getGlobalSearchResults==='function'")
        print(page.evaluate("""async () => {
          const check=(value,message)=>{if(!value)throw Error(message)};
          const songs=[
            {id:'hymn',title:'구주의 십자가 보혈로',hymn_no:250,versions:[]},
            {id:'ccm',title:'주 은혜임을',original_title:'Your Grace',metadata:{artist:'테스트팀'},
              versions:[{id:'v',version_name:'기본',forms:[{lyrics:'상한 나의 맘 보시네'}]}]},
            {id:'other',title:'다른 찬양',versions:[]},
          ];
          state.songs=songs;state.services=[];clearSearchCaches();
          const cases=[['구주의십자가','hymn'],['ㄱㅈㅇ','hymn'],['250','hymn'],
            ['250장','hymn'],['찬 250','hymn'],['찬송가 250장','hymn'],
            ['250 구주의','hymn'],['Your Grace','ccm'],['주 은혜임을 테스트팀','ccm'],
            ['상한 나의 맘','ccm']];
          for(const moduleName of ['home','praise','service','presenter']){
            state.module=moduleName;
            for(const [query,id] of cases){
              state.search=query;
              check(getGlobalSearchResults().praise[0]?.song.id===id, moduleName+' '+query);
            }
          }
          state.search='zzznomatch';clearSearchCaches();
          check(getGlobalSearchResults().praise.length===0,'Unmatched praise');
          renderGlobalSearchList();check(refs.songCount.textContent==='0개 표시','Action counted as result');
          const query='요한복음 3:16-18';
          const range=getGlobalScriptureResults(query,getSearchTokens(query)).find(r=>r.kind==='reference');
          check(range.verseEnd===18,'Range dropped');
          check(renderGlobalScriptureResult(range).includes('data-global-verse-end="18"'),'Range markup dropped');
          const originalOpenBook=openGlobalBookResult;
          const selected=[];
          selectScriptureBook=async(book,options)=>selected.push({book,...options});
          state.module='scripture';
          refs.songList.innerHTML=renderGlobalScriptureResult(range);
          refs.songList.querySelector('[data-global-book-code]').click();
          await new Promise(resolve=>setTimeout(resolve,0));
          check(selected[0]?.verse===16 && selected[0]?.verseEnd===18,'Click range navigation');
          const calls=[];
          openGlobalSongResult=async id=>calls.push(['praise',id]);
          openGlobalServiceResult=async id=>calls.push(['service',id]);
          openGlobalBookResult=async(code,options)=>calls.push(['scripture',code,options]);
          getScriptureSearchShortcut=async()=>null;
          const resultFixture={praise:[{song:songs[1]}],scripture:[range],
            service:[{id:'service'}]};
          getGlobalSearchResults=()=>resultFixture;
          for(const [moduleName,kind,id] of [['praise','praise','ccm'],['service','service','service'],['home','praise','ccm']]){
            state.module=moduleName;state.search='fixture';
            await handleSearchKeydown({key:'Enter',preventDefault(){}});
            check(calls.at(-1)[0]===kind && calls.at(-1)[1]===id,'Enter target '+moduleName);
          }
          const count=calls.length;
          await handleSearchKeydown({key:'Enter',isComposing:true,preventDefault(){}});
          await handleSearchKeydown({key:'Enter',keyCode:229,preventDefault(){}});
          check(calls.length===count,'IME Enter navigated');
          getScriptureSearchShortcut=async()=>{state.search='new typing';return null;};
          await handleSearchKeydown({key:'Enter',preventDefault(){}});
          check(calls.length===count,'Stale query navigated');
          return 'PASS 40 praise queries, lyrics scope, hymn aliases, mixed fields, range click, Enter, IME, stale input';
        }"""))
        browser.close()
finally:
    server.shutdown()
