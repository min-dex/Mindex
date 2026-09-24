"""Bulk worship input accepts values in template order without inserting labels."""
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
                    const values = presenterPreparationValueExamplesForService(service);
                    check(values.includes('다음 주 예배 후 모임이 있습니다') && !values.includes('광고:'), 'value-only examples: ' + values);
                    const host = document.createElement('div'); host.innerHTML = renderPresenterServiceInputRail(service); document.body.append(host);
                    const input = host.querySelector('[data-presenter-preparation-input]');
                    check(input.value === '', 'the input must start empty');
                    check(!host.querySelector('[data-presenter-preparation-form]'), 'the form button must not render');
                    check(input.placeholder === values, 'placeholder must contain only values');
                    const prepared = presenterPreparationDraftForApply(service, '공지 내용\\n김은혜 집사');
                    check(prepared.value === '광고: 공지 내용\\n대표기도: 김은혜 집사', 'slot mapping: ' + prepared.value);
                    const legacy = presenterPreparationDraftForApply(service, '광고: 기존 공지\\n대표기도: 김은혜 집사');
                    check(legacy.value.includes('광고: 기존 공지'), 'legacy labels remain supported');
                    const scripture = presenterPreparationDraftForApply(service, '요 3:16');
                    check(scripture.value.startsWith('광고: 요 3:16'), 'scripture-shaped value remains a value');
                    const overflow = presenterPreparationDraftForApply(service, '첫 줄\\n둘째 줄\\n셋째 줄');
                    check(overflow.error.includes('3번째 줄'), 'overflow is explicit');
                    host.remove();
                    return 'ok';
                  } finally { state.services = previous.services; state.serviceItems = previous.items; state.presenterPreparationDrafts = previous.drafts; }
                }""")
                assert result == "ok", result
                print(engine, "PASS values-only bulk input, legacy labels, and slot bounds", flush=True)
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
