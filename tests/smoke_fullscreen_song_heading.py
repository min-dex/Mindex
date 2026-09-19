from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chrome', 'webkit'):
                browser = launch_chromium(p) if engine == 'chrome' else p.webkit.launch()
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                page.route('**/*supabase*/**', lambda route: route.abort())
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_function("typeof renderPresenterSlideFrame === 'function'")
                result = page.evaluate('''() => {
                  const root=document.createElement('div');
                  root.className='presenter-output-root no-chromakey';
                  document.body.append(root);
                  let checked=0;
                  for(const width of [406,1280,1920]) {
                    root.style.cssText=`position:fixed;inset:0;width:${width}px;height:${width*9/16}px;container-type:size;z-index:99999`;
                    for(const label of ['입례찬양','결단찬양','봉헌찬양','파송찬양','찬양 1']) {
                      const slide={type:'title-assignee',elementType:PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
                        layout:PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,orderTitle:label,title:label,
                        label,songTitle:'하늘 보좌',contentTitle:'하늘 보좌',songDetail:'Original title'};
                      const before=JSON.stringify(slide);
                      root.innerHTML=renderPresenterSlideFrame(slide,{noChromakey:true});
                      const heading=root.querySelector('.presenter-fullscreen-song-heading');
                      const title=root.querySelector('.presenter-title-content-title');
                      const detail=root.querySelector('.presenter-fullscreen-song-detail');
                      if(detail?.textContent!=='Original title') throw Error('Missing song detail');
                      const detailSize=parseFloat(getComputedStyle(detail).fontSize),headingSize=parseFloat(getComputedStyle(heading).fontSize);
                      if(Math.abs(detailSize-75*width/1920)>.1 || getComputedStyle(detail).fontWeight!=='700' || getComputedStyle(title).fontWeight!=='800') throw Error('Incorrect type hierarchy');
                      // Output headings omit order numbers (b088437a): '찬양 1' renders as '찬양'.
                      if(heading?.textContent!==label.replace(/\s*\d+$/,'') || !title?.textContent.includes('하늘 보좌')) throw Error('Missing title');
                      const h=heading.getBoundingClientRect(),t=title.getBoundingClientRect(),r=root.getBoundingClientRect();
                      if(h.height<=0 || h.bottom>t.top+1 || h.left<r.left-1 || h.right>r.right+1 || t.bottom>r.bottom+1) throw Error('Clipped or overlapping: '+label+' '+width);
                      const d=detail.getBoundingClientRect();
                      if(d.top<t.bottom-1 || d.bottom>r.bottom+1) throw Error('Detail overlap');
                      if(JSON.stringify(slide)!==before) throw Error('Source mutated');
                      if(renderPresenterSlideFrame(slide,{}).includes('presenter-fullscreen-song-heading')) throw Error('Chromakey changed');
                      checked++;
                    }
                  }
                  const special=presenterSpecialSongSectionTitleSlide({label:'봉헌특송',assignee:'찬양대'}, {},0);
                  const html=renderPresenterSlideFrame(special,{noChromakey:true});
                  if(!html.includes('찬양대') || html.includes('presenter-fullscreen-song-heading')) throw Error('Special assignee changed');
                  if(presenterSongTitleDetail({title:'나 이제 주님의 새 생명 얻은 몸',hymn_no:'436'},{name:'새찬송가'})!=='새찬송가 436장') throw Error('Hymn detail');
                  if(presenterSongTitleDetail({original_title:'Original',subtitle:'Subtitle'})!=='Original') throw Error('Original precedence');
                  if(presenterSongTitleDetail({original_title:' ',subtitle:'Subtitle'})!=='Subtitle') throw Error('Subtitle fallback');
                  if(presenterSongTitleDetail({title:'Only title'})!=='') throw Error('Empty detail');
                  for(const label of ['특송','봉헌특송']) {
                    const item={id:'special-fixture',label,assignee:'이연약구역 일동'};
                    const section={sectionKey:label==='특송'?'special_song':'offering',sectionLabel:label};
                    const song={title:'나 이제 주님의 새 생명 얻은 몸',hymn_no:'436'};
                    const titleSlide=presenterSongTitleSlide(item,section,song,{name:'새찬송가'},song.title,0);
                    if(!titleSlide.songTitleContent || 'fullscreenSongName' in titleSlide || 'songDetail' in titleSlide) throw Error('Legacy fields generated');
                    const slides=presenterSlidesWithSpecialSongTitle(item,section,[titleSlide],0,{type_id:'sunday-second'});
                    if(slides.length!==2) throw Error('Special title sequence lost');
                    if(slides[1].songTitleContent.orderTitle!=='' || 'omitFullscreenOrderTitle' in slides[1]) throw Error('Layout flag generated');
                    const repeated=presenterSlidesWithSpecialSongTitle(item,section,slides,0,{type_id:'sunday-second'});
                    if(repeated.length!==2) throw Error('Repeated composition duplicated title');
                    if(!titleSlide.songTitleContent.orderTitle) throw Error('Original title data mutated');
                    const first=renderPresenterSlideFrame(slides[0],{noChromakey:true});
                    if(!first.includes(label)||!first.includes('이연약구역 일동')) throw Error('Missing special heading');
                    root.innerHTML=renderPresenterSlideFrame(slides[1],{noChromakey:true});
                    if(root.querySelector('.presenter-fullscreen-song-heading')) throw Error('Repeated special heading');
                    if(root.querySelector('.presenter-title-content-title').textContent.includes('436')) throw Error('Repeated hymn number');
                    if(root.querySelector('.presenter-fullscreen-song-detail').textContent!=='새찬송가 436장') throw Error('Missing hymn detail');
                    if(!renderPresenterSlideFrame(slides[1],{}).includes('436')) throw Error('Chromakey number removed');
                  }
                  for(const [song,expected] of [[{original_title:'Original',subtitle:'Subtitle'},'Original'],[{subtitle:'Subtitle'},'(Subtitle)'],[{original_title:' ',subtitle:'Subtitle'},'(Subtitle)']]) {
                    const slide=presenterSongTitleSlide({label:'찬양 1'},{}, {...song,title:'곡명'}, {},'곡명',0);
                    root.innerHTML=renderPresenterSlideFrame(slide,{noChromakey:true});
                    if(root.querySelector('.presenter-fullscreen-song-detail')?.textContent!==expected) throw Error('Detail punctuation');
                  }
                  return checked;
                }''')
                page.screenshot(path=f'/tmp/fullscreen-song-heading-{engine}.png')
                print('PASS fullscreen headings, layout, chromakey and special assignee', engine, result)
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
