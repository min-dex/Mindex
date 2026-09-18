from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page(viewport={'width':1200,'height':800})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof capturePresenterViewportSnapshot === 'function'")
            result = page.evaluate('''async () => {
              const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
              state.module='presenter';state.selectedServiceId='fixture';
              document.body.classList.remove('ui-booting');
              const pane=refs.detailPane;
              pane.style.cssText='position:fixed;inset:0 auto auto 0;width:600px;height:400px;overflow:auto;display:block;overflow-anchor:none';
              pane.innerHTML=`<div id="servicePresenterControls" data-service-id="fixture">
                <div style="height:500px"></div>
                <div class="svc-board-subgroup" data-service-item-index="0" data-service-element-id="citation">
                  <div id="rows" style="height:300px"><div class="svc-slide-thumb-wrap" style="height:100px"><button class="svc-slide-thumb" data-service-id="fixture" data-presenter-index="0">slide</button></div></div>
                  <div class="svc-citation-composer" style="height:80px"><input data-presenter-citation-reference-input data-service-id="fixture" data-presenter-citation-element-id="citation"></div>
                </div><div style="height:500px"></div></div>`;
              const input=pane.querySelector('input');input.value='요 15:9';input.focus({preventScroll:true});pane.scrollTop=650;await frame();
              const before=input.getBoundingClientRect().top;
              const snapshot=capturePresenterViewportSnapshot('fixture');
              pane.querySelector('#rows').style.height='500px';
              restorePresenterViewportSnapshot(snapshot);await frame();
              const after=input.getBoundingClientRect().top;
              if(Math.abs(after-before)>1) throw Error('composer shifted after insertion: '+(after-before));
              const checkbox=document.createElement('input');checkbox.type='checkbox';input.parentElement.append(checkbox);checkbox.focus({preventScroll:true});
              const beforeCheckbox=input.getBoundingClientRect().top;
              const checkboxSnapshot=capturePresenterViewportSnapshot('fixture');
              pane.querySelector('#rows').style.height='700px';restorePresenterViewportSnapshot(checkboxSnapshot);await frame();
              if(Math.abs(input.getBoundingClientRect().top-beforeCheckbox)>1) throw Error('checkbox focus lost scroll anchor');
              const beforeNavigation=pane.scrollTop;
              scrollPresenterBoardToIndex('fixture',0,{force:true});await frame();
              if(pane.scrollTop===beforeNavigation) throw Error('explicit navigation stopped scrolling');
              return {anchor:snapshot.selector,inputShiftAfterInsertion:Math.round(after-before),inputTopAfterForcedJump:Math.round(input.getBoundingClientRect().top),viewportBottom:Math.round(pane.getBoundingClientRect().bottom),draft:input.value,focused:document.activeElement===input};
            }''')
            print(engine, result, flush=True)
            browser.close()
finally:
    server.shutdown()
