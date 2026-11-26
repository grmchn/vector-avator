"""Check a vector character (public/characters/<id>/vector/vector.json) against
.claude/skills/vector-avator/references/parts-spec.md, run the vector_layers.py validator/build (tools/vector/layers/), and render review images.

usage: .venv/bin/python tools/vector/check_parts.py <id> [--no-render] [--json PATH]
exit code 0 when there are no errors.
"""
import argparse, copy, json, math, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# validator / SVG builder (copied from the rebuild-character-layers skill)
SKILL = Path(__file__).resolve().parent / "layers"

BONES = {"hips", "spine", "chest", "neck", "head", "leftShoulder", "rightShoulder", "leftUpperArm", "rightUpperArm",
         "leftLowerArm", "rightLowerArm", "leftHand", "rightHand", "leftUpperLeg", "rightUpperLeg", "leftLowerLeg",
         "rightLowerLeg", "leftFoot", "rightFoot"}
LAYERS = {"body", "hair_back", "ear", "head", "feature", "hair_side", "hair_front"}
SIDES = ("L", "R")
HANDS_LEGACY = ("open", "point", "fist", "palm")
REQUIRED = (["torso", "neck", "head", "leg_L", "leg_R", "nose"]
            + [f"eye_{s}_{k}" for s in SIDES for k in ("white", "iris", "pupil", "half", "closed")]
            + [f"mouth_{k}" for k in ("closed", "a", "i", "u", "e", "o", "smile", "surprise", "trouble")]
            + [f"hand_{s}_{k}" for s in SIDES for k in HANDS_LEGACY])
# hand set (.claude/skills/vector-avator/references/parts-spec.md 4.3): the original four are always required. The newer
# four are required as soon as a character has palm_up, peace or thumbs_up (point_front alone
# does not count: it was optional before); a character with none is the legacy set (warning
# only), so existing characters keep passing
HANDS_NEW = ("palm_up", "point_front", "peace", "thumbs_up")
HANDS_TRIGGER = ("palm_up", "peace", "thumbs_up")
SKELETON_KEYS = (["hips", "chest", "neck", "head", "head_center", "head_radius"]
                 + [f"{j}_{s}" for j in ("shoulder", "elbow", "wrist", "hip", "ankle") for s in SIDES])
EXPRESSIONS = ("normal", "smile", "surprise", "trouble")
COLOR = re.compile(r"#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------- geometry helpers
def path_bbox(d):
    from svgpathtools import parse_path
    xmin, xmax, ymin, ymax = parse_path(d).bbox()
    return xmin, ymin, xmax, ymax


def part_bbox(p):
    boxes = [path_bbox(s["d"]) for s in p.get("shapes", []) if s.get("d")]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def side_of(pid):
    m = re.search(r"_(L|R)(_|$)", pid)
    return m.group(1) if m else None


# ---------------------------------------------------------------- structural checks
def check(art, relax=frozenset()):
    """relax: 'far_face' = the far eye / brow / cheek may be missing (side head);
    'sides' = skip the screen-side checks of _L/_R parts and shoulders (body turned 60 / 90 deg)."""
    E, W = [], []
    parts = art.get("parts", [])
    ids = [p.get("id") for p in parts]
    by_id = {p.get("id"): p for p in parts}
    if art.get("format") != "so-chara-vector/1":
        E.append('format must be "so-chara-vector/1"')
    if art.get("schema_version") != 1:
        E.append("schema_version must be 1")
    Wd, Ht = art.get("width"), art.get("height")
    if (Wd, Ht) != (1024, 1536):
        W.append(f"canvas is {Wd}x{Ht} (spec: 1024x1536)")
    for pid in ids:
        if not isinstance(pid, str) or not re.fullmatch(r"[a-z][a-z0-9]*(_([a-z0-9]+|L|R))*", pid):
            E.append(f"bad part id: {pid!r} (lower snake case, sides as _L/_R)")
    if len(set(ids)) != len(ids):
        E.append("duplicate part ids")
    for r in REQUIRED:
        # the far side is the character's right, or its left for the opposite-direction heads (far_L)
        if "far_face" in relax and re.match(rf"(eye|brow|cheek)_{'L' if 'far_L' in relax else 'R'}(_|$)", r):
            continue
        if r not in by_id:
            E.append(f"missing required part: {r}")
    new_hands = [f"hand_{s}_{k}" for s in SIDES for k in HANDS_NEW]
    if any(f"hand_{s}_{k}" in by_id for s in SIDES for k in HANDS_TRIGGER):
        for h in new_hands:
            if h not in by_id:
                E.append(f"missing required part: {h} (hand set of {', '.join(HANDS_LEGACY + HANDS_NEW)})")
    else:
        miss = sorted({h.split("_", 2)[2] for h in new_hands if h not in by_id})
        W.append(f"legacy hand set: add {', '.join(miss)} for each side (.claude/skills/vector-avator/references/parts-spec.md 4.3)")
    for pid, p in by_id.items():  # hands are drawn from the wrist (pivot) downward
        if re.fullmatch(r"hand_[LR]_[a-z_]+", pid) and p.get("shapes"):
            try:
                bb = part_bbox(p)
            except Exception:
                bb = None
            if bb and p.get("pivot") and bb[3] <= p["pivot"][1] + 5:
                W.append(f"{pid}: nothing is drawn below the pivot (a hand is drawn from the wrist toward +Y)")
    chain_ids = {c.get("id") for c in art.get("chains", [])}
    groups = {}
    for p in parts:
        pid = p.get("id")
        for s in p.get("shapes", []):
            if s.get("stroke") or s.get("width", 0):
                E.append(f"{pid}/{s.get('name')}: stroke is not allowed (fill only)")
            if s.get("fill") and not COLOR.match(s["fill"]):
                E.append(f"{pid}/{s.get('name')}: bad fill color")
        if p.get("bone") not in BONES and p.get("bone") not in chain_ids:
            E.append(f"{pid}: bone {p.get('bone')!r} is neither a skeleton bone nor a chain id")
        if p.get("layer") not in LAYERS:
            E.append(f"{pid}: layer {p.get('layer')!r} not in {sorted(LAYERS)}")
        if ("group" in p) != ("variants" in p):
            E.append(f"{pid}: group and variants go together")
        if "group" in p:
            if not isinstance(p["variants"], list) or not p["variants"]:
                E.append(f"{pid}: variants must be a non-empty list")
            g = groups.setdefault(p["group"], {"variants": set(), "shown": [], "hidden": set()})
            g["variants"].update(p["variants"])
            if p.get("visible"):
                g["shown"].append(set(p["variants"]))
            else:
                g["hidden"].update(p["variants"])
        if p.get("clipTo") and p["clipTo"] not in by_id:
            E.append(f"{pid}: clipTo {p['clipTo']!r} does not exist")
        if p.get("color") and not COLOR.match(p["color"]):
            E.append(f"{pid}: bad color")
        if "outline" in p and not isinstance(p["outline"], bool):
            E.append(f"{pid}: outline must be true/false")
        for o in p.get("seamlessWith", []) or []:
            if o not in by_id and o not in ("arm_L", "arm_R"):
                E.append(f"{pid}: seamlessWith {o!r} is neither a part nor arm_L/arm_R")
        if p.get("color") and p.get("shapes") and p["color"].upper() not in {(sh.get("fill") or "").upper() for sh in p["shapes"]}:
            W.append(f"{pid}: color {p['color']} is not one of its fills (use seamlessWith/outline instead of a fake colour)")
        pv = p.get("pivot", [None, None])
        if not (isinstance(pv, list) and len(pv) == 2 and all(isinstance(v, (int, float)) for v in pv)):
            E.append(f"{pid}: bad pivot")
        elif Wd and Ht and not (-Wd * 0.1 <= pv[0] <= Wd * 1.1 and -Ht * 0.1 <= pv[1] <= Ht * 1.1):
            W.append(f"{pid}: pivot {pv} is outside the canvas")
    for gname, g in groups.items():
        g["default"] = (set.intersection(*g["shown"]) - g["hidden"]) if g["shown"] else set()
        if len(g["default"]) != 1:
            E.append(f"group {gname}: the visible parts must make up exactly one variant (got {sorted(g['default'])})")
    for s in SIDES:
        for k in ("eye", "hand"):
            if k == "eye" and s == ("L" if "far_L" in relax else "R") and "far_face" in relax:
                continue
            if f"{k}_{s}" not in groups:
                E.append(f"missing group {k}_{s}")
    if "mouth" not in groups:
        E.append("missing group mouth")

    sk = art.get("skeleton", {})
    for k in SKELETON_KEYS:
        v = sk.get(k)
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(n, (int, float)) for n in v)):
            E.append(f"skeleton.{k} must be [x, y]")
    if "sides" not in relax and (not E or all(not e.startswith("skeleton") for e in E)):
        try:
            if sk["shoulder_L"][0] <= sk["shoulder_R"][0]:
                E.append("skeleton: shoulder_L must be on the screen right (character's own left)")
            for j in ("shoulder", "elbow", "wrist"):
                L, R = sk[f"{j}_L"], sk[f"{j}_R"]
                if abs((L[0] - sk["hips"][0]) + (R[0] - sk["hips"][0])) > 0.25 * abs(L[0] - R[0]) + 20:
                    W.append(f"skeleton: {j} L/R are not roughly symmetric around hips")
            up = [math.dist(sk[f"shoulder_{s}"], sk[f"elbow_{s}"]) for s in SIDES]
            fo = [math.dist(sk[f"elbow_{s}"], sk[f"wrist_{s}"]) for s in SIDES]
            if min(up) < 5 or min(fo) < 5:
                E.append("skeleton: arm bones are too short")
        except (KeyError, TypeError, IndexError):
            pass

    arms = art.get("arms", {})
    for s in SIDES:
        a = arms.get(s)
        if not isinstance(a, dict):
            E.append(f"arms.{s} missing")
            continue
        w = a.get("width", {})
        if not all(isinstance(w.get(k), (int, float)) and w[k] > 0 for k in ("shoulder", "elbow", "wrist")):
            E.append(f"arms.{s}.width needs shoulder/elbow/wrist > 0")
        bands = a.get("bands", [])
        if not bands or bands[0].get("from") != 0 or bands[-1].get("to") != 1:
            E.append(f"arms.{s}.bands must cover t = 0..1")
        for b in bands:
            if not COLOR.match(str(b.get("color"))):
                E.append(f"arms.{s}.bands: bad color")
        sh = a.get("shade", {})
        if not COLOR.match(str(sh.get("color"))) or sh.get("side") not in ("under", "over", "front", "back"):
            E.append(f"arms.{s}.shade needs color and side (under|over)")

    for c in art.get("chains", []):
        for k in ("id", "bone", "parts", "root", "tip", "segments"):
            if k not in c:
                E.append(f"chain {c.get('id')}: missing {k}")
        for pid in c.get("parts", []):
            if pid not in by_id:
                E.append(f"chain {c.get('id')}: unknown part {pid}")
            elif by_id[pid].get("bone") != c.get("id"):
                W.append(f"chain {c.get('id')}: part {pid} has bone {by_id[pid].get('bone')!r} (expected the chain id)")
        for k in ("stiffness", "damping", "gravity"):
            v = c.get(k)
            if not isinstance(v, (int, float)) or not 0 <= v <= 1:
                E.append(f"chain {c.get('id')}: {k} must be 0..1")

    used_layers = {p.get("layer") for p in parts} - {"body"}
    for l in used_layers:
        if l not in art.get("parallax", {}):
            W.append(f"parallax has no value for layer {l}")
    for l, v in art.get("parallax", {}).items():
        if not isinstance(v, (int, float)) or not -1 <= v <= 1.5:
            E.append(f"parallax.{l} must be a number in -1..1.5")
    if art.get("parallax", {}).get("feature", 0) < 0:
        E.append("parallax.feature must not be negative (features are on the front of the head)")

    # head turn tunables (.claude/skills/vector-avator/references/parts-spec.md 3.5.1, src/renderers/vector/head.ts HeadTurn)
    HEAD_TURN = {"radius": (0.5, 2.5), "rimFalloff": (1, 4), "shift": (0, 0.4), "domeFloor": (0, 1), "irisRoll": (0, 0.5), "pupilDepth": (1, 2), "irisSqueeze": (0, 1), "lidFollow": (0, 1.5),
                 "earSqueeze": (0, 0.6), "earIn": (0, 1.5), "earInner": (0, 0.3), "earWidthTurn": (0, 1.5), "noseDepth": (0.8, 1.5), "pitchGain": (0, 2)}
    ht = art.get("headTurn", {})
    if not isinstance(ht, dict):
        E.append("headTurn must be an object")
        ht = {}
    for k, v in ht.items():
        if k == "reach":
            if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) and x > 0 for x in v)):
                E.append("headTurn.reach must be [half width, up, down] in px (> 0)")
            elif isinstance(sk.get("head_radius"), list) and v[0] < sk["head_radius"][0]:
                W.append("headTurn.reach[0] is smaller than head_radius[0] (the rim of the whole head should contain the face)")
        elif k not in HEAD_TURN:
            E.append(f"headTurn.{k}: unknown key (known: reach, {', '.join(HEAD_TURN)})")
        elif not isinstance(v, (int, float)) or not HEAD_TURN[k][0] <= v <= HEAD_TURN[k][1]:
            E.append(f"headTurn.{k} must be a number in {HEAD_TURN[k][0]}..{HEAD_TURN[k][1]}")

    ex = art.get("expressions", {})
    for e in EXPRESSIONS:
        if e not in ex:
            E.append(f"expressions.{e} missing")
            continue
        for key, v in ex[e].items():
            gs = [g for g in groups if g == key or g.startswith(key + "_")]
            if not gs:
                E.append(f"expressions.{e}.{key}: no group {key}/{key}_L/{key}_R")
            for g in gs:
                if v not in groups[g]["variants"]:
                    E.append(f"expressions.{e}.{key}={v}: group {g} has no such variant")

    # left/right sanity: character's left is the screen right
    cx = sk.get("hips", [Wd / 2 if Wd else 512])[0] if isinstance(sk.get("hips"), list) else 512
    for p in parts:
        s = side_of(p.get("id", ""))
        if "sides" in relax or not s or not p.get("shapes"):
            continue
        try:
            bb = part_bbox(p)
        except Exception as e:  # noqa: BLE001
            E.append(f"{p['id']}: cannot parse path ({e})")
            continue
        mx = (bb[0] + bb[2]) / 2
        if (s == "L" and mx < cx - 4) or (s == "R" and mx > cx + 4):
            E.append(f"{p['id']}: is on the wrong side (_{s} = character's own {'left' if s == 'L' else 'right'}, "
                     f"screen {'right' if s == 'L' else 'left'}; center x={mx:.0f}, body x={cx:.0f})")
    return E, W


def skill_validate(art):
    sys.path.insert(0, str(SKILL))
    import vector_layers  # noqa: E402
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(art, f, ensure_ascii=False)
        tmp = Path(f.name)
    try:
        _, compiled, report = vector_layers.load_art(tmp)
        return None, report, compiled
    except SystemExit as e:
        return str(e), None, None
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}", None, None
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- rendering
def default_state(art):
    shown, hidden = {}, {}
    for p in art["parts"]:
        if "group" in p:
            if p.get("visible"):
                shown.setdefault(p["group"], []).append(set(p["variants"]))
            else:
                hidden.setdefault(p["group"], set()).update(p["variants"])
    st = {}
    for g, sets in shown.items():
        d = set.intersection(*sets) - hidden.get(g, set())
        if d:
            st[g] = sorted(d)[0]
    return st


def visible_ids(art, state, hide=(), show=()):
    out = []
    for p in art["parts"]:
        if "group" in p:
            on = state.get(p["group"]) in p["variants"]
        else:
            on = p.get("visible", True)
        if p["id"] in show:
            on = True
        if p["id"] in hide:
            on = False
        if on:
            out.append(p["id"])
    return out


def matrices(art, transforms):
    by_id = {p["id"]: p for p in art["parts"]}
    cache = {}

    def own(pid):
        t = transforms.get(pid, {})
        px, py = by_id[pid]["pivot"]
        a = math.radians(t.get("deg", 0))
        c, s = math.cos(a), math.sin(a)
        dx, dy = t.get("dx", 0), t.get("dy", 0)
        # rotate about pivot, then translate
        return (c, s, -s, c, px - c * px + s * py + dx, py - s * px - c * py + dy)

    def mul(m, n):
        a, b, c, d, e, f = m
        A, B, C, D, E, F = n
        return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)

    def get(pid):
        if pid not in cache:
            par = by_id[pid].get("parent")
            m = own(pid)
            cache[pid] = mul(get(par), m) if par else m
        return cache[pid]

    return get


def svg_doc(art, ids, transforms=None, bg="#EEF1F6"):
    by_id = {p["id"]: p for p in art["parts"]}
    get = matrices(art, transforms or {})
    W, H = art["width"], art["height"]
    defs, body = [], []
    for pid in ids:
        p = by_id[pid]
        m = get(pid)
        tr = f'transform="matrix({",".join(f"{v:.4f}" for v in m)})"'
        clip = ""
        if p.get("clipTo") and p["clipTo"] in by_id:
            cp = by_id[p["clipTo"]]
            cm = get(cp["id"])
            ctr = f'transform="matrix({",".join(f"{v:.4f}" for v in cm)})"'
            defs.append(f'<clipPath id="clip_{pid}">' + "".join(
                f'<path d="{s["d"]}" {ctr}/>' for s in cp["shapes"] if s.get("fill")) + "</clipPath>")
            clip = f' clip-path="url(#clip_{pid})"'
        body.append(f'<g id="{pid}"{clip}>' + "".join(
            f'<path d="{s["d"]}" fill="{s.get("fill") or "none"}" {tr}/>' for s in p["shapes"]) + "</g>")
    bgr = f'<rect width="{W}" height="{H}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<defs>{"".join(defs)}</defs>{bgr}{"".join(body)}</svg>')


def render(svg_text, png, width=None):
    png.parent.mkdir(parents=True, exist_ok=True)
    svg = png.with_suffix(".svg")
    svg.write_text(svg_text, encoding="utf-8")
    cmd = ["resvg", str(svg), str(png)] + (["-w", str(width)] if width else [])
    subprocess.run(cmd, check=True, capture_output=True)
    svg.unlink()


def contact(tiles, out, cols=6, tile=220):
    from PIL import Image, ImageDraw
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tile, rows * (tile + 28)), "#FFFFFF")
    dr = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        im = im.copy()
        im.thumbnail((tile - 12, tile - 12))
        x, y = i % cols * tile, i // cols * (tile + 28)
        sheet.paste(im, (x + (tile - im.width) // 2, y + (tile - im.height) // 2))
        dr.text((x + 6, y + tile + 4), label, fill="#17233A")
    sheet.save(out)


def crop_box(art, ids, pad=24):
    by_id = {p["id"]: p for p in art["parts"]}
    boxes = [part_bbox(by_id[i]) for i in ids if by_id[i].get("shapes")]
    x0 = max(0, min(b[0] for b in boxes) - pad); y0 = max(0, min(b[1] for b in boxes) - pad)
    x1 = min(art["width"], max(b[2] for b in boxes) + pad); y1 = min(art["height"], max(b[3] for b in boxes) + pad)
    return int(x0), int(y0), int(x1), int(y1)


def render_all(art, cid, out, preview_name="preview.png"):
    from PIL import Image
    tmp = out / "_tmp"
    st0 = default_state(art)
    neutral = out / "neutral.png"
    render(svg_doc(art, visible_ids(art, st0)), neutral)
    vdir = ROOT / "public/characters" / cid / "vector"
    render(svg_doc(art, visible_ids(art, st0), bg=None), vdir / preview_name)

    # QA cases from the art.json part
    for q in art.get("qa", []):
        st = dict(st0)
        ids = visible_ids(art, st, q.get("hide", []), q.get("show", []))
        render(svg_doc(art, ids, q.get("transforms")), out / f"qa_{q['name']}.png", width=512)

    # variant groups
    groups = {}
    for p in art["parts"]:
        if "group" in p:
            for v in p["variants"]:
                groups.setdefault(p["group"], [])
                if v not in groups[p["group"]]:
                    groups[p["group"]].append(v)
    tiles = []
    for g, vs in sorted(groups.items()):
        gid = [p["id"] for p in art["parts"] if p.get("group") == g]
        box = crop_box(art, gid, pad=40 if g.startswith(("eye", "brow")) else 30)
        for v in vs:
            st = dict(st0); st[g] = v
            png = tmp / f"{g}_{v}.png"
            ids = visible_ids(art, st)
            if g.startswith(("hand", "sleeve")):  # show the hand alone (it is drawn pointing down)
                ids = [i for i in ids if art_part(art, i).get("group") == g]
            render(svg_doc(art, ids), png)
            tiles.append((f"{g}:{v}", Image.open(png).convert("RGB").crop(box)))
    if tiles:
        contact(tiles, out / "variants.png")

    # expressions (head crop)
    head_ids = [p["id"] for p in art["parts"] if p.get("bone") == "head" or p.get("parent") == "head"]
    hb = crop_box(art, [i for i in head_ids if art_part(art, i).get("visible") or "group" not in art_part(art, i)], 20)
    tiles = []
    for e, spec in art.get("expressions", {}).items():
        st = dict(st0)
        for key, v in spec.items():
            for g in groups:
                if g == key or g.startswith(key + "_"):
                    st[g] = v
        png = tmp / f"expr_{e}.png"
        render(svg_doc(art, visible_ids(art, st)), png)
        tiles.append((e, Image.open(png).convert("RGB").crop(hb)))
    if tiles:
        contact(tiles, out / "expressions.png", cols=4, tile=300)

    # every part alone
    tiles = []
    for i, p in enumerate(art["parts"]):
        png = tmp / f"part_{p['id']}.png"
        render(svg_doc(art, [p["id"]], bg="#D9DEE6"), png)
        try:
            bb = crop_box(art, [p["id"]], 8)
            tiles.append((f"{i:02d} {p['id']}", Image.open(png).convert("RGB").crop(bb)))
        except Exception:  # noqa: BLE001
            pass
    contact(tiles, out / "parts.png", cols=8, tile=180)

    # skeleton overlay
    from PIL import ImageDraw
    im = Image.open(neutral).convert("RGB")
    dr = ImageDraw.Draw(im)
    sk = art.get("skeleton", {})
    for a, b in [("neck", "head"), ("neck", "chest"), ("chest", "hips")] + [
            (f"{x}_{s}", f"{y}_{s}") for s in SIDES for x, y in (("shoulder", "elbow"), ("elbow", "wrist"), ("hip", "ankle"))]:
        if a in sk and b in sk:
            dr.line([tuple(sk[a]), tuple(sk[b])], fill="#E8305A", width=4)
    for k, v in sk.items():
        if k != "head_radius":
            dr.ellipse([v[0] - 7, v[1] - 7, v[0] + 7, v[1] + 7], outline="#1D4ED8", width=3)
    if "head_center" in sk and "head_radius" in sk:
        (hx, hy), (rx, ry) = sk["head_center"], sk["head_radius"]
        dr.ellipse([hx - rx, hy - ry, hx + rx, hy + ry], outline="#1D4ED8", width=2)
    for c in art.get("chains", []):
        dr.line([tuple(c["root"]), tuple(c["tip"])], fill="#16A34A", width=4)
    im.save(out / "skeleton.png")
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()


def art_part(art, pid):
    return next(p for p in art["parts"] if p["id"] == pid)


def skill_build(art, cid):
    sys.path.insert(0, str(SKILL))
    import vector_layers
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "art.json"
        f.write_text(json.dumps(art, ensure_ascii=False), encoding="utf-8")
        out = ROOT / "public/characters" / cid / "vector/build"
        r = subprocess.run([sys.executable, str(SKILL / "vector_layers.py"), "build", "--art", str(f), "--out", str(out)],
                           capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)[-800:]


# ---------------------------------------------------------------- turned body view
VIEW_SKELETON = ["hips", "chest", "neck", "head", "shoulder_L", "shoulder_R", "hip_L", "hip_R", "ankle_L", "ankle_R"]
NUM = re.compile(r"[MLCQZmlcqz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def map_path(d, dx, dy):
    """Translate an absolute M/L/C/Q/Z path."""
    out, xi = [], True
    for t in NUM.findall(d):
        if t.isalpha():
            out.append(t)
            xi = True
            continue
        v = float(t) + (dx if xi else dy)
        out.append(f"{v:.2f}")
        xi = not xi
    return " ".join(out)


def swap_side(s):
    """Character's left <-> right in an id (bodyView.ts swapSide)."""
    s = re.sub(r"_L(?=$|_)", "\x01", s)
    s = re.sub(r"_R(?=$|_)", "_L", s).replace("\x01", "_R")
    return re.sub(r"^right", "left", re.sub(r"^left", "\x02", s)).replace("\x02", "right") if s.startswith(("left", "right")) else s


def mirror_path(d, cx):
    """Mirror an absolute M/L/C/Q/Z path about x = cx."""
    out, xi = [], True
    for t in NUM.findall(d):
        if t.isalpha():
            out.append(t)
            xi = True
            continue
        v = 2 * cx - float(t) if xi else float(t)
        out.append(f"{v:.2f}")
        xi = not xi
    return " ".join(out)


def mirror_view(v):
    """The view drawn the other way round (bodyView.ts mirrorView): mirrored about the hips (a
    head view: its head joint), sides swapped. Used to put an opposite-direction head (
    head<deg>_opp.json) on the mirrored body drawing, as the renderer does."""
    cx = (v["skeleton"].get("hips") or v["skeleton"]["head"])[0]
    f = lambda q: [2 * cx - q[0], q[1]]
    w = copy.deepcopy(v)
    w["yaw"] = -v["yaw"]
    w["skeleton"] = {swap_side(k): (q if k == "head_radius" else f(q)) for k, q in v["skeleton"].items()}
    for q in w["parts"]:
        q["id"] = swap_side(q["id"])
        if q.get("pivot"):
            q["pivot"] = f(q["pivot"])
        for k in ("bone", "parent", "group"):
            if isinstance(q.get(k), str):
                q[k] = swap_side(q[k])
        for sh in q["shapes"]:
            sh["d"] = mirror_path(sh["d"], cx)
    for c in w.get("chains", []):
        c["id"], c["bone"] = swap_side(c["id"]), swap_side(c["bone"])
        c["parts"] = [swap_side(i) for i in c.get("parts", [])]
        c["root"], c["tip"] = f(c["root"]), f(c["tip"])
    if w.get("arms"):
        a = w["arms"]
        w["arms"] = {"L": a.get("R"), "R": a.get("L")}
        for k in "LR":
            if w["arms"][k] and w["arms"][k].get("attach"):
                w["arms"][k]["attach"] = swap_side(w["arms"][k]["attach"])
    if w.get("order"):
        w["order"] = [swap_side(i) for i in w["order"]]
    if w.get("headOffset"):
        w["headOffset"] = [-w["headOffset"][0], w["headOffset"][1]]
    return w


def head_ids(art):
    hc = {c["id"] for c in art.get("chains", []) if c.get("bone") == "head"}
    return {p["id"] for p in art["parts"] if p.get("bone") == "head" or p.get("bone") in hc}


def is_hand_sleeve(p):
    return bool(p.get("group")) and re.match(r"(hand|sleeve)_", p["group"]) is not None


def front_body_view(front):
    """The front body as a view (to check a side head before the 90 deg body exists)."""
    heads = head_ids(front)
    return {"format": "so-chara-vector-view/1", "view": "body0", "yaw": 0, "skeleton": dict(front["skeleton"]),
            "parts": [p for p in front["parts"] if p["id"] not in heads and not is_hand_sleeve(p)],
            "chains": [c for c in front.get("chains", []) if c.get("bone") != "head"]}


def translate_part(p, dx, dy):
    q = copy.deepcopy(p)
    q["pivot"] = [p["pivot"][0] + dx, p["pivot"][1] + dy]
    for sh in q["shapes"]:
        sh["d"] = map_path(sh["d"], dx, dy)
    return q


def compose_view(front, view, head=None):
    """Same composition as src/renderers/vector/bodyView.ts composeView (head: a side head
    view, head90.json)."""
    ax = front["skeleton"]["hips"][0] - view["skeleton"]["hips"][0]
    if ax:  # place the view's hips on the front's vertical axis (alignView)
        view = copy.deepcopy(view)
        view["skeleton"] = {k: [p[0] + ax, p[1]] for k, p in view["skeleton"].items()}
        for p in view["parts"]:
            p["pivot"] = [p["pivot"][0] + ax, p["pivot"][1]]
            for sh in p["shapes"]:
                sh["d"] = map_path(sh["d"], ax, 0)
        for c in view.get("chains", []):
            c["root"] = [c["root"][0] + ax, c["root"][1]]
            c["tip"] = [c["tip"][0] + ax, c["tip"][1]]
    fs, vs = front["skeleton"], view["skeleton"]
    hsk = head["skeleton"] if head else fs
    dx, dy = vs["head"][0] - hsk["head"][0], vs["head"][1] - hsk["head"][1]
    if not head and view.get("headOffset"):
        # the front head turned along with the body sits off the pivot (.claude/skills/vector-avator/references/parts-spec.md 8.2);
        # the renderer applies it in id071
        dx, dy = dx + view["headOffset"][0], dy + view["headOffset"][1]
    heads = head_ids(front)
    kept = {}
    for p in front["parts"]:
        if p["id"] in heads and not head:
            kept[p["id"]] = translate_part(p, dx, dy)
        elif is_hand_sleeve(p):
            kept[p["id"]] = p
    if head:
        for p in head["parts"]:
            kept[p["id"]] = translate_part(p, dx, dy)
    vparts = {p["id"]: p for p in view["parts"]}
    order = (head or {}).get("order") or view.get("order")
    if head and not order:
        order = [p["id"] for p in view["parts"]] + [p["id"] for p in head["parts"]]
    if head and order:
        # the body parts among themselves keep the body drawing's order (bodyView.ts withBodyOrder)
        body = {p["id"] for p in view["parts"]}
        own = [i for i in view["order"] if i in body] if view.get("order") else [p["id"] for p in view["parts"]]
        listed = {i for i in order if i in body}
        seq = iter([i for i in own if i in listed])
        order = [next(seq, i) if i in body else i for i in order]
    if order:
        parts = [kept.get(i) or vparts.get(i) for i in order]
        parts = [p for p in parts if p] + [p for p in front["parts"] if is_hand_sleeve(p) and p["id"] not in order]
    else:
        parts, k = [], 0
        for p in front["parts"]:
            if p["id"] in kept:
                parts.append(kept[p["id"]])
            elif k < len(view["parts"]):
                parts.append(view["parts"][k])
                k += 1
        parts += view["parts"][k:]
    sk = dict(fs)
    sk.update(vs)
    for s in "LR":
        sh = vs.get(f"shoulder_{s}", fs[f"shoulder_{s}"])
        for j in ("elbow", "wrist"):
            sk[f"{j}_{s}"] = [sh[0] + fs[f"{j}_{s}"][0] - fs[f"shoulder_{s}"][0], sh[1] + fs[f"{j}_{s}"][1] - fs[f"shoulder_{s}"][1]]
    sk["head_center"] = [hsk["head_center"][0] + dx, hsk["head_center"][1] + dy]
    if head:
        sk["head_radius"] = list(hsk["head_radius"])
    vch = {c["id"]: c for c in view.get("chains", [])}
    hx, hy = vs["hips"][0] - fs["hips"][0], vs["hips"][1] - fs["hips"][1]
    chains = []
    hch = {c["id"]: c for c in (head or {}).get("chains", [])}
    for c in front.get("chains", []):
        if c.get("bone") == "head":
            if head and c["id"] not in hch:
                continue
            c = hch.get(c["id"], c)
            chains.append(dict(c, root=[c["root"][0] + dx, c["root"][1] + dy], tip=[c["tip"][0] + dx, c["tip"][1] + dy]))
        else:
            chains.append(vch.get(c["id"]) or dict(c, root=[c["root"][0] + hx, c["root"][1] + hy], tip=[c["tip"][0] + hx, c["tip"][1] + hy]))
    chains += [c for c in view.get("chains", []) if c["id"] not in {x["id"] for x in chains}]
    arms = {s: dict(front["arms"][s], **(view.get("arms", {}) or {}).get(s, {})) for s in "LR"}
    out = dict(front, parts=parts, skeleton=sk, chains=chains, arms=arms)
    if head:
        out["parallax"] = dict(front.get("parallax", {}), **head.get("parallax", {}))
        out["headTurn"] = dict(front.get("headTurn", {}), **head.get("headTurn", {}))
        heads = {p["id"] for p in head["parts"]}
    # QA cases for the turned body: the body without the head and the cover parts, and the
    # legs / tail swung from their pivots
    ids = {p["id"] for p in parts}
    body = [p["id"] for p in view["parts"]]
    hide_head = [i for i in heads if i in ids]
    qa = [{"name": "reveal_body", "kind": "reveal", "hide": hide_head, "check": "頭を外しても、首・胴の上端が丸く閉じている"}]
    covers = [i for i in body if i not in ("torso", "neck") and not i.startswith(("leg_", "tail"))]
    if covers:
        qa.append({"name": "reveal_torso", "kind": "reveal", "hide": hide_head + covers, "check": "胸元・襟などを外しても、胴が補完されている"})
    mv = {i: {"deg": 18 if i.endswith("_L") else -18} for i in body if i.startswith("leg_")}
    if "tail" in ids:
        mv["tail"] = {"deg": 25}
    if mv:
        qa.append({"name": "move_legs", "kind": "move", "transforms": mv, "check": "脚・しっぽを回しても、付け根に切り口が出ない"})
    out["qa"] = qa
    return out


def check_view(front, view):
    E, W = [], []
    if view.get("format") != "so-chara-vector-view/1":
        E.append('view format must be "so-chara-vector-view/1"')
    if not isinstance(view.get("yaw"), (int, float)) or not (0 < abs(view["yaw"]) <= 90):
        E.append("view yaw must be a number of degrees (15, 30, 45, 60, 75 or 90)")
    if view.get("kind") == "head":
        return check_head_view(front, view, E, W)
    for k in VIEW_SKELETON:
        v = view.get("skeleton", {}).get(k)
        if not (isinstance(v, list) and len(v) == 2):
            E.append(f"view skeleton.{k} missing")
    heads = head_ids(front)
    fbody = [p["id"] for p in front["parts"] if p["id"] not in heads and not is_hand_sleeve(p)]
    vids = [p["id"] for p in view.get("parts", [])]
    if sorted(fbody) != sorted(vids) and not view.get("order"):
        E.append(f"view parts {sorted(vids)} differ from the front body parts {sorted(fbody)} (write 'order' when they differ)")
    for p in view.get("parts", []):
        if p.get("bone") == "head" or p.get("layer") != "body":
            E.append(f"view part {p['id']}: body parts only (layer body, not on the head)")
    vch = {c["id"] for c in view.get("chains", [])}
    fch = {c["id"]: c for c in front.get("chains", [])}
    for p in view.get("parts", []):
        if p.get("bone") in fch and p["bone"] not in vch:
            W.append(f"view part {p['id']} hangs on chain {p['bone']} but the view has no chain for it (front chain shifted by the hips is used)")
    # skeleton.head is the head pivot = centre of the neck's upper end (.claude/skills/vector-avator/references/parts-spec.md 8.2)
    neck = next((p for p in view.get("parts", []) if p["id"] == "neck"), None)
    hd = view.get("skeleton", {}).get("head")
    if neck and isinstance(hd, list):
        pts = [xy for s in neck.get("shapes", []) for xy in path_points(s.get("d", ""))]
        if pts:
            top = min(y for _, y in pts)
            band = [x for x, y in pts if y < top + 40]
            mid = (min(band) + max(band)) / 2
            if abs(hd[0] - mid) > 8:
                W.append(f"view skeleton.head x={hd[0]} is {hd[0] - mid:+.0f}px from the centre of the neck top (x={mid:.0f}); "
                         "head is the pivot, put the front-head shift in headOffset")
    ho = view.get("headOffset")
    if ho is not None and not (isinstance(ho, list) and len(ho) == 2 and all(isinstance(v, (int, float)) for v in ho)):
        E.append("view headOffset must be [dx, dy]")
    return E, W


def path_points(d: str):
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2]))


def check_head_view(front, head, E, W):
    """Turned head (head60.json / head90.json, .claude/skills/vector-avator/references/parts-spec.md 8.3, 8.5)."""
    for k in ("head", "head_center", "head_radius"):
        v = head.get("skeleton", {}).get(k)
        if not (isinstance(v, list) and len(v) == 2):
            E.append(f"head view skeleton.{k} missing")
    fheads = {p["id"]: p for p in front["parts"] if p["id"] in head_ids(front)}
    for p in head.get("parts", []):
        if p.get("layer") == "body":
            E.append(f"head view part {p['id']}: head parts only (not layer body)")
        f = fheads.get(p["id"])
        if f and (f.get("group"), f.get("layer")) != (p.get("group"), p.get("layer")):
            W.append(f"head view part {p['id']}: group/layer differ from the front ({f.get('group')}/{f.get('layer')})")
        far = "L" if head.get("yaw", -90) > 0 else "R"   # the opposite-direction heads turn the other way
        if abs(head.get("yaw", 90)) >= 75 and re.match(rf"(eye|brow|cheek)_{far}(_|$)", p["id"]):
            W.append(f"head view part {p['id']}: the far eye / brow / cheek is not seen from the side")
    hids = {p["id"] for p in head.get("parts", [])}
    side = abs(head.get("yaw", 90)) >= 75  # the side head has no far eye / brow / cheek
    far = "L" if head.get("yaw", -90) > 0 else "R"
    fronts = {g for p in fheads.values() if (g := p.get("group")) and not (side and re.match(rf"(eye|brow|cheek)_{far}", g))}
    for g in sorted(fronts):
        want = {v for p in fheads.values() if p.get("group") == g for v in p.get("variants", [])}
        got = {v for p in head.get("parts", []) if p.get("group") == g for v in p.get("variants", [])}
        if want - got:
            E.append(f"head view group {g}: missing variants {sorted(want - got)}")
    order = head.get("order")
    if not order:
        E.append("head view: order (all parts incl. the body ids) is required")
    else:
        body = [p["id"] for p in front["parts"] if p["id"] not in fheads and not is_hand_sleeve(p)]
        miss = [i for i in list(hids) + body if i not in order]
        if miss:
            E.append(f"head view order misses {miss}")
        unknown = [i for i in order if i not in hids and i not in body and not any(i == p["id"] for p in front["parts"])]
        if unknown:
            E.append(f"head view order has unknown ids {unknown}")
    fch = {c["id"] for c in front.get("chains", []) if c.get("bone") == "head"}
    for c in head.get("chains", []):
        if c.get("bone") != "head":
            E.append(f"head view chain {c.get('id')}: bone must be head")
    for p in head.get("parts", []):
        if p.get("bone") in fch and p["bone"] not in {c["id"] for c in head.get("chains", [])}:
            E.append(f"head view part {p['id']} hangs on chain {p['bone']} but the head view has no such chain")
    return E, W


def main_view(a):
    vdir = ROOT / "public/characters" / a.id / "vector"
    front = json.loads((vdir / "vector.json").read_text(encoding="utf-8"))
    view = json.loads((vdir / f"{a.view}.json").read_text(encoding="utf-8"))
    E, W = check_view(front, view)
    if E and any("missing" in e and "skeleton" in e for e in E):
        for e in E:
            print("ERROR", e)
        sys.exit(1)
    if view.get("kind") == "head":
        # a turned head (head60 / head90) on the body drawn at the same angle (or on the front body)
        bpath = vdir / (a.body or f"body{abs(int(view.get('yaw', -90)))}.json")
        opp_body = vdir / f"body{abs(int(view.get('yaw', -90)))}_opp.json"
        if not a.body and view.get("yaw", 0) > 0 and opp_body.exists():
            bpath = opp_body   # an opposite-direction body drawn on its own
        body = json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else front_body_view(front)
        if bpath.exists() and body.get("yaw", 0) * view.get("yaw", 0) < 0:
            body = mirror_view(body)   # an opposite-direction head on the mirrored body
            print(f"head view on {bpath.name} (mirrored)")
        else:
            print(f"head view on {bpath.name if bpath.exists() else 'the front body'}")
        same = f"body{abs(int(view.get('yaw', -90)))}.json"
        if bpath.name == same and bpath.exists():
            bh, hh = body["skeleton"].get("head"), view["skeleton"].get("head")
            same = same + (" (mirrored)" if view.get("yaw", 0) > 0 else "")
            if bh and hh and max(abs(bh[0] - hh[0]), abs(bh[1] - hh[1])) > 2:
                W.append(f"head view skeleton.head {hh} differs from {same} skeleton.head {bh}: both are the same pivot on the same reference")
        art = compose_view(front, body, view)
        relax = {"far_face", "sides"} | ({"far_L"} if view.get("yaw", -90) > 0 else set())
    else:
        art = compose_view(front, view)
        relax = {"sides"} if abs(view.get("yaw", 0)) >= 45 else set()
    E2, W2 = check(art, frozenset(relax))
    E += E2
    W += W2
    err, report, _ = skill_validate(art)
    if err:
        E.append("skill validate: " + err)
    for w in W:
        print("WARN ", w)
    for e in E:
        print("ERROR", e)
    print(f"{a.id} {a.view}: {len(view.get('parts', []))} body parts, {len(E)} errors, {len(W)} warnings")
    if not a.no_render and not err:
        out = ROOT / "var/vector" / a.id / (f"check_{a.view}" + (f"_on_{Path(a.body).stem}" if view.get("kind") == "head" and a.body else ""))
        out.mkdir(parents=True, exist_ok=True)
        render_all(art, a.id, out, preview_name=f"preview_{a.view}.png")
        print("review images:", out.relative_to(ROOT))
    sys.exit(1 if E else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--json", type=Path, help="vector.json path (default: public/characters/<id>/vector/vector.json)")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--view", help="check a turned body view instead (e.g. body30: public/characters/<id>/vector/body30.json, .claude/skills/vector-avator/references/parts-spec.md §7), or a turned head (head30 / head60 / head90, §8; head30_opp etc. for the opposite direction)")
    ap.add_argument("--body", help="with --view head60/head90: the body view file to put the head on (default: the body at the same angle)")
    a = ap.parse_args()
    if a.view:
        return main_view(a)
    path = a.json or ROOT / "public/characters" / a.id / "vector/vector.json"
    art = json.loads(path.read_text(encoding="utf-8"))
    E, W = check(art)
    err, report, _ = skill_validate(art)
    if err:
        E.append("skill validate: " + err)
    elif report and report.get("warnings"):
        W += ["skill: " + w for w in report["warnings"]]
    for w in W:
        print("WARN ", w)
    for e in E:
        print("ERROR", e)
    print(f"{a.id}: {len(art.get('parts', []))} parts, {len(E)} errors, {len(W)} warnings")
    if not a.no_render and not err:
        ok, msg = skill_build(art, a.id)
        if not ok:
            print("ERROR skill build failed:", msg)
            E.append("build")
        out = ROOT / "var/vector" / a.id / "check"
        out.mkdir(parents=True, exist_ok=True)
        render_all(art, a.id, out)
        print("review images:", out.relative_to(ROOT))
    sys.exit(1 if E else 0)


if __name__ == "__main__":
    main()
