"""Actual app create/delete/scheduler calls; no external network or live data."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    fixtures = []
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page()
                    page.route('**/*', lambda route: route.continue_()
                               if urlsplit(route.request.url).netloc == urlsplit(url).netloc else route.abort())
                    page.goto(url+'?output=presenter&mindexSmokeRaw=1', wait_until='domcontentloaded')
                    page.wait_for_function("typeof insertWorshipServicesWithCalendarAssignees==='function'")
                    page.wait_for_function("typeof isSongServiceLabel==='function'")
                    fixtures.append(page.evaluate('''async () => {
                      const check=(ok,msg)=>{if(!ok)throw Error(msg)};
                      window.MINDEX_WORSHIP_ATOMIC_PROTOCOL=1;
                      state.services=[];state.worshipSections=[];state.worshipElements=[];state.serviceItems={};
                      state.serviceTypes=[normalizeWorshipServiceType({id:'sun_1st',display_name:'주일예배 [1부]'})];
                      state.loadedWorshipServiceIds.clear();state.dirtyServiceElementIds.clear();state.dirtyServiceStructureIds.clear();
                      state.dirty.service=false;state.selectedServiceId=null;state.saving=false;
                      loadCalendarData=async()=>{state.calendarLoaded=true};
                      requireClient=()=>true;updateSaveState=()=>{};captureWorshipRecoverySnapshot=()=>{};
                      renderServiceList=()=>{};renderCurrentServiceModuleDetail=()=>{};syncBrowserHistory=()=>{};
                      window.confirm=()=>true;showToast=()=>{};
                      const typed={inputMode:true,contentState:true};
                      let empty=false;
                      calendarAssigneeRowsForNewService=service=>{
                        if(empty)return {sections:[],elements:[]};
                        const item=normalizeServiceItem({id:service.id+':prayer',service_id:service.id,
                          label:'대표기도',assignee:'Fixture person',raw_title:'대표기도',_worshipSectionKey:'prayer',
                          _worshipSectionTitle:'기도',_worshipSlotKey:'prayer.person',
                          memo:serializeServiceItemMemo({elementType:'title_person',inputMode:'title_person'})});
                        const rows=buildWorshipPersistenceRows(service,[item],{},{},{elementTypedStateColumns:typed});
                        sanitizeWorshipPersistenceRows(rows,{elementTypedStateColumns:typed});compactWorshipPersistenceRows(rows);
                        return rows;
                      };
                      const records=new Map(),receipts=new Map(),requests=[];
                      let mode='before',candidates=[];
                      state.client={from:table=>{
                        check(table==='mindex_worship_services','unexpected table');
                        const query={select:()=>query,eq:()=>query,in:()=>query,contains:()=>query,
                          then:resolve=>Promise.resolve({data:candidates.map(id=>({id}))}).then(resolve)};
                        return query;
                      },rpc:async(name,{sid,req})=>{
                        if(name==='get_worship_service_v1')return {data:structuredClone(records.get(sid))};
                        if(mode==='before'||(mode==='batch-fail'&&req.metadataPatch?.title==='Batch failure')) {
                          return {error:{code:'P0001',message:'INJECTED_LIFECYCLE_FAILURE'}};
                        }
                        requests.push({name,req:structuredClone(req)});
                        if(receipts.has(req.requestId))return {data:{...structuredClone(receipts.get(req.requestId)),replayed:true}};
                        let receipt;
                        if(name==='create_worship_service_v1'){
                          check(!records.has(req.serviceId),'duplicate create');
                          const aggregate={revision:'1',service:{id:req.serviceId,service_type_id:req.serviceTypeId,
                            service_date:req.serviceDate,...req.metadataPatch,
                            source_ref:{...req.metadataPatch.source_ref,mindexServiceDocument:req.document}},
                            sections:req.sections.map(x=>({id:x.id,service_id:req.serviceId,...x.patch})),
                            elements:req.elements.map(x=>({id:x.id,section_id:x.sectionId,...x.patch})),slides:[]};
                          records.set(req.serviceId,aggregate);
                          receipt={aggregate:structuredClone(aggregate),committedRevision:'1',replayed:false};
                        }else if(name==='save_worship_service_v1'){
                          const aggregate=records.get(req.serviceId);
                          check(aggregate.revision===req.expectedRevision,'stale leader write');
                          check(!req.elementPatches.length&&!req.sectionPatches.length,'leader changed child rows');
                          Object.assign(aggregate.service,req.metadataPatch);
                          aggregate.service.source_ref.mindexServiceDocument=req.document;
                          aggregate.revision=String(Number(aggregate.revision)+1);
                          receipt={aggregate:structuredClone(aggregate),committedRevision:aggregate.revision,replayed:false};
                        }else if(name==='delete_worship_service_v1'){
                          check(records.get(req.serviceId)?.revision===req.expectedRevision,'stale delete');
                          records.delete(req.serviceId);receipt={aggregate:null,deleted:true,currentRevision:'2',committedRevision:'2',replayed:false};
                        }else throw Error('Unexpected lifecycle RPC');
                        receipts.set(req.requestId,structuredClone(receipt));
                        if(mode==='lost'){mode='ok';throw Error('Response lost')}
                        return {data:receipt};
                      }};
                      const payload=(title,date='2026-10-18')=>({id:crypto.randomUUID(),service_type_id:'sun_1st',service_date:date,
                        title,status:'draft',praise_leader:'',source_ref:{created_from:'mindex_auto_schedule',auto_generated:true},notes:''});
                      try{await insertWorshipServicesWithCalendarAssignees([payload('Create')]);throw Error('failure accepted')}
                      catch(e){check(e.message==='INJECTED_LIFECYCLE_FAILURE',e.message)};
                      check(!records.size&&!state.worshipElements.length,'failed create changed data');
                      mode='lost';
                      try{await insertWorshipServicesWithCalendarAssignees([payload('Create')]);throw Error('loss accepted')}
                      catch(e){check(e.message==='Response lost',e.message)};
                      check(records.size===1&&!state.worshipElements.length,'uncertain create acknowledged');
                      const [created]=await insertWorshipServicesWithCalendarAssignees([payload('Create')]);
                      check(records.size===1&&state.worshipElements.length===1,'retry duplicated or lost creation');
                      check(JSON.stringify(requests[0])===JSON.stringify(requests[1]),'create retry changed request');
                      state.services=[normalizeWorshipService(created)];
                      mode='before';await deleteService(created.id);
                      check(state.services.length===1&&records.size===1&&state.worshipElements.length===1,'failed delete changed state');
                      mode='lost';await deleteService(created.id);
                      check(state.services.length===1&&!records.size,'lost delete response acknowledged');
                      await deleteService(created.id);
                      check(!state.services.length&&!state.worshipElements.length,'delete retry failed to clear local state');
                      check(JSON.stringify(requests[2])===JSON.stringify(requests[3]),'delete retry changed request');
                      mode='batch-fail';
                      try{await insertWorshipServicesWithCalendarAssignees([payload('Batch success'),payload('Batch failure')]);throw Error('batch failure accepted')}
                      catch(e){check(e.message==='INJECTED_LIFECYCLE_FAILURE',e.message)};
                      check(state.services.some(x=>records.get(x.id)?.service.title==='Batch success'),'confirmed batch member lost');
                      check([...records.values()].some(x=>x.service.title==='Batch success'),'confirmed batch member rolled back');
                      mode='ok';empty=true;
                      const [unassigned]=await insertWorshipServicesWithCalendarAssignees([payload('','2026-10-25')]);
                      empty=false;
                      const [assigned]=await insertWorshipServicesWithCalendarAssignees([payload('Assigned','2026-10-25')]);
                      state.services.push(normalizeWorshipService(unassigned),normalizeWorshipService(assigned));
                      mode='before';
                      try{await persistWorshipSetlistLeader('worship:'+assigned.id,'Leader','');throw Error('leader failure accepted')}
                      catch(e){check(e.message==='INJECTED_LIFECYCLE_FAILURE',e.message)};
                      check(records.get(assigned.id).service.praise_leader==='','failed leader save changed data');
                      mode='ok';await persistWorshipSetlistLeader('worship:'+assigned.id,'Leader','');
                      check(records.get(assigned.id).service.praise_leader==='Leader','leader save missing');
                      try{await persistWorshipSetlistLeader('worship:'+assigned.id,'Stale','');throw Error('leader conflict accepted')}
                      catch(e){check(e.message!=='leader conflict accepted',e.message)};
                      candidates=[unassigned.id,assigned.id];
                      upcomingSundayDate=()=> '2026-10-25';calendarSkippedServiceTypesForDate=()=>['sunday-first'];isAllGenerationsWorshipDate=()=>false;
                      const removed=await purgeAutoGeneratedUnavailableSundayServices();
                      check(removed===1&&!records.has(unassigned.id)&&records.has(assigned.id),'purge failed to preserve assigned content');
                      return {requests};
                    }'''))
                    print(f'PASS {engine}: actual creation/deletion retries, batch failure preservation, protected automatic cleanup')
                finally:
                    page.unroute_all(behavior='ignoreErrors')
                    browser.close()
    finally:
        server.shutdown()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(fixtures, ensure_ascii=False))


if __name__ == '__main__':
    main()
