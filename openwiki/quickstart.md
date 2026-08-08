# OpenWiki 빠른 시작

SHIM은 FastAPI, SQLAlchemy, SQLite, Jinja2, Tailwind CSS로 구성된 폐쇄망/내부망용 연차 관리 시스템입니다. 저장소의 중심은 연차 신청과 승인, 사용자/팀 가시성, 공휴일 처리, 감사 로그, 백업 복구, 그리고 Docker·로컬·포터블 실행 지원입니다.

이 저장소의 핵심 사용자군은 다음과 같습니다.
- **직원(STAFF)**: 개인 연차 달력, 신청, 취소, 조회
- **팀장/PM(TEAM_LEAD, PM)**: 팀 범위 또는 더 넓은 승인 및 가시성
- **관리자(ADMIN)**: 사용자, 공휴일, 설정, 감사, 운영 상태 관리

## 먼저 볼 문서
- [아키텍처 개요](architecture.md)
- [연차 관리 도메인](domain/leave-management.md)
- [관리자 워크플로우](workflows/admin.md)
- [운영 및 유지보수](operations.md)
- [테스트 및 검증](testing.md)

## 이 시스템이 하는 일
- 연도별 연차 할당과 차감을 SQLite에 저장합니다.
- 시작/종료 시각 기반 연차와 날짜 목록 기반 일괄 신청을 지원합니다.
- 승인 필요 여부, 점심시간 제외, 시간 단위 정책을 시스템 설정으로 제어합니다.
- 팀/회사 캘린더 가시성을 역할과 설정으로 조절합니다.
- 감사 로그, 알림, 공휴일, 운영 메트릭을 같은 DB에 유지합니다.
- 백업, DB 복구, 알림 정리 같은 운영 작업을 앱 내부 스케줄러로 수행합니다.
- Docker, 로컬 Windows, 포터블 Windows 실행을 모두 지원합니다.

## 핵심 소스 영역
- 앱 시작과 런타임 경로 해석: `src/app/main.py`
- 데이터 모델: `src/app/models.py`
- 인증과 세션 무효화: `src/app/auth.py`, `src/app/dependencies.py`
- 연차 정책과 상태 전이: `src/app/services/leave_policy.py`
- 연차 신청 처리: `src/app/services/leave_service.py`
- 관리자 통계/쿼리/운영 헬퍼: `src/app/services/admin_service.py`, `src/app/services/ops.py`
- 사용자/관리자 라우터: `src/app/routers/*`
- 포터블 배포: `portable/README_PORTABLE.md`, `portable/build_portable.ps1`
- Docker 배포: `infra/docker/*`
- 검증 스크립트: `tools/scripts/*`

## 문서 읽는 순서
1. 이 페이지에서 저장소 범위를 잡습니다.
2. [아키텍처 개요](architecture.md)에서 런타임, 경로, 스케줄러, 보안 모델을 봅니다.
3. [연차 관리 도메인](domain/leave-management.md)에서 상태 전이와 정책 규칙을 확인합니다.
4. [관리자 워크플로우](workflows/admin.md)에서 승인, 사용자, 공휴일, 감사 작업을 봅니다.
5. [운영 및 유지보수](operations.md)와 [테스트 및 검증](testing.md)으로 변경 영향과 확인 방법을 봅니다.

## 변경 작업 시 주의할 점
- 비즈니스 규칙은 `src/app/services/*`에 있고, 라우팅과 화면은 `src/app/routers/*` 및 `src/templates/*`에 걸쳐 있습니다.
- 연차 정책을 바꾸면 서비스 코드, 템플릿, 검증 스크립트를 함께 봐야 합니다.
- 인증이나 사용자 상태를 바꾸면 `token_version` 기반 세션 무효화가 함께 따라갑니다.
- DB나 백업 로직을 바꾸면 스케줄러와 복구 경로를 같이 검증해야 합니다.
- 포터블 경로는 소스 실행과 다르게 템플릿/정적 자산을 다시 해석합니다.

## 기존 한국어 문서
`docs/` 디렉터리에는 설계서, 운영 가이드, 작업 로그, 릴리스 산출물 등 상세 문서가 이미 있습니다. OpenWiki는 이를 대체하지 않고, 읽기 순서와 탐색 경로를 정리하는 상위 맵 역할을 합니다.

참고 문서:
- `README.md`
- `docs/0_문서_인덱스.md`
- `docs/4-1_SHIM_프로젝트_설계서.md`
- `portable/README_PORTABLE.md`
