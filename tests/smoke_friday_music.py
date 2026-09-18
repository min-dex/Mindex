from smoke_app import launch_chromium, start_local_app_server, sync_playwright

server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ('chrome', 'webkit'):
            browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderServiceSlotMusic === 'function'")
            print(engine, page.evaluate('''async () => {
 const check=(v,m)=>{if(!v)throw Error(m)};
 const service={id:'fixture',type_id:'friday'},item={_worshipSlotKey:'prayer.meeting.free'};
 const a={paused:true,currentTime:0,src:'',load(){this.loads=(this.loads||0)+1},pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()}};
 state.serviceMusic.audio=a;
 const m=document.createElement('div');m.id='music-test';m.style.width='254px';m.innerHTML=renderServiceSlotMusic({service,item});document.body.append(m);refreshIcons(m);
 check(!('prayerMusic' in state),'dedicated state left');
 check(a.loads===1&&a.paused,'preload autoplay');
 renderServiceSlotMusic({service,item});check(a.loads===1,'preload repeated');
 check(!m.querySelector('[data-service-music-action="repeat"]'),'repeat shown');
 const root=m.querySelector('[data-service-music-player]'),binding=root.dataset;
 const source=state.serviceMusic.sourceKey;
 const toggle=m.querySelector('[data-service-music-action="toggle"]');
 const pos=()=>JSON.stringify([...m.querySelectorAll('button,select')].map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width]}));
 const positions=pos();let finish;
 a.play=()=>new Promise(r=>{finish=()=>{a.paused=false;r()}});
 const first=runServiceMusicAction('toggle',binding);
 check(toggle.textContent.includes('준비 중'),'pending label');check(toggle.getAttribute('aria-pressed')==='false','pending playing');check(pos()===positions,'pending shift');
 finish();await first;check(toggle.textContent.includes('일시정지'),'playing label');check(pos()===positions,'playing shift');check(!a.loop,'loop');
 setServiceMusicVolume(2);check(a.volume===0.4&&m.querySelector('select').value==='2','shared volume');
 await runServiceMusicAction('toggle',binding);check(a.paused&&!state.serviceMusic.playing,'pause');
 a.currentTime=12;runServiceMusicAction('stop',binding);check(a.currentTime===0,'stop reset');
 const pending=runServiceMusicAction('toggle',binding);runServiceMusicAction('toggle',binding);check(!state.serviceMusic.pending,'cancel pending');finish();a.paused=true;await pending;check(!state.serviceMusic.playing,'stale play revived');
 setServiceMusicSource(a,'other.mp3','manual',{loop:true},'Other');state.serviceMusic.playing=true;a.paused=false;
 renderServiceSlotMusic({service,item});check(a.src==='other.mp3'&&!a.paused,'render interrupted music');
 check(state.serviceMusic.repeatAllowed,'other repeat disabled');
 a.play=function(){this.paused=false;return Promise.resolve()};await runServiceMusicAction('toggle',binding);check(a.src===source&&!a.loop&&!state.serviceMusic.repeatAllowed,'source switch');
 check(!renderServiceMusicPlayer().includes('data-service-music-action="repeat"'),'sidebar repeat');
 runServiceMusicAction('stop',binding);
 for(const theme of ['light','dark']){document.body.dataset.theme=theme;for(const width of [254,390,1000]){m.style.width=width+'px';check(m.scrollWidth<=width,'overflow '+width);}}
 clearServiceMusicSyncTimer();return 'PASS common player, preload, state, cancellation, source isolation, repeat disabled, volume, widths';
}'''), flush=True)
            page.locator('#music-test').screenshot(path='/tmp/mindex-prayer-controls-'+engine+'.png')
            browser.close()
finally:
    server.shutdown()
