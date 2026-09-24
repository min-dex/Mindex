from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    page = browser.new_page()
                    page.route('**/*supabase*/**', lambda r: r.abort())
                    page.goto(url+'?output=presenter', wait_until='domcontentloaded')
                    page.wait_for_selector('#presenterOutputRoot', state='attached')
                    page.evaluate('''async () => {
                      window.originalPlay=HTMLMediaElement.prototype.play;
                      window.calls=0;
                      // Model the browser refusing the first audible autoplay attempt.
                      HTMLMediaElement.prototype.play=function(){calls++;this.autoplay=false;return Promise.reject(new DOMException('blocked','NotAllowedError'))};
                      window.payload={serviceId:'start-test',index:0,chromakey:true,slides:[{id:'first',type:'video',elementType:'video',layout:'media',videoSrc:'assets/presenter/chromakey-ready-loop-pingpong.mp4',playback:{autoplay:true,muted:false,controls:false}}]};
                      renderPresenterOutput(payload);
                      await Promise.resolve();await Promise.resolve();
                      window.video=document.querySelector('.is-active video');
                      if(calls!==1 || video.controls || video.muted)throw Error('first-start recovery or audio changed');
                      if(presenterOutputVideoHealth(payload).status!=='blocked')throw Error('blocked state not distinguished');
                      renderPresenterOutput(payload);
                      if(calls!==1 || video!==document.querySelector('.is-active video'))throw Error('repeated autoplay or replaced video');
                      HTMLMediaElement.prototype.play=originalPlay;
                    }''')
                    page.keyboard.down('Space')
                    page.wait_for_function('!video.paused && video.currentTime > .1')
                    page.keyboard.down('Space')
                    assert page.evaluate("video===document.querySelector('.is-active video')"), 'held recovery key advanced slide'
                    page.keyboard.up('Space')
                    assert page.evaluate("!video.controls && !video.muted && !video.dataset.autoplayBlocked")
                    page.evaluate('''async () => {
                      video.pause();
                      window.calls=0;
                      HTMLMediaElement.prototype.play=function(){calls++;return originalPlay.call(this)};
                      const manual={...payload,index:0,slides:[{...payload.slides[0],id:'manual',playback:{autoplay:false,muted:false,controls:true}}]};
                      renderPresenterOutput(manual);
                      if(calls!==0)throw Error('manual playback forced');
                      const key={key:' ',target:document.body};
                      const v=document.querySelector('.is-active video');
                      Object.defineProperty(v,'readyState',{configurable:true,value:4});
                      Object.defineProperty(v,'paused',{configurable:true,value:false});
                      if(handlePresenterVideoRecoveryKey(key))throw Error('healthy space hijacked');
                      delete v.readyState;delete v.paused;
                      if(handlePresenterVideoRecoveryKey({...key,ctrlKey:true}))throw Error('modified space hijacked');
                      const old=document.querySelector('.is-active video');
                      old.play=()=>new Promise((resolve,reject)=>window.rejectLate=reject);
                      const pending=requestPresenterVideoPlayback(old);
                      renderPresenterOutput({...payload,slides:[{id:'text',type:'title-assignee',elementType:'title_assignee',layout:'lower-bar-text',title:'Next'}]});
                      rejectLate(new DOMException('blocked','NotAllowedError'));await pending;
                      if(document.querySelector('.is-active video'))throw Error('late rejection restored old video');
                      HTMLMediaElement.prototype.play=originalPlay;
                    }''')
                    print('PASS', engine, 'first-start policy rejection simulation, gesture recovery, audio preserved, no duplicate start, manual mode, stale rejection')
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
