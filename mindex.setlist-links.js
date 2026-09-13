(function (root) {
  "use strict";
  const key = (value) => String(value || "").normalize("NFKC").replace(/\s+/gu, "").toLowerCase();
  function titleParts(value) {
    let text = String(value || "").trim();
    const verse = text.match(/\s*([⑴-⒇①-⑳](?:\s*[,·]\s*[⑴-⒇①-⑳])*)$/u)?.[1] || "";
    if (verse) text = text.slice(0, text.lastIndexOf(verse)).trim();
    const hymn = text.match(/^(통\s*)?(\d{1,4})\s+(.+)$/u);
    return { text: hymn ? hymn[3] : text, number: hymn ? String(Number(hymn[2])) : "", oldHymnal: Boolean(hymn?.[1]), verse };
  }
  function aliases(value) {
    const text = titleParts(value).text;
    return [...new Set([text, text.replace(/\s*[(（\[][^)）\]]*[)）\]]/gu, "").trim(),
      ...Array.from(text.matchAll(/[(（\[]([^)）\]]+)[)）\]]/gu), (match) => match[1])].map(key).filter(Boolean))];
  }
  function buildIndex(songs = [], versions = []) {
    const byId = new Map(songs.map((song) => [song.id, { ...song, modernNumbers: new Set(), oldNumbers: new Set() }]));
    const titles = new Map(), names = new Map();
    function add(map, name, id) {
      const normalized = key(name);
      if (!normalized) return;
      if (!map.has(normalized)) map.set(normalized, new Set());
      map.get(normalized).add(id);
    }
    for (const song of byId.values()) {
      add(titles, song.title, song.id);
      if (song.subtitle) add(titles, `${song.title} (${song.subtitle})`, song.id);
      for (const name of [song.title, song.subtitle, song.original_title]) {
        for (const alias of aliases(name)) add(names, alias, song.id);
      }
      if (/^\d+$/u.test(String(song.hymn_no || ""))) song.modernNumbers.add(String(Number(song.hymn_no)));
    }
    for (const version of versions) {
      const song = byId.get(version.source_song_id) || byId.get(version.canonical_song_id);
      if (!song) continue;
      for (const name of [version.curated_version_name, version.version_label, version.subtitle, version.original_title]) {
        if (!name || /^(default|기본|새찬송가|통일찬송가|version\s*\d+)$/iu.test(name.trim())) continue;
        for (const alias of aliases(name)) add(names, alias, song.id);
      }
      const old = [version.curated_version_name, version.version_label].map((name) => String(name || "").match(/^(?:통일|통)\s*(\d+)/u)).find(Boolean);
      if (old) song.oldNumbers.add(String(Number(old[1])));
    }
    return { byId, titles, names };
  }
  function isExcluded(candidate, serviceType = "") {
    const label = String(candidate.raw_label || "").replace(/\s+/gu, "");
    if (!label.includes("특송")) return false;
    if (label.includes("3부")) return true;
    return ["sun_3rd", "sunday-main"].includes(serviceType) && !/[12]부/u.test(label);
  }
  function split(value) {
    const text = String(value || "").trim();
    const wrapped = text.match(/^메들리\s*[(（]([\s\S]*)[)）]$/u);
    return (wrapped ? wrapped[1] : text).split(/\s*[+＋]\s*/u).filter(Boolean);
  }
  function resolve(value, index, explicitId = "") {
    if (!index) return { status: "pending", text: value, candidates: [] };
    const part = titleParts(value);
    let ids = explicitId ? new Set(index.byId.has(explicitId) ? [explicitId] : []) : index.titles.get(key(part.text));
    if (!ids?.size && !explicitId) ids = new Set(aliases(part.text).flatMap((alias) => [...(index.names.get(alias) || [])]));
    const candidates = [...(ids || [])].map((id) => index.byId.get(id)).filter(Boolean);
    if (!candidates.length) return { status: explicitId ? "broken-link" : "unmatched", text: value, candidates };
    const numbered = part.number ? candidates.filter((song) => (part.oldHymnal ? song.oldNumbers : song.modernNumbers).has(part.number)) : candidates;
    if (!numbered.length) return { status: "hymn-number", text: value, candidates };
    if (numbered.length !== 1) return { status: "ambiguous", text: value, candidates: numbered };
    const song = numbered[0];
    const prefix = part.number ? `${part.oldHymnal ? "통 " : ""}${part.number} ` : "";
    const sameTitle = [...(index.titles.get(key(song.title)) || [])].map(id => index.byId.get(id));
    const needsSubtitle = sameTitle.some(other => other.id !== song.id
      && Boolean(other.modernNumbers.size || other.oldNumbers.size) === Boolean(song.modernNumbers.size || song.oldNumbers.size));
    const title = needsSubtitle && song.subtitle ? `${song.title} (${song.subtitle})` : song.title;
    return { status: "linked", song, text: `${prefix}${title}${part.verse ? ` ${part.verse}` : ""}`, candidates: numbered };
  }
  function fromServices(snapshot = {}, archivedSources = [], index = null) {
    const occupied = new Set(archivedSources.map(s => s.service_date + "|" + s.service_type_id));
    const sections = new Map((snapshot.sections || []).map(s => [s.id, s]));
    const grouped = new Map();
    for (const element of snapshot.elements || []) {
      const section = sections.get(element.section_id);
      if (!section || element.element_type !== "praise" || (!element.song_id && !String(element.title || "").trim())) continue;
      if (!grouped.has(section.service_id)) grouped.set(section.service_id, []);
      grouped.get(section.service_id).push({element, section});
    }
    const sources = [], candidates = [];
    for (const service of snapshot.services || []) {
      const identity = service.service_date + "|" + service.service_type_id;
      if (!service.service_date || occupied.has(identity)) continue;
      const rows = grouped.get(service.id) || [];
      if (!rows.length) continue;
      occupied.add(identity);
      const id = "worship:" + service.id;
      sources.push({id, service_id: service.id, source_kind: "worship", source_name: service.title || "",
        service_date: service.service_date, service_type_id: service.service_type_id,
        leader: service.praise_leader || "", aliases:service.service_alias || "", status: service.status});
      rows.sort((a,b) => (Number(a.section.sort_order)||0)-(Number(b.section.sort_order)||0)
        || String(a.section.id).localeCompare(String(b.section.id))
        || (Number(a.element.sort_order)||0)-(Number(b.element.sort_order)||0)
        || String(a.element.id).localeCompare(String(b.element.id)));
      let mainNumber = 0;
      rows.forEach(({element, section}, i) => {
        let label = String(element.label || element.source_ref?.label || section.title || "찬양").trim();
        if (/^찬양(?:\s*\d+)?$/.test(label)) {
          const count = element.song_id ? 1 : Math.max(1, split(element.title).length);
          const first = mainNumber + 1;
          mainNumber += count;
          label = `찬양 ${first}${count > 1 ? `–${mainNumber}` : ""}`;
        }
        candidates.push({id:element.id, import_source_id:id, sort_order:i+1, archive_display_order:i+1,
          candidate_level:"element", candidate_key:section.section_key || "praise", suggested_type:"praise",
          raw_label:label, raw_title:String(index?.byId.get(element.song_id)?.title || element.title || "").trim(), suggested_song_id:element.song_id || null,
          archive_live:true,
          archive_manual_song:!element.song_id, review_status:"approved"});
      });
    }
    return {sources, candidates};
  }
  function mergeSundayEntries(entries = []) {
    const isType = (entry, ...types) => types.includes(entry.source.service_type_id);
    return entries.filter(entry => !isType(entry, "sun_1st", "sunday-first", "sun_2nd", "sunday-second")).map(entry => {
      if (!isType(entry, "sun_3rd", "sunday-main")) return entry;
      const label = row => String(row.archive_display_label || row.raw_label || "").replace(/\s+/gu, "");
      const rows = entry.candidates.map(row => label(row) === "특송"
        ? {...row, raw_label:"3부 특송", archive_display_label:"3부 특송"} : row);
      if (!rows.some(row => label(row) === "2부특송")) {
        const second = entries.find(other => isType(other, "sun_2nd", "sunday-second")
          && other.source.service_date === entry.source.service_date);
        const specials = (second?.candidates || []).filter(row => /^(?:2부)?특송$/.test(label(row))).map(row => ({
          ...row, raw_label:"2부 특송", archive_display_label:"2부 특송", archive_source_service_type:"sun_2nd",
        }));
        rows.push(...specials);
      }
      const orderedRows = [
        ...rows.filter(row => label(row) === "2부특송"),
        ...rows.filter(row => label(row) !== "2부특송"),
      ];
      return {...entry, candidates:orderedRows, missing:rows.length === 0,
        needsReview:rows.filter(row => row.review_status === "needs_review").length};
    });
  }
  root.MindexSetlistLinks = { buildIndex, resolve, split, isExcluded, fromServices, mergeSundayEntries };
})(typeof window === "undefined" ? globalThis : window);
