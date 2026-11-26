"""Lip-sync tracks for a TTS line (three methods, for comparison).

  whisper : kana morae distributed uniformly over the voiced spans of each Whisper segment
  rms     : mouth openness from the audio level only (sil / e / a)
  kana    : morae at a fixed 0.15 s, ignoring the audio (baseline)

Usage: python tools/lipsync/align.py <wav> <whisper.json> <out_prefix> --kana "<reading per sentence, 。separated>"
Writes <out_prefix>_{whisper,rms,kana}.json : {"keys": [{"t": s, "mouth": "a"}...], "duration": s}"""
import argparse, json, wave
import numpy as np

ROWS = {"a": "あかさたなはまやらわがざだばぱぁゃ", "i": "いきしちにひみりぎじぢびぴぃ", "u": "うくすつぬふむゆるぐずづぶぷぅゅゔ",
        "e": "えけせてねへめれげぜでべぺぇ", "o": "おこそとのほもよろをごぞどぼぽぉょ", "sil": "んっ"}
SMALL = "ゃゅょぁぃぅぇぉ"


def morae(text):
    out = []
    for ch in text:
        if ch == "ー" and out:
            out.append(out[-1]); continue
        m = next((k for k, v in ROWS.items() if ch in v), None)
        if m is None:
            continue
        if ch in SMALL and out:
            out[-1] = m; continue
        out.append(m)
    return out


def read_wav(path):
    with wave.open(path) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        x = np.frombuffer(w.readframes(n), dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    x = x.reshape(-1, ch).mean(1) / (2 ** (8 * sw - 1))
    return x, sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav"); ap.add_argument("whisper"); ap.add_argument("out")
    ap.add_argument("--kana", required=True)
    ap.add_argument("--min-mora", type=float, default=0.06)
    a = ap.parse_args()
    x, sr = read_wav(a.wav)
    dur = len(x) / sr
    sentences = [s for s in a.kana.split("。") if s.strip()]
    segs = json.load(open(a.whisper))["segments"]
    # --- whisper-aligned
    keys = []
    si = 0
    for seg in segs:
        # a Whisper segment may hold several sentences: take as many as it has "。"
        n = max(1, seg["text"].count("。"))
        mor = [m for s in sentences[si:si + n] for m in morae(s)]
        si += n
        spans = [(w["start"], w["end"]) for w in seg.get("words", [])] or [(seg["start"], seg["end"])]
        # merge touching spans; gaps longer than 0.08 s are pauses (mouth closed)
        merged = []
        for s, e in spans:
            if merged and s - merged[-1][1] < 0.08:
                merged[-1][1] = e
            else:
                merged.append([s, e])
        total = sum(e - s for s, e in merged)
        if not mor or total <= 0:
            continue
        step = total / len(mor)
        k = 0.0
        for s, e in merged:
            t = s
            while t < e - 1e-6 and int(k / step) < len(mor):
                keys.append({"t": round(t, 3), "mouth": mor[int(k / step)]})
                adv = min(step - (k % step), e - t)
                t += max(adv, 1e-3); k += max(adv, 1e-3)
            keys.append({"t": round(e, 3), "mouth": "sil"})
    keys.sort(key=lambda k: k["t"])
    json.dump({"method": "whisper", "duration": dur, "keys": keys}, open(f"{a.out}_whisper.json", "w"))
    # --- rms only
    hop = int(sr / 30)
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1
    level = rms / ref
    rk, last = [], None
    for i, v in enumerate(level):
        m = "sil" if v < 0.12 else ("e" if v < 0.45 else "a")
        if m != last:
            rk.append({"t": round(i / 30, 3), "mouth": m}); last = m
    json.dump({"method": "rms", "duration": dur, "keys": rk}, open(f"{a.out}_rms.json", "w"))
    # --- kana only (fixed mora length, starting at the first voiced word)
    t0 = segs[0]["start"] if segs else 0
    kk, t = [], t0
    for s in sentences:
        for m in morae(s):
            kk.append({"t": round(t, 3), "mouth": m}); t += 0.15
        kk.append({"t": round(t, 3), "mouth": "sil"}); t += 0.3
    json.dump({"method": "kana", "duration": dur, "keys": kk}, open(f"{a.out}_kana.json", "w"))
    print("keys:", len(keys), len(rk), len(kk), "duration", round(dur, 2))


if __name__ == "__main__":
    main()
