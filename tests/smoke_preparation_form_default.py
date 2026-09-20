"""The bulk worship input starts filled with the service's label-only form."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof presenterPreparationDisplayTextForService === 'function' && typeof renderPresenterServiceInputRail === 'function'")
            result = page.evaluate("""() => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const service = { id: '__prep_form_default__', type_id: 'sunday-main', date: '2026-09-20', title: '주일예배 [3부]' };
              const previous = { services: state.services, drafts: state.presenterPreparationDrafts, dirty: state.dirty.service };
              const textareaValue = (html) => { const host = document.createElement('div'); host.innerHTML = html; return host.querySelector('[data-presenter-preparation-input]').value; };
              try {
                state.services = [service, ...previous.services];
                state.presenterPreparationDrafts = {};
                const form = presenterPreparationFormFromExamples(presenterPreparationPlaceholderForService(service));
                check(form && form.split('\\n').length > 3 && /^\\S+:\\s*$/m.test(form), 'the form is a list of label-only lines: ' + form);

                // untouched: both panels start with the form
                check(textareaValue(renderPresenterServiceInputRail(service)) === form, 'right panel starts with the form');
                check(textareaValue(renderPresenterSidebarPreparationInput(service)) === form, 'sidebar panel starts with the form');
                check(state.dirty.service === previous.dirty && Object.keys(state.presenterPreparationDrafts).length === 0, 'showing the form must not create a draft or mark the service dirty');

                // a filled form has nothing to apply: blank labels are skipped, nothing becomes a song or a note
                const parsed = parsePresenterPreparationInput(form, { skipEmptyLabels: true });
                check(parsed.entries.length === 0 && parsed.skipped.length > 0, 'the untouched form applies nothing');

                // what the user typed wins
                state.presenterPreparationDrafts[service.id] = '찬양1: 주 은혜임을';
                check(textareaValue(renderPresenterServiceInputRail(service)) === '찬양1: 주 은혜임을', 'a typed draft is kept');
                // a box emptied on purpose stays empty
                state.presenterPreparationDrafts[service.id] = '';
                check(textareaValue(renderPresenterServiceInputRail(service)) === '', 'an emptied box stays empty');
                // after a successful apply the draft is deleted and the form comes back
                delete state.presenterPreparationDrafts[service.id];
                check(textareaValue(renderPresenterServiceInputRail(service)) === form, 'the form returns after the draft is cleared');

                // keyboard focus on the untouched form lands after the first label (Tab then starts at slot 1)
                const host = document.createElement('div'); host.innerHTML = renderPresenterServiceInputRail(service); document.body.append(host);
                const box = host.querySelector('[data-presenter-preparation-input]'); box.setSelectionRange(0, 0);
                placeCaretInUntouchedPreparationForm(box);
                check(box.value.slice(0, box.selectionStart) === form.split('\\n')[0], 'caret after the first label, got ' + JSON.stringify(box.value.slice(0, box.selectionStart)));
                check(presenterPreparationTabTarget(box.value, box.selectionStart) === form.split('\\n')[0].length + 1 + form.split('\\n')[1].length, 'Tab from there goes to the second slot');
                box.setSelectionRange(3, 3); placeCaretInUntouchedPreparationForm(box);
                check(box.selectionStart === 3, 'an explicit caret position is never moved');
                state.presenterPreparationDrafts[service.id] = form; box.setSelectionRange(0, 0); placeCaretInUntouchedPreparationForm(box);
                check(box.selectionStart === 0, 'a user draft is never touched');
                delete state.presenterPreparationDrafts[service.id]; host.remove();

                // no examples: nothing to prefill
                const empty = { id: '__prep_none__', type_id: '__none__', date: '2026-09-20', title: '' };
                state.services = [empty, ...state.services];
                check(textareaValue(renderPresenterServiceInputRail(empty)) === (presenterPreparationFormFromExamples(presenterPreparationPlaceholderForService(empty)) || ''), 'services without a form stay empty');
                return 'ok';
              } finally {
                state.services = previous.services; state.presenterPreparationDrafts = previous.drafts;
              }
            }""")
            assert result == 'ok', result
            print('PASS bulk worship input starts with the form', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
