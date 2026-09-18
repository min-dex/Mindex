from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 900, "height": 700})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterSlideThumb === 'function'")
            result = page.evaluate('''() => {
              document.body.classList.remove('ui-booting');
              document.body.dataset.theme='dark';
              const host = document.createElement('div');
              host.style.cssText='position:fixed;inset:0;background:#171715;padding:24px;overflow:auto;z-index:99999';
              document.body.append(host);
              const slide={id:'fixture',type:'blank',elementId:'citation',sectionKey:'sermon',liveScriptureControl:true};
              const widths=[200,240,320];
              for(const width of widths) {
                const box=document.createElement('div');box.style.cssText=`width:${width}px;margin-bottom:24px`;
                box.innerHTML=renderPresenterSlideThumb(slide,0,-1,'fixture');host.append(box);
                const meta=box.querySelector('.svc-slide-thumb-meta').getBoundingClientRect();
                const thumb=box.querySelector('.svc-slide-thumb').getBoundingClientRect();
                for(const selector of ['.svc-slide-citation-reference-input','.svc-slide-citation-auto-output']) {
                  const rect=box.querySelector(selector).getBoundingClientRect();
                  if(rect.right>box.getBoundingClientRect().right+1 || rect.bottom>thumb.top+1 || rect.bottom>meta.bottom+1) throw Error('overflow '+width+' '+selector);
                }
                if(!box.querySelector('[data-presenter-citation-auto-output]').checked) throw Error('default unchecked');
              }
              presenterCitationAutoOutput=false;
              const rerender=document.createElement('div');rerender.innerHTML=renderPresenterSlideThumb(slide,0,-1,'fixture');
              if(rerender.querySelector('[data-presenter-citation-auto-output]').checked) throw Error('state lost after render');
              return widths;
            }''')
            page.screenshot(path='/tmp/mindex-citation-toggle.png')
            print('PASS citation toggle layout:', result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
