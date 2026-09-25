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
      // Common copy is explicitly loaded here, as through the editor reference button.
      const doc={source,fields:{...B.profileForDate(source.date),notices:source.notices},settings:{theme:'auto'},frames:B.defaultFrames()};
      const {pages,issues}=B.renderPages(doc,'content');
      document.body.replaceChildren(...pages);
      const style=document.createElement('style');style.textContent='@page{size:A4 landscape;margin:0}body{margin:0}.bulletin-sheet{display:block;width:100%;height:auto;break-after:page}@media print{.bulletin-sheet{width:297mm;height:210mm}}';document.head.append(style);
      await Promise.all([...document.querySelectorAll('image')].map(el=>new Promise(resolve=>{const im=new Image();im.onload=im.onerror=resolve;im.src=el.getAttribute('href');})));
      const sermon=pages[1].querySelector('[data-frame-id="sermon"]');
      const news=pages[0].querySelector('[data-frame-id="news"]');
      return {issues:[...issues],flip:pages[1].querySelector('image').getAttribute('transform'),
        sermon:[...sermon.querySelectorAll('text')].map(t=>({text:t.textContent,size:Number(t.getAttribute('font-size'))})),
        news:news.textContent,notes:[...pages[1].querySelectorAll('[data-frame-id="notes"] line')].map(l=>Number(l.getAttribute('y1')))};
    },fixture);
    assert.deepEqual(result.issues,[]);
    assert.equal(result.flip,'translate(297 0) scale(-1 1)');
    assert.equal(result.sermon[1].text,'사무엘상 22:1–5');
    assert.ok(result.sermon[1].size<result.sermon[0].size);
    assert.ok(!result.news.includes('기도 모임'));
    assert.deepEqual(result.notes,[160,167.5,175,182.5,190]);
    const pdf=await PDFDocument.load(await page.pdf({preferCSSPageSize:true,printBackground:true}));
    assert.equal(pdf.getPageCount(),2);
    if(process.env.BULLETIN_SCREENSHOTS)for(const sheet of await page.locator('.bulletin-sheet').all())console.log('IMAGE:'+await sheet.screenshot({type:'jpeg'}).then(b=>b.toString('base64')));
    console.log('PASS actual September 20: no overflow, mirrored inside, sermon typography, notes and two-page PDF');
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
