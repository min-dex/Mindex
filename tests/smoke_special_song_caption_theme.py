from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        page.route('**/*supabase*/**', lambda route: route.abort())
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function("typeof presenterSlidesWithSpecialSongTitle === 'function' && typeof renderPresenterSlideFrame === 'function'")
        print(page.evaluate('''() => {
          const check = (v, m) => { if (!v) throw Error(m); };
          const lyric = { id: 'l1', type: 'lyrics', layout: 'lower_bar_text', elementType: 'lyrics', text: '지금은 엘리야 때처럼\\n주 말씀이 선포되고', sectionKey: 'special_song' };
          const section = { sectionKey: 'special_song', sectionLabel: '특송' };
          const build = (assignee) => presenterSlidesWithSpecialSongTitle(
            { id: 'sp', label: '특송', assignee, _worshipSectionKey: 'special_song' }, section, [{ ...lyric }], 0, null);
          const cadaros = build('카다로스 중창단');
          const other = build('시온 찬양대');
          check(cadaros.length >= 2 && cadaros.every((s) => s.captionTheme === 'cadaros'), 'cadaros slides not themed (title, lyrics)');
          check(other.every((s) => !s.captionTheme), 'other special song themed');
          check(build('  카다로스  중창단 ').every((s) => s.captionTheme === 'cadaros'), 'assignee spacing broke theme');

          const mount = (slides, cls) => {
            const root = document.createElement('main');
            root.className = 'presenter-output-root ' + cls;
            root.style.cssText = 'position:static;transform:none;width:640px;height:360px';
            root.innerHTML = renderPresenterSlideFrame(slides[slides.length - 1]);
            document.body.append(root);
            return root;
          };
          const luminance = (rgb) => {
            const m = rgb.match(/[\\d.]+/g).map(Number);
            return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
          };
          const themed = mount(cadaros, '');
          const plain = mount(other, '');
          const full = mount(cadaros, 'no-chromakey');
          const themedSlide = themed.querySelector('.presenter-slide');
          const themedText = themed.querySelector('.presenter-slide-text');
          const barImage = getComputedStyle(themedSlide, '::before').backgroundImage;
          check(/gradient/.test(barImage) && /rgb\\(255, 255, 255\\)/.test(barImage), 'themed bar should be white-based');
          check(luminance(getComputedStyle(themedText).color) < 120, 'themed text should be dark on the white bar');
          check(/Eulyoo1945/.test(getComputedStyle(themedText).fontFamily), 'themed text should use the Eulyoo reading face');
          check(getComputedStyle(themedSlide, '::after').backgroundImage.startsWith('url('), 'ornament missing');
          const plainBar = getComputedStyle(plain.querySelector('.presenter-slide'), '::before').backgroundImage;
          check(/rgb\\(0, 10, 100\\)/.test(plainBar), 'other special songs must keep the navy bar');
          check(luminance(getComputedStyle(plain.querySelector('.presenter-slide-text')).color) > 200, 'other special songs must keep white text');
          check(!/rgb\\(255, 255, 255\\)/.test(getComputedStyle(full.querySelector('.presenter-slide'), '::before').backgroundImage), 'fullscreen output must not get the white bar');
          check(luminance(getComputedStyle(full.querySelector('.presenter-slide-text')).color) > 200, 'fullscreen text must stay light');
          return 'PASS cadaros special-song caption theme (bar, text, font, ornament, scope)';
        }'''), flush=True)
        browser.close()
finally:
    server.shutdown()
