const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={console,document:{addEventListener(){}},localStorage:{getItem(){return null}},setTimeout,clearTimeout,URL,URLSearchParams,crypto:require('node:crypto').webcrypto};c.window=c;c.location={search:'',hash:'',pathname:'/'};vm.createContext(c);
for(const f of ['mindex.constants.js','mindex.presenter.js','mindex.worship-input.js','mindex.setlist-links.js','app.js'])vm.runInContext(fs.readFileSync(f,'utf8'),c,{filename:f});
c.assert=assert;
vm.runInContext(`
 const service={id:'fixture',type_id:'sunday-main',date:'2026-07-26'};
 state.services=[service];state.loadedWorshipServiceIds.add(service.id);
 const item=normalizeServiceItem({id:'confession',service_id:service.id,label:'참회기도',raw_title:'',_worshipSectionKey:'confession',memo:serializeServiceItemMemo({elementType:'body'})},0);
 const status=resolvePresenterServiceItemContentState(item,parseServiceItemMemo(item.memo),null,service);
 assert.equal(status.state,'filled');assert.equal(status.reason,'confession_title');
 const slides=buildPresenterSlidesForServiceItem(item,service,0);
 assert.equal(slides.length,1);assert.equal(slides[0].title,'참회기도');assert.equal(slides[0].assignee,'');
 const praise={...item,id:'praise',label:'찬양 1',_worshipSectionKey:'praise',memo:serializeServiceItemMemo({elementType:'praise',inputMode:'lyrics_db'})};
 assert.equal(resolvePresenterServiceItemContentState(praise,parseServiceItemMemo(praise.memo),null,service).state,'missing');
 console.log('PASS confession title is complete without masking empty praise');
`,c);
