"""Bust framing acting: props from the first meaning tag, pose runs, prop keys, arm lift."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import bust as B  # noqa: E402


def test_prop_kind_uses_the_first_tag_only():
    assert B.prop_kind(["question"]) == "question"
    assert B.prop_kind(["think"]) == "question"
    assert B.prop_kind(["introduce", "emphasize"]) == "idea"
    assert B.prop_kind(["contrast", "emphasize"]) is None   # stresses a word later: no prop
    assert B.prop_kind([]) is None


def test_pose_runs_limits_repeats():
    ids = ["a", "b", "c", "d", "e"]
    props = {"a": "question", "b": "question", "c": "question", "d": "idea", "e": "idea"}
    posed = B.pose_runs(ids, props)
    assert posed == {"a", "b", "d"}   # think twice at most, idea once in a row


def test_prop_keys_are_short_cues_on_the_first_line_of_a_run():
    tl = [{"id": "a", "start": 1.0, "end": 6.0}, {"id": "b", "start": 6.5, "end": 9.0}, {"id": "c", "start": 10.0, "end": 11.0}]
    keys = B.prop_keys(tl, {"a": "question", "b": "question", "c": "idea"})
    seq = [(k["face"]["prop"], k["face"]["propAmt"]) for k in keys]
    # a shows the question mark (b, the same run, shows none); c shows the bulb
    assert seq == [("question", 0), ("question", 1), ("question", 1), ("none", 0),
                   ("idea", 0), ("idea", 1), ("idea", 1), ("none", 0)]
    ts = [k["t"] for k in keys]
    assert ts == sorted(ts)
    assert ts[3] - ts[0] <= 3.0 + 0.15 + B.SHRINK + 1e-6   # held at most HOLD seconds
    assert ts[7] <= 11.0 + B.SHRINK + 1e-6                 # gone right after its line


def test_lift_arms_moves_away_from_rest_and_keeps_rest():
    keys = [{"t": 0, "bones": {"rightUpperArm": [0, 0, 70], "leftUpperArm": [0, 0, -70]}},
            {"t": 1, "bones": {"rightUpperArm": [0, 35, 48], "leftUpperArm": [0, -35, -48], "rightLowerArm": [0, 0, -100]}}]
    out = B.lift_arms(keys, 70.0)
    assert out[0]["bones"]["rightUpperArm"][2] == 70 and out[0]["bones"]["leftUpperArm"][2] == -70
    assert out[1]["bones"]["rightUpperArm"][2] < 48 and out[1]["bones"]["leftUpperArm"][2] > -48
    assert out[1]["bones"]["rightLowerArm"][2] < -100
    assert keys[1]["bones"]["rightUpperArm"][2] == 48   # input untouched
