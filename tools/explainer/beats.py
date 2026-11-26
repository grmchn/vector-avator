"""Beat gestures: where in a line's voice the hands and head give a small beat.

Candidates come from the line's audio:
  onset   : rises of the loudness (log energy over 30 ms) = heads of stressed syllables
  pitch   : local peaks of the voice pitch (autocorrelation f0)
  phrase  : starts of voiced spans after a pause (heads of phrases)
  emphasis: morae of the phrases in the line's `emphasize` list (kana found in `ja_kana`),
            timed like the lip-sync (morae spread over the voiced spans)
Each candidate gets a score; select() keeps the best ones with a minimum interval, a cap per
second, and none inside "busy" windows (the big strokes of a gesture).

usage (figure of the candidates of every line of a script):
  .venv/bin/python tools/explainer/beats.py --script <build-form script.json> --audio-dir <wav folder> --out beats.svg
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lipsync"))
from align import morae  # noqa: E402

SR = 48000
HOP = 0.01

# strength levels: beat amplitude scale, minimum interval (s), beats per second of voice
LEVELS = {
    "off": {"amp": 0.0, "gap": 9.0, "rate": 0.0},
    "weak": {"amp": 0.6, "gap": 0.8, "rate": 0.5},
    "mid": {"amp": 1.0, "gap": 0.55, "rate": 0.8},
    "strong": {"amp": 1.6, "gap": 0.45, "rate": 1.0},
}


HOP_N = int(SR * HOP)


def loudness_db(x):
    n = len(x) // HOP_N
    rms = np.sqrt(np.mean(x[: n * HOP_N].reshape(n, HOP_N) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    k = np.ones(3) / 3
    return np.convolve(db, k, mode="same")


def f0_track(x, fmin=110.0, fmax=700.0, win=0.04):
    """Very small autocorrelation pitch tracker: f0 (Hz) per 10 ms hop, 0 where unvoiced."""
    n = len(x) // HOP_N
    W = int(SR * win)
    lo, hi = int(SR / fmax), int(SR / fmin)
    out = np.zeros(n)
    db = loudness_db(x)
    floor = np.percentile(db, 95) - 25
    for i in range(n):
        if db[i] < floor:
            continue
        a = i * HOP_N
        seg = x[a:a + W]
        if len(seg) < W:
            break
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[W - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.45:
            out[i] = SR / k
    return out


def local_peaks(v, min_dist):
    """Indices of local maxima (plateaus: first index), at least min_dist frames apart (greedy by value)."""
    idx = [i for i in range(1, len(v) - 1) if v[i] > 0 and v[i] >= v[i - 1] and v[i] > v[i + 1]]
    idx.sort(key=lambda i: -v[i])
    keep = []
    for i in idx:
        if all(abs(i - j) >= min_dist for j in keep):
            keep.append(i)
    return sorted(keep)


def mora_times(shapes, spans, min_len=0.06):
    """Start time of each mora, spread over the voiced spans like build_timeline.distribute()."""
    times = []
    total = sum(b - a for a, b in spans) or 1
    rest = list(range(len(shapes)))
    for i, (a, b) in enumerate(spans):
        share = len(shapes) * (b - a) / total
        k = max(1, round(share)) if i < len(spans) - 1 else max(1, len(rest))
        part, rest = rest[:k], rest[k:]
        if not part:
            continue
        step = max(min_len, (b - a) / len(part))
        for j, _ in enumerate(part):
            times.append(a + j * step)
    while len(times) < len(shapes):
        times.append(times[-1] if times else 0.0)
    return times


def emphasis_ranges(line, spans):
    """Time ranges of the line's emphasized phrases (kana substrings of ja_kana)."""
    kana = line.get("ja_kana", "")
    shapes = morae(kana)
    if not shapes or not line.get("emphasize"):
        return []
    mt = mora_times(shapes, spans)
    out = []
    for ph in line["emphasize"]:
        i = kana.find(ph)
        if i < 0:
            continue
        k0 = len(morae(kana[:i]))
        k1 = min(len(mt) - 1, k0 + max(1, len(morae(ph))) - 1)
        out.append((mt[k0], mt[k1] + 0.15))
    return out


def candidates(x, t0, spans, emph=()):
    """Beat candidates of one line: [{"t", "score", "kind": [...]}], t in timeline seconds."""
    db = loudness_db(x)
    peak = np.percentile(db, 95)
    rise = np.maximum(0, db - np.concatenate([np.full(3, db[0]), db[:-3]]))
    on = local_peaks(np.where(rise > 4.0, rise, 0), 8)
    f0 = f0_track(x)
    # pitch peaks: smoothed f0 over voiced frames, peaks clearly above the line's median
    voiced = f0 > 0
    pk = []
    if voiced.sum() > 10:
        med = np.median(f0[voiced])
        sm = np.convolve(np.where(voiced, f0, 0), np.ones(5) / 5, mode="same")
        pk = [i for i in local_peaks(sm, 15) if sm[i] > med * 1.08]
    cands = []
    for i in on:
        # loudness reached in the 150 ms after the rise, relative to the line
        j = min(len(db), i + 15)
        loud = float(np.max(db[i:j]) - peak)
        s = 1.0 + 0.04 * rise[i] + 0.08 * max(-12.0, loud)
        cands.append({"t": t0 + i * HOP, "score": s, "kind": ["onset"]})
    for i in pk:
        t = t0 + i * HOP
        near = [c for c in cands if abs(c["t"] - t) < 0.12]
        if near:
            near[0]["score"] += 0.5; near[0]["kind"].append("pitch")
        else:
            cands.append({"t": t, "score": 0.6, "kind": ["pitch"]})
    for k, (a, b) in enumerate(spans):
        if k == 0 or a - spans[k - 1][1] >= 0.12:
            near = [c for c in cands if abs(c["t"] - a) < 0.1]
            if near:
                near[0]["score"] += 0.6; near[0]["kind"].append("phrase")
            else:
                cands.append({"t": a + 0.03, "score": 0.9, "kind": ["phrase"]})
    for a, b in emph:
        inside = [c for c in cands if a - 0.05 <= c["t"] <= b]
        if inside:
            best = max(inside, key=lambda c: c["score"])
            best["score"] += 1.5; best["kind"].append("emphasis")
        else:
            cands.append({"t": a, "score": 2.0, "kind": ["emphasis"]})
    return sorted(cands, key=lambda c: c["t"])


def select(cands, start, end, level="mid", busy=(), rate_scale=1.0):
    """Best candidates with a minimum interval and a cap per second of voice; none in busy windows."""
    L = LEVELS[level]
    if L["amp"] <= 0:
        return []
    n_max = max(1, int(round((end - start) * L["rate"] * rate_scale)))
    keep = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if any(a <= c["t"] <= b for a, b in busy):
            continue
        if all(abs(c["t"] - k["t"]) >= L["gap"] for k in keep):
            keep.append(c)
        if len(keep) >= n_max:
            break
    return sorted(keep, key=lambda c: c["t"])


# ------------------------------------------------------------------ figure
def figure(rows, out):
    """SVG: per line, the loudness, the candidates (grey, height = score) and the chosen beats (red)."""
    W, rh, pad = 1400, 120, 60
    H = pad + rh * len(rows) + 20
    tmax = max(r["end"] - r["start"] for r in rows) + 0.3
    sx = (W - 2 * pad) / tmax
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="&apos;M PLUS Rounded 1c&apos;, sans-serif">',
          f'<rect width="{W}" height="{H}" fill="#fffafc"/>',
          f'<text x="{pad}" y="32" font-size="18" fill="#2d3d5c">拍の候補（灰：候補、高さ＝点数／赤：選んだ拍／水色：強調語／黒：音量）</text>']
    for k, r in enumerate(rows):
        y0 = pad + k * rh
        base = y0 + rh - 22
        el.append(f'<text x="8" y="{y0 + 20}" font-size="14" fill="#2d3d5c">{r["id"]}</text>')
        el.append(f'<text x="{pad}" y="{y0 + 16}" font-size="13" fill="#5a6b8c">{r["text"]}</text>')
        for a, b in r["emph"]:
            el.append(f'<rect x="{pad + (a - r["start"]) * sx:.1f}" y="{y0 + 22}" width="{(b - a) * sx:.1f}" height="{rh - 44}" fill="#bfe9ff" opacity="0.6"/>')
        db = r["db"]
        top = max(db)
        pts = " ".join(f"{pad + i * HOP * sx:.1f},{base - max(0, (v - top + 40)) * 1.6:.1f}" for i, v in enumerate(db))
        el.append(f'<polyline points="{pts}" fill="none" stroke="#2d3d5c" stroke-width="1"/>')
        for c in r["cands"]:
            x = pad + (c["t"] - r["start"]) * sx
            el.append(f'<line x1="{x:.1f}" y1="{base}" x2="{x:.1f}" y2="{base - 14 * c["score"]:.1f}" stroke="#a0a8b8" stroke-width="3"/>')
        for c in r["beats"]:
            x = pad + (c["t"] - r["start"]) * sx
            el.append(f'<circle cx="{x:.1f}" cy="{base + 8}" r="6" fill="#ff4f8b"/>')
        el.append(f'<line x1="{pad}" y1="{base}" x2="{pad + (r["end"] - r["start"]) * sx:.1f}" y2="{base}" stroke="#d0d6e2"/>')
    for s in range(int(tmax) + 1):
        x = pad + s * sx
        el.append(f'<text x="{x:.1f}" y="{H - 4}" font-size="11" fill="#5a6b8c">{s}s</text>')
    el.append("</svg>")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(el), encoding="utf-8")


def main():
    sys.path.insert(0, str(ROOT / "tools/explainer"))
    from build_timeline import load_wav, trim, cap_pauses, voiced_spans  # noqa: E402
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--max-pause", type=float, default=0.0)
    ap.add_argument("--level", default="mid")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for l in json.load(open(ROOT / a.script))["lines"]:
        x = trim(load_wav(ROOT / a.audio_dir / f"{l['id']}_t1.wav"))
        if a.max_pause > 0:
            x = cap_pauses(x, a.max_pause)
        spans = voiced_spans(x, 0.0)
        emph = emphasis_ranges(l, spans)
        cands = candidates(x, 0.0, spans, emph)
        dur = len(x) / SR
        beats = select(cands, 0.0, dur, a.level)
        rows.append({"id": l["id"], "text": l["ja"], "start": 0.0, "end": dur, "db": list(loudness_db(x)),
                     "cands": cands, "beats": beats, "emph": emph})
        print(l["id"], f"{dur:.2f}s", len(cands), "cands ->", [round(b["t"], 2) for b in beats], [b["kind"] for b in beats])
    figure(rows, ROOT / a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
