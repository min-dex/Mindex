"""Bulk input renders fixed labels with empty value fields."""
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
              const fields = html => { const host = document.createElement('div'); host.innerHTML = html; return [...host.querySelectorAll('[data-presenter-preparation-field]')]; };
              try {
                state.services = [service, ...previous.services]; state.presenterPreparationDrafts = {};
                const inputs = fields(renderPresenterServiceInputRail(service));
                check(inputs.length > 0 && inputs.every((input) => input.value === ''), 'value fields must start empty');
                check(inputs.every((input) => input.dataset.presenterPreparationFieldLabel), 'each field needs a fixed label');
                check(inputs.some((input) => input.dataset.presenterPreparationFieldLabel === '찬양 1'), 'numbered praise label needs readable spacing');
                const host = document.createElement('div'); host.innerHTML = renderPresenterSidebarPreparationInput(service);
                check(!host.querySelector('[data-presenter-preparation-form]'), 'no form button');
                state.presenterPreparationDrafts[service.id] = '찬양1: 주 은혜임을';
                check(fields(renderPresenterServiceInputRail(service))[0].value === '주 은혜임을', 'typed value is retained');
                delete state.presenterPreparationDrafts[service.id];
                check(fields(renderPresenterServiceInputRail(service)).every((input) => input.value === ''), 'cleared draft returns to empty values');
                return 'ok';
              } finally { state.services = previous.services; state.presenterPreparationDrafts = previous.drafts; state.dirty.service = previous.dirty; }
            }""")
            assert result == "ok", result
            print("PASS bulk worship input renders fixed labels with empty values", flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
