"""QuickSearch 전용 앱 아이콘 생성기.

Pillow로 돋보기 아이콘을 그려 assets/quicksearch.ico (멀티 해상도) 와
assets/quicksearch.png (256px) 를 만든다. 아이콘 디자인을 바꾸려면 이 파일만
수정하고 다시 실행하면 된다.

    python tools/make_icon.py
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFilter

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# 앱 강조색(ui/styles.qss 의 #3478F6)을 중심으로 한 세로 그라데이션
GRADIENT_TOP = (91, 155, 255)
GRADIENT_BOTTOM = (30, 92, 214)
GLASS_FILL = (255, 255, 255, 64)

# ICO 에 담을 해상도. Windows 는 트레이/작업표시줄/탐색기에서 서로 다른 크기를 고른다.
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# 안티앨리어싱용 슈퍼샘플링 배율
SS = 8


class IconSpec(NamedTuple):
    """해상도별 렌더링 파라미터(모두 아이콘 변 길이에 대한 비율)."""

    stroke: float       # 선 두께
    corner: float       # 배경 라운드 반경
    lens: float         # 렌즈 반지름
    center: float       # 렌즈 중심 좌표
    handle_end: float   # 손잡이 끝점 좌표
    glass: int          # 렌즈 내부 채움 알파(0이면 채우지 않음)
    sharpen: float      # 다운샘플 후 언샤프 강도(0이면 생략)


def _vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """세로 방향 선형 그라데이션 이미지."""
    strip = Image.new("RGB", (1, size))
    draw = ImageDraw.Draw(strip)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.point((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return strip.resize((size, size), Image.Resampling.BILINEAR)


def _magnifier_mask(size: int, spec: "IconSpec") -> Image.Image:
    """돋보기 실루엣(흰색으로 칠할 영역) 마스크."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    stroke = max(1.0, spec.stroke * size)
    cx = cy = spec.center * size
    radius = spec.lens * size

    # 렌즈 유리: 링 안쪽을 옅게 채워 작은 크기에서도 원형이 읽히게 한다
    if spec.glass:
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=spec.glass,
        )
    # 렌즈 링
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=255,
        width=round(stroke),
    )

    # 손잡이: 링 바깥 대각선. 양 끝을 원으로 덮어 둥근 캡을 만든다.
    handle_w = stroke * 1.15
    inner = radius + stroke * 0.25
    x0 = cx + inner * 0.7071
    y0 = cy + inner * 0.7071
    x1 = spec.handle_end * size
    y1 = spec.handle_end * size
    draw.line([x0, y0, x1, y1], fill=255, width=round(handle_w))
    for px, py in ((x0, y0), (x1, y1)):
        r = handle_w / 2
        draw.ellipse([px - r, py - r, px + r, py + r], fill=255)

    return mask


def _spec_for(size: int) -> "IconSpec":
    """크기별 형상 스펙. 작을수록 글리프를 키우고 선을 굵게 잡아야 형태가 읽힌다."""
    if size <= 20:
        # 16~20px: 렌즈를 최대한 키우고 손잡이를 짧게, 유리 채움은 생략
        return IconSpec(stroke=0.115, corner=0.20, lens=0.245, center=0.405,
                        handle_end=0.79, glass=0, sharpen=1.05)
    if size <= 32:
        return IconSpec(stroke=0.100, corner=0.21, lens=0.230, center=0.415,
                        handle_end=0.80, glass=48, sharpen=0.9)
    return IconSpec(stroke=0.090, corner=0.225, lens=0.215, center=0.425,
                    handle_end=0.80, glass=GLASS_FILL[3], sharpen=0.0)


def render(size: int) -> Image.Image:
    """지정한 픽셀 크기의 아이콘 한 장을 렌더링한다."""
    hi = size * SS
    spec = _spec_for(size)
    corner_ratio = spec.corner

    # 라운드 사각형 배경 + 그라데이션
    bg_mask = Image.new("L", (hi, hi), 0)
    ImageDraw.Draw(bg_mask).rounded_rectangle(
        [0, 0, hi - 1, hi - 1], radius=corner_ratio * hi, fill=255
    )
    icon = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    icon.paste(_vertical_gradient(hi, GRADIENT_TOP, GRADIENT_BOTTOM), (0, 0), bg_mask)

    # 흰색 돋보기 합성
    glyph = Image.new("RGBA", (hi, hi), (255, 255, 255, 0))
    glyph.putalpha(_magnifier_mask(hi, spec))
    icon = Image.alpha_composite(icon, glyph)

    out = icon.resize((size, size), Image.Resampling.LANCZOS)
    if spec.sharpen:
        # 다운샘플로 흐려진 경계를 되살린다(작은 크기 전용)
        out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(spec.sharpen * 100), threshold=0))
    return out


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    frames = [render(s) for s in ICO_SIZES]

    ico_path = ASSETS_DIR / "quicksearch.ico"
    frames[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    png_path = ASSETS_DIR / "quicksearch.png"
    frames[-1].save(png_path, format="PNG")

    print(f"생성: {ico_path} ({', '.join(f'{s}x{s}' for s in ICO_SIZES)})")
    print(f"생성: {png_path} (256x256)")


if __name__ == "__main__":
    main()
