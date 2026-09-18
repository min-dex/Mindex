(function(root) {
  const slots = [
    ['sunday-main','주일예배',0], ['sunday-afternoon','주일오후예배',0],
    ['nursery','유치부 예배',0], ['children','어린이부 예배',0], ['youth','청소년부 예배',0],
    ['young-adult','청년부 예배',0], ['wednesday','수요예배',3], ['friday','금요기도회',5],
  ];
  const type = id => ({sun_3rd:'sunday-main',sun_1st:'sunday-first',sun_2nd:'sunday-second',young_adult:'young-adult',wed:'wednesday',fri:'friday',monthly:'friday',kindergarten:'nursery',preschool:'nursery','유치부':'nursery','유치부 예배':'nursery'})[id] || id;
  const date = text => /^\d{4}-\d{2}-\d{2}$/.test(text || '') ? new Date(text+'T00:00:00Z') : new Date(NaN);
  const add = (text, days) => { const d=date(text); d.setUTCDate(d.getUTCDate()+days); return d.toISOString().slice(0,10); };
  const week = text => {const d=date(text);return Number.isNaN(+d)?'':add(text,-d.getUTCDay());};
  const aliases = s => [s.source_name,s.title,s.service_alias,...(Array.isArray(s.aliases)?s.aliases:[s.aliases])].filter(Boolean).join(' ');
  const absent = s => s && (s.no_gathering === true || s.no_gathering === 'true' || s.source_ref?.no_gathering === true || s.source_ref?.no_gathering === 'true' || /집회\s*없음/.test(aliases(s)));
  function build(entries = [], services = []) {
    const usable = services.filter(s=>!['sunday-first','sunday-second'].includes(type(s.service_type_id)));
    const keys=[...entries.map(e=>week(e.source.service_date)),...usable.map(s=>week(s.service_date))].filter(Boolean).sort();
    if (!keys.length) return [];
    const groups=[];
    for(let key=keys[0];key<=keys[keys.length-1];key=add(key,7)) {
      const actual=entries.filter(e=>week(e.source.service_date)===key);
      const scheduled=usable.filter(s=>week(s.service_date)===key);
      const main=actual.find(e=>type(e.source.service_type_id)==='sunday-main')?.source || scheduled.find(s=>type(s.service_type_id)==='sunday-main');
      const allGeneration=main && /온세대/.test(aliases(main));
      const used=new Set();
      const cells=slots.flatMap(([id,name,day])=>{
        const matching=actual.filter(e=>type(e.source.service_type_id)===id);
        if(matching.length) return matching.map(e=>{
          used.add(e);
          if(e.candidates.length) return {...e,slotName:name};
          const saved=scheduled.find(s=>s.service_date===e.source.service_date && type(s.service_type_id)===id);
          const noGathering=absent(e.source)||absent(saved);
          return {...e,slotName:name,weeklyStatus:e.source.weekly_status||(noGathering?'집회 없음':'콘티 미등록'),
            weeklyReason:e.source.weekly_reason||(noGathering?(saved?.service_alias||saved?.title||''):'찬양 목록이 아직 등록되지 않았습니다')};
        });
        const saved=scheduled.find(s=>type(s.service_type_id)===id);
        const merged=allGeneration && ['children','youth'].includes(id);
        const noGathering=absent(saved);
        return [{source:{...(saved||{}),service_type_id:id,service_date:saved?.service_date||add(key,day),aliases:saved?.service_alias||''},
          candidates:[],missing:true,slotName:name,weeklyStatus:merged?'집회 없음':noGathering?'집회 없음':saved?'콘티 미등록':'기록 없음',
          weeklyReason:merged?'온세대 찬양예배':noGathering?(saved.service_alias||saved.title||''):saved?'찬양 목록이 아직 등록되지 않았습니다':'집회 여부 미확인'}];
      });
      for(const e of actual) if(!used.has(e)) cells.push(e);
      groups.push({key,title:key+' ~ '+add(key,6),entries:cells});
    }
    return groups.reverse();
  }
  root.MindexWorshipWeek={build};
})(typeof window==='undefined'?globalThis:window);
