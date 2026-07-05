# OpenWiki 빠른 시작

SHIM은 FastAPI, SQLAlchemy, SQLite, Jinja2, Tailwind CSS로 구성된 폐쇄망용 연차 관리 시스템입니다. 이 저장소는 두 가지 주요 사용자군을 대상으로 합니다.
- **직원**: 개인 연차 달력과 신청 흐름을 사용합니다.
- **관리자 / 팀장 / PM**: 승인, 사용자, 공휴일, 설정, 감사, 운영 상태를 관리합니다.

이 저장소는 로컬 Windows 실행, Docker 배포, 그리고 오프라인 환경용 포터블 패키지 실행을 모두 염두에 두고 설계되었습니다.

## 먼저 볼 문서
- [아키텍처 개요](architecture.md)
- [관리자 워크플로우](workflows/admin.md)
- [관리자 라우터 소스 맵](routers/admin-source-map.md)
- [연차 관리 도메인](domain/leave-management.md)
- [운영 및 유지보수](operations.md)
- [테스트 및 검증](testing.md)

## 이 시스템이 하는 일
- SQLite에서 연도별 할당 및 차감 규칙으로 연차를 관리합니다.
- 날짜 단위와 시간대 단위 연차 신청을 지원하며, 점심시간 제외와 정책 기반 반올림을 포함합니다.
- STAFF, TEAM_LEAD, PM, ADMIN 역할 기반 워크플로우를 제공합니다.
- 감사 로그, 알림, 공휴일, 시스템 설정을 같은 SQLite DB에 유지합니다.
- 백업과 알림 정리 배경 작업을 수행하며, SQLite 손상 또는 잠금 경합에 대한 복구 로직을 포함합니다.
- 사용자 및 관리자 경험을 위해 HTML 페이지와 소규모 JSON API를 함께 제공합니다.

## 핵심 소스 영역
- 애플리케이션 시작 및 라우팅: `src/app/main.py`
- 데이터 모델 및 감사/이벤트 훅: `src/app/models.py`
- 인증 및 JWT/쿠키 처리: `src/app/auth.py`
- SQLite 설정 및 세션 관리: `src/app/database.py`
- 연차 정책 및 상태 전이 규칙: `src/app/services/leave_policy.py`
- 연차 신청 워크플로우: `src/app/services/leave_service.py`
- 관리자 대시보드 및 통계 쿼리: `src/app/services/admin_service.py`
- 운영 백업 및 DB 복구: `src/app/services/ops.py`
- 사용자/관리자 라우터: `src/app/routers/*`
- 포터블 패키지 참고: `portable/README_PORTABLE.md`
- Docker 배포 파일: `infra/docker/*`
- 유틸리티 스크립트: `tools/scripts/*`

## 현재 작업 모델
이 저장소의 가장 중요한 설계 제약은, 더 무거운 인프라보다 가벼운 SQLite 기반 스택을 선호한다는 점입니다. 최근 변경들은 다음을 강화하는 방향으로 누적되었습니다.
- SQLite WAL 동작과 잠금 처리
- token_version 기반 세션 무효화
- 키가 있을 때 민감 텍스트 필드 암호화
- 시스템 설정 캐시와 시작 시 복구
- 백업 / 정리 스케줄러 및 상태 메트릭

## 주요 영역
- [아키텍처와 런타임](architecture.md)
- [연차 관리 도메인](domain/leave-management.md)
- [운영 및 유지보수](operations.md)
- [테스트 및 검증](testing.md)

## 기존 문서 참고
`docs/` 디렉터리에는 설계서, 운영 산출물, 작업 로그, 백로그 등 상세한 한국어 자료가 이미 있습니다. OpenWiki는 이를 대체하는 문서가 아니라, 위 자료 위에 얹히는 탐색/요약 레이어로 보는 것이 맞습니다.

## 향후 작업 시 메모
- 비즈니스 규칙은 `src/app/services/*`, 요청/응답 처리는 `src/app/routers/*`를 우선 확인합니다.
- 연차 로직을 바꿀 때는 정책 검증과 UI 템플릿을 함께 봐야 합니다. 폼과 정책 헬퍼가 강하게 결합되어 있습니다.
- 인증이나 사용자 생명주기 동작을 바꿀 때는 `token_version`이 기존 JWT 쿠키를 무효화한다는 점을 기억해야 합니다.
- DB나 백업 로직을 바꿀 때는 스케줄러와 복구 경로를 둘 다 검증해야 합니다.
