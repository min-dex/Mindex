import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    server, url = (None, args.url) if args.url else start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                page = browser.new_page()
                page.route('**/*supabase*/**', lambda route: route.abort())
                page.goto(url + '?output=presenter', wait_until='domcontentloaded')
                page.wait_for_function("typeof presenterServiceScriptureCacheSignature === 'function'")
                result = page.evaluate('''() => {
                  const assert=(v,m)=>{if(!v)throw Error(m)};
                  const service={id:'audit',type_id:'fixture'};state.services=[service];
                  function legacy(slides, items) {
                    const entries=slides.map((slide,slideIndex)=>({slide,slideIndex}));
                    const belongs=(slide,item)=>{
                      const c=normalizeServiceConnectedPraise(slide.connectedPraise||slide.connected_praise);
                      return presenterSlideBelongsToItem(slide,item)||Boolean(c&&[c.primaryItemId,...(c.itemIds||[]),...(c.secondaryItemIds||[])].includes(String(item.id||'')));
                    };
                    items.forEach((item,index)=>{
                      if(entries.some(({slide})=>belongs(slide,item)))return;
                      const slide={...presenterSectionForServiceItem(item,index,serviceItemDisplayText(item)),id:`${item.id}:editor-only`,controllerEditorOnly:true,label:item.label||'',title:serviceItemDisplayText(item),text:''};
                      const next=entries.findIndex(e=>items.slice(index+1).some(i=>belongs(e.slide,i)));
                      entries.splice(next<0?entries.length:next,0,{slide,slideIndex:-1});
                    });return entries;
                  }
                  const match=presenterSlideBelongsToItem;let comparisons=0;
                  presenterSlideBelongsToItem=(...args)=>{comparisons++;return match(...args)};
                  let cases=0,oldComparisons=0,newComparisons=0;
                  for(const count of [0,1,30,60,120])for(const mode of ['all','missing','empty','connected']) {
                    const items=Array.from({length:count},(_,i)=>({id:'i'+i,label:'항목 '+i,memo:'',sort_order:i+1}));
                    const slides=items.filter((_,i)=>mode==='all'||(mode!=='empty'&&i%2===0)).flatMap(item=>Array.from({length:8},(_,j)=>({id:item.id+':'+j,elementId:item.id,type:'lyrics',text:'가사',...(mode==='connected'?{connectedPraise:{primaryItemId:item.id,itemIds:[item.id,'i1'],secondaryItemIds:['i3']}}:{})})));
                    getServiceOutlineItems=()=>items;
                    comparisons=0;const expected=legacy(slides,items);const old=comparisons;
                    comparisons=0;const actual=presenterBoardEntries(slides,service);
                    assert(JSON.stringify(actual)===JSON.stringify(expected),'order changed '+count+mode);
                    if(count===120&&mode==='missing'){oldComparisons=old;newComparisons=comparisons;}
                    cases++;
                  }
                  assert(newComparisons<oldComparisons/5,'membership cost not reduced');
                  state.serviceItems.audit=[{id:'song',label:'찬양',raw_title:'곡',memo:''}];
                  const signature=presenterSlideBuildSourceSignature;let calls=0,builds=0;
                  presenterSlideBuildSourceSignature=(...args)=>{calls++;return signature(...args)};
                  buildServicePresenterSlidesUncached=()=>{builds++;return [{id:'slide',type:'lyrics',text:'가사'}]};
                  state.presenter.serviceId='other';presenterSlideBuildCache.clear();presenterSlidesForService('audit');calls=0;builds=0;
                  for(let i=0;i<40;i++)presenterSlidesForService('audit');
                  assert(calls===40&&builds===0,'duplicate signature / cache miss');
                  const before=signature('audit');state.bibleVerseCacheVersion++;assert(signature('audit')===before,'unrelated chapter invalidated song');
                  state.bibleTranslations=[{id:'translation',name:'개역개정'}];
                  state.serviceItems.audit=[{id:'scripture',label:'성경봉독',raw_title:'마 5:45',memo:''}];
                  const key=bibleVerseCacheKey('translation','MAT',5);
                  const empty=signature('audit');
                  state.bibleVerseCache.set(key,[{verse:45,text:'본문'}]);
                  const loaded=signature('audit');assert(empty!==loaded,'referenced load missed');
                  state.bibleVerseCache.get(key)[0].text='수정 본문';assert(signature('audit')!==loaded,'in-place verse edit missed');
                  const current=signature('audit');state.bibleVerseCache.set(bibleVerseCacheKey('translation','JHN',1),[{verse:1,text:'다른 장'}]);state.bibleVerseCacheVersion++;
                  assert(signature('audit')===current,'unrelated scripture invalidated service');
                  state.bibleTranslations=[{id:'new-translation',name:'개역개정'}];assert(signature('audit')!==current,'translation change missed');
                  const preloadService={id:'preload',type_id:'sunday-afternoon'};
                  state.services=[preloadService];
                  const originalBuild=buildServicePresenterSlides;
                  const originalImagePreload=preloadPresenterOutputImage;
                  const originalVideoWarmup=warmPresenterOutputVideoMetadata;
                  const imageWarmups=[];const videoWarmups=[];
                  buildServicePresenterSlides=()=>[
                    {id:'first-image',type:'image',elementType:'image',layout:'media',imageSrc:'first.png'},
                    {id:'first-video',type:'video',elementType:'video',layout:'media',videoSrc:'first.mp4'},
                    {id:'second-video',type:'video',elementType:'video',layout:'media',videoSrc:'second.mp4'},
                    {id:'third-video',type:'video',elementType:'video',layout:'media',videoSrc:'third.mp4'},
                  ];
                  preloadPresenterOutputImage=(source,options)=>{imageWarmups.push({source,options});return Promise.resolve()};
                  warmPresenterOutputVideoMetadata=source=>{videoWarmups.push(source);return null};
                  const warmed=warmPresenterServiceAssets('preload');
                  assert(warmed.images===imageWarmups.length&&warmed.images<=PRESENTER_SERVICE_ASSET_PRELOAD_LIMIT,'asset image warmup limit missed');
                  assert(JSON.stringify(videoWarmups)===JSON.stringify(['first.mp4','second.mp4']),'asset video warmup scope missed');
                  buildServicePresenterSlides=originalBuild;
                  preloadPresenterOutputImage=originalImagePreload;
                  warmPresenterOutputVideoMetadata=originalVideoWarmup;
                  return {cases,oldComparisons,newComparisons,cacheReads:40,signatures:calls,dependencyChecks:true};
                }''')
                print('PASS structural cache and board tests', engine, result)
                browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
