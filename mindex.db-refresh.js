// Fetch into a detached snapshot; never reuse loaders that render or publish mid-load.
(() => {
  let busy = false;
  let editRevision = 0;
  document.addEventListener("input", () => { editRevision += 1; }, true);
  document.addEventListener("change", () => { editRevision += 1; }, true);
  const button = document.getElementById("refreshDbBtn");
  if (!button) return;

  function blockedReason() {
    if (isPresenterOutputWindowOpen() || state.presenter.outputPendingAt) return "송출 중에는 DB 갱신을 보류합니다. 송출 종료 후 다시 눌러 주세요.";
    if (document.querySelector('[data-input-status="error"]')) return "저장에 실패한 입력이 있어요. 해당 입력을 다시 저장한 뒤 새로고침해 주세요.";
    if (pendingSundayEditSync.size) return "연결된 예배에 반영하지 못한 변경이 남아 있어요. 해당 예배를 저장해 동기화를 완료해 주세요.";
    const pendingFeedback = [...document.querySelectorAll('[data-input-status="modified"]')].some(node => {
      const editor = node.closest('.svc-board-subgroup-control-item');
      if (!editor) return true;
      const fields = [...editor.querySelectorAll('[data-service-item-field]')];
      // Only dismiss feedback when every field has a known, unchanged text baseline.
      return !fields.length || fields.some(field => !isDeferredServiceTextInput(field)
        || field.dataset.initialValue === undefined || field.value !== field.dataset.initialValue);
    });
    if (hasDirtyChanges({ reconcile: true })
      || state.dirtyServiceElementIds.size || state.dirtyServiceStructureIds.size || state.dirtyServiceTypeIds.size
      || Object.values(state.presenterPreparationDrafts).some(value => String(value || "").trim())
      || [...worshipSetlistLeaderDrafts.values()].some(draft => draft.saving || cleanServiceAssignee(draft.value) !== draft.original)
      || pendingFeedback) {
      return "미저장 입력이 있어요. 먼저 저장한 뒤 DB를 새로고침해 주세요.";
    }
    if (state.saving || state.loading || activeServiceSavePromise || songLoadPromise || serviceDataLoadPromise
      || calendarLoadPromise || linkedSongLoadPromises.size || serviceItemLoadPromises.size
      || presenterServiceHydrationPromises.size || worshipPresenterSlideLoadPromises.size
      || state.presenterPreparationApplyingServiceIds.size
      || document.querySelector('[data-input-status="saving"]')) {
      return "저장 또는 불러오기가 진행 중이에요. 완료 후 다시 눌러 주세요.";
    }
    return "";
  }

  async function songsSnapshot(ids = null) {
    const songs = (ids
      ? await fetchSupabaseBatches(ids, batch => fetchSupabasePaged("mindex_songs", "*", q => q.in("id", batch).order("id")))
      : await fetchSupabasePaged("mindex_songs", "*", q => q.order("id"))).map(normalizeServerSong);
    const versions = ids
      ? await fetchSupabaseBatches(ids, async batch => {
        const source = await fetchSupabasePaged("mindex_song_versions", "*", q => q.in("source_song_id", batch).order("id"));
        const canonical = await fetchSupabasePaged("mindex_song_versions", "*", q => q.in("canonical_song_id", batch).order("id"));
        return [...new Map([...source, ...canonical].map(row => [row.id, row])).values()];
      })
      : await fetchSupabasePaged("mindex_song_versions", "*", q => q.order("id"));
    const units = ids
      ? await fetchSupabaseBatches(versions.map(row => row.id), batch => fetchSupabasePaged("mindex_version_units", "*", q => q.in("version_id", batch).order("curated_order").order("unit_order").order("id")))
      : await fetchSupabasePaged("mindex_version_units", "*", q => q.order("version_id").order("curated_order").order("unit_order").order("id"));
    attachRelationalSongVersionRows(versions, units, null, songs);
    return songs;
  }

  async function fetchSnapshot(module, serviceId) {
    if (module === "praise") {
      const songs = await songsSnapshot();
      const relations = await fetchSupabasePaged("mindex_song_relations", "source_song_id,related_song_id", q => q.eq("relation_type", "related").order("id"));
      const related = new Map(songs.map(song => [song.id, new Set()]));
      for (const row of relations) {
        if (!related.has(row.source_song_id) || !related.has(row.related_song_id)) continue;
        related.get(row.source_song_id).add(row.related_song_id);
        related.get(row.related_song_id).add(row.source_song_id);
      }
      songs.forEach(song => { song.related_song_ids = [...related.get(song.id)]; });
      return { songs };
    }
    if (["home", "service", "presenter"].includes(module)) {
      const serviceRows = await fetchSupabasePaged("mindex_worship_services", state.serviceAliasSupported ? WORSHIP_SERVICE_LIST_SELECT : WORSHIP_SERVICE_BASE_LIST_SELECT, worshipServiceListQuery);
      const ids = serviceId ? [serviceId] : initialWorshipElementServiceIds(serviceRows.map(normalizeWorshipService));
      const fullServices = await fetchSupabaseBatches(ids, batch => fetchSupabasePaged("mindex_worship_services", "*", q => q.in("id", batch).order("id")));
      const sections = await fetchSupabaseBatches(ids, batch => fetchSupabasePaged("mindex_worship_sections", WORSHIP_SECTION_LIST_SELECT, q => q.in("service_id", batch).order("sort_order").order("id")));
      const elementSelect = await worshipElementListSelect();
      const elements = await fetchSupabaseBatches(sections.map(row => row.id), batch => fetchSupabasePaged("mindex_worship_elements", elementSelect, q => q.in("section_id", batch).order("sort_order").order("id")));
      const oldSectionIds = new Set(state.worshipSections.filter(row => ids.includes(row.service_id)).map(row => row.id));
      const oldSongs = state.worshipElements.filter(row => oldSectionIds.has(row.section_id)).map(row => row.song_id);
      const songs = await songsSnapshot([...new Set([...oldSongs, ...elements.map(row => row.song_id)].filter(Boolean))]);
      const slides = await fetchSupabaseBatches(ids, batch => fetchSupabasePaged("mindex_worship_presenter_slides", "*", q => q.in("service_id", batch).order("section_order").order("element_order").order("slide_order")));
      return { ids, serviceRows, fullServices, sections, elements, elementSelect, songs, slides };
    }
    if (module === "scripture") return { scriptures: await fetchSupabasePaged("mindex_scriptures", "*", q => q.eq("is_active", true).order("id")) };
    if (module === "references") return { references: await fetchSupabasePaged("mindex_reference_links", "*", q => q.order("sort_order").order("id")) };
    if (module === "calendar") return { calendar: await fetchSupabasePaged("mindex_sunday_calendar", "*", q => q.gte("date", CALENDAR_MIN_DATE).order("date").order("id")) };
    throw new Error("이 화면은 아직 DB 새로고침을 지원하지 않습니다.");
  }

  function applySnapshot(snapshot, module) {
    if (snapshot.songs) {
      state.songs = (module === "praise" ? snapshot.songs
        : [...new Map([...state.songs, ...snapshot.songs].map(song => [song.id, song])).values()]).sort(sortSongs);
      clearSearchCaches();
      if (module === "praise") {
        songCatalogLoaded = true;
        const owner = state.songs.find(song => song.versions?.some(version => version.id === state.selectedVersionId));
        if (owner) state.selectedSongId = owner.id;
        const song = getSelectedSong();
        if (!song) state.selectedSongId = null;
        state.selectedVersionId = song?.versions?.some(v => v.id === state.selectedVersionId)
          ? state.selectedVersionId : song ? getPreferredVersionId(song) : null;
        state.forms = normalizeForms((getSelectedVersion()?.forms || []).map(form => withLocalId({ ...form, song_id: state.selectedVersionId })));
        captureCleanFingerprint("praise");
      }
    }
    if (snapshot.serviceRows) {
      const full = new Map(snapshot.fullServices.map(row => [row.id, row]));
      state.services = snapshot.serviceRows.map(row => normalizeWorshipService(full.get(row.id) || row));
      const ids = new Set(snapshot.ids);
      const sectionIds = new Set([...state.worshipSections.filter(row => ids.has(row.service_id)), ...snapshot.sections].map(row => row.id));
      state.worshipSections = [...state.worshipSections.filter(row => !ids.has(row.service_id)), ...snapshot.sections];
      state.worshipElements = [...state.worshipElements.filter(row => !sectionIds.has(row.section_id)), ...snapshot.elements];
      const grouped = groupWorshipElements(snapshot.sections, snapshot.elements);
      const hidden = new Set(snapshot.elements.filter(row => row.config?.hiddenInPresentation || row.config?.hidden_in_presentation || row.config?.hidden).map(row => row.id));
      const slides = groupWorshipPresenterSlides(snapshot.slides, hidden);
      for (const id of ids) {
        const service = state.services.find(row => row.id === id);
        state.serviceItems[id] = service ? projectWorshipServiceItemsFromTemplate(service, grouped[id] || []) : [];
        state.loadedWorshipServiceIds.add(id);
        state.worshipPresenterSlides[id] = slides[id] || [];
        state.loadedWorshipPresenterServiceIds.add(id);
        presenterSlideBuildCache.delete(id);
      }
      if (!state.services.some(row => row.id === state.selectedServiceId)) state.selectedServiceId = null;
      const listSelect = state.serviceAliasSupported ? WORSHIP_SERVICE_LIST_SELECT : WORSHIP_SERVICE_BASE_LIST_SELECT;
      const listKey = WORSHIP_EMERGENCY_TODAY_ONLY ? `today:${localDateStringWithOffset(new Date(), 0)}` : listSelect;
      writeStaticSupabaseCache("mindex_worship_services", listKey, snapshot.serviceRows);
      writeStaticSupabaseCache("mindex_worship_rows", worshipRowsCacheKey(snapshot.ids, snapshot.elementSelect), [{ sections: snapshot.sections, elements: snapshot.elements }]);
      captureCleanFingerprint("service");
    }
    if (snapshot.scriptures) {
      const rows = snapshot.scriptures.map(normalizeServerScripture);
      state.uiVerses = extractUiVerses(rows);
      state.scriptures = rows.filter(row => !uiVerseSlot(row)).sort(sortScriptures);
      if (!state.scriptures.some(row => row.id === state.selectedScriptureId)) state.selectedScriptureId = null;
      captureCleanFingerprint("scripture");
    }
    if (snapshot.references) {
      state.referenceLinks = snapshot.references.map(normalizeReferenceLink).sort(sortReferenceLinks);
      state.referenceLinksLoaded = true;
      state.referenceError = "";
      captureCleanFingerprint("references");
    }
    if (snapshot.calendar) {
      state.calendarData = snapshot.calendar;
      state.calendarLoaded = true;
      state.calendarError = "";
    }
  }

  async function refresh() {
    if (busy) return false;
    const reason = blockedReason();
    if (reason) { showToast(reason, "error"); return false; }
    if (!requireClient()) return false;
    const context = () => JSON.stringify([state.module, state.selectedServiceId, state.selectedSongId, state.selectedVersionId, state.selectedScriptureId, presenterViewServiceId()]);
    const before = context();
    const revision = editRevision;
    const module = state.module;
    busy = true;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.title = "DB 불러오는 중";
    try {
      const snapshot = await fetchSnapshot(module, module === "presenter" ? presenterViewServiceId() : state.selectedServiceId);
      // A user may start editing, navigate, save, or start output while the network is pending.
      if (before !== context() || revision !== editRevision || blockedReason()) {
        showToast("화면이나 입력 상태가 바뀌어 갱신을 보류했어요. 기존 내용은 유지됩니다.", "error");
        return false;
      }
      const viewport = captureDetailViewportSnapshot();
      applySnapshot(snapshot, module);
      persistUiState();
      render();
      restoreDetailViewportSnapshot(viewport);
      showToast("DB 새로고침 완료");
      return true;
    } catch (error) {
      console.error("[DB refresh]", error);
      showToast("DB를 불러오지 못했어요. 기존 내용은 유지됩니다.", "error");
      return false;
    } finally {
      busy = false;
      button.disabled = false;
      button.setAttribute("aria-busy", "false");
      button.title = "DB 새로고침";
    }
  }
  button.addEventListener("click", () => { void refresh(); });
  window.MINDEX_DB_REFRESH = { refresh };
})();
