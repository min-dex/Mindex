"""Detect green bleed beneath an opaque sidebar preview at fractional widths."""
from io import BytesIO
from PIL import Image
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine, dpr in [(e, d) for e in ['chromium', 'webkit'] for d in [1, 1.25, 2]]:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page(viewport={"width": 1100, "height": 700}, device_scale_factor=dpr)
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.route('**/chromakey-ready-loop-fast.mp4*', lambda r: r.abort())
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
                    if green:
                        shot.save('/private/tmp/mindex-preview-edge-failure.png')
                    assert not green, (engine,dpr,width,green[:8])
                print('PASS sidebar edge pixels', engine, 'DPR', dpr, flush=True)
                page.evaluate('''() => {
                  const host=document.getElementById('edge-fixture');
                  host.innerHTML='<div class="svc-presenter-live-preview"><span class="svc-slide-mini-output"><span class="svc-slide-mini-canvas presenter-output-root">'+renderPresenterSlideFrame({type:'ready',elementType:'video',layout:'media',presenterRole:'waiting_loop',videoSrc:'assets/presenter/chromakey-ready-loop-fast.mp4'}, {previewStage:true})+'</span></span></div>';
                  // Model a fractional compositor seam without changing stage dimensions.
                  host.querySelector('.presenter-slide').style.transform='translateX(8px)';
                  applyPresenterPreviewScales(host);
                }''')
                for width in [220, 254.5, 296, 296.75, 360]:
                    page.evaluate('''w => {
                      const host=document.getElementById('edge-fixture');
                      host.style.width=w+'px';applyPresenterPreviewScales(host);
                    }''', width)
                    shot = Image.open(BytesIO(page.locator('#edge-fixture .svc-presenter-live-preview').screenshot())).convert('RGB')
                    green = [(x,y) for x in range(min(3,shot.width)) for y in range(8,shot.height-8)
                             if (lambda c: c[1]>c[0]+20 and c[1]>c[2]+20)(shot.getpixel((x,y)))]
                    assert not green, ('video seam',engine,dpr,width,green[:8])
                colors = page.evaluate('''() => {
                  const canvas=document.querySelector('#edge-fixture .svc-slide-mini-canvas');
                  const thumb=document.createElement('div');thumb.className='svc-slide-thumb-frame';
                  thumb.append(canvas.cloneNode(true));document.body.append(thumb);
                  const standalone=canvas.cloneNode(true);standalone.className='presenter-output-root';
                  document.body.append(standalone);
                  const result={preview:getComputedStyle(canvas).backgroundColor,thumbnail:getComputedStyle(thumb.firstElementChild).backgroundColor,output:getComputedStyle(standalone).backgroundColor,width:canvas.offsetWidth,height:canvas.offsetHeight};
                  standalone.remove();thumb.remove();return result;
                }''')
                assert colors == {'preview':'rgb(0, 0, 0)', 'thumbnail':'rgb(0, 0, 0)', 'output':'rgb(0, 255, 0)', 'width':1920, 'height':1080}, colors
                print('PASS video seam and unchanged output', engine, 'DPR', dpr, flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
