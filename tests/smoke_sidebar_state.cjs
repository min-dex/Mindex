/* Offline integration test: no production connections or artifact files. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium}=require('playwright');
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
  const browser=await chromium.launch({headless:true,executablePath:process.env.BULLETIN_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page=await browser.newPage({viewport:{width:800,height:900}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
    await page.goto(base);await page.waitForFunction(()=>typeof state!=='undefined');
    const findings=await page.evaluate(async()=>{
      const results={};
      document.body.classList.remove('sidebar-collapsed');
      state.module='presenter';document.body.dataset.module='presenter';syncSidebarCollapsedState();
      await new Promise(r=>setTimeout(r,300));
      results.presenterOpenWidth=refs.sidebar.getBoundingClientRect().width;
      state.module='praise';state.search='';const praise=getListScrollKey();
      state.module='bulletin';results.distinctScroll=getListScrollKey()!==praise;
      const shortcut=getScriptureSearchShortcut,run=runScriptureSearchShortcut,open=runServiceBulletinAction;
      let scriptureOpened=false,bulletinOpened='';
      try {
        getScriptureSearchShortcut=async()=>({type:'reference',book:{code:'GEN'},chapter:1});
        runScriptureSearchShortcut=async()=>{scriptureOpened=true;};
        runServiceBulletinAction=async(action,id)=>{bulletinOpened=id;};
        state.services=[{id:'matched',type_id:'young-adult',date:'2026-09-20',title:'청년부'}];
        state.search='주보';refs.songList.innerHTML='<button data-bulletin-open="matched">날짜</button>';
        await handleSearchKeydown({key:'Enter',preventDefault(){}});
        results.searchStaysBulletin=!scriptureOpened&&bulletinOpened==='matched';
      } finally {getScriptureSearchShortcut=shortcut;runScriptureSearchShortcut=run;runServiceBulletinAction=open;}
      state.search='';state.module='praise';
      refs.songList.innerHTML='<div style="height:4000px">목록</div>';
      state.listScroll[getListScrollKey()]=180;restoreCurrentListScroll();
      state.module='bulletin';refs.songList.scrollTop=0;
      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      results.staleScrollCancelled=refs.songList.scrollTop===0;
      return results;
    });
    console.log(findings);
    assert.ok(findings.presenterOpenWidth>150,'Expanded Presenter sidebar must be visible at 800px');
    assert.ok(findings.distinctScroll,'Bulletin must not share praise scroll state');
    assert.ok(findings.searchStaysBulletin,'Enter must open the displayed bulletin result');
    assert.ok(findings.staleScrollCancelled,'Old scroll restoration must not move a different module');
    for(const width of [1500,800,500]) {
      await page.setViewportSize({width,height:900});
      for(const module of ['bulletin','presenter','calendar','praise']) {
        const result=await page.evaluate(async module=>{
          state.module=module;document.body.dataset.module=module;state.search='';
          document.body.classList.remove('sidebar-collapsed');renderModuleSwitcher();
          refs.searchInput.focus();handleSidebarToggle();
          const collapsed=refs.sidebar.inert&&refs.sidebar.getAttribute('aria-hidden')==='true'&&document.activeElement===refs.sidebarToggleBtn;
          handleSidebarToggle();await new Promise(r=>setTimeout(r,300));
          const visible=refs.sidebar.getBoundingClientRect().width>150&&!refs.sidebar.inert;
          const active=[...document.querySelectorAll('.nav-rail-tab.active')].map(b=>b.dataset.homeModule);
          const toggle=refs.sidebarToggleBtn.getBoundingClientRect(),bar=document.querySelector('.topbar').getBoundingClientRect();
          const aligned=Math.abs((toggle.top+toggle.height/2)-(bar.top+bar.height/2))<1;
          return {collapsed,visible,active,aligned};
        },module);
        assert.ok(result.collapsed&&result.visible&&result.aligned,JSON.stringify({width,module,...result}));
        assert.deepEqual(result.active,[module==='presenter'?'service':module]);
      }
    }
    await page.setViewportSize({width:1500,height:900});
    const reused=await page.evaluate(()=>{
      state.module='presenter';document.body.dataset.module='presenter';
      const markup=id=>`<div data-presenter-right-sidebar data-service-id="${id}"><div style="height:1200px">내용</div><details><summary>도움말</summary>안내</details><input data-presenter-preparation-field data-service-id="${id}" data-presenter-preparation-field-label="광고" value="DB 내용"></div>`;
      setRightSidebarContent(markup('same'));
      const root=refs.rightSidebar.firstElementChild,input=root.querySelector('input'),details=root.querySelector('details');
      input.focus();input.value='입력 중';input.setSelectionRange(1,2);details.open=true;refs.rightSidebar.scrollTop=100;
      for(let i=0;i<10;i++)setRightSidebarContent(markup('same'));
      const stable=root.isConnected&&document.activeElement===input&&input.value==='입력 중'&&input.selectionStart===1&&details.open&&refs.rightSidebar.scrollTop===100;
      setRightSidebarContent(markup('other'));
      const switched=!root.isConnected&&refs.rightSidebar.firstElementChild.dataset.serviceId==='other';
      state.module='bulletin';setRightSidebarContent('');
      return {stable,switched,hidden:refs.rightSidebar.hidden&&refs.rightSidebar.inert&&!document.body.classList.contains('right-sidebar-open')};
    });
    assert.deepEqual(reused,{stable:true,switched:true,hidden:true});
    assert.deepEqual(errors,[]);
    console.log('PASS sidebar scroll isolation, stale callbacks, search, responsive expansion, focus, navigation and header alignment');
  } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
