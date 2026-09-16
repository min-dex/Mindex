from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterControlsTop === 'function'")
            for theme in ['light', 'dark']:
                for width in [1440, 390]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    result = page.evaluate("""({theme,width}) => {
                      document.body.dataset.theme=theme;
                      document.body.dataset.module='presenter';
                      document.head.insertAdjacentHTML('beforeend','<style>#test * {transition:none!important}</style>');
                      const service={id:'hierarchy-fixture',type_id:'sunday-second',date:'2026-09-13'};
                      state.services=[service];state.serviceItems[service.id]=[];
                      isPresenterOutputWindowOpen=()=>false;
                      document.body.innerHTML='<main id="test"></main>';
                      const host=document.querySelector('#test');
                      host.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;padding:20px';
                      host.innerHTML='<div id="left">'+renderPresenterSidebarServiceSummary(service)+'</div><div class="svc-presenter-side-panel" id="right">'+renderPresenterControlsTop(service,[],false,0)+renderPresenterServiceInputRail(service)+'</div>';
                      bindDetailInteractionRoot(host);refreshIcons(host);
                      const left=host.querySelector('#left [data-presenter-action="open"]');
                      const right=host.querySelector('#right [data-presenter-action="open"]');
                      const input=host.querySelector('textarea');
                      const bg=el=>getComputedStyle(el).backgroundColor;
                      const height=el=>el.getBoundingClientRect().height;
                      document.body.classList.remove('right-sidebar-open');
                      const primary=bg(left), leftHeight=height(left), rightHeight=height(right);
                      if(bg(right)!==primary) throw Error('Right start is not primary');
                      input.value='찬양1: 입력 초안';input.dispatchEvent(new Event('input',{bubbles:true}));
                      input.focus();input.setSelectionRange(3,3);
                      document.body.classList.add('right-sidebar-open');
                      if(bg(left)===primary || bg(right)!==primary) throw Error('Duplicated emphasis');
                      if(height(left)!==leftHeight || height(right)!==rightHeight) throw Error('Button resized');
                      if(document.activeElement!==input || input.selectionStart!==3 || input.value!=='찬양1: 입력 초안') throw Error('Draft/focus changed');
                      document.body.classList.remove('right-sidebar-open');
                      if(bg(left)!==primary) throw Error('Closed-panel fallback lost');
                      left.focus();
                      if(document.activeElement!==left || left.disabled) throw Error('Left command inaccessible');
                      if(host.scrollWidth>host.clientWidth+1) throw Error('Horizontal overflow');
                      document.body.classList.add('right-sidebar-open');
                      left.classList.add('svc-presenter-launch--stop');
                      right.classList.add('svc-presenter-launch--stop');
                      const stopColors=[bg(left),bg(right)];
                      document.body.classList.remove('right-sidebar-open');
                      if(bg(left)!==stopColors[0] || bg(right)!==stopColors[1]) throw Error('Stop styling changed');
                      left.classList.remove('svc-presenter-launch--stop');
                      right.classList.remove('svc-presenter-launch--stop');
                      document.body.classList.add('right-sidebar-open');
                      return {theme,width,leftHeight,rightHeight,draft:state.presenterPreparationDrafts[service.id]};
                    }""", {'theme': theme, 'width': width})
                    assert result['draft'] == '찬양1: 입력 초안', result
                    page.screenshot(path=f'/tmp/mindex-output-hierarchy-{theme}-{width}.png')
            browser.close()
            print('PASS light/dark desktop/narrow primary action, fallback, stable sizes, draft/focus')
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
