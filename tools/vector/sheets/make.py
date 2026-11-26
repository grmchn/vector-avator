"""Generate vector-style reference images (front standing pose, character sheets) with
Codex imagegen, in the same way for every character.

The prompt is composed from three files:
  style_base.md            common art style
  characters/<id>.md       character-specific notes (traits to keep, overrides)
  layouts/<kind>.md        what to draw (front | restyle | sheet_turnaround | sheet_face | sheet_front | clean)
                           clean: remove backgrounds, captions and props from a busy original (no common style;
                           pass the original with --ref; the result is used as an "original" reference)
                           sheet_front: sheet 1 for characters that only need the front body (front pose + hands)

usage:
  python tools/vector/sheets/make.py gen <id> <kind> [--count N] [--note TEXT] [--ref PATH=ROLE ...]
  python tools/vector/sheets/make.py adopt <id> <kind> <NN>
  python tools/vector/sheets/make.py log <id>

Attempts go to var/vector/<id>/gen/<kind>_<NN>.png (+ .prompt.txt, .json).
Adopted images are copied to public/characters/<id>/vector/ref/<kind>.png.
"""
import argparse, glob, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SIZES = {"clean": "1536x1024", "sheet_front": "1536x1024", "front": "1024x1536", "restyle": "1024x1536", "sheet_turnaround": "1536x1024", "sheet_face": "1536x1024"}
RAW_KINDS = {"clean"}  # kinds that keep the original look: no common style, no character notes, no default refs
ANGLE_ROLE = "a frame of a 360-degree turntable video of the same character ({}); use it only to understand the 3D shape at that angle"


def char_conf(cid):
    return json.loads((HERE / "characters" / f"{cid}.json").read_text(encoding="utf-8"))


def gen_dir(cid):
    d = ROOT / "var" / "vector" / cid / "gen"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ref_dir(cid):
    d = ROOT / "public" / "characters" / cid / "vector" / "ref"
    d.mkdir(parents=True, exist_ok=True)
    return d


def references(cid, kind, extra, angles=True):
    """Ordered list of (path, role). Character originals first, then generated references."""
    conf = char_conf(cid)
    roles = conf.get("roles", {})
    refs = [] if kind in RAW_KINDS else \
        [(p, roles.get(p, "the original character design")) for p in conf["refs"]["original"]]
    rd = ref_dir(cid)
    if kind.startswith("sheet"):
        if (rd / "front.png").exists():
            refs.append((str((rd / "front.png").relative_to(ROOT)),
                         "the adopted front standing pose in the target style (main reference for colors and shapes)"))
        for deg in (45, 90, 180):
            p = rd / f"angle_{deg:03d}.png"
            if angles and p.exists():
                refs.append((str(p.relative_to(ROOT)), ANGLE_ROLE.format(f"{deg} degrees")))
        for sheet1 in ("sheet_turnaround.png", "sheet_front.png"):
            if kind == "sheet_face" and (rd / sheet1).exists():
                refs.append((str((rd / sheet1).relative_to(ROOT)),
                             "sheet 1 of the same character (keep the head identical to it)"))
    for e in extra:
        path, _, role = e.partition("=")
        refs.append((path, role or "additional reference"))
    return refs


def compose(cid, kind, note):
    parts = [] if kind in RAW_KINDS else \
        [(HERE / "style_base.md").read_text(encoding="utf-8").split("-->", 1)[-1].strip(),
         (HERE / char_conf(cid)["notes"]).read_text(encoding="utf-8").strip()]
    parts.append((HERE / "layouts" / f"{kind}.md").read_text(encoding="utf-8").strip())
    if note:
        parts.append("【今回の追加指示】\n" + note.strip())
    return "\n\n".join(parts) + "\n"


def next_index(d, kind):
    nums = [int(Path(p).stem.rsplit("_", 1)[1]) for p in glob.glob(str(d / f"{kind}_[0-9][0-9].png"))]
    return max(nums, default=0) + 1


def run_codex(prompt, refs, size, out_png, log_txt):
    lines = ["Use the imagegen skill with the built-in image_gen tool (do not use the CLI fallback, "
             "do not draw the image with code).",
             "Attached images:"]
    for i, (p, role) in enumerate(refs, 1):
        lines.append(f"- Image {i} ({os.path.basename(p)}): {role}")
    lines += [f"Make exactly 1 image_gen call, size {size}, using the attached images as references, "
              "with the PROMPT below passed verbatim (it is written in Japanese).",
              f"After it finishes, copy the generated PNG from $CODEX_HOME/generated_images/ to {out_png} "
              "and reply with that path only.",
              "PROMPT:", prompt]
    env = dict(os.environ, PATH=codex_path())
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(ROOT)]
    for p, _ in refs:
        cmd += ["-i", str(ROOT / p)]
    cmd += ["-o", str(log_txt), "-"]
    t0 = time.time()
    r = subprocess.run(cmd, input="\n".join(lines), text=True, capture_output=True, env=env)
    return time.time() - t0, r


def codex_path():
    """PATH with the codex CLI on it: as is, or with the newest nvm Node's bin added
    (non-interactive shells often lack the nvm PATH)."""
    path = os.environ.get("PATH", "")
    if shutil.which("codex", path=path):
        return path
    bins = sorted(Path.home().glob(".nvm/versions/node/*/bin"), key=lambda p: p.stat().st_mtime, reverse=True)
    for b in bins:
        if (b / "codex").exists():
            return f"{b}:{path}"
    sys.exit("codex CLI not found: install it (npm i -g @openai/codex) and log in (codex login)")


def newest_generated(after):
    cands = [p for p in CODEX_HOME.glob("generated_images/**/*.png") if p.stat().st_mtime >= after]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def cmd_gen(a):
    d = gen_dir(a.id)
    for _ in range(a.count):
        n = next_index(d, a.kind)
        stem = d / f"{a.kind}_{n:02d}"
        prompt = compose(a.id, a.kind, a.note)
        refs = references(a.id, a.kind, a.ref, not a.no_angles)
        stem.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
        out_png = stem.with_suffix(".png")
        start = time.time()
        secs, r = run_codex(prompt, refs, SIZES[a.kind], out_png, stem.with_suffix(".codex.txt"))
        if not out_png.exists():
            g = newest_generated(start)
            if g:
                shutil.copy(g, out_png)
        meta = {"id": a.id, "kind": a.kind, "n": n, "seconds": round(secs), "size": SIZES[a.kind],
                "refs": refs, "note": a.note, "angles": not a.no_angles, "ok": out_png.exists(), "returncode": r.returncode,
                "date": time.strftime("%Y-%m-%d %H:%M")}
        stem.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if not out_png.exists():
            sys.stderr.write(r.stdout[-2000:] + r.stderr[-2000:])
        print(f"{out_png.relative_to(ROOT)} ok={meta['ok']} {meta['seconds']}s")


def normalize_front(src, dst, size=(1024, 1536)):
    """Scale the image to cover 1024x1536 and crop the centre. If the cropped margins are not
    plain background, pad instead (the character must never be cut)."""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    W, H = size
    s = max(W / im.width, H / im.height)
    big = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x0, y0 = (big.width - W) // 2, (big.height - H) // 2
    bg = big.getpixel((2, 2))
    def plain(box):
        if box[2] <= box[0] or box[3] <= box[1]:
            return True
        px = big.crop(box).get_flattened_data()
        return all(sum(abs(c - b) for c, b in zip(p, bg)) < 40 for p in px)
    if plain((0, 0, x0, big.height)) and plain((x0 + W, 0, big.width, big.height)) \
            and plain((0, 0, big.width, y0)) and plain((0, y0 + H, big.width, big.height)):
        out = big.crop((x0, y0, x0 + W, y0 + H))
    else:
        s = min(W / im.width, H / im.height)
        small = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        out = Image.new("RGB", size, im.getpixel((2, 2)))
        out.paste(small, ((W - small.width) // 2, (H - small.height) // 2))
    out.save(dst)


def cmd_adopt(a):
    src = gen_dir(a.id) / f"{a.kind}_{int(a.n):02d}.png"
    name = a.as_name or ("front" if a.kind == "restyle" else a.kind)
    dst = ref_dir(a.id) / f"{name}.png"
    if name == "front":
        normalize_front(src, dst)
    else:
        shutil.copy(src, dst)
    log = ref_dir(a.id) / "adopted.json"
    data = json.loads(log.read_text()) if log.exists() else {}
    data[name] = {"from": str(src.relative_to(ROOT)), "date": time.strftime("%Y-%m-%d %H:%M")}
    log.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print("adopted", dst.relative_to(ROOT))


def cmd_log(a):
    for p in sorted(gen_dir(a.id).glob("*.json")):
        m = json.loads(p.read_text())
        print(f"{p.stem:24s} ok={m['ok']!s:5s} {m['seconds']:4d}s  {m.get('note') or ''}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen"); g.add_argument("id"); g.add_argument("kind", choices=list(SIZES))
    g.add_argument("--count", type=int, default=1); g.add_argument("--note", default="")
    g.add_argument("--no-angles", action="store_true", help="do not attach the H3 angle frames")
    g.add_argument("--ref", action="append", default=[], help="PATH=ROLE (relative to the project root)")
    ad = sub.add_parser("adopt"); ad.add_argument("id"); ad.add_argument("kind"); ad.add_argument("n")
    ad.add_argument("--as", dest="as_name", help="name in ref/ (default: front for restyle, else the kind)")
    lg = sub.add_parser("log"); lg.add_argument("id")
    a = ap.parse_args()
    {"gen": cmd_gen, "adopt": cmd_adopt, "log": cmd_log}[a.cmd](a)


if __name__ == "__main__":
    main()
