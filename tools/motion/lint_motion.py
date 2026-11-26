"""Check a hand-keyed motion against the motion rules (docs/motion-rules.md).

  python tools/motion/lint_motion.py data/motions/<name>.json [more.json ...] [--strict]

Counts what can be counted from the keys alone (the renderer's idle layer, saccades and blinks
are not part of the file):

  - share of the time with the neutral expression (smile eyes all the time hide the moving
    irises; rule: neutral >= 50 %)
  - the longest stretch in which the hips neither move nor tilt (a standing figure keeps shifting
    its weight; rule: <= 4 s)
  - slow floats: the hips rising over a long gap between sparse keys (the figure drifts off its
    shadow; rule: no rise > 0.01 m over a gap longer than 1 s)
  - winks (one eye closed while the other is open; rule: <= 2 per video)

Prints one line per check; --strict exits with 1 when any check fails."""
import argparse
import json
import sys
from pathlib import Path

STILL_M = 0.003       # hips travel (m) that still counts as standing still
STILL_DEG = 0.75      # hips roll (deg) that still counts as standing still
FLOAT_M = 0.01        # about 3 % of the leg: above this the feet leave the ground (vPlant=2)
FLOAT_GAP = 1.0       # s: a rise over a longer gap than this is a slow float, not a jump


def track(keys, get):
    out = []
    for k in keys:
        v = get(k)
        if v is not None:
            out.append((k["t"], v))
    return out


def held(tr, t, default):
    """Step track: the value of the last key at or before t."""
    v = default
    for kt, kv in tr:
        if kt <= t + 1e-9:
            v = kv
        else:
            break
    return v


def lin(tr, t):
    if not tr:
        return None
    if t <= tr[0][0]:
        return tr[0][1]
    for (t0, v0), (t1, v1) in zip(tr, tr[1:]):
        if t0 <= t <= t1:
            a = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            if isinstance(v0, (list, tuple)):
                return [x + (y - x) * a for x, y in zip(v0, v1)]
            return v0 + (v1 - v0) * a
    return tr[-1][1]


def lint(path: Path):
    m = json.loads(path.read_text(encoding="utf-8"))
    keys = sorted(m.get("keys", []), key=lambda k: k["t"])
    dur = float(m.get("duration") or (keys[-1]["t"] if keys else 0))
    res = []
    if dur <= 0:
        return [("duration", True, "static pose, nothing to check")]
    dt = 1 / 30
    n = max(1, int(dur / dt))
    ts = [i * dt for i in range(n + 1)]

    # 1. neutral expression share
    ex = track(keys, lambda k: (k.get("face") or {}).get("expression"))
    neutral = sum(1 for t in ts if held(ex, t, "neutral") == "neutral") / len(ts)
    shares = {}
    for t in ts:
        e = held(ex, t, "neutral")
        shares[e] = shares.get(e, 0) + 1
    detail = ", ".join(f"{e} {100 * c / len(ts):.0f}%" for e, c in sorted(shares.items(), key=lambda x: -x[1]))
    res.append(("neutral eyes >= 50%", neutral >= 0.5, detail))

    # 2. longest still stretch of the hips (position and the hips bone's roll)
    hp = track(keys, lambda k: k.get("hips"))
    def roll(k):
        r = (k.get("bones") or {}).get("hips")
        return r[2] if isinstance(r, list) else None
    hr = track(keys, roll)
    add = sorted(m.get("additive") or [], key=lambda k: k["t"])  # beat / groove layer on top
    ap_, ar_ = track(add, lambda k: k.get("hips")), track(add, roll)
    if not hp and not hr and not ap_ and not ar_:
        res.append(("hips move (still <= 4 s)", dur <= 4, f"no hips keys at all: still for the whole {dur:.1f} s"))
    else:
        best, start, ref = 0.0, 0.0, None
        for t in ts:
            p = [x + y for x, y in zip(lin(hp, t) or [0, 0, 0], lin(ap_, t) or [0, 0, 0])]
            r = (lin(hr, t) or 0.0) + (lin(ar_, t) or 0.0)
            if ref is None:
                ref = (p, r, t)
            moved = max(abs(a - b) for a, b in zip(p, ref[0])) > STILL_M or abs(r - ref[1]) > STILL_DEG
            if moved:
                ref = (p, r, t)
            best = max(best, t - ref[2])
            if best == t - ref[2]:
                start = ref[2]
        res.append(("hips move (still <= 4 s)", best <= 4.0, f"longest still stretch {best:.1f} s from {start:.1f} s"))

    # 3. slow floats between sparse hips keys
    floats = []
    for (t0, v0), (t1, v1) in zip(hp, hp[1:]):
        if t1 - t0 > FLOAT_GAP and v1[1] - v0[1] > FLOAT_M:
            floats.append(f"{t0:.2f}-{t1:.2f} s (+{v1[1] - v0[1]:.3f} m)")
    res.append(("no slow float of the hips", not floats,
                "hold the old value right before a jump: " + ", ".join(floats) if floats else "ok"))

    # 4. winks
    winks = 0
    for k in keys:
        f = k.get("face") or {}
        l, r = f.get("eyeL"), f.get("eyeR")
        if (l == "closed") != (r == "closed") and "closed" in (l, r):
            winks += 1
    res.append(("winks <= 2", winks <= 2, f"{winks} wink key(s)"))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("motions", nargs="+", type=Path)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    bad = 0
    for p in a.motions:
        print(p)
        for name, ok, detail in lint(p):
            print(f"  {'ok  ' if ok else 'WARN'} {name}: {detail}")
            bad += not ok
    sys.exit(1 if a.strict and bad else 0)


if __name__ == "__main__":
    main()
