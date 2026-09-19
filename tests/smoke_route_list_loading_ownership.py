from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chromium", "webkit"):
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                page = browser.new_page()
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof appendRouteParams === 'function'")
                result = page.evaluate('''() => {
                  const check=(value,label)=>{if(!value)throw Error(label)};
                  const route=(snapshot)=>{const params=new URLSearchParams();appendRouteParams(params,snapshot);return params};
                  const base={module:'scripture',search:'은혜',selectedSongId:'song',selectedVersionId:'version',selectedScriptureId:'scripture',selectedBookCode:'MAT',selectedBibleTranslationId:'krv',selectedBibleChapter:5,selectedBibleVerse:4,selectedServiceTypeId:'sunday',selectedServiceId:'service',bibleTextSearchQuery:'사랑',bibleTextSearchPage:2};
                  const scripture=route(base);
                  check(!scripture.has('songId')&&!scripture.has('versionId')&&!scripture.has('service'),'scripture URL retained foreign context');
                  check(scripture.get('scriptureId')==='scripture'&&scripture.get('book')==='MAT','scripture URL lost own context');
                  const praise=route({...base,module:'praise'});
                  check(praise.get('songId')==='song'&&praise.get('versionId')==='version','praise URL lost own context');
                  check(!praise.has('scriptureId')&&!praise.has('service'),'praise URL retained foreign context');

                  const copiedPraise={label:'찬양 8',_worshipSectionKey:'praise',_worshipSlotKey:'praise.song.1',memo:''};
                  check(serviceItemSlotKey(copiedPraise)==='praise.song.8','renamed copied praise retained stale slot');
                  const copiedPraiseNine={label:'찬양 9',_worshipSectionKey:'praise',_worshipSlotKey:'praise.song.1',memo:''};
                  check(serviceItemSlotKey(copiedPraiseNine)==='praise.song.9','second renamed copied praise retained stale slot');

                  state.module='scripture';state.loadingModules=new Set(['praise']);
                  check(!currentLoadingStatusItems().includes('찬양 데이터'),'off-screen praise load leaked into scripture status');
                  state.module='praise';
                  check(currentLoadingStatusItems().includes('찬양 데이터'),'active praise load missing');
                  state.loadingModules.clear();

                  state.auth.session={user:{id:'fixture'}};state.connectionError='';state.search='';state.praiseFilter='all';state.selectedSongId='song-220';
                  state.songs=Array.from({length:250},(_,index)=>({id:`song-${index}`,title:`찬양 ${index}`,versions:[],hymn_no:null}));
                  state.praiseListWindow={key:'',limit:180};
                  renderSongList();
                  check(refs.songList.querySelector('[data-song-id="song-220"]'),'active deep-link song was not included in initial list window');
                  state.selectedSongId='song-10';state.praiseListWindow={key:'',limit:180};
                  renderSongList();
                  check(refs.songList.querySelectorAll('[data-song-id]').length===180,'initial list window is not capped');
                  const more=refs.songList.querySelector('[data-praise-list-more]');check(more,'missing incremental load control');
                  more.click();
                  check(refs.songList.querySelectorAll('[data-song-id]').length===250&&!refs.songList.querySelector('[data-praise-list-more]'),'incremental list did not finish');
                  return {routeOwnership:true,slotOwnership:true,loadingOwnership:true,incrementalList:true};
                }''')
                print("PASS", engine, result)
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
