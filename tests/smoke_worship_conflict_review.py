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
                      await openWorshipConflictReview(service.id);
                      check(reads === 1, 'duplicate conflict review started another read');
                      items[0].raw_title = '저장 이후 새 입력';
                      release(); await opening;
                      check(items[0].raw_title === '저장 이후 새 입력', 'review overwrote active draft');
                      dialog.querySelector('[data-conflict-export]').click();
                      check(exported[0].draft.items[0].raw_title === '입력 중', 'export not frozen at review start');
                      check(dialog.querySelector('[aria-label="내 입력"]').value.includes('<script>'), 'text not preserved');
                      check(!dialog.querySelector('script'), 'user text interpreted as HTML');
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
                      if (!dialog.textContent.includes('조회 실패')) throw Error('missing failure state');
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
                    page.close()
                browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
