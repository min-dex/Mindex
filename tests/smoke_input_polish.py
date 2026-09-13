"""Keep empty attachment tools and connected audio from disturbing editor layout."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chrome', 'webkit'):
                browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
                page = browser.new_page(viewport={'width': 1100, 'height': 800})
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.route('https://example.test/**', lambda r: r.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof renderPresenterBoardItemActions === 'function'")
                result = page.evaluate('''() => {
                  const errors=[];
                  const service={id:'polish-fixture',type_id:'fixture'};
                  state.services=[service];state.selectedServiceId=service.id;
                  const host=document.createElement('main');
                  host.style.cssText='position:fixed;left:8px;top:8px;width:280px;background:var(--panel);z-index:99999;padding:0';
                  document.body.append(host);
                  const item=normalizeServiceItem({id:'media',service_id:service.id,label:'참고 화면',
                    _worshipSectionKey:'announcements',memo:serializeServiceItemMemo({elementType:'image',inputMode:'asset',asset:{kind:'image'}})},0);
                  host.innerHTML='<div class="svc-board-subgroup-controls">'+renderPresenterServiceAssetInput(item,0,parseServiceItemMemo(item.memo),{headerActions:true})+'</div>';
                  const toolbar=host.querySelector('.svc-reference-media-toolbar');
                  if(toolbar.getBoundingClientRect().width || toolbar.getBoundingClientRect().height)errors.push('empty toolbar still occupies space');
                  const title=host.querySelector('.svc-reference-media-title').getBoundingClientRect();
                  if(title.left>host.querySelector('.svc-reference-media-input').getBoundingClientRect().left+1)errors.push('empty toolbar leaves gap');
                  host.innerHTML=renderPresenterBoardItemActions(service.id,{item,service,index:0});
                  refreshIcons(host);
                  if(host.scrollWidth>host.clientWidth+1)errors.push('attachment file input overflow');
                  serviceItemSupportsHeaderAudio=()=>true;
                  const song=normalizeServiceItem({id:'song',service_id:service.id,label:'찬양1',raw_title:'긴 제목',
                    memo:serializeServiceItemMemo({audioAsset:{url:'https://example.test/song.mp3',name:'아주 긴 찬양 음원 파일 이름.mp3'}})},0);
                  state.serviceItems[service.id]=[song];
                  for(const width of [240,280,320,600]){
                    host.style.width=width+'px';
                    host.innerHTML=renderPresenterBoardItemActions(service.id,{item:song,service,index:0});
                    refreshIcons(host);
                    const audio=host.querySelector('.svc-board-subgroup-audio');
                    if(!audio?.querySelector('audio'))throw Error('missing connected audio fixture');
                    const boundary=host.getBoundingClientRect();
                    for(const node of audio.querySelectorAll('audio,strong,button,label')){
                      const rect=node.getBoundingClientRect();
                      if(rect.right>boundary.right+1 || rect.left<boundary.left-1)errors.push('audio overflow at '+width);
                    }
                    if(host.scrollWidth>host.clientWidth+1)errors.push('horizontal overflow at '+width+': '+host.scrollWidth+' '+[...host.querySelectorAll('*')].filter(n=>n.getBoundingClientRect().right>boundary.right+1).map(n=>n.tagName+'.'+n.className));
                    if(!host.querySelector('[data-service-item-actions]').lastElementChild.matches('[data-service-item-commit]'))errors.push('save order');
                  }
                  return errors;
                }''')
                page.screenshot(path=f'/tmp/mindex-input-polish-{engine}.png')
                assert not result, result
                print('PASS', engine, 'empty tools, connected audio, save order at 240/280/320/600px', flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
