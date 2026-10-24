"""Generate mebuds' SVG artwork in a "lineal colour" style: thick dark
outlines, light fill, a shading band and a highlight stroke.

    python tools/gen_art.py mebuds/data

The colours below are also swapped at runtime for dark themes
(mebuds/icons.py), so keep the two lists in sync.
"""
import math
import sys

OUT = sys.argv[1]
INK = "#232629"
FILL = "#eceef0"
SHADE = "#cbcfd4"
DEEP = "#9da2a8"
SW = 4.6


def f(v):
    return f"{v:.1f}"


class Ellipse:
    def __init__(self, cx, cy, rx, ry, rot):
        self.cx, self.cy, self.rx, self.ry, self.rot = cx, cy, rx, ry, rot

    def at(self, t_deg, k=1.0, dy=0.0):
        t, r = math.radians(t_deg), math.radians(self.rot)
        rx, ry = self.rx * k, self.ry * k
        x = self.cx + rx * math.cos(t) * math.cos(r) - ry * math.sin(t) * math.sin(r)
        y = self.cy + rx * math.cos(t) * math.sin(r) + ry * math.sin(t) * math.cos(r)
        return x, y + dy

    def t_at_x(self, x, lo, hi):
        """Parameter in [lo, hi] (degrees) where the outline crosses x."""
        for _ in range(60):
            mid = (lo + hi) / 2
            if (self.at(lo)[0] - x) * (self.at(mid)[0] - x) <= 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    def arc(self, t0, t1, k=1.0, dy=0.0, steps=48):
        """Polyline along the ellipse; good enough at icon sizes and avoids
        SVG arc-flag fiddling."""
        pts = [self.at(t0 + (t1 - t0) * i / steps, k, dy) for i in range(steps + 1)]
        return " ".join(f"L{f(x)} {f(y)}" for x, y in pts)


def bud(ox=0.0, oy=0.0, scale=1.0, details=True):
    """Right earbud as in the product photo: nozzle on the left, stem below.
    Returns SVG elements; the left bud is the same drawing mirrored."""
    s = scale
    head = Ellipse(ox + 60 * s, oy + 42 * s, 31 * s, 28 * s, -14)
    sl, sr = ox + 60 * s, ox + 79 * s          # stem left/right x
    bottom = oy + 119 * s
    rad = (sr - sl) / 2
    # Where the stem's sides meet the head (lower half: t in 0..180).
    t_r = head.t_at_x(sr, 0, 90)
    t_l = head.t_at_x(sl, 90, 180)
    rx_, ry_ = head.at(t_r)
    lx_, ly_ = head.at(t_l)

    # Fill: head, then shading band, then stem on top of it.
    head_fill = f"M{f(rx_)} {f(ry_)} " + head.arc(t_r, t_l - 360) + " Z"
    shade = (f"M{f(head.at(150)[0])} {f(head.at(150)[1])} "
             + head.arc(150, 20) + " " + head.arc(20, 150, dy=-10 * s) + " Z")
    stem_fill = (f"M{f(sl)} {f(ly_ - 6 * s)} L{f(sl)} {f(bottom - rad)} "
                 f"A{f(rad)} {f(rad)} 0 0 0 {f(sr)} {f(bottom - rad)} "
                 f"L{f(sr)} {f(ry_ - 6 * s)} Z")

    # Outline: head over the top, then down and around the stem.
    outline_head = f"M{f(rx_)} {f(ry_)} " + head.arc(t_r, t_l - 360)
    stem_outline = (f"M{f(sr)} {f(ry_)} L{f(sr)} {f(bottom - rad)} "
                    f"A{f(rad)} {f(rad)} 0 0 1 {f(sl)} {f(bottom - rad)} "
                    f"L{f(sl)} {f(ly_)}")

    out = [
        f'<path d="{head_fill}" fill="{FILL}"/>',
        f'<path d="{shade}" fill="{SHADE}"/>',
        f'<path d="{stem_fill}" fill="{FILL}"/>',
    ]
    if details:
        # Speaker nozzle on the left edge.
        nx, ny = head.at(186, k=0.86)
        out.append(f'<ellipse cx="{f(nx)}" cy="{f(ny)}" rx="{f(5.5 * s)}" ry="{f(9.5 * s)}" '
                   f'transform="rotate(12 {f(nx)} {f(ny)})" fill="{DEEP}" '
                   f'stroke="{INK}" stroke-width="{SW * s * 0.8:.2f}"/>')
    stroke = (f'fill="none" stroke="{INK}" stroke-width="{SW * s:.2f}" '
              'stroke-linecap="round" stroke-linejoin="round"')
    out += [
        f'<path d="{outline_head}" {stroke}/>',
        f'<path d="{stem_outline}" {stroke}/>',
    ]
    if details:
        # Highlight stroke near the top and the mic slot on the face.
        out.append(f'<path d="M{f(head.at(-128, k=0.72)[0])} {f(head.at(-128, k=0.72)[1])} '
                   + head.arc(-128, -95, k=0.72) + f'" {stroke}/>')
        mx, my = head.at(-30, k=0.42)
        out.append(f'<path d="M{f(mx - 4.5 * s)} {f(my + 2.6 * s)} L{f(mx + 4.5 * s)} '
                   f'{f(my - 2.6 * s)}" fill="none" stroke="{INK}" '
                   f'stroke-width="{SW * s * 1.25:.2f}" stroke-linecap="round"/>')
    return "\n  ".join(out)


CASE = ("M16 50 C16 39 24 32 37 32 H91 C104 32 112 39 112 50 V64 "
        "C112 89 93 106 64 106 C35 106 16 89 16 64 Z")


def case_svg():
    stroke = (f'fill="none" stroke="{INK}" stroke-width="{SW}" '
              'stroke-linecap="round" stroke-linejoin="round"')
    return "\n  ".join([
        f'<path d="{CASE}" fill="{FILL}"/>',
        # shading band along the bottom
        f'<path d="M16 64 C16 89 35 106 64 106 C93 106 112 89 112 64 '
        f'C110 84 92 97 64 97 C36 97 18 84 16 64 Z" fill="{SHADE}"/>',
        # lid seam and lid gap highlight
        f'<path d="M16 57 H112" fill="none" stroke="{INK}" stroke-width="{SW * 0.7:.2f}"/>',
        f'<path d="{CASE}" {stroke}/>',
        f'<path d="M30 43 C30 40 32 39 35 39" {stroke}/>',
        f'<path d="M57 84 H71" fill="none" stroke="{INK}" stroke-width="{SW * 1.2:.2f}" '
        'stroke-linecap="round"/>',
    ])


def icon_svg():
    """Open case with both earbuds standing in it."""
    stroke = (f'fill="none" stroke="{INK}" stroke-width="{SW}" '
              'stroke-linecap="round" stroke-linejoin="round"')
    lid = "M18 62 C16 36 34 20 64 20 C94 20 112 36 110 62 Z"
    cavity = "M26 62 C25 41 39 29 64 29 C89 29 103 41 102 62 Z"
    body = "M14 62 H114 V72 C114 96 94 112 64 112 C34 112 14 96 14 72 Z"
    # Right bud with its head centred at x=84; the left one is its mirror
    # image around the middle of the icon. Stems disappear behind the case.
    s = 0.5
    right = bud(ox=84 - 60 * s, oy=44 - 42 * s, scale=s).replace("\n", "")
    return "\n  ".join([
        f'<path d="{lid}" fill="{FILL}"/>',
        f'<path d="{cavity}" fill="{DEEP}"/>',
        f'<path d="{lid}" {stroke}/>',
        f"<g>{right}</g>",
        f'<g transform="translate(128 0) scale(-1 1)">{right}</g>',
        f'<path d="{body}" fill="{FILL}"/>',
        f'<path d="M14 72 C14 96 34 112 64 112 C94 112 114 96 114 72 '
        f'C111 92 92 103 64 103 C36 103 17 92 14 72 Z" fill="{SHADE}"/>',
        f'<path d="{body}" {stroke}/>',
        f'<path d="M57 92 H71" fill="none" stroke="{INK}" stroke-width="{SW * 1.2:.2f}" '
        'stroke-linecap="round"/>',
    ])


def svg(body, comment=""):
    c = f"  <!-- {comment} -->\n" if comment else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">\n'
            f"{c}  {body}\n</svg>\n")


files = {
    "earbud": svg(bud(), "Right earbud; the left one is drawn mirrored."),
    "case": svg(case_svg()),
    "mebuds": svg(icon_svg(), "App icon: open case with both earbuds."),
}
for name, content in files.items():
    with open(f"{OUT}/{name}.svg", "w") as fh:
        fh.write(content)
print("written")
