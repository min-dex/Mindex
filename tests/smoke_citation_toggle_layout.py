import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--webkit', action='store_true')
    args = parser.parse_args()
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = p.webkit.launch() if args.webkit else launch_chromium(p)
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
              const subgroup={slides:[{slide,slideIndex:0},{slide:{...slide,id:'second'},slideIndex:1}]};
              const trailingBlank={id:'normal-trailing-blank',type:'blank',elementId:'normal',autoTrailingBlank:true,citationQuickInsert:true};
              if(renderPresenterCitationComposer({slides:[{slide:trailingBlank,slideIndex:0}]},'fixture')) throw Error('composer attached to normal trailing blank');
              const section=document.createElement('div');
              section.innerHTML=renderPresenterBoardSubgroup(subgroup,-1,'fixture');
              if(!section.querySelector('.svc-board-grid + .svc-citation-composer')) throw Error('composer not below element slides');
              if(section.querySelector('.svc-slide-thumb')) throw Error('internal citation placeholder was visible');
              if(section.querySelector('.svc-element-hidden-badge')) throw Error('citation control hid the element');
              if(renderPresenterSlideThumb(slide,0,-1,'fixture').includes('data-presenter-citation-reference-input')) throw Error('input still on thumbnail');
              const widths=[280,480,800];
              for(const width of widths) {
                const box=document.createElement('div');box.style.cssText=`width:${width}px;margin-bottom:24px`;
                box.innerHTML=renderPresenterCitationComposer(subgroup,'fixture');host.append(box);
                if(box.querySelectorAll('[data-presenter-citation-reference-input]').length!==1) throw Error('duplicate composer');
                const boundary=box.querySelector('.svc-citation-composer').getBoundingClientRect();
                for(const selector of ['.svc-slide-citation-reference-input','.svc-slide-citation-auto-output']) {
                  const rect=box.querySelector(selector).getBoundingClientRect();
                  if(rect.right>boundary.right+1 || rect.bottom>boundary.bottom+1) throw Error('overflow '+width+' '+selector);
                }
                if(!box.querySelector('[data-presenter-citation-auto-output]').checked) throw Error('default unchecked');
              }
              presenterCitationAutoOutput=false;
              const rerender=document.createElement('div');rerender.innerHTML=renderPresenterCitationComposer(subgroup,'fixture');
              if(rerender.querySelector('[data-presenter-citation-auto-output]').checked) throw Error('state lost after render');
              const field=host.querySelector('[data-presenter-citation-reference-input]');field.value='요 15:9';field.focus();field.setSelectionRange(2,4);
              const snapshot=capturePresenterFocusedInput(host);
              field.parentElement.innerHTML=field.parentElement.innerHTML;
              restorePresenterFocusedInput(host,snapshot);
              if(document.activeElement.value!=='요 15:9' || document.activeElement.selectionStart!==2 || document.activeElement.selectionEnd!==4) throw Error('draft/caret lost');
              const retained=host.querySelector('[data-presenter-citation-reference-input]');
              host.querySelector('[data-presenter-citation-auto-output]').focus();
              const fresh=retained.cloneNode();fresh.value='';fresh.placeholder='updated';
              patchPresenterControlTree(retained,fresh);
              if(retained.value!=='요 15:9') throw Error('unfocused draft lost');
              let submissions=0;appendPresenterCitationReference=async()=>{submissions++};
              host.addEventListener('click',handleDetailClick);
              host.querySelector('[data-presenter-citation-add]').click();
              if(submissions!==1) throw Error('submit button');
              refreshIcons(host);
              return widths;
            }''')
            page.screenshot(path='/tmp/mindex-citation-toggle.png')
            print('PASS citation toggle layout:', result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
