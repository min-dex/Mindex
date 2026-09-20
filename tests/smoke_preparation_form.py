"""Bulk input form: 양식 button, faint example hints, Tab slots and blank-label apply."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof renderPresenterServiceInputRail === 'function' && typeof fillPresenterPreparationForm === 'function'")
                page.evaluate('''() => {
                  const service={id:'form-fixture',type_id:'fixture'};
                  const make=(label,memo,section)=>normalizeServiceItem({id:label,service_id:service.id,label,raw_title:label,
                    _worshipSectionKey:section,memo:serializeServiceItemMemo(memo)},0);
                  const items=[make('광고',{elementType:'body',inputMode:'text'},'announcements'),
                    make('특송',{elementType:'praise',inputMode:'manual_praise',slides:['x']},'special_song')];
                  state.services=[service]; state.serviceItems={[service.id]:items}; state.selectedServiceId=service.id;
                  servicePrepEditorItems=()=>state.serviceItems[service.id];
                  getServiceItems=()=>state.serviceItems[service.id];
                  window.__toasts=[]; showToast=(text,type)=>window.__toasts.push([type,text]);
                  // Own host on <body> (the app re-renders its sidebars) wired with the app's real delegated handlers.
                  const host=document.createElement('div'); host.id='rail-host';
                  host.style.cssText='position:fixed;top:0;right:0;width:360px;z-index:9999;background:#111';
                  // The box now starts filled with the form; a box the user emptied stays empty and the button restores it.
                  state.presenterPreparationDrafts[service.id]='';
                  host.innerHTML=renderPresenterServiceInputRail(service);
                  document.body.append(host);
                  bindDetailInteractionRoot(host);
                  syncPresenterPreparationGhost(host.querySelector('textarea'));
                }''')
                box = page.locator('#rail-host textarea')
                ghost = page.locator('#rail-host [data-presenter-preparation-ghost]')
                assert box.input_value() == '', 'an emptied box should stay empty'

                page.click('#rail-host [data-presenter-preparation-form]')
                form = box.input_value()
                lines = form.split('\n')
                assert len(lines) >= 2 and all(line.endswith(': ') for line in lines), form
                labels = [line.split(':')[0] for line in lines]
                assert '광고' in labels and '특송' in labels, labels
                caret = page.evaluate("document.querySelector('#rail-host textarea').selectionStart")
                assert caret == len(lines[0]), f'caret after first label, got {caret}'
                assert page.evaluate("document.activeElement === document.querySelector('#rail-host textarea')"), 'focus in box'
                hint = ghost.inner_text()
                assert '다음 주 예배 후 모임이 있습니다' in hint, hint  # example value stays as a faint hint

                # Tab hops to the next empty slot; typing into it hides that line's hint.
                page.keyboard.type('공지 내용')
                page.keyboard.press('Tab')
                caret = page.evaluate("document.querySelector('#rail-host textarea').selectionStart")
                second_end = len(lines[0]) + len('공지 내용') + 1 + len(lines[1])
                assert caret == second_end, f'tab should land after 2nd label, got {caret} want {second_end}'
                page.keyboard.press('Shift+Tab')
                caret = page.evaluate("document.querySelector('#rail-host textarea').selectionStart")
                assert caret == second_end, 'shift+tab has no earlier empty slot, caret must stay'

                # Button does not overwrite typed text.
                page.click('#rail-host [data-presenter-preparation-form]')
                assert '공지 내용' in box.input_value() and box.input_value().count('광고:') == 1, 'form must not overwrite'
                assert any('비어 있을 때만' in text for _, text in page.evaluate('window.__toasts')), 'refusal toast'

                # Apply: filled line lands, blank label is skipped without an error.
                result = page.evaluate('''async () => {
                  const service=state.services[0];
                  servicePrepEditorItems=()=>state.serviceItems[service.id];
                  renderServiceList=()=>{}; renderCurrentServiceModuleDetail=()=>{};
                  refreshPresenterForService=()=>{}; updateSaveState=()=>{};
                  projectWorshipServiceItemsFromTemplate=(_,items)=>items;
                  window.__toasts.length=0;
                  await applyPresenterPreparationInput(service.id, {draft: document.querySelector('#rail-host textarea').value});
                  return window.__toasts;
                }''')
                errors = [text for kind, text in result if kind == 'error']
                infos = ' '.join(text for kind, text in result if kind == 'info')
                assert not errors, errors
                assert '1개 항목을 반영' in infos and '1개 항목은 건너뛰었습니다' in infos, infos

                # Nothing filled: a hint, no error, nothing applied.
                result = page.evaluate('''async () => {
                  window.__toasts.length=0;
                  await applyPresenterPreparationInput('form-fixture', {draft: '광고: \\n특송: '});
                  return window.__toasts;
                }''')
                assert result and result[0][0] == 'info' and '채운 항목이 없습니다' in result[0][1], result
                print(engine, 'PASS form button, hints, tab slots, no-overwrite, blank-label apply', flush=True)
                browser.close()
    finally:
        server.shutdown()


main()
