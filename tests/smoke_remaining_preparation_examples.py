from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 800, "height": 900})
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof remainingPresenterPreparationExamples === 'function'")
                print(engine, page.evaluate("""() => {
                  const check=(v,m)=>{if(!v)throw Error(m)};
                  const examples=['찬양1: 꽃들도','찬양2: 주 품에','대표기도: 홍길동 집사',
                    '성경봉독: 요한복음 3:16','설교 제목: 은혜 / 홍길동 목사','설교 본문: 요한복음 3:16'].join('\\n');
                  const remaining=draft=>remainingPresenterPreparationExamples(examples,draft);
                  check(remaining('')==='','empty should use native placeholder');
                  check(!remaining('찬양1: 꽃들도').includes('찬양1:'),'completed entry');
                  check(remaining('찬양1: 꽃들도').includes('찬양2:'),'unfilled entry');
                  check(!remaining('대표기도:').includes('대표기도:'),'pending label');
                  check(!remaining('대표기').includes('대표기도:') && remaining('대표기').includes('찬양1:'),'partial label misread as song');
                  check(remaining('찬양').includes('찬양1:') && remaining('찬양').includes('찬양2:'),'ambiguous prefix');
                  check(!remaining('기도: 김철수 집사').includes('대표기도:'),'alias');
                  check(!remaining('말씀: 은혜로 사는 삶').includes('설교 제목:') && remaining('말씀: 은혜로 사는 삶').includes('설교 본문:'),'sermon title alias');
                  check(remainingPresenterPreparationExamples('기도1: 담당\\n기도2: 담당','기도1:')==='기도2: 담당','numbered pending label');
                  check(!remaining('꽃들도').includes('찬양1:'),'shorthand song');
                  check(!remaining('찬양2: 주 품에\\n대표기도:').includes('찬양2:'),'out of order');
                  check(remaining(examples)==='','all complete');
                  const service={id:'remaining-fixture',type_id:'fixture'};
                  state.services=[service];
                  presenterPreparationPlaceholderForService=()=>examples;
                  const host=document.createElement('main');
                  host.style.cssText='position:fixed;inset:0 auto auto 0;width:300px;background:var(--panel);padding:10px';
                  host.innerHTML=renderPresenterSidebarPreparationInput(service);document.body.append(host);
                  host.addEventListener('input',handleDetailInput);
                  const input=host.querySelector('textarea');
                  const hints=host.querySelector('[data-presenter-preparation-examples]');
                  check(hints.hidden,'empty draft duplicates examples');
                  input.focus();input.value='찬양2: 주 품에';input.setSelectionRange(4,4);
                  input.dispatchEvent(new Event('input',{bubbles:true}));
                  check(!hints.hidden && hints.textContent===remaining(input.value),'live hints');
                  check(input.selectionStart===4 && document.activeElement===input,'caret lost');
                  check(input.value==='찬양2: 주 품에','hints inserted into actual draft');
                  input.value='대표기도: ㄱ';input.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));
                  check(input.value==='대표기도: ㄱ' && hints.textContent.includes('찬양2:'),'composition or restored example');
                  input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));
                  check(hints.hidden && input.placeholder===examples,'cleared draft');
                  input.value='찬양1: <script>alert(1)</script>';
                  input.dispatchEvent(new Event('input',{bubbles:true}));
                  check(!hints.querySelector('script'),'HTML interpolation');
                  state.presenterPreparationDrafts[service.id]='대표기도:';
                  const restored=document.createElement('div');restored.innerHTML=renderPresenterSidebarPreparationInput(service);
                  check(!restored.querySelector('[data-presenter-preparation-examples]').textContent.includes('대표기도:'),'rerender loses filtering');
                  check(hints.getBoundingClientRect().right<=host.getBoundingClientRect().right,'narrow panel overflow');
                  return 'PASS remaining examples, partial input, aliases, reorder, deletion, composition, caret, escaping';
                }"""), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
