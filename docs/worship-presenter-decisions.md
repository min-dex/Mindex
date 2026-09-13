# Worship / Presenter Decision Log

## 50px Metadata Typography (2026-09-13)

- Presenter roles at the 1920-stage 50px size use weight 600. Larger fullscreen
  support/liturgical roles retain their prior weights via mode-specific tokens.
- Fin. shares the reading body's font-family token and retains italic styling;
  reading body size/weight and the translation label's family are unchanged.
- Eulyoo1945 is currently a local installed font, not a bundled web font. Safari
  may restrict access to user-installed fonts; CSS family equality alone does
  not guarantee identical glyphs across browsers. No font files were added.

## Document Restore Blanks (2026-09-13)

- While document-slide fallback remains active, restored slides pass through the
  same trailing-blank policy as item-built slides. Existing blanks are retained.
- This does not recreate the fallback in checkouts that have removed it, mutate
  stored snapshots, or change which data source is selected for presentation.

## Automatic Blank Grouping (2026-09-13)

- Controller section grouping uses the originating element's non-automatic slide
  for automatic blanks. Empty output metadata must not split the controller group.
- This applies to all sections, including the shared closing hymn/visual group.
  Output payload, slide order, and persisted worship data are unchanged.

## Blank Group Ownership (2026-09-12)

- Keep sectionRole on generated blanks: the controller uses it to keep praise
  blanks with their originating songs and avoid duplicate editor groups.
- A blank layout is never a preparation slide, regardless of inherited role.
  Ready and closing trailing blanks remain enabled; no DB content is changed.

## Ready And Closing Blanks (2026-09-12)

- Ready screens/videos and closing visuals use the common trailing-blank rule.
  The ready/closing suppression helper is removed. Existing blank slides and
  automatic blanks still do not receive duplicate blanks.
- Generated blanks clear ready metadata as well as visible media/text. Waiting
  video playback itself and persisted worship content are unchanged.

## Welcome Blank And Examples (2026-09-12)

- Praise welcome uses the common trailing-blank rule; it no longer explicitly
  suppresses its blank. Ready and closing-screen behavior is unchanged.
- The first ten bulk-input example lines choose distinct song/hymn examples by
  displayed position, rather than repeating one hymn or cycling three songs.
- These changes do not modify persisted worship content.

## Preparation Examples (2026-09-12)

- Manual praise examples use the persisted input mode even when the editor
  exposes that mode as text. Announcement examples use announcement content.
- Monthly grouped prayers expose one example per prayer. Bulk input updates the
  corresponding corporatePrayers entry, preserving its sibling, sourceElementId,
  and an omitted assignee. No separate prayer elements are created.
- Bulk apply remains an in-memory edit; saving is still a separate action.

## Individual Input Feedback (2026-09-12)

- The individual editor command is labeled `반영·저장`: it still applies the
  fields and saves to the DB. Quick worship input retains its separate semantics.
- Visible editors show modified, saving, saved, or failed feedback next to the
  command. Feedback updates do not replace input DOM or move focus.
- Save completion compares the captured field values and pending deferred input.
  Later typing remains modified; failure leaves the draft intact. Feedback is
  transient UI state, not persisted worship metadata.
- Individual commit returns the real save result, including false on validation
  or persistence failure. Existing save serialization and synchronization remain.

## Sunday Edit Synchronization (2026-09-12)

- Each service displays and edits its own persisted values. Empty values do not
  borrow sibling content or hide their editor.
- Confirmed edits synchronize after source save: praise 1-3 between Sunday 1/2,
  reading and sermon/citations between 2/3, offering hymn between 1/2/3 on the same date.
- Only existing, unambiguous, standard elements with matching previous content
  participate. Alternative offerings, videos, special songs, custom media, and
  missing template rows are not converted into shared elements.
- Different target content, pending edits, live output, and revision conflicts
  are preserved. Failures are visible; local retry records survive reload.
  Saving the source again retries them without resynchronizing unchanged fields.
- Only target content fields are written, never sibling sections/order. Document
  text/history and that element's slide snapshots are updated while unrelated
  slide snapshots are retained. Multi-row writes are not an atomic transaction.

This is the durable record for behavior that must not be silently reverted by
another task. It supplements the data contract; it records reviewed product
decisions rather than implementation history.

## Update Rule

When a change affects live service operation, templates, output behavior,
default selection, or a user-visible exception:

1. Update this file in the same change.
2. State the rule, its scope, and the exception if one exists.
3. Add or update a focused smoke assertion when the behavior is testable.
4. Do not replace a documented rule with a local workaround or fallback.

If another thread sees a documented rule that appears wrong, it must ask the
user or update this log with the new reviewed rule. Do not silently revert a
documented decision during cleanup, refactor, or smoke-test repair.

Small visual polish that does not alter behavior does not need an entry.

## Current Decisions

- 부서 예배의 광고는 엘리멘트 label과 새 예배 템플릿 제목 자체를 `광고`로 통일한다.
  기존 청소년부 광고·청년부 광고 label은 로드 시 변환하고 이후 저장도 `광고`로 한다.
  순서 목록, 편집기, 송출도 동일하게 표시한다. 광고 본문과 예배 소속은 변경하지 않는다.
  본문형 광고의 동작은 부서명이 아니라 announcements 섹션과 body 유형으로 판정한다.
  본문형 광고는 고정 `교회소식` 제목 분기를 거치지 않으며, 입력창과 본문 슬라이드를 유지한다.

- 월삭 공동기도는 `공동기도 1·2`, `기도찬양`, `공동기도 3·4`의 세 엘리멘트로 편집한다.
  각 기도 묶음은 두 제목과 두 담당을 corporatePrayers에 함께 저장하고 해당 출력도 소유한다.
  기도찬양의 기존 곡 연결은 그대로 유지한다. 제목만 묶고 담당을 별도 항목으로 남기지 않는다.
  기존 개별 기도는 번호와 섹션이 유일하게 확인되는 경우만 묶음으로 가져온다.
  중복 후보, 제목 충돌, 미디어나 별도 본문이 있는 항목은 자동 병합하지 않는다.
  기존 DB 행은 일괄 삭제하지 않는다. 묶음이 저장한 sourceElementId로 이미 포함된
  레거시 행을 식별하여 다시 엘리멘트로 추가하지 않는다.

- 인용 구절은 크로마키와 풀스크린 모두 성경 책 전체 이름을 표시한다 (2026-09-12 수정).
  크로마키 인용 구절은 흰색 탭에 출처, 전체 폭 남색 바에 본문만 표시한다.
  흰색 탭 너비는 출처 텍스트와 좌우 여백 및 오른쪽 사선 길이에 맞춘다.
  풀스크린과 성경봉독 레이아웃은 변경하지 않는다.
  섬네일과 실제 송출은 동일한 규칙을 사용하며 저장된 말씀 입력값은 변경하지 않는다.

- 찬양 로딩 완료 시 promise 해제 후 로딩 표시를 갱신한다.
- 찬양 버전·가사 테이블은 독립적으로 병렬 조회하되 둘 다 성공해야 곡에 반영한다.
  가사 검색과 Presenter가 전체 가사를 사용하므로 목록 최적화를 이유로 가사를 생략하지 않는다.
- 연결 곡·가사와 예배 상세 묶음 조회는 80개씩 제한된 병렬 요청을 사용한다.
  모든 페이지를 수집하고, 실패한 묶음은 진행 중 요청이 끝난 뒤 오류/캐시 경로로 처리한다.
  섹션→엘리먼트, 버전→가사의 의존 순서는 유지한다.
- 역대 콘티 화면에서 사용하지 않는 곡 매칭 수 계산은 하지 않는다.
  예배 목록의 source_ref와 복구 스냅샷은 보존한다. 이를 축소하거나 오래된 캐시로
  먼저 표시하는 최적화는 편집·복구·자동 예배 생성의 최신성 검증 없이 적용하지 않는다.

- 전역 담당 표기는 `담당`, 유형명은 `제목 / 담당`으로 통일한다. 옛 명칭의
  레거시 별칭은 DB 전수 검사 후 제거했다. 상세 규칙은 `docs/ui-contracts.md`의 Assignee Terminology를 따른다.

### Setlist Archive Navigation

- 2026-09-09: 주별 보기는 한 주의 예배 현황을 겸한다. 주일·주일오후·어린이부·청소년부·청년부·수요·금요 자리를 고정하고, 자료 범위 내 모든 주를 표시한다.
  실제 콘티는 유지하며 비어 있는 칸은 집회 없음 / 콘티 미등록 / 기록 없음으로 구분한다.
  집회 없음은 명시된 DB 근거만 사용한다. 온세대·연합예배로 함께 드린 부서도 `집회 없음` + 사유로 통일한다. 온세대 주는 별도 콘티 없는 어린이부·청소년부의 사유를 `온세대 찬양예배`로 표시하며 실제 기록을 우선한다.
  원문으로 확인한 2/20 문화예배, 4/5 청소년부·청년부 통합 사유는 import source의 `raw_payload.service.weekly_status/weekly_reason`에 보관한다.
  수요예배 등 자료가 없는 과거 주는 휴회로 추정하지 않는다. 검색 중에는 일치하는 카드만 보여주며 빈칸을 생성하지 않는다.
  금요일 월삭예배는 금요 자리에 표시하며, 1·2부 개별 카드는 만들지 않는다.

- 별명은 카드 첫 줄 오른쪽에 정렬한다. 주별은 예배명, 예배별은 날짜 옆에 표시한다.
- 2026-01-04~05-31 주일 콘티 17건의 `나는 예배자입니다 + 소원`을 DB에서
  `입례찬양`/`entrance_praise`로 정정했다. 메인 번호에서 제외하며 원본 백업은
  `backups/setlist-sunday-entrance-before-20260906.json`에 보관한다.

- 1부 설교자를 예배 인도자 기본값으로 자동 대입하던 예외는 제거한다.

- 주일 콘티는 3부 기준 `주일예배` 카드 하나만 표시한다. 같은 날짜 2부 특송만
  3부 특송 앞에 합치며, 기존 콘티에 2부 특송이 있으면 추가하지 않는다.
  1·2부 별도 카드는 표시하지 않고 예배 DB 원본은 유지한다.

- 콘티 카드에 예배 별명을 표시하고 검색에도 포함한다. 실제 예배의 `service_alias`와
  import 콘티의 service tags를 사용하며 비어 있으면 별명 줄을 만들지 않는다.
  메인 찬양 번호는 행 수가 아니라 곡 수로 센다. `A + B`는 `찬양 1–2`,
  다음 `C + D + E`는 `찬양 3–5`이며 이후 단일 곡은 `찬양 6`이다.
- 역대 콘티는 기존 import 콘티와 실제 Worship 예배를 함께 표시한다. 실제 예배는
  저장된 praise 항목에 곡 ID 또는 제목이 있을 때만 카드를 만들고 빈 순서는 제외한다.
  section/element 순서와 찬양 인도자(없으면 예배 인도자)를 사용한다. 가사·슬라이드는 조회하지 않는다.
  같은 날짜·예배 유형의 import 콘티가 있으면 기존 콘티를 우선해 중복 카드를 만들지 않는다.
  1·2·3부는 서로 다른 예배로 취급한다. 실제 예배 자료는 복사 저장하지 않고 조회해서 구성하며,
  콘티를 다시 열거나 새로고침하면 변경된 예배 내용이 반영된다. 직접 입력한 곡명은 임의 매칭하지 않는다.
- 청소년부의 서로 다른 날짜에 반복된 콘티는 각각 유지한다. 2026-09-06 원문 대조로
  같은 날짜 중복 7개를 제거하고 22개 날짜를 보존했다. 원문의 `결단(07)`에 따라
  `예수 닮기를`은 5/31이 아닌 6/7 결단찬양이다. 쉼표로 나열한 날짜를 연속 기간으로
  바꾸거나 날짜 한정 결단찬양을 다른 날짜에 복제하지 않는다.
  백업: `backups/youth-setlist-dedup-before-20260906.json`.
- 2026-09-06 사용자 확인: 청년부 `2026-04-09`는 `2026-04-19` 오기다.
  두 콘티 7행의 내용·곡 연결이 동일함을 검증하고 4/9 중복 원본을 제거했다.
  4/19는 유지하며 옛 입력 자료의 4/9를 다시 가져오지 않는다.
  백업: `backups/setlist-april09-duplicate-before-20260906.json`.
- 주일예배 3부 특송은 제목 정규화·곡 링크·미연결 확인 목록에서 제외한다. 부수 없는
  주일예배 원본의 특송(부활절 칸타타 포함)도 해당하며, 2부 특송과 다른 예배 특송은 유지한다.
- 콘티의 옛 제목은 연결된 DB 제목으로 정리하며, 일회성 제목 별칭은 정리 후 제거한다.
- `능력의 이름 예수`는 사용자가 별도 곡으로 확인했다. `예수 예수` 별칭을 콘티와
  기존 예배 lookup 양쪽에서 제거했으며 미확정 11곡과 함께 독립 곡·기본 버전으로 등록했다.
  가사와 저작자 정보는 임의로 채우지 않았다.
- 콘티 곡명은 곡·버전 metadata의 유일한 일치 후보에만 찬양 DB 링크를 붙인다.
  hover/focus에서 밑줄을 표시하고 기존 곡 열기 동작을 사용한다. 가사는 링크 판정에 조회하지 않는다.
- 메들리는 `+`로 나눈 각 곡에 개별 링크를 붙인다. 화면과 tooltip 모두 연결된
  DB 제목을 표시한다. 옛 제목을 별도로 보존·표시하는 흐름은 두지 않는다.
- 동명곡은 subtitle로 구분 가능한 정확한 표기를 우선하고, 남은 복수 후보는 임의로
  선택하지 않는다. 찬송가 번호/통일찬송가 구분/절 표기를 보존하며 번호 충돌은 미연결로 둔다.
- 2026-09-06 사용자 지시로 콘티 후보 95행의 제목과 normalized payload 제목을
  연결된 DB 제목으로 통일했다. 찬송가 번호·절·순서는 유지한다. 변경 전 백업은
  `backups/setlist-db-titles-before-20260906.json`에만 보관하며 운영 표시에는 사용하지 않는다.
- 2026-09-06 연결 검토 완료: 사용자 지시로 12곡을 신규 등록했고, 내부 레코드만
  남은 `십자가`, `나는 주를 섬기는 것에 후회가 없습니다`, `주 말씀 향하여`는 기존
  canonical ID로 복구해 연결했다. 십자가의 기존 가사는 보존했다.
  `마라나타`는 고형원 CCM, `예수 우리 왕이여`는 예수전도단 번역 CCM으로 연결했다.
  수정 전 기록은 `backups/setlist-create-twelve-20260906.json`,
  `backups/setlist-restore-three-20260906.json`, `backups/setlist-ccm-selection-20260906.json`,
  `backups/setlist-hymn259-before-20260906.json`에 보관한다. 완료된 일회성 확인 목록은 제거했다.

- 역대 콘티의 `sunday-main`/`sun_3rd` 원본은 2부 특송을 함께 담으므로
  `주일예배`로 표시한다. 예배별 그룹에서는 최상단, 주별에서는 같은 날짜의
  다른 예배보다 먼저 둔다. 실제 예배의 1·2·3부 구분은 유지한다.

- 모든 예배의 메인 `찬양`에 표시 순서대로 번호를 붙인다. 한 원본에 함께 기록된
  `2부 특송`·`3부 특송`은 원본 예배 분류와 달라도 숨기지 않는다.
  번호와 부별 label은 화면 표시에서 보존하고 candidate 원본은 수정하지 않는다.

- 역대 콘티는 표시·검색에 필요한 필드와 element 후보만 조회하고 후보 묶음은
  최대 3개씩 병렬로 요청한다. 공개 프로젝트는 프로젝트 URL별 완성된 snapshot을
  6시간까지 캐시해 재방문 시 먼저 표시하고 항상 서버에서 갱신한다. 인증이 필요한
  프로젝트에는 적용하지 않는다. 새로고침은 서버를 직접 조회하며 실패 시 기존
  완성된 화면과 오류를 유지한다. 일부 요청만 성공한 결과로 캐시를 덮어쓰지 않는다.

- 인도자는 원본 `raw_payload.service.leader`의 이름·직분을 그대로 표시하고
  검색에도 포함한다. 값이 없으면 `인도 미기록`으로 표시하며 다른 예배의
  담당자를 추정해 채우지 않는다. 주별 카드는 예배명을 제목으로 쓰고 개별 날짜를
  함께 표시한다. 예배별 카드는 날짜를 제목으로 쓴다. 곡 역할과 곡명은 열을 나누어 표시한다.
- 금요기도회 역대 콘티의 메인 찬양은 `찬양 1·2·3…`으로 표시한다.
  기존 `setlist` import에서 `찬양` 6곡으로 합쳐진 경우 앞의 5곡이 메인
  찬양이고 마지막 1곡은 `입례찬양`이다. 화면에서는 특송 뒤, 결단 앞에
  배치한다. 5곡뿐인 콘티는 모두 메인 찬양으로 유지하며, 다른 예배나
  다른 곡 수에 이 복원 규칙을 확대 적용하지 않는다. 명시적인 `입례찬양`(기존 `예배찬양`)
  항목이 이미 있으면 그것을 사용한다. 이 규칙은 archive 표시용이며
  원본 import 데이터와 현재 예배/Presenter의 입례찬양 규칙을 변경하지 않는다.
- 역대 콘티 전체에서 `예배찬양`은 `입례찬양`으로, 봉헌·결단·기도·파송·폐회·입례는
  `봉헌찬양`처럼 찬양을 붙여 표시한다. 번호는 `기도찬양 1`처럼 뒤에 둔다.
  이미 찬양이 붙은 이름과 특송은 유지하고, 표시명 변경으로 순서를 바꾸지 않는다.
- `주별`(기본)은 일요일~토요일로 묶고 최신 주부터 표시한다. 주 안에서는
  날짜 오름차순, 같은 날짜는 예배 순서대로 표시한다. 월·연도를 넘어도 같은 주로 묶는다.
  `예배별`은 예배 종류별로 묶어 각 그룹 안에서 최신 날짜부터 표시한다. 검색은 두
  보기 모두에 적용하며, 보기 선택은 화면 재진입과 데이터 새로고침 동안 유지한다.
- `역대 콘티`로 이동하면 활성 탭 제목과 저장된 탭 snapshot도 즉시
  갱신한다. 다른 예배 화면으로 돌아가면 해당 화면의 제목을 표시한다.

### Controller Reload Recovery

- Reloading the controller must not stop an already-open Presenter output.
  The output keeps its last rendered frame while the controller reconnects.
- After the output answers the controller's `ready` / heartbeat signal, the
  controller restores the last active service, slide index, blank state, and
  live scripture state from the persisted presenter payload, then republishes
  freshly built slides from the current service data.
- Restoration is only allowed while an output is actually connected and only
  for a payload newer than 12 hours. A stale local payload must never start a
  presentation by itself when the app is opened later.

### Presenter Typography Scale

- Presenter typography is controlled by role tokens, not by individual slide
  exceptions: `Title` (weight 800), `Main song` (800), `Section` (800),
  `Content` / `Lyrics` (700), `Support` (600), and scripture-reading text.
- Fixed measurements on the 1920x1080 stage use a **5px grid**. Timing uses a
  **50ms grid**. Use the closest grid value when adjusting a fixed font size,
  thumbnail size, blank-cross dimension, or animation duration. Percentages,
  container ratios, and typographic ratios (for example the reviewed scripture
  `letter-spacing: -0.06em`) retain their semantic values and are not rounded.
- At the fixed 1920x1080 presenter stage, the reviewed scale is:

  | Role | Chromakey | Fullscreen |
  | --- | ---: | ---: |
  | Title | 90px | 170px |
  | Main song title | 100px | 150px |
  | Section title | 70px | 140px |
  | Content | 70px | 100px |
  | Lyrics | 70px | 100px |
  | Support | 50px | 100px |
  | Formal scripture verse body | 90px | 90px |

- The formal scripture reading deliberately keeps the same 90px verse body
  across output modes. It is a shared reading form rather than a fullscreen
  display variant. This table is the source of truth for future typography
  adjustments; change the role token first, then review the representative
  slides before adding a local override.

### Scripture Input And Reading

- `성경봉독` and `설교 본문` are separate visible service elements in chromakey
  services, but their scripture references may be shared when one side is
  intentionally empty.
- Fullscreen/clean public worship does not need a separate `설교 본문` element:
  `성경봉독` is already the fullscreen scripture output. Existing clean-output
  `설교 본문` items are treated as redundant no-output compatibility items.
- A directly entered `성경봉독` reference is valid content for the reading and
  must not be ignored merely because `설교 본문` is empty.
- If `설교 본문` is empty and `성경봉독` has a valid reference, `설교 본문`
  may use the reading reference as fallback so it does not show `입력 필요`.
- If `성경봉독` is empty and `설교 본문` has a valid reference, `성경봉독`
  may use the sermon-body reference as fallback.
- Direct input always wins over fallback input.
- Scripture reference normalization for service inputs follows the Scripture
  search parser: Korean/English abbreviations, attached book+chapter text such
  as `요21:15~25`, `~` ranges, and comma-separated references are accepted.
- 성경 원본 데이터가 한 행에 여러 절을 묶고 다음 절 번호를 생략한 경우에는
  (예: 대한성서공회 `신 6:18-19`) 그 번호 공백을 읽어 화면 표기를 `18–19`로
  복원한다. 이 규칙은 특정 역본이나 문장 종결 판단에 의존하지 않는다.
- `인용 구절` is optional, separate from the sermon body, and may be entered
  before or during worship. An empty citation creates neither a missing warning
  nor an empty slide.
- A scripture-reading final slide keeps the scripture-reading background and is
  followed by one plain trailing blank that suppresses the service background.
  In chromakey output this is the chromakey blank; in fullscreen/clean output it
  is the default blank frame.
- Scripture-reading output uses the installed `Eulyoo1945` / `을유1945` face
  for the verse body text only. The body uses `font-weight: 700`, allows weight
  synthesis, and applies a very small text stroke for projection readability
  because the installed Eulyoo face can render too thin at screen size. The
  reference line, translation label, and `Fin.` keep the presenter font. Do not
  bundle the Eulyoo font file in this repo.
- Scripture-reading references include the current verse number in the header,
  e.g. `요한계시록 3:19`; the large standalone verse-number column is not used.
- The translation label uses the same color as the reference line and is one
  text-size step larger than the old caption size.
- Scripture-reading output keeps the Eulyoo verse body tighter with
  `letter-spacing: -0.05em` and removes text shadow; body stroke/weight
  synthesis is the other readability boost.

### Ministry Service Auto-Generation

- Youth and young-adult worship stay in the weekly auto-generation flow.
- Children's worship templates and service type remain available for later use,
  but weekly auto-generation is off until explicitly enabled through a reviewed
  product decision. Do not hardcode a September activation date.

### Service Outline And Input State

- Missing-input state belongs to the actionable element only. Section rows show
  structure and start position; they do not repeat an element's `입력 필요`
  badge.
- Fixed liturgical content, shared scripture reading, and fixed closing media
  are not preparation inputs.
- `예배 입력`의 `반영`은 서비스 입력에만 적용하고 저장하지 않는다.
  저장 단축키는 capture 단계에서 Cmd/Ctrl+S를 처리하며 한글 키보드의 KeyS도 인식한다.
  예배 저장은 dirty 판정으로 입력 중인 값의 commit을 건너뛰지 않는다.
  반영 뒤에는 상단 `저장` 버튼이 활성화되며, 사용자가 그 버튼으로
  Supabase 저장을 명시적으로 확정한다.
- `예배 입력`은 현장용 rough text를 받아야 한다. `찬송가 9, 288, 182`
  같은 한 줄 hymn list는 순서대로 `찬양 1`, `찬양 2`, `찬양 3`에
  매핑하고, `성경봉독 롬 8:12~17`, `설교 제목 한 가지 그것을`,
  `봉헌찬송 찬 187장`처럼 colon 없는 known-label line도 인식한다.
- `예배 입력`의 placeholder는 선택된 예배의 editable input만 예시로
  보여준다. Fixed/default/shared output은 예시에 넣지 않는다.
- 금요기도회 메인 찬양은 `찬양 1`부터 `찬양 5`까지 독립 슬롯이다.
  `찬양 1 곡명` 형식은 같은 번호 슬롯에 연결하고, 성경봉독 직전 찬양은
  성경봉독과 설교 사이의 독립 `입례찬양` section/element로 유지한다. 붙여넣기 입력의 `[팀명.날짜]` 같은
  머리말과 `금요기도회입니다!` 같은 마무리말은 무시하며, 곡명 뒤의 조성
  표기(`G`, `D`, `F#m` 등)는 연주 참고용으로만 보고 곡 검색에서 제외한다.
- 기존 금요 예배의 메인 `찬양` 또는 `성경봉독 전 찬양` 안에 있던 입례찬양은 열 때
  독립 `입례찬양` section으로 정규화한다. `자율기도`는 입력이 필요 없는 고정 순서이므로 missing 상태나
  입력 필드를 만들지 않는다.
- 금요기도회의 `기도회` 섹션에는 `기도찬양 1·2`와 마지막 `자율기도`를
  둔다. `교회소식`은 독립 `광고` 섹션에만 둔다. 기존 데이터의 위치를
  추정해 자동 이동하지 않고, 템플릿 매칭으로 각각의 섹션을 유지한다.
- `인용 구절`은 optional `설교` 엘리멘트다. 풀스크린의
  메인 찬양, 입례찬양, 기도찬양의 제목은 152px, weight 800으로 표시하며
  봉헌·특송 등 다른 순서의 곡 제목과 구분한다.
- `온세대 찬양예배`는 주일 3부 날짜 치환 서비스지만 찬양 곡 수가 고정되지
  않는다. 정확한 전체 순서가 확정되기 전에도 `예배 입력`에 `찬양 1`부터
  `찬양 12`처럼 template보다 많은 메인 찬양이 들어오면, 입력 개수만큼
  `찬양` 섹션의 praise element를 동적으로 materialize한다. 일반 주일 3부의
  기본 `찬양 1~4 + 입례찬양` 구조를 이 규칙으로 바꾸지는 않는다.
- 2026-07-19 온세대 찬양예배 PPT에서 import된 메인 찬양은 `찬양 1 모든
  민족과 방언들 가운데`, `찬양 2 이 눈에 아무 증거 아니 뵈어도`,
  `찬양 3 우리는 주의 백성이오니`, `찬양 4 일어나라 주의 백성`,
  `찬양 5 내 안에 부어 주소서`, `찬양 6 모든 열방 주 볼 때까지 + 물이
  바다 덮음같이`다. 이 곡 목록과 PPT 순서 기반 송폼은 7월 19일 서비스
  인스턴스의 실제 데이터이며, 이후 온세대 날짜에 반복 적용되는 template
  default가 아니다. 온세대 variant에서는 일반 3부의 별도 `입례찬양` 슬롯을
  만들지 않고 입력된 만큼 `찬양 n`으로 둔다.
- 온세대 찬양예배에는 `특송` 섹션은 두되, 일반 3부의 할렐루야 찬양대
  기본 담당자/곡을 자동 주입하지 않는다. 특송은 매 예배마다 입력 가능한
  일반 특송 슬롯으로 유지한다. 온세대 variant의 큰 순서는
  `준비 → 찬양 → 대표기도 → 성경봉독 → 특송 → 설교 → 결단 → 봉헌 → 교회소식 → 파송 → 폐회`다.
  `폐회`에는 표어/마무리 이미지만 두고 `폐회찬송`은 만들지 않는다.
  일반 3부의 `참회기도`, 중간 `찬송`, `신앙고백`, `공동체고백`은 온세대에서
  자동 생성하지 않는다.
- 온세대 variant의 봉헌은 일반 3부의 `봉헌찬송` score slot을 쓰지 않고
  `봉헌특송` praise slot을 사용한다. 2026-07-19만 어린이부 봉헌특송 직후
  PPT 마지막 감사/안내 이미지(`all-generations-2026-07-19-offering-thanks.png`)를
  서비스 인스턴스에 포함한다.
- 일반 3부 특송은 할렐루야 찬양대 운용 때문에 clean/fullscreen output 예외를
  탈 수 있지만, 온세대 찬양예배 특송은 할렐루야 고정 특송이 아니므로 그 예외를
  적용하지 않는다.
- 온세대 찬양예배는 주일 3부 variant이지만 출력 방식은 일반 주일 3부처럼
  chromakey를 사용한다. 온세대 감지는 순서/템플릿 projection에만 쓰고,
  service-wide clean/fullscreen 전환 조건으로 쓰지 않는다.
- 금요기도회는 `성경봉독 → 입례찬양 → 설교` 순서로 진행한다.
- 2026년 8월부터 금요일 예배 자동 생성은 주차별 운영명을 따른다.
  첫째 금요일은 `월삭예배`로 만들고 월삭예배 템플릿을 사용한다.
  둘째 금요일은 `문화예배`로 만들되 영화 관람 등으로 집회가 없는 날이므로
  금요기도회 송출 템플릿을 붙이지 않는다. 셋째 금요일 `삼삼오오예배`는
  찬양 3곡, 입례찬양 없음, 특송 없음, 기도회 없음, 결단 다음 `교회소식`,
  파송 축도, 폐회 뒤 `교제`가 있는 별도 양식을 사용한다. `교제`
  엘리먼트는 축도처럼 고정 순서명에 담당자만 입력한다. 넷째 금요일 `구역연합예배`는
  표시명을 바꾸고 기존 금요기도회 양식을 유지하되, 출력은 chromakey로 사용한다. 다섯째 금요일은
  별도 지시가 없으면 기존 `금요기도회`로 둔다.
- 금요일 저녁에 드리는 예배들은 UI에서 `금요예배` family로 묶고,
  `월삭예배`, `문화예배`, `삼삼오오예배`, `구역연합예배`, `금요기도회`는
  variant로 표시한다. DB service type은 월삭 템플릿과 금요 템플릿을 안정적으로
  유지하기 위해 기존 `monthly`/`friday`를 그대로 사용한다.
- 교회력 `church_schedule`에 `설 연휴`가 있는 주는 정규 예배 찬양 콘티가
  없어도 archive completeness 누락으로 보지 않는다. 이 주의 금요예배가
  문화예배/영화 관람 등으로 대체된 경우에도 빈 콘티가 정상 상태다.
- 예전 찬양 콘티 archive completeness audit에서는 사무총회/사무총회 속회,
  온세대/통합예배, 부서 헌신예배 때문에 해당 부서가 주일오후예배와 연합한
  날짜를 누락으로 보지 않는다. 2026년 상반기 audit 기준으로 실제 확인이
  필요한 누락 후보는 `2026-06-10` 수요예배와 `2026-06-17` 수요예배다.
- `삼삼오오예배`는 `friday` 계열 variant이며 금요기도회와 같은 clean/fullscreen
  output을 사용한다.
- 풀스크린 예배의 준비 element 표시명은 `대기 화면`으로 둔다. 실제 준비 화면은
  이미지/영상/기본 화면을 모두 쓸 수 있으므로 `대기 영상`처럼 특정 media type으로
  고정해 부르지 않는다. 기존 `대기 영상` 저장값은 legacy alias로 계속 인식한다.
- 풀스크린 `대기 화면`의 기도 준비 문구는 안내 톤으로 작게 두고, `잠시 후
  {예배명}가 시작됩니다`도 본문보다 과한 display scale을 쓰지 않는다. 예배 이름만
  굵게 강조하고 전체 화면은 차분한 waiting screen으로 유지한다.
- 출력 창은 BroadcastChannel 연결 시 이전 local payload를 재출력하지 않고
  현재 controller state를 기다린다. 따라서 풀스크린 예배 시작 시 이전
  크로마키 프레임이 잠깐 노출되지 않는다.
- 풀스크린의 빈 화면 십자가는 세로선을 위에서 아래로 먼저 그린 뒤,
  가로선을 왼쪽에서 오른쪽으로 이어 그린다. 크로마키 빈 화면에는 십자가를
  표시하지 않는다.
- 풀스크린 예배의 설교 `인용 구절`은 성경봉독과 같은 말씀 전용 화면으로
  출력한다. 크로마키 예배에서는 기존 하단 바 성구 화면을 유지한다.
- 금요기도회의 기본 배경은 `26-B` 계열이다. 서비스별로 직접 고른
  배경은 유지하지만, 금요기도회 템플릿/자동 생성 기본값은 `B` 그룹을
  따른다.
- `말씀 <제목>`은 성경 주소처럼 보이지 않으면 `설교 제목`으로,
  `설교 <이름/직분>`은 설교 제목 요소의 담당자로 반영한다.
- 찬양 DB에서 원제/부제/첫 가사 등으로도 곡을 하나로 찾지 못하면,
  새찬송가 score 전용 슬롯을 제외하고 입력 제목의 빈 Praise record를
  만들고 해당 예배 항목에 연결한다. 사용자는 나중에 Praise 탭에서
  가사와 버전을 채운다.
- Fullscreen/clean output의 찬양·특송 등 song-like 항목은 입력 전
  `입력 필요` placeholder도 실제 곡 입력 후와 같은 lower-bar song frame을
  사용한다. 담당자/기도 등 title-person 항목은 기존 center title-content
  placeholder를 유지한다.
- 찬양 제목 앞 표기는 16분음표 `♬`를 쓰며, 한글 제목 폰트를 바꾸지 않고 별도 inline glyph로
  크기와 baseline만 보정한다. 풀스크린/clean output은 실제 송출 화면에만
  250ms 이하의 약한 opacity/brightness dissolve를 적용할 수 있으며,
  controller thumbnails와 chromakey/shared scripture output에는 적용하지 않는다.

### Public Worship Timing

- Home selects public Worship by each service's actual KST meeting window, not
  by service date alone. A currently running service is shown before the next
  future service.
- Regular windows are: 수요예배 `19:10-20:30`, 금요기도회 and 월삭예배
  `20:00-22:00`, 주일예배 [1부] `07:00-08:00`, [2부] `08:50-10:00`,
  [3부] `10:50-12:00`, and 주일오후예배 `13:20-14:30`.
- Department and special services have no inferred time window. Until they
  carry explicit timing metadata, Home falls back to their service date.

### Default Ministers

- Default sermon/benediction ministers are template defaults, not missing
  preparation inputs. A per-service edit may override them.
- 주일예배 [1부] rotates weekly from `2026-08-23` (`김광한 전도사`), then
  `김석범 목사`. `김광한 전도사` weeks use `주기도문` instead of `축도`;
  `김석범 목사` weeks use `축도` 담당 `김석범 목사`.
- 주일예배 [2부], [3부], 주일오후예배, 수요예배, and 월삭예배 default to
  김남영 목사 for sermon and benediction when those elements exist.
- 금요기도회 defaults to 김남영 목사 for sermon. It has no benediction element.
- 청년부 예배 defaults to 김석범 목사 for sermon, offering prayer, and
  benediction.
- In the sending section, `축도` and `주기도문` are mutually exclusive in the
  presenter/order projection. If both legacy/persisted items exist, keep `축도`
  and drop `주기도문`.

### Sunday Public Worship Templates

- Sunday first and second service share the same three main-praise contents:
  `찬양 1`, `찬양 2`, and `찬양 3`.
- Sunday third service praise/hymn slots are not shared into first/second
  main-praise slots; only second/third scripture and sermon content are linked.
- Sunday second and third service share scripture reading and the whole sermon
  section content: `성경봉독`, `설교 제목`, `설교 본문`, and `인용 구절`.
- Sunday first, second, and third service share `봉헌찬송`.
- These are same-date linked content rules, not presenter-only fallback.
  When a linked slot is filled, edited, or cleared in one service, saving writes
  the same content to the other same-date services in its sharing group.
  Presenter fallback may remain only as legacy recovery for older rows that have
  not been normalized yet.
- Sunday first and second service doxology is fixed to hymn 5,
  `이 천지간 만물들아`.
- Sunday afternoon doxology is fixed to hymn 1, `만복의 근원 하나님`.
- A fixed doxology is output content, not an input. It must not appear in the
  input rail, block saving, or produce an `입력 필요` warning.
- Sunday afternoon worship starts with four main-praise slots:
  `찬양 1` through `찬양 4`.
- Sunday afternoon worship uses the dedication-service order by default because
  most afternoon services are dedication services. `특송` and `봉헌`
  (`봉헌찬송`, `봉헌기도`) stay in the base template; non-dedication days should
  skip/hide those slots instead of removing them from the scaffold.
- Sunday third service uses the same `신앙고백 → 사도신경` title-slide rule as
  the first and second services. `공동체고백` and `주기도문` also retain their
  own title slides before their body text.
- Template-provided praise defaults are real linked Praise selections, not
  display-only text. Sunday third preloads `입례찬양` (내 한 가지 소원),
  `파송찬송` (359 천성을 향해 가는 성도들아), and `폐회찬송` (352 십자가
  군병들아) when their catalog records are available.
- These are template rules, not copied weekly content. A service instance may
  override them only through a deliberate template-modified edit.
- 주일예배 [3부] 특송 is allowed to be a one-off manual choir item. When the
  element carries manual slides/body, it must not auto-link to Praise DB even
  if the title matches a hymn, because choir arrangements often reuse hymn
  titles with custom lyrics.
- 특송 elements may carry a deliberate image deck in `asset.slides`. In that
  case the presenter outputs those images as-is and does not add an extra
  generated title slide, because the supplied deck is already designed for
  projection.

### Youth Worship Template

- 청소년부 예배 is a regular 10:50 Sunday ministry service. On a date marked
  `온세대 찬양예배`, it is not generated because youth worship is integrated
  with 주일예배 [3부].
- New 청소년부 예배 services receive this weekly scaffold: `사도신경`, main
  praise 3곡, `대표기도`, `봉헌` (`봉헌찬양`, `봉헌기도`), `성경봉독`, `설교`,
  `결단기도`, `광고`, `주기도문`, and `반별 모임`.
- `통성기도` and `결단찬양` are not part of the regular youth template unless
  a user deliberately adds them for that service.
- In every service template, the child element of the `대표기도` section is also
  labeled `대표기도`. Legacy projected items labeled `기도` are normalized for
  display without changing their leader or entered content.
- The regular `봉헌찬양` default is `대단한 믿음 없어도` with the `V1-C` song
  form. It is prefilled for each weekly service rather than copied from the
  previous week.

### Preparation Input Parsing

- `본문`, `성경본문`, `설교본문`, `말씀`, and `말씀본문` are dynamic
  preparation aliases. If the service has a `설교 본문` element, they target
  that element; otherwise they target `성경봉독`.
- This keeps fullscreen/clean public worship from failing when it has no
  separate `설교 본문` input because `성경봉독` is the fullscreen scripture
  source.
- `인용 구절` accepts the same scripture-reference normalization as scripture
  search, including abbreviations, `~`, and comma-separated references. If a
  service has no `설교 본문` element, citation slides are inserted in the
  sermon section after `설교 제목`.
- Implicit praise shorthand numbering advances from the highest explicit
  `찬양 N` already parsed, so mixed explicit and shorthand lines do not reuse a
  number.

### Hymn Version Selection

- When a hymn has both 새찬송가 and 통일찬송가 versions, 새찬송가 is the
  default in Praise and service-item selection.
- 통일찬송가 is an explicit exception. It remains selectable and is used by
  default only when it is the sole available hymn-book version.
- Existing linked song versions are preserved; this default applies when a
  version is newly selected or resolved.
- Worship preparation input and service-item auto-linking use the same
  preferred 새찬송가 default, so resolved hymn-score praise does not remain
  missing only because a version was not explicitly picked.

### Score Praise Output

- `특송` praise items with an assignee output a separate `특송 / 담당자`
  title-assignee slide before the normal praise song-title slide. The song-title
  slide remains visible and carries the song name.
- Hymn-score praise items such as `봉헌찬송` and `송영` keep the normal
  `song-title` title slide. Do not create a separate score-only title layout.
- Score-mode praise may resolve a song from the raw title, so rough input like
  `찬송 80` can find hymn score slides even before the item has a persisted
  `song_id`. `특송` is the explicit exception: it must never output hymn score
  images, even if an item still carries `outputMode: "score"`.
- Non-score praise items that require DB selection must not silently resolve
  lyrics by raw title alone. Leave them as `입력 필요` unless they have a
  linked song or explicit manual slide text.
- Only the score image slides use the score fullscreen contract. A score image
  slide must render as the primary `score` slide class before generic image
  handling so fullscreen output does not inherit chromakey or lower-bar image
  fallback behavior.
- Score image slides remain clean fullscreen media with a white score canvas and
  no visible presenter meta. Title slides remain the same praise title contract
  as non-score praise.
- In chromakey services, the automatic blank after a score image returns to the
  chromakey blank context. It must not appear as a black fullscreen blank behind
  or after the score.

### Presenter Song Forms

- Explicit song-form presets may intentionally omit unlisted forms when they
  are grouped (`V1A`, `V1B`), manual/forced/song-default presets, or contain
  deliberate consecutive repeats such as `C-C`.
- User-entered `manual` song forms are exact output instructions. A typed
  sequence such as `V-C-V-C` or `V-C-V-C-Tag` must not auto-preserve unlisted
  `Bridge`, `Pre-Chorus`, or extra chorus forms from the linked song version.
  Template `default` and `forced` presets follow the same exactness rule unless
  they explicitly list the supplemental forms.
- An automatic/default preset must not show `C 없음` when the linked source
  song has no chorus form at all. Explicit manual requests still surface a
  missing-form warning so an operator typo does not pass silently.
- Grouped labels such as `V1A` and `V1B` mean split `Verse 1` by lyric block.
  If there are no blank-line blocks, split evenly by lyric lines when possible.
- `amen`/`아멘` is not a song-form type. Existing form rows have been migrated
  to `Coda`; import, parser, backfill, and presenter paths must not create it.

## Source Of Truth

- Runtime public-worship template rules: `app.js`.
- Worship data ownership and persistence model:
  `docs/worship-data-contract.md`.
- Presenter-specific workflow and verification:
  `docs/thread-worship-presenter.md`.

## Worship Service Identity

- `mindex_worship_services`에는 범용 `tags`를 두지 않는다. 날짜별로 화면에
  표시할 공개 이름은 `service_alias`에 저장한다. 예: `온세대 찬양예배`,
  `청소년부 제자헌신예배`.
- `금요기도회`, `월삭예배`, `삼삼오오예배`, `문화예배`, `구역연합예배`는
  제목을 하나로 덮어쓰지 않는다. 전체 예배 목록 UI에서는 같은 family인
  `금요예배`로 묶고, 각 카드에는 variant 이름을 subtitle로 표시한다.
- 정규 예배 유형과 기본 제목은 `service_type_id`와 `title`이 소유한다.
  별명은 이 값을 덮어쓰지 않으며, 목록·검색·프레젠터 표시에서만 우선한다.
- 찬양대·찬양팀 이름은 해당 찬양 섹션의 담당자, 집회 없음·헌신예배 같은
  machine state는 typed `source_ref`, 절기와 교회 일정은 교회력 데이터가 각각 소유한다.
  별명에 이 값을 합쳐 저장하거나 새 범용 metadata bucket을 만들지 않는다.

## Presenter Output Rules
- Controller startup restores display coordinates in the background only when
  `window-management` permission is already granted. Otherwise display detection
  remains an explicit user action. Electron uses its existing display bridge.
  Output launch never awaits detection; saved available targets retain priority.
  Display-change events update future launch targets, never move or reopen live
  output windows, and never request fullscreen.
- `참고 화면`은 전역 presenter toolbar가 아니라 `설교` 또는 `광고` 섹션에 추가한다.
  `참고 화면 추가`는 해당 섹션의 마지막에 image element를 만들며, 이름과
  파일/링크를 채우면 기존 media contract로 clean fullscreen output에 송출한다.
  따라서 크로마키 예배에서도 참고 이미지는 green background나 lower bar를
  물려받지 않는다. 영상은 동일한 asset element contract를 확장해 추가한다.
- `주일오후예배`는 기본적으로 헌신예배 순서를 따른다. `특송`은
  악보(score)가 아니라 일반 praise/lyrics 입력이며, `봉헌찬송`만 score
  output을 사용한다. 헌신예배가 아닌 날에는 `특송`/`봉헌` slot을
  skip/hide한다.
- 크로마키 찬양 제목 slide는 본문 가사 크기와 별도로 더 큰 제목 scale을
  사용한다. 설교 제목 lower bar는 왼쪽 `설교` label을 출력하지 않고
  설교 제목을 왼쪽, 담당자를 오른쪽에 둔다.
- 모든 예배 타입의 설교 제목은 presenter와 프리뷰에서 홑낫표
  `｢제목｣`로 감싼다. 입력에 기존 따옴표가 있어도 출력에서는 중첩하지 않는다.
- 크로마키 lower-bar 성구는 하단 bar 안에 들어오는 것이 우선이다. 긴 절은
  presenter/thumbnail 공통 fit 로직으로 최대 32px까지 줄이고, bar 밖으로
  overflow시키지 않는다.
- Presenter sidebar의 순서 row를 누르면 개별 thumb가 아니라 해당 element
  subgroup의 시작점으로 board를 이동한다. 긴 찬양/지연 렌더 구간에서도
  선택된 순서의 입력·thumb 영역이 빈 화면 없이 보이는 것이 우선이다.

## Benediction Replacement
- 모든 예배의 축도 입력 영역에 `주기도문으로 변경` 버튼을 제공한다.
- 변경은 해당 예배 요소에만 저장하며 공통 양식과 다른 예배는 수정하지 않는다.
- `config.benedictionReplacement` version 1에 원래 축도 필드를 보관한다.
  원래 slot identity를 유지하여 재조회 시 축도가 다시 생성되지 않게 한다.
- 주기도문은 기존 공통 본문/렌더러를 사용한다. `축도로 되돌리기`는 보관한
  담당자, 제목, 메모를 복원하며 replacement metadata를 제거한다.
- 예배 document exceptions에는 `benediction_replacement` 사유를 남긴다.
- 주일 1부의 기존 설교자별 기본 순서 판정은 변경하지 않는다.

## Service Auto-Schedule Rules
- 금요 2주 문화예배와 3주 삼삼오오예배의 자동 배정은 2026년 8월에만
  적용한다. 이후 2·3주는 기본 금요기도회이며, 명시적으로 지정한 개별
  예외는 유지한다. 1주 월삭예배와 4주 구역연합예배 규칙은 유지한다.
- 어린이부 예배, 청소년부 예배, 청년부 예배는 주일 자동 생성 대상이다.
- 단, 해당 주일의 교회력 `church_schedule`에 `온세대 찬양예배`가
  명시된 경우에만 어린이부, 청소년부, 청년부 예배를 별도로 생성하지
  않는다. 그날은 3부 예배(`sunday-main`)가 통합 예배의 source of
  truth다. `service_alias`, 절기명, 메모, 부서 담당 정보만으로는 온세대
  variant를 자동 판정하지 않는다.
- 부서별 외부 모임처럼 해당 부서의 MINDEX 예배가 따로 없는 날은
  교회력 `church_schedule`의 stable phrase를 기준으로 해당 부서
  자동 생성을 제외한다. 예: `청년부 야외예배`는 `young-adult` 예배를
  생성하지 않는다. 기존에 자동 생성된 row도 auto-generated source_ref가
  확인될 때만 purge한다.
- 이미 일반 3부 template으로 materialized 된 3부 예배가 나중에 교회력상
  온세대 찬양예배로 판정되면, projection 단계에서 수정되지 않은 일반
  3부 전용 항목(`참회기도`, `찬송`, `입례찬양`, `사도신경`, `공동체고백`,
  기존 `봉헌찬송`, `폐회찬송`)은 제거한다. `새가족환영`은 3부 공통 안내 slot으로
  유지한다. 사용자가 수정한 항목은
  `template_modified`를 존중해 보존한다.

## Empty Praise Removal from Source Text
- 예배 원문에서 빈 찬양 줄을 지우면 해당 예배의 template suppression을 저장하여 재조회·양식 투영 후에도 다시 생성하지 않는다.
- 원문 항목이 모두 매칭된 경우만 적용하며, 곡·직접 입력·가사·파일이 있는 순서와 찬양 이외 항목은 이 처리로 삭제하지 않는다.

## Linked Praise Hydration and Medley Labels
- 곡 목록 로딩 지연·실패로 연결된 곡을 찾지 못해도 저장된 song/version ID를 지우지 않는다. 연결 해제와 직접 입력 전환은 기존 명시적 사용자 동작으로 처리한다.
- 원숫자 변환은 송출 슬라이드 내부에만 적용한다(메들리 포함: `찬양 6–7` → `찬양 ⑥–⑦`). 컨트롤러 목록·입력 제목은 저장된 일반 숫자를 유지한다. 썸네일·미리보기의 슬라이드 내용은 실제 송출과 동일하다.

## Song Form Input Normalization
- 송폼 입력·저장 시 알려진 영문 토큰을 `V`, `PC`, `C`, `B`, `Int`, `Tag`, `Tags`, `Coda`, `VL`로 정규화하고 구분자 앞뒤 공백을 제거한다. 예: `v1a - pc - c - 간주` → `V1A-PC-C-Int`.
- 절 번호·부분 구분·반복 순서·빈 입력은 유지한다. 한글 표기도 `1절 → V1`, `후렴 → C`, `마지막 절 → VL`, `간주 → Int`로 통일한다. 알 수 없는 토큰은 임의로 바꾸거나 삭제하지 않는다.

## Calendar Assignees at Service Creation
- 자동·수동 예배 생성 시 교회력을 먼저 읽고 담당을 실제 `mindex_worship_elements.person`에 저장한다. 어린이부·청소년부·청년부 대표기도 및 청소년부 봉헌기도에 동일한 규칙을 적용한다.
- 화면·주보는 교회력 담당을 실시간 대체값으로 사용하지 않는다. 생성 이후 교회력 변경이나 재조회로 저장된 담당(빈칸 포함)을 덮어쓰지 않는다.
- 교회력 로딩 실패는 담당이 없는 날과 구분하여 생성을 중단한다. 담당 요소 저장 실패 시 이번에 만든 예배만 정리하고 오류를 알린다.

## Setlist Sunday Order and Worship Leaders
- 역대 콘티의 통합 주일예배 카드는 2부 특송을 가장 먼저 표시하며 나머지 곡 순서는 유지한다. 기존에 카드 안에 들어 있던 2부 특송과 별도 2부 예배에서 합친 특송에 같은 규칙을 적용한다.
- 주일·수요 콘티의 인도는 찬양단 이름보다 저장된 예배 인도자를 우선한다. 일반 주일예배는 김석범 목사, 온세대는 이재희 청년이다.
- 수요예배 인도는 2026-07-15까지 김석범 목사, 2026-07-22부터 김광한 전도사·김석범 목사가 주별로 교대한다. 신규 생성 시 저장하며 찬양단·설교 담당은 변경하지 않는다.
