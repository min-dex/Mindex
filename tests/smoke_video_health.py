from pathlib import Path
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def run(browser, url, engine):
    context = browser.new_context()
    context.route('**/*supabase*/**', lambda route: route.abort())
    controller = context.new_page()
    controller.goto(url, wait_until='domcontentloaded')
    controller.wait_for_function("typeof requestPresenterVideoRetry === 'function'")
    controller.evaluate('''() => {
      state.presenter.serviceId='video-health-test';
      state.presenter.index=0;
      state.presenter.safetyBlank=false;
      state.presenter.liveScripture=null;
      markPresenterOutputConnected=()=>{};
      restorePresenterControllerSession=()=> 'restored';
      const host=document.createElement('div');
      host.className='svc-presenter-video-health';
      host.dataset.presenterVideoHealth='';host.dataset.serviceId='video-health-test';
      document.body.append(host);
      bindDetailInteractionRoot(host);
      window.fixture={serviceId:'video-health-test',serviceType:'sunday-afternoon',chromakey:true,
        slides:[{id:'video',type:'video',elementType:'video',layout:'media',
          videoSrc:'probe-health.mp4',playback:{autoplay:true,muted:true,loop:true}}],
        index:0,safetyBlank:false,updatedAt:Date.now()};
      publishPresenterPayload(fixture,{force:true});
    }''')
    output = context.new_page()
    failed = True

    def media(route):
        if failed:
            route.abort()
        else:
            route.fulfill(path=str(Path(__file__).resolve().parents[1] / 'assets/presenter/chromakey-ready-loop-pingpong.mp4'), content_type='video/mp4')

    output.route('**/probe-health.mp4', media)
    output.goto(url+'?output=presenter', wait_until='domcontentloaded')
    controller.wait_for_function("state.presenter.videoHealth?.status === 'error'")
    assert controller.locator('[data-presenter-video-health]').inner_text().strip() == '영상 재생 실패', repr(controller.locator('[data-presenter-video-health]').inner_text())
    output.evaluate('''() => {
      window.video=document.querySelector('.is-active video');
      window.loads=0;const load=video.load.bind(video);
      video.load=()=>{loads++;return load()};
    }''')
    failed = False
    controller.click('[data-presenter-action="retry-video"]')
    controller.wait_for_function("state.presenter.videoHealth?.status === 'playing'")
    output.wait_for_function('video.currentTime > .2')
    assert output.evaluate('loads') == 1, 'two transports must not reload twice'
    assert controller.locator('[data-presenter-video-health]').inner_text() == ''
    controller.evaluate('publishPresenterPayload({...fixture,updatedAt:Date.now()},{force:true})')
    output.wait_for_timeout(200)
    assert output.evaluate("video === document.querySelector('.is-active video') && loads === 1 && !video.paused")
    # A delayed request cannot restart healthy playback or a different frame.
    output.evaluate('''async () => {
      const payload={serviceId:'video-health-test',index:0};
      const health=presenterOutputVideoHealth(payload);
      await retryPresenterOutputVideo(health,payload);
      if(loads!==1)throw Error('healthy video reloaded');
      video.pause();
      await retryPresenterOutputVideo({...health,frameKey:'stale'},payload);
      if(!video.paused)throw Error('stale retry affected new frame');
    }''')
    controller.wait_for_function("state.presenter.videoHealth?.status === 'paused'")
    before = output.evaluate('video.currentTime')
    controller.click('[data-presenter-action="retry-video"]')
    output.wait_for_function('!video.paused')
    assert output.evaluate('video.currentTime') >= before
    assert output.evaluate('loads') == 1
    # A browser-policy rejection gets a local gesture recovery, never forced mute.
    output.evaluate('''async () => {
      video.pause();
      const play=video.play;
      video.play=()=>Promise.reject(new DOMException('blocked','NotAllowedError'));
      const payload={serviceId:'video-health-test',index:0};
      await retryPresenterOutputVideo(presenterOutputVideoHealth(payload),payload);
      video.play=play;
      if(video.controls || video.dataset.autoplayBlocked!=='true')throw Error('blocked state or unexpected controls');
    }''')
    controller.wait_for_function("state.presenter.videoHealth?.status === 'blocked'")
    # Status updates do not replace their subtree when the status is unchanged.
    for width in [240, 320]:
        controller.evaluate('''width => {
          const host=document.querySelector('[data-presenter-video-health]');
          host.style.width=width+'px';
          const text=host.querySelector('span').getBoundingClientRect();
          const button=host.querySelector('button').getBoundingClientRect();
          if(text.right>button.left || button.right>host.getBoundingClientRect().right+1)throw Error('status overlap');
        }''', width)
        controller.locator('[data-presenter-video-health]').screenshot(path=f'/private/tmp/video-health-{engine}-{width}.png')
    controller.evaluate('''() => {
      syncPresenterVideoHealthControl();
      const before=document.querySelector('[data-presenter-video-health]').firstChild;
      syncPresenterVideoHealthControl();
      if(before!==document.querySelector('[data-presenter-video-health]').firstChild)throw Error('health churn');
      state.presenter.index=1;syncPresenterVideoHealthControl();
      if(document.querySelector('[data-presenter-video-health]').textContent)throw Error('stale status');
    }''')
    output.evaluate('''() => {
      presenterOutputVideoWarmupCache.clear();
      const slides=[
        {id:'current',type:'text',elementType:'title-content',layout:'text'},
        {id:'next-video',type:'video',elementType:'video',layout:'media',videoSrc:'next-video.mp4'},
        {id:'later-video',type:'video',elementType:'video',layout:'media',videoSrc:'later-video.mp4'},
      ];
      warmPresenterOutputNextVideo({slides,index:0});
      if(!presenterOutputVideoWarmupCache.has('next-video.mp4'))throw Error('next video metadata was not warmed');
      if(presenterOutputVideoWarmupCache.has('later-video.mp4'))throw Error('more than one future video was warmed');
      clearPresenterOutputVideoWarmup();
      if(presenterOutputVideoWarmupCache.size)throw Error('video warmup cache was not released');
    }''')
    print('PASS', engine, 'failure reporting, explicit retry, dual-channel dedup, healthy reuse, stale guard, resume, autoplay recovery, status stability')
    context.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ['chromium', 'webkit']:
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    run(browser, url, engine)
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
