from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ["chromium", "webkit"]:
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                for width, height in [(1440, 900), (390, 844)]:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.route("**/*supabase*/**", lambda route: route.abort())
                    page.goto(url + "?mindexSmokeRaw=1", wait_until="domcontentloaded")
                    page.wait_for_function("typeof openWorshipConflictReview === 'function'")
                    print(engine, width, page.evaluate("""async () => {
                      const check = (ok, why) => { if (!ok) throw Error(why); };
                      const service = {id:'review-fixture', title:'예배', _worshipSourceTextDraft:'내 입력 <script>alert(1)</script>\\n'.repeat(12)};
                      state.services = [service];
                      const items = [{id:'item', raw_title:'입력 중', memo:'', label:'광고'}];
                      getServiceItems = () => items;
                      serviceSourceTextareaForService = () => null;
                      let release, reads = 0, saves = 0, resumes = 0;
                      saveAll = async () => { saves++; };
                      scheduleServiceMusicResume = () => { resumes++; };
                      const exported = [];
                      downloadTextFile = text => exported.push(JSON.parse(text));
                      worshipAtomicClient = async () => ({inspectConflict: async (id, draft) => {
                        reads++;
                        const frozen = structuredClone(draft);
                        await new Promise(resolve => { release = resolve; });
                        return {serviceId:id, draft:frozen, baseline:{revision:'3'},
                          latest:{revision:'4',service:{id,source_ref:{mindexServiceDocument:{sourceText:'서버의 새 원문\\n'.repeat(18)}}}}};
                      }});
                      delete window.MINDEX_WORSHIP_ATOMIC_PROTOCOL;
                      await openWorshipConflictReview(service.id);
                      check(!document.querySelector('.worship-conflict-dialog'), 'disabled protocol opened dialog');
                      window.MINDEX_WORSHIP_ATOMIC_PROTOCOL = 1;
                      const opening = openWorshipConflictReview(service.id);
                      await new Promise(resolve => setTimeout(resolve, 0));
                      const dialog = document.querySelector('.worship-conflict-dialog');
                      check(dialog?.open, 'modal not visible');
                      check(!dialog.querySelector('.worship-conflict-details').open, 'source comparison starts expanded');
                      check(dialog.querySelector('[aria-label="저장 충돌 요약"]'), 'conflict summary missing');
                      await openWorshipConflictReview(service.id);
                      check(reads === 1, 'duplicate conflict review started another read');
                      items[0].raw_title = '저장 이후 새 입력';
                      release(); await opening;
                      check(items[0].raw_title === '저장 이후 새 입력', 'review overwrote active draft');
                      check(!dialog.querySelector('[data-conflict-keep]').disabled && !dialog.querySelector('[data-conflict-reopen]').disabled, 'loaded conflict choices remain disabled');
                      dialog.querySelector('[data-conflict-export]').click();
                      check(exported[0].draft.items[0].raw_title === '입력 중', 'export not frozen at review start');
                      check(dialog.querySelector('[aria-label="내 입력"]').value.includes('<script>'), 'text not preserved');
                      check(!dialog.querySelector('script'), 'user text interpreted as HTML');
                      check(dialog.querySelector('[data-conflict-server-summary]').textContent.includes('기준 3') && dialog.querySelector('[data-conflict-server-summary]').textContent.includes('저장본 4'), 'server revision summary missing');
                      check(dialog.querySelector('[data-conflict-export]').textContent.includes('내 초안 다운로드'), 'draft download action unclear');
                      check(dialog.querySelector('[data-conflict-keep]').textContent.includes('내 입력 계속 사용'), 'keep choice unclear');
                      check(dialog.querySelector('[data-conflict-reopen]').textContent.includes('초안 보관 후 최신본으로 전환'), 'latest choice unclear');
                      const button = dialog.querySelector('[data-conflict-close]');
                      button.dispatchEvent(new KeyboardEvent('keydown',{key:'s',code:'KeyS',metaKey:true,bubbles:true,cancelable:true}));
                      button.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
                      check(saves === 0 && resumes === 0, 'review triggered save or music resume');
                      const rect = dialog.getBoundingClientRect();
                      check(rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight, 'dialog overflow');
                      check(dialog.scrollWidth <= dialog.clientWidth + 1, 'horizontal overflow');
                      return 'PASS gated, frozen draft, no writes, no audio interaction, responsive comparison';
                    }"""), flush=True)
                    page.screenshot(path=f"/private/tmp/mindex-conflict-{engine}-{width}.png")
                    page.keyboard.press("Escape")
                    page.wait_for_selector(".worship-conflict-dialog", state="detached")
                    print(page.evaluate("""async () => {
                      worshipAtomicClient = async () => ({inspectConflict:async () => {throw Error('offline')}});
                      await openWorshipConflictReview('review-fixture');
                      const dialog = document.querySelector('.worship-conflict-dialog');
                      if (!dialog.textContent.includes('불러오지 못했습니다')) throw Error('missing failure state');
                      if (!dialog.querySelector('[aria-label="내 입력"]').value) throw Error('failure lost draft');
                      await new Promise(resolve => {dialog.addEventListener('close', resolve, {once:true}); dialog.close();});
                      let release;
                      worshipAtomicClient = async () => ({inspectConflict: () => new Promise(resolve => {release=resolve})});
                      const pending = openWorshipConflictReview('review-fixture');
                      await new Promise(resolve => setTimeout(resolve, 0));
                      const closing = document.querySelector('.worship-conflict-dialog');
                      await new Promise(resolve => {closing.addEventListener('close', resolve, {once:true}); closing.close();});
                      release({latest:null,baseline:null}); await pending;
                      if (document.querySelector('.worship-conflict-dialog')?.open) throw Error('late read reopened closed dialog');
                      return 'PASS failure retains draft; late response does not reopen dismissed review';
                    }"""), flush=True)
                    page.wait_for_selector(".worship-conflict-dialog", state="detached")
                    print(page.evaluate("""async () => {
                      saveDirtyServiceTypes = async () => {};
                      beginServiceInputFeedback = () => [];
                      finishServiceInputFeedback = () => {};
                      updateSaveState = () => {};
                      showToast = () => {};
                      worshipAtomicClient = async () => ({inspectConflict: async (id, draft) => ({serviceId:id,draft,baseline:{revision:'3'},latest:null})});
                      const fail = async () => {throw Error('REVISION_CONFLICT')};
                      const result = await runServiceSave({feedbackServiceId:'review-fixture'}, fail);
                      await new Promise(resolve => setTimeout(resolve, 0));
                      const dialog = document.querySelector('.worship-conflict-dialog');
                      if (result !== false || state.saving || !dialog?.open) throw Error('save conflict did not unlock and open review');
                      if (!dialog.textContent.includes('서버에서 삭제된 예배')) throw Error('deleted service state missing');
                      dialog.close();
                      return 'PASS actual save conflict opens review; deleted service identified and save lock released';
                    }"""), flush=True)
                    page.wait_for_selector(".worship-conflict-dialog", state="detached")
                    print(page.evaluate("""async () => {
                      const check = (ok, why) => { if (!ok) throw Error(why); };
                      const {createWorshipAtomicClient} = await import('./mindex.worship-atomic-client.mjs');
                      const id = 'review-fixture', other = {id:'other',title:'다른 예배'};
                      const original = {id,title:'내 초안',_worshipSourceTextDraft:'보관할 입력'};
                      state.services = [original,other];
                      state.serviceItems = {[id]:[{id:'old-item',raw_title:'미저장'}],other:[{id:'other-item'}]};
                      getServiceItems = id => state.serviceItems[id];
                      state.selectedServiceId = id;
                      const field = document.createElement('textarea');
                      Object.assign(field.dataset,{serviceId:id,serviceItemIndex:'0',serviceItemField:'raw_title',initialValue:'이전 입력'});
                      field.value = '아직 반영하지 않은 입력';
                      refs.detailPane.append(field);
                      const foreign = field.cloneNode();
                      foreign.dataset.serviceId = 'other'; foreign.value = '다른 예배 입력';
                      refs.detailPane.append(foreign);
                      const captured = worshipConflictDraft(id);
                      check(captured.pendingInputs.length === 1 && captured.pendingInputs[0].value === field.value,'pending input capture/scope failed');
                      state.worshipSections = [{id:'old-section',service_id:id},{id:'other-section',service_id:'other'}];
                      state.worshipElements = [{id:'old-item',section_id:'old-section'},{id:'other-item',section_id:'other-section'}];
                      state.dirtyServiceElementIds = new Map([[id,new Set(['old-item'])],['other',new Set(['other-item'])]]);
                      state.dirtyServiceStructureIds = new Set([id,'other']);
                      projectWorshipServiceItemsFromTemplate = (service,items) => items;
                      renderServiceList = () => {};
                      renderCurrentServiceModuleDetail = () => {};
                      let publishes = 0, writes = 0, failStorage = true, waitRead = null;
                      publishPresenterState = () => {publishes++};
                      const realSet = safeStorageSet;
                      safeStorageSet = (...args) => failStorage ? false : realSet(...args);
                      let db = {revision:'1',service:{id,title:'서버',service_date:'2026-09-19',source_ref:{mindexServiceDocument:{sourceText:'서버 최신 원문'}}},sections:[],elements:[]};
                      const memory = new Map();
                      const atomic = createWorshipAtomicClient({journal:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},rpc:async name => {
                        if(name !== 'get_worship_service_v1'){writes++;throw Error('unexpected write')}
                        if(waitRead) await waitRead();
                        return {data:structuredClone(db)};
                      }});
                      worshipAtomicClient = async () => atomic;
                      await atomic.read(id);
                      db.revision = '2';
                      let review = await atomic.inspectConflict(id,worshipConflictDraft(id));
                      try {await reopenWorshipConflict(review);throw Error('storage failure accepted')}
                      catch(e){check(e.message === 'DRAFT_NOT_PRESERVED',e.message)}
                      check(state.services[0] === original && atomic.baseline(id).revision === '1','storage failure altered state');
                      failStorage = false;
                      let release;
                      waitRead = () => new Promise(resolve => {release = resolve});
                      const loading = reopenWorshipConflict(review);
                      await new Promise(resolve=>setTimeout(resolve,0));
                      field.value = '읽는 동안 추가 입력';
                      release();
                      try {await loading;throw Error('new input overwritten')}
                      catch(e){check(e.message === 'LOCAL_DRAFT_CHANGED',e.message)}
                      waitRead = null;
                      check(atomic.baseline(id).revision === '1','changed draft adopted revision');
                      state.serviceItems[id][0].raw_title = '새 입력';
                      await openWorshipConflictReview(id);
                      let dialog = document.querySelector('.worship-conflict-dialog');
                      let button = dialog.querySelector('[data-conflict-reopen]');
                      let keep = dialog.querySelector('[data-conflict-keep]');
                      check(dialog.querySelector('[aria-label="미반영 입력"]').value.includes('읽는 동안 추가 입력'),'pending input not shown in comparison');
                      check(dialog.scrollWidth <= dialog.clientWidth + 1,'pending input causes horizontal overflow');
                      check(!button.disabled && !keep.disabled,'conflict choices unavailable');
                      const keepClosed = new Promise(resolve=>dialog.addEventListener('close',resolve,{once:true}));
                      keep.click(); await keepClosed;
                      const serverArchive = latestWorshipRecoverySnapshotForService(id);
                      check(state.services[0] === original && state.serviceItems[id][0].raw_title === '새 입력','keep choice changed current draft');
                      check(serverArchive.reason === 'conflict-server-latest' && serverArchive.serviceDocument.sourceText === '서버 최신 원문','keep choice did not archive server snapshot');
                      await openWorshipConflictReview(id);
                      dialog = document.querySelector('.worship-conflict-dialog');
                      button = dialog.querySelector('[data-conflict-reopen]');
                      const closed = new Promise(resolve=>dialog.addEventListener('close',resolve,{once:true}));
                      button.click(); await closed;
                      check(atomic.baseline(id).revision === '2','review not adopted');
                      check(state.services[0].title === '서버' && state.serviceItems[id].length === 0,'latest data not installed');
                      check(state.services[1] === other && state.serviceItems.other[0].id === 'other-item','other draft modified');
                      check(state.dirtyServiceElementIds.has('other') && state.dirtyServiceStructureIds.has('other'),'other dirty flags lost');
                      check(state.worshipElements.length === 1 && state.worshipElements[0].id === 'other-item','other rows lost');
                      const archived = latestWorshipRecoverySnapshotForService(id);
                      check(archived.draft.items[0].raw_title === '새 입력' && archived.serviceDocument.sourceText === '보관할 입력','complete draft not archived');
                      check(archived.draft.pendingInputs[0].value === '읽는 동안 추가 입력','pending input not archived');
                      check(renderServiceSourceRecovery({id}).includes('읽는 동안 추가 입력'),'archived pending input not available in recovery UI');
                      check(writes === 0 && publishes === 0,'reopen wrote DB or published output');
                      safeStorageSet = realSet;
                      return 'PASS recovery action archives full draft; quota and in-flight edits block; unrelated drafts and live output untouched';
                    }"""), flush=True)
                    page.close()
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
