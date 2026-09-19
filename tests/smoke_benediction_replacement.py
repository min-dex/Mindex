"""Instance-only benediction replacement, persistence, projection and restore."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url):
    context = browser.new_context()
    context.route('**/*supabase*/**', lambda route: route.abort())
    page = context.new_page()
    page.goto(url + '?output=presenter', wait_until='domcontentloaded')
    page.wait_for_function("typeof replaceServiceBenediction === 'function'")
    results = page.evaluate("""async () => {
      const check = (ok, msg) => { if (!ok) throw Error(msg); };
      const clone = value => JSON.parse(JSON.stringify(value));
      const sid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
      const columns = {inputMode:true, contentState:true};
      const results = [];
      refs.detailPane = document.createElement('section');
      document.body.append(refs.detailPane);
      requireClient = () => true;
      ensureWorshipServiceRowsLoadedForPersistence = async () => {};
      worshipElementTypedStateColumns = async () => columns;
      captureWorshipRecoverySnapshot = () => {};
      updateSaveState = () => {};
      refreshPresenterForService = () => {};
      renderServiceList = () => {};
      render = () => {};
      captureCleanFingerprint = () => {};
      let fail = false, writes = [];
      state.client = {from:table => ({
        upsert:async rows => { writes.push({table, rows:clone(rows)}); return {error:fail ? Error('injected failure') : null}; },
        update:() => ({eq:async () => ({error:null, count:1})}),  // save receipts require count === 1 (e4158878)
        delete:() => ({in:async () => ({error:null})}),
      })};
      const fixture = type => {
        // 2026-09-13 is a 김석범 Sunday, so the 1부 template has a 축도 (not 주기도문).
        const service = {id:sid, type_id:type, date:'2026-09-13'};
        state.services = [service];
        state.selectedServiceId = sid;
        state.saving = false; activeServiceSavePromise = null;
        state.dirtyServiceElementIds = new Map();
        state.dirtyServiceStructureIds = new Set();
        state.dirtyServiceTypeIds = new Set();
        state.templateElementSuppressions = new Map();
        state.dirty.service = false;
        // Derive the fixture from the real scaffold: a lone 축도 without its sibling
        // template elements is not a shape the app produces and made template
        // projection merge it with the fixed 송영.
        const scaffold = buildWorshipServiceScaffold(sid, type, {service});
        const items = groupWorshipElements(scaffold.sections, scaffold.elements)[sid];
        const item = items.find(x => x.label === '축도');
        if (!item) throw Error(type+' scaffold has no 축도');
        item.assignee = '원래 담당 목사';
        item.memo = serializeServiceItemMemo({...parseServiceItemMemo(item.memo), note:'원래 메모'});
        item._worshipElementTemplateModified = true;
        const rows = buildWorshipPersistenceRows(service, items, {}, {}, {elementTypedStateColumns:columns});
        state.worshipSections = rows.sections; state.worshipElements = rows.elements;
        state.serviceItems = {[sid]:groupWorshipElements(rows.sections, rows.elements)[sid]};
        refs.detailPane.innerHTML = '';
        writes = []; fail = false;
        return service;
      };
      const roundtrip = service => {
        const rows = buildWorshipPersistenceRows(service, getServiceItems(sid), {}, {}, {elementTypedStateColumns:columns});
        validateWorshipPersistenceRows(rows, {serviceId:sid});
        state.worshipSections = rows.sections; state.worshipElements = rows.elements;
        state.serviceItems[sid] = groupWorshipElements(rows.sections, rows.elements)[sid];
        return rows;
      };
      for (const type of ['wednesday','sunday-first','sunday-second','sunday-main','sunday-afternoon','monthly','young-adult']) {
        const service = fixture(type);
        const original = getServiceItems(sid).find(x => x.label === '축도');
        check(original, type+' missing original');
        const before = clone(original);
        check(parseServiceItemMemo(before.memo).note === '원래 메모', type+' stored note not loaded');
        check(presenterServiceInputControls(original, 0, service).includes('주기도문으로 변경'), type+' missing common button');
        check(replaceServiceBenediction(original, true), type+' switch rejected');
        let rows = roundtrip(service);
        let replacement = getServiceItems(sid).find(x => parseServiceItemMemo(x.memo).benedictionReplacement);
        check(replacement?.label === '주기도문' && replacement.assignee === '', type+' replacement lost');
        check(!getServiceItems(sid).some(x => x.label === '축도'), type+' benediction regenerated');
        check(presenterServiceInputControls(replacement, 0, service).includes('축도로 되돌리기'), type+' missing restore');
        state.saving = true;
        check(!presenterServiceInputControls(replacement, 0, service).includes('disabled'), type+' save-time render leaves button locked');
        state.saving = false;
        const slides = buildPresenterSlidesForServiceItem(replacement, service, 0);
        check(JSON.stringify(slides).includes('하늘에 계신'), type+' prayer body missing from slides');
        check(serviceDocumentExceptionForItem(service, replacement).type === 'benediction_replacement', 'exception note missing');
        replacement = getServiceItems(sid).find(x => parseServiceItemMemo(x.memo).benedictionReplacement);
        check(replaceServiceBenediction(replacement, false), type+' restore rejected');
        rows = roundtrip(service);
        const restored = getServiceItems(sid).find(x => x.label === '축도');
        check(restored?.assignee === before.assignee && restored.raw_title === before.raw_title, type+' original content lost '+JSON.stringify({before,restored}));
        check(restored.memo === before.memo, type+' original memo lost');
        check(!JSON.stringify(buildPresenterSlidesForServiceItem(restored, service, 0)).includes('하늘에 계신'), type+' prayer remained after restore');
        check(!rows.elements.some(x => x.config.benedictionReplacement), type+' stale override persisted');
        results.push(type+' common control / DB roundtrip / slides / restoration');
      }
      const service = fixture('wednesday');
      let target = getServiceItems(sid).find(x => x.label === '축도');
      const other = clone(target);
      check(await setServiceBenedictionReplacement(sid, target.id, true), 'save failed');
      check(writes.some(x => x.table === 'mindex_worship_elements' && x.rows.some(e => e.config.benedictionReplacement)), 'replacement not sent to DB');
      check(other.label === '축도', 'separate instance changed');
      target = getServiceItems(sid).find(x => parseServiceItemMemo(x.memo).benedictionReplacement);
      check(await setServiceBenedictionReplacement(sid, target.id, false), 'restore save failed');
      target = getServiceItems(sid).find(x => x.label === '축도');
      fail = true;
      check(await setServiceBenedictionReplacement(sid, target.id, true) === false, 'failure reported success');
      check(state.dirty.service && getServiceItems(sid).some(x => parseServiceItemMemo(x.memo).benedictionReplacement), 'failure lost draft');
      results.push('real save path / restore / failure retains draft');
      fail = false;
      target = getServiceItems(sid).find(x => parseServiceItemMemo(x.memo).benedictionReplacement);
      refs.detailPane.innerHTML = presenterServiceInputControls(target, getServiceItems(sid).findIndex(x => x.id === target.id), service);
      refs.detailPane.addEventListener('click', handleDetailClick);
      document.getElementById('presenterOutputRoot')?.remove();
      return results;
    }""")
    for result in results:
        print('PASS', result, flush=True)
    page.get_by_role('button', name='축도로 되돌리기').click()
    page.wait_for_function("!state.saving && getServiceItems(state.selectedServiceId).some(x => x.label === '축도')")
    print('PASS actual delegated button click', flush=True)
    context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    print(engine, flush=True)
                    run(browser, url)
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
