"""Progressive disclosure without altering input or live output behavior."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url, engine):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.route("**/*supabase*/**", lambda route: route.abort())
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function("typeof renderPresenterServiceInputRail === 'function'")
        page.evaluate("""() => {
          state.module='presenter';
          state.services=[{id:'disclosure-fixture',type_id:'fixture'}];
          state.selectedServiceId='disclosure-fixture';
          state.presenter.serviceId='disclosure-fixture';
          state.presenter.index=0;
          state.presenter.slides=[{id:'fixture-slide',type:'lyrics',layout:'center-text',title:'찬양',text:'첫째 줄\\n둘째 줄'}];
          presenterPreparationPlaceholderForService=()=> '찬양1: 곡명\\n대표기도: 이름';
          state.presenterPreparationDrafts={};
          refs.rightSidebar=document.createElement('aside');
          refs.rightSidebar.style.cssText='display:block;width:320px;background:var(--panel);color:var(--ink)';
          document.body.append(refs.rightSidebar);
          window.mountFixture=()=>setRightSidebarContent(renderPresenterRightSidebar(state.services[0],state.presenter.slides,true,0));
          mountFixture();
        }""")
        summary = page.locator('[data-presenter-preparation-disclosure] > summary')
        field = page.locator('[data-presenter-preparation-input]')
        assert not field.is_visible(), "empty bulk form dominates controller"
        summary.focus()
        summary.press('Enter')
        assert field.is_visible(), "keyboard cannot open bulk input"
        assert page.evaluate('state.presenter.index === 0'), 'disclosure advanced output'
        page.evaluate("""() => {
          const field=document.querySelector('[data-presenter-preparation-input]');
          window.originalField=field;
          field.value='찬양1: 작성 중';
          state.presenterPreparationDrafts['disclosure-fixture']=field.value;
          field.focus();field.setSelectionRange(2,5);
          mountFixture();
          if(field!==document.querySelector('[data-presenter-preparation-input]')
            || document.activeElement!==field || field.selectionStart!==2 || field.selectionEnd!==5
            || field.value!=='찬양1: 작성 중') throw Error('rerender lost draft/focus/selection');
        }""")
        summary.focus()
        summary.press('Space')
        assert not field.is_visible(), "keyboard cannot close bulk input"
        page.evaluate('mountFixture()')
        assert not field.is_visible(), "controller update reopened manually closed draft"
        assert field.input_value() == '찬양1: 작성 중'
        summary.press('Enter')
        assert field.is_visible()
        assert page.evaluate("originalField === document.querySelector('[data-presenter-preparation-input]')")
        for width in (254, 320, 390):
            page.evaluate('(w)=>refs.rightSidebar.style.width=w+"px"', width)
            assert page.evaluate("""() => {
              const root=refs.rightSidebar, r=root.getBoundingClientRect();
              return [...root.querySelectorAll('summary,input,textarea,button')]
                .filter(e=>e.getClientRects().length).every(e=>{
                  const b=e.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1;
                });
            }"""), f'overflow at {width}'
        summary.click()
        page.evaluate('refs.rightSidebar.style.width="320px"')
        page.locator('[data-presenter-right-sidebar]').screenshot(path=f'/tmp/mindex-disclosure-{engine}.png')
        page.evaluate("""() => {
          refs.rightSidebar.replaceChildren();
          mountFixture();
          if(!document.querySelector('[data-presenter-preparation-disclosure]').open)
            throw Error('first mount hides existing draft');
          refs.rightSidebar.replaceChildren();
          state.presenterPreparationDrafts={};
          state.presenterPreparationApplyingServiceIds.add('disclosure-fixture');
          mountFixture();
          if(!document.querySelector('[data-presenter-preparation-disclosure]').open
            || !document.querySelector('[data-presenter-preparation-apply]').disabled)
            throw Error('pending apply hidden or enabled');
        }""")
        print('PASS', engine, 'keyboard, draft, selection, remount, applying, 254/320/390 widths', flush=True)
    finally:
        context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    run(browser, url, engine)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
