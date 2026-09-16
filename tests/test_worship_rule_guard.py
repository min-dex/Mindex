from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "app.js"
STYLES_CSS = Path(__file__).resolve().parents[1] / "styles.css"


def read_app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def read_styles_css() -> str:
    return STYLES_CSS.read_text(encoding="utf-8")


def block(source: str, name: str, end_marker: str = "\n};") -> str:
    match = re.search(rf"const\s+{re.escape(name)}\s*=\s*(?:Object\.freeze\()?[\[{{]", source)
    if not match:
        raise AssertionError(f"{name} block not found")
    start = match.start()
    end = source.find(end_marker, match.end())
    if end == -1:
        raise AssertionError(f"{name} block end not found")
    return source[start:end]


def function_block(source: str, name: str) -> str:
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*{{", source)
    if not match:
        raise AssertionError(f"{name} function not found")
    depth = 0
    started = False
    for index in range(match.end() - 1, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
            started = True
        elif char == "}":
            depth -= 1
            if started and depth == 0:
                return source[match.start():index + 1]
    raise AssertionError(f"{name} function end not found")


class WorshipRuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = read_app_js()

    def test_praise_input_modes_match_database_allowed_values(self) -> None:
        ui_block = block(self.source, "SERVICE_PRAISE_INPUT_MODES", "\n];")
        db_block = self.source[
            self.source.index("const WORSHIP_DB_ELEMENT_INPUT_MODES")
            : self.source.index("const WORSHIP_DB_ELEMENT_TYPES")
        ]
        expected = {
            "score_db": "악보 불러오기",
            "lyrics_db": "가사 불러오기",
            "manual_praise": "직접 입력하기",
        }
        for value, label in expected.items():
            self.assertIn(f'"{value}"', ui_block)
            self.assertIn(label, ui_block)
            self.assertIn(f'"{value}"', db_block)

    def test_media_element_types_remain_supported(self) -> None:
        source = self.source
        for value in ("image", "video", "audio", "score", "file"):
            self.assertRegex(source, rf'\["{value}",')
            self.assertRegex(source, rf'SERVICE_ASSET_KINDS = new Set\(\[[^\]]*"{value}"')

    def test_minister_defaults_for_public_and_young_adult_services(self) -> None:
        defaults = block(self.source, "SERVICE_MINISTER_DEFAULTS", "\n});")
        expectations = [
            ('"sunday-second"', "offeringPrayer", "김남영 목사"),
            ('"sunday-main"', "offeringPrayer", "김남영 목사"),
            ('"young-adult"', "sermon", "김석범 목사"),
            ('"young-adult"', "offeringPrayer", "김석범 목사"),
            ('"young-adult"', "benediction", "김석범 목사"),
        ]
        for service_type, key, value in expectations:
            pattern = rf"{re.escape(service_type)}:[^}}]+{key}:\s*\"{re.escape(value)}\""
            self.assertRegex(defaults, pattern)

    def test_department_announcement_defaults_stay_seeded(self) -> None:
        youth = function_block(self.source, "youthWorshipAnnouncementsStep")
        young_adult = function_block(self.source, "youngAdultWorshipAnnouncementsStep")
        self.assertIn('label: "광고"', youth)
        self.assertIn("오늘도 청소년부 예배에 오신 여러분을 환영하고 축복합니다 :)", youth)
        self.assertIn("1. 오늘 2부 활동은 반별 모임으로 진행합니다.", youth)
        self.assertIn('label: "광고"', young_adult)
        self.assertIn("오늘도 청년부 예배에 오신 여러분을 환영하고 축복합니다 :)", young_adult)
        self.assertIn("1. 오늘 2부 활동은 셀 모임으로 진행합니다.", young_adult)

    def test_young_adult_outdoor_calendar_skips_auto_service(self) -> None:
        skip_guard = function_block(self.source, "calendarSkippedServiceTypesForDate")
        contexts = block(self.source, "CALENDAR_SERVICE_SKIP_CONTEXTS", "\n];")
        keywords = block(self.source, "CALENDAR_SERVICE_SKIP_KEYWORDS", "\n];")
        self.assertIn('"young-adult"', contexts)
        self.assertIn("청년부", contexts)
        self.assertIn("청년", contexts)
        self.assertIn("야외예배", keywords)
        self.assertIn("문화예배", keywords)
        self.assertIn("matchesAlternative", skip_guard)
        self.assertIn("calendarSkippedServiceTypesForDate(sunday)", self.source)
        self.assertIn("!skippedSundayServiceTypes.has(target.typeId)", self.source)
        self.assertIn("calendarSkippedServiceTypesForDate(sundayDate)", self.source)
        self.assertIn("auto_generated: true", self.source)

    def test_sunday_shared_content_contract_stays_linked(self) -> None:
        shared = function_block(self.source, "sundaySharedContentTypesForItem")
        sync_after_save = function_block(self.source, "syncSharedSundayContentAfterSave")
        sync_to_service = function_block(self.source, "syncSharedSundayContentToService")
        source_lookup = function_block(self.source, "sharedSundayContentSourceItem")
        participant_guard = function_block(self.source, "worshipServiceParticipatesInSharedSundayContent")
        self.assertIn("!isAllGenerationsWorshipService(service)", participant_guard)
        self.assertIn("worshipServiceParticipatesInSharedSundayContent(service)", shared)
        self.assertNotIn("syncSharedSundayContentToService(", sync_after_save)
        self.assertNotIn("state.client", sync_after_save)
        self.assertIn("worshipServiceParticipatesInSharedSundayContent(targetService)", sync_to_service)
        self.assertIn("return null", source_lookup)
        self.assertIn("previousItems", sync_after_save)
        self.assertIn("persistSundayEditSync(job, options)", sync_after_save)
        edit_sync = function_block(self.source, "persistSundayEditSync")
        self.assertIn('count: "exact"', edit_sync)
        self.assertIn('.eq("updated_at", existing.updated_at)', edit_sync)
        self.assertNotIn(".upsert(", edit_sync)
        main_praise_branch = shared.split('key.startsWith("main-praise:")', 1)[1].split('if ((["scripture-reading"', 1)[0]
        self.assertIn('return ["sunday-first", "sunday-second"]', main_praise_branch)
        self.assertNotIn('"sunday-main"', main_praise_branch)
        self.assertRegex(shared, r'"scripture-reading",\s*"sermon-title",\s*"sermon-scripture"')
        self.assertIn('key.startsWith("sermon-citation:")', shared)
        self.assertRegex(shared, r'"sunday-second",\s*"sunday-main"')
        self.assertIn('key === "offering-hymn"', shared)

    def test_full_save_preserves_existing_content_rows(self) -> None:
        save = function_block(self.source, "saveWorshipServiceInstance")
        element_patch = function_block(self.source, "saveWorshipServiceElementPatch")
        preserve = function_block(self.source, "preserveExistingWorshipContentRows")
        self.assertNotIn("materializeSharedSundayContentForPersistence", save)
        self.assertNotIn("materializeSharedSundayContentForPersistence", element_patch)
        self.assertLess(
            save.index("preserveExistingWorshipContentRows(rows, existingSections, existingElements)"),
            save.index("validateWorshipPersistenceRows(rows, { serviceId })"),
        )
        should_preserve = function_block(self.source, "shouldPreserveExistingWorshipElement")
        self.assertIn("worshipElementHasPersistedContent(element)", should_preserve)
        self.assertIn("rows.elements.push(element)", preserve)
        self.assertIn("rows.sections.push(section)", preserve)

    def test_sermon_scripture_slot_wins_over_generic_sermon_label(self) -> None:
        derive = function_block(self.source, "deriveWorshipSlotKey")
        sermon_branch = derive.split('if (sectionKey === "sermon")', 1)[1].split('if (sectionKey === "response_song")', 1)[0]
        self.assertLess(
            sermon_branch.index('inputMode === "scripture" || elementType === "scripture_body"'),
            sermon_branch.index('["설교", "설교제목"].includes(label)'),
        )
        self.assertIn("const itemSlotKey = normalizeWorshipSlotKey(item._worshipSlotKey || item.slotKey || item.slot_key)", self.source)
        self.assertIn("if (itemSlotKey) sourceRef.slotKey = itemSlotKey", self.source)

    def test_fixed_doxology_scope_does_not_absorb_sunday_main(self) -> None:
        fixed = function_block(self.source, "publicFixedDoxologySpec")
        self.assertIn('"sunday-first"', fixed)
        self.assertIn('"sunday-second"', fixed)
        self.assertIn('"sunday-afternoon"', fixed)
        self.assertNotIn('"sunday-main": { hymnNo: "5"', fixed)

    def test_public_service_time_windows_are_stable(self) -> None:
        windows = block(self.source, "SERVICE_TIME_WINDOWS")
        expected = {
            "wednesday": ("19:10", "20:30"),
            "friday": ("20:00", "22:00"),
            "monthly": ("20:00", "22:00"),
            "sunday-first": ("07:00", "08:00"),
            "sunday-second": ("08:50", "10:00"),
            "sunday-main": ("10:50", "12:00"),
            "sunday-afternoon": ("13:20", "14:30"),
        }
        for key, (start, end) in expected.items():
            self.assertRegex(windows, rf'"?{re.escape(key)}"?:\s*{{\s*start:\s*"{start}",\s*end:\s*"{end}"')

    def test_persistence_rows_are_sanitized_before_validation(self) -> None:
        save = function_block(self.source, "saveWorshipServiceInstance")
        shared = function_block(self.source, "persistSharedSundayServiceItems")
        sanitizer = function_block(self.source, "sanitizeWorshipPersistenceRows")
        for save_path in (save, shared):
            self.assertIn("sanitizeWorshipPersistenceRows(rows", save_path)
            self.assertLess(
                save_path.index("sanitizeWorshipPersistenceRows(rows"),
                save_path.index("validateWorshipPersistenceRows(rows"),
            )
        self.assertIn("worshipDbInputModeForSave", sanitizer)
        self.assertIn("element.song_version_id = null", sanitizer)
        self.assertIn("section.created_at = section.created_at || persistedAt", sanitizer)
        self.assertIn("sanitizeSongContentStateWithoutSong(element.content_state", sanitizer)
        self.assertIn("sanitizeSongContentStateWithoutSong(element.config.contentState", sanitizer)

    def test_shared_sunday_sync_loads_and_merges_target_rows(self) -> None:
        helper = function_block(self.source, "ensureWorshipServiceRowsLoadedForPersistence")
        shared = function_block(self.source, "persistSharedSundayServiceItems")
        self.assertIn("fetchWorshipRowsForServiceIds([id])", helper)
        self.assertIn("state.loadedWorshipServiceIds.add(id)", helper)
        self.assertLess(
            shared.index("await ensureWorshipServiceRowsLoadedForPersistence(serviceId)"),
            shared.index("const existingSections"),
        )
        self.assertNotIn("removedElementIds", shared)
        self.assertNotIn("removedSectionIds", shared)
        self.assertNotIn(".delete()", shared)
        self.assertIn("savedSectionIds", shared)
        self.assertIn("savedElementIds", shared)
        self.assertIn('.from("mindex_worship_elements")', shared)
        self.assertIn('.from("mindex_worship_sections")', shared)

    def test_committed_item_edits_use_element_patch_save(self) -> None:
        patch = function_block(self.source, "saveWorshipServiceElementPatch")
        item_save = function_block(self.source, "saveServiceItemPatch")
        lifecycle = function_block(self.source, "runServiceSave")
        committed = function_block(self.source, "resolveAndSaveCommittedServiceItem")

        self.assertIn("saveWorshipServiceElementPatch(service, item.id)", item_save)
        self.assertIn("await runServiceSave({ ...options, feedbackServiceId: serviceId, feedbackItemId: itemId }", item_save)
        self.assertIn("waitForServiceSave(options", item_save)
        self.assertIn("activeServiceSavePromise = savePromise", lifecycle)
        self.assertIn("const result = await savePromise", lifecycle)
        self.assertIn("return result;", lifecycle)
        self.assertIn('.from("mindex_worship_sections")', patch)
        self.assertIn('.upsert([sectionRow], { onConflict: "id" })', patch)
        self.assertIn('.from("mindex_worship_elements")', patch)
        self.assertIn('.upsert([elementRow], { onConflict: "id" })', patch)
        self.assertNotIn(".delete()", patch)
        self.assertIn("await saveServiceItemPatch(serviceId, index, options)", committed)
        self.assertNotIn("await saveService(serviceId, options)", committed)

    def test_calendar_load_precedes_auto_worship_generation(self) -> None:
        load_worship = function_block(self.source, "hydrateSupplementalWorshipDataAfterInitialRender")
        self.assertLess(
            load_worship.index("loadCalendarData({ silent: true })"),
            load_worship.index("await ensureUpcomingPublicWorshipServices()"),
        )

    def test_worship_outline_child_titles_stay_single_line(self) -> None:
        styles = read_styles_css()
        match = re.search(r"\.service-outline-row--child \.service-outline-main strong\s*\{(?P<body>[^}]+)\}", styles)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("display: block", body)
        self.assertIn("white-space: nowrap", body)
        self.assertIn("text-overflow: ellipsis", body)
        self.assertIn("word-break: keep-all", body)
        self.assertNotIn("-webkit-line-clamp", body)
        self.assertNotIn("white-space: normal", body)

if __name__ == "__main__":
    unittest.main()
