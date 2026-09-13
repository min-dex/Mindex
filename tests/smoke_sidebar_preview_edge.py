"""Detect green bleed beneath an opaque sidebar preview at fractional widths."""
from io import BytesIO
from PIL import Image
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for dpr in [1, 1.25, 2]:
                browser = launch_chromium(p)
                page = browser.new_page(viewport={"width": 1100, "height": 700}, device_scale_factor=dpr)
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof applyPresenterPreviewScales === 'function'")
                page.evaluate('''() => {
                  const host=document.createElement('div');
                  host.className='svc-presenter-side-panel';host.id='edge-fixture';
                  host.style.cssText='position:fixed;left:10.25px;top:10px;width:296px;z-index:99999';
                  host.innerHTML='<div class="svc-presenter-live-preview"><span class="svc-slide-mini-output"><span class="svc-slide-mini-canvas presenter-output-root">'+renderPresenterSlideFrame({type:'lyrics',elementType:'lyrics',layout:'lower_bar_text',text:'가장자리 확인',title:'찬양'}, {previewStage:true})+'</span></span></div>';
                  document.body.append(host);
                }''')
                for width in [220, 254.5, 296, 296.75, 360]:
                    page.evaluate('''w => {
                      document.getElementById('edge-fixture').style.width=w+'px';
                      applyPresenterPreviewScales(document.getElementById('edge-fixture'));
                    }''', width)
                    shot = Image.open(BytesIO(page.locator('#edge-fixture .svc-presenter-live-preview').screenshot())).convert('RGB')
                    green = [(x,y) for x in range(shot.width) for y in range(int(shot.height*.87),shot.height-8)
                             if (lambda c: c[1]>c[0]+20 and c[1]>c[2]+20)(shot.getpixel((x,y)))]
                    assert not green, (dpr,width,green[:8])
                print('PASS sidebar edge pixels DPR', dpr, flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
