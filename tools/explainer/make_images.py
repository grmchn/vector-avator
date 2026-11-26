"""Make the line images of an explainer content with Codex imagegen.

  python tools/explainer/make_images.py <content dir> [--only agi,rsi] [--force] [--jobs 3]

Reads <content dir>/images.json (a common style and one prompt per visual.image id) and writes
var/explainer/images/<content id>/<image id>.png, which make_video.py / simple_compose.py pick up.
The prompts ask for no text in the images; the composer puts the content's visual.text under the
image. Uses tools/vector/sheets/make.py's codex wrapper (one image_gen call per image).
"""
import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/vector/sheets"))
import make as SHEETS  # noqa: E402


def make_one(spec, iid, out_dir):
    out = out_dir / f"{iid}.png"
    prompt = spec["style"] + "\n\n" + spec["images"][iid]
    (out_dir / f"{iid}.prompt.txt").write_text(prompt, encoding="utf-8")
    start = time.time()
    secs, r = SHEETS.run_codex(prompt, [], spec.get("size", "1536x1024"), out, out_dir / f"{iid}.codex.txt")
    if not out.exists():
        g = SHEETS.newest_generated(start)
        if g:
            shutil.copy(g, out)
    return iid, round(secs), out.exists()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    d = Path(a.dir)
    cid = json.loads((d / "content.json").read_text(encoding="utf-8"))["id"]
    spec = json.loads((d / "images.json").read_text(encoding="utf-8"))
    out_dir = ROOT / "var/explainer/images" / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = [i for i in spec["images"] if (not a.only or i in a.only.split(",")) and (a.force or not (out_dir / f"{i}.png").exists())]
    with ThreadPoolExecutor(a.jobs) as ex:
        for iid, secs, ok in ex.map(lambda i: make_one(spec, i, out_dir), ids):
            print(f"{iid}: {'ok' if ok else 'FAILED'} ({secs} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
