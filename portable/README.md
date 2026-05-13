# Portable 디렉토리 가이드 (Developer & Maintainer)

이 디렉토리는 SHIM 시스템을 Docker 없이 무설치 실행 가능하도록 빌드하고 관리하는 데 필요한 자산들을 포함합니다.

## 📂 파일 구성 및 역할

| 파일명 | 역할 | 상세 설명 |
|:--- |:--- |:--- |
| **`build_portable.ps1`** | **빌드 스크립트** | Tailwind CSS 빌드, 버전 동기화, PyInstaller 패키징 및 최종 산출물 구성을 수행하는 PowerShell 스크립트입니다. |
| **`README_PORTABLE.md`** | **배포용 가이드** | 최종 사용자(폐쇄망 운영자)에게 전달되는 문서입니다. 설치, 실행, 백업 방법이 기술되어 있습니다. |
| **`run_portable.bat`** | **실행 배치 파일** | 사용자가 포트 번호를 지정하여 시스템을 기동할 수 있게 돕는 래퍼 스크립트입니다. |
| **`stop_portable.bat`** | **종료 배치 파일** | 백그라운드에서 실행 중인 SHIM 프로세스를 안전하게 종료합니다. |
| **`shim_portable.py`** | **실행 진입점** | PyInstaller가 바이너리를 만들 때 참조하는 Python 진입점입니다. 런타임 경로 환경 변수 설정 로직을 포함합니다. |

---

## 🛠️ 빌드 및 관리 가이드

### 1. 포터블 빌드 원리
본 프로젝트는 **PyInstaller**를 사용하여 Python 인터프리터와 소스 코드, 정적 자산(Templates, Static)을 하나의 폴더(`dist/SHIM_Portable`)로 묶습니다.
- 빌드 과정에서 `src/templates`와 `src/static`은 바이너리 내부로 번들링됩니다.
- 운영 데이터는 번들링된 바이너리 옆의 `data/` 폴더에 생성 및 유지됩니다.

### 2. 빌드 스크립트 (`build_portable.ps1`) 수정 시 주의사항
- **의존성**: 빌드 전 `requirements.txt`와 `pyinstaller`가 설치되어 있어야 합니다.
- **버전 동기화**: 빌드 직전에 `release.ps1`을 호출하여 `main.py`와 `package.json`의 버전이 일치하도록 보장합니다.
- **자산 복사**: 빌드가 완료된 후 `run_portable.bat` 등 실행에 필요한 부속 파일들을 `dist` 폴더로 자동 복사합니다.

### 3. 배포 주의사항
- 최종 사용자에게는 `artifacts/dist/SHIM_Portable` 폴더 전체를 전달해야 합니다.
- `.exe` 파일만 단독으로 전달할 경우, 내부 자산과 런타임 라이브러리가 누락되어 실행되지 않습니다.

---

## 🔗 관련 문서
- **최종 사용자 가이드**: [README_PORTABLE.md](README_PORTABLE.md)
- **메인 README**: [저장소 루트 README.md](../README.md)
- **시스템 설계서**: [docs/4-1_SHIM_프로젝트_설계서.md](../docs/4-1_SHIM_프로젝트_설계서.md)
