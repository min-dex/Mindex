"""Preparation fields retain defaults and support Enter-to-apply navigation."""
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
              const previous = { services: state.services, items: state.serviceItems, drafts: state.presenterPreparationDrafts, dirty: state.dirty.service, apply: applyPresenterPreparationInput };
              const fields = html => { const host = document.createElement('div'); host.innerHTML = html; return [...host.querySelectorAll('[data-presenter-preparation-field]')]; };
              try {
                state.services = [service, ...previous.services]; state.presenterPreparationDrafts = {};
                const inputs = fields(renderPresenterServiceInputRail(service));
                check(inputs.length > 0 && inputs.some((input) => input.value), 'template defaults must be shown in value fields');
                check(inputs.every((input) => input.dataset.presenterPreparationFieldLabel), 'each field needs a fixed label');
                check(inputs.some((input) => input.dataset.presenterPreparationFieldLabel === '찬양 1'), 'numbered praise label needs readable spacing');
                check(inputs.some((input) => input.dataset.presenterPreparationFieldLabel === '인용 구절'), 'citation label needs readable spacing');
                const host = document.createElement('div'); host.innerHTML = renderPresenterSidebarPreparationInput(service);
                check(!host.querySelector('[data-presenter-preparation-form]'), 'no form button');
                state.presenterPreparationDrafts[service.id] = '찬양1: 주 은혜임을';
                check(fields(renderPresenterServiceInputRail(service))[0].value === '주 은혜임을', 'typed value is retained');
                delete state.presenterPreparationDrafts[service.id];
                check(fields(renderPresenterServiceInputRail(service)).some((input) => input.value), 'cleared draft restores template defaults');

                const interaction = document.createElement('div');
                interaction.innerHTML = renderPresenterServiceInputRail(service);
                document.body.append(interaction);
                bindDetailInteractionRoot(interaction);
                const enterFields = [...interaction.querySelectorAll('[data-presenter-preparation-field]')];
                let enterCall = null;
                applyPresenterPreparationInput = async (...args) => { enterCall = args; };
                enterFields[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
                check(enterCall && enterCall[1].focusTarget.label === enterFields[1].dataset.presenterPreparationFieldLabel, 'Enter applies then targets the next field');
                interaction.remove();
                return 'ok';
              } finally { state.services = previous.services; state.serviceItems = previous.items; state.presenterPreparationDrafts = previous.drafts; state.dirty.service = previous.dirty; applyPresenterPreparationInput = previous.apply; }
            }""")
            assert result == "ok", result
            print("PASS worship preparation defaults, citation label, and Enter navigation", flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
