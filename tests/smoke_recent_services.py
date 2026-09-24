from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof recentServiceWeeks === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              for(const [base,start,end] of [
                ['2026-09-19T12:00:00','2026-09-13','2026-09-26'],
                ['2026-09-20T23:00:00','2026-09-20','2026-10-03'],
                ['2026-12-31T12:00:00','2026-12-27','2027-01-09']]) {
                const weeks=recentServiceWeeks(new Date(base));
                check(toLocalDateStr(weeks[0].start)===start && toLocalDateStr(weeks[1].end)===end,'week boundary '+base);
                check(weeks.flatMap(w=>w.days).length===14,'missing days');
              }
              const actualWeeks=recentServiceWeeks;
              recentServiceWeeks=()=>actualWeeks(new Date('2026-09-19T12:00:00'));
              const dates=['2026-09-12','2026-09-13','2026-09-18','2026-09-20','2026-09-25','2026-09-26','2026-09-27'];
              state.services=dates.map((date,i)=>({id:'s'+i,date,type_id:'friday',title:'금요기도회',...(i===4?{_worshipSourceRef:{no_gathering:true}}:{})}));
              state.serviceTypes=[{id:'friday',name:'금요기도회'}];state.search='';
              getFilteredServices=()=>state.services;serviceItemPreviewParts=()=>({text:''});
              check(getServiceDashboardServices().length===5,'two week filtering');
              renderServiceDashboard();
              check(SERVICE_WEEK_PANEL_TITLE==='최근 예배','navigation label');
              check(refs.detailPane.querySelectorAll('.service-week-board').length===2,'board count');
              check(refs.detailPane.querySelectorAll('.service-week-day').length===14,'day count');
              check(!refs.detailPane.textContent.includes('다가오는 예배'),'old section remains');
              check(refs.detailPane.querySelectorAll('.service-week-card:disabled').length===1,'no gathering guard lost');
              check(refs.detailPane.querySelector('[data-service-list]'),'all services missing');
              renderServiceDashboard({compactWeeks:true,title:'예배 일정'});
              check(refs.detailPane.querySelector('.service-date-list-title').textContent==='예배 일정','home schedule title');
              check(!refs.detailPane.querySelector('.service-week-board'),'home retained empty calendar board');
              check(!refs.detailPane.querySelector('.service-week-day'),'home retained empty calendar days');
              check(refs.detailPane.querySelectorAll('.service-date-card').length===5,'home schedule cards');
              check(refs.detailPane.querySelectorAll('.service-date-card:disabled').length===1,'home no gathering guard lost');
              const html=refs.detailPane.innerHTML;
              state.search='검색';renderServiceDashboard();
              check(!refs.detailPane.querySelector('.service-week-board'),'search should remain list');
              check(refs.detailPane.querySelectorAll('.service-date-card').length===5,'search entries');
              state.search='';refs.detailPane.innerHTML=html;
              state.client={};state.connectionError='';state.serviceError='';
              state.selectedServiceId=null;state.module='service';
              getUpcomingServiceShortcuts=()=>[state.services[3]];
              getHomeSidebarRecentServiceShortcuts=()=>[state.services[3]];
              finishListRender=()=>{};
              renderServiceList();
              check(refs.songList.textContent.includes('다가오는 예배'),'service sidebar shortcuts missing');
              state.module='home';renderServiceList();
              check(refs.songList.textContent.includes('다가오는 예배'),'home sidebar shortcuts missing');
              check(renderPresenterSidebar('',[],null).includes('다가오는 예배'),'presenter sidebar shortcuts missing');
              check(!refs.detailPane.textContent.includes('다가오는 예배'),'sidebar restoration changed dashboard');
              document.body.dataset.theme='dark';
              return 'PASS two weeks, Sunday/year boundaries, cards, absent status and search';
            }'''), flush=True)
            for width in (1440, 640):
                page.set_viewport_size({'width': width, 'height': 1100})
                page.locator('#detailPane').screenshot(path=f'/tmp/mindex-recent-{engine}-{width}.png')
            browser.close()
finally:
    server.shutdown()
