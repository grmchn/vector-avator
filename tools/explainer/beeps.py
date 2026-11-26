"""Find and mute the TTS "beep" artifacts at the edges of a line.

Irodori-TTS sometimes adds a short, almost pure tone (about 1.1-1.2 kHz, falling,
50-100 ms, as loud as the voice) right before the first word or after the last
one -- often after a final "?". It sounds like a stray sound effect. Speech
never looks like this: a voiced frame spreads its energy over several harmonics
of a low fundamental, while the beep puts most of it into one narrow peak, is
short, and starts out of silence (high voices put a strong harmonic near 1 kHz
too, but inside a longer, connected vowel).

  find_beeps(x)          -> [(t0, t1), ...] in seconds, edge artifacts only
  mute(x, spans)         -> a copy with those spans silenced (same length, short fades)
  python tools/explainer/beeps.py <narration.wav> <timeline.json> [--apply]
      scans each line of an assembled narration and, with --apply, mutes the
      beeps in place (timing unchanged, so the captured presenter still fits).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000
HOP = 480                  # 10 ms frames
FMIN, FMAX = 900.0, 1500.0  # where the beep sits (the voice's fundamental is ~230 Hz)
CONC = 0.62                # share of frame energy within +-60 Hz of the peak
CONC_MAX = 0.67            # at least one frame of a run must be this pure
MIN_FRAMES = 4
MAX_FRAMES = 12            # a beep lasts 40-120 ms; a held high vowel lasts longer
SUB_MAX = 0.002            # no fundamental at half the peak (a high voice's 2nd harmonic has one)
QUIET_DB = -35.0           # the beep starts out of silence (the 5 frames before its 20 ms onset are quiet)
HEAD, TAIL = 0.35, 0.45    # only runs this close to the first / last voiced frame count
VOICED_DB = -42.0

_FR = np.fft.rfftfreq(4096, 1 / SR)
_WIN = np.hanning(HOP)


def _frames(x: np.ndarray):
    n = len(x) // HOP
    for i in range(n):
        f = x[i * HOP:(i + 1) * HOP]
        db = 20 * np.log10(np.sqrt(np.mean(f ** 2)) + 1e-9)
        sp = np.abs(np.fft.rfft(f * _WIN, 4096)) ** 2
        k = int(np.argmax(sp))
        band = (_FR > _FR[k] - 60) & (_FR < _FR[k] + 60)
        sub = (_FR > _FR[k] / 2 - 40) & (_FR < _FR[k] / 2 + 40)   # a voice's fundamental under its harmonic
        yield db, _FR[k], sp[band].sum() / (sp.sum() + 1e-20), sp[sub].max() / (sp[k] + 1e-20)


def find_beeps(x: np.ndarray) -> list[tuple[float, float]]:
    """Edge beeps in a single line's audio, as (start, end) seconds."""
    fs = list(_frames(np.asarray(x, dtype=np.float64)))
    if not fs:
        return []
    voiced = [i for i, f in enumerate(fs) if f[0] > VOICED_DB]
    if not voiced:
        return []
    first, last = voiced[0], voiced[-1]
    hit = [db > -40 and FMIN <= pk <= FMAX and c >= CONC and sub < SUB_MAX for db, pk, c, sub in fs]
    runs, i = [], 0
    while i < len(fs):
        if hit[i]:
            j = i
            while j + 1 < len(fs) and (hit[j + 1] or (j + 2 < len(fs) and hit[j + 2])):
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    out = []
    for a, b in runs:
        if not MIN_FRAMES <= b - a + 1 <= MAX_FRAMES or max(fs[k][2] for k in range(a, b + 1)) < CONC_MAX:
            continue
        if any(fs[k][0] >= QUIET_DB for k in range(max(0, a - 7), max(0, a - 2))):   # skip its own onset
            continue   # glued to speech: a high harmonic of a voice, not a stray beep
        if a - first <= HEAD * 100:        # before the first word: mute from the start
            out.append((0.0, (b + 1) / 100 + 0.015))
        elif last - b <= TAIL * 100:       # after the last word: mute to the end
            out.append((max(0.0, a / 100 - 0.015), len(x) / SR))
    return out


def mute(x: np.ndarray, spans, fade: float = 0.01) -> np.ndarray:
    """Silence the spans (seconds) with short fades; the length is unchanged."""
    y = np.array(x, dtype=np.float32, copy=True)
    f = int(fade * SR)
    for t0, t1 in spans:
        a, b = max(0, int(t0 * SR)), min(len(y), int(t1 * SR))
        if b <= a:
            continue
        if a > 0:
            k = min(f, a)
            y[a - k:a] *= np.linspace(1, 0, k)
        if b < len(y):
            k = min(f, len(y) - b)
            y[b:b + k] *= np.linspace(0, 1, k)
        y[a:b] = 0
    return y


def _load(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _save(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description="find (and mute) TTS edge beeps in an assembled narration")
    ap.add_argument("narration")
    ap.add_argument("timeline")
    ap.add_argument("--apply", action="store_true", help="mute in place (a copy is kept as *.orig.wav)")
    a = ap.parse_args()
    path = Path(a.narration)
    x = _load(path)
    lines = json.loads(Path(a.timeline).read_text())["lines"]
    spans = []
    for l in lines:
        s0, s1 = max(0.0, l["start"] - 0.05), min(len(x) / SR, l["end"] + 0.05)
        for t0, t1 in find_beeps(x[int(s0 * SR):int(s1 * SR)]):
            spans.append((s0 + t0, s0 + t1))
            print(f"{l['id']}  {s0 + t0:7.2f}-{s0 + t1:7.2f}s  ({'head' if t0 == 0 else 'tail'})")
    print(f"{len(spans)} beeps")
    if a.apply and spans:
        orig = path.with_suffix(".orig.wav")
        if not orig.exists():
            shutil.copy(path, orig)
        _save(path, mute(x, spans))
        print(f"muted -> {path} (original: {orig})")


if __name__ == "__main__":
    main()
