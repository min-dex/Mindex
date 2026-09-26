from smoke_app import launch_chromium, start_local_app_server, sync_playwright


server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ("chrome", "webkit"):
            browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
            page = browser.new_page()
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(f"{url}?output=presenter", wait_until="domcontentloaded")
            page.wait_for_selector("#presenterOutputRoot")
            print(engine, page.evaluate("""() => {
              const check=(value,label)=>{if(!value)throw Error(label)};
              check(document.documentElement.classList.contains('presenter-output-document'),'output document class missing');
              check(!document.documentElement.classList.contains('presenter-output-pending'),'output remained hidden');
              check(!document.querySelector('.app-shell'),'controller shell survived output bootstrap');
              check(getComputedStyle(document.body).backgroundColor==='rgb(0, 0, 0)','output must begin on black');
              return 'PASS presenter output boots without controller shell';
            }"""), flush=True)
            browser.close()
finally:
    server.shutdown()
