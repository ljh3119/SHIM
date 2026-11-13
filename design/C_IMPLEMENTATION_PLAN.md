# C BASELINE 실제 앱 적용 계획

## 목표와 작업 경계

`design/braun-linear-exploration` 브랜치에서 기존 FastAPI·Jinja2·Tailwind 앱에 refined C BASELINE의 색, 밀도, 타이포그래피, 작은 모서리, 왼쪽 탐색 구조를 적용한다. 구현 담당은 `gemini-3.8-flash-medium`, 이후 독립 검증 담당은 Argon이다. 이 문서는 실행 계획이며 구현 완료 보고서가 아니다.

사용자는 기존 dirty prototype 작업을 명시적으로 승인했다. `.gitignore`, `.hallmark/`, `design/ui-mockup/braun-linear-exploration.html`, `design/ui-mockup/c-variants/`를 보존한다. dirty tree라는 이유로 중단하거나 정리하지 않는다. reset, checkout 복원, stash, clean을 실행하지 않는다. 커밋·푸시·릴리스·버전 변경은 범위 밖이다.

기준은 `design/ui-mockup/braun-linear-exploration.html`의 **C BASELINE**과 `c-variants/tokens.css`, `c-variants/c-system.css`의 공통 스타일 및 `Option C Baseline` 구간이다. `base.css`는 참조용이다. C1·C2·C3은 선택되지 않은 대안이다. 상단 탐색형 C1, 작업대형 C2, 명령 스트립형 C3의 구조를 섞지 않는다. 비교 페이지, 시안 선택 메뉴, 데모 데이터, 데모 JavaScript를 앱에 복사하지 않는다.

기존 화면을 유지하면서 시각 체계를 통일한다. 시안에 없는 관리자 화면도 동일 토큰을 적용하되, 표·필터·기능을 시안에 맞춰 삭제하거나 재설계하지 않는다. 새 프레임워크, 아이콘 패키지, 폰트 다운로드, CDN, 런타임 의존성은 필요하지 않다. 불가피하다고 판단되면 구현을 확장하지 말고 근거를 부모에게 전달한다.

## 확인한 근거와 미검증 항목

- OpenWiki `quickstart.md`, `architecture.md`, `testing.md`, `operations.md`, `workflows/admin.md`, `domain/leave-management.md`를 확인했다.
- `package.json`, `tailwind.config.js`, `src/static/css/app.css`, `base.html`, 사용자 달력·팀 달력 및 신청 partial의 관련 소스, `fragment_base.html`, 사용자 라우터의 템플릿 연결을 확인했다.
- `app.css`는 Tailwind v4 `@theme`에 `dense-*` 색을 정의하며 템플릿과 Python 파일을 `@source`로 스캔한다. 실제 CSS 링크는 `/static/css/tailwind.css?v={{ app_version }}`다.
- 개인·팀 달력은 `desktop_partial`에 따라 `base.html` 또는 `partials/fragment_base.html`을 상속한다. fragment base는 content 블록만 출력한다. 전체 페이지와 fragment가 같은 외형을 공유해야 한다.
- `base.html`에는 큰 radius를 가진 `.glass-panel`, `.shim-side-link`, sidebar 접기 규칙, toast 스타일이 인라인으로 존재한다. 토큰만 바꾸면 이 스타일과 각 화면의 명시적 유틸리티가 남는다.
- `database.py`, `db_init.py`, `seed_test_data.py`를 텍스트로만 확인했다. 앱 import, 시딩, DB 연결, 서버 실행은 하지 않았다.
- `.venv_laptop`, `.venv_pc`, `.venv_review`와 각 `Scripts/python.exe` 파일은 존재한다. sandbox에서 review와 pc Python은 기반 Python312를 찾지 못했다. 이것만으로 실제 호스트에서도 사용할 수 없다고 단정하지 않는다. 승인 대기 환경 확인은 부모 지시에 따라 중단했다. **Python, 의존성, Node 빌드, hc, 서버 기동과 브라우저 동작은 미검증**이며 부모가 별도로 확인한다.
- 다른 관리자 템플릿의 상세 DOM 계약은 구현 직전 해당 파일을 읽어 기록한다. 아래 목록은 변경 허용 범위이며 모든 파일을 반드시 수정하라는 뜻은 아니다.

## 변경 파일과 금지 영역

| 파일 | 허용 작업 |
| --- | --- |
| `src/static/css/app.css` | C 토큰, 기존 dense 토큰 매핑, 공통 시각 클래스, 반응형·접근성 스타일 |
| `src/static/css/tailwind.css` | `npm run build:css` 생성 결과만 반영. 수동 편집 금지 |
| `src/templates/base.html` | 공통 폰트·배경·패널·탐색·toast·modal 외형. 중복 시각 CSS를 app.css로 이동 |
| `src/templates/partials/sidebar_user.html`, `sidebar_admin.html` | 기존 메뉴·조건·접기 계약을 유지한 rail 외형 |
| `src/templates/login.html` | 기존 로그인 폼에 같은 색·타입·입력·버튼 적용 |
| `src/templates/user_calendar.html`, `user_team_calendar.html` | 기존 달력·일정·timeline 레이아웃을 유지한 시각 조정. 동적 생성 마크업의 스타일 문자열 포함 |
| `src/templates/partials/user_left_panel.html`, `user_leave_timeline.html` | 잔여량·신청·내역 외형과 기존 상태 클래스의 시각 매핑 |
| `src/templates/user_history.html`, `user_approvals.html` | 표·필터·배지·승인/반려 컨트롤 외형 |
| `src/templates/admin_dashboard.html`, `admin_users.html`, `admin_master.html`, `admin_holidays.html`, `admin_audit.html`, `admin_leaves_calendar.html` | 기존 정보 구조를 유지한 공통 디자인 적용 |
| `src/templates/partials/admin_leaves_yearly_partial.html`, `admin_leaves_timeline_partial.html` | 부분 응답의 표·달력·timeline 외형 |

`partials/macros.html`의 시간 표시 계산과 `partials/fragment_base.html`의 출력 구조는 유지한다. `src/app/**`, `src/static/js/time.js`, `chart.umd.js`, `package.json`, lockfile, `tailwind.config.js`, seed·DB 초기화 스크립트는 수정하지 않는다. 차트가 템플릿에서 색을 설정한다면 그 색 상수만 바꿀 수 있다. 새 앱 파일·테스트 프레임워크를 만들지 않는다. 기존 검증 스크립트 수정이 필요하다고 판단하면 우선 실패 원인을 부모에게 보고한다.

## 적용할 디자인 값

값의 원본은 `c-variants/tokens.css`다. 아래 값을 app.css에 공통 토큰으로 넣고 기존 `dense-*` 이름도 계속 제공한다. 각 화면의 hex 값을 일괄 치환하지 않는다. 의미가 일치하는 색에만 매핑한다.

| 토큰 | 값 | 사용 |
| --- | --- | --- |
| paper | `oklch(99.0% 0.005 88)` | 본문 표면, 입력, 카드 |
| paper-2 | `oklch(96.6% 0.007 88)` | 앱 배경, hover 보조 표면 |
| paper-3 | `oklch(94.0% 0.009 88)` | rail, 표 머리, 통계 띠, 비활성 날짜 |
| paper-4 | `oklch(91.2% 0.011 88)` | segmented control 바탕 |
| ink | `oklch(22.5% 0.010 88)` | 주요 텍스트 |
| ink-2 | `oklch(34.0% 0.010 88)` | 보조 제목·탐색 |
| muted | `oklch(44.5% 0.010 88)` | 보조 설명 |
| field-edge | `oklch(54.0% 0.012 88)` | 입력·보조 버튼 테두리 |
| rule | `oklch(85.5% 0.011 88)` | 1px 구획선 |
| rule-strong | `oklch(74.0% 0.012 88)` | 달력 외곽·주요 구획 |
| accent | `oklch(50.8% 0.194 259.6)` | 주요 동작, 선택 표시 |
| accent-hover | `oklch(45.5% 0.188 259.6)` | 주요 버튼 hover |
| accent-ink | `oklch(99.0% 0.005 88)` | 주요 버튼 글자 |
| accent-soft | `oklch(94.2% 0.026 255)` | 선택·승인 상태 배경 |
| accent-text | `oklch(40.5% 0.165 259.6)` | 선택·승인 상태 글자 |
| focus | `oklch(50.8% 0.200 259.6)` | 2px focus-visible outline |
| warning / warning-soft | `oklch(42.0% 0.110 62)` / `oklch(94.8% 0.030 80)` | 대기 |
| success / success-soft | `oklch(41.0% 0.105 155)` / `oklch(94.5% 0.026 155)` | 성공·가용 |
| error / error-soft | `oklch(44.5% 0.170 28)` / `oklch(94.6% 0.026 28)` | 오류·위험·휴일 |

기존 이름의 매핑은 `dense-bg→paper-2`, `dense-surface→paper`, `dense-surface-soft→paper-2`, `dense-line→rule`, `dense-grid→rule`, `dense-line-strong→rule-strong`, `dense-text→ink`, `dense-muted→muted`, `dense-nav-text→ink-2`, `dense-blue→accent`, `dense-blue-soft→accent-soft`, `dense-amber→warning`, `dense-green→success`, `dense-danger→error`, 각 soft→동명 soft, `dense-gray-soft→paper-3`으로 한다. 상태 글자에는 accent-text를 별도로 적용한다. 입력 테두리는 field-edge를 사용한다. 기존 `dense-line-strong`을 전체적으로 field-edge로 바꾸지 않는다.

### 타이포그래피·모서리·아이콘

- 폰트는 `"Pretendard Variable", "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif`다. 로컬 설치 폰트가 없으면 fallback을 사용한다. 외부 폰트 요청을 추가하지 않는다.
- 본문 14px, 표·컨트롤 13px, 보조 라벨·배지 12px, 중간 제목 16px, 섹션 제목 18px, 화면 제목 22px, 가장 큰 제목 상한 26px. 제목 weight 600·tracking -0.02em, 일반 400, 컨트롤·라벨 500을 기본으로 한다. 기존 10px 업무 텍스트는 12px로 올리고 700/800/900 굵기는 500/600으로 정리한다.
- 본문 line-height 1.5, 컨트롤 1.25, 제목 1.25. 날짜·시간·잔여량은 `font-variant-numeric: tabular-nums`. 화면 수치의 계산·단위·표시는 바꾸지 않는다.
- 작은 배지·날짜·연차 slot radius 2px, 카드·입력·버튼·탐색 4px, 큰 외곽·modal 6px. 원형 avatar, 상태 점, 실제 toggle track/thumb만 원형을 유지한다. `rounded-full` 전체 치환은 금지한다.
- 1px 테두리와 면 차이로 구획한다. 카드 확대·뜀 hover와 큰 장식 그림자를 제거한다. 필요한 외곽 그림자는 `0 1px 2px color-mix(in oklab, var(--color-ink) 6%, transparent)` 수준으로 제한한다. modal의 시인성과 기존 backdrop은 유지한다.
- 기존 inline SVG를 재사용한다. 기본 16×16px, `stroke:currentColor`, `fill:none`, stroke-width 1.6, round cap/join. 의미상 필요한 큰 아이콘은 20px까지 허용한다. 브랜드·상태 점을 일반 선 아이콘 규칙으로 덮지 않는다. 장식 emoji는 같은 의미의 기존 inline SVG 또는 텍스트로 바꾸되 hook 클래스와 접근 가능한 이름은 남긴다.
- 아이콘 전용 버튼에는 기존 title을 유지하고 필요하면 한국어 `aria-label`을 추가한다. 색만으로 상태를 구별하지 않는다. 승인·대기·반려·취소 텍스트와 기존 상태 조건을 유지한다.

### 레이아웃·상태

- C baseline rail 기준 폭은 188px. 실제 앱에서 기존 sidebar 컨테이너에 적용하고 메뉴를 복제하지 않는다. 접힌 폭 76px와 `.is-collapsed` 동작은 유지한다. 기본 sidebar 반응형 경계 768px와 달력 desktop 경계 1024px를 바꾸지 않는다.
- 콘텐츠는 `min-width:0`, 작업 영역 padding 16px 24px, 구획 gap 16px를 기본으로 한다. 시안의 1360px은 비교용 기준 폭이며 관리자 timeline에 전역 max-width로 강제하지 않는다.
- 간격은 2·4·8·12·16·24·32px를 사용한다. 바깥 gutter는 넓은 화면 32px, 960px 이하 20px, 640px 이하 12px를 기준으로 기존 컨테이너에 맞춘다. 중첩 padding을 누적하지 않는다.
- 개인 달력의 기존 잔여량·사용량 요약을 C의 평평한 통계 띠로 표현한다. 현재 제공하지 않는 가용 인원·통계를 추가하거나 하드코딩하지 않는다. 기존 연간·월간·timeline 표시 방식을 월간 시안으로 교체하지 않는다.
- 월간 desktop 셀이 해당되는 경우 시안의 92px 최소 높이를 기준으로 사용한다. 연간 작은 달력과 모바일 셀에는 강제하지 않는다. 연차 slot은 2px 왼쪽 상태선, 2px radius, 12px 텍스트를 쓴다.
- 버튼·입력의 desktop 최소 높이 36px. 모바일 주요 조작은 44px 이상 터치 영역, 입력 글자는 16px를 사용한다. 촘촘한 표 전체에 44px 행 높이를 강제하지 않는다.
- 기본·hover·focus-visible·active·disabled·loading·empty·error 외형을 확인한다. 기존 상태 분기·재시도 핸들러를 재사용한다. 시안의 가짜 로딩 상태를 실제 앱에 새로 구현하지 않는다.
- 전환은 색·테두리 위주 120ms, 필요한 짧은 전환 200ms. `prefers-reduced-motion: reduce`에서는 장식 애니메이션을 끈다. 기존 modal·toast·고정 바의 z-index 관계는 그대로 유지한다.

## 반드시 보존할 계약

모든 route, HTTP method, query parameter, form action/method, input name/type/value, hidden field, required/maxlength, ID, data 속성, onclick/onchange/submit 핸들러, 전역 함수 이름, localStorage 키를 보존한다. Jinja의 조건·반복·변수·상속·include·escape/tojson 필터를 바꾸지 않는다. class가 JS selector 또는 상태 토글 대상이면 이름을 유지하고 시각 정의만 바꾼다.

특히 다음 계약을 확인한다.

- `easy-*_desktop`, `easy-*_mobile`, `easy-submit-btn-g_desktop`, `prevMonthLink`, `nextMonthLink`, `multiSelectToggleBtn`, `multiSelectToggleCircle`, `multiSelectFloatingBar`, `selectedCount`와 날짜·연차 ID의 연결.
- `/api/user/leave`, `/user/calendar/desktop-partial`, `/user/team-calendar/desktop-partial`, `/api/user/team-calendar` 및 기존 개인 달력 JSON 요청의 URL·응답 처리.
- `loadMobileCalendarG`, `loadTeamDesktopG`, `loadTeamScheduleDataG`, `initializeTeamResponsiveG`의 조건, 요청 순서 보호, 실패·재시도 처리. 개인 달력 함수의 정확한 위치와 전체 연결은 수정 전에 소스로 확인한다.
- `team-desktop-container-g`, `mobile-schedule-view-g`, `mobile-team-month-form-g`, `mobile-schedule-date-label-g`, `mobile-schedule-list-g`와 개인 달력의 대응 컨테이너.
- `desktop_partial` 분기와 `fragment_base.html`. CSS는 base가 한 번 로드하는 빌드 파일에서 제공한다. fragment에 별도 shell·CSS 링크·중복 ID를 삽입하지 않는다.
- `.hidden`, responsive display 클래스, transform 이동 클래스, selected/loading 상태 class는 장식 정리 대상으로 삭제하지 않는다.
- STAFF·TEAM_LEAD·PM·ADMIN의 메뉴·데이터 가시성, 승인·취소 권한, 팀/회사 공유 설정과 서버의 권한 검사를 보존한다. CSS로 숨기는 방식으로 RBAC를 대체하지 않는다.
- 휴일 제외, 시간 단위·점심 공제, 비차감 사유 필수, 연도별 0시간 할당, 승인·대기 차감, 반려 사유, 상태 전이, 감사·엑셀·백업을 바꾸지 않는다. 사용자 문자열의 `textContent` 처리와 escaping을 유지한다.

## 구현 순서와 단계별 종료 조건

1. **작업 전 기록.** branch와 `git status --short`, `git diff -- .gitignore`를 확인한다. 수정 예정 파일의 원본 diff 또는 사본을 임시 작업 디렉터리에 보관한다. 사용자 프로토타입·gitignore는 해시를 기록한다. 각 작업 묶음을 읽으며 위 DOM 계약과 JS selector를 기록한다. 허용 범위 밖 기존 변경은 유지한다.
2. **토큰과 공통 shell.** app.css에 토큰과 매핑을 넣고 base·두 sidebar·login의 스타일을 정리한다. `.glass-panel`, `.shim-side-link`, icon, toast의 기존 정의를 이동할 때 원래 정의를 제거해 중복 cascade를 막는다. 전역 `*`, `button`, `svg`에 강한 override나 `!important`를 덧붙이는 방식은 피한다. 로그인·사용자·관리자 shell에 같은 폰트와 4/6px 모서리가 적용되면 종료한다.
3. **개인·팀 달력과 신청.** user_calendar, user_team_calendar, user_left_panel, user_leave_timeline 순서로 작업한다. 먼저 정적 클래스, 다음 JS가 생성하는 HTML/class 문자열의 시각 값만 바꾼다. 요청·계산·분기·이벤트 코드는 유지한다. desktop full/partial와 모바일에서 같은 배지·입력 외형을 확인하면 종료한다.
4. **내역·승인과 관리자.** user_history, user_approvals 이후 admin_dashboard, admin_users, admin_master, admin_holidays, admin_audit, admin_leaves_calendar 및 두 admin partial 순서로 적용한다. 표는 가로 스크롤 컨테이너 안에 남기고 헤더·필터·sticky 열을 보존한다. 기능을 생략하지 않은 상태에서 색·타입·radius가 통일되면 종료한다.
5. **CSS 빌드와 회귀.** 아래 빌드·자동 검사·브라우저 검사를 수행한다. 단계별 실패는 그 단계 diff에서 해결한다. 백엔드 수정이 필요한 실패는 독단적으로 고치지 않고 부모에게 전달한다.
6. **사용자 테스트 인계.** 검증된 격리 환경의 URL, 프로세스/터미널 ID, 데이터 경로, 테스트 계정, 종료 방법을 부모에게 전달한다. 마지막으로 변경 파일과 계약 보존 diff를 Argon에게 전달한다. 구현자가 자기 검증을 Argon 독립 검증으로 표현하지 않는다.

각 단계에서 완료 파일·실행한 검사·미해결 항목을 짧게 기록한다. 화면 전체 재작성이나 새로운 컴포넌트 체계 추출을 시작하지 않는다. 일정 압박 때문에 관리자·모바일 경로를 누락한 상태로 완료 선언하지 않는다.

## CSS 빌드와 회귀 검사

부모가 실행 가능한 Python 절대 경로와 Node/npm을 먼저 확인한다. `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`을 설정한다. 설치가 필요한 경우 기존 `requirements-dev.txt`와 lockfile을 사용하며 새 의존성을 추가하지 않는다.

```powershell
npm run build:css
& $shimPython tools/scripts/test_mobile_ui.py
& $shimPython tools/scripts/test_review_regressions.py
& $shimPython tools/scripts/run_tests.py smoke
git diff --check
git diff --stat
```

개별 테스트도 실행 전에 소스를 읽어 임시 데이터 격리 여부를 확인한다. 격리가 불명확하면 아래 사용자 테스트 DB와 별도의 새 임시 `SHIM_DATA_DIR`을 사용한다. 공통 실행기는 하위 검사별 임시 경로를 사용한다. UI 변경만으로 전체 release 검사를 반복하지 않되, smoke 실패나 추가 변경이 있으면 원인에 맞는 검사를 수행한다. Python 미확보로 검사를 실행하지 못하면 통과로 기록하지 않는다.

빌드 후 실제 생성 CSS에 새 색·상태·반응형 클래스가 포함되는지 확인한다. class 이름을 문자열 조합으로 새로 만들지 않는다. 기존 scan 범위 밖 파일을 추가하지 않는다. version을 올려 cache를 우회하지 말고 테스트 브라우저에서 강력 새로고침한다. `design/`의 시안 CSS나 JS를 실제 앱이 요청하면 실패다.

브라우저 검사 폭은 1440, 1024, 768, 390, 360px이며, 달력 분기 경계 1023/1024px도 확인한다. 최소 다음을 기록한다.

| 영역 | 확인 동작과 통과 기준 |
| --- | --- |
| 공통 | 로그인 실패·성공, 로그아웃, 알림·toast, sidebar 접기/펼치기, 현재 메뉴 표시, 키보드 focus, modal 닫기. 콘솔 오류·외부 자산 요청 없음 |
| 개인 달력 | 현재 월·연도 변경, 빠른 연속 이동, 다중 날짜, 전일·반일·직접 시간·비차감 신청, 차감 미리보기, 취소. 화면 날짜와 제출 날짜 일치 |
| 팀 달력 | 월 이동, 팀/회사 범위, timeline 날짜 선택, 모바일 목록, desktop partial 로딩·실패·재시도. 숨겨진 권한 데이터가 노출되지 않음 |
| 내역·승인 | 필터·페이지 이동, 승인·반려 사유·취소, 긴 이름과 사유. 버튼 가려짐·텍스트 소실 없음 |
| 관리자 | 대시보드, 사용자 조회/편집, 설정, 공휴일, 감사 조회/엑셀, 연차 달력·연간·timeline. 요청 URL·필드·결과 유지 |
| 반응형 | 문서 전체의 불필요한 가로 스크롤 없음. 넓은 표는 자체 컨테이너에서 스크롤. 고정 바·modal이 입력과 버튼을 가리지 않음 |
| 상태·접근성 | 빈 결과, loading, error, disabled, 긴 텍스트, 200% 확대, reduced-motion. 상태는 문자로도 식별 가능 |

모바일 race·권한·윤달 등은 기존 자동 검사를 그대로 사용한다. 스크린샷만으로 이벤트·권한 통과를 판단하지 않는다. 동일 데이터에서 주요 화면의 변경 전후 스크린샷을 남기고 C BASELINE의 rail·중립 면·평평한 구획·작은 radius와 비교한다.

## 격리 사용자 테스트 서버와 데이터 준비

이 절차는 **부모의 Python·런타임 확인 후 구현 단계에서 실행**한다. 계획 작성 중 실행하지 않았다. 운영 DB를 복사하거나 열지 않는다. shell 환경을 설정하기 전에 앱을 import하지 않는다. `seed_test_data.py --help`도 최상위 앱 import가 있으므로 환경 확인 용도로 실행하지 않는다.

1. `$shimPython`에 부모가 검증한 Python 절대 경로를 넣는다. Python 버전만으로 의존성 충족을 판단하지 않는다. 기존 가상환경의 패키지 상태를 확인한다.
2. 테스트 전용 자식 터미널에서 GUID가 붙은 새 데이터 디렉터리를 만든다. 예시는 Windows TEMP 아래이며 실행 환경의 쓰기 권한이 필요하면 부모가 허용된 임시 위치를 지정한다. 경로가 프로젝트 `var/data`, `src/var/data`, portable data 또는 NAS 경로가 아닌지 확인한다. `database.py`의 소스 실행 기본값은 `Path(__file__).resolve().parents[2] / 'var' / 'data'`이므로 문서의 기본 경로 설명에 의존하지 말고 반드시 환경변수를 지정한다.
3. 기존 운영 키 환경을 자식 터미널에 그대로 전달하지 않는다. `auth.py`, `key_material.py`에서 지원하는 키 환경변수 이름을 부모가 확인하고 테스트 전용 값 또는 새 데이터 폴더의 자동 생성 키를 사용한다. 운영 키·DB·backup 경로는 사용하지 않는다.

```powershell
# 새 테스트 전용 터미널에서 실행. $shimPython은 부모가 제공한다.
$shimUiRoot = Join-Path $env:TEMP ('shim-c-ui-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $shimUiRoot -ErrorAction Stop | Out-Null
$env:SHIM_DATA_DIR = $shimUiRoot
$env:SHIM_TIMEZONE = 'Asia/Seoul'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# 운영 키 환경을 제거/대체했는지 먼저 확인한다.
& $shimPython tools/scripts/db_init.py
if ($LASTEXITCODE -ne 0) { throw '격리 DB 초기화 실패' }
& $shimPython tools/scripts/seed_test_data.py
if ($LASTEXITCODE -ne 0) { throw '격리 시딩 실패' }
```

`--reset`을 사용하지 않는다. 이 옵션은 설정된 DB의 테이블을 drop하며 운영 경로 오지정 시 파괴적이다. 새 DB는 db_init으로 먼저 테이블과 migration을 만든다. seed는 예외를 출력하고 삼키므로 종료 코드 0만으로 성공을 판정할 수 없다. 출력의 `[SEED] Error:` 여부, 역할별 계정, 설정 행과 실제 화면 데이터를 확인해야 한다. 같은 DB에 seed를 반복 실행하면 연차·감사 데이터가 추가될 수 있다. 재시도가 필요하면 원인을 해결한 뒤 별도의 새 GUID 폴더로 다시 준비한다.

seed의 기본 계정은 `admin`, `pm_kim`, `pm_lee`, `lead_park`, `lead_choi`, `lead_jung`, `lead_kang`, `staff_01`~`staff_12`이며 테스트 비밀번호는 `0000`이다. 연도별 120시간 할당, 현재 날짜 주변 연차, 공휴일, 감사 데이터를 만든다. STAFF의 회사·팀과 연차 상태는 무작위다. 모든 상태·팀 범위가 자동 보장된다고 가정하지 않는다.

서버 기동 후 격리 앱의 기존 관리자 화면에서 `staff_01`을 `lead_park`와 같은 `A-건설/설계팀`으로 맞추고, 비교용 다른 팀 STAFF를 확인한다. 승인 필요 설정을 켜고 STAFF로 미래 업무일에 대기 요청을 만든다. 승인·반려·취소·비차감 사례는 실제 UI 흐름으로 준비한다. 팀 공유 ON/OFF, 회사 공유 ON/OFF는 각각 테스트하고 최종 사용자 테스트 설정을 기록한다. 운영 설정은 변경하지 않는다.

서버는 빈 포트 8017을 우선 사용하되 부모가 점유 여부를 확인한다. 점유 시 기존 프로세스를 종료하지 말고 다른 빈 포트를 기록한다. 같은 환경을 상속하는 전용 터미널에서 다음을 실행한다.

```powershell
& $shimPython -m uvicorn src.app.main:app --host 127.0.0.1 --port 8017
```

reload와 다중 worker는 사용하지 않는다. hc 사용 가능 여부와 `hc --skill`을 부모가 확인한 뒤 관리 터미널로 실행하거나, 전용 foreground 터미널을 사용한다. 서버의 lifespan은 백업·정리 작업을 수행하므로 DB뿐 아니라 생성 키·백업·로그가 격리 위치에 있는지도 확인한다. `/health`, 로그인, 정적 CSS 응답을 확인한 뒤 사용자에게 URL을 전달한다.

인계에는 실제 URL, 테스트 계정, `$shimUiRoot`, 시작한 PID 또는 hc 터미널 ID, 검사 결과, 미검증 항목을 포함한다. 사용자 테스트 중 서버를 임의로 끄지 않는다. 종료 시 해당 터미널의 Ctrl+C로 정상 종료하고 데이터는 사용자 판단 전까지 보존한다. 운영 프로세스 일괄 종료·임시 디렉터리 일괄 삭제는 하지 않는다.

## Argon 독립 검증과 완료 조건

Argon은 구현자의 보고만 인용하지 말고 diff와 실제 화면을 확인한다. 새 기능·새 디자인을 추가하지 않는다.

- 변경 파일이 허용 범위에 있는지, `.gitignore`와 prototype 해시가 보존되는지 확인한다.
- route·form·ID·handler·Jinja 조건·RBAC와 모바일 partial 요청이 유지되는지 diff로 확인한다. JS 변경은 시각 문자열에 한정됐는지 본다.
- C1~C3 전용 shell, mock 데이터, 비교용 script, 외부 폰트·새 의존성이 들어오지 않았는지 확인한다.
- CSS 빌드와 회귀 검사 결과를 확인하고, 개인·팀 달력의 full/partial/모바일 경로 및 역할별 핵심 동작을 독립적으로 재현한다.
- 실제 실행 환경에서 재현하지 못한 항목은 미검증으로 남긴다. Python·서버 준비 실패를 디자인 완료나 회귀 통과로 포장하지 않는다.

완료 보고에는 적용 화면·변경 파일, 실제 실행한 검사와 결과, 사용자 테스트 URL·데이터 위치·종료 방법, Argon 결과와 남은 문제를 기록한다. 커밋·푸시는 하지 않는다.
