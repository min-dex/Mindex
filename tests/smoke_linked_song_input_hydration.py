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
                    () => {
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
                      const model = serviceItemEditorModel(item, { service });
                      const html = renderServiceSongPicker(item, 0, model);
                      return {
                        linked: Boolean(item.song_id),
                        version: item.song_version_id,
                        rawTitle: item.raw_title,
                        loading: html.includes('연결된 찬양 불러오는 중'),
                        falseSearchFailure: html.includes('검색 결과 없음'),
                        clearControl: html.includes('data-service-song-clear'),
                      };
                    }
                    """
                )
                assert result == {
                    "linked": True,
                    "version": "22222222-2222-4222-8222-222222222222",
                    "rawTitle": "359 천성을 향해 가는 성도들아",
                    "loading": True,
                    "falseSearchFailure": False,
                    "clearControl": False,
                }, (engine, result)
                print("PASS", engine, "linked song input waits for hydration without clearing IDs or showing false search failure")
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
