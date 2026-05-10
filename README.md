# 쉼(休) SHIM / 연차 관리 시스템

**릴리스 버전:** 1.2.1

폐쇄망 환경에서 사용 가능한 FastAPI 기반 연차 관리 시스템입니다.
사용자/관리자 화면, 월별/연간 캘린더, 시간 슬롯 기반 차감, 타임라인 검증 기능을 제공합니다.

## 프로젝트 개요

- 백엔드: `FastAPI`, `SQLAlchemy`, `SQLite`
- 프론트: `Jinja2 Template`, `Tailwind CSS`
- 실행 방식: 로컬 Python 실행 또는 Docker 컨테이너 실행
- 기본 DB 파일: `var/data/shim_internal.db`

## 주요 기능

- 사용자 로그인/로그아웃
- 사용자 연차 신청 및 조회
- 관리자 대시보드
- 사용자/회사/팀 필터 기반 연차 캘린더(월별/연간)
- 시간 슬롯(예: 오전 2시간, 전일) 관리
- 퇴사자 비활성화 관리
- 사용자별 연차 지급값 관리
- 다국어(한국어) 및 공휴일 자동 시딩

## ⚠️ 한계 및 주의사항 (Limitations)

본 프로젝트는 특정 환경(폐쇄망, 소규모 팀)을 위해 설계되었으므로 아래와 같은 제약 사항이 있습니다. 도입 전 반드시 확인하시기 바랍니다.

### 1. 기능적 제약 (Functional)
- **동시성**: SQLite를 사용하므로 수백 명 이상의 동시 쓰기가 발생하는 환경에는 적합하지 않습니다.
- **알림**: 외부망 차단을 전제로 하므로 이메일, 슬랙 등 외부 연동 알림 기능이 없습니다.
- **워크플로우**: 1단계(관리자 직접 승인/반려)의 단순한 결재 구조만 지원합니다.
- **인사 연동**: AD/LDAP 등 외부 인사 시스템과의 자동 동기화 기능이 없습니다.

### 2. 보안적 제약 (Security)
- **통신 보안**: 기본적으로 HTTP로 동작합니다. 공개된 네트워크에서 운영 시 반드시 Nginx 등을 이용해 HTTPS(SSL/TLS)를 적용해야 합니다.
- **데이터 보호**: DB 파일(`shim_internal.db`)에 접근할 수 있는 권한은 곧 모든 데이터에 대한 접근 권한과 같습니다. 물리적/OS 수준의 보안이 중요합니다.
- **인증키 관리**: `SHIM_SECRET_KEY`가 유출되면 토큰 위조가 가능합니다. 반드시 기본값을 변경하고 엄격히 관리하십시오.
- **보안 정책**: 무차별 대입 공격 방지(계정 잠금)나 2차 인증(MFA) 기능은 현재 구현되어 있지 않습니다.

## 빠른 시작

처음 실행하는 사람은 아래 문서를 순서대로 보면 됩니다.

1. `docs/1-1_초심자_구동_가이드.md`
2. `docs/1-2_백업_복구_유지보수_가이드.md`
3. `docs/0_문서_인덱스.md`

개발 PC에서 즉시 실행:

```powershell
pip install -r requirements.txt
npm install
npm run dev
```

Docker 실행(운영/개발 분리):

```powershell
# 운영(실행 전용): 먼저 버전 태그로 이미지 빌드 후 compose 실행
docker build -f infra/docker/Dockerfile -t shim:1.2.1 -t shim:latest .
docker compose -f infra/docker/docker-compose.yml up -d

# 개발(compose에서 빌드 포함)
docker compose -f infra/docker/docker-compose.dev.yml up -d --build
```

스크립트 단축 명령:

```powershell
# 로컬 개발 서버(Tailwind watch + Uvicorn)
.\tools\scripts\dev.ps1

# DB 백업 생성
.\tools\scripts\backup_db.ps1

# 관리자 화면 성능 리허설(서버 기동 후)
python tools\scripts\performance_rehearsal.py

# Docker 단축 명령 도움말
.\tools\scripts\docker.ps1 help

# 릴리즈 버전 동기화(예: 1.2.1)
.\tools\scripts\release.ps1 -Version 1.2.1

# package.json 기준으로 코드·README·포터블 README 버전 일치 검사
.\tools\scripts\verify_version_sync.ps1
```

## 실행 포트

- 기본 포트: `8000`
- 접속 주소: `http://localhost:8000`

## 기본 관리자 계정

- ID: `admin`
- PW: `0000`

처음 로그인 후 반드시 비밀번호를 변경하세요.
운영 배포 전에는 JWT 서명키(`SHIM_SECRET_KEY`)도 반드시 고정하세요.

권장 방식은 `.env.example`을 `.env`로 복사한 뒤 긴 랜덤 문자열을 넣는 것입니다.

```powershell
Copy-Item .\.env.example .\.env
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
```

생성된 값을 `.env`에 넣습니다.

```env
SHIM_SECRET_KEY=여기에_생성한_긴_랜덤_문자열
```

그 뒤 Docker를 실행합니다.

```powershell
docker compose -f infra/docker/docker-compose.yml up -d
```

설정하지 않아도 기본값으로 실행은 되지만, 실제 운영에서는 보안상 `.env` 설정을 권장합니다.

## 변경 이력

상세 릴리즈 증적과 검증 결과는 `docs/2-1_운영_릴리즈_통합_산출물.md`에서 관리합니다.

- 최신 릴리즈: `1.2.1` (2026-05-07)
- 주요 변경: dense UI 가독성 보정(텍스트 대비 토큰 상향, 사이드바 토글 아이콘/밸런스 개선), 승인 워크플로우 OFF 시 관리자 대시보드의 결재 대기 강조/위젯 숨김(상세·검증은 `docs/2-1_운영_릴리즈_통합_산출물.md`)

## 문서 목록

- `docs/0_문서_인덱스.md`: 현재 유지 문서/산출물 빠른 안내
- `docs/1-1_초심자_구동_가이드.md`: 설치부터 실행까지
- `docs/1-2_백업_복구_유지보수_가이드.md`: 운영/장애 대응 가이드
- `docs/1-3_운영_릴리즈_실행_체크리스트.md`: 운영 담당자용 1페이지 릴리즈 실행 체크리스트
- `docs/1-4_작업_로그.md`: 릴리즈 증적에 넣지 않는 내부 작업 메모
- `docs/2-1_운영_릴리즈_통합_산출물.md`: 완료된 릴리즈 증적/검증 결과
- `docs/3-1_향후_개선계획.md`: 앞으로 할 작업 목록
- `docs/3-2_AI_인수인계_가이드.md`: 다른 AI 또는 개발자가 이어받을 때의 작업 기준
- `docs/4-1_SHIM_프로젝트_설계서.md`: 아키텍처·DB·비즈니스 규칙·산출물 인덱스(구현 기준)
- `design/ui-handoff/`: Dense UI 설계 원칙 및 디자인 대안 시안 (참고용 히스토리 자산, 앱 실행과는 무관)
- `portable/README_PORTABLE.md`: Docker 불가 폐쇄망 PC 무설치 실행 가이드

## 산출물 목록

- 운영 데이터: `var/data/shim_internal.db` (Git 제외, 초기 기동 시 자동 생성)
- 배포용 CSS: `src/static/css/tailwind.css` (빌드 스크립트로 자동 생성)
- 포터블 실행본(빌드 후): `dist/SHIM_Portable/` (Git 제외, 빌드 시 생성)
- 포터블 빌드 스크립트: `portable/build_portable.ps1`
- 개발 실행 스크립트: `tools/scripts/dev.ps1`
- Docker 단축 스크립트: `tools/scripts/docker.ps1`
- DB 백업 스크립트: `tools/scripts/backup_db.ps1`
- 운영 규모 성능 리허설 스크립트: `tools/scripts/performance_rehearsal.py`
- Docker 운영 환경 변수 샘플: `.env.example`
