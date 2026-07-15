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
본 프로젝트는 **PyInstaller**로 Python 인터프리터와 소스 코드, 정적 자산(Templates, Static)을 로컬 임시 폴더에 묶고, 검증된 결과를 `dist/SHIM_Portable_v<버전>_<빌드시각>.zip` 한 파일로 게시합니다.
- 빌드 과정에서 `src/templates`와 `src/static`은 바이너리 내부로 번들링됩니다.
- 운영 데이터는 번들링된 바이너리 옆의 `data/` 폴더에 생성 및 유지됩니다.
- IANA 시간대 데이터(`tzdata`)는 `--collect-data tzdata`로 포함되어 폐쇄망에서도 `SHIM_TIMEZONE`을 해석합니다.

### 2. 빌드 스크립트 (`build_portable.ps1`) 수정 시 주의사항
- **의존성**: 빌드 전 `requirements.txt`와 `pyinstaller`가 설치되어 있어야 합니다.
- **버전 동기화**: 빌드 직전에 `release.ps1`을 호출하여 `package.json`, `package-lock.json`, `src/app/constants.py`, Docker 기본 이미지 태그와 배포 문서의 버전이 일치하도록 보장합니다.
- **자산 복사**: 빌드가 완료된 후 `stop_portable.bat`와 `README_PORTABLE.md`를 로컬 스테이징 패키지에 포함하고, 운영 DB·비밀키 없이 ZIP으로 게시합니다.

### 3. 포터블 빌드 실행 방법
*이 작업은 인터넷이 가능하고 개발 환경이 세팅된 Local PC에서 수행합니다.*

#### 사전 요구사항
- **Python**: 3.11 이상
- **Node.js**: 18 이상 (Tailwind CSS 빌드용)
- **의존성**: 프로젝트 루트에서 `npm install` 및 `pip install -r requirements.txt` 완료 상태

#### 빌드 실행 명령어
프로젝트 루트에서 다음 PowerShell 스크립트를 실행합니다. 이 스크립트는 CSS 빌드, 버전 동기화, 바이너리 패키징을 일괄 처리합니다.
```powershell
powershell -ExecutionPolicy Bypass -File .\portable\build_portable.ps1
```
- **결과물**: `dist/SHIM_Portable_v<버전>_<빌드시각>.zip`이 생성됩니다. 기존 산출물은 삭제하거나 덮어쓰지 않습니다.

### 4. 배포 주의사항
- 최종 사용자에게는 최신 버전별 ZIP 한 파일을 전달하고, 대상 PC에서 전체 압축을 풀도록 안내합니다.
- `.exe` 파일만 단독으로 전달할 경우, 내부 자산과 런타임 라이브러리가 누락되어 실행되지 않습니다.

---

### 5. 무설치 배포용 UI 색상 및 스타일 관리 정책
- **폐쇄망 제로 컨디션 최적화**: 포터블 실행 환경은 외부 인터넷망이 완전히 차단되어 있으므로 어떠한 외부 CDN이나 웹 API로부터 색상 및 스타일 리소스를 가져오지 않습니다.
- **회사/팀 배지 색상 격리**: 회사명과 팀명을 고대비 HSL 색상으로 표현하는 로직(`string_to_badge_style`)이 내장되어 있습니다. 회사는 0~140도(웜톤/녹색계열), 팀은 180~340도(쿨톤 계열)로 고정 분리하여, 포터블 구동 중 여러 회사가 참여한 캘린더나 타임라인 뷰를 조회할 때 색상만으로도 완벽한 구분이 가능합니다.

---

## 🔗 관련 문서
- **최종 사용자 가이드**: [README_PORTABLE.md](README_PORTABLE.md)
- **메인 README**: [저장소 루트 README.md](../README.md)
- **시스템 설계서**: [docs/4-1_SHIM_프로젝트_설계서.md](../docs/4-1_SHIM_프로젝트_설계서.md)
