# 청년부 주보 archive review

Reviewed: 2026-09-23. Scope: fixed content, changes, recurrence and implications for MINDEX.
This is source evidence and a design recommendation, not authorization to backfill production data.

## Coverage and limits

- 청년부 주보 폴더의 PDF **72개 / 144쪽** 전체에서 텍스트·페이지 규격을 읽어 비교했다.
  2024년 4개(11/24–12/15), 2025년 42개(1/5–12/21), 2026년 26개(1/18–9/20).
- 전부 A4 가로 297 × 210 mm, 2쪽이다.
- 2024-11-24, 2025-05-04, 2025-12-21, 2026-01-18, 03-29, 05-24, 06-07,
  09-20의 앞뒷면 16쪽은 렌더링으로 배치도 확인했다. 모든 호의 정밀 좌표를 측정한 것은 아니다.
- 비교 기준은 파일명 날짜와 지면 내용이다. 파일이 없다는 사실만으로 휴회나 미발행을 단정하지 않는다.
  주보에 예고된 일정도 최종 실시 여부를 증명하지 않는다.
- 원본과 운영 DB를 변경하지 않았다. 추출 텍스트·비교 이미지는 메모리에서 처리했고 중간 파일을 만들지 않았다.
  아래 날짜는 별도 명시가 없으면 **자료에서 처음 관찰한 날짜**이며 실제 효력 발생일과 다를 수 있다.

## Field matrix

| 구분 | 내용 | 관찰한 주기 | MINDEX에서 관리할 방식 |
| --- | --- | --- | --- |
| 구조 | A4 가로 양면, 중앙 접지, 일정/소식·표지·예배순서·노트 | 장기 유지 | Template version |
| 공동체 설정 | 교회명, 웹사이트, 주소, 예배 시간·장소 | 장기 유지하되 중간 변경 가능 | 적용 시작일을 둔 shared profile |
| 표어·성구 | 공동체 표어와 성경 구절 | 수개월~연간 이상 | 연도만 고정하지 않는 적용 기간 |
| 섬김이 | 직책, 이름, 직분 | 임원 개편 시 | 직책별 목록 + 적용 기간 |
| 상시 안내 | 환영, 이단 출입 금지, 정기 기도 모임 | 지속하되 시간/노출 변경 | 반복 안내 + 해당 호 표시 여부 |
| 날짜·호수 | 실제 발행일, 연내 연속 호수 | 발행할 때 | 발행 기록으로 번호 제안, 수동 수정 허용 |
| 예배 | 찬양, 인도자, 대표기도, 본문·설교, 결단찬양 | 매 예배 | 저장된 worship DB |
| 준고정 예배곡 | 봉헌곡, 파송곡 | 일정 기간 유지 | 예배 원본 우선, 주보에 곡명 하드코딩 금지 |
| 교회력 | 절기·주일 명칭, 기념주일 | 주별/절기별 | 교회력 DB + 복수 명칭 |
| 일정 | 월삭, 온세대 찬양예배, 특별기도회 | 월간 + 행사별 | 표시 대상 월 선택 + 실제 일정 |
| 위원표 | 날짜별 기도자, 연합/야외예배 등 상태, NEXT | 월간 목록을 매주 갱신 | 날짜별 상태와 담당자, 발행일 기준 NEXT |
| 소식 | 셀 모임, 수련회, 모집, 일정 변경 | 주간 + 수주간 반복 | 공지별 노출 기간·상태·이번 주 문구 |
| 설교 요점 | 번호 목록, 제목·본문, 선택적 성경 쪽수 | 매 예배, 없는 호도 있음 | 선택 필드, 없을 때 공간 보존 |
| 배경 | 사진·색상·절기 전용 배경·로고 표현 | 계절/절기/디자인 개편 | 자산을 공유하는 theme version |

## Confirmed changes

| 경계 자료 | 관찰 |
| --- | --- |
| 2025-01-26 → 02-02 | 표어가 “하나님의 주 되심을 인정하는 청년들”/시편 127:1에서 “말씀으로 인도받는 RIA 청년 공동체”/이사야 49:10b로 바뀐다. 2026-09-20까지 후자를 유지한다. 따라서 매년 1월 자동 교체 규칙은 근거가 없다. |
| 2025-03-09 → 03-16 | 3/9 소식에 다음 주부터 봉헌·파송찬양 추가를 예고하고 3/16 순서에 반영한다. 예배순서 자체도 템플릿에 영구 고정하면 안 된다. |
| 2025-04-27 → 05-04 | 온세대 찬양예배 안내 시각이 10:30에서 10:50으로 바뀐다. 청년부 기본 예배 안내 13:10과는 별개다. |
| 2025-09-07 → 09-14 | 토요일 기도 모임 안내가 오전 10시에서 오전 11시로 바뀐다. |
| 2025-11-30 → 12-07 | 11/30 청년부 정기총회 공지 이후 새 임원 구성이 지면에 나타난다. 회장 김음파, 총무 이재희, 서기 박지훈, 회계 서영윤. 2026년 자료 26개에서 유지된다. 임기는 1월부터라는 가정이 맞지 않는다. |
| 2025-12-21 → 2026-01-18 | 단체사진 중심 표지에서 RIA 마크 중심으로 개편한다. 중보기도/정리 담당 등 2025 요소를 2026 필수 필드로 가져오면 안 된다. |
| 2026-05-24 → 05-31 | 5/31 소식에 기도 모임을 토요일 오후 3시로 변경했다고 명시한다. 6/7부터 상시 안내에도 반영된다. |
| 2026-06-28 → 07-05 | 지면 주소가 “인천광역시 서구”에서 “인천광역시 검단구”로 바뀐다. 이는 주보 표기 변화 확인이며 행정 법령 효력일에 대한 판단은 아니다. |
| 2026-07-26 → 08-02 | 일정 명칭이 “월삭예배”에서 “온세대 월삭예배”로 바뀐다. |
| 2026-08-23 → 09-06 | 9월호는 물결·낙엽 배경과 분리된 흰 패널을 쓴다. 기존 검은 RIA와 달리 로고 내부에도 배경 이미지가 보인다. 9/20 단일 배경을 전 기간 공통으로 취급하면 안 된다. |

현재(마지막 자료 기준) 장기 설정 후보: 기독교대한성결교회 검단우리교회,
gdwoori.org, 인천광역시 검단구 완정로 178번안길 1,
주일 오후 1:10 / 1층 베데스다홀. 위임목사 김남영, 담당 교역자 김석범.
이 값들은 과거 지면에 소급 적용할 상수가 아니라 최근 버전의 후보값이다.

## Recurrence and exceptions

### Issue numbering and omitted dates

2025년은 1/5 제1호, 1/12 제2호, 1/26 제3호이고,
2026년은 1/18 제1호, 1/25 제2호, 2/8 제3호다.
각 연도에서 존재하는 파일의 호수는 연속이며 2026-09-20은 제26호다.
ISO week나 그해 지난 주일 수로 호수를 계산하지 않는다.

2026-08-23 소식은 8/30 야외예배를 예고하며 8/30 PDF는 없다.
2026-07 위원표는 7/12 연합예배를 표시하며 그날 PDF는 없다.
다만 2026-04-05처럼 앞 주보에서 별도 예배를 예고했는데 파일이 없는 경우도 있다.
자료 부재만으로 예배 상태를 생성하지 않는다.

### Calendar and roster months

- 2026년 26개 자료의 위원표는 **발행 월의 모든 주일 + 다음 달 첫 주일**이다.
  4주인 달은 5칸, 5주인 달은 6칸이다. 담당자 없는 특별 일정도 한 칸을 차지한다.
- NEXT는 시각 확인한 자료에서 다음 주일 칸에 붙는다.
  6/7판의 NEXT는 6/14이고, 이후 6/21판에서 6/14가 “선교사 파송예배”로 수정된다.
  1/25판의 다음 주는 “사무총회”다. 다음 **기도자 있는 날**만 찾아 건너뛰는 규칙은 부족하다.
- 동일 월에도 담당자와 상태가 바뀐다. 2026-04-12→04-19에 4/19·4/26 배정이,
  08-02→08-16→08-23에 8/9·8/23·8/30·9/6 배정/상태가 수정된다.
  최신 DB 조회와 발행 당시 snapshot 보관을 구분해야 한다.
- 2025년은 대체로 월말 마지막 주일에 **위원표 전체를 다음 달로 교체**한다.
  1/26→2월, 2/23→3월, 4/27→5월, 10/26→11월 등이 확인된다.
  2026 방식과 다르므로 historical template별 정책이 필요하다.
- 교회 일정의 표시 월도 항상 발행일의 달은 아니다.
  2025-03-30은 4월, 06-29는 7월, 08-31은 9월, 09-28은 10월, 11/30은 12월 일정이다.
  특히 1/26은 일정 1월·위원표 2월로 서로 다르다. 표시 월 두 개를 독립 선택해야 한다.
- 2025 초반 “몇째 주”는 단순히 그달 몇 번째 일요일과 일치하지 않는다.
  1/5를 “둘째 주”로 쓴다. 주간 구간의 월 귀속 관례인지 확정하지 않고,
  현행 교회력 주일 명칭을 우선한다.

### Repeating events and notices

- 2026년 1~9월 일정의 월삭예배는 첫 금요일 20:00이다.
  온세대 찬양예배는 10:50이나 셋째 주일로 고정되지 않는다(2/22·3/22·8/23은 넷째).
  반복 규칙은 후보 생성에만 쓰고 확정 일정이 우선해야 한다.
- 셀 모임은 자주 반복되지만 연합 셀 모임, 생일 파티, 공연 연습, 총회 등으로 바뀐다.
  “오늘 2부 활동”을 무조건 셀 모임으로 생성하지 않는다.
- 2025-01-05의 10·11·12월 생일 파티, 02-09의 1·2월, 04-13의 3·4월 파티는
  묶음 개최의 근거다. 그러나 매월/격월 특정 주 자동 규칙을 확정할 표본은 부족하다.
- 수련회 공지는 여러 주 재사용하되 문구가 “공지”→“일주일 후”→“오늘”로 변한다.
  2026-07-26·08-02가 명확한 예다. 2025 MT도 5/4판 5/23–24에서
  5/11판 5/30–31로 수정된다. 단순 전주 복사 대신 공지의 날짜·상태가 필요하다.
- 상시 안내도 지면 사정에 따라 빠진다. 2026-06-21에는 수련회·단기선교 공지가 늘면서
  다른 주에 있던 하단 두 안내가 텍스트에서 빠진다. 매호 표시 여부를 조절할 수 있어야 한다.
- 2024 말~2025-05-04에는 찬양·서적·기도·말씀 “주간 코너”가 있다.
  2025-01-05 찬양→01-12 말씀→01-26 서적→02-02 기도 순환이 보이지만,
  4월에는 순서가 달라지고 5/11 이후에는 해당 제목이 사라진다.
  현행 기능의 강제 4주 순환으로 도입하지 않는다.

### Worship order and notes

2026년 26개 모두에 “임재”와 “피난처 되시는 주 예수”가 나오고,
시각 확인한 자료에서 봉헌곡·파송곡으로 배치된다.
이는 기간 내 준고정 사용이며 향후에도 고정된다는 보장은 아니다.
찬양 인도자·설교자는 대체자가 있고, 2025-05-04에는 축도 대신 주기도문이 있다.
순서·담당자·곡은 저장된 예배 원본을 사용해야 한다.

말씀 요약은 없는 호(2026-01-18, 01-25, 07-26)도 있다.
2026-08-02에는 요점 네 개가 있지만 “말씀 요약” 제목은 없다.
2026-07-26까지 자주 있던 성경 쪽수가 8월 이후 표본에는 빠진다.
제목·요점·성경 약칭·쪽수·노트 줄은 각각 선택 가능해야 한다.
과거 누락된 요점을 AI가 임의로 만들어 채우지 않는다.

### Visual themes

2024/2025 표본은 단체사진과 띠 색상이 중심이고,
2026년은 RIA 마크 중심으로 큰 구역을 유지한다.
2026-01-18은 짙은 녹색 배경, 03-29 종려·수난주일은 종려잎,
05-24 성령강림주일은 빛/주황 계열, 06-07은 어두운 외곽과 흰 내부,
09-20은 물결·낙엽과 분리된 흰 패널이다.
배경의 정확한 정기 교체 주기는 이 표본만으로 확정하지 않는다.
계절 기본 테마에 특별 주일 override를 두는 구조를 권장한다.
로고 색/채움도 테마 자산에 속하며 본문 내용과 분리한다.

## Implications for the current implementation

검토 시점의 초기 구현과 비교한 후속 작업이다. 조사 후 사용자 승인으로 날짜별 공통 문구와 재사용,
위원표/NEXT, 표시 월 분리, 배경 선택, 프레임 숨김, 확인된 과거 호수 기본값을 반영했다.
아래의 DB 발행 기록·snapshot, 공지별 기간 관리, 과거 테마 복원은 여전히 후속 범위다.

1. **Shared profile + effective dates:** 교회·표어·섬김이·상시 안내를 예배별 빈 입력으로
   시작하지 않고 해당 날짜의 설정에서 가져온다. 과거 발행본 값은 보존한다.
2. **Roster status:** 조사 당시 resolveSource는 young_adult_prayer가 비어 있는 날짜를 제외했다.
   연합·야외예배·총회 등의 상태 행도 유지하고 NEXT를 다음 주일에 표시하도록 보완한다.
3. **Independent display months:** 교회 일정 월과 위원표 월을 분리하고,
   2026년의 월 전체+다음 달 첫 주일 정책을 명시한다.
4. **Publication sequence:** 발행 기록 기준 호수 제안과 연도별 번호를 지원한다.
   예배가 있다고 모두 발행한 것으로 처리하지 않는다.
5. **Theme/profile versioning:** 현재 9월 배경 하나를 계절·특별 주일 자산 선택으로 확장한다.
   2025 양식을 지원하려면 다른 frame set이 필요하다.
6. **Reusable notices:** 기간·일정 변경·이번 주 상대 문구와 선택적 표시를 지원한다.
   주보 소식은 예배 광고의 초기값을 받을 수 있지만 독립 편집·이력을 가져야 한다.
7. **Optional note sections:** 요약 제목, 요점, 성경 쪽수, 노트 줄을 독립 제어한다.
8. **Validation:** 9/20 소식 번호가 ①·①로 중복된 것처럼 원본에도 편집 실수가 있다.
   원본 오탈자/중복을 템플릿 규칙으로 학습하지 않고 번호는 자동 생성한다.

추천 저장 구분은 profile version / template version / dated service and calendar /
dated announcements / published issue snapshot이다. 별도 DB 스키마는 Data 영역과 협의할 후속 범위다.

## Source inventory

원본 위치 링크. 이름의 6자리 날짜는 YYMMDD이다. 아래 목록은 열람 범위를 고정하며 원문 사본을 저장하지 않는다.

- [청년부 주보 241124.pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2024/청년부 주보 241124.pdf>)
- [청년부 주보 241201.pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2024/청년부 주보 241201.pdf>)
- [청년부 주보 241208.pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2024/청년부 주보 241208.pdf>)
- [청년부 주보 241215.pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2024/청년부 주보 241215.pdf>)
- [청년부 주보 250105 (제1호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250105 (제1호).pdf>)
- [청년부 주보 250112 (제2호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250112 (제2호).pdf>)
- [청년부 주보 250126 (제3호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250126 (제3호).pdf>)
- [청년부 주보 250202 (제4호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250202 (제4호).pdf>)
- [청년부 주보 250209 (제5호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250209 (제5호).pdf>)
- [청년부 주보 250216 (제6호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250216 (제6호).pdf>)
- [청년부 주보 250223 (제7호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250223 (제7호).pdf>)
- [청년부 주보 250309 (제8호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250309 (제8호).pdf>)
- [청년부 주보 250316 (제9호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250316 (제9호).pdf>)
- [청년부 주보 250323 (제10호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250323 (제10호).pdf>)
- [청년부 주보 250330 (제11호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250330 (제11호).pdf>)
- [청년부 주보 250413 (제12호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250413 (제12호).pdf>)
- [청년부 주보 250420 (제13호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250420 (제13호).pdf>)
- [청년부 주보 250427 (제14호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250427 (제14호).pdf>)
- [청년부 주보 250504 (제15호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250504 (제15호).pdf>)
- [청년부 주보 250511 (제16호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250511 (제16호).pdf>)
- [청년부 주보 250518 (제17호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250518 (제17호).pdf>)
- [청년부 주보 250525 (제18호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250525 (제18호).pdf>)
- [청년부 주보 250601 (제19호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250601 (제19호).pdf>)
- [청년부 주보 250615 (제20호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250615 (제20호).pdf>)
- [청년부 주보 250622 (제21호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250622 (제21호).pdf>)
- [청년부 주보 250629 (제22호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250629 (제22호).pdf>)
- [청년부 주보 250720 (제23호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250720 (제23호).pdf>)
- [청년부 주보 250727 (제24호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250727 (제24호).pdf>)
- [청년부 주보 250803 (제25호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250803 (제25호).pdf>)
- [청년부 주보 250810 (제26호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250810 (제26호).pdf>)
- [청년부 주보 250817 (제27호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250817 (제27호).pdf>)
- [청년부 주보 250831 (제28호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250831 (제28호).pdf>)
- [청년부 주보 250907 (제29호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250907 (제29호).pdf>)
- [청년부 주보 250914 (제30호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250914 (제30호).pdf>)
- [청년부 주보 250921 (제31호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250921 (제31호).pdf>)
- [청년부 주보 250928 (제32호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 250928 (제32호).pdf>)
- [청년부 주보 251012 (제33호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251012 (제33호).pdf>)
- [청년부 주보 251019 (제34호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251019 (제34호).pdf>)
- [청년부 주보 251026 (제35호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251026 (제35호).pdf>)
- [청년부 주보 251102 (제36호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251102 (제36호).pdf>)
- [청년부 주보 251109 (제37호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251109 (제37호).pdf>)
- [청년부 주보 251116 (제38호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251116 (제38호).pdf>)
- [청년부 주보 251130 (제39호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251130 (제39호).pdf>)
- [청년부 주보 251207 (제40호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251207 (제40호).pdf>)
- [청년부 주보 251214 (제41호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251214 (제41호).pdf>)
- [청년부 주보 251221 (제42호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2025/청년부 주보 251221 (제42호).pdf>)
- [청년부 주보 260118 (제1호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260118 (제1호).pdf>)
- [청년부 주보 260125 (제2호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260125 (제2호).pdf>)
- [청년부 주보 260208 (제3호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260208 (제3호).pdf>)
- [청년부 주보 260222 (제4호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260222 (제4호).pdf>)
- [청년부 주보 260308 (제5호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260308 (제5호).pdf>)
- [청년부 주보 260322 (제6호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260322 (제6호).pdf>)
- [청년부 주보 260329 (제7호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260329 (제7호).pdf>)
- [청년부 주보 260412 (제8호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260412 (제8호).pdf>)
- [청년부 주보 260419 (제9호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260419 (제9호).pdf>)
- [청년부 주보 260426 (제10호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260426 (제10호).pdf>)
- [청년부 주보 260510 (제11호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260510 (제11호).pdf>)
- [청년부 주보 260517 (제12호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260517 (제12호).pdf>)
- [청년부 주보 260524 (제13호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260524 (제13호).pdf>)
- [청년부 주보 260531 (제14호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260531 (제14호).pdf>)
- [청년부 주보 260607 (제15호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260607 (제15호).pdf>)
- [청년부 주보 260621 (제16호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260621 (제16호).pdf>)
- [청년부 주보 260628 (제17호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260628 (제17호).pdf>)
- [청년부 주보 260705 (제18호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260705 (제18호).pdf>)
- [청년부 주보 260719 (제19호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260719 (제19호).pdf>)
- [청년부 주보 260726 (제20호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260726 (제20호).pdf>)
- [청년부 주보 260802 (제21호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260802 (제21호).pdf>)
- [청년부 주보 260816 (제22호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260816 (제22호).pdf>)
- [청년부 주보 260823 (제23호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260823 (제23호).pdf>)
- [청년부 주보 260906 (제24호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260906 (제24호).pdf>)
- [청년부 주보 260913 (제25호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260913 (제25호).pdf>)
- [청년부 주보 260920 (제26호).pdf](</Users/parkjihun/Library/CloudStorage/OneDrive-Personal/02_Church/12_주보/04_청년부 주보/청년부 주보 2026/청년부 주보 260920 (제26호).pdf>)
