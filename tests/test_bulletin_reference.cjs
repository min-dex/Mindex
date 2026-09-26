// In-memory visual/PDF regression against the September 20 IDML and DB snapshot.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require('playwright');
const {PDFDocument}=require('pdf-lib');
const fixture=require('./fixtures/bulletin-20260920.json');
const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname==='/'){res.setHeader('Content-Type','text/html');res.end('<meta charset="utf-8"><script src="/mindex.bulletin.js"></script>');return;}
  const file=path.resolve(root,pathname.slice(1));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||fs.statSync(file).isDirectory()){res.writeHead(404);res.end();return;}
  if(file.endsWith('.svg'))res.setHeader('Content-Type','image/svg+xml');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true,executablePath:process.env.BULLETIN_CHROME});
  try{
    const page=await browser.newPage({viewport:{width:1200,height:860}});
    await page.route('**/*',r=>r.request().url().startsWith(base)?r.continue():r.abort());
    await page.goto(base);
    const result=await page.evaluate(async fixture=>{
      const B=window.MindexBulletin;await B.readyAssets();
      const source=B.resolveSource(fixture);
      source.autoBackground={key:'26-A5.png',url:'assets/worship-backgrounds/26-A5.png'};
      // A fresh document needs no manual common-copy import.
      const doc={source,fields:{},settings:{theme:'auto'},frames:B.defaultFrames()};
      const {pages,issues}=B.renderPages(doc,'content');
      document.body.replaceChildren(...pages);
      const style=document.createElement('style');style.textContent='@page{size:A4 landscape;margin:0}body{margin:0}.bulletin-sheet{display:block;width:100%;height:auto;break-after:page}@media print{.bulletin-sheet{width:297mm;height:210mm}}';document.head.append(style);
      await Promise.all([...document.querySelectorAll('image')].map(el=>new Promise(resolve=>{const im=new Image();im.onload=im.onerror=resolve;im.src=el.getAttribute('href');})));
      const sermon=pages[1].querySelector('[data-frame-id="sermon"]');
      const news=pages[0].querySelector('[data-frame-id="news"]');
      return {styles:{church:[...pages[0].querySelectorAll('[data-frame-id="church"] tspan')].map(t=>[t.textContent,t.getAttribute('font-weight')]),welcome:[...pages[0].querySelectorAll('[data-frame-id="welcome"] tspan')].map(t=>[t.textContent,Number(t.getAttribute('font-size')),t.getAttribute('font-weight')]),month:[...pages[0].querySelectorAll('[data-frame-id="eventsMonth"] tspan')].map(t=>[t.textContent,Number(t.getAttribute('font-size'))]),news:[...news.querySelectorAll('tspan')].map(t=>[t.textContent,t.getAttribute('font-weight')])},issues:[...issues],flip:pages[1].querySelector('image').getAttribute('transform'),
        sermon:[...sermon.querySelectorAll('text')].map(t=>({text:t.textContent,size:Number(t.getAttribute('font-size'))})),
        events:pages[0].querySelector('[data-frame-id="events"]').textContent,church:pages[0].querySelector('[data-frame-id="church"]').textContent,news:news.textContent,notes:[...pages[1].querySelectorAll('[data-frame-id="notes"] line')].map(l=>Number(l.getAttribute('y1')))};
    },fixture);
    assert.deepEqual(result.issues,[]);
    assert.deepEqual(result.styles.church,[['기독교대한성결교회 ','500'],['검단우리교회','700']]);
    assert.ok(result.styles.welcome.some(([text,,weight])=>text==='축복'&&weight==='800'));
    assert.ok(result.styles.month[1][1]>result.styles.month[0][1]);
    assert.ok(result.styles.news.some(([text,weight])=>text==='셀 모임'&&weight==='700'));
    assert.match(result.news,/①.*②/);
    assert.equal(result.flip,'translate(297 0) scale(-1 1)');
    assert.equal(result.sermon[1].text,'삼상 22:1–5');
    assert.ok(result.sermon[1].size<result.sermon[0].size);
    assert.ok(!result.news.includes('기도 모임'));
    assert.match(result.events,/4일 \(금\).*8:00/);
    assert.match(result.events,/20일 \(주일\).*10:50/);
    assert.match(result.church,/검단우리교회/);
    assert.deepEqual(result.notes,[160,167.5,175,182.5,190]);
    const pdf=await PDFDocument.load(await page.pdf({preferCSSPageSize:true,printBackground:true}));
    assert.equal(pdf.getPageCount(),2);
    if(process.env.BULLETIN_SCREENSHOTS)for(const sheet of await page.locator('.bulletin-sheet').all())console.log('IMAGE:'+await sheet.screenshot({type:'jpeg'}).then(b=>b.toString('base64')));
    await page.evaluate(fixture=>{
      document.querySelector('style').remove();document.body.innerHTML='<div id="editor"></div>';
      window.reuseDB={};
      const dates={'a':'2026-09-20','b':'2026-09-27','c':'2026-10-04'};
      window.mountReuseTest=()=>window.MindexBulletin.mount(document.querySelector('#editor'),{
        scope:'reuse-test',serviceId:'a',services:Object.entries(dates).map(([id,label])=>({id,label})),
        loadDraft:async id=>structuredClone(window.reuseDB[id]||null),
        saveDraft:async(id,value,revision)=>{const row={...structuredClone(value),revision:revision+1};window.reuseDB[id]=row;return structuredClone(row);},
        loadSource:async(id,settings)=>{
          const history=Object.entries(window.reuseDB).filter(([key])=>key!==id).map(([key,row])=>({date:dates[key],content:row.content}));
          const source=window.MindexBulletin.resolveSource({...fixture,service:{...fixture.service,id,service_date:dates[id]},settings,history});
          source.autoBackground={key:'26-A5.png',url:'assets/worship-backgrounds/26-A5.png'};return source;
        }
      });
      window.reuseEditor=window.mountReuseTest();
    },fixture);
    const ready=()=>page.waitForFunction(()=>!document.querySelector('[data-bulletin-print]').disabled);
    const field=key=>page.locator(`[data-bulletin-field="${key}"]`);
    await ready();
    await page.locator('[data-bulletin-common] summary').click();
    await field('meeting').fill('새 예배실');await field('news').fill('이번 주만 수정한 소식');
    await field('eventsText').fill('이번 달 확정 일정');
    await page.locator('[data-bulletin-save]').click();
    await page.waitForFunction(()=>window.reuseDB.a?.revision===1);
    await page.locator('[data-bulletin-service]').selectOption('b');await ready();
    assert.equal(await field('meeting').inputValue(),'새 예배실');
    assert.equal(await field('eventsText').inputValue(),'이번 달 확정 일정');
    assert.ok(!(await field('news').inputValue()).includes('이번 주만 수정한 소식'));
    await page.locator('[data-bulletin-setting="eventsMonth"]').fill('2026-10');
    await page.locator('[data-bulletin-setting="eventsMonth"]').dispatchEvent('change');await ready();
    assert.equal(await field('eventsText').inputValue(),'');
    await field('eventsText').fill('다음 달 확정 일정');
    await page.locator('[data-bulletin-setting="eventsMonth"]').fill('2026-09');
    await page.locator('[data-bulletin-setting="eventsMonth"]').dispatchEvent('change');await ready();
    assert.equal(await field('eventsText').inputValue(),'이번 달 확정 일정');
    await page.locator('[data-bulletin-save]').click();await page.waitForFunction(()=>window.reuseDB.b?.revision===1);
    await page.locator('[data-bulletin-service]').selectOption('c');await ready();
    assert.equal(await field('eventsText').inputValue(),'다음 달 확정 일정');
    await page.evaluate(()=>{window.reuseEditor.destroy();localStorage.clear();window.reuseEditor=window.mountReuseTest();});await ready();
    assert.equal(await field('meeting').inputValue(),'새 예배실');
    assert.equal(await field('eventsText').inputValue(),'이번 달 확정 일정');
    assert.equal(await field('news').inputValue(),'이번 주만 수정한 소식');
    console.log('PASS editor reuse across dates, separate months, weekly-copy isolation and DB reopen without browser backup');
    console.log('PASS actual September 20: no overflow, mirrored inside, sermon typography, notes and two-page PDF');
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
