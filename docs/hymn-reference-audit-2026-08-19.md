# Hymn Reference Audit - 2026-08-19

## Scope

- Reference: 하나성경 hymn pages
- 새찬송가: 1-645
- 통일찬송가: 1-558
- MINDEX tables: `mindex_songs`, `mindex_song_versions`, `mindex_version_units`
- Read-only: no Supabase rows were inserted, updated, or deleted
- Reference lyrics were compared in memory and were not persisted in the report

## Verification

- Supabase schema check: no issues or warnings
- Reference pages checked: 1,203
- Reference fetch failures: 0
- Audit findings: 621

| Book | Finding | Count |
| --- | --- | ---: |
| 새찬송가 | Title review candidate | 1 |
| 새찬송가 | Chorus structure review candidate | 22 |
| 새찬송가 | Amen structure review candidate | 1 |
| 새찬송가 | Low lyric similarity candidate | 23 |
| 통일찬송가 | Numbered version not found | 79 |
| 통일찬송가 | Version found but lyrics empty | 452 |
| 통일찬송가 | Duplicate numbered version candidate | 4 |
| 통일찬송가 | Title review candidate | 36 |
| 통일찬송가 | Chorus structure review candidate | 1 |
| 통일찬송가 | Amen structure review candidate | 1 |
| 통일찬송가 | Low lyric similarity candidate | 1 |

새찬송가 645곡은 모두 MINDEX song/version/lyrics records가 존재했다. 통일찬송가의
`not found` 결과는 통일 장 번호를 version metadata에서 찾지 못했다는 뜻이며, 곧바로
곡 자체가 DB에 없다는 뜻은 아니다.

## Review Rule

Do not auto-apply findings. 하나성경 새찬송가 19장 제목은 `찬양하는 소리 있어`로
표시되지만 MINDEX의 `찬송하는 소리 있어`가 맞을 가능성이 높다. 제목, 맞춤법,
줄바꿈, 새찬송가-통일찬송가 연결은 다른 대조 자료와 교차 확인한 뒤 확실한 항목만
수정한다.

## Confirmed Title Repairs

Seven clear typographical errors were cross-checked and repaired in
`mindex_song_versions.curated_version_name` and `version_label` only:

| 통일찬송가 | Before | After |
| ---: | --- | --- |
| 307 | 공중 나는 새르 보라 | 공중 나는 새를 보라 |
| 326 | 죄집에 눌린 사람은 | 죄짐에 눌린 사람은 |
| 346 | 값비산 향율을 주께 드린 | 값비싼 향유를 주께 드린 |
| 438 | 예부터 도움 도시고 | 예부터 도움 되시고 |
| 455 | 주 안에 이는 나에게 | 주 안에 있는 나에게 |
| 474 | 이 세상에 금심된 일이 많고 | 이 세상에 근심된 일이 많고 |
| 486 | 주 에수여 은혜를 | 주 예수여 은혜를 |

The repair used exact old-value guards and required one matching version per
hymn number. Post-repair schema checks had no issues or warnings. A targeted
reference audit found no remaining title mismatch for the seven versions, and
the deployed GitHub Pages praise list showed every corrected title with none of
the old spellings present.

## Confirmed Duplicate Mapping Repairs

Four duplicate 통일찬송가 mappings were cross-checked and repaired:

| 통일찬송가 | Final 새찬송가 | Removed or moved from |
| ---: | ---: | --- |
| 132 호산나 호산나 | 141 | Removed empty version from 143 웬말인가 날 위하여 |
| 548 주 기도문 영창 | 636 | Removed alias from 635 and moved the official version from 635 to 636 |
| 549 우리 기도를 | 631 | Removed empty version from 632 주여 주여 우리를 |
| 550 주 너를 지키시고 | 638 | Removed empty version from 639 주 함께하소서 |

All four deleted versions had zero `mindex_version_units`. The operation reduced
`mindex_song_versions` from 1,640 to 1,636 while `mindex_version_units` remained
at 4,186. Post-repair schema checks had no issues or warnings, the targeted audit
reported no duplicate mappings, and the deployed praise list showed two versions
only on 새찬송가 141, 631, 636, and 638.

## New York Bethel Cross-check

The [New York Bethel Church index](https://nybethel.org/240) covers all 645 new hymns, but its text table has
several shifted or mistyped old-hymnal numbers. Candidate mismatches were therefore
checked against the linked score image, the local corrected lyric filename, and the
`(통 nnn)` header rendered in the Mindex score asset.

Three existing versions were confirmed as attached to the adjacent same-title hymn
and moved without changing their IDs or lyric units:

| 통일찬송가 | Before | After |
| ---: | ---: | ---: |
| 2 | 새찬송가 4 | 새찬송가 3 |
| 36 | 새찬송가 37 | 새찬송가 36 |
| 114 | 새찬송가 108 | 새찬송가 114 |

새찬송가 143↔통일찬송가 141 and 새찬송가 343↔통일찬송가 443 are supported by
the same metadata sources. The canonical record for 새찬송가 143 already contained
a hidden six-unit version with lyrics identical to 통일찬송가 141. That legacy
version was removed, and 통일찬송가 141 was rebuilt from the curated 새찬송가 units
so both hymn versions use the same line-break convention without importing lyrics.
새찬송가 343↔통일찬송가 443 uses different old-hymnal wording. The verified old
wording was stored as a separate 통일찬송가 version with modern Korean spacing and
the same four-line verse layout used by the curated 새찬송가 version.
Automated reference matches remain `pending`/`needs_review` until a person reviews
them; external cross-checking alone does not clear the visible review badge.

## Spacing-only Identical Lyrics

The 452 mapped unified versions with no lyric units were checked against both
Hbible editions. A version qualified only when the current MINDEX 새찬송가 text
matched the 새찬송가 reference and the two reference editions differed solely in
whitespace, line breaks, verse-number prefixes, or chorus structure labels.
Punctuation and every other character remained significant, so `노랫소리` and
`노래 소리` were treated as different lyrics.

| Result | Count |
| --- | ---: |
| Eligible spacing-only identical versions | 50 |
| Edition lyric differences | 339 |
| MINDEX 새찬송가/reference differences | 63 |

The 50 eligible versions contain 226 units. They are copied from the existing
curated 새찬송가 units without changing text, labels, or line breaks. Every target
version is set to `pending`, and every copied unit is set to `needs_review` with no
review timestamp. This operation does not approve imported lyrics automatically.

Both hymnals follow modern Korean spacing in Mindex. Edition-specific words and
endings remain distinct, while spacing-only differences are not preserved. For
example, 통443 keeps `맙소서`/`줍소서` but uses the principle forms `시험받을`,
`지켜 줍소서`, `맡아 줍소서`, and `의지하리니`.

The same cleanup removed all 58 remaining hidden `기본`/`public` hymn versions and
their 231 units after confirming that every affected hymn had a formal 새찬송가
version and none of the legacy versions was referenced by a worship element.
The schema source now also records the two production uniqueness constraints on
`(canonical_song_id, version_order)` and `(canonical_song_id, lyric_signature)`.

The same full local-score pass found one more existing metadata error among the
appendix Amen settings. The rendered score for 새찬송가 643 explicitly says `통555`,
while Mindex labeled its unchanged threefold-Amen unit as `통556`. The local score,
the New York Bethel score, and the Hbible lyric reference agree on 새643↔통555, so
the existing version metadata was corrected from 556 to 555. 새찬송가 642 has no
old-hymnal number in its local score and was not assigned one by inference.
After the correction, all 480 mappings confirmed by corrected filenames or explicit
local-score headers had zero wrong links, zero missing versions, and zero duplicated
unified numbers.

## Commands

The final strict 1,203-page pass and confirmed lyric repairs are documented in
`docs/full-hymn-audit-2026-08-19.md`.

```sh
python3 tests/check_supabase_schema.py
python3 -m unittest tests.test_audit_hbible_hymns
python3 scripts/audit_hbible_hymns.py --book both \
  --workers 4 --delay 0.05 \
  --output /tmp/mindex-hymn-audit-full.json
python3 scripts/audit_identical_hymn_lyrics.py --workers 4 --timeout 30 \
  --retries 2 --output /tmp/mindex-identical-hymn-candidates.json
python3 scripts/backfill_identical_unified_hymn_lyrics.py \
  --report /tmp/mindex-identical-hymn-candidates.json --apply
```

## Completed repair tool cleanup — 2026-09-22

The one-time repair tools were removed after their final conditions were checked
against the current production database. Their dedicated tests were also removed;
reusable audits, import tools, schema sources, and application regression tests remain.
No database records were changed by this cleanup. Historical repair implementations
are available in Git at `73dc5a45:scripts/`; do not rerun them as current maintenance.
