import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    server, url = (None, args.url) if args.url else start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url + '?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("""() => [...document.styleSheets].some((sheet) =>
              sheet.href && sheet.href.includes('styles.presenter-output.css'))""", timeout=10000)
            result = page.evaluate('''() => {
              const cases=[
                ['lyrics','<div class="presenter-slide-text"><span>가사</span></div>','.presenter-slide-text'],
                ['song-title','<div class="presenter-slide-text">제목</div>','.presenter-slide-text'],
                ['scripture','<div class="presenter-slide-text">말씀</div>','.presenter-slide-text'],
                ['title-assignee','<div class="presenter-slide-text">담당</div>','.presenter-slide-text'],
                ['title-content presenter-slide--fullscreen-song-title','<div class="presenter-title-content">제목</div>','.presenter-title-content'],
                ['liturgical-body','<div class="presenter-liturgical-body">본문</div>','.presenter-liturgical-body'],
                ['ready','<div class="presenter-ready-screen"><div class="presenter-ready-screen-copy">대기</div></div>','.presenter-ready-screen-copy'],
                ['waiting','<div class="presenter-waiting-loop"><div class="presenter-waiting-loop-copy">대기</div></div>','.presenter-waiting-loop-copy']
              ];
              const results=[];
              for(const clean of [false,true]) for(const [type,html,selector] of cases) {
                const root=document.createElement('div');
                root.className='presenter-output-root'+(clean?' no-chromakey':'');
                root.style.cssText='position:relative;width:1920px;height:1080px;transform:none;left:0;top:0';
                root.innerHTML='<div class="presenter-slide presenter-slide--'+type+'" data-element-type="praise">'+html+'</div>';
                document.body.append(root);
                const box=root.querySelector(selector), rect=box.getBoundingClientRect(), style=getComputedStyle(box);
                const left=rect.left+parseFloat(style.paddingLeft),right=rect.right-parseFloat(style.paddingRight);
                const stage=root.getBoundingClientRect();
                results.push({clean,type,width:(right-left)/stage.width,left:(left-stage.left)/stage.width});
                root.remove();
              }
              return results;
            }''')
            for r in result:
                if r['type'] == 'liturgical-body':
                    # Liturgical copy is one output role with a shared fixed safe area.
                    expected_inset = 45
                    assert abs(r['width'] - (1 - expected_inset * 2 / 1920)) < 0.001, r
                    assert abs(r['left'] - (expected_inset / 1920)) < 0.001, r
                else:
                    assert abs(r['width'] - (0.85 if r['clean'] else 0.95)) < 0.001, r
                    assert abs(r['left'] - (0.075 if r['clean'] else 0.025)) < 0.001, r
            print('PASS 16 text layouts: standard margins plus fixed liturgical safe areas')
            browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
