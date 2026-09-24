"""The default waiting video is a playable forward-and-reverse loop."""
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url + "?output=presenter", wait_until="domcontentloaded")
            state = page.evaluate("""async () => {
              const video = document.createElement('video');
              video.muted = true;
              video.src = 'assets/presenter/chromakey-ready-loop-pingpong.mp4';
              document.body.append(video);
              await new Promise((resolve, reject) => {
                video.addEventListener('loadedmetadata', resolve, { once: true });
                video.addEventListener('error', () => reject(video.error?.message || 'video error'), { once: true });
              });
              const frame = async time => {
                video.currentTime = time;
                await new Promise(resolve => video.addEventListener('seeked', resolve, { once: true }));
                const canvas = document.createElement('canvas');
                canvas.width = 16; canvas.height = 9;
                canvas.getContext('2d').drawImage(video, 0, 0, 16, 9);
                return [...canvas.getContext('2d').getImageData(0, 0, 16, 9).data];
              };
              const forward = await frame(1);
              const reverse = await frame(video.duration - 1);
              const averageDifference = forward.reduce((total, value, index) => total + Math.abs(value - reverse[index]), 0) / forward.length;
              const result = { duration: video.duration, width: video.videoWidth, height: video.videoHeight, averageDifference };
              video.remove();
              return result;
            }""")
            assert 39 <= state["duration"] <= 41, state
            assert state["width"] > 0 and state["height"] > 0, state
            assert state["averageDifference"] < 12, state
            print("PASS ping-pong waiting video", state, flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
