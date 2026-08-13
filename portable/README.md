# Portable 디렉토리 가이드 (Developer & Maintainer)

이 디렉토리는 SHIM 시스템을 Docker 없이 무설치 실행 가능하도록 빌드하고 관리하는 데 필요한 자산들을 포함합니다.

## 📂 파일 구성 및 역할

| 파일명 | 역할 | 상세 설명 |
|:--- |:--- |:--- |
| **`build_portable.ps1`** | **빌드 스크립트** | Tailwind CSS 빌드, 버전 동기화, PyInstaller 패키징 및 최종 산출물 구성을 수행하는 PowerShell 스크립트입니다. |
| **`README_PORTABLE.md`** | **배포용 가이드** | 최종 사용자(폐쇄망 운영자)에게 전달되는 문서입니다. 설치, 실행, 백업 방법이 기술되어 있습니다. |
| **`stop_portable.bat`** | **비상 강제 종료 파일** | 트레이 종료가 동작하지 않을 때만 프로세스를 강제 종료합니다. 정상 종료 절차를 우회하므로 일상적인 종료에는 사용하지 않습니다. |
| **`shim_portable.py`** | **실행 진입점** | PyInstaller가 바이너리를 만들 때 참조하는 Python 진입점입니다. 런타임 경로 환경 변수 설정, 시스템 트레이 아이콘 스레드 구동, 포트 탐색 로직을 포함합니다. |

---

## 🛠️ 빌드 및 관리 가이드

### 1. 포터블 빌드 원리
본 프로젝트는 **PyInstaller**로 Python 인터프리터와 소스 코드, 정적 자산(Templates, Static)을 로컬 임시 폴더에 묶고, 패키징 검증을 거친 결과를 `dist/SHIM_Portable_v<버전>_<빌드시각>.zip` 한 파일로 게시합니다.
- 빌드 과정에서 `src/templates`와 `src/static`은 ZIP의 `_internal` 런타임 패키지에 포함됩니다.
- 운영 데이터는 번들링된 바이너리 옆의 `data/` 폴더에 생성 및 유지됩니다.
- IANA 시간대 데이터(`tzdata`)는 `--collect-data tzdata`로 포함되어 폐쇄망에서도 `SHIM_TIMEZONE`을 해석합니다.

### 2. 빌드 스크립트 (`build_portable.ps1`) 수정 시 주의사항
- **의존성**: 스크립트가 `requirements.txt`와 `pyinstaller`를 설치하므로 인터넷 연결 또는 준비된 패키지 캐시가 필요합니다.
- **버전 동기화**: PyInstaller 실행 전에 `release.ps1`을 호출하여 `package.json`, `package-lock.json`, `src/app/constants.py`, Docker 기본 이미지 태그와 배포 문서의 버전을 맞춥니다.
- **자산 복사**: 빌드가 완료된 후 `stop_portable.bat`와 `README_PORTABLE.md`를 로컬 스테이징 패키지에 포함하고, 운영 DB·비밀키 없이 ZIP으로 게시합니다.
- **검증 범위**: ZIP 구성·금지 파일·SHA-256은 검사하지만 전체 회귀 테스트와 포터블 실기동은 별도로 수행해야 합니다. 모바일 UI 변경 시에는 `python tools/scripts/test_mobile_ui.py`도 빌드 전에 통과시킵니다.

### 3. 포터블 빌드 실행 방법

*이 작업은 인터넷이 가능하고 개발 환경이 세팅된 Local PC에서 수행합니다.*
#### 사전 요구사항
- **Python**: 3.11 이상

- **Node.js**: 18 이상 (Tailwind CSS 빌드용)
- **의존성**: 프로젝트 루트에서 `npm install` 완료 상태
#### 빌드 실행 명령어
정식 배포 전에는 버전 동기화와 전체 검사를 먼저 통과시킨 뒤 포터블 패키지를 만듭니다.
```powershell
$version = (Get-Content .\package.json -Raw | ConvertFrom-Json).version
.\tools\scripts\release.ps1 -Version $version -RunChecks
powershell -ExecutionPolicy Bypass -File .\portable\build_portable.ps1
```

포터블 빌드 스크립트는 CSS 생성, 버전 재확인, PyInstaller 패키징과 ZIP 검증을 수행합니다. 최종 배포 전에는 생성된 EXE를 실제 기동하여 `/health`의 HTTP 200, 기본 OpenAPI 세 경로의 HTTP 404, 주요 화면의 보안 헤더와 정상 종료를 확인하고 버전 표시도 확인하십시오.
- **결과물**: `dist/SHIM_Portable_v<버전>_<빌드시각>.zip`이 생성됩니다. 기존 산출물은 삭제하거나 덮어쓰지 않습니다.
### 4. 배포 주의사항

- 최종 사용자에게는 최신 버전별 ZIP 한 파일을 전달하고, 대상 PC에서 전체 압축을 풀도록 안내합니다.
- `.exe` 파일만 단독으로 전달할 경우, 내부 자산과 런타임 라이브러리가 누락되어 실행되지 않습니다.

---

### 5. 무설치 배포용 UI 색상 및 스타일 관리 정책
- **폐쇄망 제로 컨디션 최적화**: 포터블 실행 환경은 외부 인터넷망이 완전히 차단되어 있으므로 어떠한 외부 CDN이나 웹 API로부터 색상 및 스타일 리소스를 가져오지 않습니다.
- **회사/팀 배지 색상 격리**: 회사명과 팀명을 고대비 HSL 색상으로 표현하는 로직(`string_to_badge_style`)이 내장되어 있습니다. 회사는 0~140도(웜톤/녹색계열), 팀은 180~340도(쿨톤 계열)로 분리하여 캘린더와 타임라인의 시각적 구분을 보조합니다.
- **반응형 패키징 계약**: 모바일과 PC는 같은 템플릿·정적 자산을 사용하며 1024px을 기준으로 필요한 월 JSON 또는 PC 부분 HTML을 한 번만 지연 조회합니다. 사용자 에이전트 분기, 서비스 워커, 외부 UI 프레임워크는 추가하지 않습니다.
- **모바일 UI 빌드 게이트**: 템플릿 또는 Tailwind 클래스 변경 후 `npm run build:css`와 `python tools/scripts/test_mobile_ui.py`를 실행한 다음 포터블 패키지를 생성합니다. `src/templates/partials`와 생성된 `src/static/css/tailwind.css`가 `_internal`에 포함되는지 확인합니다.
- **패널 계층 계약**: 주요 외곽 패널은 `dense-line`, 표·차트·달력 셀·내부 목록은 `dense-grid`를 사용합니다. 포터블 빌드 전 `python tools/scripts/test_ui_style.py`로 토큰·산출물·상태 의미색 보존을 확인합니다.
- **운영 범위**: `STAFF`, `TEAM_LEAD`, `PM`의 신청·조회·취소와 권한별 팀 일정·결재 흐름은 모바일을 지원합니다. `ADMIN` 모바일은 조회 수준만 보장하고 등록·수정·삭제는 PC에서 처리합니다.
- **실기기 확인 기준**: 세로 `320×568`, `360×800`, `390×844`, `412×915`, `425px` 폭과 가로 화면에서 가로 넘침, 44×44px 터치 영역, 긴 문자열 줄바꿈, 모달 버튼 높이와 역할별 메뉴 노출을 확인합니다.

---
## 🔗 관련 문서
- **최종 사용자 가이드**: [README_PORTABLE.md](README_PORTABLE.md)
- **메인 README**: [저장소 루트 README.md](../README.md)
- **시스템 설계서**: [docs/4-1_SHIM_프로젝트_설계서.md](../docs/4-1_SHIM_프로젝트_설계서.md)
