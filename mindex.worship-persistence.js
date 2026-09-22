// Persistence-shaped worship document rules.
// Supabase I/O stays in app.js; this file owns only source_ref normalization and history compaction.

function serviceRawSourceRef(service = null) {
  if (!service || typeof service !== "object") return {};
  if (service._worshipSourceRef && typeof service._worshipSourceRef === "object") return service._worshipSourceRef;
  if (service.source_ref && typeof service.source_ref === "object") return service.source_ref;
  return {};
}

const serviceSourceRefCache = new WeakMap();
function serviceSourceRef(service = null) {
  const raw = serviceRawSourceRef(service);
  const keys = Object.keys(raw);
  if (!keys.length) return {};
  const cached = serviceSourceRefCache.get(raw);
  if (cached && cached.keys.length === keys.length
    && keys.every((key, index) => cached.keys[index] === key && cached.values[index] === raw[key])) {
    return cached.result;
  }
  const result = normalizeServiceSourceRef(raw);
  serviceSourceRefCache.set(raw, { keys, values: keys.map((key) => raw[key]), result });
  return result;
}

function normalizeServiceSourceRef(sourceRef = {}) {
  if (!sourceRef || typeof sourceRef !== "object") return {};
  const normalized = { ...sourceRef };
  const document = normalizeServiceDocumentSnapshot(normalized[MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY]);
  if (document) normalized[MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY] = document;
  else delete normalized[MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY];
  const history = normalizeServiceDocumentHistory(normalized[MINDEX_SERVICE_DOCUMENT_HISTORY_SOURCE_REF_KEY]);
  if (history.length) normalized[MINDEX_SERVICE_DOCUMENT_HISTORY_SOURCE_REF_KEY] = history;
  else delete normalized[MINDEX_SERVICE_DOCUMENT_HISTORY_SOURCE_REF_KEY];
  return normalized;
}

function normalizeServiceDocumentHistory(history = []) {
  return trimServiceDocumentHistory((Array.isArray(history) ? history : [])
    .map((entry) => normalizeServiceDocumentSnapshot(entry))
    .filter(Boolean));
}

function normalizeServiceDocumentSnapshot(document = null) {
  if (!document || typeof document !== "object") return null;
  const sourceText = limitServiceDocumentText(document.sourceText || document.source_text || "");
  const sourceRecords = normalizeServiceDocumentSourceRecords(document.sourceRecords || document.source_records);
  const slides = normalizeServiceDocumentSlides(document.slides);
  const exceptions = normalizeServiceDocumentExceptions(document.exceptions);
  const payload = {
    kind: document.kind || MINDEX_SERVICE_DOCUMENT_KIND,
    version: document.version || MINDEX_SERVICE_DOCUMENT_VERSION,
    serviceId: String(document.serviceId || document.service_id || "").trim(),
    serviceTypeId: String(document.serviceTypeId || document.service_type_id || "").trim(),
    serviceDate: String(document.serviceDate || document.service_date || "").trim(),
    serviceTitle: String(document.serviceTitle || document.service_title || "").trim(),
    serviceAlias: String(document.serviceAlias || document.service_alias || "").trim(),
    updatedAt: document.updatedAt || document.updated_at || "",
    sourceSignature: document.sourceSignature || document.source_signature || compactTextSignature(sourceText),
    slideSignature: document.slideSignature || document.slide_signature || compactTextSignature(JSON.stringify(slides)),
    sourceText,
    sourceRecords,
    slides,
    exceptions,
  };
  const sourceRecordCount = Number(document.sourceRecordCount);
  const slideCount = Number(document.slideCount);
  if (Number.isFinite(sourceRecordCount) && sourceRecordCount > 0) payload.sourceRecordCount = sourceRecordCount;
  if (Number.isFinite(slideCount) && slideCount > 0) payload.slideCount = slideCount;
  if (typeof document.contentSignature === "string" && document.contentSignature) payload.contentSignature = document.contentSignature;
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => {
    if (Array.isArray(value)) return value.length;
    return value !== "" && value != null;
  }));
}

function serviceDocumentHistoryWithPrevious(previousDocument = null, previousHistory = [], currentDocument = null) {
  const entries = [];
  const seen = new Set();
  const currentKey = serviceDocumentHistoryEntryKey(currentDocument);
  const append = (entry) => {
    const compact = compactServiceDocumentHistoryEntry(entry);
    const key = serviceDocumentHistoryEntryKey(compact);
    if (!compact || !key || key === currentKey || seen.has(key)) return;
    seen.add(key);
    entries.push(compact);
  };
  append(previousDocument);
  (Array.isArray(previousHistory) ? previousHistory : []).forEach(append);
  return trimServiceDocumentHistory(entries);
}

function normalizeServiceDocumentSourceRecords(records = []) {
  return (Array.isArray(records) ? records : []).map((record, index) => {
    if (!record || typeof record !== "object") return null;
    const linkedSource = record.linkedSource && typeof record.linkedSource === "object" ? record.linkedSource : {};
    const asset = record.asset && typeof record.asset === "object" ? normalizeServiceAsset(record.asset) : null;
    const payload = {
      index: Number(record.index) || index + 1,
      recordKey: String(record.recordKey || record.record_key || "").trim(),
      elementId: String(record.elementId || record.element_id || "").trim(),
      sectionId: String(record.sectionId || record.section_id || "").trim(),
      sectionKey: String(record.sectionKey || record.section_key || "").trim(),
      slotKey: normalizeWorshipSlotKey(record.slotKey || record.slot_key || linkedSource.slotKey || linkedSource.slot_key),
      sectionTitle: String(record.sectionTitle || record.section_title || "").trim(),
      label: String(record.label || "").trim(),
      value: normalizeServiceItemReferenceSpacing(record.value || ""),
      assignee: String(record.assignee || "").trim(),
      lyrics: limitServiceDocumentText(record.lyrics || ""),
      linkedSource,
    };
    if (asset && hasServiceAsset(asset)) payload.asset = asset;
    payload.recordKey = payload.recordKey || serviceDocumentRecordKey(payload);
    return Object.fromEntries(Object.entries(payload).filter(([, value]) => {
      if (value && typeof value === "object") return Object.keys(value).length;
      return value !== "" && value != null;
    }));
  }).filter(Boolean);
}

function normalizeServiceDocumentSlides(slides = []) {
  return (Array.isArray(slides) ? slides : []).map((slide, index) => {
    if (!slide || typeof slide !== "object") return null;
    const linkedSource = slide.linkedSource && typeof slide.linkedSource === "object" ? slide.linkedSource : {};
    const asset = normalizeServiceAsset(slide.asset || slide.media);
    const slotKey = normalizeWorshipSlotKey(slide.slotKey || slide.slot_key || linkedSource.slotKey || linkedSource.slot_key);
    const payload = {
      index: Number(slide.index) || index + 1,
      slideKey: String(slide.slideKey || slide.slide_key || "").trim(),
      id: String(slide.id || "").trim(),
      elementId: String(slide.elementId || slide.element_id || "").trim(),
      sectionId: String(slide.sectionId || slide.section_id || "").trim(),
      sectionKey: String(slide.sectionKey || slide.section_key || "").trim(),
      slotKey,
      elementLabel: String(slide.elementLabel || slide.element_label || slide.label || "").trim(),
      type: String(slide.type || "").trim(),
      layout: String(slide.layout || "").trim(),
      elementType: String(slide.elementType || slide.element_type || "").trim(),
      title: String(slide.title || "").trim(),
      text: limitServiceDocumentText(slide.text || slide.bodyText || slide.body || ""),
      outputContext: String(slide.outputContext || slide.output_context || "").trim(),
      hidden: Boolean(slide.hidden),
      autoTrailingBlank: Boolean(slide.autoTrailingBlank || slide.auto_trailing_blank),
      linkedSource,
    };
    if (asset.name || asset.url || asset.kind) payload.asset = asset;
    if (slide.imageSrc || slide.image_src) payload.imageSrc = String(slide.imageSrc || slide.image_src || "").trim();
    if (slide.videoSrc || slide.video_src) payload.videoSrc = String(slide.videoSrc || slide.video_src || "").trim();
    if (slide.audioSrc || slide.audio_src) payload.audioSrc = String(slide.audioSrc || slide.audio_src || "").trim();
    payload.slideKey = payload.slideKey || serviceDocumentSlideKey(payload);
    return Object.fromEntries(Object.entries(payload).filter(([, value]) => {
      if (Array.isArray(value)) return value.length;
      if (value && typeof value === "object") return Object.keys(value).length;
      return value !== "" && value !== false && value != null;
    }));
  }).filter(Boolean);
}

function normalizeServiceDocumentExceptions(exceptions = []) {
  return (Array.isArray(exceptions) ? exceptions : []).map((entry) => {
    if (!entry || typeof entry !== "object") return null;
    const payload = {
      type: String(entry.type || "").trim(),
      scope: String(entry.scope || "").trim(),
      target: entry.target && typeof entry.target === "object" ? entry.target : {},
      asset: normalizeServiceAsset(entry.asset),
      reason: String(entry.reason || "").trim(),
    };
    return Object.fromEntries(Object.entries(payload).filter(([, value]) => {
      if (value && typeof value === "object") return Object.keys(value).length;
      return value !== "" && value != null;
    }));
  }).filter(Boolean);
}

function serviceDocumentRecordKey(record = {}) {
  return cleanList([
    record.slotKey || "",
    record.elementId || "",
    record.sectionKey || compactSearchValue(record.sectionTitle || ""),
    compactSearchValue(record.label || ""),
  ]).join("|");
}

function serviceDocumentSlideKey(slide = {}) {
  return cleanList([
    slide.slotKey || "",
    slide.elementId || "",
    slide.id || "",
    slide.type || "",
    slide.index ? `#${slide.index}` : "",
  ]).join("|");
}

function serviceDocumentHistoryContentSignature(document = null) {
  const content = {
    kind: document.kind || MINDEX_SERVICE_DOCUMENT_KIND,
    version: document.version || MINDEX_SERVICE_DOCUMENT_VERSION,
    serviceId: document.serviceId || "",
    serviceTypeId: document.serviceTypeId || "",
    serviceDate: document.serviceDate || "",
    serviceTitle: document.serviceTitle || "",
    serviceAlias: document.serviceAlias || "",
    sourceSignature: document.sourceSignature || "",
    slideSignature: document.slideSignature || "",
    sourceText: limitServiceDocumentText(document.sourceText || ""),
    sourceRecords: Array.isArray(document.sourceRecords) ? document.sourceRecords : [],
    slides: Array.isArray(document.slides) ? document.slides : [],
    exceptions: Array.isArray(document.exceptions) ? document.exceptions : [],
  };
  return compactTextSignature(JSON.stringify(Object.fromEntries(Object.entries(content).filter(([, value]) => {
    if (Array.isArray(value)) return value.length;
    return value !== "" && value != null;
  }))));
}

function compactServiceDocumentHistoryEntry(document = null) {
  document = normalizeServiceDocumentSnapshot(document);
  if (!document) return null;
  const records = Array.isArray(document.sourceRecords) ? document.sourceRecords : [];
  const slides = Array.isArray(document.slides) ? document.slides : [];
  const exceptions = Array.isArray(document.exceptions) ? document.exceptions : [];
  const hasArrays = Boolean(records.length || slides.length || exceptions.length);
  const payload = {
    kind: document.kind || MINDEX_SERVICE_DOCUMENT_KIND,
    version: document.version || MINDEX_SERVICE_DOCUMENT_VERSION,
    serviceId: document.serviceId || "",
    serviceTypeId: document.serviceTypeId || "",
    serviceDate: document.serviceDate || "",
    serviceTitle: document.serviceTitle || "",
    serviceAlias: document.serviceAlias || "",
    updatedAt: document.updatedAt || "",
    sourceSignature: document.sourceSignature || "",
    slideSignature: document.slideSignature || "",
    contentSignature: hasArrays ? serviceDocumentHistoryContentSignature(document) : (document.contentSignature || ""),
    sourceText: limitServiceDocumentText(document.sourceText || ""),
    sourceRecordCount: records.length || Number(document.sourceRecordCount) || 0,
    slideCount: slides.length || Number(document.slideCount) || 0,
  };
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== "" && value != null && value !== 0));
}

function serviceDocumentHistoryEntryKey(document = null) {
  if (!document || typeof document !== "object") return "";
  const entry = compactServiceDocumentHistoryEntry(document);
  if (!entry) return "";
  return [entry.contentSignature || `text:${entry.sourceSignature || ""}:${entry.slideSignature || ""}`, entry.sourceText || ""].join("|");
}

function trimServiceDocumentHistory(entries = []) {
  const trimmed = entries.slice(0, MINDEX_SERVICE_DOCUMENT_HISTORY_LIMIT);
  while (trimmed.length > 1 && JSON.stringify(trimmed).length > MINDEX_SERVICE_DOCUMENT_HISTORY_MAX_BYTES) {
    trimmed.pop();
  }
  return trimmed;
}
