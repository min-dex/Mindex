// Presenter slide/output helpers split from app.js.
// Runtime order is constants -> presenter -> app. Shared controller helpers are
// owned by app.js and must not be redeclared here; tests/solid_audit.py enforces it.

const PRESENTER_SONG_NOTE = "♬";
const PRESENTER_SONG_NOTE_PATTERN = /^[\u2669\u266A\u266B\u266C]\s*/u;
const PRESENTER_DEFAULT_CHROMAKEY_READY_LOOP_VIDEO = "assets/presenter/chromakey-ready-loop-fast.mp4?v=source-quality-20260913";

function presenterSlidesWithIntroSlide(item = {}, section = {}, index = 0, memo = emptyServiceItemMemo(), slides = []) {
  const list = Array.isArray(slides) ? slides.filter(Boolean) : [];
  if (!list.length) return list;
  const introSlide = presenterIntroSlideFromMemo(item, section, index, memo);
  if (!introSlide) return list;
  const introBody = presenterTitleContentBodyText(introSlide);
  const alreadyPresent = list.some((slide) =>
    slide?._introSlide
    || (
      slide?.type === "title-content"
      && normalizeTitle(slide.title) === normalizeTitle(introSlide.title)
      && normalizeTitle(presenterTitleContentBodyText(slide)) === normalizeTitle(introBody)
    ));
  return alreadyPresent ? list : [introSlide, ...list];
}

function presenterIntroSlideFromMemo(item = {}, section = {}, index = 0, memo = emptyServiceItemMemo()) {
  const intro = normalizeServiceIntroSlide(memo.introSlide);
  if (!intro) return null;
  const title = intro.title || section.sectionTitle || item.label || "제목";
  const bodyText = intro.body || "";
  return {
    id: `${item.id || index}:intro-title`,
    ...section,
    elementLabel: item.label || section.elementLabel || "제목 / 내용",
    elementTitle: title,
    elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
    layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
    type: "title-content",
    label: item.label || "",
    title,
    bodyText,
    marker: "",
    text: [title, bodyText].filter(Boolean).join("\n"),
    sort: index - 0.001,
    _introSlide: true,
  };
}

function presenterSlidesWithSpecialSongTitle(item = {}, section = {}, slides = [], index = 0, service = null) {
  if (!shouldIncludeSpecialSongSectionTitleSlide(item, section, slides)) {
    return presenterSlidesWithSundayMainSpecialSongOutput(slides, item, section, service);
  }
  const titleSlideIndex = slides.findIndex((slide) => slide?.type === "song-title");
  const existingSpecialTitleIndex = slides.findIndex((slide) =>
    slide?.type === "title-assignee"
    && !slide.songTitle
    && normalizeTitle(slide.title) === normalizeTitle(item.label || section.sectionLabel || "특송"));
  const existingSpecialTitle = existingSpecialTitleIndex >= 0 ? slides[existingSpecialTitleIndex] : null;
  if (existingSpecialTitle?.missingContent) {
    return presenterSlidesWithSundayMainSpecialSongOutput(slides, item, section, service);
  }
  const titleSlide = titleSlideIndex >= 0 ? slides[titleSlideIndex] : null;
  const remainingSlides = slides.filter((_, slideIndex) =>
    slideIndex !== existingSpecialTitleIndex)
    .map((slide) => slide?.type === "song-title" || slide?.songTitle
      ? { ...slide, songTitleContent: { ...presenterSongTitleContent(slide), orderTitle: "" } }
      : slide);
  return presenterSlidesWithSundayMainSpecialSongOutput([
    presenterSpecialSongSectionTitleSlide(item, section, index, titleSlide),
    ...remainingSlides,
  ], item, section, service);
}

function presenterSlidesWithScriptureReadingTitle(item = {}, section = {}, slides = [], index = 0, service = null) {
  const list = Array.isArray(slides) ? slides.filter(Boolean) : [];
  if (!list.length || presenterScriptureBodyContext(item, section) !== "reading") return list;
  const existingTitle = list.some((slide) =>
    slide?.type === "title-assignee"
    && compactSearchValue(slide.title || slide.label || "") === "성경봉독");
  if (existingTitle) return list;
  const references = typeof serviceItemScriptureReferences === "function"
    ? serviceItemScriptureReferences(item, parseServiceItemMemo(item.memo), service)
    : [];
  const reference = references.length && typeof formatServiceScriptureReferenceList === "function"
    ? formatServiceScriptureReferenceList(references)
    : String(list[0]?.title || list[0]?.marker || item.raw_title || "").trim();
  return [presenterScriptureReadingTitleSlide(item, section, index, reference), ...list];
}

function presenterScriptureReadingTitleSlide(item = {}, section = {}, index = 0, reference = "") {
  const title = "성경봉독";
  const assignee = presenterScriptureReadingDisplayReference(reference);
  return {
    id: `${item.id || index}:scripture-reading-title`,
    ...section,
    elementLabel: title,
    elementTitle: title,
    elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "title-assignee",
    label: title,
    title,
    assignee,
    marker: "",
    text: cleanList([title, assignee]).join("\n"),
    sort: index - 0.002,
  };
}

function presenterScriptureReadingDisplayReference(value = "") {
  return String(value || "")
    .split(";")
    .map((part) => {
      const text = part.trim();
      const match = text.match(/^(.+?)\s+(\d{1,3}(?::|장|\s|$).*)$/);
      if (!match) return text;
      return [presenterScriptureReadingBookName(match[1]), match[2]].filter(Boolean).join(" ");
    })
    .filter(Boolean)
    .join("; ");
}

function shouldIncludeSpecialSongSectionTitleSlide(item = {}, section = {}, slides = []) {
  if (!slides.length) return false;
  const sectionKey = String(section.sectionKey || item?._worshipSectionKey || "").trim();
  if (!isPresenterSpecialSongItem(item, section)) return false;
  return true;
}

function isPresenterSpecialSongItem(item = {}, section = {}) {
  if (isSpecialSongServiceItem(item)) return true;
  const sectionKey = String(section.sectionKey || item?._worshipSectionKey || "").trim();
  if (sectionKey === "special_song") return true;
  return compactSearchValue(item?._worshipSectionTitle || "") === "특송";
}

function presenterSlidesWithSundayMainSpecialSongOutput(slides = [], item = {}, section = {}, service = null) {
  if (!shouldUseSundayMainSpecialSongCleanOutput(item, section, service)) return slides;
  return (Array.isArray(slides) ? slides : []).map((slide) => ({
    ...slide,
    outputContext: "clean",
  }));
}

function shouldUseSundayMainSpecialSongCleanOutput(item = {}, section = {}, service = null) {
  if (String(section.sectionKey || item._worshipSectionKey || "") === "offering") return false;
  if (!isPresenterSpecialSongItem(item, section)) return false;
  const rawType = String(service?.type_id || service?.typeId || "").trim();
  const typeId = typeof worshipAppServiceTypeId === "function"
    ? worshipAppServiceTypeId(rawType)
    : rawType;
  return typeId === "sunday-main" && !isPresenterAllGenerationsService(service);
}

function isPresenterAllGenerationsService(service = null) {
  if (!service || typeof service !== "object") return false;
  const sourceRef = service._worshipSourceRef && typeof service._worshipSourceRef === "object"
    ? service._worshipSourceRef
    : service.source_ref && typeof service.source_ref === "object"
      ? service.source_ref
      : {};
  const variant = String(sourceRef.sunday_main_variant || "").trim().toLowerCase();
  if (variant === "all_generations") return true;
  return compactSearchValue([service.alias, service.service_alias].filter(Boolean).join(" ")).includes("온세대찬양예배");
}

function presenterSpecialSongSectionTitleSlide(item = {}, section = {}, index = 0, songTitleSlide = null) {
  const title = item.label || section.sectionLabel || "특송";
  const assignee = cleanServiceAssignee(item.assignee);
  const subtitle = assignee;
  const text = [title, subtitle].filter(Boolean).join("\n");
  return {
    id: `${item.id || index}:special-title`,
    ...section,
    elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "title-assignee",
    label: title,
    title,
    subtitle,
    assignee: subtitle,
    marker: "",
    text,
    sort: index - 0.002,
  };
}

function presenterSpecialSongDisplayTitle(item = {}, songTitleSlide = null) {
  const rawTitle = String(item.raw_title || item.title || "").trim();
  const genericLabel = compactSearchValue(item.label || "특송");
  const fromSlideText = String(songTitleSlide?.text || "").replace(PRESENTER_SONG_NOTE_PATTERN, "").trim();
  if (fromSlideText && (rawTitle || compactSearchValue(fromSlideText) !== genericLabel)) return fromSlideText;
  const marker = String(songTitleSlide?.marker || "").trim();
  const title = String(songTitleSlide?.title || "").trim();
  const titleText = [marker, title].filter(Boolean).join(" ");
  if (titleText && (rawTitle || compactSearchValue(titleText) !== genericLabel)) return titleText;
  return rawTitle.replace(PRESENTER_SONG_NOTE_PATTERN, "").trim();
}

const PRESENTER_PUBLIC_LORDS_PRAYER_TEXT = `하늘에 계신 우리 아버지,
아버지의 이름을 거룩하게 하시며
아버지의 나라가 오게 하시며,
아버지의 뜻이 하늘에서와 같이 땅에서도 이루어지게 하소서.
오늘 우리에게 일용할 양식을 주시고,
우리가 우리에게 잘못한 사람을 용서하여 준 것같이,
우리 죄를 용서하여 주시고,
우리를 시험에 빠지지 않게 하시고, 악에서 구하소서.
나라와 권능과 영광이
영원히 아버지의 것입니다. 아멘.`;

const PRESENTER_PUBLIC_APOSTLES_CREED_TEXT = `나는 전능하신 아버지 하나님, 천지의 창조주를 믿습니다.
나는 그의 유일하신 아들, 우리 주 예수 그리스도를 믿습니다.
그는 성령으로 잉태되어 동정녀 마리아에게서 나시고,
본디오 빌라도에게 고난을 받아 십자가에 못 박혀 죽으시고,
장사된 지 사흘 만에 죽은 자 가운데서 다시 살아나셨으며,
하늘에 오르시어 전능하신 아버지 하나님 우편에 앉아 계시다가,
거기로부터 살아 있는 자와 죽은 자를 심판하러 오십니다.
나는 성령을 믿으며, 거룩한 공교회와 성도의 교제와
죄를 용서받는 것과 몸의 부활과 영생을 믿습니다. 아멘.`;

const PRESENTER_PUBLIC_APOSTLES_CREED_CHROMAKEY_TEXT = `나는 전능하신 아버지 하나님,
천지의 창조주를 믿습니다.
나는 그의 유일하신 아들,
우리 주 예수 그리스도를 믿습니다.
그는 성령으로 잉태되어
동정녀 마리아에게서 나시고,
본디오 빌라도에게 고난을 받아
십자가에 못 박혀 죽으시고,
장사된 지 사흘 만에
죽은 자 가운데서 다시 살아나셨으며,
하늘에 오르시어 전능하신 아버지
하나님 우편에 앉아 계시다가,
거기로부터 살아 있는 자와
죽은 자를 심판하러 오십니다.
나는 성령을 믿으며,
거룩한 공교회와 성도의 교제와
죄를 용서받는 것과
몸의 부활과 영생을 믿습니다. 아멘.`;

const PRESENTER_SCRIPTURE_READING_BACKGROUND = "assets/worship-backgrounds/scripture-reading-cross.png";
const PRESENTER_CHURCH_LOGO = "assets/presenter/church-logo-white.png";

const PRESENTER_PUBLIC_COMMUNITY_CONFESSION_TEXT = `우리는 세상으로부터 부름 받은 하나님의 거룩한 백성입니다.
또한 세상으로 보냄 받은 그리스도의 제자입니다.
하나님을 기쁘게 찬양하는 성령 충만한 예배자가 되겠습니다.
진리를 배우고 수호하는 은혜에 빚진 훈련자가 되겠습니다.
땅 끝까지 복음을 전파하는 전도자가 되겠습니다.
이웃의 아픔을 함께하는 치유자가 되겠습니다.
온 성도가 하나 되는 화해자가 되겠습니다.
사회적 책임을 다하는 소명자가 되겠습니다.
그리하여 우리 모두 하나님을 영화롭게 하는
검단우리교회 공동체가 되겠습니다.`;

const PRESENTER_PUBLIC_COMMUNITY_CONFESSION_CHROMAKEY_SLIDES = Object.freeze([
  "우리는 세상으로부터 부름 받은\n하나님의 거룩한 백성입니다.",
  "또한 세상으로 보냄 받은\n그리스도의 제자입니다.",
  "하나님을 기쁘게 찬양하는\n성령 충만한 예배자가 되겠습니다.",
  "진리를 배우고 수호하는\n은혜에 빚진 훈련자가 되겠습니다.",
  "땅 끝까지 복음을 전파하는\n전도자가 되겠습니다.",
  "이웃의 아픔을 함께하는\n치유자가 되겠습니다.",
  "온 성도가 하나 되는\n화해자가 되겠습니다.",
  "사회적 책임을 다하는\n소명자가 되겠습니다.",
  "그리하여 우리 모두 하나님을 영화롭게 하는\n검단우리교회 공동체가 되겠습니다.",
]);

function serviceItemOutputMode(item = {}, memo = parseServiceItemMemo(item?.memo)) {
  const mode = normalizeServiceOutputMode(
    memo.outputMode
    || item.outputMode
    || item.output_mode
    || item.renderMode
    || item.render_mode,
  );
  const flexibleOffering = typeof serviceItemUsesFlexibleOfferingSlot === "function"
    && serviceItemUsesFlexibleOfferingSlot(item);
  return flexibleOffering && mode === "score" && !presenterServiceItemUsesScoreInputMode(item, memo) ? "" : mode;
}

function presenterServiceItemUsesScoreInputMode(item = {}, memo = {}) {
  const raw = String(memo.inputMode || memo.input_mode || item.inputMode || item.input_mode || "").trim().toLowerCase();
  if (["score_db", "score", "music_score", "sheet_music", "악보"].includes(raw)) return true;
  return normalizeServiceOutputMode(
    memo.outputMode
    || item.outputMode
    || item.output_mode
    || item.renderMode
    || item.render_mode,
  ) === "score";
}

function presenterScoreSlidesForServiceItem(
  item,
  section,
  index,
  song,
  version,
  displayText,
  memo = parseServiceItemMemo(item?.memo),
  forms = [],
  formWarnings = [],
) {
  const label = item?.label || "";
  const asset = normalizeServiceAsset(memo.asset || item.asset);
  const title = presenterSongTitleDisplayTitle(song, version, displayText) || displayText || label || "악보";
  const imageSlides = presenterScoreImageSlidesFromAsset(asset, item, section, index, title, label, song, version, displayText, forms, formWarnings);
  if (imageSlides.length) return imageSlides;
  const scoreAsset = { ...asset, kind: asset.kind || "score" };
  if (!String(scoreAsset.url || "").trim()) return [];
  const fileTitle = presenterFileDisplayTitle({ title, asset: scoreAsset }, "악보");
  const scoreForms = presenterScoreFormsFromImageSources([{ formLabel: asset.formLabel || asset.form_label || asset.scoreFormLabel || asset.score_form_label }]);
  return [{
    id: `${item.id || index}:score`,
    ...section,
    sectionLabel: section.sectionLabel || label || "악보",
    sectionTitle: section.sectionTitle || section.sectionLabel || label || "악보",
    sectionName: presenterNameParts(section.sectionLabel || label, fileTitle).join(" / ") || fileTitle,
    elementTitle: fileTitle,
    elementType: PRESENTER_ELEMENT_TYPES.FILE,
    layout: PRESENTER_SLIDE_LAYOUTS.FILE,
    type: "file",
    label,
    title: fileTitle,
    subtitle: versionDisplayName(song, version),
    marker: "악보",
    text: [fileTitle, scoreAsset.url].filter(Boolean).join("\n"),
    asset: scoreAsset,
    ...presenterScoreFormMetadata(scoreForms, 0, formWarnings),
    sourceType: "score",
    componentType: "score",
    sort: index,
  }];
}

function presenterScoreImageSlidesFromAsset(
  asset,
  item,
  section,
  index,
  title,
  label,
  song = null,
  version = null,
  displayText = "",
  forms = [],
  formWarnings = [],
) {
  const explicitSources = [
    ...normalizeServiceAssetSlides(asset?.slides),
    ...normalizeServiceAssetSlides(asset?.images),
    ...normalizeServiceAssetSlides(asset?.urls),
    ...presenterImageSourcesFromAssetUrl(asset?.url),
  ];
  const sources = explicitSources.length ? explicitSources : presenterHymnScoreAssetSlides(song, version, displayText);
  const imageSources = sources
    .map((slide, slideIndex) => ({
      url: normalizePresenterMediaSource(slide.url),
      name: String(slide.name || "").trim(),
      formLabel: presenterScoreFormLabelFromAssetSlide(slide),
      formKey: String(slide.formKey || slide.form_key || slide.scoreFormKey || slide.score_form_key || "").trim(),
      order: Number(slide.order) || slideIndex + 1,
    }))
    .filter((slide) => slide.url && presenterMediaSourceIsImage(slide.url));
  const count = imageSources.length;
  const scoreForms = presenterScoreFormsFromImageSources(imageSources);
  const sequenced = presenterScoreImageSourcesForFormSequence(imageSources, scoreForms, forms, item, song, version);
  return sequenced.imageSources.map((slide, slideIndex) => {
    return {
      id: `${item.id || index}:score-image:${slideIndex}`,
      ...section,
      sectionLabel: section.sectionLabel || label || "악보",
      sectionTitle: section.sectionTitle || section.sectionLabel || label || "악보",
      sectionName: presenterNameParts(section.sectionLabel || label, title).join(" / ") || title,
      elementTitle: title,
      elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
      layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
      type: "image",
      label,
      title,
      subtitle: versionDisplayName(song, version),
      marker: "",
      text: slide.name || title,
      imageSrc: slide.url,
      asset: { ...asset, kind: asset.kind || "score", url: slide.url, name: slide.name || asset.name || "" },
      ...presenterScoreFormMetadata(sequenced.scoreForms, slideIndex, formWarnings),
      scoreBackground: true,
      sourceType: "score",
      componentType: "score",
      sort: index + slideIndex / 100,
    };
  });
}

function presenterImportedDeckSlidesFromAsset(asset, item, section, index, title, label) {
  if (asset?.kind !== "imported_deck") return [];
  const sources = normalizeServiceAssetSlides(asset.slides || asset.images || asset.pages || asset.files || asset.items);
  return sources
    .map((slide, slideIndex) => {
      const source = normalizePresenterMediaSource(slide.url);
      if (!source || !presenterMediaSourceIsImage(source)) return null;
      return {
        id: `${item.id || index}:imported-deck:${slideIndex}`,
        ...section,
        sectionLabel: section.sectionLabel || label || "자료",
        sectionTitle: section.sectionTitle || section.sectionLabel || label || "자료",
        sectionName: presenterNameParts(section.sectionLabel || label, title).join(" / ") || title,
        elementTitle: title,
        elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
        layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
        type: "image",
        label,
        title,
        marker: slide.name || `Stage ${slideIndex + 1}`,
        text: slide.name || title,
        imageSrc: source,
        asset: { ...asset, url: source, name: slide.name || asset.name || "" },
        importedDeck: {
          manifestUrl: asset.manifestUrl || "",
          fingerprint: asset.fingerprint || "",
          stage: Number(slide.order) || slideIndex + 1,
        },
        sourceType: "imported_deck",
        componentType: "imported_deck",
        sort: index + slideIndex / 100,
      };
    })
    .filter(Boolean);
}

function presenterSyncedLyricsConfigFromAsset(asset = {}) {
  if (asset?.kind !== "synced_lyrics") return null;
  const audioSource = normalizePresenterMediaSource(asset.audio?.url || asset.url || "");
  const pages = Array.isArray(asset.timing?.pages)
    ? asset.timing.pages
      .map((page, index) => ({
        page: Number(page.page || index + 1) || index + 1,
        start: Number(page.start),
      }))
      .filter((page) => Number.isFinite(page.start) && page.start >= 0)
      .sort((a, b) => (a.page || 0) - (b.page || 0))
    : [];
  if (!audioSource || !pages.length) return null;
  return {
    audioSrc: audioSource,
    audioTitle: asset.audio?.name || asset.name || "",
    pages,
    cross: Number.isFinite(Number(asset.timing?.cross)) ? Number(asset.timing.cross) : null,
    duration: Number.isFinite(Number(asset.timing?.duration)) ? Number(asset.timing.duration) : null,
  };
}

function presenterApplySyncedLyricsConfig(slides = [], syncConfig = null, item = {}, index = 0) {
  if (!syncConfig) return slides;
  let lyricIndex = 0;
  const groupId = `${item.id || index}:synced-lyrics`;
  return slides.map((slide) => {
    const isLyricSlide = slide?.type === "lyrics";
    const isIntroTitle = slide?.type === "song-title" && lyricIndex === 0;
    if (!isLyricSlide && !isIntroTitle) return slide;
    if (isLyricSlide) lyricIndex += 1;
    const page = syncConfig.pages[lyricIndex - 1] || null;
    return {
      ...slide,
      syncTimeline: {
        groupId,
        audioSrc: syncConfig.audioSrc,
        audioTitle: syncConfig.audioTitle,
        page: isLyricSlide ? lyricIndex : 0,
        start: isLyricSlide && page ? page.start : null,
        cross: syncConfig.cross,
        duration: syncConfig.duration,
        intro: isIntroTitle,
      },
      sourceType: slide.sourceType || "synced_lyrics",
      componentType: slide.componentType || "synced_lyrics",
    };
  });
}

function presenterScoreImageSourcesForFormSequence(imageSources = [], scoreForms = [], forms = [], item = {}, song = null, version = null) {
  const presetLabels = presenterScoreFormPresetLabels(item, song, version);
  const planTargets = presetLabels
    .map((label) => normalizePresenterFormPresetLabel(label))
    .filter((target) => target.key && target.type !== "lyrics");
  const scoreTargets = (scoreForms || []).map((form) =>
    form ? normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)) : null,
  );
  if (!planTargets.length || !scoreTargets.some((target) => target?.key)) {
    return { imageSources, scoreForms };
  }

  const groups = [];
  imageSources.forEach((source, index) => {
    const target = scoreTargets[index];
    const startsGroup = Boolean(target?.key);
    if (startsGroup || !groups.length) {
      groups.push({ target: target || null, sources: [], forms: [] });
    }
    const group = groups[groups.length - 1];
    group.sources.push(source);
    group.forms.push(scoreForms[index] || null);
  });

  const selected = [];
  const lastMatchedByKey = new Map();
  let cursor = 0;
  planTargets.forEach((target) => {
    const matchIndex = groups.findIndex((group, index) =>
      index >= cursor && group.target && presenterFormTargetsMatch(target, group.target),
    );
    const group = matchIndex >= 0
      ? groups[matchIndex]
      : lastMatchedByKey.get(target.key)
        || (!target.number && target.type ? lastMatchedByKey.get(target.type) : null);
    if (!group) return;
    selected.push(group);
    lastMatchedByKey.set(target.key, group);
    if (target.type) lastMatchedByKey.set(target.type, group);
    if (matchIndex >= 0) cursor = matchIndex + 1;
  });
  if (!selected.length) return { imageSources, scoreForms };
  return {
    imageSources: selected.flatMap((group) => group.sources),
    scoreForms: selected.flatMap((group) => group.forms),
  };
}

function presenterScoreFormPresetLabels(item = {}, song = null, version = null) {
  if (typeof serviceItemFormPresetDisabled === "function" && serviceItemFormPresetDisabled(item)) return [];
  const itemPreset = typeof serviceItemFormPreset === "function" ? serviceItemFormPreset(item) : null;
  const matchedRule = typeof matchedServiceItemFormPresetRule === "function"
    ? matchedServiceItemFormPresetRule(item, song, version)
    : null;
  const songDefaultPreset = presenterSongDefaultFormPreset(song, version);
  return cleanList(
    itemPreset?.forms
    || matchedRule?.formPreset?.forms
    || songDefaultPreset?.forms
    || [],
  );
}

function presenterScoreFormMetadata(forms = [], slideIndex = 0, formWarnings = []) {
  const form = Array.isArray(forms) ? forms[slideIndex] : null;
  if (!form) return formWarnings?.length ? { warnings: formWarnings } : {};
  const formId = form._localId || form.id || slideIndex;
  return {
    formKey: form._presenterScoreFormKey || `${formId}:${slideIndex}`,
    formLabel: presenterResolvedFormMarker(form),
    warnings: formWarnings,
  };
}

function presenterScoreFormsFromImageSources(imageSources = []) {
  return imageSources.map((source, index) => {
    const label = presenterScoreFormLabelFromAssetSlide(source);
    if (!label) return null;
    const target = normalizePresenterFormPresetLabel(label);
    if (!target.key || target.type === "lyrics") return null;
    const partType = presenterFormPartTypeForPresetTarget(target);
    const formKey = String(source.formKey || source.form_key || source.scoreFormKey || source.score_form_key || "").trim()
      || `score:${target.key}:${index}`;
    return {
      _presenterVirtual: true,
      _presenterScoreFormKey: formKey,
      id: formKey,
      part_type: partType,
      part_number: target.number || null,
      label,
      lyrics: label,
    };
  });
}

function presenterScoreFormLabelFromAssetSlide(slide = {}) {
  return normalizePresenterScoreFormLabel(
    slide.formLabel
    || slide.form_label
    || slide.scoreFormLabel
    || slide.score_form_label
    || slide.form
    || "",
  );
}

function normalizePresenterScoreFormLabel(value = "") {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return presenterFormPresetDisplayLabel(raw);
}

function presenterHymnScoreAssetSlides(song = null, version = null, displayText = "") {
  const hymnNo = normalizedHymnScoreNumber(song?.hymn_no || version?.hymn_no || displayText);
  if (!hymnNo) return [];
  const entry = state.hymnScoreManifest?.[hymnNo];
  const slides = Array.isArray(entry?.slides) ? entry.slides : [];
  return slides
    .map((slide, index) => ({
      url: slide.src || slide.url,
      name: slide.name || `${hymnNo} ${entry.title || stripHymnNumber(song?.title || "")} ${index + 1}`,
      formLabel: slide.scoreFormLabel || slide.score_form_label || slide.formLabel || slide.form_label || "",
      formKey: slide.scoreFormKey || slide.score_form_key || slide.formKey || slide.form_key || "",
      order: index + 1,
    }))
    .filter((slide) => slide.url);
}

function normalizedHymnScoreNumber(value = "") {
  const match = String(value || "").match(/\d{1,3}/);
  return match ? String(Number(match[0])) : "";
}

function presenterImageSourcesFromAssetUrl(value) {
  const text = String(value || "").trim();
  if (!text) return [];
  return text
    .split(/[\s,|]+/g)
    .map((part) => normalizePresenterMediaSource(part))
    .filter((source) => source && presenterMediaSourceIsImage(source))
    .map((url, index) => ({ url, name: index === 0 ? "" : "", order: index + 1 }));
}

function presenterFormPlanForServiceItem(version = {}, item, song = null) {
  version = version || {};
  const forms = normalizeForms(version.forms || []).filter((form) => normalizeLyricsForCopy(form.lyrics));
  if (typeof serviceItemFormPresetDisabled === "function" && serviceItemFormPresetDisabled(item)) return { forms, warnings: [] };
  const isHymn = versionEffectivePraiseTypes(song, version).includes("hymn");
  const itemPreset = serviceItemFormPreset(item);
  const matchedRule = matchedServiceItemFormPresetRule(item, song, version);
  const songDefaultPreset = presenterSongDefaultFormPreset(song, version);
  const specialHymnRulePreset = presenterSpecialSongHymnFormPreset(item, song, version, matchedRule);
  const preset = isHymn
    ? specialHymnRulePreset
      || itemPreset
      || matchedRule?.formPreset
      || songDefaultPreset
      || presenterDefaultVerseChorusFormPreset(forms, song, version)
      || null
    : presenterExplicitNonHymnFormPreset(itemPreset)
      || matchedRule?.formPreset
      || presenterExplicitNonHymnFormPreset(songDefaultPreset)
      || presenterDefaultVerseChorusFormPreset(forms, song, version)
      || null;
  const effectivePreset = presenterFormPresetWithAvailableForms(preset, forms);
  if (!effectivePreset?.forms?.length) return { forms, warnings: [] };
  const resolved = resolvePresenterFormPresetSequence(forms, effectivePreset);
  const warnings = presenterMissingFormWarnings(resolved.missing, forms, effectivePreset);
  const omitUnlisted = presenterFormPresetShouldOmitUnlisted(effectivePreset);
  return {
    forms: resolved.items.length
      ? omitUnlisted
        ? resolved.items
        : presenterFormsWithNoSourceOmissions(resolved.items, forms)
      : forms,
    warnings,
  };
}

function presenterMissingFormWarnings(missing = [], forms = [], preset = null) {
  if (preset?.omitMissingForms) return [];
  const strength = String(preset?.strength || "").trim().toLowerCase();
  const automaticPreset = ["auto", "default", "suggested"].includes(strength);
  const sourceHasChorus = normalizeForms(forms || [])
    .filter((form) => normalizeLyricsForCopy(form.lyrics))
    .some((form) => normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)).type === "chorus");
  return cleanList(missing)
    .filter((label) => {
      const target = normalizePresenterFormPresetLabel(label);
      return !(automaticPreset && target.type === "chorus" && !sourceHasChorus);
    })
    .map((label) => `${label} 없음`);
}

function presenterSpecialSongHymnFormPreset(item = {}, song = null, version = null, matchedRule = null) {
  if (!isPresenterSpecialSongItem(item)) return null;
  const isHymn = versionEffectivePraiseTypes(song, version).includes("hymn")
    || Boolean(song?.hymn_no || version?.hymn_no);
  if (!isHymn) return null;
  return presenterSpecialSongHymnDisplayPreset(matchedRule?.formPreset || normalizeServiceFormPreset(
    PUBLIC_SPECIAL_HYMN_FORM_PRESET_FORMS,
    PUBLIC_SPECIAL_HYMN_FORM_PRESET_HINT,
    "default",
  ));
}

function presenterSpecialSongHymnDisplayPreset(preset = null) {
  if (!preset?.forms?.length) return preset;
  const forms = cleanList(preset.forms).map((label) => {
    const target = normalizePresenterFormPresetLabel(label);
    if (target.lastVerse) return "VL";
    if (target.type === "verse" && target.number && !target.group) return `V${target.number}`;
    if (target.type === "chorus" && !target.group) return target.number ? `C${target.number}` : "C";
    if (target.type === "instrumental") return "Int";
    return String(label || "").trim();
  });
  return {
    ...preset,
    forms,
    hint: forms.join("-"),
    omitUnlisted: true,
    omitMissingForms: String(preset.strength || "").toLowerCase() === "default",
  };
}

function presenterFormPresetShouldOmitUnlisted(preset = null) {
  if (preset?.omitUnlisted) return true;
  const strength = String(preset?.strength || "").trim().toLowerCase();
  return ["default", "forced", "manual", "song-default"].includes(strength);
}

function presenterFormsWithNoSourceOmissions(plannedForms = [], sourceForms = []) {
  const source = normalizeForms(sourceForms || []).filter((form) => normalizeLyricsForCopy(form.lyrics));
  const identity = (form) => String(form?._localId || form?.id || "").trim();
  const sourceIndexes = new Map(source.map((form, index) => [identity(form), index]).filter(([id]) => id));
  if (!sourceIndexes.size) return plannedForms;

  const merged = [...plannedForms];
  const present = new Set(merged.map(identity).filter(Boolean));
  source.forEach((form) => {
    const id = identity(form);
    if (!id || present.has(id)) return;
    const sourceIndex = sourceIndexes.get(id);
    const insertAt = merged.findIndex((candidate) => {
      const candidateIndex = sourceIndexes.get(identity(candidate));
      return Number.isFinite(candidateIndex) && candidateIndex > sourceIndex;
    });
    merged.splice(insertAt < 0 ? merged.length : insertAt, 0, form);
    present.add(id);
  });
  return merged;
}

function presenterExplicitNonHymnFormPreset(preset = null) {
  if (!preset?.forms?.length) return null;
  return String(preset.strength || "").trim().toLowerCase() === "suggested" ? null : preset;
}

function presenterFormPresetWithAvailableForms(preset = null, forms = []) {
  if (!preset?.forms?.length) return preset;
  const source = normalizeForms(forms || [])
    .filter((form) => normalizeLyricsForCopy(form.lyrics))
    .map((form) => ({ form, target: normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)) }))
    .filter(({ target }) => target.key && target.type !== "lyrics");
  if (!source.length) return preset;

  const originalTargets = cleanList(preset.forms).map((label) => normalizePresenterFormPresetLabel(label));
  const genericVerseChorusPreset = originalTargets.length
    && originalTargets.every((target) => target.type === "verse" || target.type === "chorus");
  const presetStrength = String(preset?.strength || "").trim().toLowerCase();
  const exactFormPreset = ["manual", "forced", "default"].includes(presetStrength);
  const canPreserveSupplementalForms = genericVerseChorusPreset && !exactFormPreset;
  const base = presenterRepeatableVerseChorusPresetForms(preset, source) || cleanList(preset.forms);
  const merged = [];
  let sourceIndex = 0;
  base.forEach((label) => {
    const target = normalizePresenterFormPresetLabel(label);
    if (target.groupIndex) {
      merged.push(label);
      return;
    }
    if (target.lastVerse) {
      const lastVerse = source
        .map((candidate, index) => ({ ...candidate, index }))
        .filter(({ target: candidate }) => candidate.type === "verse")
        .reduce((best, candidate) => {
          if (!best) return candidate;
          const bestNumber = Number(best.target.number) || 0;
          const candidateNumber = Number(candidate.target.number) || 0;
          if (candidateNumber > bestNumber) return candidate;
          if (candidateNumber === bestNumber && candidate.index > best.index) return candidate;
          return best;
        }, null);
      if (lastVerse) {
        sourceIndex = Math.max(sourceIndex, lastVerse.index + 1);
        merged.push(presenterFormDisplayLabel(lastVerse.form));
        return;
      }
    }
    const matchIndex = source.findIndex(({ target: candidate }, index) => index >= sourceIndex && presenterFormTargetsMatch(target, candidate));
    if (matchIndex >= sourceIndex) {
      if (canPreserveSupplementalForms) {
        source.slice(sourceIndex, matchIndex).forEach(({ form, target: candidate }) => {
          if (presenterSupplementalFormType(candidate)) merged.push(presenterFormDisplayLabel(form));
        });
      }
      sourceIndex = matchIndex + 1;
      merged.push(presenterFormDisplayLabel(source[matchIndex].form));
      return;
    }
    merged.push(label);
  });

  if (preset.omitUnlisted) {
    const original = cleanList(preset.forms);
    if (merged.length === original.length && merged.every((label, index) => label === original[index])) return preset;
    return {
      ...preset,
      forms: original,
      sourceForms: merged,
      hint: original.join("-"),
    };
  }

  // Preserve endings and bridges only for inferred generic sequences such as VCVC.
  // User/default/forced presets must render exactly as written.
  if (canPreserveSupplementalForms) {
    let includeFollowingChorus = false;
    source.slice(sourceIndex).forEach(({ form, target }) => {
      if (presenterSupplementalFormType(target)) {
        merged.push(presenterFormDisplayLabel(form));
        includeFollowingChorus = target.type === "bridge" || target.type === "pre-chorus";
        return;
      }
      if (includeFollowingChorus && target.type === "chorus") {
        merged.push(presenterFormDisplayLabel(form));
        includeFollowingChorus = false;
      }
    });
  }

  const hasPreChorus = source.some(({ target }) => target.type === "pre-chorus");
  const formsWithPreChorus = canPreserveSupplementalForms && hasPreChorus
    ? presenterInsertPreChorusBeforeChoruses(merged)
    : merged;
  const original = cleanList(preset.forms);
  if (formsWithPreChorus.length === original.length && formsWithPreChorus.every((label, index) => label === original[index])) return preset;
  return {
    ...preset,
    forms: formsWithPreChorus,
    hint: formsWithPreChorus.join("-"),
  };
}

function presenterRepeatableVerseChorusPresetForms(preset = null, source = []) {
  const strength = String(preset?.strength || "").trim().toLowerCase();
  if (["default", "forced", "manual"].includes(strength)) return null;
  const presetForms = cleanList(preset?.forms);
  const targets = presetForms.map((label) => normalizePresenterFormPresetLabel(label));
  const core = targets.filter((target) => target.type !== "pre-chorus");
  const alternating = core.length >= 2
    && core.every((target, index) => target.type === (index % 2 === 0 ? "verse" : "chorus"));
  if (!alternating) return null;

  const verses = source.filter(({ target }) => target.type === "verse");
  const choruses = source.filter(({ target }) => target.type === "chorus");
  if (!verses.length || !choruses.length) return null;

  const preChoruses = source.filter(({ target }) => target.type === "pre-chorus");
  const presetChorusCount = targets.filter((target) => target.type === "chorus").length;
  const cycles = Math.max(verses.length, choruses.length, presetChorusCount);
  const expanded = [];
  for (let index = 0; index < cycles; index += 1) {
    expanded.push(presenterFormDisplayLabel(verses[index % verses.length].form));
    if (preChoruses.length) expanded.push(presenterFormDisplayLabel(preChoruses[index % preChoruses.length].form));
    expanded.push(presenterFormDisplayLabel(choruses[index % choruses.length].form));
  }
  return expanded;
}

function presenterFormTargetsMatch(target = {}, candidate = {}) {
  if (target.key === candidate.key) return true;
  return Boolean(target.type && target.type === candidate.type && (!target.number || target.number === candidate.number));
}

function presenterSupplementalFormType(target = {}) {
  return !["", "verse", "chorus", "lyrics"].includes(String(target.type || ""));
}

function presenterInsertPreChorusBeforeChoruses(forms = []) {
  return cleanList(forms).flatMap((label, index, list) => {
    const target = normalizePresenterFormPresetLabel(label);
    const previous = normalizePresenterFormPresetLabel(list[index - 1] || "");
    if (target.type === "chorus" && previous.type !== "pre-chorus") return ["PC", label];
    return [label];
  });
}

function presenterSongDefaultFormPreset(song = null, version = null) {
  const versionMeta = normalizeSongMetadata(version?.metadata);
  const songMeta = normalizeSongMetadata(song?.metadata);
  return versionMeta.presenter_form || songMeta.presenter_form || null;
}

function presenterDefaultVerseChorusFormPreset(forms = [], song = null, version = null) {
  const praiseTypes = versionEffectivePraiseTypes(song, version);
  if (!praiseTypes.includes("hymn") && !praiseTypes.includes("ccm")) return null;
  const normalizedForms = normalizeForms(forms || []);
  const verses = normalizedForms.filter((form) => normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)).type === "verse");
  const chorus = normalizedForms.find((form) => normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)).type === "chorus");
  if (!verses.length || !chorus) return null;
  const presetForms = [];
  verses.forEach((verse, index) => {
    const target = normalizePresenterFormPresetLabel(presenterFormDisplayLabel(verse));
    presetForms.push(target.number ? `V${target.number}` : index === 0 ? "V" : `V${index + 1}`);
    presetForms.push("C");
  });
  const hymnCoda = normalizedForms.find((form) => {
    const target = normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form));
    return target.type === "coda";
  });
  if (hymnCoda) presetForms.push("Coda");
  return normalizeServiceFormPreset(presetForms, presetForms.join("-"), "auto");
}

function matchedServiceItemFormPresetRule(item, song, version) {
  return serviceItemFormPresetRules(item).find((rule) => serviceItemFormPresetRuleMatches(rule, item, song, version)) || null;
}

function serviceItemFormPresetRuleMatches(rule = {}, item = {}, song = null, version = null) {
  const when = rule.when && typeof rule.when === "object" ? rule.when : {};
  const songType = String(when.songType || when.song_type || when.praiseType || when.praise_type || "").trim();
  if (songType) {
    const requiredTypes = normalizePraiseTypes(songType);
    const versionTypes = versionEffectivePraiseTypes(song, version);
    if (requiredTypes.length && !requiredTypes.some((type) => versionTypes.includes(type))) return false;
  }
  const sectionKey = String(when.sectionKey || when.section_key || "").trim();
  if (sectionKey && sectionKey !== String(item?._worshipSectionKey || "").trim()) return false;
  const label = String(when.label || "").trim();
  if (label && compactSearchValue(label) !== compactSearchValue(item?.label || "")) return false;
  return true;
}

function resolvePresenterFormPresetSequence(forms = [], preset = []) {
  const presetForms = Array.isArray(preset) ? preset : cleanList(preset?.forms);
  const sourceForms = Array.isArray(preset) ? [] : cleanList(preset?.sourceForms);
  if (presenterFormsAreUnsplitLyrics(forms)) {
    const lyricsResolved = resolvePresenterLyricsFormPresetSequence(forms, presetForms, sourceForms);
    if (lyricsResolved.items.length) return lyricsResolved;
  }
  const items = [];
  const missing = [];
  cleanList(presetForms).forEach((label, index) => {
    const resolved = findPresenterFormForPresetLabel(forms, sourceForms[index] || label);
    if (resolved) items.push({ ...resolved, _presenterPresetLabel: presenterResolvedPresetLabel(label) });
    else missing.push(normalizePresenterMissingFormLabel(label));
  });
  return { items, missing };
}

function presenterResolvedPresetLabel(label = "") {
  const raw = String(label || "").trim();
  if (isPresenterKoreanHymnPresetLabel(raw)) return raw;
  return normalizePresenterMissingFormLabel(raw);
}

function presenterFormsAreUnsplitLyrics(forms = []) {
  const normalizedForms = normalizeForms(forms || []).filter((form) => normalizeLyricsForCopy(form.lyrics));
  return Boolean(normalizedForms.length) && normalizedForms.every((form) => normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)).type === "lyrics");
}

function resolvePresenterLyricsFormPresetSequence(forms = [], presetForms = [], sourceForms = []) {
  const blocks = presenterLyricsBlocksFromForms(forms);
  const blockBySourceKey = new Map();
  const sourceBlockIndexes = new Set();
  cleanList(sourceForms).forEach((label, index) => {
    const target = normalizePresenterFormPresetLabel(label);
    if (!target.key || target.blank || blockBySourceKey.has(target.key)) return;
    const block = blocks[index];
    if (block) {
      blockBySourceKey.set(target.key, block);
      sourceBlockIndexes.add(index);
    }
  });
  const items = [];
  const missing = [];
  const assigned = new Map();
  let blockIndex = 0;
  cleanList(presetForms).forEach((label, index) => {
    const target = normalizePresenterFormPresetLabel(label);
    if (!target.key) return;
    if (target.blank) {
      items.push(presenterBlankFormPresetItem(label, target));
      return;
    }
    const assignedForm = assigned.get(target.key);
    if (assignedForm) {
      items.push({ ...assignedForm, id: `${assignedForm.id}:repeat:${index}` });
      return;
    }
    const sourceBlock = blockBySourceKey.get(target.key);
    while (!sourceBlock && sourceBlockIndexes.has(blockIndex)) blockIndex += 1;
    const block = sourceBlock || blocks[blockIndex];
    if (!block) {
      missing.push(normalizePresenterMissingFormLabel(label));
      return;
    }
    if (!sourceBlock) {
      blockIndex += 1;
    }
    const form = presenterVirtualFormPresetItem(label, target, block, index);
    assigned.set(target.key, form);
    items.push(form);
  });
  return { items, missing };
}

function presenterLyricsBlocksFromForms(forms = []) {
  return normalizeForms(forms || [])
    .flatMap((form) => String(form.lyrics || "").split(/\n\s*\n/g))
    .map((block) => normalizeLyricsForCopy(block))
    .filter(Boolean);
}

function presenterVirtualFormPresetItem(label = "", target = {}, lyrics = "", index = 0) {
  const partType = presenterFormPartTypeForPresetTarget(target);
  const partNumber = target.number || null;
  const cleanLabel = String(label || "").trim();
  const repeatedLyrics = presenterRepeatLyricsForPresetTarget(lyrics, target);
  return {
    _presenterVirtual: true,
    id: `preset-form:${target.key || compactSearchValue(cleanLabel) || index}`,
    part_type: partType,
    part_number: partNumber,
    lyrics: repeatedLyrics,
    label: cleanLabel || (partNumber ? `${partType} ${partNumber}` : partType),
  };
}

function presenterFormPartTypeForPresetTarget(target = {}) {
  const type = String(target.type || "").trim();
  if (type === "verse") return "Verse";
  if (type === "chorus") return "Chorus";
  if (type === "tag") return "Chorus";
  if (type === "bridge") return "Bridge";
  if (type === "pre-chorus") return "Pre-Chorus";
  if (type === "coda") return "Coda";
  if (type === "lyrics") return "Lyrics";
  return PART_TYPES.includes(target.rawType) ? target.rawType : "Lyrics";
}

function findPresenterFormForPresetLabel(forms = [], label = "") {
  const target = normalizePresenterFormPresetLabel(label);
  if (!target.key) return null;
  if (target.blank) return presenterBlankFormPresetItem(label, target);
  if (target.type === "tag") {
    const chorus = findPresenterFormForPresetTarget(forms, { key: "chorus", type: "chorus" });
    return chorus ? presenterTagFormPresetItem(label, target, chorus) : null;
  }
  if (target.lastVerse) {
    const verses = forms
      .map((form, index) => ({ form, index, target: normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)) }))
      .filter(({ target }) => target.type === "verse");
    if (!verses.length) return null;
    return verses.reduce((best, candidate) => {
      const bestNumber = Number(best.target.number) || 0;
      const candidateNumber = Number(candidate.target.number) || 0;
      if (candidateNumber > bestNumber) return candidate;
      if (candidateNumber === bestNumber && candidate.index > best.index) return candidate;
      return best;
    }).form;
  }
  if (target.groupIndex) {
    const form = findPresenterFormForPresetTarget(forms, target);
    return form ? presenterFormPresetGroupItem(label, target, form) : null;
  }
  return findPresenterFormForPresetTarget(forms, target);
}

function presenterTagFormPresetItem(label = "", target = {}, form = {}) {
  const lines = String(form.lyrics || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const lyrics = presenterRepeatLyricsForPresetTarget(lines[lines.length - 1] || "", target);
  if (!lyrics) return null;
  const cleanLabel = String(label || "").trim() || "Tag";
  const baseId = String(form._localId || form.id || target.key || "tag");
  return {
    ...form,
    _presenterVirtual: true,
    _presenterSourceFormId: form._localId || form.id || "",
    id: `${baseId}:tag`,
    part_type: "Chorus",
    part_number: null,
    lyrics,
    label: cleanLabel,
  };
}

function presenterRepeatLyricsForPresetTarget(lyrics = "", target = {}) {
  const text = normalizeLyricsForCopy(lyrics);
  const repeat = Number(target?.repeat) || 1;
  if (!text || repeat <= 1) return text;
  return Array.from({ length: Math.min(repeat, 12) }, () => text).join("\n");
}

function findPresenterFormForPresetTarget(forms = [], target = {}) {
  const sameType = [];
  for (const form of forms) {
    const candidate = normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form));
    if (target.type && target.type === candidate.type) sameType.push({ form, target: candidate });
    if (target.key === candidate.key) return form;
    if (target.type && target.type === candidate.type && (!target.number || target.number === candidate.number)) return form;
  }
  // A single verse is stored without a number; V1 still denotes that first verse.
  if (target.type === "verse" && target.number === 1 && sameType.length === 1 && !sameType[0].target.number) {
    return sameType[0].form;
  }
  if (target.groupIndex && target.type) {
    const unnumbered = sameType.filter(({ target: candidate }) => !candidate.number);
    if (unnumbered.length === 1) return unnumbered[0].form;
  }
  return null;
}

function presenterFormPresetGroupItem(label = "", target = {}, form = {}) {
  const chunks = presenterGroupedLyricChunks(form.lyrics, target);
  const lyrics = chunks[(Number(target.groupIndex) || 1) - 1] || "";
  if (!lyrics) return null;
  const cleanLabel = String(label || "").trim();
  const baseId = String(form._localId || form.id || target.key || compactSearchValue(cleanLabel) || "form");
  return {
    ...form,
    _presenterVirtual: true,
    _presenterSourceFormId: form._localId || form.id || "",
    id: `${baseId}:group:${target.group || target.groupIndex}`,
    lyrics,
    label: cleanLabel || presenterFormDisplayLabel(form),
  };
}

function presenterGroupedLyricChunks(lyrics = "", target = {}) {
  const groupIndex = Number(target?.groupIndex) || 0;
  if (!groupIndex) return splitPresenterLyricChunks(lyrics);
  const lines = String(lyrics || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) return lines;
  const chunkSize = Math.max(1, Math.ceil(lines.length / Math.max(groupIndex, 2)));
  const chunks = [];
  for (let index = 0; index < lines.length; index += chunkSize) {
    chunks.push(lines.slice(index, index + chunkSize).join("\n"));
  }
  return chunks;
}

function presenterFormDisplayLabel(form = {}) {
  if (form._presenterVirtual && form._presenterSourceFormId) return String(form.label || "").trim() || displayLabel(form);
  if (form._presenterVirtual) return displayLabel(form);
  return String(form.label || "").trim() || displayLabel(form);
}

function normalizePresenterFormPresetLabel(value = "") {
  const raw = String(value || "").trim();
  const compact = compactSearchValue(raw);
  const lastVerse = /^(vl|마지막절|lastverse|last)$/i.test(compact);
  if (lastVerse) return { key: "last-verse", type: "verse", number: 0, lastVerse: true };
  const hymnVerse = raw.match(/^(\d+)\s*절$/u);
  if (hymnVerse) return { key: `verse:${hymnVerse[1]}`, type: "verse", number: Number(hymnVerse[1]) };
  const shorthand = raw.match(/^(v|verse)\s*(\d*)([a-z])?$/i);
  if (shorthand) {
    const number = shorthand[2] ? Number(shorthand[2]) : 0;
    const group = shorthand[3] ? shorthand[3].toUpperCase() : "";
    const baseKey = number ? `verse:${number}` : "verse";
    return {
      key: group ? `${baseKey}:${group.toLowerCase()}` : baseKey,
      type: "verse",
      number,
      ...(group ? { group, groupIndex: group.charCodeAt(0) - 64 } : {}),
    };
  }
  const chorus = raw.match(/^(c|chorus|후렴)\s*(\d*)([a-z])?$/i);
  if (chorus) {
    const number = chorus[2] ? Number(chorus[2]) : 0;
    const group = chorus[3] ? chorus[3].toUpperCase() : "";
    const baseKey = number ? `chorus:${number}` : "chorus";
    return {
      key: group ? `${baseKey}:${group.toLowerCase()}` : baseKey,
      type: "chorus",
      number,
      ...(group ? { group, groupIndex: group.charCodeAt(0) - 64 } : {}),
    };
  }
  const groupedType = raw.match(/^(pc|prechorus|pre-chorus|b|bridge|lyrics)\s*(\d*)([a-z])?$/i);
  if (groupedType) {
    const type = normalizePresenterFormType(groupedType[1]);
    const number = groupedType[2] ? Number(groupedType[2]) : 0;
    const group = groupedType[3] ? groupedType[3].toUpperCase() : "";
    const baseKey = number ? `${type}:${number}` : type;
    return {
      key: group ? `${baseKey}:${group.toLowerCase()}` : baseKey,
      type,
      number,
      ...(group ? { group, groupIndex: group.charCodeAt(0) - 64 } : {}),
    };
  }
  if (/^(coda|ending)\s*[a-z]?$/i.test(raw)) {
    return { key: "coda", type: "coda", number: 0 };
  }
  if (/^(int|간주|interlude|instrumental)\s*[a-z]?$/i.test(raw)) {
    return { key: "instrumental", type: "instrumental", number: 0, blank: true };
  }
  const tags = raw.match(/^(tags)$/i);
  if (tags) {
    return { key: "tag", type: "tag", number: 0, repeat: 2 };
  }
  const tag = raw.match(/^(tag)\s*[a-z]?$/i);
  if (tag) {
    return { key: "tag", type: "tag", number: 0 };
  }
  const display = raw.match(/^([A-Za-z][A-Za-z -]*?)(?:\s+(\d+))?(?:\s+([a-z]))?$/);
  if (display) {
    const type = normalizePresenterFormType(display[1]);
    const number = display[2] ? Number(display[2]) : 0;
    const group = display[3] ? display[3].toUpperCase() : "";
    const baseKey = number ? `${type}:${number}` : type;
    return {
      key: group ? `${baseKey}:${group.toLowerCase()}` : baseKey,
      type,
      number,
      ...(group ? { group, groupIndex: group.charCodeAt(0) - 64 } : {}),
    };
  }
  return { key: compact, type: compact, number: 0 };
}

function normalizePresenterFormType(value = "") {
  const compact = compactSearchValue(value);
  if (/^verse$/i.test(compact)) return "verse";
  if (/^(chorus|후렴)$/i.test(compact)) return "chorus";
  if (/^(b|bridge)$/i.test(compact)) return "bridge";
  if (/^pc$/i.test(compact)) return "pre-chorus";
  if (/^prechorus$/i.test(compact)) return "pre-chorus";
  if (/^(coda|ending)$/i.test(compact)) return "coda";
  if (/^tag$/i.test(compact)) return "tag";
  if (/^lyrics$/i.test(compact)) return "lyrics";
  if (/^(int|interlude|instrumental|간주)$/i.test(compact)) return "instrumental";
  return compact;
}

function presenterFormPresetDisplayLabel(value = "") {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const target = normalizePresenterFormPresetLabel(raw);
  const group = String(target.group || "").trim().toUpperCase();
  const suffix = target.number ? ` ${target.number}` : group ? ` ${group}` : "";
  if (target.lastVerse) return "Last Verse";
  if (target.type === "verse") return `Verse${suffix}`;
  if (target.type === "chorus") return `Chorus${suffix}`;
  if (target.type === "bridge") return `Bridge${suffix}`;
  if (target.type === "pre-chorus") return `Pre-Chorus${suffix}`;
  if (target.type === "coda") return "Coda";
  if (target.type === "tag") return target.repeat > 1 ? "Tags" : "Tag";
  if (target.type === "instrumental") return "Instrumental";
  if (target.type === "lyrics") return "";
  return raw;
}

function normalizePresenterMissingFormLabel(value = "") {
  const raw = String(value || "").trim();
  const target = normalizePresenterFormPresetLabel(raw);
  if (target.lastVerse) return "마지막 절";
  if (target.type === "verse" && target.number) return `${target.number}절`;
  if (target.key === "chorus") return "C";
  if (target.key === "bridge") return "Bridge";
  if (target.key === "pre-chorus") return "Pre-Chorus";
  if (target.key === "coda") return "Coda";
  if (target.key === "tag") return "Tag";
  return raw || "송폼";
}

function presenterBlankFormPresetItem(label = "", target = {}) {
  const text = String(label || "").trim() || "빈 화면";
  return {
    _presenterBlank: true,
    _presenterToken: target.key || compactSearchValue(text) || "blank",
    id: `preset-blank:${target.key || compactSearchValue(text) || "blank"}`,
    part_type: text,
    part_number: null,
    lyrics: "",
    label: text,
  };
}

function isServicePreparationItem(item, memo = parseServiceItemMemo(item?.memo)) {
  const label = String(item?.label || "").replace(/\s+/g, "");
  const title = String(item?.raw_title || "").replace(/\s+/g, "");
  const sectionKey = String(item?._worshipSectionKey || "").trim();
  const role = normalizeServicePresenterRole(memo?.presenterRole || memo?.templateKey || memo?.templateVariant);
  return sectionKey === "ready"
    || label === "준비"
    || label === "예배준비"
    || label === "대기"
    || label === "대기화면"
    || label === "대기영상"
    || label === "인트로"
    || label === "카운트다운"
    || title === "준비"
    || title === "예배준비"
    || title === "대기"
    || title === "대기화면"
    || title === "대기영상"
    || title === "인트로"
    || title === "카운트다운"
    || role === "ready"
    || role === "waiting_loop"
    || role === "intro"
    || role === "still";
}

function isConfessionPrayerLabel(...values) {
  return values.some((value) => {
    const compact = compactSearchValue(value);
    return compact === "참회기도" || compact === "참회의기도";
  });
}

function isAbsolutionDeclarationLabel(...values) {
  return values.some((value) => compactSearchValue(value) === "사죄의선언");
}

function isConfessionPrayerServiceItem(item = {}) {
  return (String(item?._worshipSectionKey || "").trim() === "confession"
      && !isAbsolutionDeclarationLabel(item?.label, item?.raw_title, item?._worshipSectionTitle))
    || isConfessionPrayerLabel(item?.label, item?.raw_title, item?._worshipSectionTitle);
}

function isConfessionPrayerElement(element = {}, section = {}, sourceRef = {}) {
  return (String(section?.section_key || "").trim() === "confession"
      && !isAbsolutionDeclarationLabel(sourceRef?.label, section?.title, element?.title))
    || isConfessionPrayerLabel(sourceRef?.label, section?.title, element?.title);
}

function presenterConfessionPrayerSlide(item, section, index) {
  return presenterTitleOnlySlide(item, section, index, "참회기도");
}

function presenterTitleOnlySlide(item, section, index, titleText = "") {
  const title = String(titleText || item?.raw_title || item?.label || "제목").trim();
  return {
    id: `${item?.id || index}:title`,
    ...section,
    sectionLabel: item?.label || section.sectionLabel || title,
    sectionTitle: title,
    sectionName: title,
    elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "title-assignee",
    label: item?.label || "",
    title,
    assignee: "",
    marker: "",
    text: title,
    sort: index,
  };
}

function isLiturgicalBodyServiceItem(item = {}) {
  const sectionKey = String(item?._worshipSectionKey || "").trim();
  if (sectionKey === "creed" || sectionKey === "lords_prayer" || sectionKey === "community_confession") return true;
  return isLiturgicalBodyLabel(item?.label, item?.raw_title, item?._worshipSectionTitle)
    || isAnnouncementTextInputItem(item);
}

function isLiturgicalBodyLabel(...values) {
  return values.some((value) => {
    const compact = compactSearchValue(value);
    return compact === "사도신경" || compact === "신앙고백" || compact === "주기도문" || compact === "공동체고백";
  });
}

function liturgicalBodyTitle(item = {}) {
  const label = compactSearchValue(item?.label || "");
  const title = compactSearchValue(item?.raw_title || "");
  if (isAnnouncementTextInputItem(item)) return "광고";
  if (label === "주기도문" || title === "주기도문" || String(item?._worshipSectionKey || "") === "lords_prayer") return "주기도문";
  if (label === "공동체고백" || title === "공동체고백" || String(item?._worshipSectionKey || "") === "community_confession") return "공동체고백";
  return "사도신경";
}

function presenterCircledNumber(index) {
  const circledNumbers = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"];
  return circledNumbers[index] || `${index + 1}.`;
}

function presenterAnnouncementItems(text = "") {
  const circledNumbers = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"];
  const circledIndex = new Map(circledNumbers.map((marker, index) => [marker, index]));
  const items = [];
  let current = null;

  String(text || "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .forEach((line) => {
      const match = line.match(/^\s*(?:(\d+)[.)]|([①-⑳]))[ \t]?(.*)$/u);
      if (match) {
        const numericIndex = match[1] ? Number(match[1]) - 1 : circledIndex.get(match[2]);
        current = {
          marker: Number.isInteger(numericIndex) && numericIndex >= 0 ? presenterCircledNumber(numericIndex) : match[2] || "",
          lines: [String(match[3] || "")],
        };
        items.push(current);
        return;
      }
      if (current) {
        current.lines.push(line);
        return;
      }
      current = { marker: "", lines: [line] };
      items.push(current);
    });

  return items.filter((item) => item.lines.some((line) => line.trim()));
}

function presenterAnnouncementBodyText(text = "") {
  return presenterAnnouncementItems(text)
    .flatMap((item) => item.lines.map((line, index) => (index === 0 && item.marker ? `${item.marker} ${line}` : line)))
    .join("\n");
}

function liturgicalBodyText(item = {}, memo = parseServiceItemMemo(item?.memo), displayText = "") {
  const title = liturgicalBodyTitle(item);
  const canonical = presenterCanonicalLiturgicalBodyText(title);
  if (canonical && !item?.template_modified && !item?.templateModified) return canonical;
  const announcement = isAnnouncementTextInputItem(item);
  if (memo.slides?.length) {
    const memoText = memo.slides.join("\n\n");
    return announcement ? presenterAnnouncementBodyText(memoText) : memoText.trim();
  }
  const text = String(item?.raw_title || displayText || "");
  if (!text.trim() || compactSearchValue(text) === compactSearchValue(title)) return "";
  return announcement ? presenterAnnouncementBodyText(text) : canonical || text.trim();
}

function presenterCanonicalLiturgicalBodyText(title = "") {
  const key = compactSearchValue(title);
  if (key === "주기도문") return PRESENTER_PUBLIC_LORDS_PRAYER_TEXT;
  if (key === "공동체고백") return PRESENTER_PUBLIC_COMMUNITY_CONFESSION_TEXT;
  if (key === "사도신경" || key === "신앙고백") return PRESENTER_PUBLIC_APOSTLES_CREED_TEXT;
  return "";
}

function liturgicalBodyTextHighlights(item = {}, memo = parseServiceItemMemo(item?.memo)) {
  const explicit = normalizeServiceTextHighlights(memo?.textHighlights || memo?.text_highlights || memo?.highlights);
  if (explicit.length) return explicit;
  if (liturgicalBodyTitle(item) !== "공동체고백") return [];
  return [
    { text: "하나님의 거룩한 백성", bold: true },
    { text: "그리스도의 제자", bold: true },
    { text: "성령 충만한", bold: true },
    { text: "은혜에 빚진", bold: true },
    { text: "예배자", color: "#FFC832", bold: true },
    { text: "훈련자", color: "#C8FF32", bold: true },
    { text: "전도자", color: "#FF96C8", bold: true },
    { text: "치유자", color: "#FF6432", bold: true },
    { text: "화해자", color: "#32C8FF", bold: true },
    { text: "소명자", color: "#9696FF", bold: true },
    { text: "검단우리교회 공동체", bold: true },
  ];
}

function buildPresenterLiturgicalBodySlides(item, section, index, service, memo, displayText) {
  if (!isLiturgicalBodyServiceItem(item)) return [];
  const text = liturgicalBodyText(item, memo, displayText);
  if (!text) return [];
  const title = liturgicalBodyTitle(item);
  const announcementItems = isAnnouncementTextInputItem(item)
    ? presenterAnnouncementItems(text)
    : [];
  const textHighlights = liturgicalBodyTextHighlights(item, memo);
  const base = {
    ...section,
    sectionLabel: item?.label || title,
    sectionTitle: title,
    sectionName: title,
    elementType: PRESENTER_ELEMENT_TYPES.BODY_TEXT,
    label: item?.label || title,
    title,
    marker: "",
    textHighlights,
    announcementItems,
  };
  if (!presenterServiceUsesChromakey(service)) {
    return [{
      id: `${item.id || index}:liturgical-body`,
      ...base,
      layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
      type: "liturgical-body",
      text,
      bodyText: text,
      sort: index,
    }];
  }
  const chromakeyText = title === "사도신경" && text === PRESENTER_PUBLIC_APOSTLES_CREED_TEXT
    ? PRESENTER_PUBLIC_APOSTLES_CREED_CHROMAKEY_TEXT
    : text;
  return presenterLiturgicalChromakeyChunks(title, chromakeyText).map((chunk, chunkIndex) => ({
    id: `${item.id || index}:liturgical:${chunkIndex}`,
    ...base,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "lyrics",
    formKey: `liturgical:${item.id || index}`,
    marker: chunkIndex === 0 ? title : "",
    text: chunk,
    bodyText: text,
    sort: index + chunkIndex / 100,
  }));
}

function presenterLiturgicalChromakeyChunks(title = "", text = "") {
  if (liturgicalBodyTitle({ label: title }) === "공동체고백"
    && text === PRESENTER_PUBLIC_COMMUNITY_CONFESSION_TEXT) {
    return PRESENTER_PUBLIC_COMMUNITY_CONFESSION_CHROMAKEY_SLIDES;
  }
  return splitPresenterLyricChunks(text);
}

function presenterPreparationSlide(service, item, index) {
  const memo = parseServiceItemMemo(item?.memo);
  const chromakey = presenterServiceUsesChromakey(service);
  const rawPresenterRole = presenterPreparationRole(item, memo);
  const presenterRole = rawPresenterRole === "waiting_loop" && !chromakey ? "ready" : rawPresenterRole;
  const elementLabel = presenterPreparationElementLabel(item, {}, presenterRole);
  if (!chromakey && presenterRole !== "intro") {
    return presenterFullscreenPreparationSlide(service, item, index, presenterRole, elementLabel);
  }
  const configuredAsset = normalizeServiceAsset(memo.asset);
  const asset = configuredAsset.url
    ? configuredAsset
    : presenterDefaultPreparationAsset(service, item, memo);
  const elementType = presenterRole === "intro" || (presenterRole === "waiting_loop" && chromakey)
    ? PRESENTER_ELEMENT_TYPES.VIDEO
    : PRESENTER_ELEMENT_TYPES.IMAGE;
  const source = normalizePresenterMediaSource(asset.url || "");
  const playbackType = presenterRole === "intro" ? "intro-video" : "ready-video";
  const assetElementLabel = presenterPreparationElementLabel(item, asset, presenterRole);
  if (source) {
    const title = asset.name || item?.raw_title || "";
    const base = {
      ...presenterReadySlide(service),
      id: `${item?.id || index}:ready-media`,
      sectionId: item?._worshipSectionId || item?.id || `${service?.id || "service"}:ready`,
      sectionKey: item?._worshipSectionKey || "ready",
      sectionLabel: item?._worshipSectionTitle || "준비",
      elementLabel: assetElementLabel,
      elementId: item?.id || `${service?.id || "service"}:ready`,
      sectionIndex: index + 1,
      sectionTitle: item?._worshipSectionTitle || "준비",
      elementTitle: title,
      sectionName: cleanList([item?._worshipSectionTitle || "준비", assetElementLabel]).join(" / "),
      title,
      text: "",
      asset: { ...asset, kind: asset.kind || elementType },
      presenterRole,
      sort: index,
    };
    if (elementType === "image") {
      return {
        ...base,
        elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
        layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
        type: "image",
        imageSrc: source,
      };
    }
    return {
      ...base,
      elementType: PRESENTER_ELEMENT_TYPES.VIDEO,
      layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
      type: presenterRole === "intro" ? "video" : "ready",
      videoSrc: source,
      playback: presenterPlaybackConfig(memo.playback, playbackType),
    };
  }
  return {
    ...presenterReadySlide(service),
    id: `${item?.id || index}:ready`,
    sectionId: item?._worshipSectionId || item?.id || `${service?.id || "service"}:ready`,
    sectionKey: item?._worshipSectionKey || "ready",
    sectionLabel: item?._worshipSectionTitle || item?.label || "준비",
    elementLabel: assetElementLabel,
    elementId: item?.id || `${service?.id || "service"}:ready`,
    sectionIndex: index + 1,
    elementType,
    layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
    type: "ready",
    imageSrc: "",
    videoSrc: "",
    presenterRole,
    sort: index,
  };
}

function presenterFullscreenPreparationSlide(service, item, index, presenterRole, elementLabel) {
  return {
    ...presenterReadySlide(service),
    id: `${item?.id || index}:ready`,
    sectionId: item?._worshipSectionId || item?.id || `${service?.id || "service"}:ready`,
    sectionKey: item?._worshipSectionKey || "ready",
    sectionLabel: item?._worshipSectionTitle || item?.label || "준비",
    elementLabel,
    elementId: item?.id || `${service?.id || "service"}:ready`,
    sectionIndex: index + 1,
    sectionTitle: item?._worshipSectionTitle || "준비",
    elementTitle: "준비",
    sectionName: cleanList([item?._worshipSectionTitle || "준비", elementLabel]).join(" / "),
    presenterRole,
    sort: index,
  };
}

function presenterDefaultPreparationAsset(service, item = {}, memo = {}) {
  const role = normalizeServicePresenterRole(memo?.presenterRole);
  if (presenterServiceUsesChromakey(service) && (!role || role === "waiting_loop")) {
    return {
      kind: PRESENTER_ELEMENT_TYPES.VIDEO,
      name: "예배 전 영상",
      url: PRESENTER_DEFAULT_CHROMAKEY_READY_LOOP_VIDEO,
    };
  }
  return { kind: "", name: "", url: "" };
}

function presenterPreparationElementLabel(item = {}, asset = {}, presenterRole = "") {
  const assetName = String(asset?.name || "").trim();
  const label = String(item?.label || "").trim();
  const compactLabel = compactSearchValue(label);
  if ((asset?.kind === "image" || presenterMediaSourceIsImage(asset?.url)) && compactLabel === "대기영상") {
    return assetName || "준비 이미지";
  }
  return label || (presenterRole === "intro" ? "인트로" : presenterRole === "still" ? "첫 화면" : "대기");
}

function presenterPreparationRole(item = {}, memo = parseServiceItemMemo(item?.memo)) {
  const explicit = normalizeServicePresenterRole(memo?.presenterRole);
  if (explicit) return explicit;
  const compact = compactSearchValue(`${item?.label || ""} ${item?.raw_title || ""}`);
  if (compact.includes("인트로") || compact.includes("카운트다운") || compact.includes("시작영상")) return "intro";
  if (compact.includes("대기영상") || compact.includes("대기비디오") || compact.includes("waitingloop")) return "waiting_loop";
  if (compact.includes("대기") || compact.includes("준비")) return "ready";
  if (compact.includes("첫화면") || compact.includes("정지화면")) return "still";
  return "ready";
}

function presenterElementSlideFromMemoCore(item, section, index, memo, displayText, service = null) {
  const elementType = serviceMemoElementType(memo);
  if (!elementType || elementType === "praise" || elementType === "scripture") return null;
  const label = item?.label || "";
  const asset = normalizeServiceAsset(memo?.asset);
  const safeLabel = isLegacyPresentationLabel(label) ? "" : label;
  const assetTitle = asset.name && !isLegacyImportArtifactName(asset.name) ? asset.name : "";
  const title = assetTitle || displayText || label || serviceElementTypeLabel(elementType);
  if (elementType === "title") return presenterTitleOnlySlide(item, section, index, title);
  if (elementType === "title_content") {
    const titleContentText = String(item?.raw_title || displayText || "");
    const lines = titleContentText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const titleText = lines[0] || item?.label || section.sectionTitle || "제목";
    const rawBodyText = lines.slice(1).join("\n") || memo.note || item?.assignee || "";
    const mainPraiseIntro = isMainPraiseTitleContentItem(item, section, titleText);
    const sermonTitle = section.sectionKey === "sermon"
      || ["설교", "설교제목"].includes(compactSearchValue(safeLabel));
    if (sermonTitle) {
      const contentTitle = presenterSermonContentTitle(titleText);
      const assignee = cleanPresenterAssignee(rawBodyText);
      return {
        id: `${item.id || index}:title-assignee`,
        ...section,
        elementLabel: safeLabel || "설교 제목",
        elementTitle: contentTitle,
        elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
        layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
        type: "title-assignee",
        label: safeLabel || "설교 제목",
        title: contentTitle,
        assignee,
        contentTitle,
        titlePresentation: "sermon",
        marker: "",
        text: cleanList([contentTitle, assignee]).join("\n"),
        sort: index,
      };
    }
    const displayTitle = mainPraiseIntro ? "찬양" : titleText;
    const bodyText = mainPraiseIntro
      ? resolveMainPraiseIntroBodyText(service, rawBodyText)
      : rawBodyText;
    return {
      id: `${item.id || index}:title-content`,
      ...section,
      elementLabel: mainPraiseIntro ? "환영" : safeLabel || section.elementLabel || "제목 / 내용",
      elementTitle: displayTitle,
      elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
      layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
      type: "title-content",
      label: mainPraiseIntro ? "환영" : safeLabel,
      title: displayTitle,
      bodyText,
      marker: "",
      text: [displayTitle, bodyText].filter(Boolean).join("\n"),
      sort: index,
      ...(mainPraiseIntro ? { _praiseIntroSlide: true } : {}),
    };
  }
  if (presenterMemoElementIsTitleSlide(elementType)) {
    const fallbackParts = typeof serviceTitlePersonEffectiveParts === "function"
      ? serviceTitlePersonEffectiveParts(item, memo, service)
      : null;
    const legacyTitlePersonFallback = fallbackParts?.rawTitleAssignee ? fallbackParts : null;
    const titleText = legacyTitlePersonFallback?.title || presenterTitleAssigneeTitle(item, safeLabel, displayText, elementType);
    const assigneeText = legacyTitlePersonFallback?.assignee || presenterTitleAssigneePerson(item, safeLabel, displayText, titleText, service);
    const compactLabel = compactSearchValue(safeLabel);
    const orderTitle = String(section.sectionHeading || section.sectionTitle || section.sectionLabel || "").trim();
    const sermonTitle = section.sectionKey === "sermon" || ["설교", "설교제목"].includes(compactLabel);
    const contentTitle = sermonTitle
      ? presenterSermonContentTitle(displayText)
      : compactLabel === "특송"
        ? String(displayText || "").trim()
      : "";
    const slideTitle = sermonTitle ? contentTitle : titleText;
    const threePartAssignee = sermonTitle || compactLabel === "특송"
      ? cleanPresenterAssignee(item.assignee) || legacyTitlePersonFallback?.assignee || ""
      : assigneeText;
    const hasThreeParts = Boolean(orderTitle && contentTitle && threePartAssignee);
    const scriptureReading = isPresenterScriptureReadingSource({ elementType, label: safeLabel, sectionKey: section.sectionKey });
    if (!titleText && !assigneeText) return null;
    return {
      id: `${item.id || index}:title-assignee`,
      ...section,
      sectionAssignee: scriptureReading ? "" : section.sectionAssignee,
      elementLabel: safeLabel || section.elementLabel || serviceElementTypeLabel(elementType),
      elementTitle: slideTitle,
      elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
      layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
      type: "title-assignee",
      label: safeLabel,
      title: slideTitle,
      assignee: hasThreeParts ? threePartAssignee : assigneeText,
      orderTitle: hasThreeParts ? orderTitle : "",
      contentTitle: hasThreeParts ? contentTitle : "",
      // Keep the presentation role on the slide. Re-inferring this from a
      // section label later can route a sermon title through a split layout.
      titlePresentation: sermonTitle ? "sermon" : "",
      marker: "",
      text: hasThreeParts
        ? cleanList([orderTitle, contentTitle, threePartAssignee]).join("\n")
        : cleanList([slideTitle, assigneeText]).join("\n"),
      sort: index,
    };
  }
  if (elementType === "blank") {
    return {
      id: `${item.id || index}:blank`,
      ...section,
      elementType: PRESENTER_ELEMENT_TYPES.BLANK,
      layout: PRESENTER_SLIDE_LAYOUTS.BLANK,
      type: "blank",
      label,
      title: title || "Blank",
      marker: "",
      text: "",
      sort: index,
    };
  }
  if (elementType === "video") {
    const source = normalizePresenterMediaSource(asset.url || displayText);
    if (!source) return null;
    return {
      id: `${item.id || index}:video`,
      ...section,
      sectionLabel: label || "Video",
      sectionTitle: title,
      sectionName: title,
      elementType: PRESENTER_ELEMENT_TYPES.VIDEO,
      layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
      type: "video",
      label,
      title,
      marker: label || "Video",
      text: title,
      videoSrc: source,
      asset,
      presenterRole: memo.presenterRole || "",
      playback: presenterPlaybackConfig(memo.playback, "video"),
      sourceType: "video",
      componentType: "video",
      sort: index,
    };
  }
  if (elementType === "audio") {
    const source = normalizePresenterMediaSource(asset.url || displayText);
    if (!source) return null;
    const audioAsset = { ...asset, kind: asset.kind || "audio", url: source };
    const audioTitle = presenterFileDisplayTitle({ title, asset: audioAsset }, "오디오");
    return {
      id: `${item.id || index}:audio`,
      ...section,
      sectionLabel: label || "Audio",
      sectionTitle: audioTitle,
      sectionName: audioTitle,
      elementType: PRESENTER_ELEMENT_TYPES.AUDIO,
      layout: PRESENTER_SLIDE_LAYOUTS.FILE,
      type: "audio",
      label,
      title: audioTitle,
      marker: label || "Audio",
      text: [audioTitle, source].filter(Boolean).join("\n"),
      audioSrc: source,
      asset: audioAsset,
      playback: presenterPlaybackConfig(memo.playback, "audio"),
      sourceType: audioAsset.kind || "audio",
      componentType: "audio",
      sort: index,
    };
  }
  if (elementType === "image") {
    const source = normalizePresenterMediaSource(asset.url || displayText);
    if (!source) return null;
    const referenceMedia = compactSearchValue(label) === "참고화면"
      && String(memo?.inputMode || "").trim() === "asset";
    return {
      id: `${item.id || index}:image`,
      ...section,
      sectionLabel: label || "Image",
      sectionTitle: title,
      sectionName: title,
      elementType: PRESENTER_ELEMENT_TYPES.IMAGE,
      layout: PRESENTER_SLIDE_LAYOUTS.MEDIA,
      type: "image",
      label,
      title,
      marker: label || "Image",
      text: title,
      imageSrc: source,
      asset,
      referenceMedia,
      sort: index,
    };
  }
  if (elementType === "score") {
    const source = normalizePresenterMediaSource(asset.url || displayText);
    const scoreAsset = source ? { ...asset, url: source } : asset;
    const imageSlides = presenterScoreImageSlidesFromAsset(scoreAsset, item, section, index, title, safeLabel || "악보", null, null, displayText);
    if (imageSlides.length) return imageSlides;
    const fileLabel = presenterFileTypeLabel("score");
    const fileTitle = presenterFileDisplayTitle({ title: assetTitle || displayText || safeLabel, asset }, fileLabel);
    return {
      id: `${item.id || index}:score`,
      ...section,
      sectionLabel: safeLabel || fileLabel,
      sectionTitle: fileTitle,
      sectionName: fileTitle,
      elementType: PRESENTER_ELEMENT_TYPES.FILE,
      layout: PRESENTER_SLIDE_LAYOUTS.FILE,
      type: "file",
      label: safeLabel,
      title: fileTitle,
      marker: fileLabel,
      text: [fileTitle, asset.url].filter(Boolean).join("\n"),
      asset,
      sourceType: "score",
      componentType: "score",
      sort: index,
    };
  }
  if (elementType === "activity") {
    const cleanTitle = title || "실시간 성구";
    return {
      id: `${item.id || index}:activity`,
      ...section,
      sectionLabel: label || cleanTitle,
      sectionTitle: cleanTitle,
      sectionName: cleanTitle,
      elementLabel: label || cleanTitle,
      elementTitle: cleanTitle,
      elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
      layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
      type: "title-content",
      label,
      title: cleanTitle,
      bodyText: String(memo.note || "").trim(),
      marker: "",
      text: [cleanTitle, memo.note].filter(Boolean).join("\n"),
      sort: index,
    };
  }
  if (elementType === "file" || elementType === "template") {
    const fileLabel = presenterFileTypeLabel(asset.kind || elementType);
    const fileTitle = presenterFileDisplayTitle({ title: assetTitle || displayText || safeLabel, asset }, fileLabel);
    return {
      id: `${item.id || index}:${elementType}`,
      ...section,
      sectionLabel: safeLabel || fileLabel,
      sectionTitle: fileTitle,
      sectionName: fileTitle,
      elementType: elementType === "file" ? PRESENTER_ELEMENT_TYPES.FILE : PRESENTER_ELEMENT_TYPES.FREEFORM,
      layout: PRESENTER_SLIDE_LAYOUTS.FILE,
      type: "file",
      label: safeLabel,
      title: fileTitle,
      marker: fileLabel,
      text: [fileTitle, asset.url].filter(Boolean).join("\n"),
      asset,
      sourceType: asset.kind || elementType,
      componentType: elementType,
      sort: index,
    };
  }
  return null;
}

function isMainPraiseTitleContentItem(item = {}, section = {}, titleText = "") {
  const titleKey = compactSearchValue(titleText);
  const labelKey = compactSearchValue(item?.label || section.elementLabel || "");
  if (titleKey !== "찬양" && titleKey !== "환영" && labelKey !== "환영") return false;
  return String(section.sectionKey || item?._worshipSectionKey || "").trim() === "praise"
    || isMainPraiseServiceItem(item, { allowUnlabeled: true });
}

function resolveMainPraiseIntroBodyText(service = null, bodyText = "") {
  const defaultTeam = serviceDefaultMainPraiseTeamName(service);
  if (!defaultTeam) return String(bodyText || "").trim();
  const bodyKey = compactSearchValue(bodyText);
  const defaultTeamKeys = new Set([
    "",
    "찬양팀",
    "담당",
    "헤세드찬양단",
    "테힐라찬양단",
    "썸프레이즈",
  ]);
  return defaultTeamKeys.has(bodyKey) ? defaultTeam : String(bodyText || "").trim();
}

function presenterMemoElementIsTitleSlide(elementType) {
  return ["title_person", "scripture_reading"].includes(elementType);
}

function presenterTitleAssigneeTitle(item = {}, label = "", displayText = "", elementType = "") {
  const compact = compactSearchValue(label);
  const text = String(displayText || "").trim();
  if (isCreedPresenterItem(item, label, displayText)) return "신앙고백";
  if (compact === "대표기도" || compact === "기도") return "대표기도";
  if (compact === "성경봉독") return "성경봉독";
  if (compact === "특송") return "특송";
  if (compact === "봉헌기도") return "봉헌기도";
  if (compact === "축도") return "축도";
  if (compact === "교회소식" || compact === "광고") return "교회소식";
  if (compact === "월삭기도") return text || "월삭기도";
  if (compact === "설교") return text || "설교";
  if (compact === "설교제목") return "설교";
  return text || label || serviceElementTypeLabel(elementType);
}

function presenterTitleAssigneePerson(item = {}, label = "", displayText = "", titleText = "", service = null) {
  if (isCreedPresenterItem(item, label, displayText)) return "사도신경";
  const compact = compactSearchValue(label);
  const text = cleanPresenterAssignee(displayText);
  if (compact === "성경봉독") {
    const referenceText = presenterFullKoreanBibleReference(text);
    return referenceText && compactSearchValue(referenceText) !== compactSearchValue(titleText) ? referenceText : "";
  }
  const assignee = cleanPresenterAssignee(item.assignee)
    || (typeof serviceItemDefaultAssignee === "function" ? serviceItemDefaultAssignee(item, service) : "");
  if (compact === "설교제목") return cleanList([presenterSermonContentTitle(text), assignee]).join("\n");
  if (assignee) return assignee;
  const fallback = presenterTitleAssigneeUsesWorshipLeader(compact)
    ? serviceWorshipLeaderLabel(service)
    : "";
  if (!text || compactSearchValue(text) === compactSearchValue(titleText)) return fallback;
  if (["대표기도", "기도", "성경봉독", "특송", "봉헌기도", "축도"].includes(compact)) return text;
  if (fallback) return fallback;
  return "";
}

function presenterFullKoreanBibleReference(value = "") {
  const text = String(value || "").trim();
  if (!text || typeof parseBibleReference !== "function") return text;
  const reference = parseBibleReference(text);
  if (!reference?.book || !reference?.chapter) return text;
  const bookName = String(reference.book.koreanName || reference.book.shortName || reference.book.code || "").trim();
  if (!bookName) return text;
  const range = reference.verse
    ? `${reference.chapter}:${reference.verse}${reference.verseEnd ? `–${reference.verseEnd}` : ""}`
    : `${reference.chapter}`;
  return [bookName, range].filter(Boolean).join(" ").trim() || text;
}

function presenterTitleAssigneeUsesWorshipLeader(compactLabel = "") {
  return [
    "봉헌기도",
    "교회소식",
    "광고",
    "축도",
    "예배의부름",
    "사죄의선언",
    "묵도",
  ].includes(compactLabel);
}

function presenterSlideUsesWorshipLeaderAssignee(slide = {}) {
  if (isPresenterScriptureReadingSource(slide)) return false;
  const key = compactSearchValue([
    slide.elementLabel,
    slide.sectionLabel,
    slide.label,
    slide.title,
  ].filter(Boolean).join(" "));
  return [
    "봉헌기도",
    "교회소식",
    "광고",
    "축도",
    "예배의부름",
    "사죄의선언",
    "묵도",
  ].some((label) => key.includes(label));
}

function isPresenterScriptureReadingSource(source = {}) {
  const key = compactSearchValue([
    source.elementType,
    source.componentType,
    source.sectionKey,
    source.elementLabel,
    source.sectionLabel,
    source.label,
    source.title,
  ].filter(Boolean).join(" "));
  return key.includes("scripturereading")
    || key.includes("성경봉독")
    || normalizeServiceElementType(source.elementType) === "scripture_reading"
    || normalizeWorshipElementType(source.elementType) === "scripture_reading";
}

function buildPresenterCustomSlides(item, section, index) {
  if (isScriptureBodyServiceItem(item)) return [];
  const slides = parseServiceItemMemo(item?.memo).slides;
  if (!slides.length) return [];
  const label = item.label || "";
  const songLikeItem = isSongServiceLabel(label) || isPresenterSpecialSongItem(item, section);
  const lyricSlides = slides.map((block, blockIndex) => {
    const parsed = parsePresenterCustomSlideBlock(block);
    return {
      id: `${item.id || index}:custom:${blockIndex}`,
      ...section,
      elementType: parsed.blank ? PRESENTER_ELEMENT_TYPES.BLANK : songLikeItem ? PRESENTER_ELEMENT_TYPES.PRAISE : PRESENTER_ELEMENT_TYPES.FREEFORM,
      layout: parsed.blank ? PRESENTER_SLIDE_LAYOUTS.BLANK : songLikeItem ? PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT : PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT,
      type: parsed.blank ? "blank" : songLikeItem ? "lyrics" : "component",
      label,
      title: section.sectionTitle || item.raw_title || label || "Slide",
      marker: parsed.marker,
      formKey: `custom:${blockIndex}`,
      text: parsed.text,
      sort: index + blockIndex / 100,
    };
  }).filter((slide) => slide.type === "blank" || String(slide.text || "").trim());
  if (!songLikeItem || !shouldIncludeSongTitleSlide(item, label)) return lyricSlides;
  return [
    presenterSongTitleSlide(item, section, null, null, serviceItemConnectedPraiseTitle(item, "title") || serviceItemDisplayText(item), index),
    ...lyricSlides,
  ];
}

function parsePresenterCustomSlideBlock(block) {
  const lines = String(block || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return { marker: "", text: "" };
  const first = lines[0];
  const bracketed = first.match(/^\[([^\]]+)\]$/)?.[1]?.trim();
  if (lines.length === 1 && bracketed && /^(간주|interlude|instrumental)$/i.test(bracketed)) {
    return { marker: "간주", text: "", blank: true };
  }
  const markerCandidate = bracketed || first;
  if (/^(Verse|Chorus|Pre[-\s]?Chorus|PC|Bridge|Coda|Tag|Lyrics)(?:\s+\d+)?$/i.test(markerCandidate)) {
    return { marker: normalizePresenterCustomMarker(markerCandidate), text: lines.slice(1).join("\n") };
  }
  return { marker: "", text: lines.join("\n") };
}

function normalizePresenterCustomMarker(value) {
  return String(value || "")
    .replace(/^pc$/i, "Pre-Chorus")
    .replace(/^pre[\s-]?chorus/i, "Pre-Chorus")
    .replace(/^verse/i, "Verse")
    .replace(/^chorus/i, "Chorus")
    .replace(/^bridge/i, "Bridge")
    .replace(/^coda/i, "Coda")
    .replace(/^tag/i, "Tag")
    .replace(/^lyrics/i, "Lyrics");
}

function buildPresenterScriptureTextSlides(item, section, index, service = null) {
  if (!isScriptureBodyServiceItem(item)) return [];
  const payload = serviceScriptureTextPayload(item, undefined, service);
  if (!payload.verses.length) return [];
  const context = presenterScriptureBodyContext(item, section, service);
  const readingForm = presenterScriptureContextUsesReadingForm(context);
  const reference = payload.reference || section.sectionTitle || "본문";
  const lastVerseIndex = payload.verses.length - 1;
  const citation = isPresenterCitationScriptureItem(item);
  return payload.verses.map((verse, verseIndex) => {
    const verseNumber = presenterScriptureVerseNumber(verse);
    const readingFinal = context === "reading" && verseIndex === lastVerseIndex;
    const referenceBook = readingForm
      ? (verse.referenceBookFull || payload.referenceBookFull || verse.referenceBook || payload.referenceBook || "")
      : (verse.referenceBook || payload.referenceBook || "");
    const verseReference = readingForm
      ? [referenceBook, verse.referenceRange || payload.referenceRange || ""].filter(Boolean).join(" ")
      : (verse.reference || reference);
    const verseText = verseNumber ? [verseNumber, verse.text].filter(Boolean).join("   ") : verse.text;
    return {
      id: `${item.id || index}:scripture:${verseReference}:${verseNumber || verseIndex + 1}`,
      ...section,
      elementTitle: verseReference,
      sectionName: presenterNameParts(section.sectionLabel, verseReference).join(" / ") || verseReference,
      elementType: PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT,
      layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
      type: "scripture",
      scriptureContext: context,
      scriptureVerse: Number(verse.number || verse.verse) || null,
      scriptureVerseEnd: Number(verse.verseEnd || verse.verse_end) || null,
      label: item.label || "본문",
      title: verseReference,
      marker: verseReference,
      referenceBook,
      referenceRange: verse.referenceRange || payload.referenceRange || "",
      translationLabel: verse.translationLabel || payload.translationLabel || "",
      text: citation ? presenterCitationScriptureText(verse, payload, context) : verseText,
      ...(context === "citation-chromakey" ? { citationBodyText: verse.text } : {}),
      citationQuickInsert: citation,
      scriptureReadingFinal: readingFinal,
      ...(readingForm ? { outputContext: "clean" } : {}),
      sort: index + verseIndex / 100,
    };
  });
}

function presenterPendingScriptureSlide(item, section, index, service = null) {
  const memo = typeof parseServiceItemMemo === "function"
    ? parseServiceItemMemo(item?.memo)
    : {};
  const references = typeof serviceItemScriptureReferences === "function"
    ? serviceItemScriptureReferences(item, memo, service)
    : [];
  if (!references.length) return null;
  const reference = typeof formatServiceScriptureReferenceList === "function"
    ? formatServiceScriptureReferenceList(references)
    : references.join("; ");
  const context = presenterScriptureBodyContext(item, section, service);
  return {
    id: `${item.id || index}:scripture-pending`,
    ...section,
    elementTitle: reference,
    sectionName: presenterNameParts(section.sectionLabel, reference).join(" / ") || reference,
    elementType: PRESENTER_ELEMENT_TYPES.BLANK,
    layout: PRESENTER_SLIDE_LAYOUTS.BLANK,
    type: "scripture-pending",
    scriptureContext: context,
    scripturePending: true,
    label: item.label || "본문",
    title: reference,
    marker: "",
    text: "",
    skipTrailingBlank: true,
    sort: index,
  };
}

function presenterScriptureVerseNumber(verse = {}) {
  const start = Number(verse.number || verse.verse) || 0;
  const end = Number(verse.verseEnd || verse.verse_end) || 0;
  if (!start) return String(verse.number || verse.verse || "").trim();
  return end > start ? `${start}–${end}` : String(start);
}

function isPresenterCitationScriptureItem(item = {}) {
  return compactSearchValue(item?.label || "") === "인용구절";
}

function presenterCitationScriptureText(verse = {}, payload = {}, context = "") {
  const number = presenterScriptureVerseNumber(verse);
  if (context === "citation-chromakey") {
    const reference = presenterCitationVerseReference(verse, payload, number);
    return reference ? [reference, verse.text].filter(Boolean).join("   ") : verse.text;
  }
  return number ? [number, verse.text].filter(Boolean).join("   ") : verse.text;
}

function presenterCitationVerseReference(verse = {}, payload = {}, verseNumber = "") {
  const book = presenterCitationBookName(verse.referenceBook || payload.referenceBook || "");
  const range = String(verse.referenceRange || payload.referenceRange || "").trim();
  const chapter = range.match(/^(\d+)/)?.[1] || "";
  const number = String(verseNumber || "").trim();
  if (book && chapter && number) return `${book} ${chapter}:${number}`;
  return presenterCitationDisplayReference(verse.reference || payload.reference || "");
}

function presenterCitationBookName(value = "") {
  const name = String(value || "").trim();
  const book = typeof findBibleBookByReferenceName === "function" ? findBibleBookByReferenceName(name) : null;
  return MINDEX_CONSTANTS.KOREAN_BIBLE_BOOK_ABBREVIATIONS?.[book?.code] || book?.shortName || name;
}

function presenterCitationDisplayReference(value = "") {
  const text = String(value || "").trim();
  const reference = typeof parseBibleReference === "function" ? parseBibleReference(text) : null;
  if (!reference) return text;
  const parts = serviceScriptureReferenceParts(reference, text);
  return [presenterCitationBookName(parts.referenceBook), parts.referenceRange].filter(Boolean).join(" ");
}

function presenterScriptureBodyContext(item = {}, section = {}, service = null) {
  const sectionKey = String(section.sectionKey || item?._worshipSectionKey || "").trim();
  if (sectionKey === "scripture_reading") return "reading";
  const chromakey = Boolean(service && presenterServiceUsesChromakey(service));
  if (isPresenterCitationScriptureItem(item)) return chromakey ? "citation-chromakey" : "citation";
  if (sectionKey === "sermon") return chromakey ? "sermon-chromakey" : "sermon";
  return "";
}

function presenterScriptureContextUsesReadingForm(context = "") {
  return context === "reading" || context === "sermon" || context === "citation";
}

function presenterScriptureContextUsesAddressTab(context = "") {
  return context === "citation-chromakey" || context === "sermon-chromakey";
}

function serviceScriptureTextPayload(item, memo = parseServiceItemMemo(item?.memo), service = null) {
  if (typeof serviceScriptureTextPayloadFromBible === "function") {
    const resolved = serviceScriptureTextPayloadFromBible(item, memo, service);
    if (resolved?.reference || resolved?.verses?.length) return resolved;
  }
  const reference = String(memo.scriptureReference || item?.raw_title || "").trim();
  return { reference, verses: [] };
}

function isScriptureBodyServiceItem(item) {
  const label = String(item?.label || "").replace(/\s+/g, "");
  const sectionKey = String(item?._worshipSectionKey || item?.sectionKey || item?.section_key || "").trim();
  const memo = typeof parseServiceItemMemo === "function" ? parseServiceItemMemo(item?.memo) : {};
  const elementType = typeof normalizeWorshipElementType === "function"
    ? normalizeWorshipElementType(memo.elementType || item?.elementType || item?.element_type || "")
    : String(memo.elementType || item?.elementType || item?.element_type || "").trim().toLowerCase();
  const directReferences = typeof serviceItemDirectScriptureReferences === "function"
    ? serviceItemDirectScriptureReferences(item, memo)
    : [];
  const hasScriptureReference = Boolean(
    directReferences.length
    || String(memo.scriptureReference || memo.scripture_reference || item?.raw_title || item?.title || "").trim()
  );
  const scriptureReferenceLabel = ["성경봉독", "인용구절", "말씀", "성경"].includes(label);
  return elementType === "scripture_body"
    || label === "본문"
    || label === "성경본문"
    || label === "설교본문"
    || (scriptureReferenceLabel && elementType !== "scripture_reading" && hasScriptureReference)
    || (sectionKey === "scripture_reading" && elementType === "scripture_body");
}

function parsePresenterScriptureTextPayload(value) {
  const lines = String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const verses = [];
  let reference = "";
  for (const line of lines) {
    const match = line.match(/^(\d{1,3})\s{3,}(.+)$/);
    if (match) {
      verses.push({ number: match[1], text: match[2].trim() });
      continue;
    }
    const inline = parsePresenterInlineScriptureText(line);
    if (inline.verses.length) {
      if (!reference && inline.reference) reference = inline.reference;
      verses.push(...inline.verses);
    } else if (!reference) {
      reference = line;
    }
  }
  return { reference, verses };
}

function parsePresenterInlineScriptureText(line) {
  const text = String(line || "").trim();
  const markerMatches = [...text.matchAll(/(?:^|\s)(\d{1,3})\s+(?=\S)/g)];
  if (!markerMatches.length) return { reference: "", verses: [] };
  const reference = text.slice(0, markerMatches[0].index).trim();
  const verses = markerMatches
    .map((match, index) => {
      const start = match.index + match[0].length;
      const end = markerMatches[index + 1]?.index ?? text.length;
      return {
        number: match[1],
        text: text.slice(start, end).trim(),
      };
    })
    .filter((verse) => verse.text);
  return { reference, verses };
}

function shouldIncludeSongTitleSlide(item, label) {
  if (isServiceConnectedPraiseSecondaryItem(item)) return false;
  const displayText = serviceItemDisplayText(item);
  if (serviceItemConnectedPraiseTitle(item, "title")) return true;
  if (!displayText) return false;
  return Boolean(
    item?.song_id
    || isSongServiceLabel(label)
    || isPresenterSpecialSongItem(item)
    || isMainPraiseServiceItem(item, { allowUnlabeled: true }),
  );
}

function presenterSongTitleSlide(item, section, song, version, displayText, index) {
  const connectedTitle = serviceItemConnectedPraiseTitle(item, "title");
  const effectiveDisplayText = connectedTitle || displayText;
  const marker = presenterPraiseMarker(song, displayText);
  const sectionHeading = presenterSongTitleSectionHeading(item, section);
  const displayTitle = presenterSongTitleDisplayTitle(connectedTitle ? null : song, connectedTitle ? null : version, effectiveDisplayText, sectionHeading);
  const titleText = presenterSongTitleContentText(displayTitle, sectionHeading);
  const songDetail = connectedTitle ? "" : presenterSongTitleDetail(song, version);
  const songTitleContent = {
    orderTitle: sectionHeading || item.label || "",
    title: songDetail && presenterSongTitleHymnNo(song, version)
      ? splitHymnNo(displayTitle).title || displayTitle : displayTitle,
    detail: songDetail,
    detailKind: connectedTitle ? "" : presenterSongTitleDetailKind(song, version),
  };
  if (sectionHeading) {
    return { ...presenterOrderContentTitleSlide(item, section, index, sectionHeading, titleText), songTitle: displayTitle, songTitleContent };
  }
  return {
    id: `${item.id || index}:song-title`,
    ...section,
    elementType: PRESENTER_ELEMENT_TYPES.PRAISE,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "song-title",
    label: item.label || "",
    title: displayTitle,
    subtitle: connectedTitle ? "" : versionDisplayName(song, version),
    songTitleContent,
    marker,
    sectionHeading,
    bodyText: "",
    text: titleText,
    sort: index - 0.001,
  };
}

function presenterSongTitleContentText(displayTitle = "", sectionHeading = "") {
  const titleKey = compactSearchValue(String(displayTitle || "").replace(PRESENTER_SONG_NOTE_PATTERN, ""));
  const headingKey = compactSearchValue(sectionHeading);
  if (!titleKey || (headingKey && titleKey === headingKey)) return "입력 필요";
  return formatPresenterSongTitleText(displayTitle);
}

function presenterSongTitleDetail(song = null, version = null) {
  const hymnNo = presenterSongTitleHymnNo(song, version);
  if (hymnNo) {
    const number = hymnNo.replace(/^통\s*/, "");
    const versionName = versionDisplayName(song, version);
    return `${versionName} ${number}장`;
  }
  return String(song?.original_title || "").trim() || String(song?.subtitle || "").trim();
}

function presenterSongTitleDetailKind(song = null, version = null) {
  if (presenterSongTitleHymnNo(song, version)) return "hymn";
  if (String(song?.original_title || "").trim()) return "original";
  return String(song?.subtitle || "").trim() ? "subtitle" : "";
}

function presenterSongTitleContent(slide = {}) {
  if (slide.songTitleContent) return slide.songTitleContent;
  // Older in-memory snapshots use separate fields; normalize at the boundary.
  return {
    orderTitle: slide.omitFullscreenOrderTitle ? "" : String(slide.orderTitle || slide.sectionHeading || slide.label || "").trim(),
    title: String(slide.fullscreenSongName || slide.songTitle || slide.title || slide.text || "").trim(),
    detail: String(slide.songDetail || "").trim(),
  };
}

function presenterOrderContentTitleSlide(item, section, index, orderTitle = "", contentTitle = "") {
  const safeOrderTitle = String(orderTitle || "").trim();
  const safeContentTitle = String(contentTitle || "").trim();
  return {
    id: `${item.id || index}:title-assignee`,
    ...section,
    elementType: PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE,
    layout: PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT,
    type: "title-assignee",
    label: item.label || "",
    title: safeOrderTitle,
    assignee: "",
    orderTitle: safeOrderTitle,
    contentTitle: safeContentTitle,
    marker: "",
    text: cleanList([safeOrderTitle, safeContentTitle]).join("\n"),
    sort: index - 0.001,
  };
}

function presenterSongTitleDisplayTitle(song = null, version = null, fallbackText = "", sectionHeading = "") {
  void sectionHeading;
  const title = presenterPraiseTitle(song, fallbackText);
  const hymnNo = presenterSongTitleHymnNo(song, version, fallbackText);
  if (!hymnNo) return title;
  const titleParts = splitHymnNo(title);
  if (titleParts.no) return [titleParts.no, titleParts.title].filter(Boolean).join(" ");
  return [hymnNo, title].filter(Boolean).join(" ");
}

function presenterSongTitleHymnNo(song = null, version = null, fallbackText = "") {
  const rawNo = String(presenterUnifiedHymnVersionNo(version) || song?.hymn_no || version?.hymn_no || splitHymnNo(fallbackText).no || "").trim();
  if (!rawNo) return "";
  const match = rawNo.match(/^(통\s*)?(\d{1,4})/);
  if (!match) return rawNo;
  return `${match[1] ? "통 " : ""}${Number(match[2])}`;
}

function presenterUnifiedHymnVersionNo(version = null) {
  if (!version) return "";
  const values = [version.hymn_no, version.name, version.curated_version_name, version.raw_section_name, version.version_label];
  for (const value of values) {
    const text = String(value || "").trim();
    const match = text.match(/(?:^|\(|\s)통(?:일)?\s*(\d{1,4})(?:\s|[.)]|$)/);
    if (match) return `통 ${Number(match[1])}`;
  }
  return "";
}

function presenterSongTitleSectionHeading(item = {}, section = {}) {
  if (!presenterSongTitleUsesSectionHeading(item, section)) return "";
  const heading = String(
    item?.label
    || section.elementLabel
    || section.sectionLabel
    || item?._worshipSectionTitle
    || section.sectionTitle
    || "",
  ).trim();
  return presenterSongTitleNormalizedHeading(heading, String(section.sectionKey || item?._worshipSectionKey || "").trim());
}

function presenterSongTitleNormalizedHeading(heading = "", sectionKey = "") {
  const raw = String(heading || "").trim();
  if (!raw) return "";
  const compact = compactSearchValue(raw);
  const compactSectionKey = String(sectionKey || "").trim();
  const genericBySection = {
    offering: "봉헌",
    doxology: "송영",
    sending: "파송",
    response_song: "결단",
    prayer_meeting_praise: "기도회",
    closing_hymn: "폐회",
    closing_visual: "폐회",
    closing_song: "폐회",
    hymn_praise: "찬송",
  };
  const canonicalBySection = {
    offering: "봉헌찬송",
    doxology: "송영",
    sending: "송영",
    response_song: "결단찬양",
    prayer_meeting_praise: "기도찬양",
    closing_hymn: "폐회찬송",
    closing_visual: "폐회찬송",
    closing_song: "폐회찬송",
    hymn_praise: "찬송",
  };
  if (compact === genericBySection[compactSectionKey]) return canonicalBySection[compactSectionKey] || raw;
  return raw;
}

function presenterSongTitleUsesSectionHeading(item = {}, section = {}) {
  if (isPresenterSpecialSongItem(item, section)) return false;
  if (section.sectionRole === "main-praise") return false;
  const sectionKey = String(section.sectionKey || item?._worshipSectionKey || "").trim();
  if ([
    "hymn_praise",
    "offering",
    "doxology",
    "sending",
    "response_song",
    "prayer_meeting_praise",
    "closing_song",
    "closing_hymn",
    "closing_visual",
  ].includes(sectionKey)) return true;
  const compact = compactSearchValue(item?.label || section.elementLabel || section.sectionLabel || "");
  if (!compact) return false;
  return /^(송영|파송|봉헌|봉헌찬송|봉헌찬양|파송찬송|결단|결단찬송|결단찬양|기도찬양|기도회찬양|폐회|폐회찬송)$/.test(compact);
}

function formatPresenterSongTitleText(title) {
  const cleanTitle = String(title || "").trim();
  if (!cleanTitle) return "";
  return PRESENTER_SONG_NOTE_PATTERN.test(cleanTitle)
    ? cleanTitle.replace(PRESENTER_SONG_NOTE_PATTERN, `${PRESENTER_SONG_NOTE} `)
    : `${PRESENTER_SONG_NOTE} ${cleanTitle}`;
}

function presenterPraiseTitle(song, fallbackText = "") {
  const linkedTitle = String(song?.title || "").trim();
  const cleanLinkedTitle = song?.hymn_no ? stripHymnNumber(linkedTitle) : linkedTitle;
  const normalizedLinkedTitle = cleanLinkedTitle.replace(/^찬송가\s*\d+\s*장\s*/i, "").trim();
  if (normalizedLinkedTitle) return normalizedLinkedTitle;
  const fallbackTitle = presenterPraiseFallbackTitle(fallbackText);
  const { title } = splitHymnNo(fallbackTitle);
  return title || fallbackTitle || "";
}

function presenterPraiseFallbackTitle(fallbackText = "") {
  const firstLine = String(fallbackText || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .find(Boolean) || "";
  return firstLine.split(/\s+\/\s+/)[0]?.trim() || firstLine;
}

function presenterPraiseElementTitle(song, version = null, fallbackText = "") {
  const title = presenterPraiseTitle(song, fallbackText);
  if (!song) return title;
  const meta = new Set();
  [song.subtitle, song.original_title, version?.subtitle, version?.original_title]
    .forEach((value) => addTitleMeta(meta, value));
  const visibleMeta = [...meta].filter((value) => normalizeTitle(value) !== normalizeTitle(title));
  return visibleMeta.length ? `${title} (${joinMetaItems(visibleMeta)})` : title;
}

function presenterPraiseMarker(song, fallbackText = "") {
  void song;
  void fallbackText;
  return "";
}

function presenterFormMarker(form) {
  const label = presenterFormDisplayLabel(form);
  if (isGenericPresenterFormLabel(label)) return "";
  return presenterFormPresetDisplayLabel(label) || label;
}

function presenterResolvedFormMarker(form = {}) {
  const presetLabel = String(form?._presenterPresetLabel || "").trim();
  if (presetLabel && isPresenterKoreanHymnPresetLabel(presetLabel)) return presetLabel;
  if (presetLabel && !isGenericPresenterFormLabel(presetLabel)) return presenterFormPresetDisplayLabel(presetLabel) || presetLabel;
  return presenterFormMarker(form);
}

function isPresenterKoreanHymnPresetLabel(value = "") {
  return /^(\d+\s*절|후렴|간주|마지막\s*절)$/u.test(String(value || "").trim());
}

function isGenericPresenterFormLabel(value) {
  return /^(lyrics|가사)$/i.test(String(value || "").trim());
}

function presenterSectionForServiceItem(item, index, displayText, song = null, version = null) {
  const label = String(item?.label || "").trim();
  const sectionLabel = presenterSectionLabelForServiceItem(item, label);
  const formHint = serviceItemFormHint(item);
  const connectedPraise = serviceItemConnectedPraise(item);
  const { no, title } = splitHymnNo(displayText);
  const linkedSongTitle = song ? presenterSongTitleDisplayTitle(song, version, displayText) : "";
  const linkedElementTitle = linkedSongTitle || (song ? presenterPraiseElementTitle(song, version, displayText) : "");
  const elementTitle = linkedElementTitle || [no, title].filter(Boolean).join(" ") || displayText || label || `항목 ${index + 1}`;
  const sectionLabelText = cleanList([label, formHint]).join(" · ");
  // Count the source version, not the selected/repeated performance sequence.
  const verseForms = normalizeForms(version?.forms || []).filter((form) =>
    normalizePresenterFormPresetLabel(presenterFormDisplayLabel(form)).type === "verse");
  return {
    ...(verseForms.length === 1 ? { controllerSingleVerse: true } : {}),
    sectionId: item?._worshipSectionId || item?.id || `section:${index}:${normalizeTitle([label, displayText].filter(Boolean).join(" "))}`,
    elementId: item?.id || `element:${index}:${normalizeTitle([label, displayText].filter(Boolean).join(" "))}`,
    sectionIndex: Number(item?._worshipSectionOrder) || index + 1,
    sectionKey: item?._worshipSectionKey || "",
    sectionLabel,
    sectionHeading: sectionLabel,
    sectionFormHint: formHint,
    sectionRole: isMainPraiseServiceItem(item, { allowUnlabeled: true }) ? "main-praise" : "",
    sectionTitle: sectionLabel,
    elementLabel: label,
    elementTitle,
    ...(connectedPraise ? { connectedPraise } : {}),
    sectionAssignee: item?.assignee || "",
    sectionName: [sectionLabel || sectionLabelText, elementTitle].filter(Boolean).join(" / "),
  };
}

function presenterSectionLabelForServiceItem(item = {}, fallbackLabel = "") {
  const explicit = String(item?._worshipSectionTitle || "").trim();
  if (explicit) return explicit;
  const key = String(item?._worshipSectionKey || "").trim();
  const canonicalByKey = {
    creed: "신앙고백",
    praise: "찬양",
    confession: "참회기도",
    hymn_praise: "찬송",
    prayer: "대표기도",
    scripture_reading: "성경봉독",
    special_song: "특송",
    sermon: "설교",
    response_song: "결단",
    offering: "봉헌",
    offering_prayer: "봉헌기도",
    announcements: "교회소식",
    community_confession: "공동체고백",
    doxology: "송영",
    closing_hymn: "폐회",
    benediction: "축도",
    closing: "마무리",
  };
  return canonicalByKey[key] || String(fallbackLabel || "").trim();
}

function presenterVideoSourceFromServiceItem(item, displayText) {
  const label = String(item?.label || "").trim();
  const rawTitle = String(item?.raw_title || "").trim();
  const source = extractPresenterVideoSource(rawTitle) || extractPresenterVideoSource(displayText);
  if (!source) return "";
  const labelLooksLikeVideo = /영상|비디오|video|movie|media/i.test(label);
  const sourceLooksLikeVideo = /\.(mp4|webm|mov|m4v)(?:[?#].*)?$/i.test(source);
  return labelLooksLikeVideo || sourceLooksLikeVideo ? source : "";
}

function extractPresenterVideoSource(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const cleaned = text.replace(/^(?:대기\s*)?(?:영상|비디오|video|movie)\s*:?\s*/i, "").trim();
  const direct = normalizePresenterMediaSource(cleaned);
  if (direct) return direct;
  const match = text.match(/(?:https?:\/\/[^\s"'<>]+|\.{0,2}\/[^\s"'<>]+|[^\s"'<>]+\.(?:mp4|webm|mov|m4v)(?:[?#][^\s"'<>]*)?)/i);
  return normalizePresenterMediaSource(match?.[0] || "");
}

function normalizePresenterMediaSource(value) {
  const source = String(value || "").trim();
  if (!source) return "";
  if (/^(javascript|data):/i.test(source)) return "";
  if (/^(https?:\/\/|\/|\.{1,2}\/)/i.test(source)) return source;
  const worshipBackgroundSource = normalizePresenterWorshipBackgroundSource(source);
  if (worshipBackgroundSource) return worshipBackgroundSource;
  if (/\.(mp4|webm|mov|m4v|png|jpe?g|gif|webp|svg|pdf|mp3|m4a|wav|aac|ogg|flac)(?:[?#].*)?$/i.test(source)) return source;
  return "";
}

function normalizePresenterWorshipBackgroundSource(source) {
  const text = String(source || "").trim();
  if (!text || !text.includes(`${WORSHIP_BACKGROUND_BASE}/`)) return "";
  const suffixMatch = text.match(/([?#].*)$/);
  const suffix = suffixMatch ? suffixMatch[1] : "";
  const clean = suffix ? text.slice(0, -suffix.length) : text;
  const fileName = worshipBackgroundFileNameFromPath(clean);
  if (!fileName) return "";
  const candidate = worshipBackgroundCandidateFileNames(fileName)
    .find((name) => WORSHIP_BACKGROUND_STATIC_FILES.has(name));
  if (!candidate) return "";
  const prefix = clean.slice(0, clean.length - fileName.length);
  return `${prefix}${candidate}${suffix}`;
}

function presenterMediaSourceIsImage(value) {
  return /\.(png|jpe?g|gif|webp|svg)(?:[?#].*)?$/i.test(String(value || "").trim());
}

function presenterMediaSourceIsYoutube(value) {
  return /(?:youtube\.com|youtu\.be)\//i.test(String(value || "").trim());
}

function presenterSlideAudioSource(slide) {
  const syncedSource = normalizePresenterMediaSource(slide?.syncTimeline?.audioSrc || "");
  if (syncedSource) return syncedSource;
  if (presenterSlideElementType(slide) !== PRESENTER_ELEMENT_TYPES.AUDIO) return "";
  return normalizePresenterMediaSource(slide.audioSrc || slide.asset?.url || slide.text);
}

function presenterPlaybackConfig(value, elementType = "") {
  const parsed = normalizeServicePlaybackConfig(value, elementType);
  const type = String(elementType || "").trim().toLowerCase();
  const defaults = type === "ready-video"
    ? { autoplay: true, muted: true, loop: true, controls: false }
    : type === "intro-video"
      ? { autoplay: true, muted: false, loop: false, controls: false, autoAdvanceOnEnd: true }
    : type === "audio"
      ? { output: "controller-audio", autoplay: false, muted: false, loop: false, controls: false }
      : { autoplay: true, muted: false, loop: false, controls: false };
  return { ...defaults, ...(parsed || {}) };
}

function splitPresenterLyricChunks(lyrics, linesPerSlide = 2) {
  const lines = splitFreeShowLines(normalizeLyricsForCopy(lyrics))
    .map((line) => line.trim())
    .filter(Boolean);
  const chunkSize = Math.max(1, Number(linesPerSlide) || 2);
  const chunks = [];
  for (let i = 0; i < lines.length; i += chunkSize) {
    chunks.push(lines.slice(i, i + chunkSize).join("\n"));
  }
  return chunks;
}

function getServiceItemVersion(song, item, service) {
  const versions = song?.versions || [];
  if (!versions.length) return null;

  const explicitVersionId = item?.version_id || item?.song_version_id;
  if (explicitVersionId) {
    const explicit = versions.find((version) => version.id === explicitVersionId);
    if (explicit) return explicit;
  }

  const displayText = serviceItemDisplayText(item);
  const { no, title } = splitHymnNo(displayText);
  const lookupTitles = serviceItemVersionLookupTitles(displayText, title, item?.raw_title);
  const directMatch = versions.find((version) =>
    serviceVersionLookupNames(song, version).some((name) =>
      lookupTitles.some((target) => name === target || name.startsWith(target) || target.startsWith(name)),
    ),
  );
  if (directMatch) return directMatch;

  const byServiceType = versions.find((version) =>
    serviceTypePreferredPraiseTypes(service?.type_id).some((type) =>
      versionEffectivePraiseTypes(song, version).includes(type),
    ),
  );
  if (byServiceType) return byServiceType;

  if (no) {
    const hymnVersion = versions.find((version) => versionEffectivePraiseTypes(song, version).includes("hymn"));
    if (hymnVersion) return hymnVersion;
  } else if (song?.hymn_no) {
    const nonHymnVersion = versions.find((version) =>
      versionEffectivePraiseTypes(song, version).some((type) => type === "ccm" || type === "children"),
    );
    if (nonHymnVersion) return nonHymnVersion;
  }

  return versions.find((version) => version.id === getDefaultVersionId(song)) || versions[0];
}

function presenterSongForServiceItem(item = {}, displayText = serviceItemDisplayText(item), label = item?.label || "", service = null) {
  const linkedSong = item.song_id
    ? (typeof songById === "function" ? songById(item.song_id) : state.songs.find((candidate) => candidate.id === item.song_id) || null)
    : null;
  if (linkedSong) return linkedSong;
  if (!isSongServiceLabel(label) && !isPresenterSpecialSongItem(item)) return null;
  return findServicePraiseSong(displayText) || presenterSyntheticHymnSongFromDisplayText(displayText);
}

function presenterSyntheticHymnSongFromDisplayText(displayText = "") {
  const { no, title } = splitHymnNo(displayText);
  const hymnNo = normalizedHymnScoreNumber(no);
  if (!hymnNo) return null;
  const cleanTitle = stripHymnNumber(title || displayText).trim() || `찬송가 ${hymnNo}`;
  return {
    id: `__synthetic_hymn_${hymnNo}__`,
    title: cleanTitle,
    hymn_no: hymnNo,
    versions: [],
    _syntheticHymn: true,
  };
}

function getPresenterServiceItemVersion(song, item, service) {
  const preferred = getServiceItemVersion(song, item, service);
  if (presenterVersionHasUsableLyrics(preferred)) return preferred;
  return presenterFallbackLyricVersion(song, preferred) || preferred;
}

function presenterFallbackLyricVersion(song, preferred = null) {
  const versions = song?.versions || [];
  if (!versions.length) return null;
  const defaultVersionId = getDefaultVersionId(song);
  const candidates = [
    versions.find((version) => version.id === defaultVersionId),
    ...versions,
  ].filter(Boolean);
  return candidates.find((version) => version !== preferred && presenterVersionHasUsableLyrics(version)) || null;
}

function presenterVersionHasUsableLyrics(version = null) {
  return normalizeForms(version?.forms || []).some((form) => normalizeLyricsForCopy(form.lyrics));
}

function serviceTypePreferredPraiseTypes(typeId) {
  if (typeId === "children") return ["children"];
  if (typeId === "youth" || typeId === "young-adult") return ["ccm"];
  return [];
}

function serviceItemVersionLookupTitles(...values) {
  return [...new Set(
    values
      .flatMap((value) => [value, stripTitleDecorations(value)])
      .map(normalizeTitle)
      .filter((value) => value && value.length > 1),
  )];
}

function serviceVersionLookupNames(song, version) {
  return serviceItemVersionLookupTitles(
    version?.name,
    version?.curated_version_name,
    version?.raw_section_name,
    version?.version_label,
    versionDisplayName(song, version),
  );
}

function isSongServiceLabel(label) {
  const compact = String(label || "").replace(/\s+/g, "");
  if (!compact) return false;
  if (compact === "봉헌") return true;
  if (compact === "결단" || compact === "파송") return true;
  if (/찬양|찬송|특송|송영/.test(compact)) return true;
  return /^(결단|봉헌|파송)(찬양|찬송)$/.test(compact);
}

function presenterStatePayload(serviceId = state.presenter.serviceId) {
  const service = state.services.find((svc) => svc.id === serviceId);
  const slides = presenterSlidesForService(serviceId);
  const serviceChromakey = presenterServiceUsesChromakey(service);
  const hasCleanSlides = slides.some((slide) =>
    presenterSlideOutputContext(slide, serviceChromakey) === "clean");
  const backgroundImages = presenterBackgroundSourcesForService(service, {
    includeChromakeyCleanSlides: hasCleanSlides,
  });
  return {
    serviceId,
    serviceType: service?.type_id || "",
    serviceTitle: [serviceDisplayTypeName(service), service ? formatServiceDate(service) : ""].filter(Boolean).join(" · "),
    serviceDate: service?.date || "",
    chromakey: serviceChromakey,
    outputTheme: presenterOutputTheme(service?.type_id),
    backgroundImage: backgroundImages[0] || "",
    backgroundImages,
    slides,
    index: clampPresenterIndex(state.presenter.index, slides.length),
    slideAnchor: presenterSlideAnchor(slides[clampPresenterIndex(state.presenter.index, slides.length)]),
    safetyBlank: Boolean(state.presenter.safetyBlank),
    liveScripture: state.presenter.liveScripture?.active ? state.presenter.liveScripture : null,
    livePraise: null,
    updatedAt: Date.now(),
  };
}

function readPresenterControllerRestorePayload() {
  try {
    const stored = readPresenterStoredPayload();
    const payload = stored ? normalizePresenterPayload(stored) : null;
    if (!payload?.serviceId || !payload.slides.length) return null;
    if (Date.now() - payload.updatedAt > PRESENTER_CONTROLLER_RESTORE_MAX_AGE_MS) return null;
    return payload;
  } catch {
    return null;
  }
}

function primePresenterControllerRestore() {
  state.presenter.restorePayload = readPresenterControllerRestorePayload();
}

function restorePresenterControllerSession() {
  // Only reattach when an output has actually answered the controller. This
  // prevents an old local payload from reviving a presentation on app launch.
  if (state.presenter.serviceId || !isPresenterOutputHeartbeatOpen()) return "none";

  const payload = state.presenter.restorePayload || readPresenterControllerRestorePayload();
  if (!payload) return "none";

  const service = state.services.find((candidate) => candidate.id === payload.serviceId);
  if (!service || !state.serviceItems[service.id]) return "pending";

  const slides = buildServicePresenterSlides(service.id);
  if (!slides.length) return "pending";

  state.presenter.serviceId = service.id;
  state.presenter.slides = slides;
  state.presenter.index = presenterSlideIndexForAnchor(
    slides,
    payload.slideAnchor || presenterSlideAnchor(payload.slides?.[payload.index]),
    payload.index,
  );
  state.presenter.safetyBlank = Boolean(payload.safetyBlank);
  state.presenter.jumpDraft = "";
  state.presenter.liveScripture = payload.liveScripture?.active
    ? {
      reference: payload.liveScripture.reference || "",
      draft: "",
      active: true,
      slide: payload.liveScripture.slide || null,
    }
    : { reference: "", draft: "", active: false, slide: null };
  state.presenter.livePraise = emptyLivePraiseState();
  state.presenter.restorePayload = null;

  if (state.module === "presenter") {
    state.selectedServiceId = service.id;
    state.selectedServiceTypeId = service.type_id;
  }

  publishPresenterState({ force: true });
  refreshPresenterOutputConnectionState();
  return "restored";
}

function bindPresenterChannel() {
  window.addEventListener("storage", handlePresenterStorageSignal);
  if (!("BroadcastChannel" in window)) return;
  try {
    state.presenter.channel = new BroadcastChannel(PRESENTER_CHANNEL);
  } catch {
    state.presenter.channel = null;
    return;
  }
  state.presenter.channel.onmessage = (event) => handlePresenterControllerMessage(event.data);
  // The output can stay open while the controller reloads. Ask it to announce
  // itself again so sidebar clicks immediately return to live-output behavior.
  state.presenter.channel.postMessage({ type: "presenter-controller-ready" });
}

function handlePresenterControllerMessage(message = {}) {
  if (["presenter-ready", "presenter-heartbeat"].includes(message.type)) {
    state.presenter.outputTransportVersion = Number(message.transportVersion) || 0;
  }
  if (message.type === "presenter-ready") {
    markPresenterOutputConnected(message.clientId);
    const restoreState = restorePresenterControllerSession();
    if (restoreState === "none") publishPresenterState({ force: true });
    return;
  }
  if (message.type === "presenter-heartbeat") {
    markPresenterOutputConnected(message.clientId, message.warmup);
    restorePresenterControllerSession();
    reconcilePresenterTransportReceipt(message);
    state.presenter.videoHealth = message.videoHealth
      ? { ...message.videoHealth, clientId: message.clientId, receivedAt: Date.now() } : null;
    syncPresenterVideoHealthControl();
    return;
  }
  if (message.type === "presenter-output-disconnect") {
    markPresenterOutputDisconnected(message.clientId);
    return;
  }
  if (message.type === "presenter-control") {
    if (message.action === "stop") {
      stopPresenterOutput(state.presenter.serviceId);
      return;
    }
    markPresenterOutputConnected(message.clientId);
    runPresenterAction(message.action, state.presenter.serviceId, {
      index: Number.isFinite(Number(message.index)) ? Number(message.index) : undefined,
    });
    return;
  }
  if (message.type === "presenter-jump-draft") {
    if (message.value) setPresenterJumpDraft(message.value, state.presenter.serviceId);
    else clearPresenterJumpDraft(state.presenter.serviceId);
  }
}

function handlePresenterStorageSignal(event) {
  if (event.key !== PRESENTER_SIGNAL_KEY || !event.newValue) return;
  try {
    handlePresenterControllerMessage(JSON.parse(event.newValue));
  } catch {
    // Ignore malformed cross-window presenter signals.
  }
}

function markPresenterOutputConnected(clientId = "", warmup = null) {
  if (state.presenter.outputStopAt) {
    if (clientId && clientId === state.presenter.outputStoppingClientId) return;
    state.presenter.outputStopAt = 0;
    state.presenter.outputStoppingClientId = "";
  }
  const wasConnected = state.presenter.outputConnectedAt
    && Date.now() - state.presenter.outputConnectedAt <= PRESENTER_OUTPUT_HEARTBEAT_TTL_MS;
  state.presenter.outputConnectedAt = Date.now();
  state.presenter.outputPendingAt = 0;
  state.presenter.outputBlockedAt = 0;
  state.presenter.outputAttemptServiceId = "";
  if (clientId) state.presenter.outputClientId = clientId;
  const warmupChanged = updatePresenterOutputWarmupState(warmup);
  if (!state.presenter.outputWindowMonitor) startPresenterOutputWindowMonitor(state.presenter.serviceId);
  if (!wasConnected || warmupChanged) refreshPresenterOutputConnectionState();
}

function markPresenterOutputDisconnected(clientId = "") {
  if (clientId && state.presenter.outputClientId && clientId !== state.presenter.outputClientId) return;
  state.presenter.outputWindow = null;
  state.presenter.outputConnectedAt = 0;
  state.presenter.outputPendingAt = 0;
  state.presenter.outputClientId = "";
  state.presenter.outputWarmup = null;
  stopPresenterOutputWindowMonitor();
  refreshPresenterOutputConnectionState();
  if (state.presenter.serviceId) renderPresenterControlState(state.presenter.serviceId);
}

function updatePresenterOutputWarmupState(warmup = null) {
  if (!warmup || typeof warmup !== "object") return false;
  const total = Math.max(0, Number(warmup.total) || 0);
  const ready = Math.max(0, Math.min(total, Number(warmup.ready) || 0));
  const queued = Math.max(0, Math.min(total, Number(warmup.queued) || 0));
  const nextWarmup = {
    serviceId: warmup.serviceId || state.presenter.serviceId || "",
    total,
    ready,
    queued,
    complete: Boolean(warmup.complete) || (total > 0 && ready >= total),
    updatedAt: Date.now(),
  };
  const previous = state.presenter.outputWarmup;
  const changed = !previous
    || previous.serviceId !== nextWarmup.serviceId
    || previous.total !== nextWarmup.total
    || previous.ready !== nextWarmup.ready
    || previous.queued !== nextWarmup.queued
    || previous.complete !== nextWarmup.complete;
  state.presenter.outputWarmup = nextWarmup;
  return changed;
}

function refreshPresenterOutputConnectionState() {
  const serviceIds = new Set([state.presenter.serviceId, state.selectedServiceId].filter(Boolean));
  serviceIds.forEach((serviceId) => renderPresenterControlState(serviceId));
}

function publishPresenterState(options = {}) {
  const payload = presenterStatePayload();
  if (!options.force && !payload.serviceId && !payload.slides.length) return;
  publishPresenterPayload(payload, options);
}

const PRESENTER_NAVIGATION_STORAGE_KEY = "mindex.presenter.state.navigation";
let presenterTransportSequence = 0;
const presenterTransportSession = `${Date.now()}:${Math.random()}`;
let presenterTransportSnapshot = null;
let presenterTransportLatest = null;

function reconcilePresenterTransportReceipt(message = {}) {
  const latest = presenterTransportLatest;
  if (!latest || typeof message.receivedMessageId !== "string") return;
  if (state.presenter.outputStopAt || latest.payload.serviceId !== state.presenter.serviceId) return;
  if (message.receivedMessageId === latest.payload.messageId) return;
  if (Date.now() - latest.sentAt < 750 || Date.now() - latest.retriedAt < 1000) return;
  latest.retriedAt = Date.now();
  // Replay the same ID: a delayed acknowledgement must not render twice.
  safeStorageSet("local", PRESENTER_STORAGE_KEY, JSON.stringify(latest.payload));
  try {
    state.presenter.channel?.postMessage({ type: "presenter-state", payload: latest.payload });
  } catch {
    // The storage event remains available when the channel has closed.
  }
}

function mergePresenterNavigation(snapshot, navigation) {
  if (!snapshot || navigation?.snapshotId !== snapshot.snapshotId) return snapshot;
  if (Number(navigation.updatedAt) < Number(snapshot.updatedAt)) return snapshot;
  return { ...snapshot, ...navigation, slides: snapshot.slides };
}

function readPresenterStoredPayload() {
  const snapshot = JSON.parse(safeStorageGet("local", PRESENTER_STORAGE_KEY, "null") || "null");
  try {
    const navigation = JSON.parse(safeStorageGet("local", PRESENTER_NAVIGATION_STORAGE_KEY, "null") || "null");
    return mergePresenterNavigation(snapshot, navigation);
  } catch {
    return snapshot;
  }
}

function publishPresenterPayload(payload, options = {}) {
  const { index, slideAnchor, safetyBlank, liveScripture, livePraise, updatedAt,
    snapshotId: previousSnapshotId, messageId: previousMessageId, ...content } = payload;
  const contentKey = JSON.stringify(content);
  const messageId = `${presenterTransportSession}:${++presenterTransportSequence}`;
  const compact = !options.force && state.presenter.outputTransportVersion === 1
    && presenterTransportSnapshot?.contentKey === contentKey;
  if (compact) {
    const navigation = { snapshotId: presenterTransportSnapshot.id, messageId,
      index, slideAnchor, safetyBlank, liveScripture, livePraise, updatedAt };
    presenterTransportLatest = { payload: { ...payload, ...navigation }, sentAt: Date.now(), retriedAt: 0 };
    safeStorageSet("local", PRESENTER_NAVIGATION_STORAGE_KEY, JSON.stringify(navigation));
    try {
      state.presenter.channel?.postMessage({ type: "presenter-navigation", payload: navigation });
    } catch {
      // Keep controller navigation usable while storage delivers the move.
    }
    return;
  }
  const snapshot = { ...payload, snapshotId: messageId, messageId };
  presenterTransportLatest = { payload: snapshot, sentAt: Date.now(), retriedAt: 0 };
  const stored = safeStorageSet("local", PRESENTER_STORAGE_KEY, JSON.stringify(snapshot));
  presenterTransportSnapshot = stored ? { id: messageId, contentKey } : null;
  try {
    state.presenter.channel?.postMessage({ type: "presenter-state", payload: snapshot });
  } catch {
    // Storage delivery and heartbeat reconciliation can recover this send.
  }
}

function presenterOutputUrl(options = {}) {
  const url = new URL(window.location.href);
  url.searchParams.set("output", "presenter");
  url.hash = "";
  return url.toString();
}

function handlePresenterShortcut(event) {
  const presenterServiceId = state.presenter.serviceId;
  if (state.module !== "presenter" || !presenterServiceId) return false;
  if (event.key === "F11" && isPresenterOutputWindowOpen()) {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    requestPresenterOutputFullscreenFromController();
    return true;
  }
  if (shouldKeepPresenterShortcutInFocusedControl(event)) return false;
  if (event.metaKey || event.ctrlKey || event.altKey) return false;
  const activeServiceSelected = state.selectedServiceId === presenterServiceId;

  if (event.key === "Escape") {
    consumePresenterShortcutEvent(event);
    if (activeServiceSelected && state.presenter.jumpDraft) {
      clearPresenterJumpDraft(presenterServiceId);
      return true;
    }
    const now = Date.now();
    if (now - (state.presenter.exitArmedAt || 0) <= PRESENTER_OUTPUT_ESCAPE_EXIT_MS) {
      stopPresenterOutput(presenterServiceId);
      return true;
    }
    state.presenter.exitArmedAt = now;
    return true;
  }

  if (!activeServiceSelected) return false;

  if (/^\d$/.test(event.key)) {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    setPresenterJumpDraft(`${state.presenter.jumpDraft || ""}${event.key}`, presenterServiceId);
    return true;
  }

  if (event.key === "Enter" && state.presenter.jumpDraft) {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    commitPresenterJumpDraft(presenterServiceId);
    return true;
  }

  if (event.key === "Enter" || event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "PageDown" || event.key === " ") {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    runPresenterAction("next", presenterServiceId);
    return true;
  }

  if (event.key === "ArrowLeft" || event.key === "ArrowUp" || event.key === "PageUp") {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    runPresenterAction("prev", presenterServiceId);
    return true;
  }

  if (event.key === "Home") {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    runPresenterAction("first", presenterServiceId);
    return true;
  }

  if (event.key === "End") {
    consumePresenterShortcutEvent(event);
    state.presenter.exitArmedAt = 0;
    runPresenterAction("last", presenterServiceId);
    return true;
  }

  return false;
}

function consumePresenterShortcutEvent(event) {
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
}

function requestPresenterOutputFullscreenFromController() {
  presenterOutputWindowRef()?.focus?.();
  window.mindexElectron?.fullscreenPresenterOutput?.().catch?.(() => {});
}

function shouldKeepPresenterShortcutInFocusedControl(event) {
  const target = event?.target instanceof Element ? event.target : null;
  if (!target) return false;
  if (target.closest("[data-presenter-jump-input]")) {
    return !["ArrowRight", "ArrowDown", "PageDown", " ", "ArrowLeft", "ArrowUp", "PageUp"].includes(event.key);
  }
  if (target.closest("[data-service-music-action]")) return true;
  if (
    (presenterControllerNavigationKey(event.key) || /^\d$/.test(event.key) || event.key === "Escape")
    && target.closest("[data-presenter-action], .svc-slide-thumb[data-presenter-index][data-service-id], .svc-slide-thumb-wrap[data-presenter-index][data-service-id]")
  ) {
    return false;
  }
  if (target.closest("button, a, [role='button'], [tabindex]:not([tabindex='-1'])")) return true;
  return shouldKeepHorizontalNavigationInFocusedControl(target);
}

function presenterControllerNavigationKey(key = "") {
  return ["Enter", "ArrowRight", "ArrowDown", "PageDown", " ", "ArrowLeft", "ArrowUp", "PageUp", "Home", "End"].includes(key);
}

function isPresenterOutputRoute() {
  const params = new URLSearchParams(window.location.search);
  return params.get("output") === "presenter" || params.get("mindex-output") === "presenter";
}

function presenterOutputDocumentTitle(payload = {}) {
  const title = String(payload?.serviceTitle || "").split("·")[0].trim();
  return title || "MINDEX";
}

function syncPresenterOutputDocumentTitle(payload = {}) {
  document.title = presenterOutputDocumentTitle(payload);
}

function presenterScaleForBox(width, height, stageWidth = 1920, stageHeight = 1080) {
  const boxWidth = Number(width);
  const boxHeight = Number(height);
  if (!Number.isFinite(boxWidth) || !Number.isFinite(boxHeight) || boxWidth <= 0 || boxHeight <= 0) return 1;
  return Math.min(1, boxWidth / stageWidth, boxHeight / stageHeight);
}

const PRESENTER_PREVIEW_OVERSCAN_PX = 0;

function presenterPreviewScaleForBox(width, height, stageWidth = 1920, stageHeight = 1080) {
  const boxWidth = Number(width);
  const boxHeight = Number(height);
  if (!Number.isFinite(boxWidth) || !Number.isFinite(boxHeight) || boxWidth <= 0 || boxHeight <= 0) return 1;
  return presenterScaleForBox(
    boxWidth + PRESENTER_PREVIEW_OVERSCAN_PX,
    boxHeight + PRESENTER_PREVIEW_OVERSCAN_PX,
    stageWidth,
    stageHeight,
  );
}

function applyPresenterOutputViewportScale(root = document.getElementById("presenterOutputRoot")) {
  if (!root) return;
  root.style.setProperty("--presenter-stage-scale", "1");
}

function applyPresenterPreviewScales(host = document) {
  if (!host?.querySelectorAll) return;
  host.querySelectorAll(".svc-slide-mini-canvas.presenter-output-root").forEach((canvas) => {
    const frame = canvas.closest(".svc-slide-thumb-frame, .svc-presenter-live-preview") || canvas.parentElement;
    const rect = frame?.getBoundingClientRect?.();
    const scale = presenterPreviewScaleForBox(
      rect?.width || 0,
      rect?.height || 0,
    );
    const currentScale = Number(canvas.style.getPropertyValue("--presenter-preview-scale"));
    if (Number.isFinite(currentScale) && Math.abs(currentScale - scale) < 0.000001) return;
    canvas.style.setProperty("--presenter-preview-scale", String(scale));
  });
}

function initPresenterOutputCore() {
  document.title = "MINDEX";
  document.documentElement.classList.add("presenter-output-document");
  document.body.className = "presenter-output-body";
  document.body.innerHTML = `
    <main id="presenterOutputRoot" class="presenter-output-root no-chromakey" aria-live="polite"></main>
  `;
  applyPresenterOutputViewportScale();
  window.addEventListener("resize", () => applyPresenterOutputViewportScale());

  let currentPayload = null;
  let channel = null;
  let jumpDraft = "";
  let exitArmedAt = 0;
  let outputStopping = false;
  const outputClientId = `presenter-output:${Date.now()}:${Math.random().toString(36).slice(2)}`;
  let heartbeatTimer = null;
  const receivedMessages = new Set();
  const receivedSequences = new Map();
  const applyPayload = (payload) => {
    if (payload?.messageId && receivedMessages.has(payload.messageId)) return;
    if (payload?.messageId) {
      const split = payload.messageId.lastIndexOf(":");
      const sender = payload.messageId.slice(0, split);
      const sequence = Number(payload.messageId.slice(split + 1));
      if (Number.isFinite(sequence) && sequence <= (receivedSequences.get(sender) || 0)) return;
      if (Number.isFinite(sequence)) receivedSequences.set(sender, sequence);
      receivedMessages.add(payload.messageId);
      if (receivedMessages.size > 128) receivedMessages.delete(receivedMessages.values().next().value);
    }
    currentPayload = normalizePresenterPayload(payload);
    syncPresenterOutputDocumentTitle(currentPayload);
    renderPresenterOutput(currentPayload, { onAutoAdvance: requestPresenterOutputNext });
  };
  const applyInitialPresenterState = (payload) => {
    applyPayload(payload);
  };
  const sendControllerMessage = (message) => {
    const payload = { ...message, updatedAt: Date.now() };
    if (channel) {
      channel.postMessage(payload);
      return true;
    }
    return safeStorageSet("local", PRESENTER_SIGNAL_KEY, JSON.stringify(payload));
  };
  const postHeartbeat = () => {
    if (outputStopping) return;
    sendControllerMessage({
      type: "presenter-heartbeat",
      clientId: outputClientId,
      transportVersion: 1,
      receivedMessageId: currentPayload?.messageId || "",
      videoHealth: presenterOutputVideoHealth(currentPayload),
      warmup: presenterOutputWarmupSummary(),
    });
  };
  presenterOutputImageWarmupState.onProgress = postHeartbeat;
  const closeOutputChannel = () => {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    channel?.close?.();
    channel = null;
    presenterOutputImageWarmupState.onProgress = null;
  };
  const canCloseOutputWindow = () => {
    try {
      return Boolean(window.opener && !window.opener.closed);
    } catch {
      return false;
    }
  };
  const requestPresenterOutputStop = () => {
    if (outputStopping) return;
    outputStopping = true;
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    const payload = {
      type: "presenter-control",
      action: "stop",
      clientId: outputClientId,
      updatedAt: Date.now(),
    };
    sendControllerMessage(payload);
    window.setTimeout(() => {
      closeOutputChannel();
      if (canCloseOutputWindow()) window.close();
    }, 120);
  };
  const applyPresenterOutputActionLocally = (action, detail = {}) => {
    if (!currentPayload) return;
    currentPayload = applyPresenterActionToPayload(currentPayload, action, detail);
    publishPresenterPayload(currentPayload);
    renderPresenterOutput(currentPayload, { onAutoAdvance: requestPresenterOutputNext });
  };
  const requestPresenterOutputNext = () => {
    postHeartbeat();
    sendControllerMessage({ type: "presenter-control", action: "next", clientId: outputClientId });
    applyPresenterOutputActionLocally("next");
  };
  const postDisconnect = () => {
    const payload = {
      type: "presenter-output-disconnect",
      clientId: outputClientId,
      updatedAt: Date.now(),
    };
    sendControllerMessage(payload);
  };

  const renderStoredState = () => {
    try {
      const stored = readPresenterStoredPayload();
      applyPayload(stored);
    } catch {
      applyPayload(null);
    }
  };
  const renderFreshStoredState = () => {
    try {
      const stored = readPresenterStoredPayload();
      if (!stored?.updatedAt || Date.now() - Number(stored.updatedAt) > 5000) return false;
      applyPayload(stored);
      return true;
    } catch {
      return false;
    }
  };
  let lastVideoRetryId = "";
  const handleOutputSignalMessage = (message = {}) => {
    if (message.type === "presenter-video-retry") {
      if (message.clientId !== outputClientId || !message.requestId || message.requestId === lastVideoRetryId) return;
      lastVideoRetryId = message.requestId;
      retryPresenterOutputVideo(message, currentPayload).finally(postHeartbeat);
      return;
    }
    if (message?.type === "presenter-navigation") {
      if (message.payload?.snapshotId === currentPayload?.snapshotId) {
        applyPayload(mergePresenterNavigation(currentPayload, message.payload));
      } else {
        renderStoredState();
      }
      return;
    }
    if (message?.type === "presenter-state") {
      applyInitialPresenterState(message.payload);
      return;
    }
    if (message?.type === "presenter-controller-ready") {
      sendControllerMessage({ type: "presenter-ready", clientId: outputClientId });
      postHeartbeat();
      return;
    }
    if (message?.type === "presenter-output-close") {
      window.setTimeout(() => {
        closeOutputChannel();
        window.close();
      }, 40);
    }
  };

  if ("BroadcastChannel" in window) {
    try {
      channel = new BroadcastChannel(PRESENTER_CHANNEL);
    } catch {
      channel = null;
    }
  }
  if (channel) {
    renderFreshStoredState();
    channel.onmessage = (event) => {
      if (event.data?.type === "presenter-video-retry") {
        handleOutputSignalMessage(event.data);
        return;
      }
      if (event.data?.type === "presenter-navigation") {
        handleOutputSignalMessage(event.data);
        return;
      }
      if (event.data?.type === "presenter-state") {
        applyInitialPresenterState(event.data.payload);
        return;
      }
      if (event.data?.type === "presenter-controller-ready") {
        channel.postMessage({ type: "presenter-ready", clientId: outputClientId });
        postHeartbeat();
        return;
      }
      if (event.data?.type === "presenter-output-close") {
        window.setTimeout(() => {
          closeOutputChannel();
          window.close();
        }, 40);
      }
    };
    window.setTimeout(() => {
      sendControllerMessage({ type: "presenter-ready", clientId: outputClientId });
      postHeartbeat();
    }, 50);
    heartbeatTimer = window.setInterval(postHeartbeat, PRESENTER_OUTPUT_HEARTBEAT_INTERVAL_MS);
  } else {
    renderStoredState();
    window.setTimeout(() => {
      sendControllerMessage({ type: "presenter-ready", clientId: outputClientId });
      postHeartbeat();
    }, 50);
    heartbeatTimer = window.setInterval(postHeartbeat, PRESENTER_OUTPUT_HEARTBEAT_INTERVAL_MS);
  }
  window.addEventListener("pagehide", () => {
    postDisconnect();
    closeOutputChannel();
  });

  window.addEventListener("storage", (event) => {
    if (event.key === PRESENTER_STORAGE_KEY || event.key === PRESENTER_NAVIGATION_STORAGE_KEY) {
      renderStoredState();
      return;
    }
    if (event.key !== PRESENTER_SIGNAL_KEY || !event.newValue) return;
    try {
      const message = JSON.parse(event.newValue);
      handleOutputSignalMessage(message);
    } catch {
      // Ignore malformed cross-window presenter signals.
    }
  });
  window.addEventListener("keydown", (event) => {
    if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      return;
    }
    if (!event.metaKey && !event.ctrlKey && !event.altKey && /^\d$/.test(event.key)) {
      event.preventDefault();
      jumpDraft = `${jumpDraft}${event.key}`.slice(0, PRESENTER_JUMP_MAX_DIGITS);
      sendControllerMessage({ type: "presenter-jump-draft", value: jumpDraft });
      postHeartbeat();
      return;
    }
    if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key === "Enter" && jumpDraft) {
      event.preventDefault();
      const index = Number(jumpDraft) - 1;
      jumpDraft = "";
      sendControllerMessage({ type: "presenter-jump-draft", value: "" });
      postHeartbeat();
      sendControllerMessage({ type: "presenter-control", action: "jump", index, clientId: outputClientId });
      applyPresenterOutputActionLocally("jump", { index });
      return;
    }
    if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key === "Escape" && jumpDraft) {
      event.preventDefault();
      jumpDraft = "";
      sendControllerMessage({ type: "presenter-jump-draft", value: "" });
      postHeartbeat();
      return;
    }
    if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key === "Escape") {
      event.preventDefault();
      const now = Date.now();
      if (now - exitArmedAt <= PRESENTER_OUTPUT_ESCAPE_EXIT_MS) {
        requestPresenterOutputStop();
        return;
      }
      exitArmedAt = now;
      postHeartbeat();
      return;
    }
    const action = presenterOutputKeyAction(event);
    if (action) {
      event.preventDefault();
      jumpDraft = "";
      sendControllerMessage({ type: "presenter-jump-draft", value: "" });
      postHeartbeat();
      sendControllerMessage({ type: "presenter-control", action, clientId: outputClientId });
      applyPresenterOutputActionLocally(action);
    }
  });
}

function presenterOutputKeyAction(event) {
  if (event.metaKey || event.ctrlKey || event.altKey) return "";
  if (event.key === "Enter" || event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "PageDown" || event.key === " ") return "next";
  if (event.key === "ArrowLeft" || event.key === "ArrowUp" || event.key === "PageUp") return "prev";
  if (event.key === "Home") return "first";
  if (event.key === "End") return "last";
  return "";
}

function normalizePresenterPayload(payload) {
  const slides = Array.isArray(payload?.slides) ? payload.slides : [];
  return {
    snapshotId: payload?.snapshotId || "",
    messageId: payload?.messageId || "",
    serviceId: payload?.serviceId || null,
    serviceType: payload?.serviceType || "",
    serviceTitle: payload?.serviceTitle || "",
    serviceDate: payload?.serviceDate || payload?.service_date || "",
    chromakey: Boolean(payload?.chromakey),
    outputTheme: payload?.outputTheme || presenterOutputTheme(payload?.serviceType),
    backgroundImage: payload?.backgroundImage || "",
    backgroundImages: Array.isArray(payload?.backgroundImages)
      ? payload.backgroundImages.filter(Boolean)
      : [payload?.backgroundImage].filter(Boolean),
    slides,
    index: clampPresenterIndex(payload?.index, slides.length),
    slideAnchor: payload?.slideAnchor || presenterSlideAnchor(slides[clampPresenterIndex(payload?.index, slides.length)]),
    safetyBlank: Boolean(payload?.safetyBlank),
    liveScripture: normalizeLiveScripturePayload(payload?.liveScripture),
    livePraise: null,
    updatedAt: Number(payload?.updatedAt) || Date.now(),
  };
}

function normalizeLiveScripturePayload(value) {
  if (!value?.active || !value?.slide) return null;
  return {
    reference: value.reference || value.slide.title || "",
    active: true,
    slide: value.slide,
  };
}

function normalizeLivePraisePayload(value) {
  return null;
}

function applyPresenterActionToPayload(payload, action, options = {}) {
  const next = normalizePresenterPayload(payload);
  const requestedIndex = Number(options.index);
  const appliesJump = action !== "jump"
    || requestedIndex === -1
    || isValidPresenterIndex(requestedIndex, next.slides.length);
  if (["next", "prev", "first", "last", "jump"].includes(action) && appliesJump) {
    next.liveScripture = null;
  }
  if (action === "next" && next.slides.length) {
    next.safetyBlank = false;
    next.index = presenterNextNavigableIndex(next.slides, next.index, 1);
  } else if (action === "prev" && next.slides.length) {
    next.safetyBlank = false;
    next.index = presenterNextNavigableIndex(next.slides, next.index, -1);
  } else if (action === "first" && next.slides.length) {
    next.safetyBlank = false;
    next.index = presenterFirstNavigableIndex(next.slides);
  } else if (action === "last" && next.slides.length) {
    next.safetyBlank = false;
    next.index = presenterLastNavigableIndex(next.slides);
  } else if (action === "jump" && next.slides.length) {
    if (requestedIndex === -1) {
      next.safetyBlank = true;
    } else if (isValidPresenterIndex(requestedIndex, next.slides.length)) {
      next.index = requestedIndex;
      next.safetyBlank = false;
    }
  }
  next.slideAnchor = presenterSlideAnchor(next.slides[clampPresenterIndex(next.index, next.slides.length)]);
  next.updatedAt = Date.now();
  return next;
}

function presenterNextNavigableIndex(slides = [], currentIndex = 0, direction = 1) {
  const step = direction < 0 ? -1 : 1;
  let index = Number(currentIndex) + step;
  while (index >= 0 && index < slides.length && presenterSlideIsHidden(slides[index])) index += step;
  return index >= 0 && index < slides.length ? index : Number(currentIndex);
}

function presenterFirstNavigableIndex(slides = []) {
  const index = slides.findIndex((slide) => !presenterSlideIsHidden(slide));
  return index >= 0 ? index : 0;
}

function presenterLastNavigableIndex(slides = []) {
  for (let index = slides.length - 1; index >= 0; index -= 1) {
    if (!presenterSlideIsHidden(slides[index])) return index;
  }
  return Math.max(slides.length - 1, 0);
}

function renderPresenterOutput(payload, options = {}) {
  const root = document.getElementById("presenterOutputRoot");
  if (!root) return;
  applyPresenterOutputViewportScale(root);
  clearPresenterOutputAutoAdvanceTimer();
  const slides = Array.isArray(payload?.slides) ? payload.slides : [];
  const liveSlide = payload?.liveScripture?.active ? payload.liveScripture.slide : null;
  const slide = payload?.safetyBlank
    ? presenterSafetyBlankSlide()
    : liveSlide || slides[clampPresenterIndex(payload?.index, slides.length)];
  const frameState = presenterOutputFrameStateForSlide(slide, payload);
  const activeImageSource = presenterSlideImageSource(slide);
  preloadPresenterOutputImages(payload, slide);
  if (activeImageSource && !presenterOutputImageIsReady(activeImageSource)) {
    const token = ++presenterOutputRenderState.token;
    presenterOutputRenderState.pendingImageSource = activeImageSource;
    root.dataset.presenterPendingImageSource = activeImageSource;
    root.setAttribute("aria-busy", "true");
    presenterOutputLayers(root);
    const rerenderIfReady = () => {
      if (
        token === presenterOutputRenderState.token
        && root.dataset.presenterPendingImageSource === activeImageSource
        && presenterOutputImageIsReady(activeImageSource)
      ) {
        renderPresenterOutput(payload, options);
      }
    };
    preloadPresenterOutputImage(activeImageSource)?.finally(rerenderIfReady);
    nextAnimationFrame().then(rerenderIfReady);
    window.setTimeout(rerenderIfReady, 40);
    window.setTimeout(rerenderIfReady, 160);
    return;
  }

  const token = ++presenterOutputRenderState.token;
  presenterOutputRenderState.pendingImageSource = "";
  delete root.dataset.presenterPendingImageSource;
  root.removeAttribute("aria-busy");
  commitPresenterOutputFrame(root, payload, slide, frameState, token, options);
}

function presenterOutputFrameStateForSlide(slide, payload = {}) {
  const backgroundImages = presenterPayloadBackgroundImages(payload);
  const fallbackChromakey = Boolean(payload?.chromakey);
  const slideChromakey = presenterFrameSlideOutputContext(slide, fallbackChromakey) === "chromakey";
  const cleanOutput = !slideChromakey;
  const blankSlide = presenterSlideLayout(slide) === PRESENTER_SLIDE_LAYOUTS.BLANK;
  const scoreOutput = presenterSlideIsScoreLike(slide);
  const suppressBackground = Boolean(slide?.suppressBackgroundImage || slide?.noBackgroundImage);
  // A fullscreen blank stays inside the service visual system: retain the same
  // background while the cross draws over it. Chromakey remains background-free.
  const showBackground = Boolean(backgroundImages.length && cleanOutput && !suppressBackground);
  return {
    cleanOutput,
    showBackground,
    blankOutput: Boolean(blankSlide && cleanOutput),
    scoreOutput,
    backgroundImage: backgroundImages[0] || "",
    backgroundImages,
    serviceType: payload?.serviceType || "",
    outputTheme: payload?.outputTheme || presenterOutputTheme(payload?.serviceType),
    noChromakey: !slideChromakey,
  };
}

function presenterFrameSlideOutputContext(slide, fallbackChromakey = true) {
  const explicit = presenterFrameNormalizeOutputContext(
    slide?.outputContext
    || slide?.output_context
    || slide?.presenterOutputContext
    || slide?.presenter_output_context
    || "",
  );
  if (explicit) return explicit;
  const layout = presenterSlideLayout(slide);
  const elementType = presenterSlideElementType(slide);
  if (slide?.live && elementType === PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT) return "chromakey";
  if (layout === PRESENTER_SLIDE_LAYOUTS.BLANK) return fallbackChromakey ? "chromakey" : "clean";
  const scoreLike = slide?.sourceType === "score" || slide?.componentType === "score" || slide?.scoreBackground;
  if (scoreLike) return "clean";
  if (
    layout === PRESENTER_SLIDE_LAYOUTS.MEDIA
    || layout === PRESENTER_SLIDE_LAYOUTS.FILE
    || elementType === PRESENTER_ELEMENT_TYPES.IMAGE
    || elementType === PRESENTER_ELEMENT_TYPES.VIDEO
    || elementType === PRESENTER_ELEMENT_TYPES.FILE
    || elementType === PRESENTER_ELEMENT_TYPES.AUDIO
  ) {
    return "clean";
  }
  return fallbackChromakey ? "chromakey" : "clean";
}

function presenterFrameNormalizeOutputContext(value = "") {
  const key = compactSearchValue(value);
  if (!key) return "";
  if (["chromakey", "chroma", "key", "green", "greenkey", "크로마키"].includes(key)) return "chromakey";
  if (["clean", "fullscreen", "full", "media", "image", "video", "score", "nochromakey", "no-chromakey", "풀스크린", "전체화면"].includes(key)) return "clean";
  return "";
}

function presenterOutputFrameClassNames(frameState = {}) {
  return [
    frameState.noChromakey ? "no-chromakey" : "",
    frameState.showBackground ? "has-background" : "",
    frameState.blankOutput ? "is-blank" : "",
  ].filter(Boolean).join(" ");
}

function presenterOutputFrameBackgroundStyle(frameState = {}) {
  if (!frameState.showBackground) return "";
  const sources = frameState.backgroundImages?.length
    ? frameState.backgroundImages
    : [frameState.backgroundImage].filter(Boolean);
  if (!sources.length) return "";
  return ` style="--presenter-bg-image: ${escapeAttr(presenterBackgroundCssValue(sources))}"`;
}

function commitPresenterOutputFrame(root, payload, slide, frameState, token, options = {}) {
  const html = slide ? renderPresenterSlideFrame(slide, { noChromakey: frameState.noChromakey }) : "";
  const activeImageSource = presenterSlideImageSource(slide);
  const frameKey = presenterOutputFrameKey(payload, slide, frameState);
  const commit = () => {
    if (token !== presenterOutputRenderState.token) return;
    const layers = presenterOutputLayers(root);
    if (!layers) return;
    if (layers.active?.dataset?.presenterFrameKey === frameKey) {
      applyPresenterOutputFrameState(root, frameState);
      bindPresenterOutputAutoAdvance(root, payload, slide, options, token);
      warmPresenterOutputImages(payload, slide || null);
      return;
    }
    const nextLayer = layers.next;
    if (nextLayer.dataset.presenterFrameToken !== String(token)) {
      nextLayer.innerHTML = html;
      nextLayer.dataset.presenterFrameToken = String(token);
    }
    nextLayer.dataset.presenterFrameKey = frameKey;
    nextLayer.classList.add("is-next");
    activatePresenterOutputLayer(root, layers.active, nextLayer, frameState, token, () => {
      fitPresenterChromakeyScriptureText(nextLayer, frameState);
      fitPresenterSongTitleText(nextLayer);
      fitPresenterSermonTitleText(nextLayer);
      bindPresenterOutputAutoAdvance(root, payload, slide, options, token);
    });
    warmPresenterOutputImages(payload, slide || null);
  };
  if (!activeImageSource) {
    commit();
    return;
  }
  const commitToken = ++presenterOutputRenderState.commitToken;
  root.setAttribute("aria-busy", "true");
  const layers = presenterOutputLayers(root);
  if (!layers) {
    root.removeAttribute("aria-busy");
    return;
  }
  layers.next.innerHTML = html;
  layers.next.dataset.presenterFrameToken = String(token);
  layers.next.dataset.presenterFrameKey = frameKey;
  layers.next.classList.add("is-next");
  preparePresenterOutputFrameForPaint(layers.next)
    .finally(() => {
      if (token !== presenterOutputRenderState.token || commitToken !== presenterOutputRenderState.commitToken) return;
      root.removeAttribute("aria-busy");
      commit();
    });
}

function activatePresenterOutputLayer(root, activeLayer, nextLayer, frameState = {}, token = presenterOutputRenderState.token, onActivated = null) {
  if (!activeLayer || !nextLayer) return;
  const animated = presenterOutputShouldAnimateFrameTransition(root, frameState);
  const transitionClearDelay = 260;
  const transitionEntryDelay = 220;
  const swap = () => {
    if (token !== presenterOutputRenderState.token) return;
    activeLayer.classList.remove("is-entering");
    activeLayer.removeAttribute("data-presenter-entering-token");
    nextLayer.classList.remove("is-entering");
    nextLayer.classList.remove("is-exiting");
    nextLayer.removeAttribute("data-presenter-entering-token");
    if (animated) activeLayer.classList.add("is-exiting");
    activeLayer.classList.remove("is-active");
    activeLayer.classList.remove("is-next");
    nextLayer.classList.add("is-active");
    if (animated) nextLayer.classList.add("is-entering");
    nextLayer.classList.remove("is-next");
    // Keep composited media layers attached while swapping their visibility.
    applyPresenterOutputFrameState(root, frameState);
    if (animated) {
      nextLayer.dataset.presenterEnteringToken = String(token);
      window.setTimeout(() => {
        if (nextLayer.dataset.presenterEnteringToken !== String(token)) return;
        nextLayer.classList.remove("is-entering");
        nextLayer.removeAttribute("data-presenter-entering-token");
      }, transitionEntryDelay);
    }
    onActivated?.();
    const clearPreviousLayer = () => {
      if (token !== presenterOutputRenderState.token) return;
      if (activeLayer.classList.contains("is-active")) return;
      activeLayer.innerHTML = "";
      activeLayer.removeAttribute("data-presenter-frame-token");
      activeLayer.removeAttribute("data-presenter-frame-key");
      activeLayer.removeAttribute("data-presenter-entering-token");
      activeLayer.classList.remove("is-exiting");
      activeLayer.classList.remove("is-entering");
    };
    if (animated) window.setTimeout(clearPreviousLayer, transitionClearDelay);
    else clearPreviousLayer();
  };
  if (!animated) {
    swap();
    return;
  }
  nextLayer.getBoundingClientRect();
  swap();
}

function presenterOutputFrameKey(payload = {}, slide = null, frameState = {}) {
  if (!slide) return "empty";
  return [
    payload?.serviceId || "",
    payload?.index ?? "",
    slide.id || "",
    slide.type || "",
    slide.layout || "",
    slide.elementType || "",
    slide.outputContext || slide.output_context || "",
    frameState.noChromakey ? "clean" : "chromakey",
    frameState.blankOutput ? "blank" : "",
    frameState.backgroundImage || "",
    slide.title || "",
    slide.text || "",
  ].map((value) => String(value ?? "")).join("|");
}

function presenterOutputShouldAnimateFrameTransition(root, frameState = {}) {
  if (!frameState.cleanOutput) return false;
  if (frameState.scoreOutput) return false;
  if (root?.classList?.contains("svc-slide-mini-canvas")) return false;
  if (root?.querySelector?.(":scope > .presenter-output-layer.is-active .presenter-slide--score")) return false;
  if (root?.querySelector?.(":scope > .presenter-output-layer.is-next .presenter-slide--score")) return false;
  // Fullscreen output shares the same physical surface across clean slides.
  // Cross-fading exposes the stage background between layers, so swap directly.
  return false;
}

function fitPresenterChromakeyScriptureText(host, frameState = {}) {
  if (!host || frameState.noChromakey) return;
  const textBox = host.querySelector(
    ".presenter-slide--scripture:not(.presenter-slide--scripture-reading) > .presenter-slide-text",
  );
  if (!textBox) return;

  textBox.style.removeProperty("--presenter-scripture-fitted-size");
  const baseSize = Number.parseFloat(window.getComputedStyle(textBox).fontSize);
  if (!Number.isFinite(baseSize) || baseSize <= 0) return;

  const preview = host.classList?.contains("svc-slide-mini-canvas");
  const minimumSize = Math.min(preview ? 28 : 32, baseSize);
  for (let size = Math.round(baseSize); size >= minimumSize; size -= 1) {
    textBox.style.setProperty("--presenter-scripture-fitted-size", `${size}px`);
    if (
      textBox.scrollHeight <= textBox.clientHeight + 1
      && textBox.scrollWidth <= textBox.clientWidth + 1
    ) return;
  }
}

function presenterTextNaturalWidthFits(container, targetWidth) {
  const limit = Number(targetWidth);
  if (!container?.querySelectorAll || !Number.isFinite(limit) || limit <= 0) return true;
  const nodes = [...container.querySelectorAll("span")];
  const targets = nodes.length ? nodes : [container];
  return targets.every((node) => presenterTextNaturalWidth(node) <= limit + 1);
}

function presenterTextNaturalWidth(node) {
  if (!node) return 0;
  const previous = {
    display: node.style.display,
    maxWidth: node.style.maxWidth,
    position: node.style.position,
    visibility: node.style.visibility,
    whiteSpace: node.style.whiteSpace,
    width: node.style.width,
  };
  node.style.display = "inline-block";
  node.style.maxWidth = "none";
  node.style.position = "absolute";
  node.style.visibility = "hidden";
  node.style.whiteSpace = "nowrap";
  node.style.width = "max-content";
  const width = node.scrollWidth || node.getBoundingClientRect?.().width || 0;
  node.style.display = previous.display;
  node.style.maxWidth = previous.maxWidth;
  node.style.position = previous.position;
  node.style.visibility = previous.visibility;
  node.style.whiteSpace = previous.whiteSpace;
  node.style.width = previous.width;
  return width;
}

function fitPresenterChromakeyScripturePreviews(host) {
  if (!host) return;
  host
    .querySelectorAll(".svc-slide-mini-canvas.presenter-output-root:not(.no-chromakey)")
    .forEach((preview) => fitPresenterChromakeyScriptureText(preview));
}

function fitPresenterSongTitleText(host) {
  if (!host) return;
  fitPresenterLyricText(host);
  const outputRoot = host.closest?.(".presenter-output-root") || host;
  const fullscreen = outputRoot.classList?.contains("no-chromakey");
  const minimumSize = fullscreen ? 72 : 56;
  host
    .querySelectorAll(".presenter-slide--song-title > .presenter-slide-text, .presenter-slide--song-title .presenter-section-song-title-name")
    .forEach((textBox) => {
      textBox.style.removeProperty("font-size");
      const baseSize = Number.parseFloat(window.getComputedStyle(textBox).fontSize);
      if (!Number.isFinite(baseSize) || baseSize <= 0) return;

      const floor = Math.min(minimumSize, baseSize);
      for (let size = baseSize; size >= floor; size -= 2) {
        textBox.style.fontSize = `${size}px`;
        if (textBox.scrollWidth <= textBox.clientWidth + 1) return;
      }
    });
}

const presenterLyricFitCache = new Map();
const PRESENTER_LYRIC_FIT_CACHE_LIMIT = 512;
const PRESENTER_LYRIC_FIT_STYLE_KEYS = [
  "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontStretch", "fontVariant",
  "fontFeatureSettings", "fontVariationSettings", "fontKerning", "fontOpticalSizing",
  "letterSpacing", "wordSpacing", "lineHeight", "whiteSpace", "textTransform", "textIndent",
  "writingMode", "direction", "boxSizing", "paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
  "marginLeft", "marginRight", "gap", "display", "content", "verticalAlign", "transform",
];

function presenterLyricFitKey(textBox) {
  const metrics = (node, pseudo) => {
    const style = getComputedStyle(node, pseudo);
    return PRESENTER_LYRIC_FIT_STYLE_KEYS.map((key) => style[key]);
  };
  return JSON.stringify([
    textBox.innerHTML, textBox.clientWidth, textBox.clientHeight, metrics(textBox),
    [...textBox.querySelectorAll("*")].map((node) => [metrics(node), metrics(node, "::before"), metrics(node, "::after")]),
  ]);
}

function rememberPresenterLyricFit(key, fontSize) {
  if (presenterLyricFitCache.size >= PRESENTER_LYRIC_FIT_CACHE_LIMIT) {
    presenterLyricFitCache.delete(presenterLyricFitCache.keys().next().value);
  }
  presenterLyricFitCache.set(key, fontSize);
}

// Font metrics may change without a resize, including after an initial fallback-font fit.
document.fonts?.addEventListener("loadingdone", () => {
  presenterLyricFitCache.clear();
  window.requestAnimationFrame(() => fitPresenterLyricText(document));
});
document.fonts?.addEventListener("loadingerror", () => {
  presenterLyricFitCache.clear();
  window.requestAnimationFrame(() => fitPresenterLyricText(document));
});

function fitPresenterLyricText(host) {
  host.querySelectorAll('.presenter-slide--lyrics[data-element-type="praise"] > .presenter-slide-text').forEach((textBox) => {
    textBox.style.removeProperty("font-size");
    const baseSize = Number.parseFloat(getComputedStyle(textBox).fontSize);
    if (!Number.isFinite(baseSize) || baseSize <= 0 || !textBox.clientWidth) return;
    // Read the unfitted CSS size first so theme, viewport and typography changes invalidate the key.
    const key = document.fonts?.status === "loading" ? null : presenterLyricFitKey(textBox);
    if (key !== null && presenterLyricFitCache.has(key)) {
      const size = presenterLyricFitCache.get(key);
      if (size) textBox.style.fontSize = size;
      return;
    }
    const fits = () => {
      const style = getComputedStyle(textBox);
      const width = textBox.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      return [...textBox.children].every((line) => presenterTextNaturalWidth(line) <= width - 2)
        && textBox.scrollHeight <= textBox.clientHeight + 1;
    };
    if (fits()) {
      if (key !== null) rememberPresenterLyricFit(key, "");
      return;
    }
    // Measure complete lines, including generated verse numbers, before revealing the frame.
    let low = 0;
    let high = baseSize;
    for (let step = 0; step < 14; step += 1) {
      const size = (low + high) / 2;
      textBox.style.fontSize = `${size}px`;
      if (fits()) low = size;
      else high = size;
    }
    textBox.style.fontSize = `${low}px`;
    if (key !== null) rememberPresenterLyricFit(key, textBox.style.fontSize);
  });
}

function fitPresenterSongTitlePreviews(host) {
  if (!host) return;
  host
    .querySelectorAll(".svc-slide-mini-canvas.presenter-output-root")
    .forEach((preview) => fitPresenterSongTitleText(preview));
}

function fitPresenterSermonTitleText(host) {
  if (!host) return;
  const outputRoot = host.closest?.(".presenter-output-root") || host;
  const fullscreen = outputRoot.classList?.contains("no-chromakey");
  const minimumSize = fullscreen ? 72 : 56;
  host
    .querySelectorAll(".presenter-title-assignee--sermon .presenter-title-assignee-content, .presenter-title-content-title")
    .forEach((textBox) => {
      textBox.style.removeProperty("font-size");
      const baseSize = Number.parseFloat(window.getComputedStyle(textBox).fontSize);
      if (!Number.isFinite(baseSize) || baseSize <= 0) return;

      const songTitle = textBox.closest('.presenter-slide--fullscreen-song-title');
      const floor = Math.min(songTitle ? 48 * (outputRoot.clientWidth || 1920) / 1920 : minimumSize, baseSize);
      for (let size = baseSize; size >= floor; size -= 2) {
        textBox.style.fontSize = `${size}px`;
        if (textBox.scrollWidth <= textBox.clientWidth + 1) return;
      }
    });
}

function fitPresenterSermonTitlePreviews(host) {
  if (!host) return;
  host
    .querySelectorAll(".svc-slide-mini-canvas.presenter-output-root")
    .forEach((preview) => fitPresenterSermonTitleText(preview));
}

function bindPresenterOutputAutoAdvance(root, payload, slide, options = {}, token = presenterOutputRenderState.token) {
  clearPresenterOutputAutoAdvanceTimer();
  bindPresenterVideoTimelineCatchUp(root, payload, slide, options, token);
  bindPresenterOutputAutoAdvanceOnEnd(root, payload, slide, options);
  bindPresenterOutputAutoAdvanceAt(payload, slide, options, token);
}

function bindPresenterVideoTimelineCatchUp(root, payload, slide, options = {}, token = presenterOutputRenderState.token) {
  if (!slide || presenterSlideElementType(slide) !== PRESENTER_ELEMENT_TYPES.VIDEO) return;
  if (presenterSlideLayout(slide) !== PRESENTER_SLIDE_LAYOUTS.MEDIA) return;
  const video = root?.querySelector(".presenter-output-layer.is-active video.presenter-video");
  if (!video) return;
  const onAutoAdvance = typeof options.onAutoAdvance === "function" ? options.onAutoAdvance : null;
  const applyCatchUp = () => {
    if (token !== presenterOutputRenderState.token) return;
    const duration = Number.isFinite(video.duration) && video.duration > 0
      ? video.duration
      : Number(slide.playback?.durationSeconds || 0);
    const catchUp = presenterVideoTimelineCatchUp(slide, payload, {
      now: Date.now(),
      durationSeconds: duration,
    });
    if (!catchUp) return;
    if (catchUp.shouldAdvance) {
      if (!onAutoAdvance) return;
      onAutoAdvance({
        serviceId: payload?.serviceId || "",
        slideId: slide?.id || "",
        slideIndex: clampPresenterIndex(payload?.index, Array.isArray(payload?.slides) ? payload.slides.length : 0),
        scheduledAt: catchUp.endAt?.toISOString?.() || "",
        catchUp: true,
      });
      return;
    }
    if (Number.isFinite(catchUp.offsetSeconds) && catchUp.offsetSeconds > 0) {
      try {
        video.currentTime = catchUp.offsetSeconds;
      } catch {
        // Some browsers reject seeking until more metadata is available.
      }
    }
  };
  if (Number.isFinite(video.duration) && video.duration > 0) {
    applyCatchUp();
    return;
  }
  video.addEventListener("loadedmetadata", applyCatchUp, { once: true });
}

function bindPresenterOutputAutoAdvanceOnEnd(root, payload, slide, options = {}) {
  if (!presenterSlideShouldAutoAdvanceOnEnd(slide)) return;
  const video = root?.querySelector(".presenter-output-layer.is-active video.presenter-video");
  const onAutoAdvance = typeof options.onAutoAdvance === "function" ? options.onAutoAdvance : null;
  if (!video || !onAutoAdvance) return;
  const serviceId = payload?.serviceId || "";
  const slideId = slide?.id || "";
  const slideIndex = clampPresenterIndex(payload?.index, Array.isArray(payload?.slides) ? payload.slides.length : 0);
  video.onended = () => onAutoAdvance({ serviceId, slideId, slideIndex });
}

function bindPresenterOutputAutoAdvanceAt(payload, slide, options = {}, token = presenterOutputRenderState.token) {
  const onAutoAdvance = typeof options.onAutoAdvance === "function" ? options.onAutoAdvance : null;
  if (!onAutoAdvance) return;
  const target = presenterSlideAutoAdvanceAt(slide, payload);
  if (!target) return;
  const delay = Math.max(0, target.getTime() - Date.now());
  const serviceId = payload?.serviceId || "";
  const slideId = slide?.id || "";
  const slideIndex = clampPresenterIndex(payload?.index, Array.isArray(payload?.slides) ? payload.slides.length : 0);
  presenterOutputRenderState.autoAdvanceTimer = window.setTimeout(() => {
    if (token !== presenterOutputRenderState.token) return;
    onAutoAdvance({ serviceId, slideId, slideIndex, scheduledAt: target.toISOString() });
  }, delay);
}

function clearPresenterOutputAutoAdvanceTimer() {
  if (!presenterOutputRenderState.autoAdvanceTimer) return;
  window.clearTimeout(presenterOutputRenderState.autoAdvanceTimer);
  presenterOutputRenderState.autoAdvanceTimer = null;
}

function presenterSlideShouldAutoAdvanceOnEnd(slide) {
  if (!slide || presenterSlideElementType(slide) !== PRESENTER_ELEMENT_TYPES.VIDEO) return false;
  if (presenterSlideLayout(slide) !== PRESENTER_SLIDE_LAYOUTS.MEDIA) return false;
  if (slide.live) return false;
  const presenterRole = normalizeServicePresenterRole(slide.presenterRole);
  if (presenterRole !== "intro") return false;
  const playback = presenterPlaybackConfig(slide.playback, "intro-video");
  return playback.autoAdvanceOnEnd !== false && playback.loop !== true;
}

function presenterSlideAutoAdvanceAt(slide, payload = {}) {
  if (!slide || slide.live) return null;
  const raw = String(slide.playback?.autoAdvanceAt || "").trim();
  if (!raw) return null;
  const target = parsePresenterAutoAdvanceAt(raw, payload?.serviceDate);
  if (!target || Number.isNaN(target.getTime())) return null;
  return target;
}

function presenterVideoTimelineCatchUp(slide, payload = {}, options = {}) {
  if (!slide || slide.live) return null;
  const startAt = presenterSlideTimelineStartAt(slide, payload);
  if (!startAt) return null;
  const now = Number(options.now) || Date.now();
  const elapsedSeconds = (now - startAt.getTime()) / 1000;
  if (!Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) return null;
  const durationSeconds = Number(options.durationSeconds) || Number(slide.playback?.durationSeconds || 0);
  const endAt = durationSeconds > 0 ? new Date(startAt.getTime() + (durationSeconds * 1000)) : presenterSlideAutoAdvanceAt(slide, payload);
  const shouldAdvance = Boolean(durationSeconds > 0 && elapsedSeconds >= durationSeconds && presenterSlideShouldAutoAdvanceOnEnd(slide));
  return {
    startAt,
    endAt,
    elapsedSeconds,
    offsetSeconds: durationSeconds > 0 ? Math.min(elapsedSeconds, Math.max(durationSeconds - 0.25, 0)) : elapsedSeconds,
    shouldAdvance,
  };
}

function presenterSlideTimelineStartAt(slide, payload = {}) {
  if (!slide) return null;
  const explicitStart = parsePresenterAutoAdvanceAt(slide.playback?.startAt, payload?.serviceDate);
  if (explicitStart) return explicitStart;
  const slides = Array.isArray(payload?.slides) ? payload.slides : [];
  const index = clampPresenterIndex(payload?.index, slides.length);
  const previous = slides[index - 1];
  const previousAdvanceAt = presenterSlideAutoAdvanceAt(previous, payload);
  if (previousAdvanceAt) return previousAdvanceAt;
  const ownAdvanceAt = presenterSlideAutoAdvanceAt(slide, payload);
  const durationSeconds = Number(slide.playback?.durationSeconds || 0);
  if (ownAdvanceAt && durationSeconds > 0) {
    return new Date(ownAdvanceAt.getTime() - (durationSeconds * 1000));
  }
  return null;
}

function parsePresenterAutoAdvanceAt(value, serviceDate = "") {
  const raw = String(value || "").trim();
  if (!raw) return null;
  if (/^\d{1,2}:\d{2}(?::\d{2})?$/.test(raw)) {
    const date = String(serviceDate || toLocalDateStr(new Date())).trim() || toLocalDateStr(new Date());
    return new Date(`${date}T${raw.length === 5 ? `${raw}:00` : raw}`);
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function presenterOutputLayers(root) {
  if (!root) return null;
  let layers = [...root.querySelectorAll(":scope > .presenter-output-layer")];
  if (layers.length < 2) {
    const existing = [...root.childNodes];
    root.textContent = "";
    const first = document.createElement("div");
    const second = document.createElement("div");
    first.className = "presenter-output-layer is-active";
    second.className = "presenter-output-layer";
    existing.forEach((node) => first.appendChild(node));
    root.append(first, second);
    layers = [first, second];
  }
  const active = layers.find((layer) => layer.classList.contains("is-active")) || layers[0];
  const next = layers.find((layer) => layer !== active) || layers[1];
  return { active, next };
}

function applyPresenterOutputFrameState(root, frameState = {}) {
  document.body.classList.toggle("presenter-output-body--clean", Boolean(frameState.cleanOutput));
  document.body.classList.toggle("has-background", Boolean(frameState.showBackground));
  document.body.classList.toggle("is-blank", Boolean(frameState.blankOutput));
  root.classList.toggle("no-chromakey", Boolean(frameState.noChromakey));
  root.classList.toggle("has-background", Boolean(frameState.showBackground));
  root.classList.toggle("is-blank", Boolean(frameState.blankOutput));
  root.dataset.serviceType = frameState.serviceType || "";
  root.dataset.outputTheme = frameState.outputTheme || presenterOutputTheme(frameState.serviceType);
  if (frameState.showBackground) {
    const backgroundCssValue = presenterBackgroundCssValue(frameState.backgroundImages?.length ? frameState.backgroundImages : [frameState.backgroundImage]);
    document.body.style.setProperty("--presenter-bg-image", backgroundCssValue);
    root.style.setProperty("--presenter-bg-image", backgroundCssValue);
  } else {
    document.body.style.removeProperty("--presenter-bg-image");
    root.style.removeProperty("--presenter-bg-image");
  }
}

function presenterPayloadBackgroundImages(payload = {}) {
  if (Array.isArray(payload?.backgroundImages) && payload.backgroundImages.length) {
    return payload.backgroundImages.filter(Boolean);
  }
  return [payload?.backgroundImage].filter(Boolean);
}

function preparePresenterOutputFrameForPaint(host) {
  if (!host) return Promise.resolve();
  const images = [...host.querySelectorAll("img")];
  const imageReady = images.map((image) => {
    if (presenterOutputImageIsReady(image.currentSrc || image.src)) return Promise.resolve();
    if (image.complete && image.naturalWidth > 0) return Promise.resolve();
    if (typeof image.decode === "function") return image.decode().catch(() => {});
    return new Promise((resolve) => {
      image.onload = resolve;
      image.onerror = resolve;
    });
  });
  const videos = [...host.querySelectorAll("video.presenter-video")];
  const videoReady = videos.map(preparePresenterOutputVideoForPaint);
  return Promise.all([...imageReady, ...videoReady]);
}

function presenterOutputVideoHealth(payload) {
  const layer = document.querySelector("#presenterOutputRoot .presenter-output-layer.is-active");
  const video = layer?.querySelector("video.presenter-video");
  if (!video || !payload?.serviceId) return null;
  const status = video.error ? "error" : video.ended ? "ended"
    : video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA ? "loading"
      : video.paused ? "paused" : "playing";
  return { serviceId: payload.serviceId, index: payload.index,
    frameKey: layer.dataset.presenterFrameKey || "", status };
}

async function retryPresenterOutputVideo(request, payload) {
  const health = presenterOutputVideoHealth(payload);
  if (!health || health.serviceId !== request.serviceId || health.index !== request.index
    || health.frameKey !== request.frameKey || !["error", "paused"].includes(health.status)) return;
  const video = document.querySelector("#presenterOutputRoot .presenter-output-layer.is-active video.presenter-video");
  // Reload only failed media. Resuming a paused video must preserve its position.
  if (health.status === "error") video.load();
  try { await video.play(); } catch {
    // Autoplay policy may still require a gesture in the output window.
    // Expose native controls only after this explicit recovery attempt.
    if (video.isConnected) video.controls = true;
  }
}

function requestPresenterVideoRetry(serviceId) {
  const health = state.presenter.videoHealth;
  if (!health || health.serviceId !== serviceId || serviceId !== state.presenter.serviceId
    || health.index !== state.presenter.index || state.presenter.safetyBlank || state.presenter.liveScripture?.active
    || Date.now() - health.receivedAt > 5000 || !["error", "paused"].includes(health.status)) return;
  const message = { type: "presenter-video-retry", serviceId, index: health.index,
    clientId: health.clientId, frameKey: health.frameKey,
    requestId: `${Date.now()}:${Math.random()}` };
  safeStorageSet("local", PRESENTER_SIGNAL_KEY, JSON.stringify(message));
  try { state.presenter.channel?.postMessage(message); } catch { /* Storage delivers the request. */ }
}

function preparePresenterOutputVideoForPaint(video) {
  if (!video) return Promise.resolve();
  const readyForPaint = () => video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
  const ensureInlineMutedAutoplay = () => {
    if (!video.autoplay) return;
    if (!video.muted && !video.defaultMuted && !video.hasAttribute("muted")) return;
    video.defaultMuted = true;
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
  };
  const requestPlayback = () => {
    if (!video.autoplay) return;
    ensureInlineMutedAutoplay();
    const playPromise = video.play?.();
    if (playPromise?.catch) playPromise.catch(() => {});
  };
  ensureInlineMutedAutoplay();
  requestPlayback();
  if (readyForPaint()) return Promise.resolve();
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      cleanup();
      requestPlayback();
      resolve();
    };
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("loadeddata", finish);
      video.removeEventListener("canplay", finish);
      video.removeEventListener("playing", finish);
      video.removeEventListener("error", finish);
    };
    const timeout = window.setTimeout(finish, 1500);
    video.addEventListener("loadeddata", finish, { once: true });
    video.addEventListener("canplay", finish, { once: true });
    video.addEventListener("playing", finish, { once: true });
    video.addEventListener("error", finish, { once: true });
    if (video.networkState === HTMLMediaElement.NETWORK_EMPTY) video.load?.();
  });
}

function nextAnimationFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function preloadPresenterOutputImages(payload = {}, activeSlide = null) {
  presenterOutputImageSourcesForPreload(payload, activeSlide).forEach(preloadPresenterOutputImage);
}

function presenterOutputImageSourcesForPreload(payload = {}, activeSlide = null) {
  const sources = [];
  const pushSlide = (slide) => {
    const source = presenterSlideImageSource(slide);
    if (source) sources.push(source);
  };
  pushSlide(activeSlide);

  let slideList = [];
  let activeIndex = 0;
  slideList = Array.isArray(payload?.slides) ? payload.slides : [];
  activeIndex = clampPresenterIndex(payload?.index, slideList.length);
  for (let offset = -PRESENTER_OUTPUT_IMAGE_PRELOAD_RADIUS; offset <= PRESENTER_OUTPUT_IMAGE_PRELOAD_RADIUS; offset += 1) {
    pushSlide(slideList[activeIndex + offset]);
  }
  presenterOutputScoreGroupSlidesForPreload(slideList, activeSlide, activeIndex).forEach(pushSlide);

  presenterPayloadBackgroundImages(payload).forEach((source) => {
    const backgroundImage = normalizePresenterMediaSource(source || "");
    if (backgroundImage && presenterMediaSourceIsImage(backgroundImage)) sources.push(backgroundImage);
  });
  return [...new Set(sources)];
}

function warmPresenterOutputImages(payload = {}, activeSlide = null) {
  const sources = presenterOutputWarmupSourcesForPayload(payload, activeSlide);
  const key = presenterOutputWarmupKey(payload, sources);
  if (!key || !sources.length) {
    cancelPresenterOutputImageWarmup();
    presenterOutputImageWarmupState.key = "";
    presenterOutputImageWarmupState.serviceId = "";
    presenterOutputImageWarmupState.sources = [];
    presenterOutputImageWarmupState.index = 0;
    return;
  }
  if (key === presenterOutputImageWarmupState.key) {
    schedulePresenterOutputImageWarmup();
    return;
  }

  cancelPresenterOutputImageWarmup();
  presenterOutputImageWarmupState.key = key;
  presenterOutputImageWarmupState.serviceId = payload?.serviceId || "";
  presenterOutputImageWarmupState.sources = sources;
  presenterOutputImageWarmupState.index = 0;

  const eagerCount = Math.min(PRESENTER_OUTPUT_WARMUP_EAGER_COUNT, sources.length);
  sources.slice(0, eagerCount).forEach((source) => preloadPresenterOutputImage(source));
  presenterOutputImageWarmupState.index = eagerCount;
  schedulePresenterOutputImageWarmup();
}

function presenterOutputWarmupSummary() {
  const sources = presenterOutputImageWarmupState.sources || [];
  const total = sources.length;
  const ready = sources.filter(presenterOutputImageIsReady).length;
  return {
    serviceId: presenterOutputImageWarmupState.serviceId || "",
    total,
    ready,
    queued: Math.max(0, total - presenterOutputImageWarmupState.index),
    complete: total > 0 && ready >= total,
  };
}

function presenterOutputWarmupSourcesForPayload(payload = {}, activeSlide = null) {
  const sources = [];
  const pushSource = (source) => {
    const normalized = normalizePresenterMediaSource(source);
    if (normalized && presenterMediaSourceIsImage(normalized)) sources.push(normalized);
  };
  const pushSlide = (slide) => pushSource(presenterSlideImageSource(slide));
  const serviceSlides = Array.isArray(payload?.slides) ? payload.slides : [];
  const serviceIndex = clampPresenterIndex(payload?.index, serviceSlides.length);

  pushSlide(activeSlide);
  if (payload?.liveScripture?.active) {
    pushSlide(payload.liveScripture.slide);
  }
  presenterSlidesByDistance(serviceSlides, serviceIndex).forEach(pushSlide);
  presenterPayloadBackgroundImages(payload).forEach(pushSource);
  return [...new Set(sources)].slice(0, PRESENTER_OUTPUT_IMAGE_PRELOAD_LIMIT);
}

function presenterSlidesByDistance(slides = [], activeIndex = 0) {
  if (!Array.isArray(slides) || !slides.length) return [];
  const safeIndex = clampPresenterIndex(activeIndex, slides.length);
  return slides
    .map((slide, index) => ({ slide, index, distance: Math.abs(index - safeIndex) }))
    .sort((a, b) => a.distance - b.distance || a.index - b.index)
    .map((item) => item.slide);
}

function presenterOutputWarmupKey(payload = {}, sources = []) {
  if (!Array.isArray(sources) || !sources.length) return "";
  const sourceSet = [...new Set(sources)].sort();
  return [
    payload?.serviceId || "no-service",
    payload?.serviceType || "",
    sourceSet.length,
    presenterHashString(sourceSet.join("\n")),
  ].join("|");
}

function presenterHashString(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  }
  return String(hash >>> 0);
}

function cancelPresenterOutputImageWarmup() {
  const handle = presenterOutputImageWarmupState.handle;
  if (!handle) return;
  if (handle.type === "idle" && typeof window.cancelIdleCallback === "function") {
    window.cancelIdleCallback(handle.id);
  } else {
    window.clearTimeout(handle.id);
  }
  presenterOutputImageWarmupState.handle = null;
}

function schedulePresenterOutputImageWarmup() {
  if (presenterOutputImageWarmupState.handle) return;
  if (presenterOutputImageWarmupState.index >= presenterOutputImageWarmupState.sources.length) return;
  const run = (deadline = null) => {
    presenterOutputImageWarmupState.handle = null;
    let count = 0;
    while (
      presenterOutputImageWarmupState.index < presenterOutputImageWarmupState.sources.length
      && count < PRESENTER_OUTPUT_WARMUP_BATCH_SIZE
      && (!deadline || count === 0 || deadline.timeRemaining?.() > 4)
    ) {
      const source = presenterOutputImageWarmupState.sources[presenterOutputImageWarmupState.index];
      presenterOutputImageWarmupState.index += 1;
      count += 1;
      preloadPresenterOutputImage(source, { priority: "low" });
    }
    presenterOutputImageWarmupState.onProgress?.();
    schedulePresenterOutputImageWarmup();
  };
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(run, { timeout: PRESENTER_OUTPUT_WARMUP_IDLE_TIMEOUT_MS });
    presenterOutputImageWarmupState.handle = { type: "idle", id };
  } else {
    const id = window.setTimeout(() => run(null), 50);
    presenterOutputImageWarmupState.handle = { type: "timeout", id };
  }
}

function presenterOutputScoreGroupSlidesForPreload(slides = [], activeSlide = null, activeIndex = 0) {
  if (!Array.isArray(slides) || !slides.length) return [];
  const nearbyStart = Math.max(0, activeIndex - PRESENTER_OUTPUT_IMAGE_PRELOAD_RADIUS);
  const nearbyEnd = Math.min(slides.length, activeIndex + PRESENTER_OUTPUT_IMAGE_PRELOAD_RADIUS + 1);
  const nearbySlides = slides.slice(nearbyStart, nearbyEnd);
  const scoreSlide = presenterSlideIsScoreImage(activeSlide)
    ? activeSlide
    : nearbySlides.find(presenterSlideIsScoreImage);
  const groupKey = presenterSlidePreloadGroupKey(scoreSlide);
  if (!groupKey) return [];
  return slides
    .filter((slide) => presenterSlideIsScoreImage(slide) && presenterSlidePreloadGroupKey(slide) === groupKey)
    .slice(0, PRESENTER_OUTPUT_SCORE_PRELOAD_LIMIT);
}

function presenterSlideIsScoreImage(slide) {
  return Boolean(
    slide
    && presenterSlideImageSource(slide)
    && presenterSlideIsScoreLike(slide),
  );
}

function presenterSlideIsScoreLike(slide) {
  return Boolean(slide?.sourceType === "score" || slide?.componentType === "score" || slide?.scoreBackground);
}

function presenterSlidePreloadGroupKey(slide) {
  return String(slide?.elementId || slide?.sectionId || slide?.asset?.name || slide?.title || "").trim();
}

function presenterSlideImageSource(slide) {
  if (!slide) return "";
  const layout = presenterSlideLayout(slide);
  const elementType = presenterSlideElementType(slide);
  if (layout !== PRESENTER_SLIDE_LAYOUTS.MEDIA || elementType !== PRESENTER_ELEMENT_TYPES.IMAGE) return "";
  const source = normalizePresenterMediaSource(slide.imageSrc || slide.asset?.url || slide.text);
  return source && presenterMediaSourceIsImage(source) ? source : "";
}

function preloadPresenterOutputImage(source, options = {}) {
  const normalized = normalizePresenterMediaSource(source);
  if (!normalized || !presenterMediaSourceIsImage(normalized)) return null;
  const cached = presenterOutputImagePreloadCache.get(normalized);
  if (cached) {
    if (cached.image?.complete && cached.image.naturalWidth > 0) cached.ready = true;
    cached.lastUsed = Date.now();
    return cached.promise;
  }
  const image = new Image();
  image.decoding = "async";
  image.loading = "eager";
  if ("fetchPriority" in image) image.fetchPriority = options.priority === "low" ? "low" : "high";
  image.src = normalized;
  const promise = typeof image.decode === "function"
    ? image.decode().catch(() => {})
    : new Promise((resolve) => {
      image.onload = resolve;
      image.onerror = resolve;
    });
  const record = { image, promise, lastUsed: Date.now(), ready: false };
  promise.finally(() => { record.ready = true; });
  presenterOutputImagePreloadCache.set(normalized, record);
  trimPresenterOutputImagePreloadCache();
  return promise;
}

function presenterOutputImageIsReady(source) {
  const normalized = normalizePresenterMediaSource(source);
  const cached = normalized ? presenterOutputImagePreloadCache.get(normalized) : null;
  if (!cached) return false;
  if (cached.ready) return true;
  if (cached.image?.complete && cached.image.naturalWidth > 0) {
    cached.ready = true;
    return true;
  }
  return false;
}

function trimPresenterOutputImagePreloadCache() {
  if (presenterOutputImagePreloadCache.size <= PRESENTER_OUTPUT_IMAGE_PRELOAD_LIMIT) return;
  [...presenterOutputImagePreloadCache.entries()]
    .sort((a, b) => a[1].lastUsed - b[1].lastUsed)
    .slice(0, presenterOutputImagePreloadCache.size - PRESENTER_OUTPUT_IMAGE_PRELOAD_LIMIT)
    .forEach(([source]) => presenterOutputImagePreloadCache.delete(source));
}

function renderPresenterSlideFrame(slide, options = {}) {
  if (options.noChromakey && (slide?.songTitle || (slide?.type === "song-title" && presenterSlideElementType(slide) === PRESENTER_ELEMENT_TYPES.PRAISE))) {
    const content = presenterSongTitleContent(slide);
    const title = formatPresenterSongTitleText(content.title);
    // Keep the order heading when adapting song titles for fullscreen output.
    slide = { ...slide, elementType: PRESENTER_ELEMENT_TYPES.TITLE_CONTENT,
      layout: PRESENTER_SLIDE_LAYOUTS.CENTER_TEXT, type: "title-content",
      title, text: title, songTitleContent: content, bodyText: "", assignee: "", fullscreenSongTitle: true };
  }
  const slideClass = presenterSlideRenderClass(slide);
  const extraClasses = presenterSlideExtraClasses(slide);
  const body = renderPresenterSlideBody(slide, options);
  const sectionKey = String(slide?.sectionKey || slide?.section_key || "").trim();
  const presenterRole = normalizeServicePresenterRole(slide?.presenterRole);
  const backgroundStyle = slide?.scriptureContext === "reading" && !slide?.suppressBackgroundImage && !slide?.noBackgroundImage
    ? ` style="--presenter-slide-bg-image: url('${escapeAttr(PRESENTER_SCRIPTURE_READING_BACKGROUND)}')"`
    : "";
  return `
    <section class="presenter-slide presenter-slide--${escapeAttr(slideClass)}${extraClasses ? ` ${escapeAttr(extraClasses)}` : ""}" data-element-type="${escapeAttr(presenterSlideElementType(slide))}" data-slide-layout="${escapeAttr(presenterSlideLayout(slide))}"${sectionKey ? ` data-section-key="${escapeAttr(sectionKey)}"` : ""}${presenterRole ? ` data-presenter-role="${escapeAttr(presenterRole)}"` : ""}${backgroundStyle}>
      ${renderPresenterSlideMeta(slide)}
      ${body}
    </section>
  `;
}

function presenterSlideExtraClasses(slide) {
  const classes = [];
  if (slide?.fullscreenSongTitle) classes.push("presenter-slide--fullscreen-song-title");
  const layout = presenterSlideLayout(slide);
  if (presenterSlideIsScoreLike(slide)) classes.push("presenter-slide--score");
  if (layout !== PRESENTER_SLIDE_LAYOUTS.BLANK && presenterScriptureContextUsesReadingForm(slide?.scriptureContext)) classes.push("presenter-slide--scripture-reading");
  if (layout !== PRESENTER_SLIDE_LAYOUTS.BLANK && slide?.scriptureContext === "sermon") classes.push("presenter-slide--scripture-sermon");
  if (layout !== PRESENTER_SLIDE_LAYOUTS.BLANK && slide?.scriptureContext === "citation") classes.push("presenter-slide--scripture-citation");
  if (layout !== PRESENTER_SLIDE_LAYOUTS.BLANK && presenterScriptureContextUsesAddressTab(slide?.scriptureContext)) classes.push("presenter-slide--citation-tab");
  return classes.join(" ");
}

function presenterSafetyBlankSlide() {
  return {
    id: "presenter:safety-blank",
    elementType: PRESENTER_ELEMENT_TYPES.BLANK,
    layout: PRESENTER_SLIDE_LAYOUTS.BLANK,
    type: "blank",
    title: "빈 화면",
    text: "",
  };
}

function renderPresenterSlideMeta(slide) {
  if (!presenterSlideHasMeta(slide)) return "";
  const marker = presenterVisibleMeta(slide);
  if (!marker) return "";
  return `<div class="presenter-slide-meta">${escapeHtml(marker)}</div>`;
}

function presenterVisibleMeta(slide) {
  const marker = [slide?.marker, slide?.label].filter(Boolean).join(" · ").trim();
  if (!marker) return "";
  if (presenterLabelDuplicatesSlideText(marker, slide)) return "";
  return marker;
}

function renderPresenterSlideBody(slide, options = {}) {
  const layout = presenterSlideLayout(slide);
  const elementType = presenterSlideElementType(slide);
  if (slide?.type === "ready" && options.noChromakey) return renderPresenterFullscreenReadySlide(slide);
  if (presenterSlideUsesGeneratedWaitingLoop(slide, options)) return renderPresenterGeneratedWaitingLoopSlide(slide);
  if (elementType === PRESENTER_ELEMENT_TYPES.AUDIO) return "";
  if (layout === PRESENTER_SLIDE_LAYOUTS.MEDIA && elementType === PRESENTER_ELEMENT_TYPES.VIDEO) {
    if (options.staticVideoPreview) return renderPresenterStaticVideoPreviewSlide(slide);
    return renderPresenterVideoSlide(slide, options);
  }
  if (layout === PRESENTER_SLIDE_LAYOUTS.MEDIA && elementType === PRESENTER_ELEMENT_TYPES.IMAGE) return renderPresenterImageSlide(slide, options);
  if (layout === PRESENTER_SLIDE_LAYOUTS.FILE) return renderPresenterFileSlide(slide);
  if (layout !== PRESENTER_SLIDE_LAYOUTS.BLANK && elementType === PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT && presenterScriptureContextUsesAddressTab(slide?.scriptureContext)) return renderPresenterCitationTabSlide(slide);
  if (elementType === PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT && presenterScriptureContextUsesReadingForm(slide?.scriptureContext)) return renderPresenterScriptureReadingSlide(slide);
  if (layout === PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT && elementType === PRESENTER_ELEMENT_TYPES.TITLE_ASSIGNEE) return renderPresenterTitleAssigneeSlide(slide);
  if (layout === PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT && slide?.type === "song-title" && slide.sectionHeading) return renderPresenterSectionSongTitleSlide(slide);
  if (layout === PRESENTER_SLIDE_LAYOUTS.BLANK) return "";
  if (slide?.type === "liturgical-body") return renderPresenterLiturgicalBodySlide(slide);
  if (presenterSlideIsTitleContent(slide)) return renderPresenterTitleContentSlide(slide, options);
  return `<div class="presenter-slide-text">${renderPresenterSlideText(slide)}</div>`;
}

function presenterSlideUsesGeneratedWaitingLoop(slide, options = {}) {
  if (options.noChromakey) return false;
  if (slide?.type !== "ready") return false;
  if (normalizeServicePresenterRole(slide.presenterRole) !== "waiting_loop") return false;
  if (normalizePresenterMediaSource(slide.videoSrc || slide.imageSrc || slide.text)) return false;
  return presenterSlideOutputContext(slide, true) === "chromakey";
}

function renderPresenterGeneratedWaitingLoopSlide(slide) {
  const serviceName = presenterReadySlideServiceName(slide);
  return `
    <div class="presenter-waiting-loop" aria-label="${escapeAttr(`${serviceName} 대기 영상`)}">
      <div class="presenter-waiting-loop-field" aria-hidden="true"></div>
      <div class="presenter-waiting-loop-cross" aria-hidden="true"></div>
      <div class="presenter-waiting-loop-copy">
        <p class="presenter-waiting-loop-script">지금은 기도로 예배를 준비하는 시간입니다</p>
        <p class="presenter-waiting-loop-title">잠시 후 <strong>${escapeHtml(serviceName)}</strong>가 시작됩니다</p>
      </div>
      <img class="presenter-waiting-loop-logo" src="${escapeAttr(PRESENTER_CHURCH_LOGO)}" alt="기형 검단우리교회" decoding="sync" loading="eager" fetchpriority="high" draggable="false" />
    </div>
  `;
}

function presenterReadySlideServiceName(slide) {
  return String(slide?.readyServiceName || "").trim()
    || String(slide?.text || "").split("\n").map((line) => line.trim()).filter(Boolean)[1]
    || "예배";
}

function renderPresenterFullscreenReadySlide(slide) {
  const serviceName = presenterReadySlideServiceName(slide);
  return `
    <div class="presenter-ready-screen">
      <div class="presenter-ready-screen-field" aria-hidden="true"></div>
      <div class="presenter-ready-screen-copy">
        <p class="presenter-ready-screen-kicker">지금은 기도로 예배를 준비하는 시간입니다</p>
        <p class="presenter-ready-screen-message">잠시 후 <strong>${escapeHtml(serviceName)}</strong>가 시작됩니다</p>
      </div>
      <img class="presenter-ready-screen-logo" src="${escapeAttr(PRESENTER_CHURCH_LOGO)}" alt="기형 검단우리교회" decoding="sync" loading="eager" fetchpriority="high" draggable="false" />
    </div>
  `;
}

function renderPresenterCitationTabSlide(slide) {
  const raw = String(slide?.text || "");
  const number = presenterScriptureVerseParts(raw).number || presenterScriptureVerseNumber({
    number: slide?.scriptureVerse, verseEnd: slide?.scriptureVerseEnd,
  });
  const reference = presenterScriptureReadingHeaderReference(slide, number);
  // Older slide snapshots store the reference and body separated by whitespace.
  const body = slide?.citationBodyText ?? raw.replace(/^.*?\s{2,}/, "");
  return `<div class="presenter-citation-tab">${escapeHtml(reference)}</div>
    <div class="presenter-slide-text"><span>${escapeHtml(body)}</span></div>`;
}

function renderPresenterScriptureReadingSlide(slide) {
  const reference = String(slide?.title || slide?.marker || "").trim();
  const translationLabel = String(slide?.translationLabel || "").trim();
  const { number, text } = presenterScriptureVerseParts(slide?.text || "");
  const headerReference = presenterScriptureReadingHeaderReference(slide, number) || reference;
  const referenceChars = presenterLineCharEstimate(headerReference || "본문");
  const translationChars = presenterLineCharEstimate(translationLabel || "역본");
  const verseChars = presenterLineCharEstimate(text || slide?.text || "");
  return `
    <div class="presenter-scripture-reading">
      <div class="presenter-scripture-reading-head">
        <div class="presenter-scripture-reading-ref" style="--line-chars: ${escapeAttr(referenceChars)}">${escapeHtml(headerReference || "본문")}</div>
        ${translationLabel ? `<div class="presenter-scripture-reading-version" style="--line-chars: ${escapeAttr(translationChars)}">${escapeHtml(translationLabel)}</div>` : ""}
      </div>
      <div class="presenter-scripture-reading-line">
        <span class="presenter-scripture-reading-text" style="--line-chars: ${escapeAttr(verseChars)}">${escapePresenterSlideLine(text || slide?.text || " ", slide)}</span>
      </div>
      ${slide?.scriptureContext === "reading" && slide?.scriptureReadingFinal ? `<div class="presenter-scripture-reading-fin">Fin.</div>` : ""}
    </div>`;
}

function presenterScriptureReadingHeaderReference(slide = {}, verseNumber = "") {
  const referenceBook = presenterScriptureReadingBookName(slide?.referenceBook);
  const referenceRange = String(slide?.referenceRange || "").trim();
  const chapter = referenceRange.match(/^(\d+)/)?.[1] || "";
  const verse = String(verseNumber || "").trim();
  const chapterReference = [referenceBook, chapter && verse ? `${chapter}:${verse}` : chapter ? `${chapter}장` : referenceRange].filter(Boolean).join(" ").trim();
  const fallback = String(slide?.title || slide?.marker || "").trim();
  return chapterReference || presenterScriptureReadingDisplayReference(fallback);
}

function presenterScriptureReadingBookName(value = "") {
  const referenceBook = String(value || "").trim();
  if (!referenceBook || typeof findBibleBookByReferenceName !== "function") return referenceBook;
  return String(findBibleBookByReferenceName(referenceBook)?.koreanName || referenceBook).trim();
}

function presenterScriptureVerseParts(value = "") {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{1,3}(?:[–-]\d{1,3})?)\s{2,}(.+)$/);
  if (!match) return { number: "", text };
  return { number: match[1], text: match[2].trim() };
}

function renderPresenterVideoSlide(slide, options = {}) {
  const source = normalizePresenterMediaSource(slide.videoSrc || slide.text);
  if (!source) return "";
  const presenterRole = normalizeServicePresenterRole(slide.presenterRole);
  const playbackType = presenterRole === "intro"
    ? "intro-video"
    : (presenterRole === "ready" || presenterRole === "waiting_loop" || slide.type === "ready")
      ? "ready-video"
      : "video";
  const playback = presenterPlaybackConfig(slide.playback, playbackType);
  const previewStage = Boolean(options.previewStage);
  const videoSource = previewStage ? presenterPreviewVideoSource(source) : source;
  const attrs = [
    "class=\"presenter-video\"",
    `src="${escapeAttr(videoSource)}"`,
    presenterRole ? `data-presenter-role="${escapeAttr(presenterRole)}"` : "",
    (!previewStage && playback.autoplay) ? "autoplay" : "",
    (previewStage || playback.muted) ? "muted" : "",
    (previewStage || playback.muted) ? "defaultMuted" : "",
    (!previewStage && playback.loop) ? "loop" : "",
    (!previewStage && playback.controls) ? "controls" : "",
    (options.noChromakey || previewStage) ? "" : `poster="${PRESENTER_CHROMAKEY_VIDEO_POSTER}"`,
    "playsinline",
    "webkit-playsinline",
    `preload=\"${previewStage ? "metadata" : "auto"}\"`,
  ].filter(Boolean).join(" ");
  return `
    <video ${attrs}></video>
  `;
}

function presenterPreviewVideoSource(source = "") {
  const normalized = String(source || "").trim();
  if (!normalized || normalized.includes("#")) return normalized;
  return `${normalized}#t=0.001`;
}

function renderPresenterStaticVideoPreviewSlide(slide) {
  const title = presenterFileDisplayTitle(slide, "동영상");
  return `<div class="presenter-static-media-preview" aria-label="${escapeAttr(title)}">${escapeHtml(title)}</div>`;
}

function renderPresenterImageSlide(slide, options = {}) {
  const source = normalizePresenterMediaSource(slide.imageSrc || slide.asset?.url || slide.text);
  if (!source) return "";
  const referenceClass = slide?.referenceMedia ? " presenter-image--reference" : "";
  const previewStage = Boolean(options.previewStage);
  const decoding = previewStage ? "async" : "sync";
  const loading = previewStage ? "lazy" : "eager";
  const fetchPriority = previewStage ? "low" : "high";
  return `<img class="presenter-image${referenceClass}" src="${escapeAttr(source)}" alt="" decoding="${decoding}" loading="${loading}" fetchpriority="${fetchPriority}" draggable="false" />`;
}

function presenterOrderDisplayLabel(value = "") {
  const label = String(value || "");
  // Format only order labels; content and persisted values remain unchanged.
  return label.replace(/^([가-힣A-Za-z][가-힣A-Za-z ]*?)\s*(\d+(?:\s*[·–~-]\s*\d+)*)$/u, (match, name, numbers) => {
    const values = numbers.split(/[·–~-]/u).map((part) => Number(part.trim()));
    if (values.some((number) => number < 1 || number > 50)) return match;
    const circled = values.map((number) => String.fromCodePoint(
      number <= 20 ? 0x2460 + number - 1
        : number <= 35 ? 0x3251 + number - 21 : 0x32b1 + number - 36,
    ));
    let index = 0;
    return name.trim() + " " + numbers.replace(/\d+/g, () => circled[index++]).replace(/\s*([·–~-])\s*/g, (_, separator) => separator === "·" ? "·" : "–");
  });
}

function renderPresenterTitleAssigneeSlide(slide) {
  const title = String(slide.title || slide.text || slide.label || "").trim();
  const assignee = String(slide.assignee || slide.subtitle || "").trim();
  const orderTitle = String(slide.orderTitle || "").trim();
  const contentTitle = String(slide.contentTitle || "").trim();
  const titleChars = presenterLineCharEstimate(title);
  const assigneeChars = presenterLineCharEstimate(assignee);
  const orderChars = presenterLineCharEstimate(orderTitle);
  const contentChars = presenterLineCharEstimate(contentTitle);
  if (presenterTitleAssigneeIsSermon(slide) && contentTitle && assignee) {
    return `
      <div class="presenter-slide-text presenter-title-assignee presenter-title-assignee--sermon">
        <span class="presenter-title-assignee-content" style="--line-chars: ${escapeAttr(contentChars)}">${escapeHtml(contentTitle)}</span>
        <span class="presenter-title-assignee-person" style="--line-chars: ${escapeAttr(assigneeChars)}">${escapeHtml(assignee)}</span>
      </div>
    `;
  }
  if (orderTitle && contentTitle && !assignee) {
    return `
      <div class="presenter-slide-text presenter-title-assignee presenter-title-assignee--order-content">
        <span class="presenter-title-assignee-order" style="--line-chars: ${escapeAttr(orderChars)}">${escapeHtml(presenterOrderDisplayLabel(orderTitle))}</span>
        <span class="presenter-title-assignee-content" style="--line-chars: ${escapeAttr(contentChars)}">${escapeHtml(contentTitle)}</span>
      </div>
    `;
  }
  if (orderTitle && contentTitle && assignee) {
    return `
      <div class="presenter-slide-text presenter-title-assignee presenter-title-assignee--three-part">
        <span class="presenter-title-assignee-order" style="--line-chars: ${escapeAttr(orderChars)}">${escapeHtml(presenterOrderDisplayLabel(orderTitle))}</span>
        <span class="presenter-title-assignee-content" style="--line-chars: ${escapeAttr(contentChars)}">${escapeHtml(contentTitle)}</span>
        <span class="presenter-title-assignee-person" style="--line-chars: ${escapeAttr(assigneeChars)}">${escapeHtml(assignee)}</span>
      </div>
    `;
  }
  const soloClass = assignee ? "" : " presenter-title-assignee--solo";
  return `
    <div class="presenter-slide-text presenter-title-assignee${soloClass}">
      <span class="presenter-title-assignee-title" style="--line-chars: ${escapeAttr(titleChars)}">${escapeHtml(title === slide.label || title === slide.sectionLabel ? presenterOrderDisplayLabel(title) : title)}</span>
      ${assignee ? `<span class="presenter-title-assignee-person" style="--line-chars: ${escapeAttr(assigneeChars)}">${escapeHtml(assignee)}</span>` : ""}
    </div>
  `;
}

function presenterTitleAssigneeIsSermon(slide = {}) {
  if (String(slide?.titlePresentation || "").trim() === "sermon") return true;
  const values = [
    slide.sectionKey,
    slide.sectionLabel,
    slide.sectionTitle,
    slide.orderTitle,
    slide.label,
  ].map((value) => compactSearchValue(value));
  return values.some((value) => value === "설교" || value === "sermon");
}

function renderPresenterSectionSongTitleSlide(slide) {
  const heading = presenterSongTitleNormalizedHeading(
    String(slide.sectionHeading || slide.label || slide.sectionLabel || "").trim(),
    String(slide.sectionKey || slide._worshipSectionKey || "").trim(),
  );
  const title = presenterSongTitleContentText(
    String(slide.text || formatPresenterSongTitleText(slide.title || "")).trim(),
    heading,
  );
  const headingChars = presenterLineCharEstimate(heading);
  const titleChars = presenterLineCharEstimate(title);
  return `
    <div class="presenter-slide-text presenter-section-song-title">
      <span class="presenter-section-song-title-heading" style="--line-chars: ${escapeAttr(headingChars)}">${escapeHtml(presenterOrderDisplayLabel(heading))}</span>
      <span class="presenter-section-song-title-name" style="--line-chars: ${escapeAttr(titleChars)}">${renderPresenterSongText(title, slide)}</span>
    </div>
  `;
}

function renderPresenterTitleContentSlide(slide, options = {}) {
  const title = String(slide.title || "").trim();
  const orderHeading = options.noChromakey && presenterTitleAssigneeIsSermon(slide)
    ? String(slide.orderTitle || slide.sectionTitle || "설교").trim()
    : "";
  const bodyLines = presenterTitleContentLines(slide);
  const titleChars = presenterLineCharEstimate(title);
  return `
    <div class="presenter-title-content">
      ${orderHeading ? `<span class="presenter-fullscreen-order-heading">${escapeHtml(presenterOrderDisplayLabel(orderHeading))}</span>` : ""}
      ${slide.fullscreenSongTitle && slide.songTitleContent?.orderTitle ? `<span class="presenter-fullscreen-song-heading">${escapeHtml(presenterOrderDisplayLabel(slide.songTitleContent.orderTitle))}</span>` : ""}
      <span class="presenter-title-content-title" style="--line-chars: ${escapeAttr(titleChars)}">${slide.fullscreenSongTitle ? renderPresenterSongText(title, slide) : escapeHtml(title)}</span>
      ${slide.fullscreenSongTitle && slide.songTitleContent?.detail ? `<span class="presenter-fullscreen-song-detail">${slide.songTitleContent.detailKind === "subtitle" ? `(${escapeHtml(slide.songTitleContent.detail)})` : escapeHtml(slide.songTitleContent.detail)}</span>` : ""}
      ${slide.fullscreenSongTitle ? "" : `<div class="presenter-title-content-body">
        ${bodyLines.map((line) => `<span style="--line-chars: ${presenterLineCharEstimate(line)}">${escapePresenterSlideLine(line, slide)}</span>`).join("")}
      </div>`}
    </div>
  `;
}

function renderPresenterLiturgicalBodySlide(slide) {
  const title = String(slide.title || slide.sectionTitle || "").trim();
  const lines = presenterLiturgicalBodyLines(slide);
  const titleChars = presenterLineCharEstimate(title);
  const announcementItems = Array.isArray(slide?.announcementItems) ? slide.announcementItems.filter((item) => item?.lines?.length) : [];
  const body = announcementItems.length
    ? `<div class="presenter-announcement-items">${announcementItems.map((item) => {
      const marker = String(item.marker || "").trim();
      const itemLines = item.lines.map((line) => String(line || ""));
      return `<div class="presenter-announcement-item${marker ? "" : " presenter-announcement-item--plain"}">
        ${marker ? `<span class="presenter-announcement-marker">${escapeHtml(marker)}</span>` : ""}
        <span class="presenter-announcement-copy">${itemLines.map((line) => `<span style="--line-chars: ${presenterLineCharEstimate(line)}">${line ? escapePresenterSlideLine(line, slide) : "<br>"}</span>`).join("")}</span>
      </div>`;
    }).join("")}</div>`
    : `<div class="presenter-liturgical-body-lines">
        ${lines.map((line) => `<span style="--line-chars: ${presenterLineCharEstimate(line)}">${escapePresenterSlideLine(line, slide)}</span>`).join("")}
      </div>`;
  return `
    <div class="presenter-liturgical-body">
      ${body}
      <div class="presenter-liturgical-body-heading">
        <span style="--line-chars: ${escapeAttr(titleChars)}">${escapeHtml(title)}</span>
      </div>
    </div>
  `;
}

function renderPresenterFileSlide(slide) {
  const asset = normalizeServiceAsset(slide.asset);
  const typeLabel = presenterFileTypeLabel(slide.sourceType || slide.componentType || asset.kind || "file");
  const title = presenterFileDisplayTitle({ ...slide, asset }, typeLabel);
  return `
    <div class="presenter-slide-file">
      <small>${escapeHtml(typeLabel)}</small>
      <strong>${escapeHtml(title)}</strong>
    </div>
  `;
}

function renderPresenterSlideText(slide) {
  const verseNumber = presenterLyricVerseNumber(slide);
  let verseNumberUsed = false;
  return presenterDisplayLines(slide)
    .map((line) => {
      const showVerseNumber = verseNumber && !verseNumberUsed && String(line || "").trim();
      if (showVerseNumber) verseNumberUsed = true;
      return `<span${showVerseNumber ? ` class="presenter-lyric-line presenter-lyric-line--numbered" data-verse-no="${escapeAttr(verseNumber)}"` : ""} style="--line-chars: ${presenterLineCharEstimate(line) + (showVerseNumber ? 1 : 0)}">${escapePresenterSlideLine(line, slide)}</span>`;
    })
    .join("");
}

function renderPresenterSongText(text, slide) {
  const raw = String(text || " ");
  if (presenterSlideElementType(slide) !== PRESENTER_ELEMENT_TYPES.PRAISE) return escapePresenterSlideLine(raw, slide);
  const match = raw.match(/^(\s*)([\u2669\u266A\u266B\u266C])(\s*)(.*)$/u);
  if (!match) return renderPresenterHighlightedText(raw, slide);
  const [, leading, , spacing, rest] = match;
  return `${escapeHtml(leading)}<span class="presenter-song-note" aria-hidden="true">${escapeHtml(PRESENTER_SONG_NOTE)}</span>${escapeHtml(spacing || " ")}${renderPresenterHighlightedText(rest || " ", slide)}`;
}

function presenterLyricVerseNumber(slide) {
  if (presenterSlideElementType(slide) !== PRESENTER_ELEMENT_TYPES.PRAISE) return "";
  if (presenterSlideLayout(slide) !== PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT) return "";
  if (slide?.type !== "lyrics") return "";
  const marker = String(slide?.marker || slide?.formLabel || "").trim();
  const match = marker.match(/^(?:verse|v)\s*(\d{1,2})$/i)
    || marker.match(/^(\d{1,2})\s*절$/);
  return match ? String(Number(match[1])) : "";
}

function escapePresenterSlideLine(line, slide) {
  const text = line || " ";
  if (presenterSlideElementType(slide) === PRESENTER_ELEMENT_TYPES.SCRIPTURE_TEXT) {
    return escapeHtml(text).replace(/ {2,}/g, (spaces) => "&nbsp;".repeat(spaces.length));
  }
  if (presenterSlideElementType(slide) === PRESENTER_ELEMENT_TYPES.PRAISE) {
    return renderPresenterSongText(text, slide);
  }
  return renderPresenterHighlightedText(text, slide);
}

function renderPresenterHighlightedText(line, slide) {
  const text = String(line || " ");
  const highlights = normalizeServiceTextHighlights(slide?.textHighlights || slide?.text_highlights || slide?.highlights);
  if (!highlights.length) return escapeHtml(text);
  const ranges = [];
  highlights
    .filter((highlight) => highlight.text)
    .sort((a, b) => String(b.text).length - String(a.text).length)
    .forEach((highlight) => {
      const needle = String(highlight.text || "");
      if (!needle) return;
      let index = text.indexOf(needle);
      while (index !== -1) {
        const end = index + needle.length;
        const overlaps = ranges.some((range) => index < range.end && end > range.start);
        if (!overlaps) ranges.push({ start: index, end, highlight });
        index = text.indexOf(needle, end);
      }
    });
  if (!ranges.length) return escapeHtml(text);
  ranges.sort((a, b) => a.start - b.start);
  let cursor = 0;
  const parts = [];
  ranges.forEach((range) => {
    if (range.start > cursor) parts.push(escapeHtml(text.slice(cursor, range.start)));
    const content = escapeHtml(text.slice(range.start, range.end));
    const style = presenterTextHighlightStyle(range.highlight);
    parts.push(`<span class="presenter-text-highlight"${style ? ` style="${style}"` : ""}>${content}</span>`);
    cursor = range.end;
  });
  if (cursor < text.length) parts.push(escapeHtml(text.slice(cursor)));
  return parts.join("");
}

function presenterTextHighlightStyle(highlight = {}) {
  const styles = [];
  const color = normalizeServiceTextHighlightColor(highlight.color || highlight.fg || highlight.foreground || highlight.hex);
  if (color) styles.push(`--presenter-text-highlight-color: ${escapeAttr(color)}`);
  if (highlight.bold === false) styles.push("--presenter-text-highlight-weight: inherit");
  return styles.join("; ");
}

function presenterDisplayLines(slide) {
  const baseText = slide?.text || slide?.title || "";
  const lowerBar = presenterSlideLayout(slide) === PRESENTER_SLIDE_LAYOUTS.LOWER_BAR_TEXT;
  const text = lowerBar ? slide?.text : baseText;
  const lines = String(text || "").split(/\n/);
  if (lowerBar) return lines;

  const deduped = [];
  for (const line of lines) {
    const previous = deduped[deduped.length - 1];
    if (previous !== undefined && normalizeTitle(previous) === normalizeTitle(line)) continue;
    deduped.push(line);
  }
  return deduped.length ? deduped : [""];
}

function presenterLiturgicalBodyLines(slide) {
  return String(slide?.text || slide?.bodyText || "")
    .split(/\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function presenterTitleContentBodyText(slide) {
  return String(slide?.bodyText || slide?.body || slide?.text || "").trim();
}

function presenterTitleContentLines(slide) {
  const title = String(slide?.title || "").trim();
  const lines = presenterTitleContentBodyText(slide).split(/\n/);
  const deduped = [];
  for (const line of lines) {
    if (title && normalizeTitle(line) === normalizeTitle(title)) continue;
    const previous = deduped[deduped.length - 1];
    if (previous !== undefined && normalizeTitle(previous) === normalizeTitle(line)) continue;
    deduped.push(line);
  }
  return deduped.length ? deduped : [""];
}

function presenterLineCharEstimate(line) {
  const text = String(line || "").replace(/\s+/g, " ").trim();
  if (!text) return 1;
  let score = 0;
  for (const char of text) {
    if (/\s/.test(char)) score += 0.35;
    else if (/[A-Za-z0-9]/.test(char)) score += 0.58;
    else score += 1;
  }
  return Math.max(1, Math.ceil(score));
}
