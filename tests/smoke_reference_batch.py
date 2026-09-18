from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chrome', 'webkit'):
                browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
                page = browser.new_page()
                page.route('**/*supabase*/**', lambda r: r.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof presenterReferenceMediaBatchServices !== 'undefined'")
                print(engine, page.evaluate('''async () => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const id='batch-fixture';
                  const service={id,type_id:'fixture'};
                  state.services=[service];state.selectedServiceId=id;
                  const base=normalizeServiceItem({id:'base',service_id:id,label:'광고',_worshipSectionKey:'announcements',memo:''},0);
                  const reset=()=>{state.serviceItems[id]=[{...base}];state.dirty.service=false;};
                  refreshPresenterForService=()=>{};renderCurrentServiceModuleDetail=()=>{};
                  renderServiceList=()=>{};updateSaveState=()=>{};
                  markServiceStructureDirty=()=>{};markServiceElementDirty=()=>{};
                  saveServiceItemMutation=async()=>true;
                  const messages=[];showToast=m=>messages.push(m);
                  let fail='', gate=null;
                  const sent=[];
                  state.client={storage:{from:()=>({upload:async(path,file)=>{
                    sent.push(file);
                    if(gate)await gate;
                    if(file.name===fail){getServiceItems(id)[0].raw_title='동시 수정';return {error:new Error('fixture failure')};}
                    return {};
                  },getPublicUrl:path=>({data:{publicUrl:'https://example.test/'+path}}),remove:async()=>({})})}};
                  const files=[new File(['original PNG bytes'],'one.png',{type:'image/png'}),
                    new File(['original video bytes'],'two.mp4',{type:'video/mp4'}),
                    new File(['original JPEG bytes'],'three.jpg',{type:'image/jpeg'})];
                  const input=fs=>({files:fs,dataset:{serviceId:id,presenterReferenceMediaSection:'announcements'},disabled:false,value:'chosen'});
                  reset();const control=input(files);await addAndUploadPresenterReferenceMedia(control);
                  check(getServiceItems(id).length===4,'one item per file');
                  check(getServiceItems(id).slice(1).map(i=>parseServiceItemMemo(i.memo).asset.name).join(',')==='one.png,two.mp4,three.jpg','order');
                  check(sent.every((f,i)=>f===files[i]),'file re-encoded or replaced');
                  check(!control.disabled && !control.value,'input not reset');
                  reset();sent.length=0;fail='two.mp4';await addAndUploadPresenterReferenceMedia(input(files));
                  check(getServiceItems(id).length===2,'failed dummy retained or success removed');
                  check(getServiceItems(id)[0].raw_title==='동시 수정','concurrent edit lost');
                  check(sent.length===2,'continued after failure');
                  check(!presenterReferenceMediaBatchServices.has(id),'lock leaked');
                  reset();sent.length=0;fail='';await addAndUploadPresenterReferenceMedia(input([files[0],new File(['x'],'bad.txt')]));
                  check(sent.length===0 && getServiceItems(id).length===1,'invalid batch mutated');
                  saveServiceItemMutation=async()=>{throw Error('save failed')};
                  await addAndUploadPresenterReferenceMedia(input([files[0]]));
                  check(getServiceItems(id).length===1,'save failure retained dummy');
                  saveServiceItemMutation=async()=>true;sent.length=0;
                  let resolve;gate=new Promise(r=>resolve=r);const first=addAndUploadPresenterReferenceMedia(input([files[0]]));
                  await Promise.resolve();await addAndUploadPresenterReferenceMedia(input([files[1]]));
                  check(sent.length===1,'duplicate batch allowed');resolve();await first;gate=null;
                  check(!presenterReferenceMediaBatchServices.has(id),'lock retained after success');
                  const html=renderPresenterAssetUpload(getServiceItems(id)[1],1,parseServiceItemMemo(getServiceItems(id)[1].memo),id);
                  check(html.includes('multiple'),'existing reference chooser is single');
                  const imagePreview=renderPresenterReferenceMediaPreview({kind:'image',name:'one.png',url:'https://example.test/one.png'},'image');
                  check(imagePreview.includes('<details') && imagePreview.includes('미리보기') && !imagePreview.includes('<details open'),'image preview is not collapsed');
                  const menu=document.createElement('div');menu.innerHTML=renderPresenterReferenceMediaQuickAdd('announcements',id);
                  check(menu.querySelector('[data-presenter-reference-media-direct-file]')?.multiple,'add chooser is single');
                  reset();sent.length=0;
                  const existing=normalizeServiceItem({id:'existing',service_id:id,label:'참고 화면',_worshipSectionKey:'announcements',
                    memo:serializeServiceItemMemo({elementType:'image',inputMode:'asset',asset:{kind:'image',name:'old.png',url:'https://example.test/old.png'}})},1);
                  const tail={...existing,id:'tail'};
                  state.serviceItems[id]=[{...base},existing,tail];
                  const existingInput=input(files);existingInput.dataset.serviceItemIndex='1';
                  await uploadPresenterReferenceMediaFile(existingInput);
                  check(getServiceItems(id).map(i=>i.id).at(-1)==='tail','files not inserted after current reference');
                  check(getServiceItems(id).slice(1,4).map(i=>parseServiceItemMemo(i.memo).asset.name).join(',')==='one.png,two.mp4,three.jpg','existing chooser order');
                  check(getServiceItems(id)[1].id==='existing','existing item replaced rather than reused');
                  const originalMemo=getServiceItems(id)[1].memo;
                  saveServiceItemMutation=async()=>{throw Error('save failed')};
                  await uploadPresenterReferenceMediaFile(existingInput);
                  check(getServiceItems(id)[1].memo===originalMemo && getServiceItems(id).length===5,'failed existing replacement lost original');
                  return 'PASS ordered batch, original File identity, partial failure, concurrent edits, validation and lock';
                }'''), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
