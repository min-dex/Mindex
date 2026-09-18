from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPrayerMusicControl === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              const service={id:'music-fixture',type_id:'friday'};
              const item={id:'free',label:'자율기도',_worshipSlotKey:'prayer.meeting.free'};
              state.services=[service];getServiceItems=()=>[item];
              state.presenter.serviceId=service.id;
              state.presenter.slides=[{id:'free-slide',elementId:item.id}];
              state.presenter.index=0;state.presenter.safetyBlank=false;
              state.presenter.liveScripture={active:false};
              check(!currentPresenterAudioContext().source,'sidebar source leak');
              check(!state.prayerMusic.audio,'eager audio');
              check(!renderPrayerMusicControl({service:{type_id:'sunday'},item}),'Sunday leak');
              const mount=document.createElement('div');mount.id='prayer-test';
              mount.innerHTML=renderPrayerMusicControl({service,item});document.body.append(mount);refreshIcons(mount);
              const prepared=state.prayerMusic.audio;
              check(prepared && prepared.preload==='auto' && prepared.paused,'preload without autoplay');
              renderPrayerMusicControl({service,item});
              check(prepared===state.prayerMusic.audio,'audio recreated');
              prepared.removeAttribute('src');prepared.load();
              let plays=0;
              const audio={paused:true,currentTime:0,play(){plays++;this.paused=false;return Promise.resolve()},pause(){this.paused=true}};
              state.prayerMusic.audio=audio;
              const background=JSON.stringify(state.serviceMusic);
              await runPrayerMusicAction('toggle',service.id);check(plays===1&&!audio.paused,'play');
              await runPrayerMusicAction('repeat',service.id);check(audio.loop,'repeat');
              state.module='scripture';check(!audio.paused,'navigation paused');
              await runPrayerMusicAction('toggle',service.id);check(audio.paused,'pause');
              audio.currentTime=20;await runPrayerMusicAction('stop',service.id);check(audio.currentTime===0,'stop');
              check(JSON.stringify(state.serviceMusic)===background,'background mutated');
              for(const width of [254,390,1000]){mount.style.width=width+'px';check(mount.scrollWidth<=width,'overflow '+width)}
              let allow=false,renders=0,loads=0,publishes=0;
              confirmSaveBeforeLeaving=async()=>allow;isPresenterOutputWindowOpen=()=>true;
              saveCurrentListScroll=()=>{};markWorshipServiceExplicitlyRequested=()=>{};
              persistUiState=()=>{};syncBrowserHistory=()=>{};render=()=>{renders++};
              loadServiceItems=()=>{loads++};publishPresenterState=()=>{publishes++};
              state.presenter.index=7;state.presenter.viewServiceId='other';
              renderLiveServiceReturnControl();check(!document.getElementById('returnLiveServiceBtn').hidden,'missing return');
              await returnToLiveService();check(state.module==='scripture','cancel ignored');
              allow=true;await returnToLiveService();
              check(state.module==='presenter'&&state.presenter.viewServiceId===service.id,'return');
              check(state.presenter.index===7&&!loads&&!publishes&&renders===1,'live state disturbed');
              renderLiveServiceReturnControl();check(document.getElementById('returnLiveServiceBtn').hidden,'live page button');
              state.module='praise';isPresenterOutputWindowOpen=()=>false;renderLiveServiceReturnControl();
              check(document.getElementById('returnLiveServiceBtn').hidden,'stale return');
              return 'PASS music isolation, layout, guarded return without reload/output changes';
            }'''), flush=True)
            page.locator('#prayer-test').screenshot(path='/tmp/mindex-prayer-controls-'+engine+'.png')
            browser.close()
finally:
    server.shutdown()
