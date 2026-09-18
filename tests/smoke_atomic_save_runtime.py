"""Exercise the actual app save functions, offline, and export their RPC requests."""
import json
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    origin = urlsplit(url).netloc
    fixtures = []
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page()
                    page.route('**/*', lambda route: route.continue_()
                               if urlsplit(route.request.url).netloc == origin else route.abort())
                    page.goto(url + '?output=presenter&mindexSmokeRaw=1', wait_until='domcontentloaded')
                    page.wait_for_function("typeof saveWorshipServiceInstance==='function'")
                    fixtures.append(page.evaluate('''async () => {
                      const check=(ok,msg)=>{if(!ok)throw Error(msg)};
                      window.MINDEX_WORSHIP_ATOMIC_PROTOCOL=1;
                      const sid=crypto.randomUUID();
                      const service={id:sid,type_id:'fixture',date:'2026-10-12',title:'Fixture',_worshipSourceRef:{}};
                      state.services=[service]; state.selectedServiceId=sid;state.songs=[];
                      state.dirty.service=false;state.dirtyServiceElementIds.clear();state.dirtyServiceStructureIds.clear();
                      state.loadedWorshipServiceIds=new Set([sid]);state.templateElementSuppressions.clear();
                      state.serviceAliasSupported=true;
                      const items=['First','Second'].map((title,i)=>normalizeServiceItem({
                        id:crypto.randomUUID(),service_id:sid,label:'Test '+i,raw_title:title,
                        _worshipSectionKey:'test',_worshipSectionTitle:'Test',
                        _worshipSlotKey:'test.'+i,_worshipElementTemplateModified:true,
                        memo:serializeServiceItemMemo({elementType:'title_person',inputMode:'title_person'})},i));
                      const typed={inputMode:true,contentState:true};
                      worshipElementTypedStateColumns=async()=>typed;
                      refreshPresenterForService=()=>{};
                      const rows=buildWorshipPersistenceRows(service,items,{}, {},{elementTypedStateColumns:typed});
                      sanitizeWorshipPersistenceRows(rows,{elementTypedStateColumns:typed});compactWorshipPersistenceRows(rows);
                      state.worshipSections=structuredClone(rows.sections);state.worshipElements=structuredClone(rows.elements);
                      state.serviceItems={[sid]:groupWorshipElements(rows.sections,rows.elements)[sid]};
                      const initial={serviceId:sid,serviceTypeId:'fixture',serviceDate:service.date,
                        metadataPatch:{title:'Fixture'},
                        sections:rows.sections.map(({id,service_id,created_at,updated_at,...patch})=>({id,patch})),
                        elements:rows.elements.map(({id,section_id,created_at,updated_at,...patch})=>({id,sectionId:section_id,patch})),
                        document:buildServiceDocumentSnapshot(service,state.serviceItems[sid])};
                      let db={revision:'1',service:{id:sid,service_type_id:'fixture',service_date:service.date,title:'Fixture',source_ref:{mindexServiceDocument:initial.document}},
                        ...structuredClone(rows),slides:[]};
                      service._worshipSourceRef=structuredClone(db.service.source_ref);
                      const writes=[];let failure=false,duringSave=null;
                      state.client={from(){throw Error('Legacy table write attempted')},rpc:async(name,{sid:readId,req})=>{
                        if(name==='get_worship_service_v1')return {data:structuredClone(db)};
                        check(name==='save_worship_service_v1','wrong RPC');
                        if(failure)return {error:{code:'P0001',message:'INJECTED_FAILURE'}};
                        check(req.expectedRevision===db.revision,'stale token');writes.push(structuredClone(req));
                        for(const [key,patches] of [['sections',req.sectionPatches],['elements',req.elementPatches]]) {
                          for(const change of patches){const row=db[key].find(x=>x.id===change.id);Object.assign(row,change.patch);
                            for(const [field,keys] of Object.entries(change.removeKeys||{}))for(const key of keys)delete row[field][key];}
                        }
                        db.sections.push(...req.newSections.map(x=>({id:x.id,service_id:sid,...x.patch})));
                        db.elements.push(...req.newElements.map(x=>({id:x.id,section_id:x.sectionId,...x.patch})));
                        for(const move of req.elementMoves)db.elements.find(x=>x.id===move.id).section_id=move.sectionId;
                        db.elements=db.elements.filter(x=>!req.deleteElementIds.includes(x.id));
                        db.sections=db.sections.filter(x=>!req.deleteSectionIds.includes(x.id));
                        Object.assign(db.service,req.metadataPatch);
                        db.service.source_ref={...db.service.source_ref,mindexServiceDocument:req.document};
                        db.revision=String(Number(db.revision)+1);
                        if(duringSave){const callback=duringSave;duringSave=null;callback();}
                        return {data:{aggregate:structuredClone(db),committedRevision:db.revision,replayed:false}};
                      }};
                      const client=await worshipAtomicClient();await client.read(sid);
                      const [first,second]=state.serviceItems[sid];
                      first.raw_title='Saved first';second.raw_title='Sibling UNSAVED';
                      const saved=await saveWorshipServiceElementPatch(service,first.id);
                      check(saved.unchanged,'element receipt not acknowledged');
                      check(writes[0].elementPatches.length===1,'sibling included in element patch');
                      check(!JSON.stringify(writes[0].document).includes('Sibling UNSAVED'),'sibling leaked into document');
                      check(state.serviceItems[sid].find(x=>x.id===second.id).raw_title==='Sibling UNSAVED','sibling draft lost');
                      const before=JSON.stringify({sections:state.worshipSections,elements:state.worshipElements,source:service._worshipSourceRef});
                      failure=true;
                      try {await saveWorshipServiceInstance(service);throw Error('failure accepted')}catch(e){check(e.message==='INJECTED_FAILURE',e.message)}
                      check(before===JSON.stringify({sections:state.worshipSections,elements:state.worshipElements,source:service._worshipSourceRef}),'failed save changed baseline');
                      check(!client.pending(sid),'rolled-back request still pending');failure=false;
                      duringSave=()=>{state.serviceItems[sid].find(x=>x.id===second.id).raw_title='Newer local edit'};
                      const full=await saveWorshipServiceInstance(service);
                      check(!full.unchanged,'newer draft marked clean');
                      check(JSON.stringify(writes[1].document).includes('Sibling UNSAVED'),'full save omitted captured draft');
                      check(!JSON.stringify(writes[1].document).includes('Newer local edit'),'inflight edit leaked');
                      check(state.serviceItems[sid].find(x=>x.id===second.id).raw_title==='Newer local edit','inflight edit lost');
                      // A background read while the user edits must not advance the write baseline.
                      const oldRevision=client.baseline(sid).revision;db.revision='99';
                      state.dirtyServiceElementIds.set(sid,new Set([second.id]));
                      await fetchWorshipRowsForServiceIds([sid]);
                      check(client.baseline(sid).revision===oldRevision,'background read rebased dirty draft');
                      return {initial,writes};
                    }'''))
                    print(f'PASS {engine}: actual full/element RPC paths, rollback, sibling/inflight draft isolation, no legacy fallback')
                    fixtures.append(page.evaluate('''async () => {
                      const check=(ok,msg)=>{if(!ok)throw Error(msg)};
                      const source={id:crypto.randomUUID(),date:'2026-10-12',type_id:'sunday-second'};
                      const target={id:crypto.randomUUID(),date:source.date,type_id:'sunday-main'};
                      const make=(service,title)=>normalizeServiceItem({id:crypto.randomUUID(),service_id:service.id,
                        label:'설교 제목',raw_title:title,assignee:'담당',_worshipSectionKey:'sermon',_worshipSectionTitle:'설교',
                        _worshipSlotKey:'sermon.title',memo:serializeServiceItemMemo({elementType:'title_person',inputMode:'text'})});
                      const previous=make(source,'Original'),edited={...previous,raw_title:'Edited'};
                      state.services=[source,target];state.selectedServiceId=source.id;state.dirty.service=false;
                      state.dirtyServiceElementIds.clear();state.dirtyServiceStructureIds.clear();state.loadedWorshipServiceIds.clear();
                      state.worshipSections=[];state.worshipElements=[];state.serviceItems={[source.id]:[edited]};
                      loadSongsForIds=async()=>{};
                      const typed={inputMode:true,contentState:true};
                      const rows=buildWorshipPersistenceRows(target,[make(target,'Original')],{},{},{elementTypedStateColumns:typed});
                      sanitizeWorshipPersistenceRows(rows,{elementTypedStateColumns:typed});compactWorshipPersistenceRows(rows);
                      const items=groupWorshipElements(rows.sections,rows.elements)[target.id];
                      const initial={serviceId:target.id,serviceTypeId:'sun_3rd',serviceDate:source.date,metadataPatch:{title:'Sync fixture'},
                        sections:rows.sections.map(({id,service_id,created_at,updated_at,...patch})=>({id,patch})),
                        elements:rows.elements.map(({id,section_id,created_at,updated_at,...patch})=>({id,sectionId:section_id,patch})),
                        document:buildServiceDocumentSnapshot(target,items)};
                      let db={revision:'1',service:{id:target.id,service_type_id:'sun_3rd',service_date:source.date,
                        source_ref:{mindexServiceDocument:initial.document}},...structuredClone(rows),slides:[]};
                      const writes=[];let fail=true;
                      state.client={from(){throw Error('Legacy sync write attempted')},rpc:async(name,{req})=>{
                        if(name==='get_worship_service_v1')return {data:structuredClone(db)};
                        check(name==='save_worship_service_v1','wrong sync RPC');
                        if(fail)return {error:{code:'P0001',message:'INJECTED_SYNC_FAILURE'}};
                        check(req.elementPatches.length===1 && req.sectionPatches.length===0,'sync scope changed');
                        writes.push(structuredClone(req));
                        Object.assign(db.elements[0],req.elementPatches[0].patch);
                        db.service.source_ref.mindexServiceDocument=req.document;db.revision='2';
                        return {data:{aggregate:structuredClone(db),committedRevision:'2',replayed:false}};
                      }};
                      const job={sourceServiceId:source.id,targetId:target.id,key:'sermon-title',previous,item:edited};
                      const before=JSON.stringify(db);
                      try{await persistSundayEditSync(job,{elementTypedStateColumns:typed});throw Error('failure accepted')}
                      catch(e){check(e.message==='INJECTED_SYNC_FAILURE',e.message)};
                      check(JSON.stringify(db)===before,'failed sync partially persisted');
                      check(state.worshipElements.length===0,'failed sync changed local baseline');
                      fail=false;await persistSundayEditSync(job,{elementTypedStateColumns:typed});
                      check(writes.length===1,'sync should commit once');
                      check(db.elements[0].title==='Edited','sync element missing');
                      check(db.service.source_ref.mindexServiceDocument.sourceText.includes('Edited'),'sync document stale');
                      check(state.serviceItems[target.id].some(x=>x.raw_title==='Edited'),'sync local receipt missing');
                      return {initial,writes};
                    }'''))
                    print(f'PASS {engine}: linked-service edit commits target/document together without legacy writes')
                except Exception:
                    traceback.print_exc()
                    raise
                finally:
                    page.unroute_all(behavior='ignoreErrors')
                    browser.close()
    finally:
        server.shutdown()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(fixtures, ensure_ascii=False))


if __name__ == '__main__':
    main()
