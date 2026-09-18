from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof currentPresenterAudioContext === 'function'")
            print(engine, page.evaluate('''async () => {
              const check=(v,m)=>{if(!v)throw Error(m)};
              const service={id:'music-fixture',type_id:'friday'};
              const item={id:'free',label:'자율기도',_worshipSlotKey:'prayer.meeting.free'};
              state.services=[service];
              getServiceItems=()=>[item];
              state.presenter.serviceId=service.id;
              state.presenter.slides=[{id:'free-slide',elementId:item.id}];
              state.presenter.index=0;state.presenter.safetyBlank=false;
              state.presenter.liveScripture={active:false};
              const source='./assets/presenter/friday-free-prayer.m4a';
              check(currentPresenterAudioContext().source===source,'missing default');
              const before=state.serviceMusic.audio;
              check(renderServiceMusicPlayer().includes('금요기도회 기도찬양'),'missing music UI');
              check(state.serviceMusic.audio===before,'render created audio');
              service.type_id='sunday';
              check(!currentPresenterAudioContext().source,'default leaked to Sunday');
              service.type_id='friday';item.label='기도찬양';item._worshipSlotKey='';
              check(!currentPresenterAudioContext().source,'default leaked to another item');
              item.label='자율기도';state.presenter.safetyBlank=true;
              check(!currentPresenterAudioContext().source,'blank context leaked');
              state.presenter.safetyBlank=false;state.presenter.liveScripture.active=true;
              check(!currentPresenterAudioContext().source,'live scripture context leaked');
              state.presenter.liveScripture.active=false;
              const originalSource=presenterSlideAudioSource;
              presenterSlideAudioSource=()=>'/custom.m4a';
              check(currentPresenterAudioContext().source==='/custom.m4a','custom source overridden');
              presenterSlideAudioSource=originalSource;
              renderPresenterControlState=()=>{};
              startServiceMusicSyncTimer=()=>{};
              syncServiceMusicSyncedLyricsWithCurrentTime=()=>{};
              let plays=0;
              const audio={loop:false,play:()=>{plays++;return Promise.resolve()}};
              getServiceMusicAudio=()=>audio;
              setServiceMusicSource=(a,s,m,p)=>{a.loop=p.loop;state.serviceMusic.sourceKey=s;state.serviceMusic.mode=m};
              state.serviceMusic.sourceKey='';state.serviceMusic.objectUrl='';state.serviceMusic.playing=false;
              state.serviceMusic.mode='manual';state.serviceMusic.repeat=undefined;state.serviceMusic.audio=audio;
              runServiceMusicAction('repeat');
              check(audio.loop && plays===0,'repeat started playback');
              check(renderServiceMusicPlayer().includes('aria-pressed="true"'),'repeat state missing');
              runServiceMusicAction('toggle');await Promise.resolve();
              check(plays===1 && state.serviceMusic.sourceKey===source && audio.loop,'explicit play failed');
              setServiceMusicVolume(3);check(audio.volume===0.6,'volume failed');
              runServiceMusicAction('repeat');check(!audio.loop,'repeat off failed');
              const mount=document.createElement('div');mount.id='servicePresenterControls';
              mount.innerHTML=renderServiceMusicPlayer()+'<button class="icon-btn" disabled title="사용 불가">X</button>';
              document.body.replaceChildren(mount);
              refreshIcons(mount);
              for(const width of [254,320,390]) {
                mount.style.width=width+'px';
                check(mount.scrollWidth<=width,'music controls overflow '+width);
              }
              const disabled=mount.querySelector(':disabled');
              check(getComputedStyle(disabled).cursor==='not-allowed','disabled cursor missing');
              return 'PASS context isolation, no autoplay, repeat, volume and compact layout';
            }'''), flush=True)
            page.locator('#servicePresenterControls').screenshot(path='/tmp/mindex-friday-music-'+engine+'.png')
            print(engine, page.evaluate('''() => new Promise((resolve,reject) => {
              const audio=document.createElement('audio');
              audio.preload='metadata';audio.muted=true;
              const timeout=setTimeout(()=>reject(Error('metadata timeout')),15000);
              audio.onloadedmetadata=()=>{
                clearTimeout(timeout);
                if(!audio.paused || Math.abs(audio.duration-2801.714)>1) reject(Error('unexpected audio metadata'));
                else resolve('PASS original AAC metadata and paused state');
                audio.removeAttribute('src');audio.load();
              };
              audio.onerror=()=>{clearTimeout(timeout);reject(Error('AAC failed to load'))};
              audio.src='./assets/presenter/friday-free-prayer.m4a';
            })'''), flush=True)
            browser.close()
finally:
    server.shutdown()
