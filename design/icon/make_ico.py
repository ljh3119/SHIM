"""
SHIM Portable 아이콘 생성 스크립트
===================================
SHIM_ICON.svg 디자인을 Pillow로 직접 렌더링하여 ICO 파일 생성.
SVG와 동일한 알파 합성(Alpha Compositing) 방식으로 3개 레이어를 겹쳐
교차 영역의 부드러운 색감을 정확히 재현합니다.

필요 패키지:
    pip install Pillow

사용법:
    python make_ico.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageChops
except ImportError:
    print("Pillow 패키지가 필요합니다: pip install Pillow")
    sys.exit(1)


# ── 설정 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SVG_INPUT = SCRIPT_DIR / "SHIM_ICON.svg"
PNG_OUTPUT = SCRIPT_DIR / "SHIM_ICON_256.png"
ICO_OUTPUT = SCRIPT_DIR / "SHIM_Portable.ico"

# 렌더링 해상도 (슈퍼샘플링 후 축소하여 안티앨리어싱 효과)
RENDER_SIZE = 1024  # 4x 슈퍼샘플링
FINAL_SIZE = 256

# Windows 표준 아이콘 해상도 트리
ICON_SIZES = [
    (256, 256),
    (128, 128),
    (64, 64),
    (48, 48),
    (32, 32),
    (16, 16),
]

# ── 색상 정의 (SVG 원본 기준) ─────────────────────────
GREEN = (6, 118, 71)             # #067647
BLUE_LIGHT = (239, 248, 255)     # #eff8ff
BLUE_DARK = (23, 92, 211)        # #175cd3
INTERSECT_START = (23, 92, 211)  # #175cd3
INTERSECT_END = (6, 118, 71)     # #067647


# ── 헬퍼 함수 ────────────────────────────────────────

def create_d_mask(size: int, scale: float,
                  cx: float, cy: float, r: float,
                  rect: tuple[float, float, float, float]) -> Image.Image:
    """
    D자형 마스크 생성 (원 + 직사각형).
    SVG의 path를 원+직사각형 조합으로 근사합니다.
    반환: 8bit grayscale (L) 이미지 (0=투명, 255=불투명)
    """
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    # 원 (Pillow ellipse는 내장 안티앨리어싱 제공)
    draw.ellipse(
        [
            int((cx - r) * scale), int((cy - r) * scale),
            int((cx + r) * scale), int((cy + r) * scale),
        ],
        fill=255,
    )

    # 직사각형
    draw.rectangle(
        [
            int(rect[0] * scale), int(rect[1] * scale),
            int(rect[2] * scale), int(rect[3] * scale),
        ],
        fill=255,
    )

    return mask


def create_diagonal_gradient(size: int, c1: tuple, c2: tuple) -> Image.Image:
    """
    대각선 그래디언트 (좌상→우하) 생성.
    2×2 픽셀을 Pillow 보간으로 확대하여 부드러운 그래디언트를 효율적으로 생성.
    """
    mid = tuple((a + b) // 2 for a, b in zip(c1, c2))

    tiny = Image.new("RGB", (2, 2))
    tiny.putpixel((0, 0), c1)   # 좌상: 시작색
    tiny.putpixel((1, 0), mid)  # 우상: 중간색
    tiny.putpixel((0, 1), mid)  # 좌하: 중간색
    tiny.putpixel((1, 1), c2)   # 우하: 끝색

    return tiny.resize((size, size), Image.BILINEAR)


def apply_mask_with_opacity(color_img: Image.Image, mask: Image.Image,
                            opacity: float) -> Image.Image:
    """
    색상 이미지에 마스크와 투명도를 적용하여 RGBA 레이어를 생성합니다.
    Alpha = mask_value × opacity
    """
    alpha = mask.point(lambda p: int(p * opacity))
    layer = color_img.convert("RGBA")
    layer.putalpha(alpha)
    return layer


# ── 메인 렌더링 ──────────────────────────────────────

def render_shim_icon(size: int) -> Image.Image:
    """
    SHIM 아이콘을 SVG와 동일한 알파 합성 방식으로 렌더링합니다.

    SVG 레이어 구조:
      1. 하단 녹색 D자 (fill=#067647, opacity=0.95)
      2. 상단 파란 D자 (fill=topBlueGrad, opacity=0.95)
      3. 교차 영역     (fill=intersectGrad, opacity=0.9)

    알파 합성 시, 교차부에서 녹색→파란→교차 그래디언트가 자연스럽게
    블렌딩되어 SVG 원본과 동일한 깊이감 있는 색감이 재현됩니다.
    """
    scale = size / 256.0

    # ── 1. 마스크 생성 ──

    # 녹색 D자: 원(96,144, r=64) + 직사각형(96,144 → 160,208)
    green_mask = create_d_mask(size, scale, 96, 144, 64, (96, 144, 160, 208))

    # 파란 D자: 원(160,112, r=64) + 직사각형(96,48 → 160,112)
    blue_mask = create_d_mask(size, scale, 160, 112, 64, (96, 48, 160, 112))

    # 교차 마스크: 두 D자형의 겹침 = 두 마스크의 AND
    intersect_mask = ImageChops.multiply(green_mask, blue_mask)

    # ── 2. 색상 레이어 생성 ──

    # 레이어 1: 녹색 단색
    green_color = Image.new("RGB", (size, size), GREEN)
    green_layer = apply_mask_with_opacity(green_color, green_mask, 0.95)

    # 레이어 2: 파란 대각선 그래디언트 (#eff8ff → #175cd3)
    blue_gradient = create_diagonal_gradient(size, BLUE_LIGHT, BLUE_DARK)
    blue_layer = apply_mask_with_opacity(blue_gradient, blue_mask, 0.95)

    # 레이어 3: 교차 대각선 그래디언트 (#175cd3 → #067647)
    intersect_gradient = create_diagonal_gradient(size, INTERSECT_START, INTERSECT_END)
    intersect_layer = apply_mask_with_opacity(intersect_gradient, intersect_mask, 0.9)

    # ── 3. 알파 합성 (SVG 렌더링 순서와 동일) ──
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result = Image.alpha_composite(result, green_layer)   # 1층: 녹색
    result = Image.alpha_composite(result, blue_layer)     # 2층: 파란
    result = Image.alpha_composite(result, intersect_layer)  # 3층: 교차

    return result


# ── ICO 생성 ─────────────────────────────────────────

def create_ico(base_img: Image.Image, ico_path: Path, sizes: list[tuple[int, int]]):
    """기본 이미지에서 다중 해상도 ICO 파일을 생성합니다."""
    print(f"  ICO 생성 중 (해상도 {len(sizes)}개)...")

    frames = []
    for w, h in sizes:
        resized = base_img.resize((w, h), Image.LANCZOS)
        frames.append(resized)
        print(f"    {w:>3}x{h:<3} 완료")

    frames[0].save(
        str(ico_path),
        format="ICO",
        sizes=sizes,
        append_images=frames[1:],
    )
    print(f"    -> ICO 저장: {ico_path.name}")


# ── 실행 ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  SHIM Portable Icon Generator")
    print("=" * 50)
    print()

    if not SVG_INPUT.exists():
        print(f"[ERROR] SVG 파일 없음: {SVG_INPUT}")
        sys.exit(1)

    print(f"  입력: {SVG_INPUT.name}")
    print()

    # 1단계: 슈퍼샘플링 렌더링 (알파 합성)
    print(f"  [1/3] 렌더링 ({RENDER_SIZE}x{RENDER_SIZE}, alpha compositing)...")
    raw_img = render_shim_icon(RENDER_SIZE)

    # 2단계: 다운스케일 (안티앨리어싱)
    print(f"  [2/3] 다운스케일 {RENDER_SIZE} -> {FINAL_SIZE}...")
    final_img = raw_img.resize((FINAL_SIZE, FINAL_SIZE), Image.LANCZOS)

    # PNG 저장
    final_img.save(str(PNG_OUTPUT), format="PNG")
    print(f"    -> PNG 저장: {PNG_OUTPUT.name}")
    print()

    # 3단계: ICO 변환
    print(f"  [3/3] ICO 변환...")
    create_ico(final_img, ICO_OUTPUT, ICON_SIZES)

    print()
    print("=" * 50)
    print(f"  완료!")
    print(f"    PNG: {PNG_OUTPUT}")
    print(f"    ICO: {ICO_OUTPUT}")
    print("=" * 50)


if __name__ == "__main__":
    main()