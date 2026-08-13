# 쉼(休) SHIM (Smart Holiday Information Management) / 연차 관리 시스템

**릴리스 버전:** 1.9.7

폐쇄망 및 내부망 환경에서 안정적으로 운영 가능한 FastAPI 기반의 연차 관리 시스템입니다. 사용자 시각 입력 방식의 정밀한 차감 로직과 관리자용 타임라인/캘린더 검증 기능을 통해 조직의 연차 운영 효율을 극대화합니다.

---

## 1. 프로젝트 개요 및 주요 기능

### 기술 스택
- **Backend**: `FastAPI`, `SQLAlchemy` (ORM), `SQLite` (Database)
- **Frontend**: `Jinja2 Template`, `Tailwind CSS v4`
- **Infrastructure**: 로컬 Python, Docker 컨테이너 또는 Windows 포터블 패키지 기반 배포

### 핵심 기능
- **정밀한 연차 신청**: 시작/종료 시각 입력 기반 차감 및 정책 단위(30/60/120분) 검증, 그리고 에어비앤비 스타일의 시작일~종료일 **기간 범위 선택(Range Selection)** 및 좌측 간편 신청 입력창과의 실시간 양방향 동기화(개인 달력 및 팀 타임라인 테이블 동시 지원, 150ms 디바운싱 탑재) 지원
- **조직 관리**: 회사/팀별로 구분이 명확한 동적 HSL 및 엄선된 웜톤/녹색계열 고대비 HSL 색상 배지가 적용된 전사 캘린더, 타임라인, 사원 관리 뷰 (팀 색상 간섭 배제)
- **결재 워크플로우**: 단선 결재(팀장·PM·관리자의 단일 승인/반려)와 관리자의 승인 취소(기록 보존·차감 연차 복구) 지원
- **모바일 사용자 업무**: 1024px 미만 화면에서 월간 캘린더, 연차 신청·조회·취소, 팀 일정과 권한별 결재 관리를 터치 중심 UI로 제공하며 필요한 월 데이터만 지연 조회
- **일관된 화면 계층**: 관리자·사용자 PC 주요 패널과 모바일 카드의 외곽선·라운딩·그림자를 통일하고, 표·차트·달력·내부 목록은 공통 저강도 그리드로 구분
- **브랜딩 및 커스터마이징**: 조직의 명칭, 로고 배지, 업무 시간 정책(점심시간 등) 설정
- **운영 편의성**: 2020~2050년 한국 공휴일 자동 시딩(2026년 이후 제헌절 및 대체공휴일 포함), 퇴사자 비활성화, 연도별 연차 할당 관리
- **시스템 운영 모니터링**: 데이터베이스 용량, Uptime(가동 시간), PII 보안 상태, 백그라운드 스케줄러(회전식 백업 및 30일 경과 알림 정리) 최종 실행 일시의 영속적 메트릭 관리자 실시간 대시보드 모니터링 (26시간 초과 시 지연/점검 경고 자동 표출)

## 2. ⚠️ 한계 및 주의사항 (Limitations)

본 프로젝트는 특정 환경(폐쇄망, 소규모 팀)을 타겟으로 설계되었습니다. 도입 전 아래 제약 사항을 반드시 확인하십시오.

### 1. 기능적 제약
- **동시성**: SQLite 엔진 특성상 수백 명 이상의 동시 쓰기가 발생하는 대규모 환경에는 적합하지 않습니다.
- **알림 부재**: 폐쇄망 운영을 전제로 하므로 이메일, 슬랙 등 외부망 연동 알림 기능이 기본 제외되어 있습니다.

- **인사 시스템 연동**: AD/LDAP 등 외부 인사 시스템과의 자동 동기화 기능이 없으며, 수동 또는 스크립트 기반 관리가 필요합니다.
- **관리자 모바일 범위**: 관리자 모바일 화면은 현황 조회 수준만 보장합니다. 사원·조직·연차 데이터의 등록, 수정, 삭제와 같은 운영 처리는 PC에서 수행해야 합니다.
### 2. 보안적 제약
- **통신 보안**: 기본 HTTP로 동작합니다. 공개망 운영 시 반드시 Nginx/NPMPlus 등을 통해 HTTPS(SSL/TLS)를 적용하고 `SHIM_SECURE_COOKIE=true`를 설정하십시오.
- **데이터 보호**: `SHIM_SECRET_KEY`를 설정하면 사원명과 휴가 사유 등 민감정보가 암호화됩니다. DB와 키를 모두 안전하게 백업하고, 운영 중 키를 변경하거나 분실하지 마십시오.
- **키 사고 대응**: 키 유출·분실이 의심되면 서비스를 중지하고 DB, 현재 키와 설정 파일을 한 세트로 보존하십시오. 검증된 로테이션 도구가 제공되기 전에는 운영 키를 수동 변경하거나 재생성하지 마십시오.
- **파일 권한**: DB, `.env`, `secret.key`에 대한 OS 접근 권한과 물리적 보안을 제한해야 합니다.
- **인증 보안**: 무차별 대입 공격 방지(계정 잠금)나 2차 인증(MFA) 기능은 현재 포함되어 있지 않습니다.
- **HTTP 방어선**: 모든 응답에 기본 CSP, MIME 추론·프레임·리퍼러·브라우저 권한 제한 헤더를 적용합니다. 기본 HTTP 배포 호환성을 위해 HSTS는 강제하지 않습니다.

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

설치는 **[환경 설정] → [서버 실행] → [시스템 접속]** 순으로 진행됩니다.
### Step 1. 환경 설정 및 보안 구성
Docker와 로컬 실행은 환경변수 적용 방법이 다릅니다.

#### Docker 운영

1.  **설정 파일 준비**: 예제 파일을 프로젝트 루트의 `.env`로 복사합니다.
    ```powershell
    Copy-Item ./infra/docker/.env.example ./.env
    ```
2.  **보안키 생성**: 암호학적으로 안전한 무작위 키를 생성합니다.
    ```powershell
    python -c "import secrets; print(secrets.token_urlsafe(48))"
    ```
3.  **값 반영**: 생성된 문자열을 `.env`의 `SHIM_SECRET_KEY=` 뒤에 붙여넣습니다.
    - 이 키는 JWT 서명과 PII 암호화에 함께 사용됩니다.

    - 운영 중 키를 변경하지 말고, 실제 `.env`는 DB와 별도로 안전하게 백업하십시오.
4.  **사업장 시간대 확인**: 국내 운영은 `SHIM_TIMEZONE=Asia/Seoul`을 유지합니다. 잘못된 IANA 이름이면 앱이 기동되지 않습니다.
5.  **HTTPS 쿠키 설정**: Nginx/NPMPlus로 HTTPS를 제공할 때는 `SHIM_SECURE_COOKIE=true`, 직접 HTTP로 시험할 때는 `false`를 사용합니다.
6.  **데이터 경로 확인**: 예제의 `SHIM_DATA_DIR=../../var/data`는 프로젝트 루트의 `var/data`를 Docker 데이터 폴더로 사용합니다.
7.  **운영 키 확인**: 운영 배포에서는 `SHIM_SECRET_KEY`를 비워두지 말고, 시작 로그에 `SECURE ENCRYPTION mode (PII Protected)`가 표시되는지 확인합니다.
#### 로컬 개발
루트 `.env`는 `npm run dev`에서 자동으로 로드되지 않습니다. 필요한 값을 현재 PowerShell 세션에 직접 설정합니다.
```powershell

$env:SHIM_SECRET_KEY = Read-Host "보관 중인 SHIM_SECRET_KEY"
$env:SHIM_TIMEZONE = "Asia/Seoul"

```

처음 생성한 키를 안전하게 보관하고 이후 실행에서도 같은 값을 재사용해야 합니다.
`SHIM_DATA_DIR`를 설정하지 않으면 로컬 DB는 프로젝트 루트의 `var/data`에 저장됩니다.
### Step 2. 서버 실행
환경에 따라 세 가지 방식 중 하나를 선택하여 실행합니다.
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
docker build -f infra/docker/Dockerfile -t shim:1.9.7 -t shim:latest .

# 컨테이너 실행

docker compose --env-file .env -f infra/docker/docker-compose.yml up -d
```

기동 후 `http://localhost:8000/health`가 `{"status":"ok"}`를 반환하는지 확인합니다. `/docs`, `/redoc`, `/openapi.json`은 기본적으로 비공개이며, 개발 환경에서만 `SHIM_ENABLE_OPENAPI=true`로 활성화합니다. 모든 HTTP 응답에는 CSP, MIME 스니핑·프레임·리퍼러 차단과 브라우저 권한 제한 헤더가 적용되며 HTTP 배포 호환을 위해 HSTS는 강제하지 않습니다.

#### 방식 C. 폐쇄망용 포터블 실행 (Portable)
인터넷이나 Docker 설치가 불가능한 환경에서 사용합니다.
1.  **빌드**: `powershell -ExecutionPolicy Bypass -File .\portable\build_portable.ps1`
2.  **배포**: 생성된 `dist/SHIM_Portable_v<버전>_<빌드시각>.zip`을 대상 PC로 복사한 뒤 전체 압축을 풉니다.
3.  **실행**: 해당 폴더 내 `SHIM_Portable.exe`를 더블 클릭하여 실행합니다.
    - 안내창을 확인하고 아무 키나 눌러 창을 닫아도 백그라운드에서 서버가 유지되며, 시스템 트레이 아이콘을 통해 관리(브라우저 열기, 서비스 종료)할 수 있습니다.
    - 상세 안내: [사용자용 가이드](portable/README_PORTABLE.md), [개발자용 디렉토리 가이드](portable/README.md)
### Step 3. 시스템 최초 접속 및 초기 설정
서버가 정상적으로 기동되었다면 브라우저를 통해 접속합니다.

1.  **브라우저 접속**: 기동한 환경에 맞추어 접속합니다.
    - **로컬 개발 서버**: 콘솔에 출력된 주소(기본 시작 포트 `http://localhost:9090`, 사용 중이면 다음 포트)
    - **Docker 및 포터블 환경**: `http://localhost:8000` (포터블의 경우 포트가 이미 사용 중이면 8001 등으로 자동 할당됩니다)
2.  **최초 로그인**: 아래 기본 관리자 계정으로 로그인합니다.
    - **ID**: `admin`
    - **PW**: `0000`
3.  **보안 조치**: 로그인 직후 **[마스터 관리 > 개인정보 수정]** 메뉴에서 관리자 비밀번호를 반드시 변경하십시오.

#### 모바일 기기에서 접속

1. 서버 PC와 모바일 기기를 동일한 신뢰 가능한 사내망 또는 Wi-Fi에 연결합니다.
2. 서버 PC에서 `ipconfig`로 IPv4 주소를 확인한 뒤 모바일 브라우저에서 `http://<서버 PC IPv4>:<실행 포트>`로 접속합니다. 예: `http://192.168.0.20:9090`
   - 휴대폰의 `localhost`는 서버 PC가 아니라 휴대폰 자신을 가리키므로 사용할 수 없습니다.
   - 기본 포트는 로컬 개발 `9090`, Docker·포터블 `8000`이며 실행 중 자동으로 바뀐 경우 실제 표시된 포트를 사용합니다.
3. 연결되지 않으면 Windows Defender 방화벽에서 해당 TCP 포트를 **개인 네트워크에만** 허용했는지 확인합니다.
4. 기본 통신은 HTTP이므로 공용 Wi-Fi나 인터넷에 직접 노출하지 마십시오. 외부 접속이 필요하면 HTTPS 역방향 프록시와 보안 쿠키를 먼저 구성합니다.

모바일 UI는 1024px 미만에서 활성화됩니다. 수동 확인 기준은 세로 `320×568`, `360×800`, `390×844`, `412×915`, `425px` 폭과 가로 화면입니다. `STAFF`는 신청·조회·취소, `TEAM_LEAD`와 `PM`은 권한 범위의 팀 일정·결재까지 사용할 수 있습니다. `ADMIN`은 조회용으로만 사용하고 실제 관리 처리는 PC에서 진행하십시오.


---

## 5. 💡 연차 운영 가이드 (Annual Leave Operations)

본 시스템은 **"연도별 연차 격리 방식"**을 채택하여, 특정 연도의 연차를 변경해도 다른 연도에는 영향을 주지 않습니다. 연말/연초에는 관리자 대시보드에 새해 연차 일괄 지급 안내 배너가 자동으로 표시됩니다.

> 📖 연차 격리 정책, 연말/연초 일괄 지급 절차, 결재 모델 등 상세 운영 가이드는 **[설계서 내 운영/결재 모델 절](docs/4-1_SHIM_프로젝트_설계서.md#38-현장-실무-결재-권한-운영-및-연차-지급-모델-operations--approval-models)**을 참조하십시오.

---

## 6. 기타 가이드 및 스크립트

### 유용한 단축 명령어 (PowerShell)
| 기능 | 명령어 | 비고 |
|:--- |:--- |:--- |
| **개발 서버 기동** | `.\tools\scripts\dev.ps1` | 로컬 개발용 |
| **DB 백업** | `.\tools\scripts\backup_db.ps1` | 로컬 기본 경로 `var/data/backup`에 저장 |
| **버전 동기화** | `.\tools\scripts\release.ps1 -Version 1.9.7` | 릴리즈 시 필수 실행 |
| **검사 및 Docker 빌드** | `.\tools\scripts\release.ps1 -Version 1.9.7 -RunChecks -BuildImage` | CSS·검사 통과 후 이미지 생성 |
| **버전 검증** | `.\tools\scripts\verify_version_sync.ps1` | 정합성 체크 |
| **Git 훅 설치** | `.\tools\scripts\install_git_hooks.ps1` | 최초 1회 실행 |
| **빠른 회귀 검사** | `npm test` | 핵심 검사, 약 2분 |
| **릴리스 전체 검사** | `npm run test:release` | 메모리 1,000회 포함, 약 6분 |
| **UI 스타일 회귀 검사** | `python tools/scripts/test_ui_style.py` | 패널·테두리 계층과 의미색 유지 검증 |
| **성능 측정** | `python tools/scripts/performance_rehearsal.py` | 운영 규모 시뮬레이션 |

### 주요 문서 및 산출물 목록
- **운영 가이드**: [초심자 가이드](docs/1-1_초심자_구동_가이드.md), [백업/복구 가이드](docs/1-2_백업_복구_유지보수_가이드.md), [실무 운영/결재 내용(설계서 3.8절)](docs/4-1_SHIM_프로젝트_설계서.md#38-현장-실무-결재-권한-운영-및-연차-지급-모델-operations--approval-models), [포터블 가이드](portable/README_PORTABLE.md)
- **릴리즈 정보**: [통합 산출물 증적](docs/2-1_운영_릴리즈_통합_산출물.md), [변경 이력](docs/1-4_작업_로그.md)
- **기술 설계**: [프로젝트 설계서](docs/4-1_SHIM_프로젝트_설계서.md), [AI 인수인계 내용(설계서 8절)](docs/4-1_SHIM_프로젝트_설계서.md#8-검증-및-테스트-세트-가이드-test-suite-guide)
- **데이터 위치**
  - 로컬 및 본 Docker 예제: `var/data/shim_internal.db`
  - 포터블: 실행 파일 옆 `data/shim_internal.db`
  - 암호화 모드에서는 DB뿐 아니라 `.env` 또는 `data/secret.key`도 별도로 백업해야 합니다.

---

## 7. 기여하기 (Contributing)

SHIM은 오픈소스 프로젝트로서 여러분의 기여를 환영합니다.
1. **Issue**: 버그 제보 및 기능 제안을 남겨주세요.
2. **Pull Request**: 새로운 기능을 구현하거나 버그를 수정한 경우 PR을 보내주세요.
3. **Convention**: 기존의 코드 스타일과 테스트 원칙을 준수해 주세요.

---

## 8. 라이선스 (License)

본 프로젝트는 **MIT License** 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하십시오.

Copyright (c) 2026 SHIM Authors.
