"""Measure the real angle of the MiniMax H3 turntable frames and write turned-body references.

The H3 turntable does not turn at a constant speed, and every character's video has its own
timing, so the angle_NNN.png names (taken at fixed seconds) are wrong.

The angle is measured from a pair of features that sit symmetrically left and right of the
turning axis (the two hair ribbons, the two ears). A point pair (+-x, y, z) projects to
x' = +-x cos(t) + z sin(t), so their screen distance is D cos(t). The two features are found
as a 2-means split of a colour mask inside a band of rows. Near 90 deg the two features merge
into one blob: the 90 deg frame is taken at the minimum of the distance.

The frame is then mapped to the front reference exactly as turntable.sh made the H3 input
(front.png padded to a square, scaled to 768): front px = 2 * frame px - (256, 0). The turning
axis of the video therefore keeps its place in the front drawing for every angle.

usage: python tools/vector/sheets/turn_refs.py <id> [--write 60=37,90=51] [--csv out.csv] [--other]
  without --write: print the measured angle per frame and the suggested frames.
  with --write: write ref/body<angle>.png from the given 0-based frame numbers.
  --other: the other way round, from the last quarter of the turn (the character turns
  to its own left, the face to screen right); writes ref/body<angle>_opp.png. Characters with
  asymmetric hair need these: their keys cannot simply be mirrored.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]

# feature pair per character: colour mask and the band of rows (768 px frame)
FEATURES = {
    "usagi": {"mask": "white", "rows": (20, 150), "what": "two ears (white on the blue background)"},
}


def mask_of(a: np.ndarray, kind: str) -> np.ndarray:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    if kind == "red":
        return (r > 180) & (g < 90) & (b < 140)
    if kind == "white":
        return (r > 238) & (g > 238) & (b > 238)
    if kind == "warm":
        return (r >= b + 3) & (r > 200)
    if kind == "pale_pink":
        r_, g_, b_ = r.astype(int), g.astype(int), b.astype(int)
        return (r_ > 225) & (g_ > 165) & (g_ < 215) & (b_ > 150) & (b_ < 210) & (r_ - g_ > 25)
    raise ValueError(kind)


def separation(a: np.ndarray, kind: str, rows: tuple[int, int]) -> float:
    m = mask_of(a, kind)
    m[: rows[0]] = False
    m[rows[1]:] = False
    xs = np.nonzero(m)[1]
    if len(xs) < 20:
        return float("nan")
    c = [np.percentile(xs, 5), np.percentile(xs, 95)]
    for _ in range(30):
        lab = np.abs(xs - c[0]) > np.abs(xs - c[1])
        c = [xs[~lab].mean() if (~lab).any() else c[0], xs[lab].mean() if lab.any() else c[1]]
    return float(c[1] - c[0])


def frames(video: Path) -> list[np.ndarray]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vsync", "0", f"{td}/f%03d.png"], check=True)
        return [np.asarray(Image.open(p).convert("RGB")).astype(int) for p in sorted(Path(td).glob("f*.png"))]


def measure(cid: str, fs: list[np.ndarray], other: bool = False, f: dict | None = None) -> list[tuple[int, float, float]]:
    """(frame, separation, angle deg) for the first quarter turn (until the minimum); with
    other, for the last quarter (from the minimum of the second half to the end, back to the
    front), the frame numbers still counted from the start of the video."""
    f = f or FEATURES[cid]
    if not other:
        seps = [separation(a, f["mask"], f["rows"]) for a in fs[: len(fs) // 2]]
        s0 = seps[0]
        imin = int(np.nanargmin(seps))
        out = []
        for i, s in enumerate(seps):
            ang = 90.0 if i >= imin else float(np.degrees(np.arccos(np.clip(s / s0, -1, 1))))
            out.append((i, s, ang))
        return out
    h = len(fs) // 2
    seps = [separation(a, f["mask"], f["rows"]) for a in fs[h:]]
    s0 = separation(fs[0], f["mask"], f["rows"])
    imin = int(np.nanargmin(seps))
    out = []
    for i, s in enumerate(seps):
        ang = 90.0 if i <= imin else float(np.degrees(np.arccos(np.clip(s / s0, -1, 1))))
        out.append((h + i, s, ang))
    return out


def to_front(frame: np.ndarray) -> Image.Image:
    im = Image.fromarray(frame.astype(np.uint8)).resize((1536, 1536), Image.LANCZOS)
    return im.crop((256, 0, 256 + 1024, 1536))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--write", default="")
    ap.add_argument("--csv", default="")
    ap.add_argument("--other", action="store_true")
    ap.add_argument("--mask", choices=("red", "white", "warm", "pale_pink"),
                    help="colour of the feature pair (a character not in FEATURES); with --rows")
    ap.add_argument("--rows", type=int, nargs=2, metavar=("TOP", "BOTTOM"),
                    help="band of rows of the 768 px frame holding the feature pair (e.g. the two ears)")
    a = ap.parse_args()
    feat = {"mask": a.mask, "rows": tuple(a.rows)} if a.mask and a.rows else FEATURES.get(a.id)
    if not feat:
        ap.error(f"{a.id} is not in FEATURES: give --mask and --rows for a left/right feature pair")
    ref = ROOT / f"public/characters/{a.id}/vector/ref"
    fs = frames(ref / "turntable.mp4")
    rows = measure(a.id, fs, a.other, feat)
    by_frame = {r[0]: r for r in rows}
    if a.csv:
        Path(a.csv).write_text("frame,separation,angle\n" + "".join(f"{i},{s:.1f},{g:.1f}\n" for i, s, g in rows))
    for target in (30, 45, 60, 75, 90):
        best = min(rows, key=lambda r: (abs(r[2] - target), -r[0] if a.other else r[0]))
        print(f"{a.id}: {target:>2} deg -> frame {best[0]} (measured {best[2]:.1f} deg)")
    for kv in filter(None, a.write.split(",")):
        ang, fr = kv.split("=")
        out = ref / (f"body{int(ang)}_opp.png" if a.other else f"body{int(ang)}.png")
        to_front(fs[int(fr)]).save(out)
        print("wrote", out.relative_to(ROOT), "from frame", fr, f"({by_frame[int(fr)][2]:.1f} deg)" if int(fr) in by_frame else "")


if __name__ == "__main__":
    main()
