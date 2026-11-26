"""Tests for the acting layer of the explainer presenter (G12: id096-id098):
layout mapping, pointing keys, beat selection, gesture variations and pauses."""
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import beats as BEATS  # noqa: E402
import layout as LAYOUT  # noqa: E402
import perform  # noqa: E402


def test_layout_round_trip_and_presenter_centre():
    lay = LAYOUT.load()
    for X, Y in [(0, 0), (960, 540), (1800, 1000), (500, 300)]:
        u, v = LAYOUT.screen_to_view(lay, X, Y)
        X2, Y2 = LAYOUT.view_to_screen(lay, u, v)
        assert abs(X - X2) < 1e-6 and abs(Y - Y2) < 1e-6
    # the centre of the presenter's canvas sits at presenter.cx on screen
    X, _ = LAYOUT.view_to_screen(lay, 0.5, 0.5)
    assert abs(X - lay["presenter"]["cx"] * lay["size"][0]) < 1e-6


def test_point_keys_use_the_arm_on_the_target_side_and_return():
    lay = LAYOUT.load()
    for region, side in [("card", "L"), ("tl", "R")]:
        keys = perform.point_keys(region, 1.0, 3.0, 4.0, lay)
        ts = [k["t"] for k in keys]
        assert ts == sorted(ts) and ts[0] == 1.0 and ts[-1] <= 4.0
        reach = [k["reach"][side] for k in keys if "reach" in k]
        assert reach[0][2] == 0 and reach[-1][2] == 0 and max(r[2] for r in reach) == 1
        assert any(k.get("hands", {}).get(side) == "point" for k in keys)
        # the face comes back to the viewer before the arm goes down
        face0 = [k for k in keys if "face" in k and k["face"].get("yaw") == 0]
        assert face0[-1]["t"] < ts[-1]


def test_beat_selection_keeps_the_gap_cap_and_busy_windows():
    rng = np.random.default_rng(0)
    cands = [{"t": float(t), "score": float(s), "kind": ["onset"]} for t, s in zip(np.linspace(0, 5, 40), rng.random(40))]
    got = BEATS.select(cands, 0.0, 5.0, "mid", busy=[(0, 0.6), (4.4, 5.0)])
    ts = [c["t"] for c in got]
    assert all(b - a >= BEATS.LEVELS["mid"]["gap"] - 1e-9 for a, b in zip(ts, ts[1:]))
    assert len(got) <= round(5.0 * BEATS.LEVELS["mid"]["rate"])
    assert all(not (0 <= t <= 0.6 or 4.4 <= t <= 5.0) for t in ts)
    assert BEATS.select(cands, 0.0, 5.0, "off") == []


def test_beats_follow_a_synthetic_voice():
    # three loud syllables at 0.3, 1.2 and 2.1 s on a quiet floor
    sr = BEATS.SR
    x = np.zeros(int(2.6 * sr), dtype=np.float32)
    t = np.arange(int(0.25 * sr)) / sr
    for s in (0.3, 1.2, 2.1):
        i = int(s * sr)
        x[i:i + len(t)] += 0.5 * np.sin(2 * np.pi * 220 * t)
    c = BEATS.candidates(x, 10.0, [(10.3, 10.55), (11.2, 11.45), (12.1, 12.35)])
    on = [k["t"] for k in c if "onset" in k["kind"]]
    for s in (10.3, 11.2, 12.1):
        assert min(abs(o - s) for o in on) < 0.06


def test_beat_keys_lead_the_voice_and_come_back():
    keys = perform.beat_keys([{"t": 2.0, "kind": ["onset"]}], {"head", "R"}, 1.0, lead=0.12)
    assert [k["t"] for k in keys] == [1.78, 1.88, 2.14]
    assert keys[0]["bones"]["head"] == [0, 0, 0] and keys[-1]["bones"]["head"] == [0, 0, 0]
    assert keys[1]["bones"]["head"][0] > 0 and "rightLowerArm" in keys[1]["bones"]


def test_chooser_never_repeats_and_alternates_sides():
    ch = perform.GestureChooser(random.Random(1))
    prev = None
    sides = []
    for tag in ["explain", "explain", "explain", "explain", "spread", "spread", "point", "point"]:
        name, side = ch.choose(tag)
        assert name != prev
        prev = name
        if tag == "explain" and side in ("L", "R"):
            sides.append(side)
    assert all(a != b for a, b in zip(sides, sides[1:]))
    # every tag has at least two variations, and the files exist
    for tag, opts in perform.VOCAB.items():
        assert len(opts) >= 2
        for name, _ in opts:
            assert (ROOT / f"data/motions/explainer_vocab/{name}.json").exists(), name
    # the preferred side wins for pointing
    pc = perform.GestureChooser(random.Random(2), {"point": "L"})
    assert all(pc.choose("point")[1] == "L" for _ in range(5))


def test_jitter_keeps_the_ends_and_the_order():
    keys = [{"t": 0.0, "bones": {"head": [0, 0, 0]}}, {"t": 0.5, "bones": {"head": [10, 0, 0]}},
            {"t": 0.52, "bones": {"head": [12, 0, 0]}}, {"t": 1.0, "bones": {"head": [0, 0, 0]}}]
    for seed in range(20):
        j = perform.jitter(keys, random.Random(seed))
        assert j[0] == keys[0] and j[-1] == keys[-1]
        ts = [k["t"] for k in j]
        assert ts == sorted(ts)
        assert abs(j[1]["bones"]["head"][0] - 10) <= 2.5 and j[1]["bones"]["head"][1] == 0


def test_pause_keys_glance_at_a_new_image_unless_the_next_line_points():
    lay = LAYOUT.load()
    lines = [{"id": "L1", "scene": "a", "start": 0.7, "end": 2.0, "icon": "", "gesture": "explain", "point_at": ""},
             {"id": "L2", "scene": "b", "start": 2.8, "end": 4.0, "icon": "x", "gesture": "explain", "point_at": "card"}]
    k = perform.pause_keys(lines, 5.0, lay, random.Random(0))
    assert any(f.get("face", {}).get("gazeX", 0) > 0 for f in k)
    k2 = perform.pause_keys(lines, 5.0, lay, random.Random(0), pointing=True)
    assert not any(f.get("face", {}).get("gazeX", 0) > 0 for f in k2)
