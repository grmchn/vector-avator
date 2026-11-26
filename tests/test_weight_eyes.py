"""Acting features "weight" and "eyes" of the explainer presenter (docs/motion-rules.md M16, M17, M21)."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import layout as LAYOUT  # noqa: E402
import perform  # noqa: E402

LINES = [
    {"id": "L01", "start": 0.7, "end": 2.6, "expr": "smile"},
    {"id": "L02", "start": 3.3, "end": 12.7, "expr": "neutral"},
    {"id": "L03", "start": 13.5, "end": 24.4, "expr": "surprised"},
    {"id": "L04", "start": 24.7, "end": 34.8, "expr": "smile"},
]
TOTAL = 37.0


def shifts(keys):
    """(time, x) of the held weight positions (the end of each shift)."""
    xs = [(k["t"], k["hips"][0]) for k in keys]
    return [(t, x) for (t0, x0), (t, x) in zip(xs, xs[1:]) if x != x0]


def test_weight_shifts_alternate_every_few_seconds():
    keys, roll = perform.weight_keys(LINES, TOTAL, random.Random(5))
    s = shifts(keys)
    assert len(s) >= 8
    held = [(t, x) for t, x in s if x != 0.0]
    for (t0, x0), (t1, x1) in zip(held, held[1:]):
        assert x0 * x1 < 0, "the side alternates"
        assert t1 - t0 <= 4.0 + 0.8 + 1e-6, "a shift at least every few seconds"
    assert all(0.03 <= abs(x) <= 0.06 for _, x in held), "a clear weight shift, not the idle sway"
    assert keys[0]["hips"] == [0.0, 0, 0] and keys[-1]["hips"] == [0.0, 0, 0], "square at both ends"


def test_weight_tilts_the_hips_toward_the_supporting_foot_and_counters_with_the_spine():
    keys, roll = perform.weight_keys(LINES, TOTAL, random.Random(5))
    rolls = dict(roll)
    for k in keys:
        r = rolls[k["t"]]
        assert r == 0 or (r > 0) == (k["hips"][0] > 0)
        assert k["bones"]["spine"][2] == round(-r * 1.3, 2)


def test_body_turn_and_weight_share_one_hips_track():
    lay = LAYOUT.load()
    _, roll = perform.weight_keys(LINES, TOTAL, random.Random(5))
    plain = perform.body_keys(LINES, TOTAL, lay, random.Random(3))
    merged = perform.body_keys(LINES, TOTAL, lay, random.Random(3), roll_track=roll)
    yaw = sorted({k["t"]: k["bones"]["hips"][1] for k in plain}.items())
    for k in merged:
        _, y, r = k["bones"]["hips"]
        assert abs(y - perform.track_at(yaw, k["t"])) < 0.02, "the body turn is kept"
        assert abs(r - perform.track_at(roll, k["t"])) < 0.02, "the weight tilt is kept"
    assert {t for t, _ in roll} <= {k["t"] for k in merged}


def test_expression_accents():
    smile, short, surprised, neutral = (perform.expression_keys(l, l["start"] - 0.15, nxt)
                                        for l, nxt in ((LINES[3], 37.0), (LINES[0], 3.15), (LINES[2], 24.55), (LINES[1], 13.35)))
    # a smile only at the end of the line
    assert [k["face"]["expression"] for k in smile] == ["neutral", "smile"]
    assert smile[1]["t"] == round(LINES[3]["end"] - 1.2, 3)
    # a short line keeps its expression
    assert [k["face"]["expression"] for k in short] == ["smile"]
    # surprise only at the start
    assert [k["face"]["expression"] for k in surprised] == ["surprised", "neutral"]
    assert surprised[1]["t"] - surprised[0]["t"] <= 1.0 + 1e-6
    assert [k["face"]["expression"] for k in neutral] == ["neutral"]
