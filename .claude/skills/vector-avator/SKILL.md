---
name: vector-avator
description: Turn a single character illustration into a moving 2D vector avatar for this repository (vector-avator): restyle it and make two character sheets with Codex imagegen, have Fable 5.2 draw fill-only SVG parts with hidden regions completed, check them, and play gestures, head turns, blinking and lip-sync in the viewer. Use when the user wants to add a new character, redo a character's parts, or asks how the sample character was made. 一枚絵から、身振り手振りで動くベクターキャラを作る手順。
---

# 一枚絵から、動くベクターキャラを作る

このリポジトリ（vector-avator）に、新しいキャラクターを追加する手順です。キャラの一枚絵から、画風をそろえた正面の立ち姿とキャラクターシートを作り、Fable 5.2 に部品をベクターで描き起こさせ、検査してからビューアで動かします。

見本は仮うさぎ（キャラ ID `usagi`。元の絵は `inputs/kariusagi/`）です。各段階の完成品が `public/characters/usagi/vector/` と `tools/vector/sheets/characters/usagi.*` にあるので、迷ったら見比べてください。

## 0. 前提

**作業ディレクトリは、このリポジトリのルートにします。** 以下のコマンドはすべてルートからの相対パスです。

| 道具 | 扱い | 使う段階 | 確認方法 |
|---|---|---|---|
| Claude Code ＋ Fable 5.2 | **必須** | 5. 部品分け（サブエージェント） | サブエージェントのモデルに Fable 5.2 を指定できること |
| Codex CLI（imagegen） | **必須** | 2. 画風の変換、4. シート | `codex --version`、`codex login` 済み（ChatGPT のプランで動き、API キーは不要） |
| Node 22、npm | 必須 | 7. ビューア、8. 動画 | `npm install` 済み |
| Python 3.10 以上 | 必須 | 2〜6 | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| resvg | 必須 | 6. 検査の確認画像 | `resvg --version`（`cargo install resvg` など） |
| Playwright の Chromium、ffmpeg | 必須 | 7〜8. 撮影・動画 | `npx playwright install chromium`、`ffmpeg -version` |
| MiniMax H3（ComfyUI） | 任意 | 3. 角度の見本 | ComfyUI の API（既定 `http://127.0.0.1:8188`）。ない場合は 3 を飛ばす |
| TTS | 任意 | 8. 口パクの音声 | ない場合はテキストの口パクで動かす |

Fable 5.2 または Codex imagegen が使えない場合は、ユーザーにそう伝えて止まってください。部品分けを他のモデルで代用すると、品質が足りないことが分かっています。

**開発サーバーのポート：** 既定は 5280 です（`npm run dev`）。使用中の場合は `npx vite --port <ポート> --strictPort` で起動し、撮影・動画の書き出しのコマンド（`viewer_shots.mjs`、`record.mjs`）すべてに `VIEWER_URL=http://127.0.0.1:<ポート>/` を付けます。Fable に渡す依頼文にも、その URL を書きます。

## 費用と時間の目安（実測）

仮うさぎ（47 部品）を作ったときの実測です。2 体目以降のキャラで、待ち時間を含めて **1 キャラ 1〜1.5 時間**でした。人の作業は、キャラの特徴の箇条書きとレビューだけです。

| 段階 | 担当 | 時間 | 回数 |
|---|---|---|---|
| 1. キャラの補足 | Claude（メイン） | 約 10 分 | — |
| 2. 正面の立ち姿 | Codex imagegen | 約 4.7 分 | 2 回生成して 1 枚採用 |
| 3. 角度の見本（任意） | MiniMax H3 | 約 7 分 | 1 回 |
| 4. シート 2 枚 | Codex imagegen | 約 5 分 | 各 1 回 |
| 5. 部品分け | Fable 5.2 | 約 16 分 ＋ 直し 約 2.5 分 | 1 回 ＋ 直し 1 回 |
| 6〜7. 検査・確認・調整 | Claude（メイン） | 約 20 分 | — |

- Codex imagegen は 1 枚あたり約 2〜2.5 分です。ChatGPT のプランの使用量の上限に達すると、数時間待つことがあります。1 キャラで必要なのは、正面 1〜2 回とシート 2 回です。
- Fable 5.2 の部品分けは、ほかの 2 キャラで約 22 分（49 部品）、約 24 分（61 部品）でした。
- 経緯を知らないエージェントがこの Skill だけで 1 体（63 部品）を作ったときは、角度の見本を飛ばして合計約 43 分でした（imagegen 4 回、Fable 1 回で約 24 分・約 28 万トークン、作り直し 0 回）。
- トークン数と金額は計測していません。

## 全体の流れ

| 段階 | 内容 | 道具 | 出力 |
|---|---|---|---|
| 1 | キャラの補足（残す特徴）を書く | 手書き | `tools/vector/sheets/characters/<id>.md`・`.json` |
| 2 | 原画を共通の画風に変換し、正面の A ポーズの立ち姿を作る | `make.py gen <id> restyle` | `ref/front.png` |
| 3 | 360 度回転動画からコマを切り出す（任意） | `turntable.sh <id>` | `ref/turntable.mp4`、`ref/angle_*.png` |
| 4 | シート 2 枚（4 面図＋手の形、顔の差分） | `make.py gen <id> sheet_turnaround`・`sheet_face` | `ref/sheet_turnaround.png`、`ref/sheet_face.png` |
| 5 | 塗りだけの部品を、隠れる部分まで補完して描く | Fable 5.2 ＋ `references/fable-brief.md` | `vector.json` |
| 6 | 構造の検査と、確認画像の目視 | `check_parts.py <id>` | エラー 0 件 |
| 7 | ビューアで動かして確認・調整する | `npm run dev`、`viewer_shots.mjs` | 調整した `vector.json` |
| 8 | 動画の書き出しと口パク | `record.mjs`、`lipsync.py` | MP4 |

`ref/` は `public/characters/<id>/vector/ref/` です。キャラ ID は小文字の英数字にします（例：`usagi`）。試行の画像や Fable の作業ファイルは `var/vector/<id>/` に溜まります（コミット対象外）。

## 1. キャラの補足を書く

`tools/vector/sheets/characters/<id>.md` に、**画風を変えても残すべき特徴**を箇条書きで書きます。`<id>.json` には原画のパスと、その画像の役割を書きます。原画は `inputs/<id>/` などに置きます。

- 書き方と見本は `references/character-notes.md` にあります。仮うさぎの例：`tools/vector/sheets/characters/usagi.md`・`usagi.json`。
- 色はおおよその値（`#RRGGBB`）で書きます。
- 共通の画風（`tools/vector/sheets/style_base.md`）は、キャラを「動物・生き物」として描かせます。そのままではキャラが変わってしまう点（毛のないキャラに毛の房が生える、人物でないキャラを動物に描き直す、など）は、補足に「〜は描かない」「〜は適用しない」と具体的に書いて打ち消します。共通の画風のファイルは変えません。
- 原画が動いたポーズ（体のひねり、腕の曲げ）でも、正面の A ポーズへの描き直しは `layouts/restyle.md` が指示します。補足には書かなくてよく、`<id>.json` の `roles` に「ポーズは参考にしない」と添えると安定します。

あわせて、ビューアにキャラを登録します。手順 5 で Fable がビューアで確かめるときに必要です。`data/characters/<id>.json`：

```json
{ "id": "<id>", "label": "<キャラ名>", "vector": { "url": "characters/<id>/vector/vector.json" } }
```

## 2. 正面の立ち姿（Codex imagegen）

```bash
.venv/bin/python tools/vector/sheets/make.py gen <id> restyle --count 2
.venv/bin/python tools/vector/sheets/make.py log <id>
.venv/bin/python tools/vector/sheets/make.py adopt <id> restyle <番号>
```

- プロンプトは「共通の画風＋キャラの補足＋描くもの（`layouts/restyle.md`）」を組み立てて、`codex exec` 経由で imagegen に渡します。試行は `var/vector/<id>/gen/` に、プロンプトと所要時間とともに残ります。
- **生成した画像は必ず目で見て**、原画と並べて比べます。見る点：キャラだと分かるか、2〜2.5 頭身か、真正面の A ポーズで脇に隙間があるか、目にハイライトがないか、寄り目でないか。
- 合わない場合は `--note "追加指示"` で直すか、キャラの補足を書き直します（例：仮うさぎは共通の「毛の量感」で別キャラに見えたため、補足で打ち消した）。直したことは補足に残します。
- `adopt` は採用した画像を `ref/front.png`（1024×1536）にそろえて置きます。

## 3. 角度の見本（任意：MiniMax H3）

```bash
bash tools/vector/sheets/turntable.sh <id>          # COMFY_SERVER で ComfyUI の URL を変えられる
```

- 先に `tools/vector/sheets/h3/<id>.txt`（回転動画のプロンプト）を、`h3/usagi.txt` をひな形にして書きます。キャラの説明の部分だけを差し替えます。
- 出力の `angle_045.png`・`angle_090.png`・`angle_180.png` は、4 のシートの生成で自動的に参照画像に加わります。H3 の回転は等速ではないので、角度は目安です。
- ComfyUI と H3 がない場合は、この段階を飛ばします。シートだけでも部品分けはできます。

## 4. キャラクターシート 2 枚（Codex imagegen）

```bash
.venv/bin/python tools/vector/sheets/make.py gen <id> sheet_turnaround
.venv/bin/python tools/vector/sheets/make.py adopt <id> sheet_turnaround 1
.venv/bin/python tools/vector/sheets/make.py gen <id> sheet_face
.venv/bin/python tools/vector/sheets/make.py adopt <id> sheet_face 1
```

- 1 枚目は 4 面図（正面・斜め・側面・背面）と手の形 4 種（開き・指差し・グー・手のひら）、2 枚目は顔の差分（目：開・半目・閉、口：閉・あ・い・う・え・お、表情：通常・笑顔・驚き・困り）です。
- 斜めと側面は、**顔が画面の左を向く**向きで描かせます（H3 の回転と同じ向き）。
- 目で見て、正面の立ち姿と同じキャラか、差分がそろっているか（半目で虹彩が潰れていないか、など）を確かめます。合わなければ `--note` で直して生成し直します。

## 5. 部品分け（Fable 5.2 のサブエージェント）

1. `references/fable-brief.md` のひな形に、キャラ ID・キャラ名・キャラごとの注意・ビューアの URL（既定 `http://127.0.0.1:5280/`）を差し込み、`var/vector/<id>/fable/brief.md` に保存します。キャラごとの注意の書き方と見本（仮うさぎ）は `references/character-notes.md` にあります。
2. **Fable 5.2 を指定したサブエージェント**を起動し、`brief.md` の全文を渡します。Fable は `references/parts-spec.md` に沿って、作画スクリプトで `public/characters/<id>/vector/vector.json` を作り、自分で検査してから報告します。
3. 報告を読み、6 の検査と 7 の確認を行います。直す点があれば、同じサブエージェントに続けて依頼します（新しく起動すると経緯を失います）。

守らせること（ひな形に書いてあります）：

- 部品は意味の単位で**ゼロから描く**。画素の切り抜き・自動トレースで形を決めない。
- **塗りだけで描く**。線は描画時に自動で引かれる。
- **隠れる部分も補完する**（前髪の下の額、耳の付け根の下の頭、腕を外した胴、首、しっぽの付け根など）。
- 腕の絵は描かない（描画時に生成する）。代わりに骨格の目印と腕の太さ・色を測って書く。
- `_L`・`_R` はキャラ自身の左右（正面図で `_L` は画面の右）。

## 6. 検査

```bash
.venv/bin/python tools/vector/check_parts.py <id>
```

- エラー 0 件で合格です。警告は内容を見て判断します。
- 確認画像（`var/vector/<id>/check/`）を**目で見ます**。見る点は `references/visual-qa.md` にあります。特に、手前の部品を隠した状態（`qa_*.png`）で穴・切り口がないか、差分（`variants.png`・`expressions.png`）がシートと合っているか、骨格（`skeleton.png`）の関節が絵と合っているか。
- 確認画像には、自動輪郭線と生成した腕が入りません。最終的な見え方は 7 で確かめます。

## 7. ビューアで動かす

1. `data/characters/<id>.json`（手順 1 で作成済み）があることを確かめます。
2. `npm run dev` で開発サーバーを起動し、`http://localhost:5280/?char=<id>` を開きます（キャラが 2 体以上あると、画面に選択欄が出ます）。
3. 撮影して確かめます（開発サーバーの起動中）：

   ```bash
   DSF=2 node tools/capture/viewer_shots.mjs var/vector/<id>/check/viewer \
     neutral="char=<id>" face30="char=<id>&framing=face&yaw=30&blink=0" faceM30="char=<id>&framing=face&yaw=-30&blink=0" \
     explain="char=<id>&motion=explain&t=1.0" spread="char=<id>&motion=spread&t=1.2" \
     half="char=<id>&framing=face&eye=half&blink=0" point="char=<id>&motion=point&t=1.5"
   ```

4. 見る点：白いキャラの部品の境目に余計な線が出ていないか、首振り ±30° で目が顔の輪郭の外へ出ないか、耳・髪の付け根が頭から離れないか、腕と手の太さ・色が合っているか、揺れ物の揺れ方。
5. 調整は `vector.json` の値で行います。URL のパラメーターで値を試してから書き込みます。調整できる値の一覧は `references/tuning.md`、よくある問題と対処は `references/troubleshooting.md` にあります。

## 8. 動画の書き出しと口パク

```bash
# 動画（開発サーバーの起動中）
node tools/vector/record.mjs --out out/<id>_explain --motion explain --query "char=<id>"

# 口パク：wav と読み（日本語はかな）から。TTS の種類は問わない
.venv/bin/python tools/lipsync/lipsync.py line.wav --text "こんにちは、よろしくおねがいします。" -o line.json
node tools/vector/record.mjs --out out/<id>_hello --motion talk_demo --lipsync line.json --audio line.wav --query "char=<id>"
```

- TTS がない場合は、テキストの口パクで動画を作れます：`node tools/vector/record.mjs --out out/<id>_hello --motion talk_demo --seconds 6 --query "char=<id>&say=こんにちは、よろしくね。"`。台詞は時計に合わせて繰り返され、動画の長さはモーションの長さ（ループしないモーションでは `--seconds`）で決まります。台詞の長さで止めたいときは `--seconds` を指定します（目安：1 モーラ 0.15 秒、句読点 0.3 秒）。
- 英語の台詞は `--lang en`、テキストなしで音量だけなら `--method rms`、Whisper の単語の時刻があれば `--whisper whisper.json`。
- 背景色は `--query "bg=ffd3e0"`、手描き風の線は `vHand=0〜4`（なし・弱・中・強・手描き＋。既定は強）。
- ビューアでも、口パクの JSON と音声ファイルを読み込んで再生できます。

## 終わったら

ユーザーに次を報告します。

- 作ったファイル（`ref/` の画像、`vector.json`、`data/characters/<id>.json`）と、確認画像・動画の場所
- 各段階の時間と、生成・作り直しの回数
- 検査結果と、残っている問題（自信のない部品、直しきれなかった見え方）
