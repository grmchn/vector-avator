"""Tests for the acting layer from semantic tags: tags + avatar package -> gestures, size, voice."""
import copy
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))
sys.path.insert(0, str(ROOT / "tools" / "avatar"))

import build_timeline as BT  # noqa: E402
import explainer_format as EF  # noqa: E402
import package as PKG  # noqa: E402
import perform  # noqa: E402

AGI = ROOT / "data/explainer/samples/agi_singularity"


def agi(char):
    c, s = EF.load_dir(AGI)
    return c, s[char]


def test_same_input_same_result():
    c, s = agi("usagi")
    pkg = PKG.load("usagi")
    assert perform.act(c, s, pkg, 94) == perform.act(c, s, pkg, 94)


def test_characters_act_differently():
    c, scripts = EF.load_dir(AGI)
    a = PKG.load("usagi")
    b = PKG.resolve({"id": "other", "acting": {"gestureScale": 1.0, "tempo": 1.3, "gestureWeights": {"think": 3.0}}})
    ra, rb = (perform.act(c, scripts["usagi"], p, 94)["lines"] for p in (a, b))
    assert {l["scale"] for l in ra} == {1.35} and {l["scale"] for l in rb} == {1.0}
    assert {l["tempo"] for l in rb} == {1.3}
    assert [l["gesture"] for l in ra] != [l["gesture"] for l in rb]


def test_gesture_weights_follow_the_package():
    c, _ = EF.load_dir(AGI)
    line = next(l for l in c["lines"] if l["id"] == "L09")    # question
    base = perform.gesture_weights(line, PKG.resolve({"id": "x"}))
    assert max(base, key=base.get) == ("nod", "nod_tilt")
    thinker = perform.gesture_weights(line, PKG.resolve({"id": "x", "acting": {"gestureWeights": {"nod": 0.2, "think": 3.0}}}))
    assert max(thinker, key=thinker.get) == ("think", None)
    # over many seeds, a strong preference wins most of the time
    picks = [perform.pick(thinker, random.Random(i))[0] for i in range(200)]
    assert picks.count("think") > 150


def test_override_demo_and_no_tag():
    c, s = agi("usagi")
    s = copy.deepcopy(s)
    s["lines"][0]["override"] = {"gesture": "think", "expr": "troubled"}
    pkg = PKG.load("usagi")
    r = perform.act(c, s, pkg)["lines"]
    assert (r[0]["gesture"], r[0]["expr"], r[0]["gesture_source"]) == ("think", "troubled", "override")
    v, sv = EF.load_dir(ROOT / "data/explainer/samples/vector_howto")
    r = {l["id"]: l for l in perform.act(v, sv["usagi"], pkg)["lines"]}
    assert r["L14"]["gesture"] == "turn" and r["L14"]["gesture_source"] == "demo"


def test_point_and_emphasis_reach_the_timeline_fields():
    c, s = agi("usagi")
    r = {l["id"]: l for l in perform.act(c, s, PKG.load("usagi"))["lines"]}
    assert r["L03"]["point_at"] == "card" and r["L03"]["emphasize"]
    assert r["L03"]["card_text"] == "AGI ＝ 汎用人工知能"


def test_habits_from_the_package():
    assert perform.habits_for("usagi") == {"beat_amp": 1.3, "beat_rate": 1.2}
    assert perform.habits_for("explainer") == perform.DEFAULT_HABITS   # not a character: as before


def test_gesture_size_scales_around_the_rest_pose():
    plain = BT.gesture_keys("explain", 1.0, 3.2)
    big = BT.gesture_keys("explain", 1.0, 3.2, amp=1.5)
    # the first key is the rest pose: unchanged
    assert big[0]["bones"]["rightUpperArm"] == plain[0]["bones"]["rightUpperArm"]
    k = next(i for i, x in enumerate(plain) if "bones" in x and x["bones"].get("rightUpperArm") not in (None, [0, 0, 70]))
    r = BT.REST["rightUpperArm"]
    for i in range(3):
        assert abs((big[k]["bones"]["rightUpperArm"][i] - r[i]) - 1.5 * (plain[k]["bones"]["rightUpperArm"][i] - r[i])) < 0.02
    fast = BT.gesture_keys("explain", 1.0, 3.2, tempo=1.3)
    assert fast[-1]["t"] < plain[-1]["t"]
