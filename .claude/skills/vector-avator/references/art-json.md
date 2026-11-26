# art.json の形式と QA ケース

`vector.json`（`parts-spec.md`）は、ここで説明する `art.json`（schema_version 1）の上位互換です。部品（`parts`）と `qa` の書き方は同じで、`vector.json` はそこに骨格の目印・腕・揺れ物・首振り・表情を足します。`tools/vector/check_parts.py` は、`tools/vector/layers/vector_layers.py` で `validate` と `build`（SVG の書き出し）を行います。

ベクター立ち絵では線を描かないため、例の `stroke`・`width` は `null`・0 にします。

## art.json

```json
{
  "schema_version": 1,
  "width": 1024,
  "height": 1024,
  "parts": [
    {
      "id": "Arm_L",
      "label": "腕・画面左",
      "parent": null,
      "pivot": [350, 500],
      "visible": true,
      "coverage": "肩は上着の内側まで丸く閉じる。支点から±12度の回転で確認する。",
      "shapes": [
        {
          "name": "complete_arm",
          "d": "M 348 472 C 320 470 292 520 288 570 C 286 598 313 609 326 580 L 369 505 Q 378 480 348 472 Z",
          "fill": "#FFD7BE",
          "stroke": "#15203B",
          "width": 7
        }
      ]
    }
  ],
  "qa": [
    {
      "name": "reveal_shoulders",
      "kind": "reveal",
      "hide": ["Torso"],
      "check": "胴体を隠して、腕が丸い肩まで完結しているか確認"
    },
    {
      "name": "arm_outward",
      "kind": "move",
      "transforms": {"Arm_L": {"deg": 12, "dx": -8}},
      "check": "腕を回転して肩と服の接続に透明な穴が出ないか確認"
    }
  ]
}
```

上は説明用の**抜粋**。`Torso` が省かれているためそのまま検証には通らない。実行できる全体例は `../assets/mini-character.json`（線あり・大文字の部品名の古い形式。ベクター立ち絵では塗りだけ・小文字のスネークケースにする）。

- `parts` の配列順がそのまま描画順。0が一番奥。`parent` の先後は描画順と独立。
- すべて元画像と共通の画面座標。右が+X、下が+Y。部品単位のローカル座標に混ぜない。
- `pivot` はその座標系の支点。腕なら肩、髪束なら根元。部品の重心とは限らない。
- `coverage` に補完範囲を具体的に書く。隠れない模様なら「顔上のハイライト。補完不要」等と記す。コメントがあるだけで補完できたとは判定しない。
- 色は `#RRGGBB` または `null`。線があるときは正の `width`。背景用の大きな白い矩形を加えない。
- 1つの塗りパスは1つの閉じた輪郭。穴や複数輪郭、グラデーション、部分透明、SVGマスク、クリップ、外部画像、フィルタはこの実装の対象外。
- `M/L/C/Q/Z` で作画する。円弧 `A` は三次ベジェへ直してから入力。滑らかな線・丸い線端を既定にしている。鋭角や線端が重要なら、輪郭自体を塗りの閉曲線にする方が両形式で一致させやすい。
- 表情差分は `visible:false`。通常の開いた目と閉じた口は `true`。

## QAケース

`kind` は `reveal / move / expression`。`hide / show` はそのIDだけに作用し、親の非表示を子へ伝播させない。`transforms` は親から子へ継承する。親を移動したのに目が顔から外れるなら `parent` を直す。

`transforms` は部品ごとに `dx / dy / deg`。正の `deg` は画面上で時計回り。回転は `pivot` 周り、移動はその後。各ケースはニュートラルからの独立したテストで、前のケースの変形を引き継がない。

最低限 `reveal` と `move` が必要。実際には絵に応じて左右両方向、顔・肩・脚・髪など別々の接合部を調べる。すべてに同じ角度を固定で押し付けない。ユーザーが指定する動作範囲があればそれを使う。

例：`{"name":"blink","kind":"expression","hide":["Eye_L","Eye_R","Lashes_R"],"show":["Lid_L","Lid_R"],"check":"開眼やまつ毛の残像がなく自然に閉じるか"}`。実際に存在するIDだけを書く。



<!-- source: the rebuild-character-layers skill, adapted for vector-avator -->
