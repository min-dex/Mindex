"""Save race regressions using real row conversion and an in-memory DB double."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url):
    context = browser.new_context()
    context.route('**/*supabase*/**', lambda route: route.abort())
    page = context.new_page()
    page.goto(url + '?output=presenter', wait_until='domcontentloaded')
    page.wait_for_function("typeof saveServiceItemPatch === 'function'")
    results = page.evaluate("""async () => {
      const check = (ok, message) => { if (!ok) throw Error(message); };
      const clone = value => JSON.parse(JSON.stringify(value));
      const sid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
      const columns = {inputMode:true, contentState:true};
      let hook, writes, renders, refreshOptions;
      refs.detailPane = document.createElement('section');
      document.body.append(refs.detailPane);
      requireClient = () => true;
      ensureWorshipServiceRowsLoadedForPersistence = async () => {};
      worshipElementTypedStateColumns = async () => columns;
      captureWorshipRecoverySnapshot = () => {};
      updateSaveState = () => {};
      const realRefresh = refreshPresenterForService;
      refreshPresenterForService = (id, options) => { refreshOptions = options; };
      renderServiceList = () => {};
      render = () => { renders++; };
      captureCleanFingerprint = () => {};
      const fixture = (type = 'audit-fixture') => {
        const service = {id:sid, type_id:type, date:'2026-09-06'};
        const inputs = [0,1].map(i => normalizeServiceItem({service_id:sid,
          label:'찬양 '+(i+1), raw_title:'Original '+i,
          memo:serializeServiceItemMemo({elementType:'praise', inputMode:'manual_praise',
            outputMode:'lyrics', slides:['Line '+i]}),
          _worshipSectionKey:'praise', _worshipSectionTitle:'Praise',
          _worshipElementTemplateModified:true, _worshipTemplatePlaceholder:false}, i));
        const rows = buildWorshipPersistenceRows(service, inputs, {}, {}, {elementTypedStateColumns:columns});
        state.services = [service];
        state.worshipSections = rows.sections;
        state.worshipElements = rows.elements;
        state.serviceItems = {[sid]:groupWorshipElements(rows.sections, rows.elements)[sid]};
        state.selectedServiceId = sid;
        state.module = 'presenter';
        state.saving = false;
        activeServiceSavePromise = null;
        state.dirtyServiceElementIds = new Map();
        state.dirtyServiceStructureIds = new Set();
        state.dirtyServiceTypeIds = new Set();
        state.templateElementSuppressions = new Map();
        state.dirty.service = false;
        refs.detailPane.innerHTML = '';
        writes = []; renders = 0; hook = null; refreshOptions = null;
        const write = async (table, value) => {
          writes.push({table, value:clone(value)});
          const result = hook ? await hook(table, value) : {error:null};
          return {count:1, ...result};
        };
        state.client = {from:table => ({
          upsert:rows => write(table, rows),
          update:value => ({eq:() => write(table, value)}),
          delete:() => ({in:() => write(table, [])}),
        })};
        return state.serviceItems[sid].map(item => item.id);
      };
      const item = id => getServiceItems(sid).find(item => item.id === id);
      const edit = (id, value) => {
        item(id).raw_title = value;
        markServiceElementDirty(sid, item(id));
        state.dirty.service = true;
      };
      const save = id => saveServiceItemPatch(sid, getServiceItems(sid).findIndex(x => x.id === id),
        {silent:true, renderAfterSave:false, throwOnError:true});
      const block = (fail = false) => {
        let release, entered;
        const started = new Promise(resolve => { entered = resolve; });
        const gate = new Promise(resolve => { release = resolve; });
        hook = async table => {
          if (table !== 'mindex_worship_elements') return {error:null};
          hook = null;
          entered(); await gate;
          return {error:fail ? new Error('injected failure') : null};
        };
        return {started, release};
      };
      const results = [];
      for (const mode of ['full', 'element']) {
        const [target] = fixture();
        edit(target, 'Keep invalid-scope draft');
        const realBuild = buildWorshipPersistenceRows;
        buildWorshipPersistenceRows = (...args) => {
          const rows = realBuild(...args);
          rows.sections[0].service_id = 'another-service';
          return rows;
        };
        let rejected = false;
        try {
          if (mode === 'full') await saveService(sid, {silent:true, renderAfterSave:false, throwOnError:true});
          else await save(target);
        } catch (error) { rejected = error.message.includes('service ownership mismatch'); }
        finally { buildWorshipPersistenceRows = realBuild; }
        check(rejected && writes.length === 0, mode+' invalid scope reached DB');
        check(state.dirty.service && item(target).raw_title === 'Keep invalid-scope draft', mode+' rejected save lost draft');
        check(!state.saving && !activeServiceSavePromise, mode+' rejected save kept lock');
      }
      results.push('full and element saves reject foreign sections before any DB write');
      for (const count of [0, null]) {
        const [target] = fixture();
        edit(target, 'Keep this draft');
        hook = async table => table === 'mindex_worship_services'
          ? {error:null, count} : {error:null};
        let failed = false;
        try { await save(target); } catch (_) { failed = true; }
        check(failed && state.dirty.service, 'unconfirmed patch acknowledged');
        check(item(target).raw_title === 'Keep this draft', 'patch failure lost draft');
      }
      results.push('zero/missing affected count rejects patch and retains draft');

      let [fullTarget] = fixture();
      edit(fullTarget, 'Keep full draft');
      const originalRef = state.services[0]._worshipSourceRef;
      hook = async () => ({error:null, count:0});
      let fullFailed = false;
      try {
        await saveService(sid, {silent:true, renderAfterSave:false, throwOnError:true});
      } catch (_) { fullFailed = true; }
      check(fullFailed && state.dirty.service, 'unconfirmed full save acknowledged');
      check(writes.length === 1 && writes[0].table === 'mindex_worship_services',
        'full save wrote children after zero-row update');
      check(state.services[0]._worshipSourceRef === originalRef, 'failed save replaced source baseline');
      results.push('zero-row full save stops before children and preserves baseline');

      let [a,b] = fixture();
      state.services[0]._worshipSourceRef = withServiceDocumentSnapshot(state.services[0], getServiceItems(sid));
      const baseDocument = serviceDocumentSnapshotFromRef(state.services[0]);
      baseDocument.sourceText += '\\n\\n[별도]\\n사용자 항목: Keep unknown extension';
      state.services[0]._worshipSourceRef[MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY] = baseDocument;
      const emptySnapshot = buildServiceDocumentSlideSnapshots(sid, [], state.services[0]);
      check(!JSON.stringify(emptySnapshot).includes('Original 1'), 'empty explicit snapshot revived old document slides');
      edit(a, 'Save A'); edit(b, 'Draft B');
      state.services[0]._worshipSourceTextDraft = 'UNSAVED WHOLE SERVICE SOURCE';
      await save(a);
      check(item(b).raw_title === 'Draft B', 'sibling draft overwritten');
      check(state.dirtyServiceElementIds.get(sid)?.has(b), 'sibling draft marked clean');
      check(state.dirty.service, 'dirty sibling lost');
      const storedDocument = serviceDocumentSnapshotFromRef(state.services[0]);
      check(storedDocument.sourceText.includes('Save A') && storedDocument.sourceText.includes('Original 1'), 'element document did not use committed sibling');
      check(storedDocument.sourceText.includes('Keep unknown extension'), 'unknown source text lost');
      check(!JSON.stringify(storedDocument).includes('Draft B'), 'sibling draft leaked into document/slides');
      check(!JSON.stringify(storedDocument).includes('UNSAVED WHOLE SERVICE SOURCE'), 'whole-source draft leaked into element save');
      check(state.services[0]._worshipSourceTextDraft === 'UNSAVED WHOLE SERVICE SOURCE', 'whole-source draft lost locally');
      results.push('sibling draft preserved');

      [a,b] = fixture(); edit(a, 'First');
      let wait = block(), pending = save(a);
      await wait.started; edit(a, 'Newer'); wait.release(); await pending;
      check(item(a).raw_title === 'Newer' && state.dirty.service, 'late edit lost');
      check(state.dirtyServiceElementIds.get(sid)?.has(a), 'late edit acknowledged');
      await save(a);
      check(!state.dirty.service, 'second save did not become clean');
      results.push('late edit retained until saved');

      [a,b] = fixture(); edit(a, 'First');
      wait = block(); pending = save(a); await wait.started;
      edit(b, 'Queued B'); const queuedB = save(b);
      edit(a, 'Latest A'); const queuedA = save(a);
      state.serviceItems[sid].reverse();
      wait.release();
      check((await Promise.all([pending, queuedB, queuedA])).every(Boolean), 'queue rejected');
      check(item(a).raw_title === 'Latest A' && item(b).raw_title === 'Queued B', 'queue identity changed');
      check(!state.dirty.service && !state.saving && !activeServiceSavePromise, 'queue did not settle');
      results.push('multiple queued edits use stable item IDs');

      [a,b] = fixture(); edit(a, 'Before failure');
      wait = block(true); pending = save(a).catch(() => false); await wait.started;
      edit(a, 'Retry'); const retry = save(a);
      wait.release(); check(await pending === false, 'failure swallowed');
      check(await retry && item(a).raw_title === 'Retry' && !state.dirty.service, 'retry lost');
      results.push('failed save releases queue for retry');

      [a,b] = fixture(); edit(a, 'Full first');
      wait = block(); pending = saveService(sid, {silent:true, renderAfterSave:false, throwOnError:true});
      await wait.started; edit(b, 'During full save'); wait.release(); await pending;
      check(item(b).raw_title === 'During full save' && state.dirty.service, 'full save lost edit');
      await saveService(sid, {silent:true, renderAfterSave:false, throwOnError:true});
      check(!state.dirty.service, 'full save never became clean');
      results.push('full save preserves later edits');

      [a,b] = fixture();
      state.worshipElements = [];
      edit(a, 'New item');
      wait = block(); pending = saveService(sid, {silent:true, renderAfterSave:false, throwOnError:true});
      await wait.started; edit(a, 'New item edited'); const queuedNew = save(a);
      wait.release(); await pending;
      check(await queuedNew, 'queued new item lost its identity');
      check(getServiceItems(sid).some(x => x.raw_title === 'New item edited'), 'new item edit lost');
      check(!state.dirty.service, 'new item never became clean');
      results.push('new persisted IDs carry queued edits');

      [a,b] = fixture(); edit(a, 'First');
      wait = block(); pending = save(a); await wait.started;
      const deletedSave = save(b);
      state.serviceItems[sid] = state.serviceItems[sid].filter(x => x.id !== b);
      markServiceStructureDirty(sid);
      wait.release(); await pending;
      check(await deletedSave === false && !item(b), 'deleted queued item resurrected');
      check(state.dirty.service && state.dirtyServiceStructureIds.has(sid), 'deletion marked clean');
      results.push('deleted queued item is not resurrected');

      [a,b] = fixture(); edit(a, 'Still dirty');
      wait = block(true); pending = save(a).catch(() => false); await wait.started;
      wait.release(); check(await pending === false && state.dirty.service && item(a).raw_title === 'Still dirty', 'failure discarded draft');
      check(!state.saving && !activeServiceSavePromise, 'failure left save locked');
      results.push('failure preserves draft and unlocks saving');

      [a,b] = fixture(); edit(a, 'Saved');
      wait = block(); pending = save(a); await wait.started;
      refs.detailPane.innerHTML = `<textarea data-service-item-field="raw_title" data-service-id="${sid}" data-initial-value="Old">Still typing</textarea>`;
      wait.release(); await pending;
      check(state.dirty.service && renders === 0 && refs.detailPane.querySelector('textarea').value === 'Still typing', 'typing DOM replaced');
      check(refreshOptions?.renderControls === false, 'save refresh would replace pending inputs');
      results.push('pending typing survives save completion');

      [a,b] = fixture(); edit(a, 'Saved');
      state.dirtyServiceElementIds.set('other-service', new Set(['other-item']));
      await save(a);
      check(state.dirty.service, 'other service marked clean');
      results.push('other service remains dirty');
      [a,b] = fixture(); state.saving = true;
      check(await saveService(sid, {silent:true}) === false, 'full save stole unrelated lock');
      check(await saveServiceItemPatch(sid, 0, {silent:true}) === false, 'patch stole unrelated lock');
      check(await save(a).catch(() => 'rejected') === 'rejected', 'busy throwOnError ignored');
      check(state.saving && writes.length === 0, 'busy guard performed a write');
      results.push('unrelated save lock and error options preserved');

      [a,b] = fixture(); edit(a, 'Fallback');
      const realPatch = saveWorshipServiceElementPatch;
      saveWorshipServiceElementPatch = async () => false;
      try {
        check(await save(a), 'patch fallback failed');
        check(!state.saving && !activeServiceSavePromise && !state.dirty.service, 'fallback left save locked');
      } finally { saveWorshipServiceElementPatch = realPatch; }
      results.push('patch fallback releases lock before full save');

      [a,b] = fixture(); edit(a, 'Keep after type failure');
      const realSaveTypes = saveDirtyServiceTypes;
      saveDirtyServiceTypes = async () => { throw Error('injected type save failure'); };
      try {
        check(await saveServiceItemPatch(sid, 0, {silent:true}) === false, 'save error did not return false');
        check(!state.saving && !activeServiceSavePromise && state.dirty.service && writes.length === 0, 'type failure lost dirty state or lock');
      } finally { saveDirtyServiceTypes = realSaveTypes; }
      check(await save(a), 'save could not retry after type failure');
      results.push('shared lifecycle handles prerequisite failure and retry');
      for (const type of ['sunday-first', 'sunday-second', 'sunday-main', 'sunday-afternoon']) {
        [a,b] = fixture(type);
        edit(a, 'Saved title'); edit(b, 'Unsaved title');
        await save(a);
        check(item(b)?.raw_title === 'Unsaved title', type+' lost sibling draft');
        check(!state.dirtyServiceElementIds.get(sid)?.has(a), type+' saved item remained dirty');
        results.push(type+' template projection preserves drafts');
      }
      state.presenter.serviceId = null;
      renderPresenterControlState = () => { throw Error('inactive refresh ignored renderControls'); };
      realRefresh(sid, {renderControls:false});
      results.push('inactive presenter respects explicit render suppression');
      return results;
    }""")
    for result in results:
        print('PASS', result, flush=True)
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
