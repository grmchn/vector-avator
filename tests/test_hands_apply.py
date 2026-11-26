"""Tests for tools/vector/hands/apply.py: colour tokens, mirroring, placement,
idempotence, and that only the hand_* parts change."""
import copy, importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hands_apply", ROOT / "tools" / "vector" / "hands" / "apply.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)

ORDER = ap.ORDER


def template():
    parts = []
    for v in ORDER:
        parts.append({"id": f"hand_L_{v}", "variant": v, "shapes": [
            {"name": "hand", "fill": "$base", "d": "M -50 -20 L 50 -20 L 40 100 L 10 110 Z"},
            {"name": "mark", "fill": "$line", "d": "M 20 60 L 30 60 L 30 90 Z"}]})
    return {"type": "t", "wristWidth": 100, "palette": {"base": "#111111", "line": "#222222", "pad": "#333333"}, "parts": parts}


def character():
    parts = [{"id": "torso", "shapes": [{"name": "a", "fill": "#ABCDEF", "d": "M 0 0 L 1 1 Z"}]}]
    for s in ("L", "R"):
        for v in ("open", "point", "fist", "palm"):
            parts.append({"id": f"hand_{s}_{v}", "label": f"old {s} {v}", "parent": "torso", "pivot": [0, 0],
                          "bone": "leftHand" if s == "L" else "rightHand", "layer": "body", "visible": v == "open",
                          "group": f"hand_{s}", "variants": [v], "shapes": [{"name": "x", "fill": "#FFFFFF", "d": "M 0 0 L 1 1 Z"}]})
    parts.append({"id": "arm_cover", "shapes": [{"name": "a", "fill": "#000000", "d": "M 0 0 L 1 1 Z"}]})
    return {"parts": parts, "skeleton": {"wrist_L": [700, 1000], "wrist_R": [300, 1000]},
            "arms": {"L": {"width": {"wrist": 50}}, "R": {"width": {"wrist": 50}}}}


COLORS = {"base": "#FAFAFA", "line": "#C0C0C0", "pad": "#F0D0D0"}


def nums(d):
    return [float(t) for t in ap.TOKEN.findall(d) if not t.isalpha()]


def run(v=None):
    out, warn = ap.apply(v or character(), template(), COLORS, "x", "t")
    return out, warn


def test_colors_replaced():
    out, _ = run()
    p = next(p for p in out["parts"] if p["id"] == "hand_L_open")
    assert [s["fill"] for s in p["shapes"]] == ["#FAFAFA", "#C0C0C0"]
    assert p["color"] == "#FAFAFA"


def test_placement_and_scale():
    out, _ = run()
    p = next(p for p in out["parts"] if p["id"] == "hand_L_open")
    n = nums(p["shapes"][0]["d"])
    # (-50,-20) * 0.5 + (700,1000)
    assert n[:2] == [675.0, 990.0]
    assert p["pivot"] == [700.0, 1000.0]


def test_right_is_mirrored():
    out, _ = run()
    L = nums(next(p for p in out["parts"] if p["id"] == "hand_L_point")["shapes"][1]["d"])
    R = nums(next(p for p in out["parts"] if p["id"] == "hand_R_point")["shapes"][1]["d"])
    for i in range(0, len(L), 2):
        assert R[i] - 300 == -(L[i] - 700)
        assert R[i + 1] == L[i + 1]


def test_all_16_and_visibility():
    out, _ = run()
    hands = [p for p in out["parts"] if p["id"].startswith("hand_")]
    assert len(hands) == 16
    assert {p["id"] for p in hands if p["visible"]} == {"hand_L_open", "hand_R_open"}
    # label kept from the old part
    assert next(p for p in hands if p["id"] == "hand_L_fist")["label"] == "old L fist"


def test_other_parts_unchanged_and_order():
    v = character()
    out, _ = run(copy.deepcopy(v))
    others = [p for p in out["parts"] if not p["id"].startswith("hand_")]
    assert others == [p for p in v["parts"] if not p["id"].startswith("hand_")]
    ids = [p["id"] for p in out["parts"]]
    assert ids[0] == "torso" and ids[-1] == "arm_cover"
    assert out["skeleton"] == v["skeleton"] and out["arms"] == v["arms"]


def test_idempotent():
    once, _ = run()
    twice, _ = ap.apply(copy.deepcopy(once), template(), COLORS, "x", "t")
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)


def test_length_warning():
    t = template()
    t["parts"][0]["shapes"][0]["d"] = "M -50 -20 L 50 -20 L 0 260 Z"
    _, warn = ap.apply(character(), t, COLORS, "x", "t")
    assert any("open" in w for w in warn)


def test_side_and_lines_copied():
    t = template()
    t["parts"][0]["side"] = "back"; t["parts"][0]["lines"] = "none"
    out, _ = ap.apply(character(), t, COLORS, "x", "t")
    for pid in ("hand_L_open", "hand_R_open"):
        p = next(p for p in out["parts"] if p["id"] == pid)
        assert p["side"] == "back" and p["lines"] == "none"


def test_uniform_scale():
    out, _ = ap.apply(character(), template(), COLORS, "x", "t", scale=0.5)
    n = nums(next(p for p in out["parts"] if p["id"] == "hand_L_open")["shapes"][0]["d"])
    # (-50,-20) * 0.5 (wrist 50/100) * 0.5 (scale) + (700,1000)
    assert n[:2] == [687.5, 995.0]


def test_drop_lines_per_character(monkeypatch):
    monkeypatch.setitem(ap.DROP_LINES, "x", ["peace"])
    out, _ = ap.apply(character(), template(), COLORS, "x", "t")
    peace = next(p for p in out["parts"] if p["id"] == "hand_L_peace")
    assert [s["fill"] for s in peace["shapes"]] == ["#FAFAFA"]
    other = next(p for p in out["parts"] if p["id"] == "hand_L_point")
    assert "#C0C0C0" in [s["fill"] for s in other["shapes"]]


def test_shape_scale(monkeypatch):
    monkeypatch.setitem(ap.SHAPE_SCALE, "x", {"open": 0.5})
    out, _ = ap.apply(character(), template(), COLORS, "x", "t")
    o = nums(next(p for p in out["parts"] if p["id"] == "hand_L_open")["shapes"][0]["d"])
    f = nums(next(p for p in out["parts"] if p["id"] == "hand_L_fist")["shapes"][0]["d"])
    assert o[:2] == [687.5, 995.0] and f[:2] == [675.0, 990.0]
