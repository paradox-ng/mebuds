"""Generate the README banner: the app icon next to a "mebuds" wordmark in
the same lineal style. The letters are converted to outlines, so the SVG
doesn't depend on fonts installed where it's viewed.

    pip install fonttools skia-pathops
    python tools/gen_banner.py path/to/Inter-Bold.ttf docs/banner.svg

The banner uses Inter Bold (SIL Open Font License), a sans close to
Xiaomi's MiSans.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps

ROOT = Path(__file__).resolve().parents[1]
INK = "#232629"
FILL = "#eceef0"
SHADE = "#cbcfd4"

WORD = "mebuds"
SIZE = 108         # font size in px
TRACKING = 0.04    # extra space between letters, in em


def wordmark(font_file: str) -> tuple[str, float, float]:
    """SVG path data for WORD with the baseline at y=0, its width, and the
    height of its tallest letters above the baseline."""
    font = TTFont(font_file)
    # Variable-font instances are often built from overlapping contours,
    # which the outline stroke would draw through the letters.
    removeOverlaps(font)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = SIZE / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    x = 0.0
    for ch in WORD:
        name = cmap[ord(ch)]
        # Font units are y-up; SVG is y-down.
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        x += glyphs[name].width * scale + TRACKING * SIZE
    ascender = font["OS/2"].sTypoAscender * scale * 0.97
    return pen.getCommands(), x - TRACKING * SIZE, ascender


def banner(font_file: str) -> str:
    d, word_w, ascender = wordmark(font_file)
    icon_size, gap, pad, stroke = 140, 22, 12, 3.6
    height = icon_size + 2 * pad
    tx = pad + icon_size + gap
    ty = height / 2 + ascender / 2  # centre the ascender-to-baseline span
    width = int(tx + word_w + pad + stroke)

    icon_svg = (ROOT / "mebuds" / "data" / "mebuds.svg").read_text()
    icon_body = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$|<!--.*?-->", "", icon_svg, flags=re.S)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">\n'
        '  <defs><linearGradient id="word" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0.7" stop-color="{FILL}"/><stop offset="0.7" stop-color="{SHADE}"/>'
        "</linearGradient></defs>\n"
        f'  <g transform="translate({pad} {pad}) scale({icon_size / 128:.4f})">'
        f"{icon_body.strip()}</g>\n"
        f'  <path transform="translate({tx:.1f} {ty:.1f})" d="{d}" fill="url(#word)" '
        f'stroke="{INK}" stroke-width="{stroke}" stroke-linejoin="round"/>\n'
        "</svg>\n"
    )


if __name__ == "__main__":
    Path(sys.argv[2]).write_text(banner(sys.argv[1]))
    print("written", sys.argv[2])
