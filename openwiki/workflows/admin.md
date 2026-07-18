# 관리자 워크플로우

관리자 워크플로우는 운영자가 사용자, 연차 승인, 공휴일, 감사, 시스템 설정을 관리할 때 사용하는 페이지와 API 동작을 다룹니다. 이 흐름은 `src/app/routers/admin/*`에서 조립되고 `src/app/services/admin_service.py`를 뒷받침으로 하며, `src/app/dependencies.py#get_current_admin`으로 보호됩니다.

## 핵심 흐름

### 1) 대시보드 열기
- 라우트: `GET /admin/dashboard`
- 파일: `src/app/routers/admin/dashboard.py`
- 표시 내용:
  - 활성 사용자 수, 대기 중 연차 수, 오늘의 연차 활동, 총 할당량, 승인 사용량, 소진율
  - 최근 연차와 최근 감사 로그
  - 백업/정리 최신성을 나타내는 시스템 상태 메트릭
  - 다음 해 할당이 없을 때 12월과 1월에 표시되는 초기 설정 배너
- 존재 이유:
  - 운영자가 처음 보는 화면이며, 시스템이 믿고 사용할 만한 상태인지 가장 빨리 확인할 수 있습니다.

### 2) 사원 관리
- 라우트: `GET /admin/users`
- API 동작: 활성화/비활성화, 비밀번호 초기화, 프로필 수정, 관리자 비밀번호 변경
- 파일: `src/app/routers/admin/users.py`
- 주요 규칙:
  - 관리자는 자기 계정을 비활성화할 수 없습니다.
  - 일반 사용자 토글 경로로는 관리자 계정을 비활성화할 수 없습니다.
  - 사용자를 비활성화하면 미래의 미확정 연차가 취소됩니다.
  - 비밀번호 초기화는 `0000`으로 설정하고 `token_version`을 올려 기존 세션을 종료시킵니다.
- 검색과 정렬:
  - 암호화된 이름도 찾을 수 있도록 사용자 검색은 인메모리로 수행됩니다.
  - 연차 일수 요약은 연도별 할당 데이터를 기준으로 계산됩니다.

### 3) 연차 요청 검토
- 주요 화면: `/admin/leave/*` 아래의 캘린더와 타임라인
- 파일: `src/app/routers/admin/leaves.py`
- 워크플로우 노트:
  - 타임라인 화면은 실질적으로 캘린더 화면으로 리디렉션되며 `timeline` 탭을 활성화합니다.
  - 필터는 연도, 월, 사용자, 회사, 팀, 연차 상태를 지원합니다.
  - 암호화가 켜져 있을 때는 데이터베이스 정렬 대신 인메모리 정렬을 사용합니다.
  - 연차 내보내기는 Excel 생성으로 이뤄집니다.
- 비즈니스 로직:
  - 연차 승인/반려는 `src/app/services/leave_policy.py`의 헬퍼가 담당합니다.
  - 관리자 대시보드의 연차 KPI는 `src/app/services/admin_service.py`에서 가져옵니다.

### 4) 공휴일 관리
- 라우트: `GET /admin/holidays`
- API 동작: 생성, 수정, 삭제
- 파일: `src/app/routers/admin/holidays.py`
- 워크플로우 노트:
  - 공휴일 날짜는 유일해야 합니다.
  - 모든 CRUD 작업은 감사 로그에 기록됩니다.
  - 연간 화면은 연차 계획 전에 정책 입력을 확인하는 데 유용합니다.

### 5) 시스템 설정 조정
- 라우트: `GET /api/admin/settings/approval`, `POST /api/admin/settings/*`
- 파일: `src/app/routers/admin/settings.py`
- 여기서 관리하는 설정:
  - 승인 필요 여부
  - 브랜딩 텍스트와 배지 초기값
  - 캘린더 공유 범위
  - 시간 granularity와 근무/점심 시간
- 워크플로우 노트:
  - 설정 핸들러는 `SystemSettings` 행이 없으면 새로 만듭니다.
  - 잘못되었거나 불완전한 시간 값은 먼저 거부됩니다.
  - 성공적으로 저장되면 leave-policy 캐시가 갱신되어 새 정책이 즉시 반영됩니다.

### 6) 감사 및 내보내기
- 라우트: `GET /admin/audit`
- 내보내기 라우트: `GET /admin/audit/export`
- 파일: `src/app/routers/admin/audit.py`
- 워크플로우 노트:
  - 감사 조회는 행위자, 액션, 날짜 범위로 필터링할 수 있습니다.
  - 조회 기간은 최대 90일로 제한됩니다.
  - 액션과 대상 라벨은 운영자가 읽기 쉬운 한국어 문자열로 정규화됩니다.
  - 내보내기는 `yield_per(500)`로 행을 스트리밍하고 write-only `openpyxl` 워크북에 바로 써서 메모리 사용을 낮춥니다.

## 공통 가드레일
- 모든 관리자 라우트는 `get_current_admin`에 의존하며, 비관리자는 핸들러 실행 전에 차단됩니다.
- 상태를 바꾸는 작업 대부분은 `AuditLogs`를 추가합니다.
- `token_version`은 비밀번호 변경과 사용자 상태 변경 시 세션을 무효화하는 메커니즘입니다.
- 관리자 UI는 DB 상태와 서비스 레이어 요약값 모두에 의존하므로, 변경 시 라우터와 서비스 레이어를 함께 확인해야 합니다.

## 관리자 동작을 바꿀 때 먼저 볼 파일
- `src/app/routers/admin/__init__.py`
- `src/app/routers/admin/dashboard.py`
- `src/app/routers/admin/users.py`
- `src/app/routers/admin/leaves.py`
- `src/app/routers/admin/holidays.py`
- `src/app/routers/admin/settings.py`
- `src/app/routers/admin/audit.py`
- `src/app/services/admin_service.py`
- `src/app/services/leave_policy.py`
- `src/app/dependencies.py`

## 주의할 점
- 승인이나 연차 상태 동작을 바꾸면 화면과 배경 메트릭 둘 다 영향을 받는 경우가 많습니다.
- 브랜딩이나 캘린더 범위 설정을 바꾸면 캐시 갱신 경로도 함께 업데이트해야 UI가 오래된 값을 계속 보여주지 않습니다.
- 암호화 동작을 바꾸면 관리자 타임라인과 사용자 검색 경로를 함께 테스트해야 합니다.
- 감사 액션을 바꾸면 `src/app/routers/admin/audit.py`의 라벨 매핑도 업데이트해야 내보내기가 읽기 쉬운 상태로 유지됩니다.
