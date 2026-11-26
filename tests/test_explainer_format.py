"""Tests for the three-layer explainer data (docs/explainer-format.md)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import explainer_format as EF  # noqa: E402

SAMPLES = ROOT / "data/explainer/samples"
KEYS = ("id", "scene", "gesture", "expr", "ja", "ja_tts", "ja_kana", "en", "en_tts")


def sample(name):
    return EF.load_dir(SAMPLES / name)


@pytest.mark.parametrize("name", ["vector_howto", "agi_singularity"])
def test_samples_pass_the_checks(name):
    errs, content, _ = EF.check_dir(SAMPLES / name)
    assert errs == [] and content["lines"]
    for p in (SAMPLES / name).glob("legacy_*/script.*.json"):
        assert EF.check_script(EF.read_json(p), content) == [], p


@pytest.mark.parametrize("name,char,src", [("vector_howto", "usagi", "var/original_script.json")])
def test_legacy_form_reproduces_the_original_script(name, char, src):
    p = ROOT / src
    if not p.is_file():
        pytest.skip("the original script (outputs/) is not in the repository")
    orig = json.loads(p.read_text())["lines"]
    content, _ = sample(name)
    script = EF.read_json(SAMPLES / name / "legacy_id057" / f"script.{char}.json")
    assert EF.check_script(script, content) == []
    got = EF.to_legacy(content, script)["lines"]
    assert len(got) == len(orig)
    for o, g in zip(orig, got):
        for k in KEYS:
            assert g.get(k) == o.get(k), (o["id"], k)
        assert g["icon"] == o.get("icon", "")


def test_default_acting():
    assert EF.default_acting({"tags": [{"tag": "greet"}], "emotion": "joy"}) == ("spread", "smile")
    assert EF.default_acting({"tags": [{"tag": "demo", "motion": "turn"}]}) == ("turn", "neutral")
    # a term tag does not decide the gesture
    assert EF.default_acting({"tags": [{"tag": "emphasize", "term": "x"}, {"tag": "think"}]}) == ("think", "neutral")
    assert EF.default_acting({}) == ("explain", "neutral")


def test_override_wins():
    content, _ = sample("vector_howto")
    script = EF.read_json(SAMPLES / "vector_howto" / "legacy_id057" / "script.usagi.json")
    legacy = {ln["id"]: ln for ln in EF.to_legacy(content, script)["lines"]}
    assert legacy["L02"]["gesture"] == "nod"            # tag introduce -> explain, overridden
    assert EF.default_acting(content["lines"][1])[0] == "explain"


def broken(name, char, fn_content=None, fn_script=None):
    content, _ = sample(name)
    scripts = {char: EF.read_json(SAMPLES / name / "legacy_id057" / f"script.{char}.json")} if char else {}
    content = copy.deepcopy(content)
    if fn_content:
        fn_content(content)
    errs = EF.check_content(content)
    if char and not any(e.startswith("content: ") for e in errs):
        script = copy.deepcopy(scripts[char])
        if fn_script:
            fn_script(script)
        errs += EF.check_script(script, content)
    return errs


def test_broken_content_is_reported():
    A = "agi_singularity"
    assert any("'n'" in e for e in broken(A, None, lambda c: c["lines"][2]["tags"][0].pop("n")))
    assert any("is not one of" in e for e in broken(A, None, lambda c: c["lines"][0]["tags"].append({"tag": "dance"})))
    assert any("region" in e for e in broken(A, None, lambda c: c["lines"][2]["tags"][1].update(region="sky")))
    assert any("not in terms" in e for e in broken(A, None, lambda c: c["lines"][2]["terms"].remove("汎用人工知能")))
    assert any("duplicate" in e for e in broken(A, None, lambda c: c["lines"][1].update(id="L01")))


def test_broken_script_is_reported():
    V, U = "vector_howto", "usagi"
    assert any("lines differ" in e for e in broken(V, U, fn_script=lambda s: s["lines"].pop()))
    assert any("order differs" in e for e in broken(V, U, fn_script=lambda s: s["lines"].reverse()))
    assert any("no anchor" in e for e in broken(V, U, fn_script=lambda s: s["lines"][4].pop("anchors")))
    assert any("not in ja_kana" in e for e in
               broken(V, U, fn_script=lambda s: s["lines"][4]["anchors"]["設計図"].update(kana="ぜろ")))
    assert any("not in the subtitle" in e for e in
               broken(V, U, fn_script=lambda s: s["lines"][4]["anchors"]["設計図"].update(ja="図面")))
    assert any("other than hiragana" in e for e in broken(V, U, fn_script=lambda s: s["lines"][0].update(ja_kana="コンニチハ")))
    assert any("data/characters" in e for e in broken(V, U, fn_script=lambda s: s.update(char="nobody")))
