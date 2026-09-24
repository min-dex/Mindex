from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 1000, "height": 800})
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("typeof renderPresenterPreparationFieldRows === 'function'")
            print(page.evaluate(r'''() => {
              const check=(value,message)=>{if(!value)throw Error(message)};
              const service={id:'ghost-fixture',type_id:'sunday-second',date:'2026-09-13'};
              state.services=[service]; state.serviceItems[service.id]=[];
              const examples='찬양1: 꽃들도\n찬양2: 주 품에\n대표기도: 홍길동 집사\n성경봉독: 요한복음 3:16';
              presenterPreparationPlaceholderForService=()=>examples;
              const host=document.createElement('div');
              host.style.cssText='position:fixed;inset:20px auto auto 20px;width:320px;padding:10px;background:var(--panel);z-index:9999';
              host.className='svc-presenter-side-panel';
              host.innerHTML=renderPresenterServiceInputRail(service);
              document.body.append(host); bindDetailInteractionRoot(host);
              const inputs=[...host.querySelectorAll('[data-presenter-preparation-field]')];
              const apply=host.querySelector('[data-presenter-preparation-apply]');
              const top=apply.getBoundingClientRect().top;
              check(!host.querySelector('[data-presenter-preparation-examples]'),'separate examples remain');
              check(inputs.length===4,'missing fixed input fields');
              check(inputs.map(input=>input.dataset.presenterPreparationFieldLabel).join(',')==='찬양1,찬양2,대표기도,성경봉독','field labels');
              check(inputs.every(input=>!input.value&&input.placeholder),'inputs need empty values and examples');
              inputs[0].focus(); inputs[0].value='꽃들도'; inputs[0].dispatchEvent(new Event('input',{bubbles:true}));
              check(document.activeElement===inputs[0]&&state.presenterPreparationDrafts[service.id].includes('찬양1: 꽃들도'),'field draft update');
              inputs[2].value='김철수 집사'; inputs[2].dispatchEvent(new Event('input',{bubbles:true}));
              check(state.presenterPreparationDrafts[service.id].includes('대표기도: 김철수 집사'),'second field draft update');
              check(apply.getBoundingClientRect().top===top,'panel moved while typing');
              inputs[0].value=''; inputs[0].dispatchEvent(new Event('input',{bubbles:true}));
              check(inputs[0].placeholder==='꽃들도','deletion keeps example');
              const target=servicePrepEditorItems(service.id).find(isMainPraiseServiceItem);
              check(target,'missing song fixture');
              const actions=document.createElement('div'); actions.style.cssText='width:500px;margin-top:16px';
              actions.innerHTML=renderPresenterBoardItemActions(service.id,{item:target,index:target._origIndex,service});
              document.body.append(actions);
              const save=actions.querySelector('[data-service-item-commit]');
              const audio=actions.querySelector('.svc-board-subgroup-audio-upload');
              check(save && audio,'missing header controls');
              const a=getComputedStyle(save),b=getComputedStyle(audio);
              check(a.height===b.height && a.fontSize===b.fontSize && a.fontWeight===b.fontWeight,'header button mismatch');
              check(a.padding===b.padding && a.borderRadius===b.borderRadius,'header button spacing mismatch');
              actions.remove();
              return 'PASS fixed label fields, value drafts, stable panel, matching audio/save controls';
            }'''))
            page.screenshot(path='/tmp/mindex-inline-examples.png')
            print(page.evaluate('''() => {
              const host=document.createElement('div'); host.className='svc-presenter-side-panel';
              host.style.cssText='position:fixed;top:20px;right:20px;background:var(--panel);z-index:9999';
              const service=state.services[0];
              host.innerHTML=renderPresenterControlsTop(service,[],false,0);document.body.append(host);refreshIcons(host);
              for(const width of [254,320,390]) {
                host.style.width=width+'px';
                const controls=[...host.querySelector('.svc-presenter-window-controls').children];
                if(controls.length!==3) throw Error('window control count');
                for(const el of controls) {
                  const rect=el.getBoundingClientRect();
                  if(Math.abs(rect.height-34)>1 || el.scrollWidth>el.clientWidth+1) throw Error('window control dimensions '+width+' '+el.outerHTML);
                }
                if(!controls[1].textContent.includes('전체화면')) throw Error('missing fullscreen label');
              }
              return 'PASS 34px monitor/fullscreen/pin row at 254/320/390px';
            }'''))
            page.screenshot(path='/tmp/mindex-panel-controls.png')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
