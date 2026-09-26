// July–September read-only DB fixture and original PDF regression; PDFs stay in memory.
const fs=require('fs'),path=require('path'),http=require('http');const{chromium}=require('playwright');const assert=require('node:assert/strict');const {PDFDocument}=require('pdf-lib');const root=process.cwd(),db=require('./fixtures/bulletin-2026-summer.json');
const server=http.createServer((req,res)=>{const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname),file=path.resolve(root,pathname==='/'?'index.html':pathname.slice(1));if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404).end();return;}res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.mjs':'application/javascript','.css':'text/css','.woff2':'font/woff2','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');let b=fs.readFileSync(file);if(pathname==='/')b=Buffer.from(b.toString().replace(/window\.MINDEX_SUPABASE = \{[\s\S]*?\};/,'window.MINDEX_SUPABASE = null;'));res.end(b);});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});try{const p=await browser.newPage();await p.route('**/*',r=>r.request().url().startsWith(base)?r.continue():r.abort());await p.goto(base);await p.waitForFunction(()=>window.MindexBulletin&&typeof state!=='undefined');const result=await p.evaluate(async db=>{
state.serviceTypes=[{id:'young-adult',name:'청년부',display_name:'청년부'}];
worshipAtomicClient=async()=>({read:async id=>{const service=db.services.find(s=>s.id===id),sections=db.sections.filter(s=>s.service_id===id),ids=new Set(sections.map(s=>s.id));return {service,sections,elements:db.elements.filter(e=>ids.has(e.section_id))};}});
loadBulletinReusableContent=async()=>[];
state.client={from(table){const query={select(){return this;},in(){return this;},gte(){return this;},lte(){return this;},order(){return this;},then(resolve){const data=({'mindex_songs':db.songs,'mindex_scriptures':db.scriptures,'mindex_sunday_calendar':db.calendar,'mindex_worship_services':db.services})[table]||[];return Promise.resolve({data,error:null}).then(resolve);}};return query;}};
const B=window.MindexBulletin;await B.readyAssets();const out=[];for(const service of db.services.filter(s=>s.service_date!=='2026-07-12')){const source=await loadServiceBulletinSource(service.id,{});const doc={source,fields:{},settings:{theme:'auto'},frames:B.defaultFrames()};
const {pages,issues}=B.renderPages(doc,'content');
const saved=B.storedValue(doc),restored={};B.applyStored(restored,{...saved,revision:1});
const changed={...source,leader:'changed',sermon:'changed',news:'changed',prayers:source.prayers.map(r=>({...r,person:'changed'})),order:[]};
const frozen=B.applySourceSnapshot(changed,restored.sourceSnapshot);
if(frozen.sermon!==source.sermon||frozen.leader!==source.leader||frozen.news!==source.news||JSON.stringify(frozen.prayers)!==JSON.stringify(source.prayers)||JSON.stringify(frozen.order)!==JSON.stringify(source.order))throw new Error('Publication snapshot changed: '+source.date);
if(B.applySourceSnapshot({...changed,id:'other'},restored.sourceSnapshot).leader!=='changed')throw new Error('Snapshot leaked across services');
if(B.applySourceSnapshot(changed,null).leader!=='changed')throw new Error('Explicit refresh failed');out.push({source,issues:[...issues],frames:Object.fromEntries(pages.flatMap(page=>[...page.querySelectorAll('[data-frame-id]')].map(f=>[f.dataset.frameId,f.textContent])))});}return out;
},db);
assert.equal(result.length,9);
for(const r of result){
 assert.deepEqual(r.issues,[],r.source.date+' overflow');
 assert.equal(r.source.order.length,13,r.source.date+' print order');
 assert.equal(r.source.order.filter(o=>o.label==='성경봉독').length,1);
 assert.ok(r.source.sermon);
 assert.ok(r.source.leader);
 assert.equal(r.source.announcer,'박지훈 서기');
 assert.equal(r.source.prayers.length,r.source.date.startsWith('2026-08')?6:5);
 assert.equal(r.source.autoBackground.key,r.source.date<'2026-09'?'26-A3.png':'26-A5.png');
 const count=(r.source.outline.match(/[①-⑳]/g)||[]).length;
 assert.equal(count,r.source.date==='2026-07-26'?0:r.source.date==='2026-08-02'?4:r.source.date==='2026-07-05'||r.source.date==='2026-08-23'?3:2);
 await p.evaluate(async source=>{
  const {pages}=window.MindexBulletin.renderPages({source,fields:{},settings:{theme:'auto'},frames:window.MindexBulletin.defaultFrames()},'content');
  document.body.replaceChildren(...pages);
  let style=document.querySelector('#audit-print-style');if(!style){style=document.createElement('style');style.id='audit-print-style';style.textContent='@page{size:A4 landscape;margin:0}html,body{margin:0!important;padding:0!important;display:block!important;overflow:visible!important;height:auto!important}svg.bulletin-sheet{display:block!important;width:297mm!important;height:210mm!important;break-after:page}';document.head.append(style);}
  await Promise.all([...document.querySelectorAll('svg.bulletin-sheet image')].map(el=>new Promise(resolve=>{const im=new Image();im.onload=im.onerror=resolve;im.src=el.getAttribute('href');})));
 },r.source);
 const pdf=await PDFDocument.load(await p.pdf({preferCSSPageSize:true,printBackground:true}));
 assert.equal(pdf.getPageCount(),2,r.source.date+' PDF page count');
}
const august=result.filter(r=>r.source.date.startsWith('2026-08'));
assert.deepEqual(august.map(r=>r.source.prayers.at(-1).person),['이지원 청년','이재희 청년','서영윤 청년']);
assert.equal(result.find(r=>r.source.date==='2026-08-23').source.prayers.find(r=>r.date==='2026-08-30').person,'(야외예배)');
console.log('PASS nine printed issues: legacy source projection, original weekly copy, separate roster snapshots, themes, no overflow and 18 PDF pages');
}finally{await browser.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
