"""Check reading time, pause/dismiss controls, and queued toast delivery."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ("chrome", "webkit"):
                browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.route("**/*supabase*/**", lambda route: route.abort())
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("typeof toastDisplayDuration === 'function' && typeof toastLines === 'function' && Boolean(refs.toastRegion)")
                print(engine, page.evaluate("""async () => {
                  const check=(value,message)=>{if(!value)throw Error(message)};
                  const originalSet=window.setTimeout,originalClear=window.clearTimeout;
                  const timers=new Map();let now=0,id=1000000;
                  const tick=ms=>{now+=ms;for(const [key,timer] of [...timers])if(timer.at<=now){timers.delete(key);timer.fn();}};
                  for(const toast of refs.toastRegion.children)originalClear(toast.removeTimer);
                  refs.toastRegion.replaceChildren();
                  window.setTimeout=(fn,delay)=>{timers.set(++id,{fn,at:now+delay});return id};
                  window.clearTimeout=key=>timers.delete(key);
                  try {
                    check(toastLines('반영 완료', '', ['2개 건너뜀', null], '저장 필요')==='반영 완료\\n2개 건너뜀\\n저장 필요','toast lines');
                    check(toastDisplayDuration('저장했습니다.')===4000,'save duration');
                    check(toastDisplayDuration('연결 오류','error')===6000,'error duration');
                    check(toastDisplayDuration('일반 안내')===2000,'info duration');
                    check(toastDisplayDuration('저장 '+ '긴'.repeat(300))===10000,'long duration');
                    showToast('저장했습니다.');
                    const first=refs.toastRegion.firstElementChild;
                    tick(3200);check(first.isConnected,'old premature timeout');
                    first.dispatchEvent(new MouseEvent('mouseenter'));
                    tick(30000);check(first.isConnected,'hover did not pause');
                    first.dispatchEvent(new MouseEvent('mouseleave'));
                    tick(3999);check(first.isConnected,'resume too early');
                    tick(1);check(!first.isConnected,'resume did not expire');
                    showToast('저장 실패','error');
                    const error=refs.toastRegion.firstElementChild;
                    const button=error.querySelector('button');button.focus();
                    tick(20000);check(error.isConnected,'keyboard focus did not pause');
                    button.blur();await Promise.resolve();tick(6000);
                    check(!error.isConnected,'blur did not resume');
                    for(const message of ['저장 A','저장 B','저장 C','저장 D'])showToast(message);
                    check(refs.toastRegion.children.length===4,'early eviction');
                    const queued=refs.toastRegion.lastElementChild;
                    check(queued.hidden && timers.size===3,'queue timer started before display');
                    refs.toastRegion.firstElementChild.querySelector('button').click();
                    check(!queued.hidden && timers.size===3,'close did not advance queue');
                    tick(2000);showToast('저장 D');
                    check(refs.toastRegion.children.length===3,'duplicate toast');
                    tick(2000);check(queued.isConnected,'duplicate timer not renewed');
                    tick(2000);check(!queued.isConnected,'renewed toast never expires');
                    showToast('저장 안내\\n<script>위험</script> '+ '긴문장'.repeat(80));
                    const long=refs.toastRegion.firstElementChild;
                    check(!long.querySelector('script'),'unsafe text rendering');
                    check(long.querySelector('.toast-close svg'),'close icon missing');
                    check(long.querySelector('.toast-message').textContent.includes('\\n'),'line breaks lost');
                    const rect=long.getBoundingClientRect();
                    check(rect.left>=0 && rect.right<=innerWidth,'mobile overflow');
                    check(long.scrollWidth<=long.clientWidth+1,'message overflow');
                    return 'PASS duration, hover/focus pause, dismissal, queue, duplicates, wrapping';
                  } finally {
                    refs.toastRegion.replaceChildren();
                    window.setTimeout=originalSet;window.clearTimeout=originalClear;
                  }
                }"""), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
