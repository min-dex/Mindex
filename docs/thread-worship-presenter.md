# Worship / Presenter Thread Guide

Read `HANDOFF.md` first, then `docs/worship-presenter-decisions.md`. Use this file as the short guide when a thread is mostly about Worship, service elements, presenter controls, presenter output, or order/PPT matching.

## Decision Log Discipline

`docs/worship-presenter-decisions.md` is the source for reviewed operational
rules that must survive across tasks. Update it with the same change whenever
you alter a template, required-input rule, default selection, output behavior,
or an intentional exception. Do not add a fallback that contradicts a recorded
decision.

## Scope

Focus on:

- Service dashboard and service element editing.
- Presenter slide building.
- Presenter controller controls and keyboard behavior.
- Presenter output route and projector-facing layout.
- Service templates and import/reference mapping when needed.

Avoid:

- Reworking Praise or Scripture internals unless needed for linked worship elements.
- Replacing curated song/scripture data from PPT imports.
- Adding decorative UI that does not help live service operation.

## Canonical Worship Model

Use this normalized model for new Worship/Presenter data work. Do not invent
missing service orders, section lists, or element presets when the source data is
ambiguous; ask the user and preserve curated service material.

Schema direction:

- New canonical Worship work should target `scripts/worship-schema.sql`.
- Data ownership and table responsibilities are summarized in
  `docs/worship-data-contract.md`.
- `mindex_worship_service_types` is the retained service taxonomy. Populate it
  directly from reviewed Mindex decisions, not from legacy service type rows.
- Older service tables are residue, not the Worship domain model. Do not use
  them as app fallback, template source, or import authority.
- The app/presenter read path loads Worship only. The previous PPT-derived
  Worship rows have been purged; rebuild Worship behavior on normalized worship
  tables.
- Use `mindex_worship_services` for the top-level instance name. The product
  area is Worship, and `worship service` is the intended church-domain term.
- Use `service_alias` for an optional date-specific public name such as
  `온세대 찬양예배` or `청소년부 제자헌신예배`. Do not restore generic service
  tags. Calendar occasions belong to the church calendar, praise-team names
  belong to the relevant praise section assignee, and machine state belongs to
  typed `source_ref` keys.
- Do not add new Worship concepts by expanding `raw_title`, `memo`, or
  `order_template`; create/import into the normalized Worship domain instead.

Hierarchy:

```text
Service > Section > Element > Slide
```

- `Service` is the top operational worship unit that drives the presenter.
  Examples: `주일예배 [1부]`, `주일예배 [2부]`, `주일예배 [3부]`,
  `수요예배`, `금요기도회`, `월삭예배`, department services, and special
  seasonal services. Recurring services can have stable service keys. Special
  services should normally stay in a special/seasonal grouping and receive
  per-event custom structure instead of becoming permanent top-level categories.
- `Section` is the practical first-level division of a service order. It is not
  the abstract theological flow of worship; it is the actual unit used to build,
  edit, and present the service. Examples include `준비`, `찬양`,
  `대표기도`, `교회소식`, `성경봉독`, `특송`, `설교`, `결단기도`, `봉헌`,
  a final `찬양`, `축도`, and department-only `교제`.
- `Element` is the content-bearing unit inside a section. An element can have
  `제목` (`title`), `담당자` (`person`), and `본문` (`body`), but none of those
  fields is globally required. Required fields depend on the element's type.
- `Slide` is the presenter frame/layout instance. Think of it like PowerPoint's
  layout choice: chromakey blank, chromakey lower-third text, fullscreen centered
  text, image fullscreen, imported PPT/PDF page, and so on.

Concrete hierarchy examples:

- `월삭예배 > 월삭 기도 > 기도 1 > 제목/담당자 slide`
- `월삭예배 > 월삭 기도 > 기도찬양 > praise title/body slides`
- `주일예배 > 찬양 > 가서 제자 삼으라 > praise title/body slides`
- `주일예배 > 신앙고백 > 사도신경 > body slides`
- `주일예배 > 봉헌 > 봉헌찬양 > praise slides`
- `주일예배 > 봉헌 > 봉헌기도 > 제목/담당자 slide`

`Element` examples:

- In a `찬양` section, each song such as `가서 제자 삼으라` is an element.
- In `신앙고백`, `사도신경` is an element with a title/body and usually no
  담당자.
- In monthly first-day worship prayer sections, `기도 1`, `기도 2`, `기도 3`,
  and `기도 4` can be elements with a prayer topic as `제목` and the prayer
  leader as `담당자`, but no body.
- `봉헌찬양` and `봉헌기도` are separate elements grouped under the `봉헌`
  section.

## Templates And Types

Templates and types are different concepts.

- `Template` is a reusable composition/content preset. Templates can exist at
  every level: `Service Template`, `Section Template`, `Element Template`, and
  `Slide Template`.
- `Type` is the element/slide output form, the file/rendering behavior, or the
  interaction mode used to produce presenter slides.
- A service instance is built by combining templates, but every level must allow
  free creation. When adding a service, section, element, or slide, include a
  `템플릿 없음` / no-template path.
- Editing an instance must not silently mutate the template. If an element,
  slide, imported file, or body content diverges from its
  template, display it like `템플릿명 (수정됨)` until the user explicitly saves a
  new template or updates the existing template.

Template levels:

- `Slide Template`: layout/render preset, similar to choosing a PowerPoint
  layout.
- `Element Template`: content fields and slide-building rules for one content
  unit, such as praise, prayer, Apostles' Creed, scripture reading, or video.
  Song-form defaults belong here when they apply to a specific content unit,
  e.g. monthly `봉헌 > 봉헌찬양` uses `V-C`, while `봉헌기도` has no song form.
- `Section Template`: ordered collection of element templates, such as an
  offering section containing offering song and offering prayer.
- `Service Template`: ordered collection of section templates for a recurring
  worship unit.

Initial type vocabulary:

- `Blank`: empty chromakey/fullscreen screen.
- `Plain Text`: simple text-only slide.
- `Title / Person`: title and 담당자 display.
- `Body`: body text display.
- `Praise`: loads a linked Praise record and creates a title slide plus song-form
  body slides.
- `Scripture Reading`: loads scripture from a normalized reference for formal
  reading.
- `Scripture Body`: displays prewritten or live-entered scripture/body text.
- `Image`: fullscreen image.
- `Video`: video playback.
- `Editable`: free slide editor for text/images and custom one-off layout.
- `PPT`: imported PowerPoint reference/output.
- `PDF`: imported PDF reference/output.

Chromakey/fullscreen is an output context, not by itself the content type. The
same content type may need separate chromakey and fullscreen slide templates.

## Presenter Rules

- Preparation video or waiting slide should be the first element.
- Consecutive praise songs that belong to one led block should be grouped under one praise section.
- Praise leader belongs next to the praise section, not as the main worship leader.
- Hymns in 1st/2nd service may not have a praise leader.
- Scripture reading should link to Scripture data or normalized references.
- Apostles' Creed is a faith-confession element.
- PPTX/Keynote import/reference should be an element type, not the source of truth.
- Blank screen and video should remain available elements.

## Controller UI

- The controller should feel like a simple PowerPoint/FreeShow slide sorter.
- Slide thumbnails must keep the actual output aspect ratio.
- A single thumbnail must not resize wildly just because it is alone.
- Labels should use actual section/form labels and avoid duplicate text.
- Avoid Current/Next panels when thumbnail control is the main mental model.
- Keyboard behavior:
  - Space, Right, Down: next.
  - Left, Up: previous.
  - Number plus Enter: jump.

## Output

- Chromakey services use `#00ff00`.
- Chroma range is narrow in the real broadcast setup.
- Non-chromakey services use black output unless the service explicitly provides a presenter background source.
- Explicit presenter background sources are honored as-is; do not infer or rotate backgrounds from service type, date, or season.
- All Presenter previews and output themes use the self-hosted Freesentation family; do not introduce department-specific font overrides.

## Verification

For presenter work, run at least:

```bash
cd "$(git rev-parse --show-toplevel)"
node --check app.js
git diff --check -- app.js styles.css index.html tests/smoke_app.py tests/smoke_worship_presenter.py
python3 tests/smoke_worship_presenter.py
```

For broader app changes, also run:

```bash
python3 tests/smoke_app.py
```

Manual checks when changing live presenter behavior:

- No horizontal overflow.
- Thumbnails stay 16:9 and stable.
- Double-click thumbnail starts presenter at that slide.
- Number input plus Enter jumps correctly.
- Space/Right/Down and Left/Up only affect presenter where intended.
- Non-chromakey services do not flash chromakey green.
- Output slide matches thumbnail in background, title, lyrics, and labels.

## Historical Implementation Notes

The following notes preserve earlier implementation context, not a complete
description of today's UI. In particular, old topbar-module placement and strict
linked-song-only wording must not override later reviewed controller/input
decisions. Use [current decisions](worship-presenter-decisions.md),
[UI contracts](ui-contracts.md), and the
[live citation contract](citation-live-output.md) for current behavior.

2026-07-08:

- Presenter output now warms nearby service/live-praise/image slides in the output
  window so long hymn-score or image sequences are less likely to flicker when
  moving between slides.
- Presenter controls can show image warmup progress while an output window is
  connected.
- Hymn auto form presets include a trailing `Coda` form when the linked praise
  version provides one, preserving the rule that each hymn verse is followed by
  the chorus.
- If the presenter output window has fallen out of fullscreen, `Space` or
  `Enter` first requests fullscreen again instead of advancing the slide.
- Presenter smoke coverage now checks long hymn-score warmup ordering, score
  safe-area rendering, hymn Coda output, and a less flaky output key-sync wait.
- Hymn-score asset generation now treats the source PPTX as a native rendered
  asset source. Prefer PowerPoint-exported `Slide*.png` folders with
  `render_hymn_score_assets.py --exported-slide-dir`; if those are unavailable,
  the script can fall back to LibreOffice PDF export plus Poppler page rendering.
  It no longer reconstructs PPT text boxes with PIL, which avoids broken label
  weight, transparency, and layout drift in score slides.
- Worship authoring and Presenter control are now separate topbar modules.
  `Worship` owns service/template composition and metadata, and
  item editing. `Presenter` owns recent-service launch, slide outline, live
  controls, shortcuts, and output-window state.
- Shared service data still loads through the same adapter, but render paths now
  branch through `service` versus `presenter` so controller-only shortcuts and
  output state do not run from the authoring screen.
- Preparation media can be split by `presenterRole`: `ready` for the generic
  preparation item, `waiting_loop` for looping waiting media, `intro` for a
  one-shot countdown/opening video, and `still` for the first still screen.
  `intro` video defaults to non-looping playback and advances to the next
  presenter slide when playback ends; waiting media does not auto-advance.
- A waiting/preparation slide can set `playback.autoAdvanceAt`, e.g. `10:40`
  on the service date or a full ISO timestamp. Presenter output arms a timer
  only for the active slide, clears it on slide changes, and sends `next` at
  the scheduled time. This supports `waiting_loop -> intro -> first worship
  screen` flows such as a 10-minute countdown before a 10:50 service start.
  When output starts late, presenter video uses the previous slide's
  `autoAdvanceAt`, explicit `playback.startAt`, or `autoAdvanceAt -
  durationSeconds` to seek into the correct point in the intro; if the intro
  window has already elapsed, it advances to the next worship screen.
- Narrow authoring layout now uses the same responsive editor rules as the old
  dialog and keeps dense fields inside the viewport.
- Non-chromakey output no longer infers A/B/C backgrounds from service type or
  date. It stays black unless the service explicitly provides a presenter
  background source.
- Home is now a workbench-style entry screen: next worship service, direct
  shortcuts, and utilities are grouped by actual user workflow instead of a
  decorative card layout.
- Page titles across Home utilities, Worship, Presenter, Calendar, and References
  now share the same title token so tab starts and
  header scale stay consistent.
- Worship authoring now surfaces the `Service > Section > Element > Slide`
  hierarchy at the top of the editor and separates service metadata, section
  templates and praise item editing into distinct authoring panels.
- Presenter title/assignee slides treat `인도자`, `담당자`, and similar
  generic placeholders as non-output data. If a worship-led element such as
  `봉헌기도` needs a person, Presenter uses the service `worship_leader` value
  rather than the praise leader or a generic placeholder. Board subgroup heads
  show element label plus real content and suppress duplicate label/title text.
- Worship authoring now hides non-weekly template fields from service item rows.
  Preparation items no longer expose unused title/person inputs, worship-led
  defaults such as `봉헌기도` use editable service-leader fallback text, strict
  praise items require a linked Praise record before presenter output, and
  scripture body rows resolve valid references into lower-bar verse slides while
  blocking unnormalized free text from output.
- Strict praise/score inputs still require a linked Praise record, but typing a
  uniquely resolvable hymn number/title now immediately promotes the input to
  `song_id` plus the preferred score `version_id`. Do not restore the old
  behavior where score rows kept raw search text only; it leaves valid 1/2부
  hymn-score entries showing `입력 필요`.
- Sunday afternoon dedication services are not just renamed afternoon services:
  when a service title/tag/source marks `헌신예배`, the afternoon template must
  include `특송` after `성경봉독` and `봉헌` after `결단`, so the input screen and
  presenter board expose those editable slots in the right order.
- `참고 화면` is a real presenter-media element, not a note or a placeholder.
  The 설교 and 광고 section headers can add one; it accepts image, video, or audio.
  Uploaded files are stored in the public `mindex-worship-media` Supabase Storage
  bucket (currently 50 MB per file) and the persisted public URL is the same source used by controller
  preview and presenter output. Image/video render as media slides. Audio uses
  the existing controller `음악` player when its slide is selected, so playback
  remains under the operator's explicit control.
- Praise-like elements (`찬양`, `특송`, `결단찬양`, etc.) may carry a controller-only
  header audio attachment in `memo.audioAsset`. This is for quick MR/BGM playback
  beside the element header and must not change presenter slide rendering,
  score/lyrics input mode, or `memo.asset` media-element behavior.
