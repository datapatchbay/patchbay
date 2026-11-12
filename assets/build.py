"""Build the datapatchbay brand assets.

The logo is the Michroma wordmark set as a patchbay designation strip: one jack
under every letter. The jacks under d, a, t (the data sources, red plugs) fan
out through split leads into every jack under "patchbay". The jack under the
last "a" of data stays open.

Run from the repo root:

    python3 assets/build.py

Needs fontTools and Pillow, plus Google Chrome for the PNG renders.
Outputs land next to this file; everything is regenerated on each run.
"""
from __future__ import annotations

import io
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).parent
FONT_PATH = ROOT / "fonts" / "Michroma-Regular.ttf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ── palette ──────────────────────────────────────────────────────────────
INK = "#16181D"
PAPER = "#F3F0E8"
RED = "#E4462B"
THEMES = {
    # for light backgrounds
    "light": dict(fg=INK, muted="#8A8578", source=RED),
    # for dark backgrounds
    "dark": dict(fg=PAPER, muted="#8E8B83", source=RED),
    # single colour, for print, embossing, stamps
    "mono-ink": dict(fg=INK, muted=INK, source=INK),
    "mono-white": dict(fg="#FFFFFF", muted="#FFFFFF", source="#FFFFFF"),
}

# ── geometry (all in units of one jack column) ───────────────────────────
C = 40.0                 # column width
FONT_SIZE = 0.775 * C
RING_R = 0.27 * C
RING_SW = 0.075 * C
PIN_R = 0.085 * C
PLUG_R = 0.15 * C
CABLE_SW = 0.075 * C
CABLE_GAP = 0.10 * C     # half-width of the gap cut into a ring where a cable exits
CORNER = 0.42 * C
TEXT_GAP = 0.16 * C      # descender bottom → top of jack ring
LEVEL0 = 0.75 * C        # depth of the shallowest split lead below the jack centres
LEVEL_STEP = 0.42 * C

WORD = "datapatchbay"
MUTED_LETTERS = 4        # "data"
# (source column, [target columns]); listed deepest lead first
FANS = [(0, [9, 10, 11]), (1, [6, 7, 8]), (2, [4, 5])]

font = TTFont(FONT_PATH)
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
SCALE = FONT_SIZE / font["head"].unitsPerEm


def f(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def glyph_bounds(ch):
    pen = BoundsPen(glyphs)
    glyphs[cmap[ord(ch)]].draw(pen)
    return pen.bounds  # xMin, yMin, xMax, yMax in font units (y up)


def glyph_path(ch, cx, baseline):
    """Outline of `ch`, horizontally centred (by ink bbox) on cx."""
    x0, _, x1, _ = glyph_bounds(ch)
    dx = cx - (x0 + x1) / 2 * SCALE
    pen = SVGPathPen(glyphs, ntos=f)
    glyphs[cmap[ord(ch)]].draw(TransformPen(pen, (SCALE, 0, 0, -SCALE, dx, baseline)))
    return pen.getCommands()


def ring(cx, cy, gap_bottom):
    if not gap_bottom:
        return f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(RING_R)}"/>'
    t = math.asin(CABLE_GAP / RING_R)
    x1, y1 = cx - RING_R * math.sin(t), cy + RING_R * math.cos(t)
    x2 = cx + RING_R * math.sin(t)
    return f'<path d="M{f(x1)} {f(y1)}A{f(RING_R)} {f(RING_R)} 0 1 1 {f(x2)} {f(y1)}"/>'


def strip(word, fans, muted_letters, with_text=True):
    """Return (svg body with {fg}/{muted}/{source} placeholders, width, height)."""
    n = len(word)
    tops = [glyph_bounds(ch)[3] for ch in word]
    bottoms = [glyph_bounds(ch)[1] for ch in word]
    baseline = max(tops) * SCALE if with_text else 0
    desc = -min(bottoms) * SCALE if with_text else 0
    cy = baseline + desc + TEXT_GAP + RING_R + RING_SW / 2 if with_text else RING_R + RING_SW / 2
    X = lambda i: (i + 0.5) * C

    sources = {s for s, _ in fans}
    patched = sources | {t for _, ts in fans for t in ts}

    text_muted, text_fg = [], []
    if with_text:
        for i, ch in enumerate(word):
            (text_muted if i < muted_letters else text_fg).append(glyph_path(ch, X(i), baseline))

    rings = "".join(ring(X(i), cy, i in patched) for i in range(n))
    pins = "".join(f'<circle cx="{f(X(i))}" cy="{f(cy)}" r="{f(PIN_R)}"/>' for i in range(n) if i not in patched)

    leads, deepest = [], cy
    k = len(fans)
    for idx, (src, tgts) in enumerate(fans):
        level = cy + LEVEL0 + LEVEL_STEP * (k - 1 - idx)
        far = max(tgts)
        R = CORNER
        leads.append(
            f"M{f(X(src))} {f(cy)}V{f(level - R)}Q{f(X(src))} {f(level)} {f(X(src) + R)} {f(level)}"
            f"H{f(X(far) - R)}Q{f(X(far))} {f(level)} {f(X(far))} {f(level - R)}V{f(cy)}"
        )
        for t in tgts:
            if t != far:
                leads.append(f"M{f(X(t) - R)} {f(level)}Q{f(X(t))} {f(level)} {f(X(t))} {f(level - R)}V{f(cy)}")
        deepest = max(deepest, level)

    src_plugs = "".join(f'<circle cx="{f(X(i))}" cy="{f(cy)}" r="{f(PLUG_R)}"/>' for i in sorted(sources))
    tgt_plugs = "".join(f'<circle cx="{f(X(i))}" cy="{f(cy)}" r="{f(PLUG_R)}"/>' for i in sorted(patched - sources))

    body = ""
    if text_muted:
        body += f'<path fill="{{muted}}" d="{"".join(text_muted)}"/>'
    if text_fg:
        body += f'<path fill="{{fg}}" d="{"".join(text_fg)}"/>'
    body += (
        f'<g fill="none" stroke="{{fg}}" stroke-width="{f(RING_SW)}">{rings}</g>'
        f'<g fill="{{fg}}">{pins}</g>'
        f'<g fill="none" stroke="{{fg}}" stroke-width="{f(CABLE_SW)}" stroke-linecap="round" stroke-linejoin="round">'
        + "".join('<path d="' + p + '"/>' for p in leads) + "</g>"
        f'<g fill="{{fg}}">{tgt_plugs}</g>'
        f'<g fill="{{source}}">{src_plugs}</g>'
    )
    height = deepest + CABLE_SW / 2
    return body, n * C, height


def paint(body, theme):
    t = THEMES[theme]
    return body.replace("{fg}", t["fg"]).replace("{muted}", t["muted"]).replace("{source}", t["source"])


def svg_doc(body, vb, size=None, bg=None, radius=0, title="datapatchbay"):
    x, y, w, h = vb
    dims = f' width="{f(size[0])}" height="{f(size[1])}"' if size else ""
    back = (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(radius)}" fill="{bg}"/>' if bg else "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(x)} {f(y)} {f(w)} {f(h)}"{dims} role="img" aria-label="{title}">'
        f"<title>{title}</title>{back}{body}</svg>\n"
    )


def fit_square(w, h, pad):
    """viewBox for a square tile around content of size w×h with `pad` fraction margin."""
    side = max(w, h) / (1 - 2 * pad)
    return (w / 2 - side / 2, h / 2 - side / 2, side, side)


# ── outputs ──────────────────────────────────────────────────────────────
def build():
    out_logo = ROOT / "logo"
    out_icon = ROOT / "icon"
    out_social = ROOT / "social"
    for d in (out_logo, out_icon, out_social):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)

    # 1. Logo strip
    body, w, h = strip(WORD, FANS, MUTED_LETTERS)
    m = 0.04 * C
    vb = (-m, -m, w + 2 * m, h + 2 * m)
    for theme in THEMES:
        (out_logo / f"datapatchbay-logo-{theme}.svg").write_text(svg_doc(paint(body, theme), vb))

    # 2. Icon: "dpb" over three jacks, d (data) feeds p and b through one split lead
    ibody, iw, ih = strip("dpb", [(0, [1, 2])], 1)
    ivb = fit_square(iw, ih, 0.15)
    for theme, bg in (("dark", INK), ("light", PAPER)):
        (out_icon / f"datapatchbay-icon-{theme}.svg").write_text(svg_doc(paint(ibody, theme), ivb, bg=bg))

    # 3. Favicon: no lettering, three heavier jacks + split lead (reads at 16px)
    global RING_SW, CABLE_SW, PIN_R, PLUG_R, CABLE_GAP, LEVEL0
    saved = (RING_SW, CABLE_SW, PIN_R, PLUG_R, CABLE_GAP, LEVEL0)
    RING_SW, CABLE_SW, PLUG_R, CABLE_GAP, LEVEL0 = 0.11 * C, 0.11 * C, 0.16 * C, 0.12 * C, 0.62 * C
    fbody, fw, fh = strip("dpb", [(0, [1, 2])], 1, with_text=False)
    RING_SW, CABLE_SW, PIN_R, PLUG_R, CABLE_GAP, LEVEL0 = saved
    fvb = fit_square(fw, fh, 0.07)
    fav_svg = svg_doc(paint(fbody, "dark"), fvb, bg=INK, radius=fvb[2] * 0.2)
    (out_icon / "favicon.svg").write_text(fav_svg)

    # 4. Renders
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def render(svg_text, px_w, px_h, dest, transparent=True, scale=1):
            page = tmp / "page.html"
            page.write_text(
                "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
                "svg{display:block;width:100vw;height:100vh}</style></head><body>"
                f"{svg_text}</body></html>"
            )
            shot = tmp / "shot.png"
            args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--force-device-scale-factor={scale}", f"--window-size={px_w},{px_h}",
                    f"--screenshot={shot}", page.as_uri()]
            if transparent:
                args.insert(4, "--default-background-color=00000000")
            subprocess.run(args, check=True, capture_output=True)
            Image.open(shot).convert("RGBA").save(dest, optimize=True)

        # logo PNGs, 1200px wide, transparent
        aspect = vb[3] / vb[2]
        for theme in ("light", "dark"):
            render(svg_doc(paint(body, theme), vb), 1200, round(1200 * aspect),
                   out_logo / f"datapatchbay-logo-{theme}.png")

        # Square rasters: render large once, then downsample (Chrome won't open
        # windows smaller than ~500px, so tiny direct renders come out wrong).
        def square(svg_text, px, transparent):
            big = tmp / "big.png"
            render(svg_text, 1024, 1024, big, transparent=transparent)
            return Image.open(big).convert("RGBA").resize((px, px), Image.LANCZOS)

        icon_dark = (out_icon / "datapatchbay-icon-dark.svg").read_text()
        square(icon_dark, 512, False).save(out_icon / "avatar-512.png", optimize=True)
        square(icon_dark, 180, False).save(out_icon / "apple-touch-icon.png", optimize=True)

        # favicon.ico with 16/32/48 frames from the simplified favicon mark
        frames = {px: square(fav_svg, px, True) for px in (16, 32, 48)}
        frames[48].save(out_icon / "favicon.ico", format="ICO",
                        sizes=[(16, 16), (32, 32), (48, 48)],
                        append_images=[frames[16], frames[32]])
        frames[32].save(out_icon / "favicon-32.png", optimize=True)

        # social preview 1280×640: dark, logo centred, tagline under it
        logo_w = 760
        logo_h = logo_w * aspect
        tag = "data products as code"
        social = f"""<!doctype html><html><head><style>
@font-face{{font-family:M;src:url('{FONT_PATH.as_uri()}')}}
html,body{{margin:0;width:1280px;height:640px;background:{INK};overflow:hidden}}
.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:54px}}
.logo{{width:{logo_w}px;height:{logo_h:.1f}px}}.logo svg{{width:100%;height:100%;display:block}}
.tag{{font-family:M;font-size:21px;letter-spacing:.32em;color:#8E8B83;text-transform:lowercase}}
</style></head><body><div class="wrap"><div class="logo">{svg_doc(paint(body, "dark"), vb)}</div>
<div class="tag">{tag}</div></div></body></html>"""
        page = tmp / "social.html"
        page.write_text(social)
        shot = tmp / "social.png"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=1280,640",
                        "--virtual-time-budget=3000", f"--screenshot={shot}", page.as_uri()],
                       check=True, capture_output=True)
        Image.open(shot).convert("RGB").save(out_social / "social-preview.png", optimize=True)

    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and p.parent.name in ("logo", "icon", "social"):
            print(p.relative_to(ROOT.parent))


if __name__ == "__main__":
    build()
