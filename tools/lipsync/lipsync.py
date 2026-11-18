"""Lip-sync track (mouth shapes over time) for one voice line, independent of the TTS engine.

Input: a WAV file and what is said in it. Output: the JSON read by the viewer
({"method", "duration", "keys": [{"t": seconds, "mouth": "sil|a|i|u|e|o"}]}).

  voiced  (default) mouth shapes from the text, spread over the voiced spans of the audio
  whisper           the same, but aligned to the word timings of a Whisper JSON (--whisper)
  rms               openness from the audio level only (no text needed)

Japanese text should be the reading in kana (kanji are skipped). English text (--lang en) is
turned into one rough vowel shape per vowel group of each word.

Usage:
  python tools/lipsync/lipsync.py line.wav --text "こんにちは、よろしくおねがいします。" -o line.json
  python tools/lipsync/lipsync.py line.wav --text "Hello there." --lang en -o line.json
  python tools/lipsync/lipsync.py line.wav --method rms -o line.json
  python tools/lipsync/lipsync.py line.wav --text "..." --whisper line.whisper.json -o line.json

Needs numpy only (Whisper is run separately, if at all)."""
import argparse
import json
import re
import wave

import numpy as np

ROWS = {"a": "あかさたなはまやらわがざだばぱぁゃアカサタナハマヤラワガザダバパァャ",
        "i": "いきしちにひみりぎじぢびぴぃイキシチニヒミリギジヂビピィ",
        "u": "うくすつぬふむゆるぐずづぶぷぅゅゔウクスツヌフムユルグズヅブプゥュヴ",
        "e": "えけせてねへめれげぜでべぺぇエケセテネヘメレゲゼデベペェ",
        "o": "おこそとのほもよろをごぞどぼぽぉょオコソトノホモヨロヲゴゾドボポォョ",
        "sil": "んっンッ"}
SMALL = "ゃゅょぁぃぅぇぉャュョァィゥェォ"


def ja_shapes(text):
    """One mouth shape per mora of a kana reading (small kana change the previous mora)."""
    out = []
    for ch in text:
        if ch == "ー" and out:
            out.append(out[-1])
            continue
        m = next((k for k, v in ROWS.items() if ch in v), None)
        if m is None:
            continue
        if ch in SMALL and out:
            out[-1] = m
            continue
        out.append(m)
    return out


def en_shapes(text):
    """Very rough English mouth shapes: one per vowel group of each word, closed after m/b/p."""
    out = []
    for w in re.findall(r"[a-zA-Z']+|\d", text.lower()):
        for g in re.findall(r"[aeiouy]+", w) or ["e"]:
            out.append({"a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "i"}[g[0]])
        if re.search(r"[mbp]$", w):
            out.append("sil")
    return out


def read_wav(path):
    with wave.open(path) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw not in (2, 4):
        raise SystemExit(f"{path}: only 16-bit or 32-bit PCM WAV is supported (convert with ffmpeg -c:a pcm_s16le)")
    x = np.frombuffer(raw, dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    return x.reshape(-1, ch).mean(1) / (2 ** (8 * sw - 1)), sr


def voiced_spans(x, sr, thr_db=-34.0, min_gap=0.09):
    """Spans (s) where the voice is on; gaps shorter than min_gap are merged."""
    hop = max(1, int(sr * 0.01))
    n = len(x) // hop
    if n == 0:
        return []
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    peak = 20 * np.log10(np.percentile(rms, 95))
    on = 20 * np.log10(rms) > max(thr_db, peak - 26)
    spans, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            spans.append([s, i])
            s = None
    if s is not None:
        spans.append([s, n])
    merged = []
    for a, b in spans:
        if merged and (a - merged[-1][1]) * 0.01 < min_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a * 0.01, b * 0.01) for a, b in merged if (b - a) * 0.01 > 0.05]


def distribute(shapes, spans, min_len=0.06):
    """Share the shapes among the spans by length; the mouth closes at the end of each span."""
    keys = []
    total = sum(b - a for a, b in spans) or 1
    rest = list(shapes)
    for i, (a, b) in enumerate(spans):
        share = len(shapes) * (b - a) / total
        k = max(1, round(share)) if i < len(spans) - 1 else max(1, len(rest))
        part, rest = rest[:k], rest[k:]
        if not part:
            part = ["a"]
        step = max(min_len, (b - a) / len(part))
        for j, m in enumerate(part):
            t = a + j * step
            if t < b:
                keys.append({"t": round(t, 3), "mouth": m})
        keys.append({"t": round(b, 3), "mouth": "sil"})
    return keys


def whisper_spans(path):
    """Word spans of a Whisper JSON ({"segments": [{"start", "end", "words": [...]}]})."""
    segs = json.load(open(path, encoding="utf-8"))["segments"]
    spans = []
    for seg in segs:
        spans += [(w["start"], w["end"]) for w in seg.get("words", [])] or [(seg["start"], seg["end"])]
    merged = []
    for s, e in sorted(spans):
        if merged and s - merged[-1][1] < 0.08:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def rms_keys(x, sr):
    hop = max(1, int(sr / 30))
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, max(0, len(x) - hop), hop)])
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1
    keys, last = [], None
    for i, v in enumerate(rms / ref):
        m = "sil" if v < 0.12 else ("e" if v < 0.45 else "a")
        if m != last:
            keys.append({"t": round(i / 30, 3), "mouth": m})
            last = m
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("-o", "--out", required=True, help="output JSON")
    ap.add_argument("--text", default="", help="what is said (Japanese: kana reading)")
    ap.add_argument("--lang", choices=["ja", "en"], default="ja")
    ap.add_argument("--method", choices=["voiced", "whisper", "rms"], default=None,
                    help="default: whisper when --whisper is given, voiced otherwise")
    ap.add_argument("--whisper", help="Whisper JSON with word timings")
    a = ap.parse_args()
    method = a.method or ("whisper" if a.whisper else "voiced")
    x, sr = read_wav(a.wav)
    dur = len(x) / sr
    if method == "rms":
        keys = rms_keys(x, sr)
    else:
        if not a.text:
            raise SystemExit("--text is required for the voiced and whisper methods (or use --method rms)")
        shapes = en_shapes(a.text) if a.lang == "en" else ja_shapes(a.text)
        if not shapes:
            raise SystemExit("no mouth shapes found in --text (Japanese text must be written in kana)")
        if method == "whisper":
            if not a.whisper:
                raise SystemExit("--method whisper needs --whisper")
            spans = whisper_spans(a.whisper)
        else:
            spans = voiced_spans(x, sr)
        if not spans:
            raise SystemExit("no voiced part found in the audio")
        keys = distribute(shapes, spans)
    keys.sort(key=lambda k: k["t"])
    json.dump({"method": method, "duration": round(dur, 3), "keys": keys}, open(a.out, "w", encoding="utf-8"))
    print(f"{method}: {len(keys)} keys, {dur:.2f} s -> {a.out}")


if __name__ == "__main__":
    main()
