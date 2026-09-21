# Worship Data Contract

This document describes the target Worship domain model and historical design
decisions. It is not proof of the deployed database constraints or atomic saves.
For the implementation baseline, write paths, compatibility fields and known
guarantee gaps, read [Current Persistence Contract](worship-persistence-current.md).
It follows `docs/thread-worship-presenter.md` and `scripts/worship-schema.sql`.

## Boundary

Worship owns only worship planning, worship structure, import review, and
presenter instances.

It must not own canonical Praise or Scripture content. Worship elements link to
Praise/Scripture records instead.

Older service tables are compatibility/import residue. Do not add new Worship
concepts by extending `raw_title`, `memo`, `fixed_items`, or `order_template`.

## Core Hierarchy

This is the relational target hierarchy. Current saves persist service documents
in `services.source_ref` as well as section/element rows; they do not write the
slide table as the authoritative slide document. See the current contract above.

```text
mindex_worship_services
  > mindex_worship_sections
    > mindex_worship_elements
      > mindex_worship_slides
```

## Module And Slot Contract Draft

This is a UX/Presenter-facing draft for the next data review. It does not add a
new visible hierarchy above sections by itself. A module is a behavior contract:
it owns which section/element slots are allowed, which inputs are required,
which Presenter rules apply, and how legacy records normalize.

Keep the user-facing controller mostly section/element based. The module/slot
layer should stabilize behavior internally so labels can change without moving
or reviving the wrong worship element.

```text
Service Type
└─ Module[] (internal behavior unit)
   └─ Section[] (visible order grouping)
      └─ Element[] (visible/editable item)
         └─ Slot identity (stable behavioral identity)
```

Proposed runtime fields:

```text
moduleKey
├─ internal behavior group, e.g. ready, praise, word, offering, sending
└─ optional at first; can be derived from section_key while migrating

slotKey
├─ stable element identity, e.g. offering.media, sermon.scripture
├─ should not depend on Korean display labels
└─ should become the primary projection/migration match key

label
└─ user-facing display name only, e.g. 봉헌 영상, 설교 본문

elementType / inputMode / outputMode
└─ keep their current meanings; slotKey explains why the element behaves that way
```

Initial slot examples:

| slotKey | Default label | section_key | elementType | inputMode | outputMode | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ready.waiting` | 대기 화면 | `ready` | `video` or `image` | `asset` | media | Label must not regress to `대기 영상`. |
| `prayer.silent` | 묵도 | `silent_prayer` | `plain_text` / `body` | `text` | body | Silent/opening prayer. |
| `faith.creed` | 사도신경 | `creed` | `body` | `text` | body | Fixed confession text. |
| `confession.prayer` | 참회기도 | `confession` | `plain_text` / `body` | `text` | body | Public-service repentance prayer. |
| `confession.assurance` | 사죄의 선언 | `confession` | `plain_text` / `body` | `text` | body | Optional paired element after confession. |
| `praise.welcome` | 환영 | `praise` | `title_content` | `text` | lyrics/clean | Optional in public-style praise blocks. |
| `praise.main` | 찬양 | `praise` | `praise` | `lyrics_db` / `score_db` / `manual_praise` | lyrics/score | Legacy bare praise slot when numbered praise is absent. |
| `praise.entrance` | 입례찬양 | `praise`, `entrance_praise`, `pre_scripture_praise` | `praise` | `lyrics_db` / `score_db` | lyrics/score | Entrance/pre-scripture praise. |
| `praise.song.N` | 찬양 N | `praise` | `praise` | `lyrics_db` / `score_db` / `manual_praise` | lyrics/score | Consecutive praise slots can be visually grouped. |
| `prayer.representative` | 대표기도 | `prayer` | `title_person` | `text` | title-assignee | 담당자 중심. |
| `word.reading` | 성경봉독 | `scripture_reading` | `scripture_body` | `scripture` | scripture | Must load normalized references before Presenter output. |
| `word.body` | 성경 본문 | `scripture_reading` | `scripture_body` | `scripture` | scripture | Legacy split body row paired with `word.reading`; uses the same scripture loader. |
| `hymn.main` | 찬송 | `hymn_praise` | `praise` | `score_db` / `lyrics_db` | score/lyrics | Shared public-service hymn slot. |
| `special.song` | 특송 | `special_song` | `praise` | `lyrics_db` / `score_db` / `manual_praise` | lyrics/score | Non-offering special song. |
| `sermon.title` | 설교 제목 | `sermon` | `title_person` | `text` | title-assignee | 제목 + 담당자. |
| `sermon.scripture` | 설교 본문 | `sermon` | `scripture_body` | `scripture` | scripture | Same scripture loader as reading, but sermon context. |
| `sermon.citation` | 인용 구절 | `sermon` | `scripture_body` | `scripture` | live/optional scripture | Optional; empty is not a required warning. |
| `sermon.media` | 자료화면 | `sermon` | `image` / `video` / `file` | `asset` | media/file | Optional dated/manual slot for sermon visuals. |
| `sermon.live_scripture` | 실시간 성구 송출 | `sermon` | `plain_text` | `config` / empty | live scripture | Controller helper slot; normally hidden from saved presentation flow. |
| `response.song` | 결단찬양 | `response_song` | `praise` | `lyrics_db` / `score_db` / `manual_praise` | lyrics/score | Optional by service type. |
| `response.prayer` | 결단기도 | `response_song` | `title_person` or `title` | `text` | title-assignee/title | Service templates decide whether 담당자 is needed. |
| `prayer.corporate.N` | 공동기도 N | `corporate_prayer` | `title_person` | `text` | title-assignee | Repeatable monthly prayer slots. |
| `prayer.corporate.song` | 기도찬양 | `corporate_prayer` | `praise` | `lyrics_db` / `score_db` | lyrics/score | Monthly prayer praise within corporate prayer. |
| `prayer.meeting.song.N` | 기도찬양 N | `prayer_meeting_praise` | `praise` | `lyrics_db` / `score_db` | lyrics/score | Friday/prayer-meeting praise slots. |
| `prayer.meeting.free` | 자율기도 | `prayer_meeting_praise` | `plain_text` / `title_person` | `text` | title/body | Free prayer slot. |
| `offering.praise` | 봉헌찬송 | `offering` | `praise` | `score_db` / `lyrics_db` | score/lyrics | Regular public services only unless explicitly enabled. |
| `offering.special` | 봉헌특송 | `offering` | `praise` | `lyrics_db` / `manual_praise` / `score_db` | lyrics/score | Optional dated/manual slot. |
| `offering.media` | 봉헌 영상 | `offering` | `video` / `image` | `asset` | media | Optional dated/manual slot; must not imply `offering.praise`. |
| `offering.prayer` | 봉헌기도 | `offering` | `title_person` | `text` | title-assignee | Usually required when offering module exists. |
| `announcements.main` | 교회소식 | `announcements` | `title` / `title_content` | `text` | title/body | For announcements, content fields should say 내용, not 제목. |
| `announcements.department` | 부서 광고 | `announcements` | `body` | `text` | body | Youth/young-adult department announcement body. |
| `announcements.media` | 참고 화면 | `announcements` | `image` / `video` / `ppt` | `asset` | media | Announcement reference image/video. |
| `announcements.new_family` | 새가족환영 | `announcements` | `plain_text` | `text` | title/body | New-family welcome when stored inside announcements. |
| `new_family.welcome` | 새가족환영 | `new_family` | `plain_text` | `text` | title/body | Dedicated welcome slot when separated from announcements. |
| `sending.doxology` | 송영 | `sending` | `praise` | `score_db` / `lyrics_db` | score/lyrics | Fixed by service type where applicable. |
| `sending.benediction` | 축도 | `sending` | `title_person` | `text` | title-assignee | 담당자 중심. |
| `sending.lords_prayer` | 주기도문 | `sending`, `lords_prayer` | `body` | `text` | body | Used when benediction is omitted or service type requires it. |
| `closing.visual` | 마무리 | `closing_visual` | `image` | `asset` | media | Closing image/default visual. |
| `closing.hymn` | 폐회찬송 | `closing_visual` | `praise` | `score_db` / `lyrics_db` | score/lyrics | Optional public 3rd-service-style slot. |
| `community.confession` | 공동체고백 | `community_confession` | `body` | `text` | body | Department/community confession text. |
| `fellowship.person` | 교제 | `fellowship` | `title_person` | `text` | title-assignee | 담당자 only in the current 3355 UX. |

Module options should handle occasional custom worship needs without turning
them into ad hoc label exceptions:

```text
OfferingModule
├─ praise: on/off
├─ special: on/off
├─ media: on/off
└─ prayer: on/off

SermonModule
├─ title: required
├─ scripture: optional/required by service type
├─ citation: optional
└─ media: optional
```

For intergenerational worship (`sunday-main` service with all-generation
schedule/alias), date-specific customizations should choose module options, not
patch display labels. Examples:

```text
2026-07-19 all-generation offering
├─ offering.special
├─ offering.media (감사 이미지)
└─ offering.prayer

2026-08-23 all-generation offering
├─ offering.media (봉헌 영상)
└─ offering.prayer
```

The 2026-08-23 shape must not generate `offering.praise` / `봉헌찬송`.

Migration/adapter priority:

1. Derive `slotKey` at runtime from `section_key`, `source_ref.label`,
   `element_type`, `input_mode`, and config/memo without changing schema.
2. Use `slotKey` before labels for projection matching, missing-content
   decisions, Presenter behavior, and template suppression.
3. Add a DB column or template-item field only after Data validates existing
   production rows and conflict constraints.
4. Backfill legacy records conservatively. Preserve manually curated input,
   linked Praise songs, linked Scripture references, and uploaded assets.

Adapter-first implementation note:

- Template blueprints may use `mindex_worship_template_items.slot_key` where
  present, but live instance rows are normalized through an adapter first.
- Live instances derive `_worshipSlotKey` at hydration time and persist the
  resolved value into `mindex_worship_elements.source_ref.slotKey`.
- The current schema has no live-element `slot_key` column. Do not probe,
  select, or write that proposed column. A future column migration must update
  this contract and the client together after the data audit.
- Imported/cached rows may still supply a top-level `slot_key`; normalize it
  into `source_ref.slotKey` before persistence and omit the nonexistent column.
- `source_ref.slotKey` is transitional metadata. It must not overwrite curated
  lyrics/manual slides, `song_id`, `song_version_id`, Scripture references, or
  uploaded media assets.
- Audit production rows with `migrations/2026-08-26-worship-slot-key-audit.sql` before any
  DB backfill or unique constraint migration.
- The eventual DB guard should prevent duplicate singleton slots per section
  while allowing repeatable materialized slots such as `praise.song.1` and
  `sermon.citation.1`. Date-specific media slots such as `offering.media` and
  `sermon.media` must remain valid even when they are absent from the base
  template.

## Data Structure

```text
mindex_worship_service_types (예배 타입)
├─ id / name / sort_order
└─ taxonomy only: not weekly content, not a template instance

mindex_worship_services (특정 날짜 예배)
├─ id / service_type_id / service_date
├─ created_at / updated_at
├─ title / service_alias / status
├─ worship_leader / praise_leader
├─ template link / source lineage
└─ owns ordered sections for that date

mindex_worship_sections (예배 순서 묶음)
├─ id / service_id / sort_order
├─ created_at / updated_at (required when creating a projected section)
├─ section_key
├─ title / person
├─ template_id / template_modified
└─ owns ordered elements

mindex_worship_elements (순서 안의 콘텐츠 단위)
├─ id / section_id / sort_order
├─ created_at / updated_at (required when creating a projected element)
├─ element_type
├─ title / person / body / scripture_reference
├─ song_id / song_version_id
├─ input_mode / content_state
├─ asset / config / source_ref
├─ template_id / template_modified
└─ may generate presenter slides

mindex_worship_slides (인스턴스 출력 프레임)
├─ id / element_id / sort_order
├─ created_at / updated_at
├─ layout / elementType / text / media
└─ instance-level slide override, not canonical Praise/Scripture data
```

## Public Worship Schedule

The public Worship schedule is operational metadata. Home uses these local
Korea Standard Time (KST) windows to identify an in-progress service before it
selects the next one. Keep this table and `SERVICE_TIME_WINDOWS` in `app.js`
in sync when the church changes a regular meeting time.

| Service type | Meeting window |
| --- | --- |
| 수요예배 (`wednesday`) | 19:10-20:30 |
| 금요기도회 (`friday`) | 20:00-22:00 |
| 월삭예배 (`monthly`) | 20:00-22:00 |
| 주일예배 [1부] (`sunday-first`) | 07:00-08:00 |
| 주일예배 [2부] (`sunday-second`) | 08:50-10:00 |
| 주일예배 [3부] (`sunday-main`) | 10:50-12:00 |
| 주일오후예배 (`sunday-afternoon`) | 13:20-14:30 |

Special and department services do not have a universal time window. Until a
time field is modeled for them, Home falls back to their service date.

Bulletin authoring UI is currently hidden. Keep the code path available for
later work, but do not expose the button/workbench in the app yet.

## Minister Defaults

Default ministers are materialized into generated worship elements, not inferred
at render time. Current operational defaults:

- `sunday-second` and `sunday-main`: offering prayer person is `김남영 목사`.
- `sunday-first`: sermon/worship leader rotates weekly from `2026-08-23`
  (`김광한 전도사`) and then `김석범 목사`. `김광한 전도사` weeks use
  `주기도문`; `김석범 목사` weeks use `축도`.
- `young-adult`: sermon person, offering prayer person, and benediction person
  are `김석범 목사`.

## Runtime Projection Tree

This is the structure the app should keep in mind when turning a recurring
service type into one actual worship instance and then into Presenter output.

Presenter output must be built from hydrated service data. Before
`preparePresenterService()` opens or jumps the output, the selected service
items, linked Praise records, linked Scripture payloads, and required score
manifest must be loaded. Do not render template-only placeholders into the live
Presenter first and then swap them later; that causes slide-count drift and can
move the current slide during refresh.

```text
Service Type (예배 타입)
└─ Service Template / Scaffold (예배 구조 템플릿)
   └─ Section[] (순서 묶음, ordered)
      ├─ sectionKey (구조 식별자)
      ├─ label / name (표시 이름)
      ├─ required / flex / repeatable (필수 / 유동 / 반복 가능)
      └─ Element[] (입력/출력 항목, ordered)
         ├─ elementType (입력/출력 타입)
         ├─ label / name (항목 이름)
         ├─ default_text / person / defaultSong / asset (기본값)
         ├─ formPreset / formHint / outputMode (출력 보조 규칙)
         └─ input mode (입력 방식)
            ├─ praise DB search (찬양 DB 검색)
            ├─ text/person input (텍스트/담당자 입력)
            ├─ scripture lookup/manual text (성경 조회/직접 입력)
            └─ asset picker/url (미디어/파일 연결)

Service Instance (특정 날짜 예배)
├─ service metadata (날짜, 타입, 인도자, 태그)
└─ Projected Service Item[] (템플릿에서 투영된 실제 순서)
   ├─ template identity (템플릿 정체성)
   │  ├─ _worshipSectionKey
   │  ├─ _worshipSectionTitle
   │  ├─ _worshipSectionOrder
   │  ├─ _worshipElementOrder
   │  ├─ _worshipTemplateProjected
   │  └─ _worshipTemplatePlaceholder
   ├─ user input (사용자 입력)
   │  ├─ raw_title
   │  ├─ assignee
   │  ├─ song_id / version_id
   │  └─ memo
   ├─ content state (콘텐츠 상태; stored in element config for now)
   │  ├─ default/input/song/asset exists
   │  │  └─ build Presenter slide
   │  ├─ no default and no user input
   │  │  └─ missingContent / Input Required (입력 필요)
   │  └─ deleted for this service only
   │     └─ templateSuppressed
   └─ Presenter Slide[] (출력 슬라이드)
      ├─ title-assignee
      ├─ song-title / lyrics / score
      ├─ scripture / liturgical-body
      ├─ image / video / file / audio
      ├─ blank
      └─ missingContent
```

## Worship Structures

These trees are structural order definitions. They are not theological
validation metadata.

```text
sunday-first
├─ 01. Ready / ready
│  └─ video / 준비
├─ 02. Creed / creed
│  └─ body / 사도신경
├─ 03. Praise / praise
│  ├─ praise / 찬양 1
│  ├─ praise / 찬양 2
│  └─ praise / 찬양 3
├─ 04. Confession Prayer / confession
│  └─ title / 참회기도
├─ 05. Scripture Reading / scripture_reading
│  └─ scripture_body / 성경봉독
├─ 06. Sermon / sermon
│  ├─ title_person / 설교 제목
│  ├─ scripture_body / 설교 본문
│  └─ live_scripture / 실시간 성구 송출
├─ 07. Response / response_song
│  └─ title / 결단기도
├─ 08. Offering / offering
│  ├─ praise / 봉헌찬송
│  └─ title_person / 봉헌기도
├─ 09. Announcements / announcements
│  └─ title / 교회소식
├─ 10. Sending / sending
│  ├─ praise / 송영, unless disabled
│  ├─ title_person / 축도, when enabled
│  └─ body / 주기도문, when enabled
└─ 11. Closing Visual / closing_visual
   └─ image / 마무리

sunday-second
├─ 01. Ready / ready
├─ 02. Creed / creed
├─ 03. Praise / praise
│  ├─ praise / 찬양 1
│  ├─ praise / 찬양 2
│  └─ praise / 찬양 3
├─ 04. Confession Prayer / confession
├─ 05. Prayer / prayer
│  └─ title_person / 기도
├─ 06. Scripture Reading / scripture_reading
│  └─ scripture_body / 성경봉독
├─ 07. Special Song / special_song
│  └─ praise / 특송
├─ 08. Sermon / sermon
├─ 09. Response / response_song
│  └─ title / 결단기도
├─ 10. Offering / offering
├─ 11. Announcements / announcements
├─ 12. Sending / sending
│  ├─ praise / 송영
│  └─ title_person / 축도
└─ 13. Closing Visual / closing_visual

sunday-main
├─ 01. Ready / ready
│  └─ video / 준비
├─ 02. Praise / praise
│  ├─ title_content / 환영
│  ├─ praise / 찬양 1
│  ├─ praise / 찬양 2
│  ├─ praise / 찬양 3
│  ├─ praise / 찬양 4
│  └─ praise / 입례 찬양
├─ 03. Confession Prayer / confession
│  └─ title / 참회기도
├─ 04. Hymn Praise / hymn_praise
│  └─ praise / 찬송
├─ 05. Prayer / prayer
│  └─ title_person / 기도
├─ 06. Scripture Reading / scripture_reading
│  └─ scripture_body / 성경봉독
├─ 07. Special Song / special_song
│  └─ praise / 특송
├─ 08. Sermon / sermon
│  ├─ title_person / 설교 제목
│  ├─ scripture_body / 설교 본문
│  └─ live_scripture / 실시간 성구 송출
├─ 09. Response / response_song
│  └─ title_person / 결단기도
├─ 10. Creed / creed
│  └─ body / 사도신경
├─ 11. Offering / offering
│  ├─ praise / 봉헌찬송
│  └─ title_person / 봉헌기도
├─ 12. Announcements / announcements
│  └─ title / 교회소식
├─ 13. Community Confession / community_confession
│  └─ body / 공동체고백
├─ 14. Sending / sending
│  ├─ praise / 파송찬송
│  └─ title_person / 축도
└─ 15. Closing Visual / closing_visual
   ├─ image / 마무리
   └─ praise / 폐회찬송

sunday-afternoon
├─ 01. Ready / ready
├─ 02. Praise / praise
│  └─ praise / 찬양
├─ 03. Silent Prayer / silent_prayer
│  └─ title / 묵도
├─ 04. Hymn Praise / hymn_praise
│  └─ praise / 찬송
├─ 05. Prayer / prayer
├─ 06. Scripture Reading / scripture_reading
├─ 07. Sermon / sermon
├─ 08. Response / response_song
│  └─ title / 결단기도
├─ 09. Announcements / announcements
├─ 10. Sending / sending
│  ├─ praise / 송영
│  └─ title_person / 축도
└─ 11. Closing Visual / closing_visual

monthly
├─ 01. Ready / ready
├─ 02. Praise / praise
│  ├─ title_content / 환영
│  ├─ praise / 찬양 1
│  ├─ praise / 찬양 2
│  ├─ praise / 찬양 3
│  ├─ praise / 찬양 4
│  └─ praise / 찬양 5
├─ 03. Prayer / prayer
├─ 04. Scripture Reading / scripture_reading
├─ 05. Special Song / special_song
├─ 06. Sermon / sermon
├─ 07. Response / response_song
│  ├─ praise / 결단찬양
│  └─ title_person / 결단기도
├─ 08. Corporate Prayer / corporate_prayer
│  ├─ title_person / 공동기도 1
│  ├─ title_person / 공동기도 2
│  ├─ praise / 기도찬양
│  ├─ title_person / 공동기도 3
│  └─ title_person / 공동기도 4
├─ 09. Offering / offering
│  ├─ praise / 봉헌찬양
│  └─ title_person / 봉헌기도
├─ 10. Announcements / announcements
├─ 11. Sending / sending
│  ├─ praise / 파송찬송
│  └─ title_person / 축도
└─ 12. Closing Visual / closing_visual
```

## Element Type Structure

The editor should expose the element types that are actually used by current
worship data and service config. Do not add speculative types to ordinary
worship templates.

Active editor options:

```text
찬양
성경봉독
성경 본문
제목
제목 / 담당자
제목 / 내용
본문
일반 텍스트
이미지
동영상
오디오
악보
파일
실시간 성구
빈 화면
```

Current data basis:

- `praise`, `title_person`, `scripture_body`, `plain_text`, `image`, `body`,
  `video`, and `scripture_reading` exist in `mindex_worship_elements.element_type`.
- `title`, `title_content`, and `live_scripture` are used through service
  config/memo and presenter generation.
- `audio`, `score`, and `file` are active operational types even when they are
  sparse in weekly data. They must keep their existing presenter/preview output.
- Do not expose unused legacy/scratch types such as `template`, `live_praise`,
  or `editable` in ordinary worship editing.
- Do not expose `auto` as an element type. Template defaults must be materialized
  into concrete element types and output modes when a worship service is created.
- Praise elements expose three input methods, independent from fullscreen or
  chromakey rendering:
  - `score_db`: "악보 불러오기" loads a Praise DB song and renders score output.
  - `lyrics_db`: "가사 불러오기" loads a Praise DB song and renders lyric output.
  - `manual_praise`: "직접 입력하기" stores the title and manual lyric slides on
    the worship element, without requiring `song_id` or `song_version_id`.
- `mindex_worship_elements.input_mode` is a DB-compatible bucket. Persist
  praise-specific modes (`score_db`, `lyrics_db`, `manual_praise`) as
  `praise_db` in this column so older Supabase constraints do not reject saves.
  Keep the exact choice in `content_state.inputMode` and `config.inputMode`.
- `mindex_worship_elements.input_mode` must allow at least:
  `''`, `praise_db`, `text`, `scripture`, `asset`, `config`, and `none`.
  Newer schemas may also allow `score_db`, `lyrics_db`, and `manual_praise`,
  but app persistence must not depend on that.

```text
Element Type (템플릿/저장 타입)
├─ praise (찬양)
│  ├─ input: Praise DB search, version, optional manual title
│  ├─ storage: song_id / song_version_id / raw_title / formPreset
│  ├─ outputMode=score: score image/file path
│  └─ presenter: song-title, lyrics, score image/file
├─ scripture_reading (성경봉독)
│  ├─ input: scripture reference
│  ├─ storage: scripture_reference or raw_title
│  └─ presenter: title-assignee / clean scripture reading
├─ scripture_body (성경 본문)
│  ├─ input: scripture reference + resolved Bible text
│  ├─ storage: scripture_reference/body payload
│  └─ presenter: scripture lower bar, reading form, sermon body, or citation
├─ title (제목)
│  ├─ input: text title
│  ├─ storage: title or raw_title/default_text
│  └─ presenter: title-assignee or title slide
├─ title_person (제목 + 담당자)
│  ├─ input: assignee/person text
│  ├─ storage: person/assignee plus optional title
│  └─ presenter: title-assignee / lower bar
├─ title_content (제목 + 내용)
│  ├─ input: first line title, following lines body
│  ├─ storage: title/body-like text in raw_title or memo note
│  └─ presenter: title-content / center text
├─ body (본문)
│  ├─ input: fixed/manual body text
│  ├─ storage: body/default_text/memo slides
│  └─ presenter: liturgical-body or lower-bar body chunks
├─ plain_text (일반 텍스트)
│  ├─ input: manual text
│  ├─ storage: raw_title/body-like text
│  └─ presenter: title-content/freeform text
├─ image (이미지)
│  ├─ input: asset picker/url
│  ├─ storage: asset.url
│  └─ presenter: image / media layout
├─ video (동영상)
│  ├─ input: asset picker/url
│  ├─ storage: asset.url + playback config
│  └─ presenter: video / media layout
├─ audio (오디오)
│  ├─ input: asset picker/url
│  ├─ storage: DB element_type=plain_text, config.elementType=audio,
│  │  asset.url + playback config
│  └─ presenter: audio/file preview
├─ score (악보)
│  ├─ input: score asset or hymn score manifest
│  ├─ storage: asset.url or linked Praise/hymn metadata
│  └─ presenter: score image slides or file slide
├─ file (파일)
│  ├─ input: asset picker/url
│  ├─ storage: asset.url
│  └─ presenter: file slide
├─ live_scripture (실시간 성구)
│  ├─ input: live scripture config
│  ├─ storage: memo/config
│  └─ presenter: live scripture bridge
└─ blank (빈 화면)
   ├─ input: none
   ├─ storage: element_type=blank
   └─ presenter: blank / blank layout
```

## Presenter Slide Model Contract

Presenter output must receive normalized slide models, not raw worship items.
The renderer should only care about this contract:

```text
Presenter Slide
├─ identity
│  ├─ id
│  ├─ elementId / sectionId
│  └─ sectionKey / sectionLabel / elementLabel
├─ render contract
│  ├─ elementType
│  ├─ layout
│  ├─ outputContext: chromakey | clean
│  └─ type: legacy render class only
├─ content payload
│  ├─ title / assignee / bodyText / text
│  ├─ marker / formKey
│  ├─ imageSrc / videoSrc / audioSrc / asset
│  └─ scriptureContext / reference metadata
└─ operational state
   ├─ missingContent / inputMode
   ├─ hiddenInPresentation
   ├─ suppressBackgroundImage
   └─ autoTrailingBlank / skipTrailingBlank
```

Allowed `layout -> elementType` pairs are intentionally narrow:

```text
blank
└─ blank

center_text
├─ title
├─ plain_text
├─ title_content
├─ title_assignee
├─ body_text
├─ scripture_reading / scripture_text
├─ praise
└─ freeform

lower_bar_text
├─ title_assignee
├─ praise
├─ scripture_reading / scripture_text
├─ plain_text / body_text
└─ freeform

media
├─ image
└─ video

file
├─ audio
├─ file
└─ freeform
```

When a new element type or layout is added, update the app contract and the
Presenter smoke test before relying on it in a worship template.

```text
Content State By Element (콘텐츠 상태)
├─ has default value
│  └─ filled, builds presenter output
├─ has user input
│  └─ filled, builds presenter output
├─ no default + no user input
│  └─ missingContent / Input Required with inputMode
└─ deleted for this service
   └─ templateSuppressed, excluded from projection
```

## Structural Risks

These are the problems exposed by the projection tree above.

- Runtime template authority: structural templates currently live in app code.
  That is now the only active runtime source, but it should eventually move to
  reviewed template data so service structures can be versioned and compared.
- Mixed template shapes: fallback templates may be strings, section-like
  objects, or section objects with nested elements. Normalize early so later
  code only sees one shape.
- Content state is now persisted on the element instance config, but it is still
  derived from loose fields: `raw_title`, `assignee`, `song_id`, `asset`, and
  `memo` feed the resolver before save. A later schema should promote this from
  JSON config into typed instance fields.
- Save code must validate generated section/element rows before Supabase
  upsert. When adding a new element type, input mode, or media kind, update the
  DB schema/migrations, `validateWorshipPersistenceRows`, and smoke coverage
  together so users do not see raw database constraint errors.
- Placeholder lifecycle is subtle: an unfilled template slot, a filled instance
  item, and a one-service deletion must never collapse into the same state.
- Presenter currently resolves too much: slide generation is doing content
  resolution, missing-content detection, and output rendering decisions. Those
  should be split into a resolver step and a renderer step.
- Labels still carry too much meaning: section labels are useful for display,
  but matching and behavior should rely on stable keys and element types.
- Input mode is now explicit in the runtime content-state payload and persisted
  on the service element config. It should eventually become a typed instance
  field so validation can happen before Presenter output without reading JSON
  config.

### `mindex_worship_service_types`

Recurring worship categories such as Sunday 1st service, Wednesday service,
Friday prayer meeting, youth worship, and special groups.

This is taxonomy, not service content.

Initial taxonomy lives directly in `mindex_worship_service_types`. Treat it as
reviewed Mindex taxonomy, not as a mirror of legacy service type rows. Do not
copy legacy `fixed_items` or `order_template` content into Worship.

### `mindex_worship_services`

One actual worship service instance on a date.

Use this for date, status, the canonical service title, an optional human-facing
`service_alias`, worship leader, praise leader, template link, and
source lineage. Do not add generic tags back: church-calendar occasions belong
to the calendar, while machine state belongs to typed keys in `source_ref`.

Presenter background is opt-in. Until a dedicated column exists, keep an
explicit source in `source_ref.presenter_background`; Presenter must not infer
or rotate backgrounds from service type, date, or season.

### `mindex_worship_sections`

Practical order blocks used by humans and Presenter: preparation, praise,
scripture reading, sermon, offering, announcements, benediction.

This is not a theological order taxonomy.

### `mindex_worship_elements`

The content-bearing unit inside a section: one praise song, Apostles' Creed,
one prayer topic, scripture reading, sermon title, video, blank, or imported
file reference.

Use `song_id` / `song_version_id` for linked Praise. Use `scripture_id` or
`scripture_reference` for Scripture. Do not copy curated lyrics or Bible text
into Worship unless it is a one-off body element.

### `mindex_worship_slides`

Materialized presenter frames for a specific worship instance.

Slides may be generated from an element/template, but the actual service needs
instance slides so last-minute edits do not mutate templates or canonical
Praise/Scripture data.

## Templates

```text
mindex_worship_templates
mindex_worship_template_items
```

Templates are reusable blueprints at four levels:

- `service`
- `section`
- `element`
- `slide`

Types are not templates. Types describe rendering or behavior. Templates
describe reusable structure/defaults.

Every creation path must allow no template.

If an instance diverges from a template, set `template_modified = true`. Do not
silently update the template.

### Versioning

Public worship starts with the shared `2026-q3` baseline, effective from
`2026-07-01`. The service type remains part of the template identity; the
version label marks the reviewed rule set shared by those type-specific
templates.

Do not create a new template version merely because a month changes. Create a
later version only for a lasting rule change, such as a revised recurring song
form or section structure, and give it its actual effective date. A one-off
service change remains an instance override and must not become a version.

The Worship tab currently treats template rows as an empty drafting surface.
Templates should be created from reviewed service decisions with the user. The
previous inactive draft templates derived from the PPT import were purged with
the imported Worship batch.

## Imports

```text
mindex_worship_import_sources
  > mindex_worship_import_candidates
    > mindex_worship_import_mappings
```

Imports are a staging/review pipeline, not canonical data.

### `mindex_worship_import_sources`

One source file or source batch: PPT, PDF, manual worship order, legacy service rows.

Store source identity, source path/hash, parse report, and raw payload.

- 2026-09-06 사용자 요청으로 archived setlist 183건의 `raw_payload.sections`를
  현재 candidate의 곡명·label·section key와 전수 대조한 뒤 제거했다.
  182건은 동일했고, 2026-06-21 청년부는 현재 candidate에 결단 `주 말씀 향하여`가
  추가된 상태로 원문의 모든 곡은 보존되어 있었다. 1,140개 candidate는 변경하지 않았다.
- `raw_payload.service`(인도자 포함), `source_ref`, `import_identity`, `schema_version`과
  source identity/hash, parse report는 유지한다. 인도자는 아직 이 metadata에서 읽는다.
  정리된 archive의 원문 곡 묶음을 단순 재수입으로 복원하지 않는다.
- 삭제 전 전체 source/candidate 백업은 Git 제외 경로
  `backups/setlist-raw-before-prune-20260906.json`에 보관했다.

### `mindex_worship_import_candidates`

Parsed possible service/section/element/slide records before approval.

Use this to review raw PPT section names, normalized titles, suggested Praise
links, suggested Scripture links, and confidence.

No current helper script should re-import the previous PPT-derived Worship rows
or convert legacy service rows directly into canonical services. Future imports
must land in the review tables first, then be accepted into
`Service > Section > Element > Slide` only after user review.

The previous legacy import batch was backed up and purged from worship canonical
tables: `mindex_worship_services`, sections, elements, slides, import staging,
mappings, and draft templates are intentionally empty. Older PPT-imported
service rows were also purged. `mindex_worship_service_types` remains as the
service taxonomy.

### `mindex_worship_import_mappings`

Approved or rejected application of a candidate to a real Worship target.

Mappings are the audit trail between import input and Mindex-owned Worship
records.

## Presenter Read Model

`mindex_worship_presenter_slides` is the read model for Presenter. It joins
service, section, element, and slide instance data in display order.

The app can later read this view directly once Worship data is populated.

## Song Form Defaults

Presenter song defaults should follow a verse/chorus cycle first, then tail
sections:

```text
V1-C-V2-C-...-B-Coda
```

Older metadata may still contain shapes such as `V1-V2-C-V3-Coda`. Treat those
as legacy default metadata and normalize them at read time to the cycle above.
Do not apply this rewrite to manual worship-item overrides; explicit manual
forms are operator intent.

Public special-song hymns keep their separate public preset:

```text
1절-후렴-2절-후렴-간주-마지막 절-후렴
```

## Naming Decision

Use `worship service` for the top-level instance name. The product area is
Worship, and `worship service` is the intended church-domain term.

## Bible Data Weight

The practical weight in Bible data is `mindex_bible_verses`, especially its text
search indexes. Hiding translations with `is_active = false` is not enough when
the goal is actual database size reduction.

As of 2026-08-02, KJV, NIV, and RSV must be preserved by user request. Korean
translations should also remain. The reviewed first prune target is limited to
unused foreign translations:

```text
asv
darby
nas
nkjv
nrs
rewebst
shinkaiyaku_3rd
webster
```

Those rows were backed up locally before pruning work:

```text
/Users/parkjihun/Code/Mindex/backups/bible-translation-prune-full-20260802-102547
```

The browser anon key only has read policy on `mindex_bible_translations` and
`mindex_bible_verses`, so actual pruning must run from Supabase SQL Editor or a
service-role/database connection. Use:

```text
scripts/migrations/prune-unused-bible-translations-2026-08-02.sql
```
