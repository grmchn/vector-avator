"""One command from the script layer to the explainer video.

  .venv/bin/python tools/explainer/make_video.py <content dir> <char> [--out OUT.mp4] [--steps tts,timeline,capture,compose]
      [--images DIR] [--force-tts] [--act-seed N] [--seed N]

  1. tts       tools/explainer/tts.py ja --content --avatar     (the package voice; existing lines are kept)
  2. timeline  tools/explainer/build_timeline.py ja --content --avatar
               (acting layer: tags -> gestures with the character's habits; G12 pointing, beats, variety, pauses)
  3. capture   tools/explainer/capture.sh (restarts the capture server so the new motion is loaded)
  4. compose   tools/explainer/simple_compose.py --avatar   (image or text card per line, subtitles)

Outputs: var/explainer/audio/<content>/<char>/, var/explainer/public/<content>_<char>/ja/
(narration, timeline, performed.json), data/motions/explainer/<content>_<char>_ja.json,
public/audio/<content>_<char>_ja.json, var/explainer/video/<content>_<char>/presenter.mp4 and the
video (default out/explainer/<content>_<char>_ja.mp4). Generated audio and videos are never committed.
Images: <content dir>/images/ or var/explainer/images/<content>/ (<visual.image>.png); a line without
its image shows the content's visual.text on a card.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv/bin/python")
STEPS = ("tts", "timeline", "capture", "compose")


def run(cmd, label):
    t = time.time()
    print(f"== {label}: {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)
    print(f"== {label} done in {time.time() - t:.0f} s", flush=True)
    return round(time.time() - t, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="script layer -> explainer video in one command")
    ap.add_argument("content")
    ap.add_argument("char")
    ap.add_argument("--out", default="")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--images", default="")
    ap.add_argument("--force-tts", action="store_true")
    ap.add_argument("--act-seed", type=int, default=94)
    ap.add_argument("--seed", type=int, default=98, help="G12 variety / pauses seed")
    ap.add_argument("--turn", choices=("on", "off"), default="off",
                    help="turned body / head drawings: on = the body turns up to 30 deg on the turned drawings; "
                         "off = front views only, the body turns at most 15 deg (a flat drawing turned further looks flat)")
    a = ap.parse_args(argv)
    steps = [s for s in a.steps.split(",") if s]
    bad = [s for s in steps if s not in STEPS]
    if bad:
        ap.error(f"unknown steps {bad}")
    cdir = Path(a.content)
    cid = json.loads((ROOT / cdir / "content.json").read_text(encoding="utf-8"))["id"]
    tag = f"{cid}_{a.char}"
    pub = ROOT / f"var/explainer/public/{tag}/ja"
    vid = ROOT / f"var/explainer/video/{tag}"
    out = Path(a.out) if a.out else ROOT / f"out/explainer/{tag}_ja.mp4"
    images = a.images or next((str(p) for p in (ROOT / cdir / "images", ROOT / f"var/explainer/images/{cid}") if p.is_dir()), "")
    t0 = time.time()
    times = {}
    if "tts" in steps:
        times["tts"] = run([PY, "tools/explainer/tts.py", "ja", "--content", cdir, "--avatar", a.char, *(["--force"] if a.force_tts else [])], "tts")
    if "timeline" in steps:
        times["timeline"] = run([PY, "tools/explainer/build_timeline.py", "ja", "--content", cdir, "--avatar", a.char,
             "--act-seed", a.act_seed, "--seed", a.seed, *(["--body-max", 30] if a.turn == "on" else [])], "timeline")
    if "capture" in steps:
        os.environ["TURN"] = "1" if a.turn == "on" else "0"
        total = json.loads((pub / "timeline.json").read_text(encoding="utf-8"))["total"]
        vid.mkdir(parents=True, exist_ok=True)
        times["capture"] = run(["bash", "tools/explainer/capture.sh", a.char, f"{tag}_ja", total, vid / "presenter.mp4"], "capture")
    if "compose" in steps:
        out.parent.mkdir(parents=True, exist_ok=True)
        times["compose"] = run([PY, "tools/explainer/simple_compose.py", "--timeline", pub / "timeline.json", "--presenter", vid / "presenter.mp4",
             "--audio", pub / "narration.wav", "--avatar", a.char, *(["--images", images] if images else []), "--out", out], "compose")
    vid.mkdir(parents=True, exist_ok=True)
    log = vid / "times.json"   # seconds per step, merged over runs (the latest run of each step wins)
    old = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else {}
    log.write_text(json.dumps({**old, **times}, indent=1) + "\n", encoding="utf-8")
    print(f"done in {time.time() - t0:.0f} s: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
