// Worship preparation input parsing and song-resolution helpers.
// Loaded before app.js so these browser globals stay available to app orchestration.

function remainingPresenterPreparationExamples(examples = "", draft = "") {
  if (!String(draft).trim()) return "";
  const rows = String(examples).split(/\r?\n/).filter((line) => line.includes(":"));
  const keyFor = (label) => compactSearchValue(normalizePresenterPreparationInputLabel(label));
  const entryKey = (entry) => compactSearchValue(entry.rawLabel || entry.label) === "말씀"
    && String(entry.content || "").trim() && !presenterPreparationContentLooksScriptureReference(entry.content)
    ? "설교제목" : keyFor(entry.label);
  const keys = rows.map((line) => keyFor(line.slice(0, line.indexOf(":"))));
  const covered = new Set();
  const labelOnlyLines = new Set();
  String(draft).split(/\r\n?|\n/).forEach((line, index) => {
    const text = normalizePresenterPreparationLineText(line);
    if (!text) return;
    const pending = text.match(/^([^:：]+)[:：]\s*$/);
    const parsed = parseKnownPresenterPreparationLine(text) || parsePresenterPreparationLine(text)
      || (pending ? { label: pending[1] } : null);
    if (parsed) {
      covered.add(entryKey(parsed));
      return;
    }
    const prefix = keyFor(text);
    const matching = keys.filter((key) => key.startsWith(prefix));
    if (!matching.length) return;
    labelOnlyLines.add(index + 1);
    if (keys.includes(prefix)) covered.add(prefix);
    else if (matching.length === 1) covered.add(matching[0]);
  });
  for (const entry of parsePresenterPreparationInput(draft).entries) {
    if (!labelOnlyLines.has(entry.line)) covered.add(entryKey(entry));
  }
  return rows.filter((_, index) => !covered.has(keys[index])).join("\n");
}

function presenterPreparationPlaceholderSongLabel(item) {
  const label = String(item?.label || "").replace(/\s+/g, "").trim();
  if (!label) return "";
  const numberedPraise = label.match(/^찬양(\d+)$/);
  if (numberedPraise) return `찬양${Number(numberedPraise[1])}`;
  const numberedPrayerPraise = label.match(/^기도찬양(\d+)$/);
  if (numberedPrayerPraise) return `기도찬양${Number(numberedPrayerPraise[1])}`;
  const numberedCommonPrayer = label.match(/^공동기도(\d+)$/);
  if (numberedCommonPrayer) return `공동기도${Number(numberedCommonPrayer[1])}`;
  return normalizePresenterPreparationInputLabel(item.label || "");
}

function presenterPreparationPlaceholderTextLabel(item) {
  const key = compactSearchValue(item?.label || "");
  if (key === "기도" || key === "대표기도") return "대표기도";
  if (key === "성경봉독") return "성경봉독";
  if (key === "설교본문" || key === "본문" || key === "성경본문") return "설교 본문";
  if (key === "설교" || key === "설교제목") return "말씀";
  if (key === "봉헌기도") return "봉헌기도";
  if (key === "축도") return "축도";
  if (key === "인용구절") return "인용구절";
  return normalizePresenterPreparationInputLabel(item?.label || "");
}

function parsePresenterPreparationInput(value = "") {
  const entries = [];
  const errors = [];
  const seenKeys = new Set();
  let nextImplicitPraiseNumber = 1;
  let pending = null;
  let shorthandAllowed = true;
  const missingContent = (entry) => errors.push(`${entry.line}번째 줄 ${entry.rawLabel}의 내용을 입력해 주세요.`);
  String(value || "").split(/\r\n?|\n/).forEach((line, index) => {
    const text = normalizePresenterPreparationLineText(line);
    if (!text) return;
    if (isPresenterPreparationContextLine(text)) return;
    const known = parseKnownPresenterPreparationLine(text);
    let sourceLine = index + 1;
    let parsedLine;
    if (pending && !known) {
      parsedLine = { ...pending, content: text };
      sourceLine = pending.line;
      pending = null;
    } else {
      if (pending) missingContent(pending);
      pending = null;
      parsedLine = known || parsePresenterPreparationLine(text)
        || (shorthandAllowed ? inferPresenterPreparationShorthandLine(text, nextImplicitPraiseNumber) : null);
    }
    if (!parsedLine) {
      errors.push(`${index + 1}번째 줄의 항목을 확인해 주세요: ${text}`);
      return;
    }
    if (!parsedLine.content) {
      pending = { ...parsedLine, line: sourceLine };
      return;
    }
    const lineEntries = expandPresenterPreparationParsedLine(parsedLine, nextImplicitPraiseNumber);
    for (const entry of lineEntries) {
      const label = String(entry.label || "").trim();
      const rawLabel = String(entry.rawLabel || label).trim();
      let content = cleanPresenterPreparationContent(entry.content);
      content = normalizePresenterPreparationEntryContent(label, content);
      const key = compactSearchValue(label);
      const rawKey = compactSearchValue(rawLabel);
      if (!label || !content) {
        errors.push(`${index + 1}번째 줄에 항목과 내용을 모두 입력해 주세요.`);
        return;
      }
      const duplicateKey = presenterPreparationDuplicateKey(key, rawKey);
      if (seenKeys.has(duplicateKey)) {
        errors.push(`${label} 항목이 두 번 입력되었습니다.`);
        return;
      }
      seenKeys.add(duplicateKey);
      const praiseMatch = key.match(/^찬양(\d+)$/);
      if (praiseMatch) nextImplicitPraiseNumber = Math.max(nextImplicitPraiseNumber, Number(praiseMatch[1]) + 1);
      shorthandAllowed = Boolean(praiseMatch);
      entries.push({ label, key, rawLabel, rawKey, content, line: sourceLine });
    }
  });
  if (pending) missingContent(pending);
  return { entries, errors };
}

function isPresenterPreparationContextLine(text = "") {
  const value = String(text || "").trim();
  if (!value) return true;
  if (/^\[[^\]]{1,120}\]$/.test(value)) return true;
  if (/^(?:(?:\d{4}년\s*)?\d{1,2}월\s*\d{1,2}일|\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}\/\d{1,2})\s*.*(?:예배|기도회|집회)(?:\s*\[[^\]]+\])?$/u.test(value)) return true;
  return /(?:예배|기도회|찬양예배|집회)입니다[!.。]?$/u.test(value);
}

function planPresenterPreparationEntries(entries, service) {
  const planned = [];
  const errors = [];
  const targets = new Set();
  for (const entry of entries) {
    if (entry.key === "인용구절") {
      const references = normalizeServiceScriptureReferenceList(entry.content);
      if (!references.length || references.some((reference) => !parseBibleReference(reference))) {
        errors.push(`${entry.line}번째 줄 인용 구절의 성경 주소를 확인해 주세요.`);
      }
      planned.push({ entry });
      continue;
    }
    const targetLabel = presenterPreparationTargetLabel(entry.rawLabel || entry.label, service, entry.content);
    const contentParts = entry.content.split(/\s+\/\s+/);
    const content = String(contentParts.shift() || "").trim();
    const assignee = contentParts.join(" / ").trim();
    const prayerNumber = Number(entry.key.match(/^공동기도(\d+)$/)?.[1]);
    const prayerGroups = prayerNumber ? servicePrepEditorItems(service.id).filter((item) => {
      if (!isMonthlyCorporatePrayerGroupItem(item)) return false;
      const start = Number(String(item.label).match(/\d+/)?.[0]);
      return prayerNumber === start || prayerNumber === start + 1;
    }) : [];
    if (prayerGroups.length > 1) {
      errors.push(`${entry.line}번째 줄 공동기도의 대상이 여러 개입니다.`);
      continue;
    }
    const projected = prayerGroups[0] || findPresenterPreparationProjectedItem(service, targetLabel);
    const corporatePrayerIndex = prayerGroups.length
      ? prayerNumber - Number(String(projected.label).match(/\d+/)?.[0]) : undefined;
    if (!projected) {
      errors.push(`${entry.line}번째 줄 ${entry.label} 항목을 이 예배에서 찾지 못했습니다.`);
      continue;
    }
    // Sermon title and preacher may intentionally address different fields of one item.
    const field = (entry.rawKey || entry.key) === "설교" && !assignee
      && presenterPreparationContentLooksAssignee(content) ? "assignee" : "content";
    const targetKey = `${projected.id || targetLabel}:${corporatePrayerIndex ?? field}`;
    if (targets.has(targetKey)) {
      errors.push(`${entry.line}번째 줄 ${entry.label} 항목이 같은 예배 순서에 중복 지정되었습니다.`);
    }
    targets.add(targetKey);
    const memo = parseServiceItemMemo(projected.memo);
    const mode = isSongServiceLabel(projected.label) || isSpecialSongServiceItem(projected)
      ? servicePraiseInputMode(projected, memo, service)
      : serviceMemoInputMode(memo, projected);
    if (mode === "scripture" || isScriptureBodyServiceItem(projected)) {
      const references = normalizeServiceScriptureReferenceList(content);
      if (!references.length || references.some((reference) => !parseBibleReference(reference))) {
        errors.push(`${entry.line}번째 줄 ${entry.label}의 성경 주소를 확인해 주세요.`);
      }
    }
    planned.push({ entry, projected, content, assignee, mode, corporatePrayerIndex });
  }
  return { planned, errors };
}

function cleanPresenterPreparationContent(value = "") {
  let text = String(value || "")
    .replace(/^\s*[:：·ㆍ•.-]\s*/, "")
    .trim();
  const quotePairs = [
    ['"', '"'],
    ["'", "'"],
    ["“", "”"],
    ["‘", "’"],
    ["「", "」"],
    ["『", "』"],
  ];
  for (const [open, close] of quotePairs) {
    if (text.startsWith(open) && text.endsWith(close)) {
      text = text.slice(open.length, text.length - close.length).trim();
      break;
    }
  }
  return text;
}

function normalizePresenterPreparationEntryContent(label = "", content = "") {
  const text = String(content || "").trim();
  if (!text) return "";
  const labelKey = compactSearchValue(label);
  const isSongSlot = /^찬양\d+$/.test(labelKey)
    || ["찬송가", "찬송", "봉헌찬송", "파송찬송", "폐회찬송", "송영"].includes(labelKey);
  if (!isSongSlot) return text;
  const hymnOnly = text.match(/^(?:새\s*)?(?:찬송가|찬)?\s*(\d{1,4})\s*장?\s*$/);
  if (!hymnOnly) return text;
  const hasHymnSignal = /(?:찬송가|찬|장)/.test(text);
  if (!hasHymnSignal && !/^찬양\d+$/.test(labelKey)) return text;
  return `찬 ${Number(hymnOnly[1])}장`;
}

function normalizePresenterPreparationLineText(line = "") {
  return String(line || "")
    .replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parsePresenterPreparationLine(text = "") {
  const known = parseKnownPresenterPreparationLine(text);
  if (known) return known;
  const match = String(text || "").match(/^([^:：]+?)\s*[:：]\s*(.+)$/);
  if (!match) return null;
  if (/\d\s*$/.test(match[1]) && /^\d/.test(match[2])) return null;
  return {
    rawLabel: match[1],
    label: normalizePresenterPreparationInputLabel(match[1]),
    content: String(match[2] || "").trim(),
  };
}

function inferPresenterPreparationShorthandLine(text = "", praiseNumber = 1) {
  const content = String(text || "").trim();
  if (!content) return null;
  if (presenterPreparationContentLooksAssignee(content)
    || /^(?:담당|인도|설교자|날짜|일시|장소)\s*[:： ]/u.test(content)
    || /\d+\s*:\s*\d+/.test(content)) return null;
  return {
    rawLabel: `찬양 ${Math.max(1, Number(praiseNumber) || 1)}`,
    label: `찬양 ${Math.max(1, Number(praiseNumber) || 1)}`,
    content,
  };
}

function expandPresenterPreparationParsedLine(parsedLine = {}, praiseNumber = 1) {
  const label = String(parsedLine.label || "").trim();
  const rawLabel = String(parsedLine.rawLabel || label).trim();
  const content = String(parsedLine.content || "").trim();
  if (compactSearchValue(label) !== "찬송가") return [{ rawLabel, label, content }];
  const hymnNumbers = presenterPreparationHymnNumbers(content);
  if (!hymnNumbers.length) return [{ rawLabel, label: `찬양 ${Math.max(1, Number(praiseNumber) || 1)}`, content }];
  return hymnNumbers.map((hymnNo, offset) => ({
    rawLabel: "찬송가",
    label: `찬양 ${Math.max(1, Number(praiseNumber) || 1) + offset}`,
    content: `찬 ${hymnNo}장`,
  }));
}

function presenterPreparationHymnNumbers(value = "") {
  const raw = String(value || "").trim();
  if (!raw) return [];
  const normalized = raw
    .replace(/[，、]/g, ",")
    .replace(/\s*(?:찬송가|찬|장)\s*/g, " ")
    .trim();
  const parts = normalized.split(/[,\s/]+/).filter(Boolean);
  return parts.length && parts.every((part) => /^\d{1,3}$/.test(part)) ? parts : [];
}

function presenterPreparationDuplicateKey(key = "", rawKey = "") {
  if (["말씀", "설교"].includes(rawKey)) return rawKey;
  return key;
}

function parseKnownPresenterPreparationLine(text = "") {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const separator = "[:：·ㆍ•.-]";
  const patterns = [
    new RegExp(`^(찬양)\\s*(\\d+)(?=\\s|${separator}|$)\\s*(?:${separator}\\s*)?(.*)$`),
    new RegExp(`^(기도\\s*찬양)\\s*(\\d+)(?=\\s|${separator}|$)\\s*(?:${separator}\\s*)?(.*)$`),
    new RegExp(`^(공동기도)\\s*(\\d+)(?=\\s|${separator}|$)\\s*(?:${separator}\\s*)?(.*)$`),
    new RegExp(`^(기도\\s*찬양|찬송가|찬송|(?:대표\\s*)?기도|성경\\s*봉독\\s*본문|성경\\s*봉독|성경\\s*본문|설교\\s*본문|설교\\s*제목|인용\\s*구절|봉헌\\s*특송|특송|입례\\s*찬양|봉헌\\s*찬양|봉헌\\s*찬송|봉헌\\s*기도|결단\\s*찬양|결단\\s*기도|파송\\s*찬양|파송\\s*찬송|폐회\\s*찬송|축도|송영|말씀|본문|설교)(?=\\s|${separator}|$)\\s*(?:${separator}\\s*)?(.*)$`),
  ];
  for (const pattern of patterns) {
    const match = raw.match(pattern);
    if (!match) continue;
    if (match.length === 4) {
      return {
        rawLabel: `${match[1]} ${match[2]}`,
        label: normalizePresenterPreparationInputLabel(`${match[1]} ${match[2]}`),
        content: String(match[3] || "").trim(),
      };
    }
    return {
      rawLabel: match[1],
      label: normalizePresenterPreparationInputLabel(match[1]),
      content: String(match[2] || "").trim(),
    };
  }
  return null;
}

function normalizePresenterPreparationInputLabel(label = "") {
  const raw = String(label || "").replace(/\s+/g, " ").trim();
  const key = compactSearchValue(raw);
  const aliases = {
    기도: "대표기도",
    대표기도: "대표기도",
    기도찬양: "기도찬양",
    성경: "성경봉독",
    성경본문: "성경봉독",
    성경봉독본문: "성경봉독",
    본문: "설교 본문",
    설교본문: "설교 본문",
    말씀본문: "설교 본문",
    말씀: "설교 본문",
    설교: "설교 제목",
    설교제목: "설교 제목",
    인용구절: "인용 구절",
    봉헌: "봉헌찬송",
    봉헌찬양: "봉헌찬양",
    봉헌찬송: "봉헌찬송",
    봉헌기도: "봉헌기도",
    봉헌특송: "봉헌특송",
    결단: "결단찬양",
    결단찬양: "결단찬양",
    결단기도: "결단기도",
    입례찬양: "입례찬양",
    파송찬양: "파송찬양",
    파송찬송: "파송찬송",
    폐회찬송: "폐회찬송",
  };
  if (aliases[key]) return aliases[key];
  const numbered = key.match(/^(찬양|기도찬양|공동기도)(\d+)$/);
  if (numbered) {
    const displayBase = {
      찬양: "찬양",
      기도찬양: "기도찬양",
      공동기도: "공동기도",
    }[numbered[1]] || numbered[1];
    return `${displayBase} ${Number(numbered[2])}`;
  }
  return raw;
}

function presenterPreparationSermonBodyTargetLabel(service = null) {
  const items = service?.id ? servicePrepEditorItems(service.id) : [];
  const hasSermonBody = items.some((item) =>
    serviceItemSlotKey(item) === "sermon.scripture"
    || (
      String(item?._worshipSectionKey || "").trim() === "sermon"
      && ["설교본문", "본문", "성경본문"].includes(compactSearchValue(item?.label || ""))
    ));
  if (hasSermonBody) return "설교 본문";
  const hasScriptureReading = items.some((item) =>
    ["word.reading", "word.body"].includes(serviceItemSlotKey(item))
    || (
      String(item?._worshipSectionKey || "").trim() === "scripture_reading"
      && compactSearchValue(item?.label || "") === "성경봉독"
    ));
  return hasScriptureReading ? "성경봉독" : "설교 본문";
}

function presenterPreparationContentLooksScriptureReference(value = "") {
  return Boolean(parseBibleReference(normalizeServiceItemReferenceSpacing(String(value || "").trim())));
}

function presenterPreparationContentLooksAssignee(value = "") {
  return /(목사|전도사|강도사|장로|권사|집사|간사|선교사|일동)\s*$/.test(String(value || "").trim());
}

function isPresenterPreparationSermonTitleItem(item = {}) {
  if (serviceItemSlotKey(item) === "sermon.title") return true;
  return String(item?._worshipSectionKey || "").trim() === "sermon"
    && ["설교", "설교제목"].includes(compactSearchValue(item?.label || ""));
}

function presenterPreparationTargetLabel(key = "", service = null, content = "") {
  const sermonBodyTarget = presenterPreparationSermonBodyTargetLabel(service);
  const compactKey = compactSearchValue(key);
  if (compactKey === "말씀" && !presenterPreparationContentLooksScriptureReference(content)) {
    return "설교 제목";
  }
  return {
    대표기도: "대표기도",
    기도찬양: "기도찬양",
    기도: "대표기도",
    성경: "성경봉독",
    성경봉독: "성경봉독",
    성경본문: "성경봉독",
    성경봉독본문: "성경봉독",
    본문: sermonBodyTarget,
    설교: "설교 제목",
    설교제목: "설교 제목",
    설교본문: sermonBodyTarget,
    말씀본문: sermonBodyTarget,
    말씀: sermonBodyTarget,
    인용구절: "인용 구절",
    봉헌: "봉헌찬송",
    결단: "결단찬양",
  }[compactKey] || String(key || "").trim();
}

function findPresenterPreparationProjectedItem(service, label) {
  const labelKey = compactSearchValue(label);
  const items = servicePrepEditorItems(service.id);
  const exact = items.filter((item) => compactSearchValue(item.label || "") === labelKey);
  if (exact.length === 1) return exact[0];
  const aliases = items.filter((item) => compactSearchValue(normalizePresenterPreparationInputLabel(item.label || "")) === labelKey);
  if (aliases.length === 1) return aliases[0];
  if (labelKey === "기도" || labelKey === "대표기도") {
    return items.find((item) =>
      String(item._worshipSectionKey || "") === "prayer"
      && ["기도", "대표기도"].includes(compactSearchValue(item.label || "")));
  }
  if (labelKey === "기도찬양") {
    return items.find((item) =>
      String(item._worshipSectionKey || "") === "prayer_meeting_praise"
      && compactSearchValue(item.label || "").replace(/\d+$/, "") === "기도찬양");
  }
  if (labelKey === "봉헌찬송") {
    return items.find((item) =>
      serviceItemSlotKey(item) === "offering.praise"
      || (
        String(item._worshipSectionKey || "") === "offering"
        && ["봉헌찬송", "봉헌찬양"].includes(compactSearchValue(item.label || ""))
      ));
  }
  if (labelKey === "설교제목") {
    return items.find((item) =>
      serviceItemSlotKey(item) === "sermon.title"
      || (
        String(item._worshipSectionKey || "") === "sermon"
        && ["설교", "설교제목"].includes(compactSearchValue(item.label || ""))
      ));
  }
  const dynamicPraise = createDynamicMainPraiseProjectedItem(service, label);
  if (dynamicPraise) return dynamicPraise;
  const numbered = labelKey.match(/^(.*?)(\d+)$/);
  if (numbered) {
    const baseKey = numbered[1];
    const ordinal = Number(numbered[2]);
    const matches = items.filter((item) => {
      const itemKey = compactSearchValue(item.label || "");
      return itemKey === baseKey || itemKey.replace(/\d+$/, "") === baseKey;
    });
    if (ordinal > 0 && matches[ordinal - 1]) return matches[ordinal - 1];
  }
  return null;
}

function materializePresenterPreparationItem(service, items, projectedItem) {
  const existingIndex = items.findIndex((item) => item.id === projectedItem.id);
  if (existingIndex >= 0) return existingIndex;
  const { _serviceItemIndex, _origIndex, ...projected } = projectedItem;
  items.push(normalizeServiceItem({
    ...projected,
    id: createLocalId(),
    service_id: service.id,
    sort_order: items.length + 1,
    _worshipTemplateProjected: false,
    _worshipTemplatePlaceholder: false,
    _worshipElementTemplateModified: true,
    _worshipSharedContentDirty: true,
  }, items.length));
  return items.length - 1;
}

function applyPresenterPreparationTextUpdateToWorshipElementCache(service = null, update = {}) {
  const serviceId = String(service?.id || "").trim();
  if (!serviceId || !Array.isArray(state.worshipElements) || !Array.isArray(state.worshipSections)) return;
  const sectionById = Object.fromEntries(
    state.worshipSections
      .filter((section) => section.service_id === serviceId)
      .map((section) => [section.id, section]),
  );
  const updateId = String(update.id || "").trim();
  const updateSlotKey = normalizeWorshipSlotKey(update.slotKey);
  const updateSectionKey = String(update.sectionKey || "").trim();
  const updateLabelKey = compactSearchValue(update.label || "");
  const candidates = state.worshipElements
    .map((element) => ({ element, section: sectionById[element.section_id] }))
    .filter(({ section }) => Boolean(section));
  const matchesUpdateSlot = ({ element, section }) => {
    const sourceRef = element.source_ref && typeof element.source_ref === "object" ? element.source_ref : {};
    const config = element.config && typeof element.config === "object" ? element.config : {};
    const elementSlotKey = normalizeWorshipSlotKey(element.slot_key || sourceRef.slotKey || sourceRef.slot_key || config.slotKey || config.slot_key);
    return Boolean(
      updateSlotKey
      && elementSlotKey === updateSlotKey
      && (!updateSectionKey || String(section.section_key || "").trim() === updateSectionKey),
    );
  };
  const matchesUpdateLabel = ({ element, section }) => {
    const sourceRef = element.source_ref && typeof element.source_ref === "object" ? element.source_ref : {};
    const labelKey = compactSearchValue(sourceRef.label || section.title || element.title || "");
    return Boolean(
      updateSectionKey
      && updateLabelKey
      && String(section.section_key || "").trim() === updateSectionKey
      && labelKey === updateLabelKey,
    );
  };
  const matchedElements = uniqueList(
    candidates
      .filter((candidate) =>
        (updateId && candidate.element.id === updateId)
        || matchesUpdateSlot(candidate)
        || matchesUpdateLabel(candidate)
        || (updateSectionKey && String(candidate.section.section_key || "").trim() === updateSectionKey))
      .map(({ element }) => element),
  );
  const rawTitle = String(update.raw_title || "").trim();
  const assignee = cleanServiceAssignee(update.assignee);
  matchedElements.forEach((element) => {
    element.person = assignee;
    if (rawTitle) element.title = rawTitle;
    element.source_ref = element.source_ref && typeof element.source_ref === "object" ? element.source_ref : {};
    if (update.label) element.source_ref.label = String(update.label || "").trim();
    if (updateSlotKey) element.source_ref.slotKey = updateSlotKey;
    element.template_modified = true;
  });
}

function presenterPreparationSongLabels(song = {}) {
  const title = String(song.title || "").trim();
  const subtitle = String(song.subtitle || "").trim();
  const hymnNo = String(song.hymn_no || "").trim();
  return [
    title,
    songServiceOptionLabel(song),
    [title, subtitle].filter(Boolean).join(" "),
    [hymnNo, title].filter(Boolean).join(" "),
    String(song.original_title || "").trim(),
  ].filter(Boolean);
}

function addPresenterPreparationSongIndexEntry(map, key, song) {
  const value = String(key || "").trim();
  if (!value || !song) return;
  const existing = map.get(value);
  if (existing) existing.push(song);
  else map.set(value, [song]);
}

function presenterPreparationSongExactIndex() {
  if (
    state.searchCache.presenterPreparationSongs
    && state.searchCache.presenterPreparationSongSource === state.songs
  ) {
    return state.searchCache.presenterPreparationSongs;
  }

  const index = {
    labels: new Map(),
    strippedTitles: new Map(),
    hymnNos: new Map(),
  };
  (state.songs || []).forEach((song) => {
    presenterPreparationSongLabels(song).forEach((label) => {
      addPresenterPreparationSongIndexEntry(index.labels, compactSearchValue(label), song);
    });
    addPresenterPreparationSongIndexEntry(
      index.strippedTitles,
      compactSearchValue(stripHymnNumber(song.title || "")),
      song,
    );
    addPresenterPreparationSongIndexEntry(index.hymnNos, String(song.hymn_no || "").trim(), song);
  });
  state.searchCache.presenterPreparationSongs = index;
  state.searchCache.presenterPreparationSongSource = state.songs;
  return index;
}

function parsePresenterPreparationHymnHint(value = "") {
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  if (!raw) return { title: "", hymnNo: "" };
  const paren = raw.match(/^(.+?)\s*[(（]\s*(?:새\s*)?(?:찬송가|찬)?\s*(\d+)\s*장?\s*[)）]\s*$/);
  if (paren) return { title: String(paren[1] || "").trim(), hymnNo: String(paren[2] || "").trim() };
  const leading = raw.match(/^(?:새\s*)?(?:찬송가|찬)\s*(\d+)\s*장?\s+(.+)$/);
  if (leading) return { title: String(leading[2] || "").trim(), hymnNo: String(leading[1] || "").trim() };
  const bareLeading = raw.match(/^(\d{1,4})\s*장\s+(.+)$/);
  if (bareLeading) return { title: String(bareLeading[2] || "").trim(), hymnNo: String(bareLeading[1] || "").trim() };
  const bareNumberLeading = raw.match(/^(\d{1,4})\s+(.+)$/);
  if (bareNumberLeading) return { title: String(bareNumberLeading[2] || "").trim(), hymnNo: String(bareNumberLeading[1] || "").trim() };
  const trailing = raw.match(/^(.+?)\s+(?:새\s*)?(?:찬송가|찬)\s*(\d+)\s*장?\s*$/);
  if (trailing) return { title: String(trailing[1] || "").trim(), hymnNo: String(trailing[2] || "").trim() };
  const bareTrailing = raw.match(/^(.+?)\s+(\d{1,4})\s*장\s*$/);
  if (bareTrailing) return { title: String(bareTrailing[1] || "").trim(), hymnNo: String(bareTrailing[2] || "").trim() };
  const prefixedOnly = raw.match(/^(?:새\s*)?(?:찬송가|찬)\s*(\d+)\s*장?\s*$/);
  if (prefixedOnly) return { title: "", hymnNo: String(prefixedOnly[1] || "").trim() };
  const only = raw.match(/^(?:새\s*)?(?:찬송가|찬)?\s*(\d+)\s*장\s*$/);
  if (only && /(?:찬|장)/.test(raw)) return { title: "", hymnNo: String(only[1] || "").trim() };
  return { title: raw, hymnNo: "" };
}

function resolvePresenterPreparationHymnSong(value = "") {
  const hint = parsePresenterPreparationHymnHint(value);
  if (!hint.hymnNo) return null;
  const hymnMatches = presenterPreparationSongExactIndex().hymnNos.get(hint.hymnNo) || [];
  if (!hymnMatches.length) return null;
  if (!hint.title) return hymnMatches.length === 1 ? hymnMatches[0] : null;
  const titleKey = compactSearchValue(hint.title);
  const titled = hymnMatches.filter((song) => [
    song.title,
    stripHymnNumber(song.title || ""),
    songServiceOptionLabel(song),
    song.subtitle,
  ].some((label) => compactSearchValue(label) === titleKey));
  return titled.length === 1 ? titled[0] : (hymnMatches.length === 1 ? hymnMatches[0] : null);
}

function resolvePresenterPreparationSong(value, item, service) {
  const songInput = presenterPreparationSongContent(value);
  const query = compactSearchValue(songInput);
  if (!query) return null;
  if (presenterPreparationSongContentHasConnection(songInput)) return null;
  const hymnSong = resolvePresenterPreparationHymnSong(songInput);
  if (hymnSong) return hymnSong;
  const songIndex = presenterPreparationSongExactIndex();
  const exact = songIndex.labels.get(query) || [];
  if (exact.length === 1) return exact[0];
  const titleExact = songIndex.strippedTitles.get(query) || [];
  if (titleExact.length === 1) return titleExact[0];
  const praiseSong = findServicePraiseSong(songInput);
  if (praiseSong) return praiseSong;
  return findConfidentServicePraiseSong(songInput, item, service);
}

function resolveExistingPraiseSongForServiceInput(value, item = {}, service = selectedServiceForEditor()) {
  const songInput = presenterPreparationSongContent(value);
  const title = stripHymnNo(songInput).title.trim();
  const candidates = [...new Set([songInput, title].map((entry) => String(entry || "").trim()).filter(Boolean))];
  for (const candidate of candidates) {
    const song = resolvePresenterPreparationSong(candidate, item, service)
      || findServicePraiseSong(candidate)
      || findConfidentServicePraiseSong(candidate, item, service);
    if (song) return song;
  }
  return null;
}

async function resolveExistingPraiseSongForServiceInputAfterCatalogLoad(value, item = {}, service = selectedServiceForEditor()) {
  const existing = resolveExistingPraiseSongForServiceInput(value, item, service);
  if (existing) return existing;
  if (!state.client || songCatalogLoaded) return null;
  await loadSongs();
  return resolveExistingPraiseSongForServiceInput(value, item, service);
}

function presenterPreparationSongContent(value = "") {
  const text = cleanPresenterPreparationContent(value);
  // Keys such as G or D are notes for the instrumental team, not part of a song title.
  return stripServiceSongInputPrefix(stripServicePraiseTrailingMusicKey(text));
}

function presenterPreparationSongContentHasConnection(value = "") {
  return /\s[+＋]\s/u.test(String(value || "").normalize("NFKC"));
}

function findConfidentServicePraiseSong(value, item = {}, service = selectedServiceForEditor()) {
  const songInput = presenterPreparationSongContent(value);
  const tokens = getSearchTokens(songInput);
  if (!tokens.length) return null;

  const requiresNewHymnal = serviceItemRequiresNewHymnalScoreSong(item);
  const query = compactSearchValue(songInput);
  const ranked = state.songs
    .filter((song) => !requiresNewHymnal || isNewHymnalScoreSong(song))
    .map((song) => ({ song, match: getSongSearchMatch(song, tokens) }))
    .filter((entry) => entry.match)
    .sort((a, b) => b.match.score - a.match.score || sortSongsForCurrentList(a.song, b.song));
  if (!ranked.length) return null;

  const exact = ranked.filter((entry) => presenterPreparationSongLabels(entry.song)
    .some((label) => compactSearchValue(label) === query));
  if (exact.length === 1) return exact[0].song;
  if (exact.length > 1) return exact[0].song;

  const [best, second] = ranked;
  const gap = best.match.score - (second?.match.score || 0);
  if (best.match.phraseMatched && (gap >= 20 || ranked.length === 1)) return best.song;
  return null;
}

async function createBlankPraiseSongForServiceInput(value, service = selectedServiceForEditor(), item = {}) {
  const existing = await resolveExistingPraiseSongForServiceInputAfterCatalogLoad(value, item, service);
  if (existing) return existing;
  if (!state.client) return null;

  const title = stripHymnNo(presenterPreparationSongContent(value)).title.trim();
  if (presenterPreparationSongContentHasConnection(title)) return null;
  if (!title) return null;

  const praiseType = service?.type_id === "children" ? "children" : "ccm";
  const defaultVersion = {
    id: createUuid(),
    name: "기본",
    is_primary: true,
    praise_types: [praiseType],
    forms: [],
  };
  const useVersionTables = state.songVersionTablesSupported === true;
  const payload = {
    title,
    praise_types: [praiseType],
    memo: useVersionTables ? null : serializeSongMemo({ versions: [defaultVersion] }),
  };
  const { data, error } = await state.client
    .from("mindex_songs")
    .insert(payload)
    .select("*")
    .single();
  if (error) throw error;

  const song = normalizeServerSong(data);
  song.versions = normalizeSongVersions(song, song.versions?.length ? song.versions : [defaultVersion]);
  song._memoHasVersions = !useVersionTables;
  if (useVersionTables) {
    try {
      await saveSongVersions(song);
    } catch (saveError) {
      if (!isUnavailableRelationError(saveError)) throw saveError;
      state.songVersionTablesSupported = false;
      song._memoHasVersions = true;
      await state.client
        .from("mindex_songs")
        .update({ memo: serializeSongMemo(song) })
        .eq("id", song.id);
    }
  }
  state.songs = [song, ...state.songs.filter((candidate) => candidate.id !== song.id)].sort(sortSongs);
  clearSearchCaches();
  return song;
}
