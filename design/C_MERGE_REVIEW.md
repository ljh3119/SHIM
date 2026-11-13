# C BASELINE 통합 검토

## 병합 기준과 결정

`main e6e831b`의 v1.11.0 기능 위에 `design/braun-linear-exploration cd84c08`의 두 커밋을 통합했다. 구현은 AGY Flash3.8, 독립 검토는 AGY Argon이 담당한다. 원래 main과 디자인 브랜치는 보존하며 최종 main 반영은 PR 검토 이후에 진행한다.

- 반차 시간 옵션은 main의 두 컨텍스트 생성 경로를 유지했다. 대시보드는 C 외형과 저장된 부재 시간 라벨을 결합했다.
- 간편 신청 패널은 C 외형과 날짜 입력 즉시 갱신을 결합했다. 공통 IIFE는 한 번만 로드하며 base의 중복 신청 핸들러는 제거했다.
- 개인·팀 달력은 C 레이아웃에 main의 모바일 초기화·동기화를 유지했다. 날짜 복원으로 기간 선택을 자동 활성화하지 않는다.
- 기간 신청 전일 제한과 반차 비활성화, 단일 날짜 복귀, 토글 OFF 시 날짜·사유 보존을 유지했다.
- 설정 GET, 자동 백업, 비상 초기화, 휴일 생성, 사용자 시간·브랜딩 설정과 권한 정책은 main 구현을 유지했다. 버전과 의존성은 변경하지 않았다.
- 최초 아르곤 검토에서 날짜 그리드의 중복 래퍼를 발견했다. 중복 태그 두 줄을 제거한 뒤 개인·팀 달력의 1024·1440px 4개 사례에서 시작일·종료일의 실제 좌표와 직계 자식 2개를 확인하고 관련 UI·모바일 검사를 다시 통과했다.
- 기능 검사는 유지하고 반경·토큰·장식 제거에 해당하는 시각적 기대값만 바꿨다. CSS는 통합된 소스에서 다시 생성했다.

## 실행 검증

운영 DB와 키를 사용하지 않고 새 임시 DB와 직원·팀장·PM·관리자 계정으로 실행했다. 이전 디자인 브랜치의 검사 기록과 이번 결과를 구분한다.

| 검사 | 결과 |
| --- | --- |
| CSS 빌드 | `npm run build:css` 성공, 기존 lockfile 유지 |
| Python 컴파일·버전 | 성공, v1.11.0 정합성 확인 |
| Smoke | 17개 스크립트 종료 코드 0 |
| Release 추가 검사 | 정상 종료와 메모리 1,000회 검사 종료 코드 0. 메모리 API RSS +6.56MB, Python heap +0.27MB. 중복 실행 검사는 Linux에서 종료 코드 1이며 Win32 Named Mutex 검증이 필요한 환경 한계로 구분 |
| 화면 크기 | 11개 화면 × 360·390·768·1023·1024·1440px, 66개 사례 통과. 문서 전체 가로 넘침, 의도하지 않은 HTTP 실패·콘솔 예외·외부 자산 요청 없음 |
| 간편 신청 | 30·60·120·240분 정책의 기존 23개 브라우저 사례 통과. 기간 전일 제한·단일 날짜 복귀·직접선택 제한·토글·복원·resize 검증 |
| 기간 실제 저장 | 두 요청이 전일 6행으로 저장됨. 2026-12-22~24는 09:00~18:00·점심 제외 8시간, 2027-03-08~10은 08:30~17:30·점심 없음 9시간 |
| 승인·반려·취소 | PC 팀장 승인, 모바일 팀장 반려·직원 취소 후 DB 상태 확인. 직원 승인·관리자 API 접근과 타인 취소는 403 |
| 조작 상태 | 모달 Escape·포커스 복귀, 키보드 2px focus-visible, 주요 모바일 날짜·제출·월 이동 조작 높이 44px 확인 |
| 오류·긴 입력 | 실제 모바일 로딩 → 의도적 HTTP 500 → 재시도 성공 확인. 긴 사유와 HTML 문자를 입력해 텍스트로 유지되고 가로 넘침이 없음을 확인. reduced-motion과 200% 확대 화면도 검사 |
| 달력·차트 | 선택·해제 색상 복원과 2px 반경 확인. Chart.js 두 차트의 Canvas 렌더링, RGB 데이터셋, OKLCH 격자색과 pointHitRadius 12 확인 |

기본 검사 재실행 명령:

```sh
npm ci
npm run build:css
python -m compileall -q src/app tools/scripts
python tools/scripts/verify_version_sync.py
python tools/scripts/run_tests.py smoke
git diff --cached --check
```

실브라우저는 Playwright Chromium으로 실행했다. 이 작업 환경의 검사기와 집계 결과는 `/tmp/shim-browser-check/verify-c-*.cjs`, `c-*-results.json`, `c-period-after-root.json`에 있다. 이 임시 경로는 다른 환경에 설치되는 프로젝트 테스트가 아니다. 같은 시나리오를 재현할 때는 별도 DB와 계정을 생성하고 브라우저·폰트를 준비해야 한다.

## 같은 fixture의 전후 화면

브라우저 캐시를 비우고 같은 초기 데이터 사본으로 캡처했다. 이미지의 계정과 데이터는 검증 fixture이며 실제 사용자 데이터가 아니다. 한글 폰트는 검증 환경에만 추가했고 앱의 외부 요청이나 의존성을 추가하지 않았다.

| 화면 | main | C 통합본 |
| --- | --- | --- |
| 개인 달력 PC 1440px | [변경 전](review-c-merge/before-calendar-desktop.png) | [변경 후](review-c-merge/after-calendar-desktop.png) |
| 간편 신청 모바일 390px | [변경 전](review-c-merge/before-calendar-mobile.png) | [변경 후](review-c-merge/after-calendar-mobile.png) |
| 관리자 대시보드 PC 1440px | [변경 전](review-c-merge/before-dashboard-desktop.png) | [변경 후](review-c-merge/after-dashboard-desktop.png) |

## 독립 검토 최종 판정

AGY Argon은 중복 래퍼 수정 후 소스·스테이징 diff·4개 브라우저 좌표 사례와 최종 비교 이미지를 확인하고 UI·모바일 표적 검사를 독립 재실행하여 최종 PASS로 판정했다.

## 환경 한계

Windows 전용 포터블·트레이 검사는 Linux 결과로 대체하지 않는다. 실제 Windows, 다른 브라우저 엔진과 Docker·포터블 산출물 검증은 이번 기록에 포함하지 않는다. 기존 시험 TAR를 이번 C 통합본 산출물로 취급하지 않는다.
