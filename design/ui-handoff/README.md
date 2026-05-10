# Dense UI 정적 시안 (`design/ui-handoff`)

**위치**: 저장소 루트 `design/ui-handoff/` (런타임·빌드에 포함되지 않음)

v1.2.0에서 1차 Dense는 **`src/templates`**·**`src/static/css/app.css`**에 반영되었습니다. 이 폴더는 **브라우저용 목업·디렉팅**만 보관합니다.

- **백로그**: `docs/3-1_향후_개선계획.md`에만 적습니다.
- **구현 근거**: `docs/4-1_edu_LAMS_프로젝트_설계서.md`, 완료 증적 `docs/2-1_…`

## 빠른 진입

| 순서 | 내용 |
|:---:|:---|
| 0 | 브라우저 목차: **`galleries/samples-hub.html`** |
| 1 | 디렉팅: **`directing/admin-dashboard-design-direction.md`** |
| 2 | 토큰 미리보기: `samples/reference/design-tokens-preview.html` |
| 3 | 본편 시안: `samples/admin/dense-operations-console.html`, `samples/user/dense-operations-console.html` |

## 폴더

| 경로 | 역할 |
|:---|:---|
| `directing/` | Markdown 디렉팅 (**기준**) |
| `samples/` | 정적 HTML · CDN 없음 · UTF-8 |
| `samples/reference/` | `dense-tokens.css`(시안 팔레트; 제품과 맞춤 시 `src/static/css/app.css` 주석 참고) |
| `galleries/` | `samples-hub.html` |
| `legacy/_deprecated/` | 구 갤러리·실험 시안 (**참고만**) |

## 신규 시안 규칙

1. 파일명: `dense-*.html` 또는 `*-shell.html` (공백·한글 금지)  
2. `reference/dense-tokens.css` 링크 권장, 페이지별만 `<style>`  
3. 파일 상단 주석: 목적 · 대응 `src/templates/...` · CDN 없음  
4. 반영은 항상 `src/templates/`에서 수행  

끝난 작업은 `docs/2-1`에, 새 과제는 `docs/3-1`에만 남깁니다.
