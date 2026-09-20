"""A file above the storage limit should get an actionable Korean message."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof presenterMediaUploadErrorMessage === 'function'")
            result = page.evaluate("""() => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const big = { size: 100 * 1024 * 1024 };
              const tooLarge = presenterMediaUploadErrorMessage({ statusCode: '413', message: 'The object exceeded the maximum allowed size' }, big);
              check(tooLarge.includes('50MB') && tooLarge.includes('100MB') && tooLarge.includes('공개 링크'), 'size limit message: ' + tooLarge);
              check(presenterMediaUploadErrorMessage({ message: 'Payload too large' }).includes('50MB'), 'message-only detection');
              check(presenterMediaUploadErrorMessage({ message: 'permission denied' }) === 'permission denied', 'other errors pass through');
              check(presenterMediaUploadErrorMessage(null) === '미디어 파일을 올리지 못했습니다.', 'empty error fallback');
              return 'ok';
            }""")
            assert result == 'ok', result
            print('PASS storage size limit gets an actionable message', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
