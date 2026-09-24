from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page()
                page.route('**/*supabase*/**', lambda route: route.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof setRightSidebarContent === 'function'")
                result = page.evaluate('''async () => {
                  state.module='presenter';
                  const markup=(id,title)=>`<div data-presenter-right-sidebar data-service-id="${id}">
                    <div style="height:600px">${title}</div>
                    <div class="svc-presenter-live-preview" style="width:254px"><span class="svc-slide-mini-output"><span class="svc-slide-mini-canvas presenter-output-root"><span>${title}</span></span></span></div>
                    <details data-presenter-help><summary>도움말</summary>내용</details>
                    <input data-presenter-preparation-field data-service-id="${id}" data-presenter-preparation-field-label="광고" value="초안"></div>`;
                  refs.rightSidebar.style.cssText='display:block;height:300px;overflow:auto';
                  setRightSidebarContent(markup('fixture','첫 화면'));
                  const root=refs.rightSidebar.firstElementChild, canvas=root.querySelector('.svc-slide-mini-canvas');
                  const input=root.querySelector('[data-presenter-preparation-field]'), help=root.querySelector('details');
                  input.value='작성 중';input.focus();input.setSelectionRange(1,2);help.open=true;
                  refs.rightSidebar.scrollTop=200;
                  let removals=0;
                  const observer=new MutationObserver(records=>records.forEach(r=>r.removedNodes.forEach(n=>{if(n===root||n===canvas||n===input)removals++;})));
                  observer.observe(refs.rightSidebar,{subtree:true,childList:true});
                  for(let i=0;i<10;i++)setRightSidebarContent(markup('fixture','화면 '+i));
                  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                  const stable=root.isConnected && canvas.isConnected && input.isConnected && !removals;
                  const editing=document.activeElement===input && input.value==='작성 중' && input.selectionStart===1;
                  const preserved=help.open && refs.rightSidebar.scrollTop===200;
                  const updated=canvas.textContent==='화면 9';
                  observer.disconnect();
                  setRightSidebarContent(markup('other','다른 예배'));
                  const switched=!root.isConnected && refs.rightSidebar.firstElementChild.dataset.serviceId==='other';
                  setRightSidebarContent('');
                  return {stable,editing,preserved,updated,switched,cleared:!refs.rightSidebar.children.length};
                }''')
                assert all(result.values()), result
                print('PASS sidebar reuse', engine, result)
                updates = page.evaluate('''() => {
                  const service={id:'controls-fixture',type_id:'sunday-afternoon'};
                  state.services=[service]; state.presenter.serviceId=service.id;
                  isPresenterOutputWindowOpen=()=>true;
                  const slides=Array.from({length:45},(_,i)=>({id:'slide:'+i,type:'lyrics',elementType:'praise',layout:'center-text',title:'찬양',text:'가사 '+i}));
                  const root=document.createElement('div'); root.className='svc-presenter-side-panel';root.style.width='300px';document.body.append(root);
                  root.innerHTML=renderPresenterControlsTop(service,slides,true,0);
                  refreshIcons(root);applyPresenterPreviewScales(root);fitPresenterPreviewText(root);
                  const selectors=['.svc-presenter-top','.svc-presenter-live-preview','[data-presenter-jump-input]','[data-presenter-action="next"]'];
                  const nodes=selectors.map(s=>root.querySelector(s));nodes[2].focus();
                  for(let i=1;i<=40;i++) {
                    patchPresenterControlsTop(root,service,slides,true,i);
                    if(selectors.some((s,j)=>root.querySelector(s)!==nodes[j]) || document.activeElement!==nodes[2]) throw Error('controller replaced');
                    if(Number(nodes[2].value)!==i+1 || !nodes[1].textContent.includes('가사 '+i)) throw Error('stale slide');
                  }
                  root.remove();return 40;
                }''')
                print('PASS live controller transitions', engine, updates)
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
