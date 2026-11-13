# 테스트 및 검증

이 저장소는 하나의 전통적인 테스트 프레임워크만 쓰기보다, 실행 가능한 테스트 헬퍼와 시나리오 스크립트, 릴리스 시 검증 유틸리티를 함께 사용합니다.

## 테스트 및 검증 스크립트
`tools/scripts/` 아래에서 발견되는 파일:
- `test_db_recovery.py` — 키·현재 스키마 호환 백업 선택과 격리·설치·최종 검증 실패 원복 경로 검증
- `test_duplicate_execution.py` — 스케줄러/워커 중복 실행 패턴 방지
- `test_graceful_shutdown.py` — 정상 종료와 시그널 처리 검증
- `test_memory_leak.py` — 반복 작업 중 메모리 동작 점검
- `test_secret_key_security.py` — 공개 JWT 키 거부와 Zero-Configuration 키 생성·재사용 검증
- `test_leave_service_improvements.py` — 연차 중복·시간 입력·전일 차감·동시 요청 검증
- `test_auth_password_limits.py` — bcrypt UTF-8 72바이트 경계 검증
- `test_login_security.py` — 존재·미존재 계정의 실제 HTTP 및 bcrypt 호출 구조, ASCII·다중바이트 72/73바이트, 빈·손상 해시, 비활성 계정과 HS256 고정 검증
- `test_portable_logging.py` — 항상 격리된 임시 데이터 폴더에서 포터블 단일 파일 writer, 한글 UTF-8 순환, 백업·DB 초기화 오류, handler 오류 재귀 방지, 로그 초기화 실패·자식 조기 종료·worker 실패 코드 보존·트레이 등록 실패 중단을 검증하고 Windows에서는 실제 master·worker·트레이 종료 event, lifespan·Uvicorn 종료와 WAL/SHM 정리까지 확인
- `test_ops_safety.py` — 백업 원자성·무결성·회전, 일간 스케줄러의 24시간 호환 백업 판정 경계, 알림 정리 실패 메트릭 검증
- `test_http_security.py` — `/health` 읽기 전용 실패 처리, OpenAPI 기본 비공개와 HTTP 보안 헤더 검증
- `test_string_utils.py` — 문자열 마스킹 / 유틸리티 동작 검증
- `test_system_metrics.py` — 운영 메트릭 보고 검증
- `test_mobile_ui.py` — 모바일 팀·개인 달력의 부분 렌더링, 월별 가시성·권한, 윤달·월 이동 경계, 간편 신청 스크립트 단일 로드 및 데스크톱/모바일 폼 동적 초기화·반차 프리셋 선택·제출 동작, 기간 신청(`start < end`) 시 전일 강제 및 반차 비활성화, 기간 선택 토글의 독립 상태 동작을 검증합니다. 렌더링된 JavaScript를 Node.js vm에서 실행해 연속 월 이동, 역순 응답·오래된 오류·JSON 지연, 실패 후 재시도, 로딩 중 클릭 차단과 날짜·연차 ID 일치 및 간편 신청 폼 동작을 확인합니다.
- `test_half_day_policy.py` — 240분 반일 정책 및 비240분 정책 하에서 표준 반차 경계의 time_options 포함 여부와 반차 시간 차감 정합성 검증
- `test_holiday_names.py` — 기독탄신일(크리스마스) 및 대체 휴일 레이블 정규화, 노동절·제헌절 시딩, 관리자 편집 보존 및 감사 로그 기반 시딩 재실행 멱등성 검증
- `test_review_regressions.py` — HTML 사유/따옴표 이름, 동시 승인·취소·반려 및 잔여량 경쟁, 관리자 보호, 연도별 할당 0/누락, 점심 겹침과 00:00/24:00, 중복 설정·호환 백업 보존, 설정 GET 조회 시 DB 불변 및 transient 인스턴스 검증, 대시보드 부재자 시간 표시, 비상 초기화 CLI 종료 코드 및 마스킹 검증. 렌더링된 JavaScript 검증에 Node.js를 사용합니다.
- `test_timezone_utils.py` — IANA 시간대, DST 경계, UTC 저장, 기동 실패, 화면 ISO 파싱, 서반구 날짜 보존 검증
- `run_remaining_tests.py` — 남은 시나리오 커버리지 실행

## 공통 실행 모드
- `npm test` 또는 `python tools/scripts/run_tests.py smoke`: 개발 중 핵심 회귀 검사(약 2분)
- `npm run test:release` 또는 `python tools/scripts/run_tests.py release`: smoke와 정상 종료·중복 실행·메모리 1,000회 검사(약 6분)
- 각 하위 검사는 별도 임시 `SHIM_DATA_DIR`에서 실행되어 운영·개발 DB를 건드리지 않습니다.
- `test_http_security.py`는 단독 실행 시에도 호출자의 `SHIM_DATA_DIR`와 키 환경을 사용하지 않고 별도 임시 폴더를 사용합니다. 공통 실행기는 자식 프로세스의 Python 입출력을 UTF-8로 고정합니다.
- 의존성은 별도 가상환경에 `requirements-dev.txt`로 설치한 후 검사합니다. 전역 Python의 설치 버전만으로 프로젝트 의존성 충족을 판단하지 않습니다.
- ASGI 테스트는 개발 전용 `httpx2==2.12.0`의 명시적 transport를 사용합니다.

## 2026-10-23 개발 의존성 보안 패치
- `httpx2` 2.7.0 → 2.12.0: Dependabot 경고 #14~18의 수정 버전을 반영했습니다. HTTP 헤더 처리, SSE 버퍼링, SOCKS 경유 TLS, 압축 해제 메모리 관련 경고입니다. [보안 권고](https://github.com/advisories/GHSA-8xx6-hgc6-gc2m)
- Tailwind 빌드의 간접 의존성 `source-map-js` 1.2.1 → 1.2.2: 경고 #19의 서비스 거부 취약점 수정 버전을 lockfile에 반영했습니다. [보안 권고](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
- 운영용 `requirements.txt`는 변경하지 않습니다. Python 개발 환경은 `python -m pip install -r requirements-dev.txt`, Node 빌드 환경은 `npm ci`로 갱신합니다.
- 패치 버전 환경에서 release 19개 스크립트, CSS 빌드, `pip check`가 통과했습니다. npm 감사 결과는 취약점 0건이며 CSS 생성 결과는 기존과 동일했습니다.

## 이런 테스트가 존재하는 이유
최근 커밋 이력은 다음 영역의 하드닝에 집중되어 있습니다.
- 더 안전한 SQLite 생명주기 처리
- 포터블 런타임 안정성
- 사용자/세션 무효화 동작
- 문자열 마스킹 및 유틸리티 엣지 케이스
- graceful process shutdown
- DB 복구 및 검증 스크립트 정합성

즉, 이 테스트들은 단순한 단위 테스트가 아니라 저장소의 운영 가정을 지키는 회귀 방지 장치입니다.

## 코드 변경 시 무엇을 검증할지
### 연차 규칙
다음 항목을 바꿀 때는 연차 정책 및 시나리오 스크립트를 다시 실행합니다.
- 날짜/시간 검증
- 점심시간 제외
- 연도별 할당 동작
- 승인 상태 전이
- 캘린더 렌더링 전제
- 모바일 달력 비동기 월 이동 응답 역전 방지 및 날짜·연차 ID 정합성

### 인증 및 사용자 생명주기
다음 항목을 바꿀 때는 다시 검증합니다.
- JWT 클레임 또는 쿠키 동작
- `token_version` 갱신
- 비밀번호 초기화
- 사용자 활성화/비활성화
- 암호화 키 처리

### 운영
다음 항목을 바꿀 때는 다시 검증합니다.
- 백업 스케줄링
- 데이터베이스 복구 로직
- SQLite PRAGMA
- 정리 스케줄러
- 포터블 런타임 시작 경로
- 포터블 트레이·master·worker 종료 전달과 WAL/SHM 정리
- `/health`, Docker healthcheck 또는 OpenAPI 노출 설정
- CSP와 공통 HTTP 보안 헤더

## Docker 테스트 설정
`infra/docker/docker-compose.test.yml`은 컨테이너 기반 테스트 환경을 위한 파일입니다. 실제 배포와 더 가까운 구성으로 앱을 검증하고 싶을 때 사용합니다.

## 향후 작업자에게 유용한 실전 조언
이 저장소에서 가장 가치 있는 검증은 대개 광범위한 커버리지보다, 지금 손대는 영역에 대한 표적 회귀 검증입니다. 스케줄러 스크립트와 관리자/사용자 라우터 핸들러를 특히 주의해서 보세요. 많은 변경이 비즈니스 로직에서 UI와 운영 메트릭 양쪽으로 퍼집니다.
