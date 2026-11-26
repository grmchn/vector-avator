"""Gesture vocabulary with variations for the explainer presenter.

Writes data/motions/explainer_vocab/<name>.json: for every gesture tag of the scripts two or
more variations, made from the hand-keyed gestures of id013 (copied, mirrored left/right,
scaled) and a few new hand-keyed ones (docs/motion-rules.md: weight shift toward the active
side M1, the face follows the hand M3).

usage: .venv/bin/python tools/explainer/make_vocab.py
"""
import copy, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/motions"
OUT = ROOT / "data/motions/explainer_vocab"
ARM = ("UpperArm", "LowerArm", "Hand", "Shoulder")
REST = {"leftUpperArm": [0, 0, -70], "leftLowerArm": [0, 0, -5], "rightUpperArm": [0, 0, 70], "rightLowerArm": [0, 0, 5]}


def load(name):
    return json.load(open(SRC / f"{name}.json"))


def swap(name):
    if name.startswith("left"):
        return "right" + name[4:]
    if name.startswith("right"):
        return "left" + name[5:]
    return name


def mirror(m):
    """Left/right mirror (x -> -x): bones swap sides, euler (x, y, z) -> (x, -y, -z)."""
    m = copy.deepcopy(m)
    for k in m["keys"]:
        if "bones" in k:
            k["bones"] = {swap(b): [v[0], -v[1], -v[2]] for b, v in k["bones"].items()}
        if "hips" in k:
            k["hips"] = [-k["hips"][0], k["hips"][1], k["hips"][2]]
        if "face" in k:
            for f in ("yaw", "roll", "gazeX"):
                if f in k["face"]:
                    k["face"][f] = -k["face"][f]
        if "hands" in k:
            k["hands"] = {("R" if s == "L" else "L"): v for s, v in k["hands"].items()}
    return m


def scale(m, s):
    """Smaller / bigger: arm bones move s times as far from the rest pose, others s times."""
    m = copy.deepcopy(m)
    for k in m["keys"]:
        for b, v in k.get("bones", {}).items():
            base = REST.get(b, [0, 0, 0]) if any(a in b for a in ARM) else [0, 0, 0]
            k["bones"][b] = [round(base[i] + s * (v[i] - base[i]), 2) for i in range(3)]
        if "hips" in k:
            k["hips"] = [round(x * s, 4) for x in k["hips"]]
    return m


def named(m, name, label):
    m = copy.deepcopy(m)
    m["name"], m["label"], m["loop"] = f"vocab_{name}", f"語彙 {label}", False
    return m


def rest_key(t, **extra):
    k = {"t": t, "bones": {**REST, "chest": [0, 0, 0], "head": [0, 0, 0]}, "hips": [0, 0, 0]}
    k.update(extra)
    return k


# new hand-keyed variations ------------------------------------------------------------
EXPLAIN_BOTH = {"duration": 3.0, "keys": [
    rest_key(0, hands={"L": "open", "R": "open"}),
    {"t": 0.35, "hands": {"L": "palm", "R": "palm"}},
    {"t": 0.5, "bones": {"leftUpperArm": [0, -30, -55], "rightUpperArm": [0, 30, 55], "leftLowerArm": [0, 0, 70],
                         "rightLowerArm": [0, 0, -70], "chest": [-3, 0, 0], "head": [-2, 0, 0]}, "hips": [0, 0.004, 0]},
    {"t": 1.2, "bones": {"leftLowerArm": [0, 0, 58], "rightLowerArm": [0, 0, -82]}, "face": {"roll": 3}},
    {"t": 1.9, "bones": {"leftLowerArm": [0, 0, 78], "rightLowerArm": [0, 0, -62]}, "face": {"roll": -2}},
    {"t": 2.4, "bones": {"leftUpperArm": [0, -30, -55], "rightUpperArm": [0, 30, 55], "leftLowerArm": [0, 0, 70],
                         "rightLowerArm": [0, 0, -70], "chest": [-3, 0, 0], "head": [-2, 0, 0]}, "face": {"roll": 0}},
    {"t": 2.6, "hands": {"L": "open", "R": "open"}},
    rest_key(3.0),
]}
SPREAD_ONE_L = {"duration": 2.6, "keys": [
    rest_key(0, hands={"L": "open", "R": "open"}),
    {"t": 0.3, "bones": {"leftUpperArm": [0, 0, -76], "chest": [2, 0, 0]}},
    {"t": 0.45, "hands": {"L": "palm_up"}},
    {"t": 0.7, "bones": {"leftUpperArm": [0, -30, -22], "leftLowerArm": [0, 0, -15], "chest": [-4, 8, 0], "head": [-4, 0, 0]},
     "hips": [0.012, 0.006, 0], "face": {"yaw": 10, "roll": 3}},
    {"t": 1.8, "bones": {"leftUpperArm": [0, -30, -18], "leftLowerArm": [0, 0, -15], "chest": [-4, 8, 0], "head": [-4, 0, 0]},
     "hips": [0.012, 0.006, 0], "face": {"yaw": 8, "roll": 2}},
    {"t": 2.2, "hands": {"L": "open"}},
    rest_key(2.6, face={"yaw": 0, "roll": 0}),
]}
NOD_ONCE = {"duration": 1.4, "keys": [
    {"t": 0, "bones": {**REST, "head": [0, 0, 0], "chest": [0, 0, 0]}, "hips": [0, 0, 0], "face": {"eye": "open"}},
    {"t": 0.12, "bones": {"head": [-3, 0, 0]}},
    {"t": 0.45, "bones": {"head": [20, 0, 0], "chest": [3, 0, 0]}, "hips": [0, -0.006, 0], "face": {"eye": "half"}},
    {"t": 0.85, "bones": {"head": [0, 0, 0], "chest": [0, 0, 0]}, "hips": [0, 0, 0], "face": {"eye": "open"}},
    {"t": 1.4, "bones": {"head": [0, 0, 0]}},
]}
NOD_TILT = {"duration": 1.8, "keys": [
    {"t": 0, "bones": {**REST, "head": [0, 0, 0], "chest": [0, 0, 0]}, "hips": [0, 0, 0], "face": {"roll": 0}},
    {"t": 0.35, "bones": {"head": [12, 0, 0]}, "face": {"roll": 6}},
    {"t": 0.65, "bones": {"head": [0, 0, 0]}, "face": {"roll": 6}},
    {"t": 0.95, "bones": {"head": [12, 0, 0]}, "face": {"roll": 4}},
    {"t": 1.3, "bones": {"head": [0, 0, 0]}, "face": {"roll": 0}, "hips": [-0.008, 0, 0]},
    {"t": 1.8, "hips": [0, 0, 0]},
]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nod2 = load("nod_surprise")
    nod2 = {**nod2, "duration": 1.5, "keys": [k for k in nod2["keys"] if k["t"] <= 1.5]}
    surprise = load("nod_surprise")
    vocab = {
        "explain_r": (load("explain"), "説明（右手）"),
        "explain_l": (mirror(load("explain")), "説明（左手）"),
        "explain_both": (EXPLAIN_BOTH, "説明（両手で小さく）"),
        "spread_big": (load("spread"), "両手を広げる"),
        "spread_small": (scale(load("spread"), 0.6), "両手を小さく広げる"),
        "spread_one_l": (SPREAD_ONE_L, "片手を広げる（左）"),
        "point_r": (load("point"), "指差し（右手）"),
        "point_l": (mirror(load("point")), "指差し（左手）"),
        "point_l_small": (scale(mirror(load("point")), 0.75), "指差し（左手・低め）"),
        "nod_double": (nod2, "うなずく（2 回）"),
        "nod_once": (NOD_ONCE, "うなずく（深く 1 回）"),
        "nod_tilt": (NOD_TILT, "首をかしげてうなずく"),
        "think_r": (load("think"), "考える（右手）"),
        "think_l": (mirror(load("think")), "考える（左手）"),
        "surprise_big": (surprise, "驚く"),
        "surprise_small": (scale(surprise, 0.65), "驚く（小さく）"),
    }
    for name, (m, label) in vocab.items():
        (OUT / f"{name}.json").write_text(json.dumps(named(m, name, label), ensure_ascii=False))
    print("wrote", len(vocab), "motions to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
