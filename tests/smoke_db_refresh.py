"""DB refresh uses read-only fixtures, never the operational database."""
from smoke_app import APP_DIR, launch_chromium, start_local_app_server, sync_playwright


def run(browser, url):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.route("**/*supabase*/**", lambda route: route.abort())
    page = context.new_page()
    try:
        page.goto(url + "?output=presenter", wait_until="domcontentloaded")
        page.wait_for_function("typeof attachRelationalSongVersionRows === 'function'")
        page.wait_for_function("!document.getElementById('refreshDbBtn')")
        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<button id=refreshDbBtn>Refresh</button>')")
        page.add_script_tag(path=str(APP_DIR / "mindex.db-refresh.js"))
        print(page.evaluate("""async () => {
          const check = (ok, msg) => { if (!ok) throw Error(msg); };
          const refreshButton = document.getElementById('refreshDbBtn');
          const oldId='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
          const newId='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
          const version='cccccccc-cccc-4ccc-8ccc-cccccccccccc';
          const serviceId='dddddddd-dddd-4ddd-8ddd-dddddddddddd';
          const sectionId='eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
          const elementId='ffffffff-ffff-4fff-8fff-ffffffffffff';
          const tables = {
            mindex_songs:[{id:oldId,title:'주의 이름 송축하리',praise_types:['ccm']}, {id:newId,title:'예수님 찬양',praise_types:['ccm']}],
            mindex_song_versions:[{id:version,source_song_id:newId,canonical_song_id:newId,version_order:1,version_label:'기본'}],
            mindex_version_units:[{id:'unit',version_id:version,unit_kind:'verse',unit_label:'Verse 1',text:'보존된 가사',unit_order:1}],
            mindex_song_relations:[],
            mindex_worship_services:[{id:serviceId,title:'수요예배',service_date:'2026-09-16',source_ref:{marker:'fresh'},service_type_id:'type'}],
            mindex_worship_sections:[{id:sectionId,service_id:serviceId,title:'찬양',section_key:'praise',sort_order:1}],
            mindex_worship_elements:[{id:elementId,section_id:sectionId,element_type:'praise',song_id:newId,song_version_id:version,source_ref:{label:'찬양 2',slotKey:'praise.song.2'},config:{},sort_order:1}],
            mindex_worship_presenter_slides:[],
          };
          let reads=0, renders=0, fail='', gate=null, entered=null, live=false;
          fetchSupabasePaged = async (table, select, build) => {
            reads++;
            if (entered) { const callback=entered; entered=null; callback(); }
            if (gate) await gate;
            if (table===fail) throw Error('injected read failure');
            let rows=structuredClone(tables[table] || []);
            const q={in:(field,values)=>{rows=rows.filter(r=>values.includes(r[field]));return q;},eq:()=>q,order:()=>q,gte:()=>q};
            if (build) build(q);
            return rows;
          };
          state.client={}; requireClient=()=>true; isPresenterOutputWindowOpen=()=>live;
          render=()=>{renders++;}; persistUiState=()=>{}; showToast=()=>{};
          worshipElementListSelect=async()=>'*';
          // Refresh must not call output or existing destructive loaders.
          refreshPresenterForService=()=>{throw Error('output refresh forbidden');};
          loadSongs=()=>{throw Error('legacy song loader forbidden');};
          loadServiceData=()=>{throw Error('legacy service loader forbidden');};
          state.loading=false; state.saving=false; state.presenter.outputPendingAt=0;
          state.presenterPreparationDrafts={}; state.presenterPreparationApplyingServiceIds.clear();
          Object.keys(state.dirty).forEach(key=>state.dirty[key]=false);
          const reset=()=>{
            state.module='praise'; state.selectedSongId=oldId; state.selectedVersionId=version;
            state.songs=[normalizeServerSong({id:oldId,title:'Old',praise_types:['ccm']})];
            state.forms=[]; state.selectedServiceId=null; state.presenter.viewServiceId='';
          };
          reset();
          state.dirty.forms=true;
          check(await MINDEX_DB_REFRESH.refresh()===false && reads===0,'dirty refresh fetched');
          state.dirty.forms=false;
          const editor=document.createElement('div'); editor.dataset.inputStatus='modified'; document.body.append(editor);
          check(await MINDEX_DB_REFRESH.refresh()===false && reads===0,'deferred draft lost'); editor.remove();
          live=true; check(await MINDEX_DB_REFRESH.refresh()===false && reads===0,'live refresh fetched'); live=false;
          const prior=state.songs;
          fail='mindex_version_units';
          check(await MINDEX_DB_REFRESH.refresh()===false && state.songs===prior && renders===0,'partial failure changed state'); fail='';
          const hold=()=>{let release; gate=new Promise(r=>release=r); let start; const started=new Promise(r=>start=r); entered=start; return {started,release:()=>{gate=null;release();}};};
          let h=hold(), pending=MINDEX_DB_REFRESH.refresh(); await h.started;
          check(await MINDEX_DB_REFRESH.refresh()===false,'duplicate refresh admitted');
          const input=document.createElement('input'); document.body.append(input); input.value='new draft'; input.dispatchEvent(new Event('input',{bubbles:true}));
          h.release(); check(await pending===false && state.songs===prior,'typing during refresh lost'); input.remove();
          h=hold(); pending=MINDEX_DB_REFRESH.refresh(); await h.started; live=true; h.release();
          check(await pending===false && state.songs===prior,'live transition changed state'); live=false;
          h=hold(); pending=MINDEX_DB_REFRESH.refresh(); await h.started; state.module='calendar'; h.release();
          check(await pending===false && state.songs===prior,'navigation published stale snapshot'); state.module='praise';
          const presenter=JSON.stringify(state.presenter);
          check(await MINDEX_DB_REFRESH.refresh()===true,'successful refresh failed');
          check(state.selectedSongId===newId && state.selectedVersionId===version,'split version selection not retained');
          check(state.forms.length===1 && state.forms[0].lyrics==='보존된 가사','fresh lyrics missing');
          check(JSON.stringify(state.presenter)===presenter,'presenter mutated');
          check(renders===1,'multiple renders');
          state.module='service'; state.selectedServiceId=serviceId;
          state.services=[normalizeWorshipService(tables.mindex_worship_services[0])];
          state.serviceTypes=[];
          state.worshipSections=structuredClone(tables.mindex_worship_sections);
          state.worshipElements=[{...tables.mindex_worship_elements[0],song_id:oldId}];
          state.serviceItems={[serviceId]:[]};
          check(await MINDEX_DB_REFRESH.refresh()===true,'service refresh failed');
          check(state.worshipElements[0].song_id===newId,'service link stale');
          check(state.services[0]._worshipSourceRef.marker==='fresh','source document stale');
          check(state.songs.find(s=>s.id===oldId).versions.every(v=>v.id!==version),'old linked song retained moved version');
          check(JSON.stringify(state.presenter)===presenter,'service refresh published output');
          check(!refreshButton.disabled,'button not released');
          return 'PASS split-song refresh, service links, drafts, failure atomicity, races, duplicate clicks and output isolation';
        }"""), flush=True)
    finally:
        context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chromium", "webkit"):
                browser = launch_chromium(p) if engine == "chromium" else p.webkit.launch()
                try:
                    print(engine, flush=True)
                    run(browser, url)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
