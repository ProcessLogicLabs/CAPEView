"""Render the CAPEView SVG icon into a multi-resolution Windows ``icon.ico``.

Pipeline:
    capeview_icon_hires.svg   (master)
        --> cairosvg renders PNGs at 16/24/32/48/64/128/256 px
        --> Pillow saves them as a single multi-resolution .ico

Run this whenever ``capeview_icon_hires.svg`` changes:
    python scripts/make_icon.py

The output is committed (``CAPEView/Resources/icon.ico``) so end users
don't need cairosvg installed to build CAPEView.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import cairosvg  # type: ignore[import-not-found]
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "CAPEView" / "Resources" / "capeview_icon_hires.svg"
ICO_PATH = ROOT / "CAPEView" / "Resources" / "icon.ico"
PNG_PREVIEW = ROOT / "CAPEView" / "Resources" / "icon_512.png"

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_png(size: int) -> Image.Image:
    """Rasterize the SVG at ``size``×``size`` and return a Pillow Image."""
    png_bytes = cairosvg.svg2png(
        url=str(SVG_PATH),
        output_width=size,
        output_height=size,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def main() -> int:
    if not SVG_PATH.exists():
        sys.exit(f"SVG not found: {SVG_PATH}")

    print(f"Reading {SVG_PATH}")
    images = []
    for size in SIZES:
        print(f"  rendering {size}x{size}")
        images.append(render_png(size))

    # 512px preview for documentation / Slack / quick visual checks
    preview = render_png(512)
    preview.save(PNG_PREVIEW, format="PNG")
    print(f"Saved preview: {PNG_PREVIEW}")

    # Pillow's .ico writer accepts a list of PIL images via the "sizes"
    # parameter; pass the largest image and let Pillow downsample.
    largest = images[-1]
    largest.save(
        ICO_PATH,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Saved ICO:     {ICO_PATH}  ({ICO_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
