"""Put a hand template (tools/vector/hands/templates/<type>.json) on a character: the 8 left-hand
shapes are moved to skeleton.wrist_L, scaled to arms.L.width.wrist, recoloured with the
character's hand colours, and mirrored at skeleton.wrist_R for the right hand. Only the hand_*
parts of vector.json are replaced, in place (other parts, order, skeleton and arms are kept).

usage:
  python tools/vector/hands/apply.py CHAR TYPE [--out PATH] [--base #RRGGBB] [--line #..] [--pad #..] [--dry-run]

Idempotent: the parts are replaced by id, so running it twice gives the same file. Before the
first run the current vector.json is copied to var/vector/<CHAR>/hands_v1/vector.json (kept if present).
This tool only transforms coordinates and replaces colours; it never draws shapes (drawing is
Fable 5.2's job, docs/vector-parts.md 4.3).
"""
import argparse, json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "tools" / "vector" / "hands" / "templates"
ORDER = ["open", "palm", "palm_up", "point", "point_front", "fist", "peace", "thumbs_up"]
# hand colours per character (issue id081); --base/--line/--pad override
COLORS = {
    "usagi": {"base": "#FDFEFE", "line": "#C2C5CD", "pad": "#F3E3E6"},
}
# uniform hand size per character (the templates follow the approved references, whose hands are
# about 1.6-1.8 x the wrist width; the characters' sheets have smaller hands). Shape is not changed.
SCALE = {"usagi": 0.7}  # chosen against ref/front.png
# extra uniform scale per character and hand shape, on top of SCALE (owner 2026-11-21: the
# resting hand of a furry character / a twin-tail character is a little big; gesture hands keep their size)
SHAPE_SCALE = {}  # e.g. {"<id>": {"open": 0.8}}: a smaller resting hand
# inner $line shapes left out per character and hand shape (owner 2026-11-21: a furry character's peace
# reads better without finger lines). Only removes shapes; never draws.
DROP_LINES = {}  # e.g. {"<id>": ["peace"]}: hand shapes drawn without the inner lines
LABELS = {"open": "開き（力を抜いた手・手の甲側）", "palm": "手のひら", "palm_up": "手のひら上（差し出す手）",
          "point": "指差し", "point_front": "カメラへ指差し", "fist": "グー", "peace": "ピース", "thumbs_up": "いいね"}
TOKEN = re.compile(r"[MLCQZ]|-?\d+(?:\.\d+)?(?:e-?\d+)?")


def transform_d(d, ox, oy, k, mirror):
    """Template path -> canvas path: x' = ox + s*k*x, y' = oy + k*y (s = -1 when mirrored)."""
    out, i = [], 0
    for tk in TOKEN.findall(d):
        if tk.isalpha():
            out.append(tk)
            i = 0
            continue
        v = float(tk)
        v = ox + (-v if mirror else v) * k if i % 2 == 0 else oy + v * k
        out.append(f"{v:.1f}")
        i += 1
    return " ".join(out)


def hand_length(tpart):
    """Wrist -> farthest point below the wrist, in template units."""
    ys = []
    for s in tpart["shapes"]:
        nums = [float(t) for t in TOKEN.findall(s["d"]) if not t.isalpha()]
        ys += nums[1::2]
    return max(ys) if ys else 0


def build_parts(v, template, colors, cid, ttype, scale=1.0):
    sk, arms = v["skeleton"], v["arms"]
    tw = template.get("wristWidth", 100)
    old = {p["id"]: p for p in v["parts"] if p["id"].startswith("hand_")}
    tparts = {(p.get("variant") or p["id"].split("hand_L_", 1)[1]): p for p in template["parts"]}
    missing = [k for k in ORDER if k not in tparts]
    if missing:
        raise SystemExit(f"template {ttype}: missing {missing}")
    warn = []
    new = {}
    for side, mirror in (("L", False), ("R", True)):
        ox, oy = sk[f"wrist_{side}"]
        k0 = arms[side]["width"]["wrist"] / tw * scale
        for var in ORDER:
            tp = tparts[var]
            k = k0 * SHAPE_SCALE.get(cid, {}).get(var, 1.0)
            pid = f"hand_{side}_{var}"
            L = hand_length(tp) / tw * scale * SHAPE_SCALE.get(cid, {}).get(var, 1.0)
            if side == "L" and not (template.get("minLength", 0.75) <= L <= 2.0):
                warn.append(f"{var}: hand length {L:.2f} x wrist width (expected about 0.9-1.8)")
            shapes = []
            drop = var in DROP_LINES.get(cid, [])
            for s in tp["shapes"]:
                if drop and s["fill"] == "$line":
                    continue
                f = s["fill"]
                fill = colors[f[1:]] if f.startswith("$") else f
                shapes.append({"name": s.get("name", "hand"), "fill": fill, "d": transform_d(s["d"], ox, oy, k, mirror)})
            o = old.get(pid, {})
            new[pid] = {
                "id": pid,
                "label": o.get("label") or f"手・{LABELS[var]}（キャラの{'左・画面右' if side == 'L' else '右・画面左'}）",
                "parent": o.get("parent", "torso"),
                "pivot": [float(ox), float(oy)],
                "bone": o.get("bone", "leftHand" if side == "L" else "rightHand"),
                "layer": o.get("layer", "body"),
                "visible": var == "open",
                "coverage": f"手のテンプレート {ttype}（tools/vector/hands/templates/{ttype}.json）を apply.py で載せた。"
                            "手首から真下向き。手首の切り口は前腕の中まで丸く閉じてある。",
                "group": f"hand_{side}",
                "variants": [var],
                "color": colors["base"],
                "shapes": shapes,
            }
            for key in ("side", "lines"):  # which face is seen and which inner lines are drawn
                if tp.get(key):
                    new[pid][key] = tp[key]
    return new, warn


def apply(v, template, colors, cid, ttype, scale=1.0):
    """Return a new vector dict with the hand_* parts replaced (others untouched)."""
    new, warn = build_parts(v, template, colors, cid, ttype, scale)
    parts, placed = [], set()
    hand_idx = [i for i, p in enumerate(v["parts"]) if p["id"].startswith("hand_")]
    first = hand_idx[0] if hand_idx else len(v["parts"])
    for i, p in enumerate(v["parts"]):
        if i == first:
            for side in ("L", "R"):
                for var in ORDER:
                    parts.append(new[f"hand_{side}_{var}"])
                    placed.add(f"hand_{side}_{var}")
        if not p["id"].startswith("hand_"):
            parts.append(p)
    if first == len(v["parts"]):
        parts += [new[f"hand_{s}_{k}"] for s in ("L", "R") for k in ORDER]
    out = dict(v)
    out["parts"] = parts
    return out, warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char")
    ap.add_argument("type")
    ap.add_argument("--out")
    ap.add_argument("--base"); ap.add_argument("--line"); ap.add_argument("--pad")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scale", type=float, help="uniform hand size (default: rig.hands.scale of the character definition, SCALE[char] or 1.0)")
    a = ap.parse_args()
    src = ROOT / "public" / "characters" / a.char / "vector" / "vector.json"
    v = json.loads(src.read_text(encoding="utf-8"))
    template = json.loads((TEMPLATES / f"{a.type}.json").read_text(encoding="utf-8"))
    # the character definition's rig.hands (data/characters/<char>.json) wins over the tables above
    cfg = ROOT / "data" / "characters" / f"{a.char}.json"
    rh = (json.loads(cfg.read_text(encoding="utf-8")).get("rig") or {}).get("hands") or {} if cfg.is_file() else {}
    if rh.get("shapeScale"):
        SHAPE_SCALE[a.char] = rh["shapeScale"]
    if rh.get("dropLines"):
        DROP_LINES[a.char] = rh["dropLines"]
    colors = dict(template["palette"])
    colors.update(COLORS.get(a.char, {}))
    colors.update(rh.get("colors") or {})
    for k in ("base", "line", "pad"):
        if getattr(a, k):
            colors[k] = getattr(a, k)
    # a template with "charScale": false continues the arm (stick): the wrist width as it is
    scale = a.scale if a.scale is not None else rh.get("scale", SCALE.get(a.char, 1.0)) if template.get("charScale", True) else 1.0
    out, warn = apply(v, template, colors, a.char, a.type, scale)
    for w in warn:
        print("WARN", w, file=sys.stderr)
    if a.dry_run:
        print(f"{a.char}: {sum(1 for p in out['parts'] if p['id'].startswith('hand_'))} hand parts (dry run)")
        return
    dst = Path(a.out) if a.out else src
    if dst == src:
        bk = ROOT / "var" / "vector" / a.char / "hands_v1" / "vector.json"
        if not bk.exists():
            bk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, bk)
            print("backup", bk.relative_to(ROOT))
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {dst} ({a.type}, scale {scale}, colors {colors})")


if __name__ == "__main__":
    main()
