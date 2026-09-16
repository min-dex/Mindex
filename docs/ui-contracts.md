# Mindex UI Contracts

Read `HANDOFF.md` first. This file is the short UI contract for Codex threads so layout work does not require rediscovering the same app-shell rules.

## Shell

- Detail pane page padding: `25px` on all sides on desktop and narrow layouts,
  unless a feature has an explicit fullscreen/presenter reason to override it.
- New app-layout spacing should use the shared `5px`/`10px` rhythm instead of
  adding one-off numbers.
- App UI typography is separate from presenter output typography. Use the
  compact app scale by role: labels `12px / 700`, supporting metadata
  `12px / 500`, normal rows and form controls `14px / 600`, card titles
  `16px / 700`, and page titles `20px / 700`.
- Weight should communicate hierarchy, not decoration: primary labels and
  titles may use `700`, routine editable values should usually use `600`, and
  helper/meta text should stay at `500` unless it is an actionable label.
- Icon sizing follows a separate glyph rhythm because Lucide-style interface
  icons are optically tuned around `16px`: use `16px` for normal icons, `14px`
  for dense helper icons, and `20px` for large home/action tiles. Topbar buttons
  stay `40px`; normal icon buttons stay `35px`; dense inline controls may use
  `30px` or `28px` only when they sit inside compact editor/tool rows.
- Sidebar open or closed must not change the detail pane gutter.
- Topbar icon buttons are square, `40px` by `40px`.
- Sidebar toggle, home, theme, and save controls should share the same button geometry.
- Left topbar actions align to the left rail edge. Right topbar actions align to
  the right rail edge because they belong to the app-level utility side.
- Mindex brand/home buttons may navigate home, but should not add hover motion.
- Avoid horizontal page overflow on desktop and mobile.

## Color And Surfaces

- Keep `accent`, `warn`, and `danger` semantically distinct in both themes:
  accent is primary/selection, warning is incomplete attention, and danger is
  destructive or failed work. Do not make them aliases of one another.
- All normal-size text on a solid UI surface must meet at least WCAG AA `4.5:1`.
  Accent-colored text needs a text-safe accent token; do not reuse a low-contrast
  decorative fill color for labels or buttons.
- Keyboard focus must remain conspicuous in both themes: use a `2px` accent
  outline with an offset rather than a low-contrast neutral hairline.
- Shell controls should stay neutral. Theme, navigation, and disabled save
  buttons should not pull accent color into the app chrome.
- Use accent for active/primary/data emphasis, such as selected rows, brand
  accent, enabled primary save/present actions, and linked/reference states.
- Search should read as an independent surface on the sidebar through background
  contrast, not a visible stroke. Focus may strengthen the surface tone without
  adding an accent or border line.

## Navigation

- 예배 검색 결과는 `7월 19일 주일예배 [3부]`처럼 날짜와 정규 예배 종류를
  한 줄로 표시한다. 요일, 예배 별명, 설교 미리보기는 검색 결과 행에 붙이지 않는다.
  검색 매칭과 클릭 시 열리는 예배는 기존 동작을 유지한다.

Primary app modules:

1. `service` - Worship and presenter work.
2. `praise` - Song database.
3. `scripture` - Bible/search/copy tools.
4. `calendar` - Home utility.
5. `references` - Home utility.

Home hierarchy:

- Worship is the primary operational area.
- Home shows the week dashboard: `이번 주 예배` plus `다가오는 예배`.
- The Worship/Service tab opens to `전체 예배` by default. `이번 주 예배` remains
  a secondary sidebar panel, not the default Worship tab landing screen.
- Praise and Scripture are major resources.
- Calendar and References are home utilities.
- Template structure is an internal management concept. Do not surface it in
  the ordinary home/sidebar worship path unless the user is explicitly editing
  templates.
- Prefer direct action labels over explanatory copy in operational screens. If a
  button already says what will happen, do not add a nearby sentence that repeats
  it.

Inactive module tabs should stay visually quiet. Active tabs may show a clearer label and accent.

- When two or more page tabs are open, tabs can be dragged to reorder them.
- The active page remains active after reordering, and the new order is persisted with the existing tab session state.
- The add-tab control is not part of the draggable sequence.
- Page tabs use `13px / 600`; the active tab uses `700`. The add-tab control is
  a `40px` square command with a direct neutral hover surface and a centered
  `16px / 1.5` Lucide Plus icon.

## Sidebar

- Sidebar width should stay consistent unless a module has a strong reason.
- Sidebar row padding should align visually with the sidebar toggle x-position.
- Sidebar content should feel relaxed, not cramped.
- Home utility pages should keep the integrated Mindex search available.

## Empty States

- Home, Praise, and Scripture empty states should use the shared UI verse system when available.
- Do not hardcode live content into empty states.
- Setup errors may name the required SQL file, but should not become a visually separate design system.

## References

- Reference links are database-managed.
- Groups are the organizational model. Avoid category/description UI unless there is a new product need.
- Groups should be editable and reorderable.
- Link move buttons inside a group should reorder only within that group.
- Group move buttons should move the whole group.
- References should remain visually neutral unless the design system intentionally changes.

## Calendar

- Calendar is a home utility, not a Praise or Scripture filter.
- Active calendar handling starts at `2025-11-30`.
- Opening Calendar should scroll to the current month when data exists.
- Header summary may show church year and series, such as `2026 · Series A`.
- Fixed feasts may appear visually, but should not behave like editable Sunday services.

## Presenter

- With the right panel open, the start command beside the preview is primary;
  the left start command remains available with a neutral surface. Closing the
  right panel restores the left command's accent. Stop styling and button
  dimensions do not change with this hierarchy.
- Bulk worship input remains expanded. Keep drafts, inline per-line examples,
  focus and save/apply behavior intact; do not add automatic collapse.

Presenter details live in `docs/thread-worship-presenter.md`. Keep shell edits out of presenter internals unless required for integration.

- Chromium may suppress CSS transitions inside the `service` and `presenter`
  modules to keep worship loading, thumbnail sizing, and live controls stable.
  Keep that safeguard scoped to those operational modules; home and resource
  modules should retain their normal interaction feedback.
- Dense presenter status, navigation, help, and section metadata must still use
  the shared `11px` label and `12px` metadata scale. Reserve smaller text for
  nonessential thumbnail annotations only.

## Individual Save Draft Retention

- The header save command must preserve the editor DOM, current draft, focus,
  and text selection while its response is pending and after failure. Failure
  re-enables retry; retry reads the current fields, not the previous snapshot.
- An older successful response must leave newer typing marked modified. Only
  success for an unchanged input snapshot may display saved.
- Repeated identical feedback does not rewrite matching DOM text/attributes.
  Compare each target value, rather than skipping solely on editor status, so a
  replaced header/status node still receives its current label and busy state.
- Cross-app source: STUDEX `dbSaveEntry` retains drafts when its conditional
  update is not confirmed; VITEX `backup_once` distinguishes local verification
  from cloud upload. MINDEX adopts the confirmation boundary, not their storage
  mechanisms or an implied server transaction guarantee.
- Regression: `python3 tests/smoke_header_save_draft_retention.py` exercises the
  real header renderer and commit/feedback lifecycle in Chromium and WebKit,
  with deferred persistence doubles. It does not verify production writes,
  cross-client conflict rejection, durable recovery, or multi-row atomicity.

## Assignee Terminology

- 전역 UI에서 개인·단체 공통 입력 label과 placeholder는 `담당`으로 통일한다.
  `title_person` 유형의 표시명은 `제목 / 담당`이다. 특송도 같은 용어를 사용한다.
- `인도`, `설교` 등 구체적인 역할명은 유지한다. 옛 담당 명칭을 위한 레거시 별칭과
  기본값 판별은 두지 않는다. 예배 DB 10개 테이블 전수 검사에서 옛 명칭이 없음을
  확인한 뒤 해당 호환 처리를 제거했다 (2026-09-06).
- 내부 `person`/`assignee` 필드와 DB 값은 이 용어 정리를 위해 변경하지 않는다.
