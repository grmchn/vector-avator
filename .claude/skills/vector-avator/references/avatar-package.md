# アバターパッケージ（キャラ定義）

解説動画のキャラを、キャラ ID の指定だけで差し替えるための、キャラ定義 `data/characters/<id>.json` の規格です。見た目（`vector`）に、骨格の調整・声・性格・演技の癖・撮影の既定値を足します。すべて省略でき、省略した項目は既定値になります。見本は `data/characters/usagi.json` です。

## 1. 目的

解説動画のキャラを、キャラ ID の指定だけで差し替えられるようにする。


新しいファイル形式は作らず、既存のキャラ定義に項目を足す。ビューアは今の項目（`vector`・`urlDefaults` など）をそのまま読み、新しい項目は無視してよい。

## 2. 決まりごと

- **素材は参照する。声はコピーする:** 部品 SVG・3D モデルは URL で参照する。声は、Irodori-TTS-Custom の声をキャラの素材フォルダ `public/characters/<id>/voice/<声 ID>/` へコピーし、そのコピーから合成する。素材も声のコピーもコミットしない。
- **すべて省略可能:** 省略した項目は、今の道具の既定値と同じ動作になる（§5 の表）。古い定義（`schemaVersion` なし）も読める。
- **キャラ設定はユーザーが決める:** 声の割り当て・性格・口調・演技の癖は、エージェントが案を出し、ユーザーが確定する。確定前の値には `"status": "draft"` を付ける。
- **読み込みは 1 か所:** TypeScript は `CharacterConfig`（`src/core/renderer.ts`）、Python は `tools/avatar/package.py` の `load(char_id)` で読み、既定値の補完もそこで行う。道具が JSON を直接読まない。

## 3. 全体の形

```json
{
  "schemaVersion": 1,
  "id": "a twin-tail character",
  "label": "ツインテールのキャラ",

  "vector": { "url": "characters/a twin-tail character/vector/vector.json" },
  "urlDefaults": {},

  "rig": {
    "hands": { "type": "beast", "scale": 0.8, "shapeScale": { "open": 0.8 } },
    "rest": { "upperArm": 70 },
    "turn": "turn90_opp"
  },

  "voice": {
    "ja": { "engine": "irodori", "voice": "a twin-tail character" },
    "en": { "engine": "drama3", "voice": "a twin-tail character" },
    "byExpression": {},
    "speed": 1.0,
    "timing": { "lineGap": 0.28, "sceneGap": 0.8, "maxPause": 0.22 }
  },

  "persona": {
    "status": "draft",
    "firstPerson": "ツインテールのキャラ",
    "callsViewer": "みんな",
    "endings": ["〜だよ", "〜なの", "〜でしょ？"],
    "tone": "明るく素直。ちょっといたずら好き。",
    "avoid": ["難しい漢語の連続", "命令口調"],
    "examples": ["はじめまして、ツインテールのキャラだよ！", "ここ、大事だからね。"]
  },

  "acting": {
    "status": "draft",
    "gestureScale": 1.2,
    "tempo": 1.15,
    "beat": { "amp": 1.2, "rate": 1.15 },
    "gestureWeights": { "spread": 1.5, "explain": 1.0, "think": 0.5 },
    "tiltRate": 0.3,
    "blinkRate": 1.0
  },

  "capture": { "bg": "dde6f2", "crop": 0.6, "ph": 0.84, "py": null }
}
```

方式 A〜D 用の `model3d`・`parts2d`・`faces2d` は今のまま残す。

## 4. 項目

### 4.1 基本・見た目（既存）

| 項目 | 型 | 内容 |
|---|---|---|
| `schemaVersion` | 整数 | 規格の版。本案は `1`。省略時は `0`（今の形）として読む |
| `id`・`label` | 文字列 | キャラ ID と表示名 |
| `vector.url` | 文字列 | ベクター立ち絵の `vector.json`（`public/` からの相対） |
| `urlDefaults` | 文字列の辞書 | ビューアの URL パラメータの既定値（輪郭線 `vOuter`・`vLine` など） |
| `model3d`・`parts2d`・`faces2d` | — | 方式 A〜D 用（今のまま） |

### 4.2 骨格・能力 `rig`

| 項目 | 型 | 内容 | 今の場所 |
|---|---|---|---|
| `hands.type` | `mitten`・`beast`・`human` | 手のテンプレートのタイプ | `tools/vector/hands/apply.py` の引数 |
| `hands.scale` | 数値 | 手の大きさ | `apply.py` の `SCALE` |
| `hands.shapeScale` | 形 → 倍率 | 形ごとの追加の倍率 | `apply.py` の `SHAPE_SCALE` |
| `hands.dropLines` | 形の配列 | 内側の線を省く形 | `apply.py` の `DROP_LINES` |
| `hands.colors` | `base`・`line`・`pad` | 手の塗り・線・肉球の色 | `apply.py` のキャラ別の色 |
| `hands.unavailable` | 形の配列 | 使えない手の形（代わりの形に置き換える） | なし |
| `rest.upperArm` | 度 | 待機ポーズの上腕の角度（水平から下向き） | `build_timeline.py` の `--rest-upper` |
| `turn` | 下の表 | 回転の対応範囲。演技層はこの範囲を超える向きを作らない ||

`turn` の値は次のとおり。

| 値 | 意味 | 該当（現時点） |
|---|---|---|
| `front` | 正面のみ（頭も回さない） | 黒い太線のキャラ |
| `parallax30` | 頭の視差で ±30° | 別のキャラ |
| `turn90` | ターンエンジンで ±90°（鍵の頭・体＋中割り） | 仮うさぎ |
| `turn90_opp` || ツインテールのキャラ・毛の多いキャラ・斜めがけのかばんのキャラ |

### 4.3 声 `voice`

| 項目 | 型 | 内容 | 既定（今の動作） |
|---|---|---|---|
| `ja.engine`・`ja.voice` | 文字列 | 日本語の TTS と声 ID。`files`（TTS を使わず、行ごとの wav を自分で置く）・`command`（任意の TTS のコマンドを呼ぶ。`ja.command`）・`irodori`（Irodori-TTS-Custom。場所は環境変数 `IRODORI_HOME`） | `files`・空 |
| `ja.command` | 文字列の配列 | `command` のときのコマンドと引数。`{text}`（読み）・`{out}`（出力の wav）・`{expr}`（表情）・`{seed}`・`{speed}` を差し込む。例：`["my-tts", "--text", "{text}", "-o", "{out}"]` | なし |
| `ja.dir` | 文字列 | パッケージにコピーした声のフォルダ（`public/` からの相対。§4.3.1）。ないときは声 ID でライブラリを引く | なし |
| `en.*` | — | 英語の声（形は `ja` と同じ。解説動画の道具は今は日本語のみ） | `files`・空 |
| `byExpression` | 表情 → 声 ID | 表情ごとに声を替える（例：`smile` → 明るい声の ID） | なし |
| `emotion` | 表情 → 感情名 | 表情ごとに `--emotion` を付ける（Irodori-TTS-Custom の感情差分） | なし |
| `speed` | 数値 | 話速の倍率 | `1.0` |
| `timing.lineGap`・`sceneGap` | 秒 | 行の間・シーンの切り替わりの間 | `0.28`・`0.8`（`build_timeline.py` の `GAP`・`SCENE_GAP`。場面の間は G12 で 0.8 秒に決定） |
| `timing.maxPause` | 秒 | 行の中の間の上限（`0` は切らない） | `0` |


### 4.4 性格・口調 `persona`

| 項目 | 型 | 内容 |
|---|---|---|
| `status` | `draft`・`approved` | ユーザーの確認状態 |
| `firstPerson` | 文字列 | 一人称 |
| `nameReading` | 文字列 | 名前の読み（カタカナ）。表示名がそのまま読めないとき |
| `callsViewer` | 文字列 | 視聴者の呼び方 |
| `endings` | 文字列の配列 | 好んで使う語尾 |
| `tone` | 文字列 | 口調の説明（1〜3 文） |
| `avoid` | 文字列の配列 | 言わないこと・使わない言い回し |
| `examples` | 文字列の配列 | 例文 3〜5 行 |

### 4.5 演技の癖 `acting`

| 項目 | 型 | 内容 | 既定 |
|---|---|---|---|
| `status` | `draft`・`approved` | ユーザーの確認状態 | — |
| `style` | 文字列 | 演技の方向の説明 | なし |
| `gestureScale` | 数値 | 身振りの大きさの倍率 | `1.0` |
| `tempo` | 数値 | 身振りの速さの倍率 | `1.0` |
| `beat.amp`・`beat.rate` | 数値 | ビートジェスチャーの大きさと頻度（今の `perform.py` の `HABITS`） | `1.0` |
| `gestureWeights` | ジェスチャー → 重み | 意味タグからジェスチャーを選ぶときの好み | すべて `1.0` |
| `tiltRate` | 0〜1 | 考える・問いかけの行で首をかしげる割合 | `0.3` |
| `blinkRate` | 数値 | まばたきの頻度の倍率 | `1.0` |

### 4.6 撮影 `capture`

| 項目 | 型 | 内容 | 既定（今の動作） |
|---|---|---|---|
| `bg` | 16 進の色 | 背景色（白いキャラが白背景に溶けないように） | `dde6f2`（`simple_compose.py`） |
| `crop` | 0〜1 | 司会役の動画の中央の切り出し幅 | なし（切り出さない） |
| `ph`・`py` | 0〜1 | 画面の中の司会役の高さと上端 | `layout.json` の値 |
| `bust` | オブジェクト | バストアップの小窓の枠の調整：`top`（頭の上の余白、頭の高さに対する割合）・`bot`（下端。0＝首、1＝腰）・`w`（幅÷高さ）・`x`（左右のずれ）・`follow`（首の動きにカメラが付いていく割合）・`lag`（その遅れ、秒）。`capture.sh` に `FRAMING=bust` を付けると使う | `top` 0.22・`bot` 0.55・`w` 1・`x` 0・`follow` 0.6・`lag` 0.3 |
| `rim` | オブジェクト | 淡い部分の輪郭線：`color`（16 進の色）・`minL`（この CIE L* 以上の塗りを「淡い」とみなす）・`width`（太さ、描画座標の px）。白に近い肌のキャラを淡い背景に置くとき、淡い部分のシルエットの外側にだけ薄い線を引く。ビューアの URL の `vRim`・`vRimL`・`vRimW` に当たる（`package.py` の `rim_query`）。撮影の枠の端で切れた所には線が出ない | なし（引かない）。`minL` 88・`width` 4.5 |


## 6. 道具の対応

解説動画の道具は `--avatar <キャラ ID>` でパッケージを読む（手順は `tools/explainer/README.md`）。

| 道具 | パッケージから取るもの |
|---|---|
| `tools/explainer/tts.py` | `voice`（コピーした声、`byExpression`・`emotion`、`speed` → `--duration-scale`） |
| `tools/explainer/build_timeline.py` | `rig.rest.upperArm`、`voice.timing`、`acting`（演技層 `perform.act`：`gestureWeights`・`gestureScale`・`tempo`、ビートの `beat`） |
| `tools/explainer/capture.sh`・`simple_compose.py` | `capture`（背景色・切り出し） |

`perform.py` にあった仮置きの `HABITS` はパッケージの `acting.beat` に置き換えた（`perform.habits_for()`）。手のテンプレートの倍率・色（`tools/vector/hands/apply.py` の `SCALE`・`COLORS`）はまだ道具側にあり、パッケージの `rig.hands` と同じ値を持つ（手の作り直しのときに移す）。`acting.tiltRate`・`blinkRate` はまだ使っていない。

## 7. 検査と共通テスト

### 7.1 規格の検査 `tools/avatar/check.py`

```bash
.venv/bin/python tools/avatar/check.py <キャラ ID> [...]   # --all で全キャラ、--quick で部品の検査を省く、--json で結果を保存
```

結果は「エラー」と「警告」に分かれ、エラーが 0 件なら合格（終了コード 0）とする。

| 区分 | エラー | 警告 |
|---|---|---|
| 定義 | 型・値の誤り、`id`・`label`・`vector.url` の欠け | `schemaVersion` がない |
| 部品 | `vector.json` がない、`check_parts.py` のエラー（宣言した回転範囲の向きの部品も検査する） | `check_parts.py` の警告 |
| 回転 | `rig.turn` に必要な向きの部品がない（`turn90`：体と頭の 30°・60°・90°、`turn90_opp`：さらに反対向きの頭） | 宣言より多い向きの部品がある、`rig.turn` が未宣言 |
| 手 | 左右どちらかに、元からの 4 形（`open`・`point`・`fist`・`palm`）がない | 新しい 4 形（`palm_up`・`point_front`・`peace`・`thumbs_up`）がない（`rig.hands.unavailable` に書けば警告しない）、`rig.hands.type` が未宣言 |
| 声 | 声 ID がライブラリにない、コピーの記録 `voice.json` がない、参照音声が欠けている・記録と違う（sha256）、LoRA のアダプタがライブラリにない | 声をパッケージにコピーしていない、ライブラリの LoRA が取り込み後に変わった、英語の `drama3` の声ファイルがない |
| 性格・演技 | — | 未記入、ユーザー未承認（`draft`） |

