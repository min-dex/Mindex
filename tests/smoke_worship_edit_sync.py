from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page()
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url+'?output=presenter', wait_until='domcontentloaded')
                page.wait_for_function("typeof persistSundayEditSync === 'function'")
                print(engine, page.evaluate('''async () => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const clone=x=>JSON.parse(JSON.stringify(x));
                  const sid='11111111-1111-4111-8111-111111111111',tid='22222222-2222-4222-8222-222222222222';
                  const source={id:sid,date:'2026-09-06',type_id:'sunday-second'};
                  const target={id:tid,date:source.date,type_id:'sunday-main'};
                  const make=(service,title)=>normalizeServiceItem({id:service.id,service_id:service.id,label:'설교 제목',raw_title:title,
                    assignee:'담당',_worshipSectionKey:'sermon',_worshipSectionTitle:'설교',
                    memo:serializeServiceItemMemo({elementType:'title_person',inputMode:'text'})});
                  const previous=make(source,'Original'),edited=make(source,'Edited');
                  edited._worshipSharedContentDirty=true;
                  const originalPersist=persistSundayEditSync;
                  let jobs=[];
                  persistSundayEditSync=async job=>{jobs.push(clone(job))};
                  state.services=[source,target,{id:'third-date',date:'2026-09-13',type_id:'sunday-main'}];
                  pendingSundayEditSync.clear();
                  await syncSharedSundayContentAfterSave(source,[edited],{previousItems:[previous]});
                  check(jobs.length===1&&jobs[0].targetId===tid,'wrong sync scope');
                  await syncSharedSundayContentAfterSave(source,[edited],{previousItems:[edited]});
                  check(jobs.length===1,'unchanged save resynced');
                  const blank=make(target,'');state.serviceItems={[sid]:[edited],[tid]:[blank]};
                  check(serviceItemWithSharedSundayContent(blank,target).raw_title==='','read borrowed content');
                  check(!presenterServiceInputIsStatic(blank),'editor hidden');
                  check(!sundayEditSyncEligible({...blank,label:'봉헌 영상'},target),'video eligible');
                  const praise={...previous,label:'찬양 1',_worshipSectionKey:'praise',memo:serializeServiceItemMemo({elementType:'praise',inputMode:'lyrics_db'})};
                  check(sundaySharedContentTypesForItem(praise,target).length===0,'third praise linked');
                  check(applySundayEditSync(edited,previous).raw_title==='Original','apply');
                  check(applySundayEditSync(edited,make(source,'')).raw_title==='','clear unsupported');
                  const manual={...praise,song_id:null,raw_title:'Manual',memo:serializeServiceItemMemo({elementType:'praise',inputMode:'manual_praise',outputMode:'lyrics',slides:['New lyrics']})};
                  const appliedManual=parseServiceItemMemo(applySundayEditSync(praise,manual).memo);
                  check(appliedManual.inputMode==='manual_praise'&&appliedManual.outputMode==='lyrics'&&appliedManual.slides[0]==='New lyrics','manual lyric mode lost');
                  const raw='Memo before\\n[설교]\\n설교 제목: Original\\n  담당: 담당\\n\\n[별도]\\n사용자 항목: Keep exactly\\n  알수없는정보: keep';
                  const replaced=sundayEditSyncSourceText({sourceText:raw},previous,edited,source);
                  check(replaced.startsWith('Memo before\\n'),'source preamble lost');
                  check(replaced.endsWith('[별도]\\n사용자 항목: Keep exactly\\n  알수없는정보: keep'),'unrelated source text changed');
                  check(replaced.includes('설교 제목: Edited'),'source block not changed');
                  check(!Object.hasOwn(parseServiceSourceText(raw)[0],'startLine'),'parser default contract changed');
                  persistSundayEditSync=originalPersist;
                  const typed={inputMode:true,contentState:true};
                  let db,serviceRow,writes,mode;
                  const reset=()=>{
                    const rows=buildWorshipPersistenceRows(target,[make(target,'Original')],{}, {},{elementTypedStateColumns:typed});
                    db=clone(rows);writes=[];mode='ok';
                    serviceRow={id:tid,service_type_id:'sun_3rd',service_date:source.date,source_ref:{}};
                    state.services=[source,target];state.selectedServiceId=sid;state.dirty.service=false;
                    state.dirtyServiceElementIds=new Map();state.dirtyServiceStructureIds=new Set();
                    state.worshipSections=[];state.worshipElements=[];state.serviceItems={[sid]:[edited]};
                    state.loadedWorshipServiceIds=new Set();
                  };
                  fetchWorshipRowsForServiceIds=async()=>clone(db);
                  refreshPresenterForService=()=>{};
                  state.client={from:table=>({
                    select:()=>({eq:()=>({single:async()=>({data:clone(serviceRow),error:null})})}),
                    update:(payload,options)=>{
                      const filters={};
                      const q={eq:(k,v)=>{filters[k]=v;return q},then:resolve=>{
                        check(options.count==='exact','missing receipt request');
                        check(filters.id,'missing row id');
                        check(table==='mindex_worship_services'?filters.source_ref:filters.updated_at,'missing optimistic lock');
                        writes.push({table,payload:clone(payload),filters});
                        const count=mode==='conflict'||(mode==='document-conflict'&&table==='mindex_worship_services')?0:1;
                        if(count===1&&table==='mindex_worship_elements')db.elements=db.elements.map(r=>r.id===filters.id?{...r,...payload}:r);
                        if(count===1&&table==='mindex_worship_services')serviceRow={...serviceRow,...payload};
                        return Promise.resolve({error:null,count}).then(resolve);
                      }};return q;
                    }
                  })};
                  const job={sourceServiceId:sid,targetId:tid,key:'sermon-title',previous,item:edited};
                  reset();await persistSundayEditSync(job,{elementTypedStateColumns:typed});
                  check(writes.length===1&&db.elements[0].title==='Edited','target not saved');
                  check(!Object.hasOwn(writes[0].payload,'sort_order')&&!Object.hasOwn(writes[0].payload,'section_id'),'structure overwritten');
                  reset();db.elements[0].title='Independent';
                  let failed=false;try{await persistSundayEditSync(job,{elementTypedStateColumns:typed})}catch{failed=true}
                  check(failed&&writes.length===0,'independent value overwritten');
                  reset();state.dirtyServiceElementIds.set(tid,new Set(['draft']));failed=false;
                  try{await persistSundayEditSync(job,{elementTypedStateColumns:typed})}catch{failed=true}
                  check(failed&&writes.length===0,'local draft overwritten');
                  reset();mode='conflict';failed=false;
                  try{await persistSundayEditSync(job,{elementTypedStateColumns:typed})}catch{failed=true}
                  check(failed&&db.elements[0].title==='Original','zero-row receipt accepted');
                  reset();serviceRow.source_ref={mindexServiceDocument:{sourceText:'설교 제목: Original',slides:[
                    {id:'custom',elementId:'other',type:'image',imageSrc:'keep.png',title:'Keep'},
                    {id:'old',elementId:db.elements[0].id,type:'title-assignee',text:'Original'}]}};
                  await persistSundayEditSync(job,{elementTypedStateColumns:typed});
                  const doc=serviceRow.source_ref.mindexServiceDocument;
                  check(doc.sourceText.includes('Edited'),'source text stale');
                  check(doc.slides.some(x=>x.id==='custom'&&x.imageSrc==='keep.png'),'unrelated snapshot lost');
                  check(!doc.slides.some(x=>x.elementId===db.elements[0].id&&x.text==='Original'),'changed snapshot stale');
                  reset();serviceRow.source_ref={mindexServiceDocument:{sourceText:'Original',slides:[]}};mode='document-conflict';failed=false;
                  try{await persistSundayEditSync(job,{elementTypedStateColumns:typed})}catch{failed=true}
                  check(failed&&db.elements[0].title==='Edited','partial save not reported');
                  mode='ok';await persistSundayEditSync(job,{elementTypedStateColumns:typed});
                  check(serviceRow.source_ref.mindexServiceDocument.sourceText.includes('Edited'),'partial retry did not repair source');
                  reset();db.elements=[];await persistSundayEditSync(job,{elementTypedStateColumns:typed});
                  check(writes.length===0,'missing item created');
                  reset();db.elements[0].source_ref.label='봉헌 영상';db.elements[0].element_type='video';
                  await persistSundayEditSync(job,{elementTypedStateColumns:typed});check(writes.length===0,'replacement overwritten');
                  reset();
                  const citation=(service)=>normalizeServiceItem({id:service.id,service_id:service.id,label:'인용 구절',
                    raw_title:'요한복음 3:16',_worshipSectionKey:'sermon',_worshipSectionTitle:'설교',_worshipSlotKey:'sermon.citation.1',
                    memo:serializeServiceItemMemo({elementType:'scripture_body',scriptureReferences:['요한복음 3:16']})});
                  const beforeCitation=citation(source),emptyCitation=citation(source);
                  emptyCitation.raw_title='';emptyCitation.memo=serializeServiceItemMemo({elementType:'scripture_body'});
                  db=clone(buildWorshipPersistenceRows(target,[citation(target)],{}, {},{elementTypedStateColumns:typed}));
                  db.elements[0].source_ref.scriptureReferences=['요한복음 3:16'];
                  db.elements[0].source_ref.customNote='keep';
                  await persistSundayEditSync({sourceServiceId:sid,targetId:tid,key:'sermon-citation:1',previous:beforeCitation,item:emptyCitation},{elementTypedStateColumns:typed});
                  const restoredCitation=groupWorshipElements(db.sections,db.elements)[tid][0];
                  check(serviceItemScriptureReferences(restoredCitation).length===0,'linked citation deletion resurrected');
                  check(db.elements[0].source_ref.customNote==='keep','unrelated linked metadata lost');
                  pendingSundayEditSync.clear();persistSundayEditSync=async()=>{throw Error('network')};failed=false;
                  try{await syncSharedSundayContentAfterSave(source,[edited],{previousItems:[previous]})}catch{failed=true}
                  check(failed&&pendingSundayEditSync.size===1,'failed job lost');
                  check(readPendingSundayEditSync().size===1,'retry not durable');
                  persistSundayEditSync=async()=>{};
                  await syncSharedSundayContentAfterSave(source,[edited],{previousItems:[edited]});
                  check(pendingSundayEditSync.size===0,'retry failed');
                  return 'PASS read isolation, editable blanks, scoped edit sync, explicit clear, exceptions, local drafts, CAS, no inserts, failure retry';
                }'''))
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
