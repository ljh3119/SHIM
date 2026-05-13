# SHIM Dense UI 스타일 변경 실행 가이드 (Dense Console 확정본)

## 문서 목적
- 이 문서는 `SHIM` 본 프로그램의 스타일을 **Dense Operations Console** 방향으로 이식하기 위한 **실행 가이드**다.
- 대상 독자는 다른 AI(또는 신규 작업자)이며, 이 문서만 읽고도 안전하게 작업할 수 있어야 한다.
- 목표는 "새로운 기능 추가"가 아니라 **기존 기능/데이터를 유지한 스타일 변경**이다.
- 아래 **[레이아웃·적용 범위 (프로젝트 확정)]** 에 따라 템플릿에 순차 반영한다.

---

## 확정된 디자인 방향
- 최종 방향: **Dense Operations Console**
- 핵심 키워드: 빠른 스캔, 높은 정보 밀도, 테이블 중심, 상태 강조
- 비목표:
  - 과한 장식(글래스모피즘, 네온, 과한 그림자)
  - 마케팅형 히어로/카피
  - 실제 미지원 액션 버튼 추가

---

## 레이아웃·적용 범위 (프로젝트 확정)

다음은 추후 논의 대상이 아니라 **현재 프로젝트에서 확정된 전제**다.

1. **메인 내비게이션 — 사이드바**
   - 정보 구조의 중심은 **좌측 Dense 사이드바**다. 접기/펼치기·active 스타일·아이콘+라벨 규칙은 본 문서 [사이드바 통일 규칙](#사이드바-통일-규칙-adminuser-공통) 및 `samples/*/dense-operations-console.html` 등 시안과 동일 계열로 맞춘다.
   - 관리자·사용자 각각 메뉴 항목만 다르고 **컴포넌트는 동일**하게 구현한다.

2. **상단 영역 (`base.html`) — 보조·외형**
   - 글로벌 상단 바는 **구조(로그인 여부·로그아웃·역할별 링크 등)를 유지**한다.
   - **디자인은 Dense 톤에 필요한 만큼만** 맞춘다 (브랜드 마크·구분선·여백·타이포 등 **모양만** 정리). 본문 네비게이션을 상단으로 다시 늘리지 않는다.

3. **적용 범위 — 전역**
   - **모든 주요 화면**을 Dense 문법·토큰으로 정렬한다. (`login.html`, 관리자·사용자 대시보드, 타임라인·캘린더·사원·휴일·마스터, 공통 `base.html` 등 `src/templates/`의 실사용 템플릿 전부.)
   - 로그인 포함 **글래스 중심 UI는 Dense에 맞게 축소·평탄화**하고, 샘플 `dense-login-shell.html` 계열 톤으로 맞춘다.

---

## 상단 바·사이드바 UX 표준 (확정)

- **메인 내비는 사이드바만**: 화면 이동은 **좌측 사이드바 링크**로 한다. 상단(`base.html`)에는 **브랜드(홈)**, **비밀번호 변경**(로그인 시), **로그아웃**만 둔다. 예전처럼 상단에 대시보드·캘린더 등을 **나란히 두지 않는다**(경로 중복·시선 분산 방지).
- **위계**: 사이드바 active는 **연한 블루 배경 + 블루 텍스트**. 상단 텍스트 링크는 **muted 톤**으로 두어 본문·사이드가 우선 보이게 한다.
- **브랜드 클릭 목적지**: 관리자 세션 → `/admin/dashboard`, 일반 사용자 세션 → `/user/dashboard`, 비로그인 → `/`(로그인). 라우트 변경 없음.
- **공통 구현 위치**: 관리자 메뉴는 `src/templates/partials/sidebar_admin.html`, 사용자 메뉴는 `partials/sidebar_user.html`에서만 확장한다. 새 관리 화면은 라우트 추가 후 해당 partial에 항목만 더한다.
- **로그인 페이지**: 사이드바 없음. 상단도 최소한만 유지한다.

---

## 색상 토큰 (제품)

- **단일 소스**: `src/static/css/app.css` 의 `@theme` 블록에 Dense 팔레트가 정의되어 있다. 빌드: `npm run build:css` → `src/static/css/tailwind.css`.
- **Tailwind 유틸 예**: `bg-dense-bg`, `text-dense-text`, `border-dense-line`, `bg-dense-blue`, `bg-dense-blue-soft`, `text-dense-muted`, `bg-dense-amber-soft`, `text-dense-amber` 등.
- **시안 동기화**: `design/ui-handoff/samples/reference/dense-tokens.css` 의 값과 맞출 것(주석에 제품 경로 명시됨).
- **레거시 인디고 유틸**: 페이지 개선 시 새 코드는 가능하면 **dense-* 유틸**로 교체한다. 한 번에 못 바꿔도 동작에는 문제 없으나 최종적으로는 통일한다.

---

## 작업 대상 (실서비스 템플릿)

- **공통**: `src/templates/base.html`
- **공통 partial**: `src/templates/partials/sidebar_admin.html`, `src/templates/partials/sidebar_user.html`
- **인증**: `src/templates/login.html`
- **관리자**: `src/templates/admin_dashboard.html`, `admin_leaves_timeline.html`, `admin_leaves_calendar.html`, `admin_users.html`, `admin_holidays.html`, `admin_master.html`
- **사용자**: `src/templates/user_dashboard.html`
- **기타**: 위 목록에 포함되는 매크로·부분 템플릿이 있으면 동일 토큰·문법으로 통일한다.

> `design/ui-handoff/samples/*` 파일은 시안·합의용이다. 실반영은 반드시 `src/templates/*`에서 한다.

---

## 절대 고정 조건
- 데스크톱 전용
- 폐쇄망 환경 (외부 CDN/웹폰트/원격 리소스 금지)
- 시스템 폰트만 사용
- 기존 기능/데이터 바인딩 유지 (Jinja 변수, 루프, 라우트, 폼 액션 변경 금지)
- 미지원 기능 노출 금지
- 안내성/추천성 문구 최소화

---

## 관리자 화면 필수 구조 (변경 금지)
1. 헤더: `관리자 대시보드` + 상태값 1개
2. KPI 4개:
   - 활성 사원 수
   - 금일 신청 건수
   - 결재 대기 건수
   - 금일 사용 연차(h)
3. 최근 7일 신청 타임라인 테이블
4. 필터 버튼: `전체 / 결재 대기 / 승인됨 / 반려`

### 관리자 화면 금지 요소
- 히어로 섹션 추가
- "추천", "도움말", "가이드 문장"성 카피
- 실제 동작하지 않는 버튼 (예: 일괄 승인, 리포트 다운로드)

---

## 사용자 화면 권장 구조
- 헤더: `사용자 대시보드` + 연도 정보
- KPI 4개: 총 연차 / 사용 / 잔여 / 결재 대기
- 신청 내역 테이블
- 연차 신청 패널
- (기존 기능 존재 시) 연도 선택, 신청 폼, 캘린더/모달은 유지

> 사용자 화면은 관리자만큼 강한 고정 규격은 아니지만, **동일한 디자인 문법**(색상/간격/컴포넌트 톤)을 유지한다.

---

## 사이드바 통일 규칙 (admin/user 공통)
- 동일 컴포넌트로 구현한다. (메뉴 항목만 다름)
- 공통 요구:
  - 접기/펼치기 토글 지원
  - 펼침: 아이콘 + 라벨
  - 접힘: 아이콘만 표시
  - active 항목은 Blue soft 배경 + Blue 텍스트
  - 사이드바 패널 스타일(반경/패딩/보더) admin/user 동일
- 접근성:
  - 토글 버튼 `aria-expanded` 갱신
  - 키보드 포커스 outline 유지

---

## 색상/타이포/컴포넌트 토큰 원칙
- 상태색 의미 고정:
  - 대기/주의: Amber
  - 완료/정상: Green
  - 선택/정보: Blue
- KPI 강조:
  - 기본은 중립 톤
  - `결재 대기`만 우선순위 색 강조 가능
- 테이블:
  - 헤더 대비 명확
  - 숫자 컬럼 우측 정렬
  - 배지는 연한 배경 + 진한 텍스트

---

## 구현 절차 (다른 AI 작업 순서)
1. 제품 색 토큰은 **`src/static/css/app.css`의 `@theme`** 이 단일 소스다. 변경 후 `npm run build:css` 로 `tailwind.css`를 갱신한다.
2. **사이드바 공통 partial**은 `partials/sidebar_admin.html`, `partials/sidebar_user.html` 에 구현되어 있다. 메뉴 추가·active 규칙 변경 시 이 파일만 수정한다. 상단 `base.html`은 계정 액션·브랜드만 유지한다.
3. 기존 Jinja 바인딩·라우트·폼 액션을 보존한 채 **본문 레이아웃**을 Dense 그리드로 정리한다.
4. **관리자 본편**을 먼저 완성한다 (`admin_dashboard.html` 고정 규격 우선).
5. **사용자 대시보드**를 동일 컴포넌트 문법으로 동기화한다.
6. **나머지 관리자 페이지**(타임라인·캘린더·사원·휴일·마스터 등)와 **로그인**을 순차 적용한다.
7. **전 페이지 반영 후** `base.html` 상단 바를 Dense 톤으로 한 번 더 통일(과장 없이)한다.
8. 레이아웃 stretch 이슈 확인 — 카드가 비정상적으로 세로로 늘어나면 `grid align-items/align-content` 점검
9. 최종 점검 체크리스트 수행

---

## 의사결정 기록 (확정 요약)

| 항목 | 결정 |
|:---|:---|
| 네비게이션 | **사이드바**가 본문의 메인 내비. 상단은 보조·필요 시 외형만 조정. |
| 적용 범위 | **전역** — 나열된 모든 주요 템플릿에 Dense 적용. |
| 로그인·장식 | **Dense 정렬** — 과한 글래스는 줄이고 토큰·밀도 우선. |

추가로 운영 정책 문서(`docs/` 번호 체계)와 충돌하는 표현이 없는지 배포 전 검토한다.

---

## 전역 rollout 순서 (권장)

- 목표는 **전 페이지 Dense**다. 아래는 **병행 리스크를 줄이기 위한 권장 순서**이며, 범위를 줄이는 것이 아니다.
  1. 공통: 사이드바 컴포넌트 + 토큰 매핑 초안
  2. `admin_dashboard.html` → `user_dashboard.html`
  3. `admin_leaves_timeline.html` → `admin_leaves_calendar.html`
  4. `admin_users.html` → `admin_holidays.html` → `admin_master.html`
  5. `login.html`
  6. `base.html` 상단 바 최종 톤 정리

- 시안(`samples/*`)은 필요 시만 수정하고, 구현의 근거는 항상 본 문서와 템플릿이다.

---

## 품질 게이트 (완료 조건)
- [ ] 관리자 대시보드 헤더가 `관리자 대시보드 + 상태값 1개` 형태인가?
- [ ] KPI 4개/타임라인/필터 4종이 관리자 본편에서 유지되는가?
- [ ] 미지원 액션/안내성 카피가 없는가?
- [ ] 상태 배지 색 의미가 **전 페이지**에서 일관적인가?
- [ ] admin/user 사이드바가 동일 컴포넌트 규칙인가? (접기/펼치기·active·아이콘 두께)
- [ ] 로그인·마스터·사원 등 부가 화면까지 Dense 토큰·밀도에 맞는가?
- [ ] `base.html` 상단이 본문과 어색하지 않게 최소 정렬되었는가? (과한 상단 메뉴 확장 없음)
- [ ] 기존 데이터 바인딩(Jinja)과 라우트/폼 동작이 깨지지 않았는가?

---

## 디자인 추가 개선 포인트 (차후 반영 후보)
아래 항목은 기능 변경 없이 시각 완성도를 올리는 개선안이다.

1. 밀도 미세 조정
- KPI 카드 세로 패딩을 1단계 축소해 첫 화면에서 타임라인 시작점을 더 위로 당긴다.
- 테이블 헤더 높이와 행 높이의 비율을 고정해 스캔 리듬을 일정하게 만든다.

2. 타이포 위계 통일
- 제목/패널제목/라벨/보조텍스트 크기 단계를 4단계로 고정한다.
- admin/user 간 동일 의미 텍스트는 동일 폰트 크기/굵기를 사용한다.

3. 상태 표현 정규화
- 배지 높이/패딩/테두리 두께를 단일 규격으로 통일한다.
- 숫자 강조(결재 대기 등)만 색 강조하고 설명 문구는 중립색으로 고정한다.

4. 사이드바 완성도
- 접힘 상태 아이콘 시각 무게를 맞추기 위해 아이콘 stroke를 단일 값으로 유지한다.
- 메뉴 간격과 active 배경 반경을 admin/user 동일 토큰으로 잠근다.

5. 테이블 가독성
- 날짜/사용자/상태/차감 컬럼의 최소 폭을 고정해 줌 환경에서도 레이아웃 붕괴를 줄인다.
- 긴 텍스트는 말줄임 + title 툴팁 패턴으로 통일한다.

---

## 참고 시안 파일 (디자인 레퍼런스)
- 관리자 Dense 시안: `design/ui-handoff/samples/admin/dense-operations-console.html`
- 사용자 Dense 시안: `design/ui-handoff/samples/user/dense-operations-console.html`
- 로그인 Dense 시안: `design/ui-handoff/samples/reference/dense-login-shell.html`
- 마스터 관리 Dense 시안: `design/ui-handoff/samples/admin/dense-master-shell.html`
- 사원 관리 표 Dense 시안: `design/ui-handoff/samples/admin/dense-users-table-shell.html`

> 이 파일들은 "모양 참고" 용도다. 실반영은 반드시 `src/templates/*`에서 한다.

---

## 차후 기능 변경(슬롯 -> 시간입력 자동계산) 대비 규칙
- 본 변경이 예정되어 있다면, 디자인 적용 전 기능 구조를 먼저 확정한다.
- UI 원칙:
  - 입력: 날짜 + 시작시각 + 종료시각 (+필요 시 휴게시간)
  - 결과: 차감 시간 자동 계산값을 제출 버튼 근처에 즉시 표시
  - 오류: 인라인 검증 메시지(종료<시작, 범위 초과 등)를 필드 하단에 노출
- 테이블 표기 원칙:
  - 슬롯 라벨 대신 `HH:MM-HH:MM (xh)` 형식으로 통일
  - 관리자/사용자 화면 모두 동일 표기 규칙 유지

---

## AI 작업 지시 템플릿 (복붙용)
```text
다음 작업을 수행해줘.

[목표]
- SHIM 전역 템플릿을 Dense Operations Console 스타일로 반영한다.
- 기능 추가가 아니라 스타일 이식이 목적이다.

[레이아웃 전제]
- 본문 메인 내비는 좌측 Dense 사이드바. 상단(base)은 필요 시 모양만 Dense 톤에 맞춘다.

[대상 파일]
- src/templates/base.html, login.html
- admin_dashboard.html, user_dashboard.html
- admin_leaves_timeline.html, admin_leaves_calendar.html
- admin_users.html, admin_holidays.html, admin_master.html
- (존재 시) 연관 부분 템플릿

[절대 조건]
- 기존 Jinja 변수/루프/폼 액션/라우트 변경 금지
- 외부 리소스(CDN/웹폰트/원격 이미지) 사용 금지
- 미지원 액션 버튼 추가 금지
- 관리자 대시보드 고정 구조(헤더+상태값, KPI 4개, 타임라인, 필터 4종) 유지
- admin/user 사이드바 동일 컴포넌트 + 접기/펼치기 + 접근성 속성 유지
- 로그인 등 나머지 화면도 Dense 토큰·밀도에 맞출 것 (과한 글래스 축소)

[산출물]
- 수정된 템플릿 파일
- 어떤 스타일 규칙을 통일했는지 요약
- 체크리스트 기준 자체 점검 결과
```
