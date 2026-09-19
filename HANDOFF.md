# Mindex Handoff

Last updated: 2026-08-09

Mindex is a church ministry operations app. It is not only a song database and not only a presenter. It should support weekly worship preparation, lyrics/scripture management, worship presentation, calendar, and references while sharing one Supabase-backed data model and one coherent UI system. Activities/event screens are deferred to standalone utilities unless promoted later.

This document is the canonical handoff for new Codex/Claude/GPT threads. Read this before editing. Keep changes conservative, verify them, and never undo unrelated local work.

Important behavior changes must be documented in the relevant Markdown contract
or decision log in the same change. If a later task disagrees with a documented
rule, update the document with the reviewed replacement instead of silently
reverting code to an older behavior.

For Worship/Presenter work, also read
`docs/worship-presenter-decisions.md`. Any durable behavior change must update
that decision log in the same change so a later task does not silently restore
an older rule.

For documentation routing, read `docs/README.md`. It separates current
contracts, deferred plans, and historical incident notes so old drafts do not
outrank reviewed decisions.

## Thread Ownership

- **UX thread** owns the user-facing experience: interaction flow, controller
  and presenter behavior, layout, visual states, accessibility, and UI-side
  validation. It may read the data contract to integrate existing fields, but
  must not change the Supabase schema, run data migrations, or rewrite curated
  production records.
- **Data thread** owns the internal data layer: Supabase schema, migrations,
  import/backfill jobs, data repair, canonical record rules, and production
  data integrity.
- Cross-boundary work starts with a handoff: UX records the user-facing
  requirement and expected fields; Data records the schema/data decision and
  reports the stable contract back. Neither thread silently broadens the other
  thread's scope.

## Repository And Runtime

- Repository: this repo root
- Current app: static HTML/CSS/JS app
- Main files:
  - `index.html`
  - `app.js`
  - `styles.css`
  - `supabase-schema.sql`
  - `scripts/worship-schema.sql`
  - `scripts/activities-schema.sql`
  - `scripts/reference-links-schema.sql`
- Local Supabase config:
  - `.env.supabase.local`
  - `.env.supabase`
- Preferred local server:
  - `python3 serve.py`
  - The app is often tested at `http://localhost:2300`.
- GitHub Pages deployment exists, but do not assume remote pages are updated immediately after local edits. Local verification comes first.

## Global Product Direction

Mindex should become a practical ministry workbench for church media and worship preparation.

Top-level product areas:

1. Worship / Presenter
   - The operational worship preparation and presentation area.
   - Must be reliable enough for live church use.
   - Presenter is the urgent priority.

2. Praise
   - Song database.
   - Canonical song pages with versions and forms.
   - Used by Worship/Presenter, but not subordinate to Worship.

3. Scripture
   - Bible database and lookup/search/copy workflow.
   - Used by Worship/Presenter, but not subordinate to Worship.

4. Home Utilities
   - Calendar, References, and similar support tools.
   - These should not feel like full database modules unless their functionality grows enough.

5. Activities / Event Screens
   - Activities are not exposed as a standing Mindex tab or home module for now.
   - Retreat games, quizzes, and event screens should be built as standalone HTML or small utilities when needed.
   - If a repeated workflow emerges, promote it back into Mindex deliberately.

## Strong Behavioral Rules

- Never overwrite already curated lyrics/forms/data unless explicitly asked.
- When syncing/importing from PPT, use PPT as reference material, not as authority over curated Mindex data.
- If existing Mindex data has been manually curated, preserve it.
- Do not hardcode real content that belongs in Supabase.
- Do not introduce dummy seed data into the app runtime.
- Do not invent song form splits. If uncertain, keep as `Lyrics` or leave for review.
- For hymns, official hymn titles should follow the Korean hymnal source requested by the user, not arbitrary first-line extraction.
- Children’s songs should generally be treated as audio-use lyrics, not manually split into song forms, unless explicitly curated.
- Do not treat a church department’s use of a song as the song’s intrinsic type.
- If one song has genuinely different canonical identities, split pages but provide related-song navigation.
- Keep the UI minimal. Remove decorative strokes, redundant labels, and explanatory copy that does not help live work.
- Use English for functional UI where natural, but worship content and Korean worship terms should remain Korean.

## Data Model Principles

The app is Supabase-centered. Local seeds should not be the source of truth for live content.

Song structure:

- `mindex_songs`
  - Canonical song metadata.
  - Title, subtitle, original title, hymn number, promoted metadata fields.
- Song versions
  - Version-specific title/name and lyrics/forms.
  - Version-level type tagging is important.
  - A song can have hymn/CCM/children-related versions without collapsing all versions into one type.
- Forms/units
  - Use structured forms when curated.
  - Use `Lyrics` when the lyrics are not meaningfully form-split.
  - Form labels should avoid unnecessary numbering when there is only one of that type.

Scripture structure:

- Bible books, chapters, verses, translations are database-managed.
- Copy behavior must support references and no-reference modes.
- Korean references should use spacing between book and chapter, e.g. `창 1:1`, not `창1:1`.

Service/Worship structure:

- Service types should use reviewed stable keys such as `sunday-first`, `sunday-second`, `sunday-main`, `sunday-afternoon`, `wednesday`, `friday`, and `monthly`.
- Special seasonal or temporary services can be grouped as special services instead of being promoted to permanent top-level categories.
- First Friday prayer meeting of each month is replaced by monthly first-day worship where applicable.
- Worship hierarchy is `Service > Section > Element > Slide`.
- Worship elements should be structured records, not loose text whenever possible.
- Praise elements should link to Mindex Praise records.
- Scripture elements should link to Mindex Scripture records or normalized references.
- Activity/game elements are deferred. Do not expose them in the main app shell until a repeated workflow justifies it.
- Detailed Worship terminology, template/type semantics, and examples live in
  `docs/thread-worship-presenter.md`.

Deferred activities structure:

- Activity Event: shared team/score context.
- Game: reusable playable unit.
- Team: name, color, score.
- Score Event: score change history.
- Presenter: projector-facing game display.
- Game-specific details should live in typed tables where useful, not all inside one JSON blob.

## Worship / Presenter Rules

The presenter must support real church operation.

Priority:

1. Live reliability.
2. Faithful worship sequence representation.
3. Fast correction before/during worship.
4. Clear controller UI.
5. Presentation output quality.

Current output concepts:

- Chromakey services:
  - Sunday 2nd, Sunday 3rd, Sunday afternoon, Wednesday, monthly first-day worship.
  - Special services vary.
  - Chromakey color is `#00ff00`.
  - Chroma range is narrow in the real broadcast setup.
- Non-chromakey services:
  - Department services and some prayer services.
  - Use background images.
  - Department worship backgrounds can rotate by two-month theme cycles.
- Youth and young adult department worship can use public-worship backgrounds where specified.

Presenter elements:

- Preparation video / waiting slide should be the first element.
- Praise section should group consecutive praise songs under one praise section when they belong to one led praise block.
- Praise leader belongs next to the praise section, not as the main worship leader.
- Hymns in 1st/2nd service may not have a praise leader.
- Scripture reading should be linked to scripture data and displayed with proper reference formatting.
- Apostles’ Creed is a faith-confession element whose content is the Apostles’ Creed.
- PPTX/Keynote import/reference should be an element type, not a replacement for Mindex data.
- Blank screen should remain an available element.
- Video should be an available element.
- Live scripture lookup during sermon is implemented: the live citation composer sits below the citation element's slide grid in the controller (see `docs/worship-presenter-decisions.md`, "Live Citation Composer And Scroll").
- Pre/post worship music player with volume control is implemented in the controller (`renderServiceMusicPlayer`, slot audio via `SERVICE_SLOT_MUSIC`; covered by `tests/smoke_friday_music.py`).

Presenter UI:

- Controller should feel closer to PowerPoint slide sorter / FreeShow controller, but simpler.
- Presenter control strip should avoid cramming all actions into one line. Keep primary launch/status/jump controls visually separate from music/live-input/navigation actions so controls do not collide at normal desktop widths.
- Presenter controls must be checked at reduced widths; wrapping is acceptable, horizontal overflow or overlapping controls are not.
- Slide thumbnails must match the actual output aspect ratio and layout. Do not enlarge a single slide just because it is alone.
- Thumbnail labels should not invent titles. Use actual section/form labels only when helpful.
- A section can contain multiple slides/forms; show section grouping without making it visually heavy.
- Song form labels can appear near the slide title/section label, but avoid duplicate text such as `주기도문 주기도문`.
- Do not show unnecessary panels like Current/Next if thumbnail control is the primary mental model.
- Keep slide navigation keyboard-friendly:
  - Space/Right/Down: next
  - Left/Up: previous
  - Number + Enter: jump
- Do not expose browser-native title tooltips for dense shortcut text.

PPT/reference rule:

- Existing worship PPTs are reference material for layout and service element structure.
- For past services, each PPT section/slide sequence should map closely to Mindex sections/elements.
- If slide numbers are not continuous within a block, treat them as separate elements unless the PPT clearly groups them.
- For complex cases such as intergenerational praise worship or 3rd-service special music, expect exceptions and manual slide editing.

## Praise Database Rules

Song identity:

- Same title does not always mean duplicate.
- Different title can still be same tune/history, but may need separate canonical pages with related links.
- Examples needing careful identity handling:
  - `살아 계신 주` / `하나님의 독생자` / `Because He Lives`
  - `이 믿음 더욱 굳세라` / `We Will Keep Our Faith Alive`
  - `저 들 밖에 한밤중에` and a children’s version
- Some same-title cases are homonyms, not duplicates. Check subtitle and original title before merging.

Metadata:

- Subtitle, original title, alternate title, artist, lyricist, composer, translator, album, track, scripture reference should be cleanly represented.
- Do not mix subtitle with original title.
- Parentheses in display are derived from metadata; avoid duplicated metadata display.
- `Other title` and `subtitle` may be conceptually close, but merge only when the meaning is truly the same.
- Be careful with English subtitle/original-title capitalization:
  - Main words capitalized.
  - Articles/prepositions/conjunctions lowercased unless first/last word.
  - Preserve user-confirmed exceptions.
- `Come and Celebrate` was user-confirmed as intended.

Forms:

- Supported types include at least:
  - `Lyrics`
  - `Verse`
  - `Pre-Chorus`
  - `Chorus`
  - `Bridge`
  - `Coda`
  - `Tag`
- If there is only one form of a type, avoid unnecessary numbering.
- If multiple of a type exist, use numbered labels.
- Explicit user-entered song forms are operator intent. Do not auto-insert
  omitted Bridge/Pre-Chorus/extra Chorus slides into a `manual`, `forced`, or
  template `default` form preset.
- Do not auto-split by location or repeated pattern without review.
- Children/audio-use lyrics should usually be `Lyrics`, not `Verse 1...Verse 6`.

Praise UI:

- The Praise tab should expose an in-context `곡 추가` action in the Praise detail area, not only through hidden/global chrome.
- New songs should be created as real Praise records with a default version, then opened immediately for metadata and lyric editing.
- Linked songs should be visible in the version comparison area as readonly linked columns, while editing remains scoped to the current song/version.

Review markers:

- Review should be meaningful and version-level where possible.
- A sidebar marker should make it clear which version needs attention.
- Do not use noisy double-ring icons; simple `!` is preferred.
- Do not soften or clear review markers from lyrics until spelling, song-form split, and two-line stanza grouping have all been reviewed.

## Scripture Rules

Search:

- Support direct references:
  - `창 1:1`
  - `창세기 1장`
  - `창세기 1장 1절`
  - `Gen 1:1`
  - `gen 1 4`
  - `암 4 3`
- Do not auto-switch OT/NT tabs merely because a search result belongs there.
- Text search should show results in the main area, not force the sidebar to become result previews.
- Result count should be accurate, not `100+` unless truly paginated that way with controls.

Copy:

- Multiple verse selection must support Cmd/Ctrl click and Shift range selection.
- Cmd/Ctrl+C should copy selected verses.
- If text inside a selected verse is manually highlighted, copy only the highlighted text.
- Copy format should allow reference/no-reference modes clearly.
- Korean copy example:
  - `히 11:6   믿음이 없이는...`
  - Reference, three spaces, verse text.
- English versions should support the same reference inclusion behavior.

Display:

- Book list should show concise metadata only.
- Chapter count can appear like song version count.
- Metadata panes should share visual grammar with Praise.

## Home / Calendar / References

Home:

- Home is not a dumping ground. It should clarify the hierarchy:
  - Worship as the main operational area.
  - Praise and Scripture as major resources.
  - Calendar and References as home utilities.
- Normal Home should prioritize module entry cards over a visible verse. Use data-managed UI verses for empty/loading/fallback states, not as the primary home content.
- Fallback when service data cannot load:
  - Psalm 27:14, NIV.

Calendar:

- Calendar is a home utility, not part of Praise/Scripture filtering.
- Church year starts should not include dates before 2025-11-30 in active calendar handling.
- Calendar should scroll to the current month when opened.
- Calendar header should show year and series where useful, e.g. `2026 · Series A`.
- Church-year fixed feasts should be visually present but not treated like editable Sunday services.
- Do not show unnecessary labels such as `57 Sundays` unless useful in context.

References:

- References are home utility links.
- Reference links are database-managed, not hardcoded.
- Grouping is needed.
- Groups should be editable and reorderable.
- Links should be editable inline from each card.
- Avoid category/description fields if groups already cover the organizational need.
- References should not have a strong independent accent color unless the design system later calls for it.

## Activities Direction

Activities are currently removed from the visible Mindex app shell. Build event/game screens as standalone HTML or small ad hoc utilities unless the user explicitly reopens the Activities module decision.

Scope:

- Rec games
- Quizzes
- Team games
- Retreat games
- Presenter display

Core data:

- Activity Event
- Game
- Team
- Score Event
- Presenter state

Initial game types:

- Puzzle Hunt
  - Puzzle board.
  - Piece discovery state.
  - Team that found each piece.
  - Score changes.
- Quiz
  - OX, multiple choice, short answer, motion.
  - Question display.
  - Answer reveal.
  - Team score updates.
- Physical Game
  - Timer.
  - Score.
  - Supplies.
  - Owner/person in charge.
  - Location.
  - Memo.

If Activities returns later, its empty verse should use the shared UI verse system rather than a one-off implementation.

## UI System Rules

Use `docs/design-system.md` for reusable UI tokens and design grammar. Use
`docs/ui-contracts.md` for screen-level shell, navigation, sidebar, empty-state,
calendar, reference, and presenter controller behavior.

Current UI baseline:

- App shell spacing uses the reviewed `24px` detail gutter, with new local
  spacing on 5px/10px steps unless an existing area is still on the legacy 4px
  shell rhythm.
- App UI typography follows the compact role ladder documented in
  `docs/design-system.md`; presenter output typography remains separate.
- Button geometry and icon sizing come from `mindex.design-tokens.js`.
- Sidebar/ambient utility actions should be quiet icon-only controls with
  accessible labels.
- Do not use retired 25px/20px gutter or 32x32 icon-button notes as current
  design guidance.

## Testing And Verification

Use the lightest verification that matches the risk, then broader tests before committing or deploying.

Always after JS/CSS edits:

```bash
cd "$(git rev-parse --show-toplevel)"
node --check app.js
git diff --check -- app.js styles.css index.html
```

Schema/data sanity:

```bash
cd "$(git rev-parse --show-toplevel)"
python3 tests/check_supabase_schema.py
python3 scripts/audit_mindex_content.py --json
```

App smoke:

```bash
cd "$(git rev-parse --show-toplevel)"
python3 tests/smoke_app.py
```

Presenter-specific checks:

- Open Worship/Presenter locally.
- Verify no horizontal overflow.
- Verify slide thumbnails maintain 16:9 and do not resize wildly when count changes.
- Verify double-click thumbnail starts presenter at that slide.
- Verify number input + Enter jumps correctly.
- Verify Space/Right/Down and Left/Up only affect presenter where intended.
- Verify non-chromakey services do not flash chromakey green.
- Verify fonts do not flash from one family to another after output opens.
- Verify output slide matches thumbnail, including background, title, lyrics, and labels.
- Verify output-window stop from the output screen does not leave stale heartbeat/monitor state in the controller.
- Verify image/score slides do not swap to a blank frame before the active image is decoded; keep the previous rendered frame until the image is ready.
- Verify lower-bar title/assignee output does not ellipsize long Korean titles or names; text should fit its column and stay vertically centered.

Praise-specific checks:

- Check song count loads correctly above 1000 if applicable.
- Check Hymns/CCM/Children filters and version-level tagging.
- Check review markers are meaningful and version-level.
- Check metadata editor displays the same data that appears in the list/detail display.
- Check copy/export outputs preserve brackets/original-title conventions.

Scripture-specific checks:

- Search `창 1:1`, `창세기 1장`, `Gen 1:1`, `gen 1 4`, `암 4 3`.
- Multi-select verses with Cmd/Ctrl and Shift.
- Copy selected verses with Cmd/Ctrl+C.
- Copy with and without references in Korean and English.
- Verify chapter-level copy.

Calendar/Home/Reference checks:

- Calendar opens at current month.
- Calendar does not show pre-2025-11-30 active church-year data unless intentionally in historical view.
- References list loads from DB.
- Reference group edit/reorder works.
- Home integrated search stays available when opening Calendar/References.

Activities checks:

- Activities should not appear in the app shell unless the module is intentionally revived.
- If revived, event/team/game tables must exist before exposing editing controls.
- Score changes should create score-event rows, not only mutate totals.

Deployment sanity:

- Localhost passing does not guarantee GitHub Pages has updated.
- If GitHub Pages does not show fresh changes, confirm commit/push and Pages build status.
- External access needs anon Supabase config to be available through approved link/config path.
- Do not expose service role keys in public links or client code.

## Current Split For Future Threads

Use two ownership tracks and hand off at the boundary:

1. Data thread
   - Supabase schema, migrations, imports/backfills, data repair, canonical
     Praise/Scripture records, service defaults, and production data integrity.

2. UX thread
   - App shell, controller/presenter interaction, layout, accessibility,
     loading states, and UI-side validation.

Presenter/Worship work often crosses both tracks. UX owns the user-facing
behavior; Data owns persisted contracts and production data changes. If a task
touches both, document the handoff instead of silently changing the other
track's assumptions.

Each thread should read this document first, then inspect current files before editing.

## Data Notes

- 2026-08-09: `예수 우리 왕이여` is intentionally split into two same-display-title songs.
  - Hymn: `hymn_no=38`, `praise_types=["hymn"]`, no subtitle/original title.
  - CCM: `praise_types=["ccm"]`, subtitle/original title `Jesus, We Enthrone You`, version `예수전도단 역`.
  - The CCM canonical uses internal variant key `normalized_title=예수우리왕이여::ccm` only to avoid the unique normalized-title collision; do not merge it back into hymn 38.
- 2026-08-09: Youth worship order intentionally places `광고` before `주기도문`.
  - Template order is `... 결단기도 → 청소년부 광고 → 주기도문 → 반별 모임`.
  - Existing youth services with both sections were updated in Supabase; older imported youth services without those sections were left untouched.

## Final Reminder

The user values practical church usability over technical cleverness. Make the app calmer, faster, clearer, and safer. Preserve curated data. When uncertain, inspect the source data and ask only when a wrong automatic edit could damage real worship material.
