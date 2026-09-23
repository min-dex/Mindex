import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    server, url = (None, args.url) if args.url else start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url + '?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof appendPresenterCitationReference === 'function'")
            result = page.evaluate('''async () => {
              const assert=(value,message)=>{if(!value)throw Error(message)};
              const slide={type:'scripture',elementType:'scripture_text',layout:'lower_bar_text',
                title:'마태복음 5:45',marker:'마태복음 5:45',referenceBook:'마태복음',referenceRange:'5:45',text:'45   본문 테스트'};
              const mount=document.createElement('div');
              mount.innerHTML=renderPresenterSlideFrame({...slide,scriptureContext:'citation'},{noChromakey:true});
              assert(mount.querySelector('.presenter-scripture-reading-ref')?.textContent==='마태복음 5:45','fullscreen reference');
              mount.innerHTML=renderPresenterSlideFrame({...slide,scriptureContext:'reading'},{noChromakey:true});
              assert(mount.querySelector('.presenter-citation-tab, .presenter-scripture-reading-ref')?.textContent==='마태복음 5:45','reading changed');
              const inline=presenterCitationScriptureText({number:45,text:'본문',referenceBook:'마태복음',referenceRange:'5:45'},{},'citation-chromakey');
              assert(inline==='마 5:45   본문','chromakey citation');
              assert(slide.title==='마태복음 5:45' && formatServiceScriptureReferenceList('마 5:45')==='마태복음 5:45','stored/display title changed');
              for(const [code,name] of Object.entries(KOREAN_BIBLE_BOOK_NAMES)) {
                assert(presenterCitationBookName(name)===MINDEX_CONSTANTS.KOREAN_BIBLE_BOOK_ABBREVIATIONS[code],code+' abbreviation');
              }
              assert(presenterSlideMatchesScriptureReference(slide,parseBibleReference('마 5:45-48')),'range first verse');
              assert(presenterSlideMatchesScriptureReference({...slide,title:'마태복음 5:45-46'},parseBibleReference('마 5:46')),'combined verse');
              assert(!presenterSlideMatchesScriptureReference(slide,parseBibleReference('마 5:46')),'wrong verse');
              assert(!presenterSlideMatchesScriptureReference(slide,parseBibleReference('막 5:45')),'wrong book');
              const generated=buildPresenterScriptureTextSlides({id:'generated',label:'인용 구절',raw_title:'마 5:45-48',memo:JSON.stringify({
                scriptureReferences:['마 5:45-48'],manualScripture:{reference:'마 5:45-48',verses:[45,46,47,48].map(number=>({number,text:'본문'}))}
              })},{sectionKey:'sermon',elementId:'generated'},0);
              assert(generated.length===4,'generated fixture');
              const citationControl=buildPresenterSlidesForServiceItem({id:'citation-control',label:'인용 구절',raw_title:'마 5:45-48',memo:JSON.stringify({
                elementType:'scripture_body',scriptureReferences:['마 5:45-48'],manualScripture:{reference:'마 5:45-48',verses:[45,46,47,48].map(number=>({number,text:'본문'}))}
              })},{id:'citation-control-service',type_id:'fixture'},0,{allowHydration:false});
              assert(citationControl.length===5 && citationControl.at(-1).liveScriptureControl,'citation control blank missing');
              assert(generated.findIndex(s=>presenterSlideMatchesScriptureReference(s,parseBibleReference('마 5:47')))===2,'range metadata hid individual verse');
              assert(generated.filter(s=>presenterSlideMatchesScriptureReference(s,parseBibleReference('마 5:47'))).length===1,'multiple verses matched');
              const serviceId='citation-fixture',elementId='citation-element';
              const setup=()=>{
                state.selectedServiceId=serviceId;
                state.services=[{id:serviceId,type_id:'fixture'}];
                state.serviceItems[serviceId]=[{id:elementId,service_id:serviceId,label:'인용 구절',memo:''}];
              };
              const input=document.createElement('input');
              input.dataset.serviceId=serviceId;input.dataset.presenterCitationElementId=elementId;
              input.dataset.presenterCitationReferenceInput='';
              let live=false,actions=[],saves=0,resolutions=0,release,opens=0,scrolls=0,reservations=0,closed=0;
              isPresenterOutputWindowOpen=()=>live;
              window.open=()=>{reservations++;return {closed:false,location:{replace:()=>{}},close(){this.closed=true;closed++}}};
              openPresenterOutput=async()=>{opens++};
              presenterControllerIsLive=()=>live;
              runPresenterAction=(action,id,options)=>actions.push(['live',action,options.index]);
              setPresenterPendingSlide=(id,index)=>actions.push(['pending',index]);
              renderPresenterControlState=()=>{};
              scrollPresenterBoardToIndex=()=>{scrolls++};
              saveServiceItemPatch=async()=>{saves++};
              showToast=()=>{};
              presenterSlidesForService=()=>[{...slide,elementId:'different'}, {...slide,elementId}, {...slide,elementId,title:'마태복음 5:46'}];
              resolveServiceScriptureBeforeSave=()=>{resolutions++;return new Promise(resolve=>{release=resolve})};
              for(const autoOutput of [true,false]) for(const isLive of [false,true]) {
                presenterCitationAutoOutput=autoOutput;
                setup();live=isLive;actions=[];input.value='마 5:45-48';
                const before=resolutions,priorOpens=opens,priorScrolls=scrolls,priorReservations=reservations;
                const pending=appendPresenterCitationReference(input);
                await appendPresenterCitationReference(input);
                assert(resolutions===before+1,'duplicate Enter');
                presenterCitationAutoOutput=!autoOutput;
                release();await pending;
                const expected=autoOutput?[['live','jump',1]]:[];
                assert(JSON.stringify(actions)==JSON.stringify(expected),'wrong navigation '+JSON.stringify(actions));
                assert(opens-priorOpens===(autoOutput&&!isLive?1:0),'output opening');
                assert(reservations-priorReservations===(autoOutput&&!isLive?1:0),'gesture window reservation');
                assert(scrolls===priorScrolls,'citation submission scrolled away from input');
                assert(input.value==='' && !pendingPresenterCitationRequests.size,'input or lock not cleared');
              }
              presenterCitationAutoOutput=true;live=false;
              setup();actions=[];input.value='잘못된 성경 주소';
              const before=resolutions;await appendPresenterCitationReference(input);
              assert(resolutions===before && !actions.length && input.value,'invalid reference changed output');
              input.value='마 5:45';resolveServiceScriptureBeforeSave=async()=>{throw Error('offline')};
              await appendPresenterCitationReference(input);
              assert(!actions.length && input.value && !pendingPresenterCitationRequests.size,'failed lookup navigation/lock');
              assert(closed===1,'failed lookup left reserved window');
              const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.presenterCitationAutoOutput='';
              document.body.append(checkbox);checkbox.addEventListener('change',handleDetailChange);
              checkbox.checked=false;checkbox.dispatchEvent(new Event('change'));
              assert(presenterCitationAutoOutput===false && !actions.length,'toggle changed output');
              let submitted=0;appendPresenterCitationReference=async()=>{submitted++};
              input.addEventListener('keydown',handleDetailKeydown);
              input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true}));
              assert(submitted===0,'IME Enter submitted');
              const event=new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true});
              input.dispatchEvent(event);
              assert(submitted===1 && event.defaultPrevented,'Enter not handled');
              return {books:66,saves,rangeNavigation:true,liveAndPending:true,duplicateGuard:true,imeGuard:true};
            }''')
            print('PASS citation-only abbreviations and Enter navigation:', result)
            browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
