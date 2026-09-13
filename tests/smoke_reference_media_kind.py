from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 1100, "height": 700})
                page.route("**/*supabase*/**", lambda r: r.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof presenterReferenceMediaKindForSource === 'function'")
                print(engine, page.evaluate("""() => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  for(const [source,kind] of [
                    ['https://example.test/photo.JPG?token=x#view','image'],
                    ['assets/clip.MP4?download=1','video'],
                    ['https://example.test/audio%2Emp3','audio'],
                    ['https://example.test/download?filename=clip.mp4',''],
                    ['https://example.test/live',''],
                    ['javascript:clip.mp4',''],['','']
                  ]) check(presenterReferenceMediaKindForSource(source)===kind,source);
                  const service={id:'kind-fixture',type_id:'fixture'};
                  const item=normalizeServiceItem({id:'kind-item',service_id:service.id,label:'참고 화면',
                    _worshipSectionKey:'announcements',
                    memo:serializeServiceItemMemo({elementType:'image',inputMode:'asset',asset:{kind:'image'}})},0);
                  const host=document.createElement('main');document.body.append(host);
                  for(const source of ['', 'https://example.test/clip.MP4', 'https://example.test/live']){
                    const memo=parseServiceItemMemo(item.memo);memo.asset.url=source;
                    host.innerHTML=renderPresenterServiceAssetInput(item,0,memo);
                    const select=host.querySelector('select');
                    check(Boolean(select)===(source.endsWith('/live')),'wrong selector visibility');
                    check(host.querySelector('input[type=file]'),'missing file replacement');
                    if(source.endsWith('.MP4'))check(host.querySelector('.svc-reference-media-kind')?.textContent==='영상','missing detected label');
                  }
                  state.services=[service];state.selectedServiceId=service.id;state.serviceItems={[service.id]:[item]};
                  const context={item,index:0,service};
                  host.className='svc-board-subgroup-controls';host.style.width='600px';
                  host.innerHTML=renderPresenterBoardItemActions(service.id,context)
                    +presenterServiceInputControls(item,0,service,{headerActions:true});
                  const actions=host.querySelector('[data-service-item-actions]');
                  check(actions.lastElementChild.matches('[data-service-item-commit]'),'save not last');
                  check(host.querySelectorAll('input[type=file]').length===1,'duplicate file chooser');
                  check(actions.querySelector('input[type=file]'),'file chooser not in header');
                  for(const node of actions.querySelectorAll('.svc-reference-media-upload,.svc-board-subgroup-commit'))
                    check(node.getBoundingClientRect().height===30,'action height inconsistent');
                  check(host.querySelector('.svc-reference-media-title').getBoundingClientRect().width<=360.5,'title stretched');
                  refreshPresenterForService=()=>{};updateSaveState=()=>{};markServiceElementDirty=()=>{};
                  const field=document.createElement('input');
                  field.dataset.serviceId=service.id;field.dataset.serviceItemIndex='0';
                  field.dataset.serviceItemField='asset_url';field.value='https://example.test/clip.mp4?token=x';
                  updateServiceItemField(field);
                  let memo=parseServiceItemMemo(getServiceItems(service.id)[0].memo);
                  check(memo.elementType==='video' && memo.asset.kind==='video','URL kind not persisted');
                  field.value='https://example.test/live';updateServiceItemField(field);
                  field.dataset.serviceItemField='element_type';field.value='audio';updateServiceItemField(field);
                  memo=parseServiceItemMemo(getServiceItems(service.id)[0].memo);
                  check(memo.elementType==='audio' && memo.asset.kind==='audio','manual fallback not persisted');
                  return 'PASS inference, selector visibility, URL persistence, manual fallback';
                }"""), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
