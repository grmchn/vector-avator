"""Gesture size (acting.gestureScale) in build_timeline.scale_bones: Euler keys are scaled around the
rest pose; quaternion keys of the MotionBricks variants ({"q": ...}) are passed through."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import build_timeline as BT  # noqa: E402


def test_scale_bones_scales_euler_around_rest():
    out = BT.scale_bones({"spine": [0, 0, 10]}, 1.5)
    assert out["spine"] == [0, 0, 15]


def test_scale_bones_keeps_quaternion_keys():
    q = {"q": [0.0, 0.0, 0.0, 1.0]}
    out = BT.scale_bones({"hips": q, "spine": [0, 0, 10]}, 1.3)
    assert out["hips"] == q
    assert out["spine"] == [0, 0, 13]
