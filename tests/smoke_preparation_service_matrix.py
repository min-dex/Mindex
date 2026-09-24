"""Audit bulk-input examples using each service's real template and parser."""
import json

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page()
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof presenterPreparationPlaceholderForService === 'function'")
                result = page.evaluate("""() => {
                  const results=[];
                  const check=(value,message)=>{if(!value)throw Error(message)};
                  const cases=Object.keys(SERVICE_TYPE_DISPLAY_NAMES).filter(t=>!/[가-힣]/.test(t))
                    .map(type=>[type,'2026-09-13']);
                  for(const date of ['2026-08-07','2026-08-14','2026-08-21','2026-08-28',
                    '2026-09-04','2026-09-11','2026-09-18','2026-09-25']) cases.push(['friday',date]);
                  for(const [type,date] of cases){
                    const target=type==='friday'?autoFridayServiceTarget(date):{};
                    const service={...target,id:'matrix-'+type+date,type_id:target.typeId||type,date,
                      _worshipSourceRef:target.sourceRef};
                    state.services=[service];
                    state.serviceTypes=[{id:type,name:SERVICE_TYPE_DISPLAY_NAMES[type]}];
                    const scaffold=buildWorshipServiceScaffold(service.id,service.type_id,{service});
                    state.serviceItems={[service.id]:groupWorshipElements(scaffold.sections,scaffold.elements)[service.id]||[]};
                    const items=servicePrepEditorItems(service.id);
                    const examples=presenterPreparationPlaceholderForService(service);
                    const valueExamples=presenterPreparationValueExamplesForService(service);
                    const expected=items.filter(i=>presenterServiceInputHasEditableField(i,service)).flatMap(i=>
                      presenterPreparationPlaceholderLinesForItem(i,service,presenterServiceInputItem(i,service)));
                    const parsed=parsePresenterPreparationInput(expected.length?examples:'');
                    const plan=planPresenterPreparationEntries(parsed.entries,service);
                    check(!parsed.errors.length && !plan.errors.length,`${type} ${date}: ${[...parsed.errors,...plan.errors].join(', ')}`);
                    check(parsed.entries.length===expected.length,`${type}: missing examples ${parsed.entries.length}/${expected.length}`);
                    check(plan.planned.every(p=>!p.projected || items.some(i=>i.id===p.projected.id)),`${type}: synthetic target`);
                    check(!/^(대기 영상|사도신경|주기도문):/m.test(examples),`${type}: fixed content example`);
                    const form=expected.length?presenterPreparationFormFromExamples(examples):'';
                    const blank=parsePresenterPreparationInput(form,{skipEmptyLabels:true});
                    check(form.split('\\n').filter(Boolean).length===(expected.length?examples.split('\\n').length:0),`${type}: form label count`);
                    const half=expected.length?examples.split('\\n').map((line,i)=>i%2?line:line.slice(0,line.search(/[:：]/)+1)+' ').join('\\n'):'';
                    const partial=parsePresenterPreparationInput(half,{skipEmptyLabels:true});
                    check(!partial.errors.length,`${type}: half-filled form errors: ${partial.errors.join(', ')}`);
                    check(expected.length<2||(partial.entries.length>0&&partial.entries.length<expected.length),`${type}: half-filled entries ${partial.entries.length}/${expected.length}`);
                    check(!blank.errors.length && !blank.entries.length,`${type}: blank form must apply nothing: ${blank.errors.join(', ')} ${blank.entries.map(e=>e.label+'='+e.content).join(', ')}`);
                    const host=document.createElement('div');
                    host.style.width='300px';
                    host.innerHTML=renderPresenterSidebarPreparationInput(service);
                    document.body.append(host);
                    const input=host.querySelector('textarea');
                    check(input.placeholder===valueExamples,`${type}: rendered value placeholder differs`);
                    check(!host.querySelector('[data-presenter-preparation-form]'),`${type}: form button remains`);
                    if(expected.length>10){
                      input.scrollTop=input.scrollHeight;
                      check(input.scrollTop>0,`${type}: cannot scroll through examples`);
                    }
                    host.remove();
                    results.push({type,date,lines:parsed.entries.length});
                  }
                  check(presenterPreparationPlaceholderLinesForItem({label:'참고 화면'},null,{mode:'asset',memo:{}}).length===0,'asset example');
                  check(presenterPreparationPlaceholderLinesForItem({label:'주기도문'},null,{mode:'benediction',memo:{benedictionReplacement:{}}}).length===0,'replaced benediction example');
                  return results;
                }""")
                print(engine, json.dumps(result, ensure_ascii=False), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
