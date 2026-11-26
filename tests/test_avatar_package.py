"""Tests for the avatar package loader (docs/avatar-package.md)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "avatar"))

import package as PKG  # noqa: E402


def test_all_characters_load_and_validate():
    ids = PKG.ids()
    assert {"usagi"} <= set(ids)
    for c in ids:
        assert PKG.validate(PKG.load(c, resolve_defaults=False)) == [], c
        p = PKG.load(c)
        assert p["id"] == c and p["vector"]["url"].endswith("vector.json")


def test_empty_definition_gives_the_old_tool_defaults():
    p = PKG.resolve({"id": "x", "label": "x"})
    assert p["schemaVersion"] == 0
    assert p["voice"]["ja"] == {"engine": "files", "voice": ""}
    assert p["rig"]["rest"]["upperArm"] == 70.0                           # build_timeline.py --rest-upper
    assert p["voice"]["timing"]["lineGap"] == 0.28 and p["voice"]["timing"]["sceneGap"] == 0.8
    assert p["acting"]["beat"] == {"amp": 1.0, "rate": 1.0}               # perform.DEFAULT_HABITS
    assert p["capture"]["bg"] == "dde6f2"                                 # simple_compose.py --bg


def test_partial_fields_merge_with_defaults_and_do_not_leak():
    p = PKG.resolve({"id": "x", "voice": {"ja": {"voice": "voice_a"}}, "rig": {"hands": {"shapeScale": {"open": 0.8}}}})
    assert p["voice"]["ja"] == {"engine": "files", "voice": "voice_a"}
    assert p["voice"]["en"]["voice"] == ""
    assert p["rig"]["hands"]["shapeScale"] == {"open": 0.8} and p["rig"]["hands"]["type"] == "mitten"
    # the defaults themselves are not changed by a resolve
    assert PKG.DEFAULTS["rig"]["hands"]["shapeScale"] == {}
    assert PKG.resolve({"id": "y"})["voice"]["ja"]["voice"] == ""


def test_voice_for_expression():
    p = PKG.resolve({"id": "x", "voice": {"ja": {"voice": "voice_a"}, "byExpression": {"smile": "voice_b"},
                                          "emotion": {"surprise": "surprise"}}})
    assert PKG.voice_for(p, "ja") == "voice_a"
    assert PKG.voice_for(p, "ja", "smile") == "voice_b"
    assert PKG.voice_for(p, "ja", "trouble") == "voice_a"
    assert PKG.emotion_for(p, "surprise") == "surprise" and PKG.emotion_for(p, "smile") is None


def test_validate_reports_bad_values():
    errs = PKG.validate({"id": "x", "schemaVersion": 9, "rig": {"hands": {"type": "claw", "scale": 0}, "turn": "spin",
                                                                  "rest": {"upperArm": 120}},
                         "persona": {"status": "ok"}, "capture": {"bg": "#fff", "crop": 1.5}})
    assert len(errs) == 8, errs


def test_sample_has_persona_and_acting():
    raw = json.loads(PKG.path_of("usagi").read_text())
    assert raw["persona"]["examples"] and raw["acting"]
    assert PKG.load("usagi")["voice"]["ja"]["engine"] == "files"


def test_tts_args_use_the_copied_voice(tmp_path, monkeypatch):
    vdir = tmp_path / "public/characters/x/voice/v1"
    (vdir / "ref").mkdir(parents=True)
    (vdir / "voice.json").write_text(json.dumps({"method": "ref", "lora": None, "caption": None,
                                                 "refs": [{"path": "ref/01_a.wav"}]}))
    monkeypatch.setattr(PKG, "ROOT", tmp_path)
    p = PKG.resolve({"id": "x", "voice": {"ja": {"voice": "v1", "dir": "characters/x/voice/v1"},
                                          "byExpression": {"smile": "other"}, "emotion": {"surprise": "surprise"}}})
    args = PKG.tts_args(p, "ja")
    assert args[0] == "--ref-wavs" and args[1].endswith("characters/x/voice/v1/ref/01_a.wav") and "--voice" not in args
    assert PKG.tts_args(p, "ja", "smile") == ["--voice", "other"]
    assert PKG.tts_args(p, "ja", "surprise")[-2:] == ["--emotion", "surprise"]
    # a LoRA voice keeps the library's adapter (by id) and uses the copied references
    (vdir / "voice.json").write_text(json.dumps({"method": "lora", "lora": {"reference": True}, "caption": "c",
                                                 "refs": [{"path": "ref/01_a.wav"}]}))
    args = PKG.tts_args(p, "ja")
    assert args[:2] == ["--voice", "v1"] and "--ref-wavs" in args and args[-2:] == ["--caption", "c"]
    # not copied: by id
    assert PKG.tts_args(PKG.resolve({"id": "y"}), "ja") == ["--voice", ""]
