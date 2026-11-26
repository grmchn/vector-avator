"""Hand template lab: render the 8 left-hand shapes of a hand template on a forearm tube,
at several sizes, so their shapes can be judged the way they will be seen in the viewer.

Template format (tools/vector/hands/templates/<type>.json, see docs/vector-parts.md §4.3):
  {"type": "human", "wristWidth": 100,
   "palette": {"base": "#..", "line": "#..", "pad": "#.."},
   "parts": [{"id": "hand_L_open", "variant": "open", "shapes": [{"name": .., "fill": "$base", "d": "M .."}]}]}
  Coordinates: wrist centre (pivot) at (0, 0), wrist width = wristWidth, fingers point down (+Y).
  Left hand (_L): in the A pose its arm is on the screen right, the body is to the -x side.

usage:
  python tools/vector/hands/lab.py TEMPLATE [--out DIR]           lab.png, lab_zoom.png, lab_small.png, lab_rot.png
  python tools/vector/hands/lab.py T1 T2 [T3] --compare --out DIR   compare.png (one row per template)
  python tools/vector/hands/lab.py TEMPLATE --quiz SEED --out DIR   quiz.png + quiz_key.json (shuffled silhouettes)

The forearm is drawn over the hand, with a round end of radius wristWidth/2 at the wrist,
the same way the renderer hides the wrist when arms.*.seamlessHand is true. Like the renderer
(outer outlines off), only fills are drawn.
"""
import argparse, json, random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORDER = ["open", "palm", "palm_up", "point", "point_front", "fist", "peace", "thumbs_up"]
BG = "#E3E8F2"
# cell extents in template units (wrist width 100)
X0, X1, Y0, Y1 = -170, 170, -90, 240
FOREARM = 85  # visible forearm length above the wrist
DIRS = [("down", (0, 1)), ("side", (1, 0)), ("diag_up", (0.7071, -0.7071)), ("up", (0, -1))]


def load(path):
    t = json.loads(Path(path).read_text(encoding="utf-8"))
    parts = {}
    for p in t["parts"]:
        v = p.get("variant") or p["id"].split("hand_L_", 1)[-1]
        parts[v] = p
    missing = [v for v in ORDER if v not in parts]
    if missing:
        sys.exit(f"{path}: missing shapes {missing}")
    return t, parts


def fill_of(t, f):
    return t["palette"][f[1:]] if f.startswith("$") else f


def hand_svg(t, part, sil=None):
    out = []
    for s in part["shapes"]:
        out.append(f'<path d="{s["d"]}" fill="{sil or fill_of(t, s["fill"])}"/>')
    return "".join(out)


def forearm_svg(t, sil=None, length=FOREARM):
    w = t.get("wristWidth", 100)
    c = sil or t["palette"]["base"]
    r = w / 2
    return (f'<path d="M {-r} {-length} L {-r} 0 A {r} {r} 0 0 0 {r} 0 L {r} {-length} Z" fill="{c}"/>')


def unit(t, part, sil=None, rot=0.0, scale=1.0):
    """Hand + forearm in template units, wrist at the origin, rotated by rot degrees."""
    s = 100 / t.get("wristWidth", 100) * scale
    return (f'<g transform="rotate({rot:.2f}) scale({s:.4f})">'
            f'{hand_svg(t, part, sil)}{forearm_svg(t, sil)}</g>')


def grid_svg(rows, cols, cell_w, cell_h, draw, label_h=0, labels=None, title=None, title_h=0, bg=BG):
    W, H = cols * cell_w, title_h + rows * (cell_h + label_h)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    if title:
        out.append(f'<text x="8" y="{title_h * 0.72:.0f}" font-family="sans-serif" font-size="{title_h * 0.55:.0f}" fill="#444">{title}</text>')
    for r in range(rows):
        for c in range(cols):
            x, y = c * cell_w, title_h + r * (cell_h + label_h)
            out.append(f'<g transform="translate({x},{y})">{draw(r, c)}</g>')
            if labels and labels(r, c):
                out.append(f'<text x="{x + cell_w / 2}" y="{y + cell_h + label_h * 0.75:.0f}" text-anchor="middle" '
                           f'font-family="sans-serif" font-size="{label_h * 0.6:.0f}" fill="#444">{labels(r, c)}</text>')
    out.append("</svg>")
    return "".join(out)


def render(svg, png, scale_up=1):
    sp = Path(png).with_suffix(".svg")
    sp.write_text(svg, encoding="utf-8")
    subprocess.run(["resvg", "--sans-serif-family", "Inter", str(sp), str(png)], check=True)
    if scale_up > 1:
        from PIL import Image
        im = Image.open(png)
        im.resize((im.width * scale_up, im.height * scale_up), Image.NEAREST).save(
            str(png).replace(".png", f"_x{scale_up}.png"))


def cell(t, part, px_wrist, sil=None, rot=0.0):
    """Cell drawing for a wrist width of px_wrist pixels."""
    k = px_wrist / 100
    w, h = (X1 - X0) * k, (Y1 - Y0) * k
    return w, h, f'<g transform="translate({-X0 * k:.2f},{-Y0 * k:.2f}) scale({k:.4f})">{unit(t, part, sil, rot)}</g>'


def lab(tpath, out):
    t, parts = load(tpath)
    name = t["type"]
    # (1) zoom x3 of the 90 px size
    w, h, _ = cell(t, parts["open"], 270)
    svg = grid_svg(1, 8, w, h, lambda r, c: cell(t, parts[ORDER[c]], 270)[2], 40, lambda r, c: ORDER[c],
                   f"{name}: zoom (wrist 270 px)", 50)
    render(svg, out / "lab_zoom.png")
    # (2) 90 px, (3) full-body size 25 px, (4) silhouette at 25 px
    rows = [(90, None, "1:1 (wrist 90 px)"), (25, None, "full body (wrist 25 px)"), (25, "#111", "silhouette (wrist 25 px)")]
    blocks = []
    for px, sil, label in rows:
        w, h, _ = cell(t, parts["open"], px)
        blocks.append((px, sil, label, w, h))
    W = 8 * blocks[0][3]
    H = sum(b[4] + 34 for b in blocks)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}">', f'<rect width="100%" height="100%" fill="{BG}"/>']
    y = 0
    for px, sil, label, w, h in blocks:
        o.append(f'<text x="6" y="{y + 22}" font-family="sans-serif" font-size="16" fill="#444">{name}: {label}</text>')
        y += 30
        cw = W / 8
        for c, v in enumerate(ORDER):
            o.append(f'<g transform="translate({c * cw + (cw - w) / 2:.1f},{y})">{cell(t, parts[v], px, sil)[2]}</g>')
        y += h + 4
    o.append("</svg>")
    render("".join(o), out / "lab.png")
    # small: (3) and (4) at true size, plus an x4 nearest copy for viewing
    w, h, _ = cell(t, parts["open"], 25)
    svg = grid_svg(2, 8, w, h, lambda r, c: cell(t, parts[ORDER[c]], 25, "#111" if r else None)[2])
    render(svg, out / "lab_small.png", scale_up=4)
    # forearm directions
    w, h, _ = cell(t, parts["open"], 60)
    side = max(w, h) * 1.25

    def rot_cell(r, c):
        d = DIRS[r][1]
        import math
        rot = math.degrees(math.atan2(-d[0], d[1]))
        k = 60 / 100
        return f'<g transform="translate({side / 2:.1f},{side / 2:.1f}) scale({k})">{unit(t, parts[ORDER[c]], None, rot)}</g>'
    svg = grid_svg(4, 8, side, side, rot_cell, 22, lambda r, c: f"{ORDER[c]} / {DIRS[r][0]}", f"{name}: forearm directions (left hand, arm on screen right)", 34)
    render(svg, out / "lab_rot.png")
    print("wrote", ", ".join(str((out / n).relative_to(ROOT)) for n in ("lab_zoom.png", "lab.png", "lab_small.png", "lab_rot.png")))


def compare(paths, out):
    ts = [load(p) for p in paths]
    w, h, _ = cell(ts[0][0], ts[0][1]["open"], 90)
    svg = grid_svg(len(ts), 8, w, h, lambda r, c: cell(ts[r][0], ts[r][1][ORDER[c]], 90)[2], 26,
                   lambda r, c: f"{ts[r][0]['type']} {ORDER[c]}", "templates compared (wrist 90 px)", 36)
    render(svg, out / "compare.png")
    print("wrote", (out / "compare.png").relative_to(ROOT))


def quiz(tpath, seed, out):
    t, parts = load(tpath)
    order = ORDER[:]
    random.Random(seed).shuffle(order)
    w, h, _ = cell(t, parts["open"], 25)
    svg = grid_svg(1, 8, w, h + 4, lambda r, c: cell(t, parts[order[c]], 25, "#111")[2], 14, lambda r, c: str(c + 1), bg="#FFFFFF")
    render(svg, out / "quiz.png", scale_up=4)
    svg = grid_svg(1, 8, w * 3, h * 3, lambda r, c: cell(t, parts[order[c]], 75, "#111")[2], 30, lambda r, c: str(c + 1), bg="#FFFFFF")
    render(svg, out / "quiz_large.png")
    (out / "quiz_key.json").write_text(json.dumps({"template": str(tpath), "seed": seed,
                                                    "key": {str(i + 1): v for i, v in enumerate(order)}}, indent=1))
    print("wrote", (out / "quiz.png").relative_to(ROOT), "(key in quiz_key.json)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("templates", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--quiz", type=int, default=None, metavar="SEED")
    a = ap.parse_args()
    out = Path(a.out or ROOT / "var" / "vector" / "hands" / "lab").resolve()
    out.mkdir(parents=True, exist_ok=True)
    if a.compare:
        compare(a.templates, out)
    elif a.quiz is not None:
        quiz(a.templates[0], a.quiz, out)
    else:
        lab(a.templates[0], out)


if __name__ == "__main__":
    main()
