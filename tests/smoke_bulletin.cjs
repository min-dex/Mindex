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
    await page.evaluate(async()=>{
      const id='11111111-1111-4111-8111-111111111111';
      window.bulletinTest={id,reads:0,writes:0,fail:false,prayer:'교회력 기도자',sermon:'DB에서 읽은 설교'};
      const b=window.bulletinTest;
      b.drafts={};b.saves=0;
      loadBulletinDraft=async sid=>structuredClone(b.drafts[sid]||null);
      saveBulletinDraft=async(sid,value,revision)=>{
        if(b.saveFail)throw new Error('DB 저장 실패 테스트');
        if((b.drafts[sid]?.revision||0)!==revision)throw new Error('다른 곳에서 주보가 변경되었습니다');
        if(b.delaySave)await new Promise(resolve=>b.releaseSave=resolve);
        b.saves++;b.drafts[sid]={...structuredClone(value),service_id:sid,revision:revision+1};return structuredClone(b.drafts[sid]);
      };
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
      state.connectionError='';state.serviceError='';state.loadedWorshipPresenterServiceIds.add(id);state.serviceItems[id]=[{id:'unsaved',service_id:id,label:'설교',raw_title:'UNSAVED PRESENTER DRAFT',assignee:'담당자',sort_order:1,memo:JSON.stringify({elementType:'title_person',inputMode:'text'})}];state.dirty.service=true;
      state.loadedWorshipServiceIds.add(id);
      if(!renderServicePresenterControls(state.services[0],[],false,0).includes('data-service-bulletin-action="open"'))throw new Error('Missing entry');
      await runServiceBulletinAction('open',id);
    });
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    const sheetBox=await page.locator('.bulletin-sheet').first().boundingBox();
    assert.ok(Math.abs(sheetBox.width/sheetBox.height-297/210)<.01,'Preview must retain A4 aspect ratio despite global icon CSS');
    assert.match(await page.locator('.bulletin-canvas').textContent(),/연결된 DB 찬양/);
    assert.match(await page.locator('.bulletin-canvas').textContent(),/교회력 기도자/);
    assert.match(await page.locator('.bulletin-canvas').textContent(),/9월 27일.*NEXT.*연합예배/);
    assert.equal(await page.locator('[data-bulletin-field="issue"]').inputValue(),'26');
    assert.match(await page.locator('.bulletin-sheet').first().locator(':scope > image').first().getAttribute('href'),/26-A5\.png$/);
    const autoCases=await page.evaluate(()=>{
      const pick=(type,date,liturgical='')=>bulletinBackgroundForService({type_id:type,date},{date,liturgical})?.key;
      return [pick('young-adult','2026-09-20'),pick('young-adult','2026-07-05'),pick('friday','2026-09-25'),pick('children','2026-09-20'),pick('young-adult','2026-05-24','성령강림주일'),pick('young-adult','2026-03-29','종려주일'),pick('young-adult','2026-04-05','부활주일')];
    });
    assert.deepEqual(autoCases,['26-A5.png','26-A4.png','26-B5.png','26-C5.png','26-S6.png','26-S4.png','26-S5.png']);

    assert.equal(await page.evaluate(()=>state.module),'bulletin');
    assert.equal(await page.locator('[data-home-module="bulletin"]').getAttribute('aria-current'),'page');
    await page.locator('[data-bulletin-close]').click();
    await page.locator('[data-home-module="bulletin"]').click();
    await page.waitForFunction(()=>state.module==='bulletin'&&!state.presenterBulletinServiceId);
    assert.match(await page.locator('#detailPane').textContent(),/왼쪽 목록에서 주보를 선택/);
    await page.locator('[data-bulletin-open]').first().click();
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    assert.equal(await page.evaluate(()=>linkStateFromParams(readLinkParams()).module),'bulletin');
    console.log('PASS independent bulletin navigation, date list, selection and module route');
    assert.equal(await page.evaluate(()=>state.pageTabs.length),2,'Bulletin opens a separate app tab');
    assert.match(await page.locator('.page-tab.active').textContent(),/청년부 주보/);
    assert.equal(await page.evaluate(()=>linkStateFromParams(readLinkParams()).presenterBulletinServiceId),await page.evaluate(()=>bulletinTest.id));
    await page.locator('[data-bulletin-field="news"]').fill('탭 전환 전 편집');
    await page.evaluate(()=>activatePageTab(0));
    assert.equal(await page.locator('.bulletin-workbench').count(),0,'Presenter tab remains separate');
    await page.evaluate(()=>runServiceBulletinAction('open',bulletinTest.id));
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    assert.equal(await page.evaluate(()=>state.pageTabs.length),2,'Repeated opening reuses the bulletin tab');
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'탭 전환 전 편집');
    await page.locator('[data-bulletin-undo]').click();
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'');
    await page.locator('[data-bulletin-field="news"]').fill('탭 이동 중 저장');
    await page.evaluate(()=>bulletinTest.delaySave=true);
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>!!bulletinTest.releaseSave);
    await page.evaluate(()=>activatePageTab(0));
    await page.evaluate(()=>runServiceBulletinAction('open',bulletinTest.id));
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    await page.evaluate(()=>{bulletinTest.delaySave=false;bulletinTest.releaseSave();});
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 저장됨'),{},{timeout:3000});
    await page.evaluate(async()=>{
      const id='22222222-2222-4222-8222-222222222222';
      state.services.push({...state.services[0],id,date:'2026-09-27'});
      await runServiceBulletinAction('open',id);
    });
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    await page.locator('[data-bulletin-service]').selectOption(await page.evaluate(()=>bulletinTest.id));
    await page.waitForFunction(()=>state.pageTabIndex===1&&document.querySelector('[data-bulletin-print]')?.disabled===false);
    assert.equal(await page.evaluate(()=>state.pageTabs.filter(t=>t.snapshot.presenterBulletinServiceId===bulletinTest.id).length),1);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'탭 이동 중 저장');
    await page.evaluate(()=>closePageTab(2));
    console.log('PASS save completion across tab switches and existing bulletin selection without duplicates');
    console.log('PASS independent bulletin tab, route, reuse, unsaved text and undo across tab switches');

    assert.ok(!(await page.locator('.bulletin-canvas').textContent()).includes('UNSAVED'));
    await page.locator('[data-bulletin-field="church"]').fill('샘플 교회');
    assert.equal(await page.locator('[data-frame-id="insideChurch"]').textContent(),'샘플 교회');
    await page.locator('[data-bulletin-field="news"]').fill('이번 주 소식\n다음 주 소식');
    await page.locator('[data-bulletin-field="news"]').press('Control+s');
    await page.evaluate(()=>saveAll());
    await page.waitForFunction(()=>window.bulletinTest.saves>0);
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
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    assert.equal(await page.locator('[data-bulletin-field="church"]').inputValue(),'샘플 교회');
    assert.equal(await page.evaluate(()=>state.serviceItems[window.bulletinTest.id].find(item=>item.id==='unsaved')?.raw_title),'UNSAVED PRESENTER DRAFT');
    await page.evaluate(()=>{window.bulletinTest.fail=true;});await page.locator('[data-bulletin-refresh]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 연결 실패'));
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.evaluate(()=>{window.bulletinTest.fail=false;});await page.locator('[data-bulletin-refresh]').click();
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].content.fields.church),'샘플 교회');
    await page.locator('[data-bulletin-setting="rosterMonth"]').fill('2026-08');
    await page.locator('[data-bulletin-setting="rosterMonth"]').press('Tab');
    await page.waitForFunction(()=>document.querySelector('.bulletin-canvas').textContent.includes('8월 30일'));
    await page.locator('[data-bulletin-setting="rosterMonth"]').fill('2026-09');
    await page.locator('[data-bulletin-setting="rosterMonth"]').press('Tab');
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    await page.locator('[data-bulletin-mode="layout"]').click();
    assert.equal(await page.locator('[data-bulletin-setting="theme"]').inputValue(),'auto');
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].layout.background),'auto');
    await page.locator('[data-bulletin-setting="theme"]').selectOption('');
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('.bulletin-sheet').first().locator(':scope > image').count(),1,'No-background keeps only the logo');
    await page.locator('[data-bulletin-setting="theme"]').selectOption('auto');
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.match(await page.locator('.bulletin-sheet').first().locator(':scope > image').first().getAttribute('href'),/26-A5\.png$/);
    for(const file of ['26-A1.png','26-A2.png','26-A4.png','26-B1.png','26-S4.png','26-S6.png','26-A3.png']) {
      await page.locator('[data-bulletin-setting="theme"]').selectOption(file);
      await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
      assert.match(await page.locator('.bulletin-sheet').first().locator(':scope > image').first().getAttribute('href'),new RegExp('/'+file.replace('.','\\.')+'$'));
      assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),false);
    }
    await page.locator('[data-bulletin-setting="theme"]').selectOption('26-S6.png');
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
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
    // Failed/conflicting saves preserve recovery copy and never claim DB success.
    await page.locator('[data-bulletin-mode="content"]').click();
    await page.locator('[data-bulletin-field="news"]').fill('내가 수정한 원문 ③');
    await page.evaluate(()=>{window.bulletinTest.saveFail=true;});
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 저장 실패 테스트'));
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'내가 수정한 원문 ③');
    await page.evaluate(()=>{const b=window.bulletinTest;b.saveFail=false;b.drafts[b.id].revision++;b.drafts[b.id].content.fields.news='다른 기기에서 저장한 원문';});
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('다른 곳에서'));
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].content.fields.news),'다른 기기에서 저장한 원문');
    await page.locator('[data-bulletin-reload]').click();
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-field="news"]').value==='다른 기기에서 저장한 원문');
    await page.locator('[data-bulletin-local]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'내가 수정한 원문 ③');
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 저장됨'));
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].layout.background),'26-S6.png');
    // A clean browser-local state still loads the same content and layout from DB.
    await page.evaluate(()=>localStorage.clear());
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>runServiceBulletinAction('open',window.bulletinTest.id));
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'내가 수정한 원문 ③');
    assert.equal(await page.locator('[data-frame-id="notes"]').count(),0);
    assert.match(await page.locator('.bulletin-sheet').first().locator(':scope > image').first().getAttribute('href'),/26-S6\.png$/);
    await page.locator('[data-bulletin-field="news"]').fill('저장 요청 시점');
    await page.evaluate(()=>window.bulletinTest.delaySave=true);
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>!!window.bulletinTest.releaseSave);
    await page.locator('[data-bulletin-field="news"]').fill('저장 중에 계속 입력');
    await page.evaluate(()=>{window.bulletinTest.delaySave=false;window.bulletinTest.releaseSave();});
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-save]').disabled);
    assert.match(await page.locator('.bulletin-status').textContent(),/수정됨/);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'저장 중에 계속 입력');
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].content.fields.news),'저장 요청 시점');
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>document.querySelector('.bulletin-status').textContent.includes('DB 저장됨'));
    console.log('PASS DB save, failure recovery, revision conflicts, local recovery, clean-browser reload and edits during save');
    // Local storage is optional: quota/security failures must never mask or block DB work.
    await page.evaluate(()=>{
      window.bulletinStorage={set:Storage.prototype.setItem,get:Storage.prototype.getItem};
      Storage.prototype.setItem=function(key,value){if(key.startsWith('mindex.bulletin'))throw new DOMException('quota','QuotaExceededError');return window.bulletinStorage.set.call(this,key,value);};
    });
    await page.locator('[data-bulletin-field="news"]').fill('복구 공간이 없어도 DB 저장');
    assert.match(await page.locator('.bulletin-status').textContent(),/수정됨.*브라우저 임시 저장 불가/);
    assert.equal(await page.evaluate(()=>saveAll()),true);
    assert.match(await page.locator('.bulletin-status').textContent(),/DB 저장됨.*브라우저 임시 저장 불가/);
    await page.locator('[data-bulletin-field="news"]').fill('공간 부족 중 새 수정');
    await page.locator('[data-bulletin-reload]').click();
    await page.waitForFunction(()=>document.querySelector('[data-bulletin-field="news"]').value==='복구 공간이 없어도 DB 저장');
    await page.locator('[data-bulletin-local]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'공간 부족 중 새 수정');
    await page.evaluate(()=>{window.bulletinTest.saveFail=true;});
    assert.equal(await page.evaluate(()=>saveAll()),false);
    assert.match(await page.locator('.bulletin-status').textContent(),/DB 저장 실패 테스트/);
    await page.evaluate(()=>{
      window.bulletinTest.saveFail=false;
      Storage.prototype.getItem=function(key){if(key.startsWith('mindex.bulletin'))throw new DOMException('blocked','SecurityError');return window.bulletinStorage.get.call(this,key);};
    });
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>runServiceBulletinAction('open',window.bulletinTest.id));
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'복구 공간이 없어도 DB 저장');
    await page.evaluate(()=>Object.assign(Storage.prototype,{getItem:window.bulletinStorage.get,setItem:window.bulletinStorage.set}));
    // Invalid local shapes and metadata cannot break DB loading or replace its revision/identity.
    await page.evaluate(()=>{
      const key='mindex.bulletin.v1:https://offline-bulletin.test:'+window.bulletinTest.id;
      localStorage.setItem(key,JSON.stringify({version:3,fields:{news:'로컬'},frames:{},settings:{},savedAt:1}));
      localStorage.setItem(key+':recovery',JSON.stringify({fields:{news:'복구된 문구'},frames:[null,{id:'news',x:999}],settings:{},id:'wrong-id',revision:999,key:'wrong-key',savedAt:2}));
    });
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>runServiceBulletinAction('open',window.bulletinTest.id));
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    await page.locator('[data-bulletin-local]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'복구된 문구');
    assert.equal(await page.evaluate(()=>saveAll()),true);
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts[window.bulletinTest.id].content.fields.news),'복구된 문구');
    assert.equal(await page.evaluate(()=>window.bulletinTest.drafts['wrong-id']),undefined);
    // Newer local edits outrank an older recovery snapshot.
    await page.evaluate(()=>{
      const key='mindex.bulletin.v1:https://offline-bulletin.test:'+window.bulletinTest.id;
      localStorage.setItem(key,JSON.stringify({version:3,fields:{news:'최신 로컬 수정'},frames:[],settings:{},savedAt:200}));
      localStorage.setItem(key+':recovery',JSON.stringify({fields:{news:'오래된 복구본'},frames:[],settings:{},savedAt:100}));
    });
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>runServiceBulletinAction('open',window.bulletinTest.id));
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    await page.locator('[data-bulletin-local]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="news"]').inputValue(),'최신 로컬 수정');
    // Hidden overflowing frames must not disable printing even while editing the layout.
    await page.locator('[data-bulletin-field="news"]').fill('영역 넘침 검사 '.repeat(200));
    await page.locator('[data-bulletin-mode="layout"]').click();
    await page.locator('[data-bulletin-frame]').selectOption('news');
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.locator('[data-bulletin-hidden]').uncheck();
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),false);
    await page.locator('[data-bulletin-frame]').selectOption('prayers');
    await page.locator('[data-bulletin-dimension="w"]').fill('50');
    await page.locator('[data-bulletin-dimension="w"]').press('Tab');
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.locator('[data-bulletin-undo]').click();
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),false);
    await page.locator('[data-bulletin-frame]').selectOption('events');
    await page.locator('[data-bulletin-dimension="w"]').fill('30');
    await page.locator('[data-bulletin-dimension="w"]').press('Tab');
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),true);
    await page.locator('[data-bulletin-undo]').click();
    assert.equal(await page.locator('[data-bulletin-print]').isDisabled(),false);
    console.log('PASS quota/security failures, DB status, safe recovery, newest draft and hidden-frame output');
    // Print is single-flight; closing the editor while print fonts load must cancel safely.
    await page.evaluate(()=>{
      const create=document.createElement;
      window.printAudit={created:0,calls:0,releases:[],restore:()=>document.createElement=create};
      document.createElement=function(...args){
        const node=create.apply(this,args);
        if(args[0]==='iframe'){
          window.printAudit.created++;
          node.addEventListener('load',()=>{
            node.contentWindow.print=()=>window.printAudit.calls++;
            node.contentDocument.fonts.load=()=>new Promise(resolve=>window.printAudit.releases.push(resolve));
          },{once:true});
        }
        return node;
      };
      document.querySelector('[data-bulletin-print]').click();
      document.querySelector('[data-bulletin-print]').click();
    });
    await page.waitForFunction(()=>window.printAudit.releases.length===3);
    assert.equal(await page.evaluate(()=>window.printAudit.created),1);
    await page.locator('[data-bulletin-close]').click();
    await page.evaluate(()=>{window.printAudit.releases.forEach(resolve=>resolve([]));window.printAudit.restore();});
    await page.waitForTimeout(50);
    assert.equal(await page.evaluate(()=>window.printAudit.calls),0);
    console.log('PASS duplicate print prevention and close-during-print cancellation');



    await page.evaluate(async()=>{
      const host=document.getElementById('detailPane');host.replaceChildren();
      const source=window.MindexBulletin.resolveSource({...window.bulletinSaved,service:{...window.bulletinSaved.service,id:'next-bulletin',service_date:'2026-10-04'}});
      source.autoBackground=bulletinBackgroundForService({type_id:'young-adult',date:source.date},{date:source.date,liturgical:source.liturgical});
      window.MindexBulletin.mount(host,{serviceId:source.id,scope:'https://offline-bulletin.test',services:[{id:source.id,label:'다음 주보'}],loadSource:async()=>source,loadDraft:async()=>null,saveDraft:saveBulletinDraft,onClose(){}});
    });
    await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    assert.equal(await page.locator('[data-bulletin-field="church"]').inputValue(),'','No automatic historical common copy');
    assert.equal(await page.locator('[data-bulletin-field="issue"]').inputValue(),'','Unknown future issue must not be guessed');
    assert.deepEqual(errors,[]);
    if(process.env.BULLETIN_LIVE_STDIN) {
      const snapshot=JSON.parse(fs.readFileSync(0,'utf8'));
      const result=await page.evaluate(async data=>{
        const source=window.MindexBulletin.resolveSource(data);
        source.autoBackground=bulletinBackgroundForService(normalizeWorshipService(data.service),data.calendar?.find(row=>row.date===source.date));
        const host=document.getElementById('detailPane');host.replaceChildren();
        window.MindexBulletin.mount(host,{serviceId:source.id,scope:'live-read-review',
          services:[{id:source.id,label:source.date+' · 청년부'}],loadSource:async()=>source,loadDraft:async()=>null,saveDraft:saveBulletinDraft,onClose(){}});
        await window.MindexBulletin.readyAssets();
        const rendered=window.MindexBulletin.renderPages({source,fields:{},frames:window.MindexBulletin.defaultFrames()},'print',null);
        return {orderRows:source.order.length,prayers:source.prayers.length,issues:[...rendered.issues]};
      },snapshot);
      assert.deepEqual(result.issues,[],'Real saved service must fit default frames');
      await page.waitForFunction(()=>document.querySelector('[data-bulletin-print]')?.disabled===false);
      console.log('LIVE_READ:'+JSON.stringify(result));
    }
    if(process.env.BULLETIN_THEME_IMAGE){
      await page.locator('[data-bulletin-mode="layout"]').click();
      for(const file of ['26-S4.png','26-S6.png']) {
        await page.locator('[data-bulletin-setting="theme"]').selectOption(file);
      await page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
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
