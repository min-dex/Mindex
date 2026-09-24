"""Bulk worship input keeps labels fixed beside value-only fields."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chromium", "webkit"):
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof presenterPreparationDraftForApply === 'function'")
                result = page.evaluate("""async () => {
                  const check = (ok, message) => { if (!ok) throw new Error(message); };
                  const service = { id: 'values-only-fixture', type_id: 'fixture' };
                  const make = (label, memo, section) => normalizeServiceItem({
                    id: label, service_id: service.id, label, raw_title: '',
                    _worshipSectionKey: section, memo: serializeServiceItemMemo(memo),
                  }, 0);
                  const items = [
                    make('광고', { elementType: 'body', inputMode: 'text' }, 'announcements'),
                    make('대표기도', { elementType: 'title_person', inputMode: 'text' }, 'prayer'),
                  ];
                  const previous = { services: state.services, items: state.serviceItems, drafts: state.presenterPreparationDrafts };
                  try {
                    state.services = [service]; state.serviceItems = { [service.id]: items };
                    state.presenterPreparationDrafts = {}; state.selectedServiceId = service.id;
                    servicePrepEditorItems = () => state.serviceItems[service.id];
                    getServiceItems = () => state.serviceItems[service.id];
                    const host = document.createElement('div'); host.innerHTML = renderPresenterServiceInputRail(service); document.body.append(host);
                    const inputs = [...host.querySelectorAll('[data-presenter-preparation-field]')];
                    check(inputs.length === 2, 'two fixed fields render');
                    check(inputs[0].dataset.presenterPreparationFieldLabel === '광고', 'first field label');
                    check(inputs[0].value === '' && inputs[0].placeholder.includes('다음 주 예배'), 'value field starts empty with example');
                    check(!host.querySelector('[data-presenter-preparation-form]'), 'the form button must not render');
                    inputs[0].value = '공지 내용'; inputs[1].value = '김은혜 집사';
                    const draft = presenterPreparationDraftFromRoot(host, service);
                    check(draft === '광고: 공지 내용\\n대표기도: 김은혜 집사', 'field mapping: ' + draft);
                    const prepared = presenterPreparationDraftForApply(service, draft);
                    check(prepared.value === draft, 'prepared labeled draft');
                    const legacy = presenterPreparationDraftForApply(service, '광고: 기존 공지\\n대표기도: 김은혜 집사');
                    check(legacy.value.includes('광고: 기존 공지'), 'legacy labels remain supported');
                    host.remove();
                    return 'ok';
                  } finally { state.services = previous.services; state.serviceItems = previous.items; state.presenterPreparationDrafts = previous.drafts; }
                }""")
                assert result == "ok", result
                print(engine, "PASS fixed-label bulk input fields and legacy labels", flush=True)
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
