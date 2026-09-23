from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof serviceOrderTemplate === 'function'")
            print(engine, page.evaluate('''() => {
              const check=(value,label)=>{if(!value)throw Error(label)};
              const nurseryType=normalizeWorshipServiceType({id:'nursery',display_name:'유치부 예배',config:{autoScheduleEnabled:true}});
              state.serviceTypes=[nurseryType];
              state.calendarData=[];
              check(worshipAppServiceTypeId('유치부 예배')==='nursery','Korean alias');
              check(worshipAppServiceTypeId('kindergarten')==='nursery','legacy alias');
              check(serviceTypeGroupKey('nursery')==='ministry','not department');
              check(serviceTypeDisplayName('nursery')==='유치부 예배','display name');
              check(presenterOutputTheme('nursery')==='children','children theme');
              check(!serviceTypeUsesChromakey('nursery'),'clean output');
              check(SERVICE_RECURRENCE.nursery?.weekday===0 && SERVICE_TIME_WINDOWS.nursery?.start==='10:50','Sunday schedule');
              check(!INTEGRATED_SUNDAY_SKIP_SERVICE_TYPES.has('nursery'),'must remain for all-generation worship');
              check(serviceTypePreferredPraiseTypes('nursery').join(',')==='children','children praise preference');
              const nurseryTemplate=serviceOrderTemplate('nursery').map(step=>step.label);
              const childrenTemplate=serviceOrderTemplate('children').map(step=>step.label);
              check(JSON.stringify(nurseryTemplate)===JSON.stringify(childrenTemplate),'template differs');
              const targets=autoUpcomingPublicServiceTargets(new Date('2026-09-19T12:00:00'));
              check(targets.some(target=>target.typeId==='nursery'),'configured schedule missing');
              const targetKeys=(date)=>autoUpcomingPublicServiceTargets(new Date(date)).map(target=>`${target.typeId}:${target.date}`);
              const wednesdayBeforeEnd=targetKeys('2099-08-19T20:29:00');
              const wednesdayAfterEnd=targetKeys('2099-08-19T20:30:00');
              const fridayAfterEnd=targetKeys('2099-08-21T22:00:00');
              check(wednesdayBeforeEnd.includes('wednesday:2099-08-19'),'current Wednesday rolled too early');
              check(wednesdayAfterEnd.includes('wednesday:2099-08-26'),'next Wednesday target missing');
              check(!wednesdayAfterEnd.includes('wednesday:2099-08-19'),'expired Wednesday target remained');
              check(fridayAfterEnd.includes('friday:2099-08-28'),'next Friday target missing');
              check(!fridayAfterEnd.includes('friday:2099-08-21'),'expired Friday target remained');
              return 'PASS nursery behavior and expired service target rollover';
            }'''), flush=True)
            browser.close()
finally:
    server.shutdown()
