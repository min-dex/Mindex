"""Header save lifecycle with a deferred persistence double, never a live DB."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url):
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    context.route("**/*supabase*/**", lambda route: route.abort())
    page = context.new_page()
    try:
        page.goto(url + "?output=presenter", wait_until="domcontentloaded")
        page.wait_for_function("typeof commitServiceItemInputs === 'function'")
        print(page.evaluate("""async () => {
          const check = (ok, message) => { if (!ok) throw Error(message); };
          const service = {id:'draft-retention-fixture', type_id:'fixture'};
          const item = normalizeServiceItem({id:'draft-item', service_id:service.id,
            label:'설교 제목', raw_title:'Original',
            memo:serializeServiceItemMemo({elementType:'text'})}, 0);
          state.services = [service];
          state.serviceItems = {[service.id]:[item]};
          state.selectedServiceId = service.id;
          const ctx = {service,item,index:0};
          presenterBoardSubgroupInputContexts = () => [ctx];
          presenterBoardSubgroupItemContext = () => ctx;
          presenterBoardSubgroupDisplay = () => ({label:item.label,title:item.raw_title});
          renderPresenterSlideThumb = () => '';
          const host = document.createElement('main');
          host.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--bg)';
          document.body.append(host);
          host.innerHTML = renderPresenterBoardSubgroup({
            slides:[{slide:{sectionLabel:item.label},slideIndex:0}],name:item.label
          }, 0, service.id, {showHead:true});
          refs.detailPane = host;
          const editor = host.querySelector('.svc-board-subgroup-control-item');
          const field = editor.querySelector('input[data-service-item-field="raw_title"]');
          const header = host.querySelector('.svc-board-subgroup-head-row');
          const button = header.querySelector('[data-service-item-commit]');
          const status = header.querySelector('[data-service-input-status]');
          check(field && button && status, 'real header editor missing');
          check(!editor.contains(button), 'save command must be outside input editor');

          // Keep the real commit/feedback lifecycle; isolate data resolution and writes.
          updateServiceItemField = input => { if (input === field) item.raw_title = input.value; };
          resolveServiceSongSelectionBeforeSave = async () => {};
          serviceItemSongSelectionInvalid = () => false;
          serviceItemScriptureInputInvalid = () => false;
          let release, entered, captured;
          const armSave = () => {
            const started = new Promise(resolve => { entered = resolve; });
            saveServiceItemPatch = () => {
              captured = item.raw_title;
              entered();
              return new Promise(resolve => { release = resolve; });
            };
            return started;
          };
          const assertDraft = expected => {
            check(editor.querySelector('input[data-service-item-field="raw_title"]') === field,
              'input DOM replaced');
            check(field.value === expected && document.activeElement === field,
              'draft or focus lost');
            check(field.selectionStart === 2 && field.selectionEnd === 5,
              'selection moved by save feedback');
          };
          field.focus();
          field.value = 'First draft';
          markServiceInputFeedbackChanged(field);
          let started = armSave();
          let pending = commitServiceItemInputs(service.id, 0);
          await started;
          check(button.disabled && button.getAttribute('aria-busy') === 'true', 'pending save not busy');
          check(status.textContent === '반영·저장 중' && !field.disabled, 'pending status or editability');
          field.value = 'Newer draft';
          field.setSelectionRange(2, 5);
          release(false);
          check(await pending === false && captured === 'First draft', 'failed result or snapshot incorrect');
          assertDraft('Newer draft');
          check(status.textContent === '저장 실패' && !button.disabled
            && button.getAttribute('aria-busy') === 'false', 'failure did not unlock retry');

          started = armSave();
          pending = commitServiceItemInputs(service.id, 0);
          await started;
          check(captured === 'Newer draft', 'retry used old input');
          field.value = 'Latest unsaved draft';
          field.setSelectionRange(2, 5);
          release(true);
          check(await pending === true, 'retry result lost');
          assertDraft('Latest unsaved draft');
          check(status.textContent === '수정됨' && !button.disabled,
            'older success falsely acknowledged newer draft');

          started = armSave();
          pending = commitServiceItemInputs(service.id, 0);
          await started;
          check(captured === 'Latest unsaved draft', 'final save missed latest draft');
          release(true);
          check(await pending === true, 'final save failed');
          assertDraft('Latest unsaved draft');
          check(status.textContent === '저장됨' && !button.disabled, 'confirmed unchanged draft not saved');
          return 'PASS header pending/failure/retry, newer draft, focus and selection';
        }"""), flush=True)
    finally:
        context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chromium", "webkit"):
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                try:
                    print(engine, flush=True)
                    run(browser, url)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
