from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ["chromium", "webkit"]:
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                page = browser.new_page()
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof renderServiceSongPicker === 'function'")
                result = page.evaluate(
                    """
                    async () => {
                      const check = (value, message) => { if (!value) throw Error(message); };
                      const songId = '11111111-1111-4111-8111-111111111111';
                      const service = { id: 'linked-song-input-fixture', type_id: 'sunday-first' };
                      const item = {
                        id: 'linked-song-item', service_id: service.id, label: '파송찬송',
                        raw_title: '359 천성을 향해 가는 성도들아', song_id: songId,
                        version_id: '22222222-2222-4222-8222-222222222222',
                        song_version_id: '22222222-2222-4222-8222-222222222222',
                        memo: JSON.stringify({ elementType: 'praise', inputMode: 'lyrics_db', formHint: 'V1-V2-C' }),
                      };
                      state.songs = [];
                      state.songById = new Map();
                      state.songLookupSource = state.songs;
                      state.client = { from: () => ({}) };
                      state.selectedServiceId = service.id;
                      let requests = 0;
                      let release;
                      let response = [];
                      let fail = false;
                      fetchSupabaseBatches = async () => {
                        requests++;
                        await new Promise(resolve => { release = resolve; });
                        if (fail) throw Error('simulated outage');
                        return response;
                      };
                      attachRelationalSongVersionsForSongs = async () => {};
                      const model = serviceItemEditorModel(item, { service });
                      const before = JSON.stringify(item);
                      const renderPicker = () => renderServiceSongPicker(item, 0, serviceItemEditorModel(item, { service }));
                      for (let i = 0; i < 20; i++) renderPicker();
                      check(requests === 0, 'rendering must not start network requests');
                      check(renderPicker().includes('data-service-song-retry'), 'unavailable link needs retry');
                      const first = loadSongsForIds([songId]);
                      const duplicate = loadSongsForIds([songId]);
                      const html = renderServiceSongPicker(item, 0, model);
                      check(html.includes('연결된 찬양 불러오는 중'), 'pending state');
                      check(!html.includes('data-service-song-retry'), 'no concurrent retry');
                      check(requests === 1, 'duplicate loads must share one request');
                      fail = true;
                      release();
                      await Promise.all([first, duplicate]);
                      for (let i = 0; i < 20; i++) renderPicker();
                      check(requests === 1, 'failed request must not create render loop');
                      check(renderPicker().includes('data-service-song-retry'), 'failure retry');
                      check(!renderPicker().includes('검색 결과 없음'), 'not a title search failure');
                      check(serviceItemSongSelectionInvalid({...item, raw_title: ''}, service), 'missing linked row must block empty-title save');
                      check(!serviceItemSongSelectionInvalid({...item, song_id: null, version_id: null, song_version_id: null, raw_title: ''}, service), 'genuinely empty slot stays valid');
                      fail = false;
                      const empty = loadSongsForIds([songId]);
                      release();
                      await empty;
                      for (let i = 0; i < 20; i++) renderPicker();
                      check(requests === 2, 'empty response must not create render loop');
                      check(JSON.stringify(item) === before, 'failed/empty loads changed saved input');
                      let saveBlocked = false;
                      try { serviceItemSongVersionIdForSave(item, service); }
                      catch (error) { saveBlocked = error.message.includes('불러온 뒤'); }
                      check(saveBlocked, 'row serialization must not silently clear an unresolved version');
                      const resolveByTitle = resolvePresenterPreparationSong;
                      const findByTitle = findServicePraiseSong;
                      resolvePresenterPreparationSong = () => ({id: 'other-song', title: item.raw_title});
                      findServicePraiseSong = resolvePresenterPreparationSong;
                      applyServiceSongSelectionWithService(item, service);
                      check(JSON.stringify(item) === before, 'title fallback replaced the saved song ID');
                      const getItems = getServiceItems;
                      const asyncResolve = resolveExistingPraiseSongForServiceInputAfterCatalogLoad;
                      state.services = [service];
                      state.serviceItems[service.id] = [item];
                      getServiceItems = () => [item];
                      resolveExistingPraiseSongForServiceInputAfterCatalogLoad = async () => { throw Error('saved link must not be resolved by title'); };
                      await resolveServiceSongSelectionBeforeSave(service.id, 0);
                      check(JSON.stringify(item) === before, 'pre-save resolver replaced the saved song ID');
                      getServiceItems = getItems;
                      resolveExistingPraiseSongForServiceInputAfterCatalogLoad = asyncResolve;
                      resolvePresenterPreparationSong = resolveByTitle;
                      findServicePraiseSong = findByTitle;
                      let renders = 0;
                      renderCurrentServiceModuleDetail = () => { renders++; renderPicker(); };
                      refreshPresenterForService = () => {};
                      response = [{id: songId, title: '천성을 향해 가는 성도들아', hymn_no: '359'}];
                      canUseClientData = () => true;
                      const host = document.createElement('div');
                      host.innerHTML = renderPicker();
                      const retry = host.querySelector('[data-service-song-retry]');
                      handleDetailClick({target: retry});
                      handleDetailClick({target: retry});
                      check(retry.disabled && requests === 3, 'retry click must deduplicate and disable');
                      state.selectedServiceId = 'another-service';
                      item.raw_title = '사용자 편집 중';
                      release();
                      await new Promise(resolve => setTimeout(resolve, 30));
                      check(renders === 0, 'late response must not redraw another service');
                      check(item.raw_title === '사용자 편집 중', 'late response overwrote draft');
                      check(item.song_version_id === '22222222-2222-4222-8222-222222222222', 'late response cleared version');
                      check(renderPicker().includes('data-service-song-clear'), 'success restores linked picker');
                      check(requests === 3, 'unexpected extra requests');
                      return 'PASS bounded loading, retry, save guard and late response';
                    }
                    """
                )
                print(engine, result, flush=True)
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
