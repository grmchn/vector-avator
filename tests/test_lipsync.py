"""Tests for tools/lipsync/lipsync.py with a synthetic WAV (no TTS or project assets needed).
run: .venv/bin/python -m pytest tests/test_lipsync.py -q
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/lipsync/lipsync.py"
sys.path.insert(0, str(TOOL.parent))
import lipsync as ls  # noqa: E402

SR = 16000


def write_wav(path, bursts):
    """Silence with tone bursts at the given (start, end) seconds."""
    x = np.zeros(int(SR * 3.0), dtype=np.float32)
    for a, b in bursts:
        t = np.arange(int(SR * a), int(SR * b)) / SR
        x[int(SR * a):int(SR * b)] = 0.5 * np.sin(2 * np.pi * 220 * t)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def test_kana_shapes():
    assert ls.ja_shapes("きゃら") == ["a", "a"]  # small kana changes the previous mora
    assert ls.ja_shapes("こんにちは") == ["o", "sil", "i", "i", "a"]
    assert ls.ja_shapes("らーめん") == ["a", "a", "e", "sil"]
    assert ls.ja_shapes("漢字") == []


def test_english_shapes():
    assert ls.en_shapes("hello") == ["e", "o"]
    assert ls.en_shapes("time") == ["i", "e"]
    assert ls.en_shapes("bomb")[-1] == "sil"


def test_voiced_spans_follow_the_audio(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, [(0.5, 1.2), (1.8, 2.4)])
    x, sr = ls.read_wav(str(p))
    spans = ls.voiced_spans(x, sr)
    assert len(spans) == 2
    assert abs(spans[0][0] - 0.5) < 0.03 and abs(spans[0][1] - 1.2) < 0.03
    assert abs(spans[1][0] - 1.8) < 0.03 and abs(spans[1][1] - 2.4) < 0.03


def test_cli_voiced_and_rms(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, [(0.5, 1.2), (1.8, 2.4)])
    out = tmp_path / "v.json"
    subprocess.run([sys.executable, str(TOOL), str(p), "--text", "あいうえお", "-o", str(out)], check=True)
    j = json.loads(out.read_text())
    assert j["method"] == "voiced" and abs(j["duration"] - 3.0) < 1e-3
    shapes = [k["mouth"] for k in j["keys"] if k["mouth"] != "sil"]
    assert shapes == ["a", "i", "u", "e", "o"]
    # the mouth is shut outside the voiced spans
    assert all(0.45 <= k["t"] <= 2.45 for k in j["keys"])
    out2 = tmp_path / "r.json"
    subprocess.run([sys.executable, str(TOOL), str(p), "--method", "rms", "-o", str(out2)], check=True)
    r = json.loads(out2.read_text())
    assert r["keys"][0]["mouth"] == "sil" and any(k["mouth"] == "a" for k in r["keys"])
