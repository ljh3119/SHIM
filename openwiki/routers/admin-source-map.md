# 관리자 라우터 소스 맵

이 페이지는 관리자용 라우터 파일이 각각 어떤 화면과 기능을 담당하는지 정리합니다. 관리자 영역은 `src/app/routers/admin/__init__.py`에서 조립되고 `src/app/main.py`에서 마운트됩니다.

## 진입점과 구성
- `src/app/main.py`는 `app.include_router(admin_page_router)`와 `app.include_router(admin_api_router)`로 관리자 라우터를 붙입니다.
- `src/app/routers/admin/__init__.py`는 다음 6개 서브모듈로 관리자 영역을 구성합니다.
  - `dashboard.py`
  - `users.py`
  - `leaves.py`
  - `holidays.py`
  - `settings.py`
  - `audit.py`

## 라우터 맵

### `src/app/routers/admin/dashboard.py`
- 라우트: `GET /admin/dashboard`
- 목적: 운영 KPI와 차트를 보여주는 관리자 첫 화면
- 뒷단 서비스: `src/app/services/admin_service.py#get_admin_dashboard_stats`, `#get_admin_dashboard_charts_data`
- 주요 동작:
  - 템플릿 호환을 위해 서비스 키를 재명명합니다.
  - `src/app/main.py:START_TIME`으로부터 업타임을 계산합니다.
  - 백업/정리 최신성과 26시간 건강 임계치를 보여줍니다.
  - `src/app/auth.py#get_encryption_key`로 암호화 활성 여부를 판단합니다.

### `src/app/routers/admin/users.py`
- 페이지 라우트: `GET /admin/users`
- API 라우트:
  - `POST /api/admin/user/toggle`
  - `POST /api/admin/user/reset-password`
  - `POST /api/admin/user/update`
  - `POST /api/admin/change-password`
- 목적: 사원 관리, 역할 표시, 연차 일수 요약, 활성화/비활성화, 비밀번호 관리
- 주요 동작:
  - 관리자는 자기 자신이나 다른 관리자 계정을 비활성화할 수 없습니다.
  - 사용자를 비활성화하면 미래 연차가 취소됩니다.
  - 비관리자 비밀번호는 `0000`으로 초기화됩니다.
  - 모든 변경은 `AuditLogs`에 기록됩니다.
  - 암호화된 이름과 한글 초성 검색을 위해 인메모리 검색을 사용합니다.

### `src/app/routers/admin/leaves.py`
- 페이지 라우트: `GET /admin/leave/calendar` 및 관련 타임라인 라우트
- API 라우트: 관리 대상 연차 기록의 승인 / 반려 / 삭제 / 내보내기 흐름
- 목적: 캘린더와 타임라인 화면을 통한 연차 검토, 내보내기, 배치 작업
- 주요 동작:
  - `/admin/leave/timeline`을 타임라인 탭이 열린 캘린더 화면으로 리디렉션합니다.
  - 필터링된 타임라인 쿼리는 `admin_service.get_leaves_timeline_query`를 사용합니다.
  - 사용자 이름이 암호화된 경우 암호화 인지 정렬을 적용합니다.
  - 연차 데이터를 Excel로 내보냅니다.
  - 상태 전이는 `src/app/services/leave_policy.py`의 로직을 사용합니다.

### `src/app/routers/admin/holidays.py`
- 페이지 라우트: `GET /admin/holidays`
- API 라우트:
  - `POST /api/admin/holiday/create`
  - `POST /api/admin/holiday/update`
  - `POST /api/admin/holiday/delete`
- 목적: 연차 계산과 계획에 쓰이는 공휴일 달력 관리
- 주요 동작:
  - 공휴일 날짜의 유일성을 검증합니다.
  - 모든 CRUD 작업을 감사 로그에 기록합니다.

### `src/app/routers/admin/settings.py`
- API 라우트:
  - `GET /api/admin/settings/approval`
  - `POST /api/admin/settings/branding`
  - `POST /api/admin/settings/calendar-scope`
  - `POST /api/admin/settings/approval`
  - `POST /api/admin/settings/time-policy`
- 목적: 승인 정책, 브랜딩, 캘린더 가시성, 근무 시간 규칙 설정
- 주요 동작:
  - 쓰기 전에 `SystemSettings` 행이 존재하는지 보장합니다.
  - 누락되거나 잘못된 시간 정책 값을 정규화합니다.
  - 업데이트 후 `src/app/services/leave_policy.py`의 캐시를 강제로 갱신합니다.
  - 모든 변경을 감사 로그에 남깁니다.

### `src/app/routers/admin/audit.py`
- 페이지 라우트: `GET /admin/audit`
- API / 내보내기 라우트: `GET /admin/audit/export`
- 목적: 시스템 감사 로그를 조회하고 내보내기
- 주요 동작:
  - 조회 기간을 최대 90일로 제한합니다.
  - 감사 액션과 대상에 대해 사람이 읽기 쉬운 라벨을 사용합니다.
  - 현재 필터를 쿼리 문자열에 보존한 채로 내보내기를 지원합니다.

## 공통 관리자 의존성
- `src/app/dependencies.py#get_current_admin`은 호출자가 활성 `ADMIN` 계정인지 보장합니다.
- `src/app/auth.py`는 토큰 검증, 쿠키 설정, 암호화 키 조회를 담당합니다.
- `src/app/models.py`는 관리자 영역 전반에서 쓰이는 `Users`, `Leaves`, `AuditLogs`, `Holidays`, `SystemSettings`를 정의합니다.
- `src/app/services/admin_service.py`는 대시보드, 타임라인, 감사 페이지에서 사용하는 쿼리 로직을 담고 있습니다.

## 변경 가이드
- 라우트를 다른 파일로 옮기면 이 맵과 `src/app/routers/admin/__init__.py`를 둘 다 업데이트해야 합니다.
- 관리자 권한을 바꾸려면 `src/app/dependencies.py`부터 시작한 뒤 `get_current_admin`을 쓰는 모든 라우터를 점검해야 합니다.
- 연차 승인 동작을 조정할 때는 `src/app/routers/admin/leaves.py`와 `src/app/services/leave_policy.py`를 함께 봐야 합니다.
- 설정 저장 방식을 바꿀 때는 `src/app/services/leave_policy.py`의 캐시 갱신 경로가 새 필드와 일치하는지 확인해야 합니다.
