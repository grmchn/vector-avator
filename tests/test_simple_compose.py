"""Tests for the explainer composer's text layout: subtitle and card wrapping."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "explainer"))

import simple_compose as S  # noqa: E402


def test_short_text_is_one_row():
    assert S.wrap("こんにちは、仮うさぎです。", 32) == ["こんにちは、仮うさぎです。"]


def test_wraps_at_punctuation_near_the_middle():
    rows = S.wrap("賢くなったAIが、もっと賢いAIを作って、それがさらに賢いAIを作る！このくり返しで、改良がどんどん速くなるんだ。", 41)
    assert len(rows) == 2 and rows[0].endswith("！")
    assert "".join(rows) == "賢くなったAIが、もっと賢いAIを作って、それがさらに賢いAIを作る！このくり返しで、改良がどんどん速くなるんだ。"


def test_wraps_after_a_particle_not_inside_a_word():
    rows = S.wrap("その先は、人間には予測できない世界になるって考えられてるんだ。ドキドキだね！", 36)
    assert rows[0].endswith("って") and rows[1].startswith("考え")


def test_card_text_breaks_at_its_separators():
    assert S.wrap("AGI・RSI・シンギュラリティ", 11, "、。！？・→＝↔ ") == ["AGI・RSI・", "シンギュラリティ"]


def test_every_row_fits():
    text = "まとめるね！AGIができて、RSIで自分を改良し続けると、シンギュラリティにたどり着くかもしれない、ってことだよ！"
    for n in (20, 30, 40):
        assert all(S.text_width(r) <= n for r in S.wrap(text, n))
