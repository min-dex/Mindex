"""Untouched bulk inputs stay empty and expose value-only examples."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("typeof presenterPreparationDisplayTextForService === 'function' && typeof renderPresenterServiceInputRail === 'function'")
            result = page.evaluate("""() => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const service = { id: '__prep_values_default__', type_id: 'sunday-main', date: '2026-09-20', title: '주일예배 [3부]' };
              const previous = { services: state.services, drafts: state.presenterPreparationDrafts, dirty: state.dirty.service };
              const textarea = html => { const host = document.createElement('div'); host.innerHTML = html; return host.querySelector('[data-presenter-preparation-input]'); };
              try {
                state.services = [service, ...previous.services]; state.presenterPreparationDrafts = {};
                const examples = presenterPreparationValueExamplesForService(service);
                const box = textarea(renderPresenterServiceInputRail(service));
                check(box.value === '', 'untouched input must be empty');
                check(box.placeholder === examples && !/^\S+[:：]/m.test(examples), 'examples must be values only: ' + examples);
                const host = document.createElement('div'); host.innerHTML = renderPresenterSidebarPreparationInput(service);
                check(!host.querySelector('[data-presenter-preparation-form]'), 'no form button');
                state.presenterPreparationDrafts[service.id] = '주 은혜임을';
                check(textarea(renderPresenterServiceInputRail(service)).value === '주 은혜임을', 'typed value is retained');
                delete state.presenterPreparationDrafts[service.id];
                check(textarea(renderPresenterServiceInputRail(service)).value === '', 'cleared draft returns to an empty input');
                return 'ok';
              } finally { state.services = previous.services; state.presenterPreparationDrafts = previous.drafts; state.dirty.service = previous.dirty; }
            }""")
            assert result == "ok", result
            print("PASS bulk worship input starts empty with value-only examples", flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
