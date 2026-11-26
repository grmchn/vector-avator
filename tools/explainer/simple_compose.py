"""Compose a simple explainer video: presenter (left), an image card per line (right), subtitles (bottom).


usage:
  .venv/bin/python tools/explainer/simple_compose.py --timeline T.json --presenter P.mp4 --audio N.wav
      --images DIR [--intro-image I.png] --out OUT.mp4 [--bg dde6f2] [--size 1920x1080]
      [--crop 0.6] [--ph 0.84] [--py 0.02]   (presenter: centre crop of its width, height and top)
      [--total S]                           (cut the video to S seconds; default: the timeline's total)
      [--layout L.json]                     (screen layout shared with perform.py; default tools/explainer/layout.json.
                                             --crop/--ph/--py/--size override it)
      [--window A B]                        (only A..B seconds of the timeline; the presenter video starts at A,
                                             e.g. captured with sequence.mjs T0=A)
      [--marks tl,tr,...]                   (draw a dot at the centre of these layout regions, for tests)
      [--avatar CHAR]                       (--bg/--crop/--ph/--py default to the avatar package's capture)

timeline.json lines: {"start", "end", "text", "icon", "card_text"}; icon is a file stem in --images
("" = --intro-image). A line whose image file does not exist but has a card_text (the content's
visual.text) shows that text on a white card instead. An image stays on screen from its
line's start until the next line with a different image starts. Subtitles longer than the frame are
wrapped at a punctuation mark near the middle.
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as LAYOUT  # noqa: E402

import os  # noqa: E402
# subtitle font: $FONT, else M PLUS Rounded 1c Bold if installed, else ffmpeg's default font
FONT = Path(os.environ.get("FONT") or (Path.home() / ".local/share/fonts/google/mplusrounded1c/MPLUSRounded1c-Bold.ttf"))


def text_width(t):
    """Width of a text in full-width characters (ASCII about half)."""
    return sum(1.0 if ord(c) > 0x2000 else 0.55 for c in t)


def wrap(text, max_chars, marks_set="、。！？!?…"):
    """Split a text into rows of at most max_chars (full-width) characters, preferring a break
    after a punctuation mark near the middle. A short text stays one row."""
    if text_width(text) <= max_chars:
        return [text]
    marks = [i + 1 for i, c in enumerate(text) if c in marks_set and 0 < i + 1 < len(text)]
    mid = len(text) / 2
    cut = min(marks, key=lambda i: abs(i - mid)) if marks else None
    if cut is None or abs(cut - mid) > len(text) * 0.3:
        # no punctuation near the middle: after a particle (は・が・を・に・て …), not inside a word
        soft = [i + 1 for i, c in enumerate(text[:-1]) if c in "はがをにでとてのもへやよね" and not
                ("\u3041" <= text[i + 1] <= "\u309f" and text[i + 1] not in "はがをにでとのもへ")]
        near = [i for i in soft if abs(i - mid) <= len(text) * 0.3]
        cut = min(near, key=lambda i: abs(i - mid)) if near else int(mid)
    head, tail = text[:cut].strip(), text[cut:].strip()
    return wrap(head, max_chars, marks_set) + wrap(tail, max_chars, marks_set)


def text_card(text, tmp, width, H):
    """A white card image with the text (content visual.text when there is no image)."""
    out = Path(tmp) / f"card_{abs(hash(text)) % 10**8}.png"
    if not out.is_file():
        pad = int(width * 0.08)
        ps = int(H * 0.055)
        # break at the card's own separators (・ → ＝ ↔ and spaces) rather than inside a word
        rows = wrap(text, int((width - 2 * pad) / ps), "、。！？・→＝↔ ")
        subprocess.run(["magick", "-background", "white", "-fill", "#2d3d5c", "-font", str(FONT),
                        "-pointsize", str(ps), "-gravity", "center", "label:" + "\n".join(rows),
                        "-gravity", "center", "-extent", f"{width - 2 * pad}x",
                        "-bordercolor", "white", "-border", f"{pad}x{int(pad * 1.6)}", str(out)], check=True)
    return str(out)


def image_card(img, text, tmp, width, H):
    """An image with the content's visual.text under it, on white."""
    out = Path(tmp) / f"imgcard_{abs(hash((img, text))) % 10**8}.png"
    if not out.is_file():
        ps = int(H * 0.042)
        rows = wrap(text, int(width / ps), "、。！？・→＝↔ ")
        subprocess.run(["magick", img, "-resize", f"{width}x", "(", "-background", "white", "-fill", "#2d3d5c",
                        "-font", str(FONT), "-pointsize", str(ps), "-gravity", "center", "label:" + "\n".join(rows),
                        "-gravity", "center", "-extent", f"{width}x", ")", "-background", "white", "-append",
                        "-bordercolor", "white", "-border", f"0x{int(ps * 0.4)}", str(out)], check=True)
    return str(out)


def text_strip(text, tmp, width, H):
    """The white strip with the content's visual.text, to go under a clip (the same look as image_card)."""
    out = Path(tmp) / f"strip_{abs(hash(text)) % 10**8}.png"
    if not out.is_file():
        ps = int(H * 0.042)
        mx = width / ps
        # break at the full-width spaces of the text first (they separate the items), packing items into rows
        rows, cur = [], ""
        for seg in text.split("\u3000"):
            if cur and text_width(cur + " " + seg) <= mx:
                cur += " " + seg
            else:
                if cur:
                    rows.append(cur)
                cur = seg
        rows.append(cur)
        rows = [r2 for r in rows for r2 in wrap(r, int(mx), "、。！？・→＝↔ ")]
        subprocess.run(["magick", "-background", "white", "-fill", "#2d3d5c", "-font", str(FONT), "-pointsize", str(ps),
                        "-gravity", "center", "label:" + "\n".join(rows), "-gravity", "center", "-extent", f"{width}x",
                        "-bordercolor", "white", "-border", f"0x{int(ps * 0.4)}", str(out)], check=True)
    return str(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--presenter", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--images", default="", help="folder of the line images (<icon>.png)")
    ap.add_argument("--clips", default="", help="folder of <icon>.mp4 clips (moving versions of the images, e.g. H3); played forward and backward in a loop")
    ap.add_argument("--intro-image", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bg", default=None, help="background colour (default dde6f2 or the package's capture.bg)")
    ap.add_argument("--size", default=None)
    ap.add_argument("--crop", type=float, default=None, help="centre crop of the presenter video (fraction of its width)")
    ap.add_argument("--ph", type=float, default=None, help="presenter height (fraction of the frame height)")
    ap.add_argument("--py", type=float, default=None, help="presenter top (fraction of the frame height)")
    ap.add_argument("--layout", default="", help="layout JSON (default: tools/explainer/layout.json)")
    ap.add_argument("--window", type=float, nargs=2, default=None, help="cut A..B seconds of the timeline (presenter video starts at A)")
    ap.add_argument("--marks", default="", help="comma-separated layout regions to mark with a dot")
    ap.add_argument("--total", type=float, default=0.0, help="video length in seconds (default: the timeline's); the audio fades out over the last 0.3 s")
    ap.add_argument("--avatar", default="", help="character id; its capture settings are the defaults")
    a = ap.parse_args()
    Path(a.out).resolve().parent.mkdir(parents=True, exist_ok=True)
    if a.avatar:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "avatar"))
        import package as PKG  # noqa: E402
        cap = PKG.load(a.avatar)["capture"]
        a.bg = a.bg or cap["bg"]
        a.crop = cap["crop"] if a.crop is None else a.crop
        a.ph = cap["ph"] if a.ph is None else a.ph
        a.py = cap["py"] if a.py is None else a.py
    a.bg = a.bg or "dde6f2"
    lay = LAYOUT.load(a.layout or None)
    pr = lay["presenter"]
    W, H = map(int, a.size.split("x")) if a.size else lay["size"]
    a.crop = pr["crop"] if a.crop is None else a.crop
    a.ph = pr["ph"] if a.ph is None else a.ph
    a.py = pr["py"] if a.py is None else a.py
    card = lay["card"]
    tl = json.load(open(a.timeline))
    lines, total = tl["lines"], (a.total or tl["total"])
    if a.window:
        A, B = a.window
        lines = [{**l, "start": round(l["start"] - A, 3), "end": round(l["end"] - A, 3)} for l in lines]
        total = round(B - A, 3)
    tmp = Path(tempfile.mkdtemp(prefix="compose_"))

    # image segments: consecutive lines with the same image are merged.
    # a line whose image has a moving version (<--clips>/<icon>.mp4, e.g. made with MiniMax H3 from the still)
    # shows the clip, played forward and backward in a loop, with the text strip under it.
    segs = []
    cw = int(W * card["w"])  # card width
    for i, l in enumerate(lines):
        img = str(Path(a.images) / f"{l['icon']}.png") if (l.get("icon") and a.images) else ""
        clip = str(Path(a.clips) / f"{l['icon']}.mp4") if (l.get("icon") and a.clips) else ""
        strip = ""
        if clip and Path(clip).is_file() and l.get("card_text"):
            strip = text_strip(l["card_text"], tmp, cw - 48, H)
            key = (clip, l["card_text"])
            img = ""
        else:
            clip = ""
            if img and Path(img).is_file() and l.get("card_text"):
                img = image_card(img, l["card_text"], tmp, cw - 48, H)     # the image with its text under it
            elif not (img and Path(img).is_file()):
                img = text_card(l["card_text"], tmp, cw - 48, H) if l.get("card_text") else (img or a.intro_image)
            if not img:
                continue
            key = img
        if segs and segs[-1]["key"] == key:
            continue
        if segs:
            segs[-1]["e"] = l["start"]
        segs.append({"key": key, "img": img, "clip": clip, "strip": strip, "s": l["start"], "e": total})
    # --window: images entirely outside the window are dropped; one already on screen at its
    # start is shown from 0 without the fade
    segs = [g for g in segs if g["e"] > 0 and g["s"] < total]
    inputs = ["-i", a.presenter, *(["-ss", str(a.window[0])] if a.window else []), "-i", a.audio]
    for g in segs:
        if g["clip"]:
            inputs += ["-i", g["clip"], "-loop", "1", "-t", str(total), "-i", g["strip"]]
        else:
            inputs += ["-loop", "1", "-t", str(total), "-i", g["img"]]
    f = [f"color=c=0x{a.bg}:s={W}x{H}:d={total}[base]",
         f"[0:v]crop=trunc(iw*{a.crop}/2)*2:ih,scale=-2:{int(H * a.ph) // 2 * 2}[pv]",
         f"[base][pv]overlay=x={int(W * pr['cx'])}-overlay_w/2:y={int(H * a.py)}[v0]"]
    cur = "v0"
    idx = 2
    for k, g in enumerate(segs):
        s, e = g["s"], g["e"]
        fade = f"fade=t=in:st={s}:d=0.25:alpha=1" if s >= 0 else "null"
        if g["clip"]:
            # forward + backward = a seamless loop; the strip (white, with the text) goes under it
            f.append(f"[{idx}:v]fps=24,scale={cw - 48}:-2,split=2[ca{k}][cb{k}];[cb{k}]reverse[cr{k}];"
                     f"[ca{k}][cr{k}]concat=n=2:v=1:a=0,loop=loop=-1:size=400:start=0,format=rgba,setpts=N/24/TB+{s}/TB[cv{k}]")
            f.append(f"[{idx + 1}:v]fps=24,format=rgba,setpts=N/24/TB+{s}/TB[cs{k}]")
            f.append(f"[cv{k}][cs{k}]vstack=inputs=2,pad=iw+48:ih+48:24:24:white,format=rgba,{fade}[c{k}]")
            idx += 2
        else:
            # white rounded-ish card: pad the image with white, then fade in
            f.append(f"[{idx}:v]scale={cw - 48}:-2,pad=iw+48:ih+48:24:24:white,format=rgba,{fade}[c{k}]")
            idx += 1
        nxt = f"v{k + 1}"
        cy = f"{int(H * 0.04)}" if g["clip"] else f"{int(H * card['cy'])}-overlay_h/2"   # clip cards: top-aligned
        f.append(f"[{cur}][c{k}]overlay=x={int(W * card['cx'])}-overlay_w/2:y={cy}:"
                 f"enable='between(t,{s},{e})'[{nxt}]")
        cur = nxt
    for name in [m for m in a.marks.split(",") if m]:
        X, Y = LAYOUT.region_point(lay, name)
        r = int(H * 0.018)
        nxt = f"m_{name}"
        f.append(f"[{cur}]drawbox=x={int(X) - r}:y={int(Y) - r}:w={2 * r}:h={2 * r}:color=0xff4f8b@0.9:t=fill[{nxt}]")
        cur = nxt
    for i, l in enumerate(lines):
        fs = int(H * 0.05)
        rows = wrap(l["text"], int(W * 0.92 / fs))
        if len(rows) > 2:   # a long line: smaller letters in two rows rather than three over the presenter
            fs = int(H * 0.04)
            rows = wrap(l["text"], int(W * 0.94 / fs))
        end = lines[i + 1]["start"] if i + 1 < len(lines) else total
        for j, row in enumerate(rows):   # one drawtext per row: each row centred, the last at the old place
            tf = tmp / f"line{i}_{j}.txt"
            tf.write_text(row, encoding="utf-8")
            y = int(H * 0.11) + (len(rows) - 1 - j) * int(fs * 1.5)
            nxt = f"t{i}_{j}"
            f.append(f"[{cur}]drawtext=fontfile='{FONT}':textfile='{tf}':fontsize={fs}:fontcolor=0x2d3d5c:"
                     f"x=(w-text_w)/2:y=h-{y}:box=1:boxcolor=white@0.88:boxborderw={int(fs * 0.45)}:"
                     f"enable='between(t,{l['start']},{end - 0.05})'[{nxt}]")
            cur = nxt
    cmd = ["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(f),
           "-map", f"[{cur}]", "-map", "1:a", "-af", f"afade=t=out:st={max(0.0, total - 0.3):.2f}:d=0.3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-t", str(total), a.out]
    subprocess.run(cmd, check=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
