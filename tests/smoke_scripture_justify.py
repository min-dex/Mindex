from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url + '?output=presenter', wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterSlideFrame === 'function'")
            for width in [1920, 960, 320]:
                page.set_viewport_size({'width': width, 'height': round(width * 9 / 16)})
                for context in ['reading', 'sermon', 'citation', 'citation-chromakey', 'sermon-chromakey']:
                    result = page.evaluate("""async (context) => {
                      const lower = context.endsWith('chromakey');
                      const text = '하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니 이는 그를 믿는 자마다 멸망하지 않고 영생을 얻게 하려 하심이라';
                      const slide = {elementType:PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
                        layout:PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT, type:'scripture',
                        scriptureContext:context, referenceBook:'요한복음', referenceRange:'3:16',
                        scriptureVerse:16, title:'요한복음 3:16', text, citationBodyText:text};
                      document.body.innerHTML='<div id="fixture" class="presenter-output-root '+(lower?'':'no-chromakey')+'">'+renderPresenterSlideFrame(slide)+'</div>';
                      await document.fonts.ready;
                      const root=document.querySelector('#fixture');
                      fitPresenterChromakeyScriptureText(root);
                      const body=root.querySelector('.presenter-scripture-reading-text, .presenter-slide-text span');
                      const style=getComputedStyle(body);
                      const rect=body.getBoundingClientRect();
                      const node=body.firstChild;
                      const lines=[];
                      for(let i=0;i<node.length;i++){
                        if(/\s/.test(node.textContent[i])) continue;
                        const range=document.createRange();range.setStart(node,i);range.setEnd(node,i+1);
                        const r=range.getBoundingClientRect();
                        let line=lines.find(l=>Math.abs(l.top-r.top)<1);
                        if(!line){line={top:r.top,right:r.right};lines.push(line);}
                        line.right=Math.max(line.right,r.right);
                      }
                      const justified=lines.length<2 || Math.abs(lines[0].right-rect.right)<Math.max(2, parseFloat(style.fontSize)*.07);
                      const lastLeft=lines.length<2 || lines.at(-1).right<rect.right-2;
                      body.textContent='짧은 첫 줄\\n짧은 마지막 줄';
                      const range=document.createRange();range.setStart(body.firstChild,0);range.setEnd(body.firstChild,6);
                      const manualShort=range.getBoundingClientRect().width<rect.width*.8;
                      return {align:style.textAlign,last:style.textAlignLast,space:style.whiteSpace,
                        justified,lastLeft,manualShort};
                    }""", context)
                    assert result == {'align': 'justify', 'last': 'left', 'space': 'pre-wrap',
                                      'justified': True, 'lastLeft': True, 'manualShort': True}, (width, context, result)
                    if width == 960 and context == 'reading':
                        page.evaluate("""() => {
                          document.querySelector('.presenter-scripture-reading-text').textContent=
                            '하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니 이는 그를 믿는 자마다 멸망하지 않고 영생을 얻게 하려 하심이라';
                        }""")
                        page.screenshot(path='/tmp/mindex-scripture-justify.png')
            browser.close()
            print('PASS scripture justification, last/explicit lines at 1920/960/320 across 5 contexts')
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
