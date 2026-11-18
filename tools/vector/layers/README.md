# vector_layers.py

`vector.json`（`art.json` の上位互換）を検査し、Inkscape レイヤー付きの SVG・部品ごとの SVG に書き出すスクリプトです。

- 出所：Skill `rebuild-character-layers`（作者の個人 Skill）の `scripts/vector_layers.py` を複製したものです。
- `tools/vector/check_parts.py` が `validate` と `build` に使います。
- 依存：`svgpathtools`、`Pillow`（`qa` だけ Inkscape の CLI も必要。`check_parts.py` は `qa` を使いません）。
