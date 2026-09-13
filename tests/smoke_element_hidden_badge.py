"""Hidden status belongs to the element header, not every thumbnail."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page()
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof renderPresenterBoardSubgroup === 'function'")
                print(engine, page.evaluate("""() => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const service={id:'hidden-fixture',type_id:'fixture'};
                  state.services=[service];
                  let context=null;
                  presenterBoardSubgroupItemContext=()=>context;
                  presenterBoardSubgroupInputContexts=()=>[];
                  presenterBoardSubgroupDisplay=()=>({label:'특송',title:'찬양 제목'});
                  const host=document.createElement('div');
                  host.style.width='300px';document.body.append(host);
                  const make=(hidden,index)=>({slideIndex:index,slide:{id:'s'+index,
                    type:'text',text:'가사',hiddenInPresentation:hidden}});
                  for(const showHead of [true,false]){
                    const entries=[make(true,0),make(true,1),make(true,2)];
                    const before=JSON.stringify(entries);
                    host.innerHTML=renderPresenterBoardSubgroup({label:'특송',slides:entries},-1,service.id,{showHead});
                    check(host.querySelectorAll('.svc-element-hidden-badge').length===1,'one badge per element');
                    check(host.querySelector('.svc-board-subgroup-head .svc-element-hidden-badge'),'badge outside header');
                    check(!host.querySelector('.svc-slide-thumb-meta .svc-element-hidden-badge, .svc-slide-hidden-badge'),'thumbnail badge');
                    check(host.querySelectorAll('.svc-slide-thumb-wrap.hidden').length===3,'hidden styling lost');
                    check(JSON.stringify(entries)===before,'slide data changed');
                    const rect=host.querySelector('.svc-element-hidden-badge').getBoundingClientRect();
                    check(rect.right<=host.getBoundingClientRect().right+1,'badge overflow');
                  }
                  host.innerHTML=renderPresenterBoardSubgroup({slides:[make(false,0),make(true,1)]},-1,service.id,{showHead:true});
                  check(!host.querySelector('.svc-element-hidden-badge'),'partial slide hiding mislabeled as element');
                  context={index:0,item:{id:'hidden-item',memo:serializeServiceItemMemo({hiddenInPresentation:true})}};
                  host.innerHTML=renderPresenterBoardSubgroup({slides:[]},-1,service.id,{showHead:false});
                  check(host.querySelector('.svc-element-hidden-badge'),'empty hidden element missing status');
                  check(firstPresenterNavigableIndex([make(true,0).slide,make(false,1).slide])===1,'navigation changed');
                  host.remove();
                  return 'PASS header-only status, collapsed header, empty element, no slide mutation, navigation';
                }"""), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
