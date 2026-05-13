# SHIM Portable (폐쇄망 PC 무설치 실행)

이 폴더는 Docker 설치가 불가능한 폐쇄망 Windows PC에서 SHIM를 실행하기 위한 전용 산출물입니다.

## 0) 빌드 전 준비(개발 PC)

- Python 3.11 이상
- Node.js + npm
- 프로젝트 루트에서 `npm install` 1회 수행

## 1) 빌드(인터넷 가능한 개발 PC)

`build_portable.ps1`는 Tailwind 빌드 직후 `package.json`의 버전으로 `tools/scripts/release.ps1`을 한 번 호출해 `main.py`·`base.html`·Compose 기본 태그와 동기화합니다(묶는 실행본이 항상 패키지 버전과 맞도록).

프로젝트 루트에서 아래 실행:

```powershell
powershell -ExecutionPolicy Bypass -File .\portable\build_portable.ps1
```

완료되면 `dist/SHIM_Portable` 폴더가 생성됩니다.

생성 산출물:

- `dist/SHIM_Portable/SHIM_Portable.exe`
- `dist/SHIM_Portable/run_portable.bat`
- `dist/SHIM_Portable/stop_portable.bat`
- `dist/SHIM_Portable/README_PORTABLE.md`
- `dist/SHIM_Portable/data/shim_internal.db` (초기 DB)

최신 반영 사항(2026-05-13, v1.3.1):

- **Tailwind CSS v4 통합 및 엔진 업그레이드**: Tailwind CSS v4.x 도입 및 `@tailwindcss/cli` 기반 빌드 시스템 전환
- **의존성 최신화**: `tailwindcss`, `@tailwindcss/cli` 최신 버전(v4.3.0) 반영
- **결재 권한 확장**: `PM`(프로젝트 매니저) 역할에 결재 권한 부여 및 승인/반려 로직 고도화
- **사용자 UI 개선**: 전용 결재 관리 페이지 신설 및 대시보드 메뉴 분리(결재·팀 캘린더·히스토리)
- **로직 안정화**: 반려된 연차 신청 건의 시간대 점유 해제 로직 반영
- 앱·템플릿·Docker compose 기본 태그와 동기화된 `1.3.1` 반영(빌드 시 `package.json` 버전과 동일)
- (이전 v1.3.0) 역할 기반 권한 체계(RBAC) 도입 및 팀장 결재 워크플로우 반영
- 폐쇄망 기준: Tailwind CDN/Google Fonts 없음, 로컬 `tailwind.css` 사용 유지
- 포터블 빌드(2026-05-13): `build_portable.ps1`로 재빌드 완료, `dist/SHIM_Portable` 갱신.

## 2) 전달(폐쇄망 PC)

`dist/SHIM_Portable` 폴더를 **통째로** 복사합니다.

- `SHIM_Portable.exe`만 단독 복사하면 실행되지 않습니다.
- 반드시 `_internal`, `data`, `run_portable.bat`, `stop_portable.bat`를 함께 전달하세요.

## 3) 실행(폐쇄망 PC)

- `run_portable.bat` 더블클릭 실행
  - 최초 1회는 `SHIM_SECRET_KEY`를 입력받아 `data/secret.key`로 저장합니다.
  - 2회차부터는 저장된 키를 자동으로 사용합니다.
  - 실행 시 `Port [default 8000]:`가 표시됩니다.
  - 그냥 엔터를 누르면 `8000`으로 실행됩니다.
  - 예: `8010` 입력 후 엔터 → `8010` 포트로 실행
- 선택한 포트가 다른 프로그램에서 이미 사용 중이면 실행이 중단되고 안내 메시지가 표시됩니다.
- 명령줄 직접 실행도 가능: `run_portable.bat 8080`
- 브라우저 접속: `http://localhost:포트번호` (기본 `8000`)
- 관리자 초기 계정: `admin / 0000`
- 운영 인수 후 관리자 비밀번호를 즉시 변경하세요.
- 점검 URL(권장): `http://localhost:포트번호/docs` (200 응답이면 서버 정상 기동)

## 4) 종료

- `stop_portable.bat` 실행
- `SHIM_Portable.exe` 프로세스를 종료합니다.
- 업데이트/재실행 전에는 먼저 `stop_portable.bat`를 실행하세요.

## 5) 데이터 백업/복원

- DB 파일: `data/shim_internal.db`(기본). 고급: 실행 전에 환경 변수 `SHIM_DATA_DIR`을 지정하면 해당 폴더에 동일 파일명으로 저장됨(`src/app/database.py` 참고)
- 백업: 해당 파일을 별도 저장소에 복사
- 복원: 앱 종료 후 백업 파일로 덮어쓰기

## 6) 주의사항

- 포터블 실행 대상 PC에는 **Python/Node.js/Docker 설치가 필요 없습니다.**
- 전제 조건: Windows 64bit 환경에서 폴더 쓰기 권한이 있어야 합니다.
- `data/secret.key`는 JWT 서명키 파일이므로 외부 공유 금지, 접근 권한 최소화를 권장합니다.
- 보안 솔루션(백신/실행제한 정책)이 `SHIM_Portable.exe` 실행을 차단할 수 있습니다.
- 포트 충돌(기본 8000)이 있으면 `run_portable.bat 8010`처럼 다른 포트를 사용하세요.
- NAS와 PC를 동시에 운영하면 데이터가 분기됩니다.
- 비상 운영 시 최신 DB를 기준으로 단일 원본을 유지하세요.
- 실행은 `SHIM_Portable.exe` 직접 실행보다 `run_portable.bat` 사용을 권장합니다(포트 선택/환경 일관성 확보).

## 7) NAS <-> PC 비상 전환 절차 (DB 동기화)

동시에 두 곳을 운영하지 말고, 항상 "단일 원본 DB"만 유지합니다.

### 7-1. NAS -> PC 비상 전환

1. NAS SHIM를 중지합니다.
2. NAS의 최신 `shim_internal.db`를 백업/복사합니다.
3. 폐쇄망 PC의 `SHIM_Portable\data\shim_internal.db`에 덮어씁니다.
4. PC에서 `run_portable.bat` 실행 후 정상 동작 확인합니다.

체크:

- 로그인 가능 여부
- 최근 신청 데이터 존재 여부
- 관리자 공휴일/캘린더 화면 정상 여부

### 7-2. PC -> NAS 복귀 전환

1. PC SHIM를 `stop_portable.bat`로 종료합니다.
2. PC의 최신 `SHIM_Portable\data\shim_internal.db`를 복사합니다.
3. NAS의 DB 파일을 백업한 뒤, 복사본으로 교체합니다.
4. NAS SHIM를 재시작하고 기능 점검합니다.

### 7-3. 권장 운영 규칙

- 전환 시각과 담당자를 기록합니다.
- 전환 전/후 DB 파일명을 타임스탬프로 보관합니다.
- 최소 월 1회 복구 리허설을 수행합니다.
