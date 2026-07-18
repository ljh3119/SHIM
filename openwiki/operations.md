# 운영 및 유지보수

이 페이지는 프로덕션과 유사한 환경에서 SHIM을 안정적으로 유지하기 위한 비사용자용 워크플로우를 다룹니다.

## 사업장 시간대
`SHIM_TIMEZONE`에 IANA 이름을 지정합니다. 미설정 시 `Asia/Seoul`이며 잘못된 이름은 기동 실패로 처리됩니다. Docker OS 시간대는 이미지에서 UTC로 고정되며 Compose에서 중복 지정하지 않습니다. 설정 변경은 재기동 후 적용됩니다.

## 데이터베이스 초기화와 시딩
`tools/scripts/` 아래의 유용한 스크립트는 다음과 같습니다.
- `db_init.py` — 데이터베이스 구조 생성 또는 초기화
- `seed_test_data.py` — 개발/테스트 데이터 채움
- `emergency_reset_admin.py` — 비상 관리자 초기화 유틸리티

저장소 README에는 릴리스용 버전 동기화 흐름도 설명되어 있으며, 이는 PowerShell 스크립트로도 제공됩니다.

## 백업과 복구
`src/app/services/ops.py`가 운영 안전망을 담당합니다.
- 백업 복사 전에 WAL checkpoint 수행
- 같은 디렉터리의 임시 파일에 백업한 뒤 `PRAGMA quick_check;` 통과 시 `os.replace`로 최종 `.bak`를 원자적으로 생성
- 손상 백업은 `.invalid`로 격리하고 건강한 백업만 회전·최근성 판단·`last_backup_count` 집계에 포함
- 삭제 실패 파일은 목록에서 임의로 제외하지 않고 실제 건강한 백업 수를 다시 집계
- `PRAGMA quick_check;`를 통한 손상 탐지
- 손상된 DB 및 관련 WAL/SHM 파일 격리
- 손상이 감지되면 사용 가능한 최신 백업에서 복원

중요한 운영 소스:
- `src/app/services/ops.py`
- `src/app/database.py`

## 알림 정리와 유지보수 상태
오래된 알림은 긴 lock을 피하기 위해 청크 단위로 삭제됩니다. 모든 청크와 메트릭 저장이 성공한 경우에만 `SystemSettings.last_cleanup_time`를 갱신합니다. 중간 실패 전 커밋된 일부 삭제는 남을 수 있으며, 이때 이전 성공 시각은 유지됩니다.

관리자 대시보드는 이 메트릭을 소비하며, 마지막 실행이 저장소의 건강 임계치보다 오래되면 백업/정리 지연으로 표시합니다.

## 버전 및 릴리스 워크플로우
이 저장소는 `package.json`, `README.md`, `src/app/constants.py`의 런타임 상수 사이 버전 정합성을 추적합니다.

참조 스크립트:
- `tools/scripts/release.ps1`
- `tools/scripts/verify_version_sync.ps1`
- `tools/scripts/run_remaining_tests.py`

최근 커밋 이력도 Docker와 포터블 실행 파일 산출물을 포함한 동기화된 버전 상승을 강조합니다.

## 포터블 실행
`portable/` 디렉터리는 오프라인 Windows 배포를 지원합니다. 핵심 파일:
- `portable/build_portable.ps1`
- `portable/shim_portable.py`
- `portable/README_PORTABLE.md`
- `portable/README.md`

운영상 포터블 런타임은 소스 실행이나 Docker 실행과 다르게 번들된 템플릿/static 리소스를 해석합니다.

## Docker 배포
Docker 지원은 `infra/docker/` 아래에 있습니다.
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.dev.yml`
- `docker-compose.test.yml`
- `.env.example`

Compose 파일에는 SQLite 볼륨 경로, 환경 기본값, 호스트별 마운트 동작이 들어 있습니다.

## 문제 해결 시 먼저 볼 주제
- 데이터베이스 lock 경합
- 암호화 키 재료 누락 또는 오래된 상태
- 백업 회전 실패
- 계정 변경 후 세션 무효화
- 고정/포터블 빌드에서의 런타임 자산 경로 불일치

## 핵심 소스 참고
- `src/app/services/ops.py`
- `src/app/main.py`
- `src/app/auth.py`
- `infra/docker/*`
- `portable/*`
- `tools/scripts/*`
