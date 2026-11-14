# 쉼(休) SHIM: 현장의 부재 일정을 함께 보는 연차 관리 도구

**릴리스 버전:** 1.12.2

SHIM(Smart Holiday Information Management)은 **누가 언제 휴가·출장으로 자리를 비우는지 한 화면에서 공유하는 내부망용 도구**입니다. 여러 회사가 함께 일하는 단기 프로젝트에서 팀과 PM이 일정을 조율하고 가용 인력을 파악하도록 돕기 위해 만들었습니다.

출발점은 폐쇄망 현장의 협업입니다. 외부 서비스를 연결하기 어려운 환경에서도 회사와 팀을 넘나드는 부재 일정을 모아 보고, 신청과 결재를 같은 곳에서 처리하는 데 초점을 맞췄습니다. 이 배경과 범위는 [프로젝트 설계서의 설계 철학](docs/4-1_SHIM_프로젝트_설계서.md#0-설계-철학-및-시스템-정체성-design-philosophy--identity)에 기록되어 있습니다.

## 어떤 현장에 맞나요?

- 외부 서비스 호출 없이 내부망에서 직접 운영해야 하는 현장
- 여러 회사가 컨소시엄으로 참여하며, 한 프로젝트의 부재 일정을 함께 확인하는 조직
- 별도 DB 서버 없이 PC나 NAS에서 운영하려는 소규모 팀
- 급여·인사 시스템과 별개로 연차 신청, 결재, 일정 공유가 필요한 단기 프로젝트

Windows 무설치 패키지와 Docker 실행을 지원합니다. 운영자는 서버 접근, 계정, 백업과 키를 관리해야 합니다. MIT 라이선스로 사용할 수 있지만 장비와 운영 관리 비용까지 없어지는 것은 아닙니다.

## 무엇을 할 수 있나요?

| 필요한 일 | SHIM이 제공하는 기능 |
| --- | --- |
| 함께 일하는 사람의 부재 확인 | 여러 회사·팀의 연차와 출장·공가 같은 비차감 일정을 캘린더와 타임라인에서 조회합니다. 회사·팀 배지는 소속을 구분하는 표시입니다. |
| 신청과 결재 처리 | 승인 필요 여부를 설정하고, 팀장·PM·관리자가 권한 범위에서 단일 승인·반려를 처리합니다. 관리자는 승인 취소 시 기록을 남기고 차감 연차를 복구할 수 있습니다. |
| 현장 근무 정책 반영 | 근무·점심시간, 신청 단위 30/60/120/240분을 설정합니다. 240분 정책에서는 전일 또는 표준 오전·오후 반차를 신청합니다. |
| 과거 신청 기준 보존 | 신청 시점의 시간과 차감량을 스냅샷으로 저장하고, 연차 할당을 연도별로 관리합니다. |
| 운영 상태 확인 | 앱 내 알림, 감사 로그, 공휴일 관리, 백업과 스케줄러 상태 조회를 제공합니다. 조직명·약칭·배지 문자도 설정할 수 있습니다. |

팀장은 **같은 회사·팀**의 요청을 결재하며, PM은 전사 범위를 다룹니다. 캘린더 공유 범위는 역할과 설정에 따라 달라집니다. 회사·팀 표시는 회사별로 독립된 보안 테넌트를 제공한다는 뜻이 아닙니다.

직원(`STAFF`), 팀장(`TEAM_LEAD`), PM은 모바일에서 신청·조회·취소와 권한별 팀 일정·결재를 사용할 수 있습니다. 관리자(`ADMIN`) 모바일 화면은 조회 위주이며, 등록·수정·삭제 같은 운영 업무는 PC에서 처리합니다.

## 지원 범위와 한계

등록된 부재 일정은 협업을 위한 참고 정보입니다. 출퇴근을 실측하거나, 일정이 비어 있는 사람이 실제로 업무에 투입될 수 있음을 보장하지 않습니다.

- 급여·노무 정산, 인사 평가, 법정 연차 자동 발생이나 입사일 기준 자동 산정 엔진은 제공하지 않습니다. 연도별 할당량은 운영자가 관리합니다.
- 다단계 결재, AD/LDAP/SSO 자동 동기화, 외부 메일·메신저 연동은 지원하지 않습니다. 알림은 앱 안에서 확인합니다.
- SQLite를 쓰는 단일 인스턴스 운영이 기본입니다. 대규모 동시 쓰기, 다중 서버 고가용성, 독립된 다중 프로젝트 테넌트 운영은 보장하지 않습니다. 적정 규모는 실제 장비와 신청·조회 패턴으로 측정해야 합니다.
- `python-jose` 의존성의 취약점 경고가 남아 있습니다. 현재 SHIM의 인증 방식은 검토한 공격 조건과 다르지만, 라이브러리 자체의 수정은 완료되지 않았습니다. [현재 개선 과제와 검토 상태](docs/3-1_향후_개선계획.md)를 확인하세요.

### 운영 전 보안 조건

기본 사용 환경은 신뢰 가능한 내부망이며 통신은 HTTP입니다. 로그인 시도 제한·계정 잠금과 MFA는 없습니다. 인터넷에 직접 노출하지 마세요. HTTPS 역방향 프록시를 사용할 때는 `SHIM_SECURE_COOKIE=true`도 설정해야 하지만, 이것만으로 공개망 운영의 보안 검증이 끝나는 것은 아닙니다.

**신규 DB를 암호화해서 시작하려면 첫 실행 전에 `SHIM_SECRET_KEY`를 설정하세요.** 이 키는 JWT 서명과 사원명·휴가 사유 같은 민감 컬럼 암호화에 사용됩니다. 키를 지정하지 않았을 때 자동 생성되는 데이터 폴더의 `secret.key`는 로그인용 JWT 키이며, 민감 컬럼은 평문 모드일 수 있습니다. 자동 생성 키가 있다는 이유로 암호화됐다고 판단하지 마세요.

**기존 DB는 사용하던 키와 암호화 모드를 그대로 유지하세요.** 평문 DB에 키만 추가해도 자동 암호화되지 않습니다. 키·모드가 불일치하면 기동이 거부되거나 데이터를 읽지 못할 수 있습니다. 암호화 전환·키 교체 도구는 제공하지 않습니다. 키 유출·분실이 의심되면 서비스를 중지하고 DB, 기존 키와 설정을 보존하세요.

DB와 백업, `.env`, `secret.key`의 파일 접근 권한을 제한하세요. DB와 키는 함께 복구할 수 있도록 대응 관계를 유지하되 별도로 안전하게 보관해야 합니다. 복구 조건과 절차는 [백업·복구 가이드](docs/1-2_백업_복구_유지보수_가이드.md)와 [운영 및 유지보수](openwiki/operations.md)를 참고하세요.

## 빠른 시작: 받은 파일로 폐쇄망에서 실행

아래는 관리자로부터 **이미 준비된 패키지**를 받은 경우의 안내입니다. 현재 공개 GitHub Release에 바이너리를 게시하지 않았습니다. 패키지의 실행 안내와 체크섬 파일도 함께 받으세요.

| 받은 파일 | 대상 환경 | 실행 PC에 필요한 것 |
| --- | --- | --- |
| `SHIM_Portable_1.12.2_windows-x64.zip` | Windows x64 | 쓰기 가능한 폴더. Python 3.12.16 런타임 동봉 |
| `SHIM_Docker_1.12.2_linux-amd64.tar` | Linux amd64 컨테이너를 실행하는 PC·NAS | 설치된 Docker. ARM NAS 지원을 뜻하지 않음 |

이 패키지의 실행에는 인터넷 연결이나 별도 Python·Node.js 설치가 필요하지 않습니다. 소스에서 패키지를 만드는 준비사항은 아래 개발·빌드 안내에서 다룹니다. 패키지별 소스·아카이브 검사 결과는 함께 제공하는 manifest에 기록합니다. 제작 환경에서는 실제 Docker·Windows 기동을 검증하지 못했습니다. [릴리스 검증 범위](docs/2-1_운영_릴리즈_통합_산출물.md)를 확인하고 대상 장비에서 접속과 종료를 점검하세요.

### Windows CMD ZIP

1. ZIP을 쓰기 가능한 새 폴더에 **전체 압축 해제**합니다. `START_SHIM.cmd`, `START_SHIM_CONSOLE.cmd`, `runtime/`, `app/`을 함께 유지하세요.
2. 신규 암호화 DB라면 첫 실행 전에 아래 절차로 키를 준비합니다. 기존 DB를 옮기는 경우에는 기존 `data/`와 키·설정을 보존합니다.
3. `START_SHIM.cmd`로 시작합니다. 최초 실행 시 패키지 루트에 `data/`가 생성됩니다. 오류를 콘솔에서 확인하려면 `START_SHIM_CONSOLE.cmd`를 실행합니다. 이 파일은 `--foreground` 모드로 동작합니다.
4. 종료할 때는 트레이의 SHIM 아이콘에서 **종료**를 선택합니다. 콘솔 모드는 `Ctrl+C`로 종료합니다.

신규 암호화 설치에서는 패키지 루트의 PowerShell에서 다음 명령으로 키를 생성하고 안전하게 보관합니다. **기존 DB의 키를 새로 생성하거나 덮어쓰는 용도로 사용하지 마세요.**

```powershell
.\runtime\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

보관한 키를 같은 PowerShell 세션에 입력하고 시작합니다. 이후 실행에서도 같은 키를 설정해야 합니다. 이 방식으로 시작한 뒤에는 환경변수 없이 CMD를 더블 클릭해 재시작하지 마세요.

```powershell
$env:SHIM_SECRET_KEY = Read-Host "보관한 SHIM_SECRET_KEY"
$env:SHIM_TIMEZONE = "Asia/Seoul"
.\START_SHIM.cmd
```

백그라운드 로그는 `data/log/shim-master.log`와 `data/log/shim-app.log`에 있습니다. 이 CMD ZIP은 아래의 PyInstaller EXE 패키지와 다른 형태입니다.

### Docker TAR

Docker가 설치된 대상 장비에서 이미지를 불러옵니다.

```sh
docker load -i SHIM_Docker_1.12.2_linux-amd64.tar
```

아래 실행 예시는 **새 DB용**입니다. 기존 운영 DB는 기존 볼륨·키·모드를 보존하고 [백업·복구 가이드](docs/1-2_백업_복구_유지보수_가이드.md)에 따라 이전하세요. 같은 SQLite 데이터 볼륨을 두 컨테이너에서 동시에 사용하지 마세요.

신규 암호화 DB의 키는 불러온 이미지로 생성할 수 있습니다. 호스트에 Python을 설치할 필요가 없습니다.

```sh
docker run --rm --network none --entrypoint python shim:1.12.2 -c "import secrets; print(secrets.token_urlsafe(48))"
```

생성된 키를 안전하게 보관한 뒤 현재 폴더에 `.env`를 만듭니다. 아래의 안내 문구를 실제 키로 바꾸세요. `.env`를 저장소에 커밋하지 마세요.

```dotenv
SHIM_SECRET_KEY=생성하여_보관한_키로_교체
SHIM_TIMEZONE=Asia/Seoul
SHIM_SECURE_COOKIE=false
```

새 전용 볼륨 `shim-data`에 데이터를 보관하며 실행합니다. 이미 같은 이름의 볼륨이 있다면 내용과 키를 확인한 뒤 사용하세요.

```sh
docker run -d --name shim --env-file .env -p 8000:8000 -v shim-data:/app/var/data --restart unless-stopped shim:1.12.2
```

DB는 볼륨 안의 `shim_internal.db`에 저장됩니다. 시작 상태는 `docker logs shim`으로 확인하고, 종료는 `docker stop shim`으로 합니다. 신규 암호화 설치에서는 로그의 `SECURE ENCRYPTION mode (PII Protected)` 표시를 확인하세요.

### 최초 접속

1. Docker는 `http://localhost:8000`에 접속합니다. 포터블은 안내된 주소를 사용합니다. 기본 8000번이 사용 중이면 8001번 등으로 바뀔 수 있습니다.
2. 초기 관리자 `admin` / `0000`으로 로그인합니다.
3. 화면의 **비밀번호 변경** 메뉴에서 관리자 비밀번호를 즉시 변경합니다.
4. 회사·팀과 사용자, 연도별 할당량, 근무시간, 공유·승인 정책을 현장에 맞게 설정합니다. 공휴일도 확인하세요.

`http://localhost:8000/health`의 정상 응답은 `{"status":"ok"}`입니다. 포트가 바뀌면 실제 포트로 확인하세요. `/docs`, `/redoc`, `/openapi.json`은 기본 비공개입니다.

모바일은 같은 신뢰 가능한 사내망·Wi-Fi에서 `http://<서버 PC IPv4>:<실행 포트>`로 접속합니다. Windows 서버 주소는 `ipconfig`로 확인할 수 있습니다. 휴대폰의 `localhost`는 서버 PC를 가리키지 않습니다. 연결되지 않으면 방화벽에서 해당 TCP 포트를 신뢰 가능한 사내 네트워크에 허용했는지 확인하세요.

### 테스트 데이터가 필요한 경우

두 패키지에 `seed_test_data.py`가 동봉되어 있습니다. 앱을 한 번 정상 기동하여 DB를 초기화한 뒤 **테스트용 DB에만 수동으로 한 번** 실행하세요. 샘플 데이터는 앱 시작 때 자동 입력되지 않습니다. 반복 실행하면 기록이 추가될 수 있고, `--reset`은 데이터를 삭제하므로 아래 명령에 붙이지 마세요.

Docker에서는 실제 컨테이너 이름을 사용합니다. 위 예시의 이름은 `shim`입니다.

```sh
docker exec shim python /app/tools/scripts/seed_test_data.py
```

Windows CMD ZIP은 패키지 루트의 PowerShell에서 앱과 같은 데이터 경로를 명시합니다. 암호화 DB라면 앞서 설정한 것과 동일한 `SHIM_SECRET_KEY`도 이 세션에 있어야 합니다.

```powershell
$env:SHIM_DATA_DIR = Join-Path (Get-Location) 'data'
.\runtime\python.exe .\app\tools\scripts\seed_test_data.py
```

## 개발·빌드 준비

기술 구성은 FastAPI, SQLAlchemy, SQLite, Jinja2, Tailwind CSS v4입니다. 검증에 사용한 환경은 Python 3.12와 Node.js 22입니다. 잠금 파일의 `@tailwindcss/oxide`가 요구하는 Node.js 최소 버전은 20입니다. 다른 Python 버전 전체의 호환성을 검증했다는 뜻은 아닙니다.

소스의 `pip`, `npm`, Docker 빌드는 의존성·기본 이미지 다운로드를 위해 인터넷 또는 미리 준비한 wheel·npm 캐시·이미지가 필요합니다. 제공 Dockerfile은 기본적으로 온라인 설치를 사용합니다.

Windows PowerShell의 저장소 루트에서 가상환경을 준비한 뒤 실행합니다. 루트 `.env`는 `npm run dev`가 자동으로 읽지 않으므로, 새 암호화 개발 DB라면 실행 전에 세션에 키를 설정하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm ci
npm run dev
```

개발 서버는 기본 `http://localhost:9090`에서 시작하며 포트가 사용 중이면 다음 포트를 선택합니다. 기본 데이터 위치는 `var/data/shim_internal.db`이고 `SHIM_DATA_DIR`로 바꿀 수 있습니다.

Docker 소스 빌드 전에는 CSS를 생성합니다.

```powershell
npm run build:css
docker build -f infra/docker/Dockerfile -t shim:1.12.2 .
```

Compose를 사용할 때는 [환경변수 예제](infra/docker/.env.example)를 루트 `.env`로 복사해 키와 경로를 설정한 뒤 `docker compose --env-file .env -f infra/docker/docker-compose.yml up -d`로 실행합니다. 예제의 `SHIM_DATA_DIR=../../var/data`는 Compose 파일 기준으로 저장소의 `var/data`를 가리킵니다.

별도 Windows EXE 패키지는 `powershell -ExecutionPolicy Bypass -File .\portable\build_portable.ps1`로 만듭니다. 생성되는 `dist/SHIM_Portable_v<버전>_<빌드시각>.zip`은 `SHIM_Portable.exe`와 `_internal`을 함께 배포하는 PyInstaller 형태입니다. EXE나 `python.exe` 하나만 복사해서는 실행할 수 없습니다. [포터블 빌드 안내](portable/README.md)와 [EXE 패키지 사용자 안내](portable/README_PORTABLE.md)를 참고하세요.

## 운영·개발 문서

- [OpenWiki 빠른 시작](openwiki/quickstart.md): 구조, 도메인, 작업 흐름을 읽는 순서
- [초심자 구동 가이드](docs/1-1_초심자_구동_가이드.md), [백업·복구 가이드](docs/1-2_백업_복구_유지보수_가이드.md): 설치와 데이터 보존
- [연차 관리 도메인](openwiki/domain/leave-management.md), [관리자 워크플로우](openwiki/workflows/admin.md): 연도별 할당, 결재, 공휴일, 감사 관리
- [테스트 및 검증](openwiki/testing.md): 개발 의존성 준비, `npm test`, `npm run test:release`와 변경별 검사
- [릴리스 스크립트](tools/scripts/release.ps1): 버전 동기화와 검사·빌드 절차. 정합성만 확인하려면 `python tools/scripts/verify_version_sync.py`를 실행합니다.
- [릴리스 검증 기록](docs/2-1_운영_릴리즈_통합_산출물.md), [변경 이력](docs/1-4_작업_로그.md), [남은 개선 과제](docs/3-1_향후_개선계획.md)
- [전체 문서 인덱스](docs/0_문서_인덱스.md), [상세 설계서](docs/4-1_SHIM_프로젝트_설계서.md)

## 기여하기

버그 제보와 기능 제안은 Issue로, 수정은 Pull Request로 제출하세요. 기존 코드 스타일과 [테스트 지침](openwiki/testing.md)을 따릅니다.

## 라이선스

[MIT License](LICENSE). Copyright (c) 2026 SHIM Authors.
