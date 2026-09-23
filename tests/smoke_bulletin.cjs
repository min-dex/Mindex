/* Offline integration test: no production connections or artifact files. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium}=require('playwright');
const {PDFDocument}=require('pdf-lib');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file=path.resolve(root,pathname==='/'?'index.html':pathname.slice(1));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||fs.statSync(file).isDirectory()){res.writeHead(404);res.end();return;}
  const types={'.html':'text/html','.js':'application/javascript','.mjs':'application/javascript','.css':'text/css','.woff2':'font/woff2','.svg':'image/svg+xml','.webp':'image/webp'};
  res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');
  let bytes=fs.readFileSync(file);
  if(pathname==='/'||pathname==='/index.html')bytes=Buffer.from(bytes.toString().replace(/window\.MINDEX_SUPABASE = \{[\s\S]*?\};/,'window.MINDEX_SUPABASE = null;'));
  res.end(bytes);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,...(process.env.BULLETIN_CHROME?{executablePath:process.env.BULLETIN_CHROME}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
    await page.goto(base);
    await page.waitForFunction(()=>typeof window.MindexBulletin?.mount==='function'&&typeof state!=='undefined');
    await page.evaluate(()=>{
      const id='11111111-1111-4111-8111-111111111111';
      window.bulletinTest={id,reads:0,writes:0,fail:false,prayer:'교회력 기도자',sermon:'DB에서 읽은 설교'};
      const b=window.bulletinTest;
      saveService=async()=>{b.writes++;return true;};
      const service={id,service_type_id:'young-adult',service_date:'2026-09-20',title:'청년부',worship_leader:'인도자'};
      window.bulletinSaved={service,sections:[
        {id:'s',service_id:id,section_key:'praise',title:'찬양',sort_order:1},
        {id:'p',service_id:id,section_key:'prayer',title:'대표기도',sort_order:2},
        {id:'w',service_id:id,section_key:'sermon',title:'설교',sort_order:3}],elements:[
        {id:'song-element',section_id:'s',sort_order:1,element_type:'praise',song_id:'song'},
        {id:'prayer-element',section_id:'p',sort_order:1,element_type:'title_person',person:'예배 기도자'},
        {id:'sermon-element',section_id:'w',sort_order:1,element_type:'title_person',title:b.sermon,source_ref:{slotKey:'sermon.title'}}]};
      worshipAtomicClient=async()=>({read:async(sid,options)=>{
        if(options.adopt!==false)throw new Error('Bulletin must not adopt the Presenter baseline');
        b.reads++;if(b.fail)throw new Error('테스트 DB 연결 실패');
        const copy=structuredClone(window.bulletinSaved);copy.elements[2].title=b.sermon;return copy;
      }});
      state.client={supabaseUrl:'https://offline-bulletin.test',from(table){
        const query={select(){return this;},in(){return this;},gte(){return this;},lte(){return this;},order(){return this;},
          then(resolve){return Promise.resolve({data:table==='mindex_songs'?[{id:'song',title:'연결된 DB 찬양',hymn_no:309}]:
            table==='mindex_worship_services'?[{id:'exception',service_type_id:'young-adult',service_date:'2026-09-27',service_alias:'연합예배',source_ref:{no_gathering:true}}]:table==='mindex_sunday_calendar'?[{date:'2026-09-20',young_adult_prayer:b.prayer,liturgical:'교회력 명칭',church_schedule:'DB 일정'},
              {date:'2026-09-27',young_adult_prayer:'다음 기도자'}]:[],error:null}).then(resolve);}};return query;
      }};
      state.module='presenter';state.serviceTypes=[{id:'young-adult',name:'청년부',display_name:'청년부'}];
      state.services=[normalizeWorshipService(service)];state.selectedServiceId=id;state.selectedServiceTypeId='young-adult';
      state.serviceError='';state.serviceItems[id]=[{id:'unsaved',service_id:id,label:'설교',raw_title:'UNSAVED PRESENTER DRAFT',assignee:'담당자',sort_order:1,memo:JSON.stringify({elementType:'title_person',inputMode:'text'})}];state.dirty.service=true;
      state.loadedWorshipServiceIds.add(id);
      if(!renderServicePresenterControls(state.services[0],[],false,0).includes('data-service-bulletin-action="open"'))throw new Error('Missing entry');
      runServiceBulletinAction('open',id);
    });
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]')?.disabled);
    const sheetBox=await page.locator('.bulletin-sheet').first().boundingBox();
    assert.ok(Math.abs(sheetBox.width/sheetBox.height-297/210)<.01,'Preview must retain A4 aspect ratio despite global icon CSS');
    assert.match(await page.locator('.bulletin-canvas').textContent(),/연결된 DB 찬양/);
    assert.match(await page.locator('.bulletin-canvas').textContent(),/교회력 기도자/);
    assert.match(await page.locator('.bulletin-canvas').textContent(),/9월 27일.*NEXT.*연합예배/);
    assert.equal(await page.locator('[data-bulletin-field="issue"]').inputValue(),'26');
    assert.ok(!(await page.locator('.bulletin-canvas').textContent()).includes('UNSAVED'));
    await page.locator('[data-bulletin-field="church"]').fill('샘플 교회');
    await page.locator('[data-bulletin-field="news"]').fill('이번 주 소식\n다음 주 소식');
    await page.locator('[data-bulletin-field="news"]').press('Control+s');
    await page.evaluate(()=>saveAll());
    assert.equal(await page.evaluate(()=>window.bulletinTest.writes),0,'Global Save must not save Presenter while Bulletin is open');
    await page.evaluate(()=>{window.bulletinTest.sermon='갱신된 설교';});
    await page.locator('[data-bulletin-refresh]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-canvas').textContent.includes('갱신된 설교'));
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'이번 주 소식\n다음 주 소식');
    await page.locator('[data-bulletin-mode="layout"]').click();
    await page.locator('[data-bulletin-frame]').selectOption('news');
    const input=page.locator('[data-bulletin-dimension="x"]');
    await input.fill('13.1');await input.press('Tab');
    assert.equal(await input.inputValue(),'12.5');
    await page.locator('[data-bulletin-undo]').click();assert.equal(await input.inputValue(),'10');
    await page.locator('[data-bulletin-redo]').click();assert.equal(await input.inputValue(),'12.5');
    await page.locator('[data-bulletin-reset-layout]').click();assert.equal(await input.inputValue(),'10');
    await page.locator('[data-bulletin-undo]').click();assert.equal(await input.inputValue(),'12.5');

    await page.locator('[data-bulletin-mode="content"]').click();
    await page.locator('[data-bulletin-field="news"]').fill('넘침 검사 문구 '.repeat(200));
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.locator('[data-bulletin-field="news"]').fill('이번 주 소식\n다음 주 소식');
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>runServiceBulletinAction('open',window.bulletinTest.id));
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]')?.disabled);
    assert.equal(await page.locator('[data-bulletin-field="church"]').inputValue(),'샘플 교회');
    assert.equal(await page.evaluate(()=>state.serviceItems[window.bulletinTest.id].find(item=>item.id==='unsaved')?.raw_title),'UNSAVED PRESENTER DRAFT');
    await page.evaluate(()=>{window.bulletinTest.fail=true;});await page.locator('[data-bulletin-refresh]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 연결 실패'));
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.evaluate(()=>{window.bulletinTest.fail=false;});await page.locator('[data-bulletin-refresh]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]')?.disabled);
    await page.locator('[data-bulletin-profile]').click();
    assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('mindex.bulletin.profiles:https://offline-bulletin.test'))[0].fields.church),'샘플 교회');
    await page.locator('[data-bulletin-setting="rosterMonth"]').fill('2026-08');
    await page.locator('[data-bulletin-setting="rosterMonth"]').press('Tab');
    await page.waitForFunction(()=>document.querySelector('.bulletin-canvas').textContent.includes('8월 30일'));
    await page.locator('[data-bulletin-setting="rosterMonth"]').fill('2026-09');
    await page.locator('[data-bulletin-setting="rosterMonth"]').press('Tab');
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    await page.locator('[data-bulletin-mode="layout"]').click();
    for(const [theme,file] of Object.entries({aurora:'26-A1.png',lent:'26-A2.png',palm:'26-S4.png',pentecost:'26-S6.png',stars:'26-A3.png'})) {
      await page.locator('[data-bulletin-setting="theme"]').selectOption(theme);
      assert.match(await page.locator('.bulletin-sheet').first().locator(':scope > image').first().getAttribute('href'),new RegExp('/'+file.replace('.','\\.')+'$'));
      assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),false);
    }
    await page.locator('[data-bulletin-setting="theme"]').selectOption('pentecost');
    await page.locator('[data-bulletin-frame]').selectOption('notes');
    await page.locator('[data-bulletin-hidden]').uncheck();
    await page.locator('[data-bulletin-mode="content"]').click();
    assert.equal(await page.locator('[data-frame-id="notes"]').count(),0);
    await page.locator('[data-bulletin-print]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-print-frame')?.contentDocument?.querySelectorAll('svg').length===2);
    assert.match(await page.evaluate(()=>document.querySelector('.bulletin-print-frame').contentDocument.querySelector('svg>image').getAttribute('href')),/26-S6\.png$/);
    assert.equal(await page.evaluate(()=>document.querySelector('.bulletin-print-frame').contentDocument.querySelectorAll('[data-frame-id="notes"]').length),0);
    const markup=await page.evaluate(()=>document.querySelector('.bulletin-print-frame').contentDocument.documentElement.outerHTML);
    const printing=await browser.newPage();await printing.setContent(markup);await printing.evaluate(()=>document.fonts.ready);
    const bytes=await printing.pdf({preferCSSPageSize:true,printBackground:true});
    const pdf=await PDFDocument.load(bytes);assert.equal(pdf.getPageCount(),2);
    await printing.close();
    await page.evaluate(async()=>{
      const host=document.getElementById('detailPane');host.replaceChildren();
      const source=window.MindexBulletin.resolveSource({...window.bulletinSaved,service:{...window.bulletinSaved.service,id:'next-bulletin',service_date:'2026-10-04'}});
      window.MindexBulletin.mount(host,{serviceId:source.id,scope:'https://offline-bulletin.test',services:[{id:source.id,label:'다음 주보'}],loadSource:async()=>source,onClose(){}});
    });
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-field="church"]')?.value==='샘플 교회');
    assert.equal(await page.locator('[data-bulletin-field="issue"]').inputValue(),'','Unknown future issue must not be guessed');
    assert.deepEqual(errors,[]);
    if(process.env.BULLETIN_LIVE_STDIN) {
      const snapshot=JSON.parse(fs.readFileSync(0,'utf8'));
      const result=await page.evaluate(async data=>{
        const source=window.MindexBulletin.resolveSource(data);
        const host=document.getElementById('detailPane');host.replaceChildren();
        window.MindexBulletin.mount(host,{serviceId:source.id,scope:'live-read-review',
          services:[{id:source.id,label:source.date+' · 청년부'}],loadSource:async()=>source,onClose(){}});
        await window.MindexBulletin.readyAssets();
        const rendered=window.MindexBulletin.renderPages({source,fields:{},frames:window.MindexBulletin.defaultFrames()},'print',null);
        return {orderRows:source.order.length,prayers:source.prayers.length,issues:[...rendered.issues]};
      },snapshot);
      assert.deepEqual(result.issues,[],'Real saved service must fit default frames');
      await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]')?.disabled);
      console.log('LIVE_READ:'+JSON.stringify(result));
    }
    if(process.env.BULLETIN_THEME_IMAGE){
      await page.locator('[data-bulletin-mode="layout"]').click();
      for(const theme of ['palm','pentecost']) {
        await page.locator('[data-bulletin-setting="theme"]').selectOption(theme);
        await page.locator('[data-bulletin-mode="content"]').click();
        console.log('IMAGE:'+(await page.locator('.bulletin-sheet').first().screenshot({type:'jpeg',quality:80})).toString('base64'));
        await page.locator('[data-bulletin-mode="layout"]').click();
      }
    }
    if(process.env.BULLETIN_SMOKE_IMAGE){
      console.log('IMAGE:'+ (await page.screenshot({type:'jpeg',quality:80})).toString('base64'));
      console.log('IMAGE:'+ (await page.locator('.bulletin-sheet').nth(1).screenshot({type:'jpeg',quality:80})).toString('base64'));
    }
    console.log('PASS app entry, committed DB binding, prayer precedence, preserved Presenter draft, refresh, local draft restoration, grid, undo/redo, overflow, load failure and two-page PDF');
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
