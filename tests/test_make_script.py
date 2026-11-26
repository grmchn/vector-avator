"""Tests for the script-layer rewrite tools: the brief and the rewrite warnings."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))
sys.path.insert(0, str(ROOT / "tools" / "avatar"))

import explainer_format as EF  # noqa: E402
import make_script as MS  # noqa: E402
import package as PKG  # noqa: E402

SAMPLES = ROOT / "data/explainer/samples"


@pytest.mark.parametrize("name", ["vector_howto", "agi_singularity"])
@pytest.mark.parametrize("char", ["usagi"])
def test_brief_is_filled(name, char):
    text = MS.brief(SAMPLES / name, char)
    assert "{{" not in text
    p = PKG.load(char)["persona"]
    assert p["firstPerson"] in text and p["tone"] in text
    content, _ = EF.load_dir(SAMPLES / name)
    for ln in content["lines"]:
        assert f"### {ln['id']}" in text and ln["gist"] in text


def test_mora():
    assert MS.mora("きょうは") == 3          # きょ・う・は
    assert MS.mora("えーじーあい") == 6
    assert MS.mora("、 。") == 0


def legacy():
    content, _ = EF.load_dir(SAMPLES / "vector_howto")
    return content, EF.read_json(SAMPLES / "vector_howto/legacy_id057/script.usagi.json")


def test_original_wording_has_no_rewrite_warnings_for_its_presenter():
    content, script = legacy()
    assert MS.rewrite_warnings(content, script, PKG.resolve({"id": "x"})) == []


def test_rewrite_warnings():
    content, script = legacy()
    s = copy.deepcopy(script)
    s["lines"][0]["ja_kana"] = "あ"                                   # far too short
    s["lines"][1]["ja"] = "ぼくがぜんぶ見せちゃうね。"                    # first person not the persona's
    s["lines"][2]["ja"] = s["lines"][2]["ja"].replace("画像生成", "AI の絵")   # a term rewritten away
    s["lines"][3]["ja_tts"] = "次に、動画生成AIで"                       # letters left for TTS
    s["lines"][4]["ja"] = "あ" * 80                                     # subtitle too long
    pkg = PKG.resolve({"id": "x", "persona": {"firstPerson": "ワタシ"}})
    w = MS.rewrite_warnings(content, s, pkg)
    assert any(x.startswith("L01: length") for x in w)
    assert any(x.startswith("L02: first person ぼく") for x in w)
    assert any("L03: the term '画像生成'" in x for x in w)
    assert any(x.startswith("L04: ja_tts still has letters") for x in w)
    assert any(x.startswith("L05: subtitle is 80") for x in w)


def test_first_person_inside_another_word_is_not_doubled():
    content, script = legacy()
    s = copy.deepcopy(script)
    s["lines"][1]["ja"] = "わたくしがぜんぶ見せます。"
    w = MS.rewrite_warnings(content, s, PKG.resolve({"id": "x", "persona": {"firstPerson": "わたくし"}}))
    assert not any("first person" in x for x in w)
