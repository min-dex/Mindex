# Full Hymn Audit - 2026-08-19

## Scope

- 새찬송가 1-645 and 통일찬송가 1-558
- Reference: 하나성경 hymn pages
- Production DB: `mindex_songs`, `mindex_song_versions`, `mindex_version_units`
- Strict lyric comparison ignores only whitespace, line breaks, verse-number prefixes,
  and Mindex unit labels. Punctuation and all other characters remain significant.
- All 1,203 reference pages were fetched successfully before and after repair.

## Coverage

| Item | Count |
| --- | ---: |
| 새찬송가 records with lyrics | 645 / 645 |
| Confirmed 통일찬송가 mappings | 481 / 558 |
| Mapped 통일찬송가 versions with lyrics | 79 |
| Mapped 통일찬송가 versions with empty lyrics | 402 |
| 통일찬송가 numbers without a confirmed version | 77 |

An absent or empty 통일찬송가 version is not filled from 새찬송가 unless the two
editions have independently verified identical lyrics. The 63 confirmed identical
pairs are listed in `docs/identical-hymn-lyrics-2026-08-19.md`.

## Strict Comparison

| Finding | Before | After |
| --- | ---: | ---: |
| Reference fetch failures | 0 | 0 |
| Character mismatches | 102 | 83 |
| Spacing-only differences | 533 | 549 |
| Title review candidates | 29 | 29 |
| Chorus structure candidates | 23 | 23 |
| Amen structure candidates | 2 | 2 |
| Low-similarity candidates | 24 | 24 |

The repair moved 19 versions out of character mismatch. 새찬송가 601 remains a
character candidate because its external reference uses a different edition phrase;
only its two certain modern-spacing errors were repaired.

## Confirmed Repairs

Only unmistakable typos, malformed characters, grammatical omissions, and modern
Korean spacing errors were changed. The guarded update covered 20 versions, 28 lyric
units, and 34 exact occurrences.

| Hymnal | Number | Title | Occurrences |
| --- | ---: | --- | ---: |
| 새찬송가 | 38 | 예수 우리 왕이여 | 1 |
| 새찬송가 | 60 | 영혼의 햇빛 예수님 | 3 |
| 새찬송가 | 63 | 주가 세상을 다스리니 | 2 |
| 새찬송가 | 70 | 피난처 있으니 | 3 |
| 새찬송가 | 184 | 불길 같은 주 성령 | 1 |
| 새찬송가 | 208 | 내 주의 나라와 | 1 |
| 새찬송가 | 220 | 사랑하는 주님 앞에 | 1 |
| 새찬송가 | 223 | 하나님은 우리들의 | 3 |
| 새찬송가 | 235 | 보아라 즐거운 우리 집 | 1 |
| 새찬송가 | 280 | 천부여 의지 없어서 | 1 |
| 새찬송가 | 311 | 내 너를 위하여 | 5 |
| 새찬송가 | 329 | 주 날 불러 이르소서 | 2 |
| 새찬송가 | 348 | 마귀들과 싸울지라 | 2 |
| 새찬송가 | 370 | 주 안에 있는 나에게 | 1 |
| 새찬송가 | 398 | 어둠의 권세에서 | 1 |
| 새찬송가 | 399 | 어린 양들아 두려워 말아라 | 1 |
| 새찬송가 | 456 | 거친 세상에서 실패하거든 | 1 |
| 새찬송가 | 601 | 하나님이 정하시고 | 2 |
| 통일찬송가 | 182 | 구주의 십자가 보혈로 | 1 |
| 통일찬송가 | 509 | 거친 세상에서 실패하거든 | 1 |

Every affected version remains `pending`; every changed unit remains
`needs_review`. 새찬송가 456 and 통일찬송가 509 are still strictly identical after
the shared correction.

## Deferred Review

- The 549 spacing-only findings are not bulk corrections because the external
  reference does not consistently apply modern Korean spacing.
- Refrain repetition and verse-layout differences are structural review candidates,
  not missing lyric text.
- Edition wording such as different endings or substantives is preserved even when
  the external reference differs.
- The remaining 83 character mismatches need score or second-source confirmation.
- The 29 title candidates remain unchanged unless the mismatch is independently
  confirmed; for example, 새찬송가 19 is not changed to the reference site's title.

## Two-line Block Integrity

All 724 hymn versions containing lyrics were also checked for the Mindex hymn
layout convention: each lyric unit is divided into blocks of at most two lines,
with one blank line between blocks. This blank-line structure is used when a
presenter form addresses grouped sections such as `V1A` and `V1B`.

| Item | Count |
| --- | ---: |
| Lyric units checked | 3,182 |
| Units already conforming | 2,816 |
| Units normalized | 366 |
| Affected 새찬송가 versions | 115 |
| Affected 통일찬송가 versions | 6 |
| Nonconforming units after repair | 0 |

Every affected row had no internal blank line before repair. Normalization only
inserted blank lines after each pair of existing lyric lines; it did not split,
join, reorder, or edit any non-whitespace character. Each changed unit remains
`needs_review`, and each affected version remains `pending`. All 63 independently
confirmed identical 새찬송가-통일찬송가 pairs still match in exact text and block
structure after normalization.

## Verification

- Pre- and post-update Supabase schema checks: zero issues, zero warnings
- Production row counts unchanged: 1,579 versions and 4,186 lyric units
- Post-update full audit: 1,203 / 1,203 pages fetched, zero fetch failures
- Deployed UI: corrected 새찬송가 348 and both 새456/통509 texts displayed correctly
- Review badges remained visible in the deployed UI

```sh
python3 tests/check_supabase_schema.py
python3 scripts/normalize_hymn_two_line_blocks.py
python3 scripts/normalize_hymn_two_line_blocks.py --apply
python3 scripts/audit_hbible_hymns.py --book both --workers 4 \
  --timeout 30 --retries 2 --delay 0.05 \
  --output /tmp/mindex-hymn-audit-strict-post-20260819.json
```

## Completed repair tool cleanup — 2026-09-22

The one-time repair tools were removed after their final conditions were checked
against the current production database. Their dedicated tests were also removed;
reusable audits, import tools, schema sources, and application regression tests remain.
No database records were changed by this cleanup. Historical repair implementations
are available in Git at `73dc5a45:scripts/`; do not rerun them as current maintenance.
