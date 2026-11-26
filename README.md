# vector-avator

**English summary:** vector-avator turns a single character illustration into a 2D vector avatar that moves with a 3D skeleton: gestures with generated arms and 8 hand shapes, head turns up to ±30° (optionally the whole body up to ±90° with turned key drawings and in-betweens), swinging ears and tails, automatic outlines, living eyes (blinks, micro saccades, gaze) and an idle weight shift, lip-sync, video export, and an explainer-video pipeline (content / script / semantic tags -> gestures, pointing, beats, pauses, weight shifts from foot to foot and short expression accents -> TTS of your choice -> capture -> compose). Motion rules learned from reviews are written down for agents. It runs in the browser (TypeScript + Canvas 2D, no 3D model). A Claude Code skill (`.claude/skills/vector-avator/`) walks you through making your own character: Codex imagegen restyles the picture and draws two character sheets, then Fable 5.2 draws the fill-only SVG parts. The sample character "Kariusagi" is included. Documentation is in Japanese.

---

一枚のキャラ絵から、身振り手振りで動く 2D のベクターアバターを作るためのリポジトリです。

![仮うさぎが話して、両手を広げて、跳ねる](docs/media/kariusagi.gif)

（音声なしの見本動画：[docs/media/kariusagi_demo.mp4](docs/media/kariusagi_demo.mp4)）

## できること

- **3D の骨格で動く 2D：** 部品はベクター（SVG のパス）で、骨格の動きに合わせて動きます。3D モデルは要りません。
- **腕は描かずに生成：** 上腕・前腕を長さの決まった 3D の骨として動かし、2D に投影して描きます。肘で曲がり、奥行きで太さが変わり、胴の前・後ろを自動で切り替えます。画面の一点を指す腕の IK もあります。
- **手は 8 種：** 開き・手のひら・手のひら上・指差し・カメラへの指差し・グー・ピース・いいね。人の手・けもの型（親指＋3 本）・ミトン型・棒型のテンプレートを、キャラに合わせて載せられます。手のひらの向きと体の向きから、手の絵を自動で選びます。
- **首振り ±30°：** 正面の絵 1 枚を、顔の球面に沿って変形させて向きを変えます。
- **体ごと ±90°（オプション）：** 体と頭の回転の絵（30°・60°・90°）を描き足すと、その間を中割りでつないで真横まで向きます。見本の仮うさぎには同梱していますが、ビューアの既定は「使わない」です。
- **揺れ物：** 耳・ツインテール・しっぽが、ばねの計算で遅れて揺れます。
- **自動輪郭線：** 部品は塗りだけで、線は描画時に引きます。手前の部品が同じか近い色の部品に重なる縁にだけ線が出ます。手描き風の線（強弱・揺らぎ・ボイル）も選べます。
- **表情と口パク：** 目（開・半目・閉）、口（無音・あ・い・う・え・お）、表情 4 種（通常・笑顔・驚き・困り）。テキストや音声から口パクを作れます。
- **止まらない体と目：** 自動まばたき、目の泳ぎ（虹彩が小さく跳ぶ）、呼吸、重心の左右移動（待機の微動）を、モーションに重ねて常に入れます。
- **動きのルール：** 実際に動画をレビューして分かった「自然に見える動き」のルール（ニコニコの目で止めない、腰を動かし続ける、カメラ目線を基本にする、同じ身振りを続けない、など）を、エージェント向けにまとめています（`.claude/skills/vector-avator/references/motion-rules.md`）。モーションの検査ツールもあります。
- **解説動画：** 内容・台本・意味タグの 3 層のデータから、身振り・指差し・声に合わせたビート・間の演技・重心の入れ替え・表情のアクセントを自動で付け、音声・撮影・合成まで 1 コマンドで書き出します。TTS は好きなものを使えます。
- **動画の書き出し：** コマごとに時計を止めて撮るので、マシンの速さに関係なく同じ動画になります。

## 動かし方

必要なもの：Node 22、npm。

```bash
git clone https://github.com/grmchn/vector-avator.git
cd vector-avator
npm install
npm run dev
```

ブラウザで `http://localhost:5280/` を開くと、仮うさぎが表示されます。モーション、体と顔の向き、目・口・表情、手の形、線の設定を画面で変えられます。

- **回転の絵：** 画面の「体と頭の回転の絵（30・60・90°）」で「使う」を選ぶか、URL に `?vBody=1` を付けると、体が ±90° まで向きます。回転を使うモーション（`turn90` など、一覧に「（回転の絵）」と付くもの）を選ぶと、自動で「使う」になります。
- **待機の微動：** 既定でオンです。止めるときは画面で切るか、URL に `?idle=0` を付けます。

動画の書き出し（開発サーバーの起動中。Playwright の Chromium と ffmpeg が必要）：

```bash
npx playwright install chromium
node tools/vector/record.mjs --out out/explain --motion explain
```

テストとビルド：`npm test`、`npm run build`。

## 自分のキャラを作る

このフォルダで [Claude Code](https://claude.com/claude-code) を開くと、Skill `vector-avator`（`.claude/skills/vector-avator/SKILL.md`）が読み込まれます。「この絵のキャラを追加して」のように頼むと、次の手順で進みます。

1. キャラの特徴の箇条書きを書く
2. 画風をそろえた正面の立ち姿を作る（Codex imagegen）
3. 360 度回転動画で角度の見本を作る（MiniMax H3、任意）
4. キャラクターシート 2 枚を作る（Codex imagegen）
5. 部品を、隠れる部分まで補完して描く（Fable 5.2 のサブエージェント）
6. 検査する
7. ビューアで動かして調整する
8. 動画と口パクを作る（TTS は任意）
9. （任意）体と頭の回転の絵を描き足す
10. （任意）声・性格・演技の癖を決めて、解説動画を作る

| 道具 | 扱い |
|---|---|
| Claude Code ＋ Fable 5.2 | 必須（部品分け） |
| Codex CLI（imagegen） | 必須（画風の変換・シート） |
| Python 3.10 以上、resvg | 必須（生成・検査の道具） |
| Node 22、Playwright の Chromium、ffmpeg | 必須（ビューア・撮影） |
| MiniMax H3（ComfyUI） | 任意 |
| TTS | 任意 |

### 費用と時間の目安（実測）

仮うさぎを作ったときの実測です。2 体目以降のキャラで、待ち時間を含めて **1 キャラ 1〜1.5 時間**でした。人の作業は、キャラの特徴の箇条書きとレビューだけです。

| 段階 | 担当 | 時間 |
|---|---|---|
| キャラの補足 | Claude | 約 10 分 |
| 正面の立ち姿（2 回生成） | Codex imagegen | 約 4.7 分 |
| 角度の見本（任意） | MiniMax H3 | 約 7 分 |
| シート 2 枚 | Codex imagegen | 約 5 分 |
| 部品分け（47 部品）＋直し | Fable 5.2 | 約 16 分 ＋ 約 2.5 分 |
| 検査・確認・調整 | Claude | 約 20 分 |

公開前の確認として、このリポジトリの経緯を知らない別の Claude Code のエージェントに、この Skill と一枚絵だけを渡して、もう 1 体（63 部品）を作らせました。角度の見本（任意）を飛ばして **約 43 分**（Codex imagegen 4 回、Fable 5.2 は 1 回で約 24 分・約 28 万トークン、作り直し 0 回）で、ジェスチャーと口パクの動画まで作れました。

Codex imagegen は ChatGPT のプランの使用量の上限に達すると、数時間待つことがあります。トークン数と金額は計測していません。

## 解説動画を作る

見本の内容（`data/explainer/samples/agi_singularity/`：AGI・RSI・シンギュラリティをかるく説明する 11 行）を、仮うさぎで書き出す例です。

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 1. 音声：見本の仮うさぎは「wav を自分で置く」設定です（TTS は問いません）。足りない wav と読みの一覧が出ます
.venv/bin/python tools/explainer/tts.py ja --content data/explainer/samples/agi_singularity --avatar usagi
#    → var/explainer/audio/agi_singularity/usagi/<行 ID>_t1.wav を置く
# 2〜4. タイムライン（演技）・撮影・合成
.venv/bin/python tools/explainer/make_video.py data/explainer/samples/agi_singularity usagi --steps timeline,capture,compose
#    → out/explainer/agi_singularity_usagi_ja.mp4
```

- TTS のコマンドを持っている場合は、`data/characters/usagi.json` の `voice.ja` を `{"engine": "command", "command": ["my-tts", "--text", "{text}", "-o", "{out}"]}` のように書くと、1 で自動で読み上げます。
- 画面の図は、`images.json` から Codex imagegen で作れます（`tools/explainer/make_images.py`）。図がない行は、文字のカードで出ます。
- 体を 15° より大きく向けるときは `--turn on`（回転の絵を使う）を付けます。
- 演技は既定で、指差し・ビート・身振りの変化・間の演技・体の向き・首の振りに加えて、体重をかける足の入れ替え（`weight`）と、笑顔・驚き・困りを行の一部だけにする表情のアクセント（`eyes`）を入れます。`tools/explainer/build_timeline.py --acting` で選べます。
- 書き出したモーションは `.venv/bin/python tools/motion/lint_motion.py data/motions/explainer/<名前>.json` で、動きのルール（ふつうの目の割合、腰が止まっている時間など）に合っているかを確かめられます。
- データの形式は `.claude/skills/vector-avator/references/explainer-format.md`、キャラ定義（声・性格・演技の癖・撮影の既定値）は `avatar-package.md` にあります。

## フォルダ構成

| 場所 | 内容 |
|---|---|
| `src/core/` | 骨格・ポーズ・モーション・顔・まばたき・目の泳ぎ・待機の微動・腕の IK・口パク（描画に依存しない） |
| `src/renderers/vector/` | 描画エンジン（腕の生成、手の形、首振り、回転の中割り、揺れ物、自動輪郭線） |
| `src/vviewer/` | ビューア |
| `data/motions/` | モーション（手付けのジェスチャー、ダンス、回転、AI 生成のモーション、解説動画の身振り `explainer_vocab/`） |
| `data/characters/` | キャラ定義（見た目・骨格の調整・声・性格・演技の癖・撮影の既定値） |
| `data/explainer/samples/` | 解説動画の見本の内容と台本 |
| `public/characters/usagi/vector/` | 見本キャラ：部品（`vector.json`）、回転の絵（`body*.json`・`head*.json`）、参照画像（`ref/`） |
| `inputs/kariusagi/` | 見本キャラの元の絵 |
| `tools/vector/` | シートの生成、部品の検査、動画の書き出し、手のテンプレート（`hands/`） |
| `tools/lipsync/` | 口パクの作成 |
| `tools/motion/` | モーションの検査（`lint_motion.py`） |
| `tools/explainer/`・`tools/avatar/` | 解説動画の道具と、キャラ定義の読み込み・検査 |
| `.claude/skills/vector-avator/` | Skill（手順書と部品仕様） |

## 更新履歴

- **2026-11-26：**
  - 体と頭の回転の絵（30°・60°・90°）と、その間の中割り（オプション。ビューアの既定は使わない）。
  - 手の形 8 種と手のテンプレート（人の手・けもの型・ミトン型・棒型）。
  - 待機の微動（重心の移動）と目の泳ぎを既定でオン。
  - 動きのルールと検査ツール（`lint_motion.py`）。
  - 解説動画の道具一式：3 層のデータ、演技（重心の入れ替え・表情のアクセントを含む）、好きな TTS、撮影、合成。
- **2026-11-18：** 最初の公開。

## このリポジトリについて

- 開発用のリポジトリから切り出した**スナップショット**です。更新は不定期です。
- Issue と Pull Request を歓迎します。このリポジトリで自由に育ててください。よい変更は、開発用のリポジトリにも取り込みます（詳しくは [CONTRIBUTING.md](CONTRIBUTING.md)）。

## ライセンス

- **コード：** [MIT License](LICENSE)
- **見本キャラ「仮うさぎ」の素材：** 動作確認用の見本です。個人の方は、改変・商用を含め自由に使えます。企業の商用利用は、X の [@grmchn4ai](https://x.com/grmchn4ai) まで DM でご連絡ください。詳しくは [ASSETS_LICENSE.md](ASSETS_LICENSE.md)。
- **モーションデータ：** `data/motions/ai/` は、NVIDIA の Kimodo と MotionBricks で生成したものです（出所は各ファイルの `source`）。
