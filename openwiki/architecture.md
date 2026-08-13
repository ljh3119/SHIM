# 아키텍처와 런타임

SHIM은 단일 SQLite 데이터베이스를 사용하는 서버 렌더링 FastAPI 애플리케이션입니다. 폐쇄망, 일반 Windows PC, Docker, 포터블 실행 파일 환경에서 모두 동작할 수 있도록 구조를 단순하게 유지합니다.

## 런타임 형태
- **웹 프레임워크:** `src/app/main.py`에서 생성하는 FastAPI 애플리케이션
- **템플릿:** 런타임 `templates/` 디렉터리에서 로드하는 Jinja2 템플릿
- **정적 자산:** 런타임 `static/` 디렉터리에서 제공되는 Tailwind CSS 빌드 결과와 기타 정적 파일
- **데이터베이스:** 기본 경로는 `var/data/shim_internal.db`, 필요 시 `SHIM_DATA_DIR`로 대체 가능
- **인증:** HttpOnly 쿠키에 저장되는 JWT
- **백그라운드 작업:** 앱 lifespan에서 시작하는 일일 백업과 알림 정리 작업

## 요청 경로와 화면 조합
서버는 HTML 렌더링을 기본으로 하지만, 일부 화면은 부분 렌더링 partial을 같이 사용합니다.
- `src/app/routers/api_user.py`의 사용자 달력과 팀 달력은 전체 페이지와 `/calendar/desktop-partial` 계열 partial 응답을 둘 다 제공합니다.
- `src/templates/user_calendar.html`과 `src/templates/user_team_calendar.html`은 `desktop_partial` 플래그에 따라 `base.html` 또는 `partials/fragment_base.html`을 상속합니다.
- 관리자 화면도 대시보드, 캘린더, 타임라인, 감사 같은 영역별 템플릿으로 분리되어 있습니다.

이 구조는 모바일과 데스크톱, 전체 페이지와 fragment 로드를 함께 지원하려는 최근 UI 변경과도 맞닿아 있습니다.

## 시간대 불변식
- 배포 환경의 `SHIM_TIMEZONE` 하나를 사업장 시간대로 사용하며 기본값은 `Asia/Seoul`입니다.
- SQLite에는 naive UTC를 저장하고 Python에서는 timezone-aware datetime만 사용합니다.
- 화면, 감사, 엑셀, 날짜 경계, 알림 정리 02:00은 모두 사업장 시간대로 계산합니다.
- Docker OS 시간대는 UTC이며 브라우저/사용자별 현지 변환은 하지 않습니다.

## 시작과 종료
`src/app/main.py`가 애플리케이션 lifespan을 연결합니다. 시작 시에는 다음을 수행합니다.
- 시작 점검과 DB 복구 실행
- 일일 백업 스케줄러 시작
- 알림 정리 스케줄러 시작
- 소스 실행, Docker 실행, 포터블 실행에 맞는 런타임 리소스 기준 경로 해석

종료 시에는 백그라운드 작업을 취소하고 SQLAlchemy 엔진을 dispose하여 SQLite lock이 깔끔하게 해제되도록 합니다.

관련 소스:
- `src/app/main.py`
- `src/app/services/ops.py`
- `src/app/database.py`

## SQLite 전략
이 앱은 서버형 DB보다 SQLite를 중심으로 설계되었습니다. 이 선택은 여러 구현 세부에 영향을 줍니다.
- 연결 시 `src/app/database.py`에서 WAL mode, foreign key, durability 관련 PRAGMA를 활성화합니다.
- `SessionLocal`을 요청 범위 세션으로 사용합니다.
- 데이터 디렉터리는 `SHIM_DATA_DIR`, 포터블 EXE 폴더, `var/data/` 순으로 해석합니다.
- `src/app/services/ops.py`의 복구 로직은 손상된 DB를 격리하고 최신 백업에서 복원할 수 있습니다.

## 보안 및 세션 모델
인증은 의도적으로 가볍게 유지됩니다.
- 자격 증명은 `src/app/auth.py`에서 bcrypt로 검증합니다.
- bcrypt 비밀번호 입력은 UTF-8 72바이트를 상한으로 하며 초과 검증 입력은 인증 실패로 정규화합니다.
- 공개된 예전 JWT 기본키는 거부하고, Zero-Configuration 키 파일을 만들거나 읽을 수 없으면 공개 폴백 없이 기동을 중단합니다.
- JWT payload에는 subject와 token version이 포함됩니다.
- `src/app/dependencies.py`는 토큰 버전이 사용자 행과 일치하지 않으면 요청을 거부합니다.
- 관리자가 사용자를 비활성화하거나 비밀번호를 초기화하면 `token_version`이 증가하여 기존 세션이 무효화됩니다.
- 관리자 초기 비밀번호 `0000`과 화면 안내는 운영 결정으로 유지하며, 변경 시 기존 세션 무효화 정책을 따릅니다.
- 비밀번호 변경, 사용자 비활성화, 사용자 비밀번호 초기화는 모두 감사 로그를 남깁니다.
- 쿠키 플래그는 요청 scheme과 환경 변수에 따라 동적으로 결정됩니다.

민감한 텍스트 필드는 사용 가능한 암호화 키가 있을 때 `src/app/models.py`의 `EncryptedString` SQLAlchemy 타입을 사용합니다. 키가 없을 때는 오프라인/개발 워크플로우를 유지하기 위해 평문으로 저장하는데, 이는 이 저장소에서 의도된 절충입니다.

모든 HTTP 응답에는 CSP, `nosniff`, 프레임 차단, 리퍼러 차단과 카메라·마이크·위치 권한 제한 헤더를 적용합니다. 현재 템플릿 호환을 위해 CSP의 인라인 스크립트·스타일은 허용하지만 일반 화면에서 외부 출처는 허용하지 않습니다. 기본 HTTP 배포가 있으므로 HSTS는 강제하지 않습니다.

OpenAPI 경로는 기본 비활성화되며 `SHIM_ENABLE_OPENAPI=true`인 개발 환경에서만 `/docs`, `/redoc`, `/openapi.json`을 제공합니다. 이때 문서 화면에 한해서만 FastAPI 기본 CDN과 폰트 출처를 CSP에 추가합니다.

## 스케줄링과 운영 상태
`src/app/services/ops.py`에는 두 개의 장기 유지보수 루프가 있습니다.
- **일일 백업 스케줄러**: SQLite 백업을 생성하고 오래된 백업 파일을 회전 삭제합니다.
- **알림 정리 스케줄러**: 락 경합을 줄이기 위해 30일이 지난 알림을 청크 단위로 삭제합니다.

관리자 대시보드는 이 메트릭을 `SystemSettings`에서 읽어 오며, 백업 또는 정리 시각이 너무 오래되면 시스템을 비정상으로 표시합니다.

## 배포 방식
### 로컬 개발
이 저장소는 Python과 Node/Tailwind 도구를 함께 사용합니다. PowerShell 개발 스크립트로 앱을 실행하고 Tailwind CLI로 CSS를 다시 빌드합니다.

### Docker
`infra/docker/docker-compose.yml`과 `infra/docker/docker-compose.dev.yml`이 컨테이너 실행을 정의합니다. SQLite 볼륨 경로, 환경 기본값, 호스트/네트워크 차이가 이 파일들에 들어 있습니다.

이미지의 healthcheck는 Python 표준 라이브러리로 `/health`를 호출합니다. 이 경로는 브랜딩 DB 조회를 건너뛰고 표준 `sqlite3` 읽기 전용 연결로 DB와 필수 테이블만 확인하므로 누락된 DB 파일을 만들거나 내부 오류를 공개하지 않습니다.

### 포터블 실행 파일
`portable/shim_portable.py`와 `portable/build_portable.ps1`는 오프라인 환경용 Windows 번들 실행을 지원합니다. PyInstaller로 고정된 상태에서는 템플릿/정적 경로를 다른 방식으로 해석합니다.

## 주의할 점
- UI, 템플릿 컨텍스트, 정책 헬퍼는 서로 강하게 연결되어 있으므로 한쪽만 바꾸면 안 됩니다.
- SQLite lock 동작은 모든 배경 작업, 백업 흐름, 대량 쓰기 경로에서 중요합니다.
- `src/app/main.py`에는 런타임 경로 대체 로직이 여러 갈래 있으므로, 소스/Docker/포터블 해석을 깨지 않도록 주의해야 합니다.
- 많은 관리자 페이지는 `src/app/services/leave_policy.py`의 캐시된 시스템 설정에 의존합니다.
- 이 저장소는 일반 요청 핸들러에서 동기 DB 작업을 선호합니다.

## 다음에 볼 파일
- 도메인과 저장 구조: `src/app/models.py`
- 검증 및 상태 전이: `src/app/services/leave_policy.py`
- 운영 워크플로우: `src/app/services/ops.py`
- 관리자 요청 흐름: `src/app/routers/admin/*.py`
