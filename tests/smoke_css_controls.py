"""Check shared theme tokens and section-editor layout at narrow widths."""

import argparse
from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    server, url = start_local_app_server() if not args.url else (None, args.url)
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof renderPresenterSectionEditorItem === 'function'")
            page.evaluate("""() => {
              const service={id:'css-test', type_id:'sunday-main'};
              const items=[{id:'prayer',label:'공동기도',raw_title:'교회학교를 위해',assignee:'담당자',_origIndex:0},
                {id:'song',label:'찬양 1',raw_title:'찬양 제목',_origIndex:1}];
              const fixture=document.createElement('div'); fixture.id='cssFixture';
              fixture.innerHTML=`<div class="presenter-section-editor-layer"><section class="presenter-section-editor">
                <div class="presenter-section-editor-body"><div class="presenter-section-editor-list">
                ${items.map((item,i)=>renderPresenterSectionEditorItem(item,i,{service,sectionItems:items})).join('')}
                </div></div></section></div>
                <span class="svc-presenter-pin-track"></span><div class="cal-view"><span id="calTokenProbe" style="color:var(--cal-text)">달력</span></div>
                <div style="display:flex;flex-wrap:wrap;gap:8px">
                  <button class="svc-mode-tab" data-focus-probe>모드</button>
                  <button class="svc-output-action" data-focus-probe>출력</button>
                  <span class="svc-board-scale"><button data-focus-probe>크기</button></span>
                  <button class="svc-presenter-preparation-form" data-focus-probe>양식</button>
                  <button class="svc-music-name" data-focus-probe>음악</button>
                  <button class="svc-reference-media-add" data-focus-probe>파일</button>
                </div>
                <div class="svc-prep-editor">
                  <details class="svc-item-note" open>
                    <summary>추가 정보</summary>
                    <div class="svc-item-note-grid">
                      <label><span>담당</span><input value="담당자"></label>
                      <label><span>메모</span><textarea>내용</textarea></label>
                    </div>
                  </details>
                </div>`;
              document.body.append(fixture); refreshIcons(fixture);
            }""")
            for theme in ('light','dark'):
                page.evaluate('(theme)=>document.body.dataset.theme=theme',theme)
                for width in (1440, 800, 390):
                    page.set_viewport_size({'width':width,'height':900})
                    result=page.evaluate("""() => {
                      const fixture=document.getElementById('cssFixture');
                      const rows=[...fixture.querySelectorAll('.presenter-section-editor-item')];
                      const noteGrid=fixture.querySelector('.svc-item-note-grid');
                      const pin=getComputedStyle(fixture.querySelector('.svc-presenter-pin-track'),'::after');
                      const focusRings=[...fixture.querySelectorAll('[data-focus-probe]')].every(button=>{
                        button.focus();
                        const css=getComputedStyle(button);
                        return css.outlineStyle!=='none' && parseFloat(css.outlineWidth)>=2;
                      });
                      return {rowsFit:rows.every(row=>row.scrollWidth<=row.clientWidth+1),
                        fieldsFit:rows.every(row=>[...row.querySelectorAll('input,select,button')].every(el=>{
                          const r=el.getBoundingClientRect(),b=row.getBoundingClientRect();
                          return !r.width || r.left>=b.left-1 && r.right<=b.right+1;
                        })),
                        noteGridFits:noteGrid.scrollWidth<=noteGrid.clientWidth+1 && [...noteGrid.querySelectorAll('input,textarea')].every(el=>{
                          const r=el.getBoundingClientRect(),b=noteGrid.getBoundingClientRect();
                          return r.left>=b.left-1 && r.right<=b.right+1;
                        }),
                        pinVisible:pin.backgroundColor!=='rgba(0, 0, 0, 0)',
                        focusRings,
                        calendarToken:Boolean(getComputedStyle(fixture.querySelector('.cal-view')).getPropertyValue('--cal-text').trim())};
                    }""")
                    assert all(result.values()), (theme,width,result)
                    print('PASS CSS controls',theme,width,flush=True)
            page.screenshot(path='/tmp/mindex-css-controls-mobile.png')
            browser.close()
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    main()
