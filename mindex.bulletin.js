(function () {
  "use strict";
  const MM = 72 / 25.4;
  const TOKENS = Object.freeze({width:297, height:210, fold:148.5, inset:5, content:10, grid:2.5, baseline:2.5,
    fontSizes:[7.5,10,12.5,15,17.5,20]});
  const SVG = "http://www.w3.org/2000/svg";
  // Reuse MINDEX's worship artwork. Legacy theme keys preserve saved drafts.
  const themeArtwork={water:"26-A5.png",aurora:"26-A1.png",lent:"26-A2.png",palm:"26-S4.png",pentecost:"26-S6.png",stars:"26-A3.png"};
  const artworkPath=key=>`assets/worship-backgrounds/${themeArtwork[key]}`;
  const logoPath="assets/bulletin/ria-mark.webp";
  const assets = [logoPath,...Object.keys(themeArtwork).map(artworkPath)];
  const fields = {eventsText:"교회 일정 (주보용)",issue:"호수", church:"교회명", news:"청년부 소식", welcome:"환영 문구", notices:"상시 안내", staff:"섬김이 명단",
    motto:"공동체 표어", verse:"표어 성구", website:"웹사이트", address:"주소", meeting:"예배 시간·장소", outline:"설교 요점"};
  const frameLabels={eventsMonth:"일정 월",prayersMonth:"위원표 월",insideChurch:"안쪽 교회명",insideBrand:"안쪽 공동체명",eventsTitle:"교회 일정 제목",events:"교회 일정",newsTitle:"청년부 소식 제목",liturgical:"교회력 명칭",
    orderTitle:"예배 순서 제목",order:"예배 순서",leader:"인도자",prayersTitle:"예배 위원 제목",prayers:"예배 위원",
    sermon:"설교 제목·본문",notesTitle:"설교 노트 제목",notes:"노트 줄"};
  const frameLabel=id=>fields[id]||frameLabels[id]||id;
  const clean = value => String(value ?? "").trim();
  const snap = (value, step=2.5) => Math.round(value/step)*step;
  const clone = value => JSON.parse(JSON.stringify(value));
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const dateLabel = value => { const [y,m,d]=String(value).split("-").map(Number); return y&&m&&d ? `${y}년 ${m}월 ${d}일` : ""; };
  const shortDate = value => { const [,m,d]=String(value).split("-").map(Number); return m&&d ? `${m}월 ${d}일` : ""; };

  const profileKeys=["church","notices","staff","motto","verse","website","address","meeting"];
  // Confirmed archive metadata only; never infer a future issue from week numbers.
  const archiveIssues={"2025-01-05":"1","2025-01-12":"2","2025-01-26":"3","2025-02-02":"4","2025-02-09":"5","2025-02-16":"6","2025-02-23":"7","2025-03-09":"8","2025-03-16":"9","2025-03-23":"10","2025-03-30":"11","2025-04-13":"12","2025-04-20":"13","2025-04-27":"14","2025-05-04":"15","2025-05-11":"16","2025-05-18":"17","2025-05-25":"18","2025-06-01":"19","2025-06-15":"20","2025-06-22":"21","2025-06-29":"22","2025-07-20":"23","2025-07-27":"24","2025-08-03":"25","2025-08-10":"26","2025-08-17":"27","2025-08-31":"28","2025-09-07":"29","2025-09-14":"30","2025-09-21":"31","2025-09-28":"32","2025-10-12":"33","2025-10-19":"34","2025-10-26":"35","2025-11-02":"36","2025-11-09":"37","2025-11-16":"38","2025-11-30":"39","2025-12-07":"40","2025-12-14":"41","2025-12-21":"42","2026-01-18":"1","2026-01-25":"2","2026-02-08":"3","2026-02-22":"4","2026-03-08":"5","2026-03-22":"6","2026-03-29":"7","2026-04-12":"8","2026-04-19":"9","2026-04-26":"10","2026-05-10":"11","2026-05-17":"12","2026-05-24":"13","2026-05-31":"14","2026-06-07":"15","2026-06-21":"16","2026-06-28":"17","2026-07-05":"18","2026-07-19":"19","2026-07-26":"20","2026-08-02":"21","2026-08-16":"22","2026-08-23":"23","2026-09-06":"24","2026-09-13":"25","2026-09-20":"26"};
  const themes={...themeArtwork,paper:"흰 바탕",ink:"짙은 테두리"};
  const validMonth=v=>/^\d{4}-(0[1-9]|1[0-2])$/.test(v||"");
  function profileForDate(date) {
    if(!date||date<"2024-11-24")return {};
    const modern=date>="2025-02-02";
    const hour=date>="2026-05-31"?"오후 3시":date>="2025-09-14"?"오전 11시":"오전 10시";
    return {church:"기독교대한성결교회 검단우리교회",website:"gdwoori.org",
      address:`인천광역시 ${date>="2026-07-05"?"검단구":"서구"} 완정로 178번안길 1`,
      welcome:"오늘도 청년부 예배에 오신 여러분을\n환영하고 축복합니다 :)",
      meeting:"주일 오후 1:10 · 1층 베데스다홀",
      motto:modern?"말씀으로 인도받는 RIA 청년 공동체":"하나님의 주 되심을 인정하는 청년들",
      verse:modern?'이는 그들을 긍휼히 여기는 이가 그들을 이끌되 샘물 근원으로 인도할 것임이라\n— 이사야 49:10b':'여호와께서 집을 세우지 아니하시면 세우는 자의 수고가 헛되며\n여호와께서 성을 지키지 아니하시면 파수꾼의 깨어 있음이 헛되도다 — 시편 127:1',
      notices:["검단우리교회는 신천지 추수꾼 및 각종 이단의 출입을 금지합니다.",date>="2025-04-13"?`기도 모임: 매주 토요일 ${hour} · 1층 청년부실`:"예배 시작 10분 전에 모여 함께 기도로 준비해 주세요."].join("\n"),
      staff:date>="2025-12-07"?"위임목사 김남영 목사 · 담당 교역자 김석범 목사\n회장 김음파 청년 · 총무 이재희 청년\n서기 박지훈 청년 · 회계 서영윤 청년":""};
  }
  function monthlyView(calendar,date,settings={},services=[]) {
    const eventsMonth=validMonth(settings.eventsMonth)?settings.eventsMonth:date.slice(0,7);
    const rosterMonth=validMonth(settings.rosterMonth)?settings.rosterMonth:date.slice(0,7);
    const [y,m]=rosterMonth.split("-").map(Number),cursor=new Date(Date.UTC(y,m-1,1));
    cursor.setUTCDate(1+(7-cursor.getUTCDay())%7);
    const next=new Date(`${date}T00:00:00Z`);next.setUTCDate(next.getUTCDate()+(7-next.getUTCDay()||7));
    const nextDate=next.toISOString().slice(0,10),prayers=[];
    do {
      const day=cursor.toISOString().slice(0,10),row=calendar.find(r=>r.date===day)||{};
      const exception=services.find(r=>r.date===day&&r.noGathering);
      prayers.push({date:day,person:exception?`(${exception.label||"집회 없음"})`:clean(row.young_adult_prayer)||"미정",next:day===nextDate});
      cursor.setUTCDate(cursor.getUTCDate()+7);
    } while(prayers[prayers.length-1].date.slice(0,7)===rosterMonth);
    return {eventsMonth,rosterMonth,prayers,events:calendar.filter(r=>r.date.slice(0,7)===eventsMonth&&clean(r.church_schedule))
      .sort((a,b)=>a.date.localeCompare(b.date)).map(r=>`${shortDate(r.date)}  ${clean(r.church_schedule)}`).join("\n")};
  }

  function resolveSource({service, sections=[], elements=[], songs=[], scriptures=[], calendar=[], settings={}, services=[]}) {
    const songById = new Map(songs.map(s=>[s.id,s]));
    const scriptureById = new Map(scriptures.map(s=>[s.id,s]));
    const sectionById = new Map(sections.map(s=>[s.id,s]));
    const date = service.service_date;
    const today = calendar.find(r=>r.date===date) || {};
    const source = {id:service.id, date, leader:clean(service.worship_leader), liturgical:clean(today.liturgical),
      sermon:"", scripture:"", news:"", order:[], prayers:[], events:"", loadedAt:new Date().toISOString()};
    const hasReading=elements.some(e=>sectionById.get(e.section_id)?.section_key==="scripture_reading");
    const ordered = elements.filter(e=>sectionById.has(e.section_id)).sort((a,b)=>
      (sectionById.get(a.section_id).sort_order-sectionById.get(b.section_id).sort_order) || (a.sort_order-b.sort_order));
    for (const el of ordered) {
      const section=sectionById.get(el.section_id), config=el.config||{}, ref=el.source_ref||{};
      const type=config.elementType||config.element_type||el.element_type;
      const slot=clean(ref.slotKey||config.slotKey);
      let label=clean(ref.label||section.title);
      if (/^(ready|preparation|closing|fellowship)(\.|$)/.test(slot) || /^sermon\.citation\./.test(slot)
        || /^(ready|preparation|closing|fellowship)$/.test(section.section_key)
        || /^(준비|폐회|실시간 성구 송출)$/.test(label)
        || ["blank","image","video","audio","file","ppt","pdf","live_scripture"].includes(type)
        || config.templateSuppressed || el.content_state?.status==="suppressed") continue;
      label=label.replace(/^(찬양|찬송)\s*\d+(?:\s*[–~-]\s*\d+)?$/, "$1");
      const linked = songById.get(el.song_id);
      const scripture = scriptureById.get(el.scripture_id);
      let content = linked ? [linked.hymn_no,linked.title].filter(Boolean).join(" ") : clean(el.title);
      const reference = clean(el.scripture_reference||config.scriptureReference||config.scripture_reference||scripture?.reference);
      if(slot==="sermon.scripture") {if(reference)source.scripture=reference;if(hasReading)continue;}
      if (reference && /scripture|성경|본문/.test([type,slot,label].join(" "))) {
        content=reference;
        if (!source.scripture) source.scripture=reference;
        label="성경봉독";
      }
      if (slot==="sermon.title" || label==="설교") {source.sermon=content;label="설교";}
      if (/announcements/.test(section.section_key) && ["body","plain_text","editable"].includes(type)) {
        source.news=[source.news,clean(el.body||el.title)].filter(Boolean).join("\n");
        source.order.push({id:el.id,label:"광고",content:"",person:clean(el.person)});
        continue;
      }
      let person=clean(el.person);
      if (label.replace(/\s/g,"")==="대표기도") person=clean(today.young_adult_prayer)||person;
      if (content===label) content="";
      if(["사도신경","주기도문","공동체 고백"].includes(label))content="";
      const last=source.order[source.order.length-1];
      if (last && last.label===label && last.person===person && content) last.content=[last.content,content].filter(Boolean).join("\n");
      else source.order.push({id:el.id,label,content,person});
    }
    const copy={news:[],notices:[],welcome:[]};
    for(const line of source.news.split("\n")) {
      const plain=line.replace(/^\s*(?:\d+[.)]|[①-⑳◈◆])\s*/,"");
      if(/^오늘도.*환영|^청년부 예배에.*환영/.test(plain))copy.welcome.push(plain);
      else if(/^(?:검단우리교회는.*신천지|청년부 기도 모임|기도 모임[:(])/.test(plain))copy.notices.push(plain);
      else copy.news.push(line);
    }
    source.news=copy.news.join("\n").trim();source.notices=copy.notices.join("\n");source.welcome=copy.welcome.join("\n");
    Object.assign(source,monthlyView(calendar,date,settings,services));
    return source;
  }

  function defaultFrames() {
    const frames=[];
    const text=(id,page,x,y,w,h,size,binding,align="left",weight=500)=>frames.push({id,page,x,y,w,h,size,binding,align,weight,type:"text"});
    text("eventsTitle",0,10,20,90,10,17.5,"label:교회 일정","left",700);
    text("eventsMonth",0,108.5,20,30,12.5,10,"month:eventsMonth","right");
    frames.push({id:"events",page:0,x:10,y:35,w:128.5,h:45,size:12.5,type:"events",binding:"field:eventsText"});
    text("newsTitle",0,10,87.5,65,10,17.5,"label:청년부 소식","left",700);
    text("welcome",0,88.5,87.5,50,12.5,10,"field:welcome","right");
    frames.push({id:"news",page:0,x:10,y:102.5,w:128.5,h:37.5,size:12.5,type:"list",binding:"field:news"});
    frames.push({id:"notices",page:0,x:10,y:145,w:128.5,h:17.5,size:12.5,type:"list",binding:"field:notices"});
    frames.push({id:"staff",page:0,x:10,y:170,w:128.5,h:25,size:10,type:"staff",binding:"field:staff"});
    text("church",0,158.5,20,128.5,12.5,20,"field:church","center",700);
    text("liturgical",0,158.5,30,128.5,15,15,"source:liturgical","center",700);
    text("motto",0,158.5,170,128.5,10,20,"field:motto","center",700);
    text("verse",0,158.5,180,128.5,15,12.5,"field:verse","center");
    text("website",0,10,2.5,128.5,5,10,"field:website");
    text("issue",0,158.5,2.5,128.5,5,10,"issue","right");
    text("address",0,10,202.5,128.5,5,10,"field:address");
    text("meeting",0,158.5,202.5,128.5,5,10,"field:meeting","right");
    text("orderTitle",1,10,20,75,10,17.5,"label:예배 순서","left",700);
    text("leader",1,108.5,20,30,12.5,10,"leader","right");
    frames.push({id:"order",page:1,x:10,y:37.5,w:128.5,h:150,size:12.5,type:"order",binding:"source:order"});
    text("prayersTitle",1,158.5,20,90,10,17.5,"label:예배 위원","left",700);
    text("prayersMonth",1,257,20,30,12.5,10,"month:rosterMonth","right");
    frames.push({id:"prayers",page:1,x:158.5,y:35,w:128.5,h:35,size:12.5,type:"prayers",binding:"source:prayers"});
    text("sermon",1,158.5,85,128.5,17.5,12.5,"sermon","right",700);
    frames.push({id:"outline",page:1,x:158.5,y:100,w:128.5,h:35,size:12.5,type:"list",binding:"field:outline"});
    text("notesTitle",1,158.5,142.5,128.5,10,17.5,"label:설교 노트","left",700);
    frames.push({id:"notes",page:1,x:158.5,y:157.5,w:128.5,h:30,size:10,type:"rules",binding:""});
    text("insideChurch",1,10,2.5,128.5,5,10,"label:검단우리교회");
    text("insideBrand",1,158.5,202.5,128.5,5,10,"label:RIA 청년부","right");
    return frames;
  }

  function svg(tag, attrs={}, value) {
    const node=document.createElementNS(SVG,tag);
    for (const [key,val] of Object.entries(attrs)) node.setAttribute(key,String(val));
    if (value!==undefined) node.textContent=value;
    return node;
  }
  let fontReady;
  function readyAssets() {
    if (!fontReady) fontReady=(async()=>{
      await Promise.all([[500,"5Medium"],[700,"7Bold"],[800,"8ExtraBold"]].map(async([weight,name])=>{
        const font=new FontFace("MindexBulletin",`url(${new URL(`vendor/fonts/freesentation/Freesentation-${name}.woff2`,document.baseURI)})`,{weight:String(weight)});
        document.fonts.add(await font.load());
      }));
      await Promise.all(assets.map(path=>new Promise((resolve,reject)=>{
        const image=new Image(); image.onload=resolve; image.onerror=()=>reject(new Error("주보 이미지를 불러오지 못했습니다."));
        image.src=new URL(path,document.baseURI).href;
      })));
      await document.fonts.ready;
    })().catch(error=>{fontReady=null;throw error;});
    return fontReady;
  }
  function wrap(text,width,size,weight=500) {
    const ctx=wrap.context||(wrap.context=document.createElement("canvas").getContext("2d"));
    ctx.font=`${weight} ${size}px MindexBulletin`; ctx.fontKerning="normal";
    const fits=s=>ctx.measureText(s).width/MM<=width+.001;
    const result=[];
    for (const paragraph of String(text).split("\n")) {
      let line="";
      for (const part of paragraph.match(/\S+\s*|\s+/gu)||[""]) {
        if (fits(line+part)) {line+=part;continue;}
        if (line.trim()) {result.push(line.trimEnd());line="";}
        if (fits(part)) {line=part;continue;}
        for (const char of Array.from(part)) {
          if (line && !fits(line+char)) {result.push(line.trimEnd());line="";}
          line+=char;
        }
      }
      result.push(line.trimEnd());
    }
    return result;
  }
  function writeText(parent,text,box,issues,id) {
    if (!text) return 0;
    const size=box.size||12.5,weight=box.weight||500;
    const leading=snap(size*1.4,TOKENS.baseline);
    const lines=wrap(text,box.w,size,weight);
    const first=Math.ceil((box.y*MM+size)/TOKENS.baseline)*TOKENS.baseline/MM;
    const end=first+(lines.length-1)*leading/MM;
    if (end+size*.25/MM>box.y+box.h+.01) issues.add(id);
    const anchor=box.align==="right" ? "end" : box.align==="center" ? "middle" : "start";
    const x=box.x+(anchor==="end"?box.w:anchor==="middle"?box.w/2:0);
    lines.forEach((line,i)=>parent.append(svg("text",{x,y:first+i*leading/MM,"font-size":size/MM,
      "font-family":"MindexBulletin","font-weight":weight,"text-anchor":anchor,fill:box.color||"#231f20"},line)));
    return end-box.y+size*.25/MM;
  }
  function fieldValue(doc,key) {
    if(Object.hasOwn(doc.fields,key))return doc.fields[key];
    if(key==="news")return doc.source?.news||"";
    if(key==="eventsText")return doc.source?.events||"";
    if(key==="welcome"&&doc.source?.welcome)return doc.source.welcome.replace(/\s*(환영하고)/,"\n$1");
    if(key==="issue")return archiveIssues[doc.source?.date]||"";
    const value=doc.profile?.[key]??profileForDate(doc.source?.date)[key]??"";
    if(key!=="notices")return value;
    if(doc.source?.notices)return doc.source.notices;
    // The saved announcement may already include these standard notices.
    return value.split("\n").filter(line=>!["신천지","기도 모임"].some(term=>line.includes(term)&&doc.source?.news?.includes(term))).join("\n");
  }
  function boundText(doc,frame) {
    const [kind,key]=frame.binding.split(":");
    if(kind==="label")return key;
    if(kind==="month"){const [y,m]=(doc.source?.[key]||"").split("-");return y&&m?`${y}년\n${Number(m)}월`:"";}
    if(kind==="field")return fieldValue(doc,key);
    if(kind==="source")return doc.source?.[key]||"";
    if(kind==="leader")return doc.source?.leader?`인도자\n${doc.source.leader}`:"";
    if(kind==="sermon")return [doc.source?.sermon,doc.source?.scripture].filter(Boolean).join("\n");
    if(kind==="issue")return [dateLabel(doc.source?.date),fieldValue(doc,"issue")?`제${fieldValue(doc,"issue")}호`:""].filter(Boolean).join(" · ");
    return "";
  }
  function renderPages(doc,mode,selected) {
    const issues=new Set(); const pages=[];
    for(let page=0;page<2;page++) {
      const root=svg("svg",{viewBox:"0 0 297 210",class:"bulletin-sheet",role:"img","aria-label":page?"주보 안쪽":"주보 겉면"});
      const theme=doc.settings?.theme||"water";
      if(Object.hasOwn(themeArtwork,theme))root.append(svg("image",{href:new URL(artworkPath(theme),document.baseURI).href,width:297,height:210,preserveAspectRatio:"xMidYMid slice"}));
      else root.append(svg("rect",{width:297,height:210,fill:theme==="ink"?"#202b35":"#fff"}));
      for(const x of [5,153.5])root.append(svg("rect",{x,y:10,width:138.5,height:190,fill:"white","fill-opacity":["palm","pentecost"].includes(theme)?.88:1}));
      if(page===0)root.append(svg("image",{href:new URL(logoPath,document.baseURI).href,x:170,y:67.5,width:105,height:72.5}));
      for(const f of doc.frames.filter(f=>f.page===page&&(!f.hidden||mode==="layout"))) {
        const group=svg("g",{"data-frame-id":f.id});
        if(f.type==="rules") {
          for(let y=0;y<=f.h;y+=7.5)group.append(svg("line",{x1:f.x,y1:f.y+y,x2:f.x+f.w,y2:f.y+y,stroke:"#555","stroke-width":.15}));
        } else if(f.type==="list") {
          let y=f.y,index=0;
          for(const line of String(boundText(doc,f)).split("\n").filter(l=>l.trim())) {
            const content=line.replace(/^\s*(?:\d+[.)]|[①-⑳◈◆])\s*/,"");
            const mark=f.id==="notices"?"◈":String.fromCodePoint(0x2460+Math.min(index++,19));
            writeText(group,mark,{...f,y,w:7.5,h:10},issues,f.id);
            const h=writeText(group,content,{...f,x:f.x+7.5,y,w:f.w-7.5,h:f.y+f.h-y},issues,f.id);
            y+=Math.max(f.id==="news"?10:7.5,h+2.5);
          }
        } else if(f.type==="staff") {
          const value=boundText(doc,f),pairs=value.split(/\n|\s*·\s*/).filter(Boolean);
          const parsed=pairs.map(t=>t.match(/^(위임목사|담당 교역자|회장|총무|서기|회계)\s+(.+)$/));
          if(parsed.every(Boolean)&&parsed.length===6)parsed.forEach((row,i)=>{
            const col=(f.w-7.5)/2,x=f.x+(i%2)*(col+7.5),y=f.y+Math.floor(i/2)*7.5;
            writeText(group,row[1],{...f,x,y,w:col,h:7.5},issues,f.id);
            writeText(group,row[2],{...f,x,y,w:col,h:7.5,align:"right"},issues,f.id);
          });else writeText(group,value,f,issues,f.id);
        } else if(f.type==="events") {
          let y=f.y;
          for(const line of String(boundText(doc,f)).split("\n").filter(Boolean)) {
            const parts=line.match(/^(\d+월 \d+일)\s+(.+)$/);
            if(!parts){y+=writeText(group,line,{...f,y,h:f.y+f.h-y},issues,f.id)+2.5;continue;}
            const body=parts[2],h=Math.max(7.5,wrap(body,f.w-35,f.size).length*snap(f.size*1.4)/MM+2.5);
            writeText(group,parts[1],{...f,y,w:30,h},issues,f.id);
            writeText(group,body,{...f,x:f.x+35,y,w:f.w-35,h,align:"right"},issues,f.id);y+=h;
            if(y>f.y+f.h+.01)issues.add(f.id);
          }
        } else if(f.type==="order") {
          const list=doc.source?.order||[],inner=f.w-60;
          if(inner<10){issues.add(f.id);root.append(group);continue;}
          const leading=snap(f.size*1.4)/MM;
          const counts=list.map(row=>Math.max(wrap(row.label,30,f.size).length,wrap(row.content,inner,f.size,700).length,wrap(row.person,30,f.size).length));
          const used=counts.reduce((sum,n)=>sum+n*leading,0),gap=list.length>1?Math.max(2.5,(f.h-used)/(list.length-1)):0;
          let y=f.y;
          list.forEach((row,i)=>{
            const height=counts[i]*leading,base={...f,y,h:height+1};
            const centered=y+Math.max(0,(counts[i]-1)*leading/2);
            const printLabel=row.label==="봉헌찬양"?"봉헌":row.label;
            const letters=printLabel.replace(/\s/g,"");
            if(letters.length>1&&letters.length<=5) [...letters].forEach((letter,j)=>writeText(group,letter,{...base,y:centered,x:f.x+j*27.5/(letters.length-1),w:6},issues,f.id));
            else writeText(group,row.label,{...base,y:centered,w:30},issues,f.id);
            writeText(group,row.content,{...base,x:f.x+30,w:inner,align:"center",weight:700},issues,f.id);
            writeText(group,row.person,{...base,y:centered,x:f.x+f.w-30,w:30,align:"right"},issues,f.id);
            y+=height+(i<list.length-1?gap:0);
          });
          if(y>f.y+f.h+.01)issues.add(f.id);
        } else if(f.type==="prayers") {
          const list=doc.source?.prayers||[],left=Math.floor(list.length/2),col=(f.w-5)/2;
          list.forEach((r,i)=>{
            const x=f.x+(i>=left?col+5:0),y=f.y+(i>=left?i-left:i)*10;
            writeText(group,shortDate(r.date),{...f,x,y,w:27.5,h:10},issues,f.id);
            if(r.next){group.append(svg("rect",{x:x+29,y:y+2,width:9,height:4,rx:2,fill:"white",stroke:"#555","stroke-width":.2}));
              writeText(group,"NEXT",{...f,x:x+29,y:y+1,w:9,h:7.5,size:7.5,align:"center"},issues,f.id);}
            writeText(group,r.person,{...f,x:x+38.5,y,w:col-38.5,h:10,align:"right"},issues,f.id);
            if(y+10>f.y+f.h+.01)issues.add(f.id);
          });
        } else writeText(group,boundText(doc,f),{...f,color:(f.y<10||f.y>=200)&&!["paper","palm","pentecost"].includes(theme)?"#fff":"#231f20"},issues,f.id);
        if(mode==="layout") {
          group.append(svg("rect",{class:`bulletin-frame-hit${selected===f.id?" is-selected":""}`,x:f.x,y:f.y,width:f.w,height:f.h,
            fill:"transparent",stroke:selected===f.id?"#477953":"#47795380","stroke-width":.25,"data-frame-hit":f.id}));
          if(selected===f.id)group.append(svg("rect",{class:"bulletin-resize",x:f.x+f.w-1.5,y:f.y+f.h-1.5,width:3,height:3,fill:"#477953","data-resize":f.id}));
        }
        root.append(group);
      }
      pages.push(root);
    }
    return {pages,issues};
  }

  function restore(scope,id) {
    const key=`mindex.bulletin.v1:${scope}:${id}`;
    let saved=null;
    try {saved=JSON.parse(localStorage.getItem(key)||"null");}catch{ /* corrupt/blocked storage remains recoverable */ }
    const frames=defaultFrames();
    if(saved?.version===1)for(const f of frames){
      const patch=saved.frames?.find(p=>p.id===f.id);
      if(!patch)continue;
      for(const name of ["x","y","w","h","size"]){
        const n=Number(patch[name]);
        if(Number.isFinite(n)&&n>=0&&n<=297&&(name!=="size"||TOKENS.fontSizes.includes(n)))f[name]=n;
      }
      f.hidden=patch.hidden===true;
      if(["left","center","right"].includes(patch.align))f.align=patch.align;
      f.w=Math.max(10,Math.min(297,f.w));f.h=Math.max(5,Math.min(210,f.h));
      f.x=Math.min(f.x,297-f.w);f.y=Math.min(f.y,210-f.h);
    }
    const values={};
    if(saved?.version===1)for(const key of Object.keys(fields))if(typeof saved.fields?.[key]==="string")values[key]=saved.fields[key];
    const settings={};
    for(const k of ["eventsMonth","rosterMonth"])if(validMonth(saved?.settings?.[k]))settings[k]=saved.settings[k];
    if(Object.hasOwn(themes,saved?.settings?.theme||""))settings.theme=saved.settings.theme;
    return {key,fields:values,settings,frames,source:null,history:[],future:[]};
  }
  function snapshot(doc){return {fields:clone(doc.fields),settings:clone(doc.settings||{}),frames:clone(doc.frames)};}

  function mount(host,options) {
    const controller=new AbortController(),signal=controller.signal;
    let doc,mode="content",selected="news",loading=false,assetLoaded=false,error="",serial=0,saveError="",issues=new Set();
    const documents=new Map();
    const on=(target,event,fn)=>target.addEventListener(event,fn,{signal});
    host.innerHTML=`<section class="bulletin-workbench" aria-label="주보 편집">
      <header class="bulletin-toolbar"><button class="bulletin-back" type="button" data-bulletin-close title="예배로 돌아가기" aria-label="예배로 돌아가기"><i data-lucide="arrow-left"></i></button>
      <h2>주보</h2><select aria-label="주보 예배" data-bulletin-service>${options.services.map(s=>`<option value="${escape(s.id)}">${escape(s.label)}</option>`).join("")}</select>
      <span class="bulletin-spacer"></span><div class="bulletin-history" role="group" aria-label="편집 기록">
      <button type="button" data-bulletin-undo aria-label="주보 실행 취소" title="실행 취소"><i data-lucide="undo-2"></i></button><button type="button" data-bulletin-redo aria-label="주보 다시 실행" title="다시 실행"><i data-lucide="redo-2"></i></button></div>
      <button class="bulletin-primary" type="button" data-bulletin-print disabled><i data-lucide="printer"></i><span>인쇄 / PDF</span></button></header>
      <div class="bulletin-meta"><div class="bulletin-status" role="status"></div><button type="button" data-bulletin-refresh title="저장된 예배 자료 다시 불러오기"><i data-lucide="refresh-cw"></i><span>새로고침</span></button></div>
      <div class="bulletin-body"><aside class="bulletin-inspector" aria-label="주보 편집 도구">
      <div class="bulletin-modes"><button type="button" data-bulletin-mode="content">내용</button><button type="button" data-bulletin-mode="layout">양식</button></div>
      <div class="bulletin-properties"></div></aside><section class="bulletin-preview" aria-label="인쇄 미리보기"><div class="bulletin-preview-head"><strong>미리보기</strong><span>A4 가로 · 2쪽</span></div><div class="bulletin-canvas" tabindex="0" aria-label="주보 페이지"></div></section></div></section>`;
    const root=host.firstElementChild,q=selector=>root.querySelector(selector);
    window.lucide?.createIcons({root});
    function loadProfile(date) {
      let versions=[];try{versions=JSON.parse(localStorage.getItem(`mindex.bulletin.profiles:${options.scope}`)||"[]");}catch{}
      const profile=profileForDate(date);
      if(Array.isArray(versions))for(const v of versions.filter(v=>v&&typeof v.date==="string"&&v.date<=date).sort((a,b)=>a.date.localeCompare(b.date)))
        for(const k of profileKeys)if(typeof v.fields?.[k]==="string")profile[k]=v.fields[k];
      return profile;
    }
    function remember(before=snapshot(doc)){doc.history.push(before);if(doc.history.length>50)doc.history.shift();doc.future=[];}
    function persist(){
      try{localStorage.setItem(doc.key,JSON.stringify({version:1,...snapshot(doc)}));saveError="";}
      catch{saveError="기기에 저장하지 못했습니다. 이 화면을 닫기 전에 출력해 주세요.";}
    }
    on(root,"mindex-bulletin-save",()=>{persist();status();});
    function status(){
      const text=error||saveError||(loading?"저장된 예배 자료를 불러오는 중…":!assetLoaded?"글꼴과 이미지를 준비하는 중…":
        `이 기기에 자동 저장 · 예배 자료 연결됨${issues.size?` · 영역 넘침: ${[...issues].map(frameLabel).join(", ")}`:""}`);
      q(".bulletin-status").textContent=text;
      q(".bulletin-status").dataset.state=error||saveError||issues.size?"warning":loading||!assetLoaded?"loading":"saved";
      q("[data-bulletin-print]").disabled=loading||!assetLoaded||!!error||!doc?.source?.order.length||issues.size>0;
      q("[data-bulletin-undo]").disabled=!doc?.history.length;
      q("[data-bulletin-redo]").disabled=!doc?.future.length;
      q("[data-bulletin-refresh]").disabled=loading;
    }
    function preview(){
      if(!doc||!assetLoaded){status();return;}
      const rendered=renderPages(doc,mode,selected);issues=rendered.issues;
      q(".bulletin-canvas").replaceChildren(...rendered.pages);status();
    }
    function properties(){
      root.querySelectorAll("[data-bulletin-mode]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.bulletinMode===mode)));
      const p=q(".bulletin-properties");
      if(!doc){p.replaceChildren();return;}
      if(mode==="content") {
        const field=key=>`<label>${escape(fields[key])}${["issue","church","website"].includes(key)?
          `<input data-bulletin-field="${key}" value="${escape(fieldValue(doc,key))}" ${key==="issue"?'inputmode="numeric"':''}>`:
          `<textarea data-bulletin-field="${key}" rows="${key==="news"?5:3}">${escape(fieldValue(doc,key))}</textarea>`}</label>`;
        p.innerHTML=`<section class="bulletin-property-section"><h3>이번 주 내용</h3>${["issue","news","eventsText","outline","welcome"].map(field).join("")}</section>
          <section class="bulletin-property-section"><h3>일정과 위원표</h3><div class="bulletin-number-grid">
          <label>교회 일정<input type="month" data-bulletin-setting="eventsMonth" value="${escape(doc.settings.eventsMonth||doc.source?.eventsMonth||"")}"></label>
          <label>예배 위원<input type="month" data-bulletin-setting="rosterMonth" value="${escape(doc.settings.rosterMonth||doc.source?.rosterMonth||"")}"></label></div></section>
          <section class="bulletin-property-section"><h3>공통 정보</h3>${profileKeys.map(field).join("")}
          <button class="bulletin-reuse" type="button" data-bulletin-profile>이 날짜부터 공통 정보 재사용</button>
          <p class="bulletin-help">다음 주보에도 적용됩니다. 기존 주보에서 직접 수정한 내용은 유지해요.</p></section>`;

      } else {
        const f=doc.frames.find(f=>f.id===selected)||doc.frames[0];selected=f.id;
        p.innerHTML=`<button type="button" data-bulletin-reset-layout>원본형 양식 적용</button><p class="bulletin-help">문구는 유지하고 배치만 원본 기준으로 바꿉니다. 실행 취소할 수 있어요.</p><label>배경<select data-bulletin-setting="theme">${Object.entries(themes).map(([v,t])=>`<option value="${v}" ${(doc.settings.theme||"water")===v?"selected":""}>${t}</option>`).join("")}</select></label><p class="bulletin-help">MINDEX의 기존 예배 배경을 함께 사용합니다. 날짜별 자동 전환은 하지 않습니다.</p><label>프레임<select data-bulletin-frame>${doc.frames.map(f=>`<option value="${f.id}" ${f.id===selected?"selected":""}>${escape(frameLabel(f.id))} · ${f.page?"안쪽":"겉면"}</option>`).join("")}</select></label>
          <label><input type="checkbox" data-bulletin-hidden ${f.hidden?"":"checked"}> 출력에 표시</label><p class="bulletin-help">${escape(frameLabel(f.id))}<br>이동·크기 2.5mm · 글자 2.5pt 단계</p><div class="bulletin-number-grid">`+
          [["x","가로 위치"],["y","세로 위치"],["w","너비"],["h","높이"]].map(([key,label])=>`<label>${label} (mm)<input type="number" step="2.5" data-bulletin-dimension="${key}" value="${f[key]}"></label>`).join("")+`</div>
          <label>글자 크기 (pt)<select data-bulletin-dimension="size">${TOKENS.fontSizes.map(n=>`<option ${f.size===n?"selected":""}>${n}</option>`).join("")}</select></label>
          <label>정렬<select data-bulletin-align>${[["left","왼쪽"],["center","가운데"],["right","오른쪽"]].map(([v,t])=>`<option value="${v}" ${f.align===v?"selected":""}>${t}</option>`).join("")}</select></label>
          <p class="bulletin-help">페이지에서 드래그해 이동하거나 선택 모서리로 크기를 바꿀 수 있어요. 방향키로 2.5mm씩 이동합니다.</p>`;
      }
    }
    async function load(id) {
      const request=++serial;loading=true;error="";
      if(!documents.has(id))documents.set(id,restore(options.scope,id));
      doc=documents.get(id);q("[data-bulletin-service]").value=id;properties();preview();
      try{const source=await options.loadSource(id,doc.settings);if(request!==serial||signal.aborted)return;doc.source=source;doc.profile=loadProfile(source.date);}
      catch(e){if(request===serial&&!signal.aborted)error=e.message||"DB 자료를 불러오지 못했습니다.";}
      finally{if(request===serial&&!signal.aborted){loading=false;properties();preview();}}
    }
    function history(redo=false){
      const from=redo?doc.future:doc.history,to=redo?doc.history:doc.future;
      if(!from.length)return;const months=JSON.stringify([doc.settings.eventsMonth,doc.settings.rosterMonth]);to.push(snapshot(doc));Object.assign(doc,from.pop());persist();properties();preview();
      if(months!==JSON.stringify([doc.settings.eventsMonth,doc.settings.rosterMonth]))void load(q("[data-bulletin-service]").value);
    }
    function setDimension(f,key,value){
      if(key==="size"){if(TOKENS.fontSizes.includes(value))f.size=value;return;}
      const origin=key==="x"&&f.x>=TOKENS.fold?TOKENS.fold:0;
      value=snap(value-origin)+origin;
      if(key==="x")f.x=Math.max(0,Math.min(TOKENS.width-f.w,value));
      if(key==="y")f.y=Math.max(0,Math.min(TOKENS.height-f.h,value));
      if(key==="w")f.w=Math.max(10,Math.min(TOKENS.width-f.x,value));
      if(key==="h")f.h=Math.max(5,Math.min(TOKENS.height-f.y,value));
    }
    on(root,"input",event=>{
      const key=event.target.dataset.bulletinField;if(!key)return;
      remember();doc.fields[key]=event.target.value;persist();preview();
    });
    on(root,"change",event=>{
      const t=event.target;
      if(t.dataset.bulletinSetting){
        const key=t.dataset.bulletinSetting;if(key!=="theme"&&!validMonth(t.value))return;
        remember();doc.settings[key]=t.value;persist();
        if(key==="theme")preview();else void load(q("[data-bulletin-service]").value);return;
      }
      if(t.matches("[data-bulletin-hidden]")){remember();doc.frames.find(f=>f.id===selected).hidden=!t.checked;persist();preview();return;}
      if(t.matches("[data-bulletin-service]")){void load(t.value);return;}
      if(t.matches("[data-bulletin-frame]")){selected=t.value;properties();preview();return;}
      const f=doc.frames.find(f=>f.id===selected);
      if(t.dataset.bulletinDimension){const n=Number(t.value);if(!Number.isFinite(n)){properties();return;}remember();setDimension(f,t.dataset.bulletinDimension,n);persist();properties();preview();}
      if(t.matches("[data-bulletin-align]")){remember();f.align=t.value;persist();preview();}
    });
    on(root,"click",event=>{
      const b=event.target.closest("button");if(!b)return;
      if(b.hasAttribute("data-bulletin-reset-layout")){remember();doc.frames=defaultFrames();persist();properties();preview();return;}
      if(b.hasAttribute("data-bulletin-profile")){
        if(!doc.source?.date)return;
        try {
          const key=`mindex.bulletin.profiles:${options.scope}`;
          let versions=JSON.parse(localStorage.getItem(key)||"[]");if(!Array.isArray(versions))versions=[];
          versions=versions.filter(v=>v&&typeof v.date==="string"&&v.date!==doc.source.date);
          versions.push({date:doc.source.date,fields:Object.fromEntries(profileKeys.map(k=>[k,fieldValue(doc,k)]))});
          localStorage.setItem(key,JSON.stringify(versions));saveError="";
          for(const d of documents.values())if(d.source)d.profile=loadProfile(d.source.date);
          q(".bulletin-status").textContent="공통 문구를 이 날짜부터 재사용하도록 저장했습니다.";
        }catch{saveError="공통 문구를 기기에 저장하지 못했습니다.";status();}return;
      }
      if(b.hasAttribute("data-bulletin-close")){options.onClose();return;}
      if(b.dataset.bulletinMode){mode=b.dataset.bulletinMode;properties();preview();}
      if(b.hasAttribute("data-bulletin-refresh"))void load(q("[data-bulletin-service]").value);
      if(b.hasAttribute("data-bulletin-undo"))history();
      if(b.hasAttribute("data-bulletin-redo"))history(true);
      if(b.hasAttribute("data-bulletin-print"))void print();
    });
    let drag=null;
    on(root,"pointerdown",event=>{
      const hit=event.target.closest("[data-frame-hit],[data-resize]");if(!hit||mode!=="layout"||event.button!==0)return;
      event.preventDefault();selected=hit.dataset.frameHit||hit.dataset.resize;
      const f=doc.frames.find(f=>f.id===selected),rect=hit.closest("svg").getBoundingClientRect();
      drag={before:snapshot(doc),frame:clone(f),clientX:event.clientX,clientY:event.clientY,scale:297/rect.width,resize:!!hit.dataset.resize};
      properties();preview();q(".bulletin-canvas").focus();
    });
    on(document,"pointermove",event=>{
      if(!drag||!root.isConnected)return;
      const f=doc.frames.find(f=>f.id===selected),dx=(event.clientX-drag.clientX)*drag.scale,dy=(event.clientY-drag.clientY)*drag.scale;
      setDimension(f,drag.resize?"w":"x",drag.frame[drag.resize?"w":"x"]+dx);
      setDimension(f,drag.resize?"h":"y",drag.frame[drag.resize?"h":"y"]+dy);
      preview();
    });
    function endDrag(){if(!drag)return;if(JSON.stringify(drag.before)!==JSON.stringify(snapshot(doc))){remember(drag.before);persist();}drag=null;properties();preview();}
    on(document,"pointerup",endDrag);on(document,"pointercancel",endDrag);
    on(root,"keydown",event=>{
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s"){event.preventDefault();event.stopPropagation();persist();status();return;}
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="p"){event.preventDefault();event.stopPropagation();void print();return;}
      if(event.target.matches("input,textarea,select"))return;
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="z"){event.preventDefault();event.stopPropagation();history(event.shiftKey);return;}
      if(mode!=="layout"||!selected||!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key))return;
      event.preventDefault();event.stopPropagation();remember();const f=doc.frames.find(f=>f.id===selected),step=event.shiftKey?10:2.5;
      if(event.key==="ArrowLeft")setDimension(f,"x",f.x-step);if(event.key==="ArrowRight")setDimension(f,"x",f.x+step);
      if(event.key==="ArrowUp")setDimension(f,"y",f.y-step);if(event.key==="ArrowDown")setDimension(f,"y",f.y+step);
      persist();properties();preview();
    });
    let printFrame;
    async function print(){
      if(q("[data-bulletin-print]").disabled)return;
      const output=clone({fields:doc.fields,settings:doc.settings,profile:doc.profile,frames:doc.frames,source:doc.source});
      try{
        await readyAssets();
        if(signal.aborted)return;
        const rendered=renderPages(output,"print",null);if(rendered.issues.size)throw new Error("내용이 프레임을 넘습니다. 양식을 조정해 주세요.");
        printFrame?.remove();printFrame=document.createElement("iframe");
        printFrame.title="주보 인쇄";printFrame.className="bulletin-print-frame";
        const fontCSS=[[500,"5Medium"],[700,"7Bold"],[800,"8ExtraBold"]].map(([w,n])=>`@font-face{font-family:MindexBulletin;font-weight:${w};src:url('${new URL(`vendor/fonts/freesentation/Freesentation-${n}.woff2`,document.baseURI)}')}`).join("");
        const loaded=new Promise(resolve=>printFrame.onload=resolve);
        printFrame.srcdoc=`<!doctype html><html lang="ko"><meta charset="utf-8"><title>주보 ${escape(output.source.date)}</title><style>${fontCSS}@page{size:297mm 210mm;margin:0}body{margin:0}svg{display:block;width:297mm;height:210mm;break-after:page}svg:last-child{break-after:auto}*{print-color-adjust:exact;-webkit-print-color-adjust:exact}</style><body>${rendered.pages.map(p=>p.outerHTML).join("")}</body></html>`;
        document.body.append(printFrame);await loaded;
        await Promise.all([500,700,800].map(w=>printFrame.contentDocument.fonts.load(`${w} 12.5pt MindexBulletin`)));
        await printFrame.contentDocument.fonts.ready;
        printFrame.contentWindow.focus();printFrame.contentWindow.print();
      }catch(e){error=e.message;status();}
    }
    const observer=new MutationObserver(()=>{if(!root.isConnected)destroy();});
    observer.observe(document.body,{childList:true,subtree:true});
    function destroy(){serial++;controller.abort();observer.disconnect();printFrame?.remove();}
    void readyAssets().then(()=>{if(signal.aborted)return;assetLoaded=true;preview();}).catch(e=>{if(!signal.aborted){error=e.message;status();}});
    void load(options.serviceId);
    return {destroy, reload(){return load(q("[data-bulletin-service]").value);}};
  }
  window.MindexBulletin=Object.freeze({mount,resolveSource,defaultFrames,renderPages,readyAssets,TOKENS,wrap,profileForDate,monthlyView});
})();
