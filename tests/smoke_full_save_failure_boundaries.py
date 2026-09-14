"""Characterize full-save partial commits; no production traffic or atomicity claim."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url):
    context = browser.new_context()
    context.route('**/*supabase*/**', lambda route: route.abort())
    try:
        page = context.new_page()
        page.goto(url + '?output=presenter', wait_until='domcontentloaded')
        page.wait_for_function("typeof saveWorshipServiceInstance==='function'")
        return page.evaluate('''async () => {
          const check=(ok,message)=>{if(!ok)throw Error(message)};
          const clone=value=>JSON.parse(JSON.stringify(value));
          const sid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
          const stages=['mindex_worship_services','mindex_worship_sections','mindex_worship_elements'];
          const results=[];
          refs.detailPane=document.createElement('section');document.body.append(refs.detailPane);
          requireClient=()=>true;
          ensureWorshipServiceRowsLoadedForPersistence=async()=>{};
          worshipElementTypedStateColumns=async()=>({inputMode:true,contentState:true});
          updateSaveState=()=>{};renderServiceList=()=>{};render=()=>{};
          refreshPresenterForService=()=>{};
          syncSharedSundayContentAfterSave=async()=>{};
          let recovery;
          captureWorshipRecoverySnapshot=(service)=>{recovery=clone(getServiceItems(service.id))};
          captureCleanFingerprint=()=>{};

          for(const failedStage of stages) for(const timing of ['before-commit','lost-response']) {
            const baseline={fixture:'previous committed baseline'};
            const service={id:sid,type_id:'failure-fixture',date:'2026-09-14',_worshipSourceRef:baseline};
            const inputs=[0,1].map(i=>normalizeServiceItem({service_id:sid,label:'찬양 '+(i+1),raw_title:'Original '+i,
              memo:serializeServiceItemMemo({elementType:'praise',inputMode:'manual_praise',outputMode:'lyrics',slides:['Original line '+i]}),
              _worshipSectionKey:'praise',_worshipSectionTitle:'Praise',
              _worshipElementTemplateModified:true,_worshipTemplatePlaceholder:false},i));
            const rows=buildWorshipPersistenceRows(service,inputs,{}, {},{elementTypedStateColumns:{inputMode:true,contentState:true}});
            state.services=[service];state.worshipSections=clone(rows.sections);state.worshipElements=clone(rows.elements);
            state.serviceItems={[sid]:groupWorshipElements(rows.sections,rows.elements)[sid]};
            state.selectedServiceId=sid;state.module='presenter';state.saving=false;activeServiceSavePromise=null;
            state.dirtyServiceElementIds=new Map();state.dirtyServiceStructureIds=new Set();state.dirtyServiceTypeIds=new Set();
            state.templateElementSuppressions=new Map();
            for(const item of getServiceItems(sid)){item.raw_title='Changed '+item.raw_title;markServiceElementDirty(sid,item)}
            state.dirty.service=true;
            const draft=clone(getServiceItems(sid));
            const dirtyIds=[...state.dirtyServiceElementIds.get(sid)];
            const localRows=JSON.stringify([state.worshipSections,state.worshipElements]);
            const db={mindex_worship_services:[{id:sid,source_ref:clone(baseline)}],
              mindex_worship_sections:clone(rows.sections),mindex_worship_elements:clone(rows.elements)};
            const before=clone(db);const attempts=[],commits=[];let inject=true;
            const write=async(table,value)=>{
              attempts.push(table);
              if(inject&&table===failedStage&&timing==='before-commit')return {error:new Error('injected '+timing)};
              const incoming=Array.isArray(value)?value:[{id:sid,...value}];
              for(const row of incoming){const i=db[table].findIndex(old=>old.id===row.id);if(i<0)db[table].push(clone(row));else db[table][i]={...db[table][i],...clone(row)}}
              commits.push(table);
              if(inject&&table===failedStage&&timing==='lost-response')throw new Error('injected '+timing);
              return {error:null,count:1};
            };
            state.client={from:table=>({
              update:(value,options)=>{check(options.count==='exact','missing receipt request');return {eq:(key,id)=>{check(key==='id'&&id===sid,'unexpected predicate');return write(table,value)}}},
              upsert:value=>write(table,value),
              delete:()=>{throw Error('unexpected structural delete in this fixture')},
            })};
            let saved=false,saveError='';
            try { saved=await saveService(sid,{silent:true,renderAfterSave:false,throwOnError:true}); }
            catch(error) { saveError=error.message; }
            check(saved===false,'failed/uncertain request acknowledged');
            check(JSON.stringify(attempts)===JSON.stringify(stages.slice(0,stages.indexOf(failedStage)+1)),'unexpected writes '+JSON.stringify(attempts)+' at '+failedStage+': '+saveError);
            check(saveError==='injected '+timing,'fixture failed outside the injected boundary: '+saveError);
            const expectedCommits=stages.slice(0,stages.indexOf(failedStage)+(timing==='lost-response'?1:0));
            check(JSON.stringify(commits)===JSON.stringify(expectedCommits),'unexpected commit boundary');
            for(const table of stages) if(!expectedCommits.includes(table))check(JSON.stringify(db[table])===JSON.stringify(before[table]),'untouched table changed');
            if(expectedCommits.length)check(JSON.stringify(db.mindex_worship_services)!==JSON.stringify(before.mindex_worship_services),'fixture did not retain earlier document commit');
            check(service._worshipSourceRef===baseline,'failed save advanced local baseline');
            check(JSON.stringify([state.worshipSections,state.worshipElements])===localRows,'failed save replaced local persisted rows');
            check(JSON.stringify(getServiceItems(sid))===JSON.stringify(draft),'failed save changed draft');
            check(state.dirty.service&&dirtyIds.every(id=>state.dirtyServiceElementIds.get(sid)?.has(id)),'failed save cleared dirty IDs');
            check(!state.saving&&!activeServiceSavePromise,'failed save left queue locked');
            check(JSON.stringify(recovery)===JSON.stringify(draft),'recovery capture missed draft');

            inject=false;attempts.length=0;
            check(await saveService(sid,{silent:true,renderAfterSave:false})===true,'explicit retry failed');
            check(JSON.stringify(attempts)===JSON.stringify(stages),'retry skipped a write stage');
            check(!state.dirty.service&&!state.dirtyServiceElementIds.has(sid),'confirmed retry stayed dirty');
            check(JSON.stringify(service._worshipSourceRef)===JSON.stringify(db.mindex_worship_services[0].source_ref),'retry baseline differs from persisted document');
            check(db.mindex_worship_elements.length===rows.elements.length,'retry duplicated stable IDs');
            check(db.mindex_worship_elements.every(row=>row.title.startsWith('Changed ')),'retry omitted draft content');
            results.push('PASS '+failedStage+' / '+timing+': draft retained, partial commits characterized, explicit retry confirmed');
          }
          return results;
        }''')
    finally:
        context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    for result in run(browser, url):
                        print(engine, result)
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
