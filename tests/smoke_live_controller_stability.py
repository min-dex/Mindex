"""Preserve controller position and discard superseded live scripture requests."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 1200, "height": 800})
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof runLiveScriptureAction === 'function'")
                print(engine, page.evaluate("""async () => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                  const service={id:'stability-fixture',type_id:'fixture'};
                  state.module='presenter';state.selectedServiceId=service.id;state.services=[service];
                  state.presenter.serviceId=service.id;
                  const pane=refs.detailPane;
                  pane.style.cssText='position:fixed;inset:0 auto auto 0;width:600px;height:400px;overflow:auto;display:block';
                  pane.innerHTML=`<div id="servicePresenterControls" data-service-id="${service.id}">
                    <div style="height:300px"></div>
                    <div class="svc-board-subgroup" data-service-element-id="element" data-service-item-index="0">
                    ${Array.from({length:12},(_,i)=>`<div class="svc-slide-thumb-wrap" style="height:100px">
                      <button class="svc-slide-thumb" data-service-id="${service.id}" data-presenter-index="${i}"
                        data-presenter-slide-id="slide-${i}" data-presenter-element-key="element">${i}</button></div>`).join('')}
                    </div><div style="height:500px"></div></div>`;
                  const panel=document.createElement('div');panel.className='svc-presenter-side-panel';
                  panel.style.cssText='position:fixed;left:650px;top:0;width:300px';document.body.append(panel);
                  isPresenterOutputWindowOpen=()=>true;
                  const slides=[{id:'normal',type:'lyrics',text:'가사',title:'찬양',elementType:'praise'}];
                  state.presenter.slides=slides;
                  state.presenter.liveScripture={active:false,draft:'',slide:null};
                  panel.innerHTML=renderPresenterControlsTop(service,slides,true,0);
                  refreshIcons(panel);
                  const help=panel.querySelector('[data-presenter-help]');help.open=true;
                  const field=panel.querySelector('[data-live-scripture-input]');
                  const nextButton=panel.querySelector('[data-presenter-action="next"]');nextButton.focus();
                  pane.scrollTop=720;
                  const snapshot=capturePresenterViewportSnapshot(service.id);
                  const anchor=presenterViewportRestoreTarget(document.getElementById('servicePresenterControls'),snapshot);
                  check(anchor.classList.contains('svc-slide-thumb-wrap'),'slide anchor became element header');
                  restorePresenterViewportSnapshot(snapshot);await frame();
                  check(Math.abs(pane.scrollTop-720)<1,'unchanged board jumped');
                  pane.querySelector('#servicePresenterControls > div').style.height='350px';
                  restorePresenterViewportSnapshot(snapshot);await frame();
                  check(Math.abs(pane.scrollTop-770)<1,'content insertion lost visible slide offset');
                  const editing=pane.querySelector('.svc-slide-thumb');editing.focus({preventScroll:true});
                  const focusedSnapshot=capturePresenterViewportSnapshot(service.id);
                  check(presenterViewportRestoreTarget(document.getElementById('servicePresenterControls'),focusedSnapshot).classList.contains('svc-board-subgroup'),'focused element anchor lost');
                  nextButton.focus();
                  for(let i=0;i<12;i++){
                    state.presenter.liveScripture={active:i%2===0,draft:'요한복음 3:16',slide:{type:'scripture',title:'요한복음 3:16',text:'본문'}};
                    patchPresenterControlsTop(panel,service,slides,true,0);
                    check(panel.querySelector('[data-presenter-help]')===help && help.open,'help replaced/reset');
                    check(panel.querySelector('[data-live-scripture-input]')===field,'scripture field replaced');
                    check(document.activeElement===nextButton,'control focus lost');
                  }
                  state.presenter.liveScripture.active=true;patchPresenterControlsTop(panel,service,slides,true,0);
                  field.focus();field.value='마태복음 5:';field.setSelectionRange(3,3);
                  patchPresenterControlsTop(panel,service,slides,true,0);
                  check(field.value==='마태복음 5:' && field.selectionStart===3,'in-progress scripture overwritten');
                  const pending=[];const published=[];
                  preparePresenterService=id=>{state.presenter.serviceId=id};
                  buildLiveScriptureSlide=query=>new Promise((resolve,reject)=>pending.push({query,resolve,reject}));
                  publishPresenterState=()=>published.push(state.presenter.liveScripture.reference);
                  renderPresenterControlState=()=>{};
                  field.value='요한복음 3:16';const first=runLiveScriptureAction('show',service.id);
                  field.value='마태복음 5:1';const second=runLiveScriptureAction('show',service.id);
                  pending[1].resolve({title:'마태복음 5:1'});await second;
                  pending[0].resolve({title:'요한복음 3:16'});await first;
                  check(published.length===1 && published[0]==='마태복음 5:1','old request replaced latest');
                  const third=runLiveScriptureAction('show',service.id);
                  await runLiveScriptureAction('clear',service.id);
                  pending[2].resolve({title:'늦은 결과'});await third;
                  check(!state.presenter.liveScripture.active,'clear resurrected by pending request');
                  const fourth=runLiveScriptureAction('show',service.id);
                  updateLiveScriptureDraft('입력 중인 다음 주소');
                  pending[3].resolve({title:'마태복음 5:1'});await fourth;
                  check(state.presenter.liveScripture.draft==='입력 중인 다음 주소','async completion overwrote draft');
                  preparePresenterNavigation=()=>{};
                  syncSelectedServiceItemToPresenterSlide=()=>{};
                  syncServiceMusicWithPresenterContext=()=>{};
                  scrollPresenterOutlineToActive=()=>{};
                  const navigating=runLiveScriptureAction('show',service.id);
                  runPresenterAction('next',service.id,{scroll:false});
                  const afterNavigation=published.length;
                  pending[4].resolve({title:'이동 전 조회'});await navigating;
                  check(!state.presenter.liveScripture.active && published.length===afterNavigation,'navigation resurrected live scripture');
                  const count=published.length;
                  const fifth=runLiveScriptureAction('show',service.id);
                  state.presenter.serviceId='other';pending[5].resolve({title:'이전 예배'});await fifth;
                  check(published.length===count,'old service published');
                  state.presenter.serviceId=service.id;
                  const citation={id:'citation',service_id:service.id,label:'인용 구절',memo:''};
                  state.serviceItems[service.id]=[citation];
                  const citationInput=document.createElement('input');
                  citationInput.dataset.serviceId=service.id;citationInput.dataset.presenterCitationElementId=citation.id;
                  citationInput.value='마 5:45';
                  presenterControllerIsLive=()=>true;
                  resolveServiceScriptureBeforeSave=async()=>{};
                  presenterSlidesForService=()=>[{elementId:citation.id,type:'scripture',title:'마태복음 5:45'}];
                  saveServiceItemPatch=async()=>true;
                  const jumps=[],scrolls=[];
                  runPresenterAction=(action,id,options)=>jumps.push({action,id,...options});
                  scrollPresenterBoardToIndex=(...args)=>scrolls.push(args);
                  await appendPresenterCitationReference(citationInput);
                  check(jumps.length===1 && jumps[0].index===0 && jumps[0].scroll===false,'citation duplicate scroll path');
                  check(scrolls.length===1 && citationInput.value==='','citation scroll or input clear');
                  panel.remove();
                  return 'PASS slide/element anchors, live toggles, focus/draft, latest request, clear, service switch';
                }"""), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
