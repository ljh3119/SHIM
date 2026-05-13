# 쉼(休) SHIM / 연차 관리 시스템

**릴리스 버전:** 1.3.2

폐쇄망 및 내부망 환경에서 안정적으로 운영 가능한 FastAPI 기반의 연차 관리 시스템입니다. 사용자 시각 입력 방식의 정밀한 차감 로직과 관리자용 타임라인/캘린더 검증 기능을 통해 조직의 연차 운영 효율을 극대화합니다.

---

## 1. 프로젝트 개요 및 주요 기능

### 기술 스택
- **Backend**: `FastAPI`, `SQLAlchemy` (ORM), `SQLite` (Database)
- **Frontend**: `Jinja2 Template`, `Tailwind CSS v4`
- **Infrastructure**: 로컬 Python 가상환경 또는 Docker 컨테이너 기반 배포

### 핵심 기능
- **정밀한 연차 신청**: 시작/종료 시각 입력 기반 차감 및 정책 단위(30/60/120분) 검증
- **조직 관리**: 사용자/회사/팀 필터 기반의 전사 캘린더 및 타임라인 뷰
- **결재 워크플로우**: 2단계 결재(팀장 승인/반려 및 관리자 최종 승인) 지원
- **브랜딩 및 커스터마이징**: 조직의 명칭, 로고 배지, 업무 시간 정책(점심시간 등) 설정
- **운영 편의성**: 한국 공휴일 자동 시딩, 퇴사자 비활성화, 연도별 연차 할당 관리

## 2. ⚠️ 한계 및 주의사항 (Limitations)

본 프로젝트는 특정 환경(폐쇄망, 소규모 팀)을 타겟으로 설계되었습니다. 도입 전 아래 제약 사항을 반드시 확인하십시오.

### 1. 기능적 제약
- **동시성**: SQLite 엔진 특성상 수백 명 이상의 동시 쓰기가 발생하는 대규모 환경에는 적합하지 않습니다.
- **알림 부재**: 폐쇄망 운영을 전제로 하므로 이메일, 슬랙 등 외부망 연동 알림 기능이 기본 제외되어 있습니다.
- **인사 시스템 연동**: AD/LDAP 등 외부 인사 시스템과의 자동 동기화 기능이 없으며, 수동 또는 스크립트 기반 관리가 필요합니다.

### 2. 보안적 제약
- **통신 보안**: 기본 HTTP로 동작합니다. 공개망 운영 시 반드시 Nginx 등을 통해 HTTPS(SSL/TLS)를 적용하십시오.
- **데이터 보호**: DB 파일(`shim_internal.db`)에 대한 접근 권한이 곧 전사 데이터 접근 권한과 같습니다. 물리적 보안 및 OS 권한 관리가 필수적입니다.
- **인증 보안**: 무차별 대입 공격 방지(계정 잠금)나 2차 인증(MFA) 기능은 현재 포함되어 있지 않습니다.

---

## 3. 🛠️ 사전 요구사항 (Prerequisites)

시스템 구축을 시작하기 전, 아래 환경이 준비되었는지 확인하십시오.

### 로컬 개발 환경 (Local Development)
- **Python**: 3.10 이상
- **Node.js**: 18 이상 (Tailwind CSS 빌드용)
- **OS**: Windows (PowerShell 사용 권장) 또는 Linux/macOS

### 운영 환경 (Production)
- **Docker**: Docker Engine 20.10+
- **Docker Compose**: v2.0+

---

## 🚀 4. 빠른 시작 (Quick Start)

설치는 인지적 흐름에 따라 **[환경 설정] -> [서버 실행] -> [시스템 접속]** 순으로 진행됩니다.

### Step 1. 환경 설정 및 보안 구성
가장 먼저 시스템의 보안의 핵심인 JWT 서명키를 설정해야 합니다. 이는 로그인 토큰 위조를 방지하기 위한 필수 절차입니다.

1.  **설정 파일 준비**: `infra/docker/.env.example` 파일을 프로젝트 루트의 `.env` 파일로 복사합니다.
    ```powershell
    Copy-Item ./infra/docker/.env.example ./.env
    ```
2.  **보안키 생성**: 아래 명령어를 통해 랜덤 서명키를 생성합니다.
    ```powershell
    # PowerShell 예시
    [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
    ```
3.  **값 반영**: 생성된 문자열을 `.env` 파일의 `SHIM_SECRET_KEY=` 뒤에 붙여넣고 저장합니다.

### Step 2. 서버 실행
환경에 따라 두 가지 방식 중 하나를 선택하여 실행합니다.

#### 방식 A. 로컬 환경에서 즉시 실행 (Local)
```powershell
# 의존성 설치
pip install -r requirements.txt
npm install

# 서버 기동 (Tailwind watch 포함)
npm run dev
```

#### 방식 B. Docker 컨테이너로 실행 (Production)
```powershell
# 이미지 빌드
docker build -f infra/docker/Dockerfile -t shim:1.3.2 -t shim:latest .

# 컨테이너 실행
docker compose -f infra/docker/docker-compose.yml up -d
```

### Step 3. 시스템 최초 접속 및 초기 설정
서버가 정상적으로 기동되었다면 브라우저를 통해 접속합니다.

1.  **브라우저 접속**: `http://localhost:8000`에 접속합니다.
2.  **최초 로그인**: 아래 기본 관리자 계정으로 로그인합니다.
    - **ID**: `admin`
    - **PW**: `0000`
3.  **보안 조치**: 로그인 직후 **[마스터 관리 > 개인정보 수정]** 메뉴에서 관리자 비밀번호를 반드시 변경하십시오.

---

## 5. 기타 가이드 및 스크립트

### 유용한 단축 명령어 (PowerShell)
| 기능 | 명령어 | 비고 |
|:--- |:--- |:--- |
| **개발 서버 기동** | `.\tools\scripts\dev.ps1` | 로컬 개발용 |
| **DB 백업** | `.\tools\scripts\backup_db.ps1` | `var/data/backup`에 저장 |
| **버전 동기화** | `.\tools\scripts\release.ps1 -Version 1.3.2` | 릴리즈 시 필수 실행 |
| **버전 검증** | `.\tools\scripts\verify_version_sync.ps1` | 정합성 체크 |
| **성능 측정** | `python tools/scripts/performance_rehearsal.py` | 운영 규모 시뮬레이션 |

### 주요 문서 및 산출물 목록
- **운영 가이드**: [초심자 가이드](docs/1-1_초심자_구동_가이드.md), [백업/복구 가이드](docs/1-2_백업_복구_유지보수_가이드.md)
- **릴리즈 정보**: [통합 산출물 증적](docs/2-1_운영_릴리즈_통합_산출물.md), [변경 이력](docs/1-4_작업_로그.md)
- **기술 설계**: [프로젝트 설계서](docs/4-1_SHIM_프로젝트_설계서.md), [AI 인수인계 가이드](docs/3-2_AI_인수인계_가이드.md)
- **데이터베이스**: `var/data/shim_internal.db` (운영 시 정기 백업 필수)

---

## 6. 기여하기 (Contributing)

SHIM은 오픈소스 프로젝트로서 여러분의 기여를 환영합니다.
1. **Issue**: 버그 제보 및 기능 제안을 남겨주세요.
2. **Pull Request**: 새로운 기능을 구현하거나 버그를 수정한 경우 PR을 보내주세요.
3. **Convention**: 기존의 코드 스타일과 테스트 원칙을 준수해 주세요.

---

## 7. 라이선스 (License)

본 프로젝트는 **MIT License** 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하십시오.

Copyright (c) 2026 SHIM Authors.
