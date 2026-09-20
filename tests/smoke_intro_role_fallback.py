"""A 준비 element with the intro role plays the video, and falls back to the waiting screen without one."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof presenterPreparationSlide === 'function'")
            result = page.evaluate("""() => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const item = (role, assetUrl) => normalizeServiceItem({ id: 'prep', service_id: 's', label: '대기 영상', raw_title: '', _worshipSectionKey: 'ready', _worshipSectionTitle: '준비',
                memo: serializeServiceItemMemo({ elementType: 'video', presenterRole: role, asset: assetUrl ? { kind: 'video', name: '인트로', url: assetUrl } : { kind: '', name: '', url: '' } }) }, 0);
              const chromakey = { id: 's', type_id: 'sunday-main', date: '2026-09-20', alias: '온세대 찬양예배', title: '온세대 찬양예배' };
              check(presenterServiceUsesChromakey(chromakey), 'fixture should use chromakey output');

              const withFile = presenterPreparationSlide(chromakey, item('intro', 'https://example.com/intro.mp4'), 0);
              check(withFile.type === 'video' && withFile.videoSrc === 'https://example.com/intro.mp4', 'intro with a file plays the video');
              check(withFile.playback.autoplay === true && withFile.playback.muted === false && withFile.playback.loop === false && withFile.playback.autoAdvanceOnEnd === true,
                'intro plays once with sound and advances on end');

              // Without a file the intro is the ordinary waiting screen: the looping default video that
              // never advances by itself (it used to become a blank ready screen).
              const noFile = presenterPreparationSlide(chromakey, item('intro', ''), 0);
              check(noFile.type === 'ready', 'intro without a file is a ready slide, got ' + noFile.type);
              check(/chromakey-ready-loop/.test(String(noFile.videoSrc || '')), 'the default waiting loop is kept, got "' + noFile.videoSrc + '"');
              check(noFile.playback && noFile.playback.loop === true && noFile.playback.muted === true && noFile.playback.autoAdvanceOnEnd !== true,
                'the fallback loops silently and must not auto-advance: ' + JSON.stringify(noFile.playback));

              // Fullscreen output has no waiting loop: the ordinary ready screen, never a video.
              const fullscreen = { id: 's2', type_id: 'youth', date: '2026-09-20', title: '청소년부 예배' };
              const fsIntro = presenterPreparationSlide(fullscreen, item('intro', 'https://example.com/intro.mp4'), 0);
              check(fsIntro.videoSrc === 'https://example.com/intro.mp4', 'intro with a file also plays on fullscreen services');
              return 'ok';
            }""")
            assert result == 'ok', result
            print('PASS intro role: video with a file, waiting loop without one', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
