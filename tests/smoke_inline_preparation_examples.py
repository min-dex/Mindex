from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 1000, "height": 800})
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("typeof renderPresenterPreparationGhost === 'function'")
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
              const input=host.querySelector('textarea');
              const ghost=host.querySelector('[data-presenter-preparation-ghost]');
              const apply=host.querySelector('[data-presenter-preparation-apply]');
              const top=apply.getBoundingClientRect().top;
              check(!host.querySelector('[data-presenter-preparation-examples]'),'separate examples remain');
              check(ghost.children.length===4,'missing initial examples');
              const set=value=>{input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));};
              input.focus(); set('찬양1: ㄱ'); input.setSelectionRange(5,5);
              check(ghost.children[0].classList.contains('is-occupied'),'active line not hidden');
              check(!ghost.children[1].classList.contains('is-occupied'),'next line hidden');
              check(input.selectionStart===5 && document.activeElement===input,'caret changed');
              set('찬양1: 꽃들도\n\n대표기도: 김철수 집사');
              check(ghost.children[1].textContent==='찬양2: 주 품에','blank line lost hint');
              check(ghost.children[2].classList.contains('is-occupied'),'third line visible');
              check(apply.getBoundingClientRect().top===top,'panel moved while typing');
              set(''); check(!ghost.querySelector('.is-occupied'),'deletion did not restore hints');
              set('<script>alert(1)</script>'); check(!ghost.querySelector('script'),'unsafe interpolation');
              set(Array(12).fill('긴 입력입니다 '.repeat(12)).join('\n'));
              input.scrollTop=80; input.dispatchEvent(new Event('scroll'));
              check(ghost.style.transform===`translateY(${-input.scrollTop}px)`,'scroll mismatch');
              set('찬양1: 꽃들도\n'); input.scrollTop=0; syncPresenterPreparationGhost(input);
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
              return 'PASS inline examples, blank lines, deletion, caret, scroll, stable height, matching audio/save controls';
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
