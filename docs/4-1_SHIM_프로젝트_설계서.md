# [SHIM] 가변형 연차 관리 시스템 설계서

**문서 성격**: 구현 기준(코드·DB·배포)과 일치하도록 유지하는 기술 설계·산출물 인덱스  
**애플리케이션 버전**: 1.2.1  
**최종 동기화 기준일**: 2026-05-09

---

## 1. 프로젝트 개요

- **목적**: 레드마인 ID(또는 사내 고유 ID) 기반의 폐쇄망·내부망용 연차 관리 및 관리자 검증 시스템.
- **식별**: `user_id`를 PK로 사용해 동명이인·계정 중복을 구분한다.
- **시간 입력 기반**: 사용자가 시작시간/종료시간을 입력하고, 시스템 정책(30/60/120분 단위, 업무시간 범위, 점심시간 제외)에 따라 차감 시간을 계산한다.
- **검증**: 등록 시각 기준 타임라인, 연도·회사·팀 필터가 있는 관리자 캘린더로 운영 검증을 지원한다.

---

## 2. 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| ORM | SQLAlchemy 2.x |
| DB | SQLite, 파일명 `shim_internal.db` |
| 인증 | JWT(HS256), `httpOnly` 쿠키(`access_token`) |
| 비밀번호 | bcrypt (`passlib` 의존은 requirements에 있으나 해시는 `bcrypt` 직접 사용) |
| UI | Jinja2 템플릿 + Tailwind CSS v4 (`@tailwindcss/cli`로 빌드). 운영 밀도(Dense): `app.css`의 `@theme`/색·간격 토큰과 `dense-*` 유틸, 공통 레이아웃 `base.html`(v1.2.0에서 핵심 화면에 적용) |
| 공휴일 | `holidays` 라이브러리(한국 기본 공휴일 시드) |
| 컨테이너 | Docker (`Dockerfile`, `docker-compose.yml`) |
| 폐쇄망 PC | PyInstaller 기반 포터블 빌드(`portable/`) |

---

## 3. 시스템 구성 요약

- **단일 프로세스**: FastAPI 앱이 정적 파일·템플릿·API·폼 처리를 모두 담당한다.
- **DB 경로 결정** (`src/app/database.py`):
  1. 환경 변수 `SHIM_DATA_DIR`이 있으면 해당 디렉터리 아래 `shim_internal.db`
  2. PyInstaller(frozen) 실행 시 실행 파일 옆 `data/`
  3. 소스 실행 시 프로젝트 루트 `data/`
- **시작 시**: 테이블 생성(`create_all`), SQLite 컬럼 추가(경량 마이그레이션), 기존 DB 인덱스 보강, 기본 관리자·시스템 설정·한국 공휴일 시드(감사 로그로 연도별 시드 완료 여부 추적).

---

## 4. 디렉터리 구조(주요)

| 경로 | 설명 |
|------|------|
| `src/app/` | 애플리케이션 패키지(`main.py`, `models.py`, `auth.py`, `database.py`, `routers/`) |
| `src/templates/` | Jinja2 화면 |
| `src/static/` | 정적 자산(CSS 등). Tailwind 출력은 `src/static/css/tailwind.css` |
| `var/data/` | 기본 SQLite 저장 위치(운영 시 백업 대상) |
| `docs/` | 구동·백업·유지보수 가이드 |
| `design/ui-handoff/` | Dense UI 정적 시안·디렉팅(참고용, 앱 번들에 미포함) |
| `portable/` | 포터블 빌드 스크립트 및 설명 |
| `tools/scripts/` | `dev.ps1` 등 개발 보조 스크립트 |

---

## 5. 데이터베이스 모델

### 5.1 `users`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `user_id` | String, PK | 로그인 ID(레드마인 ID 등) |
| `user_name` | String | 표시 이름 |
| `company` | String | 회사(필터·캘린더용) |
| `team` | String | 팀 |
| `password` | String | bcrypt 해시 |
| `total_leave_hours` | Integer | 연간 부여 시간(기본 120h = 15일×8h) |
| `is_active` | Boolean | 재직 여부 |
| `is_admin` | Boolean | 관리자 여부 |

### 5.2 `leaves`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | Integer, PK | |
| `user_id` | String, FK | |
| `date` | Date | 사용일 |
| `snapshot_slot_label` | String | 신청 당시 시간대 라벨 |
| `snapshot_start_min` / `snapshot_end_min` | Integer | 신청 당시 하루 기준 분 단위 구간 |
| `snapshot_deduction_hours` | Float | 신청 당시 차감 시간 |
| `status` | String | `PENDING` / `APPROVED` / `REJECTED` / `CANCELED` |
| `rejection_reason` | String(500), nullable | 반려 사유. 검색/정렬 대상이 아니므로 인덱스를 두지 않음 |
| `created_at` | DateTime | 등록 시각(타임라인 정렬) |
| `year` | Integer | `date`의 연도와 동일하게 저장·필터 |

핵심 조회 인덱스:

- `leaves(user_id, date)`
- `leaves(year, date)`
- `leaves(year, user_id)`
- `leaves(created_at)`

### 5.3 `audit_logs`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | Integer, PK | |
| `actor_id` | String, FK | 수행자 |
| `action` | String | 예: `RESET_PASSWORD`, `DELETE_LEAVE`, `SEED_KR_HOLIDAYS_2026` |
| `target_info` | String | 대상 요약 |
| `old_data` / `new_data` | String | 변경 전후(민감값은 마스킹 처리될 수 있음) |
| `timestamp` | DateTime | |

연차 상태 변경 감사 로그(`UPDATE_LEAVE_STATUS`)는 상태와 반려 사유 존재 여부를 함께 기록한다. 반려 사유 본문은 신청 데이터에 저장하고, 감사 로그에는 민감 정보 확산을 피하기 위해 사유 존재 여부만 남긴다.

### 5.4 `holidays`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | Integer, PK | |
| `name` | String | 공휴일명 |
| `date` | Date, unique | |
| `created_at` | DateTime | |

### 5.5 `user_yearly_leave_allocations`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | Integer, PK | |
| `user_id` | String, FK | 사용자 ID |
| `year` | Integer | 지급 기준 연도 |
| `allocated_hours` | Integer | 해당 연도 지급 시간 |
| `created_at` | DateTime | 생성 시각 |
| `updated_at` | DateTime | 수정 시각 |

- 제약: `user_id + year` 유니크(연도별 1건)

---

## 6. 핵심 비즈니스 로직

### 6.1 연차 신청(일반 사용자)

- 동일 일자에 시작시간/종료시간 입력으로 신청한다.
- **주말**·**등록된 공휴일**에는 신청 불가.
- 입력 시각은 정책 단위 경계(30/60/120)만 허용하며, 임의 분 입력은 차단한다.
- 신청 구간은 업무시간 범위(`work_start_minute`~`work_end_minute`) 안에서만 허용한다.
- 선택 구간 길이가 정책 단위보다 짧으면 차단한다.
- 당일 기존 신청과 **시간대가 겹치면** 추가 불가.
- **당일 총 차감 시간**이 8시간을 넘으면 불가(기존 + 신청 합산).
- 점심시간 제외 정책이 설정된 경우 차감 시간 계산에서 제외한다.
- 신청 당시 시간대를 스냅샷(`snapshot_*`)으로 저장한다.
- 일반 사용자는 신청 **취소·수정 API 없음** → 잘못 등록 시 관리자가 삭제.

### 6.2 승인 상태 전이

- 기본 상태는 `SystemSettings.is_approval_required=false`면 `APPROVED`, `true`면 `PENDING`이다.
- 허용 전이: `PENDING -> APPROVED`, `PENDING -> REJECTED`, `PENDING -> CANCELED`, `APPROVED -> CANCELED`.
- 기본 차단 전이: `REJECTED -> APPROVED`, `CANCELED -> APPROVED`.
- `REJECTED` 처리 시 반려 사유는 필수이며, 공백-only 입력은 허용하지 않고 최대 500자로 제한한다.
- 반려 사유는 사용자 본인 화면과 관리자 타임라인에서 확인할 수 있다.

### 6.3 연도·잔여 시간

- 연도별 조회는 `Leaves.year` 및 `date`로 구분한다.
- 연도별 지급값은 `user_yearly_leave_allocations`를 우선 사용한다.
- 해당 연도 지급값이 없는 경우에만 `users.total_leave_hours`를 fallback으로 사용한다(레거시 호환).
- **매년 1월 1일 자동 초기화 배치는 없음**. 운영자는 관리자 화면에서 연도별 지급값(개별/일괄)을 반영한다.

### 6.4 관리자

- 사용자 생성·비활성화·연차 일수(시간) 조정, 비밀번호 **0000** 강제 초기화.
- 연차 삭제, 결재 상태 변경.
- 시간 정책(단위/업무시간/점심시간 제외)·공휴일 관리, 타임라인(필터·정렬), 연간/월별 관점의 **캘린더 뷰**(회사·팀 등 정렬 옵션).

### 6.5 감사 로그

- 비밀번호 변경·관리자 조치 등 주요 이벤트가 `audit_logs`에 적재된다.
- 한국 공휴일 시드는 연도별 `SEED_KR_HOLIDAYS_YYYY` 액션으로 중복 시드를 방지한다.

---

## 7. 인증·보안(구현 기준)

- JWT 만료: `ACCESS_TOKEN_EXPIRE_MINUTES`(기본 24시간) — `app/auth.py`.
- JWT 서명키는 `SHIM_SECRET_KEY` 환경 변수를 우선 사용한다. 운영 환경에서는 기본 fallback 값이 아닌 운영용 긴 랜덤 문자열로 고정한다.
- 기본 관리자: 최초 기동 시 `admin` 계정이 없으면 생성되며 초기 비밀번호는 **`0000`**(bcrypt 저장). 로그인 후 즉시 변경 권장.

---

## 8. 화면(템플릿) 맵

| 파일 | 역할 |
|------|------|
| `login.html` | 로그인 |
| `user_dashboard.html` | 사용자 대시보드·연간 캘린더·신청 |
| `admin_dashboard.html` | 관리자 요약 KPI |
| `admin_users.html` | 사용자 관리 |
| `admin_leaves_timeline.html` | 신청 타임라인 |
| `admin_leaves_calendar.html` | 조직 캘린더 |
| `admin_holidays.html` | 공휴일 관리 |
| `base.html` | 공통 레이아웃 |

Dense 정적 시안·디렉팅(비번들): `design/ui-handoff/`(`README.md`, `galleries/samples-hub.html`).

---

## 9. 배포

### 9.1 Docker

- 운영 경로: `docker build -f infra/docker/Dockerfile -t shim:1.2.0 -t shim:latest .` 후 `docker compose -f infra/docker/docker-compose.yml up -d`.
- `infra/docker/docker-compose.yml`은 기본값으로 `shim:1.2.0` 이미지를 실행하며(필요 시 `SHIM_IMAGE`로 오버라이드), 호스트 `../../var/data`를 컨테이너 `/app/data`에 마운트한다.
- `SHIM_SECRET_KEY`는 compose 환경 변수 매핑으로 컨테이너에 전달한다. 운영 배포 전 PowerShell 세션 또는 `.env`에 운영용 값을 설정한다.
- 개발 경로: `infra/docker/docker-compose.dev.yml`은 루트 context 빌드를 포함하므로 개발자가 필요할 때 `docker compose -f infra/docker/docker-compose.dev.yml up -d --build`로 사용할 수 있다.
- 폐쇄망: `pip download`로 wheel 디렉터리 구성 후 Dockerfile에서 `--no-index` 설치하는 방식이 주석으로 안내되어 있다.

### 9.2 포터블(무설치)

- `portable/build_portable.ps1` → 산출 `artifacts/dist/SHIM_Portable/`.
- 상세: `portable/README_PORTABLE.md`.
- v1.2.0 기준 포터블 산출물은 외부 CDN 없이 로컬 CSS로 동작하며 `/`, `/docs`, `/static/css/tailwind.css`, `/favicon.ico`, 로그인 후 `/admin/dashboard` 응답을 검증한다.

### 9.3 개발 실행

- `npm run dev`: Tailwind watch + Uvicorn(`tools/scripts/dev.ps1`).
- 또는 `uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload`.

---

## 10. 산출물·문서 체계

| 산출물 | 위치 |
|--------|------|
| 운영 DB | `var/data/shim_internal.db`(또는 `SHIM_DATA_DIR` 지정 경로) |
| Tailwind 빌드 CSS | `src/static/css/tailwind.css`(배포 시 최신 빌드 포함 권장) |
| 포터블 패키지 | `artifacts/dist/SHIM_Portable/`(빌드 후) |
| 운영 가이드 | `README.md`, `docs/1-1_초심자_구동_가이드.md`, `docs/1-2_백업_복구_유지보수_가이드.md`, `docs/1-3_운영_릴리즈_실행_체크리스트.md` |
| 릴리즈 증적 | `docs/2-1_운영_릴리즈_통합_산출물.md` |
| 향후 계획 | `docs/3-1_향후_개선계획.md` |
| AI 인수인계 | `docs/3-2_AI_인수인계_가이드.md` |
| 포터블 설명 | `portable/README_PORTABLE.md` |
| 본 설계서 | `docs/4-1_SHIM_프로젝트_설계서.md`(이 문서) |

---

## 11. 기존 설계서 대비 정정 요약

| 항목 | 과거 기술 | 현재 구현 |
|------|-----------|-----------|
| DB 파일 위치 | 루트 `shim_internal.db` 언급 | 기본 `var/data/shim_internal.db`, `SHIM_DATA_DIR` 지원 |
| 비밀번호 | 평문 `'000'` 등 | bcrypt, 관리자 초기·강제 초기화 **`0000`** |
| 사용자 스키마 | department 중심 | `company`, `team` 중심 |
| 신청 방식 | 슬롯 선택 기반 | 시작/종료시간 입력 + 단위 경계/점심 제외 정책 기반 |
| 연도 처리 | “1/1 자동 아카이브” 뉘앙스 | 연도는 `Leaves.year`·조회로 구분, **자동 연초 배치 없음** |
| 공휴일 | 미기술 | `holidays` 테이블 + 기동 시 KR 시드 |
| 인증 | 미기술 | JWT 쿠키 기반 세션 |

---

## 12. 구현 기준 변경 요약

상세 릴리즈 증적과 검증 결과는 `docs/2-1_운영_릴리즈_통합_산출물.md`에서 관리합니다. 이 설계서에는 현재 구현 기준을 이해하는 데 필요한 구조 변화만 남깁니다.

- `v1.2.0`: 시스템 브랜딩 필드 및 마스터 저장 API·UI 확장, `create_all` 직후 `ensure_sqlite_system_schema()`로 기존 SQLite 컬럼 보강, `product_user_sidebar_title` 계열 제거, 일반 레이아웃 사이드바 정리. **Dense UI 1차 범위**를 반영: 로그인·공통 shell, 관리자 대시보드→타임라인→월·연 캘린더, 사용자 대시보드, 사원·공휴일·마스터 등. 타임라인 가독성, KR 공휴일 노동절 시드 등 포함.
- `v1.1.7`: 슬롯 기반 신청/관리(`time_slots`, `LeavePolicies`)를 제거하고 시작/종료시간 입력 기반으로 전환, 시간 정책(30/60/120/업무시간/점심 제외), 신청 전 예상 차감 확인 UX를 반영함.
- `v1.1.6`: 문서/폴더 구조를 `src`, `infra/docker`, `tools/scripts`, `var/data`, `artifacts` 기준으로 표준화하고 릴리즈 자동화 인코딩을 보정함.
- `v1.1.5`: 결재 상태 전이 서비스화, 반려 사유 정책, 감사 로그 기록 기준을 반영함.
- `v1.1.0`: 폐쇄망 런타임 기준으로 외부 CDN/웹폰트 의존을 제거하고 로컬 Tailwind CSS 산출물, `SHIM_SECRET_KEY`, 테스트 DB 격리, 핵심 조회 인덱스를 반영함.
- `v1.0.0`: 연차 이력을 `Leaves.snapshot_*`와 `status` 중심으로 분리하고 승인 설정, SQLite WAL, 백업/운영 문서를 정식 기준으로 반영함.

---

## 13. 향후 설계 과제

향후 작업 목록은 `docs/3-1_향후_개선계획.md`에서 관리합니다. 이 설계서에서는 현재 구현과 분리해야 하는 큰 설계 과제만 명시합니다.

- 결재 권한 분리(`is_admin`과 별도 `can_approve`) 기반 추가 결재자 지정
- 셀프 결재 금지
- 다단계 결재, 대리결재, 결재권자 풀/순번 기반 확장은 현재 범위에서 제외
- Alembic 등 정식 DB 마이그레이션 도구 도입 검토

### 13.1 자유시간 입력 계약(설계 초안)

- 입력 방식: 사용자 신청 입력을 `slot_ids` 중심에서 `start_minute/end_minute` 기반으로 확장 검토한다.
- 단위 정책: `time_granularity_minutes` 값은 30/60/120만 허용하고 기본값은 60으로 둔다.
- 경계 검증: 시작/종료 시각은 정책 단위 경계값만 허용한다.
  - 60분 정책: `HH:00`만 허용
  - 30분 정책: `HH:00`, `HH:30` 허용
  - 120분 정책: 기준 시각을 00:00으로 볼 때 120분 배수만 허용
- 서버 검증: UI 제약과 별개로 API에서 임의 분 입력과 역전 구간(`end <= start`)을 차단한다.
- 기존 규칙 유지: 주말/공휴일 차단, 당일 겹침 차단, 1일 8시간 상한, 결재 ON/OFF 기본 상태 규칙은 유지한다.

### 13.2 연도 확정 스냅샷 정책(설계 초안)

- 연도별 잔여 계산은 실시간 집계를 사용하되, 감사/재현 목적의 최소 확정 스냅샷을 남긴다.
- 최소 스냅샷 필드:
  - `year`(확정 연도)
  - `allocated_hours`(연도 지급 기준값)
  - `policy_version`(단위/점심시간/반올림 규칙 버전)
  - `finalized_at`(확정 시각)
  - `finalized_by`(확정 주체)
- 스냅샷 저장 시점:
  - 운영 마감 시 수동 확정
  - 또는 연도 마감 배치/운영 절차 실행 시 확정
- 불변 원칙: 확정된 과거 연도 스냅샷은 정정 로그 없이 직접 수정하지 않는다.

### 13.3 구현 영향 범위(우선순위)

1. `src/app/routers/api_user.py` (입력 계약/검증/신청 저장 진입점)
2. `src/app/services/leave_policy.py` (단위 경계, 점심 제외, 상태 규칙 공통화)
3. `src/app/models.py` (스냅샷/정책 테이블 또는 컬럼 확장 시 영향)
4. `src/app/main.py` (기동 시 마이그레이션/기본값/인덱스 적용 경로)
5. `src/templates/user_dashboard.html` (단위 경계 기반 입력 UI)
6. `src/app/routers/api_admin.py`, `src/templates/admin_master.html` (정책 설정/운영 화면)
7. `src/templates/admin_leaves_timeline.html` (관리자 조회/상태 변경 화면 정합성)
8. `tools/scripts/run_remaining_tests.py` (회귀/신규 시나리오 검증)

### 13.4 검증 및 산출물 동기화 원칙

- 회귀 검증: 결재 ON/OFF 기본 상태, 상태 전이, 반려 사유 정책, 스냅샷 저장, 연도별 집계
- 신규 검증: 단위 경계(30/60/120), 임의 분 입력 차단, 점심 제외 규칙, 겹침 차단, 1일 8시간 상한
- 문서 동기화:
  - 진행/미완료는 `docs/3-1_향후_개선계획.md`
  - 완료 증적/검증 결과는 `docs/2-1_운영_릴리즈_통합_산출물.md`
  - 구현 기준 변경은 본 문서와 `docs/3-2_AI_인수인계_가이드.md`에 반영

이 문서는 코드 변경 시 함께 갱신하는 것을 원칙으로 한다.
