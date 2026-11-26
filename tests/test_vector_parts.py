"""Tests for tools/vector/check_parts.py using a tiny hand-made character.
run: .venv/bin/python -m pytest tests/test_vector_parts.py -q
"""
import copy, importlib.util, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_parts", ROOT / "tools/vector/check_parts.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def ellipse(cx, cy, rx, ry):
    k = 0.5523
    return (f"M {cx - rx} {cy} C {cx - rx} {cy - k * ry} {cx - k * rx} {cy - ry} {cx} {cy - ry} "
            f"C {cx + k * rx} {cy - ry} {cx + rx} {cy - k * ry} {cx + rx} {cy} "
            f"C {cx + rx} {cy + k * ry} {cx + k * rx} {cy + ry} {cx} {cy + ry} "
            f"C {cx - k * rx} {cy + ry} {cx - rx} {cy + k * ry} {cx - rx} {cy} Z")


def part(pid, cx, cy, rx, ry, fill="#FFFFFF", bone="head", layer="feature", parent="head", **kw):
    p = {"id": pid, "label": pid, "parent": parent, "pivot": [cx, cy], "visible": True,
         "coverage": "test", "bone": bone, "layer": layer,
         "shapes": [{"name": "fill", "d": ellipse(cx, cy, rx, ry), "fill": fill}]}
    p.update(kw)
    return p


def mini():
    parts = [
        part("leg_L", 560, 1250, 40, 120, bone="leftUpperLeg", layer="body", parent="torso"),
        part("leg_R", 464, 1250, 40, 120, bone="rightUpperLeg", layer="body", parent="torso"),
        part("torso", 512, 1050, 120, 160, bone="chest", layer="body", parent=None),
        part("neck", 512, 880, 40, 40, bone="neck", layer="body", parent="torso"),
        part("head", 512, 650, 260, 230, layer="head", parent="neck"),
        part("nose", 512, 700, 12, 8, fill="#D24A32"),
    ]
    for s, x in (("L", 600), ("R", 424)):
        parts += [
            part(f"eye_{s}_white", x, 640, 40, 55, group=f"eye_{s}", variants=["open", "half"]),
            part(f"eye_{s}_iris", x, 645, 30, 42, fill="#5FCDF8", group=f"eye_{s}", variants=["open", "half"],
                 clipTo=f"eye_{s}_white"),
            part(f"eye_{s}_pupil", x, 650, 12, 22, fill="#111111", group=f"eye_{s}", variants=["open", "half"],
                 clipTo=f"eye_{s}_white"),
            part(f"eye_{s}_lash", x, 590, 36, 6, fill="#333333", group=f"eye_{s}", variants=["open"]),
            dict(part(f"eye_{s}_half", x, 615, 42, 30, fill="#F4F4F4", group=f"eye_{s}", variants=["half"]), visible=False),
            dict(part(f"eye_{s}_closed", x, 650, 36, 5, fill="#333333", group=f"eye_{s}", variants=["closed"]), visible=False),
        ]
        for k in ("open", "point", "fist", "palm"):
            parts.append(dict(part(f"hand_{s}_{k}", 720 if s == "L" else 304, 1160, 28, 34,
                                   bone=("left" if s == "L" else "right") + "Hand", layer="body", parent="torso",
                                   group=f"hand_{s}", variants=[k]), visible=(k == "open")))
    for k in ("closed", "a", "i", "u", "e", "o", "smile", "surprise", "trouble"):
        parts.append(dict(part(f"mouth_{k}", 520, 740, 24, 10, fill="#E58A9A", group="mouth", variants=[k]),
                          visible=(k == "closed")))
    return {
        "schema_version": 1, "format": "so-chara-vector/1", "character": "mini", "width": 1024, "height": 1536,
        "parts": parts,
        "skeleton": {"hips": [512, 1150], "chest": [512, 1000], "neck": [512, 900], "head": [512, 870],
                     "head_center": [512, 650], "head_radius": [260, 230],
                     "shoulder_L": [610, 930], "elbow_L": [670, 1030], "wrist_L": [720, 1130],
                     "shoulder_R": [414, 930], "elbow_R": [354, 1030], "wrist_R": [304, 1130],
                     "hip_L": [560, 1150], "hip_R": [464, 1150], "ankle_L": [560, 1360], "ankle_R": [464, 1360]},
        "arms": {s: {"width": {"shoulder": 50, "elbow": 40, "wrist": 32},
                     "bands": [{"from": 0, "to": 1, "color": "#FFFFFF"}],
                     "shade": {"color": "#E2E4EA", "side": "under", "ratio": 0.3}, "attach": "torso"} for s in "LR"},
        "chains": [],
        "parallax": {"head": 0.0, "feature": 0.3},
        "expressions": {e: {"eye": "open", "mouth": m} for e, m in
                        (("normal", "closed"), ("smile", "smile"), ("surprise", "surprise"), ("trouble", "trouble"))},
        "qa": [{"name": "reveal_head", "kind": "reveal", "hide": ["nose"], "check": "t"},
               {"name": "move_head", "kind": "move", "transforms": {"head": {"deg": 5}}, "check": "t"}],
    }


def test_valid_character_has_no_errors():
    E, W = cp.check(mini())
    assert E == [], E


def test_skill_validator_accepts_the_superset():
    err, report, _ = cp.skill_validate(mini())
    assert err is None, err
    assert report["parts"] == len(mini()["parts"])


def test_stroke_is_rejected():
    a = mini()
    a["parts"][0]["shapes"][0].update(stroke="#000000", width=4)
    E, _ = cp.check(a)
    assert any("stroke" in e for e in E)


def test_left_right_is_the_characters_own_side():
    a = mini()
    for p in a["parts"]:  # mirror everything: _L ends up on the screen left
        if p["id"].startswith("eye_L") or p["id"].startswith("eye_R"):
            p["shapes"][0]["d"] = ellipse(1024 - p["pivot"][0], p["pivot"][1], 30, 40)
    E, _ = cp.check(a)
    assert any("wrong side" in e for e in E)


def test_missing_required_and_bad_expression():
    a = mini()
    a["parts"] = [p for p in a["parts"] if p["id"] != "mouth_o"]
    a["expressions"]["smile"]["eye"] = "smile"
    E, _ = cp.check(a)
    assert any("mouth_o" in e for e in E)
    assert any("expressions.smile.eye" in e for e in E)


def test_default_variant_must_be_unique():
    a = mini()
    for p in a["parts"]:
        if p["id"] == "mouth_a":
            p["visible"] = True
    E, _ = cp.check(a)
    assert any("group mouth" in e for e in E)


def test_render_transforms_rotate_about_pivot():
    a = mini()
    get = cp.matrices(a, {"head": {"deg": 90}})
    m = get("head")
    px, py = a["parts"][4]["pivot"]  # head pivot is a fixed point
    x = m[0] * px + m[2] * py + m[4]
    y = m[1] * px + m[3] * py + m[5]
    assert math.isclose(x, px, abs_tol=1e-6) and math.isclose(y, py, abs_tol=1e-6)


def add_hands(a, kinds):
    """add hand drawings (hidden variants) of the given kinds for both sides"""
    for s in "LR":
        for k in kinds:
            a["parts"].append(dict(part(f"hand_{s}_{k}", 720 if s == "L" else 304, 1160, 28, 34,
                                        bone=("left" if s == "L" else "right") + "Hand", layer="body", parent="torso",
                                        group=f"hand_{s}", variants=[k]), visible=False))
    return a


def test_legacy_hand_set_is_a_warning_only():
    E, W = cp.check(mini())
    assert not any("hand" in e for e in E)
    assert any("legacy hand set" in w and "palm_up" in w for w in W)


def test_full_hand_set_passes():
    a = add_hands(mini(), ("palm_up", "point_front", "peace", "thumbs_up"))
    E, W = cp.check(a)
    assert not any("hand" in e for e in E), E
    assert not any("legacy hand set" in w for w in W)


def test_partial_new_hand_set_is_an_error():
    a = add_hands(mini(), ("palm_up",))  # one of the new shapes: all of them are now required
    E, _ = cp.check(a)
    for k in ("peace", "thumbs_up", "point_front"):
        assert any(f"hand_L_{k}" in e for e in E), k


def test_point_front_alone_keeps_the_legacy_set():
    a = add_hands(mini(), ("point_front",))
    E, W = cp.check(a)
    assert not any("hand" in e for e in E)
    assert any("legacy hand set" in w for w in W)
